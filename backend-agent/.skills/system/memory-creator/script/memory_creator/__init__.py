def __getattr__(name: str):
    if name in ("consolidate_memory_source", "consolidate_chat_transcript", "consolidate_document_text"):
        from memory_creator.orchestrator import (
            consolidate_chat_transcript,
            consolidate_document_text,
            consolidate_memory_source,
        )
        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "consolidate_memory_source",
    "consolidate_chat_transcript",
    "consolidate_document_text",
]
