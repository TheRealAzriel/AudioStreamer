from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import tempfile

from audio_common import app_data_directory, is_valid_ip


APP_VERSION = "1.0.3"
SETTINGS_VERSION = 1


class SettingsError(Exception):
    pass


@dataclass
class AppSettings:
    saved_receivers: list[tuple[str, str]] = field(default_factory=list)
    receiver_name: str = ""
    recording_folder: str | None = None


def validate_receivers(value: object) -> list[tuple[str, str]]:
    if not isinstance(value, list):
        raise SettingsError("Saved receivers must be a list.")
    receivers = []
    for entry in value:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise SettingsError("Each saved receiver must contain an IP address and a name.")
        address, name = entry
        if not isinstance(address, str) or not is_valid_ip(address):
            raise SettingsError("A saved receiver has an invalid IPv4 address.")
        if not isinstance(name, str):
            raise SettingsError("A saved receiver name must be text.")
        receivers.append((address, name))
    return receivers


def validate_receiver_name(value: object) -> str:
    if not isinstance(value, str) or len(value) > 64:
        raise SettingsError("Receiver name must be text with at most 64 characters.")
    return value


def validate_recording_folder(value: object) -> str | None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise SettingsError("Recording folder must be a non-empty path or null.")
    return value


def decode_settings(value: object) -> AppSettings:
    if not isinstance(value, dict):
        raise SettingsError("Settings must be a JSON object.")
    if type(value.get("schema_version")) is not int or value["schema_version"] != SETTINGS_VERSION:
        raise SettingsError("Unsupported settings schema version.")
    required = {"schema_version", "saved_receivers"}
    optional = {"receiver_name", "recording_folder"}
    if not required.issubset(value) or set(value) - required - optional:
        raise SettingsError("Settings contain missing or unsupported fields.")
    return AppSettings(
        validate_receivers(value["saved_receivers"]),
        validate_receiver_name(value.get("receiver_name", "")),
        validate_recording_folder(value.get("recording_folder")),
    )


def settings_path(app_name: str) -> Path:
    return app_data_directory(app_name) / "settings.json"


def default_recording_directory() -> Path:
    music_directory = Path.home() / "Music"
    if music_directory.is_dir():
        return music_directory / "Audio Receiver Recordings"
    return app_data_directory("Audio Receiver") / "Recordings"


def ensure_recording_directory_writable(directory: Path) -> None:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=directory, prefix=".write-test-", delete=True
        ):
            pass
    except OSError as exc:
        raise SettingsError(f"Recording folder is not writable: {directory}") from exc


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SettingsError(f"Unable to read settings file: {path}") from exc


def save_settings(app_name: str, settings: AppSettings) -> None:
    document = {
        "schema_version": SETTINGS_VERSION,
        "saved_receivers": validate_receivers(settings.saved_receivers),
        "receiver_name": validate_receiver_name(settings.receiver_name),
        "recording_folder": validate_recording_folder(settings.recording_folder),
    }
    path = settings_path(app_name)
    temporary_path = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=".settings-",
            suffix=".tmp", delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(document, temporary, ensure_ascii=False, indent=2)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    except (OSError, UnicodeError) as exc:
        raise SettingsError(f"Unable to save settings file: {path}") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError as exc:
                raise SettingsError(f"Unable to remove temporary settings file: {temporary_path}") from exc


def load_settings(app_name: str, legacy_paths: tuple[Path, ...] = ()) -> AppSettings:
    path = settings_path(app_name)
    try:
        # Open rather than exists(): permission errors must not look like missing settings.
        with path.open(encoding="utf-8-sig") as file:
            document = json.load(file)
    except FileNotFoundError:
        for legacy_path in legacy_paths:
            try:
                legacy_path.stat()
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise SettingsError(f"Unable to access saved Receiver addresses: {legacy_path}") from exc
            settings = AppSettings(validate_receivers(_read_json(legacy_path)))
            save_settings(app_name, settings)
            return settings
        return AppSettings()
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SettingsError(f"Unable to read settings file: {path}") from exc
    return decode_settings(document)
