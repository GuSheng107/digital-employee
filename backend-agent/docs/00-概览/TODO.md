# 待办清单（TODO）

> 定位：当前优先要做的、可勾选的具体任务。高频变更，做完划掉或删掉；长期路线图不写这里（在 [当前状态与路线图.md](当前状态与路线图.md)）。
> 规则：每条 = 可执行动作 + 关联文档；先做 P0。

## P0（核心，最高优先级）

- [x] 会话持久化：Session/Turn/Run/Event/Message 五对象模型 + Event/Message 双写；当前使用 SQLite，后续经 RunStore 接口迁移到 PostgreSQL。`user_id` / `user_role` 已预留，auth 接入前不启用。见 [../20-模块/session/总文档.md](../20-模块/session/总文档.md) 与 [../20-模块/session/Phase1-基础可用.md](../20-模块/session/Phase1-基础可用.md)。
- [ ] 模型服务提供与管理：提供统一的模型服务目录、可用模型获取、凭据管理和调用入口；Agent 使用服务端提供的模型，不要求终端用户配置模型 Key。当前 LiteLLM + 本地 `.env` 仅用于开发测试，正式运行通过模型网关或独立模型服务接入。见 [../20-模块/model-模型网关与配置.md](../20-模块/model-模型网关与配置.md)。

## P1（较高优先级）

- [ ] 沙箱（配合工具调用）：SandboxProvider 接口 + SandboxManager + DockerProvider（Phase 1）。见 [../20-模块/sandbox/总文档.md](../20-模块/sandbox/总文档.md) 与 [../20-模块/sandbox/Phase1-DockerProvider.md](../20-模块/sandbox/Phase1-DockerProvider.md)。
- [ ] 权限策略与审批：独立实现 Sandbox Policy 和 Approval Policy；工具或命令执行前先判断允许、需要审批或拒绝，等待审批时可暂停运行，获准后仍必须受沙箱策略限制，并记录完整结果。见 [../20-模块/sandbox/总文档.md](../20-模块/sandbox/总文档.md) 与 [../20-模块/sandbox/Phase2-安全演进.md](../20-模块/sandbox/Phase2-安全演进.md)。
- [ ] Trace 执行链路观测：独立于会话持久化记录和查看一次 Run 的完整过程，包括每轮实际提示词、模型响应、工具 schema、调用参数与结果、状态、耗时和错误；支持按 `trace_id` 检索和分析。见 [../20-模块/runtime-请求生命周期.md](../20-模块/runtime-请求生命周期.md) 与 [../40-参考研究/deepseek-harness-agent-runtime-reference.md](../40-参考研究/deepseek-harness-agent-runtime-reference.md)。
- [ ] 多 Agent 协同与流程编排：支持 Agent 之间的任务分工、协作和结果传递，按角色分配可用插件与工具；提供计划-生成-评审等协作流程，并预留前后端分工、项目经理分工等可配置组织模式。见 [../20-模块/阶段需求与范围.md](../20-模块/阶段需求与范围.md) 与 [项目定位与总体方向.md](项目定位与总体方向.md)。

## P2（中优先级）

- [ ] 插件化的工具调用：Skill / MCP 等统一经 Adapter 归一为 ToolSpec，按能力合同接入。见 [../20-模块/tools-工具系统-MCP与Skill.md](../20-模块/tools-工具系统-MCP与Skill.md)。

## P3（低优先级，后置）

- [ ] 分层记忆（Memory）：用户画像、偏好等长期记忆，按需检索注入。见 [../20-模块/context-上下文组装.md](../20-模块/context-上下文组装.md)。
- [ ] 知识库插件：定义外部知识库检索接口，支持接入和切换第三方知识库平台，不在核心服务内实现具体知识库。见 [../20-模块/阶段需求与范围.md](../20-模块/阶段需求与范围.md) 与 [../10-决策记录/10-决策记录.md](../10-决策记录/10-决策记录.md) D-008。
