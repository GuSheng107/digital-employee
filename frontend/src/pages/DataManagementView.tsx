import { Modal, Card, Button } from 'antd';
import { FolderOpenOutlined, DollarOutlined, FileTextOutlined, MessageOutlined } from '@ant-design/icons';
import { useRuntimeStore } from '@/store/runtime';
import { formatBytes } from '@/utils/format';

function formatNumber(n: unknown): string {
  const num = Number(n ?? 0);
  if (!num || num === 0) return '0';
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
  return String(num);
}

function formatPercent(v: unknown): string {
  const num = Number(v ?? 0);
  if (!Number.isFinite(num)) return '0%';
  return `${Math.round(num)}%`;
}

function MetricCard({ label, value }: { label: string; value: React.ReactNode }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

export default function DataManagementView() {
  const { dataOverview, tokenUsage, botStatuses, optimizingData, optimizeData } = useRuntimeStore();

  const overview = (dataOverview || {}) as Record<string, unknown>;
  const usage = (tokenUsage || {}) as Record<string, unknown>;

  const runningBotCount = Object.values(botStatuses || {}).filter((s: unknown) => (s as { running?: boolean })?.running).length;

  const manualReplies = Number(overview.manual_replies || 0);
  const aiReplies = Number(overview.ai_replies || 0);
  const totalReplies = manualReplies + aiReplies;

  const confirmOptimize = () => {
    Modal.confirm({
      title: '确认优化数据库',
      content: '该操作会先停止所有正在运行的 Bot，然后执行以下清理，优化完成后不会自动恢复 Bot，需要你回到工作台手动启动。该操作不可恢复，确认执行？',
      okText: '确认清理并优化',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: () => optimizeData(),
    });
  };

  return (
    <section>
      <div className="data-overview-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 24, alignItems: 'stretch' }}>
        {/* Database Overview */}
        <Card className="panel" title={<div className="panel-title"><FolderOpenOutlined /> 数据库概览</div>}>
          <div className="data-hero">
            <div>
              <p className="eyebrow">SQLite Database</p>
              <h2>{formatBytes(overview.size_bytes as number)}</h2>
              <span className="mono-text">{String(overview.path || '-')}</span>
            </div>
            <Button danger loading={optimizingData} onClick={confirmOptimize}>优化数据库</Button>
          </div>

          <div className="metric-row metric-row--quad" style={{ marginTop: 20 }}>
            <MetricCard label="会话数" value={Number(overview.conversations || 0)} />
            <MetricCard label="消息数" value={Number(overview.messages || 0)} />
            <MetricCard label="日志数" value={Number(overview.logs || 0)} />
            <MetricCard label="近 30 天 AI 任务" value={Number(overview.recent_ai_tasks || 0)} />
          </div>
          <div className="metric-row metric-row--quad" style={{ marginTop: 16 }}>
            <MetricCard label="Bot 总数" value={Number(overview.bot_count || 0)} />
            <MetricCard label="启用 Bot" value={Number(overview.enabled_bot_count ?? overview.active_bot_count ?? 0)} />
            <MetricCard label="运行中 Bot" value={runningBotCount} />
            <MetricCard label="启用任务数" value={Number(overview.enabled_periodic_tasks || 0) + Number(overview.enabled_one_time_tasks || 0)} />
          </div>
        </Card>

        {/* Token Usage */}
        <Card className="panel" title={<div className="panel-title"><DollarOutlined /> Token 消耗</div>}>
          <div className="metric-row metric-row--quad">
            <MetricCard label="输入 Token" value={formatNumber(usage.input_tokens)} />
            <MetricCard label="输出 Token" value={formatNumber(usage.output_tokens)} />
            <MetricCard label="聊天与任务" value={formatNumber(usage.bot_tokens)} />
            <MetricCard label="系统与维护" value={formatNumber(usage.system_tokens)} />
          </div>

          <div className="metric-row metric-row--triple" style={{ marginTop: 16 }}>
            <div className="token-time-card">
              <span>总消耗</span>
              <small>{String(usage.total_range_label || '-')}</small>
              <strong>{formatNumber(usage.total_tokens)}</strong>
            </div>
            <div className="token-time-card">
              <span>周消耗</span>
              <small>{String(usage.weekly_range_label || '-')}</small>
              <strong>{formatNumber(usage.weekly_tokens)}</strong>
            </div>
            <div className="token-time-card">
              <span>月消耗</span>
              <small>{String(usage.monthly_range_label || '-')}</small>
              <strong>{formatNumber(usage.monthly_tokens)}</strong>
            </div>
          </div>

          <div className="metric-row metric-row--triple" style={{ marginTop: 16 }}>
            <MetricCard label="模型调用记录" value={Number(usage.record_count || 0)} />
            <MetricCard label="平均单次调用" value={formatNumber(usage.avg_tokens_per_record)} />
            <MetricCard label="最高单次调用" value={formatNumber(usage.max_tokens_per_record)} />
          </div>
        </Card>

        {/* Memory Stats */}
        <Card className="panel" title={<div className="panel-title"><FileTextOutlined /> 记忆量</div>}>
          <div className="metric-row metric-row--quad">
            <MetricCard label="上传文档数" value={Number(overview.uploaded_documents || 0)} />
            <MetricCard label="已转换文档数" value={Number(overview.converted_documents || 0)} />
            <MetricCard label="已转换记录数" value={Number(overview.converted_messages || 0)} />
            <MetricCard label="未转换消息数" value={Number(overview.unconverted_messages || 0)} />
          </div>
          <div className="metric-row metric-row--quad" style={{ marginTop: 16 }}>
            <MetricCard label="文档转换率" value={formatPercent(overview.document_conversion_rate)} />
            <MetricCard label="消息转换率" value={formatPercent(overview.message_conversion_rate)} />
            <MetricCard label="记忆更新次数" value={Number(overview.memory_update_count || 0)} />
            <MetricCard label="文档提取次数" value={Number(overview.document_extraction_count || 0)} />
          </div>
          <div className="metric-row metric-row--dual" style={{ marginTop: 16 }}>
            <MetricCard label="记忆包注入成功" value={Number(overview.memory_pack_injection_success_count || 0)} />
            <MetricCard label="记忆包注入失败" value={Number(overview.memory_pack_injection_failed_count || 0)} />
          </div>
        </Card>

        {/* Task Stats */}
        <Card className="panel" title={<div className="panel-title"><MessageOutlined /> 任务量</div>}>
          <div className="metric-row metric-row--dual">
            <MetricCard label="人工回复" value={manualReplies} />
            <MetricCard label="AI 回复" value={aiReplies} />
          </div>
          <div className="metric-row metric-row--triple" style={{ marginTop: 16 }}>
            <MetricCard label="总回复量" value={totalReplies} />
            <MetricCard label="人工占比" value={totalReplies ? `${Math.round((manualReplies / totalReplies) * 100)}%` : '0%'} />
            <MetricCard label="AI 占比" value={totalReplies ? `${Math.round((aiReplies / totalReplies) * 100)}%` : '0%'} />
          </div>
          <div className="metric-row metric-row--quad" style={{ marginTop: 16 }}>
            <MetricCard label="AI 任务总数" value={Number(overview.ai_task_total || 0)} />
            <MetricCard label="已完成任务" value={Number(overview.ai_task_completed || 0)} />
            <MetricCard label="失败任务" value={Number(overview.ai_task_failed || 0)} />
            <MetricCard label="进行中/排队" value={Number(overview.ai_task_running || 0)} />
          </div>
        </Card>
      </div>
    </section>
  );
}
