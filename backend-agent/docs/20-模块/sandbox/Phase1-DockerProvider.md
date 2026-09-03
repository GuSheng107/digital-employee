# Sandbox Phase 1：Docker Sandbox（基础安全执行）

> 所属模块：sandbox（沙箱）
> 定位：第一阶段落地清单。目标 = 能安全执行代码、拥有独立 Workspace。

## 阶段总览

| 阶段 | 目标 | 实现 |
| --- | --- | --- |
| P1 | 能安全执行代码 | Docker Sandbox |
| P2 | Runtime 解耦 Sandbox | Sandbox Server + Execution |
| P3 | 精细安全控制 | Filesystem + Network + Approval + OS Sandbox |
| P4 | Agent 可恢复工作环境 | Workspace Snapshot |
| P5 | 企业级强隔离 | Firecracker / MicroVM |

## Phase 1 目标与实现

第一阶段只解决：Agent 能够安全执行 Shell / Python / Node，并拥有独立 Workspace。

```text
SandboxManager
      ↓
DockerProvider
      ↓
Docker Container
```

## 功能要求

### 生命周期

`create / start / stop / kill / destroy`。

### 执行

`exec(command)`，支持 cwd、environment、timeout、stdin、stdout、stderr、exit_code。

### 文件

`read_file / write_file / list_files`。

### Workspace

固定 `/workspace`。Workspace 与 Sandbox 分离：

```text
workspace_id
      ↓
host directory / Docker volume
      ↓
/workspace
```

不要让 Workspace 生命周期绑定 Docker Container。以后可以销毁 Sandbox 而保留 Workspace，供新的 Sandbox 继续使用。

### Sandbox Policy（三个模式）

```text
read_only
workspace_write
full_access
```

默认：`workspace_write` + `network_disabled`。推荐：`/workspace` RW、`/tmp` RW、其他文件系统 RO；敏感目录不得挂载。

### Network

只支持 `disabled / enabled`，默认 disabled。第一阶段不要实现复杂 Network Proxy，后续再增加 allowlist、proxy。

### Resource Limits

至少支持：CPU、Memory、Process Count、Execution Timeout、Disk。

```yaml
resources:
  cpu: 2
  memory: 4Gi
  pids: 256
  timeout: 300
```

避免 Agent 出现 fork bomb、无限循环、内存爆炸、CPU 占满等问题。

### 数据库 sandboxes 表

```sql
CREATE TABLE sandboxes (
    id UUID PRIMARY KEY,
    tenant_id UUID,
    session_id UUID,
    workspace_id UUID,
    provider VARCHAR(32) NOT NULL,       -- 如 docker
    provider_id TEXT,                    -- Provider 内部的资源 ID（如容器 ID）
    status VARCHAR(32) NOT NULL,         -- creating / running / stopped / destroyed
    image TEXT NOT NULL,
    policy JSONB NOT NULL,               -- 安全策略快照
    resource_policy JSONB NOT NULL,      -- 资源限制快照
    created_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    stopped_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_sandboxes_session ON sandboxes(session_id);
CREATE INDEX idx_sandboxes_workspace ON sandboxes(workspace_id);
CREATE INDEX idx_sandboxes_status ON sandboxes(status);
```

### Sandbox 与 Run 的关系

一个 Sandbox 可以服务多个 Run：

```text
Session
   │
   └── Workspace
          │
          └── Sandbox
                │
                ├── Run 1
                ├── Run 2
                └── Run 3
```

默认在 Session / Workspace 生命周期内复用 Sandbox。

### Sandbox 与 Sub Agent

第一阶段提供 isolated 和 shared 两种模式，默认 isolated：

```text
Main Agent
   └── Sandbox A

Sub Agent
   └── Sandbox B
```

如果明确要求共享，则 Sub Agent 复用 Main Agent 的 Sandbox，但不要默认共享。

## 第一阶段明确"不做"

❌ Firecracker　❌ Kubernetes　❌ VM Pool　❌ Network Proxy　❌ Landlock　❌ seccomp 自研规则　❌ Workspace Snapshot　❌ 分布式 Sandbox Scheduler　❌ 跨节点 Sandbox Migration　❌ 复杂 Approval Engine

第一阶段只有：Docker + Workspace + SandboxManager + SandboxProvider + Shell + File + Process + Resource Limit。

## 第一阶段验收标准

完成后必须可以：

- 创建 Sandbox：`create()` 返回 sandbox_id
- 执行 Shell：`exec("python test.py")` 返回 stdout、stderr、exit_code
- 文件操作：`write_file()`、`read_file()` 正常
- Workspace 持久化：销毁 Sandbox A 后，新建 Sandbox B 仍能看到 Workspace
- Runtime 重启恢复：重启后 Sandbox 状态可重新发现
- Agent Run 关联：Run → Tool Call → Sandbox Execution 链路完整
- Sub Agent 隔离：Main Agent 与 Sub Agent 各自独立 Sandbox（默认）
- 安全限制验证：workspace 可写、workspace 外不可写、超时 kill、进程限制、network disabled、destroy 后无法继续执行

## 实施顺序

```text
Step 1  定义 Sandbox 接口
Step 2  定义 SandboxConfig / Policy / Execution Model
Step 3  实现 SandboxManager
Step 4  实现 DockerProvider
Step 5  实现 Workspace
Step 6  实现 exec / file API
Step 7  加入 Resource Limit
Step 8  加入 sandboxes 数据库表
Step 9  接入 Agent Tool
Step 10 接入 Run / Event Persistence
Step 11 补齐集成测试
```

完成 Step 11 后才进入 Phase 2。

## Phase 1 目录结构

```text
runtime/
└── sandbox/
    ├── interface.py
    ├── manager.py
    ├── models.py
    ├── policy.py
    └── providers/
        └── docker/
            ├── provider.py
            ├── container.py
            └── executor.py
```

## 相关文档

- 概述：[总文档.md](总文档.md)
- Phase 2+：[Phase2-安全演进.md](Phase2-安全演进.md)
