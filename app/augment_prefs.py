"""优选海克斯清单：按英雄保存用户指定的强化优先级，纯本地文件，不上传。"""
import json
import os
import threading
from pathlib import Path

MAX_CHAMPIONS = 300
MAX_AUGMENTS = 12
_lock = threading.Lock()


def _path():
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "LOL战绩查询"
    return base / "augment-preferences.json"


def _positive_int(value):
    if isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def normalize(raw):
    """只接受 {英雄ID: [强化ID...]}：丢弃非法值、去重、限量，保持用户排序。"""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key, values in raw.items():
        champion = _positive_int(key)
        if not champion or champion in out or not isinstance(values, list):
            continue
        augments, seen = [], set()
        for value in values:
            augment = _positive_int(value)
            if not augment or augment in seen:
                continue
            seen.add(augment)
            augments.append(augment)
            if len(augments) >= MAX_AUGMENTS:
                break
        if augments:
            out[str(champion)] = augments
        if len(out) >= MAX_CHAMPIONS:
            break
    return out


def load():
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    raw = data.get("preferences") if isinstance(data, dict) else data
    return normalize(raw)


def save(raw):
    preferences = normalize(raw)
    with _lock:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = str(path) + ".tmp"
        with open(temporary, "w", encoding="utf-8") as f:
            json.dump({"preferences": preferences}, f, ensure_ascii=False)
        # 先写临时文件再替换：中途失败也不会留下半个文件。
        os.replace(temporary, path)
    return preferences
