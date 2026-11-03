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
    decode_settings, load_settings, save_settings, settings_path,
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
            ]},
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
        ):
            with self.subTest(document=document), self.assertRaises(SettingsError):
                decode_settings(document)

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
    def test_receiver_settings_load_errors_are_logged_and_shown(self):
        tree = ast.parse((ROOT / "Audio Receiver.py").read_text(encoding="utf-8-sig"))
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


if __name__ == "__main__":
    unittest.main()
