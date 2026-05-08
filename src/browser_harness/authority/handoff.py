"""Handoff protocol — human-in-the-loop for challenge resolution.

When ChallengeStateMachine emits NEED_HANDOFF, this module manages the
handoff lifecycle: create pending requests, persist to disk, sign resume
tokens after user completion, and validate tokens on retry.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class HandoffRequest:
    handoff_id: str
    origin: str
    url: str
    challenge_kind: str
    created_at: float
    expires_at: float


@dataclass
class ResumeToken:
    origin: str
    account_id: str
    session_ref_id: str
    completed_at: float
    expires_at: float
    nonce: str
    signature: bytes = b""

    def to_bytes(self) -> bytes:
        d = asdict(self)
        d["signature"] = d["signature"].hex() if isinstance(d["signature"], bytes) else d["signature"]
        return json.dumps(d, sort_keys=True).encode()

    @classmethod
    def from_bytes(cls, data: bytes) -> ResumeToken:
        d = json.loads(data)
        d["signature"] = bytes.fromhex(d["signature"]) if isinstance(d["signature"], str) else d["signature"]
        return cls(**d)


class HandoffBroker:
    """Manage handoff requests and resume tokens."""

    _SAFE_ID = re.compile(r"^[0-9a-f]{1,32}$")

    def __init__(self, store_dir: Path | None = None):
        self._store_dir = store_dir or Path(
            os.environ.get("BH_HANDOFFS_DIR", os.path.expanduser("~/.bh-handoffs"))
        )
        self._store_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(str(self._store_dir), 0o700)

    def create(
        self,
        url: str,
        origin: str,
        challenge_kind: str,
        ttl: float = 300.0,
    ) -> HandoffRequest:
        now = time.time()
        request = HandoffRequest(
            handoff_id=uuid.uuid4().hex[:16],
            origin=origin,
            url=url,
            challenge_kind=challenge_kind,
            created_at=now,
            expires_at=now + ttl,
        )
        path = self._store_dir / f"{request.handoff_id}.json"
        path.write_text(json.dumps(asdict(request), indent=2))
        os.chmod(str(path), 0o600)
        return request

    def get(self, handoff_id: str) -> HandoffRequest | None:
        if not self._SAFE_ID.match(handoff_id):
            return None
        path = self._store_dir / f"{handoff_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            request = HandoffRequest(**data)
        except (json.JSONDecodeError, TypeError):
            return None
        if time.time() > request.expires_at:
            return None
        return request

    def complete(
        self,
        handoff_id: str,
        account_id: str = "",
        session_ref_id: str = "",
        ttl: float = 3600.0,
    ) -> ResumeToken | None:
        if not self._SAFE_ID.match(handoff_id):
            return None
        request = self.get(handoff_id)
        if not request:
            return None

        now = time.time()
        token = ResumeToken(
            origin=request.origin,
            account_id=account_id,
            session_ref_id=session_ref_id,
            completed_at=now,
            expires_at=now + ttl,
            nonce=uuid.uuid4().hex[:16],
        )

        sig = self._sign(token)
        token = ResumeToken(
            origin=token.origin,
            account_id=token.account_id,
            session_ref_id=token.session_ref_id,
            completed_at=token.completed_at,
            expires_at=token.expires_at,
            nonce=token.nonce,
            signature=sig,
        )

        # Clean up the pending request
        path = self._store_dir / f"{handoff_id}.json"
        if path.exists():
            path.unlink()

        return token

    def consume(self, token_bytes: bytes) -> ResumeToken | None:
        try:
            token = ResumeToken.from_bytes(token_bytes)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None
        if not self._verify(token):
            return None
        if time.time() > token.expires_at:
            return None
        return token

    def _sign(self, token: ResumeToken) -> bytes:
        key = self._derive_key()
        unsigned = ResumeToken(
            origin=token.origin,
            account_id=token.account_id,
            session_ref_id=token.session_ref_id,
            completed_at=token.completed_at,
            expires_at=token.expires_at,
            nonce=token.nonce,
            signature=b"",
        )
        return hmac.new(key, unsigned.to_bytes(), hashlib.sha256).digest()

    def _verify(self, token: ResumeToken) -> bool:
        key = self._derive_key()
        expected = self._sign(ResumeToken(
            origin=token.origin,
            account_id=token.account_id,
            session_ref_id=token.session_ref_id,
            completed_at=token.completed_at,
            expires_at=token.expires_at,
            nonce=token.nonce,
            signature=b"",
        ))
        return hmac.compare_digest(expected, token.signature)

    def _derive_key(self) -> bytes:
        try:
            ino = self._store_dir.stat().st_ino.to_bytes(8, "big")
        except OSError:
            ino = b"\x00" * 8
        uid = os.getuid().to_bytes(4, "big")
        return hashlib.sha256(ino + uid + b"bh-handoff-hmac").digest()
