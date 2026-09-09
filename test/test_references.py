import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

from app import references as R
from app.query import slim_game

GLOBAL_PAGE = '''<p>Versus Patch 26.16</p><p>Current data: Patch 26.17</p>
<section data-augment-tier><button><span>T2</span></button>
<article><a href="/en/augments/1007">Blunt Force</a><span class="stat-value text-green">53.21%</span></article>
<article><a href="/en/augments/1006">Blade Waltz</a><span class="stat-value">—</span></article></section>'''


def champion_data():
    return {'championId': 266, 'championAugments': [['266', json.dumps({
        'augments': {'1007': {'tier': '1', 'win_rate': '0.5321', 'num_games': '1000'},
                     '1006': {'tier': '3', 'win_rate': None, 'num_games': None}},
        'match_history': {'game_patch': '16.17', 'date': '2026-09-07',
                          'region': 'WORLD', 'minimum_augment_games': 255}}), '2026-09-07', '16.17']]}


class ReferenceTests(unittest.TestCase):
    def test_global_parse_uses_current_patch_and_preserves_unknown_samples(self):
        result = R.parse_reference(GLOBAL_PAGE)
        self.assertEqual(result['patch'], '26.17')
        self.assertEqual(result['rows'], [{'id': 1007, 'tier': 'T2', 'winRate': 53.21, 'sampleSize': None}])
        with self.assertRaises(ValueError):
            R.parse_reference('<h1>Service unavailable</h1>')

    def test_champion_complete_json_metadata_and_missing_rates(self):
        result = R.parse_champion_reference(champion_data(), 266)
        self.assertEqual(len(result['rows']), 2)
        self.assertEqual(result['rows'][0]['winRate'], 53.21)
        self.assertEqual(result['rows'][0]['sampleSize'], 1000)
        self.assertIsNone(result['rows'][1]['winRate'])
        self.assertEqual(result['sourceUpdated'], '2026-09-07')
        self.assertEqual(result['patch'], '16.17')
        self.assertIn('WORLD', result['scope'])
        with self.assertRaises(ValueError):
            R.parse_champion_reference(champion_data(), 103)

    def test_cache_and_failed_refresh_do_not_fabricate_stats(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'reference.json'
            response = Mock(text=GLOBAL_PAGE)
            with patch.object(R, '_cache_path', return_value=path), patch.object(R.requests, 'get', return_value=response) as get:
                first = R.get_reference()
                self.assertFalse(first['cached'])
                second = R.get_reference()
                self.assertTrue(second['cached'])
                get.assert_called_once()
                get.side_effect = requests.ConnectionError
                stale = R.get_reference(force=True)
                self.assertTrue(stale['stale'])
                self.assertEqual(stale['rows'], first['rows'])
                path.unlink()
                with self.assertRaisesRegex(ValueError, '公开参考暂不可用'):
                    R.get_reference(force=True)

    def test_personal_match_selects_queried_identity(self):
        data = {'participants': [{'participantId': 1, 'championId': 266, 'stats': {'win': True}},
                                 {'participantId': 2, 'championId': 103, 'stats': {'win': False}}],
                'participantIdentities': [{'participantId': 2, 'player': {'puuid': 'target'}}]}
        result = slim_game(data, 'target')
        self.assertEqual(result['championId'], 103)
        self.assertFalse(result['win'])


if __name__ == '__main__':
    unittest.main()
