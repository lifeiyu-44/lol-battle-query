"""本机最近搜索：仅保存玩家标识和显示名称，不保存客户端凭据。"""
import os
import sqlite3
import time
from pathlib import Path
from contextlib import closing


class SearchHistory:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "LOL战绩查询" / "search-history.sqlite3"

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=5)
        db.execute("CREATE TABLE IF NOT EXISTS searches (puuid TEXT PRIMARY KEY, name TEXT NOT NULL, tag TEXT NOT NULL, accessed INTEGER NOT NULL)")
        return db

    def list_recent(self):
        if not self.path.exists():
            return []
        with closing(self._connect()) as db:
            return [{"puuid": p, "name": n, "tagLine": t} for p, n, t in db.execute(
                "SELECT puuid,name,tag FROM searches ORDER BY accessed DESC LIMIT 20")]

    def remember(self, player):
        if not isinstance(player, dict):
            raise ValueError("玩家信息无效")
        p, n, t = (player.get(k) or "" for k in ("puuid", "name", "tagLine"))
        if not all(isinstance(v, str) and len(v) <= 256 for v in (p, n, t)) or not p.strip("0- ") or not n.strip():
            raise ValueError("玩家信息无效")
        with closing(self._connect()) as db, db:
            db.execute("INSERT OR REPLACE INTO searches VALUES (?,?,?,?)", (p, n, t, time.time_ns()))
            db.execute("DELETE FROM searches WHERE puuid NOT IN (SELECT puuid FROM searches ORDER BY accessed DESC LIMIT 20)")
        return self.list_recent()

    def remove(self, puuid=None):
        if self.path.exists():
            with closing(self._connect()) as db, db:
                if puuid is None:
                    db.execute("DELETE FROM searches")
                else:
                    db.execute("DELETE FROM searches WHERE puuid=?", (puuid,))
        return self.list_recent()
