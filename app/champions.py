# -*- coding: utf-8 -*-
"""英雄/装备名称与图片映射，数据来自腾讯官方资料站 CDN，本地缓存。"""
import json
import os
import re
import sys
import threading
import base64
import time
from pathlib import Path

import requests

CDN_BASE = "https://game.gtimg.cn/images/lol"
CHAMPION_LIST_URL = CDN_BASE + "/act/img/js/heroList/hero_list.js"

_lock = threading.Lock()
_cache = None  # {str(championId): {"name":, "title":, "alias":}}
_loading = False  # 是否有线程正在从网络补全英雄资料
_local_avatars = {}
_avatar_attempts = {}
_item_icons = {}
_item_paths = None
_item_map_port = None
_item_map_attempt = None


def _cache_paths():
    """返回 (可写缓存路径, 打包内置只读副本)。开发模式下两者相同。"""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bundled = os.path.join(meipass, "champions_cache.json")
        writable_dir = os.path.join(
            os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
            "LOL战绩查询",
        )
        try:
            os.makedirs(writable_dir, exist_ok=True)
        except OSError:
            return None, bundled
        return os.path.join(writable_dir, "champions_cache.json"), bundled
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "champions_cache.json")
    return p, None


def _load_offline():
    global _cache
    writable, bundled = _cache_paths()
    for path in (writable, bundled):
        if not path:
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                _cache = json.load(f)
                return
        except Exception:
            continue
    _cache = None


def _parse_champion_list(text):
    """解析腾讯资料站 hero_list.js：{"hero":[{"heroId","name","title","alias"}...]}"""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    data = json.loads(m.group(0))
    out = {}
    items = data.get("hero") if isinstance(data, dict) else data
    for it in items or []:
        if not isinstance(it, dict):
            continue
        cid = str(it.get("heroId") or it.get("championId") or "")
        if not cid:
            continue
        out[cid] = {
            "name": it.get("name") or "",
            "title": it.get("title") or "",
            "alias": it.get("alias") or it.get("slug") or "",
        }
    return out


def get_champion_map(force_refresh=False):
    global _cache, _loading
    with _lock:
        if _cache is not None and not force_refresh:
            return _cache
        _load_offline()
        if _cache is not None and not force_refresh:
            return _cache
        if _loading:
            # 已有线程在补全资料：不阻塞界面线程，先用当前掌握的数据。
            return _cache if _cache is not None else {}
        _loading = True
    # 网络补全放到锁外，避免首次查询被最长 10 秒的请求拖住。
    fetched = {}
    try:
        resp = requests.get(CHAMPION_LIST_URL, timeout=5,
                            headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            fetched = _parse_champion_list(resp.text)
    except Exception:
        fetched = {}
    with _lock:
        _loading = False
        if fetched:
            _cache = fetched
            writable, _ = _cache_paths()
            if writable:
                try:
                    with open(writable, "w", encoding="utf-8") as f:
                        json.dump(fetched, f, ensure_ascii=False)
                except Exception:
                    pass
        if _cache is None:
            _cache = {}
        return _cache


def warmup():
    """应用启动时后台预热英雄映射，避免首次查询触发同步网络请求。"""
    threading.Thread(target=get_champion_map, name="champion-map-warmup", daemon=True).start()


def champion_name(champion_id):
    info = get_champion_map().get(str(champion_id))
    if info and info["name"]:
        return info["name"] if not info["title"] else \
            "{}·{}".format(info["title"], info["name"])
    return "英雄#{}".format(champion_id)


def champion_avatar(champion_id, lcu=None):
    try:
        cid = int(champion_id)
    except (TypeError, ValueError):
        return ""
    if cid <= 0:
        return ""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    if (base / "ui" / "champion-icons" / (str(cid) + ".png")).is_file():
        # 与页面一起打包，浏览器只加载本地文件，不再依赖外网证书和 CDN。
        return "champion-icons/{}.png".format(cid)
    if cid in _local_avatars:
        return _local_avatars[cid]
    cache = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "LOL战绩查询" / "champion-icons" / (str(cid) + ".png")
    data_url = _read_cached_png(cache)
    if data_url:
        _local_avatars[cid] = data_url
        return data_url
    key = (getattr(lcu, "port", None), cid)
    if lcu and key[0] and time.monotonic() - _avatar_attempts.get(key, float('-inf')) > 30:
        _avatar_attempts[key] = time.monotonic()
        icon = lcu.asset_data_url("/lol-game-data/assets/v1/champion-icons/{}.png".format(cid))
        if icon:
            _local_avatars[cid] = icon
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_bytes(base64.b64decode(icon.partition(',')[2]))
            except OSError:
                pass
            return icon
    info = get_champion_map().get(str(champion_id))
    if info and info["alias"]:
        return "{}/act/img/champion/{}.png".format(CDN_BASE, info["alias"])
    return ""


def _read_cached_png(path):
    try:
        raw = path.read_bytes()
        if raw.startswith(b"\x89PNG\r\n\x1a\n"):
            return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
    except OSError:
        pass
    return ""


def _item_icon_path(item_id, lcu):
    """从客户端 items.json 取装备图标路径；每个端口 5 分钟内最多刷新一次。"""
    global _item_paths, _item_map_port, _item_map_attempt
    port = getattr(lcu, "port", None)
    now = time.monotonic()
    if (_item_paths is None or _item_map_port != port or
            _item_map_attempt is None or now - _item_map_attempt > 300):
        _item_map_attempt, _item_map_port = now, port
        try:
            code, data = lcu.request("GET", "/lol-game-data/assets/v1/items.json", timeout=8)
            if code == 200 and isinstance(data, list):
                paths = {}
                for row in data:
                    if not isinstance(row, dict) or not isinstance(row.get("id"), int):
                        continue
                    icon_path = row.get("iconPath") or ""
                    if icon_path.startswith("/lol-game-data/assets/"):
                        paths[row["id"]] = icon_path
                _item_paths = paths
        except Exception:
            pass
    return (_item_paths or {}).get(item_id, "")


def item_icon(item_id, lcu=None):
    """装备图标：客户端与本地缓存优先，CDN 兜底。

    CDN 在代理/VPN 异常时可能整站不可达，导致详情里的装备全部消失；
    详情查询本来就依赖客户端，图标直接从客户端取并落盘缓存即可离线显示。
    """
    try:
        iid = int(item_id)
    except (TypeError, ValueError):
        return ""
    if iid <= 0:
        return ""
    cached = _item_icons.get(iid)
    if cached:
        return cached
    cache = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / \
        "LOL战绩查询" / "item-icons" / (str(iid) + ".png")
    data_url = _read_cached_png(cache)
    if not data_url and lcu and getattr(lcu, "port", None):
        icon_path = _item_icon_path(iid, lcu)
        if icon_path:
            data_url = lcu.asset_data_url(icon_path)
            if data_url:
                try:
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    cache.write_bytes(base64.b64decode(data_url.partition(",")[2]))
                except OSError:
                    pass
    if not data_url:
        data_url = "{}/act/img/item/{}.png".format(CDN_BASE, iid)
    _item_icons[iid] = data_url
    return data_url
