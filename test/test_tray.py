import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.main import Api


class TrayCloseTests(unittest.TestCase):
    def _api_with_tmp_settings(self):
        tmp = Path(tempfile.mkdtemp())
        api = Api()
        patcher = patch.object(Api, "_settings_path", lambda self: tmp / "app-settings.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        return api, tmp / "app-settings.json"

    def test_settings_roundtrip(self):
        api, path = self._api_with_tmp_settings()
        api._settings = {"close_to_tray": False}
        api.save_app_settings()
        self.assertEqual(api.load_app_settings(), {"close_to_tray": False})
        api._settings = {"close_to_tray": True}
        api.save_app_settings()
        self.assertEqual(api.load_app_settings(), {"close_to_tray": True})

    def test_missing_settings_default_to_tray(self):
        api, path = self._api_with_tmp_settings()
        self.assertEqual(api.load_app_settings(), {"close_to_tray": True})

    def test_closing_hides_to_tray_when_enabled(self):
        api = Api()
        api._tray_available = True
        api._settings = {"close_to_tray": True}
        api._main_window = Mock()
        self.assertFalse(api._on_main_closing())  # False = 取消关闭
        api._main_window.hide.assert_called_once()

    def test_closing_exits_when_disabled(self):
        api = Api()
        api._tray_available = True
        api._settings = {"close_to_tray": False}
        api._main_window = Mock()
        self.assertIsNone(api._on_main_closing())
        api._main_window.hide.assert_not_called()

    def test_closing_allows_exit_once_exiting(self):
        api = Api()
        api._tray_available = True
        api._settings = {"close_to_tray": True}
        api._exiting = True
        api._main_window = Mock()
        self.assertIsNone(api._on_main_closing())

    def test_closing_exits_without_tray(self):
        api = Api()
        api._tray_available = False
        api._settings = {"close_to_tray": True}
        api._main_window = Mock()
        self.assertIsNone(api._on_main_closing())
        api._main_window.hide.assert_not_called()

    def test_toggle_flips_setting_and_updates_menu(self):
        api, path = self._api_with_tmp_settings()
        api._settings = {"close_to_tray": True}
        icon = Mock()
        api._toggle_close_to_tray(icon=icon)
        self.assertFalse(api._settings["close_to_tray"])
        self.assertEqual(api.load_app_settings(), {"close_to_tray": False})
        icon.update_menu.assert_called_once()
        api._toggle_close_to_tray(icon=icon)
        self.assertTrue(api.load_app_settings()["close_to_tray"])

    def test_exit_destroys_window_and_marks_exiting(self):
        api = Api()
        api._tray_icon = Mock()
        api._main_window = Mock()
        api._exit_app(icon=api._tray_icon)
        self.assertTrue(api._exiting)
        api._main_window.destroy.assert_called_once()
        api._tray_icon.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
