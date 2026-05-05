"""Thin callable helpers for the YouTube surface map.

This module intentionally does not own browser sessions, retries, or fallback
routing. Each function maps to one primitive ID in ``surface-map.json`` and
either parses provided payloads or returns an explicit terminal/advance reason.
Live browser work still belongs in browser-harness scripts.
"""
from __future__ import annotations

import json
import re
import shutil
import importlib.util
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent
SURFACE_MAP_PATH = ROOT / "surface-map.json"

ADVANCE_CODES = {
    "not_available",
    "not_found",
    "empty_result",
    "parse_error",
    "blocked",
    "timeout",
    "unsupported_shape",
}
TERMINATE_CODES = {"login_required", "members_only", "age_restricted"}
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
UC_CHANNEL_RE = re.compile(r"^UC[A-Za-z0-9_-]{20,}$")


def result(
    ok: bool,
    data: Any = None,
    reason: str = "success",
    *,
    tier: int = 1,
    path_type: str = "local",
    degraded: bool = False,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "data": data,
        "reason": reason,
        "tier": tier,
        "path_type": path_type,
        "degraded": degraded,
    }


def load_surface_map(path: Path = SURFACE_MAP_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def primitive_ids() -> list[str]:
    return [item["id"] for item in load_surface_map()["primitives"]]


def ytdlp_available() -> bool:
    return shutil.which("yt-dlp") is not None


def ytdlp_command_shape(mode: str, target: str) -> list[str]:
    """Return allowed no-media command shapes without executing yt-dlp."""
    if mode == "dump_json":
        return ["yt-dlp", "--skip-download", "--dump-single-json", target]
    if mode == "flat_playlist":
        return ["yt-dlp", "--skip-download", "--flat-playlist", "--dump-single-json", target]
    if mode == "comments":
        return ["yt-dlp", "--skip-download", "--write-comments", "--dump-single-json", target]
    if mode == "subs":
        return ["yt-dlp", "--skip-download", "--write-subs", "--write-auto-subs", target]
    if mode == "ytsearch":
        return ["yt-dlp", "--skip-download", f"ytsearch:{target}"]
    raise ValueError(f"unknown yt-dlp mode: {mode}")


def _caption_parser_module():
    spec = importlib.util.spec_from_file_location("caption_parsers", ROOT / "caption_parsers.py")
    if not spec or not spec.loader:
        raise RuntimeError("caption parser module unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def local_caption_payload_text(fmt: str, raw: str) -> dict[str, Any]:
    """Normalize an already-captured caption payload with explicit parse errors."""
    try:
        parsers = _caption_parser_module()
        normalized_fmt = fmt.lower().lstrip(".")
        if normalized_fmt == "vtt":
            text = parsers.vtt_to_text(raw)
        elif normalized_fmt == "json3":
            text = parsers.json3_to_text(raw)
        elif normalized_fmt in {"xml", "ttml", "srv3", "timedtext"}:
            text = parsers.xml_to_text(raw)
        else:
            return result(False, {"format": fmt}, "unsupported_shape", path_type="local")
    except (json.JSONDecodeError, ET.ParseError, ValueError, TypeError, RuntimeError) as exc:
        return result(False, {"format": fmt, "error": f"{exc.__class__.__name__}: {exc}"}, "parse_error", path_type="local")
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return result(False, {"format": fmt, "line_count": 0}, "empty_result", path_type="local")
    return result(True, {"format": fmt, "text": text, "line_count": len(lines)}, path_type="local")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts = [_text(item) for item in value]
        joined = "".join(part for part in parts if part)
        return joined or None
    if not isinstance(value, dict):
        return None
    for key in ("simpleText", "text", "content", "accessibilityText"):
        if isinstance(value.get(key), str):
            return value[key]
    if isinstance(value.get("runs"), list):
        return _text(value["runs"])
    if isinstance(value.get("title"), (dict, str)):
        return _text(value["title"])
    return None


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _renderer_items(payload: Any) -> list[tuple[str, dict[str, Any]]]:
    items: list[tuple[str, dict[str, Any]]] = []
    for node in _walk(payload):
        for key, value in node.items():
            if key.endswith("Renderer") or key.endswith("ViewModel"):
                if isinstance(value, dict):
                    items.append((key, value))
    return items


def _first_renderer(payload: Any, name: str) -> dict[str, Any] | None:
    for renderer_name, renderer in _renderer_items(payload):
        if renderer_name == name:
            return renderer
    return None


def _continuations(payload: Any) -> list[str]:
    tokens: list[str] = []
    for node in _walk(payload):
        command = node.get("continuationCommand") if isinstance(node, dict) else None
        if isinstance(command, dict) and isinstance(command.get("token"), str):
            tokens.append(command["token"])
        if isinstance(node, dict) and isinstance(node.get("continuation"), str):
            tokens.append(node["continuation"])
    return list(dict.fromkeys(tokens))


def _video_id_from_renderer(renderer: dict[str, Any]) -> str | None:
    if isinstance(renderer.get("videoId"), str):
        return renderer["videoId"]
    endpoint = renderer.get("navigationEndpoint") or renderer.get("onTap", {}).get("innertubeCommand")
    if isinstance(endpoint, dict):
        for node in _walk(endpoint):
            for key in ("videoId", "contentId"):
                if isinstance(node.get(key), str) and VIDEO_ID_RE.match(node[key]):
                    return node[key]
    if isinstance(renderer.get("contentId"), str) and VIDEO_ID_RE.match(renderer["contentId"]):
        return renderer["contentId"]
    return None


def _parse_video_renderers(payload: Any) -> list[dict[str, Any]]:
    videos: list[dict[str, Any]] = []
    for renderer_name, renderer in _renderer_items(payload):
        if renderer_name not in {"videoRenderer", "playlistVideoRenderer", "lockupViewModel", "shortsLockupViewModel"}:
            continue
        video_id = _video_id_from_renderer(renderer)
        title = _text(renderer.get("title")) or _text(renderer.get("metadata")) or _text(renderer)
        if not video_id and not title:
            continue
        videos.append({
            "renderer": renderer_name,
            "video_id": video_id,
            "title": title,
            "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
            "duration_text": _text(renderer.get("lengthText")),
            "view_count_text": _text(renderer.get("viewCountText")),
            "published_time_text": _text(renderer.get("publishedTimeText")),
        })
    return videos


def _parse_playlist_renderers(payload: Any) -> list[dict[str, Any]]:
    playlists: list[dict[str, Any]] = []
    for renderer_name, renderer in _renderer_items(payload):
        if renderer_name not in {"playlistRenderer", "gridPlaylistRenderer", "lockupViewModel"}:
            continue
        playlist_id = renderer.get("playlistId") or renderer.get("contentId")
        if not playlist_id and renderer_name == "lockupViewModel":
            continue
        playlists.append({
            "renderer": renderer_name,
            "playlist_id": playlist_id,
            "title": _text(renderer.get("title")) or _text(renderer.get("metadata")),
            "item_count": renderer.get("videoCount") or _text(renderer.get("videoCountText")),
        })
    return playlists


def _html_initial_json(html: str, variable: str) -> dict[str, Any] | None:
    marker = f"{variable} = "
    start = html.find(marker)
    if start == -1:
        marker = f"var {variable} = "
        start = html.find(marker)
    if start == -1:
        return None
    start += len(marker)
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(html)):
        char = html[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(html[start:index + 1])
    return None


def local_video_id_extraction(url_or_id: str) -> dict[str, Any]:
    value = (url_or_id or "").strip()
    if VIDEO_ID_RE.match(value):
        return result(True, {"video_id": value, "source_pattern": "raw_id"})
    parsed = urllib.parse.urlparse(value)
    query = urllib.parse.parse_qs(parsed.query)
    candidates = []
    candidates.extend(query.get("v", []))
    path_parts = [part for part in parsed.path.split("/") if part]
    if parsed.netloc.endswith("youtu.be") and path_parts:
        candidates.append(path_parts[0])
    for prefix in ("shorts", "embed", "live"):
        if prefix in path_parts:
            index = path_parts.index(prefix)
            if len(path_parts) > index + 1:
                candidates.append(path_parts[index + 1])
    for candidate in candidates:
        if VIDEO_ID_RE.match(candidate):
            return result(True, {"video_id": candidate, "source_pattern": "url"})
    return result(False, None, "not_found")


def static_oembed_video_card(payload: dict[str, Any] | None = None, **_: Any) -> dict[str, Any]:
    if not payload:
        return result(False, None, "not_available", path_type="static")
    keys = ["title", "author_name", "author_url", "thumbnail_url", "html"]
    return result(True, {key: payload.get(key) for key in keys}, path_type="static")


def static_thumbnails(video_id: str, size: str = "hqdefault") -> dict[str, Any]:
    extracted = local_video_id_extraction(video_id)
    if not extracted["ok"]:
        return extracted
    vid = extracted["data"]["video_id"]
    sizes = ["maxresdefault", "hqdefault", "mqdefault", "default"]
    selected = size if size in sizes else "hqdefault"
    return result(True, {
        "selected_size": selected,
        "url": f"https://i.ytimg.com/vi/{vid}/{selected}.jpg",
        "fallback_urls": [f"https://i.ytimg.com/vi/{vid}/{item}.jpg" for item in sizes],
    }, path_type="static")


def _parse_rss(xml_text: str | None, feed_url: str) -> dict[str, Any]:
    if not xml_text:
        return result(False, {"feed_url": feed_url}, "not_available", path_type="static")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return result(False, {"feed_url": feed_url}, "parse_error", path_type="static")
    ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
    entries = []
    for entry in root.findall("atom:entry", ns):
        entries.append({
            "video_id": _text(entry.findtext("yt:videoId", namespaces=ns)),
            "title": entry.findtext("atom:title", namespaces=ns),
            "published": entry.findtext("atom:published", namespaces=ns),
            "updated": entry.findtext("atom:updated", namespaces=ns),
        })
    return result(True, {"feed_url": feed_url, "entries": entries, "entry_count": len(entries)}, path_type="static")


def static_channel_rss(channel_id: str, xml_text: str | None = None) -> dict[str, Any]:
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    return _parse_rss(xml_text, feed_url)


def static_playlist_rss(playlist_id: str, xml_text: str | None = None) -> dict[str, Any]:
    feed_url = f"https://www.youtube.com/feeds/videos.xml?playlist_id={playlist_id}"
    return _parse_rss(xml_text, feed_url)


def api_autocomplete(payload: Any = None) -> dict[str, Any]:
    if payload is None:
        return result(False, None, "not_available", path_type="api")
    suggestions: list[str] = []
    if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], list):
        for item in payload[1]:
            if isinstance(item, list) and item:
                suggestions.append(str(item[0]))
            elif isinstance(item, str):
                suggestions.append(item)
    return result(bool(suggestions), {"suggestions": suggestions}, "success" if suggestions else "empty_result", path_type="api")


def api_global_search(payload: Any = None) -> dict[str, Any]:
    if payload is None:
        return result(False, None, "not_available", path_type="api")
    renderers = [{"renderer": name, "title": _text(renderer), "video_id": _video_id_from_renderer(renderer)} for name, renderer in _renderer_items(payload)]
    data = {
        "renderers": renderers,
        "renderer_types": sorted({item["renderer"] for item in renderers}),
        "videos": _parse_video_renderers(payload),
        "playlists": _parse_playlist_renderers(payload),
        "continuations": _continuations(payload),
    }
    return result(bool(renderers), data, "success" if renderers else "empty_result", path_type="api")


def api_search_continuation(payload: Any = None) -> dict[str, Any]:
    parsed = api_global_search(payload)
    parsed["data"] = parsed["data"] or {}
    parsed["data"]["continuation_result"] = True
    return parsed | {"path_type": "api"}


def api_search_filters(surface_map: dict[str, Any] | None = None) -> dict[str, Any]:
    surface_map = surface_map or load_surface_map()
    return result(True, {"filter_groups": surface_map["search"]["filter_groups"]}, path_type="hybrid")


def api_search_chips(surface_map: dict[str, Any] | None = None) -> dict[str, Any]:
    surface_map = surface_map or load_surface_map()
    return result(True, {"chips": surface_map["search"]["chips"]}, path_type="hybrid")


def browser_channel_local_search(payload: Any = None) -> dict[str, Any]:
    parsed = api_global_search(payload)
    parsed["path_type"] = "browser"
    return parsed


def api_player_metadata(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not payload:
        return result(False, None, "not_available", path_type="api")
    player = payload.get("ytInitialPlayerResponse", payload)
    status = player.get("playabilityStatus", {})
    if status.get("status") == "LOGIN_REQUIRED":
        return result(False, {"playabilityStatus": status}, "login_required", path_type="api")
    details = player.get("videoDetails", {})
    microformat = player.get("microformat", {}).get("playerMicroformatRenderer", {})
    data = {
        "playabilityStatus": status,
        "videoDetails": details,
        "microformat": microformat,
        "captions": player.get("captions", {}),
        "storyboards": player.get("storyboards", {}),
    }
    return result(bool(status or details), data, "success" if status or details else "unsupported_shape", path_type="api")


def api_watch_next_detail(payload: Any = None) -> dict[str, Any]:
    if payload is None:
        return result(False, None, "not_available", path_type="api")
    renderers = _renderer_items(payload)
    data = {
        "renderer_types": sorted({name for name, _ in renderers}),
        "panels": [name for name, _ in renderers if "Panel" in name or "panel" in name],
        "continuations": _continuations(payload),
    }
    return result(bool(renderers), data, "success" if renderers else "empty_result", path_type="api")


def _parse_comment_renderer(renderer: dict[str, Any], parent_comment_id: str | None = None) -> dict[str, Any]:
    comment_id = renderer.get("commentId") or renderer.get("commentEntityPayload", {}).get("properties", {}).get("commentId")
    return {
        "comment_id": comment_id,
        "parent_comment_id": parent_comment_id,
        "author": _text(renderer.get("authorText")),
        "text": _text(renderer.get("contentText")),
        "votes": _text(renderer.get("voteCount")),
        "time_text": _text(renderer.get("publishedTimeText")),
    }


def api_comments(payload: Any = None, max_threads: int | None = None, expand_replies: bool = True, max_reply_threads: int = 3) -> dict[str, Any]:
    if payload is None:
        return result(False, None, "not_available", path_type="hybrid")
    threads = []
    for _, thread in [(name, renderer) for name, renderer in _renderer_items(payload) if name == "commentThreadRenderer"]:
        comment = thread.get("comment", {}).get("commentRenderer", {})
        parsed = _parse_comment_renderer(comment)
        replies = []
        if expand_replies and len(threads) < max_reply_threads:
            for name, renderer in _renderer_items(thread.get("replies", {})):
                if name == "commentRenderer":
                    replies.append(_parse_comment_renderer(renderer, parsed.get("comment_id")))
        parsed["replies"] = replies
        parsed["reply_continuations"] = _continuations(thread.get("replies", {}))
        threads.append(parsed)
        if max_threads and len(threads) >= max_threads:
            break
    data = {
        "threads": threads,
        "thread_count": len(threads),
        "continuations": _continuations(payload),
        "bounded_reply_expansion": expand_replies,
    }
    return result(bool(threads), data, "success" if threads else "empty_result", path_type="hybrid")


def browser_transcript_panel(payload: Any = None) -> dict[str, Any]:
    if payload is None:
        return result(False, None, "not_available", path_type="hybrid")
    segments = []
    for name, renderer in _renderer_items(payload):
        if name != "transcriptCueRenderer":
            continue
        segments.append({
            "text": _text(renderer.get("cue")),
            "start_ms": renderer.get("startOffsetMs"),
            "duration_ms": renderer.get("durationMs"),
        })
    return result(bool(segments), {"segments": segments, "segment_count": len(segments)}, "success" if segments else "empty_result", path_type="hybrid")


def api_related_videos(payload: Any = None) -> dict[str, Any]:
    videos = _parse_video_renderers(payload)
    return result(bool(videos), {"videos": videos}, "success" if videos else "empty_result", path_type="hybrid")


def api_chapters_key_moments(payload: Any = None) -> dict[str, Any]:
    if payload is None:
        return result(False, None, "not_available", path_type="hybrid")
    chapters = []
    for name, renderer in _renderer_items(payload):
        if name != "macroMarkersListItemRenderer":
            continue
        chapters.append({
            "title": _text(renderer.get("title")),
            "time_text": _text(renderer.get("timeDescription")),
            "url": renderer.get("onTap", {}).get("commandMetadata", {}).get("webCommandMetadata", {}).get("url"),
        })
    return result(bool(chapters), {"chapters": chapters}, "success" if chapters else "empty_result", path_type="hybrid")


def browser_share_panel(payload: Any = None) -> dict[str, Any]:
    if payload is None:
        return result(False, None, "not_available", path_type="hybrid")
    return result(True, {
        "embed": _first_renderer(payload, "embedRenderer") is not None or "embed" in json.dumps(payload).lower(),
        "copy": "copy" in json.dumps(payload).lower(),
        "renderer_types": sorted({name for name, _ in _renderer_items(payload)}),
    }, path_type="hybrid")


def browser_action_surfaces(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if payload is None:
        return result(False, None, "not_available", path_type="browser")
    return result(True, {
        "save_available": bool(payload.get("save_available")),
        "report_available": bool(payload.get("report_available")),
        "auth_wall": bool(payload.get("auth_wall")),
    }, path_type="browser")


def static_embed_page(video_id: str | None = None, html_text: str | None = None) -> dict[str, Any]:
    if html_text:
        player = _html_initial_json(html_text, "ytInitialPlayerResponse")
        return result(True, {"player_metadata_shape": bool(player), "embeddability": "embed" in html_text.lower()}, path_type="static")
    if video_id:
        extracted = local_video_id_extraction(video_id)
        if extracted["ok"]:
            return result(True, {"iframe_route": f"https://www.youtube.com/embed/{extracted['data']['video_id']}"}, path_type="static")
    return result(False, None, "not_available", path_type="static")


def api_channel_resolution(handle_or_url: str, payload: Any = None) -> dict[str, Any]:
    value = (handle_or_url or "").strip()
    parsed = urllib.parse.urlparse(value if "://" in value else f"https://www.youtube.com/{value.lstrip('/')}")
    path_parts = [part for part in parsed.path.split("/") if part]
    if UC_CHANNEL_RE.match(value):
        return result(True, {"browseId": value, "channel_id": value, "resolution_source": "raw_uc"}, path_type="hybrid")
    if path_parts[:1] == ["channel"] and len(path_parts) > 1 and UC_CHANNEL_RE.match(path_parts[1]):
        return result(True, {"browseId": path_parts[1], "channel_id": path_parts[1], "resolution_source": "channel_url"}, path_type="hybrid")
    handle = None
    if value.startswith("@"):
        handle = value
    elif path_parts and path_parts[0].startswith("@"):
        handle = path_parts[0]
    browse_id = None
    if payload is not None:
        for node in _walk(payload):
            endpoint = node.get("browseEndpoint") if isinstance(node, dict) else None
            if isinstance(endpoint, dict) and isinstance(endpoint.get("browseId"), str):
                browse_id = endpoint["browseId"]
                break
    if browse_id:
        return result(True, {"browseId": browse_id, "channel_id": browse_id if browse_id.startswith("UC") else None, "canonical_handle": handle, "resolution_source": "payload"}, path_type="hybrid")
    if handle:
        return result(False, {"canonical_handle": handle}, "not_available", path_type="hybrid")
    return result(False, None, "not_found", path_type="hybrid")


def api_storyboard_spec(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not payload:
        return result(False, None, "not_available", path_type="api")
    player = payload.get("ytInitialPlayerResponse", payload)
    renderer = player.get("storyboards", {}).get("playerStoryboardSpecRenderer", {})
    spec = renderer.get("spec")
    if not spec:
        return result(False, None, "empty_result", path_type="api")
    parts = spec.split("|")
    base = parts[0]
    levels = []
    for raw in parts[1:]:
        fields = raw.split("#")
        levels.append({
            "raw_part_count": len(fields),
            "width": int(fields[0]) if fields and fields[0].isdigit() else None,
            "height": int(fields[1]) if len(fields) > 1 and fields[1].isdigit() else None,
            "tile_count": int(fields[2]) if len(fields) > 2 and fields[2].isdigit() else None,
        })
    return result(True, {"spec": spec, "url_template": base.split("?")[0], "levels": levels, "level_count": len(levels)}, path_type="api")


def api_video_live_status(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = api_player_metadata(payload)
    if not meta["ok"]:
        return meta
    details = meta["data"].get("videoDetails", {})
    microformat = meta["data"].get("microformat", {})
    live = microformat.get("liveBroadcastDetails", {})
    data = {
        "is_live_content": bool(details.get("isLiveContent")),
        "is_live_now": bool(live.get("isLiveNow")),
        "is_upcoming": bool(live.get("isUpcoming")),
        "premiere_state": live.get("premiereState"),
        "start_timestamp": live.get("startTimestamp"),
        "end_timestamp": live.get("endTimestamp"),
    }
    return result(True, data, path_type="api")


def api_channel_about(payload: Any = None) -> dict[str, Any]:
    if payload is None:
        return result(False, None, "not_available", path_type="api")
    data = {
        "description": _text(payload.get("description") if isinstance(payload, dict) else None) or _text(payload),
        "renderer_types": sorted({name for name, _ in _renderer_items(payload)}),
        "links": [node.get("url") for node in _walk(payload) if isinstance(node.get("url"), str)],
    }
    return result(bool(data["description"] or data["renderer_types"]), data, "success" if data["description"] or data["renderer_types"] else "empty_result", path_type="api")


def api_channel_videos(payload: Any = None, **_: Any) -> dict[str, Any]:
    videos = _parse_video_renderers(payload)
    return result(bool(videos), {"videos": videos, "continuations": _continuations(payload)}, "success" if videos else "empty_result", path_type="hybrid")


def api_channel_shorts(payload: Any = None, **_: Any) -> dict[str, Any]:
    parsed = api_channel_videos(payload)
    parsed["data"]["shorts"] = [item for item in parsed["data"]["videos"] if item["renderer"] == "shortsLockupViewModel"]
    return parsed


def api_channel_playlists(payload: Any = None) -> dict[str, Any]:
    playlists = _parse_playlist_renderers(payload)
    return result(bool(playlists), {"playlists": playlists, "continuations": _continuations(payload)}, "success" if playlists else "empty_result", path_type="hybrid")


def api_channel_community(payload: Any = None, max_results: int | None = None) -> dict[str, Any]:
    if payload is None:
        return result(False, None, "not_available", path_type="hybrid")
    posts = []
    for name, renderer in _renderer_items(payload):
        if name not in {"backstagePostThreadRenderer", "postRenderer"}:
            continue
        posts.append({"renderer": name, "text": _text(renderer), "has_poll": "poll" in json.dumps(renderer).lower()})
        if max_results and len(posts) >= max_results:
            break
    return result(bool(posts), {"posts": posts, "continuations": _continuations(payload)}, "success" if posts else "empty_result", path_type="hybrid")


def api_channel_streams(payload: Any = None, **_: Any) -> dict[str, Any]:
    parsed = api_channel_videos(payload)
    parsed["data"]["streams"] = parsed["data"]["videos"]
    return parsed


def api_playlist_contents(payload: Any = None, max_results: int | None = None) -> dict[str, Any]:
    if payload is None:
        return result(False, None, "not_available", path_type="api")
    videos = _parse_video_renderers(payload)
    if max_results:
        videos = videos[:max_results]
    data = {
        "videos": videos,
        "video_count": len(videos),
        "playlists": _parse_playlist_renderers(payload),
        "continuations": _continuations(payload),
        "renderer_types": sorted({name for name, _ in _renderer_items(payload)}),
    }
    return result(bool(videos or data["playlists"]), data, "success" if videos or data["playlists"] else "empty_result", path_type="api")


def api_trending(payload: Any = None) -> dict[str, Any]:
    parsed = api_global_search(payload)
    parsed["data"] = parsed["data"] or {}
    parsed["data"]["surface"] = "trending"
    return parsed | {"path_type": "api"}


def api_hashtag(payload: Any = None, tag: str | None = None) -> dict[str, Any]:
    parsed = api_global_search(payload)
    parsed["data"] = parsed["data"] or {}
    parsed["data"]["tag"] = tag
    parsed["data"]["surface"] = "hashtag"
    return parsed | {"path_type": "api"}


PRIMITIVE_FUNCTIONS: dict[str, Callable[..., dict[str, Any]]] = {
    "static_oembed_video_card": static_oembed_video_card,
    "static_thumbnails": static_thumbnails,
    "static_channel_rss": static_channel_rss,
    "api_autocomplete": api_autocomplete,
    "api_global_search": api_global_search,
    "api_search_filters": api_search_filters,
    "api_search_chips": api_search_chips,
    "browser_channel_local_search": browser_channel_local_search,
    "api_player_metadata": api_player_metadata,
    "api_watch_next_detail": api_watch_next_detail,
    "api_comments": api_comments,
    "browser_transcript_panel": browser_transcript_panel,
    "api_related_videos": api_related_videos,
    "api_chapters_key_moments": api_chapters_key_moments,
    "browser_share_panel": browser_share_panel,
    "browser_action_surfaces": browser_action_surfaces,
    "static_embed_page": static_embed_page,
    "local_video_id_extraction": local_video_id_extraction,
    "api_channel_resolution": api_channel_resolution,
    "api_search_continuation": api_search_continuation,
    "api_storyboard_spec": api_storyboard_spec,
    "api_video_live_status": api_video_live_status,
    "static_playlist_rss": static_playlist_rss,
    "api_channel_about": api_channel_about,
    "api_channel_videos": api_channel_videos,
    "api_channel_shorts": api_channel_shorts,
    "api_channel_playlists": api_channel_playlists,
    "api_channel_community": api_channel_community,
    "api_channel_streams": api_channel_streams,
    "api_playlist_contents": api_playlist_contents,
    "api_trending": api_trending,
    "api_hashtag": api_hashtag,
}
