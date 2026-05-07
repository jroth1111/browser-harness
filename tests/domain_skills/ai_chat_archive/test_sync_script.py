import importlib.util
from pathlib import Path
from types import SimpleNamespace


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "domain-skills"
    / "ai-chat-archive"
    / "scripts"
    / "sync.py"
)


def load_sync_script():
    spec = importlib.util.spec_from_file_location("ai_chat_archive_sync_script", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_sync_account_filter_tolerates_scalar_account_labels(tmp_path, monkeypatch, capsys):
    module = load_sync_script()
    synced = []

    monkeypatch.setattr(module.schema, "init_db", lambda path: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(module.archive_db, "connect", lambda path: object())
    monkeypatch.setattr(module, "list_provider_ids", lambda: ["chatgpt"])
    monkeypatch.setattr(
        module.archive_db,
        "list_cookie_jars",
        lambda db, provider_id, only_active: [
            {
                "provider_id": provider_id,
                "jar_id": "jar-1",
                "account_label": 12345,
                "source_browser": "chrome",
                "source_profile": "Default",
            },
        ],
    )

    def fake_sync_one_jar(db, jar, *, fresh, limit, options):
        synced.append(jar)
        return SimpleNamespace(
            listed=1,
            captured=1,
            skipped_unchanged=0,
            failed=0,
            as_dict=lambda: {"provider_id": jar["provider_id"], "captured": 1},
        )

    monkeypatch.setattr(module, "sync_one_jar", fake_sync_one_jar)

    assert module.main(["--db", str(tmp_path / "archive.sqlite3"), "--account", "123"]) == 0
    assert synced[0]["account_label"] == 12345
    assert "sync complete: 1 captures across 1 jar(s)" in capsys.readouterr().out
