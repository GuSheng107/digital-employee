from __future__ import annotations


def format_memory_files(memory_files: dict[str, str]) -> str:
    parts: list[str] = []
    for file_key, content in memory_files.items():
        if content:
            parts.append(f"## File: {file_key}\n{content}")
    return "\n\n".join(parts) if parts else "(no memory files)"
