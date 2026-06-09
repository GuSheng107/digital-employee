from __future__ import annotations


class AppError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        detail: str = "",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail


class NotFoundError(AppError):
    def __init__(self, message: str = "资源未找到", *, detail: str = "") -> None:
        super().__init__(message, status_code=404, detail=detail)


class ValidationError(AppError):
    def __init__(self, message: str = "请求参数错误", *, detail: str = "") -> None:
        super().__init__(message, status_code=400, detail=detail)


class ConflictError(AppError):
    def __init__(self, message: str = "操作冲突", *, detail: str = "") -> None:
        super().__init__(message, status_code=409, detail=detail)


class ConfigError(AppError):
    def __init__(self, message: str = "配置错误", *, detail: str = "") -> None:
        super().__init__(message, status_code=400, detail=detail)


class DependencyError(AppError):
    def __init__(self, message: str = "依赖不可用", *, detail: str = "") -> None:
        super().__init__(message, status_code=500, detail=detail)


class CryptoError(AppError):
    def __init__(self, message: str = "加解密失败", *, detail: str = "") -> None:
        super().__init__(message, status_code=500, detail=detail)
