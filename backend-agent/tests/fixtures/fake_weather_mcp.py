from fastmcp import FastMCP

mcp = FastMCP("fake-weather")


@mcp.tool()
async def get_weather(city: str) -> dict[str, object]:
    """Return deterministic weather for runtime integration tests."""
    return {"city": city, "weather": "晴", "temperature_c": 26.0, "source": "test"}


if __name__ == "__main__":
    mcp.run(transport="stdio")
