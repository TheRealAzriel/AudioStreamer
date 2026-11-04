from collections import deque
import logging
import threading


class ProcessDiagnostics:
    def __init__(self, pipe, label):
        self.pipe = pipe
        self.label = label
        self.lines = deque(maxlen=12)
        self.streaming = False
        self.input_opened = False
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        progress_keys = {
            "bitrate", "total_size", "out_time_us", "out_time_ms", "out_time",
            "dup_frames", "drop_frames", "speed", "progress",
        }
        try:
            while True:
                line = self.pipe.readline(2048)
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                key, separator, value = text.partition("=")
                if separator and key in progress_keys:
                    if key == "out_time_us" and not self.streaming:
                        try:
                            positive = int(value) > 0
                        except ValueError:
                            positive = False
                        if positive:
                            self.streaming = True
                            logging.info("%s: audio output confirmed by progress", self.label)
                    continue
                if "Input #0," in text and not self.input_opened:
                    self.input_opened = True
                    logging.info(
                        "%s: input opened (not proof of speaker playback)", self.label
                    )
                if text:
                    self.lines.append(text)
        except (OSError, ValueError):
            logging.exception("%s: diagnostic reader failed", self.label)
        finally:
            self.pipe.close()

    def finish(self, returncode, reason):
        self.thread.join(timeout=2)
        if self.thread.is_alive():
            logging.error("%s: diagnostic reader did not finish", self.label)
        signed = returncode
        if returncode is not None and returncode > 2147483647:
            signed = returncode - 4294967296
        logging.info(
            "%s ended: reason=%s; exit_code=%s; signed_exit_code=%s",
            self.label, reason, returncode, signed,
        )
        if self.lines:
            logging.info("%s recent diagnostics:\n%s", self.label, "\n".join(self.lines))
