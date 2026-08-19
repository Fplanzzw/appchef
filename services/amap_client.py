"""[高德地图] 逆地理编码等轻量封装，API Key 从环境变量读取。"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any, Optional

from appchef.common.logger import logger


def _get_gaode_key() -> str:
    """读取高德 API Key，优先 GAODE_KEY，回退 AMAP_API_KEY / AMAP_WEB_KEY。"""
    return (
        os.getenv("GAODE_KEY", "").strip()
        or os.getenv("AMAP_API_KEY", "").strip()
        or os.getenv("AMAP_WEB_KEY", "").strip()
    )


def _get_gaode_base_url() -> str:
    """读取高德 API 基础 URL，默认 https://restapi.amap.com/v3。"""
    return os.getenv("GAODE_BASE_URL", "https://restapi.amap.com/v3").rstrip("/")


def _get_gaode_timeout() -> float:
    """读取超时秒数，默认 8.0。"""
    try:
        return float(os.getenv("GAODE_TIMEOUT", "8"))
    except (ValueError, TypeError):
        return 8.0


def amap_regeo(lon: float, lat: float, timeout: float | None = None) -> Optional[dict[str, Any]]:
    """
    根据经纬度返回城市/区县等（需 GAODE_KEY / AMAP_API_KEY）。
    失败时返回 None，不阻断主流程。
    """
    key = _get_gaode_key()
    if not key:
        logger.debug("[Amap] 未配置 GAODE_KEY / AMAP_API_KEY，跳过逆地理")
        return None

    base_url = _get_gaode_base_url()
    actual_timeout = timeout if timeout is not None else _get_gaode_timeout()

    params = urllib.parse.urlencode(
        {
            "key": key,
            "location": f"{lon},{lat}",
            "extensions": "base",
        }
    )
    url = f"{base_url}/geocode/regeo?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AppChef/1.0"})
        with urllib.request.urlopen(req, timeout=actual_timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning("[Amap] 请求失败: %s", e)
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if str(data.get("status")) != "1":
        logger.warning("[Amap] 接口 status 非 1: %s", raw[:200])
        return None
    return data


def amap_weather(city_code: str, timeout: float | None = None) -> Optional[dict[str, Any]]:
    """
    查询高德天气接口。
    """
    key = _get_gaode_key()
    if not key:
        logger.debug("[Amap] 未配置 GAODE_KEY / AMAP_API_KEY，跳过天气查询")
        return None

    base_url = _get_gaode_base_url()
    actual_timeout = timeout if timeout is not None else _get_gaode_timeout()

    params = urllib.parse.urlencode({"key": key, "city": city_code})
    url = f"{base_url}/weather/weatherInfo?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AppChef/1.0"})
        with urllib.request.urlopen(req, timeout=actual_timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning("[Amap] 天气请求失败: %s", e)
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if str(data.get("status")) != "1":
        logger.warning("[Amap] 天气接口 status 非 1: %s", raw[:200])
        return None
    return data


def format_location_hint(lon: Optional[float], lat: Optional[float]) -> str:
    if lon is None or lat is None:
        return ""
    info = amap_regeo(float(lon), float(lat))
    if not info:
        return f"用户大致坐标：经度 {lon}，纬度 {lat}。"
    regeo = info.get("regeocode") or {}
    comp = regeo.get("addressComponent") or {}
    parts = [
        comp.get("province"),
        comp.get("city") or comp.get("district"),
        comp.get("district"),
    ]
    addr = " ".join(p for p in parts if p)
    formatted = regeo.get("formatted_address")
    if formatted:
        return f"用户定位解析：{formatted}（{addr}）"
    return f"用户定位解析：{addr}" if addr else ""
