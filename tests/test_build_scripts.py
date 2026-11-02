import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
POWERSHELL = shutil.which("powershell.exe")
APPS = ("Audio Receiver", "Audio Streamer")
FAKE_PYINSTALLER = """
from pathlib import Path
import sys

if "--version" in sys.argv:
    print("test builder")
    sys.exit(0)
app = Path(sys.argv[-1]).stem
with Path("build_calls.txt").open("a") as calls:
    calls.write(app + "\\n")
mode = Path("build_mode.txt").read_text()
if mode == "fail " + app:
    sys.exit(7)
output = Path("dist") / app
output.mkdir(parents=True, exist_ok=True)
if mode != "missing exe " + app:
    (output / (app + ".exe")).write_text("new executable")
if mode != "missing internal " + app:
    (output / "_internal").mkdir()
    (output / "_internal" / "runtime.txt").write_text("new runtime")
"""
FAKE_APP = """
import json
from pathlib import Path
import sys

Path("app_args.json").write_text(json.dumps(sys.argv[1:]))
sys.exit(9 if "fail" in sys.argv else 0)
"""


def quote_ps(value):
    return "'" + str(value).replace("'", "''") + "'"


@unittest.skipUnless(os.name == "nt" and POWERSHELL, "Requires Windows PowerShell")
class BuildScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = tempfile.TemporaryDirectory(prefix="audio-test-python-")
        cls.addClassCleanup(cls.environment.cleanup)
        cls.venv = Path(cls.environment.name) / "venv"
        subprocess.run(
            [sys.executable, "-m", "venv", "--without-pip", str(cls.venv)],
            check=True, capture_output=True, text=True, timeout=60,
        )

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="audio-build-tests-")
        self.addCleanup(temporary.cleanup)
        self.parent = Path(temporary.name)
        self.repo = self.parent / "project [portable] with spaces"
        self.repo.mkdir()
        for script in ROOT.glob("*.ps1"):
            shutil.copy2(script, self.repo / script.name)
        self.python_directory = self.parent / ".venv311"
        shutil.copytree(self.venv, self.python_directory)
        self.python = self.python_directory / "Scripts" / "python.exe"
        (self.repo / "PyInstaller.py").write_text(FAKE_PYINSTALLER)
        (self.repo / "build_mode.txt").write_text("success")
        for app in APPS:
            (self.repo / f"{app}.spec").write_text("# test specification")
            (self.repo / f"{app}.py").write_text(FAKE_APP)
            for output in ("build", "dist"):
                directory = self.repo / output / app
                (directory / "_internal").mkdir(parents=True)
                (directory / "_internal" / "old.txt").write_text("old runtime")
                (directory / f"{app}.exe").write_text("old executable")
            (self.repo / "build" / app / "cache.txt").write_text("cached build")

    def run_ps(self, command, **environment):
        return subprocess.run(
            [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-Command", "$ErrorActionPreference = 'Stop'; " + command],
            cwd=self.parent, capture_output=True, text=True, timeout=60,
            env={**os.environ, **environment},
        )

    def script(self, name):
        return "& " + quote_ps(self.repo / name)

    def build(self, arguments=""):
        return self.run_ps(self.script("rebuild_audio_streamer.ps1") + " " + arguments)

    def calls(self):
        path = self.repo / "build_calls.txt"
        return path.read_text().splitlines() if path.exists() else []

    def assert_failed(self, result, message):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(message, result.stdout + result.stderr)
        self.assertNotIn("Build complete.", result.stdout)

    def test_successful_build_mirrors_both_apps_and_preserves_cache(self):
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.calls(), list(APPS))
        for app in APPS:
            directory = self.repo / "build" / app
            self.assertEqual((directory / f"{app}.exe").read_text(), "new executable")
            self.assertTrue((directory / "_internal" / "runtime.txt").is_file())
            self.assertFalse((directory / "_internal" / "old.txt").exists())
            self.assertTrue((directory / "cache.txt").is_file())

    def test_clean_build_removes_only_app_build_directories(self):
        unrelated = self.repo / "build" / "keep.txt"
        unrelated.write_text("unrelated")
        result = self.build("-CleanBuild")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for app in APPS:
            self.assertFalse((self.repo / "build" / app / "cache.txt").exists())
            self.assertTrue((self.repo / "build" / app / f"{app}.exe").is_file())
        self.assertEqual(unrelated.read_text(), "unrelated")

    def test_no_mirror_leaves_existing_builds_alone(self):
        result = self.build("-MirrorToBuild $false")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for app in APPS:
            directory = self.repo / "build" / app
            self.assertEqual((directory / f"{app}.exe").read_text(), "old executable")
            self.assertTrue((directory / "_internal" / "old.txt").is_file())

    def test_receiver_failure_stops_before_streamer_and_mirror(self):
        (self.repo / "build_mode.txt").write_text("fail Audio Receiver")
        result = self.build()
        self.assert_failed(result, "PyInstaller failed for Audio Receiver")
        self.assertEqual(self.calls(), ["Audio Receiver"])
        self.assertEqual(
            (self.repo / "build" / "Audio Receiver" / "Audio Receiver.exe").read_text(),
            "old executable",
        )

    def test_streamer_failure_does_not_mirror_receiver(self):
        (self.repo / "build_mode.txt").write_text("fail Audio Streamer")
        result = self.build()
        self.assert_failed(result, "PyInstaller failed for Audio Streamer")
        self.assertEqual(self.calls(), list(APPS))
        self.assertEqual(
            (self.repo / "build" / "Audio Receiver" / "Audio Receiver.exe").read_text(),
            "old executable",
        )

    def test_success_exit_without_exe_is_rejected(self):
        (self.repo / "build_mode.txt").write_text("missing exe Audio Receiver")
        result = self.build()
        self.assert_failed(result, "Expected build output not found")
        self.assertEqual(self.calls(), ["Audio Receiver"])

    def test_success_exit_without_internal_directory_is_rejected(self):
        (self.repo / "build_mode.txt").write_text("missing internal Audio Streamer")
        result = self.build()
        self.assert_failed(result, "Expected build output not found")
        self.assertIn("_internal", result.stderr)

    def test_missing_explicit_interpreter_fails_before_deleting_outputs(self):
        result = self.build("-PythonPath " + quote_ps(self.repo / "missing.exe"))
        self.assert_failed(result, "Python interpreter not found")
        self.assertEqual(self.calls(), [])
        self.assertTrue((self.repo / "dist" / "Audio Receiver" / "Audio Receiver.exe").exists())

    def test_missing_spec_fails_before_deleting_outputs(self):
        (self.repo / "Audio Streamer.spec").unlink()
        result = self.build()
        self.assert_failed(result, "Build specification not found")
        self.assertEqual(self.calls(), [])
        self.assertTrue((self.repo / "dist" / "Audio Receiver" / "Audio Receiver.exe").exists())

    def test_missing_pyinstaller_fails_before_deleting_outputs(self):
        (self.repo / "PyInstaller.py").unlink()
        result = self.build()
        self.assert_failed(result, "PyInstaller")
        self.assertEqual(self.calls(), [])
        self.assertTrue((self.repo / "dist" / "Audio Receiver" / "Audio Receiver.exe").exists())

    def test_explicit_interpreter_overrides_project_environment(self):
        result = self.build("-PythonPath " + quote_ps(sys.executable))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(str(Path(sys.executable)), result.stdout)

    def test_repository_venv_fallback(self):
        shutil.move(self.python_directory, self.repo / ".venv")
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(str(self.repo / ".venv" / "Scripts" / "python.exe"), result.stdout)

    def test_broken_selected_environment_reports_error_without_fallback(self):
        (self.python_directory / "pyvenv.cfg").write_text(
            "home = Z:\\missing-audio-test-python\ninclude-system-site-packages = false\n"
        )
        result = self.build()
        self.assert_failed(result, "Python interpreter")
        self.assertEqual(self.calls(), [])

    def test_dev_launchers_forward_arguments_and_report_failures(self):
        for launcher in ("run_audio_receiver_dev.ps1", "run_audio_streamer_dev.ps1"):
            with self.subTest(launcher=launcher):
                result = self.run_ps(self.script(launcher) + " 'argument with spaces' second")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(
                    json.loads((self.repo / "app_args.json").read_text()),
                    ["argument with spaces", "second"],
                )
                result = self.run_ps(self.script(launcher) + " -PythonPath " + quote_ps(sys.executable) + " fail")
                self.assert_failed(result, "exited with code 9")

    def test_scripts_restore_callers_working_directory(self):
        for script in ("rebuild_audio_streamer.ps1", "run_audio_receiver_dev.ps1"):
            with self.subTest(script=script):
                result = self.run_ps(
                    "$before = (Get-Location).Path; " + self.script(script)
                    + "; if ((Get-Location).Path -ne $before) { throw 'Location changed' }"
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_target_wrappers_forward_python_override(self):
        (self.repo / "make_audio.ps1").write_text(
            "param($Target, $AppVersion, [switch]$SkipRebuild, $PythonPath)\n"
            "if ($PythonPath -ne 'custom python.exe') { throw 'Override lost' }\n"
            "if (-not $SkipRebuild) { throw 'SkipRebuild lost' }\n"
            "Write-Output $Target\n"
        )
        for target in ("receiver", "streamer"):
            result = self.run_ps(
                self.script(f"make_audio_{target}.ps1")
                + " -PythonPath 'custom python.exe' -SkipRebuild"
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(target, result.stdout)

    def test_installer_entry_points_stop_after_failed_rebuild(self):
        local = self.parent / "local"
        compiler = local / "Programs" / "Inno Setup 6" / "ISCC.exe"
        compiler.parent.mkdir(parents=True)
        compiler.write_text("must not execute")
        (self.repo / "build_mode.txt").write_text("fail Audio Receiver")
        for script, arguments in (
            ("make_audio.ps1", "-Target receiver"),
            ("build_installers.ps1", ""),
        ):
            with self.subTest(script=script):
                result = self.run_ps(
                    self.script(script) + " " + arguments
                    + " -PythonPath " + quote_ps(sys.executable),
                    LOCALAPPDATA=str(local),
                )
                self.assert_failed(result, "PyInstaller failed for Audio Receiver")
                self.assertFalse((self.repo / "installer-output").exists())

    def test_all_project_powershell_scripts_parse(self):
        result = self.run_ps(
            "Get-ChildItem -LiteralPath " + quote_ps(ROOT)
            + " -Filter '*.ps1' | ForEach-Object {"
            + " $tokens = $null; $errors = $null;"
            + " [System.Management.Automation.Language.Parser]::ParseFile("
            + "$_.FullName, [ref]$tokens, [ref]$errors) | Out-Null;"
            + " if ($errors.Count) { throw ($errors | Out-String) } }"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
