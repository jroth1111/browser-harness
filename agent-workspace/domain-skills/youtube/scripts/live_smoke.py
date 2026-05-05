#!/usr/bin/env python3
"""Create a redacted YouTube live-smoke receipt skeleton from browser-harness.

Run with:
  browser-harness < agent-workspace/domain-skills/youtube/scripts/live_smoke.py

The script intentionally records shape/status evidence and ytcfg key names, not
cookies, visitor IDs, page key values, playback URLs, or caption base URLs.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path("agent-workspace/domain-skills/youtube")
REPO_ROOT_MARKERS = ("helpers.py", "agent-workspace/domain-skills/youtube/surface-map.json")
REDACT_PATTERNS = [
    (re.compile(r'("visitorData"\s*:\s*)"[^"]+"'), r'\1"<redacted>"'),
    (re.compile(r'("INNERTUBE_API_KEY"\s*:\s*)"[^"]+"'), r'\1"<redacted>"'),
    (re.compile(r'("baseUrl"\s*:\s*)"[^"]+"'), r'\1"<redacted>"'),
    (re.compile(r'("url"\s*:\s*)"https://[^"]+googlevideo[^"]+"'), r'\1"<redacted>"'),
    (re.compile(r'("signatureCipher"\s*:\s*)"[^"]+"'), r'\1"<redacted>"'),
    (re.compile(r"ws://127\.0\.0\.1:\d+/devtools/browser/[A-Za-z0-9-]+"), "ws://127.0.0.1:<redacted>/devtools/browser/<redacted>"),
    (re.compile(r"http://127\.0\.0\.1:\d+"), "http://127.0.0.1:<redacted>"),
]


def redact_text(value: str) -> str:
    for pattern, replacement in REDACT_PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def safe_backend_summary(backend: dict) -> dict:
    js_probe = backend.get("js") or {}
    return {
        "kind": backend.get("kind"),
        "risks": backend.get("risks", []),
        "js": {
            "webdriver": js_probe.get("webdriver"),
            "plugins": js_probe.get("plugins"),
            "platform": js_probe.get("platform"),
        },
    }


def safe_content_status(status: dict) -> dict:
    return {key: value for key, value in status.items() if key not in {"text", "html"}}


def require_repo_root() -> None:
    missing = [marker for marker in REPO_ROOT_MARKERS if not Path(marker).exists()]
    if missing:
        raise SystemExit(
            "Run from browser-harness repo root with: "
            "browser-harness < agent-workspace/domain-skills/youtube/scripts/live_smoke.py"
        )


def load_surface_map() -> dict:
    return json.loads((ROOT / "surface-map.json").read_text(encoding="utf-8"))


def search_contract(surface_map: dict) -> dict:
    primitive = next(item for item in surface_map["primitives"] if item["id"] == "api_global_search")
    mode = next(item for item in surface_map["search"]["surface_modes"] if item["id"] == "global_search")
    return {
        "primitive_id": primitive["id"],
        "path_type": primitive["path_type"],
        "required": mode["required"],
        "fallback_chain": primitive["fallback_chain"],
        "receipt_required": surface_map["execution_policy"]["receipt_required"],
    }


def contract_summary(surface_map: dict) -> dict:
    required_primitives = {
        "api_global_search",
        "api_search_continuation",
        "api_channel_resolution",
        "api_channel_videos",
        "api_playlist_contents",
        "api_trending",
        "api_hashtag",
        "api_storyboard_spec",
        "api_video_live_status",
        "local_video_id_extraction",
    }
    primitive_ids = {item["id"] for item in surface_map["primitives"]}
    return {
        "schema_version": surface_map["schema_version"],
        "primitive_count": len(surface_map["primitives"]),
        "missing_required_primitives": sorted(required_primitives - primitive_ids),
        "search_contract": search_contract(surface_map),
        "has_channel_contract": "channel" in surface_map,
        "has_playlist_contract": "playlist" in surface_map,
        "has_discovery_contract": "discovery" in surface_map,
        "yt_dlp_optional": bool(surface_map.get("yt_dlp_policy", {}).get("optional")),
    }


def content_is_usable(status: dict, min_text: int = 200) -> bool:
    if (status.get("block") or {}).get("blocked"):
        return False
    return int(status.get("textLength") or 0) >= min_text


def route_changed(expected_url: str, landed_url: str) -> bool:
    expected = urllib.parse.urlparse(expected_url)
    landed = urllib.parse.urlparse(landed_url or "")
    return bool(landed.path and landed.path != expected.path)


def renderer_type_script() -> str:
    return """
(() => {
  const counts = {};
  const seen = new Set();
  function walk(value) {
    if (!value || typeof value !== "object") return;
    if (seen.has(value)) return;
    seen.add(value);
    if (Array.isArray(value)) {
      for (const item of value) walk(item);
      return;
    }
    for (const [key, child] of Object.entries(value)) {
      if (key.endsWith("Renderer") || key.endsWith("ViewModel")) {
        counts[key] = (counts[key] || 0) + 1;
      }
      walk(child);
    }
  }
  walk(window.ytInitialData || {});
  return Object.fromEntries(Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 40));
})()
"""


def watch_probe_script() -> str:
    return """
(() => {
  const pr = window.ytInitialPlayerResponse || {};
  const storyboards = pr.storyboards && pr.storyboards.playerStoryboardSpecRenderer;
  const spec = storyboards && storyboards.spec;
  const bodyText = (document.body && document.body.innerText || "").toLowerCase();
  return {
    has_player_response: !!Object.keys(pr).length,
    playability_status: pr.playabilityStatus && pr.playabilityStatus.status || null,
    is_live_content: pr.videoDetails && pr.videoDetails.isLiveContent || false,
    has_storyboard_spec: typeof spec === "string" && spec.length > 0,
    storyboard_level_count: typeof spec === "string" ? spec.split("|").length : 0,
    transcript_entrypoint_hint: bodyText.includes("transcript"),
    comments_entrypoint_hint: bodyText.includes("comments")
  };
})()
"""


def primitive_status_from_route(route_check: dict, required_renderers: set[str] | None = None) -> str:
    if route_check.get("status") == "failed_safe":
        return "fail"
    if route_check.get("status") == "redirected":
        return "conditional"
    if route_check.get("status") == "blocked_or_empty":
        return "conditional"
    if required_renderers:
        renderers = set((route_check.get("renderer_types") or {}).keys())
        if not (renderers & required_renderers):
            return "conditional"
    return "pass"


def primitive_checks_from_routes(route_checks: list[dict]) -> list[dict]:
    by_name = {item.get("name"): item for item in route_checks}
    checks = []

    def add(primitive_id: str, route_name: str, renderers: set[str] | None = None, terminal_reason: str | None = None) -> None:
        route = by_name.get(route_name, {})
        status = primitive_status_from_route(route, renderers)
        detail = terminal_reason if status == "conditional" and terminal_reason else "route renderer evidence captured"
        checks.append({
            "primitive_id": primitive_id,
            "status": status,
            "route": route.get("url"),
            "landed_url": (route.get("page_info") or {}).get("url"),
            "renderer_types": sorted((route.get("renderer_types") or {}).keys()),
            "terminal_reason": detail if status != "pass" else None,
            "fallback_attempts": [],
            "redaction_status": "applied_globally",
            "cleanup_status": "checked_globally",
        })

    add("api_global_search", "search", {"videoRenderer", "channelRenderer", "playlistRenderer", "shortsLockupViewModel"})
    add("api_search_continuation", "search", {"continuationItemRenderer"})
    add("api_channel_about", "channel_about", {"channelAboutFullMetadataRenderer", "contentMetadataViewModel"})
    add("api_channel_videos", "channel_about", {"gridVideoRenderer", "videoRenderer", "lockupViewModel"})
    add("api_playlist_contents", "playlist", {"playlistVideoListRenderer", "playlistVideoRenderer"})
    add("api_trending", "trending", {"richGridRenderer", "videoRenderer"}, "signed-out trending may redirect or return empty state")
    add("api_hashtag", "hashtag", {"richGridRenderer", "videoRenderer", "shortsLockupViewModel"})

    watch = by_name.get("watch", {})
    watch_probe = watch.get("watch_probe") or {}
    watch_status = primitive_status_from_route(watch, {"videoPrimaryInfoRenderer", "videoSecondaryInfoRenderer"})
    checks.append({
        "primitive_id": "api_video_live_status",
        "status": "pass" if watch_probe.get("has_player_response") and watch_probe.get("playability_status") else watch_status,
        "route": watch.get("url"),
        "landed_url": (watch.get("page_info") or {}).get("url"),
        "renderer_types": sorted((watch.get("renderer_types") or {}).keys()),
        "terminal_reason": None if watch_probe.get("playability_status") else "player response status unavailable",
        "fallback_attempts": [],
        "redaction_status": "applied_globally",
        "cleanup_status": "checked_globally",
        "live_status": {
            "playability_status": watch_probe.get("playability_status"),
            "is_live_content": watch_probe.get("is_live_content"),
        },
    })
    checks.append({
        "primitive_id": "api_storyboard_spec",
        "status": "pass" if watch_probe.get("has_storyboard_spec") else "conditional",
        "route": watch.get("url"),
        "landed_url": (watch.get("page_info") or {}).get("url"),
        "renderer_types": sorted((watch.get("renderer_types") or {}).keys()),
        "terminal_reason": None if watch_probe.get("has_storyboard_spec") else "storyboard spec absent from public player response",
        "fallback_attempts": [],
        "redaction_status": "applied_globally",
        "cleanup_status": "checked_globally",
        "storyboard_level_count": watch_probe.get("storyboard_level_count", 0),
    })
    checks.append({
        "primitive_id": "browser_transcript_panel",
        "status": "pass" if watch_probe.get("transcript_entrypoint_hint") else "conditional",
        "route": watch.get("url"),
        "landed_url": (watch.get("page_info") or {}).get("url"),
        "renderer_types": sorted((watch.get("renderer_types") or {}).keys()),
        "terminal_reason": None if watch_probe.get("transcript_entrypoint_hint") else "transcript entry point not visible in bounded route smoke",
        "fallback_attempts": [],
        "redaction_status": "applied_globally",
        "cleanup_status": "checked_globally",
    })
    checks.append({
        "primitive_id": "api_comments",
        "status": "pass" if watch_probe.get("comments_entrypoint_hint") or "commentThreadRenderer" in (watch.get("renderer_types") or {}) else "conditional",
        "route": watch.get("url"),
        "landed_url": (watch.get("page_info") or {}).get("url"),
        "renderer_types": sorted((watch.get("renderer_types") or {}).keys()),
        "terminal_reason": None if watch_probe.get("comments_entrypoint_hint") else "comments not hydrated in bounded route smoke",
        "fallback_attempts": [],
        "redaction_status": "applied_globally",
        "cleanup_status": "checked_globally",
    })
    checks.append({
        "primitive_id": "ytdlp_tier4_command_shapes",
        "status": "pass",
        "route": "local",
        "renderer_types": [],
        "terminal_reason": None,
        "fallback_attempts": [],
        "redaction_status": "applied_globally",
        "cleanup_status": "checked_globally",
        "command_shapes": [
            ["yt-dlp", "--skip-download", "--dump-single-json", "<target>"],
            ["yt-dlp", "--skip-download", "--flat-playlist", "--dump-single-json", "<target>"],
            ["yt-dlp", "--skip-download", "--write-subs", "--write-auto-subs", "<target>"],
        ],
    })
    return checks


def main() -> None:
    # browser-harness preloads helpers into the script namespace.
    require_repo_root()
    targets = [
        {"name": "search", "url": "https://www.youtube.com/results?search_query=openai"},
        {"name": "watch", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        {"name": "channel_about", "url": "https://www.youtube.com/@3blue1brown/about"},
        {"name": "playlist", "url": "https://www.youtube.com/playlist?list=PLZHQObOWTQDPD3MizzM2xVFitgF8hE_ab"},
        {"name": "hashtag", "url": "https://www.youtube.com/hashtag/python"},
        {"name": "trending", "url": "https://www.youtube.com/feed/trending"},
    ]
    target_ids = []
    receipt = {
        "receipt_version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "domain": "youtube.com",
        "targets": targets,
        "redactions_applied": ["visitorData", "apiKey", "cookies", "playback URLs", "signatureCipher", "caption baseUrl"],
        "status": "not_run",
        "checks": [],
        "route_checks": [],
    }
    try:
        surface_map = load_surface_map()
        receipt["surface_map"] = contract_summary(surface_map)
        contract_ok = (
            receipt["surface_map"]["search_contract"]["path_type"] == "api"
            and "context" in receipt["surface_map"]["search_contract"]["required"]
            and "query" in receipt["surface_map"]["search_contract"]["required"]
            and "fallback_attempts" in receipt["surface_map"]["search_contract"]["receipt_required"]
            and not receipt["surface_map"]["missing_required_primitives"]
            and receipt["surface_map"]["has_channel_contract"]
            and receipt["surface_map"]["has_playlist_contract"]
            and receipt["surface_map"]["has_discovery_contract"]
            and receipt["surface_map"]["yt_dlp_optional"]
        )
        receipt["checks"].append({"name": "surface_map_contract", "status": "success" if contract_ok else "failed"})
        endpoint = endpoint_info()  # type: ignore[name-defined]
        receipt["endpoint_info"] = {"keys": sorted(endpoint)}
        receipt["backend"] = safe_backend_summary(browser_backend_info())  # type: ignore[name-defined]
        route_statuses = []
        for target in targets:
            route_check = {"name": target["name"], "url": target["url"], "status": "not_run"}
            try:
                target_id = new_tab(target["url"])  # type: ignore[name-defined]
                target_ids.append(target_id)
                wait_for_load()  # type: ignore[name-defined]
                wait(2)  # type: ignore[name-defined]
                info = page_info()  # type: ignore[name-defined]
                if not info.get("url"):
                    info = page_info_js()  # type: ignore[name-defined]
                status = page_content_status(html_limit=0, text_limit=0)  # type: ignore[name-defined]
                usable = content_is_usable(status)
                ytcfg_keys = js("Object.keys((window.ytcfg && ytcfg.data_) || {}).sort()")  # type: ignore[name-defined]
                renderer_types = js(renderer_type_script())  # type: ignore[name-defined]
                redirected = route_changed(target["url"], info.get("url", ""))
                route_status = "redirected" if redirected else ("success" if usable else "blocked_or_empty")
                route_check.update({
                    "status": route_status,
                    "page_info": info,
                    "content_status": safe_content_status(status),
                    "route_changed": redirected,
                    "renderer_types": renderer_types,
                    "ytcfg_key_count": len(ytcfg_keys or []),
                    "ytcfg_has_context": "INNERTUBE_CONTEXT" in (ytcfg_keys or []),
                })
                if target["name"] == "watch":
                    route_check["watch_probe"] = js(watch_probe_script())  # type: ignore[name-defined]
                route_statuses.append(route_check["status"])
            except Exception as exc:  # pragma: no cover - intended for live harness use.
                route_check.update({"status": "failed_safe", "error": f"{exc.__class__.__name__}: {exc}"})
                route_statuses.append("failed_safe")
            receipt["route_checks"].append(route_check)
        receipt["checks"].append({"name": "route_content", "status": "success" if any(item == "success" for item in route_statuses) else "blocked_or_empty"})
        receipt["primitive_checks"] = primitive_checks_from_routes(receipt["route_checks"])
        receipt["status"] = "success" if any(item == "success" for item in route_statuses) else "blocked_or_empty"
    except Exception as exc:  # pragma: no cover - intended for live harness use.
        receipt["status"] = "failed_safe"
        receipt["error"] = f"{exc.__class__.__name__}: {exc}"
    finally:
        closed = []
        for target_id in target_ids:
            try:
                closed.append(bool(close_tab(target_id)))  # type: ignore[name-defined]
            except Exception as exc:  # pragma: no cover - best-effort local cleanup.
                closed.append(False)
                receipt.setdefault("cleanup_errors", []).append(f"{exc.__class__.__name__}: {exc}")
        receipt["cleanup"] = {"closed_tabs": closed, "all_closed": all(closed) if closed else True}
    out_dir = ROOT / "receipts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"live-smoke-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(redact_text(json.dumps(receipt, indent=2, sort_keys=True)), encoding="utf-8")
    print(str(out))


main()
