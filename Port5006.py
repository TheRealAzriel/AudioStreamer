import tkinter as tk
import subprocess
import platform
import os
from pathlib import Path

# Get the directory of the current script
script_dir = Path(__file__).parent.resolve()
# Construct full paths to 'ffmpeg.exe' using pathlib
ffmpeg_path = script_dir / 'ffmpeg' / 'bin' / 'ffmpeg.exe'
# Path to save the recording
recording_filename = script_dir / 'recordings' / "recorded_audio.mp3"

class SimpleAudioRecorderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Simple Audio Recorder")
        self.root.geometry("300x175")

        self.start_button = tk.Button(root, text="Start Recording", command=self.start_recording, width=20, height=2)
        self.start_button.pack(pady=10)

        self.stop_button = tk.Button(root, text="Stop Recording", command=self.stop_recording, state=tk.DISABLED, width=20, height=2)
        self.stop_button.pack(pady=10)

        self.status_label = tk.Label(root, text="Status: Idle", fg="blue")
        self.status_label.pack(pady=10)

        self.record_process = None
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def start_recording(self):
        if self.record_process is None:
            self.record_process = self.run_recording()
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.update_status("Recording", "orange")

    def run_recording(self):
        cmd = [
            str(ffmpeg_path),
            '-y',  # Overwrite output files without asking
            '-f', 'mpegts',  # Input format
            '-i', 'udp://0.0.0.0:5006',  # Input URL (UDP stream)
            str(recording_filename)  # Output file
        ]

        print(f"Running command: {' '.join(cmd)}")

        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return process

    def stop_recording(self):
        if self.record_process:
            try:
                # Send 'q' to the ffmpeg process's stdin to instruct it to finish processing
                print("Sending 'q' to ffmpeg process to stop recording gracefully.")
                self.record_process.stdin.write(b'q')
                self.record_process.stdin.flush()

                # Wait for the process to complete and ensure buffers are flushed
                stdout, stderr = self.record_process.communicate(timeout=10)
                print(f"Recording stdout: {stdout.decode('utf-8')}")
                print(f"Recording stderr: {stderr.decode('utf-8')}")
                print("Recording process terminated gracefully.")
            except subprocess.TimeoutExpired:
                print("Timed out. Forcibly terminating the recording process.")
                '''
                self.terminate_process(self.record_process)
                '''
            except Exception as e:
                print(f"Error terminating recording process: {e}")
            finally:
                self.record_process = None

        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.update_status("Idle", "blue")

    def terminate_process(self, process):
        if process:
            try:
                if platform.system() == "Windows":
                    process.terminate()
                else:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except Exception as e:
                print(f"Error terminating process: {e}")

    def update_status(self, text, color):
        self.status_label.config(text=f"Status: {text}", fg=color)

    def on_closing(self):
        self.stop_recording()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = SimpleAudioRecorderGUI(root)
    root.mainloop()