from typing import Any


def success_response(data: Any = None, message: str = "ok") -> dict:
    return {"success": True, "message": message, "data": data}


def fail_response(message: str = "error", data: Any = None) -> dict:
    return {"success": False, "message": message, "data": data}
