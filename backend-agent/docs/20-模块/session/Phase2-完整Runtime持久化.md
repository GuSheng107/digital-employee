# 会话持久化 Phase 2：完整 Runtime 持久化

> 所属模块：session（会话持久化）
> 定位：第一阶段稳定后，回答"Agent 是怎么执行的"，而不只是"Agent 说了什么"。

## 目标

Phase 1 稳定以后，再增加：Branch、Tool Call、LLM Call、Usage、Sub Agent Trace、Prompt Version。

## Branch

```sql
CREATE TABLE branches (
    id UUID PRIMARY KEY,                -- Branch 唯一标识
    session_id UUID NOT NULL,           -- 所属 Session ID
    parent_branch_id UUID,              -- 父 Branch ID（从哪个分支分叉）
    fork_event_id UUID,                 -- 分叉点对应的 Event ID
    fork_message_id UUID,               -- 分叉点对应的 Message ID
    created_at TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_branches_session ON branches(session_id);
```

结构：

```text
Session
  ├── Branch A
  │    ├── msg1
  │    ├── msg2
  │    └── msg3
  │
  └── Branch B
        └── msg4
```

Branch B 不复制 A 的历史，通过 `parent_branch_id` 和 `fork_event_id` 继承历史。

## Branch History 算法

查询 Branch B 的逻辑：

```text
Parent Branch History
        ↓
截止 fork_event
        ↓
+
Branch B Events
        ↓
完整 History
```

因此：

```text
A: 1 2 3 4 5
从 3 fork
B: 1 2 3 6 7
```

数据库中实际上只新增 6、7，不复制 1、2、3。

## Tool Call

增加独立表。Event 负责记录事实，Tool Call 表负责高效查询（调用了什么 Tool、参数、结果、耗时、成功与否）。

```sql
CREATE TABLE tool_calls (
    id UUID PRIMARY KEY,                -- Tool Call 唯一标识
    event_id UUID NOT NULL,             -- 对应 Event ID（tool.call 事件）
    run_id UUID NOT NULL,
    session_id UUID NOT NULL,
    tool_name TEXT NOT NULL,
    arguments JSONB,                    -- 调用参数
    result JSONB,                       -- 执行结果（小结果直接存，大结果存 artifact_id）
    status VARCHAR(32) NOT NULL,        -- pending / running / success / failed
    error TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    latency_ms BIGINT,
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_tool_calls_run ON tool_calls(run_id);
CREATE INDEX idx_tool_calls_name ON tool_calls(tool_name);
```

## LLM Call

```sql
CREATE TABLE llm_calls (
    id UUID PRIMARY KEY,                -- LLM Call 唯一标识
    event_id UUID NOT NULL,             -- 对应 Event ID（llm.request / llm.response）
    run_id UUID NOT NULL,
    provider TEXT NOT NULL,             -- openai / anthropic 等
    model TEXT NOT NULL,
    request_id TEXT,                    -- 请求 ID（用于对账）
    input_tokens INTEGER,
    output_tokens INTEGER,
    cached_tokens INTEGER,
    total_tokens INTEGER,
    latency_ms BIGINT,
    finish_reason TEXT,                 -- stop / length / tool_call 等
    status VARCHAR(32) NOT NULL,        -- success / failed
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_llm_calls_run ON llm_calls(run_id);
CREATE INDEX idx_llm_calls_model ON llm_calls(model);
```

用于：Token 统计、模型分析、Cache Hit、延迟分析、成本分析、Debug。

## Prompt 不作为 Session 固定字段

System Prompt / Developer Prompt 应该属于 Context Assembly，而不是 `session.system_prompt`。因为一次 Session 中可能出现：

- LLM #1：System Prompt V1
- LLM #2：System Prompt V1 + Memory
- LLM #3：System Prompt V2 + Tool Context

因此 Phase 2 开始记录 `prompt_version`、`prompt_hash` 即可，暂时不保存完整 Context Snapshot。

## 相关文档

- 概述：[总文档.md](总文档.md)
- Phase 1：[Phase1-基础可用.md](Phase1-基础可用.md)
- Phase 3+：[Phase3-高级恢复.md](Phase3-高级恢复.md)
