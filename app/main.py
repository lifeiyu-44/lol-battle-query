# -*- coding: utf-8 -*-
"""应用入口：桌面窗口 + 前端 JS API 桥。"""
import os
import sys
import html
import json
import time
import base64
import threading
from pathlib import Path

import webview

from .lcu import LcuClient, LcuError
from . import query as Q
from . import champions
from . import augments as A
from . import augment_prefs
from . import references
from .friends import FriendDirectory, friend_status
from .damage import DamageEvaluator
from . import current_game
from .history import HistoryClient
from .search_history import SearchHistory
from urllib.parse import quote


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return os.path.join(base, rel)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)


def _screen_bounds():
    """所有屏幕的逻辑坐标 (x, y, width, height)；拿不到时返回 None。"""
    try:
        return [(int(s.x), int(s.y), int(s.width), int(s.height)) for s in webview.screens or []]
    except Exception:
        return None


class Api:
    def __init__(self):
        self.lcu = LcuClient()
        self.friends = FriendDirectory(self.lcu)
        self.damage = DamageEvaluator(self.lcu)
        self.history = HistoryClient(self.lcu)
        self._current_window = None
        self._main_window = None
        self._notified_games = set()
        self._searches = SearchHistory()
        # 弹窗位置记忆：用户拖动后记住坐标，下次对局在原位弹出。
        self._notice_position = None
        self._notice_position_lock = threading.Lock()
        self._notice_position_saved = 0.0
        # 后台预热英雄名称/头像映射，避免首次查询时同步等待网络资料。
        champions.warmup()

    @staticmethod
    def _fail(msg):
        return {"ok": False, "error": msg}

    # ---------- 状态 ----------

    def get_status(self):
        try:
            me = self.lcu.connect()
            profile = Q._norm_summoner(me)
            profile["friendStatus"] = "self"
            return {"ok": True, "connected": True,
                    "me": profile}
        except LcuError as e:
            return {"ok": False, "connected": False, "error": str(e)}
        except Exception as e:  # psutil 权限等意外情况
            return {"ok": False, "connected": False,
                    "error": "检测客户端失败：{}".format(e)}

    # ---------- 查询 ----------

    def get_search_history(self):
        try:
            return {"ok": True, "players": self._searches.list_recent()}
        except Exception:
            return self._fail("读取本机搜索历史失败")

    def remember_search(self, player):
        try:
            return {"ok": True, "players": self._searches.remember(player)}
        except Exception:
            return self._fail("保存搜索历史失败，本次查询不受影响")

    def remove_search(self, puuid=None):
        try:
            return {"ok": True, "players": self._searches.remove(puuid)}
        except Exception:
            return self._fail("删除搜索历史失败")

    def get_saved_player(self, puuid):
        try:
            if not current_game.valid_puuid(puuid):
                raise LcuError("玩家身份无效")
            if not self.lcu.connected:
                self.lcu.connect()
            code, profile = self.lcu.request("GET", "/lol-summoner/v2/summoners/puuid/" + quote(puuid, safe=""))
            if code != 200 or not isinstance(profile, dict) or profile.get("puuid") != puuid:
                raise LcuError("该历史玩家的资料暂不可用，请确认当前大区后重试")
            player = Q._norm_summoner(profile)
            player["friendStatus"] = friend_status(self.friends.snapshot(), puuid, player["summonerId"])
            return {"ok": True, "summoner": player}
        except Exception as e:
            return self._fail(str(e))

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

    def get_matches(self, puuid, beg_index, count=20):
        try:
            games, has_more, source, note = self.history.page(puuid, beg_index, count)
            for g in games:
                g["championName"] = champions.champion_name(g["championId"])
                g["avatar"] = champions.champion_avatar(g["championId"], self.lcu)
                g["augmentNames"] = [
                    A.augment_info(a, self.lcu) for a in g["augments"]
                ]
            return {"ok": True, "games": games, "hasMore": has_more, "source": source, "note": note}
        except LcuError as e:
            return self._fail(str(e))
        except Exception as e:
            return self._fail("获取战绩失败：{}".format(e))

    def get_game_detail(self, game_id, my_puuid=""):
        try:
            d = Q.game_detail(self.lcu, game_id, my_puuid=my_puuid,
                              data=self.history.cached_game(my_puuid, game_id))
            friends = self.friends.snapshot()
            for team in d["teams"]:
                for p in team["players"]:
                    p["championName"] = champions.champion_name(p["championId"])
                    p["avatar"] = champions.champion_avatar(p["championId"], self.lcu)
                    p["itemIcons"] = [champions.item_icon(i, self.lcu) for i in p["items"]]
                    p["friendStatus"] = friend_status(friends, p["puuid"], p.get("summonerId"))
            return {"ok": True, "game": d}
        except LcuError as e:
            return self._fail(str(e))
        except Exception as e:
            return self._fail("获取详情失败：{}".format(e))

    def get_analysis_matches(self, puuid, beg_index, count=20):
        """英雄专项分析分页，不下载无关英雄与海克斯图标。"""
        try:
            if not current_game.valid_puuid(puuid):
                return self._fail("玩家身份未公开，无法分析")
            if not self.lcu.connected:
                self.lcu.connect()
            games, more, source, note = self.history.page(puuid, beg_index, count)
            # 带上伤害评价：英雄专项页的评分同样以队伍伤害占比为第一要素。
            fields = ("gameId", "championId", "queueId", "mode", "creation", "durationSec", "win", "remake",
                      "kills", "deaths", "assists", "damageEvaluation")
            lean = [{key: g[key] for key in fields if key in g} for g in games]
            for g in lean:
                g["championName"] = champions.champion_name(g.get("championId"))
                g["avatar"] = champions.champion_avatar(g.get("championId"), self.lcu)
            return {"ok": True, "games": lean, "hasMore": more, "source": source, "note": note}
        except Exception as e:
            return self._fail("读取英雄战绩失败：{}".format(e))

    def get_damage_evaluations(self, puuid, game_ids):
        """每批最多五场，前端后台补齐十人数据，不阻塞战绩展示。"""
        if not puuid or not isinstance(game_ids, list) or len(game_ids) > 5:
            return self._fail("伤害评价参数无效")
        if any(isinstance(i, bool) or not isinstance(i, int) or i <= 0 for i in game_ids):
            return self._fail("对局编号无效")
        return {"ok": True, "results": [
            {"gameId": gid, "evaluation": self.damage.get(puuid, gid)} for gid in game_ids
        ]}

    def get_current_game_status(self):
        try:
            if not self.lcu.connected:
                self.lcu.connect()
            status, _ = current_game.inspect(self.lcu)
            return {"ok": True, **status}
        except Exception as e:
            return self._fail(str(e))

    def get_current_game(self):
        try:
            if not self.lcu.connected:
                self.lcu.connect()
            status, data = current_game.inspect(self.lcu)
            friends = self.friends.snapshot()
            result = current_game.roster(self.lcu, status, data, friends.get("ownPuuid"))
            for team in result["teams"]:
                for ban in team.get("bans", []):
                    ban["championName"] = champions.champion_name(ban["championId"])
                    ban["avatar"] = champions.champion_avatar(ban["championId"], self.lcu)
                for p in team["players"]:
                    p["championName"] = champions.champion_name(p["championId"]) if p["championId"] else "英雄未公开"
                    p["avatar"] = champions.champion_avatar(p["championId"], self.lcu) if p["championId"] else ""
                    p["friendStatus"] = friend_status(friends, p["puuid"], p["summonerId"])
            return {"ok": True, **result}
        except Exception as e:
            return self._fail(str(e))

    def send_team_review(self, lines):
        """一键发送队友评价：选人阶段发选人房间，对局中发队伍聊天。"""
        try:
            if not self.lcu.connected:
                self.lcu.connect()
            result = current_game.send_team_review(self.lcu, lines)
            return {"ok": True, **result}
        except LcuError as e:
            return self._fail(str(e))
        except Exception as e:
            return self._fail("发送队友评价失败：{}".format(e))

    def get_recent_summary(self, puuid, game_key=""):
        try:
            if not current_game.valid_puuid(puuid):
                return self._fail("玩家身份未公开，无法查询战绩")
            games, _, _, _ = self.history.page(puuid, 0)
            current_id = str(game_key).split(":", 1)[0]
            games = [g for g in games if str(g.get("gameId")) != current_id]
            # 简要统计无需逐个下载海克斯图标，避免对局中产生大量请求。
            return {"ok": True, "games": games}
        except Exception as e:
            return self._fail(str(e))

    NOTICE_SIZE = (460, 340)
    # 每次打包发版递增：界面左下角会显示，方便确认跑的是哪一版。
    VERSION = "2026-09-10.7"

    def get_version(self):
        return {"ok": True, "version": self.VERSION}

    def _notice_state_path(self):
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "LOL战绩查询"
        return base / "notice-window.json"

    def _notice_position_on_screen(self, x, y, bounds=None):
        """坐标必须落在某块屏幕内，避免换显示器后弹窗跑到看不见的地方。"""
        if bounds is None:
            bounds = _screen_bounds()
        if not bounds:
            return True
        width, height = self.NOTICE_SIZE
        for sx, sy, sw, sh in bounds:
            # 允许少量出界，但要留住可以拖回来的部分。
            if (sx - width + 80 <= x <= sx + sw - 80
                    and sy - height + 60 <= y <= sy + sh - 60):
                return True
        return False

    def _load_notice_position(self):
        if self._notice_position:
            return self._notice_position
        try:
            data = json.loads(self._notice_state_path().read_text(encoding="utf-8"))
            x, y = int(data["x"]), int(data["y"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return (x, y) if self._notice_position_on_screen(x, y) else None

    def _write_notice_position(self, x, y):
        try:
            path = self._notice_state_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = str(path) + ".tmp"
            with open(temporary, "w", encoding="utf-8") as f:
                json.dump({"x": int(x), "y": int(y)}, f)
            os.replace(temporary, path)
        except (OSError, TypeError, ValueError):
            pass

    def _remember_notice_position(self, x, y):
        """拖动事件很密集：内存里实时更新，落盘做 1 秒节流。"""
        try:
            x, y = int(x), int(y)
        except (TypeError, ValueError):
            return
        with self._notice_position_lock:
            self._notice_position = (x, y)
            now = time.monotonic()
            if now - self._notice_position_saved < 1.0:
                return
            self._notice_position_saved = now
        self._write_notice_position(x, y)

    def _flush_notice_position(self, window):
        """关闭弹窗前把最终位置落盘（窗口已销毁时退回最后一次记录）。"""
        try:
            position = (int(window.x), int(window.y))
        except Exception:
            position = self._notice_position
        if position:
            self._write_notice_position(*position)

    def notify_current_game(self, game_key, mode):
        if not self._main_window or not game_key or game_key in self._notified_games:
            return {"ok": True}
        try:
            self.close_game_notice()
            markup = Path(resource_path("ui/notice.html")).read_text(encoding="utf-8")
            markup = markup.replace("{{MODE}}", html.escape(str(mode)))
            # WebView2 的 HTML 字符串页面不能加载 file:// 子资源，直接内嵌离线样式和图标。
            css = Path(resource_path("ui/style.css")).read_text(encoding="utf-8")
            markup = markup.replace('<link rel="stylesheet" href="style.css">', '<style>' + css + '</style>')
            icon = base64.b64encode(Path(resource_path("ui/app-icon.png")).read_bytes()).decode("ascii")
            markup = markup.replace('src="app-icon.png"', 'src="data:image/png;base64,' + icon + '"')
            x, y = self._load_notice_position() or (None, None)
            self._current_window = webview.create_window("当前对局提醒", html=markup, js_api=self,
                width=self.NOTICE_SIZE[0], height=self.NOTICE_SIZE[1], x=x, y=y,
                resizable=False, on_top=True, background_color="#080b14")
            # 用户每次拖动都记住位置，下次对局直接沿用。
            self._current_window.events.moved += self._remember_notice_position
            self._notified_games.add(game_key)
            return {"ok": True}
        except Exception:
            return self._fail("系统弹窗不可用，请从主界面查看当前对局")

    def close_game_notice(self):
        if self._current_window:
            self._flush_notice_position(self._current_window)
            try:
                self._current_window.destroy()
            except Exception:
                pass
            finally:
                self._current_window = None

    def show_current_game(self):
        if self._main_window:
            self._main_window.restore()
            self._main_window.show()
            self._main_window.evaluate_js("CurrentGame.open()")
        self.close_game_notice()

    def get_champion_map(self):
        m = champions.get_champion_map()
        return {"ok": True, "count": len(m), "champions": [
            {"id": int(cid), "name": champions.champion_name(cid), "avatar": champions.champion_avatar(cid, self.lcu)} for cid in m
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

    # ---------- 优选海克斯（按英雄的优先级清单） ----------

    def get_augment_catalog(self):
        try:
            client = self.lcu if self.lcu.connected else None
            return {"ok": True, "augments": A.catalog(client)}
        except Exception as e:
            return self._fail("读取海克斯资料失败：{}".format(e))

    def get_augment_preferences(self):
        try:
            return {"ok": True, "preferences": augment_prefs.load()}
        except Exception:
            return self._fail("读取优选海克斯失败")

    def save_augment_preferences(self, preferences):
        try:
            return {"ok": True, "preferences": augment_prefs.save(preferences)}
        except Exception as e:
            return self._fail("保存优选海克斯失败：{}".format(e))


def main():
    api = Api()
    api._main_window = webview.create_window(
        "英雄联盟国服战绩查询",
        url=resource_path("ui/index.html"),
        js_api=api,
        width=1120, height=800, min_size=(920, 620),
        background_color="#080b14",
    )
    api._main_window.events.closed += api.close_game_notice
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
