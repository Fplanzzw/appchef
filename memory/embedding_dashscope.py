"""[DashScope 向量] 用于长期记忆去重；模型名可通过环境变量覆盖。"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional

from appchef.common.logger import logger


def dashscope_text_embedding(text: str) -> Optional[list[float]]:
    """
    调用 DashScope OpenAI 兼容 embedd
    

ings 接口（与 init_chat_model 同 base 时可复用）。
    环境变量：DASHSCOPE_API_KEY, DASHSCOPE_BASE_URL, EMBEDDING_MODEL（默认 text-embedding-v4）
    """
    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    base = (os.getenv("DASHSCOPE_BASE_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-v4").strip()
    if not api_key:
        logger.debug("[Embedding] 无 DASHSCOPE_API_KEY，跳过向量")
        return None
    url = f"{base}/embeddings"
    body = json.dumps({"model": model, "input": text[:2000]}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        logger.warning("[Embedding] HTTP 错误: %s %s", e.code, e.read()[:300])
        return None
    except Exception as e:
        logger.warning("[Embedding] 请求失败: %s", e)
        return None
    try:
        return raw["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError):
        logger.warning("[Embedding] 响应结构异常: %s", str(raw)[:300])
        return None
