"""Minimal public-weather FastMCP server used by the phase 1 demo Agent."""

from __future__ import annotations

import httpx
from fastmcp import FastMCP

mcp = FastMCP("weather-demo")

WEATHER_CODES = {
    0: "晴",
    1: "大致晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "毛毛雨",
    53: "毛毛雨",
    55: "强毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "阵雨",
    81: "阵雨",
    82: "强阵雨",
    95: "雷暴",
}


@mcp.tool()
async def get_weather(city: str) -> dict[str, object]:
    """查询指定城市当前天气。参数 city 是中文或英文城市名，例如 北京 或 Beijing。"""
    city = city.strip()
    if not city:
        return {"ok": False, "error": "city 不能为空"}

    timeout = httpx.Timeout(12.0)
    headers = {"Accept": "application/json", "User-Agent": "backend-agent-weather-demo/0.1"}
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        try:
            geocoding = await client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city, "count": 1, "language": "zh", "format": "json"},
            )
            geocoding.raise_for_status()
            places = geocoding.json().get("results") or []
            if not places:
                return {"ok": False, "error": f"未找到城市：{city}"}
            place = places[0]
            weather = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": place["latitude"],
                    "longitude": place["longitude"],
                    "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
                    "timezone": "auto",
                },
            )
            weather.raise_for_status()
            current = weather.json()["current"]
        except (httpx.HTTPError, KeyError, TypeError) as exc:
            return {"ok": False, "error": f"天气服务暂时不可用：{type(exc).__name__}"}

    code = int(current["weather_code"])
    return {
        "ok": True,
        "city": place["name"],
        "country": place.get("country"),
        "observed_at": current.get("time"),
        "weather": WEATHER_CODES.get(code, f"天气代码 {code}"),
        "temperature_c": current.get("temperature_2m"),
        "apparent_temperature_c": current.get("apparent_temperature"),
        "wind_speed_kmh": current.get("wind_speed_10m"),
        "source": "Open-Meteo",
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
