"""[日历/时间上下文] 晚餐时段、周末、二十四节气（公历近似）——供营养师 Agent 参考。"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

# 二十四节气太阳黄经近似：每月两个节气，用固定公历日做工程近似（非天文级精确）
_SOLAR_TERMS = [
    (1, 5, "小寒"),
    (1, 20, "大寒"),
    (2, 4, "立春"),
    (2, 19, "雨水"),
    (3, 5, "惊蛰"),
    (3, 20, "春分"),
    (4, 4, "清明"),
    (4, 20, "谷雨"),
    (5, 5, "立夏"),
    (5, 21, "小满"),
    (6, 5, "芒种"),
    (6, 21, "夏至"),
    (7, 7, "小暑"),
    (7, 22, "大暑"),
    (8, 7, "立秋"),
    (8, 23, "处暑"),
    (9, 7, "白露"),
    (9, 23, "秋分"),
    (10, 8, "寒露"),
    (10, 23, "霜降"),
    (11, 7, "立冬"),
    (11, 22, "小雪"),
    (12, 7, "大雪"),

]


@dataclass
class TimeContext:
    local_label: str
    is_weekend: bool
    meal_hint: str
    solar_term: Optional[str]
    festival_hint: Optional[str]


def _approx_solar_term(now: dt.datetime) -> Optional[str]:
    m, d = now.month, now.day
    # 找到「上一个」节气名作为背景（简化）
    candidates = [(sm, sd, name) for sm, sd, name in _SOLAR_TERMS if (sm, sd) <= (m, d)]
    if not candidates:
        return "冬至"
    return candidates[-1][2]


def _festival_hint(now: dt.datetime) -> Optional[str]:
    if now.month == 12 and now.day >= 20:
        return "冬至前后：传统上有吃饺子/汤圆的习俗，可在菜谱中适度提及。"
    if now.month == 1 and now.day <= 3:
        return "元旦假期：可推荐家宴、快手菜。"
    return None


def build_time_context(now: Optional[dt.datetime] = None) -> TimeContext:
    now = now or dt.datetime.now()
    w = now.weekday()
    is_weekend = w >= 5
    hour = now.hour
    if 5 <= hour < 10:
        meal = "早餐时段"
    elif 11 <= hour < 14:
        meal = "午餐时段"
    elif 17 <= hour < 21:
        meal = "晚餐时段"
    elif 21 <= hour or hour < 2:
        meal = "夜宵/加餐时段"
    else:
        meal = "非正餐时段"
    solar = _approx_solar_term(now)
    fest = _festival_hint(now)
    return TimeContext(
        local_label=now.strftime("%Y-%m-%d %H:%M 周") + "一二三四五六日"[w],
        is_weekend=is_weekend,
        meal_hint=meal,
        solar_term=solar,
        festival_hint=fest,
    )


def format_time_context_block(ctx: TimeContext) -> str:
    lines = [
        f"- 当前时间：{ctx.local_label}",
        f"- 是否周末：{'是' if ctx.is_weekend else '否'}",
        f"- 用餐语境：{ctx.meal_hint}",
    ]
    if ctx.solar_term:
        lines.append(f"- 当前节气（近似）：{ctx.solar_term}")
    if ctx.festival_hint:
        lines.append(f"- 节日/习俗提示：{ctx.festival_hint}")
    return "【时间与节气上下文】\n" + "\n".join(lines)
