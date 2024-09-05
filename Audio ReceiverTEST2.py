import tkinter as tk
from pathlib import Path
import subprocess
import os
import time
import logging
import threading
import platform
import signal
import socket
from ctypes import POINTER, cast
import comtypes
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from datetime import datetime

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Get the directory of the current script.
script_dir = Path(__file__).parent.resolve()

# Construct full paths to 'ffmpeg.exe' and 'ffplay.exe' using pathlib
ffmpeg_path = script_dir / 'ffmpeg' / 'bin' / 'ffmpeg.exe'
ffplay_path = script_dir / 'ffmpeg' / 'bin' / 'ffplay.exe'
ffprobe_path = script_dir / 'ffmpeg' / 'bin' / 'ffprobe.exe'

# Function to terminate processes by name
def terminate_process(process_name):
    if platform.system() == "Windows":
        commands = ['taskkill', '/F', '/IM', f'{process_name}.exe', '/T']
    else:
        commands = ['pkill', '-f', process_name]

    try:
        subprocess.run(commands, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    except Exception as e:
        logging.error(f"Error terminating {process_name} processes: {e}")

class FFplayGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Audio Receiver Tester")
        self.root.geometry("400x475")

        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(
            IAudioEndpointVolume._iid_, comtypes.CLSCTX_INPROC_SERVER, None)
        self.volume = cast(interface, POINTER(IAudioEndpointVolume))

        self.process = None
        self.record_process = None
        self.stream_thread = None
        self.record_thread = None
        self.play_process = None
        self.is_muted = False

        self.recordings_dir = script_dir / 'recordings'
        self.recordings_dir.mkdir(exist_ok=True)

        self.recording_filename = self.recordings_dir / "recorded_audio.mp3"

        self.local_ip = self.get_local_ip()
        
        self.bitrate_thread = None  # Initialize bitrate_thread
        self.is_monitoring = False  # Initialize monitoring flag

        volume_frame = tk.Frame(root, bg="lightblue", bd=2, relief="solid")
        volume_frame.place(x=20, y=10, width=90, height=280)

        self.volume_slider = tk.Scale(volume_frame, from_=100, to=0, orient=tk.VERTICAL, command=self.set_volume)
        self.volume_slider.set(self.get_current_volume())
        self.volume_slider.place(x=20, y=20, height=220)

        self.volume_slider.bind("<MouseWheel>", self.on_mouse_wheel)
        self.volume_slider.bind("<Button-4>", self.on_mouse_wheel)
        self.volume_slider.bind("<Button-5>", self.on_mouse_wheel)

        self.volume_label = tk.Label(volume_frame, text="Volume", bg="skyblue")
        self.volume_label.place(x=20, y=250)

        stream_frame = tk.Frame(root, bg="royalblue1", bd=2, relief="solid")
        stream_frame.place(x=150, y=10, width=225, height=280)

        self.mute_button = tk.Canvas(stream_frame, width=50, height=50, bg="skyblue", bd=2, relief="solid")
        self.mute_button.create_oval(5, 5, 52, 52, fill="red", tag="circle")
        self.mute_button.tag_bind("circle", "<Button-1>", self.mute)
        self.mute_button.place(x=80, y=180)

        self.mute_label = tk.Label(stream_frame, text="Mute All", bg="skyblue")
        self.mute_label.place(x=84, y=250)

        self.start_button = tk.Button(stream_frame, text="Receive Stream", command=self.start_stream, width=20, height=2, relief="solid", bd=2)
        self.start_button.place(x=35, y=25)

        self.stop_button = tk.Button(stream_frame, text="Stop Receiving", command=self.stop_stream, state=tk.DISABLED, width=20, height=2, relief="solid", bd=2)
        self.stop_button.place(x=35, y=100)

        self.status_label = tk.Label(root, text="Status: Idle", fg="blue", bg="white", font=("Arial", 10, "bold"))
        self.status_label.place(x=130, y=355)

        self.bitrate_label = tk.Label(root, text="Bitrate: N/A", fg="blue", bg="white", font=("Arial", 10, "bold"))
        self.bitrate_label.place(x=130, y=375)

        self.record_button = tk.Button(root, text="Start Recording", command=self.start_recording, width=15, height=2, relief="solid", bd=2)
        self.record_button.place(x=50, y=305)

        self.stop_record_button = tk.Button(root, text="Stop Recording", command=self.stop_recording, state=tk.DISABLED, width=15, height=2, relief="solid", bd=2)
        self.stop_record_button.place(x=210, y=305)

        self.play_button = tk.Button(root, text="Play Recording", command=self.play_recording, state=tk.DISABLED, width=15, height=2, relief="solid", bd=2)
        self.play_button.place(x=130, y=405)
        self.update_play_button_state()  # Initial update based on the presence of the recording file

        self.ip_label = tk.Label(root, text=f"Local IP: {self.local_ip}", bg="white")
        self.ip_label.place(x=125, y=450)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def start_monitoring(self):
        if not self.is_monitoring:
            self.is_monitoring = True
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.bitrate_thread = threading.Thread(target=self.update_bitrate_loop)
            self.bitrate_thread.start()

    def stop_monitoring(self):
        if self.is_monitoring:
            self.is_monitoring = False
            if self.bitrate_thread and self.bitrate_thread.is_alive():
                self.bitrate_thread.join()
                self.bitrate_thread = None  # Added this line
            self.update_bitrate_label("Bitrate: N/A")

    def update_bitrate_loop(self):
        stream_url = 'udp://localhost:5004'
        while self.is_monitoring:
            if self.root.winfo_exists():  # Check if the root window exists to avoid errors during shutdown.
                bitrate = self.get_bitrate(stream_url)
                self.root.after(0, self.update_bitrate_label_safe, bitrate)
            else:
                return  # Exit the loop if the root window is destroyed.
            time.sleep(1)

    def update_bitrate_label_safe(self, bitrate):
        self.update_bitrate_label(f"Bitrate: {bitrate} bits/s")

    def update_bitrate_label(self, text):
        self.bitrate_label.config(text=text)

    @staticmethod
    def get_bitrate(stream_url):
        try:
            result = subprocess.run(
                [str(ffprobe_path), '-v', 'error', '-show_entries', 'format=bit_rate', '-of',
                 'default=noprint_wrappers=1:nokey=1', stream_url],
                capture_output=True, text=True, check=True
            )
            bitrate = result.stdout.strip()
            if bitrate:
                return bitrate
            else:
                return "N/A"
        except subprocess.CalledProcessError as e:
            logging.error(f"An error occurred: {e}")
            return "N/A"

    def get_local_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0)
        try:
            s.connect(('10.254.254.254', 1))
            ip = s.getsockname()[0]
        except Exception:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip

    def get_current_volume(self):
        current_volume = self.volume.GetMasterVolumeLevelScalar()
        return int(current_volume * 100)

    def start_stream(self):
        if self.process is None:
            self.stream_thread = threading.Thread(target=self.run_ffplay)
            self.stream_thread.start()
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.update_status("Receiving Stream", "green")
            self.start_monitoring()

    def run_ffplay(self):
        self.process = subprocess.Popen(
            [str(ffplay_path), '-nodisp', '-flags', 'low_delay', '-fflags', 'nobuffer', '-f', 'mpegts', 'udp://0.0.0.0:5005'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid if platform.system() != "Windows" else None
        )
        self.process.communicate()
        self.process = None
        self.update_button_states()
        self.update_status("Idle", "blue")

    def stop_stream(self):
        # Stop recording if it is active
        if self.record_process:
            self.stop_recording()
        
        if self.process:
            def terminate_process_thread():
                try:
                    if platform.system() == "Windows":
                        self.process.terminate()
                    else:
                        os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                except Exception as e:
                    logging.error(f"Error terminating stream process: {e}")
                finally:
                    self.process = None
                    self.update_stop_stream_ui()

            threading.Thread(target=terminate_process_thread).start()
        else:
            self.update_stop_stream_ui()

    def update_stop_stream_ui(self):
        self.update_button_states()
        self.update_status("Idle", "blue")
        self.stop_monitoring()

    def terminate_process(self, process):
        if process:
            try:
                if platform.system() == "Windows":
                    process.terminate()
                else:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            except Exception as e:
                logging.error(f"Error terminating process: {e}")

    def set_volume(self, value):
        volume_level = int(value) / 100.0
        self.volume.SetMasterVolumeLevelScalar(volume_level, None)

    def on_mouse_wheel(self, event):
        if event.num == 4 or event.delta > 0:
            self.volume_slider.set(self.volume_slider.get() + 1)
        elif event.num == 5 or event.delta < 0:
            self.volume_slider.set(self.volume_slider.get() - 1)

    def mute(self, event=None):
        if self.volume.GetMute() == 0:
            self.volume.SetMute(1, None)
            self.mute_button.itemconfig("circle", fill="green")
            self.is_muted = True
            self.update_status("Muted", "red")
        else:
            self.volume.SetMute(0, None)
            self.mute_button.itemconfig("circle", fill="red")
            self.is_muted = False
            if self.process is not None:
                self.update_status("Receiving Stream", "green")
            else:
                self.update_status("Idle", "blue")

    def update_status(self, text, color):
        if self.root.winfo_exists():
            self.status_label.config(text=f"Status: {text}", fg=color)

    def update_button_states(self):
        if self.root.winfo_exists():
            self.start_button.config(state=tk.NORMAL if self.process is None else tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL if self.process is not None else tk.DISABLED)

    def start_recording(self):
        if self.record_thread is None or not self.record_thread.is_alive():
            self.record_thread = threading.Thread(target=self.run_recording)
            self.record_thread.start()
            self.record_button.config(state=tk.DISABLED)
            self.stop_record_button.config(state=tk.NORMAL)
            self.update_status("Recording", "orange")

    def run_recording(self):
        datetime_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cmd = [
            str(ffmpeg_path),
            '-y',  # Overwrite output files without asking
            '-f', 'mpegts',  # Input format
            '-i', 'udp://0.0.0.0:5006',  # Input URL (UDP stream)
            '-metadata', f'date={datetime_now}',  # Add current date and time as metadata
            str(self.recording_filename)  # Output file
        ]

        self.record_process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.record_process.wait()
        self.record_process = None
        self.update_button_states()
        self.update_play_button_state()  # Update play button state after recording
        
        if self.process:
            self.update_status("Receiving Stream", "green")
        else:
            self.update_status("Idle", "blue")

    def stop_recording(self):
        if self.record_process:
            try:
                logging.info("Sending 'q' to ffmpeg process to stop recording gracefully.")
                self.record_process.stdin.write(b'q')
                self.record_process.stdin.flush()
                stdout, stderr = self.record_process.communicate(timeout=10)
                logging.info(f"Recording stdout: {stdout.decode('utf-8')}")
                logging.info(f"Recording stderr: {stderr.decode('utf-8')}")
                logging.info("Recording process terminated gracefully.")
            except subprocess.TimeoutExpired:
                logging.warning("Timed out. Forcibly terminating the recording process.")
                self.terminate_process(self.record_process)
            except Exception as e:
                logging.error(f"Error terminating recording process: {e}")
            finally:
                self.record_process = None
                self.record_button.config(state=tk.NORMAL)
                self.stop_record_button.config(state=tk.DISABLED)
                self.update_play_button_state()  # Update play button state after stopping recording
                self.update_status("Idle", "blue")

        # Check if streaming process is alive and set the status accordingly
        if self.process and self.process.poll() is None:
            self.update_status("Receiving Stream", "green")
        else:
            self.update_status("Idle", "blue")

    def update_play_button_state(self):
        if os.path.exists(self.recording_filename):
            self.play_button.config(state=tk.NORMAL)
        else:
            self.play_button.config(state=tk.DISABLED)

    def check_playback_status(self):
        # Check if the process is still running
        if self.play_process and self.play_process.poll() is None:
            self.play_button.after(1000, self.check_playback_status)
        else:
            # If the process has finished, reset the button text
            self.play_button.config(text='Play Recording')

    def play_recording(self):
        if self.play_button.config('text')[-1] == 'Play Recording':
            # Change button text to 'Stop Playing'
            self.play_button.config(text='Stop Playing')

            # Start playing the recording
            if os.path.exists(self.recording_filename):
                self.play_process = subprocess.Popen([str(ffplay_path), '-nodisp', '-autoexit', str(self.recording_filename)],
                                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.play_button.after(1000, self.check_playback_status)

        else:
            # Change button text to 'Play Recording'
            self.play_button.config(text='Play Recording')

            # Stop playing the recording
            if self.play_process:
                self.play_process.terminate()
                self.play_process.wait()
                self.play_process = None

    def on_closing(self):
        self.stop_stream()
        self.stop_recording()
        self.stop_monitoring()
        # Wait for bitrate thread to finish
        if self.bitrate_thread and self.bitrate_thread.is_alive():
            self.bitrate_thread.join()  # Ensure the bitrate thread has fully terminated
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = FFplayGUI(root)
    root.mainloop()