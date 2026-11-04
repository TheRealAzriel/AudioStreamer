from collections import deque
import logging
import os
from queue import Empty, Queue
import subprocess
import threading


RECEIVER_DISCONNECTED = (
    "Receiver disconnected. Start receiving on the other computer, "
    "then click Start Stream to reconnect."
)


def ffmpeg_exit_message(returncode, detail, streaming):
    # Windows exposes FFmpeg's negative exit codes as unsigned 32-bit values.
    if streaming and returncode in (-10054, 4294957242):
        return RECEIVER_DISCONNECTED
    return (
        f"FFmpeg exited unexpectedly (code {returncode})."
        + (f"\n{detail}" if detail else "")
        + "\nCheck that the Receiver is listening, its IP is correct, "
        "and VB-CABLE is available."
    )


class StreamerLifecycle:
    def __init__(self):
        self.state = "idle"
        self.error = ""
        self._events = Queue()
        self._stop = threading.Event()
        self._worker = None

    def start(self, command):
        if self.state not in ("idle", "error"):
            raise RuntimeError("Stop the current stream before starting another.")
        if self._worker is not None and self._worker.is_alive():
            raise RuntimeError("The previous stream is still shutting down.")
        self.error = ""
        self._stop.clear()
        self.state = "connecting"
        logging.info("Streamer connection attempt: starting FFmpeg")
        self._worker = threading.Thread(target=self._run, args=(command,), daemon=True)
        self._worker.start()

    def stop(self):
        if self.state in ("connecting", "streaming", "stopping"):
            logging.info("Streamer stop requested by user or window close")
            self.state = "stopping"
            self._stop.set()
        elif self.state == "error":
            self.state = "idle"
            self.error = ""

    def poll(self):
        changes = []
        while True:
            try:
                state, error = self._events.get_nowait()
            except Empty:
                break
            if state == "streaming" and self.state == "stopping":
                continue
            if state in ("idle", "error") and self._worker is not None:
                self._worker.join()
                self._worker = None
            self.state = state
            self.error = error
            changes.append((state, error))
        return changes

    def _run(self, command):
        process = None
        readers = []
        progress = threading.Event()
        stderr = deque(maxlen=8)
        reader_errors = Queue()
        error = ""
        requested_stop = False

        def read_output(pipe, is_progress):
            try:
                for line in iter(lambda: pipe.readline(2048), b""):
                    text = line.decode("utf-8", errors="replace").strip()
                    if is_progress:
                        key, separator, value = text.partition("=")
                        if separator and key == "out_time_us":
                            try:
                                if int(value) > 0:
                                    progress.set()
                            except ValueError:
                                logging.debug("Non-numeric FFmpeg progress: %s", text)
                    else:
                        if text:
                            stderr.append(text)
            except (OSError, ValueError) as exc:
                reader_errors.put(f"Unable to read FFmpeg output: {exc}")
                logging.exception("FFmpeg output reader failed")
            finally:
                pipe.close()

        try:
            if self._stop.is_set():
                requested_stop = True
            else:
                process = subprocess.Popen(
                    command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                logging.info("Streamer FFmpeg started: pid=%s", process.pid)
                for pipe, is_progress in ((process.stdout, True), (process.stderr, False)):
                    reader = threading.Thread(
                        target=read_output, args=(pipe, is_progress), daemon=True
                    )
                    readers.append(reader)
                    reader.start()

                streaming = False
                while process.poll() is None:
                    if not reader_errors.empty():
                        error = reader_errors.get_nowait()
                        break
                    if self._stop.wait(0.05):
                        requested_stop = True
                        try:
                            process.stdin.write(b"q\n")
                            process.stdin.flush()
                        except OSError:
                            logging.warning("FFmpeg input closed before graceful stop")
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            logging.warning("FFmpeg did not stop gracefully; killing owned process")
                            process.kill()
                            process.wait(timeout=3)
                        break
                    if progress.is_set() and not streaming:
                        streaming = True
                        logging.info("Streamer audio output confirmed by FFmpeg progress")
                        self._events.put(("streaming", ""))
                process.wait(timeout=3)
        except (OSError, subprocess.SubprocessError) as exc:
            error = f"Unable to run or stop FFmpeg: {exc}"
            logging.exception("FFmpeg lifecycle failed")
        finally:
            requested_stop = requested_stop or self._stop.is_set()
            if process is not None:
                if process.poll() is None:
                    try:
                        process.kill()
                        process.wait(timeout=3)
                    except (OSError, subprocess.SubprocessError) as exc:
                        error = f"Unable to stop FFmpeg: {exc}"
                        logging.exception("FFmpeg cleanup failed")
                if process.stdin is not None:
                    try:
                        process.stdin.close()
                    except OSError:
                        logging.warning("FFmpeg input pipe was already broken during cleanup")
                for reader in readers:
                    reader.join(timeout=2)
                if any(reader.is_alive() for reader in readers):
                    error = "FFmpeg output readers did not shut down."
                    logging.error(error)
                if not reader_errors.empty():
                    error = reader_errors.get_nowait()
                signed_code = process.returncode
                if signed_code is not None and signed_code > 2147483647:
                    signed_code -= 4294967296
                logging.info(
                    "Streamer FFmpeg ended: reason=%s; exit_code=%s; signed_exit_code=%s; "
                    "audio_output_confirmed=%s",
                    "user-requested stop" if requested_stop else "unexpected exit",
                    process.returncode, signed_code, progress.is_set(),
                )
                if stderr:
                    logging.info("Streamer FFmpeg recent diagnostics:\n%s", "\n".join(stderr))
                if not requested_stop and not error:
                    detail = "\n".join(stderr).strip()
                    logging.error(
                        "FFmpeg exited unexpectedly (code %s).\n%s",
                        process.returncode, detail,
                    )
                    error = ffmpeg_exit_message(process.returncode, detail, progress.is_set())
            self._events.put(("error" if error else "idle", error))
