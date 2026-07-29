"""公开认证接口限流桶静态定义。"""

from enum import StrEnum


class AuthRateLimitBucket(StrEnum):
    """登录与注册使用的多维 Redis 限流桶。"""

    LOGIN_IP = "login-ip"
    LOGIN_PAIR = "login-pair"
    LOGIN_ACCOUNT = "login-account"
    REGISTER_IP = "register-ip"
    REGISTER_IDENTITY = "register-identity"
    CAPTCHA_IP = "captcha-ip"
