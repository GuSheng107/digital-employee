"""统一链路日志使用的静态枚举。"""

from enum import StrEnum


class TraceTrigger(StrEnum):
    """链路的入口触发来源。"""

    FRONTEND_HTTP = "frontend_http"
    INTERNAL_HTTP = "internal_http"
    PLATFORM_CALLBACK = "platform_callback"
    MESSAGE_QUEUE = "message_queue"
    SCHEDULED_TASK = "scheduled_task"
    SYSTEM_LIFECYCLE = "system_lifecycle"


class TraceService(StrEnum):
    """参与链路的服务。"""

    FRONTEND = "frontend"
    BACKEND_AUTH = "backend_auth"
    BACKEND_DATA = "backend_data"
    BACKEND_GATEWAY = "backend_gateway"
    BACKEND_AGENT = "backend_agent"


class SpanKind(StrEnum):
    """Span 类型。"""

    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"
    INTERNAL = "internal"


class TraceStatus(StrEnum):
    """链路与 Span 状态。"""

    SUCCESS = "success"
    ERROR = "error"
    DENIED = "denied"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class TraceLevel(StrEnum):
    """日志事件级别。"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class TraceCallStatus(StrEnum):
    """面向查询与展示的互斥调用状态。"""

    SUCCESS = "success"
    WARNING = "warning"
    FAILURE = "failure"


class TraceEventType(StrEnum):
    """日志事件分类。"""

    HTTP_REQUEST = "http_request"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    BUSINESS_OPERATION = "business_operation"
    DATABASE = "database"
    REDIS = "redis"
    MINIO = "minio"
    MQ_PUBLISH = "mq_publish"
    MQ_CONSUME = "mq_consume"
    EXTERNAL_API = "external_api"
    AI_MODEL = "ai_model"
    EXCEPTION = "exception"


class TracePayloadType(StrEnum):
    """完整载荷分类。"""

    HTTP_REQUEST_BODY = "http_request_body"
    HTTP_RESPONSE_BODY = "http_response_body"
    IM_MESSAGE = "im_message"
    MQ_MESSAGE = "mq_message"
    MODEL_INPUT = "model_input"
    MODEL_OUTPUT = "model_output"
    EXTERNAL_REQUEST = "external_request"
    EXTERNAL_RESPONSE = "external_response"
    FILE_METADATA = "file_metadata"
