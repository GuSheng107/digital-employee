from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


SUPPORTED_DDL_TYPES = {
    "smallint",
    "integer",
    "bigint",
    "numeric",
    "boolean",
    "varchar",
    "text",
    "date",
    "timestamp",
    "timestamptz",
    "json",
    "jsonb",
    "uuid",
}


class DdlColumnDefinition(BaseModel):
    name: str = Field(min_length=1, max_length=63)
    type: Literal[
        "smallint",
        "integer",
        "bigint",
        "numeric",
        "boolean",
        "varchar",
        "text",
        "date",
        "timestamp",
        "timestamptz",
        "json",
        "jsonb",
        "uuid",
    ]
    length: int | None = None
    precision: int | None = None
    scale: int | None = None
    nullable: bool = True
    primary_key: bool = False
    default: Any = None
    comment: str = ""

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        return str(value).strip().lower()

    @model_validator(mode="after")
    def validate_shape(self) -> "DdlColumnDefinition":
        if self.primary_key and self.nullable:
            raise ValueError("primary key column cannot be nullable")

        if self.type == "varchar":
            if self.length is None or not 1 <= self.length <= 10000:
                raise ValueError("varchar length must be between 1 and 10000")
            if self.precision is not None or self.scale is not None:
                raise ValueError("varchar does not accept precision or scale")
        elif self.type == "numeric":
            if self.length is not None:
                raise ValueError("numeric does not accept length")
            if self.precision is not None and not 1 <= self.precision <= 1000:
                raise ValueError("numeric precision must be between 1 and 1000")
            if self.scale is not None:
                if self.precision is None:
                    raise ValueError("numeric scale requires precision")
                if not 0 <= self.scale <= self.precision:
                    raise ValueError("numeric scale must be between 0 and precision")
        else:
            if self.length is not None or self.precision is not None or self.scale is not None:
                raise ValueError(f"{self.type} does not accept length, precision, or scale")

        return self


class DdlTableDefinition(BaseModel):
    schema_name: str = Field(default="public", min_length=1, max_length=63)
    table_name: str = Field(min_length=1, max_length=63)
    table_comment: str = ""
    columns: list[DdlColumnDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_columns(self) -> "DdlTableDefinition":
        seen: set[str] = set()
        primary_keys = 0
        for column in self.columns:
            normalized = column.name.lower()
            if normalized in seen:
                raise ValueError(f"duplicate column name: {column.name}")
            seen.add(normalized)
            if column.primary_key:
                primary_keys += 1

        if primary_keys > len(self.columns):
            raise ValueError("invalid primary key configuration")
        return self


class DdlPreviewData(BaseModel):
    schema_name: str
    table_name: str
    table_identifier: str
    ddl: str
    execution_enabled: bool


class DdlExecuteData(DdlPreviewData):
    executed: bool
