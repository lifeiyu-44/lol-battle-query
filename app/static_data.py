# -*- coding: utf-8 -*-
"""常用静态映射：队列/地图 → 中文名。"""

QUEUE_NAMES = {
    2: "自定义对局",
    4: "匹配模式",
    6: "轮换模式",
    7: "斗魂竞技场",
    8: "斗魂竞技场",
    9: "斗魂竞技场",
    400: "匹配模式",
    410: "排位（动态组排）",
    413: "极限闪击",
    417: "极限闪击",
    420: "排位（单双排）",
    430: "匹配模式",
    440: "排位（灵活组排）",
    450: "极地大乱斗",
    490: "匹配模式",
    700: "冠军杯赛",
    720: "冠军杯赛",
    900: "无限火力",
    910: "无限乱斗",
    920: "无限火力",
    1020: "轮换模式",
    1030: "轮换模式",
    1040: "轮换模式",
    1090: "云顶之弈",
    1100: "云顶之弈（排位）",
    1130: "云顶之弈（狂暴）",
    1160: "云顶之弈（双人）",
    1700: "斗魂竞技场（排位）",
    1710: "斗魂竞技场",
    1900: "无限火力",
    2400: "海克斯大乱斗",
    3270: "海克斯大乱斗",
    30000: "训练模式",
}

MAP_NAMES = {
    1: "召唤师峡谷（练习）",
    8: "水晶之痕",
    10: "扭曲丛林",
    11: "召唤师峡谷",
    12: "嚎哭深渊",
    18: "电磁风暴（闪击）",
    21: "极限闪击",
    30: "竞技场",
    32: "斗魂竞技场",
}

GAME_TYPE_NAMES = {
    "Matchmaking": "匹配对局",
    "Custom Game": "自定义对局",
    "Co-op Vs AI": "人机对局",
    "Practise Tool": "训练模式",
}


def queue_name(queue_id, game_mode, map_id=None):
    try:
        queue_id = int(queue_id)
    except (TypeError, ValueError):
        pass
    if queue_id in QUEUE_NAMES:
        return QUEUE_NAMES[queue_id]
    mode_names = {
        "CLASSIC": "召唤师峡谷",
        "ARAM": "极地大乱斗",
        "KIWI": "海克斯大乱斗",
        "URF": "无限火力",
        "TFT": "云顶之弈",
        "NEXUSBLITZ": "闪击战",
        "ULTBOOK": "终极魔典",
        "ARENA": "斗魂竞技场",
        "CHERRY": "斗魂竞技场",
        "PRACTICETOOL": "训练模式",
    }
    if game_mode in mode_names:
        return mode_names[game_mode]
    if map_id in MAP_NAMES:
        return MAP_NAMES[map_id]
    # 未知队列显示原始 qid，便于联调时补充映射
    return "其他模式(qid:{})".format(queue_id)
