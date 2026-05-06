"""Unit tests for the ai-chat-archive implementation modules."""
import sqlite3
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent / "agent-workspace" / "domain-skills" / "ai-chat-archive"))

from lib.schema import init_db
from lib.archive_db import (
    connect, ensure_provider, ensure_account, upsert_thread, upsert_message,
    upsert_artifact, store_artifact_blob, upsert_citation, insert_capture,
    get_sync_state, set_sync_state, known_thread_keys, thread_last_capture,
    compute_content_hash, compute_thread_key, compute_message_key,
    compute_account_key, generate_run_id, generate_capture_id, new_run, finish_run,
)
from lib.render import render_thread_markdown
from lib.chatgpt_http import ChatGPTHTTPAPI


def _fresh_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""\
        PRAGMA foreign_keys=ON;
    """)
    init_db(":memory:")
    return connect(":memory:") if False else _init_mem(conn)


def _init_mem(conn):
    from lib.schema import SCHEMA_SQL
    conn.executescript(SCHEMA_SQL)
    conn.row_factory = sqlite3.Row
    return conn


def _setup_account(conn):
    ensure_provider(conn, "chatgpt", "ChatGPT")
    ak = compute_account_key("chatgpt", "user@example.com")
    ensure_account(conn, "chatgpt", ak, "user@example.com")
    return ak


# --- schema ---

def test_init_db_creates_all_tables():
    conn = sqlite3.connect(":memory:")
    from lib.schema import SCHEMA_SQL
    conn.executescript(SCHEMA_SQL)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()}
    expected = {
        "providers", "accounts", "threads", "captures", "messages",
        "artifacts", "artifact_blobs", "citations", "runs", "sync_state",
        "cdc_events",
    }
    assert expected <= tables, f"missing tables: {expected - tables}"


def test_init_db_creates_fts():
    conn = sqlite3.connect(":memory:")
    from lib.schema import SCHEMA_SQL
    conn.executescript(SCHEMA_SQL)
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view') ORDER BY name"
    ).fetchall()}
    fts = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' OR sql LIKE '%fts5%' ORDER BY name"
    ).fetchall()}
    virt = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND sql LIKE '%VIRTUAL%'"
    ).fetchall()}
    assert "capture_fts" in virt, "capture_fts virtual table missing"


# --- content hash ---

def test_content_hash_deterministic():
    h1 = compute_content_hash("hello world")
    h2 = compute_content_hash("hello world")
    assert h1 == h2
    assert h1.startswith("sha256:")


def test_content_hash_differs_for_different_input():
    h1 = compute_content_hash("hello")
    h2 = compute_content_hash("world")
    assert h1 != h2


# --- key computation ---

def test_thread_key_uses_provider_id():
    assert compute_thread_key("chatgpt", "abc-123") == "abc-123"


def test_message_key_stable():
    k1 = compute_message_key("tk1", "user", 0)
    k2 = compute_message_key("tk1", "user", 0)
    assert k1 == k2
    assert len(k1) == 24


def test_account_key_stable():
    k1 = compute_account_key("chatgpt", "user@example.com")
    k2 = compute_account_key("chatgpt", "user@example.com")
    assert k1 == k2
    assert len(k1) == 16


# --- run management ---

def test_run_lifecycle():
    conn = _init_mem(sqlite3.connect(":memory:"))
    run_id = generate_run_id()
    new_run(conn, run_id, {"script": "test"})
    row = conn.execute("SELECT status FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    assert row["status"] == "running"
    finish_run(conn, run_id, "complete", {"threads": 5})
    row = conn.execute("SELECT status, finished_at FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    assert row["status"] == "complete"
    assert row["finished_at"] is not None


# --- upsert idempotency ---

def test_upsert_thread_idempotent():
    conn = _init_mem(sqlite3.connect(":memory:"))
    ak = _setup_account(conn)
    tk = compute_thread_key("chatgpt", "conv-1")

    upsert_thread(conn, {
        "thread_key": tk, "provider_id": "chatgpt", "account_key": ak,
        "provider_thread_id": "conv-1",
        "canonical_url": "https://chatgpt.com/c/conv-1",
        "title": "My Chat", "status": "listed",
    })
    upsert_thread(conn, {
        "thread_key": tk, "provider_id": "chatgpt", "account_key": ak,
        "provider_thread_id": "conv-1",
        "canonical_url": "https://chatgpt.com/c/conv-1",
        "title": "My Chat (renamed)", "status": "listed",
    })

    count = conn.execute("SELECT count(*) FROM threads").fetchone()[0]
    assert count == 1
    row = conn.execute("SELECT title FROM threads WHERE thread_key = ?", (tk,)).fetchone()
    assert row["title"] == "My Chat (renamed)"


def test_upsert_message_inserts_new():
    conn = _init_mem(sqlite3.connect(":memory:"))
    ak = _setup_account(conn)
    tk = compute_thread_key("chatgpt", "conv-1")
    run_id = generate_run_id()
    new_run(conn, run_id, {})

    upsert_thread(conn, {
        "thread_key": tk, "provider_id": "chatgpt", "account_key": ak,
        "provider_thread_id": "conv-1", "status": "listed",
    })

    mk = upsert_message(conn, {
        "thread_key": tk, "role": "user", "ordinal": 0,
        "current_content": "Hello", "capture_id": "cap-1",
    }, run_id=run_id, provider_id="chatgpt", account_key=ak)

    count = conn.execute("SELECT count(*) FROM messages").fetchone()[0]
    assert count == 1
    assert mk is not None


def test_upsert_message_touch_when_unchanged():
    conn = _init_mem(sqlite3.connect(":memory:"))
    ak = _setup_account(conn)
    tk = compute_thread_key("chatgpt", "conv-1")
    run_id = generate_run_id()
    new_run(conn, run_id, {})

    upsert_thread(conn, {
        "thread_key": tk, "provider_id": "chatgpt", "account_key": ak,
        "provider_thread_id": "conv-1", "status": "listed",
    })

    upsert_message(conn, {
        "thread_key": tk, "role": "user", "ordinal": 0,
        "current_content": "Hello", "capture_id": "cap-1",
    }, run_id=run_id, provider_id="chatgpt", account_key=ak)

    upsert_message(conn, {
        "thread_key": tk, "role": "user", "ordinal": 0,
        "current_content": "Hello", "capture_id": "cap-2",
    }, run_id=run_id, provider_id="chatgpt", account_key=ak)

    count = conn.execute("SELECT count(*) FROM messages").fetchone()[0]
    assert count == 1

    cdc_events = conn.execute(
        "SELECT op FROM cdc_events WHERE entity_type='message' ORDER BY event_id"
    ).fetchall()
    ops = [e["op"] for e in cdc_events]
    assert ops[0] == "insert"
    assert ops[1] == "touch"


def test_upsert_message_update_when_changed():
    conn = _init_mem(sqlite3.connect(":memory:"))
    ak = _setup_account(conn)
    tk = compute_thread_key("chatgpt", "conv-1")
    run_id = generate_run_id()
    new_run(conn, run_id, {})

    upsert_thread(conn, {
        "thread_key": tk, "provider_id": "chatgpt", "account_key": ak,
        "provider_thread_id": "conv-1", "status": "listed",
    })

    upsert_message(conn, {
        "thread_key": tk, "role": "user", "ordinal": 0,
        "current_content": "Hello", "capture_id": "cap-1",
    }, run_id=run_id, provider_id="chatgpt", account_key=ak)

    upsert_message(conn, {
        "thread_key": tk, "role": "user", "ordinal": 0,
        "current_content": "Hello world", "capture_id": "cap-2",
    }, run_id=run_id, provider_id="chatgpt", account_key=ak)

    cdc_events = conn.execute(
        "SELECT op FROM cdc_events WHERE entity_type='message' ORDER BY event_id"
    ).fetchall()
    ops = [e["op"] for e in cdc_events]
    assert ops[0] == "insert"
    assert ops[1] == "update"


# --- artifacts ---

def test_artifact_upsert_and_blob():
    conn = _init_mem(sqlite3.connect(":memory:"))
    ak = _setup_account(conn)
    tk = compute_thread_key("chatgpt", "conv-1")
    run_id = generate_run_id()
    new_run(conn, run_id, {})

    upsert_thread(conn, {
        "thread_key": tk, "provider_id": "chatgpt", "account_key": ak,
        "provider_thread_id": "conv-1", "status": "listed",
    })

    art_key = upsert_artifact(conn, {
        "thread_key": tk, "label": "report.pdf",
        "artifact_type": "deep_research_report",
        "capture_id": "cap-1",
    }, run_id=run_id, provider_id="chatgpt", account_key=ak)

    assert art_key is not None

    store_artifact_blob(conn, art_key, "sha256:abc", b"PDF content here")

    blob = conn.execute(
        "SELECT bytes FROM artifact_blobs WHERE artifact_key = ?", (art_key,)
    ).fetchone()
    assert blob["bytes"] == b"PDF content here"


# --- sync state ---

def test_sync_state_round_trip():
    conn = _init_mem(sqlite3.connect(":memory:"))
    ak = _setup_account(conn)

    set_sync_state(conn, "chatgpt", ak, "last_offset", "28", {"total": 56})
    state = get_sync_state(conn, "chatgpt", ak, "last_offset")
    assert state is not None
    assert state["cursor_value"] == "28"
    assert state["state_json"]["total"] == 56


def test_known_thread_keys():
    conn = _init_mem(sqlite3.connect(":memory:"))
    ak = _setup_account(conn)

    upsert_thread(conn, {
        "thread_key": "conv-1", "provider_id": "chatgpt", "account_key": ak,
        "provider_thread_id": "conv-1", "status": "listed",
    })
    upsert_thread(conn, {
        "thread_key": "conv-2", "provider_id": "chatgpt", "account_key": ak,
        "provider_thread_id": "conv-2", "status": "listed",
    })

    keys = known_thread_keys(conn, "chatgpt", ak)
    assert keys == {"conv-1", "conv-2"}


# --- capture ---

def test_insert_and_query_capture():
    conn = _init_mem(sqlite3.connect(":memory:"))
    ak = _setup_account(conn)
    tk = compute_thread_key("chatgpt", "conv-1")
    run_id = generate_run_id()
    new_run(conn, run_id, {})
    capture_id = generate_capture_id()

    upsert_thread(conn, {
        "thread_key": tk, "provider_id": "chatgpt", "account_key": ak,
        "provider_thread_id": "conv-1", "status": "listed",
        "capture_id": capture_id,
    })

    insert_capture(conn, {
        "capture_id": capture_id,
        "run_id": run_id,
        "thread_key": tk,
        "captured_at": "2026-05-04T12:00:00Z",
        "source_context": "browser-dom",
        "completion_state": "complete",
        "normalized_json": "{}",
        "rendered_markdown": "# Test",
        "content_hash": "sha256:abc",
    })

    last = thread_last_capture(conn, tk)
    assert last is not None
    assert last["capture_id"] == capture_id
    assert last["completion_state"] == "complete"


# --- render ---

def test_render_thread_markdown_deterministic():
    capture = {
        "title": "Test Chat",
        "canonical_url": "https://chatgpt.com/c/abc",
        "messages": [
            {"role": "user", "ordinal": 0, "content": "Hello"},
            {"role": "assistant", "ordinal": 1, "content": "Hi there!"},
        ],
    }
    md1 = render_thread_markdown(capture)
    md2 = render_thread_markdown(capture)
    assert md1 == md2
    assert "## [user] #0" in md1
    assert "## [assistant] #1" in md1


def test_render_includes_artifacts_and_citations():
    capture = {
        "title": "Research",
        "messages": [],
        "artifacts": [
            {"label": "report.pdf", "artifact_type": "deep_research_report"},
        ],
        "citations": [
            {"label": "Wikipedia", "url": "https://wikipedia.org"},
        ],
    }
    md = render_thread_markdown(capture)
    assert "report.pdf" in md
    assert "deep_research_report" in md
    assert "[Wikipedia](https://wikipedia.org)" in md


def test_render_artifact_status():
    capture = {
        "title": "Test",
        "messages": [],
        "artifacts": [
            {"label": "Deep Research Report", "artifact_type": "deep_research_report",
             "storage_kind": "text", "text_length": 4200},
            {"label": "photo.png", "artifact_type": "generated_image",
             "storage_kind": "binary", "byte_length": 245000},
            {"label": "draft.py", "artifact_type": "canvas_document",
             "storage_kind": "metadata"},
        ],
    }
    md = render_thread_markdown(capture)
    assert "840 words, captured" in md
    assert "245KB, captured" in md
    assert "metadata only" in md


# --- CDC events ---

def test_cdc_events_track_insert_update_touch():
    conn = _init_mem(sqlite3.connect(":memory:"))
    ak = _setup_account(conn)
    tk = compute_thread_key("chatgpt", "conv-1")
    run_id = generate_run_id()
    new_run(conn, run_id, {})

    upsert_thread(conn, {
        "thread_key": tk, "provider_id": "chatgpt", "account_key": ak,
        "provider_thread_id": "conv-1", "status": "listed",
    })

    # Insert
    upsert_message(conn, {
        "thread_key": tk, "role": "user", "ordinal": 0,
        "current_content": "v1", "capture_id": "cap-1",
    }, run_id=run_id, provider_id="chatgpt", account_key=ak)

    # Touch (same content)
    upsert_message(conn, {
        "thread_key": tk, "role": "user", "ordinal": 0,
        "current_content": "v1", "capture_id": "cap-2",
    }, run_id=run_id, provider_id="chatgpt", account_key=ak)

    # Update (different content)
    upsert_message(conn, {
        "thread_key": tk, "role": "user", "ordinal": 0,
        "current_content": "v2", "capture_id": "cap-3",
    }, run_id=run_id, provider_id="chatgpt", account_key=ak)

    events = conn.execute(
        "SELECT op FROM cdc_events WHERE entity_type='message' ORDER BY event_id"
    ).fetchall()
    ops = [e["op"] for e in events]
    assert ops == ["insert", "touch", "update"]


# --- render: model metadata ---

def test_render_includes_model_slug():
    capture = {
        "title": "Test",
        "messages": [
            {"role": "assistant", "ordinal": 1, "content": "Hi", "model": "gpt-5"},
        ],
    }
    md = render_thread_markdown(capture)
    assert "(gpt-5)" in md


def test_render_omits_model_when_absent():
    capture = {
        "title": "Test",
        "messages": [
            {"role": "user", "ordinal": 0, "content": "Hello"},
        ],
    }
    md = render_thread_markdown(capture)
    assert "## [user] #0\n" in md


# --- HTTP API: mapping extraction ---

def test_extract_messages_from_mapping():
    detail = {
        "mapping": {
            "node_root": {"message": None, "children": ["node_a", "node_b"]},
            "node_a": {
                "message": {
                    "id": "msg_a",
                    "author": {"role": "user"},
                    "content": {"parts": ["Hello"]},
                    "create_time": 1000,
                },
                "children": [],
            },
            "node_b": {
                "message": {
                    "id": "msg_b",
                    "author": {"role": "assistant"},
                    "content": {"parts": ["Hi there!"]},
                    "metadata": {"model_slug": "gpt-5"},
                    "create_time": 2000,
                },
                "children": [],
            },
            "node_sys": {
                "message": {
                    "author": {"role": "system"},
                    "content": {"parts": ["instructions"]},
                    "create_time": 500,
                },
            },
        }
    }
    messages = ChatGPTHTTPAPI.extract_messages_from_mapping(detail)

    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello"
    assert messages[0]["ordinal"] == 1
    assert messages[0]["rich_parts"] == []
    assert messages[0]["artifact_refs"] == []
    assert messages[1]["role"] == "assistant"
    assert messages[1]["model"] == "gpt-5"
    assert messages[1]["ordinal"] == 2


def test_extract_messages_preserves_rich_parts():
    detail = {
        "mapping": {
            "n1": {
                "message": {
                    "id": "msg_1",
                    "author": {"role": "user"},
                    "content": {"parts": ["Search for X"]},
                    "create_time": 100,
                },
            },
            "n2": {
                "message": {
                    "id": "msg_2",
                    "author": {"role": "assistant"},
                    "content": {"parts": [
                        "Here is what I found.",
                        {"content_type": "image_asset_pointer",
                         "asset_pointer": "sediment://abc#file_001#p.jpg",
                         "size_bytes": 50000, "width": 512, "height": 512,
                         "fovea": None, "metadata": None},
                    ]},
                    "metadata": {"model_slug": "gpt-5"},
                    "create_time": 200,
                },
            },
        }
    }
    messages = ChatGPTHTTPAPI.extract_messages_from_mapping(detail)
    assert len(messages) == 2
    assert len(messages[1]["rich_parts"]) == 1
    assert messages[1]["rich_parts"][0]["content_type"] == "image_asset_pointer"
    assert len(messages[1]["artifact_refs"]) == 1
    assert messages[1]["artifact_refs"][0]["image_asset"] == "sediment://abc#file_001#p.jpg"


def test_extract_messages_keeps_tool_widget_messages():
    detail = {
        "mapping": {
            "n1": {
                "message": {
                    "id": "msg_1",
                    "author": {"role": "user"},
                    "content": {"parts": ["Run deep research"]},
                    "create_time": 100,
                },
            },
            "n2": {
                "message": {
                    "id": "msg_2",
                    "author": {"role": "assistant"},
                    "content": {"parts": [
                        {"path": "/Deep Research App/start"},
                    ]},
                    "create_time": 200,
                },
            },
            "n3": {
                "message": {
                    "id": "msg_3",
                    "author": {"role": "tool"},
                    "content": {"parts": ["Rendered a widget"]},
                    "create_time": 150,
                },
            },
        }
    }
    messages = ChatGPTHTTPAPI.extract_messages_from_mapping(detail)
    roles = [m["role"] for m in messages]
    assert "tool" in roles
    tool_msg = [m for m in messages if m["role"] == "tool"][0]
    assert tool_msg["content"] == "Rendered a widget"


def test_extract_artifacts_finds_deep_research():
    detail = {
        "mapping": {
            "n1": {
                "message": {
                    "id": "msg_1",
                    "author": {"role": "assistant"},
                    "content": {"parts": [
                        {"path": "/Deep Research App/implicit_link::connector_openai_deep_research/start",
                         "args": {"prompt_id": "dr-abc"}},
                    ]},
                    "create_time": 100,
                },
            },
        }
    }
    artifacts = ChatGPTHTTPAPI.extract_artifacts_from_mapping(detail)
    assert len(artifacts) == 1
    assert artifacts[0]["artifact_type"] == "deep_research_report"
    assert artifacts[0]["provider_artifact_id"] == "dr-abc"


def test_extract_artifacts_finds_file_references():
    detail = {
        "mapping": {
            "n1": {
                "message": {
                    "id": "msg_1",
                    "author": {"role": "tool"},
                    "content": {"parts": [
                        {"file_id": "file-UeaKpAqtNTsDhQ3kLtvVLC", "filename": "report.pdf"},
                    ]},
                    "create_time": 100,
                },
            },
        }
    }
    artifacts = ChatGPTHTTPAPI.extract_artifacts_from_mapping(detail)
    assert len(artifacts) == 1
    assert artifacts[0]["artifact_type"] == "generated_file"
    assert artifacts[0]["provider_artifact_id"] == "file-UeaKpAqtNTsDhQ3kLtvVLC"
    assert artifacts[0]["label"] == "report.pdf"


def test_extract_artifacts_finds_canvas():
    detail = {
        "mapping": {
            "n1": {
                "message": {
                    "id": "msg_1",
                    "author": {"role": "assistant"},
                    "content": {"parts": [
                        {"path": "/canvas_tool/edit", "canvas_id": "cv-123", "title": "my-script.py"},
                    ]},
                    "create_time": 100,
                },
            },
        }
    }
    artifacts = ChatGPTHTTPAPI.extract_artifacts_from_mapping(detail)
    assert len(artifacts) == 1
    assert artifacts[0]["artifact_type"] == "canvas_document"
    assert artifacts[0]["label"] == "my-script.py"


def test_extract_artifacts_finds_images():
    detail = {
        "mapping": {
            "n1": {
                "message": {
                    "id": "msg_1",
                    "author": {"role": "tool"},
                    "content": {"parts": [
                        {"content_type": "image_asset_pointer",
                         "asset_pointer": "sediment://f9a7018f14eff32#file_001#p_0.jpg",
                         "size_bytes": 75516, "width": 768, "height": 1024,
                         "fovea": 768, "metadata": {"dalle": {"prompt": "a cat"}}},
                    ]},
                    "create_time": 100,
                },
            },
        }
    }
    artifacts = ChatGPTHTTPAPI.extract_artifacts_from_mapping(detail)
    assert len(artifacts) == 1
    assert artifacts[0]["artifact_type"] == "generated_image"
    assert artifacts[0]["provider_artifact_id"].startswith("sediment://")
    assert artifacts[0]["size_bytes"] == 75516


def test_extract_artifacts_finds_agent_screenshot():
    detail = {
        "mapping": {
            "n1": {
                "message": {
                    "id": "msg_1",
                    "author": {"role": "tool"},
                    "content": {
                        "content_type": "computer_output",
                        "screenshot": "base64data...",
                        "computer_id": "comp-1",
                        "tether_id": "tether-abc",
                    },
                    "create_time": 100,
                },
            },
        }
    }
    artifacts = ChatGPTHTTPAPI.extract_artifacts_from_mapping(detail)
    assert len(artifacts) == 1
    assert artifacts[0]["artifact_type"] == "agent_screenshot"
    assert artifacts[0]["provider_artifact_id"] == "tether-abc"


def test_extract_artifacts_finds_code_execution():
    detail = {
        "mapping": {
            "n1": {
                "message": {
                    "id": "msg_1",
                    "author": {"role": "assistant"},
                    "content": {
                        "content_type": "code",
                        "language": "python",
                        "text": "import pandas as pd\ndf = pd.read_csv('data.csv')\nprint(df.head())",
                    },
                    "create_time": 100,
                },
            },
        }
    }
    artifacts = ChatGPTHTTPAPI.extract_artifacts_from_mapping(detail)
    assert len(artifacts) == 1
    assert artifacts[0]["artifact_type"] == "code_execution"
    assert artifacts[0]["label"] == "Code (python)"


def test_extract_messages_skips_empty():
    detail = {
        "mapping": {
            "n1": {
                "message": {
                    "author": {"role": "user"},
                    "content": {"parts": [""]},
                    "create_time": 100,
                },
            },
            "n2": {
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"parts": ["real content"]},
                    "create_time": 200,
                },
            },
        }
    }
    messages = ChatGPTHTTPAPI.extract_messages_from_mapping(detail)
    assert len(messages) == 1
    assert messages[0]["content"] == "real content"


# --- cookie extraction: AES key derivation ---

def test_derive_aes_key_deterministic():
    from lib.cookie_extract import derive_aes_key
    k1 = derive_aes_key("test_password")
    k2 = derive_aes_key("test_password")
    assert k1 == k2
    assert len(k1) == 16


def test_derive_aes_key_differs_for_different_password():
    from lib.cookie_extract import derive_aes_key
    k1 = derive_aes_key("password1")
    k2 = derive_aes_key("password2")
    assert k1 != k2


def test_decrypt_cookie_value_round_trip():
    from lib.cookie_extract import derive_aes_key, decrypt_cookie_value, V10_PREFIX_LEN, HEADER_LEN, IV_LEN
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding

    aes_key = derive_aes_key("test_key")
    plaintext = "test_cookie_value_123"

    # Encrypt with the known format: v10 + 16-byte header + 16-byte IV + ciphertext
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext.encode("utf-8")) + padder.finalize()

    iv = b"\x00" * 16  # test IV
    header = b"\x01" * 16  # test header
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()

    encrypted = b"v10" + header + iv + ciphertext

    result = decrypt_cookie_value(encrypted, aes_key)
    assert result == plaintext


def test_decrypt_cookie_value_returns_none_for_non_v10():
    from lib.cookie_extract import decrypt_cookie_value
    assert decrypt_cookie_value(b"v20xxx", b"key") is None
    assert decrypt_cookie_value(b"", b"key") is None
    assert decrypt_cookie_value(None, b"key") is None
