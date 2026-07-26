from pydantic import BaseModel

from app.core.config import ConnectionTarget


class TestConnectionsRequest(BaseModel):
    target: ConnectionTarget = "all"
