"""HTTP client for gemini.google.com.

Endpoint surface (mapped via Camoufox network capture, 2026-05):

* All authenticated chat operations go through Google's batchexecute RPC:
  ``POST /_/BardChatUi/data/batchexecute?rpcids=<id>&bl=<bl>&f.sid=<sid>&_reqid=<n>&rt=c``

* Bootstrap params (``bl``, ``f.sid``, ``at``) live in the ``/app`` HTML
  inside ``WIZ_global_data`` (``cfb2h`` / ``FdrFJe``) and the ``SNlM0e``
  variable. They're per-session and must be fetched once before any RPC.

* RPC ids used by the archiver:
    - ``MaZiqc`` — paginated chat inventory.
        request: ``[<page_size>, "<cursor or null>", [<flag1>, null, 1]]``
                 (flag1: 1 means "include all", 0 means "exclude pinned"
                  observed during the page-1 + page-2 sweep)
        response: ``[<chats>, ...]`` where each chat is
            ``["c_<hex>", "<title>", null, null, null, [unix_seconds, nanos],
              [["c_<hex>", "r_<hex>"], 0], null, null, 4]``
    - ``hNvQHb`` — full thread detail (returns ~all turns at once).
        request: ``["c_<chat_id>", 10, null, 1, [1], [4], null, 1]``
        response: deeply nested array with per-turn user query + assistant
            response objects.

Wire format response shape:
    "" )]}'\n\n<len>\n<chunk_json>\n<len>\n<chunk_json>\n... ""
where each ``<chunk_json>`` is a list of envelopes:
    ``[["wrb.fr", "<rpc_id>", "<inner_json_string>", null, null, null, "generic"], ...]``
The inner JSON string is itself JSON — double-decode.

Cookies: ``__Secure-1PSID`` + ``SAPISID`` on ``.google.com`` are the load-
bearing pair. ``cf_clearance`` is not used (no Cloudflare in front). Camoufox
runs to discover endpoints; sync runs use plain HTTPS once bootstrap is done.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


GEMINI_BASE = "https://gemini.google.com"


# Regexes to pluck bootstrap values out of /app HTML. Brittle but simple;
# update if Google reshapes the page bundle.
_RE_AT = re.compile(r'"SNlM0e":"([^"]+)"')
_RE_BL = re.compile(r'"cfb2h":"([^"]+)"')
_RE_SID = re.compile(r'"FdrFJe":"(-?\d+)"')


class GeminiBootstrapError(RuntimeError):
    """Raised when /app HTML can't be parsed for bootstrap params."""


def _cookie_domain(cookies: Any, domain: str) -> dict:
    if not isinstance(cookies, dict):
        return {}
    jar = cookies.get(domain)
    return jar if isinstance(jar, dict) else {}


def _is_numeric_timestamp(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


class GeminiHTTPAPI:
    def __init__(self, cookies_by_domain: dict[str, dict[str, str]]):
        self._cookies = cookies_by_domain
        self._user_agent = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        )
        self._at: str | None = None
        self._bl: str | None = None
        self._sid: str | None = None
        self._reqid = int(time.time() % 100000) * 10
        self._authenticated = False

    # --- cookie / header plumbing ---------------------------------------

    def _cookie_header(self) -> str:
        parts: list[str] = []
        # Order matters less than coverage: include every google-domain cookie
        # we have; the server tolerates duplicates and chooses the most
        # specific scope.
        for domain in (
            ".google.com", "google.com",
            "gemini.google.com", ".gemini.google.com",
            "accounts.google.com", ".accounts.google.com",
        ):
            for k, v in _cookie_domain(self._cookies, domain).items():
                parts.append(f"{k}={v}")
        return "; ".join(parts)

    def _headers(self, content_type: str | None = None) -> dict[str, str]:
        h = {
            "Cookie": self._cookie_header(),
            "User-Agent": self._user_agent,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{GEMINI_BASE}/app",
            "Origin": GEMINI_BASE,
            "X-Same-Domain": "1",
        }
        if content_type:
            h["Content-Type"] = content_type
        return h

    # --- bootstrap ------------------------------------------------------

    def authenticate(self) -> dict:
        """Fetch /app HTML and extract SNlM0e / cfb2h / FdrFJe.

        Returns ``{authenticated: bool, ...}``. We can't extract a usable
        email/name from the page bundle without an extra RPC, so the label
        falls back to a SAPISID-derived fingerprint (handled by the
        provider, not here)."""
        try:
            req = urllib.request.Request(f"{GEMINI_BASE}/app", headers=self._headers())
            resp = urllib.request.urlopen(req, timeout=30)
            html = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            return {"authenticated": False, "error": f"HTTP {e.code}"}
        except Exception as e:
            return {"authenticated": False, "error": str(e)[:200]}

        m_at = _RE_AT.search(html)
        m_bl = _RE_BL.search(html)
        m_sid = _RE_SID.search(html)
        if not (m_at and m_bl and m_sid):
            return {
                "authenticated": False,
                "error": "bootstrap params missing — likely logged out or page reshaped",
                "have_at": bool(m_at),
                "have_bl": bool(m_bl),
                "have_sid": bool(m_sid),
            }
        self._at = m_at.group(1)
        self._bl = m_bl.group(1)
        self._sid = m_sid.group(1)
        self._authenticated = True
        # No identity data extracted here — the provider derives a label
        # from SAPISID instead.
        return {"authenticated": True, "at": self._at[:8], "bl": self._bl, "sid": self._sid}

    # --- RPC ------------------------------------------------------------

    def _rpc(self, rpc_id: str, payload: list) -> Any:
        """Call one batchexecute RPC and return the inner payload (already
        double-decoded). Raises on transport / parse failure."""
        if not self._authenticated:
            raise RuntimeError("call authenticate() first")
        self._reqid += 1
        params = {
            "rpcids": rpc_id,
            "source-path": "/app",
            "bl": self._bl,
            "f.sid": self._sid,
            "hl": "en-US",
            "_reqid": str(self._reqid),
            "rt": "c",
        }
        url = f"{GEMINI_BASE}/_/BardChatUi/data/batchexecute?{urllib.parse.urlencode(params)}"
        # Inner payload is JSON-encoded as a string within the outer envelope.
        envelope = [[[rpc_id, json.dumps(payload), None, "generic"]]]
        body = urllib.parse.urlencode({
            "f.req": json.dumps(envelope),
            "at": self._at,
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=body,
            headers=self._headers("application/x-www-form-urlencoded;charset=UTF-8"),
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=60)
            raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"gemini RPC {rpc_id}: HTTP {e.code} {e.read()[:200]!r}")
        return _parse_batchexecute(raw, rpc_id)

    # --- public surface --------------------------------------------------

    def list_chats_page(
        self, *,
        page_size: int = 20,
        cursor: str | None = None,
        flag1: int = 0,
    ) -> tuple[list[dict], str | None]:
        """One page of chats. Returns ``(chats, next_cursor)`` where
        ``next_cursor`` is None if exhausted.

        ``flag1=0`` excludes pinned/hidden, ``flag1=1`` includes them — the
        observed UI sweep uses both; we default to 0 for the inventory pass.

        Decoded MaZiqc payload shape (Camoufox capture, 2026-05)::

            [null, "<next_cursor>", [<chats>...], ...]

        where each ``<chat>`` is::

            ["c_<hex>", "<title>", null, null, null, [unix_seconds, nanos],
             [["c_<hex>", "r_<hex>"], 0]?, null, null, 4]
        """
        payload = [page_size, cursor, [flag1, None, 1]]
        decoded = self._rpc("MaZiqc", payload)
        if not isinstance(decoded, list):
            return [], None
        next_cursor = decoded[1] if len(decoded) > 1 and isinstance(decoded[1], str) else None
        chats_raw = decoded[2] if len(decoded) > 2 and isinstance(decoded[2], list) else []
        chats: list[dict] = []
        for entry in chats_raw:
            if not isinstance(entry, list) or len(entry) < 6:
                continue
            chat_id = entry[0] if isinstance(entry[0], str) else None
            title = entry[1] if isinstance(entry[1], str) else ""
            ts = entry[5] if len(entry) > 5 and isinstance(entry[5], list) else None
            updated_unix = ts[0] if ts and _is_numeric_timestamp(ts[0]) else None
            response_pair = entry[6] if len(entry) > 6 and isinstance(entry[6], list) else None
            response_id = None
            if isinstance(response_pair, list) and response_pair:
                inner = response_pair[0]
                if isinstance(inner, list) and len(inner) >= 2:
                    response_id = inner[1]
            if not chat_id:
                continue
            chats.append({
                "chat_id": chat_id,
                "title": title,
                "updated_unix": updated_unix,
                "response_id": response_id,
                "raw": entry,
            })
        return chats, next_cursor

    def all_chats(self, *, page_size: int = 50, max_pages: int = 200) -> list[dict]:
        out: list[dict] = []
        cursor: str | None = None
        seen: set[str] = set()
        for _ in range(max_pages):
            page, cursor = self.list_chats_page(page_size=page_size, cursor=cursor)
            new = 0
            for c in page:
                if c["chat_id"] in seen:
                    continue
                seen.add(c["chat_id"])
                out.append(c)
                new += 1
            if not cursor or new == 0:
                break
        return out

    def chat_detail(self, chat_id: str) -> dict | None:
        """Full thread detail. Returns the decoded RPC payload directly so
        the provider's extractor can walk it — the structure is deep and
        not worth re-shaping here."""
        payload = [chat_id, 10, None, 1, [1], [4], None, 1]
        try:
            decoded = self._rpc("hNvQHb", payload)
        except Exception:
            return None
        if not isinstance(decoded, list):
            return None
        return {"chat_id": chat_id, "raw": decoded}

    # --- extractors -----------------------------------------------------
    #
    # ``hNvQHb`` decoded payload shape (Camoufox capture, 2026-05)::
    #
    #     [<turns_list>, null, null, [...]]
    #
    # ``<turns_list>`` is a list of turn arrays, **most-recent first**.
    # Each turn looks like::
    #
    #     [
    #       [chat_id, response_id],          # 0: ids
    #       [..., ..., ...],                 # 1: misc role/header (ignored)
    #       [[<user_text>], 4, ..., user_msg_id, ...],   # 2: user block
    #       [[<assistant_block>], None, None, rc_id, ...], # 3: assistant block
    #       [unix_seconds, nanos],           # 4: turn timestamp
    #     ]
    #
    # ``<assistant_block>`` is itself ``[rc_id, [assistant_text], [...flags...], ...]``.
    # Image-generation turns put ``http://googleusercontent.com/...`` URLs in
    # ``[assistant_text]``; deep-research turns put the full markdown answer
    # there alongside many embedded ``http(s)://`` references.

    @staticmethod
    def _user_text(turn: list) -> str:
        try:
            blk = turn[2]
            if isinstance(blk, list) and blk:
                ut = blk[0]
                if isinstance(ut, list) and ut and isinstance(ut[0], str):
                    return ut[0]
        except Exception:
            pass
        return ""

    @staticmethod
    def _assistant_block(turn: list) -> list | None:
        # turn[3] = [[<response_array>], ...]
        # turn[3][0] = [<response_array>]
        # turn[3][0][0] = response_array = [rc_id, [text], [flags...], ...]
        try:
            blk = turn[3]
            if isinstance(blk, list) and blk and isinstance(blk[0], list) and blk[0]:
                inner = blk[0][0]
                if isinstance(inner, list) and inner:
                    return inner
        except Exception:
            return None
        return None

    @classmethod
    def _assistant_text(cls, turn: list) -> str:
        inner = cls._assistant_block(turn)
        if not inner:
            return ""
        try:
            text_block = inner[1]
            if isinstance(text_block, list) and text_block and isinstance(text_block[0], str):
                return text_block[0]
        except Exception:
            pass
        return ""

    @staticmethod
    def _ids(turn: list) -> tuple[str, str]:
        try:
            ids = turn[0]
            if isinstance(ids, list) and len(ids) >= 2:
                return str(ids[0] or ""), str(ids[1] or "")
        except Exception:
            pass
        return "", ""

    @staticmethod
    def _ts(turn: list) -> int | None:
        try:
            ts = turn[4]
            if isinstance(ts, list) and ts and _is_numeric_timestamp(ts[0]):
                return int(ts[0])
        except Exception:
            pass
        return None

    @staticmethod
    def _user_msg_id(turn: list) -> str:
        try:
            blk = turn[2]
            if isinstance(blk, list) and len(blk) > 4 and isinstance(blk[4], str):
                return blk[4]
        except Exception:
            pass
        return ""

    @staticmethod
    def _assistant_msg_id(inner: list | None) -> str:
        if not inner:
            return ""
        try:
            if isinstance(inner[0], str):
                return inner[0]
        except Exception:
            pass
        return ""

    @classmethod
    def extract_messages(cls, detail: dict) -> list[dict]:
        """One entry per turn → user message + assistant message (in that
        order). Turns are reversed so the output is chronological."""
        raw = detail.get("raw") if isinstance(detail, dict) else None
        if not isinstance(raw, list) or not raw or not isinstance(raw[0], list):
            return []
        turns = list(raw[0])
        turns.reverse()  # API returns newest-first; archive wants oldest-first
        messages: list[dict] = []
        for turn in turns:
            chat_id, response_id = cls._ids(turn)
            ts = cls._ts(turn)
            user_text = cls._user_text(turn)
            user_id = cls._user_msg_id(turn)
            if user_text:
                messages.append({
                    "role": "user",
                    "content": user_text,
                    "ordinal": len(messages) + 1,
                    "provider_message_id": user_id or f"{response_id}:q",
                    "content_type": "text",
                    "rich_parts": [],
                    "artifact_refs": [],
                    "metadata": {"response_id": response_id, "ts": ts},
                })
            inner = cls._assistant_block(turn)
            asst_text = cls._assistant_text(turn)
            asst_id = cls._assistant_msg_id(inner)
            if asst_text or inner:
                # artifact_refs: pull obvious googleusercontent.com URLs out
                # of the assistant block. Deep-research turns embed many
                # http URLs deeper down; we leave those inline in content
                # rather than fabricating dozens of ref entries here.
                refs: list[dict] = []
                if isinstance(inner, list) and len(inner) > 1:
                    text_block = inner[1]
                    if isinstance(text_block, list):
                        for tb in text_block:
                            if isinstance(tb, str) and tb.startswith("http") and "googleusercontent.com" in tb:
                                refs.append({"type": "image_url", "url": tb})
                messages.append({
                    "role": "assistant",
                    "content": asst_text,
                    "ordinal": len(messages) + 1,
                    "provider_message_id": asst_id or f"{response_id}:a",
                    "content_type": "text",
                    "rich_parts": [],
                    "artifact_refs": refs,
                    "metadata": {"response_id": response_id, "ts": ts, "rc_id": asst_id},
                })
        return messages

    @classmethod
    def extract_citations(cls, detail: dict) -> list[dict]:
        """Gemini surfaces citations differently per response mode and the
        structures are deeply nested. For now we don't synthesize a sources
        section: the assistant text already contains inline links, and any
        future structured-citation pass can re-walk ``normalized_json``.
        """
        return []


# ---------------------------------------------------------------------------
# Wire-format parsing helpers
# ---------------------------------------------------------------------------


_PREFIX = ")]}'"


def _parse_batchexecute(raw: str, rpc_id: str) -> Any:
    """Decode a batchexecute response and return the inner payload for ``rpc_id``.

    Format::

        )]}'
        <length>
        <chunk_json>
        <length>
        <chunk_json>
        ...

    Each ``<chunk_json>`` is a JSON list of envelopes. The ``<length>``
    prefix is meant to bound the chunk but Google's wire format is loose —
    sometimes it counts code points, sometimes UTF-8 bytes, and the offset
    has occasionally been observed off-by-one. Rather than trust the count,
    we use ``json.JSONDecoder.raw_decode`` to consume one valid JSON value
    at a time, advancing past whitespace and digit prefixes between values.

    Each envelope of interest looks like
    ``["wrb.fr", "<rpc_id>", "<inner_json>", null, null, null, "generic"]``;
    the ``<inner_json>`` is itself JSON-encoded — we double-decode it.
    """
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if not raw.startswith(_PREFIX):
        raise RuntimeError(f"batchexecute response missing magic prefix: {raw[:40]!r}")
    decoder = json.JSONDecoder()
    body = raw[len(_PREFIX):]
    i = 0
    n = len(body)
    while i < n:
        # Skip whitespace and any leading length-prefix digits.
        while i < n and (body[i].isspace() or body[i].isdigit()):
            i += 1
        if i >= n:
            break
        try:
            envelopes, end = decoder.raw_decode(body, i)
        except json.JSONDecodeError:
            # Skip this character and resync; protects against unexpected separators.
            i += 1
            continue
        i = end
        for env in envelopes if isinstance(envelopes, list) else []:
            if (
                isinstance(env, list) and len(env) >= 3
                and env[0] == "wrb.fr" and env[1] == rpc_id
                and isinstance(env[2], str)
            ):
                try:
                    return json.loads(env[2])
                except Exception:
                    return env[2]
    raise RuntimeError(f"batchexecute: rpc_id {rpc_id!r} not found in response")
