import ast
import os
from datetime import datetime
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from audio_common import (
    app_data_directory,
    is_valid_ip,
    receiver_button_states,
    receiver_status,
    recording_path,
    streamer_status,
)


ROOT = Path(__file__).resolve().parents[1]


class PathTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {}, clear=False)
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("LOCALAPPDATA", None)

    def test_local_appdata_environment_takes_precedence(self):
        with patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Custom Local Data"}):
            self.assertEqual(
                app_data_directory("Audio Streamer"), Path(r"C:\Custom Local Data\Audio Streamer")
            )

    def test_application_data_paths_preserve_current_locations(self):
        home = Path(r"C:\Users\Test User")
        with patch("audio_common.Path.home", return_value=home):
            for name in ("Audio Receiver", "Audio Streamer"):
                with self.subTest(app=name):
                    self.assertEqual(
                        app_data_directory(name), home / "AppData" / "Local" / name
                    )

    def test_history_remains_outside_packaged_application_directory(self):
        with patch("audio_common.Path.home", return_value=Path(r"C:\Users\Test User")):
            self.assertEqual(
                app_data_directory("Audio Streamer") / "ip_history.json",
                Path(r"C:\Users\Test User\AppData\Local\Audio Streamer\ip_history.json"),
            )

    def test_path_helpers_do_not_create_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            with patch("audio_common.Path.home", return_value=home):
                directory = app_data_directory("Audio Receiver")
                recording_path(directory, datetime(2026, 1, 2, 3, 4, 5))
            self.assertEqual(list(home.iterdir()), [])

    def test_recording_name_preserves_format_and_folder(self):
        directory = Path(r"C:\Recordings with spaces")
        self.assertEqual(
            recording_path(directory, datetime(2026, 1, 2, 3, 4, 5)),
            directory / "recording_20260102_030405.mp3",
        )

    def test_recording_name_preserves_second_precision(self):
        directory = Path("recordings")
        self.assertEqual(
            recording_path(directory, datetime(2026, 1, 2, 3, 4, 5, 123456)),
            recording_path(directory, datetime(2026, 1, 2, 3, 4, 5, 999999)),
        )


class IPValidationTests(unittest.TestCase):
    def test_existing_ipv4_formats_are_accepted(self):
        for address in ("192.168.1.10", "127.0.0.1", "0.0.0.0", "255.255.255.255",
                        "127.1", "2130706433"):
            with self.subTest(address=address):
                self.assertTrue(is_valid_ip(address))

    def test_invalid_addresses_are_rejected(self):
        for address in ("", "256.1.1.1", "1.2.3.4.5", "-1.0.0.1", "receiver.local",
                        "::1", "192.168.1.10:6005"):
            with self.subTest(address=address):
                self.assertFalse(is_valid_ip(address))

    def test_validation_does_not_open_network_connections(self):
        with patch("socket.socket", side_effect=AssertionError("Network access")):
            self.assertTrue(is_valid_ip("192.168.1.10"))
            self.assertFalse(is_valid_ip("not an address"))


class StatusTests(unittest.TestCase):
    def test_receiver_status_states_and_indicator_colors(self):
        for text, expected in (
            ("Idle", ("idle", "#cccccc", "#999999")),
            ("Receiving Stream", ("connected", "#4CAF50", "#2E7D32")),
            ("Receiving & Recording", ("connected", "#4CAF50", "#2E7D32")),
            ("Error: ffplay not found", ("error", "#f44336", "#d32f2f")),
            ("Muted", ("muted", "#ff9800", "#f57c00")),
        ):
            with self.subTest(text=text):
                self.assertEqual(receiver_status(text), expected)

    def test_streamer_status_states_and_indicator_colors(self):
        for text, expected in (
            ("Idle", ("idle", "#cccccc", "#999999")),
            ("Connecting", ("connecting", "#ff9800", "#f57c00")),
            ("Stopping", ("stopping", "#ff9800", "#f57c00")),
            ("Streaming", ("streaming", "#4CAF50", "#2E7D32")),
            ("Error", ("error", "#f44336", "#d32f2f")),
        ):
            with self.subTest(text=text):
                self.assertEqual(streamer_status(text), expected)

    def test_unknown_status_leaves_indicator_unchanged(self):
        for get_status in (receiver_status, streamer_status):
            for text in ("", "Unrecognized", "idle"):
                with self.subTest(app=get_status.__name__, text=text):
                    self.assertIsNone(get_status(text))

    def test_existing_status_precedence_is_preserved(self):
        self.assertEqual(receiver_status("Receiving Error"), receiver_status("Receiving"))
        self.assertEqual(receiver_status("Error: Muted"), receiver_status("Error"))
        self.assertEqual(streamer_status("Streaming Error"), streamer_status("Streaming"))

    def test_receiver_status_transitions(self):
        texts = ("Idle", "Receiving Stream", "Muted", "Receiving Stream", "Error", "Idle")
        self.assertEqual(
            [receiver_status(text) for text in texts],
            [
                ("idle", "#cccccc", "#999999"),
                ("connected", "#4CAF50", "#2E7D32"),
                ("muted", "#ff9800", "#f57c00"),
                ("connected", "#4CAF50", "#2E7D32"),
                ("error", "#f44336", "#d32f2f"),
                ("idle", "#cccccc", "#999999"),
            ],
        )

    def test_streamer_status_transitions(self):
        self.assertEqual(
            [streamer_status(text) for text in ("Idle", "Streaming", "Error", "Idle")],
            [
                ("idle", "#cccccc", "#999999"),
                ("streaming", "#4CAF50", "#2E7D32"),
                ("error", "#f44336", "#d32f2f"),
                ("idle", "#cccccc", "#999999"),
            ],
        )

    def test_receiver_controls_follow_process_start_and_stop(self):
        self.assertEqual(
            [receiver_button_states(active) for active in (False, True, False)],
            [(True, False, True), (False, True, False), (True, False, True)],
        )


class FoundationTests(unittest.TestCase):
    def test_common_module_import_has_no_application_side_effects(self):
        code = """
import pathlib
import socket
import subprocess
import sys
from unittest.mock import patch

with patch.object(pathlib.Path, "mkdir", side_effect=AssertionError("Directory write")), \\
     patch("builtins.open", side_effect=AssertionError("File access")), \\
     patch.object(socket, "socket", side_effect=AssertionError("Network access")), \\
     patch.object(subprocess, "Popen", side_effect=AssertionError("Process start")):
    import audio_common

for name in ("tkinter", "comtypes", "pycaw"):
    assert name not in sys.modules, name
"""
        result = subprocess.run(
            [sys.executable, "-B", "-c", code],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_project_python_and_specs_have_python_311_syntax(self):
        paths = sorted(ROOT.glob("*.py")) + sorted(ROOT.glob("*.spec"))
        paths += sorted((ROOT / "tests").glob("*.py"))
        for path in paths:
            with self.subTest(file=path.name):
                source = path.read_text(encoding="utf-8-sig")
                tree = ast.parse(source, filename=str(path), feature_version=(3, 11))
                compile(tree, str(path), "exec")


if __name__ == "__main__":
    unittest.main()
