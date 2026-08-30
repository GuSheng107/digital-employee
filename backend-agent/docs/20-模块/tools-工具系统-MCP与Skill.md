# 工具系统：MCP 与 Skill

## 核心判断

MCP 是外部工具协议，Skill 是可复用工作方法和受控本地能力包，两者不能混为一层 Prompt。二者经 Adapter 转换后才以同一个 `ToolSpec` 暴露给模型；Runtime 只识别 `ToolSpec` 与 `ToolResult`。

```text
ToolSpec: name, description, input_schema, source, risk_level, timeout_seconds
ToolResult: tool_call_id, status, content, structured_data, artifact_refs, error_code
```

工具名在 Registry 中必须全局唯一。暴露给 OpenAI 兼容模型时只能使用字母、数字、`_`、`-`，例如 `mcp_weather_get_weather`、`skill_weather-assistant_format_weather_observation`；Adapter 内部维护到原始 MCP/Skill 名称的映射。参数须先按 JSON Schema 校验；结果限制大小并可截断，长内容二期转 ArtifactStore。

## MCP Adapter

一期仅支持由平台管理员配置的 `stdio` MCP Server。Adapter 生命周期为：按 AgentDefinition 挂载 Server -> 启动进程 -> `list_tools` -> 转 ToolSpec -> 调用 -> 正常关闭。Server 的命令、参数、环境变量来自受控配置，不接受聊天消息传入的命令或环境变量。

一期每个 Run 可创建独立 MCP 会话，保证测试和取消语义清晰。必须对启动、发现、调用施加超时；发现失败时该 Server 不进入工具面，且在 trace 记录失败原因。HTTP/SSE、共享连接池、动态市场发现、审批和凭据轮换后置到二期。

## Skill Adapter

一期 Skill 是仓库中受信任目录下的版本化包，至少含 `SKILL.md` 和 manifest。`SKILL.md` 提供稳定工作指令；manifest 声明名称、版本、描述、是否可注入、可提供的本地工具、输入 schema 和超时。Skill 只能被 `AgentDefinition.allowed_skills` 显式授予，不能由模型自行读取任意文件或临时下载。

Skill 可只有指令而无工具。带工具的 Skill 必须经 Adapter 包装为 `ToolSpec`，执行函数应位于受控实现目录并接受结构化参数。禁止让 `SKILL.md` 中的自然语言直接变成 shell 命令；文件系统、网络和敏感动作的沙箱/审批在二期实现。

## Registry 与执行规则

构建顺序为：加载 AgentDefinition -> 加载被允许的 Skill -> 建立被允许的 MCP 连接并发现工具 -> 去重、校验 schema -> 交给 Context Builder。与旧版按用户输入关键词、LLM 扩词后筛选 Skill/MCP 不同，一期不做隐式选择，工具数量由绑定配置控制。

`ToolExecutor` 在每次调用前复核 allowlist、参数和剩余预算；调用后无论成功或失败都生成 `ToolResult`。未知工具、越权工具、无效参数、超时和异常必须作为工具结果/错误事件返回 Runtime，禁止吞掉后继续调用模型。

天气示例的 `get_weather(city)` 应是独立 FastMCP Server；将它绑定给测试 Agent 后，模型看到的只是规范化 schema，不需要知道 FastMCP 的实现细节。
