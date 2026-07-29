"""网关链路日志上报适配。"""

from data_client import get_data_client
from observability import TraceBatch


async def export_trace_batch(batch: TraceBatch) -> None:
    """通过共享 data-client 委托 backend-data 持久化。"""
    await get_data_client().submit_trace_batch(batch.model_dump(mode="json"))
