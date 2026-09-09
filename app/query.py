# -*- coding: utf-8 -*-
"""战绩查询业务层：按 ID 查人、战绩分页、单局详情、汇总统计。"""
from urllib.parse import quote

from .static_data import queue_name
from .lcu import LcuError

PAGE_SIZE = 20
MAX_TOTAL = 2000  # 防御性上限，避免无限拉取


def find_summoner(lcu, query):
    """按玩家输入查召唤师。支持「名字」与「名字#Tag」两种格式。

    国服客户端接口随版本演进，这里按优先级尝试多条接口链，
    全部失败时给出明确错误。
    """
    query = (query or "").strip()
    if not query:
        raise LcuError("请输入要查询的玩家 ID。")

    tried = []

    if "#" in query:
        name, _, tag = query.partition("#")
        name, tag = name.strip(), tag.strip()
        if name and tag:
            code, data = lcu.request(
                "GET",
                "/lol-summoner/v1/summoners-by-riot-id/{}/{}".format(
                    quote(name), quote(tag)
                ),
            )
            if code == 200 and data and data.get("puuid"):
                return _norm_summoner(data)
            tried.append("RiotID 查询(#{})".format(tag))

    # 当前大区按名字精确查询
    code, data = lcu.request("GET", "/lol-summoner/v1/summoners", params={"name": query})
    if code == 200 and data and data.get("puuid"):
        return _norm_summoner(data)
    tried.append("本大区精确查询")

    # 国服客户端按名字搜索（接口名随版本变化，做一次尝试）
    code, data = lcu.request(
        "GET", "/lol-summoner/v1/summoners-by-name", params={"name": query}
    )
    if code == 200 and data and data.get("puuid"):
        return _norm_summoner(data)
    tried.append("按名字搜索")

    raise LcuError(
        "未找到玩家「{}」。可能原因：① ID 拼写有误；② 对方不在你当前登录的大区"
        "（跨大区玩家需输入完整 名称#Tag）；③ 客户端版本接口变更。".format(query)
    )


def _norm_summoner(data):
    return {
        "puuid": data.get("puuid") or "",
        "summonerId": data.get("summonerId") or "",
        "name": data.get("displayName") or data.get("gameName")
        or data.get("name") or "未知玩家",
        "tagLine": data.get("tagLine") or "",
        "level": data.get("summonerLevel") or 0,
        "iconId": data.get("profileIconId") or 0,
    }


def match_page(lcu, puuid, beg_index):
    """拉取一页战绩，返回 (slim_games, has_more)。"""
    end_index = min(beg_index + PAGE_SIZE - 1, MAX_TOTAL)
    code, data = lcu.request(
        "GET",
        "/lol-match-history/v1/products/lol/{}/matches".format(puuid),
        params={"begIndex": beg_index, "endIndex": end_index},
    )
    if code != 200 or not data:
        raise LcuError("战绩接口返回异常（HTTP {}），请稍后重试。".format(code))
    games = (data.get("games") or {}).get("games") or []
    slim = [slim_game(g) for g in games]
    has_more = len(slim) >= PAGE_SIZE
    return slim, has_more


def slim_game(g):
    """把 LCU 战绩条目精简为前端渲染所需字段。"""
    try:
        me = next(
            p for p in g.get("participants", [])
            if p.get("stats", {}).get("puuid") or p.get("puuid")
        )
    except StopIteration:
        me = {}
        # 找不到自己：取第一个参与者兜底
        if g.get("participants"):
            me = g["participants"][0]

    stats = me.get("stats", {}) or {}
    duration_ms = g.get("gameDuration") or 0
    duration_s = duration_ms // 1000 if duration_ms > 10000 else duration_ms
    kills = stats.get("kills", 0) or 0
    deaths = stats.get("deaths", 0) or 0
    assists = stats.get("assists", 0) or 0
    cs = (stats.get("totalMinionsKilled", 0) or 0) + (
        stats.get("neutralMinionsKilled", 0) or 0
    )
    return {
        "gameId": g.get("gameId"),
        "queueId": g.get("queueId"),
        "mode": queue_name(g.get("queueId"), g.get("gameMode"), g.get("mapId")),
        "mapId": g.get("mapId"),
        "creation": g.get("gameCreation"),
        "durationSec": duration_s,
        "win": bool(stats.get("win")),
        "remake": duration_s < 300 and bool(stats.get("teamEarlySurrendered")),
        "championId": me.get("championId", 0),
        "kills": kills, "deaths": deaths, "assists": assists,
        "cs": cs,
        "gold": stats.get("goldEarned", 0) or 0,
        "damage": stats.get("totalDamageDealtToChampions", 0) or 0,
        "level": stats.get("champLevel", 0) or 0,
        "lane": stats.get("lane") or "",
        "role": stats.get("role") or "",
    }


def game_detail(lcu, game_id, my_puuid=""):
    """单局完整对局信息（两队成员）。"""
    code, data = lcu.request("GET", "/lol-match-history/v1/games/{}".format(game_id))
    if code != 200 or not data:
        raise LcuError("单局详情接口返回异常（HTTP {}）。".format(code))
    duration_ms = data.get("gameDuration") or 0
    duration_s = duration_ms // 1000 if duration_ms > 10000 else duration_ms
    teams = {100: [], 200: []}
    for p in data.get("participants", []):
        st = p.get("stats", {}) or {}
        teams.setdefault(p.get("teamId", 100), []).append({
            "name": p.get("summonerName") or "",
            "championId": p.get("championId", 0),
            "kills": st.get("kills", 0) or 0,
            "deaths": st.get("deaths", 0) or 0,
            "assists": st.get("assists", 0) or 0,
            "cs": (st.get("totalMinionsKilled", 0) or 0)
                  + (st.get("neutralMinionsKilled", 0) or 0),
            "gold": st.get("goldEarned", 0) or 0,
            "damage": st.get("totalDamageDealtToChampions", 0) or 0,
            "level": st.get("champLevel", 0) or 0,
            "items": [st.get("item{}".format(i), 0) or 0 for i in range(6)],
            "win": bool(st.get("win")),
        })
    return {
        "gameId": game_id,
        "mode": queue_name(data.get("queueId"), data.get("gameMode"), data.get("mapId")),
        "creation": data.get("gameCreation"),
        "durationSec": duration_s,
        "teams": [ {"teamId": t, "players": teams.get(t, [])} for t in (100, 200) ],
    }


def summarize(slim_games):
    """根据已加载战绩计算汇总统计。"""
    total = len(slim_games)
    if not total:
        return {"total": 0, "winRate": 0, "avgKda": "0.00", "champions": []}
    wins = sum(1 for g in slim_games if g["win"] and not g["remake"])
    counted = sum(1 for g in slim_games if not g["remake"])
    kills = sum(g["kills"] for g in slim_games)
    deaths = sum(g["deaths"] for g in slim_games)
    assists = sum(g["assists"] for g in slim_games)
    champ = {}
    for g in slim_games:
        c = champ.setdefault(g["championId"], {"games": 0, "wins": 0})
        c["games"] += 1
        if g["win"] and not g["remake"]:
            c["wins"] += 1
    top = sorted(champ.items(), key=lambda kv: -kv[1]["games"])[:8]
    return {
        "total": total,
        "counted": counted,
        "wins": wins,
        "winRate": round(wins * 100.0 / counted, 1) if counted else 0,
        "avgKda": round((kills + assists) / max(deaths, 1), 2),
        "kills": kills, "deaths": deaths, "assists": assists,
        "champions": [
            {"championId": cid, "games": c["games"],
             "winRate": round(c["wins"] * 100.0 / c["games"], 1)}
            for cid, c in top
        ],
    }
