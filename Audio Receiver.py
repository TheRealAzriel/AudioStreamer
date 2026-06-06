import tkinter as tk
from tkinter import messagebox
from pathlib import Path
import subprocess
import os
import sys
import time
import logging
import threading
import platform
import signal
import socket
from ctypes import POINTER, cast
import comtypes
from comtypes import CoInitialize
from comtypes import CoUninitialize
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from datetime import datetime

# Use _MEIPASS to correctly set the path when bundled with PyInstaller
if hasattr(sys, '_MEIPASS'):
    base_path = Path(sys._MEIPASS)
else:
    base_path = Path(__file__).parent.resolve()

# Define paths
script_dir = base_path
user_home_dir = Path.home()  # This gets the user's home directory
appdata_local_path = user_home_dir / 'AppData' / 'Local' / 'Audio Receiver'

# Icon path
icon_path = script_dir / 'icon' / 'icons8-stream-64.ico'

# Define log file path within AppData\Local
log_file_path = appdata_local_path / 'Audio_Receiver.log'

# Ensure the log file directory exists
log_file_path.parent.mkdir(parents=True, exist_ok=True)

# Set up logging to file
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(log_file_path)])

# Construct full paths to 'ffmpeg.exe', 'ffplay.exe' and 'ffprobe.exe' using pathlib
ffmpeg_path = script_dir / 'ffmpeg' / 'bin' / 'ffmpeg.exe'
ffplay_path = script_dir / 'ffmpeg' / 'bin' / 'ffplay.exe'
ffprobe_path = script_dir / 'ffmpeg' / 'bin' / 'ffprobe.exe'

# Log path information for debugging
logging.info("Application started")
logging.info(f"Base path: {base_path}")
logging.info(f"Script dir: {script_dir}")
logging.info(f"Looking for ffplay at: {ffplay_path}")
logging.info(f"ffplay.exe exists: {ffplay_path.exists()}")

# Validate critical paths exist
if not ffplay_path.exists():
    logging.error(f"CRITICAL: ffplay.exe not found at {ffplay_path}")
    # Try to find ffmpeg folder structure
    ffmpeg_dir = script_dir / 'ffmpeg'
    logging.info(f"ffmpeg directory exists: {ffmpeg_dir.exists()}")
    if ffmpeg_dir.exists():
        bin_dir = ffmpeg_dir / 'bin'
        logging.info(f"bin directory exists: {bin_dir.exists()}")
        if bin_dir.exists():
            try:
                bin_contents = list(bin_dir.iterdir())
                logging.info(f"Contents of bin directory: {[f.name for f in bin_contents]}")
            except Exception as e:
                logging.error(f"Error listing bin directory: {e}")

if not ffmpeg_path.exists():
    logging.error(f"CRITICAL: ffmpeg.exe not found at {ffmpeg_path}")

# Function to terminate processes by name
def terminate_process(process_name):
    if platform.system() == "Windows":
        commands = ['taskkill', '/F', '/IM', f'{process_name}.exe', '/T']
    else:
        commands = ['pkill', '-f', process_name]

    #logging.info(f"Attempting to terminate {process_name} processes.")
    try:
        subprocess.run(commands, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=CREATE_NO_WINDOW)
        #logging.info(f"Successfully terminated {process_name} processes.")
    except Exception as e:
        logging.error(f"Error terminating {process_name} processes: {e}")

# Define CREATE_NO_WINDOW for Windows
CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0

class FFplayGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Audio Receiver")
        self.root.geometry("400x475")
        self.primary_button_font = ("Arial", 10, "bold")
        self.secondary_button_font = ("Arial", 9, "bold")
        # Window is already withdrawn from main block
        # Using default system background color (like Audio Streamer)

        # Set the icon for the application window and taskbar
        try:
            logging.debug('Setting icon from path: %s', icon_path)
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
            else:
                logging.error('Icon file not found: %s', icon_path)
        except Exception as e:
            logging.error('Failed to set icon: %s', e)

        #self.volume = None
        self.update_volume_control()  # Initialize volume control

        self.process = None
        self.stream_thread = None
        self.play_process = None
        self.is_muted = False
        self.is_recording_mode = False
        self.running = True  # Flag to control monitoring thread
        self.connection_status = "idle"  # Track connection health

        self.recordings_dir = script_dir / 'recordings'
        self.recordings_dir.mkdir(exist_ok=True)

        # Generate timestamped filename to avoid overwrites
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.recording_filename = self.recordings_dir / f"recording_{timestamp}.mp3"

        self.local_ip = self.get_local_ip()
        
        # Remove bitrate monitoring - not needed in single-stream mode

        volume_frame = tk.Frame(root, bg="#e8e8e8", bd=2, relief="solid")
        volume_frame.place(x=20, y=10, width=90, height=280)

        self.volume_slider = tk.Scale(volume_frame, from_=100, to=0, orient=tk.VERTICAL, command=self.set_volume, bg="#e8e8e8", troughcolor="#d0d0d0", activebackground="#4CAF50")
        self.volume_slider.set(self.get_current_volume())
        self.volume_slider.place(x=20, y=20, height=220)

        self.volume_slider.bind("<MouseWheel>", self.on_mouse_wheel)
        self.volume_slider.bind("<Button-4>", self.on_mouse_wheel)
        self.volume_slider.bind("<Button-5>", self.on_mouse_wheel)

        self.volume_label = tk.Label(volume_frame, text="Volume", bg="#e8e8e8")
        self.volume_label.place(x=20, y=250)

        # Create a 1x1 transparent pixel for perfect button sizing
        self.pixel_virtual = tk.PhotoImage(width=1, height=1)

        # Mute button - Fixed for perfect centering and alignment
        self.mute_button = tk.Button(
            root, 
            text="🔊", 
            image=self.pixel_virtual, 
            compound="center",        
            command=self.mute, 
            width=40,                 # Slightly reduced to prevent "squishing" the text
            height=40,                
            bg="lightgreen", 
            relief="raised", 
            bd=2,
            highlightthickness=0,
            takefocus=0,
            padx=0,                   # Remove internal horizontal padding
            pady=0,                   # Remove internal vertical padding
            font=("Segoe UI Symbol", 12) # Better font for emojis on Windows
        )
        self.mute_button.place(x=42, y=300) # Adjusted x to center better under volume frame
        self.add_hover(self.mute_button, "#32CD32", "lightgreen")  # Much more vibrant lime green for hover

        self.mute_label = tk.Label(root, text="Mute All", bg="#f0f0f0", font=("Arial", 9))
        self.mute_label.place(x=45, y=345) # Lowered slightly to give the button breathing room

        stream_frame = tk.Frame(root, bg="#e8e8e8", bd=2, relief="solid")
        stream_frame.place(x=150, y=10, width=225, height=280)

        self.start_button = tk.Button(stream_frame, text="Receive Stream", command=self.start_stream, width=20, height=2, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"), relief="flat", bd=1, disabledforeground="#111111")
        self.start_button.place(x=25, y=25)
        self.style_button(self.start_button, normal_color="#4CAF50", hover_color="#45a049", font=self.primary_button_font)
        self.add_hover(self.start_button, "#45a049", "#4CAF50")
        
        self.stop_button = tk.Button(stream_frame, text="Stop Receiving", command=self.stop_stream, state=tk.DISABLED, width=20, height=2, bg="#f44336", fg="white", font=("Arial", 10, "bold"), relief="flat", bd=1, disabledforeground="#111111")
        self.stop_button.place(x=25, y=115)
        self.style_button(self.stop_button, normal_color="#f44336", hover_color="#d32f2f", font=self.primary_button_font)
        self.add_hover(self.stop_button, "#d32f2f", "#f44336")

        self.record_button = tk.Button(stream_frame, text="Receive & Record", command=self.start_recording, width=20, height=2, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"), relief="flat", bd=1, disabledforeground="#111111")
        self.record_button.place(x=25, y=205)
        self.style_button(self.record_button, normal_color="#4CAF50", hover_color="#45a049", font=self.primary_button_font)
        self.add_hover(self.record_button, "#45a049", "#4CAF50")

        # Create a dedicated container for status with health indicator
        self.status_container = tk.Frame(root, bg="#f0f0f0") # Match root bg
        self.status_container.place(x=150, y=300, width=225) # Span the width of the buttons above
        
        # Stream health indicator canvas
        self.health_canvas = tk.Canvas(self.status_container, width=16, height=16, bg="#f0f0f0", highlightthickness=0)
        self.health_canvas.pack(side=tk.TOP, pady=(5, 0))
        self.health_indicator = self.health_canvas.create_oval(2, 2, 14, 14, fill="#cccccc", outline="#999999")
        
        # Header: Centered in the container
        self.status_title = tk.Label(self.status_container, text="Status:", font=("Arial", 12, "bold"), bg="#f0f0f0")
        self.status_title.pack(side=tk.TOP, fill=tk.X)
        
        # Message: Centered in the container
        self.status_message = tk.Label(self.status_container, text="Idle", font=("Arial", 14, "bold"), fg="blue", bg="#f0f0f0")
        self.status_message.pack(side=tk.TOP, fill=tk.X)

        # Recording playback controls
        self.play_button = tk.Button(root, text="Play Recording", command=self.play_recording, 
                                   state=tk.DISABLED, width=12, height=2, 
                                   bg="#2196F3", fg="white", font=("Arial", 9, "bold"),
                                   relief="flat", bd=1, disabledforeground="#111111")
        self.play_button.place(x=80, y=390)      # Recentered
        self.style_button(self.play_button, normal_color="#2196F3", hover_color="#1976D2", font=self.secondary_button_font)
        self.add_hover(self.play_button, "#1976D2", "#2196F3")
        
        self.stop_play_button = tk.Button(root, text="Stop Playing", command=self.stop_playing,
                                         state=tk.DISABLED, width=12, height=2,
                                         bg="#f44336", fg="white", font=("Arial", 9, "bold"),
                                         relief="flat", bd=1, disabledforeground="#111111")
        self.stop_play_button.place(x=230, y=390) # Recentered with proper spacing
        self.style_button(self.stop_play_button, normal_color="#f44336", hover_color="#d32f2f", font=self.secondary_button_font)
        self.add_hover(self.stop_play_button, "#d32f2f", "#f44336")
        self.update_button_states()
        self.update_play_button_state()  # Initial update based on the presence of the recording file

        self.ip_label = tk.Label(root, text=f"Local IP: {self.local_ip}")
        self.ip_label.place(x=125, y=450)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.monitor_thread = threading.Thread(target=self.monitor_audio_device_changes, daemon=True)
        self.monitor_thread.start()
        
        # Show window now that all elements are positioned
        self.root.deiconify()

    def style_button(self, button, normal_color, hover_color, font):
        """Apply a consistent raised style with readable disabled text."""
        button.normal_color = normal_color
        button.hover_color = hover_color
        button.default_text_color = "white"
        button.disabled_bg = "#d7d7d7"
        button.disabled_text = "#666666"
        button.config(
            bg=normal_color,
            fg="white",
            font=font,
            activebackground=hover_color,
            activeforeground="white",
            disabledforeground=button.disabled_text,
            relief="raised",
            bd=2,
            cursor="hand2"
        )

    def set_button_enabled(self, button, enabled):
        button.config(
            state=tk.NORMAL if enabled else tk.DISABLED,
            bg=button.normal_color if enabled else button.disabled_bg,
            fg=button.default_text_color if enabled else button.disabled_text,
            activebackground=button.hover_color if enabled else button.disabled_bg,
            relief="raised",
            cursor="hand2" if enabled else "arrow"
        )

    def add_hover(self, button, hover_color, normal_color):
        """Add hover and press effects for stronger visual feedback."""
        def on_enter(event):
            if button['state'] != 'disabled':
                button.config(bg=hover_color)
        
        def on_leave(event):
            if button['state'] != 'disabled':
                button.config(bg=normal_color, relief="raised")

        def on_press(event):
            if button['state'] != 'disabled':
                button.config(relief="sunken")

        def on_release(event):
            if button['state'] != 'disabled':
                button.config(relief="raised")
        
        button.bind("<Enter>", on_enter)
        button.bind("<Leave>", on_leave)
        button.bind("<ButtonPress-1>", on_press)
        button.bind("<ButtonRelease-1>", on_release)

    def update_volume_control(self):
        # Support both legacy and newer pycaw AudioDevice APIs.
        devices = AudioUtilities.GetSpeakers()
        endpoint_volume = getattr(devices, "EndpointVolume", None)
        if endpoint_volume is not None:
            self.volume = endpoint_volume
            return

        interface = devices.Activate(
            IAudioEndpointVolume._iid_, comtypes.CLSCTX_INPROC_SERVER, None)
        self.volume = cast(interface, POINTER(IAudioEndpointVolume))

    def monitor_audio_device_changes(self):
        CoInitialize()
        try:
            # Get the ID once at the start
            devices = AudioUtilities.GetSpeakers()
            current_device = devices.GetId()
            
            while self.running:
                # Instead of re-querying the whole object, 
                # let's just wait longer between checks.
                time.sleep(5)  # 5 seconds is plenty for hardware monitoring
                
                try:
                    # Re-check the ID
                    new_device = AudioUtilities.GetSpeakers().GetId()
                    if new_device != current_device:
                        logging.info(f"Audio device changed to: {new_device}")
                        current_device = new_device
                        self.update_volume_control()
                        self.root.after(0, lambda: self.volume_slider.set(self.get_current_volume()))
                        self.root.after(0, lambda: self.mute_button.config(text="🔊" if not self.is_muted else "🔇", 
                                               bg="lightgreen" if not self.is_muted else "lightcoral"))
                except Exception as e:
                    # If a device is unplugged, GetSpeakers() might throw an error
                    # We catch it here so the thread doesn't die.
                    logging.error(f"Monitoring error: {e}")
                    
        finally:
            CoUninitialize()

    def start_monitoring(self):
        # Simplified monitoring - no bitrate display needed
        self.set_button_enabled(self.start_button, False)
        self.set_button_enabled(self.stop_button, True)
        logging.info("Stream monitoring started")

    def stop_monitoring(self):
        # Clean monitoring stop
        logging.info("Stream monitoring stopped")

    # Removed update_bitrate_label method - no longer needed

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
        if self.volume:
            current_volume = self.volume.GetMasterVolumeLevelScalar()
            return int(current_volume * 100)
        return 0

    def start_stream(self):
        logging.info("Starting TCP stream reception...")
        if self.process is None:
            self.is_recording_mode = False
            self.stream_thread = threading.Thread(target=self.run_receiver, daemon=True)
            self.stream_thread.start()
            self.set_button_enabled(self.start_button, False)
            self.set_button_enabled(self.stop_button, True)
            self.set_button_enabled(self.record_button, False)
            self.update_status("Receiving Stream", "green")
            self.start_monitoring()
            logging.info("TCP stream reception started successfully")

    def start_recording(self):
        logging.info("Starting TCP stream reception with recording...")
        if self.process is None:
            self.is_recording_mode = True
            self.stream_thread = threading.Thread(target=self.run_receiver, daemon=True)
            self.stream_thread.start()
            self.set_button_enabled(self.start_button, False)
            self.set_button_enabled(self.stop_button, True)
            self.set_button_enabled(self.record_button, False)
            self.update_status("Receiving & Recording", "orange")
            self.start_monitoring()
            logging.info("TCP stream reception with recording started successfully")

    def run_receiver(self):
        if self.is_recording_mode:
            logging.info("Starting ffmpeg TCP listener with recording on port 6005...")
        else:
            logging.info("Starting ffplay TCP listener on port 6005...")
        
        # Determine which executable and command to use
        if self.is_recording_mode:
            # Use ffmpeg with tee muxer for simultaneous playback and recording
            if not ffmpeg_path.exists():
                logging.error(f"ffmpeg.exe not found at {ffmpeg_path}")
                self.root.after(0, self.update_button_states)
                self.root.after(0, self.update_status, "Error: ffmpeg not found", "red")
                return
                
            exe_path = str(ffmpeg_path.resolve())
            logging.info(f"Using ffmpeg executable for recording at: {exe_path}")
            
            # FFmpeg command with dual output for Windows (DirectSound speakers + MP3 file)
            cmd = [
                exe_path,
                '-hide_banner', '-loglevel', 'error',
                '-f', 'mpegts',
                '-i', 'tcp://0.0.0.0:6005?listen=1&tcp_nodelay=1',
                # Output 1: To speakers via DirectSound
                '-f', 'wav', '-acodec', 'pcm_s16le', 'pipe:1',
                # Output 2: To MP3 file 
                '-c:a', 'libmp3lame', '-b:a', '192k', str(self.recording_filename)
            ]
        else:
            # Use ffplay for playback only (existing logic)
            if not ffplay_path.exists():
                logging.error(f"ffplay.exe not found at {ffplay_path}")
                self.root.after(0, self.update_button_states)
                self.root.after(0, self.update_status, "Error: ffplay not found", "red")
                return
                
            exe_path = str(ffplay_path.resolve())
            logging.info(f"Using ffplay executable at: {exe_path}")
            
            # Optimized ffplay command for low-latency TCP streaming
            cmd = [
                exe_path,
                '-nodisp', 
                '-autoexit',
                '-loglevel', 'quiet',     # Silence all console output
                '-nostats',               # Disable progress printouts in the pipe
                '-fflags', 'nobuffer+fastseek', 
                '-flags', 'low_delay', 
                '-strict', 'experimental',
                '-infbuf',
                '-probesize', '32',
                '-analyzeduration', '0', 
                '-af', 'aresample=async=1',
                '-f', 'mpegts', 
                'tcp://0.0.0.0:6005?listen=1&tcp_nodelay=1'
            ]
        
        logging.info(f"Command: {' '.join(cmd)}")
        
        try:
            if self.is_recording_mode:
                # For recording mode, ffmpeg outputs to both speakers and file
                audio_cmd = [str(ffplay_path.resolve()), '-nodisp', '-autoexit', '-f', 'wav', '-i', 'pipe:0']
                
                # Start ffmpeg process with dual outputs
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    creationflags=0x08000000 | 0x00000008  # Combine No Window and Detached Process
                )
                
                # Start ffplay to handle the piped audio for speakers
                self.audio_process = subprocess.Popen(
                    audio_cmd,
                    stdin=self.process.stdout,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=0x08000000 | 0x00000008  # Combine No Window and Detached Process
                )
                
                # Close the stdout pipe in parent to avoid deadlock
                self.process.stdout.close()
                
                logging.info("ffmpeg TCP listener active on port 6005 with recording...")
                # Wait for ffmpeg process (it will handle both outputs)
                self.process.wait()
            else:
                # Standard ffplay process for playback only
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=0x08000000 | 0x00000008  # Combine No Window and Detached Process
                )
                logging.info("ffplay TCP listener active on port 6005, waiting for connections...")
                # Wait for process completion
                self.process.wait()
            
        except Exception as e:
            logging.error(f"Failed to start TCP listener: {str(e)}")
        finally:
            logging.info("TCP listener stopped")
            # Cleanup any remaining processes
            if hasattr(self, 'audio_process') and self.audio_process:
                try:
                    self.audio_process.terminate()
                    self.audio_process.wait(timeout=2)
                except:
                    try:
                        self.audio_process.kill()
                    except:
                        pass
                self.audio_process = None
            
            self.process = None
            if self.root.winfo_exists():
                self.root.after(0, self.update_button_states)
                self.root.after(0, self.update_status, "Idle", "blue")
                if self.is_recording_mode:
                    self.root.after(0, self.update_play_button_state)

    def stop_stream(self):
        if self.process:
            def terminate_process_thread():
                try:
                    # Terminate both processes if in recording mode
                    if hasattr(self, 'audio_process') and self.audio_process:
                        try:
                            self.audio_process.terminate()
                            self.audio_process.wait(timeout=2)
                        except:
                            try:
                                self.audio_process.kill()
                            except:
                                pass
                        self.audio_process = None
                    
                    # Terminate main process
                    if platform.system() == "Windows":
                        self.process.terminate()
                        try:
                            self.process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            self.process.kill()
                    else:
                        os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                    
                    terminate_process("ffprobe")  # Cleanup any ffprobe processes
                except Exception as e:
                    logging.error(f"Error terminating stream process: {e}")
                finally:
                    self.process = None
                    self.update_stop_stream_ui()
                    self.stop_monitoring()

            terminate_thread = threading.Thread(target=terminate_process_thread, daemon=True)
            terminate_thread.start()
        else:
            self.update_stop_stream_ui()
            self.stop_monitoring()
    def update_stop_stream_ui(self):
        self.update_button_states()
        self.update_status("Idle", "blue")

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
            self.mute_button.config(text="🔇", bg="lightcoral")
            self.is_muted = True
            # Change volume slider trough to red when muted
            self.volume_slider.config(troughcolor="#ffcccb")
            # Update hover effect for muted state
            self.add_hover(self.mute_button, "#DC143C", "lightcoral")  # Much more vibrant crimson for hover
            self.update_status("Muted", "red")
        else:
            self.volume.SetMute(0, None)
            self.mute_button.config(text="🔊", bg="lightgreen")
            self.is_muted = False
            # Restore normal volume slider color
            self.volume_slider.config(troughcolor="#d0d0d0")
            # Update hover effect for unmuted state  
            self.add_hover(self.mute_button, "#32CD32", "lightgreen")  # Much more vibrant lime green for hover
            if self.process is not None:
                self.update_status("Receiving Stream", "green")
            else:
                self.update_status("Idle", "blue")

    def update_status(self, text, color):
        if self.root.winfo_exists():
            self.status_message.config(text=text, fg=color)
            # Update health indicator based on status
            if text == "Idle":
                self.connection_status = "idle"
                self.health_canvas.itemconfig(self.health_indicator, fill="#cccccc", outline="#999999")
            elif "Receiving" in text:
                self.connection_status = "connected"
                self.health_canvas.itemconfig(self.health_indicator, fill="#4CAF50", outline="#2E7D32")
            elif "Error" in text:
                self.connection_status = "error"
                self.health_canvas.itemconfig(self.health_indicator, fill="#f44336", outline="#d32f2f")
            elif "Muted" in text:
                self.connection_status = "muted"
                self.health_canvas.itemconfig(self.health_indicator, fill="#ff9800", outline="#f57c00")
            # No more coordinate math needed here!

    def update_button_states(self):
        if self.root.winfo_exists():
            if self.process is None:
                self.set_button_enabled(self.start_button, True)
                self.set_button_enabled(self.stop_button, False)
                self.set_button_enabled(self.record_button, True)
            else:
                self.set_button_enabled(self.start_button, False)
                self.set_button_enabled(self.stop_button, True)
                self.set_button_enabled(self.record_button, False)

    def update_play_button_state(self):
        if os.path.exists(self.recording_filename):
            self.set_button_enabled(self.play_button, True)
        else:
            self.set_button_enabled(self.play_button, False)
        # Always keep stop button disabled when not playing
        self.set_button_enabled(self.stop_play_button, False)

    def check_playback_status(self):
        # Check if the process is still running
        if self.play_process and self.play_process.poll() is None:
            self.play_button.after(1000, self.check_playback_status)
        else:
            # If the process has finished, reset the button states
            self.set_button_enabled(self.play_button, True)
            self.set_button_enabled(self.stop_play_button, False)
            self.play_process = None

    def play_recording(self):
        # Start playing the recording
        if os.path.exists(self.recording_filename):
            self.play_process = subprocess.Popen([str(ffplay_path), '-nodisp', '-autoexit', '-loglevel', 'quiet', str(self.recording_filename)],
                                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                                 creationflags=0x08000000 | 0x00000008)
            # Update button states
            self.set_button_enabled(self.play_button, False)
            self.set_button_enabled(self.stop_play_button, True)
            # Start monitoring playback
            self.play_button.after(1000, self.check_playback_status)
    
    def stop_playing(self):
        # Stop playing the recording
        if self.play_process:
            try:
                self.play_process.terminate()
                self.play_process.wait(timeout=2)
            except:
                try:
                    self.play_process.kill()
                except:
                    pass
            finally:
                self.play_process = None
                # Update button states
                self.set_button_enabled(self.play_button, True)
                self.set_button_enabled(self.stop_play_button, False)

    def on_closing(self):
        try:
            self.root.withdraw() 
            
            # Stop the monitoring loop flag
            self.running = False 
            
            # Clean up FFmpeg/FFplay
            if platform.system() == "Windows":
                subprocess.run(['taskkill', '/F', '/IM', 'ffmpeg.exe', '/T'], creationflags=0x08000000 | 0x00000008)
                subprocess.run(['taskkill', '/F', '/IM', 'ffplay.exe', '/T'], creationflags=0x08000000 | 0x00000008)
                
            # Give COM 200ms to uninitialize properly
            time.sleep(0.2) 
            
        except Exception as e:
            logging.error(f"Error during fast shutdown: {e}")
        finally:
            self.root.destroy()
            os._exit(0)

if __name__ == "__main__":
    root = tk.Tk()
    # HIDE IMMEDIATELY - Do this before setting icons or initializing the class
    root.withdraw() 
    
    try:
        logging.debug('Setting main window icon from path: %s', icon_path)
        if icon_path.exists():
            root.iconbitmap(str(icon_path))
        else:
            logging.error('Icon file not found in main: %s', icon_path)
    except Exception as e:
        logging.error('Failed to set main window icon: %s', e)
        
    app = FFplayGUI(root)
    root.mainloop()