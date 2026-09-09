import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from app import augments as A
from app.lcu import LcuClient
from app.query import game_detail, slim_game
from app.static_data import queue_name


class AugmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paths = patch.object(A, '_cache_paths', return_value=(
            str(Path(self.tmp.name) / 'writable.json'),
            str(Path(__file__).parents[1] / 'app/augments_cache.json')))
        self.paths.start()
        self.addCleanup(self.paths.stop)
        A._cache, A._last_attempt, A._client_port = None, None, None
        A._icons.clear()

    def test_live_metadata_and_authenticated_icon_win_over_cache(self):
        lcu = Mock(port=1234)
        lcu.request.return_value = (200, [{
            'id': 1007, 'nameTRA': '新版大力', 'rarity': 'kSilver',
            'augmentSmallIconPath': '/lol-game-data/assets/ASSETS/test.png'}])
        lcu.asset_data_url.return_value = 'data:image/png;base64,cG5n'
        with patch.object(A.requests, 'get') as remote:
            info = A.augment_info(1007, lcu)
            self.assertEqual(info['name'], '新版大力')
            self.assertTrue(info['icon'].startswith('data:image/png;'))
            self.assertEqual(A.augment_info(1007, lcu), info)
            lcu.asset_data_url.assert_called_once()
            lcu.request.assert_called_once()
            remote.assert_not_called()

    def test_offline_names_and_remote_icon_fallback(self):
        lcu = Mock(port=1234)
        lcu.request.return_value = (404, None)
        lcu.asset_data_url.return_value = ''
        with patch.object(A.requests, 'get', side_effect=requests.ConnectionError):
            info = A.augment_info(1007, lcu)
            self.assertEqual(info['name'], '大力')
            self.assertTrue(info['resolved'])
            self.assertTrue(info['icon'].endswith('/assets/ux/cherry/augments/icons/bluntforce_small.png'))
            self.assertFalse(A.augment_info(999999, lcu)['resolved'])

    def test_remote_metadata_fallback(self):
        response = Mock()
        response.json.return_value = [{'id': 9999, 'nameTRA': '新强化'}]
        with patch.object(A.requests, 'get', return_value=response):
            self.assertEqual(A.augment_info(9999)['name'], '新强化')

    def test_malformed_and_empty_slots_preserve_selection_order(self):
        self.assertEqual(A.clean_augments({'playerAugment1': '1007', 'playerAugment2': 0,
                                          'playerAugment3': 'bad', 'playerAugment4': -1,
                                          'playerAugment5': None, 'playerAugment6': 1006}), [1007, 1006])
        self.assertEqual(A.parse_augments([None, {}, {'id': 2, 'nameTRA': 4}]), {})

    def test_asset_transport_only_exposes_png(self):
        lcu = LcuClient()
        lcu.port = 1234
        response = Mock(ok=True, content=b'\x89PNG\r\n\x1a\nexample')
        with patch.object(lcu._session, 'get', return_value=response) as get:
            self.assertTrue(lcu.asset_data_url('/lol-game-data/assets/test.png').startswith('data:image/png;'))
            self.assertEqual(lcu.asset_data_url('https://example.com/image.png'), '')
            self.assertEqual(lcu.asset_data_url('/lol-game-data/assets/../secrets'), '')
            get.assert_called_once()
            response.content = b'<html>Error</html>'
            self.assertEqual(lcu.asset_data_url('/lol-game-data/assets/test.png'), '')

    def test_modes_dates_and_detail_augment_fields(self):
        for queue in (2400, '2400', 3270, '3270'):
            self.assertEqual(queue_name(queue, 'ARAM'), '海克斯大乱斗')
        self.assertEqual(queue_name(None, 'KIWI'), '海克斯大乱斗')
        g = {'gameCreationDate': '2026-09-09T00:00:00Z', 'gameMode': 'KIWI',
             'participants': [{'participantId': 1, 'teamId': 100,
                               'stats': {'playerAugment1': 1007}}]}
        self.assertEqual(slim_game(g)['creation'], g['gameCreationDate'])
        lcu = Mock()
        lcu.request.return_value = (200, g)
        with patch('app.query.augment_info', return_value={'id': 1007, 'name': '大力', 'icon': 'png'}) as info:
            detail = game_detail(lcu, 1)
            self.assertEqual(detail['teams'][0]['players'][0]['augments'][0]['icon'], 'png')
            info.assert_called_once_with(1007, lcu)


if __name__ == '__main__':
    unittest.main()
