# DeepSeek Harness Agent Runtime 设计参考

## 范围与架构事实

本稿基于本地 `参考项目/deepseek-harness` 源码及文档，不代表外部部署状态。以下“事实”均可由所列路径核验；“推导”是面向自研后端的设计建议。

**事实。** DeepSeek Harness 是 TypeScript/PNPM workspace，基于 vendored Cordis；模型、会话、工具和 Agent loop 都是插件，注册是可撤销 effect，没有需打补丁的特权内核（`参考项目/deepseek-harness/AGENTS.md`，`docs/architecture.zh.md`）。一项可替换能力由 Service Definition、Provider、Consumer 三角组成，例如工具消费子代理、文件系统或 shell Provider（`docs/architecture.zh.md#能力-seam`）。

启动时 `profile` 按序叠加 bundle 的 `cordis.patch.yml`、profile patch、home patch 和 `--patch`；patch 可替换既有配置或插入插件。`dsh-base` 是共用底座，`headless`/`web-app` 再叠加交互形态（`docs/architecture.zh.md#profile-与组合包`，`packages/boot/app-boot/src/profile.ts`）。这使同一运行时可以按会话组成不同能力集合，但也将最终行为分散到多层 YAML。

## 一次请求的数据流

**事实。** 输入进入 Agent inbox；`followup` 唤醒下一轮，`steer` 唤醒下一步骤，`inject` 只排队上下文。循环先记录 `turn/start`，领取输入，组装系统提示词段、动态上下文和工具 schema，经过 `agent/pre-step` waterfall 后记录 `step/start` 与 `user/message`（`packages/core/agent-loop/src/agent.ts`，`docs/architecture.zh.md#轮次流程`）。

随后从会话日志 `deriveMessages()` 生成历史，`agent/request` 可调整路由，LLM adapter 流式输出；每个 chunk 均追加 `assistant/chunk`，汇聚后追加 `assistant/message`。请求 header、上下文窗口、提示词和工具 schema 也记录在日志中，满足“模型可见即已记录”（`packages/core/agent-loop/src/agent.ts`，`docs/architecture.zh.md#会话日志`）。

若回复含 tool call，调度器先追加 `tool/call`，再走 `tools/pre-execute -> tools/execute -> tools/post-execute`。审批 seam 的 `ask` 缺少应答者时拒绝；并行工具受上限控制，但策略、结果和附加上下文仍按模型顺序写成 `tool/result`，并注入下一 step。无工具调用即完成，否则继续步骤直至 inbox 为空，最后记录 `step/end`、`turn/end`（`packages/core/agent-loop/src/tool-calls.ts`，`packages/core/tools/src/index.ts`，`packages/interaction/user-approval/README.zh.md`）。

**事实。** `SessionEvent` 是持久化真源；SQLite/JSONL 后端仅追加、要求连续 seq，恢复崩溃轮次时追加合成 close 事件而非截断历史（`packages/session/session-persistence/README.zh.md`）。遥测从 `session/event` 投影，保留首个流分片、经脱敏 waterfall 后交接，接收端以 `(session.id,event.seq)` 去重（`packages/session/session-telemetry/README.zh.md`）。

**事实。** 失败与取消也进入同一生命周期：模型流错误可由 `agent/request-error` 决定重试；已开始的工具调用取消后会被排空并记录结果，未开始调用补写合成的中止结果，避免回放出现未配对的调用（`packages/core/agent-loop/src/agent.ts`，`packages/core/agent-loop/src/tool-calls.ts`）。这并不等同于业务幂等，工具本体若已产生副作用仍不能靠日志回滚。

## 上下文、压缩、子代理与权限

**事实。** 本仓库的“记忆”核心是可回放的会话日志和运行时上下文，不是独立的长期语义记忆库；动态上下文在 prompt 组装时成为带来源的快照（`packages/core/system-prompt/README.zh.md`）。`compaction-basic` 以 token 压力触发：可先修剪大工具结果，再对较早完整单元作辅助 LLM 摘要，以 checkpoint 替换历史、保留近期尾部；摘要请求回放原前缀以利用 KV cache（`packages/compaction/compaction-basic/README.zh.md`）。

子代理也是 seam：可新建、fork 或经 ACP/外部 SDK 运行；父子各有会话，前台仅把最终输出作为工具结果回传，后台以任务或可继续子会话处理（`packages/subagent/README.zh.md`，`packages/subagent/tool-subagent/README.zh.md`）。权限是一次性审批和 `ask/never` 策略，审计事件写日志；工具过滤并非从父代理继承的安全上限（`packages/interaction/user-approval/README.zh.md`，`packages/subagent/tool-subagent/README.zh.md`）。

**事实。** 会话恢复不是简单读取消息：持久化服务验证格式和序号，活动会话先 flush；冷恢复会保留已发生事件并补齐中断轮次，使后续模型历史可用（`packages/session/session-persistence/README.zh.md`）。这说明日志事件既是审计记录，也是驱动 UI、恢复和 prompt 投影的领域事实；不要另外维护一份容易漂移的“聊天记录表”。

**事实。** Agent 创建和恢复把会话、作用域化 Context、注册表发布及 teardown 视为同一生命周期事务；调用方卸载、handle dispose 或 loop provider 卸载都会收敛到停止、排空、撤销作用域、注销 agent 和会话的顺序（`packages/core/agent-loop/README.zh.md`）。因此能力注册可按 agent 隔离，但该隔离是运行时组合机制，不自动赋予数据隔离或权限继承语义。

**事实。** 遥测仅观察已记录的事件，不会增加模型上下文；实时模式在事件追加时交接，按需模式从权威日志回放，二者的脱敏策略均由部署方提供（`packages/session/session-telemetry/README.zh.md`）。这把“可观测”与“影响模型行为”的插件清晰分离，也暴露了生产环境必须单独治理的日志敏感数据风险。

## 自研取舍与落地顺序

**推导。可借鉴。** 采用追加事件日志为会话事实源、把模型可见输入可重建化、让工具策略在执行前且结果有序落库。这三点使恢复、审计、回放和问题定位共享同一证据。将“模型网关、工具执行、持久化、遥测”定义为接口加适配器，也优于在 Agent loop 内直接绑定供应商。

**推导。不宜照搬。** 不必一开始把一切切成 Cordis 插件和多层 patch：小团队会承担过高的组合与排障成本。其遥测默认尽力交接且不内置脱敏，不能直接用于含隐私数据的服务；其 `toolFilter` 也不能替代服务端授权。自研必须以租户/用户/会话 scope 强制权限、为副作用工具提供幂等键与超时，并采用持久 outbox、密钥脱敏和保留/删除策略。

**推导。模块边界与阶段。** 建议拆为 `api`（鉴权、流式协议）、`runtime`（状态机/inbox）、`context`（提示词、会话窗口、长期记忆检索）、`model`（provider）、`tools`（schema、策略、执行）、`session`（事件与投影）、`persistence`、`observability`、`policy`。第一阶段完成单模型、单会话、只读工具、追加日志与 trace；第二阶段加入审批、持久化恢复、上下文预算和结构化长期记忆；第三阶段再加入压缩、后台子代理、多 Provider 与队列。测试应覆盖事件序列快照、重放等价、工具拒绝/取消/并行顺序、跨租户隔离、崩溃恢复和遥测脱敏；端到端记录 trace、模型/提示词版本、token、工具结果和记忆选择依据。

**推导。实施约束。** 每个写入事件带 `tenant_id`、`session_id`、递增序号、时间和请求关联 ID；prompt 组装产物须可序列化并以版本化规则生成。工具执行应区分“准入已拒绝、未开始、执行中止、未知结果、成功”，对写操作要求调用方提供幂等键或人工确认。观测数据采用最小必要字段，正文与工具输出先脱敏、按权限查询；告警基于模型错误率、工具失败率、恢复次数、上下文压缩频率和每轮 token/延迟。上述要求是将 Harness 的可回放理念落到多租户服务所需的补充，而非其源码直接实现。

## 未覆盖事项

未运行安装、测试或真实模型调用；未逐一审计每个 Provider、外部沙箱、MCP 工具和数据库实现。长期记忆的向量检索、写入提升与数据生命周期并非该参考仓库此处已确认的核心实现，需由自研需求独立设计。
