"""腾讯 SGP 完整历史分页；LCU 的最近战绩缓存不代表历史总数。"""
from collections import OrderedDict
import threading
from urllib.parse import quote

import requests

from . import query as Q
from .damage import evaluate
from .lcu import LcuError

# Verified against LeagueAkari-Config/config/sgp/league-servers.json on 2026-09-09.
# Only these fixed Tencent hosts receive the current client's access token.
SERVERS = {
    "HN1": "hn1-k8s-sgp", "HN10": "hn10-k8s-sgp", "BGP2": "bgp2-k8s-sgp",
    "NJ100": "nj100-sgp", "GZ100": "gz100-sgp", "CQ100": "cq100-sgp",
    "TJ100": "tj100-sgp", "TJ101": "tj101-sgp", "PBE": "pbe-sgp", "PREPBE": "prepbe-sgp",
}


def normalize_game(row):
    """SGP 平铺玩家字段转为业务层使用的 LCU 形状，不猜测查询玩家。"""
    data = row.get("json") if isinstance(row, dict) else None
    if not isinstance(data, dict) or not data.get("gameId") or not isinstance(data.get("participants"), list):
        raise LcuError("扩展战绩数据格式异常")
    fields = ["kills", "deaths", "assists", "win", "champLevel", "totalMinionsKilled",
              "neutralMinionsKilled", "goldEarned", "totalDamageDealtToChampions", "lane", "role",
              "teamEarlySurrendered"] + ["item{}".format(i) for i in range(7)] + ["playerAugment{}".format(i) for i in range(1, 7)]
    players, identities = [], []
    for p in data["participants"]:
        stats = {k: p[k] for k in fields if k in p}
        if "teamEarlySurrendered" not in stats and "gameEndedInEarlySurrender" in p:
            stats["teamEarlySurrendered"] = p["gameEndedInEarlySurrender"]
        players.append({"participantId": p.get("participantId"), "puuid": p.get("puuid"),
                        "teamId": p.get("teamId"), "championId": p.get("championId"), "stats": stats})
        identities.append({"participantId": p.get("participantId"), "player": {
            "puuid": p.get("puuid"), "summonerId": p.get("summonerId"),
            "gameName": p.get("riotIdGameName") or p.get("summonerName") or "",
            "tagLine": p.get("riotIdTagline") or p.get("riotIdTagLine") or ""}})
    return {k: data.get(k) for k in ("gameId", "gameCreation", "gameDuration", "gameMode", "queueId", "mapId", "platformId")} | {
        "participants": players, "participantIdentities": identities}


class _AuthRejected(Exception):
    """SGP 返回 401/403：缓存的令牌失效，需要重取一次。"""


class HistoryClient:
    def __init__(self, lcu):
        self.lcu = lcu
        self._http = requests.Session()
        self._http.trust_env = False
        self._games = OrderedDict()
        self._lock = threading.Lock()
        self._auth_lock = threading.Lock()
        self._auth = None  # (lcu.port, region, token)，客户端重启换端口后自动失效

    def _credentials(self):
        port = self.lcu.port
        with self._auth_lock:
            if self._auth and self._auth[0] == port:
                return self._auth[1], self._auth[2]
        code, auth = self.lcu.request("GET", "/lol-rso-auth/v1/authorization", timeout=3)
        region = auth.get("currentPlatformId") if code == 200 and isinstance(auth, dict) else None
        if region not in SERVERS:
            raise LcuError("当前大区暂不支持扩展战绩接口")
        code, data = self.lcu.request("GET", "/entitlements/v1/token", timeout=3)
        token = data.get("accessToken") if code == 200 and isinstance(data, dict) else None
        if not token:
            raise LcuError("客户端尚未提供战绩查询授权，请重新登录客户端")
        with self._auth_lock:
            self._auth = (port, region, token)
        return region, token

    def _forget_credentials(self):
        with self._auth_lock:
            self._auth = None

    def _request(self, region, token, puuid, start, count):
        url = "https://{}.lol.qq.com:21019/match-history-query/v1/products/lol/player/{}/SUMMARY".format(
            SERVERS[region], quote(puuid, safe=""))
        try:
            response = self._http.get(url, params={"startIndex": start, "count": count},
                headers={"Authorization": "Bearer " + token}, timeout=12, allow_redirects=False)
        except requests.RequestException:
            # 不将请求对象、令牌或带玩家身份的 URL 放入异常/日志。
            raise LcuError("扩展战绩连接失败，请稍后重试") from None
        if response.status_code in (401, 403):
            raise _AuthRejected
        if response.status_code != 200:
            raise LcuError("扩展战绩接口暂不可用（HTTP {}），请重试".format(response.status_code))
        try:
            result = response.json()
        except ValueError:
            raise LcuError("扩展战绩返回了无效数据") from None
        if not isinstance(result, dict) or not isinstance(result.get("games"), list):
            raise LcuError("扩展战绩缺少对局列表")
        return result["games"][:count]

    def page(self, puuid, start, count=20):
        if (not isinstance(puuid, str) or not puuid or isinstance(start, bool)
                or not isinstance(start, int) or start < 0 or isinstance(count, bool)
                or not isinstance(count, int) or not 1 <= count <= 20):
            raise LcuError("战绩分页参数无效")
        if start >= 500:
            return [], False, "sgp", ""
        count = min(count, 500 - start)
        try:
            region, token = self._credentials()
            try:
                rows = self._request(region, token, puuid, start, count)
            except _AuthRejected:
                # 令牌被拒（重新登录/切换大区）只重取一次，再被拒按普通失败上报。
                self._forget_credentials()
                region, token = self._credentials()
                try:
                    rows = self._request(region, token, puuid, start, count)
                except _AuthRejected:
                    raise LcuError("扩展战绩授权已过期，请重启客户端后重试") from None
            raw = [normalize_game(row) for row in rows]
            games = [Q.slim_game(g, puuid) for g in raw]
        except LcuError as e:
            if start != 0:
                raise
            games, more = Q.match_page(self.lcu, puuid, start, count)
            return games, more, "lcu", "{}；当前仅显示客户端缓存，不能据此判断历史总数".format(e)
        with self._lock:
            for game, data in zip(games, raw):
                game["damageEvaluation"] = evaluate(data, puuid)
                key = (self.lcu.port, puuid, game["gameId"])
                self._games[key] = data
                self._games.move_to_end(key)
            while len(self._games) > 1000:
                self._games.popitem(last=False)
        return games, len(games) == count and start + count < 500, "sgp", ""

    def cached_game(self, puuid, game_id):
        with self._lock:
            return self._games.get((self.lcu.port, puuid, game_id))
