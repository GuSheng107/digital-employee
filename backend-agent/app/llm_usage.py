from __future__ import annotations

import json
import re
from typing import Any, Iterator


_USAGE_CONTAINER_KEYS = (
    "usage_metadata",
    "response_metadata",
    "additional_kwargs",
    "model_extra",
    "token_usage",
    "usage",
)
_INPUT_TOKEN_KEYS = (
    "input_tokens",
    "prompt_tokens",
    "input_token_count",
    "prompt_token_count",
    "input",
    "prompt",
)
_OUTPUT_TOKEN_KEYS = (
    "output_tokens",
    "completion_tokens",
    "output_token_count",
    "completion_token_count",
    "output",
    "completion",
)
_TOTAL_TOKEN_KEYS = (
    "total_tokens",
    "total_token_count",
    "tokens",
)
_ALL_TOKEN_KEYS = set(_INPUT_TOKEN_KEYS + _OUTPUT_TOKEN_KEYS + _TOTAL_TOKEN_KEYS)


def _as_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
        except Exception:
            dumped = None
        if isinstance(dumped, dict):
            return dumped
    return None


def _coerce_int(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        try:
            return max(0, int(float(str(value).strip())))
        except (TypeError, ValueError):
            return 0


def _first_token_value(mapping: dict[str, Any], keys: tuple[str, ...]) -> int:
    for key in keys:
        if key in mapping:
            value = _coerce_int(mapping.get(key))
            if value:
                return value
    return 0


def _iter_usage_mappings(value: Any, seen: set[int] | None = None) -> Iterator[dict[str, Any]]:
    if value is None:
        return
    if seen is None:
        seen = set()
    value_id = id(value)
    if value_id in seen:
        return
    seen.add(value_id)

    mapping = _as_mapping(value)
    if mapping is not None:
        if any(key in mapping for key in _ALL_TOKEN_KEYS):
            yield mapping
        for key in _USAGE_CONTAINER_KEYS:
            if key in mapping:
                yield from _iter_usage_mappings(mapping.get(key), seen)
        return

    attributes: dict[str, Any] = {}
    for key in _ALL_TOKEN_KEYS:
        if hasattr(value, key):
            attributes[key] = getattr(value, key)
    if attributes:
        yield attributes

    for key in _USAGE_CONTAINER_KEYS:
        nested = getattr(value, key, None)
        if nested is not None:
            yield from _iter_usage_mappings(nested, seen)


def extract_token_usage(value: Any) -> dict[str, int]:
    for usage in _iter_usage_mappings(value):
        input_tokens = _first_token_value(usage, _INPUT_TOKEN_KEYS)
        output_tokens = _first_token_value(usage, _OUTPUT_TOKEN_KEYS)
        total_tokens = max(
            _first_token_value(usage, _TOTAL_TOKEN_KEYS),
            input_tokens + output_tokens,
        )
        if input_tokens or output_tokens or total_tokens:
            return {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            }
    return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}


def content_text(value: Any) -> str:
    content = getattr(value, "content", value)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(str(text))
            elif item is not None:
                parts.append(str(item))
        return "\n".join(parts).strip()
    try:
        return json.dumps(content, ensure_ascii=False, default=str)
    except TypeError:
        return str(content or "")


def estimate_text_tokens(text: Any) -> int:
    value = content_text(text).strip()
    if not value:
        return 0
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", value))
    other_chars = max(0, len(value) - chinese_chars)
    return max(1, chinese_chars + (other_chars + 3) // 4)


def resolve_token_usage(response: Any, prompt: Any = "") -> tuple[dict[str, int], str]:
    tokens = extract_token_usage(response)
    if tokens["total_tokens"] > 0:
        return tokens, "provider"

    input_tokens = estimate_text_tokens(prompt)
    output_tokens = estimate_text_tokens(response)
    total_tokens = input_tokens + output_tokens
    if total_tokens <= 0:
        return tokens, ""
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }, "estimated"
