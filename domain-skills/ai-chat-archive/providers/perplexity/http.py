"""HTTP client for perplexity.ai.

Surface notes:
* ``/api/auth/session`` is a standard NextAuth endpoint and reliably returns
  ``{user: {email, name, ...}, expires}`` for a logged-in session cookie.
* Library inventory and thread detail use undocumented internal REST
  endpoints under ``/rest/`` that drift between releases. We try the most
  recent shape and return an empty list/None on shape mismatch — the
  provider then reports zero captures rather than crashing the run.

Cookies:
* ``__Secure-next-auth.session-token`` on ``.perplexity.ai`` is the only
  required cookie for ``/api/auth/session``. Library/detail endpoints may
  also require ``cf_clearance`` — present in any browser-issued jar.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


PPLX_BASE = "https://www.perplexity.ai"


def _dict_rows(rows: Any) -> list[dict]:
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _cookie_domain(cookies: Any, domain: str) -> dict:
    if not isinstance(cookies, dict):
        return {}
    jar = cookies.get(domain)
    return jar if isinstance(jar, dict) else {}


class PerplexityHTTPAPI:
    def __init__(self, cookies_by_domain: dict[str, dict[str, str]]):
        self._cookies = cookies_by_domain
        self._user_agent = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        )
        self._user: dict[str, Any] | None = None

    def _cookie_header(self) -> str:
        parts: list[str] = []
        for domain in (".perplexity.ai", "perplexity.ai", "www.perplexity.ai"):
            for k, v in _cookie_domain(self._cookies, domain).items():
                parts.append(f"{k}={v}")
        return "; ".join(parts)

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        h = {
            "Cookie": self._cookie_header(),
            "User-Agent": self._user_agent,
            "Accept": "application/json",
            "Referer": f"{PPLX_BASE}/",
            "Origin": PPLX_BASE,
        }
        if extra:
            h.update(extra)
        return h

    def _fetch_json(
        self,
        path: str,
        method: str = "GET",
        body: dict | None = None,
        timeout: int = 30,
    ) -> Any:
        url = path if path.startswith("http") else f"{PPLX_BASE}{path}"
        data: bytes | None = None
        headers = self._headers()
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            payload = resp.read()
            if not payload:
                return None
            return json.loads(payload)
        except urllib.error.HTTPError as e:
            return {"__error": True, "status": e.code,
                    "body": e.read().decode("utf-8", errors="replace")[:200]}
        except Exception as e:
            return {"__error": True, "status": 0, "body": str(e)[:200]}

    # --- auth ------------------------------------------------------------

    def authenticate(self) -> dict:
        data = self._fetch_json("/api/auth/session")
        if (
            isinstance(data, dict)
            and not data.get("__error")
            and isinstance(data.get("user"), dict)
        ):
            user = data["user"]
            self._user = user
            return {
                "authenticated": True,
                "email": user.get("email", ""),
                "name": user.get("name", ""),
                "user_id": user.get("id") or user.get("user_uuid", ""),
                "expires": data.get("expires"),
            }
        return {"authenticated": False, "error": data}

    # --- inventory -------------------------------------------------------

    def list_threads(self, limit: int = 50, offset: int = 0) -> list[dict]:
        """Page of library threads ordered newest-first by ``last_query_datetime``.

        Endpoint discovered via Camoufox network capture against the live
        ``/library`` page (2026-05). Each item carries the same fields the
        UI uses: ``uuid``, ``slug``, ``title``, ``last_query_datetime``,
        ``thread_number``, ``total_threads``, ``has_next_page``, plus a
        ``query_str`` first-message preview.
        """
        body = {"limit": limit, "offset": offset}
        data = self._fetch_json(
            "/rest/thread/list_ask_threads?version=2.18&source=default",
            method="POST",
            body=body,
        )
        if isinstance(data, list):
            return _dict_rows(data)
        if isinstance(data, dict) and isinstance(data.get("threads"), list):
            return _dict_rows(data["threads"])
        return []

    def all_threads(self, page_size: int = 50, max_pages: int = 100) -> list[dict]:
        out: list[dict] = []
        seen_ids: set[str] = set()
        for page in range(max_pages):
            batch = self.list_threads(limit=page_size, offset=page * page_size)
            if not batch:
                break
            new = 0
            for t in _dict_rows(batch):
                tid = t.get("uuid") or t.get("backend_uuid") or t.get("id") or t.get("slug")
                if tid and tid not in seen_ids:
                    seen_ids.add(tid)
                    out.append(t)
                    new += 1
            if new == 0 or len(batch) < page_size:
                break
        return out

    # --- detail ----------------------------------------------------------

    def thread_detail(self, thread_id: str) -> dict | None:
        """Fetch one thread's detail.

        Tries both common shapes; returns None on failure.
        """
        # Shape 1: /rest/thread/<id>
        d = self._fetch_json(f"/rest/thread/{thread_id}")
        if isinstance(d, dict) and not d.get("__error"):
            return d
        # Shape 2: POST with body
        d = self._fetch_json(
            "/rest/thread/get",
            method="POST",
            body={"uuid": thread_id, "version": "2.18"},
        )
        if isinstance(d, dict) and not d.get("__error"):
            return d
        return None

    @staticmethod
    def _parse_steps(entry: dict) -> list[dict]:
        """``entry["text"]`` is a JSON-encoded list of step objects
        (``INITIAL_QUERY``, ``SEARCH_WEB``, ``SEARCH_RESULTS``, ``FINAL``).
        Decode it once; tolerate non-JSON / dict shapes for forward compat."""
        text = entry.get("text")
        if isinstance(text, list):
            return _dict_rows(text)
        if isinstance(text, str):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    return _dict_rows(parsed)
            except Exception:
                return []
        return []

    @staticmethod
    def _final_answer(steps: list[dict]) -> str:
        """Pull the assistant prose out of the last FINAL step. The step's
        ``content.answer`` is itself a JSON envelope of the form
        ``{"answer": "<markdown>", ...}`` — so we double-decode."""
        for step in reversed(steps):
            if step.get("step_type") not in ("FINAL", "PLAN_RESPONSE", "RESPOND"):
                continue
            content = step.get("content") or {}
            ans = content.get("answer") if isinstance(content, dict) else None
            if isinstance(ans, str):
                stripped = ans.strip()
                if stripped.startswith("{") or stripped.startswith("["):
                    try:
                        envelope = json.loads(stripped)
                        if isinstance(envelope, dict):
                            inner = envelope.get("answer")
                            if isinstance(inner, str) and inner.strip():
                                return inner
                    except Exception:
                        pass
                return ans
            if isinstance(ans, dict):
                inner = ans.get("answer")
                if isinstance(inner, str):
                    return inner
        return ""

    @classmethod
    def extract_messages(cls, detail: dict) -> list[dict]:
        """One entry = one user/assistant pair.

        User text comes from ``query_str``; assistant text from the FINAL
        step's decoded answer envelope. Older shapes that exposed a flat
        ``answer`` field on the entry are still honored.
        """
        messages: list[dict] = []
        thread = detail.get("thread") if isinstance(detail.get("thread"), dict) else {}
        entries = _dict_rows(detail.get("entries") or thread.get("entries") or [])
        for entry in entries:
            uuid = entry.get("uuid") or entry.get("backend_uuid") or ""
            query = entry.get("query_str") or entry.get("query") or ""
            if query:
                messages.append({
                    "role": "user",
                    "content": query,
                    "ordinal": len(messages) + 1,
                    "provider_message_id": f"{uuid}:q" if uuid else "",
                    "content_type": "text",
                    "rich_parts": [],
                    "artifact_refs": [],
                    "metadata": {"entry_uuid": uuid},
                })
            steps = cls._parse_steps(entry)
            answer = cls._final_answer(steps)
            if not answer:
                # Legacy path: pre-step-decomposition entries.
                fallback = entry.get("answer")
                if isinstance(fallback, dict):
                    answer = fallback.get("answer") or fallback.get("text") or ""
                elif isinstance(fallback, str):
                    answer = fallback
            if answer:
                messages.append({
                    "role": "assistant",
                    "content": answer,
                    "ordinal": len(messages) + 1,
                    "provider_message_id": f"{uuid}:a" if uuid else "",
                    "content_type": "text",
                    "rich_parts": [
                        {"type": "step", "value": s} for s in steps
                        if isinstance(s, dict) and s.get("step_type") not in ("INITIAL_QUERY", "FINAL")
                    ],
                    "artifact_refs": [],
                    "metadata": {
                        "entry_uuid": uuid,
                        "model": entry.get("display_model") or entry.get("user_selected_model"),
                        "search_focus": entry.get("search_focus"),
                        "mode": entry.get("mode"),
                    },
                })
        return messages

    @classmethod
    def extract_citations(cls, detail: dict) -> list[dict]:
        """Walk every SEARCH_RESULTS step in every entry, collect web_results."""
        citations: list[dict] = []
        seen: set[str] = set()
        thread = detail.get("thread") if isinstance(detail.get("thread"), dict) else {}
        entries = _dict_rows(detail.get("entries") or thread.get("entries") or [])
        for entry in entries:
            for step in cls._parse_steps(entry):
                if step.get("step_type") != "SEARCH_RESULTS":
                    continue
                content = step.get("content") or {}
                web_results = content.get("web_results") if isinstance(content, dict) else None
                if not isinstance(web_results, list):
                    continue
                for src in web_results:
                    if not isinstance(src, dict):
                        continue
                    url = src.get("url") or src.get("link")
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    citations.append({
                        "label": src.get("name") or src.get("title") or "",
                        "url": url,
                        "source_json": src,
                    })
        return citations
