from pathlib import Path

from redaction_scan import scan_paths, scan_text


def test_redaction_scan_allows_redacted_session_manifest_shape():
    text = """
{
  "site": "example",
  "cookie_names": ["sid"],
  "cookie_domains": [".example.com"],
  "local_storage_keys": ["state"],
  "capability_receipt_refs": ["receipt.json"]
}
"""

    assert scan_text(text) == []


def test_redaction_scan_flags_common_session_secret_shapes():
    text = """
Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789
Cookie: sid=secret-session-value; other=x
{"access_token": "abcdefghijklmnopqrstuvwxyz"}
"""

    kinds = {finding["kind"] for finding in scan_text(text)}
    assert {"bearer_token", "cookie_header", "storage_token_value"} <= kinds
    assert all("abcdefghijklmnopqrstuvwxyz" not in finding["excerpt"] for finding in scan_text(text))


def test_redaction_scan_paths_skip_private_dirs_and_flag_public_files(tmp_path):
    private = tmp_path / ".private-data"
    private.mkdir()
    (private / "raw.json").write_text("Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789")
    public = tmp_path / "receipt.json"
    public.write_text("Set-Cookie: sid=secret-session-value")

    result = scan_paths([tmp_path])

    assert result["ok"] is False
    assert {Path(finding["path"]).name for finding in result["findings"]} == {"receipt.json"}
    assert {finding["kind"] for finding in result["findings"]} >= {"set_cookie_header"}
