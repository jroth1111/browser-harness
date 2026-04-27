import admin
from io import StringIO
from unittest.mock import patch


def test_handshake_timeout_needs_chrome_remote_debugging_prompt():
    msg = "CDP WS handshake failed: timed out during opening handshake"

    assert admin._needs_chrome_remote_debugging_prompt(msg)


def test_handshake_403_needs_chrome_remote_debugging_prompt():
    msg = "CDP WS handshake failed: server rejected WebSocket connection: HTTP 403"

    assert admin._needs_chrome_remote_debugging_prompt(msg)


def test_stale_websocket_does_not_open_chrome_inspect():
    msg = "no close frame received or sent"

    assert not admin._needs_chrome_remote_debugging_prompt(msg)


def test_local_chrome_mode_uses_bh_cdp_ws_env():
    with patch.dict("os.environ", {"BH_CDP_WS": "ws://127.0.0.1:9222/devtools/browser/x"}, clear=False):
        assert not admin._is_local_chrome_mode()
    assert not admin._is_local_chrome_mode({"BH_CDP_WS": "ws://127.0.0.1:9222/devtools/browser/x"})


def test_profile_use_missing_message_is_local_only():
    with patch("shutil.which", return_value=None):
        try:
            admin.list_local_profiles()
        except RuntimeError as e:
            msg = str(e)
        else:
            raise AssertionError("expected RuntimeError")
    assert "browser-use.com/profile" not in msg
    assert "browser-harness --setup" in msg


def test_doctor_default_does_not_check_latest_release():
    stdout = StringIO()
    with patch("admin._latest_release_tag", side_effect=AssertionError("network release check")), \
         patch("admin._chrome_running", return_value=False), \
         patch("admin.daemon_alive", return_value=False), \
         patch("sys.stdout", stdout):
        assert admin.run_doctor() == 1
    assert "latest release" not in stdout.getvalue()


def test_doctor_json_shape():
    stdout = StringIO()
    with patch("admin._chrome_running", return_value=False), \
         patch("admin.daemon_alive", return_value=False), \
         patch("sys.stdout", stdout):
        assert admin.run_doctor(json_output=True) == 1
    assert '"status": "fail"' in stdout.getvalue()
    assert '"id": "daemon.alive"' in stdout.getvalue()
