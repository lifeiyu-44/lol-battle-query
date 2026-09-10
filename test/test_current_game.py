import os
import tempfile
import unittest
from urllib.parse import quote
from unittest.mock import Mock, patch

from app import current_game as C
from app.main import Api
from app.lcu import LcuError


class CurrentGameTests(unittest.TestCase):
    def test_public_draft_picks_and_confirmed_bans(self):
        data = C.draft_data({
            "myTeam": [{"cellId": 0, "summonerId": 11, "championPickIntent": 266},
                       {"cellId": 1, "summonerId": 12, "championId": 103}],
            "theirTeam": [{"cellId": 5, "summonerId": 21, "championPickIntent": 17},
                          {"cellId": 6, "summonerId": 22}],
            "bans": {"myTeamBans": [0, -1, 11, 11], "theirTeamBans": [22]},
            "actions": [[{"type": "pick", "actorCellId": 1, "championId": 12, "completed": True},
                         {"type": "pick", "actorCellId": 5, "championId": 17, "isInProgress": True},
                         {"type": "pick", "actorCellId": 6, "championId": 99, "completed": True},
                         {"type": "ban", "actorCellId": 0, "championId": 13, "completed": False},
                         {"type": "ban", "actorCellId": 6, "championId": 44, "completed": True}]]})
        overlay = data["draftOverlay"]
        self.assertEqual(overlay["11"], {"championId": 266, "pickState": "预选"})
        self.assertEqual(overlay["12"], {"championId": 103, "pickState": "已锁定"})  # 换英雄后的结果
        # 对手进行中的选择不公开；只有锁定后才可见。
        self.assertEqual(overlay["21"], {"championId": 0, "pickState": "待选择 / 尚未公开"})
        self.assertEqual(overlay["22"], {"championId": 99, "pickState": "已锁定"})
        self.assertEqual(data["draftOwnSummoners"], ["11", "12"])
        self.assertEqual(len(data["teamOneDraft"]), 2)
        self.assertEqual(len(data["teamTwoDraft"]), 2)
        self.assertEqual(data["teamOneBans"], [11])
        self.assertEqual(data["teamTwoBans"], [22, 44])

    def test_draft_revision_changes_with_champion_and_bans(self):
        def inspect(champion, bans):
            lcu = Mock()
            lcu.request.side_effect = [(200, "ChampSelect"), (200, {"gameData": {}}),
                (200, {"gameId": 12, "queueId": 420,
                       "myTeam": [{"cellId": 0, "summonerId": 7, "championId": champion}],
                       "bans": {"myTeamBans": bans}})]
            return C.inspect(lcu)[0]
        initial = inspect(266, [])
        self.assertEqual(initial["revision"], inspect(266, [])["revision"])
        self.assertNotEqual(initial["revision"], inspect(103, [])["revision"])
        self.assertNotEqual(initial["revision"], inspect(266, [17])["revision"])

    def test_draft_revision_changes_when_enemy_locks(self):
        def inspect(their_champion):
            lcu = Mock()
            lcu.request.side_effect = [(200, "ChampSelect"), (200, {"gameData": {}}),
                (200, {"gameId": 5,
                       "myTeam": [{"cellId": 0, "summonerId": 1}],
                       "theirTeam": [{"cellId": 5, "summonerId": 2, "championId": their_champion}]})]
            return C.inspect(lcu)[0]
        self.assertEqual(inspect(17)["revision"], inspect(17)["revision"])
        # 对方名单与英雄都没变时不变；锁定英雄必须触发刷新。
        self.assertNotEqual(inspect(0)["revision"], inspect(17)["revision"])

    def test_champ_select_uses_selection_id_and_roster(self):
        lcu = Mock()
        lcu.request.side_effect = [(200, "ChampSelect"), (200, {"gameData": {
            "gameId": 0, "queue": {"id": 4320}, "teamOne": [], "teamTwo": []}}),
            (200, {"gameId": 123, "queueId": 2400, "myTeam": [{"puuid": "self", "championId": 266}], "theirTeam": []})]
        status, data = C.inspect(lcu)
        self.assertTrue(status["active"])
        self.assertEqual(status["key"], "123:")
        self.assertEqual(status["phase"], "ChampSelect")
        self.assertEqual(status["mode"], "海克斯大乱斗")
        lcu.request.side_effect = None
        lcu.request.return_value = (404, None)
        result = C.roster(lcu, status, data, "self")
        self.assertEqual(result["teams"][0]["label"], "我方")
        self.assertEqual(result["teams"][0]["players"][0]["championId"], 266)
        self.assertEqual(result["teams"][1]["players"], [])
        self.assertIn("正在选择英雄", result["note"])

    def test_champ_select_keeps_enemy_roster_and_merges_picks(self):
        """大乱斗选人阶段：gameflow 名单不被选人数据替换，对方名单与英雄保留。"""
        lcu = Mock()
        lcu.request.side_effect = [
            (200, "ChampSelect"),
            (200, {"gameData": {"gameId": 9, "queue": {"id": 450},
                "teamOne": [{"puuid": "a1", "summonerId": 1, "gameName": "甲"},
                            {"puuid": "a2", "summonerId": 2, "gameName": "乙"}],
                "teamTwo": [{"puuid": "b1", "summonerId": 3, "gameName": "丙"},
                            {"puuid": "b2", "summonerId": 4, "gameName": "丁"}],
                "playerChampionSelections": [{"puuid": "a1", "championId": 103},
                                              {"puuid": "b1", "championId": 266}]}}),
            (200, {"gameId": 9, "queueId": 450, "myTeam": [
                    {"cellId": 0, "summonerId": 1, "championId": 103},
                    {"cellId": 1, "summonerId": 2, "championId": 0}],
                "theirTeam": []})]
        status, data = C.inspect(lcu)
        self.assertTrue(data["teamTwo"])  # 对方名单没有被清空
        lcu.request.side_effect = None
        lcu.request.return_value = (404, None)
        result = C.roster(lcu, status, data, "a1")
        mine, foe = result["teams"]
        self.assertEqual([t["label"] for t in result["teams"]], ["我方", "对手"])
        self.assertEqual(mine["players"][0]["championId"], 103)  # 选人数据按 summonerId 叠加
        self.assertEqual(mine["players"][1]["championId"], 0)
        self.assertEqual(foe["players"][0]["puuid"], "b1")
        self.assertEqual(foe["players"][0]["name"], "丙")
        self.assertEqual(foe["players"][0]["championId"], 266)  # 来自 gameflow 选人数据
        self.assertEqual(foe["players"][1]["championId"], 0)
        # 404 档案查询下名字仍来自 gameflow 名单，证明身份未被选人数据替换。
        self.assertEqual(foe["players"][0]["name"], "丙")

    def test_draft_enemy_lock_applies_to_roster(self):
        """排位选人：对方锁定英雄后，叠加到 gameflow 名单并标注已锁定。"""
        lcu = Mock()
        lcu.request.side_effect = [
            (200, "ChampSelect"),
            (200, {"gameData": {"gameId": 77, "queue": {"id": 420}, "teamOne": [],
                "teamTwo": [{"puuid": "e1", "summonerId": 31, "gameName": "对手甲"}]}}),
            (200, {"gameId": 77, "queueId": 420,
                   "myTeam": [{"cellId": 0, "summonerId": 41, "championId": 266}],
                   "theirTeam": [{"cellId": 5, "summonerId": 31, "championId": 17}],
                   "actions": [[{"type": "pick", "actorCellId": 5, "championId": 17, "completed": True}]]})]
        status, data = C.inspect(lcu)
        lcu.request.side_effect = None
        lcu.request.return_value = (404, None)
        result = C.roster(lcu, status, data, None)
        self.assertEqual(result["draft"], True)
        foe = result["teams"][1]["players"][0]
        self.assertEqual(foe["championId"], 17)
        self.assertEqual(foe["pickState"], "已锁定")
        self.assertEqual(foe["name"], "对手甲")

    def test_champ_select_waiting_for_session_is_explicit(self):
        lcu = Mock()
        lcu.request.side_effect = [(200, "ChampSelect"), (200, {"gameData": {}}), (404, None)]
        with self.assertRaisesRegex(LcuError, "选人名单"):
            C.inspect(lcu)

    def test_status_and_inactive_session(self):
        lcu = Mock()
        lcu.request.return_value = (200, "Lobby")
        status, data = C.inspect(lcu)
        self.assertFalse(status["active"])
        self.assertIsNone(data)
        # 大厅阶段会额外查一次大厅，用于识别自定义房间。
        self.assertEqual(lcu.request.call_count, 2)
        lcu.request.side_effect = [(200, "InProgress"), (200, {"gameData": {"gameId": 1, "queue": {"id": 2400}}})]
        status, _ = C.inspect(lcu)
        self.assertEqual(status["mode"], "海克斯大乱斗")
        self.assertEqual(status["key"], "1:")
        lcu.request.side_effect = [(200, "InProgress"), (404, None)]
        with self.assertRaises(LcuError): C.inspect(lcu)

    def test_roster_red_side_and_selection_champions(self):
        lcu = Mock()
        lcu.request.return_value = (404, None)
        data = {"queue": {"id": 2400}, "teamOne": [{"puuid": "enemy"}],
                "teamTwo": [{"puuid": "self", "summonerName": "本人"}],
                "playerChampionSelections": [{"puuid": "self", "championId": 266}]}
        result = C.roster(lcu, {"active": True}, data, "self")
        self.assertEqual(result["teams"][0]["label"], "我方")
        self.assertEqual(result["teams"][0]["teamId"], 200)
        self.assertEqual(result["teams"][0]["players"][0]["championId"], 266)
        self.assertEqual(result["teams"][1]["label"], "对手")
        self.assertIn("尚未完整", result["note"])
        result = C.roster(lcu, {"active": True}, data, "observer")
        self.assertEqual([t["label"] for t in result["teams"]], ["蓝方", "红方"])

    def test_roster_fills_bot_side_from_live_data(self):
        """人机对局：gameflow 不给对方名单时，用游戏客户端 Live 数据补齐。"""
        from unittest.mock import patch
        lcu = Mock()
        lcu.request.return_value = (404, None)
        data = {"queue": {"id": 880},
                "teamOne": [{"puuid": "me", "summonerId": 5, "gameName": "本人"}],
                "teamTwo": [], "playerChampionSelections": []}
        live = [{"gameName": "星籁歌姬（电脑）", "championName": "黑暗之女", "team": "CHAOS",
                 "isBot": True, "position": "BOTTOM"}]
        with patch("app.current_game.live_players", return_value=live):
            result = C.roster(lcu, {"active": True, "phase": "InProgress"}, data, "me")
        foe = result["teams"][1]["players"]
        self.assertEqual(len(foe), 1)
        self.assertEqual(foe[0]["name"], "星籁歌姬（电脑）")
        self.assertEqual(foe[0]["championId"], 1)  # 展示名"黑暗之女"映射回英雄 ID
        self.assertTrue(foe[0]["isBot"])
        self.assertEqual(foe[0]["puuid"], "")  # 电脑无身份，不猜
        mine, foe_team = result["teams"]
        self.assertEqual([t["label"] for t in result["teams"]], ["我方", "对手"])

    def test_live_fill_only_after_game_start(self):
        from unittest.mock import patch
        lcu = Mock()
        lcu.request.return_value = (404, None)
        data = {"queue": {"id": 880}, "teamOne": [{"puuid": "me"}], "teamTwo": []}
        with patch("app.current_game.live_players",
                   return_value=[{"gameName": "x", "championName": "黑暗之女",
                                  "team": "CHAOS", "isBot": True}]) as fetch:
            result = C.roster(lcu, {"active": True, "phase": "ChampSelect"}, data, "me")
            fetch.assert_not_called()  # 选人阶段游戏端接口尚不存在
            self.assertEqual(result["teams"][1]["players"], [])

    def test_live_fill_failure_keeps_roster(self):
        from unittest.mock import patch
        lcu = Mock()
        lcu.request.return_value = (404, None)
        data = {"queue": {"id": 880}, "teamOne": [{"puuid": "me"}], "teamTwo": []}
        with patch("app.current_game.live_players", return_value=None):
            result = C.roster(lcu, {"active": True, "phase": "InProgress"}, data, "me")
        self.assertEqual(result["teams"][1]["players"], [])
        self.assertIn("名单尚未完整公开", result["note"])

    def test_custom_lobby_exposes_both_teams_before_champ_select(self):
        """自定义房间：选人前就能看到双方全部成员，并正确标注我方/对手。"""
        lcu = Mock()
        lcu.request.side_effect = [
            (200, "Lobby"),
            (200, {"lobbyId": "abc",
                   "gameConfig": {"gameType": "CUSTOM_GAME", "queueId": 0, "mapId": 11,
                                  "gameMode": "CLASSIC", "teamSize": 5},
                   "localMember": {"summonerId": 1, "teamId": 100},
                   "members": [
                       {"summonerId": 1, "puuid": "me", "gameName": "本人", "tagLine": "CN1", "teamId": 100},
                       {"summonerId": 2, "puuid": "mate", "gameName": "队友", "teamId": 1},
                       {"summonerId": 3, "puuid": "foe", "gameName": "对手甲", "tagLine": "CN1", "teamId": 200},
                       {"summonerId": 4, "gameName": "旁观", "teamId": 200, "isSpectator": True},
                   ]}),
        ]
        status, data = C.inspect(lcu)
        self.assertTrue(status["active"])
        self.assertEqual(status["phase"], "Lobby")
        self.assertFalse(status["notify"])  # 大厅不弹窗
        self.assertEqual(status["mode"], "自定义 · 召唤师峡谷")
        self.assertTrue(data["customLobby"])
        lcu.request.side_effect = None
        lcu.request.return_value = (404, None)
        result = C.roster(lcu, status, data, "me")
        self.assertEqual([t["label"] for t in result["teams"]], ["我方", "对手"])
        mine, foe = result["teams"]
        self.assertEqual([p["name"] for p in mine["players"]], ["本人", "队友"])  # teamId 1 归一化到 100
        self.assertEqual([p["name"] for p in foe["players"]], ["对手甲"])
        self.assertNotIn("旁观", [p["name"] for p in foe["players"]])
        self.assertIn("自定义房间", result["note"])

    def test_matchmaking_lobby_is_not_exposed_as_opponents(self):
        """匹配/排位大厅只有自己的队伍，不按“双方”展示，避免误导。"""
        lcu = Mock()
        lcu.request.side_effect = [
            (200, "Lobby"),
            (200, {"gameConfig": {"gameType": "MATCHMAKING", "queueId": 420},
                   "members": [{"summonerId": 1, "teamId": 100}]}),
        ]
        status, data = C.inspect(lcu)
        self.assertFalse(status["active"])
        self.assertIsNone(data)

    def test_custom_lobby_without_members_is_inactive(self):
        lcu = Mock()
        lcu.request.side_effect = [
            (200, "Lobby"),
            (200, {"gameConfig": {"gameType": "CUSTOM_GAME", "queueId": 0}, "members": []}),
        ]
        status, data = C.inspect(lcu)
        self.assertFalse(status["active"])
        self.assertIsNone(data)

    def test_notice_position_is_remembered_and_off_screen_is_dropped(self):
        """弹窗位置：拖动后记住、重启沿用；换显示器导致跑到屏幕外则丢弃。"""
        bounds = [(0, 0, 1920, 1080)]
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"LOCALAPPDATA": tmp}):
            api = Api()
            api._remember_notice_position(400, 260)   # 用户拖动弹窗
            api._notice_position = None               # 模拟重启，只保留磁盘上的记录
            with patch("app.main._screen_bounds", return_value=bounds):
                self.assertEqual(api._load_notice_position(), (400, 260))
                api._write_notice_position(5000, 5000)  # 屏幕外
                api._notice_position = None
                self.assertIsNone(api._load_notice_position())

    def test_identity_privacy_and_conflict(self):
        lcu = Mock()
        unknown = C.resolve_player(lcu, {"puuid": "00000000-0000-0000-0000-000000000000", "summonerId": 0})
        self.assertEqual(unknown["puuid"], "")
        lcu.request.assert_not_called()
        self.assertEqual(C.resolve_player(lcu, {"isBot": True, "puuid": "bot"})["puuid"], "")
        lcu.request.return_value = (200, {"puuid": "wrong", "gameName": "错误玩家"})
        self.assertEqual(C.resolve_player(lcu, {"puuid": "right"})["puuid"], "right")
        lcu.request.return_value = (200, {"puuid": "right", "summonerId": 8, "gameName": "玩家", "tagLine": "CN"})
        self.assertEqual(C.resolve_player(lcu, {"summonerId": 8})["tagLine"], "CN")
        self.assertEqual(C.resolve_player(lcu, {"summonerId": 9})["puuid"], "")

    def test_unsupported_team_format(self):
        result = C.roster(Mock(), {"active": True}, {"queue": {"id": 1700}}, "self")
        self.assertEqual(result["teams"], [])
        self.assertIn("不支持", result["note"])

    @patch('app.main.webview.create_window')
    def test_notification_once_close_and_open(self, create):
        api = Api()
        api._main_window = Mock()
        self.assertTrue(api.notify_current_game("1", "<测试>")["ok"])
        self.assertIn("&lt;测试&gt;", create.call_args.kwargs["html"])
        api.close_game_notice()
        api.notify_current_game("1", "测试")
        self.assertEqual(create.call_count, 1)
        api.notify_current_game("2", "测试")
        self.assertEqual(create.call_count, 2)
        api.show_current_game()
        api._main_window.restore.assert_called_once()
        api._main_window.evaluate_js.assert_called_with("CurrentGame.open()")


class TeamReviewTests(unittest.TestCase):
    def test_champ_select_conversation_matching(self):
        self.assertEqual(C.champ_select_conversation([
            {"id": "party@pvp.net", "gameConversationType": None},
            {"id": "cs1", "gameConversationType": "champSelect"}]), "cs1")
        # 字段缺失时按 ID 特征兜底。
        self.assertEqual(C.champ_select_conversation([{"id": "champ-select:5:1"}]), "champ-select:5:1")
        self.assertIsNone(C.champ_select_conversation([{"id": "party@pvp.net"}]))
        self.assertIsNone(C.champ_select_conversation(None))

    def test_send_review_in_champ_select(self):
        lcu = Mock()
        lcu.request.side_effect = [
            (200, "ChampSelect"),
            (200, [{"id": "party@pvp.net", "gameConversationType": None},
                   {"id": "cs:1", "gameConversationType": "champSelect"}]),
            (200, None), (200, None)]
        with patch("app.current_game.time.sleep"):
            result = C.send_team_review(lcu, ["标题", " 1. 甲 ", ""])
        self.assertEqual(result, {"phase": "ChampSelect", "sent": 2})
        post_calls = [c for c in lcu.request.call_args_list if c[0][0] == "POST"]
        self.assertEqual(len(post_calls), 2)
        self.assertIn(quote("cs:1", safe=""), post_calls[0][0][1])
        self.assertEqual(post_calls[0][1]["body"], {"body": "标题", "type": "chat"})
        self.assertEqual(post_calls[1][1]["body"], {"body": "1. 甲", "type": "chat"})

    def test_send_review_in_game_uses_team_channel(self):
        lcu = Mock()
        lcu.request.side_effect = [(200, "InProgress"), (200, None), (200, None), (200, None)]
        with patch("app.current_game.time.sleep"):
            result = C.send_team_review(lcu, ["一", "二", "三"])
        self.assertEqual(result, {"phase": "InProgress", "sent": 3})
        posts = [c for c in lcu.request.call_args_list if c[0][0] == "POST"]
        self.assertEqual(posts[0][0][1], "/lol-game-client-chat/v1/instant-messages")
        self.assertEqual(posts[0][1]["body"], {"body": "一", "recipient": "team"})

    def test_send_review_falls_back_to_game_conversation(self):
        """对局内聊天接口缺失（404）时，回退到对局聊天室会话。"""
        lcu = Mock()
        lcu.request.side_effect = [
            (200, "GameStart"), (404, None),
            (200, [{"id": "game1", "gameConversationType": "activeGame"}]),
            (200, None)]
        with patch("app.current_game.time.sleep"):
            result = C.send_team_review(lcu, ["唯一一条"])
        self.assertEqual(result, {"phase": "GameStart", "sent": 1})
        posts = [c for c in lcu.request.call_args_list if c[0][0] == "POST"]
        self.assertEqual(posts[0][0][1], "/lol-game-client-chat/v1/instant-messages")
        self.assertIn("game1", posts[1][0][1])
        self.assertEqual(posts[1][1]["body"], {"body": "唯一一条", "type": "chat"})

    def test_send_review_rejects_bad_input_and_phase(self):
        lcu = Mock()
        lcu.request.return_value = (200, "Lobby")
        with self.assertRaises(LcuError):
            C.send_team_review(lcu, [])
        with self.assertRaises(LcuError):
            C.send_team_review(lcu, ["第{}条".format(i) for i in range(10)])
        with self.assertRaises(LcuError):
            C.send_team_review(lcu, ["大厅阶段不能发"])
        lcu.request.assert_called_once()  # 空内容/条数超限在请求前就被拦下

    def test_send_review_truncates_long_lines(self):
        lcu = Mock()
        lcu.request.side_effect = [(200, "InProgress"), (200, None)]
        with patch("app.current_game.time.sleep"):
            C.send_team_review(lcu, ["x" * 500])
        post = next(c for c in lcu.request.call_args_list if c[0][0] == "POST")
        self.assertEqual(len(post[1]["body"]["body"]), C.REVIEW_MAX_CHARS)

    def test_api_send_team_review_shapes(self):
        api = Api()
        api.lcu = Mock()
        api.lcu.connected = True
        api.lcu.request.side_effect = [(200, "Lobby")]
        failed = api.send_team_review(["x"])
        self.assertFalse(failed["ok"])
        self.assertIn("不在选人或对局中", failed["error"])
        api.lcu.request.side_effect = [(200, "InProgress"), (200, None)]
        with patch("app.current_game.time.sleep"):
            ok = api.send_team_review(["x"])
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["sent"], 1)
