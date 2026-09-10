"""当前对局仅使用客户端已公开的身份，未知玩家不按昵称猜测。"""
from urllib.parse import quote
import hashlib
import json
import time

from .lcu import LcuError
from .static_data import queue_name

ACTIVE_PHASES = {"ChampSelect", "GameStart", "InProgress", "Reconnect"}

# 队友评价的体量上限：聊天接口对单条长度与频率都有限制。
REVIEW_MAX_LINES = 9
REVIEW_MAX_CHARS = 230


def valid_puuid(value):
    return isinstance(value, str) and bool(value.strip("0-"))


def champ_select_conversation(conversations):
    """从会话列表里找选人聊天室；字段随客户端版本演进，做两级匹配。"""
    items = conversations or []
    for conv in items:
        if isinstance(conv, dict) and conv.get("gameConversationType") == "champSelect":
            return conv.get("id")
    for conv in items:
        if isinstance(conv, dict) and "champ-select" in str(conv.get("id") or ""):
            return conv.get("id")
    return None


def active_game_conversation(conversations):
    """游戏内聊天接口不可用时的回退目标：对局聊天室会话。"""
    for conv in conversations or []:
        if isinstance(conv, dict) and conv.get("gameConversationType") == "activeGame":
            return conv.get("id")
    return None


def _post_conversation(lcu, target, text):
    return lcu.request("POST", "/lol-chat/v1/conversations/{}/messages".format(quote(target, safe="")),
                       body={"body": text, "type": "chat"}, timeout=4)


def send_team_review(lcu, lines):
    """一键把队友评价逐条发进当前聊天：选人阶段发选人房间，对局中发队伍频道。

    返回 {"phase": ..., "sent": n}；客户端未就绪、阶段不对或发送失败时抛 LcuError。
    """
    cleaned = []
    for text in lines if isinstance(lines, list) else []:
        if isinstance(text, str) and text.strip():
            cleaned.append(text.strip()[:REVIEW_MAX_CHARS])
    if not cleaned:
        raise LcuError("评价内容为空")
    if len(cleaned) > REVIEW_MAX_LINES:
        raise LcuError("评价条数过多（最多 {} 条）".format(REVIEW_MAX_LINES))
    code, phase = lcu.request("GET", "/lol-gameflow/v1/gameflow-phase", timeout=3)
    if code != 200 or not isinstance(phase, str):
        raise LcuError("暂时无法确认当前游戏阶段")
    target = None
    instant = False
    if phase == "ChampSelect":
        code, conversations = lcu.request("GET", "/lol-chat/v1/conversations", timeout=3)
        target = champ_select_conversation(conversations if code == 200 else None)
        if not target:
            raise LcuError("选人聊天室尚未就绪，请稍候再试")
    elif phase in ACTIVE_PHASES:
        instant = True  # 对局中默认走游戏客户端的队伍聊天接口
    else:
        raise LcuError("当前不在选人或对局中，无法发送队友评价")
    sent = 0
    for text in cleaned:
        if instant:
            code, _ = lcu.request("POST", "/lol-game-client-chat/v1/instant-messages",
                                  body={"body": text, "recipient": "team"}, timeout=4)
            if code == 404 and sent == 0:
                # 该接口随游戏进程才可用，个别版本缺失时回退到对局聊天室会话。
                code2, conversations = lcu.request("GET", "/lol-chat/v1/conversations", timeout=3)
                fallback = active_game_conversation(conversations if code2 == 200 else None)
                if fallback:
                    target, instant = fallback, False
                    code, _ = _post_conversation(lcu, target, text)
                else:
                    raise LcuError("当前对局的聊天接口不可用（HTTP 404），无法发送")
        else:
            code, _ = _post_conversation(lcu, target, text)
        if code not in (200, 201, 204):
            if sent == 0:
                raise LcuError("发送失败（HTTP {}），请确认聊天可用后重试".format(code))
            raise LcuError("前 {} 条已发出，后续发送失败（HTTP {}）".format(sent, code))
        sent += 1
        time.sleep(0.3)  # 保序并避免触发聊天限速
    return {"phase": phase, "sent": sent}


def positive_champion(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _team_id(value):
    """大厅成员 teamId 可能是 1/2 或 100/200，统一成 100/200。"""
    try:
        team = int(value)
    except (TypeError, ValueError):
        return 0
    if team in (1, 100):
        return 100
    if team in (2, 200):
        return 200
    return 0


def custom_lobby(lcu):
    """自定义房间：全员在同一大厅，可在选人前拿到双方成员。

    只识别 gameType 为 CUSTOM_GAME 的房间；匹配/排位大厅里只有自己的队伍，
    不在这里按“双方”展示，以免把队友误当成对手。
    """
    code, lobby = lcu.request("GET", "/lol-lobby/v2/lobby", timeout=3)
    if code != 200 or not isinstance(lobby, dict):
        return None
    config = lobby.get("gameConfig") or {}
    if config.get("gameType") != "CUSTOM_GAME":
        return None
    teams = {100: [], 200: []}
    seen, snapshot = set(), []
    for raw in lobby.get("members") or []:
        if not isinstance(raw, dict) or raw.get("isSpectator"):
            continue
        sid = str(raw.get("summonerId") or "")
        puuid = raw.get("puuid") or ""
        team = _team_id(raw.get("teamId"))
        identity = sid or puuid
        if not identity or team not in teams or identity in seen:
            continue
        seen.add(identity)
        snapshot.append([team, identity])
        teams[team].append({
            "puuid": puuid, "summonerId": sid,
            "gameName": raw.get("gameName") or raw.get("summonerName") or "",
            "tagLine": raw.get("tagLine") or "",
            "championId": 0, "pickState": "自定义房间 · 等待开始", "isBot": False,
        })
    if not teams[100] and not teams[200]:
        return None
    queue_id = config.get("queueId")
    map_id = config.get("mapId")
    game_mode = config.get("gameMode")
    data = {
        "customLobby": True,
        "lobbyOwnTeamId": _team_id((lobby.get("localMember") or {}).get("teamId")) or (100 if teams[100] else 200),
        "queue": {"id": queue_id, "gameMode": game_mode, "mapId": map_id},
        "gameMode": game_mode,
        "teamOne": teams[100], "teamTwo": teams[200],
        "teamOneBans": [], "teamTwoBans": [],
    }
    status = {
        "active": True, "phase": "Lobby",
        "key": "lobby:{}:{}".format(lobby.get("lobbyId") or "", queue_id or map_id or ""),
        "revision": hashlib.sha256(json.dumps(sorted(snapshot)).encode()).hexdigest(),
        "mode": "自定义 · {}".format(queue_name(queue_id, game_mode, map_id)),
        # 大厅不弹窗打扰，仅在“当前对局”面板里展示。
        "notify": False,
    }
    return status, data


def draft_data(selection):
    """从选人会话提取英雄与选择状态，按 summonerId 叠加到 gameflow 名单。

    大乱斗类模式下选人接口不公开对方（theirTeam 为空），因此不能用它替换
    gameflow 名单——否则对方玩家会在选人阶段整体消失，只能等进入游戏。
    """
    actions = [a for group in selection.get("actions") or [] for a in group if isinstance(a, dict)]
    result = {"selectionTeams": True, "draft": True,
              "draftOverlay": {}, "draftOwnSummoners": []}
    bans = selection.get("bans") or {}
    for source, target, ban_field in (("myTeam", "teamOne", "myTeamBans"), ("theirTeam", "teamTwo", "theirTeamBans")):
        own = source == "myTeam"
        players = []
        cells = set()
        for raw in (selection.get(source) or [])[:5]:
            p = dict(raw)
            cell = p.get("cellId")
            if cell is not None:
                cells.add(cell)
            sid = str(p.get("summonerId") or "")
            cid = p.get("championId") if positive_champion(p.get("championId")) else 0
            p["pickState"] = "已选择" if cid else "待选择 / 尚未公开"
            picks = [a for a in actions if cell is not None and a.get("actorCellId") == cell and a.get("type") == "pick"]
            completed = [a for a in picks if a.get("completed") and positive_champion(a.get("championId"))]
            if completed:
                # 换英雄后以名单中当前英雄为准。
                cid = cid or completed[-1]["championId"]
                p["pickState"] = "已锁定"
            elif own:
                hover = p.get("championPickIntent")
                current = next((a for a in reversed(picks) if a.get("isInProgress") and positive_champion(a.get("championId"))), None)
                if current:
                    cid = current["championId"]
                    p["pickState"] = "选择中"
                elif not cid and positive_champion(hover):
                    cid = hover
                    p["pickState"] = "预选"
            p["championId"] = cid
            players.append(p)
            if own:
                result["draftOwnSummoners"].append(sid)
            if sid and sid != "0":
                result["draftOverlay"][sid] = {"championId": cid, "pickState": p["pickState"]}
        ids = [cid for cid in bans.get(ban_field) or [] if positive_champion(cid)]
        ids += [a["championId"] for a in actions if a.get("type") == "ban" and a.get("completed")
                and a.get("actorCellId") in cells and positive_champion(a.get("championId"))]
        result[target + "Bans"] = list(dict.fromkeys(ids))
        result[target + "Draft"] = players
    return result


def inspect(lcu):
    code, phase = lcu.request("GET", "/lol-gameflow/v1/gameflow-phase", timeout=3)
    if code != 200:
        raise LcuError("暂时无法检测当前对局")
    if phase not in ACTIVE_PHASES:
        if phase == "Lobby":
            lobby = custom_lobby(lcu)
            if lobby:
                return lobby
        return {"active": False, "phase": phase or "None"}, None
    code, session = lcu.request("GET", "/lol-gameflow/v1/session", timeout=3)
    if code != 200 or not isinstance(session, dict):
        raise LcuError("已进入对局，等待客户端提供玩家名单")
    data = session.get("gameData") or {}
    if phase == "ChampSelect":
        code, selection = lcu.request("GET", "/lol-champ-select/v1/session", timeout=3)
        if code != 200 or not isinstance(selection, dict):
            raise LcuError("正在选择英雄，等待客户端提供选人名单")
        data = {**data, "gameId": selection.get("gameId") or data.get("gameId"), **draft_data(selection)}
        # 选人初期 gameflow 可能仍保留上一种模式，以当前选人队列为准。
        if selection.get("queueId"):
            old_queue = data.get("queue") or {}
            if old_queue.get("id") != selection["queueId"]:
                data["queue"] = {"id": selection["queueId"]}
                data["gameMode"] = None
        if not data.get("gameId"):
            raise LcuError("正在选择英雄，等待客户端提供对局编号")
    gid = data.get("gameId")
    if not gid:
        raise LcuError("正在载入对局，等待对局编号")
    key = "{}:{}".format(data.get("gameId"), data.get("platformId") or "")
    queue = data.get("queue") or {}
    # 选人叠加与名单分开哈希：对方锁定英雄时名单不变，也要触发刷新。
    visible = {k: data.get(k) for k in ("teamOne", "teamTwo", "teamOneBans", "teamTwoBans",
                                        "playerChampionSelections", "draftOverlay",
                                        "draftOwnSummoners", "teamOneDraft", "teamTwoDraft")}
    revision = hashlib.sha256(json.dumps(visible, sort_keys=True).encode()).hexdigest()
    return {"active": True, "phase": phase, "key": key,
            "revision": revision,
            "mode": queue_name(queue.get("id"), data.get("gameMode") or queue.get("gameMode"), queue.get("mapId"))}, data


def resolve_player(lcu, raw):
    puuid = raw.get("puuid") if valid_puuid(raw.get("puuid")) else ""
    sid = raw.get("summonerId") or ""
    if str(sid) == "0":
        sid = ""
    result = {"puuid": puuid, "summonerId": sid, "name": raw.get("gameName") or raw.get("summonerName") or "身份未公开",
              "tagLine": raw.get("tagLine") or "", "level": 0,
              "championId": raw.get("championId") or 0, "isBot": bool(raw.get("isBot"))}
    if result["isBot"]:
        result.update(puuid="", name="电脑玩家")
        return result
    if puuid or sid:
        path = "/lol-summoner/v2/summoners/puuid/" + quote(puuid, safe="") if puuid else "/lol-summoner/v1/summoners/" + quote(str(sid), safe="")
        try:
            code, profile = lcu.request("GET", path, timeout=3)
            if code == 200 and isinstance(profile, dict) and valid_puuid(profile.get("puuid")):
                # 不接受与对局身份冲突的资料。
                if (puuid and profile["puuid"] != puuid) or (not puuid and str(profile.get("summonerId")) != str(sid)):
                    return result
                result.update(puuid=profile["puuid"], summonerId=profile.get("summonerId") or sid,
                              name=profile.get("gameName") or profile.get("displayName") or result["name"],
                              tagLine=profile.get("tagLine") or result["tagLine"], level=profile.get("summonerLevel") or 0)
        except LcuError:
            pass
    return result


def live_players():
    """游戏客户端 Live Client Data API：对局开始后提供完整双方名单（含电脑）。

    国服 gameflow 会话在部分模式（实测人机类）整局都不给出对方名单，此接口是
    唯一来源；仅在游戏进程运行期间可用，失败返回 None，由调用方保持原状。
    """
    try:
        import requests
        response = requests.get("https://127.0.0.1:2999/liveclientdata/allgamedata",
                                timeout=3, verify=False)
        if response.status_code != 200:
            return None
        players = response.json().get("allPlayers")
        return players if isinstance(players, list) and players else None
    except Exception:
        return None


def _champion_id_by_display_name():
    """Live 接口给的是展示名（称号或名称），映射回英雄 ID 用于显示头像。"""
    from . import champions
    mapping = {}
    for cid, info in champions.get_champion_map().items():
        for key in (info.get("name"), info.get("title"), champions.champion_name(cid)):
            if key:
                mapping.setdefault(key, int(cid))
    return mapping


def _fill_empty_team_from_live_data(teams, phase):
    """某队名单为空且已进入对局时，用 Live 数据补齐（人机模式的电脑名单）。"""
    if phase not in ("GameStart", "InProgress", "Reconnect"):
        return False
    players = live_players()
    if not players:
        return False
    mapping = _champion_id_by_display_name()
    filled = False
    for team, side in ((teams[0], "ORDER"), (teams[1], "CHAOS")):
        if team["players"]:
            continue
        for p in players:
            if p.get("team") != side:
                continue
            name = p.get("gameName") or p.get("summonerName") or ""
            team["players"].append({
                "puuid": "", "summonerId": "", "name": name, "tagLine": "", "level": 0,
                "championId": mapping.get((p.get("championName") or "").strip(), 0),
                "pickState": "", "isBot": bool(p.get("isBot")), "lane": p.get("position") or ""})
            filled = True
    return filled


def roster(lcu, status, data, own_puuid):
    if not status.get("active"):
        return {**status, "teams": []}
    queue = data.get("queue") or {}
    if queue.get("id") in (1700, 1710) or queue.get("mapId") in (22, 30) or (data.get("gameMode") or queue.get("gameMode")) in ("CHERRY", "TFT"):
        return {**status, "teams": [], "note": "此模式暂不支持按双方展示当前对局"}
    teams = []
    selections = {p.get("puuid"): p.get("championId") for p in data.get("playerChampionSelections") or [] if p.get("puuid")}
    overlay = data.get("draftOverlay") or {}
    for field, team_id in (("teamOne", 100), ("teamTwo", 200)):
        players = []
        known = set()
        # gameflow 名单是身份基准（puuid、昵称），选人数据只叠加英雄与状态。
        for raw in (data.get(field) or [])[:5]:
            p = resolve_player(lcu, raw)
            sid = str(raw.get("summonerId") or "")
            known.add(sid)
            extra = overlay.get(sid)
            if extra:
                p["championId"] = extra["championId"] or p["championId"] or selections.get(p["puuid"]) or 0
                p["pickState"] = extra["pickState"]
            else:
                p["championId"] = p["championId"] or selections.get(p["puuid"]) or 0
                p["pickState"] = raw.get("pickState") or ""
            players.append(p)
        # 客户端未给出 gameflow 名单时，用选人名单补齐，避免选人阶段名单为空。
        for raw in (data.get(field + "Draft") or [])[:5]:
            sid = str(raw.get("summonerId") or "")
            if sid and sid in known:
                continue
            p = resolve_player(lcu, raw)
            p["championId"] = p["championId"] or 0
            p["pickState"] = raw.get("pickState") or ""
            players.append(p)
        teams.append({"teamId": team_id, "players": players,
                      "bans": [{"championId": cid} for cid in data.get(field + "Bans") or []]})
    own_sids = {s for s in data.get("draftOwnSummoners") or [] if s and s != "0"}
    own_team = next((t["teamId"] for t in teams if own_puuid and any(p["puuid"] == own_puuid for p in t["players"])), None)
    if own_team is None and own_sids:
        own_team = next((t["teamId"] for t in teams
                         if any(str(p["summonerId"]) in own_sids for p in t["players"])), None)
    if own_team is None and data.get("lobbyOwnTeamId"):
        own_team = data["lobbyOwnTeamId"]
    if own_team is None and data.get("selectionTeams"):
        own_team = 100
    for team in teams:
        team["label"] = ("我方" if team["teamId"] == own_team else "对手") if own_team else ("蓝方" if team["teamId"] == 100 else "红方")
    if _fill_empty_team_from_live_data(teams, status.get("phase")) and own_team is None:
        if own_puuid:
            own_team = next((t["teamId"] for t in teams
                             if any(p["puuid"] == own_puuid for p in t["players"])), None)
        if own_team is None and data.get("selectionTeams"):
            own_team = 100
        for team in teams:
            team["label"] = ("我方" if team["teamId"] == own_team else "对手") if own_team else ("蓝方" if team["teamId"] == 100 else "红方")
    teams.sort(key=lambda t: t["teamId"] != own_team)
    count = sum(len(t["players"]) for t in teams)
    has_bot = any(p.get("isBot") for t in teams for p in t["players"])
    if has_bot and count == 10:
        note = "对方为电脑玩家，名单与英雄来自对局数据；电脑无个人战绩可查。"
    else:
        note = "双方最近 20 场历史战绩，重开不计胜率；不含正在进行的对局。" if count == 10 else "名单尚未完整公开，正在自动更新。"
    if data.get("customLobby"):
        note = ("自定义房间：双方共 {} 名成员已在大厅公开，可提前查看对手；开始选人后自动切换为选人数据。".format(count)
                if count else "自定义房间：等待成员加入。")
    elif status.get("phase") == "ChampSelect":
        note = "正在选择英雄，名单与英雄自动更新；对手或匿名玩家尚未公开时暂无法查询，进入游戏后继续读取。"
    return {**status, "teams": teams, "note": note, "draft": bool(data.get("draft"))}
