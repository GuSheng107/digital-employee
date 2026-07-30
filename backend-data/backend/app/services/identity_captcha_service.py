"""算术图片验证码的生成与 Redis 一次性校验。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass

from api_common import ValidationError

from app.core.config import settings
from app.core.redis_client import RedisClientWrapper, get_redis_client

CAPTCHA_WIDTH = 168
CAPTCHA_HEIGHT = 52
CAPTCHA_FONT_SIZE = 27
CAPTCHA_TEXT_MAX_WIDTH = 142
CAPTCHA_LONG_EXPRESSION_LENGTH = 10
CAPTCHA_NOISE_LINE_COUNT = 7
CAPTCHA_NOISE_DOT_COUNT = 22
CAPTCHA_OPERATORS = ("+", "-", "×")
CAPTCHA_COLORS = ("#155eef", "#0f766e", "#7c3aed", "#be123c")


@dataclass(frozen=True)
class CaptchaExpression:
    """验证码表达式及其答案。"""

    text: str
    answer: int


class IdentityCaptchaService:
    """只在 backend-data 内访问 Redis 的验证码服务。"""

    def __init__(
        self,
        redis_client: RedisClientWrapper | None = None,
    ) -> None:
        self._redis = redis_client or get_redis_client()
        self._random = secrets.SystemRandom()

    def create(self) -> dict[str, str | int]:
        """生成验证码、保存答案摘要并返回可直接展示的图片。"""
        challenge_id = secrets.token_urlsafe(24)
        expression = self._create_expression()
        self._redis.set(
            self._redis_key(challenge_id),
            self._answer_digest(challenge_id, expression.answer),
            ttl_seconds=settings.captcha_ttl_seconds,
        )
        return {
            "captcha_id": challenge_id,
            "image_data_url": self._render_svg_data_url(expression.text),
            "expires_in": settings.captcha_ttl_seconds,
        }

    def verify(self, *, captcha_id: str, captcha_answer: str) -> None:
        """消费并校验一次性验证码，错误或过期均返回统一提示。"""
        expected_digest = self._redis.get_delete(self._redis_key(captcha_id))
        normalized_answer = captcha_answer.strip()
        if (
            expected_digest is None
            or not normalized_answer.isdecimal()
            or not hmac.compare_digest(
                expected_digest,
                self._answer_digest(captcha_id, int(normalized_answer)),
            )
        ):
            raise ValidationError(message="验证码错误或已过期，请重新获取")

    def _create_expression(self) -> CaptchaExpression:
        """生成结果非负且便于人工计算的表达式。"""
        operator = self._random.choice(CAPTCHA_OPERATORS)
        if operator == "+":
            left = self._random.randint(1, 20)
            right = self._random.randint(1, 20)
            answer = left + right
        elif operator == "-":
            right = self._random.randint(1, 12)
            left = self._random.randint(right, 24)
            answer = left - right
        else:
            left = self._random.randint(2, 9)
            right = self._random.randint(2, 9)
            answer = left * right
        return CaptchaExpression(
            text=f"{left} {operator} {right} = ?",
            answer=answer,
        )

    def _render_svg_data_url(self, expression: str) -> str:
        """生成带随机干扰线、噪点和轻微旋转的 SVG 图片。"""
        line_nodes = "".join(
            (
                f'<path d="M {self._random.randint(0, CAPTCHA_WIDTH)} '
                f'{self._random.randint(0, CAPTCHA_HEIGHT)} '
                f'Q {self._random.randint(0, CAPTCHA_WIDTH)} '
                f'{self._random.randint(0, CAPTCHA_HEIGHT)} '
                f'{self._random.randint(0, CAPTCHA_WIDTH)} '
                f'{self._random.randint(0, CAPTCHA_HEIGHT)}" '
                f'stroke="{self._random.choice(CAPTCHA_COLORS)}" '
                'stroke-width="1.2" opacity=".28" fill="none"/>'
            )
            for _ in range(CAPTCHA_NOISE_LINE_COUNT)
        )
        dot_nodes = "".join(
            (
                f'<circle cx="{self._random.randint(2, CAPTCHA_WIDTH - 2)}" '
                f'cy="{self._random.randint(2, CAPTCHA_HEIGHT - 2)}" '
                f'r="{self._random.choice((1, 1, 2))}" '
                f'fill="{self._random.choice(CAPTCHA_COLORS)}" opacity=".24"/>'
            )
            for _ in range(CAPTCHA_NOISE_DOT_COUNT)
        )
        rotation = self._random.randint(-4, 4)
        fit_attributes = (
            f' textLength="{CAPTCHA_TEXT_MAX_WIDTH}" '
            'lengthAdjust="spacingAndGlyphs"'
            if len(expression) > CAPTCHA_LONG_EXPRESSION_LENGTH
            else ""
        )
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{CAPTCHA_WIDTH}" '
            f'height="{CAPTCHA_HEIGHT}" viewBox="0 0 {CAPTCHA_WIDTH} '
            f'{CAPTCHA_HEIGHT}">'
            '<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
            '<stop stop-color="#f8fafc"/><stop offset="1" stop-color="#e2e8f0"/>'
            '</linearGradient></defs>'
            f'<rect width="{CAPTCHA_WIDTH}" height="{CAPTCHA_HEIGHT}" rx="8" '
            'fill="url(#bg)"/>'
            f"{line_nodes}{dot_nodes}"
            f'<text x="{CAPTCHA_WIDTH / 2}" y="34" text-anchor="middle" '
            f'transform="rotate({rotation} {CAPTCHA_WIDTH / 2} 26)" '
            f'font-family="Consolas,monospace" font-size="{CAPTCHA_FONT_SIZE}" '
            f'font-weight="700" letter-spacing="2" fill="#172554"{fit_attributes}>'
            f"{expression}</text></svg>"
        )
        encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
        return f"data:image/svg+xml;base64,{encoded}"

    @staticmethod
    def _redis_key(challenge_id: str) -> str:
        return f"{settings.captcha_redis_prefix}:{challenge_id}"

    @staticmethod
    def _answer_digest(challenge_id: str, answer: int) -> str:
        secret = settings.api_key.encode("utf-8")
        value = f"captcha:{challenge_id}:{answer}".encode("utf-8")
        return hmac.new(secret, value, hashlib.sha256).hexdigest()
