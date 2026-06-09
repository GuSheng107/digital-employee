# WeCom Bot Agent 记忆系统说明文档

## 1. 系统概述

本项目实现了一套 **Agent-first + JSON 架构** 的智能记忆管理系统，用于在 AI Agent 对话过程中持久化存储和检索用户偏好、项目约束、工作决策等重要信息。当前实现以 `.memory/*.json`、`.memory/timeline/*.json`、`.memory/documents/*.json` 为唯一记忆存储模型，不再使用 Markdown 记忆文件。

### 1.1 Agent-first 设计理念

系统的核心设计原则是：**所有智能决策由 AI Agent 完成，算法只做机械工作**。

| 层次 | 职责 | 示例 |
|------|------|------|
| **Agent（智能层）** | 生成速查词、分类索引、审查质量、修复冲突、复盘收敛、提升归类 | speed_lookup 生成、content_type 判定、promote 决策 |
| **算法（机械层）** | 文件 I/O、目录锁、原子写入、JSON 序列化、Token 估算、评分排序 | `_write_text_atomic`、`_acquire_dir_lock`、`score_memory_items` |

这种分工确保：
- Agent 负责需要语义理解的任务（如判断记忆属于哪个分类）
- 算法负责确定性操作（如文件读写、并发控制），保证数据一致性
- JSON 文件本身就是结构化数据，自包含所有检索信息，无需额外索引层

### 1.2 核心特性

| 特性 | 说明 |
|------|------|
| JSON 存储格式 | 所有记忆文件以 JSON 存储，每条记忆是结构化的 MemoryItem 对象 |
| Agent-first 架构 | 速查词、分类、审查、复盘收敛、提升等智能决策由 Agent 完成 |
| 速查词（speed_lookup） | Agent 生成管道分隔关键词，评分权重最高（精确匹配 +10.0） |
| 多源输入支持 | 支持从聊天对话和文档两种来源提取记忆 |
| Token 预算控制 | 根据模式（compact/default/expanded）限制记忆的 Token 消耗 |
| 优先级体系 | 每条记忆按文件类别自动分配 priority 权重（2.0-10.0） |
| 原子写入 + 目录锁 | 文件写入通过临时文件 + `os.replace` 实现原子性，目录锁防止并发冲突 |
| 变更追踪 | 所有写入操作记录到 changelog.json，保留最近 500 条 |
| 复盘收敛（compress / merge） | Agent 在审核中合并、缩短、归档重复、冗余、碎片化或低价值记忆 |
| 提升（promote） | Agent 将收件箱记忆提升到正确的分类文件 |
| 分层去重 | 按“显式记忆 > 文档记忆 > 会话记忆”清理和预防重复 |
| 审查写入 | reviewer 默认只读；只有调用方显式选择 `patch` 模式才会自动应用生成的补丁，显式记忆删除补丁会被底层保护跳过 |
| 运行时强约束索引 | 用户强约束指令（"以后默认..."、"不要..."等）权重 12.0，高于显式记忆 |
| 来源标注 | Memory Pack 和回答只标注文档显示名或管理员配置内容，会话来源不外显 |
| 数据概览 | 数据管理页展示上传文档、已转换消息、记忆更新和文档提取完成次数 |
| 任务完成通知 | 记忆相关任务可配置通知 Bot，任务完成后通过企微发送结果摘要 |
| 结构化输出边界 | memory-creator / memory-reviewer 使用 `JsonOutputParser` + Pydantic schema 约束结果，普通 Agent 配置不需要常驻 JSON 输出模式 |
| 反馈闭环 | 企业微信消息反馈（满意/不满意）自动入库，驱动记忆质量持续改进 |

## 2. 记忆存储格式

### 2.1 MemoryItem 结构

每条记忆是一个 `MemoryItem` 对象，定义在 [memory_schema.py](app/memory_schema.py)：

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "content": "聚水潭推送库存到店家但库存没有变动: erp设置了不管控库存",
  "content_type": "problem_solution",
  "speed_lookup": "聚水潭|库存|推送|erp|不管控",
  "retrieval": {
    "keywords": ["聚水潭", "库存", "erp"],
    "boost": 1.0,
    "tags": ["erp", "inventory"],
    "terms": [],
    "aliases": [],
    "entities": ["聚水潭"]
  },
  "source": "chat",
  "source_id": "chat-20260501",
  "created_at": "2026-05-01T10:30:00",
  "updated_at": "2026-05-01T10:30:00",
  "priority": 10.0
}
```

#### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | str | UUID，全局唯一标识 |
| `content` | str | 记忆内容，支持多行文本 |
| `content_type` | ContentType | 内容类型枚举（见下文） |
| `speed_lookup` | str | Agent 生成的速查词，管道符 `\|` 分隔 |
| `retrieval` | RetrievalHints | 检索提示（关键词、实体、标签等） |
| `source` | Literal | 来源类型：`chat` / `document` / `explicit` / `manual` |
| `source_id` | str | 来源标识（如文档 ID、会话 ID） |
| `created_at` | str | 创建时间（ISO 8601） |
| `updated_at` | str | 更新时间（ISO 8601） |
| `priority` | float | 优先级权重，由 memory-creator 按文件类别自动分配 |

### 2.2 content_type 枚举

| 值 | 说明 | 典型场景 |
|----|------|---------|
| `problem_solution` | 问题-解决方案 | "库存没有变动: erp设置了不管控库存" |
| `qa` | 问答对 | "Q: 部署方式? A: Docker Compose" |
| `term_definition` | 术语定义 | "推送: 指从店家推到聚水潭" |
| `operation_guide` | 操作指引 | "重启服务: systemctl restart app" |
| `configuration` | 配置信息 | "数据库端口: 5432" |
| `process` | 流程步骤 | "发布流程: 1.测试 2.审核 3.上线" |
| `rule` | 规则约束 | "所有接口必须使用 RESTful 风格" |
| `fact` | 事实陈述 | "项目使用 FastAPI 框架" |
| `preference` | 用户偏好 | "回复使用简体中文" |

### 2.3 RetrievalHints 结构

```json
{
  "keywords": ["关键词1", "关键词2"],
  "boost": 1.0,
  "tags": ["tag1", "tag2"],
  "terms": ["术语1"],
  "aliases": ["别名1"],
  "entities": ["实体1"]
}
```

| 字段 | 说明 | 评分权重 |
|------|------|---------|
| `keywords` | 关键词（中英文技术术语、名词） | 精确匹配 +5.0，包含 +2.0 |
| `entities` | 命名实体（公司、人名、地点） | 精确匹配 +5.0，包含 +2.0 |
| `terms` | 领域术语和角色 | 精确匹配 +5.0，包含 +2.0 |
| `tags` | 内容标签 | 精确匹配 +5.0，包含 +2.0 |
| `aliases` | 别名 | 精确匹配 +5.0，包含 +2.0 |
| `boost` | 权重提升系数 | 乘以最终分数 |

### 2.4 priority 权重体系

memory-creator 在创建记忆时根据目标文件类别自动分配 priority：

| 文件类别 | priority | 说明 |
|----------|----------|------|
| explicit | 10.0 | 显式记忆，优先级最高 |
| work | 8.0 | 工作约束和决策 |
| profile | 6.0 | 用户长期偏好 |
| document | 5.0 | 文档记忆 |
| timeline | 4.0 | 时间线记忆 |
| rules | 3.0 | 使用规则 |
| inbox | 2.0 | 待审核项 |
| changelog | 1.0 | 变更日志 |

前端管理页面显示优先级标签：≥10 紧急、≥6 高、≥3 中、<3 低。

### 2.5 文件级数据结构

#### MemoryFile（主文件）

```json
{
  "version": 1,
  "file_key": "explicit",
  "updated_at": "2026-05-14T10:30:00",
  "items": [MemoryItem, MemoryItem, ...]
}
```

#### ChangelogFile（变更日志）

```json
{
  "version": 1,
  "entries": [
    {
      "id": "uuid",
      "action": "add",
      "target_file": "explicit",
      "item_id": "item-uuid",
      "item_content_preview": "记忆内容预览（前100字）",
      "reason": "",
      "created_at": "2026-05-14T10:30:00"
    }
  ]
}
```

`action` 枚举值：`add` / `update` / `delete` / `compress` / `promote` / `merge`

#### TimelineFile（时间线）

```json
{
  "version": 1,
  "month": "2026-05",
  "updated_at": "2026-05-14T10:30:00",
  "items": [MemoryItem, ...]
}
```

#### DocumentMemoryFile（文档记忆）

```json
{
  "version": 1,
  "source_id": "doc-api-spec",
  "source_filename": "API设计规范.pdf",
  "updated_at": "2026-05-14T10:30:00",
  "items": [MemoryItem, ...]
}
```

## 3. 记忆文件结构

### 3.1 目录结构

```
.memory/
├── explicit.json           # 显式记忆（用户明确要求记住的内容）
├── profile.json            # 用户画像（长期偏好和沟通习惯）
├── work.json               # 工作笔记（目标、约束、决策）
├── inbox.json              # 收件箱（不确定或冲突的候选项）
├── rules.json              # 记忆使用规则
├── changelog.json          # 变更日志（系统自动维护，保留最近500条）
├── documents/              # 文档记忆目录
│   └── {source_id}.json    # 单个文档的记忆摘要
├── timeline/               # 时间线目录
│   └── YYYY-MM.json        # 按月份聚合的记忆
├── reviews/                # 审核报告目录
│   └── memory_files_review_{timestamp}.md
└── .runtime/               # 运行时数据
    └── session_queries/    # 会话强约束指令索引
        └── {chat_id}.json
```

### 3.2 文件优先级

```
优先级从高到低：
┌─────────────────────────────────────────────────────────┐
│ 0. 运行时强约束索引  (权重 12.0) - 当前会话的强约束指令    │
│ 1. explicit.json     (权重 10.0) - 显式记忆，优先级最高   │
│ 2. work.json          (权重 8.0)  - 工作约束和决策        │
│ 3. profile.json       (权重 6.0)  - 用户长期偏好          │
│ 4. documents/*.json   (权重 5.0)  - 文档记忆（相关时）    │
│ 5. timeline/*.json    (权重 4.0)  - 时间线记忆            │
│ 6. rules.json         (权重 3.0)  - 使用规则              │
│ 7. inbox.json         (权重 2.0)  - 待审核项（冲突时）    │
│ 8. changelog.json     (权重 1.0)  - 变更日志              │
└─────────────────────────────────────────────────────────┘
```

### 3.3 文件职责与来源限制

| 文件 | 权重 | 职责 | 来源限制 |
|:-----|:---:|:-----|:---------|
| **explicit.json** | 10.0 | 用户明确要求记住的内容 | 仅 chat / explicit |
| **work.json** | 8.0 | 工作目标、约束、决策、架构笔记 | chat + document |
| **profile.json** | 6.0 | 稳定的长期用户偏好与沟通习惯 | 仅 chat |
| **documents/{id}.json** | 5.0 | 单个文档提炼的结构化摘要 | 仅 document |
| **timeline/YYYY-MM.json** | 4.0 | 按月聚合的聊天与文档事件 | chat + document |
| **rules.json** | 3.0 | 记忆使用规则 | 自动生成 |
| **inbox.json** | 2.0 | 不确定或冲突的记忆候选项 | 待审核 |
| **changelog.json** | 1.0 | 所有写入操作的变更日志 | 仅系统 |

### 3.4 硬性约束

| 规则 | 说明 |
|:-----|:-----|
| ❌ 文档来源 **禁止** 写入 `explicit.json` / `profile.json` | 只能从 chat 输入 |
| ❌ `changelog.json` 不可编辑 | 仅系统写入 |
| ✅ 冲突记忆放入 `inbox.json` | 待 Agent 审核提升 |

## 4. 三大模块

### 4.1 memory-creator（记忆创建）

将对话问答或文档文本转化为结构化的 JSON 记忆文件，写入 `.memory/` 目录。

#### 三条提取管道

| 管道 | 触发方式 | 目标文件 |
|:-----|:---------|:---------|
| **chat_summary_chain** | 自动/会话总结 | explicit.json, profile.json, work.json, inbox.json, timeline/ |
| **explicit_memory_chain** | `/记忆生成` 指令 | explicit.json, profile.json, work.json, timeline/ |
| **document_chunk_chain** | 文档上传 | documents/{id}.json, work.json |

#### 处理流程

```
┌──────────────┐     ┌─────────────────────────┐     ┌──────────────┐
│ 用户对话/文档  │ ──▶ │    标准化输入            │ ──▶ │  选择管道     │
└──────────────┘     └─────────────────────────┘     └──────┬───────┘
                                                            │
                    ┌───────────────────────────────────────┘
                    ▼
        ┌───────────────────────────┐
        │   chat_summary_chain      │  ←── 聊天对话管道
        │   explicit_memory_chain   │  ←── 显式记忆管道
        │   document_chunk_chain    │  ←── 文档处理管道
        └───────────┬───────────────┘
                    │
                    ▼
        ┌───────────────────────────┐
        │     Memory Promoter        │
        │  (记忆分类和优先级分配)      │
        │  → MemoryCandidate         │
        │  → target_file 决策        │
        │  → priority 按类别分配      │
        └───────────┬───────────────┘
                    │
                    ▼
        ┌───────────────────────────┐
        │     JsonWriter             │
        │  - 去重（Jaccard 相似度）   │
        │  - 跨文件去重              │
        │  - 溢出转入 inbox          │
        │  - 写入 changelog          │
        │  - 原子写入 JSON           │
        └───────────────────────────┘
```

#### Agent 强制返回 JSON Schema

三条 chain 均通过 LangChain 的 `JsonOutputParser` + Pydantic schema 强制 Agent 返回规定格式的 JSON，确保输出结构可预测：

- **chat_summary_chain** → `ChatSummary` schema
- **explicit_memory_chain** → `ExplicitMemory` schema
- **document_chunk_chain** → `DocumentSummary` schema

每条提取结果包含 `content`、`content_type`、`speed_lookup`、`retrieval` 字段，由 Agent 在提取时一并生成。

这条结构化输出约束只属于记忆创建链路。普通 Agent 对话、Bot 任务和工具调用不依赖全局 `response_format={"type":"json_object"}` 配置；如果模型配置中长期保留该字段，普通自然语言回答可能被错误地约束为 JSON。

#### Token Usage 追踪

三条 chain 均通过拆分 LCEL chain 为 `prompt.invoke() → llm.invoke() → parser.invoke()` 三步调用，从 LLM response 中提取 `token_usage`（input_tokens / output_tokens / total_tokens），随 `ConsolidationResult` 一路返回到 `task_runtime.py`，记录到数据库 `token_usage` 表。

#### Promote 分类规则

**Chat 输入：**

| 提取字段 | 目标文件 | 置信度 | priority |
|----------|---------|--------|----------|
| `explicit_memories` | explicit.json | 1.0 | 10.0 |
| `profile_candidates` | profile.json | 0.7-0.8 | 6.0 |
| `business_facts` + `decisions` | work.json | 0.9 | 8.0 |
| `open_questions` | inbox.json | 0.6 | 2.0 |
| `inbox_items` | inbox.json | 0.5 | 2.0 |
| `timeline_items` | timeline/YYYY-MM.json | 0.9 | 4.0 |

**Document 输入：**

| 提取字段 | 目标文件 | 置信度 | priority |
|----------|---------|--------|----------|
| `key_points` / `business_facts` / `rules_or_policies` 等 | documents/{source_id}.json | 0.9 | 5.0 |
| `project_memory_candidates` | work.json | 0.8 | 8.0 |
| `document_summary` | timeline/YYYY-MM.json | 0.9 | 4.0 |
| `fallback_raw_text` | inbox.json | 0.1 | 2.0 |

**Explicit 输入：**

| 提取字段 | 目标文件 | 置信度 | priority |
|----------|---------|--------|----------|
| `explicit_memories` | explicit.json | 1.0 | 10.0 |
| `profile_candidates` | profile.json | 0.9 | 6.0 |
| `work_facts` | work.json | 0.9 | 8.0 |
| `timeline_items` | timeline/YYYY-MM.json | 0.9 | 4.0 |

#### 去重机制

JsonWriter 使用 Jaccard 相似度（bigram）进行去重，阈值 0.7：
- 文件内去重：新条目与同文件已有条目比较
- 分层跨源去重：显式记忆优先于文档记忆，文档记忆优先于会话记忆；会话写入时会跳过已存在于显式/文档中的重复内容
- `mode=update` 会先按 `source_id` 清理同源旧条目，再写入新文档记忆，避免重复处理同一文档时残留旧内容
- 记忆文件允许持续增长；写入阶段不再按固定条目数截断，条目收敛交由定期审核复盘处理。

### 4.2 memory-reader（记忆读取）

读取 `.memory/` 目录中的 JSON 记忆文件，根据当前用户请求选择最相关的记忆，构建聚焦但更充分的 Memory Pack 注入 Agent 上下文。

#### 处理流程

```
┌─────────────────┐
│ 当前用户消息      │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│  JsonLoader 加载文件      │
│  - explicit.json         │
│  - profile.json          │
│  - work.json             │
│  - rules.json            │
│  - inbox.json            │
│  - timeline/*.json       │
│  - documents/*.json      │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│  build_runtime_sections  │  ←── 运行时强约束指令（权重 12.0）
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│  json_scorer 评分排序     │
│  score = speed_lookup    │
│    精确匹配 +10.0         │
│    包含匹配 +5.0          │
│  + retrieval 匹配        │
│    精确匹配 +5.0          │
│    包含匹配 +2.0          │
│  + content 包含 +3.0     │
│  + char_overlap 匹配     │
│  + priority × 0.1        │
│  × file_weight           │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│  Token 预算裁剪           │
│  compact: 1500 tokens    │
│  default: 4000 tokens    │
│  expanded: 8000 tokens   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│    生成 Memory Pack       │
│    + file_stats 统计      │
└─────────────────────────┘
```

#### 评分算法详解

`score_memory_items` 对每条 MemoryItem 计算相关性分数：

```
score = speed_lookup_score + retrieval_score + content_score + char_overlap_score + priority_score
score ×= file_weight
```

reader 会先从用户问题中抽取有效查询词，过滤“哪里、怎么、查询、查看”等泛词。中文字符重叠只在已经命中至少一个语义查询词后作为轻量加分；当查询词达到 3 个及以上时，单条记忆至少需要命中 2 个查询词，否则分数归零。这可以降低仅因“聚水潭”等常见词或中文字符重叠造成的误召回。

| 评分维度 | 计算方式 | 权重 |
|----------|---------|------|
| **speed_lookup** | 查询词与速查词精确匹配 +10.0，包含 +5.0 | **最高** |
| retrieval (keywords/entities/terms/tags/aliases) | 精确匹配 +5.0，包含 +2.0 | 中 |
| content | 查询词出现在内容中 +3.0 | 低 |
| char_overlap | 中文字符级重叠（>50% 时 +2.0 × ratio） | 辅助 |
| priority | item.priority × 0.1 | 辅助 |
| file_weight | 按文件优先级乘以权重 | 缩放 |

Memory Pack 按可读来源输出分组标题。显式记忆显示为 `[管理员配置内容]` 并在条目上标注 `来源：管理员配置内容`；文档记忆优先显示文档显示名，例如 `[文档《API设计规范.pdf》]` 和 `来源：文档《API设计规范.pdf》`。会话记忆、工作笔记、用户画像、时间线、收件箱默认不展示来源。输出仍携带 `selected_files`、`omitted_files`、`confidence`、`reason`、`needs_more_memory` 和 token 预算估算，供 `memory_usage_audits` 记录。相关记忆因总预算或分区预算未纳入时，reader 会把 `needs_more_memory` 置为 `true` 并在 `reason` 中记录预算截断数量。

#### Token 预算分配

记忆包读取采用**弹性预算扩展机制**：先以基础预算（compact/default/expanded）尝试选取，若文档记忆因预算限制被截断，且配置了扩展预算（`token_budget_expanded`），则自动扩展到更大的预算重新选取所有记忆。

| 模式 | 总预算 | rules | explicit | work | profile | timeline | document | inbox |
|------|--------|-------|----------|------|---------|----------|----------|-------|
| **compact** | 1500 | 60 | 300 | 360 | 150 | 120 | 360 | 150 |
| **default** | 4000 | 120 | 720 | 960 | 320 | 400 | 1200 | 280 |
| **expanded** | 8000 | 200 | 960 | 1600 | 560 | 800 | 3200 | 680 |

#### 弹性预算扩展流程

1. **第一轮选取**：使用 `token_budget`（或模式默认值）作为总预算，按优先级顺序（explicit > work > profile > rules > timeline > documents > inbox > changelog）选取记忆条目
2. **检测截断**：若文档记忆有匹配条目但因预算限制被截断（`doc_items_omitted_by_budget = true`），且配置了 `token_budget_expanded > token_budget`
3. **第二轮选取**：清空已选内容，使用 `token_budget_expanded` 作为总预算重新进行完整选取

#### 使用场景建议

- **compact 模式**：快速响应、简单查询
- **default 模式**：常规对话、项目咨询
- **expanded 模式**：文档分析、复杂架构讨论

### 4.3 memory-reviewer（记忆审核）

审核 `.memory/` 中的 JSON 记忆文件和 Memory Pack 的质量，检测重复、冲突、过期、放置错误、冗长/重复、碎片化等问题，并支持必要的复盘收敛和提升操作。默认执行只读审查；只有调用方显式选择 `patch` 模式才允许写入记忆文件。

#### 审核类型

| 类型 | 说明 |
|:-----|:-----|
| `memory_files` | 审核记忆文件质量，生成修复补丁 |
| `memory_pack` | 审核 Memory Pack 是否遗漏重要记忆 |
| `user_feedback` | 将用户纠正转化为修复补丁 |
| `conversation_usage` | 基于审计样本分析记忆使用效率 |
| `scheduled_cleanup` | 复盘时间线、合并重复、收敛冗余或碎片化内容并建议清理 |
| `feedback_review` | 基于用户反馈（满意/不满意）审查记忆质量，识别需要补充或修正的记忆 |

#### 处理流程

```
┌─────────────────────────────────────────┐
│           审核类型选择                    │
├──────────────┬──────────────┬───────────┤
│ memory_files │ memory_pack   │ user_     │
│ (文件审核)   │ (记忆包审核)  │ feedback  │
│              │              │ (用户纠正) │
└──────┬───────┴──────┬───────┴─────┬─────┘
       │              │             │
       ▼              ▼             ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ 加载 JSON    │ │ 检查缺失项   │ │ 解析反馈     │
│ 确定性检查   │ │ 检查超限     │ │ 定位受影响项 │
│ 可选LLM审核 │ │ 检查冲突警告 │ │ 生成修复补丁 │
└──────┬──────┘ └──────┬─────┘ └──────┬──────┘
       │               │              │
       ▼               ▼              ▼
┌─────────────────────────────────────────┐
│           生成审核报告                    │
│  - issues: 发现的问题                    │
│  - conflicts: 冲突列表                   │
│  - recommended_patches: 修复建议         │
│  - quality_score: 质量评分 (0-100)       │
│  - safe_to_apply: 是否可安全应用         │
│  - boundary_metrics: 复盘指标            │
│  - patches_applied: 已应用的补丁         │
└─────────────────────────────────────────┘
```

#### 审核报告

默认情况下审核会生成报告写入 `.memory/reviews/` 目录；传入 `--skip-report` 时不写报告、不应用补丁，适合健康检查和自动化验证。报告包含：

- **Quality Score**：100 分制，high 扣 15 分、medium 扣 8 分、low 扣 3 分
- **Issues**：发现的问题列表（duplicate / conflict / outdated / wrong_promotion / excessive_length / missing_memory / low_value / token_over_budget / chinese_not_preserved / bad_speed_lookup / fragmented_memory）
- **Review Boundary Metrics**：平均 token 使用率、遗漏率、无关率、文件条目数；文件条目数只作为观察指标，不按数量自动触发压缩。
- **Needs More Memory Signals**：来自 reader 或审计样本的 `needs_more_memory` 会优先进入遗漏和预算复盘，区分“记忆库缺失”和“相关记忆被预算截断”。
- **Applied Patches**：`patch` 模式写入时输出修复内容和原因
- **Feedback Insights**：基于用户反馈的改进建议（如高频问题未覆盖、记忆内容不准确等）

#### 复盘收敛（compress）

记忆允许持续增长，条目数量本身不是缺陷。`compress_chain` 仅在审核发现重复、冗余、碎片化、低价值或可安全缩短的内容时输出收敛建议：

| 策略 | 说明 |
|------|------|
| **merge** | 合并重叠信息的条目，新条目的 speed_lookup 包含所有源条目的关键词 |
| **shorten** | 缩减冗长或重复内容，保留关键信息 |
| **archive** | 将不再适合活跃文件但仍有历史价值的低价值条目移至 timeline |
| **delete** | 删除真正的重复条目（仅当 merge 不适用时） |

**关键规则：**
- 永远不丢失独特信息，有疑问则保留
- 条目数量和创建时间只作为观察信息，不作为压缩、归档或删除触发条件
- 合并时新 content_type 取源条目中最具体的类型
- 合并时合并所有 speed_lookup 关键词（去重，最多 8 个）
- 合并时合并所有 retrieval hints

#### 提升（promote）

`promote_chain` 由 Agent 审查 inbox 中的条目，决定其正确归属：

| 目标文件 | 优先级 | 适用内容 |
|---------|--------|---------|
| explicit | 10.0 | 直接指令、规则、用户要求记住的 Q&A |
| work | 8.0 | 业务事实、技术决策、项目知识 |
| profile | 6.0 | 用户偏好、习惯、个人特征 |
| inbox | 2.0 | 未解决、待审核的条目 |
| timeline | 4.0 | 时间相关事件、归档条目 |

**提升规则：**
- 每条记忆必须分配到恰好一个目标文件
- 根据重要性和被查询可能性设置优先级
- 如当前 content_type 不正确则更新
- 保留原有 speed_lookup 和 retrieval，除非需要改进

#### 审核模式

| 模式 | 说明 |
|------|------|
| `review` | 仅生成报告和补丁建议，不修改文件 |
| `dry_run` | 模拟应用补丁，输出预览但不实际写入 |
| `patch` | 自动应用生成的补丁；底层补丁应用器会跳过删除 `explicit` 的补丁 |

#### 审查运行机制

| 场景 | 命令要点 | 写入行为 |
|------|----------|----------|
| 健康检查 | `--mode review --skip-report` | 不写报告、不写记忆文件 |
| 常规审查 | `--mode review` | 写审核报告，不写记忆文件 |
| 补丁预演 | `--mode dry_run` | 写审核报告，预演补丁，不写记忆文件 |
| 自动修复 | `--mode patch` | 应用生成的补丁；显式记忆删除被保护跳过 |

```powershell
.\.venv\Scripts\python.exe .skills\system\memory-reviewer\script\review.py --review-type memory_files --memory-dir .memory --mode review --skip-report
.\.venv\Scripts\python.exe .skills\system\memory-reviewer\script\review.py --review-type memory_files --memory-dir .memory --mode dry_run
.\.venv\Scripts\python.exe .skills\system\memory-reviewer\script\review.py --review-type memory_files --memory-dir .memory --mode patch
```

## 5. 速查词（speed_lookup）

### 5.1 设计理念

速查词是 Agent-first 架构的核心创新。每条记忆在创建时，由 Agent 生成一组管道符 `|` 分隔的关键词，存储在 `speed_lookup` 字段中。在检索评分中，speed_lookup 的权重最高。

### 5.2 生成规则

- 由 Agent 在记忆提取时生成（三条 chain 的 prompt 均要求输出 speed_lookup）
- 使用管道符 `|` 分隔关键词
- 包含中英文关键词、缩写、别名
- 建议不超过 8 个关键词
- 每个关键词须为语义完整的词（2-6 字符中文，任意长度英文）
- 禁止包含虚词（的、了、是、在、有、可能、如果、需要等）
- 示例：`"聚水潭|库存|推送|erp|不管控"`

### 5.3 评分权重

| 匹配方式 | speed_lookup | retrieval | content |
|----------|:-----------:|:---------:|:-------:|
| 精确匹配 | **+10.0** | +5.0 | — |
| 包含匹配 | **+5.0** | +2.0 | +3.0 |

speed_lookup 的精确匹配权重是 content 包含匹配的 3.3 倍，确保速查词命中的记忆排在最前面。

## 6. 运行时强约束指令索引

### 6.1 设计目的

用户在对话中发出的强约束指令（如"以后默认用中文回复"、"不要改我的配置"等），需要比显式记忆更高的权重，确保 Agent 始终遵守。

### 6.2 匹配模式

```python
_CONSTRAINT_PATTERNS = [
    r"^以后(?:默认|都|请|要|应该)?[\s,，]*",    # 以后默认...
    r"^(?:不要|别|禁止|严禁|不许)[\s,，]*",      # 不要... / 别...
    r"^(?:必须|务必|只能)[\s,，]*",              # 必须... / 务必...
    r"^(?:记住|记住了|记一下|记下来)[\s,，]*",    # 记住...
    r"^(?:纠正|纠正一下|请纠正|你错了|不对)[\s,，]*",  # 纠正...
    r"^(?:不要改|别改|不许改|禁止改)[\s,，]*",   # 不要改...
]
```

### 6.3 存储与权重

- 存储路径：`.memory/.runtime/session_queries/{chat_id}.json`
- 每个会话最多 50 条
- 权重：12.0（高于 explicit 的 10.0）
- 自动去重：精确匹配 > 子串包含 > Jaccard 字符集相似度 ≥ 0.75

## 7. 记忆生命周期

```
┌──────────┐    ┌──────────────────┐    ┌──────────────────┐
│ 用户对话  │───▶│  memory-creator  │───▶│   .memory/       │
│ 文档输入  │    │     📝 创建       │    │   JSON 写入      │
└──────────┘    └──────────────────┘    └────────┬─────────┘
                                                  │
                         ┌────────────────────────┘
                         ▼
                ┌──────────────────┐
                │   inbox.json     │  ←── 低置信度/冲突记忆
                │   (收件箱)        │
                └────────┬─────────┘
                         │
                         ▼  memory-reviewer promote
                ┌──────────────────┐
                │   提升 (promote)  │  ←── Agent 决定正确归属
                └────────┬─────────┘
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
     ┌──────────────┐ ┌────────┐ ┌────────┐
     │explicit.json │ │work.   │ │profile.│
     │ (显式记忆)    │ │json    │ │json    │
     └──────┬───────┘ └───┬────┘ └────────┘
            │              │
            ▼              ▼
     ┌──────────────────────────┐
     │  复盘收敛 (review)        │  ←── 定期审核/必要时触发
     │  merge / shorten /       │
     │  archive / delete        │
     └──────────┬───────────────┘
                │
                ▼
     ┌──────────────────┐
     │ timeline/         │  ←── archive 归档目标
     │ YYYY-MM.json      │
     └──────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      反馈闭环（Feedback Loop）                │
├─────────────────────────────────────────────────────────────┤
│  企业微信用户反馈（👍/👎）                                      │
│       │                                                     │
│       ▼                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ message_      │───▶│ feedback_    │───▶│ memory-      │  │
│  │ feedbacks 表  │    │ alert_log 表 │    │ reviewer     │  │
│  │ (存储反馈)    │    │ (告警记录)   │    │ (质量审查)   │  │
│  └──────────────┘    └──────────────┘    └──────┬───────┘  │
│                                                  │          │
│       ┌──────────────────────────────────────────┘          │
│       ▼                                                     │
│  ┌──────────────┐                                          │
│  │ memory-creator│ ◀── 识别 gaps，补充/修正记忆              │
│  │ (记忆更新)    │                                          │
│  └──────────────┘                                          │
└─────────────────────────────────────────────────────────────┘
```

### 生命周期阶段

1. **创建**：memory-creator 从 chat/document 提取记忆，Agent 生成 speed_lookup、content_type、retrieval、priority
2. **收件箱**：低置信度或冲突记忆进入 inbox.json，等待审核
3. **提升**：memory-reviewer 的 promote_chain 将 inbox 条目提升到正确分类
4. **显式记忆**：高置信度记忆直接写入目标文件
5. **复盘收敛/归档**：定期审核发现重复、冗余、碎片化、低价值或可安全缩短内容时，compress_chain 合并、缩短或归档到 timeline
6. **反馈闭环**：用户反馈（满意/不满意）自动入库，驱动记忆质量持续改进
   - `useful` 反馈：确认记忆有效，可作为正面参考优化召回策略
   - `useless` 反馈：标记为 `needs_more_memory`，触发 memory-reviewer 审查，识别知识缺口并补充记忆

## 8. 定时任务集成

### 8.1 记忆相关任务

| 任务 | handler_name | 触发方式 | 完成通知 |
|:-----|:-------------|:---------|:---------|
| 记忆更新 | `memory_update` | 周期性 / 手动 | 可选通知 Bot |
| 文档记忆提取 | `document_memory_extraction` | 文档上传后 / 手动 | 可选通知 Bot |
| 会话记忆审查 | `self_review_chat_memory` | 周期性 / 手动，默认 `review` | 可选通知 Bot |
| 文档记忆审查 | `self_review_document_memory` | 周期性 / 手动，默认 `review` | 可选通知 Bot |
| 显式记忆 | `explicit_memory` | `/记忆生成` 指令 | 执行 Bot 通知 |

### 8.2 通知机制

平台 Agent 记忆任务可以在 `scheduled_tasks.notify_bot_key` 中配置通知 Bot；显式记忆任务使用执行任务的 Bot（`executor_id`）通知。任务完成后，系统通过 `_send_task_completion_notification` 函数发送企微通知：

- **成功**：`✅ {任务名}完成` + 摘要信息
- **失败**：`❌ {任务名}：{错误摘要}`

通知通过 `enqueue_manual_reply` 入队，由 `ManualReplyHandler` 消费发送。

未配置 `notify_bot_key` 的任务只更新 `scheduled_tasks.last_run_status`、`last_run_message` 和项目日志，不主动发送企微通知。

### 8.3 手动触发提示

在任务列表页点击"立即执行"时，系统底层任务（memory_update / document_memory_extraction / self_review_chat_memory / self_review_document_memory）会弹出确认框：

> 该任务耗时较久，请耐心等待。

### 8.4 超时配置

平台 Agent 超时上限为 1800 秒（30 分钟），用于耗时较久的记忆任务。

### 8.5 数据管理统计

数据管理页“记忆量”卡片由 `/api/data/overview` 返回，统计口径如下：

| 字段 | UI 文案 | 统计口径 |
|------|---------|----------|
| `uploaded_documents` | 上传文档数 | `uploaded_documents` 表总数 |
| `converted_messages` | 已转换记录数 | `chat_messages.convert_status = 'converted'` |
| `memory_update_count` | 记忆更新次数 | `scheduled_tasks.handler_name = 'memory_update'` 且 `last_run_status = 'completed'` |
| `document_extraction_count` | 文档提取次数 | `scheduled_tasks.handler_name = 'document_memory_extraction'` 且 `last_run_status = 'completed'` |

任务运行器写入的完成状态是 `completed`，不是 `success`。概览统计必须与 `task_scheduler.py` / `task_store.py` 的状态枚举保持一致。

## 9. API 接口

### 9.1 RESTful 记忆管理 API

所有 API 位于 `/api/memory` 前缀下，定义在 [app/routers/system.py](app/routers/system.py)。

#### 文件管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/memory/files` | 获取记忆文件列表及统计信息 |
| GET | `/api/memory/items/{file_key}` | 获取指定文件的记忆条目列表 |
| GET | `/api/memory/item` | 获取单条记忆（query: file_key, item_id） |

#### 条目操作

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/memory/items/{file_key}` | 新增记忆条目 |
| PUT | `/api/memory/item` | 更新记忆条目 |
| DELETE | `/api/memory/item` | 删除记忆条目（query: file_key, item_id） |

#### 搜索

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/memory/search` | 搜索记忆条目（query: q, file_key） |

#### 索引与审计

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/memory/indexes/rebuild` | 重建记忆索引（兼容接口） |
| GET | `/api/memory/audits` | 获取记忆审计日志（query: days, limit） |

#### 数据概览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/data/overview` | 获取数据库概览和记忆量统计，包括 `memory_update_count`、`document_extraction_count` |

### 9.2 file_key 路径格式

| file_key | 对应文件 |
|----------|---------|
| `explicit` | .memory/explicit.json |
| `profile` | .memory/profile.json |
| `work` | .memory/work.json |
| `inbox` | .memory/inbox.json |
| `rules` | .memory/rules.json |
| `timeline/2026-05` | .memory/timeline/2026-05.json |
| `documents/doc-api-spec` | .memory/documents/doc-api-spec.json |

### 9.3 Python API

#### MemoryFileManager

```python
from app.memory_file_manager import MemoryFileManager

mgr = MemoryFileManager(".memory")

mgr.init_memory_dir()
files = mgr.list_files()
items = mgr.get_items("explicit")
item = mgr.get_item("explicit", "item-uuid")

from app.memory_schema import MemoryItem
added = mgr.add_item("explicit", MemoryItem(content="新记忆", content_type="fact", speed_lookup="关键词1|关键词2"))
updated = mgr.update_item("explicit", "item-uuid", {"content": "更新内容"})
deleted = mgr.delete_item("explicit", "item-uuid")

results = mgr.search_items("部署约束")

preview = mgr.preview_remove_document_source("doc-api-spec")
removed = mgr.remove_document_source("doc-api-spec")
```

#### memory_schema 工具函数

```python
from app.memory_schema import (
    load_memory_file, save_memory_file,
    load_changelog, save_changelog, add_changelog_entry,
    load_timeline_file, save_timeline_file,
    load_document_memory, save_document_memory,
    list_timeline_months, list_document_source_ids,
)
```

#### skills_integration 子进程 API

```python
from agent_runtime.skills_integration import (
    read_memory,
    add_explicit_memory,
    extract_chat_memory,
    extract_document_memory,
    review_memory,
    init_memory,
)
```

所有函数通过子进程调用对应 skill 脚本，支持 LLM 配置注入（settings 或 database_path）。

#### 记忆使用审计

```python
from app.db.memory_usage_audit_store import (
    upsert_memory_usage_audit,
    list_recent_memory_usage_audits,
)

upsert_memory_usage_audit(
    database_path=Path("data/ai_database.db"),
    trace_id="trace-001",
    chat_id="chat-001",
    bot_key="default",
    call_type="chat",
    status="success",
    user_query="帮我查一下项目的部署约束",
    memory_pack="...",
    selected_files=["explicit.json", "work.json"],
    token_budget_used_estimate=450,
    confidence="high",
    needs_more_memory=False,
    reason="所有相关记忆已加载",
)

audits = list_recent_memory_usage_audits(
    database_path=Path("data/ai_database.db"),
    days=7,
    limit=50,
)
```

## 10. 前端管理页面

记忆管理页面通过 RESTful API 与后端交互，提供以下功能：

### 10.1 文件列表视图

- 显示所有记忆文件的条目数量和最后更新时间
- 包含主文件（explicit/profile/work/inbox/rules）和动态文件（timeline/documents）

### 10.2 条目管理

- 查看指定文件的所有记忆条目
- 新增记忆条目（填写 content、content_type、speed_lookup、priority 等字段）
- 编辑记忆条目（修改任意字段）
- 删除记忆条目

### 10.3 优先级选择

| 标签 | 值 | 说明 |
|------|-----|------|
| 低 | 2 | 一般性信息 |
| 中 | 4 | 常规工作记忆 |
| 高 | 6 | 重要偏好/约束 |
| 工作 | 8 | 关键决策/架构 |
| 紧急 | 10 | 显式记忆/强约束 |

### 10.4 搜索功能

- 全文搜索记忆条目
- 支持限定搜索范围（指定 file_key）
- 搜索结果按评分排序，显示匹配分数

### 10.5 审计日志

- 查看最近 7-30 天的记忆检索审计记录
- 显示 Token 使用量、置信度、是否需要更多记忆等信息

## 11. 数据安全

### 11.1 原子写入

所有 JSON 文件写入通过 `_write_text_atomic` 实现：
1. 在目标目录创建临时文件（前缀 `.tmp_`，后缀 `.json`）
2. 写入完整内容到临时文件
3. 使用 `os.replace` 原子性地替换目标文件
4. 写入失败时清理临时文件

### 11.2 目录锁

并发写入通过 `_acquire_dir_lock` 实现：
1. 使用 `O_CREAT | O_EXCL` 创建独占锁文件 `.lock`
2. 超时 5 秒后抛出异常
3. 写入完成后释放锁（删除 `.lock` 文件）

### 11.3 Changelog 保留策略

- 保留最近 500 条变更记录
- 每条记录包含 action、target_file、item_id、content_preview、reason

## 12. 冲突处理策略

当检测到记忆冲突时，系统遵循以下优先级：

```
1. 运行时强约束指令 > 显式记忆 > 推断记忆
2. 显式记忆 > 推断记忆
3. 工作记忆 > 普通时间线；时间线如含唯一决策、证据或项目上下文则保留
4. 新记忆 > 旧记忆
```

### 冲突检测类型

| 类型 | 说明 |
|------|------|
| `direct_contradiction` | 直接矛盾（如"用 REST" vs "用 GraphQL"） |
| `outdated` | 过时信息 |
| `scope_mismatch` | 作用域不匹配 |
| `priority_conflict` | 优先级冲突 |

## 13. 常见问题

### Q: 如何查看记忆系统的变更历史？

查看 `.memory/changelog.json` 文件，记录了所有写入操作的来源、时间和变更内容。

### Q: 如何删除某个文档的所有记忆？

```python
from app.memory_file_manager import MemoryFileManager

mgr = MemoryFileManager(".memory")
updated_files = mgr.remove_document_source("doc-api-spec")
```

### Q: 记忆系统如何控制 Token 消耗？

通过 `memory-reader` 的评分和裁剪机制，确保最终 Memory Pack 不超过指定 Token 预算。可在调用时指定模式（compact/default/expanded）来调整预算。

### Q: 如何处理记忆冲突？

冲突记忆会被放入 `inbox.json`，通过 memory-reviewer 的 promote_chain 审核并提升到正确分类。

### Q: 如何执行记忆复盘收敛？

```python
from memory_reviewer.orchestrator import compress_memory_file

result = compress_memory_file(file_key="work", memory_root=".memory", llm=llm)
```

该接口不会因为条目数量多而自动收敛；只有 Agent 审核出重复、冗余、碎片化、低价值或可安全缩短的内容时才会生成补丁。

### Q: 如何提升收件箱记忆？

```python
from memory_reviewer.orchestrator import promote_inbox_items

result = promote_inbox_items(memory_root=".memory", llm=llm)
```

### Q: 为什么记忆任务的 token_usage 之前显示 no_llm_usage_reported？

这是因为 `explicit_memory_chain` 之前使用 `chain.invoke()` 一步执行，丢失了 LLM response 的 token metadata。现已修复为拆分为 `prompt.invoke() → llm.invoke() → parser.invoke()` 三步调用，正确提取 token_usage。

### Q: 如何查看记忆使用审计？

```python
from app.db.memory_usage_audit_store import list_recent_memory_usage_audits

audits = list_recent_memory_usage_audits(
    database_path=Path("data/ai_database.db"),
    days=7,
    limit=100,
)
```

## 14. 运行维护与稳定性

### 14.1 当前稳定性结论

当前记忆系统的主链路是稳定可用的：

- 写入链路使用 JSON schema、原子写入和目录锁，显式记忆真实写入后可被 reader 召回并清理。
- 写入和审核链路按"显式记忆 > 文档记忆 > 会话记忆"处理重复，重复审核清理后再次运行不应重复报同一批优先级问题。
- reader 已按可读来源分组 Memory Pack，文档使用文档显示名，显式记忆显示为管理员配置内容，并降低中文字符重叠造成的误召回。
- Agent 系统提示词会把 `<记忆包>` 放在 Bot 自定义指令之前，并附带使用规则：仅文档来源和管理员配置内容需要在回答中标明来源，会话来源不展示。
- reviewer 默认只读；`patch` 会自动应用生成补丁，但底层保护禁止删除 `explicit` 条目。健康检查可用 `--skip-report` 完全无写运行。
- 记忆相关任务支持配置通知 Bot；数据管理页按 `completed` 任务状态统计记忆更新和文档提取完成次数。
- 结构化输出由 memory-creator / memory-reviewer 的 chain 内部约束；普通 Agent 配置不需要常驻 `response_format`。
- 查询扩展改为一次调用，结果复用于工具选择和记忆读取，避免重复 LLM 调用。
- feedback_repair_chain 提示词中 JSON 示例花括号已双写转义，不再被 ChatPromptTemplate 误识别为变量。
- 所有 LLM 链路（查询扩展、记忆创建、审核、反馈修复、时间线复盘）均通过 `app/llm_usage.py` 的 `resolve_token_usage` 提取 Token 用量，Provider 未返回时自动回退到字符估算。
- 正反馈仅用于优先提取，不再生成非法 Issue；负反馈根因审核失败时不再标记"已审核"。
- 流式回答早期失败（如 Agent 构建失败）会补充记忆使用审计记录，状态为 `failed`。

已知边界：

- `profile.json` 为空时 reviewer 会报告缺失警告，这是数据缺口，不是运行错误。
- LLM 参与的 creator/reviewer 链路仍依赖模型 API 可用性和 JSON 输出质量；失败会返回错误，不应静默写入。
- `conversation_usage` 基于近 7 天审计样本，审计样本越少，结论越偏健康检查而不是统计判断。

### 14.2 结构化输出与模型配置

记忆系统需要结构化结果，但不要求普通 Agent 模型配置长期保存 JSON 输出模式。

- memory-creator 的三条提取链路通过 `JsonOutputParser` + Pydantic schema 生成 `ChatSummary`、`ExplicitMemoryResult`、`ChunkSummary`。
- memory-reviewer 的审查、复盘收敛、提升、反馈修复和时间线复盘链路同样通过各自 schema 约束 JSON 输出。

### 14.3 本地审计脚本

本地验证脚本放在 `tests/audit_memory_pipeline.py`，该文件已从 `/tests/` 忽略规则中单独放开，作为记忆链路上线检查脚本提交；其他临时测试辅助脚本仍保持忽略。常用命令：

```powershell
.\.venv\Scripts\python.exe tests\audit_memory_pipeline.py --step provider
.\.venv\Scripts\python.exe tests\audit_memory_pipeline.py --step core
.\.venv\Scripts\python.exe tests\audit_memory_pipeline.py --step llm-core
.\.venv\Scripts\python.exe tests\audit_memory_pipeline.py --step reader --query "采购退货单 聚水潭 拉取 在哪里"
.\.venv\Scripts\python.exe tests\audit_memory_pipeline.py --step reviewer
.\.venv\Scripts\python.exe tests\audit_memory_pipeline.py --step prod-write
.\.venv\Scripts\python.exe tests\audit_memory_pipeline.py --step cleanup --source-id-prefix audit-prod-
```

`core` 使用临时 `.memory` 验证写入、读取、分层去重、补丁应用、重复审核和来源标注提示词；`llm-core` 使用当前 provider 在临时目录验证 creator/reviewer 的 LLM 链路。`prod-write` 会使用唯一 `source_id=audit-prod-<timestamp>` 写入一条临时显式记忆，完成 reader 召回验证后立即删除该 `source_id` 产生的条目。

## 15. 相关文件索引

| 功能 | 文件路径 |
|------|---------|
| 记忆 Schema 定义 | `app/memory_schema.py` |
| 记忆文件管理器 | `app/memory_file_manager.py` |
| 记忆更新构建器 | `app/memory_update_builder.py` |
| 运行时强约束索引 | `app/runtime_query_index.py` |
| 记忆使用审计 | `app/db/memory_usage_audit_store.py` |
| 消息反馈存储 | `app/db/feedback_store.py` |
| 反馈 API 路由 | `app/routers/feedback.py` |
| 记忆 API 路由 | `app/routers/system.py` |
| 任务运行时 | `app/task_runtime.py` |
| 任务调度器 | `app/task_scheduler.py` |
| 记忆创建 Skill | `.skills/system/memory-creator/` |
| 记忆读取 Skill | `.skills/system/memory-reader/` |
| 记忆审核 Skill | `.skills/system/memory-reviewer/` |
| LLM 工厂 | `.skills/system/llm_factory.py` |
| Skills 集成 | `agent_runtime/skills_integration.py` |
