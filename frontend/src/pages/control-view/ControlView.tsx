import { useEffect, useRef, useState, useCallback } from 'react';
import { Card, Tag, Button, message } from 'antd';
import { PlayCircleOutlined, PauseCircleOutlined } from '@ant-design/icons';
import { useRuntimeStore } from '@/store/runtime';
import { getAiStatus, cancelAiWork, clearAiWork, type AiStatus, type AiTask } from '@/api/agents';
import { fetchWithAuth } from '@/utils/request';
import type { Bot } from '@/api/bots';
import { getAgentLabel, formatTimeOnly } from '@/utils/format';

function stageLabel(stage?: string): string {
  const map: Record<string, string> = {
    '接收消息': '接收消息',
    '等待 Agent 并发槽': '等待并发槽',
    '构建上下文并调用 Agent（流式）': 'Agent 推理中',
    '构建上下文并调用 Agent': 'Agent 推理中',
    '发送企微回复': '发送回复',
    '完成': '完成',
    '已截断': '已截断',
    '异常截断': '异常截断',
  };
  return map[stage || ''] || stage || '--';
}

function statusTagColor(status: string): string {
  if (status === 'running') return 'blue';
  if (status === 'completed') return 'green';
  if (status === 'failed') return 'red';
  if (status === 'cancelled' || status === 'cancel_requested') return 'orange';
  return 'default';
}

function isActiveStatus(status: string): boolean {
  return ['queued', 'running', 'cancel_requested'].includes(status);
}

function taskDisplayName(task: AiTask): string {
  const convName = task.conv_display_name || '';
  const chatType = task.conv_chat_type || '';
  const senderName = task.conv_sender_name || '';
  if (chatType === 'group' && convName) {
    return senderName ? `${convName}:${senderName}` : convName;
  }
  if (senderName) return senderName;
  if (convName) return convName;
  return task.chat_name || task.chat_id || '--';
}

function reasoningPreview(task: AiTask): string {
  const reasoning = String(task?.reasoning || '').trim();
  if (reasoning) return reasoning;
  const stage = stageLabel(task?.stage || '');
  if (isActiveStatus(task?.status)) {
    return stage ? `当前阶段：${stage}` : 'Agent 正在工作...';
  }
  return task?.error ? `异常：${task.error}` : '暂无思考链记录';
}

function getBotAgentProvider(bot: Bot): string {
  return typeof bot.agent_provider === 'string' ? bot.agent_provider : '';
}

function getBotMetricCount(value: unknown): number {
  return typeof value === 'number' ? value : 0;
}

function getBotPrompt(bot: Bot): string {
  return typeof bot.system_prompt === 'string' ? bot.system_prompt : '';
}

export default function ControlView() {
  const {
    bots, agents, botStatuses, startingBots, stoppingBots,
    handleStartBot, handleStopBot, loadBots, loadAgents,
  } = useRuntimeStore();

  const [aiStatus, setAiStatus] = useState<AiStatus>({ busy: false, active: [], recent: [] });
  const [cancellingTasks, setCancellingTasks] = useState<Set<string>>(new Set());
  const [clearingTasks, setClearingTasks] = useState<Set<string>>(new Set());
  const controllerRef = useRef<AbortController | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const streamStoppedRef = useRef(false);
  const startStreamRef = useRef<() => Promise<void>>(async () => {});

  const enabledBots = bots.filter((bot) => Boolean(bot.is_active));

  const getStatus = useCallback((botKey: string) => {
    return botStatuses[botKey] || { running: false, pid: null };
  }, [botStatuses]);

  const combinedTasks = (() => {
    const tasks = [...(aiStatus.active || []), ...(aiStatus.recent || [])];
    const seen = new Set<string>();
    const unique: AiTask[] = [];
    for (const task of tasks) {
      if (task?.trace_id && !seen.has(task.trace_id)) {
        seen.add(task.trace_id);
        unique.push(task);
      }
    }
    return unique.slice(0, 15);
  })();

  // SSE stream for AI status
  const closeStream = useCallback(() => {
    if (controllerRef.current) {
      controllerRef.current.abort();
      controllerRef.current = null;
    }
  }, []);

  const startStream = useCallback(async () => {
    closeStream();
    const controller = new AbortController();
    controllerRef.current = controller;
    try {
      const response = await fetchWithAuth('/ai/status/stream', {
        headers: { Accept: 'text/event-stream' },
        signal: controller.signal,
      });
      if (!response.ok || !response.body) return;
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (!controller.signal.aborted) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let frameEnd = buffer.indexOf('\n\n');
        while (frameEnd !== -1) {
          const frame = buffer.slice(0, frameEnd);
          buffer = buffer.slice(frameEnd + 2);
          const dataLine = frame.split(/\r?\n/).find((line) => line.startsWith('data:'));
          if (dataLine) {
            try {
              setAiStatus(JSON.parse(dataLine.slice(5).trim()));
            } catch { /* ignore malformed frames */ }
          }
          frameEnd = buffer.indexOf('\n\n');
        }
      }
    } catch {
      if (!controller.signal.aborted && !streamStoppedRef.current) {
        reconnectTimerRef.current = setTimeout(() => startStreamRef.current(), 3000);
      }
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
      }
    }
  }, [closeStream]);

  // Keep ref in sync
  useEffect(() => {
    startStreamRef.current = startStream;
  });

  useEffect(() => {
    streamStoppedRef.current = false;
    loadBots();
    loadAgents();
    getAiStatus().then((data) => setAiStatus(data)).catch(() => setAiStatus({ busy: false, active: [], recent: [] }));
    startStreamRef.current();

    return () => {
      streamStoppedRef.current = true;
      closeStream();
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
    };
  }, [loadBots, loadAgents, startStream, closeStream]);

  const handleCancel = async (traceId: string) => {
    if (cancellingTasks.has(traceId)) return;
    const next = new Set(cancellingTasks);
    next.add(traceId);
    setCancellingTasks(next);
    try {
      await cancelAiWork(traceId);
      message.success('已发送取消请求');
      const status = await getAiStatus();
      setAiStatus(status);
    } catch (e) {
      message.error(String(e));
    } finally {
      const s = new Set(cancellingTasks);
      s.delete(traceId);
      setCancellingTasks(s);
    }
  };

  const handleClear = async (traceId: string) => {
    if (clearingTasks.has(traceId)) return;
    const next = new Set(clearingTasks);
    next.add(traceId);
    setClearingTasks(next);
    try {
      await clearAiWork(traceId);
      message.success('已清除任务');
      const status = await getAiStatus();
      setAiStatus(status);
    } catch (e) {
      message.error(String(e));
    } finally {
      const s = new Set(clearingTasks);
      s.delete(traceId);
      setClearingTasks(s);
    }
  };

  return (
    <section style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.45fr) minmax(320px, 0.8fr)', gap: 24, height: '100%', minHeight: 0, alignItems: 'start' }}>
      {/* Bot Cards Panel */}
      <Card
        className="panel"
        title={<div className="panel-title split"><span>已启用 Bot</span></div>}
        styles={{ body: { padding: 24, display: 'flex', flexDirection: 'column', gap: 20, overflow: 'auto', maxHeight: 'calc(100vh - 200px)' } }}
      >
        {enabledBots.length > 0 ? (
          <div className="bot-card-grid">
            {enabledBots.map((bot) => {
              const status = getStatus(bot.bot_key);
              return (
                <article key={bot.bot_key} className="bot-service-card" style={{ display: 'grid', gap: 16, padding: 18, border: '1px solid #e5e7eb', borderRadius: 12, background: '#f9fafb' }}>
                  <header style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12 }}>
                    <div>
                      <h3 style={{ margin: 0, color: '#111827', fontSize: 18 }}>{String(bot.name || bot.bot_key)}</h3>
                      <p style={{ margin: '4px 0 0', color: '#6b7280', fontSize: 13 }}>{getAgentLabel(getBotAgentProvider(bot), agents)}</p>
                    </div>
                    <Tag color={status.running ? 'green' : 'default'}>{status.running ? '运行中' : '已停止'}</Tag>
                  </header>

                  <div className="metric-row metric-row--bot" style={{ gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }}>
                    <div><span>MCP 数</span><strong>{getBotMetricCount(bot.enabled_mcp_count)}</strong></div>
                    <div><span>Skills 数</span><strong>{getBotMetricCount(bot.enabled_skill_count)}</strong></div>
                    <div><span>PID</span><strong>{status.pid || '-'}</strong></div>
                  </div>

                  <div className="prompt-preview" style={{ padding: '14px 16px', border: '1px solid #e5e7eb', borderRadius: 12, background: '#f9fafb' }}>
                    <span style={{ display: 'block', marginBottom: 6, color: '#6b7280', fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.02em' }}>提示词</span>
                    <p style={{ margin: 0, color: '#111827', lineHeight: 1.7, display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden', textOverflow: 'ellipsis', wordBreak: 'break-word' }}
                       title={getBotPrompt(bot)}>
                      {getBotPrompt(bot).trim() || '未设置提示词'}
                    </p>
                  </div>

                  <footer className="actions" style={{ justifyContent: 'flex-end' }}>
                    <Button
                      type="primary"
                      icon={<PlayCircleOutlined />}
                      disabled={status.running || startingBots.has(bot.bot_key)}
                      loading={startingBots.has(bot.bot_key)}
                      onClick={() => handleStartBot(bot.bot_key)}
                      style={{ background: '#10b981', borderColor: '#10b981' }}
                    >
                      启动服务
                    </Button>
                    <Button
                      danger
                      icon={<PauseCircleOutlined />}
                      disabled={!status.running || stoppingBots.has(bot.bot_key)}
                      loading={stoppingBots.has(bot.bot_key)}
                      onClick={() => handleStopBot(bot.bot_key)}
                    >
                      停止服务
                    </Button>
                  </footer>
                </article>
              );
            })}
          </div>
        ) : (
          <div className="empty-block" style={{ padding: '28px 24px', textAlign: 'center' }}>
            <strong>暂无已启用 Bot</strong>
            <span>请先在 Bot 配置页面启用 Bot，再回到工作台查看运行状态。</span>
          </div>
        )}
      </Card>

      {/* Task List Panel */}
      <Card
        className="panel"
        title={
          <div className="panel-title split" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>任务列表</span>
            {aiStatus.busy && <Tag color="orange">运行中</Tag>}
          </div>
        }
        styles={{ body: { padding: 24, display: 'flex', flexDirection: 'column', gap: 10, overflow: 'auto', maxHeight: 'calc(100vh - 200px)' } }}
      >
        {combinedTasks.length > 0 ? (
          <div className="task-list" style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {combinedTasks.map((task) => (
              <article key={task.trace_id} className={`task-item ${isActiveStatus(task.status) ? 'task-item--active' : ''}`}
                style={{
                  padding: '12px 14px', border: `1px solid ${isActiveStatus(task.status) ? '#3b82f6' : '#e5e7eb'}`,
                  borderRadius: 10, background: isActiveStatus(task.status) ? '#eff6ff' : '#f9fafb',
                  display: 'flex', flexDirection: 'column', gap: 6,
                }}>
                <div className="task-item__head" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                  <strong style={{ fontSize: 14, color: '#111827', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{taskDisplayName(task)}</strong>
                  <Tag color={statusTagColor(task.status)}>{stageLabel(task.stage)}</Tag>
                </div>
                <p className="task-item__question" style={{ color: '#6b7280', fontSize: 13, margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {(task.question || '').slice(0, 100)}
                </p>
                <pre className="task-item__answer" style={{
                  margin: 0, padding: '10px 12px', color: '#0f172a', background: 'rgba(255,255,255,0.78)',
                  border: '1px solid rgba(59,130,246,0.18)', borderRadius: 8, fontSize: 12,
                  lineHeight: 1.6, whiteSpace: 'pre-wrap', wordBreak: 'break-word', maxHeight: 140, overflow: 'auto',
                }}>
                  {reasoningPreview(task)}
                </pre>
                <div className="task-item__meta" style={{ display: 'flex', alignItems: 'center', gap: 12, color: '#9ca3af', fontSize: 12 }}>
                  <span>TraceId: {task.trace_id.slice(0, 8)}...</span>
                  <span>{formatTimeOnly(task.started_at)}</span>
                  {isActiveStatus(task.status) ? (
                    <Button size="small" type="link" danger
                      loading={cancellingTasks.has(task.trace_id)}
                      disabled={cancellingTasks.has(task.trace_id)}
                      onClick={() => handleCancel(task.trace_id)}>
                      取消
                    </Button>
                  ) : (
                    <Button size="small" type="link"
                      loading={clearingTasks.has(task.trace_id)}
                      disabled={clearingTasks.has(task.trace_id)}
                      onClick={() => handleClear(task.trace_id)}>
                      清除
                    </Button>
                  )}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-block empty-block--large" style={{ minHeight: 260, display: 'grid', gap: 8, placeItems: 'center', padding: '28px 24px', textAlign: 'center' }}>
            <strong>暂无任务</strong>
            <span>Bot 运行后，Agent 的调用任务会实时展示在这里。</span>
          </div>
        )}
      </Card>
    </section>
  );
}
