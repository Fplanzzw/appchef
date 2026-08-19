"""[反思优化 Agent] 用户连续拒绝菜谱时，分析原因并建议写入长期记忆的陈述句。"""
from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from appchef.common.logger import logger


_REFLECTION_SYSTEM = """你是膳食推荐系统的「反思」子模块。用户连续拒绝了多道菜谱。
请只输出一个 JSON 对象，字段如下（不要 markdown）：
{
  "summary": "一句中文总结用户可能的原因",
  "hates_category": "若用户讨厌整类食材（如鱼/贝/香菜），写类别名；否则 null",
  "hates_ingredient": "若讨厌具体食材，写食材名；否则 null",
  "allergy_suspected": true/false,
  "preference_note": "口味相关（如偏淡）或 null"
}
"""


def run_reflection_llm(model, recent_recipes: list[str], user_clarification: str) -> dict:
    recipes = "、".join(recent_recipes[-3:])
    human = HumanMessage(
        content=(
            f"最近被拒绝的菜谱：{recipes}。\n"
            f"用户补充说明：{user_clarification or '（无）'}\n"
            "请给出 JSON。"
        )
    )
    try:
        out = model.invoke([SystemMessage(content=_REFLECTION_SYSTEM), human])
        raw = (getattr(out, "content", "") or "").strip()
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return {"summary": raw[:200], "parse_error": True}
        return json.loads(m.group())
    except Exception as e:
        logger.warning("[ReflectionAgent] 解析失败: %s", e)
        return {"summary": str(e), "parse_error": True}


def reflection_to_long_term_rows(parsed: dict) -> list[tuple[str, str]]:
    """返回 (kind, content) 列表，供 MemoryStore.add_long_term。"""
    rows: list[tuple[str, str]] = []
    if not parsed or parsed.get("parse_error"):
        return rows
    if parsed.get("hates_category"):
        rows.append(("hate_category", f"不喜欢整类：{parsed['hates_category']}"))
    if parsed.get("hates_ingredient"):
        rows.append(("hate_ingredient", f"讨厌食材：{parsed['hates_ingredient']}"))
    if parsed.get("allergy_suspected"):
        rows.append(("allergy", "可能存在过敏相关反馈，需避免高风险食材并建议用户咨询医生。"))
    if parsed.get("preference_note"):
        rows.append(("preference", f"口味偏好：{parsed['preference_note']}"))
    if parsed.get("summary") and not rows:
        rows.append(("reflection", parsed["summary"]))
    return rows
