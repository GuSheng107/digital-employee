---
name: memory-reader
always_active: true
description: Read JSON memory artifacts created by memory-creator, select the most relevant and reliable memory for the current user request, build a focused Memory Pack, and return it for injection into an agent context. Use when you need to retrieve relevant memory before responding to a user, load user preferences or project constraints, build a context pack from memory files, or check for memory conflicts. Triggers on tasks involving "read memory", "load memory", "get memory context", "retrieve memory", "build memory pack", "check user preferences", "load project constraints", "读取记忆", "加载记忆", "获取记忆上下文", "检索记忆", "构建记忆包", "查看用户偏好", "加载项目约束". This skill is the read-side companion to memory-creator; use it whenever an agent needs memory context to respond accurately.
---

# Memory Reader

## Overview

memory-reader reads JSON memory files created by memory-creator, selects the most relevant and reliable memory for the current user request, builds a focused Memory Pack, and returns it for injection into an agent context.

The memory library is **globally shared** — a single unique store with no bot-level isolation.

## Core Principles

1. Reads JSON memory files only.
2. Does not read SQLite, parse raw documents, or scan unknown folders.
3. Does not use a vector database or build a free-form agent.
4. Uses deterministic selection, keyword matching, section parsing, priority rules, and optional LLM consolidation.
5. The goal is to keep the pack focused while preserving enough useful context; do not minimize tokens at the cost of losing relevant memory.
6. Current user instruction always overrides historical memory.
7. Explicit memory is higher priority than inferred memory.
8. Chinese memory content is preserved unless the original source was English.

## Memory Directory

```
.memory/
  rules.json
  profile.json
  explicit.json
  work.json
  documents/{source_id}.json
  timeline/YYYY-MM.json
  inbox.json
  changelog.json
```

## Input Schema

```json
{
  "current_message": "",
  "metadata": {
    "memory_root": ".memory",
    "current_date": "",
    "conversation_id": "",
    "source_type": "chat | document | task | unknown",
    "token_budget": 4000,
    "mode": "default | compact | expanded"
  }
}
```

## Output Schema

```json
{
  "memory_pack": "",
  "selected_files": [],
  "selected_sections": [],
  "omitted_files": [],
  "token_budget_used_estimate": 0,
  "confidence": "high | medium | low",
  "needs_more_memory": false,
  "reason": ""
}
```

## Reading Strategy

### Always Read

1. rules.json
2. explicit.json
3. profile.json
4. work.json
5. recent timeline/YYYY-MM.json

### Read Conditionally

1. documents/{source_id}.json — when source_id, file name, or topic is relevant
2. inbox.json — when there may be conflicts, uncertainty, or user asks for review
3. changelog.json — when user asks what changed or when debugging memory updates

### Priority Order

1. Current user message (highest)
2. explicit.json
3. work.json
4. profile.json
5. recent timeline
6. documents related to the current request
7. inbox.json
8. changelog.json

## Token Budget Policy

If token_budget is missing or 0, use the total budget for the selected mode.

| Mode | Total | rules | explicit | work | profile | timeline | document | inbox |
|------|-------|-------|----------|------|---------|----------|----------|-------|
| compact | 1500 | 60 | 300 | 360 | 150 | 120 | 360 | 150 |
| default | 4000 | 120 | 720 | 960 | 320 | 400 | 1200 | 280 |
| expanded | 8000 | 200 | 960 | 1600 | 560 | 800 | 3200 | 680 |

- **Compact mode**: Maximum 1500 tokens. Include explicit memory, top work constraints, critical profile preferences, and directly relevant document/timeline facts.
- **Default mode**: Maximum 4000 tokens. Include explicit memory, work memory, stable profile, relevant timeline, and relevant document memory.
- **Expanded mode**: Maximum 8000 tokens. Include broader relevant document memory, additional timeline context, and more supporting work notes.
- If relevant matched items cannot fit the total or per-file budget, set `needs_more_memory=true` and explain the omitted count in `reason`; do not report this as "no matching memory".

## Selection Pipeline

```
load_known_json_memory_files
→ extract_query_terms
→ score_memory_items
→ apply_priority_rules
→ trim_to_budget
→ optional_llm_consolidation
→ build_memory_pack
→ return_result
```

## Scoring Rules

```
score = keyword_match + priority + recency + source_weight - length_penalty
```

### Source Weights

| File | Weight |
|------|--------|
| explicit.json | 10.0 (highest) |
| work.json | 8.0 (high) |
| profile.json | 6.0 (medium-high) |
| documents/{source_id}.json | 5.0 (conditional high when relevant) |
| timeline/YYYY-MM.json | 4.0 (medium) |
| rules.json | 3.0 |
| inbox.json | 2.0 (low unless conflict-related) |
| changelog.json | 1.0 (low unless user asks about changes) |

## Accuracy Rules

- Never invent memory.
- Only use content found in JSON memory files.
- Preserve source meaning.
- Include source file paths in metadata, not in the final Memory Pack.
- If memory conflicts, do not resolve silently.
- Prefer current user instruction over historical memory.
- Prefer explicit memory over inferred memory.
- Prefer work memory over timeline summaries unless the timeline contains unique relevant evidence.
- Prefer newer memory when two memories conflict.
- Put unresolved conflicts into the output reason or needs_more_memory explanation.
- Treat budget omission as a review signal: the agent or reviewer may retry with `expanded` mode or inspect the omitted source, instead of assuming the memory base lacks coverage.

## Relevance Selection Rules

- Extract keywords from current_message.
- Match keywords against item content, `speed_lookup`, and structured retrieval hints.
- Always include high-priority explicit memory even if keyword match is weak.
- Include work constraints when work memory is available.
- Include document memory only when current_message mentions a document, file name, source_id, or topic that matches document items.
- Include inbox.json only when there may be conflicts, uncertainty, or user asks for review.
- Include changelog.json only when user asks what changed or when debugging memory updates.

## JSON Parsing Rules

- Parse only `MemoryItem` schema fields.
- Preserve file/source boundaries in metadata.
- Prefer concise bullet points over long paragraphs, but do not omit unique relevant details just to make the pack shorter.
- Ignore empty sections.
- Ignore duplicated items.
- Do not include full documents unless expanded mode explicitly requires it.

## Deduplication

- Remove repeated bullets.
- Merge near-identical constraints.
- Keep the most recent or most explicit version.
- Do not merge conflicting memories; report conflict instead.
- Preserve the effective source tier: explicit/admin-config memory outranks document memory, and document memory outranks chat/session memory.

## Memory Pack Format

```text
共检索到 N 条相关记忆 (来自 M 个文件)

[管理员配置内容]
- ... (来源：管理员配置内容)

[文档《API设计规范.pdf》]
- ... (来源：文档《API设计规范.pdf》)

[工作笔记]
- ...
```

The Memory Pack should be concise and directly useful to the agent. Only explicit memory and document memory carry answer-visible source labels: explicit memory is shown as `管理员配置内容`, and document memory is shown with the document display name. Chat/session, work, profile, timeline, and inbox items do not expose a source label unless the item itself came from a document or explicit/admin source.

## LLM Consolidation

The skill may use an LLM to consolidate selected memory sections, but only after deterministic selection.

- The LLM must not add new facts.
- The LLM must preserve important constraints, preferences, names, and technical details.
- The LLM must preserve Chinese memory content unless the source content is English.
- The LLM should remove duplicate wording and irrelevant filler, not discard relevant unique memory.

See `references/prompts.md` for the consolidation prompt template.

## How to Run

The main entry point is `script/memory_reader/orchestrator.py`.

Before importing, add the scripts directory to Python path:

```bash
# From project root
set PYTHONPATH=d:\pyPrj\wecom-bot-agent\.skills\system\memory-reader\script;%PYTHONPATH%
```

### Main Function

```python
from memory_reader.orchestrator import read_memory_for_task

result = read_memory_for_task(
    current_message="帮我查一下项目的部署约束",
    metadata={
        "memory_root": ".memory",
        "mode": "default",
    }
)
```

### Convenience Functions

```python
from memory_reader.orchestrator import (
    build_memory_pack,
    read_work_memory,
    read_explicit_memory,
    read_profile_memory,
    read_recent_timeline,
    read_document_memory,
)

pack = build_memory_pack("用户偏好是什么？", metadata={})
work = read_work_memory(memory_root=".memory")
explicit = read_explicit_memory(memory_root=".memory")
profile = read_profile_memory(memory_root=".memory")
timeline = read_recent_timeline(memory_root=".memory", limit=3)
document = read_document_memory("doc-001", memory_root=".memory")
```

## MVP Scope

### Supports

- Reading JSON memory files
- Parsing headings and bullet sections
- Keyword-based relevance selection
- Priority-based memory selection
- Token budget control
- Compact/default/expanded modes
- Optional LLM consolidation
- Conflict warnings
- Chinese memory preservation
- Returning a concise Memory Pack

### Does Not Support

- SQLite reading
- Raw document parsing
- File scanning outside memory directory
- Vector database retrieval
- Free-form agent
- Background scheduling
- Memory writing or updating
