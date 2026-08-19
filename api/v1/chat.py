from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from starlette.requests import Request
import logging
from appchef.common.logger import logger
from appchef.models.schemas import ChatRequest, RecipeFeedbackRequest, IngredientConfirmRequest
from appchef.agents.personal_chief import (
    search_recipes,
    get_messages,
    clear_messages,
    handle_recipe_feedback,
)

router = APIRouter()


@router.post("/chat/stream")
async def chat_endpoint(request: ChatRequest, http_request: Request):
    """流式对话，支持客户端中断"""
    async def generator():
        try:
            async for chunk in search_recipes(
                prompt=request.message,
                image=request.image_url,
                thread_id=request.thread_id,
                user_id=request.user_id,
                lon=request.lon,
                lat=request.lat,
            ):
                # 检查客户端是否断开连接
                if await http_request.is_disconnected():
                    logger.info("[chat_endpoint] 客户端断开连接，停止生成")
                    break
                yield chunk
        except asyncio.CancelledError:
            logger.info("[chat_endpoint] 生成被取消，停止响应")
            yield "__TERMINATED__\n已终止生成"
        except Exception as e:
            logger.exception("[chat_endpoint] 生成过程中发生错误: %s", e)
            yield "__ERROR__\n生成过程中发生错误，请重试"

    return StreamingResponse(generator(), media_type="text/event-stream")


@router.get("/chat/messages")
async def get_chat_messages(thread_id: str):
    """获取历史消息"""
    messages = get_messages(thread_id)
    return {"messages": messages}


@router.delete("/chat/messages")
async def clear_chat_messages(thread_id: str):
    """清空历史消息"""
    clear_messages(thread_id)
    return {"success": True}


@router.post("/chat/feedback")
async def recipe_feedback_endpoint(request: RecipeFeedbackRequest):
    """食谱反馈：reject（拒绝）、clarify（补充说明）或 dislike（不喜欢）"""
    result = handle_recipe_feedback(
        thread_id=request.thread_id,
        user_id=request.user_id,
        action=request.action,
        recipe_name=request.recipe_name or "",
        recent_recipes=request.recent_recipes or [],
        user_clarification=request.user_clarification,
        feedback_reason=request.feedback_reason,
    )
    return result


@router.post("/chat/confirm-ingredients")
async def confirm_ingredients_endpoint(request: IngredientConfirmRequest):
    """用户确认/修正食材后重新发起请求"""
    # 将确认的食材拼成提示词
    confirmed_text = "、".join(request.confirmed_ingredients)
    unknown_text = "、".join(request.unknown_ingredients) if request.unknown_ingredients else ""

    if unknown_text:
        message = f"已确认食材: {confirmed_text}\n修正的食材: {unknown_text}\n\n请根据这些食材推荐菜谱。"
    else:
        message = f"已确认食材: {confirmed_text}\n\n请根据这些食材推荐菜谱。"

    # 返回 StreamingResponse
    return StreamingResponse(
        search_recipes(
            prompt=message,
            image=None,  # 用户确认后不再需要图片
            thread_id=request.thread_id,
            user_id=request.user_id,
            lon=None,
            lat=None,
        ),
        media_type="text/event-stream",
    )
