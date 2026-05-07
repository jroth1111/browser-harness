import sys
from pathlib import Path


SKILL_ROOT = (
    Path(__file__).resolve().parents[3]
    / "domain-skills"
    / "ai-chat-archive"
)
sys.path.insert(0, str(SKILL_ROOT))

from lib.render import render_thread_markdown  # noqa: E402


def test_render_thread_markdown_tolerates_non_numeric_artifact_sizes():
    markdown = render_thread_markdown({
        "title": "Thread",
        "messages": [],
        "artifacts": [
            {
                "label": "notes.txt",
                "artifact_type": "text",
                "storage_kind": "text",
                "text_length": "not-a-number",
            },
            {
                "label": "image.png",
                "artifact_type": "image",
                "storage_kind": "binary",
                "byte_length": "large",
            },
        ],
    })

    assert "- **notes.txt** (text) - captured" in markdown
    assert "- **image.png** (image) - captured" in markdown
