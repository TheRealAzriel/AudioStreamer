import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
import subprocess
import platform
import logging
import socket
import threading
import json
import os
import ctypes
from ctypes import POINTER, cast
import comtypes
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from datetime import datetime

# Use _MEIPASS to correctly set the path when bundled with PyInstaller
if hasattr(sys, '_MEIPASS'):
    # Running in a PyInstaller bundle
    base_path = Path(sys._MEIPASS)
else:
    # Running in a normal Python environment
    base_path = Path(__file__).parent.resolve()


# Define script path
script_dir = base_path
user_home_dir = Path.home()  # This gets the user's home directory
appdata_local_path = user_home_dir / 'AppData' / 'Local' / 'Audio Streamer'

# Define log file path within AppData\Local
log_file_path = appdata_local_path / 'Audio_Streamer.log'

# Ensure the log file directory exists
log_file_path.parent.mkdir(parents=True, exist_ok=True)

# Initialize logging correctly to the path in appdata_local_path
logging.basicConfig(filename=log_file_path, level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s:%(message)s')

logging.debug('Starting App...')

# Set paths
ffmpeg_path = script_dir / 'ffmpeg' / 'bin' / 'ffmpeg.exe'
executable_path = script_dir / 'SetPlayBack' / 'SetPlayBack.exe'
icon_path = script_dir / 'icon' / 'icons8-stream-64.ico'
history_file = script_dir / 'ip_history.json'
vb_cable_dir = script_dir / 'VBCABLE_Driver_Pack43'

# Log path information for debugging
logging.debug(f"Base path: {script_dir}")
logging.debug(f"Looking for ffmpeg at: {ffmpeg_path}")
logging.debug(f"ffmpeg.exe exists: {ffmpeg_path.exists()}")
logging.debug(f"SetPlayback.exe exists: {executable_path.exists()}")

# Validate critical paths exist
if not ffmpeg_path.exists():
    logging.error(f"CRITICAL: ffmpeg.exe not found at {ffmpeg_path}")
    # Try to find ffmpeg folder structure
    ffmpeg_dir = script_dir / 'ffmpeg'
    logging.debug(f"ffmpeg directory exists: {ffmpeg_dir.exists()}")
    if ffmpeg_dir.exists():
        bin_dir = ffmpeg_dir / 'bin'
        logging.debug(f"bin directory exists: {bin_dir.exists()}")
        if bin_dir.exists():
            try:
                bin_contents = list(bin_dir.iterdir())
                logging.debug(f"Contents of bin directory: {[f.name for f in bin_contents]}")
            except Exception as e:
                logging.error(f"Error listing bin directory: {e}")

vb_cable_path_x64 = vb_cable_dir / 'VBCABLE_Setup_x64.exe'
vb_cable_path_x86 = vb_cable_dir / 'VBCABLE_Setup.exe'

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

# Duplicate _MEIPASS logic removed - already defined above

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def install_vb_cable():
    # Determine the system architecture
    bitness = platform.architecture()[0]

    if bitness == "64bit":
        installer_path = vb_cable_path_x64
    else:
        installer_path = vb_cable_path_x86

    if not installer_path.exists():
        messagebox.showerror("Error", "VB-CABLE installer not found. Cannot proceed with installation.")
        return False

    logging.debug('Running VB-CABLE installer as admin: %s', installer_path)
    try:
        if platform.system() == "Windows":
            # Elevate privileges and run the installer
            run_command = [
                'powershell',
                '-NoProfile',
                '-ExecutionPolicy', 'Bypass',
                '-Command', f"Start-Process cmd -ArgumentList '/c \"{str(installer_path)}\"' -Verb runas -Wait"
            ]
            logging.debug('Command to run: %s', run_command)

            # Capture both stdout and stderr
            result = subprocess.run(run_command, check=True, creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            logging.debug('Installation stdout: %s', result.stdout)
            logging.debug('Installation stderr: %s', result.stderr)
        else:
            result = subprocess.run([str(installer_path)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            logging.debug('Installation stdout: %s', result.stdout)
            logging.debug('Installation stderr: %s', result.stderr)
        
        messagebox.showinfo("Installation", "VB-CABLE installation has completed.")
        logging.debug('VB-CABLE installation finished successfully.')
        return True

    except subprocess.CalledProcessError as e:
        logging.error('VB-CABLE installation failed with error: %s\nReturn code: %d\nOutput: %s\nStderr: %s', e, e.returncode, e.output, e.stderr)
        messagebox.showerror("Error", "Failed to install VB-CABLE.")
        return False
    except Exception as e:
        logging.error('Unexpected error during VB-CABLE installation: %s', e)
        messagebox.showerror("Error", "Failed to install VB-CABLE due to an unexpected error.")
        return False

def delete_ip_history():
    global ip_history
    ip_history = []
    save_ip_history()

class FFMPEGSenderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Audio Streamer")
        self.root.geometry("450x400")
        self.root.resizable(False, False)
        self.primary_button_font = ("Arial", 10, "bold")
        self.secondary_button_font = ("Arial", 9, "bold")

        # Set the icon for the application window and taskbar
        try:
            logging.debug('Setting icon from path: %s', icon_path)
            if icon_path.exists():
                self.root.iconbitmap(str(icon_path))
            else:
                logging.error('Icon file not found: %s', icon_path)
        except Exception as e:
            logging.error('Failed to set icon: %s', e)

        # Connection Details Section
        connection_frame = tk.LabelFrame(root, text="Connection Details", font=("Arial", 10, "bold"))
        connection_frame.place(x=20, y=20, width=410, height=90)

        self.ip_label = tk.Label(connection_frame, text="Receiver IP:", font=("Arial", 10))
        self.ip_label.place(x=15, y=15)
        self.ip_entry = tk.Entry(connection_frame, font=("Arial", 10))
        self.ip_entry.place(x=120, y=13, width=260)

        self.name_label = tk.Label(connection_frame, text="Name:", font=("Arial", 10))
        self.name_label.place(x=15, y=45)
        self.name_entry = tk.Entry(connection_frame, font=("Arial", 10))
        self.name_entry.place(x=120, y=43, width=260)

        # History Management Section
        history_frame = tk.LabelFrame(root, text="Saved Connections", font=("Arial", 10, "bold"))
        history_frame.place(x=20, y=130, width=410, height=140)

        tk.Label(history_frame, text="Select:", font=("Arial", 10)).place(x=15, y=15)
        self.ip_var = tk.StringVar()
        self.ip_dropdown = ttk.Combobox(history_frame, textvariable=self.ip_var, font=("Arial", 9), 
                                       postcommand=self.update_ip_dropdown, state="readonly")
        self.ip_dropdown.place(x=15, y=35, width=375, height=25)
        self.ip_dropdown.bind("<<ComboboxSelected>>", self.on_ip_selected)

        # History management buttons in a row with better spacing
        self.delete_selected_button = tk.Button(history_frame, text="Delete Selected", 
                                              command=self.delete_selected_ip, width=16, 
                                              font=self.secondary_button_font)
        self.style_button(self.delete_selected_button, normal_color="#f0f0f0", hover_color="#e0e0e0", text_color="#111111")
        self.delete_selected_button.place(x=80, y=80)

        self.clear_history_button = tk.Button(history_frame, text="Clear All", 
                                            command=self.clear_ip_history, width=16, 
                                            font=self.secondary_button_font)
        self.style_button(self.clear_history_button, normal_color="#f0f0f0", hover_color="#e0e0e0", text_color="#111111")
        self.clear_history_button.place(x=220, y=80)

        # Stream Controls Section
        controls_frame = tk.LabelFrame(root, text="Stream Control", font=("Arial", 10, "bold"))
        controls_frame.place(x=20, y=290, width=410, height=90)

        self.start_button = tk.Button(controls_frame, text="Start Stream", command=self.start_stream, 
                                    width=15, height=2, font=self.primary_button_font)
        self.style_button(self.start_button, normal_color="#4CAF50", hover_color="#45a049")
        self.start_button.place(x=40, y=10)

        self.stop_button = tk.Button(controls_frame, text="Stop Stream", command=self.stop_stream, 
                                   width=15, height=2, font=self.primary_button_font)
        self.style_button(self.stop_button, normal_color="#f44336", hover_color="#d32f2f")
        self.stop_button.place(x=220, y=10)
        self.stop_button.config(state=tk.DISABLED)

        self.process = None
        self.output_thread = None
        self.error_thread = None  
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Load IP history on startup
        load_ip_history()

    def style_button(self, button, normal_color, hover_color, text_color="white"):
        """Apply consistent visual style and interaction feedback to buttons."""
        button.normal_color = normal_color
        button.hover_color = hover_color
        button.config(
            bg=normal_color,
            fg=text_color,
            activebackground=hover_color,
            activeforeground=text_color,
            disabledforeground="#111111",
            relief="raised",
            bd=2,
            cursor="hand2"
        )
        button.bind("<Enter>", self._on_button_enter)
        button.bind("<Leave>", self._on_button_leave)
        button.bind("<ButtonPress-1>", self._on_button_press)
        button.bind("<ButtonRelease-1>", self._on_button_release)

    def _on_button_enter(self, event):
        button = event.widget
        if button["state"] != tk.DISABLED:
            button.config(bg=button.hover_color)

    def _on_button_leave(self, event):
        button = event.widget
        if button["state"] != tk.DISABLED:
            button.config(bg=button.normal_color, relief="raised")

    def _on_button_press(self, event):
        button = event.widget
        if button["state"] != tk.DISABLED:
            button.config(relief="sunken")

    def _on_button_release(self, event):
        button = event.widget
        if button["state"] != tk.DISABLED:
            button.config(relief="raised")

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
        try:
            # Get all audio devices
            devices = AudioUtilities.GetAllDevices()
            for device in devices:
                if device.FriendlyName == device_name:
                    logging.debug('Audio device found: %s', device_name)
                    return True
            
            logging.debug('Audio device not found: %s', device_name)
            return False
        except Exception as e:
            logging.error('Error checking for audio device: %s', e)
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

        # Check if already streaming and stop gracefully
        if self.process:
            self.stop_stream()

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
            if messagebox.askyesno("Audio Device Not Found", "VB-Audio Virtual Cable is required. Do you want to install it now?"):
                if not install_vb_cable():
                    return
            else:
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
                # Use resolved absolute path for subprocess call
                setplayback_exe = str(executable_path.resolve())
                subprocess.run([setplayback_exe], cwd=playback_work_dir, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
                logging.debug('SetPlayBack.exe executed successfully')
            except subprocess.CalledProcessError as e:
                logging.error('Failed to execute SetPlayBack.exe: %s', e)
                messagebox.showerror("Error", "Failed to configure audio environment.")
                return

            # Ensure ffmpeg path exists and resolve any path issues  
            if not ffmpeg_path.exists():
                logging.error(f"ffmpeg.exe not found at {ffmpeg_path}")
                messagebox.showerror("Error", f"ffmpeg.exe not found at:\n{ffmpeg_path}")
                return
                
            # Use absolute path and ensure proper string conversion
            ffmpeg_exe = str(ffmpeg_path.resolve())
            logging.debug(f"Using ffmpeg executable at: {ffmpeg_exe}")

            # Optimized FFmpeg command for low-latency TCP streaming
            command = [
                ffmpeg_exe,  # Use resolved absolute path
                '-hide_banner', '-loglevel', 'error',  # Clean logs
                '-f', 'dshow',
                '-audio_buffer_size', '50',           # Small buffer for low latency
                '-i', f'audio={audio_device}',
                '-codec:a', 'libmp3lame',             # MP3 faster than AAC
                '-b:a', '192k',
                '-f', 'mpegts',
                '-flush_packets', '1',                # Force immediate packet transmission
                # Single TCP connection with optimizations
                f'tcp://{ip_address}:6005?timeout=5000000&tcp_nodelay=1'
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
            try:
                # Try to stop FFmpeg gracefully by sending 'q'
                self.process.stdin.write(b'q')
                self.process.stdin.flush()
                self.process.wait(timeout=3)
                logging.debug('Stream terminated gracefully with q command')
            except Exception as e:
                logging.warning(f'Graceful stop failed, forcing kill: {e}')
                try:
                    self.process.kill()
                    self.process.wait()  # Wait for the kill to complete
                    logging.debug('Stream process killed')
                except Exception as kill_error:
                    logging.error(f'Error killing process: {kill_error}')
            finally:
                self.process = None
                self.start_button.config(state=tk.NORMAL)
                self.stop_button.config(state=tk.DISABLED)
                logging.debug('Stream stopped successfully')

    def clear_ip_history(self):
        if messagebox.askyesno("Clear History", "Are you sure you want to clear the IP history?"):
            delete_ip_history()
            self.update_ip_dropdown()
            self.ip_entry.delete(0, tk.END)
            self.name_entry.delete(0, tk.END)
            self.ip_dropdown.set('')
            messagebox.showinfo("IP History", "IP history cleared.")

    def delete_selected_ip(self):
        selected_text = self.ip_dropdown.get()
        if not selected_text:
            messagebox.showwarning("No Selection", "Please select an IP record to delete from the dropdown.")
            return
        
        # Parse the selected text to get the IP and name
        try:
            name, ip = selected_text.split(": ")
        except ValueError:
            messagebox.showerror("Error", "Invalid selection format.")
            return
        
        # Confirm deletion
        if messagebox.askyesno("Delete Record", f"Are you sure you want to delete the record:\n{name}: {ip}?"):
            # Find and remove the record from ip_history
            global ip_history
            for index, (existing_ip, existing_name) in enumerate(ip_history):
                if existing_ip == ip and existing_name == name:
                    ip_history.pop(index)
                    break
            else:
                messagebox.showerror("Error", "Record not found in history.")
                return
            
            # Save updated history
            save_ip_history()
            
            # Update dropdown
            self.update_ip_dropdown()
            
            # Clear the entries if they match the deleted record
            current_ip = self.ip_entry.get()
            current_name = self.name_entry.get()
            if current_ip == ip and current_name == name:
                self.ip_entry.delete(0, tk.END)
                self.name_entry.delete(0, tk.END)
            
            # Clear dropdown selection
            self.ip_dropdown.set('')
            
            logging.debug('Deleted IP record: %s - %s', name, ip)
            messagebox.showinfo("Record Deleted", f"Record '{name}: {ip}' has been deleted.")

    def on_closing(self):
        logging.debug('Closing application')
        self.stop_stream()
        self.root.destroy()

if __name__ == "__main__":
    logging.debug('Starting Audio Streamer application')
    root = tk.Tk()
    try:
        logging.debug('Setting main window icon from path: %s', icon_path)
        if icon_path.exists():
            root.iconbitmap(str(icon_path))
        else:
            logging.error('Icon file not found: %s', icon_path)
    except Exception as e:
        logging.error('Failed to set main window icon: %s', e)
    app = FFMPEGSenderGUI(root)
    root.mainloop()
    logging.debug('Audio Streamer application closed')