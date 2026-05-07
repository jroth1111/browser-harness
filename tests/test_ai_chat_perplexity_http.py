import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / "domain-skills" / "ai-chat-archive"
sys.path.insert(0, str(SKILL_ROOT))

from providers.perplexity.http import PerplexityHTTPAPI  # noqa: E402


def test_perplexity_list_threads_skips_malformed_rows(monkeypatch):
    api = PerplexityHTTPAPI({})

    monkeypatch.setattr(api, "_fetch_json", lambda *args, **kwargs: {
        "threads": [
            "not a row",
            {"uuid": "thread-1", "title": "Thread"},
        ],
    })

    assert api.list_threads() == [{"uuid": "thread-1", "title": "Thread"}]


def test_perplexity_all_threads_handles_malformed_rows(monkeypatch):
    api = PerplexityHTTPAPI({})
    batches = iter([
        [
            ["not", "a", "row"],
            {"uuid": "thread-1", "title": "Thread"},
        ],
        [],
    ])
    monkeypatch.setattr(api, "list_threads", lambda limit=50, offset=0: next(batches))

    assert api.all_threads(page_size=2) == [{"uuid": "thread-1", "title": "Thread"}]


def test_perplexity_extract_messages_skips_malformed_entries():
    messages = PerplexityHTTPAPI.extract_messages({
        "entries": [
            "not a row",
            {"uuid": "entry-1", "query_str": "What is this?", "answer": {"answer": "A reply."}},
        ],
    })

    assert [message["role"] for message in messages] == ["user", "assistant"]


def test_perplexity_extract_citations_skips_malformed_entries():
    citations = PerplexityHTTPAPI.extract_citations({
        "entries": [
            "not a row",
            {
                "text": [
                    {
                        "step_type": "SEARCH_RESULTS",
                        "content": {
                            "web_results": [
                                "not a citation",
                                {"url": "https://example.test", "name": "Example"},
                            ],
                        },
                    }
                ],
            },
        ],
    })

    assert citations == [{
        "label": "Example",
        "url": "https://example.test",
        "source_json": {"url": "https://example.test", "name": "Example"},
    }]


def test_perplexity_extract_messages_skips_malformed_steps():
    messages = PerplexityHTTPAPI.extract_messages({
        "entries": [
            {
                "uuid": "entry-1",
                "query_str": "What is this?",
                "text": [
                    "not a step",
                    {
                        "step_type": "FINAL",
                        "content": {"answer": "{\"answer\": \"A reply.\"}"},
                    },
                ],
            },
        ],
    })

    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[-1]["content"] == "A reply."


def test_perplexity_extract_citations_skips_malformed_steps():
    citations = PerplexityHTTPAPI.extract_citations({
        "entries": [
            {
                "text": [
                    "not a step",
                    {
                        "step_type": "SEARCH_RESULTS",
                        "content": {
                            "web_results": [{"url": "https://example.test"}],
                        },
                    },
                ],
            },
        ],
    })

    assert citations == [{
        "label": "",
        "url": "https://example.test",
        "source_json": {"url": "https://example.test"},
    }]
