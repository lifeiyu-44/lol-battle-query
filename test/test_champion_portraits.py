import struct
import unittest
from pathlib import Path
from unittest.mock import Mock
from app import champions


class ChampionPortraitTests(unittest.TestCase):
    def test_every_bundled_champion_has_offline_image(self):
        lcu = Mock(port=123)
        for cid in champions.get_champion_map():
            with self.subTest(champion=cid):
                url = champions.champion_avatar(cid, lcu)
                self.assertEqual(url, "champion-icons/{}.png".format(cid))
                raw = (Path('app/ui') / url).read_bytes()
                self.assertTrue(raw.startswith(b'\x89PNG\r\n\x1a\n'))
                self.assertGreaterEqual(min(struct.unpack('>II', raw[16:24])), 32)
        lcu.asset_data_url.assert_not_called()
