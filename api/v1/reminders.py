"""节日提醒 API"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from appchef.memory.store import get_memory_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reminders", tags=["reminders"])


class FestivalReminderItem(BaseModel):
    id: int
    reminder_type: str  # festival/seasonal
    festival_name: Optional[str]
    season: Optional[str]
    weather_condition: Optional[str]
    message: str
    created_at: str


class DismissReminderRequest(BaseModel):
    reminder_id: int
    permanently_dismiss: bool = False  # True: 永久关闭此节日/季节提醒


class ReminderSettingRequest(BaseModel):
    reminder_type: str  # festival/seasonal/profile_update
    reminder_name: str  # 节日名称或季节名称
    enabled: bool  # True:开启, False:关闭


class ReminderSettingsResponse(BaseModel):
    settings: dict[str, bool]


@router.get("/festival", response_model=list[FestivalReminderItem])
async def get_active_reminders(user_id: str = "default") -> list[FestivalReminderItem]:
    """获取未关闭的节日/季节提醒列表。

    Args:
        user_id: 用户ID（默认 default）

    Returns:
        未关闭的提醒列表
    """
    mem = get_memory_store()
    try:
        with mem._lock:
            rows = mem._conn.execute(
                """
                SELECT id, reminder_type, festival_name, season, weather_condition, message, created_at
                FROM festival_reminders
                WHERE user_id = ? AND dismissed = 0
                ORDER BY created_at DESC
                LIMIT 10
                """,
                (user_id,),
            ).fetchall()

        results = []
        for row in rows:
            created_dt = datetime.fromtimestamp(row["created_at"])
            results.append(
                FestivalReminderItem(
                    id=row["id"],
                    reminder_type=row["reminder_type"],
                    festival_name=row["festival_name"],
                    season=row["season"],
                    weather_condition=row["weather_condition"],
                    message=row["message"],
                    created_at=created_dt.isoformat(),
                )
            )
        return results
    except Exception as e:
        logger.error(f"获取提醒列表失败: {e}")
        return []


@router.post("/dismiss")
async def dismiss_reminder(request: DismissReminderRequest, user_id: str = "default") -> dict:
    """关闭提醒（临时关闭或永久关闭）。

    Args:
        request: DismissReminderRequest
        user_id: 用户ID（默认 default）

    Returns:
        操作结果
    """
    mem = get_memory_store()
    try:
        with mem._lock:
            if request.permanently_dismiss:
                # 永久关闭：删除该记录
                mem._conn.execute(
                    "DELETE FROM festival_reminders WHERE id = ? AND user_id = ?",
                    (request.reminder_id, user_id),
                )
                logger.info(f"永久关闭提醒 id={request.reminder_id}")
            else:
                # 临时关闭：标记为已关闭
                mem._conn.execute(
                    "UPDATE festival_reminders SET dismissed = 1 WHERE id = ? AND user_id = ?",
                    (request.reminder_id, user_id),
                )
                logger.info(f"临时关闭提醒 id={request.reminder_id}")
            mem._conn.commit()

        return {"status": "success", "message": "提醒已关闭"}
    except Exception as e:
        logger.error(f"关闭提醒失败: {e}")
        raise HTTPException(status_code=500, detail=f"关闭提醒失败: {str(e)}")


@router.get("/settings", response_model=ReminderSettingsResponse)
async def get_reminder_settings(user_id: str = "default") -> ReminderSettingsResponse:
    """获取用户的提醒设置。

    Args:
        user_id: 用户ID（默认 default）

    Returns:
        用户的提醒设置
    """
    mem = get_memory_store()
    try:
        settings = mem.get_reminder_settings(user_id)
        return ReminderSettingsResponse(settings=settings)
    except Exception as e:
        logger.error(f"获取提醒设置失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取提醒设置失败: {str(e)}")


@router.post("/settings")
async def update_reminder_setting(request: ReminderSettingRequest, user_id: str = "default") -> dict:
    """更新用户的提醒设置。

    Args:
        request: ReminderSettingRequest
        user_id: 用户ID（默认 default）

    Returns:
        操作结果
    """
    mem = get_memory_store()
    try:
        mem.update_reminder_setting(user_id, request.reminder_type, request.reminder_name, request.enabled)
        return {"status": "success", "message": "提醒设置已更新"}
    except Exception as e:
        logger.error(f"更新提醒设置失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新提醒设置失败: {str(e)}")