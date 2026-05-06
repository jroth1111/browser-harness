import browser_harness.admin as admin
import signal
import sys
from io import StringIO
from pathlib import Path
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


def test_macos_remote_debugging_keyboard_script():
    script = admin._remote_debugging_keyboard_applescript(wait=1.5, app_name="Google Chrome")

    assert script[0] == 'tell application "Google Chrome" to activate'
    assert "delay 1.50" in script
    assert "keystroke tab" in script
    assert "keystroke space" in script
    assert "keystroke return" in script


def test_accept_remote_debugging_dialog_keyboard_runs_osascript_on_macos():
    with patch("platform.system", return_value="Darwin"), \
         patch("subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        result = admin._accept_remote_debugging_dialog_keyboard(wait=0.25)

    assert result["ok"] is True
    args = run.call_args.args[0]
    assert args[0] == "osascript"
    assert "keystroke space" in args


def test_accept_remote_debugging_dialog_keyboard_rejects_non_macos():
    with patch("platform.system", return_value="Linux"):
        result = admin._accept_remote_debugging_dialog_keyboard()

    assert result["ok"] is False
    assert "macOS" in result["reason"]


def test_launch_headful_profile_builds_loopback_chrome_command(tmp_path):
    chrome = tmp_path / "Chrome"
    chrome.write_text("")
    profile = tmp_path / "profile"

    with patch("subprocess.Popen") as popen:
        popen.return_value.pid = 1234
        result = admin.launch_headful_profile(
            profile,
            port=9333,
            url="https://example.com",
            chrome_path=str(chrome),
        )

    cmd = popen.call_args.args[0]
    assert cmd[0] == str(chrome)
    assert f"--user-data-dir={profile}" in cmd
    assert "--remote-debugging-address=127.0.0.1" in cmd
    assert "--remote-debugging-port=9333" in cmd
    assert cmd[-1] == "https://example.com"
    assert result["pid"] == 1234
    assert result["http_endpoint"] == "http://127.0.0.1:9333"
    assert Path(result["profile_path"]).exists()


def test_ensure_daemon_spawns_with_current_python_interpreter():
    class Proc:
        def poll(self):
            return None

    with patch("browser_harness.admin.daemon_alive", side_effect=[False, True]), \
         patch("subprocess.Popen", return_value=Proc()) as popen:
        admin.ensure_daemon(wait=0.1)

    cmd = popen.call_args.args[0]
    assert cmd[0] == sys.executable
    assert cmd[1].endswith("daemon.py")


def test_restart_daemon_does_not_sigterm_unrelated_stale_pid(tmp_path):
    pid_path = tmp_path / "bh.pid"
    pid_path.write_text("4321")
    calls = []

    class RefusingSocket:
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False
        def settimeout(self, timeout):
            pass
        def connect(self, path):
            raise FileNotFoundError(path)

    def fake_kill(pid, sig):
        calls.append((pid, sig))

    with patch("browser_harness.admin._paths", return_value=(str(tmp_path / "bh.sock"), str(pid_path))), \
         patch("browser_harness.admin._legacy_paths", return_value=()), \
         patch("socket.socket", return_value=RefusingSocket()), \
         patch("browser_harness.admin._pid_matches_daemon", return_value=False), \
         patch("time.sleep"), \
         patch("os.kill", side_effect=fake_kill):
        admin.restart_daemon()

    assert (4321, signal.SIGTERM) not in calls
    assert all(call == (4321, 0) for call in calls)


def test_restart_daemon_sigterms_matching_daemon_pid(tmp_path):
    pid_path = tmp_path / "bh.pid"
    pid_path.write_text("4321")
    calls = []

    class RefusingSocket:
        def __enter__(self):
            return self
        def __exit__(self, *exc):
            return False
        def settimeout(self, timeout):
            pass
        def connect(self, path):
            raise FileNotFoundError(path)

    def fake_kill(pid, sig):
        calls.append((pid, sig))

    with patch("browser_harness.admin._paths", return_value=(str(tmp_path / "bh.sock"), str(pid_path))), \
         patch("browser_harness.admin._legacy_paths", return_value=()), \
         patch("socket.socket", return_value=RefusingSocket()), \
         patch("browser_harness.admin._pid_matches_daemon", return_value=True), \
         patch("time.sleep"), \
         patch("os.kill", side_effect=fake_kill):
        admin.restart_daemon()

    assert (4321, signal.SIGTERM) in calls


def test_pid_matches_daemon_requires_this_repo_daemon():
    root = Path(admin.__file__).resolve().parent
    with patch("subprocess.check_output", return_value=f"{sys.executable} {root / 'daemon.py'}"):
        assert admin._pid_matches_daemon(4321)
    with patch("subprocess.check_output", return_value="/usr/bin/python /tmp/other/daemon.py"):
        assert not admin._pid_matches_daemon(4321)


def test_doctor_default_does_not_check_latest_release():
    stdout = StringIO()
    with patch("browser_harness.admin._latest_release_tag", side_effect=AssertionError("network release check")), \
         patch("urllib.request.urlopen", side_effect=AssertionError("unexpected network")), \
         patch("browser_harness.admin._chrome_running", return_value=False), \
         patch("browser_harness.admin.daemon_alive", return_value=False), \
         patch("sys.stdout", stdout):
        assert admin.run_doctor() == 1
    assert "latest release" not in stdout.getvalue()


def test_doctor_json_shape():
    stdout = StringIO()
    with patch("browser_harness.admin._chrome_running", return_value=False), \
         patch("browser_harness.admin.daemon_alive", return_value=False), \
         patch("sys.stdout", stdout):
        assert admin.run_doctor(json_output=True) == 1
    assert '"status": "fail"' in stdout.getvalue()
    assert '"id": "daemon.alive"' in stdout.getvalue()


def test_doctor_reports_endpoint_metadata():
    class Stat:
        st_mode = 0o100600

    endpoint = {
        "source": "env",
        "resolved_url": "ws://127.0.0.1:9222/devtools/browser/abc",
        "host": "127.0.0.1",
        "is_loopback": True,
        "remote_allowed": False,
        "browser": "Chrome/123",
        "protocol_version": "1.3",
    }

    stdout = StringIO()
    with patch("browser_harness.admin._chrome_running", return_value=True), \
         patch("browser_harness.admin.daemon_alive", return_value=True), \
         patch("browser_harness.admin._daemon_meta", return_value={"endpoint_info": endpoint}), \
         patch("pathlib.Path.stat", return_value=Stat()), \
         patch("sys.stdout", stdout):
        assert admin.run_doctor() == 0
    output = stdout.getvalue()
    assert "endpoint.present" in output
    assert "ws://127.0.0.1:9222/devtools/browser/abc" in output
    assert "endpoint.version - Chrome/123 1.3" in output


def test_doctor_network_check_only_appears_when_requested():
    stdout = StringIO()
    with patch("browser_harness.admin._chrome_running", return_value=False), \
         patch("browser_harness.admin.daemon_alive", return_value=False), \
         patch("sys.stdout", stdout):
        admin.run_doctor(json_output=True)
    assert "network.external" not in stdout.getvalue()

    stdout = StringIO()
    with patch("browser_harness.admin._chrome_running", return_value=False), \
         patch("browser_harness.admin.daemon_alive", return_value=False), \
         patch("sys.stdout", stdout):
        admin.run_doctor(json_output=True, network=True)
    assert "network.external" in stdout.getvalue()


def test_doctor_remote_endpoint_with_allowance_warns_not_fails():
    class Stat:
        st_mode = 0o100600

    endpoint = {
        "source": "env",
        "resolved_url": "ws://10.0.0.10:9222/devtools/browser/abc",
        "host": "10.0.0.10",
        "is_loopback": False,
        "remote_allowed": True,
        "browser": "Chrome/123",
        "protocol_version": "1.3",
    }

    stdout = StringIO()
    with patch("browser_harness.admin._chrome_running", return_value=True), \
         patch("browser_harness.admin.daemon_alive", return_value=True), \
         patch("browser_harness.admin._daemon_meta", return_value={"endpoint_info": endpoint}), \
         patch("pathlib.Path.stat", return_value=Stat()), \
         patch("sys.stdout", stdout):
        assert admin.run_doctor(json_output=True) == 0
    output = stdout.getvalue()
    assert '"status": "warn"' in output
    assert '"id": "endpoint.remote_allowed"' in output


def test_doctor_reports_endpoint_metadata_warnings():
    class Stat:
        st_mode = 0o100600

    endpoint = {
        "source": "env",
        "resolved_url": "wss://127.0.0.1:9222/devtools/browser/abc",
        "host": "127.0.0.1",
        "is_loopback": True,
        "remote_allowed": False,
        "warnings": ["wss on loopback is unusual; ws/http to 127.0.0.1 is the normal local shape"],
        "browser": "Chrome/123",
        "protocol_version": "1.3",
    }

    stdout = StringIO()
    with patch("browser_harness.admin._chrome_running", return_value=True), \
         patch("browser_harness.admin.daemon_alive", return_value=True), \
         patch("browser_harness.admin._daemon_meta", return_value={"endpoint_info": endpoint}), \
         patch("pathlib.Path.stat", return_value=Stat()), \
         patch("sys.stdout", stdout):
        assert admin.run_doctor(json_output=True) == 0
    output = stdout.getvalue()
    assert '"status": "warn"' in output
    assert '"id": "endpoint.warning"' in output
    assert "wss on loopback is unusual" in output


def test_doctor_does_not_duplicate_remote_allowed_warning():
    class Stat:
        st_mode = 0o100600

    endpoint = {
        "source": "env",
        "resolved_url": "ws://10.0.0.10:9222/devtools/browser/abc",
        "host": "10.0.0.10",
        "is_loopback": False,
        "remote_allowed": True,
        "warnings": ["remote CDP endpoint allowed by BH_CDP_ALLOW_REMOTE=1"],
        "browser": "Chrome/123",
        "protocol_version": "1.3",
    }

    stdout = StringIO()
    with patch("browser_harness.admin._chrome_running", return_value=True), \
         patch("browser_harness.admin.daemon_alive", return_value=True), \
         patch("browser_harness.admin._daemon_meta", return_value={"endpoint_info": endpoint}), \
         patch("pathlib.Path.stat", return_value=Stat()), \
         patch("sys.stdout", stdout):
        assert admin.run_doctor(json_output=True) == 0
    output = stdout.getvalue()
    assert output.count("endpoint.remote_allowed") == 1
    assert "endpoint.warning" not in output


def test_doctor_remote_endpoint_without_allowance_fails():
    class Stat:
        st_mode = 0o100600

    endpoint = {
        "source": "env",
        "resolved_url": "ws://10.0.0.10:9222/devtools/browser/abc",
        "host": "10.0.0.10",
        "is_loopback": False,
        "remote_allowed": False,
        "browser": "Chrome/123",
        "protocol_version": "1.3",
    }

    stdout = StringIO()
    with patch("browser_harness.admin._chrome_running", return_value=True), \
         patch("browser_harness.admin.daemon_alive", return_value=True), \
         patch("browser_harness.admin._daemon_meta", return_value={"endpoint_info": endpoint}), \
         patch("pathlib.Path.stat", return_value=Stat()), \
         patch("sys.stdout", stdout):
        assert admin.run_doctor(json_output=True) == 1
    output = stdout.getvalue()
    assert '"status": "fail"' in output
    assert '"id": "endpoint.loopback"' in output
