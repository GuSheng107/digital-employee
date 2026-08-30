# 待办清单（TODO）

> 定位：当前优先要做的、可勾选的具体任务。高频变更，做完划掉或删掉；长期路线图不写这里（在 [当前状态与路线图.md](当前状态与路线图.md)）。
> 规则：每条 = 可执行动作 + 关联文档；先做 P0。

## P0（核心，最高优先级）

- [ ] 会话持久化：Session/Turn/Run/Event/Message 五对象模型 + Event/Message 双写；**先用 SQLite 实现，后续经 RunStore 接口迁移到 PostgreSQL**。见 [../20-模块/session/总文档.md](../20-模块/session/总文档.md) 与 [../20-模块/session/Phase1-基础可用.md](../20-模块/session/Phase1-基础可用.md)。

## P1（较高优先级）

- [ ] 沙箱（配合工具调用）：SandboxProvider 接口 + SandboxManager + DockerProvider（Phase 1）。见 [../20-模块/sandbox/总文档.md](../20-模块/sandbox/总文档.md) 与 [../20-模块/sandbox/Phase1-DockerProvider.md](../20-模块/sandbox/Phase1-DockerProvider.md)。

## P2（中优先级）

- [ ] 插件化的工具调用：Skill / MCP 等统一经 Adapter 归一为 ToolSpec，按能力合同接入。见 [../20-模块/tools-工具系统-MCP与Skill.md](../20-模块/tools-工具系统-MCP与Skill.md)。

## P3（低优先级，后置）

- [ ] 分层记忆（Memory）：用户画像、偏好等长期记忆，按需检索注入。见 [../20-模块/context-上下文组装.md](../20-模块/context-上下文组装.md)。
