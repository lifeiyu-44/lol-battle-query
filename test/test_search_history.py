import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from app.search_history import SearchHistory
from app.main import Api


class SearchHistoryTests(unittest.TestCase):
    def test_persistence_dedup_cap_and_delete(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "history.db"
            store = SearchHistory(path)
            self.assertEqual(store.list_recent(), [])
            for i in range(22):
                store.remember({"puuid": str(i+1), "name": "玩家"+str(i), "tagLine": "CN", "token": "NEVER_STORE_THIS"})
            self.assertEqual(len(SearchHistory(path).list_recent()), 20)
            self.assertEqual(store.list_recent()[0]["puuid"], "22")
            store.remember({"puuid": "5", "name": "改名后", "tagLine": "TAG"})
            self.assertEqual(store.list_recent()[0]["name"], "改名后")
            self.assertEqual(len(store.list_recent()), 20)
            self.assertNotIn(b"NEVER_STORE_THIS", path.read_bytes())
            self.assertEqual(len(store.remove("5")), 19)
            self.assertEqual(store.remove(), [])
            self.assertEqual(SearchHistory(path).list_recent(), [])

    def test_current_account_identity_and_saved_player_conflict(self):
        api = Api()
        api.lcu = Mock()
        api.lcu.connect.return_value = {"puuid": "self", "summonerId": 1, "gameName": "本人", "tagLine": "CN", "summonerLevel": 100}
        me = api.get_status()["me"]
        self.assertEqual((me["puuid"], me["tagLine"], me["friendStatus"]), ("self", "CN", "self"))
        api.lcu.request.return_value = (200, {"puuid": "someone-else", "gameName": "同名玩家"})
        self.assertFalse(api.get_saved_player("wanted")["ok"])

    def test_invalid_history_never_written(self):
        with tempfile.TemporaryDirectory() as folder:
            store = SearchHistory(Path(folder)/"history.db")
            with self.assertRaises(ValueError):
                store.remember({"puuid": "0000-0000", "name": "匿名"})
            self.assertEqual(store.list_recent(), [])
