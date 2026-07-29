import { useEffect, useRef, useState } from 'react';
import { Button, Table, Tag, Typography } from 'antd';
import dayjs from 'dayjs';
import type { ColumnsType } from 'antd/es/table';
import type { TraceRecord } from '../types/observability';
import { createTablePagination } from '@/utils/table-pagination';
import {
  CALL_STATUS_COLORS,
  CALL_STATUS_LABELS,
  TRACE_SERVICE_LABELS,
  TRACE_TRIGGER_LABELS,
} from '../constants/observability';
import styles from '../index.module.css';

const TABLE_CHROME_HEIGHT = 116;
const MINIMUM_TABLE_BODY_HEIGHT = 96;

interface TraceSummaryTableProps {
  items: TraceRecord[];
  loading: boolean;
  total: number;
  page: number;
  pageSize: number;
  onPageChange: (page: number, pageSize: number) => void;
  onOpen: (trace: TraceRecord) => void;
}

export default function TraceSummaryTable({
  items,
  loading,
  total,
  page,
  pageSize,
  onPageChange,
  onOpen,
}: TraceSummaryTableProps): React.ReactElement {
  const viewportRef = useRef<HTMLDivElement>(null);
  const [tableBodyHeight, setTableBodyHeight] = useState(
    MINIMUM_TABLE_BODY_HEIGHT,
  );

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return undefined;

    const updateHeight = (): void => {
      setTableBodyHeight(Math.max(
        MINIMUM_TABLE_BODY_HEIGHT,
        viewport.clientHeight - TABLE_CHROME_HEIGHT,
      ));
    };
    updateHeight();
    const observer = new ResizeObserver(updateHeight);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, []);

  const columns: ColumnsType<TraceRecord> = [
    {
      title: '开始时间',
      dataIndex: 'started_at',
      width: 220,
      align: 'center',
      render: (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm:ss.SSS'),
    },
    {
      title: 'Trace ID',
      dataIndex: 'trace_id',
      width: 340,
      align: 'center',
      ellipsis: true,
      render: (value: string) => (
        <Typography.Text copyable={{ text: value }} ellipsis={{ tooltip: value }}>
          {value}
        </Typography.Text>
      ),
    },
    {
      title: '触发来源',
      dataIndex: 'trigger',
      width: 120,
      align: 'center',
      render: (value: string) => TRACE_TRIGGER_LABELS[value] ?? value,
    },
    {
      title: '入口服务',
      dataIndex: 'root_service',
      width: 120,
      align: 'center',
      render: (value: string) => TRACE_SERVICE_LABELS[value] ?? value,
    },
    {
      title: '请求操作',
      dataIndex: 'name',
      width: 360,
      align: 'center',
      ellipsis: true,
    },
    {
      title: '调用状态',
      dataIndex: 'call_status',
      width: 90,
      align: 'center',
      render: (value: TraceRecord['call_status']) => (
        <Tag color={CALL_STATUS_COLORS[value]}>
          {CALL_STATUS_LABELS[value]}
        </Tag>
      ),
    },
    {
      title: '耗时',
      dataIndex: 'duration_ms',
      width: 110,
      align: 'center',
      render: (value: number) => `${value} ms`,
    },
    {
      title: '操作',
      key: 'action',
      fixed: 'right',
      width: 110,
      align: 'center',
      render: (_, record) => (
        <Button type="link" onClick={() => onOpen(record)}>
          查看链路
        </Button>
      ),
    },
  ];

  return (
    <div ref={viewportRef} className={styles.tableViewport}>
      <Table<TraceRecord>
        rowKey="trace_id"
        columns={columns}
        dataSource={items}
        loading={loading}
        sticky
        scroll={{ x: 1480, y: tableBodyHeight }}
        pagination={createTablePagination({
          current: page,
          pageSize,
          total,
          onChange: onPageChange,
        })}
      />
    </div>
  );
}
