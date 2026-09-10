"""海克斯效果文本：构建时解析公开游戏资源，运行时仅读取内置中文描述。"""
import html
import json
import math
import re
import sys
from pathlib import Path

_cache = None


def render_description(text, values):
    unresolved = False
    lookup = {k.lower(): v for k, v in values.items()}
    def replace(match):
        nonlocal unresolved
        expression = re.fullmatch(r"([\w]+)(?:\*([\d.]+))?", match.group(1))
        data = lookup.get(expression[1].lower()) if expression else None
        numbers = data if isinstance(data, list) else [data]
        if not numbers or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in numbers):
            unresolved = True
            return "（数值以局内为准）"
        multiplier = float(expression[2] or 1)
        parts = list(dict.fromkeys(format(v * multiplier, '.5g') for v in numbers))
        return parts[0] if len(parts) == 1 else '/'.join(parts) + '（随等级变化）'
    text = re.sub(r'@([^@]+)@', replace, text or '')
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    text = re.sub(r'<[^>]*>', '', text)
    text = re.sub(r'%i:[^%]+%', '', text)
    text = html.unescape(text).replace('\xa0', ' ')
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return {"description": text, "dynamicValues": unresolved}


def build_rows(kiwi, strings, arena=None):
    rows = {}
    # Arena IDs 与海斗平台 ID 分开读取，不按名称模糊匹配。
    for a in (arena or {}).get('augments', []):
        if isinstance(a.get('id'), int):
            rows[str(a['id'])] = render_description(a.get('tooltip') or a.get('desc'), a.get('dataValues') or {})
    entries = strings.get('entries', {})
    for a in kiwi.values():
        if not isinstance(a, dict) or not isinstance(a.get('AugmentPlatformId'), int):
            continue
        key = a.get('AugmentTooltipTra') or a.get('DescriptionTra') or ''
        text = entries.get(key.lower()) or entries.get((a.get('DescriptionTra') or '').lower())
        if not text:
            continue
        spell = (kiwi.get(a.get('RootSpell')) or {}).get('mSpell') or {}
        values = {v['name']: v.get('values') for v in spell.get('DataValues', []) if isinstance(v, dict) and isinstance(v.get('name'), str)}
        rows[str(a['AugmentPlatformId'])] = render_description(text, values)
    return rows


def get_description(augment_id):
    global _cache
    if _cache is None:
        path = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'ui' / 'augment-descriptions.json'
        try:
            _cache = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            _cache = {}
    row = (_cache.get('rows') or {}).get(str(augment_id), {})
    return {**row, 'descriptionSource': 'CommunityDragon 中文游戏资源', 'descriptionDate': _cache.get('fetchedAt', '')}
