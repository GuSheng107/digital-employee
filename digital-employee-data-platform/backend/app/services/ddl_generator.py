import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.core.config import settings
from app.schemas.ddl import DdlColumnDefinition, DdlTableDefinition


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")

INTEGER_TYPES = {"smallint", "integer", "bigint"}
TIMESTAMP_TYPES = {"timestamp", "timestamptz"}
ALLOWED_DEFAULT_EXPRESSIONS = {
    "uuid": {"gen_random_uuid()", "uuid_generate_v4()"},
    "timestamp": {"now()", "current_timestamp"},
    "timestamptz": {"now()", "current_timestamp"},
    "date": {"current_date"},
}


class DdlValidationError(ValueError):
    pass


def validate_identifier(value: str, label: str) -> None:
    if not IDENTIFIER_RE.fullmatch(value):
        raise DdlValidationError(
            f"{label} must match ^[A-Za-z_][A-Za-z0-9_]{{0,62}}$"
        )


def quote_identifier(value: str) -> str:
    validate_identifier(value, "identifier")
    return f'"{value}"'


def quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_table_identifier(table: DdlTableDefinition) -> str:
    return f"{quote_identifier(table.schema_name)}.{quote_identifier(table.table_name)}"


def validate_table_definition(table: DdlTableDefinition) -> None:
    validate_identifier(table.schema_name, "schema_name")
    validate_identifier(table.table_name, "table_name")

    allowed_schemas = settings.ddl_allowed_schemas_list or ["public"]
    if table.schema_name not in allowed_schemas:
        raise DdlValidationError(
            f"schema_name must be one of: {', '.join(allowed_schemas)}"
        )

    seen: set[str] = set()
    for column in table.columns:
        validate_identifier(column.name, "column name")
        normalized = column.name.lower()
        if normalized in seen:
            raise DdlValidationError(f"duplicate column name: {column.name}")
        seen.add(normalized)


def build_column_type(column: DdlColumnDefinition) -> str:
    if column.type == "varchar":
        return f"varchar({column.length})"
    if column.type == "numeric" and column.precision is not None:
        if column.scale is not None:
            return f"numeric({column.precision},{column.scale})"
        return f"numeric({column.precision})"
    return column.type


def build_default_sql(column: DdlColumnDefinition) -> str | None:
    if column.default is None:
        return None

    value = column.default
    column_type = column.type

    if isinstance(value, str):
        stripped = value.strip()
        lower = stripped.lower()
        if lower in ALLOWED_DEFAULT_EXPRESSIONS.get(column_type, set()):
            return stripped

    if column_type in INTEGER_TYPES:
        if isinstance(value, bool) or not isinstance(value, int):
            raise DdlValidationError(f"default for {column.name} must be an integer")
        return str(value)

    if column_type == "numeric":
        if isinstance(value, bool) or not isinstance(value, int | float | Decimal):
            raise DdlValidationError(f"default for {column.name} must be numeric")
        return str(value)

    if column_type == "boolean":
        if not isinstance(value, bool):
            raise DdlValidationError(f"default for {column.name} must be boolean")
        return "true" if value else "false"

    if column_type in {"varchar", "text"}:
        if not isinstance(value, str):
            raise DdlValidationError(f"default for {column.name} must be a string")
        return quote_literal(value)

    if column_type == "uuid":
        if isinstance(value, str):
            try:
                UUID(value)
            except ValueError as exc:
                raise DdlValidationError(
                    f"default for {column.name} must be a UUID or allowed expression"
                ) from exc
            return quote_literal(value)
        raise DdlValidationError(
            f"default for {column.name} must be a UUID string or allowed expression"
        )

    if column_type == "date":
        if isinstance(value, str):
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise DdlValidationError(
                    f"default for {column.name} must be ISO date or allowed expression"
                ) from exc
            return quote_literal(value)
        if isinstance(value, date):
            return quote_literal(value.isoformat())
        raise DdlValidationError(f"default for {column.name} must be a date string")

    if column_type in TIMESTAMP_TYPES:
        if isinstance(value, str):
            try:
                datetime.fromisoformat(value)
            except ValueError as exc:
                raise DdlValidationError(
                    f"default for {column.name} must be ISO timestamp or allowed expression"
                ) from exc
            return quote_literal(value)
        if isinstance(value, datetime):
            return quote_literal(value.isoformat())
        raise DdlValidationError(f"default for {column.name} must be timestamp string")

    if column_type in {"json", "jsonb"}:
        try:
            return quote_literal(json.dumps(value, ensure_ascii=False))
        except TypeError as exc:
            raise DdlValidationError(f"default for {column.name} must be JSON") from exc

    raise DdlValidationError(f"default is not supported for {column.name}")


def build_create_table_sql(table: DdlTableDefinition) -> str:
    validate_table_definition(table)

    column_lines: list[str] = []
    primary_key_columns: list[str] = []
    for column in table.columns:
        parts = [quote_identifier(column.name), build_column_type(column)]
        if not column.nullable or column.primary_key:
            parts.append("NOT NULL")
        default_sql = build_default_sql(column)
        if default_sql is not None:
            parts.extend(["DEFAULT", default_sql])
        column_lines.append("    " + " ".join(parts))
        if column.primary_key:
            primary_key_columns.append(quote_identifier(column.name))

    if primary_key_columns:
        constraint_name = f"pk_{table.table_name}"
        column_lines.append(
            "    "
            + f"CONSTRAINT {quote_identifier(constraint_name)} "
            + f"PRIMARY KEY ({', '.join(primary_key_columns)})"
        )

    ddl_parts = [
        f"CREATE TABLE {build_table_identifier(table)} (\n"
        + ",\n".join(column_lines)
        + "\n);"
    ]

    if table.table_comment:
        ddl_parts.append(
            f"COMMENT ON TABLE {build_table_identifier(table)} "
            f"IS {quote_literal(table.table_comment)};"
        )

    for column in table.columns:
        if column.comment:
            ddl_parts.append(
                f"COMMENT ON COLUMN {build_table_identifier(table)}."
                f"{quote_identifier(column.name)} IS {quote_literal(column.comment)};"
            )

    return "\n".join(ddl_parts)
