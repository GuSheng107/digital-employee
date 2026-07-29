"""backend-data 业务与基础设施统一事件接入。"""

from observability import TraceEventType, traced_class

from app.core.minio_client import MinioClientWrapper
from app.core.redis_client import RedisClientWrapper
from app.services.cache_service import CacheService
from app.services.data_item_service import DataItemService
from app.services.identity_auth_service import IdentityAuthService
from app.services.identity_invite_code_service import InviteCodeService
from app.services.identity_menu_service import MenuService
from app.services.identity_permission_service import PermissionService
from app.services.identity_role_service import RoleService
from app.services.identity_session_service import IdentitySessionService
from app.services.identity_user_service import UserService
from app.services.message_broker_service import MessageBrokerService
from app.services.storage_service import StorageService

DATA_BUSINESS_SERVICES = (
    DataItemService,
    IdentityAuthService,
    InviteCodeService,
    MenuService,
    PermissionService,
    RoleService,
    IdentitySessionService,
    UserService,
    MessageBrokerService,
)


def configure_business_observability() -> None:
    """为数据服务业务和基础设施公开方法追加结构化事件。"""
    business_decorator = traced_class(TraceEventType.BUSINESS_OPERATION)
    for service_class in DATA_BUSINESS_SERVICES:
        business_decorator(service_class)
    traced_class(TraceEventType.REDIS)(RedisClientWrapper)
    traced_class(TraceEventType.MINIO)(MinioClientWrapper)
    traced_class(TraceEventType.REDIS)(CacheService)
    traced_class(TraceEventType.MINIO)(StorageService)
