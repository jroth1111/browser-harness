import importlib.util
import os
import subprocess
import sys
from pathlib import Path


def test_render_airbnb_fixtures_imports_packaged_data_display():
    spec = importlib.util.spec_from_file_location(
        "render_airbnb_fixtures",
        Path("tools/render_airbnb_fixtures.py"),
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None

    spec.loader.exec_module(module)

    assert module.render_dataset.__module__ == "browser_harness.data_display"


def test_claude_share_transcript_script_is_import_safe_without_env():
    spec = importlib.util.spec_from_file_location(
        "extract_share_transcript",
        Path("domain-skills/claude-ai/extract-share-transcript.py"),
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None

    spec.loader.exec_module(module)

    assert callable(module.main)


def test_claude_share_transcript_cli_reports_missing_env():
    env = dict(os.environ)
    env.pop("CLAUDE_SHARE_URL", None)
    env.pop("OUTPUT_DIR", None)

    result = subprocess.run(
        [sys.executable, "domain-skills/claude-ai/extract-share-transcript.py"],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode != 0
    assert "set CLAUDE_SHARE_URL and OUTPUT_DIR env vars" in result.stderr


def test_youtube_live_smoke_script_is_import_safe():
    spec = importlib.util.spec_from_file_location(
        "youtube_live_smoke",
        Path("domain-skills/youtube/scripts/live_smoke.py"),
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None

    spec.loader.exec_module(module)

    assert callable(module.main)
