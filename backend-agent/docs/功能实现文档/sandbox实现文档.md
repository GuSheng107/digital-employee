Agent Runtime Sandbox 设计与实施方案
版本：V1.0

1. 目标与核心原则
1.1 目标
为 Agent Runtime 提供统一、安全、可扩展的代码执行环境。

Sandbox 负责：

Shell / Python / Node 等代码执行

文件读写

工作目录

进程生命周期

资源限制

网络限制

Workspace 隔离

执行审计

Sandbox 生命周期管理

Sandbox 不负责：

LLM 调用

Agent 决策

Conversation

Memory

Tool 编排

Sub Agent 编排

核心原则：

Agent Runtime 决定执行什么，Sandbox 决定在哪里以及以什么权限执行。

1.2 核心架构原则
整个 Sandbox 系统需要牢记四句话：

1. Agent 不直接操作 Docker。

2. Runtime 只依赖 SandboxProvider 接口。

3. Workspace 与 Sandbox 生命周期分离。

4. 安全策略与 Approval 策略分离。

1.3 Policy 与 Approval 必须分离
Sandbox Policy 指“允许 Agent 做什么”，Approval Policy 指“什么时候需要用户批准”，二者不能混在一起。

text
Tool Request
     │
     ▼
Approval Policy
     │
 ┌───┼────┐
 ▼   ▼    ▼
Allow Ask Deny
 │    │
 │    └── User
 │
 ▼
Sandbox Policy
 │
 ▼
Execution
Sandbox 即使处于自动执行模式，也必须受到 Sandbox Policy 限制。

2. 参考项目
2.1 OpenHands —— 第一阶段主要参考
OpenHands 当前已经将 Sandbox 独立成 Runtime 层，并支持 Docker / Process / Remote 等 Provider。

Docker 模式采用：

text
Agent Runtime
      ↓
Sandbox Client
      ↓
Sandbox Server
      ↓
Docker Container
      ↓
Action Executor
容器内部负责 Shell、文件操作、Python、插件等执行能力。

参考：

OpenHands Runtime Architecture

OpenHands Docker Sandbox

OpenHands Sandbox Server

OpenHands 还支持自定义 Sandbox Image、Volume、Overlay 和 Runtime Plugin，这些设计非常适合作为本项目第一阶段的参考。

2.2 Codex —— 后期 OS Sandbox 参考
Codex Linux Sandbox 使用：

text
Bubblewrap
+
seccomp
+
Landlock
并通过 filesystem policy 控制路径访问。

后续如果需要实现低开销的本地 Sandbox，可以参考 Codex 的实现，但第一阶段不要自己实现。

2.3 E2B —— 最终企业级架构参考
E2B 的架构已经进入：

text
Control Plane
+
Data Plane
+
Firecracker MicroVM
+
Snapshot
Sandbox 本质上是可以快速恢复的 VM Snapshot。

这作为未来多租户、强隔离、高并发版本的参考，不作为当前实现目标。

3. 总体架构与核心抽象
3.1 总体架构
Sandbox 必须采用插件式 Provider 架构。

text
                         Agent Runtime
                              │
                              ▼
                       Sandbox Manager
                              │
                       Sandbox Interface
                              │
              ┌───────────────┼────────────────┐
              │               │                │
              ▼               ▼                ▼
        DockerProvider   LocalProvider   FutureProvider
              │
              ▼
        Docker Sandbox
              │
              ▼
       Sandbox Agent Server
              │
       ┌──────┼───────┐
       ▼      ▼       ▼
     Shell   Files   Process
Runtime 上层永远不允许直接调用 Docker API。

3.2 SandboxProvider 接口
python
class SandboxProvider(Protocol):
    """Sandbox 提供者的统一接口，所有 Provider 必须实现。"""

    async def create(self, config: SandboxConfig) -> Sandbox:
        """创建一个新的 Sandbox 实例。"""
        ...

    async def start(self, sandbox_id: str) -> None:
        """启动指定的 Sandbox。"""
        ...

    async def exec(self, sandbox_id: str, request: ExecRequest) -> ExecResult:
        """在 Sandbox 内执行命令。"""
        ...

    async def read_file(self, sandbox_id: str, path: str) -> bytes:
        """读取 Sandbox 内的文件内容。"""
        ...

    async def write_file(self, sandbox_id: str, path: str, content: bytes) -> None:
        """写入文件到 Sandbox。"""
        ...

    async def kill(self, sandbox_id: str) -> None:
        """强制终止 Sandbox 内的所有进程。"""
        ...

    async def stop(self, sandbox_id: str) -> None:
        """优雅停止 Sandbox。"""
        ...

    async def destroy(self, sandbox_id: str) -> None:
        """销毁 Sandbox 及其占用的资源。"""
        ...
第一阶段只实现这些接口，不要提前加入 Snapshot、Migration、Network Proxy 等接口。

3.3 SandboxManager
SandboxManager 是 Runtime 唯一的 Sandbox 入口。

text
Agent / Tool
      │
      ▼
SandboxManager
      │
      ▼
SandboxProvider
职责：

创建 Sandbox

获取 Sandbox

生命周期管理

Provider 路由

Policy 校验

Execution 管理

Sandbox 与 Session / Workspace 关联

不负责：

Docker 细节

Shell 具体实现

Agent 逻辑

3.4 SandboxConfig
第一阶段：

python
@dataclass
class SandboxConfig:
    """Sandbox 创建配置。"""

    provider: str               # Provider 名称，如 "docker"
    image: str                  # 容器镜像
    workspace_id: str           # 关联的 Workspace ID
    policy: SandboxPolicy       # 安全策略
    resources: ResourcePolicy   # 资源限制
    environment: dict[str, str] # 环境变量
    timeout_seconds: int        # 默认执行超时（秒）
示例：

yaml
sandbox:
  provider: docker
  image: agent-runtime:python
  policy:
    filesystem: workspace_write
    network: disabled
  resources:
    cpu: 2
    memory: 4Gi
  timeout_seconds: 300
4. 分阶段设计
4.0 阶段总览
阶段	目标	实现
P1	能安全执行代码	Docker Sandbox
P2	Runtime 解耦 Sandbox	Sandbox Server + Execution
P3	精细安全控制	Filesystem + Network + Approval + OS Sandbox
P4	Agent 可恢复工作环境	Workspace Snapshot
P5	企业级强隔离	Firecracker / MicroVM
4.1 Phase 1：Docker Sandbox（基础安全执行）
目标
第一阶段只解决：

Agent 能够安全执行 Shell / Python / Node，并拥有独立 Workspace。

实现：

text
SandboxManager
      ↓
DockerProvider
      ↓
Docker Container
功能要求
必须支持：

生命周期

text
create
start
stop
kill
destroy
执行

text
exec(command)
支持 cwd、environment、timeout、stdin、stdout、stderr、exit_code。

文件

text
read_file
write_file
list_files
Workspace

text
/workspace
Sandbox Policy
只提供三个模式：

text
read_only
workspace_write
full_access
默认：

text
workspace_write
+
network_disabled
推荐：

text
/workspace     RW
/tmp           RW
其他文件系统   RO
敏感目录不得挂载。

Network
只支持：

text
disabled
enabled
默认 disabled。第一阶段不要实现复杂 Network Proxy，后续再增加 allowlist、proxy。

Resource Limits
至少支持：

text
CPU
Memory
Process Count
Execution Timeout
Disk
例如：

yaml
resources:
  cpu: 2
  memory: 4Gi
  pids: 256
  timeout: 300
避免 Agent 出现 fork bomb、无限循环、内存爆炸、CPU 占满等问题。

Workspace
Workspace 与 Sandbox 分离。

text
Workspace
     │
     ▼
Sandbox
推荐：

text
workspace_id
      ↓
host directory / Docker volume
      ↓
/workspace
不要让 Workspace 生命周期绑定 Docker Container。以后可以销毁 Sandbox 而保留 Workspace，供新的 Sandbox 继续使用。

数据库
新增 sandboxes 表：

sql
CREATE TABLE sandboxes (
    id UUID PRIMARY KEY,                -- Sandbox 唯一标识
    tenant_id UUID,                     -- 租户 ID（多租户场景，可选）
    session_id UUID,                    -- 所属 Session ID
    workspace_id UUID,                  -- 关联的 Workspace ID
    provider VARCHAR(32) NOT NULL,      -- Provider 名称（如 docker）
    provider_id TEXT,                   -- Provider 内部的资源 ID（如容器 ID）
    status VARCHAR(32) NOT NULL,        -- 状态：creating / running / stopped / destroyed
    image TEXT NOT NULL,                -- 使用的镜像名称
    policy JSONB NOT NULL,              -- 安全策略快照
    resource_policy JSONB NOT NULL,     -- 资源限制快照
    created_at TIMESTAMPTZ NOT NULL,    -- 创建时间
    started_at TIMESTAMPTZ,             -- 启动时间（可为空）
    stopped_at TIMESTAMPTZ,             -- 停止时间（可为空）
    metadata JSONB NOT NULL DEFAULT '{}' -- 扩展元数据
);

CREATE INDEX idx_sandboxes_session ON sandboxes(session_id);
CREATE INDEX idx_sandboxes_workspace ON sandboxes(workspace_id);
CREATE INDEX idx_sandboxes_status ON sandboxes(status);
Sandbox 与 Run 的关系
一个 Sandbox 可以服务多个 Run。

text
Session
   │
   └── Workspace
          │
          └── Sandbox
                │
                ├── Run 1
                ├── Run 2
                └── Run 3
默认在 Session / Workspace 生命周期内复用 Sandbox。

Sandbox 与 Sub Agent
第一阶段提供 isolated 和 shared 两种模式，默认 isolated。

text
Main Agent
   └── Sandbox A

Sub Agent
   └── Sandbox B
如果明确要求共享，则 Sub Agent 复用 Main Agent 的 Sandbox，但不要默认共享。

4.2 Phase 2：Sandbox Execution 与 Runtime 解耦
目标
将执行从 SandboxManager 直接 Docker exec 升级为独立的 Sandbox Server 架构，参考 OpenHands 的 Action Execution Server 模式。

text
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
Execution API
统一为：

text
POST /exec
GET  /files
GET  /files/{path}
PUT  /files/{path}
POST /process/{id}/kill
GET  /health
Runtime 不直接关心底层是 Docker、Pod 还是 VM，只关心 Sandbox API。

Sandbox Execution 数据库
增加 sandbox_executions 表：

sql
CREATE TABLE sandbox_executions (
    id UUID PRIMARY KEY,                -- 执行记录唯一标识
    sandbox_id UUID NOT NULL,           -- 所属 Sandbox ID
    run_id UUID,                        -- 关联的 Agent Run ID
    tool_call_id UUID,                  -- 关联的 Tool Call ID
    command TEXT,                       -- 执行的命令
    cwd TEXT,                           -- 工作目录
    status VARCHAR(32),                 -- 状态：pending / running / success / failed / killed
    exit_code INTEGER,                  -- 退出码（成功为 0）
    started_at TIMESTAMPTZ,             -- 开始时间
    completed_at TIMESTAMPTZ,           -- 完成时间
    stdout_ref TEXT,                    -- stdout 内容引用（可存对象存储）
    stderr_ref TEXT,                    -- stderr 内容引用
    metadata JSONB NOT NULL DEFAULT '{}' -- 扩展元数据
);

CREATE INDEX idx_sandbox_exec_sandbox ON sandbox_executions(sandbox_id);
CREATE INDEX idx_sandbox_exec_run ON sandbox_executions(run_id);
与 Conversation Persistence 集成
最终关系：

text
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
同时写入 Event：

text
sandbox.execution.started
sandbox.execution.completed
sandbox.permission.denied
sandbox.network.denied
sandbox.process.killed
这样可以完整追踪 Agent → Tool → Sandbox → Command → Result 的链路。

Runtime Plugin
Sandbox 本身也支持插件，参考 OpenHands Runtime Plugin：

text
Sandbox
  │
  ├── Shell
  ├── Python
  ├── Node
  ├── Browser
  ├── Jupyter
  └── Custom Plugin
插件接口定义：

python
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
插件安装方式
不要让 Plugin 自己直接操作 Docker。错误方式：Plugin → Docker API。正确方式：Plugin → Sandbox API → Sandbox。插件只知道 exec、read_file、write_file、expose_port。

4.3 Phase 3：细粒度安全控制与 OS Sandbox
细粒度 Sandbox Policy
从简单的 workspace_write 升级为结构化策略：

python
class SandboxPolicy:
    filesystem: FileSystemPolicy
    network: NetworkPolicy
    process: ProcessPolicy
    resources: ResourcePolicy
Filesystem Policy
支持 read、write、deny，并支持嵌套覆盖（子路径可以覆盖父路径）。

yaml
filesystem:
  rules:
    - path: /workspace
      access: write
    - path: /workspace/.git
      access: read
    - path: /workspace/.env
      access: deny
Codex 当前 Linux Sandbox 已经处理类似的 nested read-only / denied carve-out，因此这个抽象值得提前保留。

Network Policy
从 disabled / enabled 升级为：

text
disabled
full
allowlist
proxy
示例：

yaml
network:
  mode: allowlist
  domains:
    - github.com
    - pypi.org
    - npmjs.org
Approval Policy
独立实现，模式包括 never、on_request、always、rule_based。

yaml
approval:
  rules:
    - action: shell
      pattern: "rm -rf"
      policy: ask
    - action: network
      policy: ask
注意：Approval 是用户交互层，Sandbox Policy 是安全边界。

OS Sandbox Provider
增加 DockerProvider、LinuxSandboxProvider、MacOSSandboxProvider。Linux 优先研究 Bubblewrap、seccomp、Landlock，参考 Codex 的实现，但只实现 SandboxProvider 接口，让上层完全无感。

4.4 Phase 4 & 5：Workspace Snapshot 与 MicroVM
Phase 4: Workspace Snapshot
当需要 Branch、Fork、Retry、Time Travel、Resume 时，增加 WorkspaceSnapshot。

text
Workspace
    │
    ├── Snapshot 1
    │
    └── Snapshot 2
Fork 场景：

text
Branch A
   │
Workspace Snapshot
   │
   ├── Branch A
   │
   └── Branch B
不要复制整个 Sandbox。

Phase 5: MicroVM
只有真正需要多租户、强隔离、不可信代码、高并发、快速恢复时，再增加 FirecrackerProvider。

最终 Provider 集合：

text
SandboxProvider
├── DockerProvider
├── LinuxSandboxProvider
├── MacOSSandboxProvider
└── FirecrackerProvider
参考 E2B 的 Control Plane / Data Plane / Firecracker / Snapshot 架构。

5. 实施指南
5.1 第一阶段明确不做
Codex 实现时禁止提前实现：

text
❌ Firecracker
❌ Kubernetes
❌ VM Pool
❌ Network Proxy
❌ Landlock
❌ seccomp 自研规则
❌ Workspace Snapshot
❌ 分布式 Sandbox Scheduler
❌ 跨节点 Sandbox Migration
❌ 复杂 Approval Engine
第一阶段只有：

text
Docker
+
Workspace
+
SandboxManager
+
SandboxProvider
+
Shell
+
File
+
Process
+
Resource Limit
5.2 第一阶段验收标准
完成后必须可以：

创建 Sandbox：create() 返回 sandbox_id

执行 Shell：exec("python test.py") 返回 stdout、stderr、exit_code

文件操作：write_file()、read_file() 正常工作

Workspace 持久化：销毁 Sandbox A 后，新建 Sandbox B 仍能看到 Workspace

Runtime 重启恢复：重启后 Sandbox 状态可重新发现

Agent Run 关联：Run → Tool Call → Sandbox Execution 链路完整

Sub Agent 隔离：Main Agent 与 Sub Agent 各自拥有独立 Sandbox（默认）

安全限制验证：workspace 可写、workspace 外不可写、超时 kill、进程限制、network disabled、destroy 后无法继续执行

5.3 Codex 实施顺序
text
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
完成 Step 11 后才进入 Phase 2。

5.4 最终目录结构
第一阶段：

text
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
第二阶段：

text
sandbox/
├── interface.py
├── manager.py
├── models.py
├── policy.py
├── execution.py
├── workspace.py
├── providers/
│   └── docker/
├── server/
│   ├── api.py
│   └── executor.py
└── plugins/
第三阶段：

text
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
最终：

text
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
6. 总结：最终架构关系
最终形成：

text
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
结合 Conversation Persistence：

text
                         Agent Runtime
                              │
        ┌─────────────────────┼────────────────────┐
        │                     │                    │
        ▼                     ▼                    ▼
 Conversation             Agent Engine         Sandbox
 Persistence                   │                    │
        │                ┌─────┼─────┐             │
        │                │     │     │             │
        │              Tool  SubAgent LLM          │
        │                │     │                    │
        │                └─────┼────────────────────┘
        │                      │
        │                      ▼
        │                 SandboxManager
        │                      │
        │                 SandboxProvider
        │                      │
        │                      ▼
        │                  Workspace
        │
        └────────────── Event / Run / Tool Call
最终一次代码执行链路：

text
User → Turn → Run → Tool Call → SandboxManager → SandboxProvider
→ Sandbox → Execution → Result → Tool Result → LLM → Assistant
所有关键节点都进入统一 Event Store，使 Conversation Persistence、Agent Run、Tool、Sandbox 四个模块形成完整闭环，而不是各自保存一套孤立状态。