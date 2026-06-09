from __future__ import annotations

"""记忆搜索索引管理模块。

提供记忆索引的重建接口。当前实现基于 JSON 文件自索引方式，
预留了索引重建的扩展能力。
"""

from pathlib import Path
from typing import Any


def rebuild_all_indexes(memory_root: str | Path) -> dict[str, Any]:
    return {"status": "ok", "message": "JSON files are self-indexing, no rebuild needed"}


def rebuild_index_for_file(memory_root: str | Path, relative_path: str) -> Any:
    return {"status": "ok", "message": "JSON files are self-indexing"}
