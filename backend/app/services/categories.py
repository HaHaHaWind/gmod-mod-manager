"""从 Workshop 标签推导 Mod 类型(用于按类型分类/筛选)。

Workshop 的 tags 混有「Addon Type」类型标签与描述性标签(Fun/Cartoon 等),
大小写也不统一(map/tool 为小写),这里统一小写后按映射表归一,
取第一个命中的类型作为主类型;无任何类型标签时归为 Other。
"""
from __future__ import annotations

OTHER = "Other"

# 标签(小写) → 归一化类型
_TAG_TO_CATEGORY = {
    "weapon": "Weapon",
    "model": "Model", "playermodel": "Model", "ragdoll": "Model",
    "map": "Map",
    "gamemode": "Gamemode",
    "tool": "Tool",
    "npc": "NPC",
    "vehicle": "Vehicle",
    "servercontent": "ServerContent",
    "entity": "Entity",
    "effects": "Effects", "effect": "Effects",
    "scenic": "Scenery", "scenery": "Scenery",
    "comic": "Comic",
    "screenplay": "Screenplay",
    "pac3": "Pac3",
    "dupes": "Dupes",
    "save": "Save",
    "demo": "Demo",
    "sound": "Sound",
    "animation": "Animation",
}

CATEGORY_ZH = {
    "Weapon": "武器", "Model": "模型/角色", "Map": "地图", "Gamemode": "游戏模式",
    "Tool": "工具", "NPC": "NPC", "Vehicle": "载具", "ServerContent": "服务器内容",
    "Entity": "实体", "Effects": "特效", "Scenery": "场景", "Comic": "漫画",
    "Screenplay": "剧本", "Pac3": "Pac3", "Dupes": "蓝图", "Save": "存档",
    "Demo": "录像", "Sound": "音效", "Animation": "动画", OTHER: "其他",
}

# 展示/下拉的稳定顺序(Other 置末)
CATEGORY_ORDER = ["Weapon", "Model", "Map", "Gamemode", "Tool", "NPC", "Vehicle",
                  "ServerContent", "Entity", "Effects", "Scenery", "Comic",
                  "Screenplay", "Pac3", "Dupes", "Save", "Demo", "Sound",
                  "Animation", OTHER]


def derive_category(tags: list | None) -> str:
    """按标签顺序取第一个命中的类型;无命中返回 OTHER。"""
    for t in tags or []:
        key = (t or "").strip().lower()
        if key in _TAG_TO_CATEGORY:
            return _TAG_TO_CATEGORY[key]
    return OTHER


def category_zh(cat: str | None) -> str:
    key = cat or OTHER
    return CATEGORY_ZH.get(key, key)