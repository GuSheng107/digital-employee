"""Nacos 配置字段适配层公共工具。

backend-data 与 backend-gateway 都需要把 Nacos 拍平后的环境变量
适配到各自 Settings 期望的字段名（如 POSTGRES_HOST -> CORE_DB_HOST、
MINIO_HOST + MINIO_API_PORT -> MINIO_ENDPOINT）。原本两份实现完全
相同，抽到此处统一维护，避免后续修改时行为漂移。
"""

from __future__ import annotations

import os
from urllib.parse import quote


def copy_overwrite(src_key: str, dst_key: str) -> None:
    """如果 src_key 存在，覆盖 dst_key（Nacos 优先级高于本地 .env）。"""
    src = os.environ.get(src_key)
    if src:
        os.environ[dst_key] = src


def compose_endpoint(host_key: str, port_key: str, endpoint_key: str) -> None:
    """如果 host+port 都存在，拼接为 host:port 覆盖 endpoint（Nacos 优先）。"""
    host = os.environ.get(host_key)
    port = os.environ.get(port_key)
    if host and port:
        os.environ[endpoint_key] = f"{host}:{port}"


def compose_rabbitmq_url() -> None:
    """从 RABBITMQ_HOST + AMQP_PORT + USERNAME + PASSWORD 拼接 amqp:// URL。

    凭证做 URL 编码，避免密码含 @:/ 等特殊字符时 aio-pika 解析错位。
    """
    host = os.environ.get("RABBITMQ_HOST")
    port = os.environ.get("RABBITMQ_AMQP_PORT")
    if not host or not port:
        return
    user = os.environ.get("RABBITMQ_USERNAME", "guest")
    password = os.environ.get("RABBITMQ_PASSWORD", "guest")
    # 对 user/password 做 URL 编码，生产强密码含特殊字符也能正确拼接
    user_quoted = quote(user, safe="")
    pass_quoted = quote(password, safe="")
    os.environ["RABBITMQ_URL"] = f"amqp://{user_quoted}:{pass_quoted}@{host}:{port}/"
