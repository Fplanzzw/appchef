"""[视觉 Agent] 单次多模态调用，从冰箱照片抽取食材清单（写入当轮上下文，不入主 Agent 工具循环以控成本）。"""
from __future__ import annotations

import json
import os
from typing import Dict, List

from langchain_core.messages import HumanMessage

from appchef.common.logger import logger


def load_ingredient_vocabulary() -> set[str]:
    """加载食材词库"""
    import pathlib
    vocab_path = pathlib.Path(__file__).parent.parent / "resources" / "ingredient_vocabulary.txt"
    try:
        with open(vocab_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            # 跳过注释行和空行
            ingredients = set()
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # 如果是类别标题（如"## 蔬菜类"），跳过
                if line.startswith("#") or line.startswith("###"):
                    continue
                ingredients.add(line)
            return ingredients
    except FileNotFoundError:
        logger.warning(f"食材词库文件不存在: {vocab_path}")
        return set()


_INGREDIENT_VOCAB = load_ingredient_vocabulary()


def extract_ingredients_from_image_url(multimodal_model, image_url: str) -> Dict[str, List[str]]:
    """从图片中提取食材，返回结构化数据（包含已知和未知食材）。

    Args:
        multimodal_model: 多模态模型
        image_url: 图片URL

    Returns:
        Dict: {"ingredients": [...], "unknown": [...]}
    """
    if not image_url or not str(image_url).strip():
        return {"ingredients": [], "unknown": []}
    msg = HumanMessage(
        content=[
            {"type": "image", "url": image_url},
            {
                "type": "text",
                "text": (
                    "你是冰箱食材识别助手。请严格按以下规则识别图片中的食材："
                    "1. 仅输出JSON格式，不要任何解释。"
                    "2. 每个食材需包含「名称」和「置信度」（0.0-1.0，1.0=100%确定）。"
                    "3. 若无法辨认某个物体，名称填「未知食材」，置信度≤0.5，并在「备注」中描述特征（如“绿色叶片，根部白色”）。\n"
                    "4. 示例："
                    "   {\"ingredients\": [\n"
                    "      {\"name\": \"西红柿\", \"confidence\": 0.98, \"note\": \"红色圆形果实\"},\n"
                    "      {\"name\": \"未知食材\", \"confidence\": 0.4, \"note\": \"绿色叶片，根部白色，疑似生菜但看不清\"}\n"
                    "   ]}"
                ),
            },
        ]
    )
    try:
        resp = multimodal_model.invoke([msg])
        text = (getattr(resp, "content", None) or "").strip()

        # 尝试解析JSON
        try:
            data = json.loads(text)
            if not isinstance(data, dict) or "ingredients" not in data:
                raise ValueError("返回格式不正确")

            ingredients = data.get("ingredients", [])

            # 校验食材：对比词库
            known = []
            unknown = []
            for ing in ingredients:
                ing = ing.strip()
                if not ing:
                    continue
                # 检查是否在词库中
                if any(ing in vocab_word or vocab_word in ing for vocab_word in _INGREDIENT_VOCAB):
                    known.append(ing)
                else:
                    unknown.append(ing)

            return {"ingredients": known, "unknown": unknown}
        except json.JSONDecodeError:
            # 如果解析失败，尝试从文本中提取
            logger.warning(f"Vision返回的不是JSON，尝试解析: {text}")
            # 假设返回的是用顿号分隔的列表
            if "、 " in text or "、" in text:
                ingredients = text.replace("、", "、").split("、")
                ingredients = [ing.strip() for ing in ingredients if ing.strip()]

                known = []
                unknown = []
                for ing in ingredients:
                    if any(ing in vocab_word or vocab_word in ing for vocab_word in _INGREDIENT_VOCAB):
                        known.append(ing)
                    else:
                        unknown.append(ing)

                return {"ingredients": known, "unknown": unknown}
            else:
                # 无法解析，全部作为未知
                return {"ingredients": [], "unknown": [text]}
    except Exception as e:
        logger.warning("[VisionAgent] 识别失败: %s", e)
        return {"ingredients": [], "unknown": []}