import unittest
from unittest.mock import Mock

from app.query import match_page
from app.lcu import LcuError


class PaginationTests(unittest.TestCase):
    def client(self, size):
        client = Mock()
        client.request.return_value = (200, {"games": {"games": [
            {"gameId": i} for i in range(size)
        ]}})
        return client

    def test_partial_page_and_server_ignoring_count(self):
        client = self.client(20)
        games, more = match_page(client, "test", 40, 10)
        self.assertEqual(len(games), 10)
        self.assertTrue(more)
        self.assertEqual(client.request.call_args.kwargs["params"], {"begIndex": 40, "endIndex": 49})

    def test_limit_and_history_exhaustion(self):
        client = self.client(20)
        games, more = match_page(client, "test", 490)
        self.assertEqual(len(games), 10)
        self.assertFalse(more)
        client.request.reset_mock()
        self.assertEqual(match_page(client, "test", 500), ([], False))
        client.request.assert_not_called()
        self.assertFalse(match_page(self.client(3), "test", 20)[1])

    def test_invalid_arguments(self):
        for beg, count in [(-1, 20), (True, 20), (0, 21), (0, 0), (0, True), (0, "20")]:
            with self.assertRaises(LcuError):
                match_page(self.client(20), "test", beg, count)
