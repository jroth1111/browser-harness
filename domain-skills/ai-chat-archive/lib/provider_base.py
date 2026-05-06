"""Provider plugin contract for the AI chat archive.

A Provider implementation knows how to talk to one chat service (ChatGPT,
Claude, Gemini, Grok, Perplexity, ...). The generic sync runner in
``sync_runner`` drives every provider through the same lifecycle:

    probe_login → inventory → capture_thread → capture_artifacts

Providers are stateless: they receive a ``ProviderContext`` per call carrying
cookies, optional browser-harness callables, and a SQLite connection for
delta lookups. State (cursors, last-seen ids) lives in the ``sync_state``
table keyed by ``(provider_id, account_key, cursor_name)`` so a provider can
resume between runs without holding instance state.

The contract is intentionally narrow: anything that requires per-provider
schema (rich content blobs, tool calls, deep research markers) flows through
the ``CapturedThread.normalized_json`` payload, which the sync runner stores
verbatim so we can re-render or re-extract without recapturing the surface.
"""
from __future__ import annotations

import abc
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator, Protocol


class JSCallable(Protocol):
    def __call__(self, expression: str) -> Any: ...


class AXCallable(Protocol):
    def __call__(self, *, compact: bool = True) -> list[str] | None: ...


class ClickRefCallable(Protocol):
    def __call__(self, ref: str) -> Any: ...


class ScrollCallable(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


@dataclass
class BrowserHarness:
    """Bundle of optional browser-side callables.

    A provider that can run purely over HTTP cookies (e.g. ChatGPT backend
    API) leaves these unset. A DOM-only provider (e.g. Gemini) requires all
    four. The runner is responsible for enforcing what each provider declares
    in ``Provider.capabilities``.
    """

    js: JSCallable | None = None
    ax: AXCallable | None = None
    click_ref: ClickRefCallable | None = None
    scroll: ScrollCallable | None = None
    navigate: Callable[[str], Any] | None = None
    take_screenshot: Callable[..., Any] | None = None


@dataclass
class AccountContext:
    """Result of ``probe_login``: identity proven by the supplied cookies.

    ``account_key`` is the durable hash used as the foreign key in
    ``threads``/``messages``/``cookie_jars``. ``account_label`` is what the
    user sees (email, handle, workspace name) — never raw secrets.
    """

    account_key: str
    account_label: str
    raw_identity: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderContext:
    """Per-call context handed to every provider method."""

    provider_id: str
    cookies_by_domain: dict[str, dict[str, str]]
    db: sqlite3.Connection
    account: AccountContext | None = None
    harness: BrowserHarness | None = None
    run_id: str | None = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class ThreadStub:
    """Lightweight thread descriptor returned by ``inventory``.

    The runner uses ``thread_key`` to dedupe against the archive and decide
    which threads to fetch in full. ``updated_at`` (provider-supplied epoch
    seconds or ISO string) drives incremental sync; if absent, every listed
    thread is treated as a candidate.
    """

    thread_key: str
    provider_thread_id: str | None
    canonical_url: str | None
    title: str
    updated_at: float | str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class CapturedMessage:
    role: str
    content: str
    ordinal: int
    provider_message_id: str | None = None
    content_type: str | None = None
    rich_parts: list[dict[str, Any]] = field(default_factory=list)
    artifact_refs: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CapturedArtifact:
    artifact_type: str
    label: str
    provider_artifact_id: str | None = None
    source_url: str | None = None
    parent_message_id: str | None = None
    mime_type: str | None = None
    byte_length: int | None = None
    content_hash: str | None = None
    storage_kind: str = "metadata"  # 'metadata' | 'inline_blob' | 'external_ref'
    rich_part: dict[str, Any] | None = None
    bytes: bytes | None = None  # populated by capture_artifacts when downloaded


@dataclass
class CapturedCitation:
    label: str | None
    url: str | None
    source_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class CapturedThread:
    """Result of ``capture_thread``: full normalized snapshot of one thread.

    ``normalized_json`` is the provider-specific raw payload (mapping tree,
    Claude conversation JSON, Gemini batchexecute response, ...). The runner
    stores this verbatim in ``captures.normalized_json`` so we can re-render
    or re-extract artifacts later without recapturing.

    ``rendered_markdown`` is the canonical text view used for FTS, hashing,
    and human export. ``completion_state`` reports whether the thread was
    captured fully (all messages + artifacts) or partially.
    """

    stub: ThreadStub
    messages: list[CapturedMessage]
    artifacts: list[CapturedArtifact]
    citations: list[CapturedCitation]
    normalized_json: dict[str, Any]
    rendered_markdown: str
    completion_state: str = "complete"  # 'complete' | 'partial' | 'failed'
    capture_notes: dict[str, Any] = field(default_factory=dict)


class Provider(abc.ABC):
    """Base class for all chat-service plugins.

    Subclasses declare four pieces of static metadata and four behaviors.
    All behaviors are synchronous — the runner is single-threaded per
    account because providers are bound by the same per-account auth
    rate-limit budget anyway.
    """

    #: Stable short id used as the FK in providers/threads/cookie_jars.
    provider_id: str = ""

    #: Human label shown in CLIs, exports, and the UI.
    display_name: str = ""

    #: Cookie domains this provider needs (used by harvest to filter jars).
    cookie_domains: list[str] = []

    #: What this provider needs from the harness.
    #: One of {'http', 'dom', 'http+dom'}. 'http' = pure cookie/HTTP;
    #: 'dom' = needs js/ax/click_ref/scroll; 'http+dom' = HTTP for inventory,
    #: DOM for artifact bytes (the ChatGPT pattern).
    capabilities: str = "http"

    # --- lifecycle -------------------------------------------------------

    @abc.abstractmethod
    def probe_login(self, ctx: ProviderContext) -> AccountContext | None:
        """Verify the cookies authenticate. Return identity or None.

        Must NOT raise on auth failure — return None and let the runner mark
        the cookie jar ``failed``. Raise only on transport errors the caller
        should retry (Cloudflare 5xx, network down)."""

    @abc.abstractmethod
    def inventory(
        self,
        ctx: ProviderContext,
        *,
        since: float | str | None = None,
        limit: int | None = None,
    ) -> Iterator[ThreadStub]:
        """Stream thread stubs for the authenticated account.

        ``since`` is an opaque cursor the provider previously stored via
        ``sync_state`` (e.g. ``updated_at`` of the newest thread last run).
        Yield in newest-first order so the runner can stop early once it
        sees an unchanged thread."""

    @abc.abstractmethod
    def capture_thread(
        self, ctx: ProviderContext, stub: ThreadStub,
    ) -> CapturedThread:
        """Fetch and normalize one full thread.

        Implementations should mark ``completion_state='partial'`` and
        record the gap in ``capture_notes`` rather than raising on
        partial-capture conditions (paginated tail not loaded, artifact
        body unreachable, etc.). Raise only when the thread cannot be
        captured at all (404, 403)."""

    def capture_artifacts(
        self,
        ctx: ProviderContext,
        thread: CapturedThread,
    ) -> Iterable[CapturedArtifact]:
        """Optionally download artifact bodies for the captured thread.

        Default implementation is a no-op: providers without downloadable
        artifacts (or where ``capture_thread`` already inlined them) skip
        this step. Yield artifacts with ``bytes`` populated; the runner
        will store them via ``store_artifact_blob``. Artifact metadata
        without bytes is already stored by ``capture_thread`` — re-yielding
        is fine, the runner upserts by content hash."""
        return ()

    # --- helpers (overridable) ------------------------------------------

    def cursor_name(self) -> str:
        """Name used in sync_state for the inventory cursor."""
        return "inventory_updated_at"

    def thread_key_for(self, provider_thread_id: str) -> str:
        """Override only if the provider's thread ids aren't globally unique."""
        from .archive_db import compute_thread_key
        return compute_thread_key(self.provider_id, provider_thread_id)
