from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class JsonlRunRecorder:
    """A deliberately small trace sink; callers must only pass already-sanitized data."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def record(self, trace_id: str, event_type: str, data: dict[str, Any]) -> None:
        event = {
            "at": datetime.now(UTC).isoformat(),
            "trace_id": trace_id,
            "type": event_type,
            "data": data,
        }
        with (self.directory / f"{trace_id}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")

    def get_trace(self, trace_id: str) -> list[dict[str, Any]]:
        path = self.directory / f"{trace_id}.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
