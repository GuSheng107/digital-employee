from app.core.config import settings
from app.core.database import DatabaseRole
from app.main import app


def test_openapi_does_not_expose_ddl_routes():
    paths = app.openapi()["paths"]

    assert all("/ddl" not in path for path in paths)


def test_public_config_does_not_expose_ddl_config():
    public_config = settings.public_config()

    assert "ddl" not in public_config


def test_database_roles_are_read_write_business_roles_only():
    assert {role.value for role in DatabaseRole} == {"core", "vector"}


def test_service_uses_non_conflicting_default_port():
    assert settings.app_port == 8010


def test_service_has_no_auto_create_tables_setting():
    assert not hasattr(settings, "auto_create_tables")
