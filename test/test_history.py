import unittest
from unittest.mock import Mock, patch

from app.history import HistoryClient, normalize_game
from app.lcu import LcuError


def game(gid):
    return {"json": {"gameId": gid, "gameCreation": 1700000000000 - gid * 60000,
                     "gameDuration": 1200, "gameMode": "KIWI", "queueId": 2400,
                     "participants": [{"participantId": n, "teamId": 100 if n <= 5 else 200,
                         "puuid": "target" if n == 10 else "other-{}".format(n),
                         "championId": 266, "riotIdGameName": "Player", "riotIdTagline": "CN",
                         "kills": n, "deaths": 2, "assists": 3, "win": n > 5,
                         "totalDamageDealtToChampions": n * 1000} for n in range(1, 11)]}}


class HistoryTests(unittest.TestCase):
    def client(self):
        lcu = Mock(port=1234)
        lcu.request.side_effect = lambda method, path, **kwargs: (
            (200, {"currentPlatformId": "HN1"}) if path.endswith("authorization") else
            (200, {"accessToken": "test-token"}))
        client = HistoryClient(lcu)
        client._http = Mock()
        def response(url, params, **kwargs):
            rows = [game(i+1) for i in range(params["startIndex"], min(params["startIndex"]+params["count"], 53))]
            return Mock(status_code=200, json=lambda: {"games": rows})
        client._http.get.side_effect = response
        return client

    def test_real_pagination_shape_and_damage(self):
        client = self.client()
        loaded = []
        for start, count in [(0, 20), (20, 20), (40, 10)]:
            rows, more, source, note = client.page("target", start, count)
            loaded.extend(rows)
            self.assertTrue(more)
            self.assertEqual(source, "sgp")
            self.assertEqual(note, "")
        self.assertEqual(len({g["gameId"] for g in loaded}), 50)
        self.assertEqual(loaded[0]["kills"], 10)
        self.assertEqual(loaded[0]["damageEvaluation"]["teamShare"], 25)
        self.assertEqual(loaded[0]["damageEvaluation"]["rank"], 1)
        self.assertEqual(client.cached_game("target", 50)["participantIdentities"][9]["player"]["tagLine"], "CN")
        call = client._http.get.call_args
        self.assertTrue(call.args[0].startswith("https://hn1-k8s-sgp.lol.qq.com:21019/"))
        self.assertEqual(call.kwargs["params"], {"startIndex": 40, "count": 10})
        self.assertFalse(call.kwargs["allow_redirects"])
        rows, more, _, _ = client.page("target", 50)
        self.assertEqual(len(rows), 3)
        self.assertFalse(more)

    def test_failure_is_not_end_of_history(self):
        client = self.client()
        client._http.get.return_value = Mock(status_code=503)
        client._http.get.side_effect = None
        with patch('app.history.Q.match_page', return_value=([{"gameId": 1}], True)) as fallback:
            _, more, source, note = client.page("target", 0)
            self.assertTrue(more)
            self.assertEqual(source, "lcu")
            self.assertIn("不能据此判断历史总数", note)
            with self.assertRaises(LcuError): client.page("target", 20)
            self.assertEqual(fallback.call_count, 1)

    def test_unknown_region_never_receives_token(self):
        client = self.client()
        client.lcu.request.side_effect = None
        client.lcu.request.return_value = (200, {"currentPlatformId": "unknown-host"})
        with self.assertRaises(LcuError): client._credentials()
        client._http.get.assert_not_called()

    def test_credentials_cached_across_pages_and_refreshed_after_rejection(self):
        client = self.client()
        for start in (0, 20, 40):
            client.page("target", start)
        auth_calls = [c for c in client.lcu.request.call_args_list
                      if c.args[1].endswith("authorization")]
        self.assertEqual(len(auth_calls), 1)
        client._http.get.return_value = Mock(status_code=401)
        client._http.get.side_effect = None
        with self.assertRaises(LcuError):
            client.page("target", 60)
        auth_calls = [c for c in client.lcu.request.call_args_list
                      if c.args[1].endswith("authorization")]
        self.assertEqual(len(auth_calls), 2)

    def test_validation(self):
        client = self.client()
        self.assertFalse(client.page("target", 500)[1])
        client._http.get.assert_not_called()
        for start, count in [(-1, 20), (0, 500), (False, 20), (0, True)]:
            with self.assertRaises(LcuError): client.page("target", start, count)
        with self.assertRaises(LcuError): normalize_game({"json": {"gameId": 1}})
