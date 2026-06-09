from __future__ import annotations

"""媒体消息处理模块。

处理非文本媒体消息（图片、视频、音频、文件等），包括消息解析、
下载、类型推断、大小限制检查、附件持久化以及向管理员转发媒体内容。
同时提供媒体 URL/类型推断、文件名规范化等工具函数。
"""

import asyncio
import base64
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, unquote

from agent_runtime.capabilities import ModelCapability, get_model_capabilities
from app.chat_store import get_conversation
from app.db.user_store import get_user_display_name
from app.db.bot_store import make_conversation_key
from wecom_bot.handlers.context import BotContext
from wecom_bot.reply import build_stream_id


# ==================== Media Utility Functions ====================
def is_expected_media_mime(expected_type: str, mime_type: str) -> bool:
    normalized_expected = str(expected_type or "").strip().lower()
    normalized_mime = str(mime_type or "").strip().lower()
    if normalized_expected == "image":
        return normalized_mime.startswith("image/")
    if normalized_expected == "video":
        return normalized_mime.startswith("video/")
    if normalized_expected == "audio":
        return normalized_mime.startswith("audio/")
    return bool(normalized_mime)


def normalize_attachment_filename(file_name: str, mime_type: str, fallback_stem: str) -> str:
    normalized_name = str(file_name or "").strip()
    stem = fallback_stem or "attachment"
    if not normalized_name:
        normalized_name = stem
    clean_mime = str(mime_type or "").split(";")[0].strip().lower()
    guessed_ext = mimetypes.guess_extension(clean_mime) or ""
    if guessed_ext == ".jpe":
        guessed_ext = ".jpg"
    current_suffix = Path(normalized_name).suffix.lower()
    if current_suffix:
        current_guess = mimetypes.guess_type(normalized_name)[0] or ""
        if current_guess and mime_type:
            normalized_current = current_guess.split(";")[0].strip().lower()
            normalized_target = clean_mime
            if normalized_current == normalized_target:
                return normalized_name
        normalized_name = f"{Path(normalized_name).stem}{guessed_ext}" if guessed_ext else Path(normalized_name).stem
        return normalized_name or stem
    return f"{normalized_name}{guessed_ext}" if guessed_ext else normalized_name


def _mime_to_media_kind(mime: str) -> str:
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    return "file"


def guess_type_from_url(url: str) -> tuple[str, str]:
    if not url:
        return "file", "application/octet-stream"
    parsed = urlparse(url)
    path = unquote(parsed.path).lower()
    guessed, _ = mimetypes.guess_type(path)
    if guessed and guessed != "application/octet-stream":
        return _mime_to_media_kind(guessed), guessed
    for param in parsed.query.split("&"):
        if "=" in param:
            k, v = param.split("=", 1)
            if k.lower() in ("ext", "extension", "fileext", "suffix"):
                v_lower = v.lower().strip(".")
                dot_ext = f".{v_lower}" if not v_lower.startswith(".") else v_lower
                guessed, _ = mimetypes.guess_type(f"file{dot_ext}")
                if guessed and guessed != "application/octet-stream":
                    return _mime_to_media_kind(guessed), guessed
    return "file", "application/octet-stream"


def find_nested_aes_key(node: Any) -> str:
    if isinstance(node, dict):
        for raw_key, value in node.items():
            normalized_key = str(raw_key or "").strip().lower().replace("-", "_")
            if normalized_key in {"aeskey", "aes_key"} and isinstance(value, str) and value.strip():
                return value.strip()
        for value in node.values():
            nested_value = find_nested_aes_key(value)
            if nested_value:
                return nested_value
    elif isinstance(node, list):
        for item in node:
            nested_value = find_nested_aes_key(item)
            if nested_value:
                return nested_value
    return ""


def extract_aes_key(body: dict[str, Any]) -> str:
    return find_nested_aes_key(body)


def infer_media_type(body: dict[str, Any], url: str) -> str:
    mime = ""
    for key in ("mime_type", "content_type", "file_type", "media_type", "msgtype", "type"):
        val = body.get(key)
        if isinstance(val, str):
            normalized = val.strip().lower()
            if "/" in normalized:
                mime = normalized
                break
            if normalized in {"image", "video", "audio", "voice", "file"}:
                return "audio" if normalized == "voice" else normalized
    if not mime:
        for nested_key in ("image", "video", "voice", "audio", "file"):
            nested = body.get(nested_key)
            if isinstance(nested, dict):
                nested_type = infer_media_type(nested, url)
                if nested_type != "file":
                    return nested_type
    if not mime:
        filename = extract_media_filename(body)
        if filename:
            guessed, _ = mimetypes.guess_type(filename)
            if guessed:
                mime = guessed.lower()
    if not mime and url:
        guessed_type, guessed_mime = guess_type_from_url(url)
        if guessed_mime != "application/octet-stream":
            mime = guessed_mime
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    return "file"


def guess_media_kind_from_keys(node: dict[str, Any]) -> str:
    for key in node.keys():
        normalized = str(key or "").strip().lower()
        if "video" in normalized:
            return "video"
        if "voice" in normalized or "audio" in normalized:
            return "audio"
        if "file" in normalized or "doc" in normalized:
            return "file"
        if "image" in normalized or "img" in normalized:
            return "image"
    return "file"


def guess_media_kind(node: dict[str, Any], url: str) -> str:
    inferred = infer_media_type(node, url)
    if inferred != "file":
        return inferred
    guessed_type, _ = guess_type_from_url(url)
    if guessed_type != "file":
        return guessed_type
    return guess_media_kind_from_keys(node)


def extract_media_url(node: dict[str, Any], media_type: str) -> str:
    media_keys = {
        "image": ("image_url", "url", "src", "download_url"),
        "video": ("video_url", "url", "src", "download_url"),
        "audio": ("voice_url", "audio_url", "url", "src", "download_url"),
        "file": ("file_url", "url", "src", "download_url"),
    }
    candidates = [node.get(key) for key in media_keys.get(media_type, ("url", "src", "download_url"))]
    for nested_key in ("image", "video", "voice", "audio", "file"):
        nested = node.get(nested_key)
        if isinstance(nested, dict):
            candidates.extend(
                nested.get(key)
                for key in media_keys.get(media_type, ("url", "src", "download_url"))
            )
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip().startswith(("http://", "https://", "data:")):
            return candidate.strip()
        if isinstance(candidate, dict):
            nested = candidate.get("url") or candidate.get("src")
            if isinstance(nested, str) and nested.strip().startswith(("http://", "https://", "data:")):
                return nested.strip()
    return ""


def extract_media_filename(node: dict[str, Any]) -> str:
    for key in ("filename", "file_name", "name", "title"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for nested_key in ("image", "video", "voice", "audio", "file"):
        nested = node.get(nested_key)
        if isinstance(nested, dict):
            nested_name = extract_media_filename(nested)
            if nested_name:
                return nested_name
    return ""


def extract_media_size(node: dict[str, Any]) -> int:
    for key in ("size", "file_size", "filesize", "length"):
        value = node.get(key)
        try:
            if value is not None and int(value) > 0:
                return int(value)
        except (TypeError, ValueError):
            continue
    for nested_key in ("image", "video", "voice", "audio", "file"):
        nested = node.get(nested_key)
        if isinstance(nested, dict):
            nested_size = extract_media_size(nested)
            if nested_size > 0:
                return nested_size
    return 0


def extract_media_mime_type(node: dict[str, Any], url: str, media_type: str) -> str:
    for key in ("mime_type", "content_type", "file_type", "media_type"):
        value = node.get(key)
        if isinstance(value, str) and "/" in value:
            return value.strip().lower()
    for nested_key in ("image", "video", "voice", "audio", "file"):
        nested = node.get(nested_key)
        if isinstance(nested, dict):
            nested_mime = extract_media_mime_type(nested, url, media_type)
            if nested_mime != guess_media_mime_type(url, media_type):
                return nested_mime
    filename = extract_media_filename(node)
    if filename:
        guessed, _ = mimetypes.guess_type(filename)
        if guessed:
            return guessed
    return guess_media_mime_type(url, media_type)


def guess_media_mime_type(url: str, media_type: str) -> str:
    parsed_url = urlparse(str(url or ""))
    guess_target = parsed_url.path or str(url or "")
    guessed, _ = mimetypes.guess_type(guess_target)
    if guessed:
        return guessed
    return {
        "image": "image/jpeg",
        "video": "video/mp4",
        "audio": "audio/mpeg",
        "file": "application/octet-stream",
    }.get(media_type, "application/octet-stream")


def build_media_part(node: dict[str, Any], media_type: str, media_url: str) -> dict[str, Any]:
    part = {
        "type": media_type,
        "url": media_url,
        "mime_type": extract_media_mime_type(node, media_url, media_type),
    }
    filename = extract_media_filename(node)
    if filename:
        part["filename"] = filename
    size = extract_media_size(node)
    if size > 0:
        part["size"] = size
    aes_key = find_nested_aes_key(node)
    if aes_key:
        part["aes_key"] = aes_key
    return part


def normalize_part_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"text", "plain_text", "plaintext", "paragraph"}:
        return "text"
    if text in {"image", "img", "picture"}:
        return "image"
    if text in {"video", "movie"}:
        return "video"
    if text in {"voice", "audio", "sound"}:
        return "audio"
    if text in {"file", "document", "doc"}:
        return "file"
    return text


def extract_text_value(node: dict[str, Any]) -> str:
    for key in ("text", "content", "value", "title", "desc", "description"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = value.get("content")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return ""


def collect_message_parts(
    node: Any,
    parts: list[dict[str, Any]],
    seen: set[tuple[str, str]],
) -> None:
    if isinstance(node, list):
        for item in node:
            collect_message_parts(item, parts, seen)
        return

    if not isinstance(node, dict):
        return

    normalized_type = normalize_part_type(
        node.get("type") or node.get("msgtype") or node.get("content_type") or node.get("item_type")
    )
    text_value = extract_text_value(node)
    media_url = extract_media_url(node, normalized_type)

    if normalized_type == "text" and text_value:
        key = ("text", text_value)
        if key not in seen:
            seen.add(key)
            parts.append({"type": "text", "text": text_value})
        return

    if normalized_type in {"image", "video", "audio", "file"} and media_url:
        actual_type = infer_media_type(node, media_url) if normalized_type == "file" else normalized_type
        key = (actual_type, media_url)
        if key not in seen:
            seen.add(key)
            parts.append(build_media_part(node, actual_type, media_url))
        return

    if media_url and normalized_type in {"", "unknown", "mixed"} and len(node) <= 6:
        guessed_type = guess_media_kind(node, media_url)
        key = (guessed_type, media_url)
        if key not in seen:
            seen.add(key)
            parts.append(build_media_part(node, guessed_type, media_url))
        return

    if text_value and normalized_type in {"paragraph", "plain"}:
        key = ("text", text_value)
        if key not in seen:
            seen.add(key)
            parts.append({"type": "text", "text": text_value})
        return

    for value in node.values():
        collect_message_parts(value, parts, seen)


def extract_message_parts(frame: dict[str, Any], msgtype: str) -> list[dict[str, Any]]:
    body = frame.get("body", {}) or {}
    preferred_nodes = [
        body.get("mixed"),
        body.get("content"),
        body.get("contents"),
        body.get("items"),
        body.get("msg_items"),
        body,
    ]
    parts: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for node in preferred_nodes:
        collect_message_parts(node, parts, seen)
    if msgtype in {"image", "video", "voice", "audio", "file"} and not parts:
        fallback_type = "audio" if msgtype in {"voice", "audio"} else msgtype
        media_url = extract_media_url(body, fallback_type)
        if media_url:
            parts.append(build_media_part(body, fallback_type, media_url))
    for part in parts:
        if part.get("type") == "file":
            actual_type = infer_media_type(part, str(part.get("url", "")).strip())
            if actual_type == "file":
                actual_type = infer_media_type(body, str(part.get("url", "")).strip())
            if actual_type != "file":
                part["type"] = actual_type
                part["mime_type"] = guess_media_mime_type(part.get("url", ""), actual_type)
    return parts


class MediaHandler:
    """媒体消息处理器，负责非文本消息的解析、下载、转发和发送。

    处理图片、视频、音频、文件等媒体类型的消息，包括从企微帧中
    解析媒体部件、下载媒体数据、检查大小限制、持久化附件到本地存储、
    向管理员转发媒体内容以及构建 Agent 可消费的多模态消息载荷。
    """
    def __init__(self, ctx: BotContext) -> None:
        self._ctx: BotContext = ctx

    async def download_image(self, frame: dict[str, Any]) -> tuple[bytes | None, str]:
        try:
            image_url = frame.get("body", {}).get("image_url", "")
            if not image_url:
                return None, ""
            return await self.download_image_from_url(str(image_url))
        except Exception:
            self._ctx.logger.exception("下载图片失败", extra={"category": "network"})
            return None, ""

    async def download_image_from_url(
        self,
        image_url: str,
        aes_key: str = "",
    ) -> tuple[bytes | None, str]:
        try:
            if not image_url:
                return None, ""
            if self._ctx.client is not None:
                result = await self._ctx.client.download_file(image_url, aes_key=aes_key or None)
                buffer = result.get("buffer")
                if buffer:
                    guessed, _ = mimetypes.guess_type(image_url)
                    content_type = guessed or "image/jpeg"
                    return buffer, content_type
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(image_url)
                resp.raise_for_status()
                content_type = str(resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                if not content_type.startswith("image/"):
                    guessed, _ = mimetypes.guess_type(image_url)
                    content_type = guessed or "image/jpeg"
                return resp.content, content_type or "image/jpeg"
        except Exception:
            self._ctx.logger.exception("下载图片失败", extra={"category": "network"})
            return None, ""

    async def materialize_media_part(
        self,
        media_part: dict[str, Any],
        *,
        index: int,
        trace_id: str = "",
    ) -> dict[str, Any]:
        part = dict(media_part)
        media_type = str(part.get("type") or "file").strip().lower()
        file_url = str(part.get("url") or "").strip()
        if media_type not in {"image", "video", "audio", "file"}:
            part.pop("_image_bytes", None)
            return part
        if bool(part.get("oversized")) or not file_url or file_url.startswith("/api/manual-reply-attachments/"):
            part.pop("_image_bytes", None)
            return part

        aes_key = str(part.get("aes_key") or "").strip()
        fallback_name = self.resolve_forward_media_name(part, index=index)
        fallback_mime = str(part.get("mime_type") or "application/octet-stream").strip()
        file_data: bytes | None = None
        detected_mime = fallback_mime

        if media_type == "image":
            existing_bytes = part.get("_image_bytes")
            if isinstance(existing_bytes, bytes) and existing_bytes:
                file_data = existing_bytes
            if file_data is None:
                downloaded_bytes, downloaded_mime = await self.download_image_from_url(file_url, aes_key=aes_key)
                if downloaded_bytes:
                    file_data = downloaded_bytes
                    detected_mime = downloaded_mime
        else:
            downloaded_bytes, downloaded_name = await self.download_file_for_forward(file_url, aes_key=aes_key)
            if downloaded_bytes:
                file_data = downloaded_bytes
                if downloaded_name:
                    part["filename"] = downloaded_name
                    fallback_name = downloaded_name
                if downloaded_name:
                    guessed, _ = mimetypes.guess_type(downloaded_name)
                    if guessed and guessed != "application/octet-stream":
                        detected_mime = guessed

        if not file_data:
            part.pop("_image_bytes", None)
            part["error"] = "download_failed"
            part["url"] = ""
            part["preview_url"] = ""
            if trace_id:
                self._ctx.log_event(
                    trace_id=trace_id,
                    source="message_parser",
                    category="message",
                    message=f"media materialize failed {fallback_name}",
                    level="ERROR",
                )
            return part

        effective_kind = media_type
        if media_type == "file":
            inferred_kind = infer_media_type({"mime_type": detected_mime}, fallback_name)
            if inferred_kind in {"image", "video", "audio"}:
                effective_kind = inferred_kind
        elif not is_expected_media_mime(media_type, detected_mime):
            part.pop("_image_bytes", None)
            part["error"] = "invalid_media_bytes"
            part["url"] = ""
            part["preview_url"] = ""
            if trace_id:
                self._ctx.log_event(
                    trace_id=trace_id,
                    source="message_parser",
                    category="message",
                    message=f"media kind mismatch {fallback_name} expected={media_type} actual={detected_mime}",
                    level="ERROR",
                )
            return part

        actual_size = len(file_data)
        if self.is_size_limit_exceeded(effective_kind, actual_size):
            part.pop("_image_bytes", None)
            part["type"] = effective_kind
            part["size"] = actual_size
            part["oversized"] = True
            part["error"] = "size_limit_exceeded"
            part["url"] = ""
            part["preview_url"] = ""
            if trace_id:
                limit = self.max_attachment_bytes_for_kind(effective_kind)
                self._ctx.log_event(
                    trace_id=trace_id,
                    source="message_parser",
                    category="message",
                    message=f"media exceeds size limit {fallback_name} type={effective_kind} size={actual_size} max={limit}",
                    level="WARNING",
                )
            return part

        file_name = self.resolve_storage_filename(
            part,
            detected_mime=detected_mime,
            fallback_name=fallback_name,
            fallback_stem=f"{effective_kind}-{index}",
        )
        from app.manual_reply_attachments import persist_attachment

        attachment = persist_attachment(
            self._ctx.project_root,
            file_name,
            file_data,
            mime_type=detected_mime,
        )
        part.pop("_image_bytes", None)
        part["type"] = effective_kind
        part["url"] = str(attachment.get("url") or "").strip()
        part["mime_type"] = str(attachment.get("mime_type") or detected_mime).strip() or detected_mime
        part["size"] = int(attachment.get("size") or len(file_data) or 0)
        part["storage_name"] = str(attachment.get("storage_name") or "").strip()
        part["storage_path"] = str(attachment.get("storage_path") or "").strip()
        part["filename"] = str(attachment.get("filename") or file_name).strip() or file_name
        if effective_kind == "image":
            part["preview_url"] = part["url"]
        else:
            part.pop("preview_url", None)
        return part

    async def materialize_display_parts(
        self,
        display_parts: list[dict[str, Any]],
        *,
        trace_id: str = "",
    ) -> list[dict[str, Any]]:
        materialized: list[dict[str, Any]] = []
        for index, part in enumerate(display_parts, start=1):
            materialized.append(await self.materialize_media_part(part, index=index, trace_id=trace_id))
        return materialized

    async def download_file_for_forward(self, file_url: str, aes_key: str = "") -> tuple[bytes | None, str]:
        downloaded_name = ""
        try:
            if self._ctx.client is not None:
                result = await self._ctx.client.download_file(file_url, aes_key=aes_key or None)
                buffer = result.get("buffer")
                downloaded_name = str(result.get("filename") or result.get("name") or "").strip()
                if buffer:
                    return buffer, downloaded_name
            import httpx
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(file_url)
                resp.raise_for_status()
                content_disposition = str(resp.headers.get("content-disposition") or "").strip()
                if content_disposition:
                    from urllib.parse import unquote
                    import re
                    fname_match = re.search(r'filename\*?=[\'"]?(?:UTF-\'\'8)?([^;\'"]+)', content_disposition, re.IGNORECASE)
                    if fname_match:
                        downloaded_name = unquote(fname_match.group(1)).strip()
                return resp.content, downloaded_name
        except Exception:
            self._ctx.logger.exception("下载转发文件失败", extra={"category": "network"})
            return None, downloaded_name

    async def check_video_size_ok(self, video_url: str) -> bool:
        max_video_bytes = self._ctx.settings.agent.max_video_bytes
        if max_video_bytes <= 0:
            return True
        if not video_url.startswith(("http://", "https://")):
            return True
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.head(video_url)
                content_length = resp.headers.get("content-length")
                if content_length and int(content_length) > max_video_bytes:
                    return False
        except Exception:
            self._ctx.logger.warning(
                "HEAD request failed, cannot verify video size — rejecting",
                extra={"category": "network"},
            )
            return False

    async def detect_type_by_download(
        self,
        file_url: str,
        aes_key: str = "",
    ) -> tuple[str, str]:
        guessed_type, guessed_mime = guess_type_from_url(file_url)
        if guessed_type != "file":
            return guessed_type, guessed_mime

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.head(file_url, follow_redirects=True)
                ct = str(resp.headers.get("content-type") or "").split(";")[0].strip().lower()
                if ct and ct != "application/octet-stream":
                    if ct.startswith("image/"):
                        return "image", ct
                    if ct.startswith("video/"):
                        return "video", ct
                    if ct.startswith("audio/"):
                        return "audio", ct
                    return "file", ct
        except Exception:
            pass

        try:
            file_data = None
            if self._ctx.client is not None:
                result = await self._ctx.client.download_file(file_url, aes_key=aes_key or None)
                file_data = result.get("buffer")
                downloaded_name = str(result.get("filename") or result.get("name") or "").strip()
                if downloaded_name:
                    guessed, _ = mimetypes.guess_type(downloaded_name)
                    if guessed and guessed != "application/octet-stream":
                        return _mime_to_media_kind(guessed), guessed
            if not file_data:
                _MAX_DETECT_BYTES = 2 * 1024 * 1024
                import httpx
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(file_url)
                    resp.raise_for_status()
                    file_data = resp.content[:_MAX_DETECT_BYTES]
                self._ctx.logger.info(
                    "HTTP 下载结果",
                    extra={"category": "network", "data_len": len(file_data) if file_data else 0},
                )
            if not file_data:
                return "file", "application/octet-stream"
            return "file", "application/octet-stream"
        except Exception:
            self._ctx.logger.exception("下载检测文件类型失败", extra={"category": "network"})
            return "file", "application/octet-stream"

    def is_forwardable_media_part(self, part: dict[str, Any]) -> bool:
        return str(part.get("type") or "").strip().lower() in {"image", "video", "audio", "file"}

    def resolve_forward_media_name(self, part: dict[str, Any], *, index: int) -> str:
        part_type = str(part.get("type") or "file").strip().lower()
        file_name = str(part.get("filename") or "").strip()
        if file_name:
            return file_name
        mime_type = str(part.get("mime_type") or "").strip().lower()
        guessed_extension = mimetypes.guess_extension(mime_type) or ""
        fallback_names = {
            "image": "image",
            "video": "video",
            "audio": "audio",
            "file": "attachment",
        }
        base_name = fallback_names.get(part_type, "attachment")
        suffix = guessed_extension or ".bin"
        return f"{base_name}-{index}{suffix}"

    def resolve_storage_filename(
        self,
        part: dict[str, Any],
        *,
        detected_mime: str,
        fallback_name: str,
        fallback_stem: str,
    ) -> str:
        original_name = str(part.get("filename") or "").strip()
        if original_name:
            return original_name
        return normalize_attachment_filename(fallback_name, detected_mime, fallback_stem)

    async def send_media_asset(
        self,
        chat_id: str,
        file_data: bytes,
        file_name: str,
        media_type: str,
        *,
        trace_id: str = "",
        **kwargs: Any,
    ) -> bool:
        if self._ctx.client is None:
            raise RuntimeError("WSClient not initialized")

        source = str(kwargs.get("source") or "admin_message")
        frame = kwargs.get("frame") if isinstance(kwargs.get("frame"), dict) else None
        requested_media_type = "voice" if media_type == "audio" else media_type
        if requested_media_type not in {"image", "video", "voice", "file"}:
            self._ctx.logger.warning(
                "媒体发送跳过：未知媒体类型",
                extra={"trace_id": trace_id, "category": "message"},
            )
            return False

        if frame:
            upload_media_type = requested_media_type
        else:
            upload_media_type = "file" if requested_media_type == "image" else requested_media_type
        send_media_type = upload_media_type

        try:
            upload_result = await self._ctx.client.upload_media(
                file_data,
                type=upload_media_type,
                filename=file_name,
            )
            media_id = str(upload_result.get("media_id") or "").strip()
            if not media_id:
                self._ctx.log_event(
                    trace_id=trace_id,
                    source=source,
                    category="message",
                    message=f"媒体上传失败无 media_id {file_name}",
                    level="ERROR",
                )
                return False

            if frame:
                try:
                    await self._ctx.client.reply_media(
                        frame,
                        media_type=send_media_type,
                        media_id=media_id,
                        video_title=file_name if send_media_type == "video" else None,
                    )
                    self._ctx.log_event(
                        trace_id=trace_id,
                        source=source,
                        category="message",
                        message=f"媒体被动回复成功 {file_name} media_type={send_media_type} media_id={media_id}",
                    )
                    return True
                except Exception:
                    pass

            max_send_retries = 3
            retry_delays = [1.0, 2.0, 4.0]
            for attempt in range(max_send_retries):
                try:
                    await self._ctx.client.send_media_message(
                        chat_id,
                        media_type=send_media_type,
                        media_id=media_id,
                        video_title=file_name if send_media_type == "video" else None,
                    )
                    self._ctx.log_event(
                        trace_id=trace_id,
                        source=source,
                        category="message",
                        message=f"媒体已发送 {file_name} media_type={send_media_type} media_id={media_id}",
                    )
                    return True
                except Exception as send_exc:
                    exc_msg = str(send_exc)
                    is_retryable = (
                        "errcode=-1" in exc_msg
                        or "temporarily unavailable" in exc_msg
                        or "ack timeout" in exc_msg.lower()
                        or "timeout" in exc_msg.lower()
                    )
                    if is_retryable and attempt < max_send_retries - 1:
                        delay = retry_delays[attempt]
                        self._ctx.log_event(
                            trace_id=trace_id,
                            source=source,
                            category="message",
                            message=f"媒体发送重试 {file_name} attempt={attempt + 1}/{max_send_retries} delay={delay}s err={exc_msg[:120]}",
                            level="WARNING",
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise
        except Exception as exc:
            self._ctx.logger.exception(
                f"媒体发送失败 {file_name}",
                extra={"trace_id": trace_id, "category": "network"},
            )
            self._ctx.log_event(
                trace_id=trace_id,
                source=source,
                category="message",
                message=f"媒体发送失败 {file_name} {exc}",
                level="ERROR",
            )
            return False

    def max_attachment_bytes_for_kind(self, kind: str) -> int:
        settings = self._ctx.settings.agent
        mapping: dict[str, int] = {
            "image": settings.max_image_bytes,
            "video": settings.max_video_bytes,
            "audio": settings.max_audio_bytes,
            "file": settings.max_file_bytes,
        }
        return mapping.get(kind, 0)

    def is_size_limit_exceeded(self, kind: str, size: int) -> bool:
        limit = self.max_attachment_bytes_for_kind(kind)
        return limit > 0 and size > limit

    def size_limit_exceeded_parts(self, parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            part
            for part in parts
            if bool(part.get("oversized"))
            or str(part.get("error") or "").strip() == "size_limit_exceeded"
        ]

    async def build_non_text_message_payload(
        self,
        frame: dict[str, Any],
        msgtype: str,
        caps: set[ModelCapability],
        provider: Any | None,
        *,
        trace_id: str = "",
    ) -> dict[str, Any]:
        transport_policy = self.resolve_media_transport_policy(provider, caps)
        raw_parts = extract_message_parts(frame, msgtype)
        if not raw_parts:
            raw_parts = [{"type": msgtype, "text": f"用户发送了非文本消息：{msgtype}"}]

        body = frame.get("body", {}) or {}
        aes_key = extract_aes_key(body)

        display_parts: list[dict[str, Any]] = []
        agent_parts: list[dict[str, Any]] = []
        summary_tokens: list[str] = []
        source_kind = "unknown"
        agent_image_transport = "none"
        agent_video_transport = "none"
        unsupported_modalities: list[str] = []
        image_index = 0
        video_index = 0
        audio_index = 0

        for part in raw_parts:
            part_type = str(part.get("type") or "").strip().lower()
            part_aes_key = str(part.get("aes_key") or "").strip() or aes_key
            if part_type == "file":
                inferred_type = infer_media_type(part, str(part.get("url") or "").strip())
                if inferred_type != "file":
                    part_type = inferred_type
            if part_type == "text":
                text = str(part.get("text") or "").strip()
                if not text:
                    continue
                display_parts.append({"type": "text", "text": text})
                agent_parts.append({"type": "text", "text": text})
                summary_tokens.append(text)
                continue

            if part_type == "image":
                image_index += 1
                image_url = str(part.get("url") or "").strip()
                if image_url:
                    source_kind = "url"
                display_parts.append(
                    {
                        "type": "image",
                        "url": image_url,
                        "preview_url": "",
                        "mime_type": "image/jpeg",
                        "aes_key": part_aes_key,
                    }
                )
                summary_tokens.append(f"[图片{image_index}]")
                if not transport_policy["image"]["enabled"]:
                    unsupported_modalities.append("图片")
                    continue
                image_bytes, mime_type = await self.download_image_from_url(image_url, aes_key=part_aes_key)
                if image_bytes:
                    encoded = base64.b64encode(image_bytes).decode()
                    data_url = f"data:{mime_type or 'image/jpeg'};base64,{encoded}"
                    display_parts[-1]["preview_url"] = data_url
                    display_parts[-1]["mime_type"] = mime_type or "image/jpeg"
                    display_parts[-1]["size"] = len(image_bytes)
                    display_parts[-1]["_image_bytes"] = image_bytes
                    max_image_bytes = self._ctx.settings.agent.max_image_bytes
                    if max_image_bytes > 0 and len(image_bytes) > max_image_bytes:
                        display_parts[-1]["preview_url"] = ""
                        display_parts[-1]["oversized"] = True
                        display_parts[-1]["error"] = "size_limit_exceeded"
                        unsupported_modalities.append("图片")
                        summary_tokens[-1] = f"[图片{image_index}:超过大小限制]"
                        self._ctx.log_event(
                            trace_id=trace_id,
                            source="message_parser",
                            category="message",
                            message=f"图片超过大小限制 size={len(image_bytes)} max={max_image_bytes}",
                            level="WARNING",
                        )
                        continue
                    if transport_policy["image"]["mode"] != "none":
                        agent_url = image_url if transport_policy["image"]["mode"] == "url" and image_url.startswith(("http://", "https://")) else data_url
                        agent_image_transport = "url" if agent_url == image_url else "base64"
                        agent_parts.append(
                            {"type": "image_url", "image_url": {"url": agent_url}}
                        )
                else:
                    display_parts[-1]["error"] = "download_failed"
                    if transport_policy["image"]["mode"] == "url" and image_url.startswith(("http://", "https://")):
                        agent_parts.append(
                            {"type": "image_url", "image_url": {"url": image_url}}
                        )
                        agent_image_transport = "url"
                    else:
                        unsupported_modalities.append("图片")
                        summary_tokens[-1] = f"[图片{image_index}:下载失败]"
                continue

            if part_type == "video":
                video_index += 1
                video_url = str(part.get("url") or "").strip()
                if video_url:
                    source_kind = "url"
                display_parts.append(
                    {
                        "type": "video",
                        "url": video_url,
                        "mime_type": str(part.get("mime_type") or "video/mp4"),
                        "aes_key": part_aes_key,
                    }
                )
                summary_tokens.append(f"[视频{video_index}]")
                if not transport_policy["video"]["enabled"]:
                    unsupported_modalities.append("视频")
                    continue
                video_size_ok = await self.check_video_size_ok(video_url)
                if not video_size_ok:
                    display_parts[-1]["oversized"] = True
                    display_parts[-1]["error"] = "size_limit_exceeded"
                    unsupported_modalities.append("视频")
                    summary_tokens[-1] = f"[视频{video_index}:超过大小限制]"
                    continue
                if video_url.startswith(("http://", "https://")):
                    agent_parts.append(
                        {"type": "video_url", "video_url": {"url": video_url}}
                    )
                    agent_video_transport = "url"
                else:
                    unsupported_modalities.append("视频")
                continue

            if part_type == "file":
                file_url = str(part.get("url") or "").strip()
                file_name = str(part.get("filename") or part.get("name") or "").strip()
                file_size = part.get("size") or part.get("file_size") or 0
                try:
                    file_size = int(file_size)
                except (ValueError, TypeError):
                    file_size = 0
                file_mime = str(part.get("mime_type") or "application/octet-stream").strip()
                if file_url:
                    source_kind = "url"
                if self.is_size_limit_exceeded("file", file_size):
                    display_parts.append(
                        {
                            "type": "file",
                            "url": file_url,
                            "filename": file_name,
                            "size": file_size,
                            "mime_type": file_mime,
                            "aes_key": part_aes_key,
                            "oversized": True,
                            "error": "size_limit_exceeded",
                        }
                    )
                    summary_tokens.append(f"[文件:{file_name or '附件'}:超过大小限制]")
                    continue

                if file_mime == "application/octet-stream" and file_url:
                    self._ctx.logger.info(
                        "文件 MIME 为 octet-stream，尝试下载检测实际类型",
                        extra={"trace_id": trace_id, "category": "message", "url_prefix": file_url[:80], "aes_key_found": bool(part_aes_key)},
                    )
                    detected_type, detected_mime = await self.detect_type_by_download(file_url, part_aes_key)
                    self._ctx.logger.info(
                        "文件类型检测结果",
                        extra={"trace_id": trace_id, "category": "message", "detected_type": detected_type, "detected_mime": detected_mime},
                    )
                    if detected_type == "image":
                        image_index += 1
                        image_bytes, _ = await self.download_image_from_url(file_url, aes_key=part_aes_key)
                        preview_url = ""
                        if image_bytes:
                            encoded = base64.b64encode(image_bytes).decode()
                            preview_url = f"data:{detected_mime or 'image/jpeg'};base64,{encoded}"
                        display_parts.append(
                            {
                                "type": "image",
                                "url": file_url,
                                "preview_url": preview_url,
                                "mime_type": detected_mime or "image/jpeg",
                                "aes_key": part_aes_key,
                                "_image_bytes": image_bytes,
                            }
                        )
                        summary_tokens.append(f"[图片{image_index}]")
                        if not preview_url:
                            summary_tokens[-1] = f"[图片{image_index}:下载失败]"
                        continue
                    if detected_type == "video":
                        video_index += 1
                        display_parts.append(
                            {
                                "type": "video",
                                "url": file_url,
                                "mime_type": detected_mime or "video/mp4",
                                "aes_key": part_aes_key,
                            }
                        )
                        summary_tokens.append(f"[视频{video_index}]")
                        continue
                    if detected_type == "audio":
                        audio_index += 1
                        oversized = self.is_size_limit_exceeded("audio", file_size)
                        display_parts.append(
                            {
                                "type": "audio",
                                "url": file_url,
                                "mime_type": detected_mime or "audio/mpeg",
                                "size": file_size,
                                "aes_key": part_aes_key,
                                "oversized": oversized,
                                "error": "size_limit_exceeded" if oversized else "",
                            }
                        )
                        summary_tokens.append(f"[音频{audio_index}{':超过大小限制' if oversized else ''}]")
                        unsupported_modalities.append("音频")
                        continue
                    file_mime = detected_mime or file_mime

                display_parts.append(
                    {
                        "type": "file",
                        "url": file_url,
                        "filename": file_name,
                        "size": file_size,
                        "mime_type": file_mime,
                        "aes_key": part_aes_key,
                    }
                )
                summary_tokens.append(f"[文件:{file_name or '附件'}]")
                continue

            if part_type == "audio":
                audio_index += 1
                audio_url = str(part.get("url") or "").strip()
                audio_size = 0
                try:
                    audio_size = int(part.get("size") or 0)
                except (TypeError, ValueError):
                    audio_size = 0
                oversized = self.is_size_limit_exceeded("audio", audio_size)
                if audio_url:
                    source_kind = "url"
                display_parts.append(
                    {
                        "type": "audio",
                        "url": audio_url,
                        "mime_type": str(part.get("mime_type") or "audio/mpeg"),
                        "size": audio_size,
                        "aes_key": part_aes_key,
                        "oversized": oversized,
                        "error": "size_limit_exceeded" if oversized else "",
                    }
                )
                summary_tokens.append(f"[音频{audio_index}{':超过大小限制' if oversized else ''}]")
                unsupported_modalities.append("音频")
                continue

            fallback_text = str(part.get("text") or f"用户发送了非文本消息：{part_type or msgtype}").strip()
            if fallback_text:
                display_parts.append({"type": "text", "text": fallback_text})
                agent_parts.append({"type": "text", "text": fallback_text})
                summary_tokens.append(fallback_text)

        if not display_parts:
            fallback = f"用户发送了非文本消息：{msgtype}"
            display_parts = [{"type": "text", "text": fallback}]
            agent_parts = [{"type": "text", "text": fallback}]
            summary_tokens = [fallback]

        record_content = "\n".join(summary_tokens).strip() or f"[non-text:{msgtype}]"
        unsupported_modalities = list(dict.fromkeys(unsupported_modalities))
        supports_multimodal_agent_input = any(
            part.get("type") in {"image_url", "video_url"}
            for part in agent_parts
        )
        if supports_multimodal_agent_input:
            user_input: Any = agent_parts
        else:
            user_input = "\n".join(
                str(part.get("text") or "").strip()
                for part in agent_parts
                if str(part.get("text") or "").strip()
            ).strip() or record_content

        return {
            "user_input": user_input,
            "record_content": record_content,
            "display_parts": display_parts,
            "source_kind": source_kind,
            "agent_image_transport": agent_image_transport,
            "agent_video_transport": agent_video_transport,
            "unsupported_modalities": unsupported_modalities,
        }

    def resolve_media_transport_policy(
        self,
        provider: Any | None,
        caps: set[ModelCapability],
    ) -> dict[str, dict[str, Any]]:
        # 永远不向 Agent 发送媒体消息，所有媒体消息只走转发逻辑
        return {
            "image": {"enabled": False, "mode": "none"},
            "video": {"enabled": False, "mode": "none"},
            "audio": {"enabled": False, "mode": "none"},
        }

    async def send_admin_message(
        self,
        content: str,
        *,
        trace_id: str = "",
        source: str = "admin_message",
    ) -> bool:
        if self._ctx.client is None:
            raise RuntimeError("WSClient not initialized")

        if not self._ctx.bound_chat_id:
            self._ctx.logger.warning(
                "管理员消息发送跳过：Bot 未绑定管理员会话",
                extra={"trace_id": trace_id, "category": "message"},
            )
            return False

        try:
            await self._ctx.client.send_message(
                self._ctx.bound_chat_id,
                {
                    "msgtype": "markdown",
                    "markdown": {"content": content},
                },
            )
            self._ctx.log_event(
                trace_id=trace_id,
                source=source,
                category="message",
                message="管理员消息已发送",
                detail=f"target_chat_id={self._ctx.bound_chat_id}",
            )
            return True
        except Exception as exc:
            self._ctx.logger.exception(
                "管理员消息发送失败",
                extra={"trace_id": trace_id, "category": "network"},
            )
            self._ctx.log_event(
                trace_id=trace_id,
                source=source,
                category="message",
                message=f"管理员消息发送失败 {exc}",
                level="ERROR",
            )
            return False

    async def send_admin_media(
        self,
        file_data: bytes,
        file_name: str,
        *,
        media_type: str,
        trace_id: str = "",
        source: str = "admin_message",
    ) -> bool:
        if not self._ctx.bound_chat_id:
            self._ctx.logger.warning(
                "管理员媒体发送跳过：Bot 未绑定管理员会话",
                extra={"trace_id": trace_id, "category": "message"},
            )
            return False
        return await self.send_media_asset(
            self._ctx.bound_chat_id,
            file_data,
            file_name,
            media_type,
            trace_id=trace_id,
            source=source,
        )

    async def send_admin_file(
        self,
        storage_path: Path,
        file_name: str,
        *,
        trace_id: str = "",
        source: str = "admin_message",
    ) -> bool:
        if not self._ctx.bound_chat_id:
            self._ctx.logger.warning(
                "管理员文件发送跳过：Bot 未绑定管理员会话",
                extra={"trace_id": trace_id, "category": "message"},
            )
            return False

        resolved_path = storage_path.resolve()
        if not resolved_path.exists() or not resolved_path.is_file():
            self._ctx.log_event(
                trace_id=trace_id,
                source=source,
                category="message",
                message=f"管理员文件发送失败，文件不存在 {file_name}",
                detail=f"path={resolved_path}",
                level="ERROR",
            )
            return False

        try:
            file_data = resolved_path.read_bytes()
        except Exception as exc:
            self._ctx.logger.exception(
                f"读取待转发文件失败: {file_name}",
                extra={"trace_id": trace_id, "category": "network"},
            )
            self._ctx.log_event(
                trace_id=trace_id,
                source=source,
                category="message",
                message=f"管理员文件读取失败 {file_name} {exc}",
                detail=f"path={resolved_path}",
                level="ERROR",
            )
            return False

        return await self.send_admin_media(
            file_data,
            file_name,
            media_type="file",
            trace_id=trace_id,
            source=source,
        )

    def iter_forwardable_stored_parts(
        self,
        media_parts: list[dict[str, Any]],
    ) -> list[tuple[str, Path, str]]:
        targets: list[tuple[str, Path, str]] = []
        for part in media_parts:
            part_type = str(part.get("type") or "").strip().lower()
            if part_type not in {"image", "video", "audio", "file"}:
                continue
            if str(part.get("error") or "").strip():
                continue
            storage_path_str = str(part.get("storage_path") or "").strip()
            if not storage_path_str:
                continue
            file_name = str(part.get("filename") or "").strip() or Path(storage_path_str).name
            targets.append((part_type, Path(storage_path_str), file_name))
        return targets

    async def handle_media_forward(
        self,
        frame: dict[str, Any],
        context: dict[str, str],
        display_parts: list[dict[str, Any]],
        *,
        created_at: str = "",
        trace_id: str,
        skip_reply: bool = False,
    ) -> None:
        media_parts = [part for part in display_parts if self.is_forwardable_media_part(part)]
        media_types = list(dict.fromkeys(str(part.get("type") or "").strip().lower() for part in media_parts))
        if not self._ctx.bound_chat_id:
            self._ctx.logger.warning(
                "媒体转发跳过：Bot 未绑定管理员会话",
                extra={"trace_id": trace_id, "category": "message"},
            )
            if not skip_reply:
                labels = "、".join({"image": "图片", "video": "视频", "audio": "音频", "file": "文件"}.get(media_type, media_type) for media_type in media_types) or "媒体"
                reply_text = f"已收到{labels}，暂无管理员在线，请稍后联系"
                await self._ctx.send_ai_reply_message(frame=frame, context=context, content=reply_text)
                self._ctx.record_bot_message(
                    context=context,
                    content=reply_text,
                    msg_type="system",
                    sender_id="system",
                    sender_name="系统",
                    reply_source="system",
                    trace_id=trace_id,
                    metadata={"media_forward": "skipped_no_admin", "media_types": media_types},
                )
            return

        chat_type = str(context.get("chat_type", "unknown")).strip()
        sender_id = context.get("sender_id", "")
        sender_name = context.get("sender_name", "未知用户")
        chat_id = context.get("chat_id", "")
        chat_name = context.get("chat_name", "")

        user_display_profile = get_user_display_name(self._ctx.database_path, sender_id)
        user_display_name = None
        if user_display_profile:
            user_display_name = str(user_display_profile.get("display_name") or "").strip()
        if not user_display_name:
            user_display_name = sender_name

        group_display_name = None
        if chat_type == "group" and chat_id:
            conversation = get_conversation(chat_id=chat_id, database_path=self._ctx.database_path)
            if conversation:
                group_display_name = str(conversation.get("display_name") or "").strip()
        if not group_display_name:
            group_display_name = chat_name

        send_time = self._ctx.format_local_time(created_at)

        text_parts = [p for p in display_parts if p.get("type") == "text"]

        forward_lines: list[str] = []
        if chat_type == "group":
            forward_lines.append(f"群聊 [{group_display_name}] : 用户 [{user_display_name}] 于 {send_time} 发送了 ")
        else:
            forward_lines.append(f"用户 [{user_display_name}] 于 {send_time} 发送了 ")

        for part in media_parts:
            part_type = str(part.get("type") or "file").strip().lower()
            part_label = {"image": "图片", "video": "视频", "audio": "音频", "file": "文件"}.get(part_type, "媒体")
            part_filename = str(part.get("filename") or "").strip()
            part_storage = str(part.get("storage_path") or "").strip()
            part_error = str(part.get("error") or "").strip()
            if part_error:
                error_label = "超过大小限制" if part_error == "size_limit_exceeded" else f"解析失败：{part_error}"
                forward_lines.append(f"{part_label} {part_filename or '附件'}（{error_label}）")
            elif part_filename:
                if part_storage:
                    forward_lines.append(f"附件 {part_storage}")
                else:
                    forward_lines.append(f"附件 {part_filename}")

        if text_parts:
            for tp in text_parts:
                text_content = str(tp.get("text") or "").strip()
                if text_content:
                    forward_lines.append(text_content)

        forward_text = "\n".join(forward_lines)

        await self.send_admin_message(
            forward_text,
            trace_id=trace_id,
            source="media_forward",
        )

        forwarded_attachment_count = 0
        for part_type, storage_path, file_name in self.iter_forwardable_stored_parts(media_parts):
            if part_type == "file":
                sent = await self.send_admin_file(
                    storage_path,
                    file_name,
                    trace_id=trace_id,
                    source="media_forward_file",
                )
            else:
                try:
                    file_data = storage_path.resolve().read_bytes()
                except Exception as exc:
                    self._ctx.logger.exception(
                        f"读取待转发附件失败: {file_name}",
                        extra={"trace_id": trace_id, "category": "network"},
                    )
                    self._ctx.log_event(
                        trace_id=trace_id,
                        source="media_forward_file",
                        category="message",
                        message=f"管理员附件读取失败 {file_name} {exc}",
                        detail=f"path={storage_path.resolve()}",
                        level="ERROR",
                    )
                    sent = False
                else:
                    sent = await self.send_admin_media(
                        file_data,
                        file_name,
                        media_type=part_type,
                        trace_id=trace_id,
                        source="media_forward_file",
                    )
            if sent:
                forwarded_attachment_count += 1

        stored_count = sum(1 for part in media_parts if str(part.get("storage_name") or "").strip())
        failed_count = sum(1 for part in media_parts if str(part.get("error") or "").strip())
        if not skip_reply:
            if stored_count and failed_count:
                reply_text = "已收到并通知管理员，部分附件已转发，部分解析失败"
            elif stored_count:
                reply_text = "已收到并通知管理员"
            else:
                reply_text = "已收到并通知管理员，但当前附件解析失败"
            await self._ctx.send_ai_reply_message(frame=frame, context=context, content=reply_text)
            self._ctx.record_bot_message(
                context=context,
                content=reply_text,
                msg_type="system",
                sender_id="system",
                sender_name="系统",
                reply_source="system",
                trace_id=trace_id,
                metadata={
                    "media_forward": "completed",
                    "media_types": media_types,
                    "stored_count": stored_count,
                    "failed_count": failed_count,
                    "forwarded_attachment_count": forwarded_attachment_count,
                },
                mark_user_replied=True,
            )
        return
