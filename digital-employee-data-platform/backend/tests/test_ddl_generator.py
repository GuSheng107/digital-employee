import pytest
from fastapi import HTTPException

from app.schemas.ddl import DdlColumnDefinition, DdlTableDefinition
from app.services.ddl_generator import DdlValidationError, build_create_table_sql
from app.services.ddl_service import DdlService


def make_table(**overrides):
    payload = {
        "schema_name": "public",
        "table_name": "employee_profile",
        "table_comment": "employee profile table",
        "columns": [
            DdlColumnDefinition(
                name="id",
                type="uuid",
                nullable=False,
                primary_key=True,
                default="gen_random_uuid()",
                comment="primary key",
            ),
            DdlColumnDefinition(
                name="name",
                type="varchar",
                length=100,
                nullable=False,
                default="unknown",
                comment="display name",
            ),
            DdlColumnDefinition(
                name="metadata",
                type="jsonb",
                nullable=False,
                default={},
            ),
        ],
    }
    payload.update(overrides)
    return DdlTableDefinition(**payload)


def test_build_create_table_sql_is_deterministic():
    ddl = build_create_table_sql(make_table())

    assert 'CREATE TABLE "public"."employee_profile"' in ddl
    assert '"id" uuid NOT NULL DEFAULT gen_random_uuid()' in ddl
    assert '"name" varchar(100) NOT NULL DEFAULT \'unknown\'' in ddl
    assert '"metadata" jsonb NOT NULL DEFAULT \'{}\'' in ddl
    assert 'CONSTRAINT "pk_employee_profile" PRIMARY KEY ("id")' in ddl
    assert "COMMENT ON TABLE" in ddl
    assert "COMMENT ON COLUMN" in ddl


def test_rejects_injection_identifier():
    table = make_table(table_name="bad;drop_table")

    with pytest.raises(DdlValidationError):
        build_create_table_sql(table)


def test_rejects_duplicate_columns():
    with pytest.raises(ValueError):
        make_table(
            columns=[
                DdlColumnDefinition(name="id", type="integer", nullable=False),
                DdlColumnDefinition(name="ID", type="integer", nullable=False),
            ]
        )


def test_rejects_default_sql_injection():
    table = make_table(
        columns=[
            DdlColumnDefinition(
                name="created_at",
                type="timestamptz",
                nullable=False,
                default="now(); drop table users;",
            )
        ]
    )

    with pytest.raises(DdlValidationError):
        build_create_table_sql(table)


def test_preview_does_not_require_database():
    preview = DdlService().preview(make_table())

    assert preview.table_name == "employee_profile"
    assert preview.ddl.startswith('CREATE TABLE "public"."employee_profile"')


def test_execute_is_disabled_by_default():
    with pytest.raises(HTTPException) as exc_info:
        DdlService().execute(make_table())

    assert exc_info.value.status_code == 403
