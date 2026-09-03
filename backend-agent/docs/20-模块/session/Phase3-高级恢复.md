# 会话持久化 Phase 3+：高级恢复与长上下文

> 所属模块：session（会话持久化）
> 定位：长对话、中断恢复、精确 Debug、生产级优化；只有前两阶段稳定后才做。

## Phase 3 目标

解决：长对话、Agent 中断恢复、Context Replay、Context Compaction、Time Travel、Human-in-the-loop、精确 Debug。这一阶段才引入 Checkpoint、Context Snapshot、Compaction。

## Checkpoint

Checkpoint 表示"Agent 在这个时间点的完整可恢复状态"。

```sql
CREATE TABLE checkpoints (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL,
    branch_id UUID NOT NULL,
    run_id UUID,
    event_sequence BIGINT NOT NULL,     -- 对应的 Event sequence（恢复点）
    state JSONB NOT NULL,               -- 完整可恢复状态（序列化）
    created_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_checkpoints_branch_sequence
ON checkpoints(branch_id, event_sequence DESC);
```

## Context Snapshot

记录某次 LLM 实际看到的 Context。

```sql
CREATE TABLE context_snapshots (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL,
    event_id UUID,                      -- 对应 Event ID（llm.request）
    branch_id UUID,
    prompt_hash TEXT,                   -- Prompt 哈希（版本比对）
    token_count INTEGER,                -- 上下文 token 数
    context JSONB,                      -- 实际上下文内容（小型可存 JSON）
    context_ref TEXT,                   -- 大型上下文的引用（如 Object Storage URI）
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_context_snapshots_run ON context_snapshots(run_id);
```

作用：

```text
为什么 Agent 当时这么回答？
        ↓
找到 LLM Call
        ↓
找到 Context Snapshot
        ↓
看到当时实际输入
```

## Reasoning / Thinking

不要放进 messages，应该属于 Execution Trace。可以作为 `event_type = reasoning`，或 LLM Call 的附加数据。

原则：Conversation History ≠ Reasoning。默认不进入下一次 LLM Context、不作为用户可见消息；是否保存完整内容由具体模型和隐私策略决定。

## Context Compaction

当历史过长：

```text
Message 1 ~ 500
        ↓
Compaction
        ↓
Summary
        +
Message 501 ~ latest
```

建议增加：

```sql
context_compactions
-------------------
id                -- Compaction 唯一标识
branch_id         -- 所属 Branch ID
start_sequence    -- 压缩起始 sequence
end_sequence      -- 压缩结束 sequence
summary           -- 摘要内容
token_before      -- 压缩前 token 数
token_after       -- 压缩后 token 数
created_at        -- 创建时间
```

以后 Context Builder 不再读取整个历史：

```text
Summary
+
Recent Messages
+
Relevant Memory
+
Current Tool State
```

## Phase 4：生产级优化

这一阶段才处理大规模生产问题：Object Storage、Event Partition、异步 Projection、冷热数据、全文搜索、Vector Search、Memory、Artifact、Trace/Observability、数据归档。

### 大型 Tool Result

不要让数据库保存几十 MB 的 Tool Result：

```text
Tool
  ↓
小结果 → PostgreSQL JSONB

大结果
  ↓
Object Storage
  ↓
artifact_id
```

```sql
artifacts
---------
id                -- Artifact 唯一标识
session_id        -- 所属 Session ID
run_id            -- 所属 Run ID
type              -- image / file / json 等
storage_uri       -- 存储位置 URI
size              -- 大小（字节）
content_type      -- MIME 类型
checksum          -- 校验和
created_at        -- 创建时间
metadata          -- 扩展元数据
```

Message / Tool Call 只保存 `artifact_id`。

## 推荐最终数据库结构

```text
sessions
    │
    └── branches
          │
          └── turns
                │
                └── runs
                     │
                     ├── llm_calls
                     ├── tool_calls
                     └── child runs

events
    │
    ├── messages
    ├── checkpoints
    ├── context_snapshots
    └── compactions

artifacts
```

```text
                 SESSION
                    │
                 BRANCH
                    │
                  TURN
                    │
                  RUN
              ┌─────┼─────┐
              │     │     │
             LLM   TOOL  SUBAGENT
              │     │     │
              └─────┼─────┘
                    │
                  EVENT
                    │
       ┌────────────┼─────────────┐
       ▼            ▼             ▼
   MESSAGE       TRACE         STATE
                 Context
                   │
               ┌────┴────┐
               ▼         ▼
           Snapshot   Checkpoint
```

## 一致性原则（异步演进）

若 Tool 执行时间过长：event append → async execution → result event。不要为了追求架构"高级"而在第一阶段引入复杂消息队列。

## 读取策略

| 场景 | 查询方式 |
| --- | --- |
| 普通聊天 | `messages WHERE branch_id/session_id ORDER BY sequence` |
| 执行 Debug | `events WHERE run_id ORDER BY sequence` |
| Tool 分析 | `tool_calls WHERE tool_name / run_id` |
| LLM 分析 | `llm_calls WHERE run_id / model` |
| 恢复 | `checkpoint → events since checkpoint` |
| Branch | parent history until fork + branch events |

## 三阶段 Context 恢复策略

- **Phase 1**：`messages → Context`（简单直接）。
- **Phase 2**：`messages + Tool / Run 信息 → Context`（开始支持复杂 Agent）。
- **Phase 3+**：`Checkpoint + Compaction + Recent Messages + Memory + Runtime State → Context`（支持长时间运行 Agent）。

## 实现优先级

```text
Phase 1
├── Session → Turn → Run → Event → Message
├── Conversation Restore
└── Tool / SubAgent 基础记录
        ▼
Phase 2
├── Branch / Tool Call / LLM Call
├── Token Usage / Prompt Version
└── Execution Trace
        ▼
Phase 3
├── Checkpoint / Context Snapshot / Compaction
├── Resume / Time Travel / Human-in-the-loop
        ▼
Phase 4
├── Artifact Storage / Async Projection / Event Partition
├── Search / Memory / Cold Storage
└── Production Observability
```

## 相关文档

- 概述：[总文档.md](总文档.md)
- Phase 1：[Phase1-基础可用.md](Phase1-基础可用.md)
- Phase 2：[Phase2-完整Runtime持久化.md](Phase2-完整Runtime持久化.md)
