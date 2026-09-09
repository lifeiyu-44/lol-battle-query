# -*- coding: utf-8 -*-
"""英雄/装备名称与图片映射，数据来自腾讯官方资料站 CDN，本地缓存。"""
import json
import os
import re
import sys
import threading

import requests

CDN_BASE = "https://game.gtimg.cn/images/lol"
CHAMPION_LIST_URL = CDN_BASE + "/act/img/js/heroList/hero_list.js"

_lock = threading.Lock()
_cache = None  # {str(championId): {"name":, "title":, "alias":}}


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
    global _cache
    with _lock:
        if _cache is not None and not force_refresh:
            return _cache
        _load_offline()
        if _cache is not None and not force_refresh:
            return _cache
        try:
            resp = requests.get(CHAMPION_LIST_URL, timeout=10,
                                headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                m = _parse_champion_list(resp.text)
                if m:
                    _cache = m
                    writable, _ = _cache_paths()
                    if writable:
                        try:
                            with open(writable, "w", encoding="utf-8") as f:
                                json.dump(m, f, ensure_ascii=False)
                        except Exception:
                            pass
        except Exception:
            pass
        if _cache is None:
            _cache = {}
        return _cache


def champion_name(champion_id):
    info = get_champion_map().get(str(champion_id))
    if info and info["name"]:
        return info["name"] if not info["title"] else \
            "{}·{}".format(info["title"], info["name"])
    return "英雄#{}".format(champion_id)


def champion_avatar(champion_id):
    info = get_champion_map().get(str(champion_id))
    if info and info["alias"]:
        return "{}/act/img/champion/{}.png".format(CDN_BASE, info["alias"])
    return ""


def item_icon(item_id):
    return "{}/act/img/item/{}.png".format(CDN_BASE, item_id) if item_id else ""
