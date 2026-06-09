from __future__ import annotations

"""手动回复处理模块。

处理管理员发起的手动回复队列，轮询待发送的手动回复指令并执行发送。
支持文本回复和附件发送，包括被动回复与主动发送的降级策略、
群聊权限错误处理以及发送失败后的上下文压缩触发。
"""

import asyncio
import re
from pathlib import Path
from typing import Any

from app.chat_store import clear_conversation_send_error, get_conversation, get_latest_user_message_trace_id
from app.db.bot_store import make_conversation_key
from app.manual_reply_queue import list_pending_manual_replies, mark_manual_reply
from wecom_bot.handlers.context import BotContext
from wecom_bot.reply import build_stream_id

_WECOM_ERRCODE_RE = re.compile(r"errcode=(\d+)")
_ROOM_PERMISSION_ERRCODE = "93001"


class ManualReplyHandler:
    """手动回复处理器，负责轮询并执行管理员的手动回复指令。

    持续监听手动回复队列，对每条待发送指令执行文本和附件的发送。
    优先使用被动回复（reply_stream），失败时降级为主动发送（send_message）。
    处理群聊权限错误（errcode=93001）时自动归档会话，发送成功后
    触发上下文压缩以维护对话质量。
    """
    def __init__(self, ctx: BotContext) -> None:
        self._ctx: BotContext = ctx

    @staticmethod
    def _make_compress_done_callback(chat_id: str):
        def _on_done(task: asyncio.Task) -> None:
            exc = task.exception()
            if exc is not None:
                from app.logger import get_logger
                get_logger("manual_reply_handler").warning(
                    "后台压缩上下文失败: chat_id=%s error=%s",
                    chat_id, exc, extra={"category": "ai"},
                )
        return _on_done

    async def watch_manual_replies(self) -> None:
        while not self._ctx.keepalive.is_set():
            try:
                self._ctx.refresh_runtime_settings()
                for command in list_pending_manual_replies(
                    database_path=self._ctx.database_path,
                    bot_key=self._ctx.bot_key,
                ):
                    command_id = str(command.get("id", ""))
                    mark_manual_reply(
                        command_id,
                        "processing",
                        database_path=self._ctx.database_path,
                    )
                    await self.send_manual_reply(command)
            except asyncio.CancelledError:
                raise
            except Exception:
                self._ctx.logger.exception("Failed while processing manual reply queue.", extra={"category": "task"})
            await asyncio.sleep(1)

    async def send_manual_reply(self, command: dict[str, Any]) -> None:
        if self._ctx.client is None:
            raise RuntimeError("WSClient not initialized")
        command_id = str(command.get("id", ""))
        chat_id = str(command.get("external_chat_id") or command.get("chat_id", "")).strip()
        conversation_chat_id = str(command.get("conversation_chat_id") or chat_id).strip()
        chat_name = str(command.get("chat_name", "")).strip() or chat_id
        content = str(command.get("content", "")).strip()
        metadata = command.get("metadata") if isinstance(command.get("metadata"), dict) else {}
        attachments = metadata.get("attachments") if isinstance(metadata, dict) else []
        skip_record = bool(metadata.get("skip_record"))
        if not isinstance(attachments, list):
            attachments = []

        if not command_id:
            return

        if not chat_id or chat_id == "unknown":
            mark_manual_reply(
                command_id,
                "failed",
                error="chat_id is missing",
                database_path=self._ctx.database_path,
            )
            return

        if not content and not attachments:
            mark_manual_reply(
                command_id,
                "failed",
                error="content and attachments are empty",
                database_path=self._ctx.database_path,
            )
            return

        me_chat_id = make_conversation_key(self._ctx.bot_key, self._ctx.bound_chat_id, kind="me")
        is_me_chat = conversation_chat_id == me_chat_id and bool(self._ctx.bound_chat_id)
        conversation = get_conversation(chat_id=conversation_chat_id, database_path=self._ctx.database_path)
        existing_kind = str((conversation or {}).get("conversation_kind") or "").strip()
        existing_type = str((conversation or {}).get("chat_type") or "").strip()
        target_sender_id = str(
            metadata.get("target_sender_id")
            or (conversation or {}).get("sender_id")
            or ""
        ).strip()
        target_sender_name = str(
            metadata.get("target_sender_name")
            or (conversation or {}).get("sender_name")
            or ""
        ).strip()
        existing_name = str(
            (conversation or {}).get("chat_name")
            or (conversation or {}).get("display_name")
            or chat_name
        ).strip()
        context = {
            "chat_id": conversation_chat_id,
            "chat_name": self._ctx.bound_chat_name if is_me_chat else (existing_name or chat_id),
            "external_chat_id": chat_id,
            "bot_key": self._ctx.bot_key,
            "conversation_kind": "me" if is_me_chat else (existing_kind or "external"),
            "chat_type": "single" if is_me_chat else (existing_type or "unknown"),
            "sender_id": "bot",
            "sender_name": self._ctx.settings.wecom_bot.name,
            "context_sender_id": target_sender_id,
            "context_sender_name": target_sender_name,
            "msg_type": "manual",
            "message_id": command_id,
        }

        actual_send_chat_id = self._ctx.bound_chat_id if is_me_chat else chat_id

        frame = self.resolve_manual_reply_frame(
            metadata=metadata,
            conversation_chat_id=conversation_chat_id,
            external_chat_id=actual_send_chat_id,
        )
        frame_req_id = self._ctx.frame_req_id(frame=frame)
        # 构建详细的附件信息
        attachment_details = []
        for idx, att in enumerate(attachments):
            att_info = f"[{idx+1}] {att.get('filename', '附件')} ({att.get('kind', 'file')})"
            if att.get('size'):
                att_info += f" - {att.get('size')} bytes"
            attachment_details.append(att_info)
        
        # 记录详细的手动回复信息
        detail_lines = []
        detail_lines.append(f"聊天ID: {chat_id}")
        detail_lines.append(f"聊天名称: {chat_name}")
        if content:
            detail_lines.append(f"回复内容:\n{content}")
        if attachment_details:
            detail_lines.append(f"附件列表 ({len(attachments)}):")
            detail_lines.extend(attachment_details)
        
        self._ctx.log_event(
            trace_id=command_id,
            source="manual_reply",
            category="message",
            message=f"发送手动回复: 文本={'是' if bool(content) else '否'}, 附件={len(attachments)}个",
            detail="\n".join(detail_lines),
        )

        attachment_errors: list[str] = []
        try:
            # 优先用被动回复发送文本（如果有文本内容）
            if content:
                if frame:
                    try:
                        await self._ctx.client.reply_stream(
                            frame,
                            stream_id=build_stream_id(),
                            content=content,
                            finish=True,
                        )
                        self._ctx.log_event(
                            trace_id=command_id,
                            source="manual_reply",
                            category="message",
                            message=f"手动文本被动回复成功 req_id={frame_req_id or '<empty>'}",
                        )
                    except Exception as passive_exc:
                        self._ctx.log_event(
                            trace_id=command_id,
                            source="manual_reply",
                            category="message",
                            message="手动文本被动回复失败，回退主动发送",
                            detail=f"req_id={frame_req_id or '<empty>'}\nerror={passive_exc}",
                            level="WARNING",
                        )
                        await self._ctx.send_message_with_retry(
                            chat_id=actual_send_chat_id,
                            message={
                                "msgtype": "markdown",
                                "markdown": {"content": content},
                            },
                            trace_id=command_id,
                        )
                else:
                    self._ctx.log_event(
                        trace_id=command_id,
                        source="manual_reply",
                        category="message",
                        message="手动文本未命中可用 passive frame，直接主动发送",
                        detail=(
                            f"source_trace_id={str(metadata.get('source_trace_id') or '').strip() or '<empty>'}\n"
                            f"chat_id={actual_send_chat_id or '<empty>'}"
                        ),
                        level="WARNING",
                    )
                    await self._ctx.send_message_with_retry(
                        chat_id=actual_send_chat_id,
                        message={
                            "msgtype": "markdown",
                            "markdown": {"content": content},
                        },
                        trace_id=command_id,
                    )
            
            # 附件全部使用主动发送（不使用被动回复）
            for index, attachment in enumerate(attachments):
                try:
                    await self.send_manual_reply_attachment(
                        actual_send_chat_id,
                        attachment,
                        trace_id=command_id,
                        chat_type=str(context.get("chat_type") or "unknown"),
                        frame=None,  # 附件不使用被动回复
                    )
                except Exception as att_exc:
                    att_name = str(attachment.get("filename") or "附件")
                    self._ctx.logger.exception(
                        f"附件发送失败，继续发送其余内容: {att_name}",
                        extra={"trace_id": command_id, "category": "network"},
                    )
                    attachment_errors.append(f"{att_name}: {att_exc}")
            if attachments and attachment_errors and not content and len(attachment_errors) == len(attachments):
                raise RuntimeError(f"全部附件发送失败: {'; '.join(attachment_errors)}")
        except Exception as exc:
            exc_msg = str(exc)
            errcode_match = _WECOM_ERRCODE_RE.search(exc_msg)
            if errcode_match and errcode_match.group(1) == _ROOM_PERMISSION_ERRCODE:
                mark_manual_reply(
                    command_id,
                    "archived",
                    error="机器人无权在此群聊发送消息 (errcode=93001)",
                    database_path=self._ctx.database_path,
                )
                self._ctx.log_event(
                    trace_id=command_id,
                    source="manual_reply",
                    category="message",
                    message=f"手动回复已归档：机器人无权在群聊「{chat_name}」发送消息",
                    detail=f"chat_id={chat_id}\nchat_name={chat_name}\nerrcode=93001",
                    level="WARNING",
                )
                if conversation_chat_id:
                    from app.chat_store import set_conversation_archived
                    set_conversation_archived(
                        chat_id=conversation_chat_id,
                        database_path=self._ctx.database_path,
                    )
                return

            mark_manual_reply(
                command_id,
                "failed",
                error=str(exc),
                database_path=self._ctx.database_path,
            )
            self._ctx.logger.exception(
                "Failed to send manual reply.",
                extra={"trace_id": command_id, "category": "network"},
            )
            self._ctx.handle_conversation_send_failure(
                trace_id=command_id,
                chat_id=conversation_chat_id,
                chat_name=context.get("chat_name", ""),
                error=exc,
                reason="Manual reply send failed",
            )
            return

        mark_manual_reply(command_id, "sent", database_path=self._ctx.database_path)
        # 记录成功发送的详细信息
        success_detail_lines = []
        success_detail_lines.append(f"聊天ID: {chat_id}")
        success_detail_lines.append(f"聊天名称: {chat_name}")
        if content:
            success_detail_lines.append(f"发送内容:\n{content}")
        if attachments:
            success_detail_lines.append(f"成功发送附件: {len(attachments)}个")
            for idx, att in enumerate(attachments):
                success_detail_lines.append(f"  [{idx+1}] {att.get('filename', '附件')}")
        if attachment_errors:
            success_detail_lines.append(f"注意: 部分附件发送失败")
            success_detail_lines.extend([f"  - {err}" for err in attachment_errors])
        
        self._ctx.log_event(
            trace_id=command_id,
            source="manual_reply",
            category="message",
            message=f"手动回复发送成功",
            detail="\n".join(success_detail_lines),
            level="INFO",
        )
        if attachment_errors:
            self._ctx.log_event(
                trace_id=command_id,
                source="manual_reply",
                category="message",
                message=f"部分附件发送失败: {'; '.join(attachment_errors)}",
                level="WARNING",
            )
        if conversation_chat_id:
            clear_conversation_send_error(
                chat_id=conversation_chat_id,
                database_path=self._ctx.database_path,
            )
        if not skip_record:
            record_parts = self.build_manual_reply_record_parts(content, attachments)
            record_content = self.manual_reply_record_text(content, record_parts)
            self._ctx.record_bot_message(
                context=context,
                content=record_content,
                msg_type="manual",
                sender_id="manual",
                sender_name="手动回复",
                reply_source="manual",
                trace_id=command_id,
                metadata={"parts": record_parts},
            )
            # 将压缩上下文的任务放到后台执行，不阻塞手动回复的成功标记
            compress_task = asyncio.create_task(
                self._ctx.agent_service.compress_context_if_needed(
                    conversation_chat_id,
                    sender_id=target_sender_id,
                    sender_name=target_sender_name,
                    bot_key=self._ctx.bot_key,
                )
            )
            compress_task.add_done_callback(self._make_compress_done_callback(conversation_chat_id))

    async def send_manual_reply_attachment(
        self,
        chat_id: str,
        attachment: dict[str, Any],
        *,
        trace_id: str,
        chat_type: str,
        frame: dict[str, Any] | None = None,
    ) -> None:
        if self._ctx.client is None:
            raise RuntimeError("WSClient not initialized")

        attachment_kind = str(attachment.get("kind") or "file").strip().lower()
        normalized_kind = attachment_kind if attachment_kind in {"image", "video", "audio"} else "file"
        file_name = str(attachment.get("filename") or "附件").strip() or "附件"

        file_data = attachment.get("_content_bytes")
        if not isinstance(file_data, bytes) or not file_data:
            storage_path_str = str(attachment.get("storage_path") or "").strip()
            if storage_path_str:
                storage_path = Path(storage_path_str).resolve()
            else:
                storage_name = str(attachment.get("storage_name") or "").strip()
                if storage_name:
                    from app.manual_reply_attachments import resolve_attachment_path
                    storage_path = resolve_attachment_path(self._ctx.project_root, storage_name)
                else:
                    storage_path = Path("")
            if not storage_path.exists() or not storage_path.is_file():
                raise FileNotFoundError(f"附件不存在：{file_name}")
            file_data = storage_path.read_bytes()

        if chat_type == "group" and normalized_kind in {"video", "file"}:
            raise ValueError("群聊不支持发送视频和文件，请在私聊中发送。")

        size = int(attachment.get("size") or len(file_data) or 0)
        if self._ctx.is_size_limit_exceeded(attachment_kind, size):
            raise ValueError(f"附件 {file_name} 超过大小限制")

        sent = await self._ctx.send_media_asset(
            chat_id=chat_id,
            file_data=file_data,
            file_name=file_name,
            media_type=normalized_kind,
            trace_id=trace_id,
            source="manual_reply",
            frame=frame,
        )
        if not sent:
            raise RuntimeError(f"附件发送失败：{file_name}")

    def resolve_manual_reply_frame(
        self,
        *,
        metadata: dict[str, Any],
        conversation_chat_id: str,
        external_chat_id: str,
    ) -> dict[str, Any] | None:
        source_trace_id = str(metadata.get("source_trace_id") or "").strip()
        if not source_trace_id and conversation_chat_id:
            source_trace_id = get_latest_user_message_trace_id(
                chat_id=conversation_chat_id,
                database_path=self._ctx.database_path,
            )
        if source_trace_id:
            frame = self._ctx.frame_store.pop(source_trace_id)
            if frame is not None:
                return frame
        if external_chat_id:
            return self._ctx.frame_store.pop_for_chat(external_chat_id)
        return None

    def build_manual_reply_record_parts(
        self,
        content: str,
        attachments: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        parts: list[dict[str, Any]] = []
        if content:
            parts.append({"type": "text", "text": content})
        for attachment in attachments:
            attachment_kind = str(attachment.get("kind") or "file").strip().lower()
            part_type = attachment_kind if attachment_kind in {"image", "video", "audio"} else "file"
            storage_name = str(attachment.get("storage_name") or "").strip()
            url = str(attachment.get("url") or "").strip()
            if not url and storage_name:
                from app.manual_reply_attachments import build_attachment_url
                url = build_attachment_url(storage_name)
            parts.append(
                {
                    "type": part_type,
                    "url": url,
                    "filename": str(attachment.get("filename") or "附件").strip(),
                    "size": int(attachment.get("size") or 0),
                    "mime_type": str(attachment.get("mime_type") or "application/octet-stream").strip(),
                }
            )
        return parts

    def manual_reply_record_text(
        self,
        content: str,
        parts: list[dict[str, Any]],
    ) -> str:
        tokens: list[str] = []
        if content:
            tokens.append(content)
        for part in parts:
            if part.get("type") == "image":
                tokens.append("[图片]")
            elif part.get("type") == "video":
                tokens.append("[视频]")
            elif part.get("type") == "audio":
                tokens.append("[语音]")
            elif part.get("type") == "file":
                tokens.append(f"[文件:{str(part.get('filename') or '附件')}]")
        return " ".join(token for token in tokens if token).strip()
