import tkinter as tk
from tkinter import messagebox
from pathlib import Path
import subprocess
import platform
import pyaudio
import logging
import socket
import threading

# Initialize logging
logging.basicConfig(filename='audio_streamer.log', level=logging.DEBUG, 
                    format='%(asctime)s %(levelname)s:%(message)s')

# Define script path
script_dir = Path(__file__).parent.resolve()

# Set paths
ffmpeg_path = script_dir / 'ffmpeg' / 'bin' / 'ffmpeg.exe'
executable_path = script_dir / "SetPlayBack" / "SetPlayBack.exe"

class FFMPEGSenderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("FFMPEG Stream Sender")
        self.root.geometry("400x200")
        
        self.ip_label = tk.Label(root, text="Receiver IP:", font=("Arial", 12))
        self.ip_label.place(x=20, y=30)
        self.ip_entry = tk.Entry(root, font=("Arial", 12))
        self.ip_entry.place(x=140, y=30, width=200)
        self.start_button = tk.Button(root, text="Start Stream", command=self.start_stream, width=15, height=2, relief="raised", bd=2)
        self.start_button.place(x=50, y=100)
        self.stop_button = tk.Button(root, text="Stop Stream", command=self.stop_stream, width=15, height=2, relief="raised", bd=2)
        self.stop_button.place(x=230, y=100)
        self.stop_button.config(state=tk.DISABLED)

        self.process = None
        self.output_thread = None
        self.error_thread = None
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

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
        
    def start_stream(self):
        logging.debug('Starting stream...')
        ip_address = self.ip_entry.get()
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
                '-f', 'mpegts', f'udp://{ip_address}:5005'
            ]
            logging.debug('Running ffmpeg command: %s', ' '.join(command))
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            self.output_thread = threading.Thread(target=self.handle_output, args=(self.process.stdout,))
            self.output_thread.start()

            self.error_thread = threading.Thread(target=self.handle_error, args=(self.process.stderr,))
            self.error_thread.start()

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