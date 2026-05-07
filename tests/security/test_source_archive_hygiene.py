import zipfile
import importlib.util
from pathlib import Path


def _load_checker():
    path = Path(__file__).resolve().parents[2] / "scripts" / "check_source_archive.py"
    spec = importlib.util.spec_from_file_location("check_source_archive", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


check_source_archive = _load_checker()


def test_source_archive_hygiene_fails_private_path(tmp_path):
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("browser-harness/domain-skills/x/.private-data/token.json", '{"token":"secret"}')

    violations = check_source_archive.archive_violations(archive)

    assert violations
    assert ".private-data" in violations[0]


def test_source_archive_hygiene_fails_cookie_content(tmp_path):
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("browser-harness/domain-skills/x/fixture.json", '{"Cookie":"sid=secret"}')

    violations = check_source_archive.archive_violations(archive)

    assert violations
    assert "auth-like content" in violations[0]


def test_source_archive_hygiene_allows_redaction_field_names(tmp_path):
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(
            "browser-harness/domain-skills/youtube/surface-map.json",
            '{"redact_fields":["Authorization","Cookie"]}',
        )

    assert check_source_archive.archive_violations(archive) == []
