
"""[食品安全护栏] 基于常见「食物相克」民间说法做关键词拦截（非医学结论，仅降低风险）。"""
from __future__ import annotations

import re

# (名称A, 名称B, 说明) —— 命中即告警
_CONFLICT_PAIRS = [
    ("西红柿", "螃蟹", "番茄与大量海鲜同食可能引起肠胃不适风险，建议避免同一道菜中混用。"),
    ("番茄", "螃蟹", "同上。"),
    ("柿子", "螃蟹", "传统认为易致胃肠不适，建议分开食用。"),
    ("菠菜", "豆腐", "高草酸与钙结合可能影响吸收，建议焯水并适量。"),
    ("蜂蜜", "葱", "民间说法认为同用可能刺激肠胃，建议分开。"),
]


def scan_food_conflicts(text: str) -> list[str]:
    t = text or ""
    issues: list[str] = []
    for a, b, msg in _CONFLICT_PAIRS:
        if a in t and b in t:
            issues.append(f"{a}+{b}：{msg}")
    # 简单模式：「相克」类自我矛盾输出
    if re.search(r"(相克|不能一起吃).{0,12}(推荐|可以一起)", t):
        issues.append("文案中同时出现「相克」与「推荐同食」，请人工复核。")
    return issues
