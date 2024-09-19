import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
import subprocess
import platform
import pyaudio
import logging
import socket
import threading
import json

# Initialize logging
logging.basicConfig(filename='audio_streamer.log', level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s:%(message)s')

# Use _MEIPASS to correctly set the path when bundled with PyInstaller
if hasattr(sys, '_MEIPASS'):
    # Running in a PyInstaller bundle
    base_path = Path(sys._MEIPASS)
else:
    # Running in a normal Python environment
    base_path = Path(__file__).parent.resolve()

# Define script path
script_dir = base_path

# Set paths
ffmpeg_path = script_dir / 'ffmpeg' / 'bin' / 'ffmpeg.exe'
executable_path = script_dir / 'SetPlayBack' / 'SetPlayBack.exe'
icon_path = script_dir / 'icon' / 'icons8-stream-64.ico'
history_file = script_dir / 'ip_history.json'

# Load IP history
ip_history = []

def load_ip_history():
    global ip_history
    if history_file.exists():
        with open(history_file, 'r') as file:
            ip_history = json.load(file)

def save_ip_history():
    with open(history_file, 'w') as file:
        json.dump(ip_history, file)

class FFMPEGSenderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Audio Streamer")
        self.root.geometry("400x250")

        self.ip_label = tk.Label(root, text="Receiver IP:", font=("Arial", 12))
        self.ip_label.place(x=20, y=30)

        self.ip_entry = tk.Entry(root, font=("Arial", 12))
        self.ip_entry.place(x=140, y=30, width=200)

        self.ip_var = tk.StringVar()
        self.ip_dropdown = ttk.Combobox(root, textvariable=self.ip_var, font=("Arial", 12), postcommand=self.update_ip_dropdown)
        self.ip_dropdown.place(x=100, y=110, width=240, height=25)
        self.ip_dropdown.bind("<<ComboboxSelected>>", self.on_ip_selected)

        self.name_label = tk.Label(root, text="Name:", font=("Arial", 12))
        self.name_label.place(x=20, y=70)
        self.name_entry = tk.Entry(root, font=("Arial", 12))
        self.name_entry.place(x=140, y=70, width=200)

        self.start_button = tk.Button(root, text="Start Stream", command=self.start_stream, width=15, height=2, relief="raised", bd=2)
        self.start_button.place(x=50, y=180)
        self.stop_button = tk.Button(root, text="Stop Stream", command=self.stop_stream, width=15, height=2, relief="raised", bd=2)
        self.stop_button.place(x=230, y=180)
        self.stop_button.config(state=tk.DISABLED)

        self.process = None
        self.output_thread = None
        self.error_thread = None
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Load IP history on startup
        load_ip_history()

    def update_ip_dropdown(self):
        self.ip_dropdown['values'] = [f"{name}: {ip}" for ip, name in ip_history]

    def on_ip_selected(self, event):
        selected_text = self.ip_dropdown.get()
        name, ip = selected_text.split(": ")
        self.ip_entry.delete(0, tk.END)
        self.ip_entry.insert(0, ip)
        self.name_entry.delete(0, tk.END)
        self.name_entry.insert(0, name)

    def check_audio_device(self, device_name):
        logging.debug('Checking for audio device: %s', device_name)
        p = pyaudio.PyAudio()
        device_count = p.get_device_count()
        for i in range(device_count):
            device_info = p.get_device_info_by_index(i)
            if device_name in device_info.get('name', ''):
                p.terminate()
                logging.debug('Audio device found: %s', device_name)
                return True
        p.terminate()
        logging.error('Audio device not found: %s', device_name)
        return False

    def handle_output(self, pipe):
        for line in iter(pipe.readline, b''):
            logging.debug('[FFmpeg stdout] %s', line.decode().strip())
        pipe.close()

    def handle_error(self, pipe):
        for line in iter(pipe.readline, b''):
            logging.error('[FFmpeg stderr] %s', line.decode().strip())
        pipe.close()

    def add_ip_to_history(self, ip, name):
        # Check for an existing entry and update it if found
        for index, (existing_ip, existing_name) in enumerate(ip_history):
            if existing_ip == ip:
                ip_history[index] = (ip, name)
                break
        else:
            # Add new entry if not found
            ip_history.insert(0, (ip, name))
            if len(ip_history) > 10:
                ip_history.pop()

        save_ip_history()

    def start_stream(self):
        logging.debug('Starting stream...')

        # Kill any running ffmpeg processes
        if platform.system() == "Windows":
            kill_command = ["taskkill", "/IM", "ffmpeg.exe", "/F"]
        else:
            kill_command = ["pkill", "-f", "ffmpeg"]

        try:
            logging.debug('Terminating any existing ffmpeg processes')
            subprocess.run(kill_command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
            logging.debug('ffmpeg processes terminated successfully or no ffmpeg process found')
        except subprocess.CalledProcessError as e:
            # Ignore error if no such process is found
            if "not found" in str(e.stderr).lower():
                logging.debug('No existing ffmpeg processes found to terminate.')
            else:
                logging.error('Error occurred while attempting to terminate ffmpeg processes: %s', e)

        ip_address = self.ip_entry.get()
        name = self.name_entry.get()
        try:
            socket.inet_aton(ip_address)
        except socket.error:
            logging.error('Invalid IP address format')
            messagebox.showerror("Error", "Invalid IP address format.")
            return

        audio_device = "CABLE Output (VB-Audio Virtual Cable)"
        if not self.check_audio_device(audio_device):
            messagebox.showerror("Error", f"Audio device '{audio_device}' not found.")
            return

        if self.process is None:
            # Verify that SetPlayBack.exe exists
            if not executable_path.exists():
                logging.error('SetPlayBack.exe not found at path: %s', executable_path)
                messagebox.showerror("Error", f"SetPlayBack.exe not found at path:\n{executable_path}")
                return

            # Set the working directory to where SetPlayBack.exe is located
            playback_work_dir = executable_path.parent

            # Call SetPlayBack.exe to configure the audio environment
            try:
                logging.debug('Running SetPlayBack.exe to configure the audio environment')
                subprocess.run([str(executable_path)], cwd=playback_work_dir, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
                logging.debug('SetPlayBack.exe executed successfully')
            except subprocess.CalledProcessError as e:
                logging.error('Failed to execute SetPlayBack.exe: %s', e)
                messagebox.showerror("Error", "Failed to configure audio environment.")
                return

            command = [
                str(ffmpeg_path),
                '-fflags', 'nobuffer',
                '-f', 'dshow',
                '-i', f'audio={audio_device}',
                '-probesize', '32',
                '-analyzeduration', '0',
                '-bufsize', '1000k',
                '-acodec', 'aac',
                '-b:a', '192k',
                '-fflags', '+genpts+discardcorrupt',
                '-flags', '+global_header+low_delay',
                '-f', 'mpegts', f'udp://{ip_address}:5004',
                '-f', 'mpegts', f'udp://{ip_address}:5005',
                '-f', 'mpegts', f'udp://{ip_address}:5006'
            ]
            logging.debug('Running ffmpeg command: %s', ' '.join(command))
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)

            self.output_thread = threading.Thread(target=self.handle_output, args=(self.process.stdout,))
            self.output_thread.start()

            self.error_thread = threading.Thread(target=self.handle_error, args=(self.process.stderr,))
            self.error_thread.start()

            self.add_ip_to_history(ip_address, name)
            self.update_ip_dropdown()

            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            logging.debug('Stream started successfully')

    def stop_stream(self):
        logging.debug('Stopping stream...')
        if self.process:
            self.process.terminate()
            self.process.wait()
            self.process = None
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            logging.debug('Stream stopped successfully')

    def on_closing(self):
        logging.debug('Closing application')
        self.stop_stream()
        self.root.destroy()

if __name__ == "__main__":
    logging.debug('Starting Audio Streamer application')
    root = tk.Tk()
    app = FFMPEGSenderGUI(root)
    root.mainloop()
    logging.debug('Audio Streamer application closed')