# -*- coding: utf-8 -*-
"""战绩查询业务层：按 ID 查人、战绩分页、单局详情、汇总统计。"""
from urllib.parse import quote

from .static_data import queue_name
from .lcu import LcuError
from .augments import clean_augments, augment_info
from .damage import rankings, evaluate

PAGE_SIZE = 20
MAX_TOTAL = 500


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
        "未找到玩家「{}」。当前客户端版本已下线「仅按名字」查询接口"
        "（实测 422/404），请输入完整 名称#Tag，例如「峡谷之巅#5177」；"
        "Tag 可在对方生涯页或对局载入界面查看。".format(query)
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


def match_page(lcu, puuid, beg_index, count=PAGE_SIZE):
    """拉取一页战绩，返回 (slim_games, has_more)。"""
    if (isinstance(beg_index, bool) or not isinstance(beg_index, int) or beg_index < 0
            or isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= PAGE_SIZE):
        raise LcuError("战绩分页参数无效")
    if beg_index >= MAX_TOTAL:
        return [], False
    count = min(count, MAX_TOTAL - beg_index)
    end_index = beg_index + count - 1
    code, data = lcu.request(
        "GET",
        "/lol-match-history/v1/products/lol/{}/matches".format(puuid),
        params={"begIndex": beg_index, "endIndex": end_index},
    )
    if code != 200 or not data:
        raise LcuError("战绩接口返回异常（HTTP {}），请稍后重试。".format(code))
    games = ((data.get("games") or {}).get("games") or [])[:count]
    slim = [slim_game(g, puuid) for g in games]
    has_more = len(slim) >= count and end_index + 1 < MAX_TOTAL
    return slim, has_more


def rating_participants(game):
    """前端用同一评分公式评选 MVP/SVP；保留缺失值，不把缺失当作零。"""
    return [{"participantId": p.get("participantId"), "teamId": p.get("teamId"),
             **{key: (p.get("stats") or {}).get(key) for key in
                ("kills", "deaths", "assists", "win", "totalDamageDealtToChampions")}}
            for p in game.get("participants") or []]


def slim_game(g, my_puuid=""):
    """把 LCU 战绩条目精简为前端渲染所需字段。"""
    participants = g.get("participants") or []
    identities = {p.get("participantId"): (p.get("player") or {}).get("puuid")
                  for p in g.get("participantIdentities") or []}
    me = next((p for p in participants if my_puuid and my_puuid in (
        p.get("puuid"), (p.get("stats") or {}).get("puuid"),
        identities.get(p.get("participantId")))), None)
    try:
        if me is None and my_puuid and len(participants) > 1:
            raise LcuError("战绩中未找到被查询玩家，无法计算其个人统计。")
        if me is not None:
            selected = me
        else:
            selected = next(iter(participants))
        me = selected
    except StopIteration:
        me = {}

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
        "participantId": me.get("participantId"),
        "ratingParticipants": rating_participants(g),
        "queueId": g.get("queueId"),
        "mode": queue_name(g.get("queueId"), g.get("gameMode"), g.get("mapId")),
        "mapId": g.get("mapId"),
        "creation": g.get("gameCreation") or g.get("gameCreationDate"),
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
        "augments": clean_augments(stats),
    }


def game_detail(lcu, game_id, my_puuid="", data=None):
    """单局完整对局信息（两队成员）。

    当前客户端版本参与者本体不再带名字，名字/puuid 在
    participantIdentities[].player 里，需要按 participantId 联表。
    my_puuid 用于标出被查询玩家所在队伍（前端据此显示我方/敌方）。
    """
    if data is None:
        code, data = lcu.request("GET", "/lol-match-history/v1/games/{}".format(game_id))
        if code != 200 or not data:
            raise LcuError("单局详情接口返回异常（HTTP {}）。".format(code))
    duration_ms = data.get("gameDuration") or 0
    duration_s = duration_ms // 1000 if duration_ms > 10000 else duration_ms
    identities = {}
    for pi in data.get("participantIdentities", []):
        player = pi.get("player") or {}
        identities[pi.get("participantId")] = {
            "gameName": player.get("gameName") or player.get("summonerName") or "",
            "tagLine": player.get("tagLine") or "",
            "puuid": player.get("puuid") or "",
            "summonerId": player.get("summonerId") or "",
        }
    teams = {100: [], 200: []}
    damage_status, damage_rows = rankings(data)
    my_team_id = None
    for p in data.get("participants", []):
        st = p.get("stats", {}) or {}
        ident = identities.get(p.get("participantId")) or {}
        if my_puuid and ident.get("puuid") == my_puuid:
            my_team_id = p.get("teamId")
        augments = clean_augments(st)
        teams.setdefault(p.get("teamId", 100), []).append({
            "participantId": p.get("participantId"),
            "name": ident.get("gameName") or p.get("summonerName") or "",
            "tagLine": ident.get("tagLine") or "",
            "puuid": ident.get("puuid") or "",
            "summonerId": ident.get("summonerId") or p.get("summonerId") or "",
            "championId": p.get("championId", 0),
            "kills": st.get("kills", 0) or 0,
            "deaths": st.get("deaths", 0) or 0,
            "assists": st.get("assists", 0) or 0,
            "cs": (st.get("totalMinionsKilled", 0) or 0)
                  + (st.get("neutralMinionsKilled", 0) or 0),
            "gold": st.get("goldEarned", 0) or 0,
            "damage": st.get("totalDamageDealtToChampions", 0) or 0,
            "damageEvaluation": damage_rows.get(p.get("participantId"), damage_status),
            "level": st.get("champLevel", 0) or 0,
            "items": [st.get("item{}".format(i), 0) or 0 for i in range(6)],
            "augments": [
                augment_info(a, lcu) for a in augments
            ],
            "win": bool(st.get("win")),
        })
    return {
        "gameId": game_id,
        "ratingParticipants": rating_participants(data),
        "mode": queue_name(data.get("queueId"), data.get("gameMode"), data.get("mapId")),
        "creation": data.get("gameCreation") or data.get("gameCreationDate"),
        "durationSec": duration_s,
        "myTeamId": my_team_id,
        "damageEvaluation": evaluate(data, my_puuid),
        "remake": duration_s < 300 and any(
            (p.get("stats") or {}).get("teamEarlySurrendered") for p in data.get("participants", [])),
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
