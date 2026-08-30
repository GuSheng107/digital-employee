# 会话持久化 Phase 1：基础可用

> 所属模块：session（会话持久化）
> 定位：第一阶段落地清单。目标 = 能正常聊天 + 能调 Tool/Sub Agent + 服务重启可恢复。

## 目标

第一阶段只解决最核心的问题：

- 用户能正常聊天
- Agent 能调用 Tool / Sub Agent
- 服务重启后可以恢复完整对话

**不要在这个阶段实现：** Branch、Time Travel、Checkpoint、Context Snapshot、Compaction、Memory、大型 Artifact Storage、完整 Observability。

## Phase 1 数据库（5 张核心表）

下列 SQL 用 PostgreSQL 风格类型表达逻辑字段；SQLite 实现时由存储适配层将 UUID、JSONB、TIMESTAMPTZ 映射为等价类型，数据模型不变。

### sessions

```sql
CREATE TABLE sessions (
    id UUID PRIMARY KEY,                -- 会话唯一标识
    tenant_id UUID,                     -- 租户 ID（多租户场景，可选）
    user_id UUID NOT NULL,              -- 所属用户 ID
    title TEXT,                         -- 会话标题（可由首条消息自动生成）
    status VARCHAR(32) NOT NULL DEFAULT 'active',  -- active / archived 等
    metadata JSONB NOT NULL DEFAULT '{}',           -- 扩展元数据
    created_at TIMESTAMPTZ NOT NULL,    -- 创建时间
    updated_at TIMESTAMPTZ NOT NULL     -- 最后更新时间
);

CREATE INDEX idx_sessions_user_updated
ON sessions(user_id, updated_at DESC);
```

### turns

```sql
CREATE TABLE turns (
    id UUID PRIMARY KEY,                -- Turn 唯一标识
    session_id UUID NOT NULL,           -- 所属 Session ID
    sequence BIGINT NOT NULL,           -- 在 Session 内的顺序号（从 1 递增）
    status VARCHAR(32) NOT NULL,        -- running / completed / failed
    started_at TIMESTAMPTZ NOT NULL,    -- 开始时间
    completed_at TIMESTAMPTZ,           -- 完成时间（可为空）
    metadata JSONB NOT NULL DEFAULT '{}',
    UNIQUE(session_id, sequence)        -- 同一 Session 内 sequence 唯一
);

CREATE INDEX idx_turns_session_sequence
ON turns(session_id, sequence);
```

例如：

```text
Turn 1
User: 帮我搜索资料
Agent: ...
```

### runs

Run 表示一次 Agent 执行。第一阶段就把 `parent_run_id` 设计进去，为后面的 Sub Agent 做准备。

```sql
CREATE TABLE runs (
    id UUID PRIMARY KEY,                -- Run 唯一标识
    session_id UUID NOT NULL,           -- 所属 Session ID
    turn_id UUID NOT NULL,              -- 所属 Turn ID
    parent_run_id UUID,                 -- 父 Run ID（用于 Sub Agent 嵌套）
    agent_id TEXT NOT NULL,             -- 执行该 Run 的 Agent 标识
    status VARCHAR(32) NOT NULL,        -- running / completed / failed
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_runs_turn ON runs(turn_id);
CREATE INDEX idx_runs_parent ON runs(parent_run_id);
```

因此：

```text
Main Agent Run
    │
    ├── Tool
    │
    └── Sub Agent Run
             │
             ├── LLM
             └── Tool
```

以后天然可以扩展成执行树。

### events

Event 是 Runtime 的事实记录。第一阶段先实现最基本的 Event。

```sql
CREATE TABLE events (
    id UUID PRIMARY KEY,                -- Event 唯一标识
    session_id UUID NOT NULL,           -- 所属 Session ID
    turn_id UUID,                       -- 所属 Turn ID（可为空，如 session.created）
    run_id UUID,                        -- 所属 Run ID（可为空）
    sequence BIGINT NOT NULL,           -- 在 Session 内的全局顺序号（单调递增）
    event_type VARCHAR(64) NOT NULL,    -- user.message / tool.call 等
    parent_event_id UUID,               -- 父事件 ID（关联因果关系）
    payload JSONB NOT NULL,             -- 事件负载
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE(session_id, sequence)
);

CREATE INDEX idx_events_session_sequence ON events(session_id, sequence);
CREATE INDEX idx_events_run_sequence ON events(run_id, sequence);
CREATE INDEX idx_events_parent ON events(parent_event_id);
```

### messages

Message 是专门用于恢复 LLM Conversation History 的投影表。

```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY,                -- Message 唯一标识
    session_id UUID NOT NULL,
    turn_id UUID,
    run_id UUID,
    event_id UUID NOT NULL,             -- 对应的 Event ID（来源事件）
    sequence BIGINT NOT NULL,           -- 用于排序
    role VARCHAR(32) NOT NULL,          -- system / user / assistant / tool
    content JSONB NOT NULL,             -- 消息内容（支持多模态）
    tool_call_id TEXT,                  -- tool 消息对应的 tool_call ID
    tool_name TEXT,                     -- tool 消息对应的工具名称
    is_visible BOOLEAN NOT NULL DEFAULT TRUE, -- 是否对用户可见
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_messages_session_sequence
ON messages(session_id, sequence);
```

## Phase 1 Event 类型

第一阶段只实现这些：

`session.created`、`turn.started`、`turn.completed`、`user.message`、`run.started`、`run.completed`、`llm.request`、`llm.response`、`tool.call`、`tool.result`、`subagent.started`、`subagent.completed`、`assistant.message`、`error`。

不需要一开始设计几十种 Event。

## 核心写入流程

用户发送 User Message，Runtime 执行：

```text
Session
  ↓
Create Turn
  ↓
Create Run
  ↓
append user.message Event
  ↓
append Message
  ↓
Context Builder
  ↓
LLM
```

LLM 调 Tool：

```text
tool.call Event
      ↓
Tool Execute
      ↓
tool.result Event
      ↓
继续 LLM
```

最终：

```text
assistant.message Event
      ↓
Message Projection
      ↓
Turn Complete
```

## 对话恢复

服务重启后：

```text
session_id
    ↓
SELECT messages
FROM messages
WHERE session_id = ?
ORDER BY sequence
    ↓
Message[]
    ↓
Context Builder
    ↓
LLM
```

第一阶段已满足：保存用户/AI 消息、保存 Tool、保存 Sub Agent、恢复历史、服务重启恢复、多轮对话。

## 最重要原则

虽然第一阶段主要依赖 messages 读取历史，但 **Event 必须同时写入**。即：

- `Event = Source of Truth`
- `Message = Query Projection`

如果 Message 表出现问题，可通过 events 重建 messages：

```text
events → rebuild → messages
```

第一阶段不用实现自动 Projection Worker，直接在同一个数据库事务中完成即可。

## 第一阶段明确"不做"

❌ Event Bus　❌ Kafka　❌ Event Sourcing Framework　❌ CQRS Framework　❌ Vector Database　❌ Memory System　❌ Checkpoint　❌ Time Travel　❌ Context Compaction　❌ Object Storage　❌ 分布式 Trace　❌ 复杂 Branch Graph

数据库先使用 SQLite，Runtime 直接使用 Transaction → Event → Message Projection，先把基础闭环跑起来；后续经 `RunStore` 迁移 PostgreSQL。

## 一致性原则（Phase 1）

第一阶段：Event + Message 在同一个数据库 Transaction 中写入。

```sql
BEGIN
INSERT event(user.message)
INSERT message(user)
COMMIT
```

Tool：

```sql
BEGIN
INSERT tool.call
执行 Tool
INSERT tool.result
COMMIT
```

如果未来 Tool 执行时间过长，则改成：event append → async execution → result event。不要为了"高级"而在第一阶段引入复杂消息队列。

## 第一阶段验收标准

必须能够完成：

- 普通对话：`User → Agent → User → Agent`
- 服务重启恢复：`Session → 完整恢复`
- Tool：`User → Agent → Tool Call → Tool Result → Agent`，恢复后能正确重建 Context（User / Assistant(tool call) / Tool(result) / Assistant）
- Sub Agent：`Main Agent → Sub Agent → Tool → Sub Agent Result → Main Agent`，能从 `parent_run_id` 找到完整执行关系
- Event：能根据 Event 的 `session_id + sequence` 按顺序 Replay

## 相关文档

- 概述：[总文档.md](总文档.md)
- Phase 2：[Phase2-完整Runtime持久化.md](Phase2-完整Runtime持久化.md)
- 决策依据：[../../10-决策记录/10-决策记录.md](../../10-决策记录/10-决策记录.md)
