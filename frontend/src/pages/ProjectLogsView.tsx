import { useEffect, useState, useCallback, useRef } from 'react';
import { Card, Table, Tag, Button, Select, Input, DatePicker, Modal, Descriptions, message, Space } from 'antd';
import { SearchOutlined, CopyOutlined } from '@ant-design/icons';
import { getProjectLogs } from '@/api/system';
import { formatTime } from '@/utils/format';
import type { ColumnsType } from 'antd/es/table';

const { RangePicker } = DatePicker;

interface LogEntry {
  level: string;
  category: string;
  trace_id: string;
  source: string;
  error_code?: string;
  created_at: string;
  message: string;
  detail?: string;
}

const CATEGORY_LABELS: Record<string, string> = {
  system: '系统', network: '网络', ai: 'AI', task: '任务',
  data: '数据', bot: 'Bot', media: '媒体', message: '消息',
};

function levelColor(level: string): string {
  const m: Record<string, string> = { ERROR: 'red', WARNING: 'orange', INFO: 'blue', DEBUG: 'default' };
  return m[level] || 'default';
}

function categoryColor(cat: string): string {
  const m: Record<string, string> = { system: 'blue', network: 'orange', ai: 'green', task: 'blue', data: 'default', bot: 'red', media: 'orange', message: 'blue' };
  return m[cat] || 'blue';
}

export default function ProjectLogsView() {
  const [loading, setLoading] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [category, setCategory] = useState('');
  const [level, setLevel] = useState('');
  const [traceId, setTraceId] = useState('');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [detailVisible, setDetailVisible] = useState(false);
  const [currentDetail, setCurrentDetail] = useState<LogEntry | null>(null);

  const fetchLogs = useCallback(async (p: number, ps: number) => {
    setLoading(true);
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result: any = await getProjectLogs({
        category, level, trace_id: traceId, start_time: startTime, end_time: endTime,
        page: p, page_size: ps,
      });
      setLogs(result.logs || []);
      setTotal(result.total || 0);
      setPage(result.page || 1);
      setPageSize(result.page_size || 20);
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [category, level, traceId, startTime, endTime]);

  const initialLoadDone = useRef(false);
  useEffect(() => {
    if (!initialLoadDone.current) {
      initialLoadDone.current = true;
      fetchLogs(1, 20);
    }
  }, [fetchLogs]);

  const handleSearch = () => { fetchLogs(1, pageSize); };

  const copyDetail = async () => {
    if (!currentDetail?.detail) { message.warning('没有可复制的内容'); return; }
    try {
      await navigator.clipboard.writeText(currentDetail.detail);
      message.success('复制成功');
    } catch { message.error('复制失败'); }
  };

  const columns: ColumnsType<LogEntry> = [
    { title: '行号', render: (_, __, i) => (page - 1) * pageSize + i + 1, width: 80, align: 'center' },
    { title: '级别', dataIndex: 'level', width: 100, render: (v: string) => <Tag color={levelColor(v)}>{v}</Tag> },
    { title: '类型', dataIndex: 'category', width: 110, render: (v: string) => <Tag color={categoryColor(v)}>{CATEGORY_LABELS[v] || v || '系统'}</Tag> },
    { title: 'TraceId', dataIndex: 'trace_id', ellipsis: true, minWidth: 240 },
    { title: '来源', dataIndex: 'source', ellipsis: true, minWidth: 180, render: (v: string, r: LogEntry) => r.error_code ? <>{v} <Tag color="red" style={{ marginLeft: 8 }}>{r.error_code}</Tag></> : v },
    { title: '创建时间', dataIndex: 'created_at', width: 200, render: (v: string) => formatTime(v) },
    { title: '信息', dataIndex: 'message', ellipsis: true, minWidth: 200 },
    { title: '操作', width: 100, fixed: 'right', render: (_, r) => <Button type="link" size="small" onClick={() => { setCurrentDetail(r); setDetailVisible(true); }}>查看详情</Button> },
  ];

  return (
    <section>
      <Card className="panel" title={<div className="panel-title"><span>日志查询</span></div>}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 16, alignItems: 'center' }}>
          <Space wrap>
            <span>日志类型:</span>
            <Select value={category || undefined} placeholder="请选择" allowClear style={{ width: 140 }}
              onChange={(v) => setCategory(v || '')}
              options={Object.entries(CATEGORY_LABELS).map(([k, v]) => ({ value: k, label: v }))} />
            <span>TraceId:</span>
            <Input value={traceId} placeholder="请输入 TraceId" allowClear style={{ width: 180 }}
              onChange={(e) => setTraceId(e.target.value)} />
            <span>日志级别:</span>
            <Select value={level || undefined} placeholder="请选择" allowClear style={{ width: 140 }}
              onChange={(v) => setLevel(v || '')}
              options={['ERROR', 'WARNING', 'INFO'].map((v) => ({ value: v, label: v }))} />
            <span>时间范围:</span>
            <RangePicker showTime format="YYYY-MM-DDTHH:mm:ssZ" style={{ width: 380 }}
              onChange={(dates) => { setStartTime(dates?.[0] ? dates[0].format('YYYY-MM-DDTHH:mm:ssZ') : ''); setEndTime(dates?.[1] ? dates[1].format('YYYY-MM-DDTHH:mm:ssZ') : ''); }} />
            <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>查询</Button>
          </Space>
        </div>

        <Table<LogEntry> columns={columns} dataSource={logs} rowKey={(_, i) => String(i)}
          loading={loading} size="small" scroll={{ x: 1200 }}
          pagination={{
            total, current: page, pageSize, pageSizeOptions: ['10', '20', '50', '100'],
            showSizeChanger: true, showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => fetchLogs(p, ps),
          }} />
      </Card>

      <Modal title="日志详情" open={detailVisible} onCancel={() => setDetailVisible(false)} footer={<Button onClick={() => setDetailVisible(false)}>关闭</Button>} width={900}>
        {currentDetail && (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="级别"><Tag color={levelColor(currentDetail.level)}>{currentDetail.level}</Tag></Descriptions.Item>
            <Descriptions.Item label="类型"><Tag color={categoryColor(currentDetail.category)}>{CATEGORY_LABELS[currentDetail.category] || currentDetail.category}</Tag></Descriptions.Item>
            <Descriptions.Item label="TraceId">{currentDetail.trace_id}</Descriptions.Item>
            <Descriptions.Item label="来源">{currentDetail.error_code ? `${currentDetail.source} (错误码: ${currentDetail.error_code})` : currentDetail.source}</Descriptions.Item>
            <Descriptions.Item label="创建时间">{formatTime(currentDetail.created_at)}</Descriptions.Item>
            <Descriptions.Item label="信息">{currentDetail.message}</Descriptions.Item>
            {currentDetail.detail && (
              <Descriptions.Item label={<span>详情 <Button type="link" size="small" icon={<CopyOutlined />} onClick={copyDetail}>复制</Button></span>}>
                <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', maxHeight: 400, overflow: 'auto', background: '#f5f5f5', padding: 12, borderRadius: 6, fontSize: 12, margin: 0 }}>
                  {currentDetail.detail}
                </pre>
              </Descriptions.Item>
            )}
          </Descriptions>
        )}
      </Modal>
    </section>
  );
}
