import unittest
from unittest.mock import Mock
from app.main import Api
from app.lcu import LcuError


class HeroAnalysisTests(unittest.TestCase):
    def test_exact_player_and_cursor_without_icon_fetch(self):
        api = Api()
        api.lcu.port = 123
        api.history = Mock()
        rows = [{"gameId": 1, "championId": 266}]
        api.history.page.return_value = (rows, True, "sgp", "")
        result = api.get_analysis_matches("enemy-exact", 40, 20)
        api.history.page.assert_called_once_with("enemy-exact", 40, 20)
        self.assertEqual(result["games"][0]["gameId"], 1)
        self.assertIn("亚托克斯", result["games"][0]["championName"])
        self.assertEqual(result["games"][0]["avatar"], "champion-icons/266.png")
        self.assertTrue(result["hasMore"])
        self.assertEqual(result["source"], "sgp")

    def test_hidden_identity_and_failure_do_not_become_empty_history(self):
        api = Api()
        api.lcu.port = 123
        api.history = Mock()
        self.assertFalse(api.get_analysis_matches("0000-0000", 0)["ok"])
        api.history.page.assert_not_called()
        api.history.page.side_effect = LcuError("分页失败")
        result = api.get_analysis_matches("player", 20)
        self.assertFalse(result["ok"])
        self.assertIn("分页失败", result["error"])
