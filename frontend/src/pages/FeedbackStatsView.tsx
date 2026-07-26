import { useEffect, useState, useCallback } from 'react';
import { Card, Table, Tag, Select, Button, Collapse, Space, message, Statistic, Row, Col, Pagination } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { getFeedbackStats, getFeedbackListByMessage, getFeedbackAlerts } from '@/api/feedback';
import { formatTime } from '@/utils/format';
import type { ColumnsType } from 'antd/es/table';

interface FeedbackItem {
  feedback_status: string;
  feedback_count: number;
  useful_count: number;
  useless_count: number;
  chat_type: string;
  chat_display_name: string;
  bot_name: string;
  latest_feedback_at: string;
  useless_reasons: string;
  question: string;
  answer: string;
  memory_convert_status: string;
  memory_convert_at: string;
  review_status: string;
  reviewed_count: number;
  review_feedback_count: number;
  latest_reviewed_at: string;
  feedbacks: Array<{
    id: string;
    result: string;
    reason: string;
    user_display_name: string;
    created_at: string;
    reviewed_at: string;
  }>;
}

interface AlertItem {
  id: string;
  notified_at: string;
  chat_display_name: string;
  chat_type: string;
  bot_name: string;
  feedback_count: number;
  threshold: number;
  window_minutes: number;
  metadata?: { context?: { items?: Array<{ id: string; created_at: string; user_id: string; question: string; answer: string; reason: string }> } };
}

function statusColor(s: string) {
  return { useful: 'green', useless: 'red', mixed: 'orange' }[s] || 'default';
}
function statusLabel(s: string) {
  return { useful: '有效', useless: '无效', mixed: '有争议' }[s] || '未知';
}
function convertColor(s: string) {
  return { converted: 'green', failed: 'red', unconverted: 'default' }[s] || 'default';
}
function convertLabel(s: string) {
  return { converted: '已转换', failed: '转换失败', unconverted: '待转换' }[s] || '未知';
}
function reviewColor(s: string) {
  return { reviewed: 'green', partial: 'orange', pending: 'default' }[s] || 'default';
}
function reviewLabel(s: string) {
  return { reviewed: '已审核', partial: '部分审核', pending: '待审核' }[s] || '未知';
}
function chatTypeLabel(t: string) {
  return { group: '群聊', room: '群聊', single: '用户', user: '用户' }[t] || t || '未知';
}

export default function FeedbackStatsView() {
  const [stats, setStats] = useState({ total: 0, useful: 0, useless: 0, satisfaction_rate: 0, days: 0 });
  const [feedbacks, setFeedbacks] = useState<FeedbackItem[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [querying, setQuerying] = useState(false);
  const [days, setDays] = useState(0);
  const [resultFilter, setResultFilter] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [total, setTotal] = useState(0);
  const [alertPage, setAlertPage] = useState(1);
  const [alertPageSize, setAlertPageSize] = useState(10);
  const [alertTotal, setAlertTotal] = useState(0);

  const loadAll = useCallback(async () => {
    setQuerying(true);
    try {
      const [s, f, a] = await Promise.all([
        getFeedbackStats({ days }).then((r: unknown) => r as typeof stats),
        getFeedbackListByMessage({ result: resultFilter, days, page, page_size: pageSize }).then((r: unknown) => r as { items: FeedbackItem[]; total: number }),
        getFeedbackAlerts({ days, page: alertPage, page_size: alertPageSize }).then((r: unknown) => r as { items: AlertItem[]; total: number }),
      ]);
      setStats(s);
      setFeedbacks(f.items || []);
      setTotal(f.total || 0);
      setAlerts(a.items || []);
      setAlertTotal(a.total || 0);
    } catch (e) { message.error(String(e)); }
    finally { setQuerying(false); }
  }, [days, resultFilter, page, pageSize, alertPage, alertPageSize]);

  useEffect(() => { loadAll(); }, []); // eslint-disable-line

  const handleQuery = () => { setPage(1); setAlertPage(1); loadAll(); };

  const columns: ColumnsType<FeedbackItem> = [
    { title: '序号', render: (_, __, i) => (page - 1) * pageSize + i + 1, width: 60, align: 'center' },
    { title: '状态', dataIndex: 'feedback_status', width: 80, render: (v: string) => <Tag color={statusColor(v)}>{statusLabel(v)}</Tag> },
    { title: '记忆/审核', width: 140, render: (_, r) => {
      const showConvert = r.feedback_status === 'useful' || r.feedback_status === 'mixed';
      const showReview = r.feedback_status === 'useless' || r.feedback_status === 'mixed';
      return <Space size={4}>{showConvert && <Tag color={convertColor(r.memory_convert_status)}>{convertLabel(r.memory_convert_status)}</Tag>}{showReview && <Tag color={reviewColor(r.review_status)}>{reviewLabel(r.review_status)}</Tag>}{!showConvert && !showReview && '-'}</Space>;
    }},
    { title: '反馈数', width: 70, align: 'center', render: (_, r) => r.feedback_count > 1 ? <span>{r.useful_count}<span style={{ color: '#d9d9d9' }}>/</span>{r.useless_count}</span> : r.feedback_count },
    { title: '来源', width: 80, render: (_, r) => chatTypeLabel(r.chat_type) },
    { title: '群聊/用户', dataIndex: 'chat_display_name', ellipsis: true, minWidth: 140 },
    { title: '无效原因', dataIndex: 'useless_reasons', ellipsis: true, minWidth: 160, render: (v: string) => v || '-' },
    { title: 'Bot', dataIndex: 'bot_name', width: 120, ellipsis: true },
    { title: '时间', dataIndex: 'latest_feedback_at', width: 150, render: (v: string) => formatTime(v) },
    Table.EXPAND_COLUMN,
  ];

  return (
    <section>
      <Card className="panel" title={<div className="panel-title"><span>反馈分析</span></div>}>
        <Row gutter={16} style={{ marginBottom: 20 }}>
          <Col span={6}><Card size="small"><Statistic title="总反馈数" value={stats.total} /></Card></Col>
          <Col span={6}><Card size="small" style={{ borderTop: '3px solid #10b981' }}><Statistic title="有效" value={stats.useful} valueStyle={{ color: '#10b981' }} /></Card></Col>
          <Col span={6}><Card size="small" style={{ borderTop: '3px solid #ef4444' }}><Statistic title="无效" value={stats.useless} valueStyle={{ color: '#ef4444' }} /></Card></Col>
          <Col span={6}><Card size="small" style={{ borderTop: '3px solid #3b82f6' }}><Statistic title="满意度" value={`${stats.satisfaction_rate}%`} valueStyle={{ color: '#3b82f6' }} /></Card></Col>
        </Row>

        <Space style={{ marginBottom: 16 }}>
          <span>时间范围:</span>
          <Select value={days} style={{ width: 140 }} onChange={(v) => setDays(v)}
            options={[{ value: 0, label: '今日' }, { value: 7, label: '过去一周' }, { value: 15, label: '15天前' }, { value: 30, label: '30天前' }]} />
          <span>反馈状态:</span>
          <Select value={resultFilter || undefined} allowClear placeholder="全部" style={{ width: 120 }}
            onChange={(v) => setResultFilter(v || '')}
            options={[{ value: 'useful', label: '有效' }, { value: 'useless', label: '无效' }]} />
          <Button type="primary" icon={<SearchOutlined />} loading={querying} onClick={handleQuery}>查询</Button>
        </Space>

        <div style={{ marginBottom: 16, fontWeight: 600, fontSize: 15 }}>反馈详情（按消息）</div>
        <Table<FeedbackItem> columns={columns} dataSource={feedbacks} rowKey={(_, i) => String(i)}
          loading={querying} size="small" scroll={{ x: 1100 }}
          expandable={{
            expandedRowRender: (row) => (
              <div style={{ padding: 12 }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12, marginBottom: 12 }}>
                  <div><div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>用户问题</div><div>{row.question || '-'}</div></div>
                  <div><div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>Bot 回复</div><div>{row.answer || '-'}</div></div>
                </div>
                {row.feedbacks?.length > 0 && (
                  <div style={{ marginBottom: 12 }}>
                    <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>反馈明细（{row.feedbacks.length} 条）</div>
                    {row.feedbacks.map((fb) => (
                      <div key={fb.id} style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '4px 0', fontSize: 13 }}>
                        <Tag color={fb.result === 'useful' ? 'green' : 'red'}>{fb.result === 'useful' ? '有效' : '无效'}</Tag>
                        {fb.reason && <span style={{ color: '#6b7280' }}>{fb.reason}</span>}
                        <span style={{ color: '#9ca3af', fontSize: 12 }}>{fb.user_display_name}{fb.user_display_name ? ' · ' : ''}{formatTime(fb.created_at)}</span>
                      </div>
                    ))}
                  </div>
                )}
                {row.useless_reasons && <div><div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>无效原因汇总</div><div>{row.useless_reasons}</div></div>}
              </div>
            ),
          }}
          pagination={{
            total, current: page, pageSize, pageSizeOptions: ['10', '20', '50', '100'],
            showSizeChanger: true, showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => { setPage(p); setPageSize(ps); setTimeout(loadAll, 0); },
          }} />

        <div style={{ marginTop: 24, marginBottom: 8, fontWeight: 600, fontSize: 15 }}>告警记录</div>
        {alerts.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center', color: '#9ca3af' }}>暂无告警记录</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {alerts.map((alert) => (
              <Card key={alert.id || alert.notified_at} size="small">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <strong>{alert.chat_display_name || '-'}</strong>
                  <Tag color="red">{alert.feedback_count} / {alert.threshold}</Tag>
                </div>
                <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
                  {chatTypeLabel(alert.chat_type)}{alert.bot_name ? ` · ${alert.bot_name}` : ''} · {alert.window_minutes}分钟窗口
                </div>
                <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 2 }}>{formatTime(alert.notified_at)}</div>
                <Collapse style={{ marginTop: 8 }} items={[{
                  key: 'context', label: '展开上下文',
                  children: (alert.metadata?.context?.items || []).length === 0 ? <span style={{ color: '#9ca3af' }}>暂无上下文</span> :
                    (alert.metadata?.context?.items || []).map((item, i) => (
                      <div key={item.id || i} style={{ padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}>
                        <div style={{ fontSize: 12, color: '#9ca3af' }}>{formatTime(item.created_at)} · {item.user_id || '-'}</div>
                        {item.question && <div style={{ fontSize: 13 }}>Q: {item.question}</div>}
                        {item.answer && <div style={{ fontSize: 13 }}>A: {item.answer}</div>}
                        {item.reason && <div style={{ fontSize: 12, color: '#6b7280' }}>原因: {item.reason}</div>}
                      </div>
                    )),
                }]} />
              </Card>
            ))}
          </div>
        )}
        <div style={{ marginTop: 12, textAlign: 'right' }}>
          <Pagination total={alertTotal} current={alertPage} pageSize={alertPageSize}
            pageSizeOptions={['5', '10', '20']} showSizeChanger showTotal={(t: number) => `共 ${t} 条`}
            onChange={(p: number, ps: number) => { setAlertPage(p); setAlertPageSize(ps); setTimeout(loadAll, 0); }} />
        </div>
      </Card>
    </section>
  );
}
