---
name: memory-creator
description: Convert prepared source text (chat Q&A pairs, explicit memory text, or large document text) into cleaned, structured, long-term JSON memory artifacts. Use when you need to extract reusable memory from chat transcripts, consolidate document text into memory summaries, create or update memory JSON files, or run the memory consolidation pipeline. Triggers on tasks involving "consolidate memory", "extract memory from chat", "summarize document to memory", "create memory artifacts", "process chat transcript", "process document text", "memory consolidation", "记忆提取", "记忆整理", "文档摘要写入记忆", "处理对话记录", "处理文档文本", "写入记忆", "更新记忆文件". This skill is the write-side companion to memory-reader; use it whenever source text needs to become persistent memory.
---

# Memory Creator

## Overview

memory-creator converts prepared source text into cleaned, structured, long-term JSON memory artifacts. The source text is either a concatenated chat transcript (Q&A pairs), explicit memory text, or a large extracted document text.

The memory library is **globally shared** — a single unique store with no bot-level isolation.

## Core Principles

1. Receives prepared text as input; does not read databases, parse files, or scan folders.
2. Uses LangChain as a deterministic text-processing pipeline, not a free-form agent.
3. All output memory artifacts are JSON files using `app.memory_schema`.
4. Remote LLMs receive only plain text prompts.
5. Chinese memory content by default; English technical metadata and structure.
6. Does not manage task scheduling, vector databases, OCR, or media processing.

## Source Types

### chat
Input is a concatenated chat transcript. Extract explicit memory, stable user preferences, project updates, business facts, decisions, open questions, and timeline items. Only user messages can create explicit memory.

### document
Input is a large extracted document text. Summarize and extract key points, business facts, rules, policies, terms, action items, risks, open questions, and project memory candidates. Document text must never directly create explicit user memory or profile memory.

## Input Schema

```json
{
  "source_type": "chat | document | explicit",
  "source_text": "",
  "metadata": {
    "source_id": "",
    "title": "",
    "created_at": "",
    "filename": "",
    "mime_type": "",
    "extra": {}
  }
}
```

## Output Schema

```json
{
  "source_type": "",
  "source_id": "",
  "updated_files": [],
  "memory_items": {
    "explicit": [],
    "profile": [],
    "work": [],
    "document": [],
    "timeline": [],
    "inbox": [],
    "changelog": []
  },
  "summary": ""
}
```

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

### File Responsibilities

| File | Responsibility |
|------|---------------|
| rules.json | Memory usage rules |
| profile.json | Stable long-term user preferences and communication habits |
| explicit.json | User explicitly requested memory; only from chat or explicit input |
| work.json | Work goals, constraints, decisions, architecture notes, business facts |
| documents/{source_id}.json | Cleaned summary of one document source; never store full raw text unless LLM fallback is unavoidable |
| timeline/YYYY-MM.json | Chronological summaries of chat and document events |
| inbox.json | Uncertain, conflicting, or low-confidence memory candidates |
| changelog.json | Memory update log |

## Processing Flow

1. Receive source_type, source_text, and metadata.
2. If source_type is "chat", run the Chat Consolidation Pipeline.
3. If source_type is "document", run the Document Consolidation Pipeline.
4. Generate structured memory candidates.
5. Promote candidates to target JSON files.
6. Write JSON files through schema-aware atomic writers.
7. Return updated files and extracted memory items.

## Chat Consolidation Pipeline

```
normalize_input → format_chat_transcript → chat_summary_chain → memory_promoter → json_writer
```

The chat_summary_chain extracts: conversation_summary, explicit_memories, profile_candidates, business_facts, decisions, open_questions, timeline_items, inbox_items.

## Document Consolidation Pipeline

```
normalize_input → document_chunk_chain → memory_promoter → json_writer
```

The document_chunk_chain processes the full document text in one pass and extracts: chunk_summary, key_points, business_facts, rules_or_policies, terms, action_items, risks, open_questions.

## Memory Promotion Rules

### Chat input

| Extracted Item | Target File |
|---------------|-------------|
| explicit_memories | explicit.json |
| profile_candidates (stable long-term only) | profile.json |
| business_facts, decisions | work.json |
| open_questions, low-confidence items | inbox.json |
| conversation_summary, timeline_items | timeline/YYYY-MM.json |

### Document input

| Extracted Item | Target File |
|---------------|-------------|
| document_summary, key_points, business_facts, rules_or_policies, terms, action_items, risks, open_questions | documents/{source_id}.json |
| project_memory_candidates | work.json |
| document event summary | timeline/YYYY-MM.json |
| uncertain or conflicting items | inbox.json |

### Hard Constraints

- Document input must never write to explicit.json or profile.json.
- Explicit memory can only come from chat input.
- User profile memory should come from chat behavior or explicit user instructions only.
- Conflicting memory goes to inbox.json for review.
- Actual memory content should be Chinese unless the source content is English.

## JSON Writer Rules

- Write only under the memory directory.
- Use `MemoryItem`, `MemoryFile`, `TimelineFile`, `DocumentMemoryFile`, and `ChangelogFile` schemas.
- Write atomically with the directory lock in `app.memory_schema`.
- Deduplicate before writing. The effective source tier is explicit/admin-config memory > document memory > chat/session memory; chat writes should skip content already present in explicit or document memory.
- In `mode=update`, remove old items with the same `source_id` before writing the new source content, so reprocessing a document does not leave stale duplicate entries.
- Preserve document display names by writing `metadata.title` into `DocumentMemoryFile.source_filename` when available.
- Write changelog entries for every update.

## How to Run

This skill is a **system-level skill** that runs through the project's task/tool system. When a user message triggers this skill (via keyword matching), the Agent will receive a `consolidate` script tool and call it with CLI arguments.

### Agent 调用方式

当 Agent 判断需要提取记忆时，调用 `consolidate` 脚本工具：

**处理聊天问答对：**

```
--source-type chat --source-text "用户: 以后默认用UTF-8编码\n助手: 好的，已记住" --source-id chat-001
```

**处理文档文本：**

```
--source-type document --source-text "API设计规范：所有接口必须使用RESTful风格..." --source-id doc-api-spec --title "API设计规范"
```

**从文件读取源文本：**

```
--source-type document --source-file /path/to/document.txt --source-id doc-policy --title "公司差旅政策"
```

### 参数说明

| 参数 | 必填 | 说明 |
|------|------|------|
| `--source-type` | 是 | `chat`、`document` 或 `explicit` |
| `--source-text` | 二选一 | 内联源文本内容 |
| `--source-file` | 二选一 | 源文本文件路径 |
| `--source-id` | 否 | 来源唯一标识，用于文件命名 |
| `--title` | 否 | 来源标题，用于文档索引 |
| `--memory-dir` | 否 | 记忆目录路径，默认 `.memory`（相对于项目根目录） |
| `--model` | 否 | LLM 模型名称（可选） |
| `--base-url` | 否 | LLM API 地址（可选） |

### 输出格式

脚本输出 JSON，包含更新文件列表和提取的记忆条目：

```json
{
  "ok": true,
  "source_type": "chat",
  "source_id": "chat-001",
  "updated_files": [".memory/explicit.json", ".memory/profile.json", ".memory/timeline/2026-05.json"],
  "memory_items": {
    "explicit": ["以后默认用UTF-8编码"],
    "profile": [],
    "work": [],
    "document": [],
    "timeline": ["讨论了编码规范"],
    "inbox": [],
    "changelog": []
  },
  "summary": "讨论了编码规范"
}
```

### 典型触发场景

1. **用户明确要求记住某事**："记住以后都用REST风格" → Agent 调用 `--source-type chat`
2. **用户提供大段文本要求提取**："帮我整理这段文档到记忆" → Agent 调用 `--source-type document`
3. **对话中出现可复用知识**：Agent 主动判断对话包含值得持久化的信息 → Agent 调用 `--source-type chat`
4. **文档解析后入库**：外部系统解析完文档后，将文本传入 → Agent 调用 `--source-type document`

### Python API（可选）

如需在代码中直接调用，可 import orchestrator：

```python
import sys
sys.path.insert(0, r".skills/system/memory-creator/script")

from memory_creator.orchestrator import consolidate_memory_source

result = consolidate_memory_source(
    source_type="chat",
    source_text="...",
    metadata={"source_id": "chat-001"}
)
```

## Prompt Templates

See `references/prompts.md` for the full prompt templates used in each chain.
