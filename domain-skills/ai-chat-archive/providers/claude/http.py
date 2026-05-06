"""HTTP client for the claude.ai backend API.

Auth is cookie-only — the ``sessionKey`` cookie on ``.claude.ai`` is sufficient
once it's been issued by a real browser login flow. Unlike ChatGPT there's no
second Bearer step.

Endpoints used:
    GET /api/auth/current_account            -> user + organization list
    GET /api/organizations                   -> orgs (fallback if above shape thin)
    GET /api/organizations/{org}/chat_conversations
                                              -> paginated inventory
    GET /api/organizations/{org}/chat_conversations/{conv}?tree=true&rendering_mode=raw
                                              -> full thread detail with
                                                 chat_messages[] flat array

The API isn't formally public so shapes may drift; capture the raw payload
into ``CapturedThread.normalized_json`` so we can re-extract later.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


CLAUDE_BASE = "https://claude.ai"


class ClaudeHTTPAPI:
    def __init__(self, cookies_by_domain: dict[str, dict[str, str]]):
        self._cookies = cookies_by_domain
        self._user_agent = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        )
        self._account: dict[str, Any] | None = None
        self._org_uuid: str | None = None

    # --- transport -------------------------------------------------------

    def _cookie_header(self) -> str:
        parts: list[str] = []
        for domain in (".claude.ai", "claude.ai"):
            for k, v in self._cookies.get(domain, {}).items():
                parts.append(f"{k}={v}")
        return "; ".join(parts)

    def _headers(self) -> dict[str, str]:
        return {
            "Cookie": self._cookie_header(),
            "User-Agent": self._user_agent,
            "Accept": "application/json",
            "Referer": f"{CLAUDE_BASE}/",
            "Origin": CLAUDE_BASE,
        }

    def _fetch_json(self, path: str, timeout: int = 30) -> Any:
        url = path if path.startswith("http") else f"{CLAUDE_BASE}{path}"
        req = urllib.request.Request(url, headers=self._headers())
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return {"__error": True, "status": e.code,
                    "body": e.read().decode("utf-8", errors="replace")[:200]}
        except Exception as e:
            return {"__error": True, "status": 0, "body": str(e)[:200]}

    # --- auth ------------------------------------------------------------

    def authenticate(self) -> dict:
        """Verify the cookies authenticate. Returns a normalized identity dict."""
        data = self._fetch_json("/api/auth/current_account")
        account: dict[str, Any] | None = None
        if isinstance(data, dict) and not data.get("__error"):
            # Different Claude builds return either {account: {...}} or the
            # account object directly; accept both.
            if isinstance(data.get("account"), dict):
                account = data["account"]
            elif data.get("email_address") or data.get("uuid"):
                account = data

        # Always pull orgs separately since current_account often omits them.
        orgs = self._fetch_json("/api/organizations")
        if isinstance(orgs, list) and orgs:
            self._org_uuid = orgs[0].get("uuid")

        if account is not None:
            self._account = account
            return {
                "authenticated": True,
                "email": account.get("email_address") or account.get("email", ""),
                "name": account.get("full_name") or account.get("name", ""),
                "user_id": account.get("uuid", ""),
                "org_uuid": self._org_uuid,
            }
        if self._org_uuid:
            return {
                "authenticated": True,
                "email": "",
                "name": orgs[0].get("name", ""),
                "user_id": "",
                "org_uuid": self._org_uuid,
            }
        return {"authenticated": False, "error": data}

    @property
    def org_uuid(self) -> str | None:
        return self._org_uuid

    # --- inventory -------------------------------------------------------

    def all_conversations(self) -> list[dict]:
        """Return every conversation visible to the active org."""
        if not self._org_uuid:
            return []
        # Claude's list endpoint isn't paginated by offset/limit; it returns
        # everything in one response. Defensive: if the shape ever changes,
        # this still returns a list-or-empty.
        url = f"/api/organizations/{self._org_uuid}/chat_conversations"
        data = self._fetch_json(url)
        if isinstance(data, list):
            return [
                {
                    "uuid": item.get("uuid"),
                    "name": item.get("name") or "",
                    "summary": item.get("summary") or "",
                    "created_at": item.get("created_at"),
                    "updated_at": item.get("updated_at"),
                    "model": item.get("model"),
                }
                for item in data
                if item.get("uuid")
            ]
        return []

    # --- detail ----------------------------------------------------------

    def conversation_detail(self, conversation_uuid: str) -> dict | None:
        if not self._org_uuid:
            return None
        url = (
            f"/api/organizations/{self._org_uuid}"
            f"/chat_conversations/{conversation_uuid}"
            f"?tree=true&rendering_mode=raw"
        )
        data = self._fetch_json(url)
        if not isinstance(data, dict) or data.get("__error"):
            return None
        return data

    # --- normalization helpers ------------------------------------------

    @staticmethod
    def extract_messages(detail: dict) -> list[dict]:
        """Turn ``detail['chat_messages']`` into the canonical message shape.

        Each Claude message has a ``content`` list of blocks (text, tool_use,
        tool_result, image, attachment). We concatenate text blocks for
        ``current_content`` and stash the full structured list as rich_parts
        so artifact extraction can re-walk later.
        """
        msgs: list[dict] = []
        chat = detail.get("chat_messages") or []
        for i, m in enumerate(chat, start=1):
            sender = m.get("sender", "")
            role = "user" if sender == "human" else "assistant" if sender == "assistant" else sender
            blocks = m.get("content") or []
            text_parts: list[str] = []
            rich: list[dict] = []
            for b in blocks:
                if not isinstance(b, dict):
                    continue
                btype = b.get("type", "")
                if btype == "text":
                    t = b.get("text") or ""
                    if t:
                        text_parts.append(t)
                elif btype in ("tool_use", "tool_result", "image", "thinking"):
                    rich.append(b)
            # Some builds carry a flat "text" field as a fallback.
            if not text_parts and m.get("text"):
                text_parts.append(m["text"])

            attachments = m.get("attachments") or []
            files = m.get("files_v2") or m.get("files") or []
            artifact_refs = []
            for a in attachments:
                if isinstance(a, dict) and a.get("file_uuid"):
                    artifact_refs.append({"file_uuid": a["file_uuid"], "kind": "attachment"})
            for f in files:
                if isinstance(f, dict) and f.get("file_uuid"):
                    artifact_refs.append({"file_uuid": f["file_uuid"], "kind": "file"})

            msgs.append({
                "role": role,
                "content": "\n".join(text_parts),
                "ordinal": i,
                "provider_message_id": m.get("uuid"),
                "content_type": "text" if text_parts and not rich else "mixed" if rich else "empty",
                "rich_parts": rich,
                "artifact_refs": artifact_refs,
                "metadata": {
                    "model": m.get("model"),
                    "stop_reason": m.get("stop_reason"),
                    "created_at": m.get("created_at"),
                    "attachments": attachments,
                    "files": files,
                },
            })
        return msgs

    @staticmethod
    def extract_artifacts(detail: dict) -> list[dict]:
        """Pull artifact metadata: attachments, files, and rendered Artifact panels."""
        artifacts: list[dict] = []
        for m in detail.get("chat_messages") or []:
            mid = m.get("uuid")
            for a in m.get("attachments") or []:
                if not isinstance(a, dict):
                    continue
                artifacts.append({
                    "artifact_type": "attachment",
                    "provider_artifact_id": a.get("file_uuid") or a.get("id"),
                    "label": a.get("file_name") or a.get("filename") or "attachment",
                    "parent_message_id": mid,
                    "byte_length": a.get("file_size"),
                    "mime_type": a.get("file_type"),
                    "rich_part": a,
                })
            for f in (m.get("files_v2") or m.get("files") or []):
                if not isinstance(f, dict):
                    continue
                artifacts.append({
                    "artifact_type": "file",
                    "provider_artifact_id": f.get("file_uuid") or f.get("uuid"),
                    "label": f.get("file_name") or f.get("filename") or "file",
                    "parent_message_id": mid,
                    "byte_length": f.get("file_size"),
                    "mime_type": f.get("file_type"),
                    "rich_part": f,
                })
            # Claude Artifacts (the named code/text panels) appear as tool_use
            # blocks with name='artifacts' or as separate "artifact" entries.
            for b in (m.get("content") or []):
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "tool_use" and b.get("name") in ("artifacts", "create_artifact"):
                    inp = b.get("input") or {}
                    artifacts.append({
                        "artifact_type": "claude_artifact",
                        "provider_artifact_id": inp.get("id") or b.get("id"),
                        "label": inp.get("title") or "Claude Artifact",
                        "parent_message_id": mid,
                        "rich_part": b,
                    })
        return artifacts
