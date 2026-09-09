import unittest
from unittest.mock import Mock

from app.damage import DamageEvaluator, evaluate, rankings


def fixture():
    return {'gameMode': 'KIWI', 'queueId': 2400, 'gameDuration': 1200,
            'participants': [{'participantId': i, 'teamId': 100 if i <= 5 else 200,
                              'stats': {'totalDamageDealtToChampions': i * 1000}} for i in range(1, 11)],
            'participantIdentities': [{'participantId': 10, 'player': {'puuid': 'target'}},
                                      {'participantId': 5, 'player': {'puuid': 'team-top'}}]}


class DamageTests(unittest.TestCase):
    def test_top_means_all_ten_and_matches_puuid(self):
        g = fixture()
        self.assertTrue(evaluate(g, 'target')['isTop'])
        self.assertFalse(evaluate(g, 'team-top')['isTop'])
        self.assertEqual(evaluate(g, 'team-top')['rank'], 6)
        self.assertEqual(evaluate(g, 'other')['status'], 'unknown')

    def test_ties_and_zero_damage(self):
        g = fixture()
        g['participants'][4]['stats']['totalDamageDealtToChampions'] = 10000
        self.assertTrue(evaluate(g, 'team-top')['tied'])
        self.assertTrue(evaluate(g, 'target')['tied'])
        for p in g['participants']:
            p['stats']['totalDamageDealtToChampions'] = 0
        self.assertFalse(evaluate(g, 'target')['isTop'])

    def test_missing_or_corrupt_data_is_unknown(self):
        g = fixture()
        del g['participants'][0]['stats']['totalDamageDealtToChampions']
        self.assertEqual(evaluate(g, 'target')['status'], 'unknown')
        g = fixture(); g['participants'].pop()
        self.assertEqual(evaluate(g, 'target')['status'], 'unknown')
        g = fixture(); g['participants'][0]['stats']['totalDamageDealtToChampions'] = float('nan')
        self.assertEqual(evaluate(g, 'target')['status'], 'unknown')

    def test_remakes_and_other_modes(self):
        g = fixture(); g['gameDuration'] = 180
        g['participants'][0]['stats']['teamEarlySurrendered'] = True
        self.assertEqual(evaluate(g, 'target')['status'], 'remake')
        g = fixture(); g['gameMode'] = 'CHERRY'
        self.assertEqual(evaluate(g, 'target')['status'], 'unsupported')

    def test_success_cached_failures_retry_and_port_scoped(self):
        lcu = Mock(port=1234)
        lcu.request.side_effect = [(503, None), (200, fixture()), (200, fixture())]
        service = DamageEvaluator(lcu)
        self.assertEqual(service.get('target', 1)['status'], 'unknown')
        self.assertTrue(service.get('target', 1)['isTop'])
        self.assertTrue(service.get('target', 1)['isTop'])
        self.assertEqual(lcu.request.call_count, 2)
        lcu.port = 5678
        service.get('target', 1)
        self.assertEqual(lcu.request.call_count, 3)


if __name__ == '__main__':
    unittest.main()
