# -*- coding: utf-8 -*-
"""海克斯资料：客户端中文资源优先，内置缓存及 CommunityDragon 兜底。"""
import json
import os
import sys
import threading
import time

import requests
from .augment_descriptions import get_description

DATA_PATH = "/lol-game-data/assets/v1/cherry-augments.json"
CDRAGON = "https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/"
DATA_URL = CDRAGON + "zh_cn/v1/cherry-augments.json"
_lock = threading.RLock()
_cache = None
_icons = {}
_last_attempt = None
_client_port = None


def _cache_paths():
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    bundled = os.path.join(base, "augments_cache.json")
    writable = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                            "LOL战绩查询", "augments_cache.json")
    return writable, bundled


def parse_augments(data):
    """保留客户端平台 ID，不将海斗和竞技场同名强化的 ID 混用。"""
    out = {}
    for row in data if isinstance(data, list) else []:
        if not isinstance(row, dict):
            continue
        aid = row.get("id")
        name = row.get("nameTRA") or row.get("simpleNameTRA")
        if not isinstance(aid, int) or aid <= 0 or not isinstance(name, str) or not name.strip():
            continue
        out[str(aid)] = {"name": name.strip(), "rarity": row.get("rarity", ""),
                         "iconPath": row.get("augmentSmallIconPath", "")}
    return out


def get_augment_map(lcu=None):
    global _cache, _last_attempt, _client_port
    with _lock:
        if _cache is None:
            _cache = {}
            writable, bundled = _cache_paths()
            for path in (bundled, writable):
                try:
                    with open(path, encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        _cache.update({k: v for k, v in data.items()
                                       if isinstance(v, dict) and v.get("name")})
                except (OSError, ValueError):
                    pass
        port = getattr(lcu, "port", None)
        if _last_attempt is not None and time.monotonic() - _last_attempt < 300 and port == _client_port:
            return _cache
        _last_attempt, _client_port = time.monotonic(), port
        fresh = {}
        if lcu and port:
            try:
                code, data = lcu.request("GET", DATA_PATH, timeout=4)
                if code == 200:
                    fresh = parse_augments(data)
            except Exception:
                pass
        if not fresh:
            try:
                response = requests.get(DATA_URL, timeout=5)
                response.raise_for_status()
                fresh = parse_augments(response.json())
            except (requests.RequestException, ValueError):
                pass
        if fresh:
            _cache.update(fresh)
            _icons.clear()
            writable, _ = _cache_paths()
            try:
                os.makedirs(os.path.dirname(writable), exist_ok=True)
                temporary = writable + ".tmp"
                with open(temporary, "w", encoding="utf-8") as f:
                    json.dump(_cache, f, ensure_ascii=False)
                os.replace(temporary, writable)
            except OSError:
                pass
        return _cache


def clean_augments(stats):
    out = []
    for i in range(1, 7):
        try:
            value = int(stats.get("playerAugment{}".format(i)) or 0)
        except (TypeError, ValueError):
            continue
        if value > 0:
            out.append(value)
    return out


def augment_info(augment_id, lcu=None):
    info = get_augment_map(lcu).get(str(augment_id)) or {}
    path = info.get("iconPath") or ""
    icon = ""
    if path.startswith("/lol-game-data/assets/"):
        key = (getattr(lcu, "port", None), path)
        with _lock:
            if key not in _icons:
                local = lcu.asset_data_url(path) if lcu and key[0] else ""
                _icons[key] = local or (CDRAGON + "default/" +
                                         path.split("/lol-game-data/assets/", 1)[1].lower())
            icon = _icons[key]
    return {"id": augment_id, "name": info.get("name") or "未知海克斯（资料待更新）",
            "icon": icon, "rarity": info.get("rarity", ""), "resolved": bool(info.get("name")),
            **get_description(augment_id)}


def augment_label(augment_id):
    return augment_info(augment_id)["name"]


def catalog(lcu=None):
    """全部强化的名称/稀有度/图标，用于前端「优选海克斯」的搜索添加。

    图标直接用 CDN 地址，不为整张表逐个读客户端资源（那会发出上千次请求）。
    """
    rows = []
    for key, info in get_augment_map(lcu).items():
        try:
            augment_id = int(key)
        except (TypeError, ValueError):
            continue
        name = info.get("name")
        if augment_id <= 0 or not name:
            continue
        path = info.get("iconPath") or ""
        icon = ""
        if path.startswith("/lol-game-data/assets/"):
            icon = CDRAGON + "default/" + path.split("/lol-game-data/assets/", 1)[1].lower()
        rows.append({"id": augment_id, "name": name,
                     "rarity": info.get("rarity") or "", "icon": icon})
    rows.sort(key=lambda row: (row["name"], row["id"]))
    return rows
