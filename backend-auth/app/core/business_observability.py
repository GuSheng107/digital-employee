"""backend-auth 业务服务统一事件接入。"""

from observability import TraceEventType, traced_class

from app.services.auth_service import AuthService
from app.services.invite_code_service import InviteCodeService
from app.services.menu_service import MenuService
from app.services.permission_service import PermissionService
from app.services.role_service import RoleService
from app.services.user_service import UserService

AUTHENTICATION_SERVICES = (AuthService,)

AUTH_BUSINESS_SERVICES = (
    UserService,
    RoleService,
    MenuService,
    PermissionService,
    InviteCodeService,
)


def configure_business_observability() -> None:
    """为认证中心公开业务方法统一追加结构化事件。"""
    authentication_decorator = traced_class(TraceEventType.AUTHENTICATION)
    for service_class in AUTHENTICATION_SERVICES:
        authentication_decorator(service_class)

    decorator = traced_class(TraceEventType.BUSINESS_OPERATION)
    for service_class in AUTH_BUSINESS_SERVICES:
        decorator(service_class)
