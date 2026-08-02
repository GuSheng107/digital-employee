import { Descriptions, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import styles from '../index.module.css';
import type { SystemConfigRow } from '../types/system';

export interface SystemConfigTableProps {
  rows: SystemConfigRow[];
}

/** 渲染配置值：原始类型直接展示，对象/数组用 JSON.stringify 保留可读结构 */
function renderConfigValue(value: unknown): React.ReactNode {
  if (value === null || value === undefined) {
    return '-';
  }
  if (typeof value === 'object') {
    return <pre className={styles.configValuePre}>{JSON.stringify(value, null, 2)}</pre>;
  }
  return String(value);
}

export default function SystemConfigTable({ rows }: SystemConfigTableProps): React.ReactElement {
  const columns: ColumnsType<SystemConfigRow> = [
    { title: '配置分组', dataIndex: 'group', width: 180 },
    {
      title: '脱敏配置',
      dataIndex: 'values',
      render: (values: Record<string, unknown>) => (
        <Descriptions column={3} size="small" bordered>
          {Object.entries(values).map(([key, value]) => (
            <Descriptions.Item key={key} label={key}>
              {renderConfigValue(value)}
            </Descriptions.Item>
          ))}
        </Descriptions>
      ),
    },
  ];

  return <Table className={styles.configTable} rowKey="group" columns={columns} dataSource={rows} pagination={false} bordered />;
}
