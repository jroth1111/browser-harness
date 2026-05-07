import json
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
YOUTUBE = ROOT / "domain-skills" / "youtube"


def load_surface_map():
    return json.loads((YOUTUBE / "surface-map.json").read_text(encoding="utf-8"))


def load_caption_parsers():
    path = YOUTUBE / "caption_parsers.py"
    spec = importlib.util.spec_from_file_location("youtube_caption_parsers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_youtube_primitives():
    path = YOUTUBE / "youtube_primitives.py"
    spec = importlib.util.spec_from_file_location("youtube_primitives", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_youtube_surface_map_has_unique_typed_primitives():
    data = load_surface_map()
    allowed = set(data["path_types"])
    ids = [primitive["id"] for primitive in data["primitives"]]
    assert len(ids) == len(set(ids))
    assert len(ids) >= 15
    for primitive in data["primitives"]:
        assert primitive["path_type"] in allowed
        assert primitive["primary"]
        assert primitive["inputs"]
        assert primitive["outputs"]
        assert primitive["evidence"]


def test_youtube_browser_harness_helper_coverage_is_explicit():
    data = load_surface_map()
    helpers = {helper["name"]: helper for helper in data["browser_harness_primitives"]}
    expected = {
        "endpoint_info",
        "browser_backend_info",
        "diagnose_url_capability",
        "detect_block_page",
        "discover_local_cdp_endpoints",
        "http_get",
        "http_get_browser_session",
        "http_get_browser_session_response",
        "fetch_with_browser_session",
        "seed_browser_session",
        "new_tab",
        "goto_url",
        "wait_for_load",
        "wait_for_load_js",
        "wait",
        "wait_for_content",
        "capture_screenshot",
        "capture_screenshot_trace",
        "click_at_xy",
        "type_text",
        "press_key",
        "dispatch_key",
        "scroll",
        "js",
        "page_info",
        "page_info_js",
        "page_content_status",
        "cdp",
        "drain_events",
        "ax_snapshot",
        "ensure_real_tab",
        "list_tabs",
        "current_tab",
        "switch_tab",
        "close_tab",
        "close_tabs",
        "iframe_target",
        "browser_cookies",
        "browser_cookie_header",
        "login_session_manifest",
        "prompt_user_login",
        "upload_file",
    }
    assert expected <= set(helpers)
    assert helpers["upload_file"]["use"].startswith("out of extraction scope")
    assert "never commit output" in helpers["browser_cookie_header"]["use"]


def test_youtube_json3_caption_parser_tolerates_malformed_payloads():
    parsers = load_caption_parsers()

    assert parsers.json3_to_text("{not valid json") == ""
    assert parsers.json3_to_text(json.dumps(["not", "an", "object"])) == ""
    assert parsers.json3_to_text(json.dumps({
        "events": [
            "not an event",
            {"segs": "not segment rows"},
            {"segs": [{"utf8": "Hello "}, {"utf8": "world"}]},
        ],
    })) == "Hello world"


def test_youtube_execution_policy_blocks_unsafe_fallbacks():
    data = load_surface_map()
    policy = data["execution_policy"]
    assert policy["stop_on"] == ["success"]
    assert "unsupported_shape" in policy["fallback_on"]
    forbidden = " ".join(policy["never_fallback_to"])
    assert "official YouTube Data API" in forbidden
    assert "OAuth" in forbidden
    assert "silent browser cookie read" in forbidden
    assert "account mutation" in forbidden
    assert "media download" in forbidden
    assert {"primitive_id", "path_type", "fallback_attempts", "negative_probe"} <= set(policy["receipt_required"])


def test_youtube_fallback_dags_are_declared_for_required_surfaces():
    data = load_surface_map()
    dags = data["fallback_dags"]
    for name in [
        "search_results",
        "search_continuation",
        "search_filters",
        "search_chips",
        "video_metadata",
        "watch_detail",
        "comments",
        "transcript",
        "channel_uploads",
        "channel_resolution",
        "channel_about",
        "channel_videos",
        "channel_shorts",
        "channel_playlists",
        "channel_community",
        "channel_streams",
        "playlist_contents",
        "playlist_rss",
        "trending",
        "hashtag",
        "storyboards",
        "live_status",
        "video_id_extraction",
        "thumbnails",
    ]:
        assert name in dags
        if name == "video_id_extraction":
            assert dags[name] == ["local_video_id_extraction"]
        else:
            assert len(dags[name]) >= 2
    assert dags["transcript"][0] == "browser_transcript_panel"
    assert "timedtext_non_empty_body_probe" in dags["transcript"]
    assert dags["thumbnails"] == [
        "thumbnail_maxresdefault",
        "thumbnail_hqdefault",
        "thumbnail_mqdefault",
        "thumbnail_default",
    ]


def test_youtube_primitive_fallback_references_are_known_and_typed():
    data = load_surface_map()
    primitive_ids = {primitive["id"] for primitive in data["primitives"]}
    fallback_nodes = {node["id"]: node for node in data["fallback_nodes"]}
    known = primitive_ids | set(fallback_nodes)
    for primitive in data["primitives"]:
        for fallback_id in primitive["fallback_chain"]:
            assert fallback_id in known
            if fallback_id in fallback_nodes:
                assert fallback_nodes[fallback_id]["path_type"] in data["path_types"]

    for chain in data["fallback_dags"].values():
        for fallback_id in chain:
            assert fallback_id in known


def test_youtube_search_parameters_filters_and_results_are_complete():
    data = load_surface_map()
    search = data["search"]
    modes = {mode["id"]: mode for mode in search["surface_modes"]}
    assert {
        "global_search",
        "filtered_global_search",
        "search_continuation",
        "search_chip",
        "search_filter_dialog",
        "channel_local_search",
        "channel_browse_search",
        "autocomplete",
    } <= set(modes)
    assert modes["filtered_global_search"]["required"] == ["context", "query", "params"]
    assert modes["search_continuation"]["required"] == ["context", "continuation"]

    params = {param["name"]: param for param in search["url_parameters"]}
    assert params["search_query"]["required"] is True
    for optional in ["sp", "hl", "gl", "persist_gl"]:
        assert params[optional]["required"] is False

    body_params = {param["name"]: param for param in search["innertube_body_parameters"]}
    assert body_params["context"]["required"] is True
    assert body_params["query"]["required"] is True
    assert body_params["params"]["required"] is False
    assert body_params["continuation"]["required"] is False

    groups = {group["group"]: group["filters"] for group in search["filter_groups"]}
    assert set(groups) == {"Type", "Duration", "Upload date", "Features", "Sort"}
    for filters in groups.values():
        for item in filters:
            assert "token" in item
            assert item["status"] in {"available", "default", "disabled", "selected"}
    assert {item["label"] for item in groups["Type"]} >= {"Videos", "Shorts", "Channels", "Playlists", "Movies"}
    assert {item["label"] for item in groups["Upload date"]} >= {"Last hour", "Today", "This week", "This month", "This year"}
    assert {item["label"] for item in groups["Sort"]} >= {"Relevance", "Upload date", "View count", "Rating"}
    assert next(item for item in groups["Sort"] if item["label"] == "Relevance")["status"] == "default"

    renderers = {surface["renderer"] for surface in search["result_surfaces"]}
    assert {
        "videoRenderer",
        "channelRenderer",
        "shortsLockupViewModel",
        "playlistRenderer",
        "lockupViewModel",
        "continuationItemRenderer",
        "backgroundPromoRenderer",
    } <= renderers


def test_youtube_video_detail_surfaces_are_mapped():
    data = load_surface_map()
    detail = data["video_detail"]
    endpoints = {endpoint["endpoint"]: endpoint for endpoint in detail["innertube_endpoints"]}
    assert "/youtubei/v1/player" in endpoints
    assert "/youtubei/v1/next" in endpoints
    assert "/youtubei/v1/get_transcript" in endpoints
    assert endpoints["/youtubei/v1/get_transcript"]["path_type"] == "hybrid"

    assert "ytcfg.data_" in detail["browser_globals"]
    assert "ytInitialPlayerResponse" in detail["browser_globals"]
    assert "ytInitialData" in detail["browser_globals"]
    assert "playabilityStatus" in detail["player_response_fields"]
    assert "videoPrimaryInfoRenderer" in detail["watch_initial_data_fields"]
    assert "related_lockupViewModel" in detail["watch_initial_data_fields"]
    assert "segment_text" in detail["transcript_fields"]
    assert "mutation_endpoint_not_called" in detail["action_fields"]


def test_youtube_docs_reference_the_structured_surface_map():
    required_docs = [
        "scraping.md",
        "overview.md",
        "workflows.md",
        "workflow-map.json",
        "primitives.md",
        "search.md",
        "video-detail.md",
        "channel.md",
        "playlist.md",
        "trending-discovery.md",
        "innertube.md",
        "fallback-chains.md",
        "fallbacks-and-verification.md",
        "failure-modes.md",
        "batch-policy.md",
        "crosswalk-youtube-skill.md",
        "surface-map.json",
        "surface-map.schema.json",
        "generated-surfaces.md",
        "reports/latest-summary.json",
        "youtube_primitives.py",
        "caption_parsers.py",
    ]
    for doc in required_docs:
        assert (YOUTUBE / doc).exists()
    entry = (YOUTUBE / "scraping.md").read_text(encoding="utf-8")
    for doc in required_docs[1:]:
        assert doc in entry
    for directory in ["fixtures", "receipts"]:
        assert directory in entry


def test_youtube_schema_matches_surface_map_contract():
    data = load_surface_map()
    schema = json.loads((YOUTUBE / "surface-map.schema.json").read_text(encoding="utf-8"))

    assert schema["properties"]["schema_version"]["minimum"] == 1
    assert schema["properties"]["domain"]["const"] == "youtube.com"
    assert data["schema_version"] == 2
    assert set(schema["required"]) <= set(data)
    assert set(schema["required"]) >= {
        "schema_version",
        "domain",
        "path_types",
        "forbidden",
        "execution_policy",
        "fallback_nodes",
        "browser_harness_primitives",
        "primitives",
        "search",
        "video_detail",
        "fallback_dags",
        "verification_probes",
    }

    primitive_required = schema["properties"]["primitives"]["items"]["required"]
    assert set(primitive_required) == {"id", "path_type", "primary", "fallback_chain", "inputs", "outputs", "evidence"}
    assert set(schema["properties"]["path_types"]["items"]["enum"]) == set(data["path_types"])
    for optional_section in ["channel", "playlist", "discovery", "innertube", "utilities", "yt_dlp_policy"]:
        assert optional_section in data
        assert optional_section in schema["properties"]
    assert "availability" in data
    assert "availability" in schema["properties"]
    assert data["availability"]["primitives"]["static_channel_rss"]["status"] == "conditional"
    assert data["availability"]["primitives"]["static_playlist_rss"]["status"] == "conditional"
    assert data["availability"]["fallback_nodes"]["ytdlp_ytsearch"]["status"] == "degraded"
    assert set(schema["properties"]["search"]["required"]) >= {
        "surface_modes",
        "url_parameters",
        "innertube_query_parameters",
        "innertube_body_parameters",
        "filter_groups",
        "result_surfaces",
    }
    assert set(schema["properties"]["video_detail"]["required"]) >= {
        "url_parameters",
        "browser_globals",
        "innertube_endpoints",
        "player_response_fields",
        "watch_initial_data_fields",
        "transcript_fields",
        "comment_fields",
        "share_fields",
        "action_fields",
    }
    filter_required = schema["properties"]["search"]["properties"]["filter_groups"]["items"]["properties"]["filters"]["items"]["required"]
    assert set(filter_required) == {"label", "token", "status"}
    probes = schema["properties"]["verification_probes"]
    assert probes["type"] == "object"
    assert set(probes["additionalProperties"]["required"]) == {"positive", "negative"}


def test_youtube_generated_surfaces_are_rendered_from_surface_map():
    spec = importlib.util.spec_from_file_location("youtube_render_docs", YOUTUBE / "scripts" / "render_docs.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    generated = (YOUTUBE / "generated-surfaces.md").read_text(encoding="utf-8")
    assert generated == module.render(load_surface_map())
    for primitive in load_surface_map()["primitives"]:
        assert primitive["id"] in generated
    assert "Conditional And Degraded Boundaries" in generated
    assert f"Primitive count: {len(load_surface_map()['primitives'])}" in generated
    assert "Receipt Requirements" in generated
    assert "source_url_or_endpoint_shape" in generated
    assert "static_channel_rss" in generated
    assert "ytdlp_ytsearch" in generated


def test_youtube_workflow_docs_reference_valid_primitives_and_crosswalk_is_explicit():
    data = load_surface_map()
    primitive_ids = {primitive["id"] for primitive in data["primitives"]}
    fallback_nodes = {node["id"] for node in data["fallback_nodes"]}
    known = primitive_ids | fallback_nodes

    workflows = (YOUTUBE / "workflows.md").read_text(encoding="utf-8")
    for primitive_id in [
        "api_global_search",
        "browser_transcript_panel",
        "api_channel_videos",
        "api_playlist_contents",
        "api_comments",
        "api_trending",
        "api_hashtag",
    ]:
        assert primitive_id in workflows
        assert primitive_id in known
    assert "official YouTube Data API" in workflows
    assert "browser-cookie import" in workflows
    for phrase in ["Expected output", "Unsafe paths", "Stop instead of retrying"]:
        assert phrase in workflows

    workflow_map = json.loads((YOUTUBE / "workflow-map.json").read_text(encoding="utf-8"))
    assert workflow_map["schema_version"] == 1
    assert len(workflow_map["workflows"]) == 10
    workflow_ids = {workflow["id"] for workflow in workflow_map["workflows"]}
    assert {"channel_resolution", "channel_tab_browsing"} <= workflow_ids
    for workflow in workflow_map["workflows"]:
        assert workflow["id"]
        assert workflow["goal"]
        assert workflow["primary_chain"]
        assert "fallback_chain" in workflow
        assert workflow["receipt_requirements"]
        assert workflow["unsafe_paths"]
        assert workflow["stop_rules"]
        assert workflow["expected_outputs"]
        for node_id in workflow["primary_chain"]:
            assert node_id in known

    crosswalk = (YOUTUBE / "crosswalk-youtube-skill.md").read_text(encoding="utf-8")
    for local_id in ["browser_transcript_panel", "api_global_search", "api_search_continuation", "api_channel_videos"]:
        assert local_id in crosswalk
    assert "out of scope" in crosswalk
    assert "RSS 404" in crosswalk


def test_youtube_failure_modes_and_batch_policy_cover_operational_boundaries():
    failure_modes = (YOUTUBE / "failure-modes.md").read_text(encoding="utf-8")
    for code in ["not_available", "not_found", "empty_result", "parse_error", "blocked", "timeout", "unsupported_shape"]:
        assert code in failure_modes
    for code in ["login_required", "members_only", "age_restricted"]:
        assert code in failure_modes
    assert "RSS returns 404" in failure_modes
    assert "Do not turn" not in failure_modes

    batch_policy = (YOUTUBE / "batch-policy.md").read_text(encoding="utf-8")
    for phrase in ["checkpoint", "skip ledger", "stop condition", "cleanup", "Never rely"]:
        assert phrase in batch_policy
    workflows = (YOUTUBE / "workflows.md").read_text(encoding="utf-8")
    assert workflows.count("batch-policy.md") >= 2


def test_youtube_sanitized_fixtures_cover_representative_renderer_shapes():
    fixture_paths = sorted((YOUTUBE / "fixtures").glob("*.json"))
    assert {path.name for path in fixture_paths} == {
        "channel-about-sanitized.json",
        "channel-tabs-sanitized.json",
        "channel-videos-sanitized.json",
        "comments-replies-sanitized.json",
        "comments-sanitized.json",
        "playlist-sanitized.json",
        "search-renderers-sanitized.json",
        "transcript-sanitized.json",
        "trending-sanitized.json",
        "video-detail-sanitized.json",
    }

    for path in fixture_paths:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        assert data["fixture"].startswith("youtube-")
        assert data["source"].startswith("synthetic shape fixture")
        assert data["redactions"]
        assert "REDACTED" in text
        assert "googlevideo.com" not in text
        assert '"visitorData":' not in text
        assert '"INNERTUBE_API_KEY":' not in text
        assert '"signatureCipher":' not in text
        assert "__Secure-" not in text
        assert "SAPISID" not in text

    search = json.loads((YOUTUBE / "fixtures" / "search-renderers-sanitized.json").read_text(encoding="utf-8"))
    renderer_names = {next(iter(renderer)) for renderer in search["renderers"]}
    expected_renderers = {surface["renderer"] for surface in load_surface_map()["search"]["result_surfaces"]}
    assert expected_renderers <= renderer_names

    detail = json.loads((YOUTUBE / "fixtures" / "video-detail-sanitized.json").read_text(encoding="utf-8"))
    assert detail["ytInitialPlayerResponse"]["playabilityStatus"]["status"] == "OK"
    assert "storyboards" in detail["ytInitialPlayerResponse"]
    assert detail["ytInitialData"]["engagementPanels"]

    transcript = json.loads((YOUTUBE / "fixtures" / "transcript-sanitized.json").read_text(encoding="utf-8"))
    assert transcript["request"]["endpoint"] == "/youtubei/v1/get_transcript"
    assert transcript["response"]["transcriptRenderer"]["body"]["transcriptBodyRenderer"]["cueGroups"]

    comments = json.loads((YOUTUBE / "fixtures" / "comments-sanitized.json").read_text(encoding="utf-8"))
    assert "commentThreadRenderer" in comments["comment_surface"]
    replies = json.loads((YOUTUBE / "fixtures" / "comments-replies-sanitized.json").read_text(encoding="utf-8"))
    assert "commentRepliesRenderer" in json.dumps(replies)
    channel = json.loads((YOUTUBE / "fixtures" / "channel-videos-sanitized.json").read_text(encoding="utf-8"))
    assert "richGridRenderer" in json.dumps(channel)
    tabs = json.loads((YOUTUBE / "fixtures" / "channel-tabs-sanitized.json").read_text(encoding="utf-8"))
    assert {"shorts", "playlists", "community", "streams"} <= set(tabs)
    playlist = json.loads((YOUTUBE / "fixtures" / "playlist-sanitized.json").read_text(encoding="utf-8"))
    assert "playlistVideoRenderer" in json.dumps(playlist)
    discovery = json.loads((YOUTUBE / "fixtures" / "trending-sanitized.json").read_text(encoding="utf-8"))
    assert {"trending", "hashtag"} <= set(discovery)


def test_youtube_receipts_and_live_smoke_are_redaction_first():
    receipts = sorted((YOUTUBE / "receipts").glob("*.json"))
    assert receipts
    for path in receipts:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        assert data["receipt_version"] >= 1
        assert data["domain"] == "youtube.com"
        assert set(data["redactions_applied"]) >= {"visitorData", "apiKey", "cookies", "signatureCipher"}
        assert "googlevideo.com" not in text
        assert '"visitorData":' not in text
        assert '"INNERTUBE_API_KEY":' not in text
        assert '"signatureCipher":' not in text
        assert "__Secure-" not in text
        assert "SAPISID" not in text
        if path.name.startswith("live-smoke-"):
            assert data["status"] in {"success", "blocked_or_empty", "failed_safe"}
            assert data["surface_map"]["search_contract"]["primitive_id"] == "api_global_search"
            assert data["surface_map"]["search_contract"]["path_type"] == "api"
            assert "fallback_attempts" in data["surface_map"]["search_contract"]["receipt_required"]
            assert any(check["name"] in {"surface_map_search_contract", "surface_map_contract"} for check in data["checks"])
            assert set(data["endpoint_info"]) == {"keys"}
            if "route_checks" in data:
                for route_check in data["route_checks"]:
                    assert "html" not in route_check.get("content_status", {})
                    assert "text" not in route_check.get("content_status", {})
                if "primitive_checks" in data:
                    required_keys = {"primitive_id", "status", "renderer_types", "redaction_status", "fallback_attempts", "cleanup_status"}
                    for primitive_check in data["primitive_checks"]:
                        assert required_keys <= set(primitive_check)
                        assert primitive_check["status"] in {"pass", "conditional", "degraded", "not_run", "fail"}
                assert data.get("cleanup", {}).get("all_closed") is True
            else:
                assert "html" not in data.get("content_status", {})
                assert "text" not in data.get("content_status", {})
                assert data.get("cleanup", {}).get("closed_tab") is True

    script = (YOUTUBE / "scripts" / "live_smoke.py").read_text(encoding="utf-8")
    assert "browser-harness < domain-skills/youtube/scripts/live_smoke.py" in script
    assert "require_repo_root()" in script
    assert "Run from browser-harness repo root" in script
    assert "load_surface_map()" in script
    assert "surface_map_contract" in script
    assert "new_tab(target[\"url\"])" in script
    assert "close_tab(target_id)" in script
    assert "page_info_js()" in script
    assert "redact_text" in script
    assert "page_content_status(html_limit=0, text_limit=0)" in script
    assert "content_is_usable(status)" in script
    assert "primitive_checks_from_routes" in script
    assert '"primitive_id": "ytdlp_tier4_command_shapes"' in script
    assert 'key not in {"text", "html"}' in script
    assert "browser_cookies" not in script
    assert "browser_cookie_header" not in script


def test_youtube_generated_report_summary_tracks_live_and_drift_state():
    spec = importlib.util.spec_from_file_location(
        "youtube_summarize_reports",
        YOUTUBE / "scripts" / "summarize_reports.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    generated = json.loads((YOUTUBE / "reports" / "latest-summary.json").read_text(encoding="utf-8"))
    assert generated == module.build_summary(YOUTUBE)
    assert generated["surface_map"]["primitive_count"] == len(load_surface_map()["primitives"])
    assert generated["live_primitive_count"] >= 1
    assert set(generated["live_status_counts"]) <= {"pass", "conditional", "degraded", "not_run", "fail"}
    assert "blocked_surfaces" in generated
    assert any(note["id"] == "static_channel_rss" for note in generated["drift_notes"])
    assert any(note["id"] == "ytdlp_ytsearch" for note in generated["drift_notes"])


def test_youtube_primitives_tolerate_malformed_renderer_metadata():
    module = load_youtube_primitives()

    player = module.api_player_metadata({
        "playabilityStatus": {"status": "OK"},
        "microformat": "not-an-object",
    })
    assert player["ok"] is True
    assert player["data"]["microformat"] == {}

    comments = module.api_comments({
        "commentThreadRenderer": {
            "comment": "not-an-object",
            "replies": {
                "commentRenderer": {
                    "commentEntityPayload": "not-an-object",
                    "contentText": {"simpleText": "reply"},
                },
            },
        },
    })
    assert comments["ok"] is True
    assert comments["data"]["threads"][0]["comment_id"] is None

    chapters = module.api_chapters_key_moments({
        "macroMarkersListItemRenderer": {
            "title": {"simpleText": "Intro"},
            "onTap": "not-an-object",
        },
    })
    assert chapters["ok"] is True
    assert chapters["data"]["chapters"][0]["url"] is None


def test_youtube_primitives_tolerate_malformed_storyboard_metadata():
    module = load_youtube_primitives()

    storyboard = module.api_storyboard_spec({
        "playabilityStatus": {"status": "OK"},
        "storyboards": "not-an-object",
    })
    assert storyboard["ok"] is False
    assert storyboard["reason"] == "empty_result"

    live = module.api_video_live_status({
        "playabilityStatus": {"status": "OK"},
        "videoDetails": {"isLiveContent": True},
        "microformat": {"playerMicroformatRenderer": {"liveBroadcastDetails": "not-an-object"}},
    })
    assert live["ok"] is True
    assert live["data"]["is_live_content"] is True
    assert live["data"]["is_live_now"] is False


def test_youtube_live_smoke_content_status_tolerates_malformed_shapes():
    spec = importlib.util.spec_from_file_location(
        "youtube_live_smoke",
        YOUTUBE / "scripts" / "live_smoke.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.content_is_usable("bad-status") is False
    assert module.content_is_usable({"textLength": "not-a-count", "block": {}}) is False
    assert module.content_is_usable({"textLength": 250, "block": {"blocked": True}}) is False
    assert module.content_is_usable({"textLength": 250, "block": "not-an-object"}) is True
    assert module.content_is_usable({"textLength": 250, "block": {}}) is True


def test_youtube_live_smoke_receipt_helpers_tolerate_malformed_shapes():
    spec = importlib.util.spec_from_file_location(
        "youtube_live_smoke",
        YOUTUBE / "scripts" / "live_smoke.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.safe_backend_summary("not-an-object") == {
        "kind": None,
        "risks": [],
        "js": {"webdriver": None, "plugins": None, "platform": None},
    }
    assert module.safe_backend_summary({"kind": "chromium", "js": "not-an-object"})["js"] == {
        "webdriver": None,
        "plugins": None,
        "platform": None,
    }
    assert module.safe_content_status("not-an-object") == {}


def test_youtube_forbidden_path_guard_passes_and_catches_synthetic_violations(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "assert_no_forbidden_paths",
        YOUTUBE / "scripts" / "assert_no_forbidden_paths.py",
    )
    assert spec and spec.loader
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)

    assert guard.scan(YOUTUBE) == []

    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"baseUrl": "https://example.test/not-redacted", "endpoint": "youtube.googleapis.com/youtube/v3", "token": "oauth_token"}\n'
        'yt-dlp --extract-audio https://www.youtube.com/watch?v=dQw4w9WgXcQ\n',
        encoding="utf-8",
    )
    findings = guard.scan(tmp_path)
    classes = {item["class"] for item in findings}
    assert {
        "raw_caption_base_url",
        "official_data_api_endpoint",
        "oauth_secret_material",
        "ytdlp_media_without_skip_download",
    } <= classes
