"""Memory reader CLI — read and select relevant JSON memory for the current user query.

Usage:
    python read.py --current-message "how to deploy?" --memory-dir .memory
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR))

for _p in _SCRIPT_DIR.parents:
    if (_p / "app").is_dir() and (_p / "pyproject.toml").is_file():
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))
        break

from memory_reader.orchestrator import read_memory_for_task


def _resolve_memory_dir(memory_dir: str) -> str:
    p = Path(memory_dir)
    if p.is_absolute():
        return str(p)
    project_root = _find_project_root()
    return str(project_root / memory_dir)


def _find_project_root() -> Path:
    candidate = Path(__file__).resolve()
    for parent in candidate.parents:
        if (parent / ".skills").is_dir() or (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


def main() -> None:
    parser = argparse.ArgumentParser(description="Read and select relevant memory for the current query.")
    parser.add_argument("--current-message", required=True, help="The current user query.")
    parser.add_argument("--memory-dir", default=".memory", help="Memory directory path.")
    parser.add_argument("--mode", default="default", choices=["default", "compact", "expanded"], help="Read mode.")
    parser.add_argument("--token-budget", type=int, default=0, help="Token budget (0 = use mode default).")
    parser.add_argument("--token-budget-expanded", type=int, default=0, help="Expanded token budget when documents are matched (0 = same as token-budget).")
    parser.add_argument("--document-labels-json", default="", help="JSON object mapping document source_id to display name.")
    parser.add_argument("--expanded-terms", default="", help="Pipe-separated expanded query terms from LLM.")

    args = parser.parse_args()

    memory_dir = _resolve_memory_dir(args.memory_dir)

    document_labels = {}
    if args.document_labels_json.strip():
        try:
            parsed_labels = json.loads(args.document_labels_json)
            if isinstance(parsed_labels, dict):
                document_labels = {str(k): str(v) for k, v in parsed_labels.items()}
        except json.JSONDecodeError:
            document_labels = {}

    metadata = {
        "memory_root": memory_dir,
        "mode": args.mode,
        "token_budget": args.token_budget,
        "token_budget_expanded": args.token_budget_expanded,
        "document_labels": document_labels,
        "expanded_terms": args.expanded_terms,
    }

    try:
        result = read_memory_for_task(
            current_message=args.current_message,
            metadata=metadata,
            llm=None,
        )
        output = dict(result or {})
        output["ok"] = True
        print(json.dumps(output, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
