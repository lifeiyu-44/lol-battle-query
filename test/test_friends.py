import unittest
from unittest.mock import Mock

from app.friends import FriendDirectory, friend_status


class FriendTests(unittest.TestCase):
    def test_current_account_self_friend_and_nonfriend(self):
        lcu = Mock(port=1234)
        lcu.request.side_effect = [(200, {'puuid': 'me', 'summonerId': 1}),
                                  (200, [{'puuid': 'friend', 'summonerId': 2, 'relationshipOnRiot': 'friend'},
                                         {'puuid': 'pending', 'relationshipOnRiot': 'pending'}])]
        snap = FriendDirectory(lcu).snapshot()
        self.assertEqual(friend_status(snap, 'me'), 'self')
        self.assertEqual(friend_status(snap, 'friend'), 'friend')
        self.assertEqual(friend_status(snap, '', 2), 'friend')
        self.assertEqual(friend_status(snap, 'pending'), 'not_friend')
        self.assertEqual(friend_status(snap, 'other'), 'not_friend')
        self.assertEqual(friend_status(snap), 'unknown')

    def test_unavailable_friends_never_means_nonfriend(self):
        lcu = Mock(port=1234)
        lcu.request.side_effect = [(200, {'puuid': 'me'}), (503, None)]
        snap = FriendDirectory(lcu).snapshot()
        self.assertEqual(friend_status(snap, 'me'), 'self')
        self.assertEqual(friend_status(snap, 'someone'), 'unknown')

    def test_cached_list_is_not_reused_after_account_switch(self):
        lcu = Mock(port=1234)
        lcu.request.side_effect = [(200, {'puuid': 'account1'}), (200, [{'puuid':'friend1'}]),
                                  (200, {'puuid': 'account1'}),
                                  (200, {'puuid': 'account2'}), (200, [])]
        directory = FriendDirectory(lcu)
        self.assertEqual(friend_status(directory.snapshot(), 'friend1'), 'friend')
        self.assertEqual(friend_status(directory.snapshot(), 'friend1'), 'friend')
        self.assertEqual(friend_status(directory.snapshot(), 'friend1'), 'not_friend')
        self.assertEqual(lcu.request.call_count, 5)


if __name__ == '__main__':
    unittest.main()
