import { Descriptions, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import styles from '../index.module.css';
import type { SystemConfigRow } from '../types/system';

export interface SystemConfigTableProps {
  rows: SystemConfigRow[];
}

export default function SystemConfigTable({ rows }: SystemConfigTableProps) {
  const columns: ColumnsType<SystemConfigRow> = [
    { title: '配置分组', dataIndex: 'group', width: 180 },
    {
      title: '脱敏配置',
      dataIndex: 'values',
      render: (values: Record<string, unknown>) => (
        <Descriptions column={3} size="small" bordered>
          {Object.entries(values).map(([key, value]) => (
            <Descriptions.Item key={key} label={key}>
              {String(value)}
            </Descriptions.Item>
          ))}
        </Descriptions>
      ),
    },
  ];

  return <Table className={styles.configTable} rowKey="group" columns={columns} dataSource={rows} pagination={false} bordered />;
}
