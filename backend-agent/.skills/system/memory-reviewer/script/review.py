"""Memory review CLI — review JSON memory files, Memory Packs, or handle user feedback.

Usage:
    python review.py --review-type memory_files --memory-dir .memory
    python review.py --review-type memory_pack --memory-pack "# Memory Pack..." --current-message "..."
    python review.py --review-type user_feedback --user-feedback "不要用REST风格"
    python review.py --review-type scheduled_cleanup --memory-dir .memory
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

from memory_reviewer.orchestrator import (
    review_memory_files,
    review_memory_pack,
    handle_user_feedback,
    review_conversation_usage,
    compact_timeline,
    load_memory_files,
)
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
        description="Review JSON memory files for quality issues."
    )
    parser.add_argument(
        "--review-type",
        required=True,
        choices=["memory_files", "memory_pack", "user_feedback", "scheduled_cleanup", "conversation_usage"],
        help="Review type",
    )
    parser.add_argument(
        "--memory-dir",
        default=".memory",
        help="Memory directory path, relative to project root (default: .memory).",
    )
    parser.add_argument(
        "--memory-pack",
        default="",
        help="Memory Pack text (required for memory_pack review type).",
    )
    parser.add_argument(
        "--current-message",
        default="",
        help="Current user message.",
    )
    parser.add_argument(
        "--agent-answer",
        default="",
        help="Agent answer.",
    )
    parser.add_argument(
        "--user-feedback",
        default="",
        help="User feedback (required for user_feedback review type).",
    )
    parser.add_argument(
        "--token-budget",
        type=int,
        default=1200,
        help="Token budget for Memory Pack review (default: 1200).",
    )
    parser.add_argument(
        "--mode",
        default="review",
        choices=["review", "patch", "dry_run"],
        help="Mode: review (report only), patch (apply safe patches), dry_run (show what would be applied).",
    )
    parser.add_argument(
        "--skip-report",
        action="store_true",
        help="Run the review without writing report files or applying patches.",
    )
    parser.add_argument(
        "--model",
        default="",
        help="LLM model name (optional).",
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="LLM API base URL (optional).",
    )
    parser.add_argument(
        "--provider-type",
        default="",
        help="LLM provider type",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="LLM API key",
    )
    parser.add_argument(
        "--audit-file",
        default="",
        help="Path to a JSON file containing compact memory usage audit samples.",
    )
    parser.add_argument(
        "--usage-scope",
        default="chat",
        choices=["chat", "document"],
        help="Usage review scope for conversation_usage.",
    )
    parser.add_argument(
        "--review-prompt",
        default="",
        help="Optional operator guidance for conversation usage review.",
    )

    args = parser.parse_args()

    if not args.api_key:
        args.api_key = os.environ.get("LLM_API_KEY", "")

    memory_dir = _resolve_memory_dir(args.memory_dir)

    llm = None
    provider_args_supplied = any([args.provider_type, args.model, args.base_url, args.api_key])
    if provider_args_supplied:
        if not (args.provider_type and args.model and args.api_key):
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "--provider-type, --model, and --api-key are required together when enabling LLM review.",
                    },
                    ensure_ascii=False,
                )
            )
            sys.exit(1)
        try:
            llm = build_llm(
                provider_type=args.provider_type,
                model=args.model,
                api_key=args.api_key,
                base_url=args.base_url,
                max_tokens=16384,
            )
        except Exception as exc:
            print(
                json.dumps(
                    {"ok": False, "error": f"Failed to initialize LLM: {exc}"},
                    ensure_ascii=False,
                )
            )
            sys.exit(1)

    metadata = {
        "memory_root": memory_dir,
        "token_budget": args.token_budget,
        "current_date": "",
        "mode": args.mode,
        "review_prompt": args.review_prompt,
    }

    try:
        if args.review_type == "memory_files":
            result = review_memory_files(
                memory_root=memory_dir,
                metadata=metadata,
                llm=llm,
                skip_report=bool(args.skip_report),
            )
        elif args.review_type == "memory_pack":
            if not args.memory_pack:
                print(
                    json.dumps(
                        {"ok": False, "error": "--memory-pack is required for memory_pack review type."},
                        ensure_ascii=False,
                    )
                )
                sys.exit(1)
            result = review_memory_pack(
                memory_pack=args.memory_pack,
                current_message=args.current_message,
                agent_answer=args.agent_answer,
                metadata=metadata,
                llm=llm,
            )
        elif args.review_type == "user_feedback":
            if not args.user_feedback:
                print(
                    json.dumps(
                        {"ok": False, "error": "--user-feedback is required for user_feedback review type."},
                        ensure_ascii=False,
                    )
                )
                sys.exit(1)
            result = handle_user_feedback(
                user_feedback=args.user_feedback,
                metadata=metadata,
                llm=llm,
            )
        elif args.review_type == "scheduled_cleanup":
            result = compact_timeline(
                memory_root=memory_dir,
                metadata=metadata,
                llm=llm,
            )
        elif args.review_type == "conversation_usage":
            if not args.audit_file:
                print(
                    json.dumps(
                        {"ok": False, "error": "--audit-file is required for conversation_usage review type."},
                        ensure_ascii=False,
                    )
                )
                sys.exit(1)
            audit_path = Path(args.audit_file)
            audit_samples = json.loads(audit_path.read_text(encoding="utf-8-sig")) if audit_path.exists() else []
            if not isinstance(audit_samples, list):
                audit_samples = []
            result = review_conversation_usage(
                audit_samples=audit_samples,
                usage_scope=args.usage_scope,
                memory_root=memory_dir,
                metadata=metadata,
                llm=llm,
            )
        output = result if isinstance(result, dict) else result.model_dump()
        output.setdefault("ok", True)
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
