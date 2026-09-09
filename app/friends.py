"""好友标记始终相对于本机当前登录账号；不按可重名的显示名称匹配。"""
import threading
import time


class FriendDirectory:
    def __init__(self, lcu):
        self.lcu = lcu
        self._lock = threading.Lock()
        self._owner = None
        self._updated = 0
        self._snapshot = None

    def snapshot(self):
        with self._lock:
            unknown = {"available": False, "puuids": set(), "summonerIds": set(),
                       "ownPuuid": "", "ownSummonerId": ""}
            try:
                code, me = self.lcu.request("GET", "/lol-summoner/v1/current-summoner", timeout=3)
                if code != 200 or not isinstance(me, dict) or not me.get("puuid"):
                    return unknown
                owner = (self.lcu.port, me["puuid"])
                if owner == self._owner and self._snapshot and time.monotonic() - self._updated < 60:
                    return self._snapshot
                current = {**unknown, "ownPuuid": me["puuid"],
                           "ownSummonerId": str(me.get("summonerId") or "")}
                code, rows = self.lcu.request("GET", "/lol-chat/v1/friends", timeout=3)
                if code != 200 or not isinstance(rows, list):
                    return current
                friends = [r for r in rows if isinstance(r, dict)
                           and r.get("relationshipOnRiot", "friend") == "friend"]
                current.update(available=True,
                               puuids={r["puuid"] for r in friends if r.get("puuid")},
                               summonerIds={str(r["summonerId"]) for r in friends if r.get("summonerId")})
                self._owner, self._updated, self._snapshot = owner, time.monotonic(), current
                return current
            except Exception:
                return unknown


def friend_status(snapshot, puuid="", summoner_id=""):
    sid = str(summoner_id or "")
    if (puuid and puuid == snapshot.get("ownPuuid")) or (sid and sid == snapshot.get("ownSummonerId")):
        return "self"
    if not snapshot.get("available") or not (puuid or sid):
        return "unknown"
    if puuid:
        # A stable PUUID takes precedence over legacy region-specific summoner IDs.
        return "friend" if puuid in snapshot["puuids"] else "not_friend"
    return "friend" if sid in snapshot["summonerIds"] else "not_friend"
