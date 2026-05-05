# Crosswalk: browser-harness YouTube vs ../youtube

This file records what the browser-harness domain skill can borrow from the
standalone `../youtube` skill while preserving different responsibilities.
Browser-harness remains the browser/CDP surface authority; `../youtube` remains
the no-key workflow/runtime skill for transcripts, captions, search, and batch
archives.

| ../youtube primitive | browser-harness equivalent | Notes |
| --- | --- | --- |
| `yt_dlp_single_metadata_subtitles` | `api_player_metadata`, `ytdlp_dump_json` fallback | Browser-harness records metadata surfaces first; yt-dlp is optional Tier 4. |
| `yt_dlp_write_sub_files` | `ytdlp_write_sub` fallback | Degraded subtitle fallback only, always `--skip-download`. |
| `watch_page_caption_tracks` | `api_player_metadata` | Caption track presence is metadata; raw caption URLs stay redacted. |
| `timedtext_direct_xml` | `timedtext_non_empty_body_probe` | Probe only after a safe caption-track source exists. |
| `browser_transcript_panel_dom` | `browser_transcript_panel` | Direct overlap; browser-harness owns CDP surface details. |
| `hidden_tab_bulk_dom` | out of scope | Requires batch orchestration; see `batch-policy.md` before adding. |
| `yt_dlp_channel_flat_playlist` | `ytdlp_flat_playlist` fallback | Degraded enumeration fallback for channel/playlist videos. |
| `yt_dlp_channel_rich_playlist` | `ytdlp_flat_playlist` fallback | Browser-harness does not make yt-dlp rich metadata primary. |
| `channel_videos_html_initial_data` | `api_channel_videos`, `direct_channel_html` | Browser-harness tracks tab params, renderers, and continuations. |
| `youtubei_browse_continuations` | `api_channel_videos`, `api_playlist_contents` | Shared page-derived browse continuation posture. |
| `rss_uploads_feed` | `static_channel_rss` | Conditional/opportunistic; RSS 404 must not mark channel unavailable. |
| `yt_dlp_search` | `ytdlp_ytsearch` fallback | Degraded video-oriented search, not a mixed-renderer substitute. |
| `yt_dlp_search_local_date_filter` | out of scope | Local ranking/date filtering belongs to workflow/runtime code. |
| `search_html_channel_filter` | `api_search_filters`, `api_global_search` | Browser-harness records filter tokens and renderer shape. |
| `search_html_initial_data` | `api_global_search` | Direct overlap for public search initial data. |
| `youtubei_search_continuations` | `api_search_continuation` | Direct overlap for page-derived search continuation. |
| `creator_corpus_topic_filter` | out of scope | Requires transcript corpus and local search index. |
| `creator_inception_pagination` | out of scope until batch policy is implemented | Broad channel collection requires checkpoints and stop conditions. |
| `json3_caption_parser` | `caption_parsers.json3_to_text` | Borrowed as local parser helper, not a downloader. |
| `ttml_srv3_xml_parser` | `caption_parsers.xml_to_text` | Borrowed as local parser helper. |
| `markdown_archive_export` | out of scope | Export/archive workflow belongs to `../youtube`. |
| `explicit_cookie_file_ytdlp` | out of scope | Browser-harness forbids silent browser-cookie import in committed artifacts. |
| `ios_android_client_retry` | out of scope | Alternate yt-dlp clients are runtime retry policy, not surface mapping. |
| `local_audio_asr_opt_in` | out of scope | Requires explicit media handling and generated-transcript labeling. |

## Adopted Lessons

- Keep RSS as a conditional probe, not a reliable happy path.
- Treat `yt-dlp` as auditable Tier 4 evidence, not equivalent renderer coverage.
- Reuse caption parsers for payloads already obtained by safe routes.
- Add method-level live-smoke evidence alongside route-level browser evidence.
- Keep explicit failure records instead of traceback or fabricated data.
