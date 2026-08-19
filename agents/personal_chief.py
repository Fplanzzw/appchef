"""[私厨主 Agent] LangChain Agent + LangGraph Sqlite 检查点；叠加记忆/时间/定位/护栏（尽量少改原调用链）。"""
import asyncio
import os
import sqlite3
from pathlib import Path

import dashscope

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_tavily import TavilySearch
from langgraph.checkpoint.sqlite import SqliteSaver
# from langgraph_checkpoint_sqlite import SqliteSaver

from appchef.agents.reflection import reflection_to_long_term_rows, run_reflection_llm
from appchef.agents.vision_extract import extract_ingredients_from_image_url
from appchef.common.logger import logger
from appchef.common.paths import APPCHEF_ROOT, CHECKPOINT_DB, RESOURCES_DIR
from appchef.guardrails.food_safety import scan_food_conflicts
from appchef.guardrails.recipe_sanity import scan_recipe_sanity
from appchef.memory.embedding_dashscope import dashscope_text_embedding
from appchef.memory.store import get_memory_store
from appchef.services.amap_client import format_location_hint
from appchef.services.time_context import build_time_context, format_time_context_block

# --- [环境变量] 优先项目根 .env，避免写死本机路径 ---
for _p in (
    APPCHEF_ROOT.parent / ".env",
    APPCHEF_ROOT / ".env",
    Path.cwd() / ".env",
):
    if _p.is_file():
        load_dotenv(_p)
        break
else:
    load_dotenv()

RESOURCES_DIR.mkdir(parents=True, exist_ok=True)

dashscope.base_http_api_url = "https://dashscope.aliyuncs.com/api/v1"

multimodal_model = init_chat_model(
    model="qwen3.6-plus",
    model_provider="openai",
    base_url=os.getenv("DASHSCOPE_BASE_URL"),
    api_key=os.getenv("DASHSCOPE_API_KEY"),
)

web_search = TavilySearch(max_results=5, topic="general")

# --- [LangGraph 会话检查点] 与业务记忆库分离 ---
_check_conn = sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)
checkpointer = SqliteSaver(_check_conn)
checkpointer.setup()

# --- [多智能体分工说明] 单 Agent 承载：通过 system 约束角色，后续可拆 LangGraph ---
_SYSTEM_BASE = """
你是一名私人厨师（主协调）。团队内还有：
- 视觉同事：已在上下文中提供「冰箱食材识别」结果，请优先采信。
- 营养师同事：需结合用户画像、节气与用餐时段，注意应季与营养均衡；检索菜谱时优先调用 web_search。
- 反思同事：若上下文中提示用户曾拒绝菜谱，请避免重复推荐，并主动调整品类或做法。

收到用户提供的食材照片或清单后，请按以下流程操作：
1. 识别和评估食材：综合「视觉识别」与文字描述，整理「当前可用食材清单」。
2. 智能食谱检索：优先调用 web_search，以可用食材与地域/节气为关键词查找可行菜谱。
3. 多维度评估与排序：从营养价值和制作难度等维度量化打分并排序。
4. 结构化输出：报告含食谱要点、得分、推荐理由；遵守用户长期画像中的过敏与讨厌食材约束。

【重要约束】
- **每次最多推荐 3 道菜谱**，不要超过这个数量。
- 如果上下文中包含定位信息（如「定位」字段），优先推荐该城市的**当地特色菜**。
- 如果上下文中包含「用户拒绝记录」，避免重复推荐被拒绝的菜谱。
- 如果用户的需求菜谱网页上找不到，直接回答不知道。
- 遇到不认识的不确定的食材需要诚实回答：我不认识这个，你能告诉我吗
请严格按照流程，优先调用 web_search；搜索不到时再基于常识谨慎发挥。

"""


def _build_context_block(
    *,
    thread_id: str,
    user_id: str,
    vision_line: str,
    location_hint: str,
) -> str:
    mem = get_memory_store()
    mem.prune_short_term()
    parts = []
    lt = mem.long_term_prompt_block(user_id)
    if lt:
        parts.append(lt)
    st = mem.recent_short_term_text(thread_id, limit=10)
    if st:
        parts.append("【近期对话摘要（短期记忆）】\n" + st)
    if vision_line:
        parts.append("【视觉 Agent · 冰箱食材识别】\n" + vision_line)
    tc = format_time_context_block(build_time_context())
    parts.append(tc)
    if location_hint:
        parts.append("【定位】\n" + location_hint)
    rc, recent = mem.get_rejection_state(thread_id)
    if rc:
        parts.append(
            f"【用户拒绝记录】连续拒绝次数={rc}；最近菜谱={recent}。"
            "若次数≥2，应避免同类踩雷，并优先考虑换大类食材。"
        )
    return "\n\n".join(parts)


agent = create_agent(
    model=multimodal_model,
    tools=[web_search],
    system_prompt=_SYSTEM_BASE,
    checkpointer=checkpointer,
)


async def search_recipes(
    prompt: str,
    image: str,
    thread_id: str,
    user_id: str = "default",
    lon: float | None = None,
    lat: float | None = None,
):
    """流式对话：注入记忆/时间/定位 → 调用 Agent → 护栏扫描 → 写入短期记忆。"""
    logger.info("[search_recipes] user=%s thread=%s msg_len=%s has_image=%s", user_id, thread_id, len(prompt or ""), bool(image))

    vision_data = {"ingredients": [], "unknown": []}
    if image and str(image).strip():
        vision_data = await asyncio.to_thread(extract_ingredients_from_image_url, multimodal_model, image)
        logger.info(f"[search_recipes] 视觉识别结果: {vision_data}")

        # 如果有未知食材，返回特殊标记，前端需要弹出确认框
        if vision_data["unknown"]:
            unknown_str = "、".join(vision_data["unknown"])
            yield f"__NEED_CONFIRMATION__\n以下食材未识别，请确认是否为食材：\n{unknown_str}\n\n如果是食材，请在确认后重新发送请求。"
            # 写入短期记忆（vision记录）
            mem = get_memory_store()
            mem.append_short_term(thread_id, "vision", f"识别结果: {vision_data}")
            mem.append_short_term(thread_id, "user", prompt)
            return

    # 构建视觉行文本（使用已知食材）
    vision_line = ""
    if vision_data["ingredients"]:
        vision_line = f"识别到的食材: {'、'.join(vision_data['ingredients'])}"
    elif image:
        # 如果识别失败但传了图片，提示用户
        vision_line = "未识别到有效食材"

    # 食材验证：检查是否包含非食材或未知食材
    all_ingredients = vision_data["ingredients"] + vision_data["unknown"]
    if all_ingredients:
        # 这里可以添加更复杂的食材验证逻辑
        # 例如：检查食材是否在已知食材数据库中，或者使用LLM验证
        unknown_ingredients = vision_data["unknown"]
        if unknown_ingredients:
            unknown_str = "、".join(unknown_ingredients)
            yield f"__NEED_INGREDIENT_VALIDATION__\n检测到可能非食材的物品：\n{unknown_str}\n\n请确认这些是否为有效食材，以避免错误推荐。"

    loc_hint = ""
    if lon is not None and lat is not None:
        loc_hint = await asyncio.to_thread(format_location_hint, lon, lat)

    ctx = _build_context_block(
        thread_id=thread_id,
        user_id=user_id,
        vision_line=vision_line,
        location_hint=loc_hint,
    )
    user_facing = prompt if not ctx else f"{ctx}\n\n【用户说】\n{prompt}"

    if not image or not str(image).strip():
        message = HumanMessage(content=user_facing)
    else:
        message = HumanMessage(
            content=[
                {"type": "image", "url": image},
                {"type": "text", "text": user_facing},
            ]
        )

    collected: list[str] = []
    try:
        for chunk, _metadata in agent.stream(
            {"messages": [message]},
            {"configurable": {"thread_id": thread_id}},
            stream_mode="messages",
        ):
            if isinstance(chunk, AIMessageChunk) and chunk.content:
                collected.append(chunk.content)
                yield chunk.content
            
            # 检查是否需要终止生成
            # 这里可以添加更多的终止条件检查
            # 例如：检查数据库中的终止标志，或特定的用户指令
            
    except asyncio.CancelledError:
        logger.info("[search_recipes] 生成被取消")
        yield "__TERMINATED__\n已终止生成"
        return
    except Exception as e:
        logger.exception("[search_recipes] Agent 失败: %s", e)
        yield "__ERROR__\n生成过程中发生错误，请重试"
        return

    full_text = "".join(collected)

    # 解析菜谱并限制为最多 3 个
    recipe_count = 0
    recipe_lines = []
    final_text_lines = []

    import re
    # 匹配菜名模式：# 菜名 或 ## 菜名 或 **菜名** 或 ### 菜名
    recipe_pattern = re.compile(r'^(#+\s|#{2,3}\s|\*\*)([^#\n*]+)(\*\*)?', re.MULTILINE)

    # 解析菜谱
    for match in recipe_pattern.finditer(full_text):
        recipe_name = match.group(2).strip()
        if recipe_name:
            recipe_count += 1

    # 如果菜谱超过 3 个，截取前 3 个
    if recipe_count > 3:
        logger.info(f"[search_recipes] 检测到 {recipe_count} 道菜谱，截取前 3 道")

        # 找到前 3 个菜谱的结束位置
        matches = list(recipe_pattern.finditer(full_text))
        if len(matches) > 3:
            end_pos = matches[3].start()
            full_text = full_text[:end_pos]
            full_text += "\n\n**已为你精选 3 道菜谱。如需更多选择，请继续对话！**"

    # 智能菜谱推荐：根据用户反馈调整推荐
    mem = get_memory_store()
    reject_count, recent_recipes = mem.get_rejection_state(thread_id)
    
    if reject_count >= 2:
        # 用户连续拒绝了2个菜谱，需要询问原因
        full_text += "\n\n【智能推荐】检测到您连续拒绝了2道菜谱，可能需要调整推荐策略。请告诉我：是不喜欢当前食材类型，还是口味不合，或是过敏？"
    
    elif reject_count == 1:
        # 用户拒绝了1个菜谱，推荐相似类型的菜谱
        if recent_recipes:
            last_recipe = recent_recipes[-1]
            full_text += f"\n\n【智能推荐】检测到您拒绝了「{last_recipe}」，已为您推荐相似类型的其他菜谱。"
    
    # 记录菜谱推荐到数据库（用于后续分析）
    try:
        # 提取所有菜谱名称
        recipes = []
        for match in recipe_pattern.finditer(full_text):
            recipe_name = match.group(2).strip()
            if recipe_name:
                recipes.append(recipe_name)
        
        # 记录推荐菜谱
        for recipe in recipes:
            mem.record_recipe_feedback(thread_id, user_id, recipe, "like")  # 默认标记为喜欢，用户反馈会更新
        
        logger.info(f"[search_recipes] 推荐了 {len(recipes)} 道菜谱: {recipes}")
    except Exception as e:
        logger.error(f"[search_recipes] 记录菜谱反馈失败: {e}")

    safety = scan_food_conflicts(full_text) + scan_recipe_sanity(full_text)
    for note in safety:
        yield f"\n\n【护栏提示】{note}"

    mem = get_memory_store()
    mem.append_short_term(thread_id, "user", prompt)
    mem.append_short_term(thread_id, "assistant", full_text)
    if vision_line:
        mem.append_short_term(thread_id, "vision", vision_line)


def clear_messages(thread_id: str):
    """清空 LangGraph 线程 + 业务侧拒绝计数（短期记忆可按需保留）。"""
    logger.info("清空历史消息，thread_id: %s", thread_id)
    checkpointer.delete_thread(thread_id)
    get_memory_store().reset_rejection_state(thread_id)


def get_messages(thread_id: str) -> list[dict[str, str]]:
    """获取 LangGraph checkpoint 中的消息（与原行为一致）。"""
    logger.info("获取历史消息，thread_id: %s", thread_id)
    checkpoint = checkpointer.get({"configurable": {"thread_id": thread_id}})
    if not checkpoint:
        return []
    channel_values = checkpoint.get("channel_values")
    if not channel_values:
        return []
    messages = channel_values.get("messages", [])
    if not messages:
        return []
    result = []
    for msg in messages:
        if not msg.content:
            continue
        if isinstance(msg, HumanMessage):
            result.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            result.append({"role": "assistant", "content": msg.content})
    return result


def handle_recipe_feedback(
    *,
    thread_id: str,
    user_id: str,
    action: str,
    recipe_name: str,
    recent_recipes: list[str],
    user_clarification: str | None,
    feedback_reason: str | None = None,
) -> dict:
    """
    action=reject：累计拒绝次数；第 1 次提示换同类，第 2 次起返回反思提问。
    action=clarify：不增加计数，将用户说明经反思 Agent 写入长期记忆（应在看到反思提问后调用）。
    action=dislike：记录不喜欢原因，但不增加拒绝计数
    """
    mem = get_memory_store()

    if action == "clarify":
        count, stored_recent = mem.get_rejection_state(thread_id)
        recipes = recent_recipes or stored_recent
        clar = (user_clarification or "").strip()
        if not clar:
            return {"ok": False, "error": "user_clarification 不能为空", "reject_count": count}
        parsed = run_reflection_llm(multimodal_model, recipes, clar)
        rows = reflection_to_long_term_rows(parsed)
        saved = []
        for kind, text in rows:
            emb = dashscope_text_embedding(text)
            if mem.add_long_term(user_id, kind, text, embedding=emb):
                saved.append({"kind": kind, "content": text})
        mem.reset_rejection_state(thread_id)
        return {
            "ok": True,
            "phase": "reflection_persisted",
            "reject_count": count,
            "recent_recipes": recipes,
            "reflection": parsed,
            "long_term_saved": saved,
        }

    elif action == "dislike":
        # 记录不喜欢原因，但不增加拒绝计数
        if not (recipe_name or "").strip():
            return {"ok": False, "error": "recipe_name 不能为空（action=dislike）"}
        if not feedback_reason:
            return {"ok": False, "error": "feedback_reason 不能为空（action=dislike）"}
        
        # 记录不喜欢反馈
        mem.record_recipe_feedback(thread_id, user_id, recipe_name, "dislike", feedback_reason)
        
        count, stored_recent = mem.get_rejection_state(thread_id)
        recipes = recent_recipes or stored_recent
        
        out: dict = {"ok": True, "reject_count": count, "recent_recipes": recipes, "long_term_saved": []}
        
        # 根据不喜欢原因调整推荐策略
        if "过敏" in feedback_reason:
            out["instruction"] = (
                f"检测到您对「{recipe_name}」有过敏反应。将在后续推荐中避免使用该食材，"
                "并优先推荐不含过敏原的菜谱。"
            )
            out["phase"] = "avoid_allergens"
        elif "口味" in feedback_reason:
            out["instruction"] = (
                f"检测到您不喜欢「{recipe_name}」的口味。将在后续推荐中调整口味偏好，"
                "推荐更符合您口味的菜谱。"
            )
            out["phase"] = "adjust_taste"
        else:
            out["instruction"] = (
                f"检测到您不喜欢「{recipe_name}」。将在后续推荐中避免重复推荐类似菜谱，"
                "并尝试推荐不同类型的菜谱。"
            )
            out["phase"] = "avoid_similar"
        
        return out

    # --- reject ---
    if not (recipe_name or "").strip():
        return {"ok": False, "error": "recipe_name 不能为空（action=reject）"}
    count, stored_recent = mem.record_recipe_rejection(thread_id, recipe_name)
    recipes = recent_recipes or stored_recent

    out: dict = {"ok": True, "reject_count": count, "recent_recipes": recipes, "long_term_saved": []}

    if count == 1:
        out["instruction"] = (
            f"用户拒绝了「{recipe_name}」。请在下一轮优先推荐**同一大类食材的不同菜式**（例如仍是鱼但换烹饪法），"
            "并简要说明与前次的差异。"
        )
        out["phase"] = "swap_same_category"
        return out

    if count >= 2:
        out["phase"] = "reflection_question"
        out["question"] = (
            "连续两道菜都不太合适～更可能是 **口味太重/太淡**，还是 **某类食材（如鱼或芹菜）** 不喜欢，"
            "或有 **过敏**？请用一句话回复；前端收到后请以 action=clarify 调用 /chat/feedback 回传。"
        )
        out["reflection_prompt"] = (
            f"用户连续拒绝了：{'、'.join(recipes)}。分析是食材类别问题还是烹饪方式/口味问题？"
        )
        return out
