import sys
from io import StringIO
from unittest.mock import patch
import run


def test_c_flag_executes_code():
    stdout = StringIO()
    with patch.object(sys, "argv", ["browser-harness", "-c", "print('hello from -c')"]), \
         patch("run.ensure_daemon"), \
         patch("sys.stdout", stdout):
        run.main()
    assert stdout.getvalue().strip() == "hello from -c"


def test_c_flag_does_not_read_stdin():
    stdin_read = []
    fake_stdin = StringIO("should not be read")
    fake_stdin.read = lambda: stdin_read.append(True) or ""

    with patch.object(sys, "argv", ["browser-harness", "-c", "x = 1"]), \
         patch("run.ensure_daemon"), \
         patch("sys.stdin", fake_stdin):
        run.main()

    assert not stdin_read, "stdin should not be read when -c is passed"


def test_stdin_executes_code():
    stdout = StringIO()
    with patch.object(sys, "argv", ["browser-harness"]), \
         patch("run.ensure_daemon"), \
         patch("sys.stdin", StringIO("print('hello from stdin')")), \
         patch("sys.stdout", stdout):
        run.main()
    assert stdout.getvalue().strip() == "hello from stdin"


def test_empty_stdin_does_not_start_daemon():
    with patch.object(sys, "argv", ["browser-harness"]), \
         patch("run.ensure_daemon") as ensure_daemon, \
         patch("sys.stdin", StringIO("")):
        try:
            run.main()
        except SystemExit as e:
            assert "Usage:" in str(e)
        else:
            raise AssertionError("expected SystemExit")
    ensure_daemon.assert_not_called()


def test_doctor_rejects_unknown_flags():
    with patch.object(sys, "argv", ["browser-harness", "--doctor", "--bogus"]):
        try:
            run.main()
        except SystemExit as e:
            assert e.code == 2
        else:
            raise AssertionError("expected SystemExit")


def test_setup_accepts_remote_debugging_dialog_flag():
    with patch.object(sys, "argv", ["browser-harness", "--setup", "--accept-remote-debugging-dialog"]), \
         patch("run.run_setup", return_value=0) as setup:
        try:
            run.main()
        except SystemExit as e:
            assert e.code == 0
        else:
            raise AssertionError("expected SystemExit")

    setup.assert_called_once_with(accept_remote_debugging_dialog=True)


def test_launch_profile_passes_options():
    with patch.object(sys, "argv", [
        "browser-harness",
        "--launch-profile",
        "/tmp/profile",
        "--port",
        "9333",
        "--url",
        "https://example.com",
        "--chrome",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "--json",
    ]), patch("run.run_launch_profile", return_value=0) as launch:
        try:
            run.main()
        except SystemExit as e:
            assert e.code == 0
        else:
            raise AssertionError("expected SystemExit")

    launch.assert_called_once_with(
        "/tmp/profile",
        port=9333,
        url="https://example.com",
        chrome_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        json_output=True,
    )


def test_skill_learning_gate_subcommand_does_not_start_daemon():
    with patch.object(sys, "argv", ["browser-harness", "--skill-learning-gate", "candidate.json"]), \
         patch("run.ensure_daemon") as ensure_daemon, \
         patch("skill_learning_gate.main", return_value=None) as gate:
        run.main()

    gate.assert_called_once_with(["candidate.json"])
    ensure_daemon.assert_not_called()


def test_skill_learning_gate_subcommand_loads_sibling_runner_when_module_missing(tmp_path):
    fallback = tmp_path / "skill_learning_gate.py"
    fallback.write_text(
        "def main(argv=None):\n"
        "    print('fallback:' + ','.join(argv or []))\n",
        encoding="utf-8",
    )
    stdout = StringIO()

    with patch.object(sys, "argv", ["browser-harness", "--skill-learning-gate", "candidate.json"]), \
         patch("run.ensure_daemon") as ensure_daemon, \
         patch.object(run, "__file__", str(tmp_path / "run.py")), \
         patch.dict(sys.modules, {"skill_learning_gate": None}), \
         patch("sys.stdout", stdout):
        run.main()

    assert stdout.getvalue().strip() == "fallback:candidate.json"
    ensure_daemon.assert_not_called()
