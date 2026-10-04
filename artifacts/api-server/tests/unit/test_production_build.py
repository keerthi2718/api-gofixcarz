"""Isolated publishing tests: fake pip only, no network or database access."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import Mock, patch


API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = API_ROOT.parents[1]
SCRIPT = API_ROOT / "scripts" / "production_build.py"
spec = importlib.util.spec_from_file_location("production_build", SCRIPT)
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)

FAKE_PIP = """
import json
import os
from pathlib import Path
import sys
Path(os.environ["MOCK_MARKER"]).write_text(json.dumps({
    "args": sys.argv[1:], "cwd": os.getcwd(), "python": sys.executable,
}))
print("https://dummy:dummy-secret@index.invalid/simple?token=dummy-token")
print(os.environ.get("MOCK_ERROR", ""), file=sys.stderr)
sys.exit(int(os.environ["MOCK_EXIT"]))
"""


class ProductionBuildTests(unittest.TestCase):
    def invoke(self, returncode=0, output=""):
        def fake_run(*args, **kwargs):
            kwargs["stdout"].write(output)
            return subprocess.CompletedProcess(args[0], returncode)

        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(build.subprocess, "run", side_effect=fake_run) as runner,
            patch.object(build.shutil, "which", return_value="/fake/bin/pip"),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = build.main()
        return code, stdout.getvalue(), stderr.getvalue(), runner

    def test_success_installs_exact_requirements_with_same_python(self):
        code, stdout, stderr, runner = self.invoke(output="dummy-secret")
        self.assertEqual(code, 0)
        self.assertIn("installed successfully", stdout)
        self.assertEqual(stderr, "")
        command = runner.call_args.args[0]
        self.assertEqual(command[:4], ["/fake/bin/pip", "--python", sys.executable, "install"])
        self.assertEqual(command[-2:], ["-r", str(API_ROOT / "requirements.txt")])
        self.assertIn("--no-input", command)
        self.assertEqual(runner.call_args.kwargs["cwd"], API_ROOT)
        self.assertEqual(runner.call_args.kwargs["stderr"], subprocess.STDOUT)
        self.assertTrue(runner.call_args.kwargs["stdout"].closed)
        self.assertNotIn("dummy-secret", stdout)

    def test_pip_failure_preserves_exit_code_and_redacts_raw_output(self):
        code, stdout, stderr, _ = self.invoke(
            7, "ERROR: No matching distribution for dummy-secret\n"
            "https://dummy:dummy-secret@index.invalid/?token=dummy-token\n"
        )
        self.assertEqual(code, 7)
        self.assertIn("exit code 7", stderr)
        self.assertIn("requirements.txt pins", stderr)
        self.assertNotIn("installed successfully", stdout)
        for sensitive in ("dummy-secret", "dummy-token", "https://", "index.invalid"):
            self.assertNotIn(sensitive, stdout + stderr)

    def test_unknown_failure_has_actionable_safe_message(self):
        code, _, stderr, _ = self.invoke(1, "unrecognized dummy-secret")
        self.assertEqual(code, 1)
        self.assertIn("package-index settings", stderr)
        self.assertNotIn("dummy-secret", stderr)

    def test_known_failure_categories(self):
        for raw, expected in (
            ("No module named pip", "Restore pip"),
            ("ResolutionImpossible", "conflicting dependency versions"),
            ("CERTIFICATE_VERIFY_FAILED", "do not disable verification"),
            ("Connection timed out", "network availability"),
            ("401 Unauthorized", "credentials in Publishing settings"),
            ("Failed building wheel", "system libraries"),
            ("No space left on device", "build storage"),
        ):
            with self.subTest(raw=raw):
                code, _, stderr, _ = self.invoke(1, raw)
                self.assertEqual(code, 1)
                self.assertIn(expected, stderr)

    def test_signal_termination_fails_build(self):
        code, _, stderr, _ = self.invoke(-15)
        self.assertEqual(code, 1)
        self.assertIn("exit code -15", stderr)

    def test_missing_standalone_pip_fails_without_starting_install(self):
        stderr = io.StringIO()
        with (
            patch.object(build.shutil, "which", return_value=None),
            patch.object(build.subprocess, "run") as runner,
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(build.main(), 1)
        runner.assert_not_called()
        self.assertIn("Publishing pip command is unavailable", stderr.getvalue())

    def test_unreadable_requirements_does_not_launch_pip(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(build, "REQUIREMENTS", Mock(open=Mock(side_effect=PermissionError("dummy-secret")))),
            patch.object(build.subprocess, "run") as runner,
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(build.main(), 1)
        runner.assert_not_called()
        self.assertIn("requirements.txt readability", stderr.getvalue())
        self.assertNotIn("dummy-secret", stderr.getvalue())

    def test_installer_launch_error_is_redacted(self):
        stderr = io.StringIO()
        with (
            patch.object(build.subprocess, "run", side_effect=OSError("dummy-secret")),
            patch.object(build.shutil, "which", return_value="/fake/bin/pip"),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(build.main(), 1)
        self.assertIn("build stopped", stderr.getvalue())
        self.assertNotIn("dummy-secret", stderr.getvalue())

    def test_configuration_has_one_canonical_install_and_unchanged_startup(self):
        root = tomllib.loads((REPO_ROOT / ".replit").read_text())
        artifact = tomllib.loads((API_ROOT / ".replit-artifact" / "artifact.toml").read_text())
        self.assertNotIn("build", root["deployment"])
        service = artifact["services"][0]
        self.assertEqual(
            service["production"]["build"]["args"],
            ["python", "artifacts/api-server/scripts/production_build.py"],
        )
        self.assertEqual(
            service["production"]["run"]["args"],
            ["sh", "-c", "cd /home/runner/workspace/artifacts/api-server && python scripts/production_start.py"],
        )
        self.assertEqual(service["production"]["health"]["startup"]["path"], "/api/healthz")
        self.assertNotIn("env", service["production"])

    def test_configured_build_command_success_and_failure_without_real_pip(self):
        artifact = tomllib.loads((API_ROOT / ".replit-artifact" / "artifact.toml").read_text())
        command = artifact["services"][0]["production"]["build"]["args"].copy()
        command[0] = sys.executable
        with tempfile.TemporaryDirectory() as directory:
            fake_root = Path(directory)
            fake_pip = fake_root / "pip"
            fake_pip.write_text(f"#!{sys.executable}\n" + FAKE_PIP)
            fake_pip.chmod(0o700)
            marker = fake_root / "called.json"
            for exitcode in (0, 9):
                with self.subTest(exitcode=exitcode):
                    result = subprocess.run(
                        command,
                        cwd=REPO_ROOT,
                        # Deliberately exclude app secrets and real index settings.
                        env={
                            "PATH": directory,
                            "MOCK_MARKER": str(marker),
                            "MOCK_EXIT": str(exitcode),
                            "MOCK_ERROR": "ERROR: No matching distribution found for dummy-secret",
                        },
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    self.assertEqual(result.returncode, exitcode)
                    invocation = json.loads(marker.read_text())
                    self.assertEqual(invocation["args"][-2:], ["-r", str(API_ROOT / "requirements.txt")])
                    self.assertEqual(invocation["args"][:3], ["--python", sys.executable, "install"])
                    self.assertEqual(invocation["cwd"], str(API_ROOT))
                    self.assertEqual(invocation["python"], sys.executable)
                    if exitcode:
                        self.assertIn("build stopped", result.stderr)
                        self.assertNotIn("installed successfully", result.stdout)
                    else:
                        self.assertIn("installed successfully", result.stdout)
                    for sensitive in ("dummy-secret", "dummy-token", "https://", "index.invalid"):
                        self.assertNotIn(sensitive, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()