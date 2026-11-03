import ast
import json
import logging
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from app_settings import (
    APP_VERSION, SETTINGS_VERSION, AppSettings, SettingsError,
    decode_settings, default_recording_directory, ensure_recording_directory_writable,
    load_settings, save_settings, settings_path,
)


ROOT = Path(__file__).resolve().parents[1]


class SettingsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "Local Data")})
        environment.start()
        self.addCleanup(environment.stop)
        self.app = "Audio Streamer"

    def test_paths_are_per_application_under_localappdata(self):
        for app in ("Audio Receiver", "Audio Streamer"):
            self.assertEqual(settings_path(app), self.root / "Local Data" / app / "settings.json")

    def test_missing_settings_returns_independent_defaults_without_writing(self):
        first = load_settings(self.app)
        second = load_settings(self.app)
        first.saved_receivers.append(("127.0.0.1", "First"))
        self.assertEqual(second.saved_receivers, [])
        self.assertFalse(settings_path(self.app).exists())

    def test_receiver_settings_round_trip(self):
        save_settings("Audio Receiver", AppSettings())
        self.assertEqual(load_settings("Audio Receiver"), AppSettings())

    def test_unicode_names_and_existing_ipv4_forms_round_trip(self):
        settings = AppSettings([("127.1", "Desk: Speakers"), ("192.168.1.5", "B\u00fcro")])
        save_settings(self.app, settings)
        self.assertEqual(load_settings(self.app), settings)
        self.assertEqual(
            json.loads(settings_path(self.app).read_text(encoding="utf-8")),
            {"schema_version": SETTINGS_VERSION, "saved_receivers": [
                ["127.1", "Desk: Speakers"], ["192.168.1.5", "B\u00fcro"],
            ], "receiver_name": "", "recording_folder": None},
        )

    def test_invalid_documents_are_not_silently_accepted(self):
        for document in (
            None, [], {}, {"schema_version": True, "saved_receivers": []},
            {"schema_version": 1.0, "saved_receivers": []},
            {"schema_version": 2, "saved_receivers": []},
            {"schema_version": 1, "saved_receivers": [], "unknown": True},
            {"schema_version": 1, "saved_receivers": {}},
            {"schema_version": 1, "saved_receivers": ["127.0.0.1"]},
            {"schema_version": 1, "saved_receivers": [["bad address", "Name"]]},
            {"schema_version": 1, "saved_receivers": [["127.0.0.1", 42]]},
            {"schema_version": 1, "saved_receivers": [["127.0.0.1", "Name", "Extra"]]},
            {"schema_version": 1, "saved_receivers": [], "receiver_name": 42},
            {"schema_version": 1, "saved_receivers": [], "receiver_name": "x" * 65},
            {"schema_version": 1, "saved_receivers": [], "recording_folder": ""},
        ):
            with self.subTest(document=document), self.assertRaises(SettingsError):
                decode_settings(document)

    def test_existing_settings_keep_working_with_new_receiver_defaults(self):
        self.assertEqual(
            decode_settings({"schema_version": 1, "saved_receivers": [["127.0.0.1", "Desk"]]}),
            AppSettings([("127.0.0.1", "Desk")]),
        )

    def test_receiver_preferences_round_trip(self):
        settings = AppSettings([], "Studio Receiver", str(self.root / "Music"))
        save_settings("Audio Receiver", settings)
        self.assertEqual(load_settings("Audio Receiver"), settings)

    def test_recording_directory_prefers_existing_music_folder(self):
        home = self.root / "Profile"
        music = home / "Music"
        music.mkdir(parents=True)
        with patch("app_settings.Path.home", return_value=home):
            self.assertEqual(default_recording_directory(), music / "Audio Receiver Recordings")

    def test_recording_directory_falls_back_to_local_app_data(self):
        home = self.root / "Profile"
        with patch("app_settings.Path.home", return_value=home):
            self.assertEqual(
                default_recording_directory(),
                self.root / "Local Data" / "Audio Receiver" / "Recordings",
            )

    def test_recording_directory_writability_check_creates_and_cleans_up(self):
        directory = self.root / "Recordings"
        ensure_recording_directory_writable(directory)
        self.assertTrue(directory.is_dir())
        self.assertEqual(list(directory.iterdir()), [])

    def test_recording_directory_writability_failure_is_reported(self):
        with patch("app_settings.tempfile.NamedTemporaryFile", side_effect=PermissionError):
            with self.assertRaisesRegex(SettingsError, "Recording folder is not writable"):
                ensure_recording_directory_writable(self.root / "Recordings")

    def test_corrupt_file_is_preserved_and_does_not_fall_back_to_legacy(self):
        path = settings_path(self.app)
        path.parent.mkdir(parents=True)
        path.write_text("{broken", encoding="utf-8")
        legacy = self.root / "ip_history.json"
        legacy.write_text('[["127.0.0.1", "Saved"]]')
        with self.assertRaises(SettingsError):
            load_settings(self.app, (legacy,))
        self.assertEqual(path.read_text(), "{broken")

    def test_invalid_encoding_is_reported(self):
        path = settings_path(self.app)
        path.parent.mkdir(parents=True)
        path.write_bytes(b"\xff\xfe\x00")
        with self.assertRaises(SettingsError):
            load_settings(self.app)

    def test_settings_read_permission_error_is_not_treated_as_missing(self):
        with patch("app_settings.Path.open", side_effect=PermissionError("Denied")):
            with self.assertRaises(SettingsError):
                load_settings(self.app)

    def test_bom_is_supported(self):
        path = settings_path(self.app)
        path.parent.mkdir(parents=True)
        path.write_text(
            '{"schema_version": 1, "saved_receivers": []}', encoding="utf-8-sig"
        )
        self.assertEqual(load_settings(self.app), AppSettings())

    def test_legacy_history_is_migrated_without_modifying_original(self):
        legacy = self.root / "ip_history.json"
        content = '[["127.0.0.1","First"],["192.168.0.5","Second"]]'
        legacy.write_text(content)
        settings = load_settings(self.app, (self.root / "missing.json", legacy))
        self.assertEqual(settings.saved_receivers, [
            ("127.0.0.1", "First"), ("192.168.0.5", "Second"),
        ])
        self.assertEqual(legacy.read_text(), content)
        self.assertEqual(load_settings(self.app), settings)

    def test_existing_new_settings_take_precedence_over_legacy(self):
        save_settings(self.app, AppSettings([("127.0.0.1", "New")]))
        legacy = self.root / "ip_history.json"
        legacy.write_text("invalid json")
        self.assertEqual(
            load_settings(self.app, (legacy,)).saved_receivers, [("127.0.0.1", "New")]
        )

    def test_invalid_legacy_is_not_skipped_or_overwritten(self):
        invalid = self.root / "invalid.json"
        valid = self.root / "valid.json"
        invalid.write_text('[["invalid", "Name"]]')
        valid.write_text('[["127.0.0.1", "Valid"]]')
        with self.assertRaises(SettingsError):
            load_settings(self.app, (invalid, valid))
        self.assertFalse(settings_path(self.app).exists())
        self.assertEqual(invalid.read_text(), '[["invalid", "Name"]]')

    def test_legacy_access_error_is_reported(self):
        with patch("app_settings.Path.stat", side_effect=PermissionError("Denied")):
            with self.assertRaises(SettingsError):
                load_settings(self.app, (self.root / "legacy.json",))

    def test_failed_migration_leaves_legacy_intact(self):
        legacy = self.root / "ip_history.json"
        content = '[["127.0.0.1", "Saved"]]'
        legacy.write_text(content)
        with patch("app_settings.os.replace", side_effect=PermissionError("Denied")):
            with self.assertRaises(SettingsError):
                load_settings(self.app, (legacy,))
        self.assertEqual(legacy.read_text(), content)
        self.assertFalse(settings_path(self.app).exists())
        self.assertEqual(list(settings_path(self.app).parent.glob("*.tmp")), [])

    def test_failed_atomic_replace_preserves_previous_settings(self):
        original = AppSettings([("127.0.0.1", "Original")])
        save_settings(self.app, original)
        with patch("app_settings.os.replace", side_effect=PermissionError("Denied")):
            with self.assertRaises(SettingsError):
                save_settings(self.app, AppSettings([("127.0.0.2", "New")]))
        self.assertEqual(load_settings(self.app), original)
        self.assertEqual(list(settings_path(self.app).parent.glob("*.tmp")), [])

    def test_replacement_is_same_directory_and_contains_complete_valid_json(self):
        real_replace = os.replace

        def verify_replace(source, destination):
            self.assertEqual(Path(source).parent, Path(destination).parent)
            self.assertEqual(
                decode_settings(json.loads(Path(source).read_text())),
                AppSettings([("127.0.0.1", "Saved")]),
            )
            real_replace(source, destination)

        with patch("app_settings.os.replace", side_effect=verify_replace) as replace:
            save_settings(self.app, AppSettings([("127.0.0.1", "Saved")]))
        replace.assert_called_once()

    def test_sync_failure_preserves_previous_settings_and_removes_temp(self):
        original = AppSettings([("127.0.0.1", "Saved")])
        save_settings(self.app, original)
        with patch("app_settings.os.fsync", side_effect=OSError("Disk error")):
            with self.assertRaises(SettingsError):
                save_settings(self.app, AppSettings())
        self.assertEqual(load_settings(self.app), original)
        self.assertEqual(list(settings_path(self.app).parent.glob("*.tmp")), [])

    def test_invalid_save_cannot_replace_good_settings(self):
        save_settings(self.app, AppSettings())
        with self.assertRaises(SettingsError):
            save_settings(self.app, AppSettings([("invalid", "Name")]))
        self.assertEqual(load_settings(self.app), AppSettings())

    def test_unicode_write_error_is_reported_and_previous_file_preserved(self):
        save_settings(self.app, AppSettings())
        with self.assertRaises(SettingsError):
            save_settings(self.app, AppSettings([("127.0.0.1", "\ud800")]))
        self.assertEqual(load_settings(self.app), AppSettings())
        self.assertEqual(list(settings_path(self.app).parent.glob("*.tmp")), [])

    def test_shared_version_is_used_by_both_apps(self):
        self.assertRegex(APP_VERSION, r"^\d+\.\d+\.\d+$")
        for name in ("Audio Receiver.py", "Audio Streamer.py"):
            tree = ast.parse((ROOT / name).read_text(encoding="utf-8-sig"))
            self.assertTrue(any(
                isinstance(node, ast.ImportFrom) and node.module == "app_settings"
                and any(alias.name == "APP_VERSION" for alias in node.names)
                for node in tree.body
            ))


class StreamerSettingsIntegrationTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((ROOT / "Audio Streamer.py").read_text(encoding="utf-8-sig"))
        nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))]
        self.namespace = {
            "AppSettings": AppSettings, "SettingsError": SettingsError,
            "load_settings": Mock(return_value=AppSettings([("127.0.0.1", "Original")])),
            "save_settings": Mock(), "messagebox": Mock(), "logging": logging,
            "Path": Path, "history_file": Path("legacy.json"), "script_dir": Path("app"),
            "ip_history": [], "settings_available": False,
        }
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "<streamer settings>", "exec"), self.namespace)

    def test_legacy_sources_are_passed_and_loaded_history_is_available(self):
        self.namespace["load_ip_history"]()
        self.assertEqual(self.namespace["ip_history"], [("127.0.0.1", "Original")])
        self.assertTrue(self.namespace["settings_available"])
        app, paths = self.namespace["load_settings"].call_args.args
        self.assertEqual(app, "Audio Streamer")
        self.assertEqual(paths[0], Path("legacy.json"))
        self.assertEqual(paths[-1], Path("app") / "ip_history.json")

    def test_load_error_blocks_saves_and_preserves_existing_history(self):
        self.namespace["load_settings"].side_effect = SettingsError("Broken settings")
        self.namespace["ip_history"] = [("127.0.0.1", "Original")]
        with self.assertLogs(level="ERROR"):
            self.namespace["load_ip_history"]()
            self.assertFalse(self.namespace["save_ip_history"]([]))
        self.assertFalse(self.namespace["settings_available"])
        self.namespace["save_settings"].assert_not_called()
        self.assertEqual(self.namespace["ip_history"], [("127.0.0.1", "Original")])
        self.assertEqual(self.namespace["messagebox"].showerror.call_count, 2)

    def test_save_failure_does_not_update_memory(self):
        self.namespace["load_ip_history"]()
        self.namespace["save_settings"].side_effect = SettingsError("Disk full")
        with self.assertLogs(level="ERROR"):
            self.assertFalse(self.namespace["save_ip_history"]([]))
        self.assertEqual(self.namespace["ip_history"], [("127.0.0.1", "Original")])
        self.namespace["messagebox"].showerror.assert_called_once()

    def test_successful_clear_saves_before_updating_history(self):
        self.namespace["load_ip_history"]()
        self.assertTrue(self.namespace["delete_ip_history"]())
        self.namespace["save_settings"].assert_called_once_with("Audio Streamer", AppSettings())
        self.assertEqual(self.namespace["ip_history"], [])

    def test_add_update_and_limit_preserve_existing_workflow(self):
        self.namespace["load_ip_history"]()
        gui = self.namespace["FFMPEGSenderGUI"]
        app = gui.__new__(gui)
        self.assertTrue(app.add_ip_to_history("127.0.0.1", "Updated"))
        self.assertEqual(self.namespace["ip_history"], [("127.0.0.1", "Updated")])
        for index in range(2, 13):
            app.add_ip_to_history(f"127.0.0.{index}", str(index))
        self.assertEqual(len(self.namespace["ip_history"]), 10)
        self.assertEqual(self.namespace["ip_history"][0], ("127.0.0.12", "12"))

    def test_colon_in_connection_name_round_trips_dropdown(self):
        gui = self.namespace["FFMPEGSenderGUI"]
        app = gui.__new__(gui)
        app.ip_dropdown = Mock()
        app.ip_dropdown.get.return_value = "Desk: Speakers: 127.0.0.1"
        app.ip_entry = Mock()
        app.name_entry = Mock()
        self.namespace["tk"] = Mock()
        app.on_ip_selected(None)
        app.name_entry.insert.assert_called_once_with(0, "Desk: Speakers")
        app.ip_entry.insert.assert_called_once_with(0, "127.0.0.1")

    def test_failed_clear_does_not_clear_fields_or_claim_success(self):
        self.namespace["load_ip_history"]()
        self.namespace["save_settings"].side_effect = SettingsError("Disk full")
        self.namespace["messagebox"].askyesno.return_value = True
        gui = self.namespace["FFMPEGSenderGUI"]
        app = gui.__new__(gui)
        app.update_ip_dropdown = Mock()
        app.ip_entry = Mock()
        with self.assertLogs(level="ERROR"):
            app.clear_ip_history()
        app.update_ip_dropdown.assert_not_called()
        app.ip_entry.delete.assert_not_called()
        self.namespace["messagebox"].showinfo.assert_not_called()
        self.assertEqual(self.namespace["ip_history"], [("127.0.0.1", "Original")])

    def test_failed_delete_keeps_history_and_does_not_claim_success(self):
        self.namespace["load_ip_history"]()
        self.namespace["save_settings"].side_effect = SettingsError("Disk full")
        self.namespace["messagebox"].askyesno.return_value = True
        gui = self.namespace["FFMPEGSenderGUI"]
        app = gui.__new__(gui)
        app.ip_dropdown = Mock()
        app.ip_dropdown.get.return_value = "Original: 127.0.0.1"
        app.update_ip_dropdown = Mock()
        with self.assertLogs(level="ERROR"):
            app.delete_selected_ip()
        app.update_ip_dropdown.assert_not_called()
        self.namespace["messagebox"].showinfo.assert_not_called()
        self.assertEqual(self.namespace["ip_history"], [("127.0.0.1", "Original")])


class ReceiverSettingsIntegrationTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse((ROOT / "Audio Receiver.py").read_text(encoding="utf-8-sig"))
        gui = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        names = {
            "create_menu", "start_recording", "save_preferences",
            "choose_recording_folder", "change_receiver_name", "reset_settings",
        }
        methods = [
            node for node in gui.body
            if isinstance(node, ast.FunctionDef) and node.name in names
        ]
        self.namespace = {
            "tk": Mock(),
            "threading": Mock(),
            "logging": logging,
            "datetime": __import__("datetime").datetime,
            "next_recording_path": __import__("audio_common").next_recording_path,
            "ensure_recording_directory_writable": ensure_recording_directory_writable,
            "default_recording_directory": default_recording_directory,
            "save_settings": Mock(),
            "filedialog": Mock(),
            "simpledialog": Mock(),
            "AppSettings": AppSettings,
            "Path": Path,
            "socket": Mock(gethostname=Mock(return_value="Test PC")),
            "SettingsError": SettingsError,
            "messagebox": Mock(),
        }
        exec(
            compile(ast.Module(body=methods, type_ignores=[]), "<receiver menu>", "exec"),
            self.namespace,
        )

    def test_receiver_settings_load_errors_are_logged_and_shown(self):
        tree = ast.parse((ROOT / "Audio Receiver.py").read_text(encoding="utf-8-sig"))
        log_path_assignment = next(
            node for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "log_file_path"
                for target in node.targets
            )
        )
        namespace = {"appdata_local_path": Path("local-data")}
        exec(
            compile(ast.Module(body=[log_path_assignment], type_ignores=[]),
                    "<receiver log path>", "exec"),
            namespace,
        )
        self.assertEqual(
            namespace["log_file_path"],
            Path("local-data") / "logs" / "Audio_Receiver.log",
        )

        gui = next(node for node in tree.body if isinstance(node, ast.ClassDef))
        init = next(node for node in gui.body if isinstance(node, ast.FunctionDef) and node.name == "__init__")
        settings_try = next(
            node for node in init.body if isinstance(node, ast.Try)
            and any(
                isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
                and child.func.id == "load_settings"
                for child in ast.walk(node)
            )
        )
        app = Mock()
        app.settings = None
        namespace = {
            "self": app, "load_settings": Mock(side_effect=SettingsError("Broken settings")),
            "SettingsError": SettingsError, "logging": logging, "messagebox": Mock(),
        }
        with self.assertLogs(level="ERROR"):
            exec(compile(ast.Module(body=[settings_try], type_ignores=[]), "<receiver settings>", "exec"), namespace)
        namespace["load_settings"].assert_called_once_with("Audio Receiver")
        namespace["messagebox"].showerror.assert_called_once()
        self.assertIsNone(app.settings)

    def test_receiver_menu_contains_all_requested_actions(self):
        menus = [Mock() for _ in range(4)]
        self.namespace["tk"].Menu.side_effect = menus
        app = Mock()
        self.namespace["create_menu"](app)
        labels = [
            call.kwargs.get("label")
            for menu in menus
            for call in menu.add_command.call_args_list + menu.add_cascade.call_args_list
        ]
        self.assertCountEqual(labels, [
            "Choose Recording Folder...", "Open Recording Folder", "Exit", "File",
            "Receiver Name...", "Reset Settings", "Options",
            "Open Log Folder", "About Audio Receiver", "Help",
        ])
        app.root.config.assert_called_once_with(menu=menus[0])

    def test_start_recording_uses_a_fresh_non_overwriting_filename(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            timestamp = __import__("datetime").datetime(2026, 1, 2, 3, 4, 5)
            existing = directory / "recording_20260102_030405.mp3"
            existing.touch()
            app = Mock()
            app.process = None
            app.recordings_dir = directory
            app.recording_filename = existing
            self.namespace["datetime"] = Mock(now=Mock(return_value=timestamp))
            self.namespace["start_recording"](app)
            self.assertEqual(
                app.recording_filename,
                directory / "recording_20260102_030405_2.mp3",
            )
            app.stream_thread.start.assert_called_once()
            self.assertTrue(app.is_recording_mode)

    def test_start_recording_reports_unwritable_folder_without_starting(self):
        app = Mock()
        app.process = None
        app.recordings_dir = Path("unused")
        app.is_recording_mode = False
        self.namespace["ensure_recording_directory_writable"] = Mock(
            side_effect=SettingsError("Recording folder is not writable")
        )
        with self.assertLogs(level="ERROR"):
            self.namespace["start_recording"](app)
        self.namespace["messagebox"].showerror.assert_called_once()
        self.namespace["threading"].Thread.assert_not_called()
        self.assertFalse(app.is_recording_mode)

    def test_selected_recording_folder_is_checked_and_persisted(self):
        with tempfile.TemporaryDirectory() as temporary:
            app = Mock()
            app.root = Mock()
            app.settings = AppSettings([], "Studio")
            app.recordings_dir = Path(temporary) / "old"
            app.save_preferences = self.namespace["save_preferences"].__get__(app)
            selected = Path(temporary) / "new"
            self.namespace["filedialog"].askdirectory.return_value = str(selected)
            self.namespace["choose_recording_folder"](app)
            self.assertEqual(app.settings.recording_folder, str(selected))
            self.assertEqual(app.settings.receiver_name, "Studio")
            self.assertEqual(app.recordings_dir, selected)
            self.assertEqual(list(selected.iterdir()), [])
            self.namespace["save_settings"].assert_called_once_with(
                "Audio Receiver", app.settings
            )

    def test_failed_preference_save_preserves_current_settings(self):
        app = Mock()
        original = AppSettings([], "Original")
        app.settings = original
        self.namespace["save_settings"].side_effect = SettingsError("Disk full")
        with self.assertLogs(level="ERROR"):
            self.assertFalse(self.namespace["save_preferences"](app, AppSettings()))
        self.assertIs(app.settings, original)
        self.namespace["messagebox"].showerror.assert_called_once()

    def test_receiver_name_and_reset_menu_actions_persist_preferences(self):
        app = Mock()
        app.root = Mock()
        app.settings = AppSettings([], "Old Name", "C:\\Recordings")
        app.recordings_dir = Path("C:\\Recordings")
        app.save_preferences = self.namespace["save_preferences"].__get__(app)
        self.namespace["simpledialog"].askstring.return_value = "  New Name  "
        self.namespace["change_receiver_name"](app)
        self.assertEqual(app.settings.receiver_name, "New Name")

        self.namespace["messagebox"].askyesno.return_value = True
        self.namespace["reset_settings"](app)
        self.assertEqual(app.settings, AppSettings())
        self.namespace["messagebox"].showinfo.assert_called_once()


if __name__ == "__main__":
    unittest.main()
