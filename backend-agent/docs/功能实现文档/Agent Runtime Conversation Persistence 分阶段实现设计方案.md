Agent Runtime Conversation Persistence 分阶段实现设计方案
版本：V1.0

摘要
你现在最需要的不是把所有“未来能力”一次性设计完，而是把核心数据模型一次定对，功能按阶段逐步增加。

建议把整个实现明确拆成 Phase 1 基础可用 → Phase 2 Runtime 完整 → Phase 3 高级能力 → Phase 4 生产级优化。这样第一阶段就能支撑正常 Agent 对话、Tool、Sub Agent，同时数据库结构不会把后面的能力堵死。

核心概念澄清
在阅读本文档前，请先分清以下四个概念，避免混淆：

概念	它代表什么	例子
Session	一整个聊天空间	“我的 Python Agent 聊天”
Branch	从历史某一点分叉出来的一条对话路线	“从第 10 条消息重新开始”
Turn	用户发起的一轮请求，以及 Agent 为响应它进行的整个处理	“用户问：帮我查东京天气”
Run	Agent 实际执行的一次运行	主 Agent Run、Sub Agent Run
Turn 不是 Branch。一个 Session 可以包含多个 Branch，一个 Branch 下可以包含多个 Turn；一个 Turn 内部可能触发多个 Run（主 Agent Run 和子 Agent Run）。层级关系为：

text
Session
  └── Branch
        └── Turn
              └── Run
1. 设计目标
Conversation Persistence 负责保存 Agent Runtime 的：

用户消息

Assistant 消息

System / Developer Prompt

Tool 调用与结果

Sub Agent 调用

Agent 执行过程

Conversation History

Context

Checkpoint

Branch / Fork

Token / Cache

Runtime Error

核心原则：

Event 保存事实，Message 保存对话视图，Run 保存执行过程。

不要把所有数据塞进一个 Session JSON，也不要一开始就实现完整 Event Sourcing + Checkpoint + Time Travel。

2. 总体架构
text
                    ┌──────────────┐
                    │    Session   │
                    └──────┬───────┘
                           │
                         Branch
                           │
                          Turn
                           │
                          Run
                           │
                    ┌──────┼──────┐
                    │      │      │
                   LLM    Tool   SubAgent
                    │      │      │
                    └──────┼──────┘
                           │
                         Event
                           │
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
         Messages        Runs       Context/
       Conversation      Trace      Checkpoint
数据库采用：

PostgreSQL

Object Storage（后期）

3. 数据职责划分
数据	作用	是否第一阶段实现
Session	一条聊天	✅
Branch	对话分支	第二阶段
Turn	一次用户请求	✅
Run	Agent 一次执行	✅
Event	Runtime 事实记录	✅
Message	LLM 对话历史	✅
Tool Call	Tool 执行记录	第二阶段
LLM Call	LLM 调用详情	第二阶段
Context Snapshot	LLM 实际输入	第三阶段
Checkpoint	Agent 状态恢复	第三阶段
Compaction	长上下文压缩	第三阶段
Artifact	大型 Tool 结果 / 文件	第四阶段
4. Phase 1：基础实现
4.1 目标
第一阶段只解决最核心的问题：

用户能正常聊天

Agent 能调用 Tool / Sub Agent

服务重启后可以恢复完整对话

不要在这个阶段实现：

Branch

Time Travel

Checkpoint

Context Snapshot

Compaction

Memory

大型 Artifact Storage

完整 Observability

4.2 Phase 1 数据库
第一阶段只需要 5 张核心表：

sessions

turns

runs

events

messages

4.2.1 sessions
保存聊天本身的元数据。

sql
CREATE TABLE sessions (
    id UUID PRIMARY KEY,                -- 会话唯一标识
    tenant_id UUID,                     -- 租户 ID（多租户场景，可选）
    user_id UUID NOT NULL,              -- 所属用户 ID
    title TEXT,                         -- 会话标题（可由首条消息自动生成）
    status VARCHAR(32) NOT NULL DEFAULT 'active',  -- 会话状态：active / archived 等
    metadata JSONB NOT NULL DEFAULT '{}',           -- 扩展元数据（自定义字段）
    created_at TIMESTAMPTZ NOT NULL,    -- 创建时间
    updated_at TIMESTAMPTZ NOT NULL     -- 最后更新时间
);

CREATE INDEX idx_sessions_user_updated
ON sessions(user_id, updated_at DESC);
4.2.2 turns
一次用户输入到最终 Agent 输出。

sql
CREATE TABLE turns (
    id UUID PRIMARY KEY,                -- Turn 唯一标识
    session_id UUID NOT NULL,           -- 所属 Session ID
    sequence BIGINT NOT NULL,           -- 在 Session 内的顺序号（从 1 递增）
    status VARCHAR(32) NOT NULL,        -- Turn 状态：running / completed / failed
    started_at TIMESTAMPTZ NOT NULL,    -- 开始时间
    completed_at TIMESTAMPTZ,           -- 完成时间（可为空）
    metadata JSONB NOT NULL DEFAULT '{}', -- 扩展元数据
    UNIQUE(session_id, sequence)        -- 同一 Session 内 sequence 唯一
);

CREATE INDEX idx_turns_session_sequence
ON turns(session_id, sequence);
例如：

text
Turn 1
User: 帮我搜索资料
Agent: ...
4.2.3 runs
Run 表示一次 Agent 执行。第一阶段就把 parent_run_id 设计进去，为后面的 Sub Agent 做准备。

sql
CREATE TABLE runs (
    id UUID PRIMARY KEY,                -- Run 唯一标识
    session_id UUID NOT NULL,           -- 所属 Session ID
    turn_id UUID NOT NULL,              -- 所属 Turn ID
    parent_run_id UUID,                 -- 父 Run ID（用于 Sub Agent 嵌套）
    agent_id TEXT NOT NULL,             -- 执行该 Run 的 Agent 标识
    status VARCHAR(32) NOT NULL,        -- Run 状态：running / completed / failed
    started_at TIMESTAMPTZ NOT NULL,    -- 开始时间
    completed_at TIMESTAMPTZ,           -- 完成时间（可为空）
    metadata JSONB NOT NULL DEFAULT '{}' -- 扩展元数据
);

CREATE INDEX idx_runs_turn
ON runs(turn_id);

CREATE INDEX idx_runs_parent
ON runs(parent_run_id);
因此：

text
Main Agent Run
    │
    ├── Tool
    │
    └── Sub Agent Run
             │
             ├── LLM
             └── Tool
以后天然可以扩展成执行树。

4.2.4 events
Event 是 Runtime 的事实记录。第一阶段先实现最基本的 Event。

sql
CREATE TABLE events (
    id UUID PRIMARY KEY,                -- Event 唯一标识
    session_id UUID NOT NULL,           -- 所属 Session ID
    turn_id UUID,                       -- 所属 Turn ID（可为空，如 session.created）
    run_id UUID,                        -- 所属 Run ID（可为空）
    sequence BIGINT NOT NULL,           -- 在 Session 内的全局顺序号（单调递增）
    event_type VARCHAR(64) NOT NULL,    -- 事件类型：user.message / tool.call 等
    parent_event_id UUID,               -- 父事件 ID（用于关联因果关系）
    payload JSONB NOT NULL,             -- 事件负载（具体内容）
    created_at TIMESTAMPTZ NOT NULL,    -- 事件产生时间
    UNIQUE(session_id, sequence)        -- 同一 Session 内 sequence 唯一
);

CREATE INDEX idx_events_session_sequence
ON events(session_id, sequence);

CREATE INDEX idx_events_run_sequence
ON events(run_id, sequence);

CREATE INDEX idx_events_parent
ON events(parent_event_id);
4.2.5 messages
Message 是专门用于恢复 LLM Conversation History 的投影表。

sql
CREATE TABLE messages (
    id UUID PRIMARY KEY,                -- Message 唯一标识
    session_id UUID NOT NULL,           -- 所属 Session ID
    turn_id UUID,                       -- 所属 Turn ID（可为空）
    run_id UUID,                        -- 所属 Run ID（可为空）
    event_id UUID NOT NULL,             -- 对应的 Event ID（来源事件）
    sequence BIGINT NOT NULL,           -- 在 Session 内的顺序号（用于排序）
    role VARCHAR(32) NOT NULL,          -- 角色：system / user / assistant / tool
    content JSONB NOT NULL,             -- 消息内容（支持多模态）
    tool_call_id TEXT,                  -- 若为 tool 消息，对应的 tool_call ID
    tool_name TEXT,                     -- 若为 tool 消息，对应的工具名称
    is_visible BOOLEAN NOT NULL DEFAULT TRUE, -- 是否对用户可见（默认可见）
    metadata JSONB NOT NULL DEFAULT '{}',     -- 扩展元数据
    created_at TIMESTAMPTZ NOT NULL     -- 创建时间
);

CREATE INDEX idx_messages_session_sequence
ON messages(session_id, sequence);
常见 role：

system

user

assistant

tool

4.3 Phase 1 Event 类型
第一阶段只实现这些：

session.created

turn.started

turn.completed

user.message

run.started

run.completed

llm.request

llm.response

tool.call

tool.result

subagent.started

subagent.completed

assistant.message

error

不需要一开始设计几十种 Event。

4.4 核心写入流程
用户发送 User Message，Runtime 执行：

text
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
LLM 调 Tool：

text
tool.call Event
      ↓
Tool Execute
      ↓
tool.result Event
      ↓
继续 LLM
最终：

text
assistant.message Event
      ↓
Message Projection
      ↓
Turn Complete
4.5 对话恢复
服务重启后：

text
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
因此第一阶段已经满足：

保存用户消息

保存 AI 消息

保存 Tool

保存 Sub Agent

恢复历史

服务重启恢复

多轮对话

4.6 最重要原则
虽然第一阶段主要依赖 messages 读取历史，但 Event 必须同时写入。

也就是说：

Event = Source of Truth

Message = Query Projection

如果以后 Message 表出现问题，可以通过 events 重建 messages：

text
events
   ↓
rebuild
   ↓
messages
第一阶段不用实现自动 Projection Worker，直接在同一个数据库事务中完成即可。

4.7 第一阶段明确“不做”
为了避免过度设计，第一阶段明确禁止为了“以后可能用到”而实现：

❌ Event Bus

❌ Kafka

❌ Event Sourcing Framework

❌ CQRS Framework

❌ Vector Database

❌ Memory System

❌ Checkpoint

❌ Time Travel

❌ Context Compaction

❌ Object Storage

❌ 分布式 Trace

❌ 复杂 Branch Graph

数据库直接使用 PostgreSQL，Runtime 直接使用 Transaction → Event → Message Projection，先把基础闭环跑起来。

4.8 第一阶段验收标准
第一阶段完成后，必须能够完成：

普通对话

text
User → Agent → User → Agent
服务重启恢复

text
Session → 完整恢复
Tool

text
User → Agent → Tool Call → Tool Result → Agent
恢复后：

text
User
Assistant(tool call)
Tool(result)
Assistant
能够正确重新构建 Context。

Sub Agent

text
Main Agent → Sub Agent → Tool → Sub Agent Result → Main Agent
能够从 parent_run_id 找到完整执行关系。

Event

能够根据 Event 的 session_id + sequence 按顺序重新 Replay。

5. Phase 2：完整 Runtime Persistence
5.1 目标
第一阶段稳定以后，再增加：

Branch

Tool Call

LLM Call

Usage

Sub Agent Trace

Prompt Version

这一阶段解决：

“Agent 是怎么执行的？”
而不只是：“Agent 说了什么？”

5.2 Branch
增加：

sql
CREATE TABLE branches (
    id UUID PRIMARY KEY,                -- Branch 唯一标识
    session_id UUID NOT NULL,           -- 所属 Session ID
    parent_branch_id UUID,              -- 父 Branch ID（从哪个分支分叉）
    fork_event_id UUID,                 -- 分叉点对应的 Event ID
    fork_message_id UUID,               -- 分叉点对应的 Message ID
    created_at TIMESTAMPTZ NOT NULL,    -- 创建时间
    metadata JSONB NOT NULL DEFAULT '{}' -- 扩展元数据
);

CREATE INDEX idx_branches_session
ON branches(session_id);
结构：

text
Session
 ├── Branch A
 │    ├── msg1
 │    ├── msg2
 │    └── msg3
 │
 └── Branch B
      └── msg4
Branch B 不复制 A 的历史，通过 parent_branch_id 和 fork_event_id 继承历史。

5.3 Branch History 算法
查询 Branch B 的逻辑：

text
Parent Branch History
        ↓
截止 fork_event
        ↓
+
Branch B Events
        ↓
完整 History
因此：

text
A: 1 2 3 4 5
从 3 fork
B: 1 2 3 6 7
数据库中实际上只新增 6、7，不复制 1、2、3。

5.4 Tool Call
增加独立表：

sql
CREATE TABLE tool_calls (
    id UUID PRIMARY KEY,                -- Tool Call 唯一标识
    event_id UUID NOT NULL,             -- 对应 Event ID（tool.call 事件）
    run_id UUID NOT NULL,               -- 所属 Run ID
    session_id UUID NOT NULL,           -- 所属 Session ID
    tool_name TEXT NOT NULL,            -- 工具名称
    arguments JSONB,                    -- 调用参数
    result JSONB,                       -- 执行结果（小结果直接存，大结果存 artifact_id）
    status VARCHAR(32) NOT NULL,        -- 状态：pending / running / success / failed
    error TEXT,                         -- 错误信息（失败时）
    started_at TIMESTAMPTZ,             -- 开始时间
    completed_at TIMESTAMPTZ,           -- 完成时间
    latency_ms BIGINT,                  -- 耗时（毫秒）
    metadata JSONB NOT NULL DEFAULT '{}' -- 扩展元数据
);

CREATE INDEX idx_tool_calls_run
ON tool_calls(run_id);

CREATE INDEX idx_tool_calls_name
ON tool_calls(tool_name);
Event 负责记录事实，Tool Call 表负责高效查询：

调用了什么 Tool？

参数是什么？

结果是什么？

耗时多少？

成功还是失败？

5.5 LLM Call
增加：

sql
CREATE TABLE llm_calls (
    id UUID PRIMARY KEY,                -- LLM Call 唯一标识
    event_id UUID NOT NULL,             -- 对应 Event ID（llm.request / llm.response）
    run_id UUID NOT NULL,               -- 所属 Run ID
    provider TEXT NOT NULL,             -- 模型提供商（如 openai / anthropic）
    model TEXT NOT NULL,                -- 模型名称
    request_id TEXT,                    -- 请求 ID（用于对账）
    input_tokens INTEGER,               -- 输入 token 数
    output_tokens INTEGER,              -- 输出 token 数
    cached_tokens INTEGER,              -- 缓存命中的 token 数
    total_tokens INTEGER,               -- 总 token 数
    latency_ms BIGINT,                  -- 延迟（毫秒）
    finish_reason TEXT,                 -- 结束原因：stop / length / tool_call 等
    status VARCHAR(32) NOT NULL,        -- 状态：success / failed
    metadata JSONB NOT NULL DEFAULT '{}', -- 扩展元数据
    created_at TIMESTAMPTZ NOT NULL     -- 创建时间
);

CREATE INDEX idx_llm_calls_run
ON llm_calls(run_id);

CREATE INDEX idx_llm_calls_model
ON llm_calls(model);
用于：

Token 统计

模型分析

Cache Hit

延迟分析

成本分析

Debug

5.6 Prompt 不作为 Session 固定字段
System Prompt / Developer Prompt 应该属于 Context Assembly，而不是 session.system_prompt。

因为一次 Session 中可能出现：

LLM #1：System Prompt V1

LLM #2：System Prompt V1 + Memory

LLM #3：System Prompt V2 + Tool Context

因此 Phase 2 开始记录 prompt_version、prompt_hash 即可，暂时不保存完整 Context Snapshot。

6. Phase 3：高级恢复与长上下文
6.1 目标
解决：

长对话

Agent 中断恢复

Context Replay

Context Compaction

Time Travel

Human-in-the-loop

精确 Debug

这一阶段才引入 Checkpoint、Context Snapshot、Compaction。

6.2 Checkpoint
sql
CREATE TABLE checkpoints (
    id UUID PRIMARY KEY,                -- Checkpoint 唯一标识
    session_id UUID NOT NULL,           -- 所属 Session ID
    branch_id UUID NOT NULL,            -- 所属 Branch ID
    run_id UUID,                        -- 所属 Run ID（可为空）
    event_sequence BIGINT NOT NULL,     -- 对应的 Event sequence（恢复点）
    state JSONB NOT NULL,               -- 完整可恢复状态（序列化）
    created_at TIMESTAMPTZ NOT NULL,    -- 创建时间
    metadata JSONB NOT NULL DEFAULT '{}' -- 扩展元数据
);

CREATE INDEX idx_checkpoints_branch_sequence
ON checkpoints(branch_id, event_sequence DESC);
Checkpoint 表示：

“Agent 在这个时间点的完整可恢复状态。”

6.3 Context Snapshot
记录某次 LLM 实际看到的 Context。

sql
CREATE TABLE context_snapshots (
    id UUID PRIMARY KEY,                -- Snapshot 唯一标识
    run_id UUID NOT NULL,               -- 所属 Run ID
    event_id UUID,                      -- 对应 Event ID（llm.request）
    branch_id UUID,                     -- 所属 Branch ID
    prompt_hash TEXT,                   -- Prompt 哈希（用于版本比对）
    token_count INTEGER,                -- 上下文 token 数
    context JSONB,                      -- 实际上下文内容（小型可存 JSON）
    context_ref TEXT,                   -- 大型上下文的引用（如 Object Storage URI）
    created_at TIMESTAMPTZ NOT NULL     -- 创建时间
);

CREATE INDEX idx_context_snapshots_run
ON context_snapshots(run_id);
作用：

text
为什么 Agent 当时这么回答？
        ↓
找到 LLM Call
        ↓
找到 Context Snapshot
        ↓
看到当时实际输入
6.4 Reasoning / Thinking
不要放进 messages，应该属于 Execution Trace。

可以作为 event_type = reasoning，或者 LLM Call 的附加数据。

原则：

Conversation History ≠ Reasoning

默认：

不进入下一次 LLM Context

不作为用户可见消息

是否保存完整内容，由具体模型和隐私策略决定。

6.5 Context Compaction
当历史过长：

text
Message 1 ~ 500
        ↓
Compaction
        ↓
Summary
        +
Message 501 ~ latest
建议增加：

sql
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
以后 Context Builder 不再读取整个历史：

text
Summary
+
Recent Messages
+
Relevant Memory
+
Current Tool State
7. Phase 4：生产级优化
这一阶段才处理大规模生产问题：

Object Storage

Event Partition

异步 Projection

冷热数据

全文搜索

Vector Search

Memory

Artifact

Trace/Observability

数据归档

7.1 大型 Tool Result
不要让数据库保存几十 MB 的 Tool Result。改成：

text
Tool
 ↓
小结果 → PostgreSQL JSONB

大结果
 ↓
Object Storage
 ↓
artifact_id
增加：

sql
artifacts
---------
id                -- Artifact 唯一标识
session_id        -- 所属 Session ID
run_id            -- 所属 Run ID
type              -- 类型：image / file / json 等
storage_uri       -- 存储位置 URI
size              -- 大小（字节）
content_type      -- MIME 类型
checksum          -- 校验和
created_at        -- 创建时间
metadata          -- 扩展元数据
Message / Tool Call 只保存 artifact_id。

8. 推荐最终数据库结构
最终完整版本：

text
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
可以理解为：

text
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
9. 最终数据职责
一定保持以下边界：

数据	职责
Event	发生了什么？
Message	对话是什么？
Run	Agent 怎么执行？
Tool Call	Tool 怎么调用？
LLM Call	模型怎么调用？
Context Snapshot	模型当时看到了什么？
Checkpoint	Agent 怎么恢复？
Branch	这条历史从哪里分叉？
Artifact	大型结果放在哪里？
10. Context Builder
无论哪个阶段，Context Builder 都应该作为独立模块。

text
ContextBuilder
      │
      ├── System Prompt
      ├── Conversation History
      ├── Tool Definitions
      ├── Memory
      ├── Compaction Summary
      ├── Runtime State
      └── Current User Input
             │
             ▼
        LLM Context
不要让 Agent 代码直接 SELECT * FROM messages。Context Builder 才是唯一负责：

“哪些历史应该进入模型 Context”

的组件。

11. Agent 执行时序
最终一次正常请求：

text
User
 │
 ▼
Session
 │
 ▼
Turn
 │
 ▼
Run
 │
 ├── append user.message
 │
 ├── ContextBuilder
 │       │
 │       ├── System Prompt
 │       ├── History
 │       └── Memory
 │
 │       ▼
 │      LLM
 │
 ├── Tool Call
 │      │
 │      ▼
 │   Tool Result
 │
 ├── SubAgent
 │      │
 │      ▼
 │   Child Run
 │
 ├── LLM
 │
 └── Assistant Message
         │
         ▼
    Turn Completed
每个关键动作同时产生 Event。

12. 一致性原则
第一阶段：Event + Message 在同一个 PostgreSQL Transaction 中写入。

例如：

sql
BEGIN
INSERT event(user.message)
INSERT message(user)
COMMIT
Tool：

sql
BEGIN
INSERT tool.call
执行 Tool
INSERT tool.result
COMMIT
如果未来 Tool 执行时间过长，则改成：

text
event append
    ↓
async execution
    ↓
result event
不要为了追求架构“高级”而在第一阶段引入复杂消息队列。

13. 读取策略
场景	查询方式
普通聊天	messages WHERE branch_id/session_id ORDER BY sequence
执行 Debug	events WHERE run_id ORDER BY sequence
Tool 分析	tool_calls WHERE tool_name / run_id
LLM 分析	llm_calls WHERE run_id / model
恢复	checkpoint → events since checkpoint
Branch	parent history until fork + branch events
14. 三阶段 Context 恢复策略
Phase 1
text
messages → Context
简单直接。

Phase 2
text
messages + Tool / Run 信息 → Context
开始支持复杂 Agent。

Phase 3+
text
Checkpoint + Compaction + Recent Messages + Memory + Runtime State → Context
支持长时间运行 Agent。

15. 实现优先级
严格按照以下顺序：

text
Phase 1
├── Session
├── Turn
├── Run
├── Event
├── Message
├── Conversation Restore
└── Tool / SubAgent 基础记录
        │
        ▼
Phase 2
├── Branch
├── Tool Call
├── LLM Call
├── Token Usage
├── Prompt Version
└── Execution Trace
        │
        ▼
Phase 3
├── Checkpoint
├── Context Snapshot
├── Compaction
├── Resume
├── Time Travel
└── Human-in-the-loop
        │
        ▼
Phase 4
├── Artifact Storage
├── Async Projection
├── Event Partition
├── Search
├── Memory
├── Cold Storage
└── Production Observability
16. 最终架构原则
整个 Persistence 系统最终遵循：

text
                    Event
                      │
              ┌───────┼────────┐
              ▼       ▼        ▼
          Message    Run    Checkpoint
              │       │        │
              ▼       ▼        ▼
          Context   Trace    Resume
其中：

Event 是事实。

Message 是对话历史的查询视图。

Run 是 Agent 执行视图。

Context 是模型输入视图。

Checkpoint 是恢复视图。

Branch 是历史分叉机制。

最终实现目标不是“把聊天记录存进数据库”，而是：

让 Runtime 能够低成本地保存、查询、恢复、分叉和解释一次 Agent 执行。

但这些能力不需要第一天全部实现。第一阶段只需要建立正确的五个核心对象：

text
Session → Turn → Run → Event → Message
只要这条数据链设计正确，后面的 Branch、Checkpoint、Context Snapshot、Compaction、Memory、Replay、Time Travel、Observability 都可以在不推翻基础模型的情况下逐步增加。

实施建议
这版文档可以直接作为 Persistence 模块的实施基线。尤其是第一阶段，不要被“完整 Event Sourcing”吓住：PostgreSQL + 5 张核心表 + Event/Message 双写事务 已经足够把 Agent Runtime 的核心闭环跑起来。