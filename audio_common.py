from datetime import datetime
from pathlib import Path
import os
import socket


def app_data_directory(app_name: str) -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / app_name
    return Path.home() / "AppData" / "Local" / app_name


def recording_path(directory: Path, timestamp: datetime) -> Path:
    return directory / f"recording_{timestamp:%Y%m%d_%H%M%S}.mp3"


def is_valid_ip(address: str) -> bool:
    # Preserve inet_aton's existing acceptance of abbreviated IPv4 addresses.
    try:
        socket.inet_aton(address)
    except OSError:
        return False
    return True


def receiver_status(text: str) -> tuple[str, str, str] | None:
    if text == "Idle":
        return "idle", "#cccccc", "#999999"
    if "Receiving" in text:
        return "connected", "#4CAF50", "#2E7D32"
    if "Error" in text:
        return "error", "#f44336", "#d32f2f"
    if "Muted" in text:
        return "muted", "#ff9800", "#f57c00"
    return None


def streamer_status(text: str) -> tuple[str, str, str] | None:
    if text == "Idle":
        return "idle", "#cccccc", "#999999"
    if text == "Connecting":
        return "connecting", "#ff9800", "#f57c00"
    if text == "Stopping":
        return "stopping", "#ff9800", "#f57c00"
    if "Streaming" in text:
        return "streaming", "#4CAF50", "#2E7D32"
    if "Error" in text:
        return "error", "#f44336", "#d32f2f"
    return None


def receiver_button_states(process_active: bool) -> tuple[bool, bool, bool]:
    return not process_active, process_active, not process_active
