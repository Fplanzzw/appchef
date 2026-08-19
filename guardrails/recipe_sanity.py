"""[菜谱步骤幻觉/逻辑护栏] 轻量规则，拦截明显违背常识的表述。"""
from __future__ import annotations

import re


def scan_recipe_sanity(text: str) -> list[str]:
    issues: list[str] = []
    if not text:
        return issues
    # 热油 + 大量冰/冰水 的危险组合
    if re.search(r"(热油|七成热|八成油温)", text) and re.search(r"(冰块|冰水|大量冰)", text):
        issues.append("步骤中同时出现「热油」与「冰块/冰水」，逻辑可能不安全，请复核。")
    if re.search(r"先放油", text) and re.search(r"后放冰", text):
        issues.append("检测到「先放油后放冰」类异常顺序，请复核。")
    # 未煮熟即食用风险
    if "生吃" in text and re.search(r"(鸡肉|猪肉|鸡蛋(?!羹))", text):
        issues.append("涉及生吃肉禽蛋，请确认是否应改为「熟透后食用」。")
    return issues
