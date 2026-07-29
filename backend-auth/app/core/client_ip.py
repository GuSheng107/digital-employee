"""在可信代理边界内解析认证请求的客户端 IP。"""

from __future__ import annotations

from ipaddress import ip_address, ip_network

from fastapi import Request

from app.core.config import settings


def _is_trusted_proxy(value: str) -> bool:
    """判断 IP 是否属于配置的可信代理网络。"""
    try:
        candidate = ip_address(value)
    except ValueError:
        return False
    for network_value in settings.trusted_proxy_networks_list:
        try:
            if candidate in ip_network(network_value, strict=False):
                return True
        except ValueError:
            continue
    return False


def _normalize_ip(value: str) -> str | None:
    """校验并规范化 IPv4/IPv6 文本。"""
    try:
        return str(ip_address(value.strip()))
    except ValueError:
        return None


def resolve_client_ip(request: Request) -> str | None:
    """解析真实客户端 IP，非可信直连请求不得伪造转发头。"""
    peer_ip = _normalize_ip(request.client.host) if request.client else None
    if peer_ip is None or not _is_trusted_proxy(peer_ip):
        return peer_ip

    forwarded_for = request.headers.get("X-Forwarded-For", "")
    forwarded_ips = [
        normalized
        for item in forwarded_for.split(",")
        if (normalized := _normalize_ip(item)) is not None
    ]
    if not forwarded_ips:
        return peer_ip

    for candidate in reversed([*forwarded_ips, peer_ip]):
        if not _is_trusted_proxy(candidate):
            return candidate
    return forwarded_ips[0]
