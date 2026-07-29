"""统一链路日志数据库访问。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from observability import (
    TraceBatch,
    TraceCallStatus,
    TraceLevel,
    TraceService,
    TraceStatus,
    TraceTrigger,
)
from sqlalchemy import case, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.observability import (
    TraceEventModel,
    TracePayloadChunkModel,
    TracePayloadModel,
    TraceRecordModel,
    TraceSpanModel,
)
from app.core.pagination import PageSlice, PageSpec, paginate_scalars

PAYLOAD_CHUNK_SIZE_BYTES = 256 * 1024
PAYLOAD_PREVIEW_CHARACTERS = 2048


def _escape_like_pattern(value: str) -> str:
    """转义 LIKE 通配符，保证关键字按字面值参数化查询。"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _split_utf8(text: str) -> list[tuple[str, int]]:
    """按 UTF-8 完整字符边界分块。"""
    raw = text.encode("utf-8")
    chunks: list[tuple[str, int]] = []
    start = 0
    while start < len(raw):
        end = min(start + PAYLOAD_CHUNK_SIZE_BYTES, len(raw))
        while True:
            try:
                content = raw[start:end].decode("utf-8")
                break
            except UnicodeDecodeError as exc:
                end = start + exc.start
        chunks.append((content, end - start))
        start = end
    return chunks or [("", 0)]


class ObservabilityRepository:
    """链路日志批量写入与查询仓储。"""

    def __init__(self, session: Session) -> None:
        self.session = session

    def ingest(self, batch: TraceBatch) -> None:
        """幂等写入一个服务产生的日志批次。"""
        trace_values = batch.trace.model_dump(mode="python")
        trace_values["trigger"] = batch.trace.trigger.value
        trace_values["status"] = batch.trace.status.value
        trace_values["root_service"] = batch.trace.root_service.value
        statement = insert(TraceRecordModel).values(**trace_values)
        earlier_batch = statement.excluded.started_at < TraceRecordModel.started_at
        statement = statement.on_conflict_do_update(
            index_elements=[TraceRecordModel.trace_id],
            set_={
                "trigger": case(
                    (earlier_batch, statement.excluded.trigger),
                    else_=TraceRecordModel.trigger,
                ),
                "name": case(
                    (earlier_batch, statement.excluded.name),
                    else_=TraceRecordModel.name,
                ),
                "started_at": func.least(
                    TraceRecordModel.started_at,
                    statement.excluded.started_at,
                ),
                "ended_at": func.greatest(
                    TraceRecordModel.ended_at,
                    statement.excluded.ended_at,
                ),
                "duration_ms": func.greatest(
                    TraceRecordModel.duration_ms,
                    statement.excluded.duration_ms,
                ),
                "status": case(
                    (
                        or_(
                            TraceRecordModel.status == "error",
                            statement.excluded.status == "error",
                        ),
                        "error",
                    ),
                    (
                        or_(
                            TraceRecordModel.status == "timeout",
                            statement.excluded.status == "timeout",
                        ),
                        "timeout",
                    ),
                    (
                        or_(
                            TraceRecordModel.status == "denied",
                            statement.excluded.status == "denied",
                        ),
                        "denied",
                    ),
                    (
                        or_(
                            TraceRecordModel.status == "cancelled",
                            statement.excluded.status == "cancelled",
                        ),
                        "cancelled",
                    ),
                    else_=statement.excluded.status,
                ),
                "root_service": case(
                    (earlier_batch, statement.excluded.root_service),
                    else_=TraceRecordModel.root_service,
                ),
                "http_method": case(
                    (earlier_batch, statement.excluded.http_method),
                    else_=TraceRecordModel.http_method,
                ),
                "http_path": case(
                    (earlier_batch, statement.excluded.http_path),
                    else_=TraceRecordModel.http_path,
                ),
                "http_status": case(
                    (earlier_batch, statement.excluded.http_status),
                    else_=TraceRecordModel.http_status,
                ),
                "error_message": func.coalesce(
                    statement.excluded.error_message,
                    TraceRecordModel.error_message,
                ),
            },
        )
        self.session.execute(statement)

        for span in batch.spans:
            values = span.model_dump(mode="python")
            values["service"] = span.service.value
            values["kind"] = span.kind.value
            values["status"] = span.status.value
            self.session.execute(
                insert(TraceSpanModel)
                .values(**values)
                .on_conflict_do_nothing(index_elements=[TraceSpanModel.span_id])
            )
        for event in batch.events:
            values = event.model_dump(mode="python")
            values["service"] = event.service.value
            values["event_type"] = event.event_type.value
            values["level"] = event.level.value
            self.session.execute(
                insert(TraceEventModel)
                .values(**values)
                .on_conflict_do_nothing(index_elements=[TraceEventModel.event_id])
            )
        for payload in batch.payloads:
            serialized = json.dumps(
                payload.content,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            )
            raw = serialized.encode("utf-8")
            chunks = _split_utf8(serialized)
            values = {
                "payload_id": payload.payload_id,
                "trace_id": payload.trace_id,
                "span_id": payload.span_id,
                "service": payload.service.value,
                "payload_type": payload.payload_type.value,
                "content_type": payload.content_type,
                "content_preview": serialized[:PAYLOAD_PREVIEW_CHARACTERS],
                "content_sha256": hashlib.sha256(raw).hexdigest(),
                "chunk_count": len(chunks),
                "size_bytes": len(raw),
                "created_at": payload.created_at,
            }
            self.session.execute(
                insert(TracePayloadModel)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=[TracePayloadModel.payload_id]
                )
            )
            for chunk_index, (content, size_bytes) in enumerate(chunks):
                self.session.execute(
                    insert(TracePayloadChunkModel)
                    .values(
                        payload_id=payload.payload_id,
                        chunk_index=chunk_index,
                        content=content,
                        size_bytes=size_bytes,
                    )
                    .on_conflict_do_nothing(
                        index_elements=[
                            TracePayloadChunkModel.payload_id,
                            TracePayloadChunkModel.chunk_index,
                        ]
                    )
                )
        self.session.commit()

    def list_traces(
        self,
        *,
        trace_id: UUID | None,
        started_from: datetime | None,
        started_to: datetime | None,
        trigger: TraceTrigger | None,
        service: TraceService | None,
        call_status: TraceCallStatus | None,
        keyword: str | None,
        page: int,
        page_size: int,
    ) -> PageSlice[TraceRecordModel]:
        """按企业排障维度查询链路摘要。"""
        query = select(TraceRecordModel)
        if trace_id is not None:
            query = query.where(TraceRecordModel.trace_id == trace_id)
        if started_from is not None:
            query = query.where(TraceRecordModel.started_at >= started_from)
        if started_to is not None:
            query = query.where(TraceRecordModel.started_at <= started_to)
        if trigger:
            query = query.where(TraceRecordModel.trigger == trigger.value)
        if service:
            query = query.where(TraceRecordModel.root_service == service.value)
        error_trace_ids = select(TraceEventModel.trace_id).where(
            TraceEventModel.level == TraceLevel.ERROR.value
        )
        warning_trace_ids = select(TraceEventModel.trace_id).where(
            TraceEventModel.level == TraceLevel.WARNING.value
        )
        if call_status is TraceCallStatus.FAILURE:
            query = query.where(
                or_(
                    TraceRecordModel.status != TraceStatus.SUCCESS.value,
                    TraceRecordModel.trace_id.in_(error_trace_ids),
                )
            )
        elif call_status is TraceCallStatus.WARNING:
            query = query.where(
                TraceRecordModel.status == TraceStatus.SUCCESS.value,
                TraceRecordModel.trace_id.not_in(error_trace_ids),
                TraceRecordModel.trace_id.in_(warning_trace_ids),
            )
        elif call_status is TraceCallStatus.SUCCESS:
            query = query.where(
                TraceRecordModel.status == TraceStatus.SUCCESS.value,
                TraceRecordModel.trace_id.not_in(error_trace_ids),
                TraceRecordModel.trace_id.not_in(warning_trace_ids),
            )
        if keyword:
            pattern = f"%{_escape_like_pattern(keyword)}%"
            payload_trace_ids = (
                select(TracePayloadModel.trace_id)
                .join(
                    TracePayloadChunkModel,
                    TracePayloadChunkModel.payload_id
                    == TracePayloadModel.payload_id,
                )
                .where(
                    TracePayloadChunkModel.content.ilike(
                        pattern,
                        escape="\\",
                    )
                )
            )
            query = query.where(
                or_(
                    TraceRecordModel.name.ilike(pattern, escape="\\"),
                    TraceRecordModel.http_path.ilike(pattern, escape="\\"),
                    TraceRecordModel.error_message.ilike(pattern, escape="\\"),
                    TraceRecordModel.trace_id.in_(payload_trace_ids),
                )
            )
        return paginate_scalars(
            self.session,
            query.order_by(TraceRecordModel.started_at.desc()),
            PageSpec(page=page, page_size=page_size),
        )

    def get_trace_call_statuses(self, trace_ids: list[UUID]) -> dict[UUID, str]:
        """批量计算链路调用状态：失败优先于警告，最后为成功。"""
        if not trace_ids:
            return {}
        traces = list(
            self.session.scalars(
                select(TraceRecordModel).where(
                    TraceRecordModel.trace_id.in_(trace_ids)
                )
            )
        )
        event_levels: dict[UUID, set[str]] = {
            trace_id: set() for trace_id in trace_ids
        }
        for trace_id, level in self.session.execute(
            select(
                TraceEventModel.trace_id,
                TraceEventModel.level,
            )
            .where(TraceEventModel.trace_id.in_(trace_ids))
            .distinct()
        ):
            event_levels[trace_id].add(level)

        call_statuses: dict[UUID, str] = {}
        for trace in traces:
            levels = event_levels[trace.trace_id]
            if (
                trace.status != TraceStatus.SUCCESS.value
                or TraceLevel.ERROR.value in levels
            ):
                call_statuses[trace.trace_id] = TraceCallStatus.FAILURE.value
            elif TraceLevel.WARNING.value in levels:
                call_statuses[trace.trace_id] = TraceCallStatus.WARNING.value
            else:
                call_statuses[trace.trace_id] = TraceCallStatus.SUCCESS.value
        return call_statuses

    def get_trace(self, trace_id: UUID) -> TraceRecordModel | None:
        """读取链路摘要。"""
        return self.session.get(TraceRecordModel, trace_id)

    def list_spans(self, trace_id: UUID) -> list[TraceSpanModel]:
        """读取链路全部 Span。"""
        return list(
            self.session.scalars(
                select(TraceSpanModel)
                .where(TraceSpanModel.trace_id == trace_id)
                .order_by(TraceSpanModel.started_at.asc())
            )
        )

    def list_events(self, trace_id: UUID) -> list[TraceEventModel]:
        """读取链路全部事件。"""
        return list(
            self.session.scalars(
                select(TraceEventModel)
                .where(TraceEventModel.trace_id == trace_id)
                .order_by(TraceEventModel.occurred_at.asc())
            )
        )

    def list_payloads(self, span_id: UUID) -> list[TracePayloadModel]:
        """按 Span 懒加载完整载荷。"""
        return list(
            self.session.scalars(
                select(TracePayloadModel)
                .where(TracePayloadModel.span_id == span_id)
                .order_by(TracePayloadModel.created_at.asc())
            )
        )

    def list_payload_chunks(
        self,
        payload_id: UUID,
        *,
        chunk_from: int,
        chunk_limit: int,
    ) -> tuple[list[TracePayloadChunkModel], int]:
        """分页读取长载荷正文分块。"""
        query = (
            select(TracePayloadChunkModel)
            .where(TracePayloadChunkModel.payload_id == payload_id)
            .order_by(TracePayloadChunkModel.chunk_index.asc())
        )
        total = self.session.scalar(
            select(func.count())
            .select_from(TracePayloadChunkModel)
            .where(TracePayloadChunkModel.payload_id == payload_id)
        ) or 0
        items = list(
            self.session.scalars(
                query.offset(chunk_from).limit(chunk_limit)
            )
        )
        return items, total

    @staticmethod
    def model_dict(model: Any) -> dict[str, Any]:
        """把 SQLAlchemy 模型转换为接口字典。"""
        return {
            column.name: getattr(model, column.name)
            for column in model.__table__.columns
        }
