from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR.parent.parent))
sys.path.insert(0, str(_SCRIPT_DIR))

for _p in _SCRIPT_DIR.parents:
    if (_p / "app").is_dir() and (_p / "pyproject.toml").is_file():
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))
        break

from memory_creator.writers.json_writer import JsonWriter


def _resolve_memory_dir(memory_dir: str) -> str:
    p = Path(memory_dir)
    if p.is_absolute():
        return str(p)
    candidate = Path(__file__).resolve()
    for parent in candidate.parents:
        if (parent / ".skills").is_dir() or (parent / "pyproject.toml").is_file():
            return str(parent / memory_dir)
    return str(Path.cwd() / memory_dir)


def _ensure_gitignore(project_root: Path) -> None:
    gitignore_path = project_root / ".gitignore"
    entry = "/.memory/"
    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
        if entry not in content:
            content = content.rstrip() + "\n" + entry + "\n"
            gitignore_path.write_text(content, encoding="utf-8")
    else:
        gitignore_path.write_text(entry + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Initialize .memory directory with default JSON files."
    )
    parser.add_argument(
        "--memory-dir",
        default=".memory",
        help="Memory directory path, relative to project root (default: .memory).",
    )

    args = parser.parse_args()
    memory_dir = _resolve_memory_dir(args.memory_dir)

    writer = JsonWriter(memory_dir)
    created = writer.init_memory_dir()

    project_root = Path(memory_dir).parent if Path(memory_dir).is_absolute() else Path.cwd()
    _ensure_gitignore(project_root)

    if created:
        print(
            json.dumps(
                {
                    "ok": True,
                    "memory_dir": memory_dir,
                    "created_files": created,
                    "message": f"Initialized {len(created)} file(s) in {memory_dir}",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(
            json.dumps(
                {
                    "ok": True,
                    "memory_dir": memory_dir,
                    "created_files": [],
                    "message": "Memory directory already initialized",
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
