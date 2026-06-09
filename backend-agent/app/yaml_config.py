from __future__ import annotations

"""YAML 配置加载与访问模块。

提供 YAML 配置文件的加载、合并、热重载和点号路径访问功能，
以线程安全的单例模式管理项目配置，支持默认值与用户自定义配置的深度合并。
"""

import threading
from pathlib import Path
from typing import Any

import yaml


# 默认配置值：当 config.yaml 不存在或某些配置项未设置时，使用这些默认值
_DEFAULTS: dict[str, Any] = {
    # 游客账号配置（可选）
    # enabled=true 后允许使用游客账号登录，游客仅可查看页面，无操作权限
    "guest_account": {
        "enabled": False,
        "username": "test",
        "password": "test123",
    },
    # 反馈告警配置：同一会话在指定窗口内连续收到多个无用反馈时通知管理员
    "feedback_alert": {
        "enabled": False,
        "threshold": 3,
        "window_minutes": 60,
        "cooldown_minutes": 30,
    },
    # 数据库相关配置
    "database": {
        # SQLite 数据库文件相对项目根目录的路径
        "path": "data/ai_database.db",
    },
    # 企业微信机器人相关配置
    "wecom_bot": {
        # 企业微信 WebSocket 服务地址
        "websocket_url": "wss://openws.work.weixin.qq.com",
        # 断开连接后重试间隔（毫秒）
        "reconnect_interval_ms": 1000,
        # WebSocket 心跳包发送间隔（毫秒）
        "heartbeat_interval_ms": 30000,
    },
    # 日志相关配置
    "logging": {
        # 日志级别：DEBUG/INFO/WARNING/ERROR/CRITICAL
        "level": "INFO",
    },
    # Agent/AI 相关配置
    "agent": {
        # 上下文总长度限制（字符数）：超过此值会触发上下文压缩
        "context_length_limit": 6000,
        # 上下文摘要最大字符数
        "summary_max_chars": 1200,
        # 压缩时使用的转录文本最大字符数
        "compression_transcript_max_chars": 8000,
        # 默认使用的 Agent 提供商
        "provider": "",
        # Agent 响应超时时间（秒）
        "timeout_seconds": 60,
        # Agent 最大工具调用迭代次数
        "max_iterations": 5,
        # 回复底部添加的 AI 生成提示
        "reply_notice": '--本回答由AI生成，请注意鉴别，必要时请@我说:"转人工"，我会帮您转接。',
        # 当 Agent 无法正常响应时返回的降级提示
        "fallback_text": "抱歉，我暂时无法回答您的问题，请联系管理员。",
        # Agent 输出的最大字符数
        "max_output_chars": 5000,
        # Agent 思考链的最大字符数
        "max_reasoning_chars": 10000,
        # 思考链因长度限制被截断时显示的提示文本
        "reasoning_truncation_notice": "[思考链已截断]",
        # 内容被截断时显示的提示文本
        "truncation_notice": "[内容已截断]",
        # 最大缓存条目数
        "max_cache_size": 10,
        # 流式输出的最大 chunk 数量
        "max_stream_chunks": 500,
        # 最近对话上下文的最大字符数
        "recent_context_max_chars": 1400,
        # 最近对话上下文的最大消息数
        "recent_context_max_messages": 6,
        # 获取历史消息时的倍数因子（用于筛选，实际返回数量会少于此值）
        "recent_context_fetch_multiplier": 2,
        # 单条消息的最大字符数
        "context_message_max_chars": 300,
        # 提示词中上下文摘要的最大字符数
        "summary_in_prompt_max_chars": 600,
        # 系统提示词的最大字符数
        "system_prompt_max_chars": 12000,
        # 单张图片的最大字节数（10MB）
        "max_image_bytes": 10485760,
        # 单个视频的最大字节数（1GB）
        "max_video_bytes": 1073741824,
        # 单个音频的最大字节数（20MB）
        "max_audio_bytes": 20971520,
        # 单个文件的最大字节数（50MB）
        "max_file_bytes": 52428800,
    },
    # 运行时相关配置
    "runtime": {
        # 最大并发请求数
        "max_concurrent_requests": 30,
        # 系统繁忙时返回给用户的提示文本
        "busy_reply_text": "当前业务繁忙，请稍候尝试",
        # 系统任务的最大并发数
        "max_system_task_concurrency": 10,
        # 是否在附件消息场景下允许 AI 文本回复
        "attachment_reply": False,
    },
    # 任务相关配置
    "task": {
        # 任务认领最大数量
        "claim_limit_max": 20,
        # 逾期周期倍数
        "overdue_cycle_multiplier": 2,
    },
    # 技能/工具相关配置
    "skills": {
        # ZIP 文件的最大字节数（10MB）
        "max_zip_bytes": 10485760,
        # ZIP 内单个文件的最大字节数（5MB）
        "max_single_file_bytes": 5242880,
        # ZIP 压缩包的最大文件数
        "max_zip_entries": 200,
        # 脚本输出的最大字符数
        "max_script_output_chars": 16000,
        # 工具描述的最大字符数
        "max_tool_description_chars": 1200,
    },
    # MCP（Model Context Protocol）相关配置
    "mcp": {
        # 工具事件 payload 的最大字符数
        "max_tool_event_payload_chars": 2000,
        # 工具结果的最大字符数
        "max_result_chars": 4000,
    },
    # 文档/知识库相关配置
    "doc": {
        # 允许上传的文件扩展名列表
        "allowed_extensions": [".doc", ".docx", ".txt", ".md", ".json", ".csv"],
        # 单个文档的最大文件大小（字节，10MB）
        "max_file_size": 10485760,
        # 文档提取文本的最大字符数（用于记忆提取）
        "max_characters": 5000,
    },
    # 记忆更新任务相关配置
    "memory_update": {
        # 单次记忆更新读取的最大问答对数量
        "max_pairs": 100,
        # 单次记忆更新读取的最大字符数
        "max_chars": 15000,
    },
    # 记忆检索相关配置
    "memory": {
        # 是否启用 LLM 查询扩展（语义泛化增强）
        "query_expansion": {
            "enabled": False,
        },
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """
    深度合并两个字典：将 override 的内容合并到 base 中
    如果某个键在两个字典中都存在且都是字典类型，则递归合并
    否则，override 的值会覆盖 base 的值
    
    Args:
        base: 基础字典（默认值）
        override: 覆盖字典（用户自定义值）
    
    Returns:
        合并后的新字典
    """
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _resolve_dot_path(data: dict, dot_path: str, default: Any = None) -> Any:
    """
    使用点号路径从嵌套字典中获取值
    例如：_resolve_dot_path(data, "agent.context_length_limit")
    
    Args:
        data: 嵌套字典数据
        dot_path: 点号分隔的路径字符串
        default: 路径不存在时返回的默认值
    
    Returns:
        路径对应的值，或默认值
    """
    keys = dot_path.split(".")
    current: Any = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current


def _set_dot_path(data: dict, dot_path: str, value: Any) -> None:
    """
    使用点号路径设置嵌套字典中的值
    例如：_set_dot_path(data, "agent.context_length_limit", 20000)
    
    Args:
        data: 嵌套字典数据
        dot_path: 点号分隔的路径字符串
        value: 要设置的值
    """
    keys = dot_path.split(".")
    current = data
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


class YamlConfigManager:
    """
    YAML 配置文件管理器
    功能：
    1. 自动读取和合并默认配置与用户配置
    2. 支持配置文件热重载（检测文件修改时间自动重新加载）
    3. 线程安全的读写操作
    4. 支持点号路径访问（如 "agent.context_length_limit"）
    """
    
    def __init__(self, config_path: Path) -> None:
        """
        初始化配置管理器
        
        Args:
            config_path: YAML 配置文件的路径
        """
        self._path = config_path
        self._data: dict[str, Any] = {}
        self._mtime: float = 0.0
        self._lock = threading.Lock()
        self._ensure_file()
        self._load()

    def _ensure_file(self) -> None:
        """
        确保配置文件存在
        如果不存在，则创建包含默认值的配置文件
        """
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._write_yaml(_DEFAULTS)

    def _read_mtime(self) -> float:
        """
        读取配置文件的最后修改时间
        
        Returns:
            文件修改时间戳（秒），读取失败时返回 0.0
        """
        try:
            return self._path.stat().st_mtime
        except OSError:
            return 0.0

    def _load(self) -> None:
        """
        加载配置文件并与默认值合并
        """
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            raw = {}
        self._data = _deep_merge(_DEFAULTS, raw)
        self._mtime = self._read_mtime()

    def _check_reload(self) -> None:
        """
        检查配置文件是否被修改，如果是则重新加载
        """
        current_mtime = self._read_mtime()
        if current_mtime != self._mtime:
            self._load()

    def _write_yaml(self, data: dict[str, Any]) -> None:
        """
        将数据写入 YAML 文件
        
        Args:
            data: 要写入的数据字典
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    def get(self, dot_path: str, default: Any = None) -> Any:
        """
        获取配置值（线程安全）
        
        Args:
            dot_path: 点号分隔的配置路径，例如 "agent.context_length_limit"
            default: 配置不存在时返回的默认值
        
        Returns:
            配置值
        """
        with self._lock:
            self._check_reload()
            return _resolve_dot_path(self._data, dot_path, default)

    def set(self, dot_path: str, value: Any) -> None:
        """
        设置配置值（仅内存中修改，需调用 save() 持久化）
        
        Args:
            dot_path: 点号分隔的配置路径
            value: 要设置的值
        """
        with self._lock:
            self._check_reload()
            _set_dot_path(self._data, dot_path, value)

    def save(self) -> None:
        """
        将当前内存中的配置保存到文件
        """
        with self._lock:
            self._write_yaml(self._data)
            self._mtime = self._read_mtime()

    def as_dict(self) -> dict[str, Any]:
        """
        获取完整的配置字典（副本）
        
        Returns:
            配置数据的完整副本
        """
        with self._lock:
            self._check_reload()
            return dict(self._data)

    def reload(self) -> None:
        """
        强制重新加载配置文件
        """
        with self._lock:
            self._load()


# 按项目根目录缓存的 YamlConfigManager 实例
_instances: dict[str, YamlConfigManager] = {}
_instances_lock = threading.Lock()


def get_yaml_config(project_root: Path | None = None) -> YamlConfigManager:
    """
    获取指定项目根目录的配置管理器实例（单例模式）
    
    Args:
        project_root: 项目根目录路径，如果为 None 则使用当前工作目录
    
    Returns:
        YamlConfigManager 实例
    """
    root = (project_root or Path.cwd()).resolve()
    key = str(root)
    with _instances_lock:
        if key not in _instances:
            config_path = root / "config.yaml"
            _instances[key] = YamlConfigManager(config_path)
        return _instances[key]
