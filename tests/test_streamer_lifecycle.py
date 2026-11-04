import ast
import logging
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from streamer_lifecycle import RECEIVER_DISCONNECTED, StreamerLifecycle, ffmpeg_exit_message
from audio_common import streamer_status


class StreamerLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.lifecycle = StreamerLifecycle()
        self.addCleanup(self.cleanup_stream)

    def cleanup_stream(self):
        self.lifecycle.stop()
        deadline = time.monotonic() + 10
        while self.lifecycle.state not in ("idle", "error") and time.monotonic() < deadline:
            self.lifecycle.poll()
            time.sleep(0.01)
        self.assertIn(self.lifecycle.state, ("idle", "error"), "Owned child did not stop")

    def start(self, code):
        self.lifecycle.start([sys.executable, "-u", "-c", code])

    def wait_for(self, state, timeout=10):
        deadline = time.monotonic() + timeout
        changes = []
        while time.monotonic() < deadline:
            changes.extend(self.lifecycle.poll())
            if self.lifecycle.state == state:
                return changes
            time.sleep(0.01)
        self.fail(f"Expected {state}, got {self.lifecycle.state}: {self.lifecycle.error}")

    def test_spawn_does_not_mean_streaming(self):
        self.start("import time; time.sleep(30)")
        time.sleep(0.1)
        self.assertEqual(self.lifecycle.poll(), [])
        self.assertEqual(self.lifecycle.state, "connecting")

    def test_positive_output_progress_confirms_streaming(self):
        self.start("import sys; print('out_time_us=1000'); sys.stdin.readline()")
        self.wait_for("streaming")
        self.lifecycle.stop()
        self.assertEqual(self.lifecycle.state, "stopping")
        self.wait_for("idle")
        self.assertEqual(self.lifecycle.error, "")

    def test_log_explains_confirmed_stream_and_requested_stop(self):
        with self.assertLogs(level="INFO") as logs:
            self.start("import sys; print('out_time_us=1000'); sys.stdin.readline()")
            self.wait_for("streaming")
            self.lifecycle.stop()
            self.wait_for("idle")
        text = "\n".join(logs.output)
        self.assertIn("audio output confirmed", text)
        self.assertIn("reason=user-requested stop", text)
        self.assertIn("exit_code=0", text)

    def test_stderr_is_bounded_and_only_summarized_at_exit(self):
        with self.assertLogs(level="INFO") as logs:
            self.start(
                "import sys; sys.stderr.write('diagnostic\\n'*1000);"
                "sys.stderr.flush(); print('out_time_us=1000'); sys.stdin.readline()"
            )
            self.wait_for("streaming")
            self.lifecycle.stop()
            self.wait_for("idle")
        self.assertLessEqual("\n".join(logs.output).count("diagnostic\n"), 8)
        self.assertIn("recent diagnostics", "\n".join(logs.output))

    def test_zero_or_unavailable_progress_does_not_confirm_streaming(self):
        self.start("import sys; print('out_time_us=N/A'); print('out_time_us=0'); sys.stdin.readline()")
        time.sleep(0.15)
        self.lifecycle.poll()
        self.assertEqual(self.lifecycle.state, "connecting")

    def test_immediate_failure_reports_exit_code_and_stderr(self):
        self.start("import sys; print('Connection refused', file=sys.stderr); sys.exit(7)")
        changes = self.wait_for("error")
        self.assertNotIn("streaming", [state for state, _ in changes])
        self.assertIn("code 7", self.lifecycle.error)
        self.assertIn("Connection refused", self.lifecycle.error)
        self.assertIn("Receiver", self.lifecycle.error)

    def test_later_exit_restores_error_state(self):
        self.start("import time; print('out_time_us=1000'); time.sleep(0.3); raise SystemExit(2)")
        self.wait_for("streaming")
        self.wait_for("error")
        self.assertIn("code 2", self.lifecycle.error)

    def test_connection_reset_after_progress_shows_reconnect_message(self):
        self.start(
            "import time; print('out_time_us=1000'); time.sleep(0.3);"
            "raise SystemExit(-10054)"
        )
        self.wait_for("streaming")
        with patch("streamer_lifecycle.logging.error") as log:
            self.wait_for("error")
        self.assertEqual(self.lifecycle.error, RECEIVER_DISCONNECTED)
        log.assert_called()

    def test_signed_and_unsigned_reset_codes_have_same_friendly_message(self):
        for code in (-10054, 4294957242):
            with self.subTest(code=code):
                self.assertEqual(
                    ffmpeg_exit_message(code, "Technical diagnostics", True),
                    RECEIVER_DISCONNECTED,
                )

    def test_reset_before_streaming_remains_startup_failure(self):
        message = ffmpeg_exit_message(4294957242, "Connection reset", False)
        self.assertIn("code 4294957242", message)
        self.assertIn("Connection reset", message)
        self.assertNotEqual(message, RECEIVER_DISCONNECTED)

    def test_other_failures_after_streaming_keep_technical_diagnostics(self):
        message = ffmpeg_exit_message(2, "Encoder failed", True)
        self.assertIn("code 2", message)
        self.assertIn("Encoder failed", message)

    def test_unexpected_success_exit_is_not_a_user_stop(self):
        self.start("pass")
        self.wait_for("error")
        self.assertIn("code 0", self.lifecycle.error)

    def test_missing_executable_reports_actionable_error(self):
        self.lifecycle.start([str(Path(__file__).parent / "missing-ffmpeg-test.exe")])
        self.wait_for("error")
        self.assertIn("Unable to run", self.lifecycle.error)

    def test_stop_is_nonblocking_and_kills_unresponsive_owned_child(self):
        self.start("import time; print('out_time_us=1000'); time.sleep(30)")
        self.wait_for("streaming")
        before = time.monotonic()
        self.lifecycle.stop()
        self.assertLess(time.monotonic() - before, 0.2)
        self.wait_for("idle")
        self.assertEqual(self.lifecycle.error, "")

    def test_stopping_ignores_queued_streaming_confirmation(self):
        self.start("import sys; print('out_time_us=1000'); sys.stdin.readline()")
        time.sleep(0.2)
        self.lifecycle.stop()
        changes = self.wait_for("idle")
        self.assertNotIn("streaming", [state for state, _ in changes])

    def test_repeat_start_stop_and_restart_after_failure(self):
        self.start("raise SystemExit(4)")
        self.wait_for("error")
        for _ in range(3):
            self.start("import sys; print('out_time_us=1000'); sys.stdin.readline()")
            self.wait_for("streaming")
            self.assertEqual(self.lifecycle.error, "")
            self.lifecycle.stop()
            self.wait_for("idle")
            self.assertIsNone(self.lifecycle._worker)

    def test_overlapping_start_is_rejected(self):
        self.start("import time; time.sleep(30)")
        with self.assertRaisesRegex(RuntimeError, "Stop the current"):
            self.start("pass")

    def test_stop_does_not_kill_unrelated_process(self):
        other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            self.start("import sys; print('out_time_us=1000'); sys.stdin.readline()")
            self.wait_for("streaming")
            self.lifecycle.stop()
            self.wait_for("idle")
            self.assertIsNone(other.poll())
        finally:
            other.kill()
            other.wait(timeout=5)

    def test_readers_handle_invalid_utf8_and_large_stderr(self):
        self.start(
            "import sys; sys.stderr.buffer.write(b'\\xff\\n' * 10000);"
            "sys.stderr.flush(); print('out_time_us=1000'); sys.stdin.readline()"
        )
        with patch("streamer_lifecycle.logging.error"):
            self.wait_for("streaming")
            self.lifecycle.stop()
            self.wait_for("idle")

    def test_worker_and_readers_finish_before_restart(self):
        import threading

        created = []

        real_thread = threading.Thread

        def make_thread(*args, **kwargs):
            thread = real_thread(*args, **kwargs)
            created.append(thread)
            return thread

        with patch("streamer_lifecycle.threading.Thread", side_effect=make_thread):
            self.start("import sys; print('out_time_us=1000'); sys.stdin.readline()")
            self.wait_for("streaming")
            self.lifecycle.stop()
            self.wait_for("idle")
            self.assertEqual(len(created), 3)
            self.assertTrue(all(not thread.is_alive() for thread in created))
            self.assertIsNone(self.lifecycle._worker)


class StreamerGUIIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "Audio Streamer.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        gui = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        cls.namespace = {
            "logging": logging,
            "subprocess": SimpleNamespace(
                run=Mock(), SubprocessError=subprocess.SubprocessError,
                CREATE_NO_WINDOW=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ),
            "messagebox": Mock(), "is_valid_ip": lambda ip: ip == "127.0.0.1",
            "executable_path": Mock(), "ffmpeg_path": Mock(),
            "streamer_status": streamer_status,
            "RECEIVER_DISCONNECTED": RECEIVER_DISCONNECTED,
        }
        exec(compile(ast.Module(body=[gui], type_ignores=[]), str(path), "exec"), cls.namespace)
        cls.gui_type = cls.namespace["FFMPEGSenderGUI"]

    def setUp(self):
        self.app = self.gui_type.__new__(self.gui_type)
        self.app.root = Mock()
        self.app.lifecycle = Mock(state="idle")
        self.app.lifecycle.poll.return_value = []
        self.app.closing = False
        self.app.lifecycle_after = "timer-id"
        self.app.pending_connection = None
        self.app.set_stream_state = Mock()
        self.app.status_message = Mock()
        self.app.status_canvas = Mock()
        self.app.status_indicator = "indicator"
        self.app.add_ip_to_history = Mock()
        self.app.update_ip_dropdown = Mock()
        self.app.ip_entry = Mock()
        self.app.ip_entry.get.return_value = "127.0.0.1"
        self.app.name_entry = Mock()
        self.app.name_entry.get.return_value = "Receiver"
        self.app.check_audio_device = Mock(return_value=True)
        self.namespace["messagebox"].reset_mock()
        self.namespace["subprocess"].run.reset_mock()
        self.namespace["subprocess"].run.side_effect = None

    def test_start_uses_progress_and_does_not_save_unconfirmed_connection(self):
        self.app.start_stream()
        command = self.app.lifecycle.start.call_args.args[0]
        self.assertIn("-progress", command)
        self.assertEqual(command[command.index("-progress") + 1], "pipe:1")
        self.app.set_stream_state.assert_called_once_with("connecting")
        self.app.add_ip_to_history.assert_not_called()

    def test_confirmation_saves_the_original_target_only_once(self):
        self.app.pending_connection = ("127.0.0.1", "Original Receiver")
        self.app.lifecycle.poll.return_value = [("streaming", "")]
        self.app.poll_stream()
        self.app.poll_stream()
        self.app.add_ip_to_history.assert_called_once_with("127.0.0.1", "Original Receiver")

    def test_error_restores_controls_and_shows_failure_on_ui_thread(self):
        self.app.pending_connection = ("127.0.0.1", "Receiver")
        self.app.lifecycle.poll.return_value = [("error", "Connection refused")]
        self.app.poll_stream()
        self.app.set_stream_state.assert_called_once_with("error")
        self.namespace["messagebox"].showerror.assert_called_once_with(
            "Streaming Failed", "Connection refused"
        )
        self.assertIsNone(self.app.pending_connection)

    def test_disconnect_shows_information_instead_of_failure(self):
        self.app.lifecycle.poll.return_value = [("error", RECEIVER_DISCONNECTED)]
        self.app.poll_stream()
        self.app.set_stream_state.assert_called_once_with("error")
        self.namespace["messagebox"].showinfo.assert_called_once_with(
            "Receiver Disconnected", RECEIVER_DISCONNECTED
        )
        self.namespace["messagebox"].showerror.assert_not_called()

    def test_close_waits_for_shutdown_then_destroys_without_another_callback(self):
        def stop():
            self.app.lifecycle.state = "stopping"

        self.app.lifecycle.stop.side_effect = stop
        self.app.on_closing()
        self.app.root.destroy.assert_not_called()
        self.app.lifecycle.state = "idle"
        self.app.lifecycle.poll.return_value = [("idle", "")]
        self.app.poll_stream()
        self.app.root.destroy.assert_called_once()
        self.app.root.after.assert_not_called()

    def test_idle_close_cancels_pending_poll(self):
        self.app.on_closing()
        self.app.root.after_cancel.assert_called_once_with("timer-id")
        self.app.root.destroy.assert_called_once()

    def test_preparation_failure_does_not_spawn_stream(self):
        self.namespace["subprocess"].run.side_effect = OSError("Setup cannot launch")
        self.app.start_stream()
        self.app.lifecycle.start.assert_not_called()
        self.namespace["messagebox"].showerror.assert_called_once()

    def test_invalid_ip_does_not_touch_audio_or_spawn_process(self):
        self.app.ip_entry.get.return_value = "invalid"
        self.app.start_stream()
        self.app.check_audio_device.assert_not_called()
        self.app.lifecycle.start.assert_not_called()
        self.namespace["subprocess"].run.assert_not_called()

    def test_repeated_start_while_connecting_is_ignored(self):
        self.app.lifecycle.state = "connecting"
        self.app.start_stream()
        self.app.lifecycle.start.assert_not_called()
        self.app.check_audio_device.assert_not_called()

    def test_lifecycle_states_set_controls_and_status(self):
        self.app.set_button_enabled = Mock()
        self.app.start_button = Mock()
        self.app.stop_button = Mock()
        for state, start, stop in (
            ("idle", True, False), ("connecting", False, True),
            ("streaming", False, True), ("stopping", False, False),
            ("error", True, False),
        ):
            with self.subTest(state=state):
                self.app.set_button_enabled.reset_mock()
                self.gui_type.set_stream_state(self.app, state)
                self.assertEqual(self.app.connection_status, state)
                self.app.set_button_enabled.assert_any_call(self.app.start_button, start)
                self.app.set_button_enabled.assert_any_call(self.app.stop_button, stop)


if __name__ == "__main__":
    unittest.main()
