# 一期 Runtime 请求生命周期

## 输入与输出合同

`RunRequest` 至少含 `agent_id`、`messages`、`request_id`、`stream`。服务端加载不可由客户端覆盖的 `AgentDefinition`，生成 `run_id` 和 `trace_id`。`RunResult` 返回最终消息、usage、终态及引用；流式时依次发送 `run.started`、`model.delta`、`tool.started`、`tool.completed`、`run.completed` 或 `run.failed`。

一期只允许一个 Agent、当前用户消息和调用方明确传入的少量历史；当前二期在提供 `conversation_id` 时会从 SQLite 恢复该会话消息。AgentDefinition 中的 `allowed_mcp_servers`、`allowed_skills` 是工具面唯一来源，不能由用户请求临时扩大。`user_id` / `user_role` 已进入请求和会话模型，但 auth 接入前不参与权限判断。

## 状态机

```text
created -> preparing -> model_calling -> tool_calling -> model_calling
                                     \-> completed
任一状态 -> cancelled | failed
```

执行步骤：

1. API Adapter 校验请求，Runtime 加载 AgentDefinition，Recorder 写入 `run.started`。
2. Context Builder 按稳定到动态顺序组装：系统指令、Skill 指令、显式挂载工具 schema、历史和本轮消息。
3. Tool Registry 汇总 MCP 与 Skill Adapter 的 `ToolSpec`；Runtime 调用 Model Gateway。
4. 没有 tool call 时，归一化模型文本为最终答案并结束。
5. 有 tool call 时，先校验工具名、JSON 参数、循环数与剩余预算；Tool Executor 执行并记录事件。
6. 将标准化 `ToolResult` 作为对应 tool message 追加到本轮消息，再回到步骤 3。达到最大轮数后返回可识别的 `tool_loop_limit` 失败，绝不继续猜测。

所有模型和工具事件都带同一个 `trace_id`。一期默认工具顺序执行，避免并发写操作和复杂取消语义；并行调用留到二期。

## 预算、取消与错误

- 配置 `model_timeout_seconds`、`tool_timeout_seconds`、`max_tool_rounds`、`max_output_tokens` 和单次 `max_tool_result_chars`；超限即终止当前 Run。
- 客户端断开或显式取消时，Runtime 取消可取消的模型/工具任务，写入 `cancelled`，再关闭 MCP 会话。
- 外部失败使用稳定错误码：`model_unavailable`、`tool_not_allowed`、`tool_invalid_arguments`、`tool_timeout`、`tool_execution_failed`。对用户隐藏凭据、URL Header、堆栈和原始工具密文。
- 每个事件至少记录时间、阶段、耗时、模型名或工具名、结果大小、错误码、usage；原始消息和工具结果的保存策略由二期数据治理补齐。

## 天气验收路径

把本地 FastMCP 天气服务以 `stdio` 配置挂到 `weather-agent`，并显式允许 `get_weather`。发送“北京今天天气怎样”：第一轮模型选择 `get_weather(city="北京")`，Runtime 返回查询结果，第二轮模型以结果组织中文回答。测试须断言工具确实被调用，不能只检查最终文本。
