# 模型网关与配置

## 决策

一期使用 [LiteLLM](https://github.com/BerriAI/litellm) 的 Python SDK 实现 `LiteLLMModelGateway`。Runtime 只依赖项目自定义的 `ModelGateway` 协议，不依赖 LangChain 的 Chat 类或任何厂商 SDK。LiteLLM 负责不同模型 API 的调用归一化；它不是 Agent 编排器，也不保存本项目的 Agent、工具或会话状态。

这是对旧版 `models.py` 中“按 provider type 选择 LangChain 类、再针对字段打补丁”的替代。Provider 差异应集中在一个网关配置和少量适配测试中，而不是泄漏到 Context Builder、工具系统和 API。

## 合同与配置

```text
ModelGateway.complete(request) -> ModelResponse
ModelGateway.stream(request)   -> AsyncIterator[ModelEvent]
```

请求使用项目统一消息模型、`ToolSpec` 列表和运行预算；响应统一为文本增量、完成原因、零或多个 `ToolCall`、usage、provider request ID。网关内部负责 LiteLLM 的消息和工具格式映射，Runtime 不读取厂商原始对象。

`ModelProfile` 至少包含：`profile_id`、`model`、`api_base`、`api_key_secret_ref`、超时、重试数、最大输出、默认参数和启用状态。密钥只存 secret 引用，日志和 API 永不回显。模型名、基础地址和厂商特有参数视为配置数据；配置变更需运行连通性测试。

## 一期支持策略

- 首个验收目标是一个 OpenAI 兼容端点，模型与 `api_base` 可配置；DeepSeek 或其他 Provider 通过 LiteLLM 配置接入。
- 每个 Agent 一期只选择一个 `ModelProfile`。LiteLLM 的统一接口为未来多厂商提供基础，但自动路由、fallback、负载均衡和按成本选模属于二期。
- 工具调用以当前模型实际支持的 tool/function calling 为前提。模型不支持时应在 Agent 保存或连通性测试时给出明确错误，不退化为解析自然语言命令。
- 版本固定在项目依赖文件中，并为每个已启用 Provider 建立真实或 mock 的连通性测试；不要依赖某个 LiteLLM 内部对象结构。

## 连通性与错误归一化

连通性测试使用最小非流式消息“你好”，不挂工具，不写数据。它必须记录配置摘要（脱敏）、耗时、HTTP/Provider request ID 和归一化错误码。认证、地址、限流、超时、模型不存在、工具协议不兼容要分别显示；调用日志不得写出 API Key。

一期仅在网关层做有限重试：只重试可判定的暂时性连接/服务错误，绝不重试已开始执行的工具调用。重试、限流、成本、cache 命中数据统一回传 Recorder，二期再增加按 Provider 的策略控制。
