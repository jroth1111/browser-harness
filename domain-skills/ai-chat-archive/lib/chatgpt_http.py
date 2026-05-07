"""HTTP-based ChatGPT API client using extracted browser cookies.

Works without browser automation. Requires cookies extracted from a logged-in
Chromium-based browser via cookie_extract.py.

Key discovery: the ChatGPT backend API requires DUAL authentication:
  1. Cookie header with session cookies (cf_clearance, oai-sc, session-token, etc.)
  2. Authorization Bearer token obtained from /api/auth/session
Using either alone results in Cloudflare 403 or API 401.

The oai-sc cookie value must also be sent as an HTTP header.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request


class ChatGPTHTTPAPI:
    """ChatGPT backend API client using extracted cookies."""

    def __init__(self, cookies_by_domain: dict[str, dict[str, str]]):
        self._cookies = cookies_by_domain
        self._access_token: str | None = None
        self._user_agent = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        )

    def _cookie_header(self, domains: list[str] | None = None) -> str:
        if domains is None:
            domains = [".chatgpt.com", "chatgpt.com", ".openai.com"]
        parts = []
        for d in domains:
            for k, v in self._cookies.get(d, {}).items():
                parts.append(f"{k}={v}")
        return "; ".join(parts)

    def _request_headers(self, extra_domains: list[str] | None = None) -> dict:
        headers = {
            "Cookie": self._cookie_header(extra_domains),
            "User-Agent": self._user_agent,
            "Accept": "application/json",
            "Referer": "https://chatgpt.com/",
            "Origin": "https://chatgpt.com",
            "oai-sc": self._cookies.get(".chatgpt.com", {}).get("oai-sc", ""),
        }
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    def _fetch_json(self, url: str, timeout: int = 30) -> dict | None:
        req = urllib.request.Request(url, headers=self._request_headers())
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return {"__error": True, "status": e.code,
                    "body": e.read().decode("utf-8", errors="replace")[:200]}
        except Exception as e:
            return {"__error": True, "status": 0, "body": str(e)[:200]}

    def authenticate(self) -> dict:
        """Get access token from /api/auth/session using session cookies.

        Returns user info dict with email, name, id.
        """
        data = self._fetch_json("https://chatgpt.com/api/auth/session")
        if not isinstance(data, dict) or data.get("__error"):
            return {"authenticated": False, "error": data}

        user = data.get("user", {})
        self._access_token = data.get("accessToken")

        return {
            "authenticated": True,
            "email": user.get("email", ""),
            "name": user.get("name", ""),
            "user_id": user.get("id", ""),
        }

    def get_me(self) -> dict | None:
        """Get current user info from /backend-api/me."""
        return self._fetch_json("https://chatgpt.com/backend-api/me")

    def all_conversations(self, max_pages: int = 100) -> list[dict]:
        """Paginate through all conversations."""
        page_size = 28
        all_items = []
        seen_ids = set()

        for page in range(max_pages):
            offset = page * page_size
            url = (
                f"https://chatgpt.com/backend-api/conversations"
                f"?offset={offset}&limit={page_size}&order=updated"
                f"&is_archived=false&is_starred=false"
            )
            data = self._fetch_json(url)

            if not isinstance(data, dict) or data.get("__error"):
                break

            items = data.get("items", [])
            if not items:
                break

            for item in items:
                cid = item.get("id")
                if cid and cid not in seen_ids:
                    seen_ids.add(cid)
                    all_items.append({
                        "id": cid,
                        "title": item.get("title", ""),
                        "create_time": item.get("create_time"),
                        "update_time": item.get("update_time"),
                    })

            if len(items) < page_size:
                break
            time.sleep(0.3)

        return all_items

    def conversation_detail(self, conversation_id: str) -> dict | None:
        """Fetch full conversation detail.

        The API returns a mapping dict of nodes, not a flat message list.
        Each node has: { message: { author, content, metadata, ... }, children, parent }
        Messages must be extracted by walking the tree and sorting by create_time.
        """
        url = f"https://chatgpt.com/backend-api/conversation/{conversation_id}"
        data = self._fetch_json(url)

        if not isinstance(data, dict) or data.get("__error"):
            return None

        return data

    @staticmethod
    def extract_messages_from_mapping(detail: dict) -> list[dict]:
        """Extract ordered messages from the conversation mapping node tree.

        The mapping is a dict of node_id -> { message, children, parent }.
        We walk all nodes, skip system messages, and sort by create_time.

        Handles both ``content.parts[]`` (standard messages) and
        content-type-specific fields (``thoughts``, ``code``, ``reasoning_recap``,
        ``execution_output``, ``tether_browsing_display``, ``computer_output``).
        Rich content (dict parts with artifact references) is preserved in
        ``rich_parts``.  Tool messages are always kept.
        """
        mapping = detail.get("mapping", {})
        messages = []

        for node_id, node in mapping.items():
            msg = node.get("message")
            if not msg:
                continue

            role = msg.get("author", {}).get("role", "unknown")
            if role == "system":
                continue

            msg_content = msg.get("content", {})
            content_type = msg_content.get("content_type", "")
            content_parts = msg_content.get("parts", [])
            text_parts = [p for p in content_parts if isinstance(p, str)]
            rich_parts = [p for p in content_parts if isinstance(p, dict)]
            content = "\n".join(text_parts)

            # Content-type-specific extraction (no parts array)
            if not content.strip() and content_type in (
                "code", "thoughts", "reasoning_recap",
                "execution_output", "tether_browsing_display",
                "computer_output", "multimodal_text",
            ):
                content = (
                    msg_content.get("text", "")
                    or msg_content.get("content", "")
                    or ""
                )
                thoughts = msg_content.get("thoughts")
                if thoughts and not content:
                    # Extract text from thoughts list
                    parts = []
                    for t in (thoughts if isinstance(thoughts, list) else [thoughts]):
                        if isinstance(t, dict):
                            parts.append(t.get("content", t.get("summary", "")))
                        elif isinstance(t, str):
                            parts.append(t)
                    content = "\n".join(parts)

            # Keep tool messages even with empty content — they carry metadata
            has_rich = bool(rich_parts)
            if not content.strip() and not has_rich and role != "tool":
                continue

            metadata = msg.get("metadata", {})
            artifact_refs = _extract_artifact_refs(rich_parts, metadata, role)

            messages.append({
                "role": role,
                "content": content,
                "content_type": content_type or None,
                "provider_message_id": msg.get("id", node_id),
                "created_at": msg.get("create_time"),
                "model": metadata.get("model_slug", ""),
                "finish_details": metadata.get("finish_details", {}),
                "rich_parts": rich_parts,
                "artifact_refs": artifact_refs,
            })

        messages.sort(key=lambda m: m.get("created_at") or 0)
        for i, m in enumerate(messages):
            m["ordinal"] = i + 1

        return messages

    @staticmethod
    def extract_artifacts_from_mapping(detail: dict) -> list[dict]:
        """Extract artifact metadata from the conversation mapping tree.

        Scans all message nodes for rich content parts and message-level content
        types that represent LLM-generated artifacts: images, code execution,
        Operator screenshots, canvas references, and deep research markers.
        """
        mapping = detail.get("mapping", {})
        artifacts = []

        for node_id, node in mapping.items():
            msg = node.get("message")
            if not msg:
                continue

            role = msg.get("author", {}).get("role", "unknown")
            msg_id = msg.get("id", node_id)
            content = msg.get("content", {})
            content_type = content.get("content_type", "")
            content_parts = content.get("parts", [])

            # --- Dict parts (image_asset_pointer, etc.) ---
            for part in content_parts:
                if not isinstance(part, dict):
                    continue

                ct = part.get("content_type", "")

                # Image assets (DALL-E generated or uploaded)
                if ct == "image_asset_pointer":
                    asset_pointer = part.get("asset_pointer", "")
                    is_dalle = (part.get("metadata") or {}).get("dalle") is not None
                    size_bytes = part.get("size_bytes", 0)
                    w = part.get("width", 0)
                    h = part.get("height", 0)
                    artifacts.append({
                        "artifact_type": "generated_image" if is_dalle or role == "tool" else "image",
                        "provider_artifact_id": asset_pointer,
                        "label": f"Image ({w}x{h})",
                        "parent_message_id": msg_id,
                        "rich_part": part,
                        "size_bytes": size_bytes,
                    })

                # Path-based markers (deep research, canvas, agent)
                path = part.get("path", "")
                if "Deep Research" in path:
                    artifacts.append({
                        "artifact_type": "deep_research_report",
                        "provider_artifact_id": part.get("args", {}).get("prompt_id", msg_id),
                        "label": "Deep Research Report",
                        "parent_message_id": msg_id,
                        "rich_part": part,
                    })
                if "canvas" in path.lower() or part.get("action") == "canvas":
                    artifacts.append({
                        "artifact_type": "canvas_document",
                        "provider_artifact_id": part.get("canvas_id", msg_id),
                        "label": part.get("title", "Canvas Document"),
                        "parent_message_id": msg_id,
                        "rich_part": part,
                    })
                if "operator" in path.lower() or "agent" in path.lower():
                    artifacts.append({
                        "artifact_type": "agent_report",
                        "provider_artifact_id": msg_id,
                        "label": "Agent Report",
                        "parent_message_id": msg_id,
                        "rich_part": part,
                    })

                # File references in tool messages
                if role == "tool":
                    file_id = part.get("file_id")
                    if file_id:
                        artifacts.append({
                            "artifact_type": "generated_file",
                            "provider_artifact_id": file_id,
                            "label": part.get("filename", file_id),
                            "parent_message_id": msg_id,
                            "rich_part": part,
                        })

            # --- Message-level content types ---

            # Operator/Computer use screenshots
            if content_type == "computer_output":
                screenshot = content.get("screenshot")
                if screenshot:
                    artifacts.append({
                        "artifact_type": "agent_screenshot",
                        "provider_artifact_id": content.get("tether_id", msg_id),
                        "label": f"Agent Screenshot ({content.get('computer_id', '')})",
                        "parent_message_id": msg_id,
                        "rich_part": content,
                    })

            # Code execution
            if content_type == "code" and content.get("text"):
                lang = content.get("language", "")
                code_text = content["text"]
                if len(code_text) > 50:
                    artifacts.append({
                        "artifact_type": "code_execution",
                        "provider_artifact_id": msg_id,
                        "label": f"Code ({lang})",
                        "parent_message_id": msg_id,
                        "rich_part": {"content_type": "code", "language": lang, "text": code_text},
                    })

        return artifacts


def _extract_artifact_refs(rich_parts: list[dict], metadata: dict, role: str) -> list[dict]:
    """Pull lightweight artifact references from rich content parts."""
    refs = []
    for part in rich_parts:
        ct = part.get("content_type", "")
        if ct == "image_asset_pointer":
            refs.append({"image_asset": part.get("asset_pointer")})
        path = part.get("path", "")
        if path:
            refs.append({"path": path})
        file_id = part.get("file_id")
        if file_id:
            refs.append({"file_id": file_id})
    return refs
