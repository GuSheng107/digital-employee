import { request, type ApiResponse } from './request'

export type DdlColumnType =
  | 'smallint'
  | 'integer'
  | 'bigint'
  | 'numeric'
  | 'boolean'
  | 'varchar'
  | 'text'
  | 'date'
  | 'timestamp'
  | 'timestamptz'
  | 'json'
  | 'jsonb'
  | 'uuid'

export interface DdlColumnDefinition {
  name: string
  type: DdlColumnType
  length?: number | null
  precision?: number | null
  scale?: number | null
  nullable: boolean
  primary_key: boolean
  default?: unknown
  comment: string
}

export interface DdlTableDefinition {
  schema_name: string
  table_name: string
  table_comment: string
  columns: DdlColumnDefinition[]
}

export interface DdlPreviewData {
  schema_name: string
  table_name: string
  table_identifier: string
  ddl: string
  execution_enabled: boolean
}

export interface DdlExecuteData extends DdlPreviewData {
  executed: boolean
}

export const ddlColumnTypes: DdlColumnType[] = [
  'smallint',
  'integer',
  'bigint',
  'numeric',
  'boolean',
  'varchar',
  'text',
  'date',
  'timestamp',
  'timestamptz',
  'json',
  'jsonb',
  'uuid',
]

export async function previewDdlTable(payload: DdlTableDefinition) {
  const { data } = await request.post<ApiResponse<DdlPreviewData>>(
    '/api/v1/ddl/tables/preview',
    payload,
  )
  return data
}

export async function executeDdlTable(payload: DdlTableDefinition) {
  const { data } = await request.post<ApiResponse<DdlExecuteData>>(
    '/api/v1/ddl/tables',
    payload,
  )
  return data
}
