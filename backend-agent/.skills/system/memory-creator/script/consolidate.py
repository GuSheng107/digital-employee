"""Memory consolidation CLI — extract reusable memory from chat transcripts or document text.

Usage:
    python consolidate.py --source-type chat --source-text "user: remember to use UTF-8" --source-id chat-001
    python consolidate.py --source-type document --source-file /path/to/doc.txt --source-id doc-api
    python consolidate.py --source-type chat --source-text "..." --source-id chat-002 --memory-dir .memory
"""
from __future__ import annotations

import argparse
import json
import os
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

from memory_creator.orchestrator import consolidate_memory_source
from llm_factory import build_llm


def _resolve_memory_dir(memory_dir: str) -> str:
    p = Path(memory_dir)
    if p.is_absolute():
        return str(p)
    candidate = Path(__file__).resolve()
    for parent in candidate.parents:
        if (parent / ".skills").is_dir() or (parent / "pyproject.toml").is_file():
            return str(parent / memory_dir)
    return str(Path.cwd() / memory_dir)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Consolidate source text into structured Markdown memory artifacts."
    )
    parser.add_argument(
        "--source-type",
        required=True,
        choices=["chat", "document", "explicit"],
        help="Source type: chat, document, or explicit",
    )
    parser.add_argument(
        "--source-text",
        default="",
        help="Source text content (inline). Mutually exclusive with --source-file.",
    )
    parser.add_argument(
        "--source-file",
        default="",
        help="Path to a file containing source text. Mutually exclusive with --source-text.",
    )
    parser.add_argument(
        "--source-id",
        default="",
        help="Unique identifier for this source (used for file naming).",
    )
    parser.add_argument(
        "--title",
        default="",
        help="Title of the source (used in document index).",
    )
    parser.add_argument(
        "--memory-dir",
        default=".memory",
        help="Memory directory path, relative to project root (default: .memory).",
    )
    parser.add_argument(
        "--provider-type",
        default="",
        help="LLM provider type (openai, dashscope, zhipu, minimax, moonshot, deepseek, claude, gemini, openai_compatible).",
    )
    parser.add_argument(
        "--model",
        default="",
        help="LLM model name.",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="LLM API key.",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="LLM API base URL (optional).",
    )
    parser.add_argument(
        "--split-series",
        default="",
        help="Split series basename; overrides --source-id when set.",
    )
    parser.add_argument(
        "--split-index",
        type=int,
        default=0,
        help="Current split part number (1-based); 0 means not a split.",
    )
    parser.add_argument(
        "--split-total",
        type=int,
        default=0,
        help="Total number of split parts; 0 means not a split.",
    )
    parser.add_argument(
        "--mode",
        choices=["append", "update"],
        default="append",
        help="Write mode for this source. Use update to replace existing source_id content instead of appending.",
    )

    args = parser.parse_args()

    if not args.api_key:
        args.api_key = os.environ.get("LLM_API_KEY", "")

    if args.source_text and args.source_file:
        print(
            json.dumps(
                {"ok": False, "error": "--source-text and --source-file are mutually exclusive."},
                ensure_ascii=False,
            )
        )
        sys.exit(1)

    if not args.source_text and not args.source_file:
        print(
            json.dumps(
                {"ok": False, "error": "Either --source-text or --source-file is required."},
                ensure_ascii=False,
            )
        )
        sys.exit(1)

    source_text = args.source_text
    if args.source_file:
        file_path = Path(args.source_file)
        if not file_path.is_file():
            print(
                json.dumps(
                    {"ok": False, "error": f"Source file not found: {args.source_file}"},
                    ensure_ascii=False,
                )
            )
            sys.exit(1)
        source_text = file_path.read_text(encoding="utf-8")

    source_id = args.split_series if args.split_series else args.source_id
    metadata = {
        "source_id": source_id,
        "title": args.title,
        "created_at": "",
        "filename": args.source_file or "",
        "mime_type": "",
        "extra": {},
    }
    if args.split_series:
        metadata["extra"]["split_index"] = args.split_index
        metadata["extra"]["split_total"] = args.split_total

    memory_dir = _resolve_memory_dir(args.memory_dir)

    llm = None
    if args.provider_type and args.model and args.api_key:
        try:
            llm = build_llm(
                provider_type=args.provider_type,
                model=args.model,
                api_key=args.api_key,
                base_url=args.base_url,
            )
        except Exception as exc:
            print(
                json.dumps(
                    {"ok": False, "error": f"Failed to initialize LLM: {exc}"},
                    ensure_ascii=False,
                )
            )
            sys.exit(1)
    elif args.model or args.base_url:
        try:
            from langchain_openai import ChatOpenAI

            llm_kwargs: dict = {"temperature": 0, "max_tokens": 16384}
            if args.model:
                llm_kwargs["model"] = args.model
            if args.base_url:
                llm_kwargs["base_url"] = args.base_url
            llm = ChatOpenAI(**llm_kwargs)
        except Exception as exc:
            print(
                json.dumps(
                    {"ok": False, "error": f"Failed to initialize LLM: {exc}"},
                    ensure_ascii=False,
                )
            )
            sys.exit(1)

    try:
        result = consolidate_memory_source(
            source_type=args.source_type,
            source_text=source_text,
            metadata=metadata,
            memory_dir=memory_dir,
            llm=llm,
            mode=args.mode,
        )
        output = result.model_dump()
        output["ok"] = True
        print(json.dumps(output, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error": str(exc)},
                ensure_ascii=False,
            )
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
