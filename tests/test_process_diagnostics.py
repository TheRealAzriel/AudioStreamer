import ast
import io
import logging
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from typing import cast

from process_diagnostics import ProcessDiagnostics


ROOT = Path(__file__).resolve().parents[1]


class ProcessDiagnosticsTests(unittest.TestCase):
    def test_progress_confirms_audio_once_and_is_not_in_diagnostic_tail(self):
        output = b"out_time_us=N/A\nout_time_us=0\nout_time_us=12\nout_time_us=24\nprogress=end\n"
        with self.assertLogs(level="INFO") as logs:
            diagnostics = ProcessDiagnostics(io.BytesIO(output), "Receiver FFmpeg")
            diagnostics.finish(0, "remote stream ended")
        self.assertTrue(diagnostics.streaming)
        self.assertEqual(list(diagnostics.lines), [])
        self.assertEqual(sum("audio output confirmed" in line for line in logs.output), 1)

    def test_ffplay_input_opened_is_not_claimed_as_speaker_playback(self):
        with self.assertLogs(level="INFO") as logs:
            diagnostics = ProcessDiagnostics(
                io.BytesIO(b"Input #0, mpegts, from tcp:\n"), "Receiver FFplay"
            )
            diagnostics.finish(0, "remote stream ended")
        self.assertTrue(diagnostics.input_opened)
        self.assertFalse(diagnostics.streaming)
        self.assertTrue(any("not proof of speaker playback" in line for line in logs.output))

    def test_large_stderr_is_drained_with_bounded_tail_and_invalid_utf8(self):
        child = subprocess.Popen(
            [sys.executable, "-c",
             "import sys; sys.stderr.buffer.write(b'x'*1000000+b'\\xff\\nlast error\\n')"],
            stderr=subprocess.PIPE,
        )
        try:
            diagnostics = ProcessDiagnostics(child.stderr, "Test child")
            code = child.wait(timeout=10)
            with self.assertLogs(level="INFO") as logs:
                diagnostics.finish(code, "test complete")
            self.assertFalse(diagnostics.thread.is_alive())
            self.assertLessEqual(len(diagnostics.lines), 12)
            self.assertTrue(all(len(line) <= 2048 for line in diagnostics.lines))
            self.assertTrue(any("last error" in line for line in logs.output))
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=3)

    def test_windows_exit_code_and_stop_reason_are_logged(self):
        with self.assertLogs(level="INFO") as logs:
            diagnostics = ProcessDiagnostics(io.BytesIO(b"Broken pipe\n"), "Receiver FFmpeg")
            diagnostics.finish(4294967264, "user requested Stop Receiving")
        text = "\n".join(logs.output)
        self.assertIn("signed_exit_code=-32", text)
        self.assertIn("user requested Stop Receiving", text)
        self.assertIn("Broken pipe", text)


class ReceiverDiagnosticsIntegrationTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((ROOT / "Audio Receiver.py").read_text(encoding="utf-8-sig"))
        gui = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        self.namespace = {
            "logging": logging, "subprocess": subprocess, "typing_cast": cast,
            "ProcessDiagnostics": ProcessDiagnostics, "messagebox": Mock(),
            "ffmpeg_path": Path(sys.executable), "ffplay_path": Path(sys.executable),
        }
        exec(compile(ast.Module(body=[gui], type_ignores=[]), "<Receiver>", "exec"),
             self.namespace)
        self.app = self.namespace["FFplayGUI"].__new__(self.namespace["FFplayGUI"])
        self.app.root = Mock()
        self.app.audio_process = None
        self.app.is_recording_mode = False
        self.app.receiver_stop_reason = None
        self.app.update_button_states = Mock()
        self.app.update_status = Mock()
        self.app.update_play_button_state = Mock()

    def test_remote_exit_captures_ffplay_error_and_schedules_visible_error(self):
        child = Mock(pid=123, returncode=7)
        child.stderr = io.BytesIO(b"Connection refused\n")
        child.wait.return_value = 7
        child.poll.return_value = 7
        with patch("subprocess.Popen", return_value=child):
            with self.assertLogs(level="INFO") as logs:
                self.app.run_receiver()
        self.assertIn("Connection refused", "\n".join(logs.output))
        self.assertIn("exit_code=7", "\n".join(logs.output))
        self.app.root.after.assert_any_call(
            0, self.app.update_status, "Error", "red"
        )

    def test_recording_user_stop_reports_output_and_reason_without_error_dialog(self):
        self.app.is_recording_mode = True
        self.app.receiver_stop_reason = "user requested Stop Receiving"
        main = Mock(pid=123, returncode=4294967264)
        main.stderr = io.BytesIO(b"out_time_us=100\nBroken pipe\n")
        main.wait.return_value = 4294967264
        main.poll.return_value = 4294967264
        playback = Mock(pid=124, returncode=0)
        playback.stderr = io.BytesIO(b"")
        with tempfile.TemporaryDirectory() as temporary:
            self.app.recording_filename = Path(temporary) / "recording.mp3"
            self.app.recording_filename.write_bytes(b"recorded audio")
            with patch("subprocess.Popen", side_effect=[main, playback]):
                with self.assertLogs(level="INFO") as logs:
                    self.app.run_receiver()
        text = "\n".join(logs.output)
        self.assertIn("user requested Stop Receiving", text)
        self.assertIn("finalization not confirmed", text)
        self.assertIn("14 bytes", text)
        self.assertIn("Broken pipe", text)
        self.app.root.after.assert_any_call(0, self.app.update_status, "Idle", "blue")
        self.assertFalse(any(
            call.args[1] == self.namespace["messagebox"].showerror
            for call in self.app.root.after.call_args_list
        ))

    def test_spawn_failure_is_logged_and_shown(self):
        with patch("subprocess.Popen", side_effect=OSError("Cannot start process")):
            with self.assertLogs(level="ERROR") as logs:
                self.app.run_receiver()
        self.assertIn("Cannot start process", "\n".join(logs.output))
        self.app.root.after.assert_any_call(0, self.app.update_status, "Error", "red")

    def test_recorded_file_playback_errors_are_drained_and_reported(self):
        self.namespace["os"] = __import__("os")
        self.app.play_button = Mock()
        self.app.stop_play_button = Mock()
        self.app.set_button_enabled = Mock()
        child = Mock(pid=125, returncode=1)
        child.stderr = io.BytesIO(b"Invalid recording data\n")
        child.poll.return_value = 1
        with tempfile.TemporaryDirectory() as temporary:
            self.app.recording_filename = Path(temporary) / "recording.mp3"
            self.app.recording_filename.write_bytes(b"test data")
            with patch("subprocess.Popen", return_value=child):
                with self.assertLogs(level="INFO") as logs:
                    self.app.play_recording()
                    self.app.check_playback_status()
        self.assertIn("Invalid recording data", "\n".join(logs.output))
        self.namespace["messagebox"].showerror.assert_called_once()
        self.assertIsNone(self.app.play_process)
        self.assertIsNone(self.app.play_diagnostics)


if __name__ == "__main__":
    unittest.main()
