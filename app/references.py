"""公开海斗参考数据。只请求公开统计页，不传递账号或对局信息。"""
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import threading
import time

import requests

SOURCE = "https://aramgg.com"
TTL = 6 * 3600
_lock = threading.Lock()


class Element:
    def __init__(self, tag="", attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def find(self, tag=None, attr=None):
        for child in self.children:
            if isinstance(child, Element):
                if (tag is None or child.tag == tag) and (attr is None or attr in child.attrs):
                    yield child
                yield from child.find(tag, attr)

    def text(self):
        return " ".join(c.text() if isinstance(c, Element) else c for c in self.children)


class Page(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.root = Element()
        self.stack = [self.root]
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        node = Element(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _number(value, scale=1):
    try:
        value = float(value) * scale
        return round(value, 2) if math.isfinite(value) and 0 <= value <= 100 else None
    except (ValueError, TypeError):
        return None


def _augment_id(node):
    for link in node.find("a"):
        match = re.fullmatch(r"/en/augments/(\d+)/?", link.attrs.get("href", ""))
        if match:
            return int(match[1])
    return None


def parse_reference(html, champion_id=0):
    root = Page(html).root
    rows = {}
    if champion_id:
        for node in root.find("tr", "data-win-rate"):
            aid = _augment_id(node)
            # Restrict to the single-augment table, excluding items and combos.
            links = list(node.find("a"))
            if not any(a.attrs.get("data-champion-link-placement") == "augment_table" for a in links):
                continue
            wr = _number(node.attrs["data-win-rate"], 100)
            tier = node.attrs.get("data-tier", "")
            if aid and wr is not None and tier in ("1", "2", "3", "4", "5"):
                rows[str(aid)] = {"id": aid, "winRate": wr, "tier": "T" + tier,
                                  "sampleSize": None}
    else:
        for section in root.find("section", "data-augment-tier"):
            button = next(section.find("button"), None)
            tier = re.search(r"\bT[1-5]\b", button.text() if button else "")
            if not tier:
                continue
            for article in section.find("article"):
                aid = _augment_id(article)
                values = [n.text() for n in article.find("span")
                          if "stat-value" in n.attrs.get("class", "").split()]
                wr = _number(values[0].strip().rstrip("%")) if len(values) == 1 else None
                if aid and wr is not None:
                    rows[str(aid)] = {"id": aid, "winRate": wr, "tier": tier[0],
                                      "sampleSize": None}
    text = root.text()
    patch = (re.search(r"Version\s*:\s*(\d+\.\d+)", text)
             or re.search(r"Current data:\s*Patch\s+(\d+\.\d+)", text))
    if not rows or not patch:
        raise ValueError("公开数据页结构已变化或暂无统计，未生成胜率。")
    # This is the site's publication threshold, not each row's actual sample count.
    minimum = re.search(r"Champion Augments require\s+([\d,]+)\s+games", text)
    updated = re.search(r"updated\s+([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})", text)
    return {"rows": list(rows.values()), "patch": patch[1],
            "sourceUpdated": updated[1] if updated else None,
            "minimumSample": int(minimum[1].replace(",", "")) if minimum and champion_id else None,
            "scope": ("ARAMGG 国服客户端上传样本（非官方全服胜率）" if champion_id
                      else "ARAMGG 整理的腾讯国服公开统计（来源声明）"),
            "championId": champion_id}


def parse_champion_reference(data, champion_id):
    if not isinstance(data, dict) or str(data.get("championId")) != str(champion_id):
        raise ValueError("公开英雄资料不匹配")
    payload = next((entry[1] for entry in data.get("championAugments", [])
                    if isinstance(entry, list) and len(entry) >= 2
                    and str(entry[0]) == str(champion_id)), None)
    stats = json.loads(payload) if isinstance(payload, str) else {}
    history = stats.get("match_history") or {}
    if not history.get("game_patch") or not isinstance(stats.get("augments"), dict):
        raise ValueError("公开英雄统计缺少版本或海克斯资料")
    rows = []
    for aid, row in stats["augments"].items():
        if not aid.isdigit() or not isinstance(row, dict) or str(row.get("tier")) not in ("1", "2", "3", "4", "5"):
            continue
        wr = _number(row.get("win_rate"), 100)
        count = row.get("num_games")
        count = int(count) if str(count).isdigit() and int(count) > 0 else None
        rows.append({"id": int(aid), "winRate": wr, "tier": "T" + str(row["tier"]),
                     "sampleSize": count})
    if not rows:
        raise ValueError("公开英雄统计没有有效记录")
    rows.sort(key=lambda row: (row["tier"], -(row["winRate"] if row["winRate"] is not None else -1)))
    return {"rows": rows, "patch": str(history["game_patch"]),
            "sourceUpdated": history.get("date"),
            "minimumSample": history.get("minimum_augment_games"),
            "scope": "梯队：来源腾讯国服资料；胜率：ARAMGG 客户端上传样本（区域 {}，非官方全服统计）".format(history.get("region") or "未标明"),
            "championId": champion_id}


def _cache_path(champion_id):
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "LOL战绩查询" / "references"
    return base / ("champion-{}.json".format(champion_id) if champion_id else "augments.json")


def get_reference(champion_id=0, force=False):
    champion_id = int(champion_id or 0)
    if not 0 <= champion_id <= 10000:
        raise ValueError("无效的英雄编号")
    url = SOURCE + ("/en/champion-stats/{}".format(champion_id) if champion_id else "/en/augments")
    with _lock:
        path = _cache_path(champion_id)
        cached = None
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(cached, dict) or not cached.get("rows") or cached.get("sourceUrl") != url:
                cached = None
        except (OSError, ValueError):
            pass
        if cached and not force and 0 <= time.time() - cached.get("fetchedEpoch", 0) < TTL:
            return {**cached, "cached": True, "stale": False}
        try:
            data_url = ("https://cdn.dtodo.cn/hextech/champion-details/{}.json".format(champion_id)
                        if champion_id else url)
            response = requests.get(data_url, timeout=12, headers={"User-Agent": "LOL-Battle-Query/1.0"})
            response.raise_for_status()
            result = (parse_champion_reference(response.json(), champion_id) if champion_id
                      else parse_reference(response.text))
            result.update(source="ARAMGG", sourceUrl=url, fetchedEpoch=time.time(),
                          fetchedAt=datetime.now(timezone.utc).isoformat())
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                temp = path.with_suffix(".tmp")
                temp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
                os.replace(temp, path)
            except OSError:
                pass
            return {**result, "cached": False, "stale": False}
        except (requests.RequestException, ValueError) as exc:
            if cached:
                return {**cached, "cached": True, "stale": True,
                        "warning": "公开数据刷新失败，当前显示上次缓存，请留意版本和获取日期。"}
            raise ValueError("公开参考暂不可用，请稍后重试；个人分析仍可使用。") from exc
