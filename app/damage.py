"""用完整十人数据评价对英雄伤害，缺失字段不当作零伤害。"""
from collections import OrderedDict
import math
import threading


def rankings(game):
    participants = game.get("participants") or []
    if game.get("gameMode") in ("CHERRY", "ARENA", "TFT") or game.get("queueId") in (1700, 1710):
        return {"status": "unsupported", "reason": "此模式不使用十人伤害评价"}, {}
    if (len(participants) != 10
            or sum(p.get("teamId") == 100 for p in participants) != 5
            or sum(p.get("teamId") == 200 for p in participants) != 5):
        return {"status": "unknown", "reason": "未取得完整十人数据，无法确认全场伤害最高"}, {}
    ids = [p.get("participantId") for p in participants]
    if None in ids or len(set(ids)) != 10:
        return {"status": "unknown", "reason": "参与者身份数据不完整"}, {}
    damage = {}
    for p in participants:
        value = (p.get("stats") or {}).get("totalDamageDealtToChampions")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            return {"status": "unknown", "reason": "十人伤害数据不完整"}, {}
        damage[p["participantId"]] = value
    maximum = max(damage.values())
    ties = sum(v == maximum for v in damage.values())
    results = {}
    team_by_player = {p["participantId"]: p["teamId"] for p in participants}
    team_totals = {team: sum(damage[p["participantId"]] for p in participants if p["teamId"] == team)
                   for team in (100, 200)}
    for pid, value in damage.items():
        team_total = team_totals[team_by_player[pid]]
        results[pid] = {"status": "ok", "damage": value, "maxDamage": maximum,
                        "teamDamage": team_total, "teamShare": value * 100 / team_total if team_total > 0 else None,
                        "rank": 1 + sum(v > value for v in damage.values()),
                        "isTop": value == maximum and maximum > 0,
                        "tied": value == maximum and ties > 1 and maximum > 0,
                        "players": 10}
    return {"status": "ok"}, results


def evaluate(game, puuid):
    seconds = game.get("gameDuration") or 0
    seconds = seconds / 1000 if seconds > 10000 else seconds
    if seconds < 300 and any((p.get("stats") or {}).get("teamEarlySurrendered")
                             for p in game.get("participants") or []):
        return {"status": "remake", "reason": "重开不计入评价"}
    status, rows = rankings(game)
    if status["status"] != "ok":
        return status
    identities = {p.get("participantId"): (p.get("player") or {}).get("puuid")
                  for p in game.get("participantIdentities") or []}
    targets = [p for p in game.get("participants") or [] if puuid and puuid in (
        p.get("puuid"), (p.get("stats") or {}).get("puuid"), identities.get(p.get("participantId")))]
    if len(targets) != 1:
        return {"status": "unknown", "reason": "未能准确识别被查询玩家"}
    return rows[targets[0]["participantId"]]


class DamageEvaluator:
    def __init__(self, lcu):
        self.lcu = lcu
        self.cache = OrderedDict()
        self.lock = threading.Lock()

    def get(self, puuid, game_id):
        key = (self.lcu.port, puuid, game_id)
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
        try:
            code, game = self.lcu.request("GET", "/lol-match-history/v1/games/{}".format(game_id), timeout=4)
            if code != 200 or not isinstance(game, dict):
                return {"status": "unknown", "reason": "伤害详情暂不可用，可重试"}
            result = evaluate(game, puuid)
        except Exception:
            return {"status": "unknown", "reason": "读取伤害详情失败，可重试"}
        if result["status"] != "unknown":
            with self.lock:
                self.cache[key] = result
                while len(self.cache) > 2000:
                    self.cache.popitem(last=False)
        return result
