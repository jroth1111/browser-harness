import importlib.util
import json
from pathlib import Path


YOUTUBE = Path(__file__).resolve().parents[1]


def load_module():
    spec = importlib.util.spec_from_file_location("youtube_primitives", YOUTUBE / "youtube_primitives.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fixture(name):
    return json.loads((YOUTUBE / "fixtures" / name).read_text(encoding="utf-8"))


def test_all_surface_map_primitives_have_callable_functions():
    module = load_module()
    surface_map = json.loads((YOUTUBE / "surface-map.json").read_text(encoding="utf-8"))
    primitive_ids = {item["id"] for item in surface_map["primitives"]}
    assert set(module.PRIMITIVE_FUNCTIONS) == primitive_ids


def test_video_id_extraction_accepts_supported_forms_and_rejects_invalid():
    module = load_module()
    samples = [
        "dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ?t=3",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
    ]
    for sample in samples:
        parsed = module.local_video_id_extraction(sample)
        assert parsed["ok"] is True
        assert parsed["data"]["video_id"] == "dQw4w9WgXcQ"
    assert module.local_video_id_extraction("not-a-video-id")["reason"] == "not_found"


def test_search_and_continuation_fixture_parse_mixed_renderers():
    module = load_module()
    data = fixture("search-renderers-sanitized.json")
    parsed = module.api_global_search(data)
    assert parsed["ok"] is True
    assert {"videoRenderer", "channelRenderer", "playlistRenderer", "continuationItemRenderer"} <= set(parsed["data"]["renderer_types"])
    assert parsed["data"]["continuations"] == ["REDACTED_CONTINUATION"]
    continuation = module.api_search_continuation(data)
    assert continuation["ok"] is True
    assert continuation["data"]["continuation_result"] is True


def test_watch_transcript_storyboard_live_and_comments_fixtures_parse():
    module = load_module()
    video = fixture("video-detail-sanitized.json")
    metadata = module.api_player_metadata(video)
    assert metadata["ok"] is True
    assert metadata["data"]["videoDetails"]["videoId"] == "VIDEO12345A"
    storyboard = module.api_storyboard_spec(video)
    assert storyboard["ok"] is True
    assert storyboard["data"]["level_count"] >= 1
    live_status = module.api_video_live_status(video)
    assert live_status["ok"] is True
    assert live_status["data"]["is_live_content"] is False

    transcript = module.browser_transcript_panel(fixture("transcript-sanitized.json"))
    assert transcript["ok"] is True
    assert transcript["data"]["segments"][0]["text"] == "Hello world"

    comments = module.api_comments(fixture("comments-replies-sanitized.json"), expand_replies=True)
    assert comments["ok"] is True
    assert comments["data"]["threads"][0]["replies"][0]["text"] == "A useful reply"
    assert comments["data"]["threads"][0]["reply_continuations"] == ["REDACTED_REPLY_CONTINUATION"]


def test_channel_playlist_and_discovery_fixtures_parse():
    module = load_module()
    about = fixture("channel-about-sanitized.json")
    resolution = module.api_channel_resolution("@SampleChannel", about)
    assert resolution["ok"] is True
    assert resolution["data"]["browseId"] == "UC_SAMPLE_CHANNEL"
    about_parsed = module.api_channel_about(about)
    assert about_parsed["ok"] is True
    assert "channelAboutFullMetadataRenderer" in about_parsed["data"]["renderer_types"]

    videos = module.api_channel_videos(fixture("channel-videos-sanitized.json"))
    assert videos["ok"] is True
    assert videos["data"]["videos"][0]["video_id"] == "VIDEO12345A"

    tabs = fixture("channel-tabs-sanitized.json")
    assert module.api_channel_shorts(tabs["shorts"])["data"]["shorts"][0]["video_id"] == "SHORT12345B"
    assert module.api_channel_playlists(tabs["playlists"])["data"]["playlists"][0]["playlist_id"] == "PL_SAMPLE"
    assert module.api_channel_community(tabs["community"])["ok"] is True
    assert module.api_channel_streams(tabs["streams"])["data"]["streams"][0]["video_id"] == "STREAM1234A"

    playlist = module.api_playlist_contents(fixture("playlist-sanitized.json"))
    assert playlist["ok"] is True
    assert playlist["data"]["video_count"] == 2

    discovery = fixture("trending-sanitized.json")
    assert module.api_trending(discovery["trending"])["ok"] is True
    hashtag = module.api_hashtag(discovery["hashtag"], tag="python")
    assert hashtag["ok"] is True
    assert hashtag["data"]["tag"] == "python"


def test_rss_and_ytdlp_shapes_are_no_media_and_absence_is_explicit():
    module = load_module()
    rss = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015">
      <entry>
        <yt:videoId>VIDEO12345A</yt:videoId>
        <title>Sample RSS video</title>
        <published>2026-04-28T00:00:00Z</published>
        <updated>2026-04-28T00:00:00Z</updated>
      </entry>
    </feed>"""
    parsed = module.static_playlist_rss("PL_SAMPLE", rss)
    assert parsed["ok"] is True
    assert parsed["data"]["entry_count"] == 1
    missing = module.static_playlist_rss("PL_SAMPLE")
    assert missing["reason"] == "not_available"

    for mode in ["dump_json", "flat_playlist", "comments", "subs"]:
        command = module.ytdlp_command_shape(mode, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert "--skip-download" in command
        assert "--cookies-from-browser" not in command


def test_caption_parsers_normalize_supported_payloads():
    spec = importlib.util.spec_from_file_location("caption_parsers", YOUTUBE / "caption_parsers.py")
    assert spec and spec.loader
    parsers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parsers)

    vtt = """WEBVTT

00:00:00.000 --> 00:00:01.000
Hello <b>world</b>

00:00:01.000 --> 00:00:02.000
Hello <b>world</b>

00:00:02.000 --> 00:00:03.000
Next line
    """
    assert parsers.vtt_to_text(vtt) == "Hello world\nNext line"

    vtt_with_cue_ids_and_one_word_captions = """WEBVTT

cue-1
00:00:00.000 --> 00:00:01.000
Hello

2
00:00:01.000 --> 00:00:02.000
OK

00:00:02.000 --> 00:00:03.000
Thanks
"""
    assert parsers.vtt_to_text(vtt_with_cue_ids_and_one_word_captions) == "Hello\nOK\nThanks"

    json3 = {"events": [{"segs": [{"utf8": "JSON"}, {"utf8": " captions"}]}]}
    assert parsers.json3_to_text(json.dumps(json3)) == "JSON captions"

    xml = '<transcript><text start="0">XML &amp; captions</text></transcript>'
    assert parsers.xml_to_text(xml) == "XML & captions"
    assert parsers.build_timedtext_url("dQw4w9WgXcQ", "en", "srv3") == (
        "https://www.youtube.com/api/timedtext?v=dQw4w9WgXcQ&lang=en&fmt=srv3"
    )

    module = load_module()
    parsed = module.local_caption_payload_text("json3", json.dumps(json3))
    assert parsed["ok"] is True
    assert parsed["data"]["line_count"] == 1

    invalid = module.local_caption_payload_text("json3", "{")
    assert invalid["ok"] is False
    assert invalid["reason"] == "parse_error"

    empty = module.local_caption_payload_text("vtt", "WEBVTT\n\n")
    assert empty["ok"] is False
    assert empty["reason"] == "empty_result"
