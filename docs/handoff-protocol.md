# Handoff Protocol Spec

## Problem

`ChallengeStateMachine` emits `NEED_HANDOFF` when it detects a challenge (Cloudflare, login redirect,
CAPTCHA, etc.), but there is no human-in-the-loop path. Deleting `solve_turnstile` without a handoff
protocol turns "automated bypass" into "agent fails silently" — worse, not better.

## State machine

```
                  ┌─────────────────┐
                  │ agent detects   │
                  │ challenge       │
                  └────────┬────────┘
                           │
                  ┌────────▼────────┐
                  │ HandoffBroker   │
                  │ .create()       │──── stores HandoffRequest in ~/.bh-handoffs/
                  └────────┬────────┘
                           │
                  ┌────────▼────────┐
                  │ AccessResult    │
                  │ .handoff_id=... │──── returned to agent/caller
                  └────────┬────────┘
                           │
            ┌──────────────┼──────────────┐
            │              │              │
   ┌────────▼───────┐     │     ┌────────▼───────┐
   │ user runs CLI  │     │     │ user opens tab  │
   │ bh handoff <id>│     │     │ manually        │
   └────────┬───────┘     │     └────────┬───────┘
            │              │              │
   ┌────────▼───────┐     │     ┌────────▼───────┐
   │ browser opens  │     │     │ user completes  │
   │ to challenge   │     │     │ challenge in     │
   │ URL            │     │     │ existing tab     │
   └────────┬───────┘     │     └────────┬───────┘
            │              │              │
   ┌────────▼───────┐     │     ┌────────▼───────┐
   │ user completes │     │     │ user signals    │
   │ challenge      │     │     │ done via CLI    │
   └────────┬───────┘     │     └────────┬───────┘
            │              │              │
            └──────────────┼──────────────┘
                           │
                  ┌────────▼────────┐
                  │ HandoffBroker   │
                  │ .complete()     │──── signs ResumeToken with HMAC
                  └────────┬────────┘
                           │
                  ┌────────▼────────┐
                  │ SessionBroker   │
                  │ .store_bundle() │──── reads new cookies after user completed
                  └────────┬────────┘
                           │
                  ┌────────▼────────┐
                  │ agent retries   │
                  │ with resume     │──── AccessPlane checks resume token + session
                  └─────────────────┘
```

## Data structures

```python
@dataclass
class HandoffRequest:
    handoff_id: str          # unique ID (hex)
    origin: str              # e.g. "https://www.doordash.com"
    url: str                 # the URL that triggered the challenge
    challenge_kind: str      # "cloudflare", "login_redirect", "captcha", etc.
    created_at: float        # unix timestamp
    expires_at: float        # created_at + 300 (5 minutes default)

@dataclass
class ResumeToken:
    origin: str
    account_id: str
    session_ref_id: str      # ref to the SessionBroker bundle created after completion
    completed_at: float
    expires_at: float
    nonce: str               # random hex, prevents replay
    signature: bytes         # HMAC-SHA256 of the above fields

class HandoffBroker:
    def __init__(self, store_dir: Path | None = None):
        # store_dir defaults to ~/.bh-handoffs/ with 0o700 permissions
        ...

    def create(self, url: str, origin: str, challenge_kind: str,
               ttl: float = 300.0) -> HandoffRequest:
        """Create a pending handoff. Stores to disk."""

    def get(self, handoff_id: str) -> HandoffRequest | None:
        """Retrieve a pending handoff."""

    def complete(self, handoff_id: str, account_id: str = "",
                 session_ref_id: str = "") -> ResumeToken:
        """Mark handoff complete, sign resume token, clean up request file."""

    def consume(self, token_bytes: bytes) -> ResumeToken | None:
        """Validate HMAC signature and return token if valid + not expired.
        Does NOT revoke — tokens are single-use within their TTL."""

    def _sign(self, token: ResumeToken) -> bytes:
        """HMAC-SHA256 using a per-session key derived from store_dir path."""

    def _verify(self, token_bytes: bytes) -> bool:
        """Verify HMAC signature."""
```

## Storage format

Each pending handoff is a JSON file in `~/.bh-handoffs/`:

```
~/.bh-handoffs/
  <handoff_id>.json    # pending handoff request
```

File format:
```json
{
  "handoff_id": "a1b2c3...",
  "origin": "https://www.doordash.com",
  "url": "https://www.doordash.com/v2/merchant/123",
  "challenge_kind": "cloudflare",
  "created_at": 1715174400.0,
  "expires_at": 1715174700.0
}
```

Permissions: `0o600`. Created with `os.umask(0o077)`.

HMAC key: derived from `hashlib.sha256(store_dir.stat().st_ino.to_bytes(8, 'big') + os.getuid().to_bytes(4, 'big')).digest()`.
Tied to the filesystem location and user, not to a process.

## CLI interface

```bash
browser-harness handoff <handoff_id>
```

Behavior:
1. Load handoff request from `~/.bh-handoffs/<handoff_id>.json`
2. Ensure daemon is alive
3. Open a new tab to `request.url`
4. Print: "Complete the challenge in the browser, then press Enter..."
5. Wait for Enter keypress
6. Capture browser cookies for `request.origin` via `SessionBroker.store_secret_bundle`
7. Call `HandoffBroker.complete()` with the session ref
8. Print resume token (or store it for automatic consumption)
9. Close the challenge tab

## Integration with AccessPlane

When `AccessPlane.execute()` encounters a challenge:

```python
# In AccessPlane._try_* methods, after detecting a blocked response:
if challenge.status == ChallengeStatus.NEED_HANDOFF:
    handoff = self._handoff_broker.create(
        url=request.url,
        origin=origin,
        challenge_kind=challenge.kind.value,
    )
    return AccessResult(
        url=request.url,
        status=403,
        reason="handoff required",
        block_state=ChallengeStatus.NEED_HANDOFF,
        extra={"handoff_id": handoff.handoff_id},
    )
```

When a caller provides a resume token:

```python
# New parameter on AccessPlane.execute:
def execute(self, request: WebRequest, resume_token: bytes | None = None) -> AccessResult:
    if resume_token:
        token = self._handoff_broker.consume(resume_token)
        if token and token.origin == self._origin(request.url):
            # Use the stored session for this request
            ...
```

## Test plan

`tests/test_handoff.py`:
1. `test_create_handoff_stores_request` — broker creates, file exists on disk
2. `test_get_handoff_returns_request` — round-trip through disk
3. `test_complete_signs_resume_token` — HMAC validates
4. `test_consume_valid_token` — token round-trips
5. `test_consume_expired_token` — returns None
6. `test_consume_tampered_token` — HMAC fails, returns None
7. `test_consume_wrong_origin` — token signed for different origin, fails
8. `test_handoff_request_expires` — get() returns None for expired
9. `test_access_plane_produces_handoff_id` — blocked fetch returns handoff_id in extra
10. `test_access_plane_consumes_resume_token` — fetch with valid token uses stored session
