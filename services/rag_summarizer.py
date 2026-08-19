"""RAG 总结服务"""
from __future__ import annotations

import logging
from typing import List

from appchef.agents.personal_chief import multimodal_model

logger = logging.getLogger(__name__)


def summarize_question(
    question: str,
    chunks: List[str],
    max_context_length: int = 3000,
) -> str:
    """根据检索到的文档片段，总结回答用户问题。

    Args:
        question: 用户问题
        chunks: 检索到的文档片段列表
        max_context_length: 最大上下文长度（字符）

    Returns:
        总结后的回答
    """
    if not chunks:
        return "未找到相关文档，无法回答问题。"

    # 拼接上下文（限制长度）
    context_parts = []
    total_length = 0

    for chunk in chunks:
        if total_length + len(chunk) > max_context_length:
            break
        context_parts.append(chunk)
        total_length += len(chunk)

    context = "\n\n---\n\n".join(context_parts)

    # 构建提示词
    prompt = f"""你是一个知识助手。请根据以下参考资料回答用户的问题。

【用户问题】
{question}

【参考资料】
{context}

【回答要求】
1. 基于参考资料回答，不要编造信息。
2. 如果参考资料中没有相关信息，请明确说明。
3. 回答要简洁、准确、有条理。
4. 可以适当总结和归纳。

【回答】
"""

    try:
        from langchain_core.messages import HumanMessage
        msg = HumanMessage(content=prompt)
        resp = multimodal_model.invoke([msg])
        answer = (getattr(resp, "content", None) or "").strip()
        logger.info(f"[RAG总结] 问题: {question[:50]}... -> 回答: {answer[:100]}...")
        return answer
    except Exception as e:
        logger.error(f"[RAG总结] 失败: {e}")
        return f"回答失败: {str(e)}"