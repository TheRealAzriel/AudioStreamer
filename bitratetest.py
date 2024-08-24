import tkinter as tk
import subprocess
import threading
import time
import sys

def get_bitrate(stream_url):
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=bit_rate', '-of',
             'default=noprint_wrappers=1:nokey=1', stream_url],
            capture_output=True,
            text=True,
            check=True
        )
        bitrate = result.stdout.strip()
        if bitrate:
            print(f"Bitrate: {bitrate} bits/s")
            return bitrate
        else:
            print("Bitrate could not be determined. The stream might be empty or there was an issue with the connection.")
            return "N/A"
        sys.stdout.flush()
    except subprocess.CalledProcessError as e:
        print(f"An error occurred: {e}")
        sys.stdout.flush()
        return "N/A"

class BitrateMonitor:
    def __init__(self, root):
        self.root = root
        self.root.title("Bitrate Monitor")
        self.root.geometry("300x200")

        self.bitrate_label = tk.Label(root, text="Bitrate: N/A", fg="blue", bg="white", font=("Arial", 14))
        self.bitrate_label.pack(pady=20)

        self.start_button = tk.Button(root, text="Start Monitoring", command=self.start_monitoring, width=15, height=2)
        self.start_button.pack(pady=10)

        self.stop_button = tk.Button(root, text="Stop Monitoring", command=self.stop_monitoring, state=tk.DISABLED, width=15, height=2)
        self.stop_button.pack(pady=10)

        self.is_monitoring = False
        self.bitrate_thread = None

    def start_monitoring(self):
        self.is_monitoring = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.bitrate_thread = threading.Thread(target=self.update_bitrate_loop)
        self.bitrate_thread.start()

    def stop_monitoring(self):
        self.is_monitoring = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.update_bitrate_label("Bitrate: N/A")

    def update_bitrate_loop(self):
        stream_url = 'udp://localhost:5004'
        while self.is_monitoring:
            bitrate = get_bitrate(stream_url)
            self.update_bitrate_label(f"Bitrate: {bitrate} bits/s")
            time.sleep(5)

    def update_bitrate_label(self, text):
        self.bitrate_label.config(text=text)

    def on_closing(self):
        self.stop_monitoring()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = BitrateMonitor(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()