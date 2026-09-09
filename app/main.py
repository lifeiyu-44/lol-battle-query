# -*- coding: utf-8 -*-
"""应用入口：桌面窗口 + 前端 JS API 桥。"""
import os
import sys

import webview

from .lcu import LcuClient, LcuError
from . import query as Q
from . import champions
from . import augments as A
from . import references
from .friends import FriendDirectory, friend_status
from .damage import DamageEvaluator


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, rel)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)


class Api:
    def __init__(self):
        self.lcu = LcuClient()
        self.friends = FriendDirectory(self.lcu)
        self.damage = DamageEvaluator(self.lcu)

    @staticmethod
    def _fail(msg):
        return {"ok": False, "error": msg}

    # ---------- 状态 ----------

    def get_status(self):
        try:
            me = self.lcu.connect()
            name = (me.get("displayName") or me.get("gameName")
                    or me.get("name") or "召唤师")
            return {"ok": True, "connected": True,
                    "me": {"name": name, "level": me.get("summonerLevel", 0)}}
        except LcuError as e:
            return {"ok": False, "connected": False, "error": str(e)}
        except Exception as e:  # psutil 权限等意外情况
            return {"ok": False, "connected": False,
                    "error": "检测客户端失败：{}".format(e)}

    # ---------- 查询 ----------

    def search_player(self, q):
        try:
            if not self.lcu.connected:
                self.lcu.connect()
            s = Q.find_summoner(self.lcu, q)
            s["friendStatus"] = friend_status(self.friends.snapshot(), s["puuid"], s["summonerId"])
            return {"ok": True, "summoner": s}
        except LcuError as e:
            return self._fail(str(e))
        except Exception as e:
            return self._fail("查询失败：{}".format(e))

    def get_matches(self, puuid, beg_index):
        try:
            games, has_more = Q.match_page(self.lcu, puuid, beg_index)
            for g in games:
                g["championName"] = champions.champion_name(g["championId"])
                g["avatar"] = champions.champion_avatar(g["championId"])
                g["augmentNames"] = [
                    A.augment_info(a, self.lcu) for a in g["augments"]
                ]
            return {"ok": True, "games": games, "hasMore": has_more}
        except LcuError as e:
            return self._fail(str(e))
        except Exception as e:
            return self._fail("获取战绩失败：{}".format(e))

    def get_game_detail(self, game_id, my_puuid=""):
        try:
            d = Q.game_detail(self.lcu, game_id, my_puuid=my_puuid)
            friends = self.friends.snapshot()
            for team in d["teams"]:
                for p in team["players"]:
                    p["championName"] = champions.champion_name(p["championId"])
                    p["avatar"] = champions.champion_avatar(p["championId"])
                    p["itemIcons"] = [champions.item_icon(i) for i in p["items"]]
                    p["friendStatus"] = friend_status(friends, p["puuid"], p.get("summonerId"))
            return {"ok": True, "game": d}
        except LcuError as e:
            return self._fail(str(e))
        except Exception as e:
            return self._fail("获取详情失败：{}".format(e))

    def get_damage_evaluations(self, puuid, game_ids):
        """每批最多五场，前端后台补齐十人数据，不阻塞战绩展示。"""
        if not puuid or not isinstance(game_ids, list) or len(game_ids) > 5:
            return self._fail("伤害评价参数无效")
        if any(isinstance(i, bool) or not isinstance(i, int) or i <= 0 for i in game_ids):
            return self._fail("对局编号无效")
        return {"ok": True, "results": [
            {"gameId": gid, "evaluation": self.damage.get(puuid, gid)} for gid in game_ids
        ]}

    def get_champion_map(self):
        m = champions.get_champion_map()
        return {"ok": True, "count": len(m), "champions": [
            {"id": int(cid), "name": champions.champion_name(cid)} for cid in m
        ]}

    def get_augment_reference(self, champion_id=0, force=False):
        """无需启动客户端；外部请求只包含公开的英雄 ID。"""
        try:
            data = references.get_reference(champion_id, force)
            client = self.lcu if self.lcu.connected else None
            # Copy rows so image payloads never enter the public statistics cache.
            data["rows"] = [{**row, "augment": A.augment_info(row["id"], client)}
                            for row in data["rows"]]
            return {"ok": True, "data": data}
        except Exception as e:
            return self._fail(str(e))


def main():
    api = Api()
    webview.create_window(
        "英雄联盟国服战绩查询",
        url=resource_path("ui/index.html"),
        js_api=api,
        width=1120, height=800, min_size=(920, 620),
        background_color="#010a13",
    )
    try:
        webview.start(icon=resource_path("ui/app-icon.ico"))
    except Exception as e:
        # 最常见原因：系统缺少 WebView2 Runtime
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                "启动失败：{}\n\n多数情况是系统缺少 Microsoft WebView2 运行时，"
                "请到微软官网搜索“WebView2 Runtime”安装后重试。".format(e),
                "英雄联盟国服战绩查询", 0x10)
        except Exception:
            raise


if __name__ == "__main__":
    main()
