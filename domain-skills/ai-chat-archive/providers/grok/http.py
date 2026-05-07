"""HTTP client for grok.com.

Endpoints discovered (2026-05):
* ``GET /rest/app-chat/conversations`` -> ``{conversations: [{conversationId,
  title, starred, createTime, modifyTime, ...}], textSearchMatches}``
* ``GET /rest/app-chat/conversations/{id}`` -> conversation metadata
* ``GET /rest/app-chat/conversations/{id}/responses`` -> ``{responses: [...
  one entry per turn ...], inflightResponses}``

Cookies needed: ``sso`` and ``sso-rw`` on ``.grok.com``, plus ``cf_clearance``.
The sso cookie is a JWT but its payload only carries ``session_id``; there's
no identity endpoint, so we use the session_id as the account discriminator
when no human label can be derived.
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from typing import Any


GROK_BASE = "https://grok.com"


def _dict_rows(rows: Any) -> list[dict]:
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _string_rows(rows: Any) -> list[str]:
    return [row for row in rows if isinstance(row, str)] if isinstance(rows, list) else []


def _cookie_domain(cookies: Any, domain: str) -> dict:
    if not isinstance(cookies, dict):
        return {}
    jar = cookies.get(domain)
    return jar if isinstance(jar, dict) else {}


class GrokHTTPAPI:
    def __init__(self, cookies_by_domain: dict[str, dict[str, str]]):
        self._cookies = cookies_by_domain
        self._user_agent = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        )
        self._session_id: str | None = None

    def _cookie_header(self) -> str:
        parts: list[str] = []
        for d in (".grok.com", "grok.com"):
            for k, v in _cookie_domain(self._cookies, d).items():
                parts.append(f"{k}={v}")
        return "; ".join(parts)

    def _headers(self) -> dict[str, str]:
        return {
            "Cookie": self._cookie_header(),
            "User-Agent": self._user_agent,
            "Accept": "application/json",
            "Referer": f"{GROK_BASE}/",
            "Origin": GROK_BASE,
        }

    def _fetch_json(self, path: str, timeout: int = 30) -> Any:
        url = path if path.startswith("http") else f"{GROK_BASE}{path}"
        req = urllib.request.Request(url, headers=self._headers())
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return {"__error": True, "status": e.code,
                    "body": e.read().decode("utf-8", errors="replace")[:200]}
        except Exception as e:
            return {"__error": True, "status": 0, "body": str(e)[:200]}

    def authenticate(self) -> dict:
        """Probe by listing conversations: 200 ⇒ authenticated.

        We additionally peek at the ``sso`` JWT to extract a session_id for
        account-key stability across multiple Grok logins."""
        sso = _cookie_domain(self._cookies, ".grok.com").get("sso", "")
        self._session_id = _decode_sso_session(sso)

        data = self._fetch_json("/rest/app-chat/conversations")
        if isinstance(data, dict) and isinstance(data.get("conversations"), list):
            return {
                "authenticated": True,
                "email": "",
                "name": "Grok user",
                "user_id": self._session_id or "",
                "session_id": self._session_id,
            }
        return {"authenticated": False, "error": data}

    def all_conversations(self) -> list[dict]:
        data = self._fetch_json("/rest/app-chat/conversations")
        if isinstance(data, dict):
            rows = data.get("conversations") or []
            return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        return []

    def conversation_detail(self, conversation_id: str) -> dict | None:
        meta = self._fetch_json(f"/rest/app-chat/conversations/{conversation_id}")
        if not isinstance(meta, dict) or meta.get("__error"):
            return None
        responses = self._fetch_json(
            f"/rest/app-chat/conversations/{conversation_id}/responses",
        )
        if not isinstance(responses, dict) or responses.get("__error"):
            responses = {"responses": []}
        rows = responses.get("responses") or []
        rows = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        return {"meta": meta, "responses": rows}

    @staticmethod
    def extract_messages(detail: dict) -> list[dict]:
        """One response = one message. ``sender`` is the role discriminator
        (``human`` → user, ``ASSISTANT``/anything else → assistant). Text
        always lives in ``message``; ``query`` is empty in practice.

        Filters out empty messages (e.g. control rows with ``isControl``)."""
        msgs: list[dict] = []
        for r in _dict_rows(detail.get("responses")):
            message = r.get("message")
            text = message.strip() if isinstance(message, str) else ""
            if not text:
                continue
            if r.get("isControl"):
                continue
            sender = (r.get("sender") or "").lower()
            role = "user" if sender == "human" else "assistant"
            rid = r.get("responseId") or ""
            ts = r.get("createTime")
            entry: dict = {
                "role": role,
                "content": text,
                "ordinal": len(msgs) + 1,
                "provider_message_id": rid,
                "content_type": "text",
                "rich_parts": _rich_parts_for_response(r) if role == "assistant" else [],
                "artifact_refs": _artifact_refs_for_response(r),
                "metadata": {
                    "create_time": ts,
                    "manual": r.get("manual"),
                    "parent_response_id": r.get("parentResponseId"),
                },
            }
            if role == "assistant":
                entry["metadata"].update({
                    "model": r.get("model"),
                    "query_type": r.get("queryType"),
                    "stream_errors": r.get("streamErrors"),
                })
            msgs.append(entry)
        return msgs

    @staticmethod
    def extract_artifacts(detail: dict) -> list[dict]:
        artifacts: list[dict] = []
        for r in _dict_rows(detail.get("responses")):
            rid = r.get("responseId")
            for img in _string_rows(r.get("generatedImageUrls")):
                artifacts.append({
                    "artifact_type": "generated_image",
                    "provider_artifact_id": _artifact_id_from_url(img),
                    "label": "Generated image",
                    "parent_message_id": rid,
                    "source_url": img,
                })
            for img in _dict_rows(r.get("imageAttachments")):
                artifacts.append({
                    "artifact_type": "image",
                    "provider_artifact_id": img.get("id") or img.get("url"),
                    "label": img.get("name") or "Image",
                    "parent_message_id": rid,
                    "source_url": img.get("url"),
                    "rich_part": img,
                })
            for f in _dict_rows(r.get("fileAttachments")):
                artifacts.append({
                    "artifact_type": "file",
                    "provider_artifact_id": f.get("id") or f.get("uri"),
                    "label": f.get("name") or f.get("filename") or "file",
                    "parent_message_id": rid,
                    "source_url": f.get("url") or f.get("uri"),
                    "byte_length": f.get("size"),
                    "rich_part": f,
                })
            for url in _string_rows(r.get("imageEditUris")):
                artifacts.append({
                    "artifact_type": "image_edit",
                    "provider_artifact_id": _artifact_id_from_url(url),
                    "label": "Image edit",
                    "parent_message_id": rid,
                    "source_url": url,
                })
        return artifacts

    @staticmethod
    def extract_citations(detail: dict) -> list[dict]:
        citations: list[dict] = []
        seen: set[str] = set()
        for r in _dict_rows(detail.get("responses")):
            for src in _dict_rows(r.get("citedWebSearchResults") or r.get("webSearchResults")):
                url = src.get("url") or src.get("link")
                if not url or url in seen:
                    continue
                seen.add(url)
                citations.append({
                    "label": src.get("title") or src.get("name") or "",
                    "url": url,
                    "source_json": src,
                })
        return citations


def _decode_sso_session(sso: str) -> str | None:
    if not sso:
        return None
    try:
        parts = sso.split(".")
        if len(parts) < 2:
            return None
        pad = "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + pad))
        return payload.get("session_id") or payload.get("sub")
    except Exception:
        return None


def _rich_parts_for_response(r: dict) -> list[dict]:
    rich: list[dict] = []
    for field, label in (
        ("steps", "steps"),
        ("toolResponses", "tool_responses"),
        ("xposts", "xposts"),
    ):
        value = r.get(field)
        if isinstance(value, list):
            rich.append({"type": label, "value": value})
    return rich


def _artifact_refs_for_response(r: dict) -> list[dict]:
    refs: list[dict] = []
    for url in _string_rows(r.get("generatedImageUrls")):
        refs.append({"image_url": url, "kind": "generated_image"})
    for f in _string_rows(r.get("fileUris")):
        refs.append({"file_uri": f, "kind": "file"})
    return refs


def _artifact_id_from_url(url: str) -> str:
    if not url:
        return ""
    return url.rsplit("/", 1)[-1].split("?")[0] or url
