# Helper Migration Map

Classification of every top-level helper in `helpers.py`. Categories:

- **keep** — stays in helpers.py, available in both dev and agent runtimes
- **keep_dev** — stays in helpers.py but only for dev runtime; agent runtime does not expose
- **move_adapter** — moves to a transport/adapter module; helpers.py re-exports thin wrapper
- **subordinate_broker** — functionality moves behind SessionBroker; helpers wrapper calls broker
- **delete** — removed entirely; no replacement in authority model

## Internal plumbing (keep in helpers.py, not exported)

| Line | Function | Category |
|------|----------|----------|
| 12 | `_load_env` | keep |
| 155 | `_require_key` | keep |
| 161 | `_target_infos` | keep |
| 168 | `_dict_rows` | keep |
| 172 | `_dict_value` | keep |
| 176 | `_text_value` | keep |
| 180 | `_string_field` | keep |
| 184 | `_int_count` | keep |
| 193 | `_status_code` | keep |
| 197 | `_env_int` | keep |
| 214 | `_is_recoverable` | keep |
| 266 | `_wait_until_load` | keep |
| 289 | `_wait_until_network_idle` | keep |
| 503 | `_raise_if_cdp_exception` | keep |
| 679 | `_cookie_matches_url` | subordinate_broker — internal to SessionBroker
| 694 | `_origin_url` | keep |
| 697 | `_browser_session_headers` | subordinate_broker — internal to HTTP transport
| 941 | `_debug_click_dpr` | keep |
| 1224 | `_enforce_tab_limit` | keep |
| 1304 | `_js_snippet` | keep |
| 1309 | `_js_exception_description` | keep |
| 1324 | `_decode_unserializable_js_value` | keep |
| 1340 | `_runtime_value` | keep |
| 1360 | `_runtime_evaluate` | keep |
| 1368 | `_has_return_statement` | keep |
| 1557 | `_ax_value` | keep |
| 1563 | `_ax_props` | keep |
| 1999 | `_real_user_agent` | move_adapter — used by http_get, belongs in transport
| 2048 | `_detect_cloudflare_type` | delete — absorbed into ChallengeStateMachine
| 2648 | `_authority_fetch` | keep — becomes the body of fetch() after Phase 3
| 2890 | `_close_sock` | keep |

## IPC layer (keep for dev, not agent-facing)

| Line | Function | Category |
|------|----------|----------|
| 68 | `_reconnect` | keep |
| 87 | `_recv` | keep |
| 109 | `_send` | keep |
| 219 | `with_session_recovery` | keep |
| 230 | `_recovered` | keep |

## CDP core

| Line | Function | Category |
|------|----------|----------|
| 244 | `cdp` | move_adapter — capability-gated wrapper; raw CDP not agent-facing

## Browser lifecycle

| Line | Function | Category |
|------|----------|----------|
| 249 | `drain_events` | keep |
| 250 | `endpoint_info` | keep |
| 253 | `launch_browser` | keep_dev — agent runtime uses ProviderRegistry
| 259 | `close_browser` | keep_dev

## Navigation

| Line | Function | Category |
|------|----------|----------|
| 329 | `smart_wait` | keep |
| 386 | `goto_url` | keep — used by NavigationController internally
| 425 | `goto_with_auth` | **delete** — replaced by NavigationController.goto with SessionBroker
| 456 | `navigate_via_google` | **delete** — WAF bypass, no replacement

## Page observation

| Line | Function | Category |
|------|----------|----------|
| 475 | `page_info` | keep |
| 511 | `page_info_js` | keep |
| 520 | `detect_block_page` | move_adapter — used by ChallengeStateMachine internally
| 627 | `page_content_status` | keep |
| 659 | `wait_for_content` | keep |

## Session/cookie helpers

| Line | Function | Category |
|------|----------|----------|
| 682 | `browser_cookies` | subordinate_broker — returns redacted manifest, not raw cookies
| 690 | `browser_cookie_header` | **delete** — raw cookie access removed; broker handles internally
| 700 | `http_get_browser_session_response` | subordinate_broker — delegates to HTTPTransport via broker
| 716 | `login_session_manifest` | subordinate_broker — delegates to SessionBroker.redacted_manifest
| 731 | `prompt_user_login` | keep — used by handoff CLI flow
| 742 | `http_get_browser_session` | **delete** — use bh_http.get or HTTPTransport
| 755 | `seed_browser_session` | **delete** — use SessionBroker.store_secret_bundle
| 778 | `browser_backend_info` | keep |
| 834 | `_backend_recommendation` | keep |
| 844 | `diagnose_url_capability` | keep |

## JSON extraction

| Line | Function | Category |
|------|----------|----------|
| 868 | `_extract_json_assignment` | keep |
| 907 | `_decode_nested_json_strings` | keep |
| 924 | `extract_argonaut_exchange` | keep |

## Input actions

| Line | Function | Category |
|------|----------|----------|
| 953 | `click_at_xy` | keep_dev — low-level; ActionExecutor uses click_ref
| 995 | `type_text` | keep_dev |
| 1015 | `press_key` | keep |
| 1026 | `scroll` | keep |
| 1030 | `fill_input` | keep |
| 1070 | `wait_for_element` | keep |
| 1097 | `wait_for_network_idle` | keep |
| 1514 | `dispatch_key` | keep |
| 1525 | `upload_file` | keep |

## Screenshots and tabs

| Line | Function | Category |
|------|----------|----------|
| 1137 | `capture_screenshot` | keep |
| 1157 | `list_tabs` | keep |
| 1168 | `current_tab` | keep |
| 1172 | `switch_tab` | keep |
| 1181 | `close_tab` | keep |
| 1202 | `close_tabs` | keep |
| 1233 | `new_tab` | keep — NavigationController uses internally
| 1249 | `ensure_real_tab` | keep |
| 1263 | `iframe_target` | keep |
| 1271 | `poll_for_new_tab` | keep |
| 1288 | `wait` | keep |
| 1291 | `wait_for_load` | keep |
| 1296 | `wait_for_load_js` | keep |

## JS execution

| Line | Function | Category |
|------|----------|----------|
| 1406 | `js` | move_adapter — capability-gated; JS execution is a capability

## Dialog/permissions

| Line | Function | Category |
|------|----------|----------|
| 1428 | `install_blocker_probe` | keep |
| 1440 | `pending_blockers` | keep |
| 1459 | `dismiss_dialog` | keep |
| 1480 | `capture_dialogs` | keep |
| 1491 | `dialogs` | keep |
| 1496 | `grant_permissions` | keep |
| 1505 | `set_geolocation` | keep |

## AX / ref system

| Line | Function | Category |
|------|----------|----------|
| 1574 | `ax_snapshot` | keep |
| 1642 | `clear_refs` | keep |
| 1649 | `_resolve_ref_center` | keep |
| 1669 | `_resolve_ref_fallback` | keep |
| 1703 | `click_ref` | keep |

## Diagnostics

| Line | Function | Category |
|------|----------|----------|
| 1918 | `fill_rate_triage` | keep |
| 1961 | `capture_screenshot_trace` | keep |
| 1973 | `discover_local_cdp_endpoints` | keep |

## HTTP

| Line | Function | Category |
|------|----------|----------|
| 2019 | `http_get` | move_adapter — public HTTP goes through transport layer

## Challenge/bypass (delete)

| Line | Function | Category |
|------|----------|----------|
| 2058 | `detect_turnstile` | **delete** — absorbed into ChallengeStateMachine
| 2086 | `solve_turnstile` | **delete** — replaced by handoff protocol

## Fetch

| Line | Function | Category |
|------|----------|----------|
| 2729 | `fetch` | keep — authority-routed after Phase 3
| 2885 | `fetch_with_browser_session` | **delete** — use bh_http.execute with auth_required=True

## Resource management

| Line | Function | Category |
|------|----------|----------|
| 2190 | `block_resources` | keep |
| 2445 | `url_cluster` | keep |
| 2489 | `discover_api_endpoints` | keep |
| 2548 | `replay_endpoints` | keep |

## Misc

| Line | Function | Category |
|------|----------|----------|
| 58 | `_asset_dir` | keep |
| 435 | `_domain_skill_dir` | keep |

## Summary

| Category | Count |
|----------|-------|
| keep | 78 |
| keep_dev | 4 |
| move_adapter | 4 (cdp, js, http_get, detect_block_page) |
| subordinate_broker | 4 (browser_cookies, http_get_browser_session_response, login_session_manifest, _cookie_matches_url) |
| **delete** | 8 (goto_with_auth, navigate_via_google, browser_cookie_header, http_get_browser_session, seed_browser_session, detect_turnstile, solve_turnstile, fetch_with_browser_session) |

After Phase 4, `helpers.py` should drop from ~2900 LOC to ~2200 LOC (deleting ~700 LOC of bypass/session/solver code).
After Phase 8 file moves (extracting adapters), target below 2000 LOC.
