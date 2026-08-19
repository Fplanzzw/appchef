"""[定时任务服务] 节日提醒、用户画像更新等周期性任务。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from appchef.memory.store import get_memory_store
from appchef.services.time_context import build_time_context, format_time_context_block
from appchef.agents.reflection import run_reflection_llm, reflection_to_long_term_rows
from appchef.agents.personal_chief import multimodal_model
from appchef.services.amap_client import amap_weather
# 在 scheduler.py 开头添加
import logging
import os

# 禁用 APScheduler 的文件日志
logging.getLogger('apscheduler').setLevel(logging.WARNING)
logging.getLogger('apscheduler.scheduler').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# 节日提醒配置（扩展版）
FESTIVAL_REMINDERS = {
    "春节": {"date": "01-29", "message": "春节快乐！阖家团圆，美食相伴！", "enabled": True, "type": "festival"},
    "元宵节": {"date": "02-12", "message": "元宵佳节，吃汤圆，赏花灯！", "enabled": True, "type": "festival"},
    "清明节": {"date": "04-04", "message": "清明时节，慎终追远，踏青郊游！", "enabled": True, "type": "festival"},
    "端午节": {"date": "06-10", "message": "端午安康！粽子飘香，龙舟竞渡！", "enabled": True, "type": "festival"},
    "七夕节": {"date": "08-10", "message": "七夕浪漫！与心爱的人共进美食！", "enabled": True, "type": "festival"},
    "中秋节": {"date": "09-17", "message": "中秋佳节，月饼配茶，温馨团圆！", "enabled": True, "type": "festival"},
    "重阳节": {"date": "10-11", "message": "重阳登高，敬老爱老，重阳糕正当时！", "enabled": True, "type": "festival"},
    "冬至": {"date": "12-21", "message": "冬至到啦！记得吃饺子或汤圆哦～", "enabled": True, "type": "festival"},
    "腊八节": {"date": "01-07", "message": "腊八节到了！喝一碗腊八粥，温暖一整年！", "enabled": True, "type": "festival"},
    "小年": {"date": "01-23", "message": "小年到！祭灶糖瓜甜，扫尘迎新年！", "enabled": True, "type": "festival"},
}

# 季节性建议配置（根据月份 + 天气）
SEASONAL_REMINDERS = {
    "春季": {
        "months": [3, 4, 5],
        "condition": "春暖花开",
        "hot": "春季温和，推荐清淡养胃的菜谱，如山药炒木耳、清蒸鲈鱼。",
        "cold": "春季乍暖还寒，推荐暖身滋补的菜谱，如当归羊肉汤、白萝卜炖排骨。",
        "rainy": "春季多雨潮湿，推荐祛湿菜谱，如红豆薏米汤、冬瓜排骨汤。",
        "enabled": True,
        "type": "seasonal"
    },
    "夏季": {
        "months": [6, 7, 8],
        "condition": "炎热多雨",
        "hot": "夏季炎热，推荐降火消暑的菜谱，如绿豆汤、凉拌黄瓜、冬瓜排骨汤、杨枝甘露甜品。",
        "moderate": "夏季温和，推荐清淡爽口的菜谱，如丝瓜炒蛋、清蒸鱼、凉拌木耳。",
        "rainy": "夏季多雨，推荐祛湿菜谱，如薏米红豆汤、冬瓜汤、苦瓜炒蛋。",
        "enabled": True,
        "type": "seasonal"
    },
    "秋季": {
        "months": [9, 10, 11],
        "condition": "秋高气爽",
        "hot": "秋季依然炎热，推荐清热润燥的菜谱，如银耳莲子汤、梨汤、百合炒西芹。",
        "moderate": "秋季凉爽干燥，推荐润肺养胃的菜谱，如百合银耳汤、莲子百合粥、白萝卜炖排骨。",
        "cold": "秋季转凉，推荐滋阴润燥的菜谱，如雪梨汤、银耳莲子羹、百合瘦肉汤。",
        "enabled": True,
        "type": "seasonal"
    },
    "冬季": {
        "months": [12, 1, 2],
        "condition": "寒冷干燥",
        "cold": "冬季寒冷，推荐暖身滋补的菜谱，当归羊肉汤、白萝卜炖排骨、红枣枸杞鸡汤。",
        "moderate": "冬季温和，推荐温补菜谱，如山药炖排骨、香菇炖鸡、莲藕排骨汤。",
        "enabled": True,
        "type": "seasonal"
    },
}

# 用户画像更新配置（仅每周一）
USER_PROFILE_UPDATE = {
    "weekly": {"cron": "0 0 * * 1", "message": "每周用户画像更新任务", "enabled": True},
}

class SchedulerService:
    """定时任务服务，管理节日提醒和用户画像更新。"""

    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        self._setup_tasks()

    def _setup_tasks(self):
        """设置所有定时任务。"""
        # 每日检查节日提醒和季节性建议（每天早上9点）
        self.scheduler.add_job(
            self._check_daily_reminders,
            trigger=CronTrigger(hour=9, minute=0),
            id="daily_reminders",
            replace_existing=True,
        )
        logger.info("已添加每日提醒检查任务（每天9:00）")

        # 节日提醒（特定日期触发）
        for festival, config in FESTIVAL_REMINDERS.items():
            if config["enabled"]:
                month, day = config["date"].split("-")
                self.scheduler.add_job(
                    self._send_festival_reminder,
                    trigger=CronTrigger(month=month, day=day, hour=9, minute=0),
                    args=[festival, config["message"], config["type"]],
                    id=f"festival_reminder_{festival}",
                    replace_existing=True,
                )
                logger.info(f"已添加节日提醒: {festival} ({config['date']})")

        # 用户画像更新（每周一凌晨）
        for period, config in USER_PROFILE_UPDATE.items():
            if config["enabled"]:
                self.scheduler.add_job(
                    self._update_user_profile,
                    trigger=CronTrigger.from_crontab(config["cron"]),
                    args=[period],
                    id=f"profile_update_{period}",
                    replace_existing=True,
                )
                logger.info(f"已添加用户画像更新: {period} ({config['cron']})")

    def _check_daily_reminders(self):
        """每日检查季节性建议（根据天气）。"""
        logger.info("[定时任务] 检查每日季节性建议")

        # 获取当前月份
        now = datetime.now()
        current_month = now.month

        # 找到当前季节
        current_season = None
        for season, config in SEASONAL_REMINDERS.items():
            if current_month in config["months"]:
                current_season = season
                break

        if not current_season:
            logger.info("当前月份不在任何季节定义中，跳过季节性建议")
            return

        season_config = SEASONAL_REMINDERS[current_season]

        # 获取天气建议（模拟，实际应调用天气API）
        # 这里简化：假设夏季（6-8月）天气热，其他季节天气适中
        if current_month in [6, 7, 8]:
            weather_condition = "hot"
            message = season_config["hot"]
        elif current_month in [12, 1, 2]:
            weather_condition = "cold"
            message = season_config["cold"]
        else:
            weather_condition = "moderate"
            message = season_config["moderate"]

        # 检查用户设置：是否开启此季节提醒
        mem = get_memory_store()
        user_id = "default"
        settings_key = f"seasonal_{current_season}"
        settings = mem.get_reminder_settings(user_id)
        
        if not settings.get(settings_key, True):
            logger.info(f"[定时任务] 季节性建议已关闭: {current_season}")
            return

        # 写入数据库
        try:
            mem._conn.execute(
                """
                INSERT INTO festival_reminders
                (user_id, reminder_type, season, weather_condition, message, dismissed, created_at)
                VALUES (?, ?, ?, ?, ?, 0, ?)
                """,
                (user_id, "seasonal", current_season, weather_condition, message, now.timestamp()),
            )
            mem._conn.commit()
            logger.info(f"[定时任务] 季节性建议已写入: {current_season} ({weather_condition})")
        except Exception as e:
            logger.error(f"[定时任务] 写入季节性建议失败: {e}")

    def _send_festival_reminder(self, festival: str, message: str, reminder_type: str):
        """发送节日提醒。

        Args:
            festival: 节日名称
            message: 提醒消息
            reminder_type: 提醒类型（festival/seasonal）
        """
        logger.info(f"[定时任务] 节日提醒: {festival} - {message}")

        # 检查用户设置：是否开启此节日提醒
        mem = get_memory_store()
        user_id = "default"
        settings_key = f"festival_{festival}"
        settings = mem.get_reminder_settings(user_id)
        
        if not settings.get(settings_key, True):
            logger.info(f"[定时任务] 节日提醒已关闭: {festival}")
            return

        # 写入数据库
        try:
            now = datetime.now()
            mem._conn.execute(
                """
                INSERT INTO festival_reminders
                (user_id, reminder_type, festival_name, message, dismissed, created_at)
                VALUES (?, ?, ?, ?, 0, ?)
                """,
                (user_id, reminder_type, festival, message, now.timestamp()),
            )
            mem._conn.commit()
            logger.info(f"[定时任务] 节日提醒已写入: {festival}")
        except Exception as e:
            logger.error(f"[定时任务] 写入节日提醒失败: {e}")

    def _update_user_profile(self, period: str):
        """更新用户画像（每周/每月）。

        Args:
            period: 更新周期（weekly）
        """
        logger.info(f"[定时任务] 用户画像更新: {period}")
        mem = get_memory_store()

        # 获取所有用户ID（简化：当前只支持默认用户）
        user_id = "default"

        # 检查用户设置：是否开启用户画像更新
        settings = mem.get_reminder_settings(user_id)
        if not settings.get("profile_update", True):
            logger.info(f"[定时任务] 用户画像更新已关闭")
            return

        # 从短期记忆中提取近期食谱
        recent_recipes_text = mem.recent_short_term_text(user_id, limit=50)
        # 解析出菜谱（简化：提取包含"推荐"、"菜谱"等关键词的内容）
        recent_recipes = [text for text in recent_recipes_text if "推荐" in text or "菜谱" in text]

        if not recent_recipes:
            logger.info("[定时任务] 没有找到近期菜谱，跳过用户画像更新")
            return

        # 运行反思 LLM 分析用户偏好
        analysis = run_reflection_llm(multimodal_model, recent_recipes, "分析用户近期口味变化")

        # 将分析结果写入长期记忆
        for kind, content in reflection_to_long_term_rows(analysis):
            embedding = None  # 实际应调用 embedding 服务
            mem.add_long_term(user_id, kind, content, embedding)

        logger.info(f"[定时任务] 用户画像更新完成，分析了 {len(analysis)} 个偏好维度")

    def shutdown(self):
        """关闭定时任务服务。"""
        self.scheduler.shutdown()
        logger.info("定时任务服务已关闭")


# 全局调度器实例
_scheduler: Optional[SchedulerService] = None

def get_scheduler() -> SchedulerService:
    """获取全局调度器实例。"""
    global _scheduler
    if _scheduler is None:
        _scheduler = SchedulerService()
    return _scheduler


def shutdown_scheduler():
    """关闭全局调度器。"""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        _scheduler = None