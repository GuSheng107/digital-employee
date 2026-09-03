# Sandbox Phase 2+：安全演进与解耦

> 所属模块：sandbox（沙箱）
> 定位：Phase 1 稳定后，再做 Server 解耦、精细安全控制、Snapshot 与 MicroVM。

## Phase 2：Sandbox Execution 与 Runtime 解耦

将执行从 SandboxManager 直接 Docker exec 升级为独立的 Sandbox Server 架构（参考 OpenHands 的 Action Execution Server）：

```text
Agent Runtime
      │
      ▼
SandboxManager
      │
      ▼
Sandbox Server
      │
      ▼
Docker
```

Execution API 统一为：

```text
POST /exec
GET  /files
GET  /files/{path}
PUT  /files/{path}
POST /process/{id}/kill
GET  /health
```

Runtime 不直接关心底层是 Docker、Pod 还是 VM，只关心 Sandbox API。

### Sandbox Execution 数据库

```sql
CREATE TABLE sandbox_executions (
    id UUID PRIMARY KEY,
    sandbox_id UUID NOT NULL,
    run_id UUID,
    tool_call_id UUID,
    command TEXT,
    cwd TEXT,
    status VARCHAR(32),                 -- pending / running / success / failed / killed
    exit_code INTEGER,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    stdout_ref TEXT,                    -- stdout 内容引用（可存对象存储）
    stderr_ref TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_sandbox_exec_sandbox ON sandbox_executions(sandbox_id);
CREATE INDEX idx_sandbox_exec_run ON sandbox_executions(run_id);
```

### 与 Conversation Persistence 集成

```text
Session
   │
 Branch
   │
  Run
   │
Tool Call
   │
Sandbox Execution
   │
Sandbox
   │
Command
```

同时写入 Event：`sandbox.execution.started`、`sandbox.execution.completed`、`sandbox.permission.denied`、`sandbox.network.denied`、`sandbox.process.killed`。这样可完整追踪 Agent → Tool → Sandbox → Command → Result 链路。

### Runtime Plugin

Sandbox 支持插件（参考 OpenHands Runtime Plugin）：Shell、Python、Node、Browser、Jupyter、Custom Plugin。

```python
class SandboxPlugin(Protocol):
    """Sandbox 插件接口。"""

    name: str

    async def install(self, sandbox: Sandbox) -> None:
        """在 Sandbox 中安装插件所需的依赖或环境。"""
        ...

    async def start(self, sandbox: Sandbox) -> None:
        """启动插件服务。"""
        ...

    async def stop(self, sandbox: Sandbox) -> None:
        """停止插件服务。"""
        ...
```

插件安装方式：不要让 Plugin 自己直接操作 Docker。错误方式：Plugin → Docker API；正确方式：Plugin → Sandbox API → Sandbox。插件只知道 exec、read_file、write_file、expose_port。

## Phase 3：细粒度安全控制与 OS Sandbox

### 细粒度 Sandbox Policy

从简单的 workspace_write 升级为结构化策略：

```python
class SandboxPolicy:
    filesystem: FileSystemPolicy
    network: NetworkPolicy
    process: ProcessPolicy
    resources: ResourcePolicy
```

### Filesystem Policy

支持 read、write、deny，并支持嵌套覆盖（子路径可以覆盖父路径）：

```yaml
filesystem:
  rules:
    - path: /workspace
      access: write
    - path: /workspace/.git
      access: read
    - path: /workspace/.env
      access: deny
```

Codex 的 Linux Sandbox 已处理类似 nested read-only / denied carve-out，因此这个抽象值得提前保留。

### Network Policy

从 disabled / enabled 升级为：`disabled / full / allowlist / proxy`。

```yaml
network:
  mode: allowlist
  domains:
    - github.com
    - pypi.org
    - npmjs.org
```

### Approval Policy

独立实现，模式包括 never、on_request、always、rule_based：

```yaml
approval:
  rules:
    - action: shell
      pattern: "rm -rf"
      policy: ask
    - action: network
      policy: ask
```

注意：Approval 是用户交互层，Sandbox Policy 是安全边界。

### OS Sandbox Provider

增加 DockerProvider、LinuxSandboxProvider、MacOSSandboxProvider。Linux 优先研究 Bubblewrap、seccomp、Landlock（参考 Codex），但只实现 SandboxProvider 接口，让上层完全无感。

## Phase 4 & 5：Workspace Snapshot 与 MicroVM

### Phase 4: Workspace Snapshot

当需要 Branch、Fork、Retry、Time Travel、Resume 时，增加 WorkspaceSnapshot：

```text
Workspace
    │
    ├── Snapshot 1
    └── Snapshot 2
```

Fork 场景：Branch A → Workspace Snapshot → Branch A / Branch B。不要复制整个 Sandbox。

### Phase 5: MicroVM

只有真正需要多租户、强隔离、不可信代码、高并发、快速恢复时，再增加 FirecrackerProvider。

最终 Provider 集合：

```text
SandboxProvider
├── DockerProvider
├── LinuxSandboxProvider
├── MacOSSandboxProvider
└── FirecrackerProvider
```

参考 E2B 的 Control Plane / Data Plane / Firecracker / Snapshot 架构。

## 最终目录结构

第三阶段：

```text
sandbox/
├── policy/
│   ├── filesystem.py
│   ├── network.py
│   ├── process.py
│   └── resources.py
├── providers/
│   ├── docker/
│   ├── linux/
│   └── macos/
└── approval/
```

最终：

```text
sandbox/
├── manager
├── policy
├── execution
├── workspace
├── snapshot
├── plugins
└── providers/
    ├── docker
    ├── linux
    ├── macos
    └── firecracker
```

## 总结：最终架构关系

```text
                    Agent Runtime
                          │
                         Tool
                          │
                    SandboxManager
                          │
                    SandboxProvider
                          │
          ┌───────────────┼────────────────┐
          ▼               ▼                ▼
       Docker            OS             MicroVM
       Sandbox         Sandbox           Sandbox
          │               │                │
          └───────────────┼────────────────┘
                          ▼
                       Workspace
```

结合 Conversation Persistence，一次代码执行链路：

```text
User → Turn → Run → Tool Call → SandboxManager → SandboxProvider
→ Sandbox → Execution → Result → Tool Result → LLM → Assistant
```

所有关键节点都进入统一 Event Store，使 Conversation Persistence、Agent Run、Tool、Sandbox 四个模块形成完整闭环，而不是各自保存一套孤立状态。

## 相关文档

- 概述：[总文档.md](总文档.md)
- Phase 1：[Phase1-DockerProvider.md](Phase1-DockerProvider.md)
- 决策依据：[../../10-决策记录/10-决策记录.md](../../10-决策记录/10-决策记录.md)
