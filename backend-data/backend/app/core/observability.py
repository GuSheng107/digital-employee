"""backend-data 本地链路日志落库入口。"""

import asyncio

from observability import TraceBatch

from app.core.database import get_database_client
from app.services.observability_service import ObservabilityService


async def persist_trace_batch(batch: TraceBatch) -> None:
    """在线程池中使用独立会话持久化当前日志批次。"""

    def _persist() -> None:
        with get_database_client().session() as session:
            ObservabilityService(session).ingest(batch)

    await asyncio.to_thread(_persist)
