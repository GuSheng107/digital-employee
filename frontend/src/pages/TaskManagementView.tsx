import { useEffect, useState, useCallback } from 'react';
import { Card, Table, Tag, Button, Select, Input, Modal, Space, message, Popconfirm, Row, Col } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, EyeOutlined, PlayCircleOutlined, PauseCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { getTasks, getTaskExecutors, getTaskDetail, enableTask, disableTask, updateTask, deleteTask, createTask, triggerTask } from '@/api/system';
import { formatTime } from '@/utils/format';
import type { ColumnsType } from 'antd/es/table';

interface Task {
  task_key: string;
  task_name?: string;
  task_type: string;
  scope: string;
  status: string;
  executor_kind: string;
  executor_id: string;
  schedule?: string;
  handler_name?: string;
  prompt_text?: string;
  created_at?: string;
  updated_at?: string;
  last_run_at?: string;
  last_result?: string;
}

interface ExecutorInfo { bots: Array<{ id: string; name: string }>; agents: Array<{ id: string; name: string }>; }

function scopeLabel(s: string) { return { system: '系统级', user: '用户级' }[s] || s || '-'; }
function executorLabel(k: string) { return { builtin: '内置执行器', bot: 'Bot', platform_agent: '平台 Agent' }[k] || k || '-'; }
function statusColor(s: string) {
  return { active: 'green', running: 'blue', pending: 'orange', paused: 'default', completed: 'green', failed: 'red' }[s] || 'default';
}
function statusLabel(s: string) {
  return { active: '启用中', running: '执行中', pending: '待执行', paused: '已暂停', completed: '已完成', failed: '失败' }[s] || s;
}

export default function TaskManagementView() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);
  const [executors, setExecutors] = useState<ExecutorInfo>({ bots: [], agents: [] });
  const [filters, setFilters] = useState({ keyword: '', scope: '', status: '', taskType: '' });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [total, setTotal] = useState(0);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogMode, setDialogMode] = useState<'create' | 'edit' | 'view'>('view');
  const [dialogForm, setDialogForm] = useState<Partial<Task>>({});
  const [dialogSaving, setDialogSaving] = useState(false);
  const [triggering, setTriggering] = useState('');

  const loadTasks = useCallback(async (p: number, ps: number) => {
    setLoading(true);
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result: any = await getTasks({ ...filters, page: p, page_size: ps });
      setTasks(result.tasks || []);
      setTotal(result.total || 0);
      setPage(result.page || 1);
      setPageSize(result.page_size || 10);
    } catch (e) { message.error(String(e)); }
    finally { setLoading(false); }
  }, [filters]);

  const loadExecutors = async () => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result: any = await getTaskExecutors();
      setExecutors(result || { bots: [], agents: [] });
    } catch { /* ignore */ }
  };

  useEffect(() => { loadTasks(1, 10); loadExecutors(); }, []); // eslint-disable-line

  const handleQuery = () => { loadTasks(1, pageSize); };

  const openView = async (task: Task) => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const detail: any = await getTaskDetail(task.task_key);
      setDialogForm(detail);
    } catch { setDialogForm(task); }
    setDialogMode('view'); setDialogOpen(true);
  };

  const openCreate = () => {
    setDialogForm({ task_type: 'periodic', scope: 'system', task_name: '', handler_name: '', executor_kind: 'builtin', schedule: '', prompt_text: '' });
    setDialogMode('create'); setDialogOpen(true);
  };

  const openEdit = async (task: Task) => {
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const detail: any = await getTaskDetail(task.task_key);
      setDialogForm(detail);
    } catch { setDialogForm(task); }
    setDialogMode('edit'); setDialogOpen(true);
  };

  const handleSave = async () => {
    setDialogSaving(true);
    try {
      if (dialogMode === 'create') {
        await createTask(dialogForm as Record<string, unknown>);
        message.success('任务已创建');
      } else {
        await updateTask(dialogForm.task_key!, dialogForm as Record<string, unknown>);
        message.success('任务已更新');
      }
      setDialogOpen(false);
      loadTasks(page, pageSize);
    } catch (e) { message.error(String(e)); }
    finally { setDialogSaving(false); }
  };

  const handleToggle = async (task: Task) => {
    if (task.status === 'active') {
      await disableTask(task.task_key);
      message.success('已禁用');
    } else {
      await enableTask(task.task_key);
      message.success('已启用');
    }
    loadTasks(page, pageSize);
  };

  const handleDelete = async (taskKey: string) => {
    await deleteTask(taskKey);
    message.success('已删除');
    loadTasks(page, pageSize);
  };

  const handleTrigger = async (taskKey: string) => {
    setTriggering(taskKey);
    try {
      await triggerTask(taskKey);
      message.success('任务已触发');
      loadTasks(page, pageSize);
    } catch (e) { message.error(String(e)); }
    finally { setTriggering(''); }
  };

  const getExecutorName = (task: Task) => {
    if (task.executor_kind === 'bot') return executors.bots.find((b) => b.id === task.executor_id)?.name || 'Bot';
    if (task.executor_kind === 'platform_agent') return executors.agents.find((a) => a.id === task.executor_id)?.name || '平台 Agent';
    return executorLabel(task.executor_kind);
  };

  const columns: ColumnsType<Task> = [
    { title: '任务名称', dataIndex: 'task_name', ellipsis: true, minWidth: 160 },
    { title: '类型', dataIndex: 'task_type', width: 80, render: (v: string) => <Tag>{v === 'periodic' ? '周期' : '一次性'}</Tag> },
    { title: '范围', dataIndex: 'scope', width: 80, render: (v: string) => scopeLabel(v) },
    { title: '状态', dataIndex: 'status', width: 90, render: (v: string) => <Tag color={statusColor(v)}>{statusLabel(v)}</Tag> },
    { title: '执行器', width: 120, render: (_, r) => getExecutorName(r) },
    { title: '调度', dataIndex: 'schedule', width: 100, ellipsis: true },
    { title: '最后执行', dataIndex: 'last_run_at', width: 160, render: (v: string) => formatTime(v) },
    { title: '操作', width: 220, fixed: 'right', render: (_, r) => (
      <Space size="small">
        <Button size="small" type="link" icon={<EyeOutlined />} onClick={() => openView(r)}>查看</Button>
        <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEdit(r)}>编辑</Button>
        <Button size="small" type="link" icon={r.status === 'active' ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
          onClick={() => handleToggle(r)}>{r.status === 'active' ? '禁用' : '启用'}</Button>
        {r.task_type === 'one_time' && (
          <Button size="small" type="link" icon={<PlayCircleOutlined />} loading={triggering === r.task_key}
            onClick={() => handleTrigger(r.task_key)}>触发</Button>
        )}
        <Popconfirm title="确定删除？" onConfirm={() => handleDelete(r.task_key)}>
          <Button size="small" type="link" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      </Space>
    )},
  ];

  return (
    <section>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>任务管理</h2>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={() => loadTasks(page, pageSize)}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建任务</Button>
        </Space>
      </div>

      <Card className="panel" size="small">
        <Space wrap style={{ marginBottom: 16 }}>
          <Input placeholder="搜索关键词" value={filters.keyword} allowClear style={{ width: 180 }}
            onChange={(e) => setFilters((f) => ({ ...f, keyword: e.target.value }))} />
          <Select value={filters.scope || undefined} placeholder="范围" allowClear style={{ width: 100 }}
            onChange={(v) => setFilters((f) => ({ ...f, scope: v || '' }))}
            options={[{ value: 'system', label: '系统级' }, { value: 'user', label: '用户级' }]} />
          <Select value={filters.status || undefined} placeholder="状态" allowClear style={{ width: 100 }}
            onChange={(v) => setFilters((f) => ({ ...f, status: v || '' }))}
            options={['active', 'running', 'pending', 'paused', 'completed', 'failed'].map((v) => ({ value: v, label: statusLabel(v) }))} />
          <Select value={filters.taskType || undefined} placeholder="任务类型" allowClear style={{ width: 120 }}
            onChange={(v) => setFilters((f) => ({ ...f, taskType: v || '' }))}
            options={[{ value: 'periodic', label: '周期任务' }, { value: 'one_time', label: '一次性任务' }]} />
          <Button type="primary" onClick={handleQuery}>查询</Button>
        </Space>

        <Table<Task> columns={columns} dataSource={tasks} rowKey="task_key"
          loading={loading} size="small" scroll={{ x: 1100 }}
          pagination={{ total, current: page, pageSize, pageSizeOptions: ['10', '20', '50'], showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条`,
            onChange: (p: number, ps: number) => { setPage(p); setPageSize(ps); loadTasks(p, ps); } }} />
      </Card>

      <Modal title={dialogMode === 'create' ? '新建任务' : dialogMode === 'edit' ? '编辑任务' : '任务详情'} open={dialogOpen} onCancel={() => setDialogOpen(false)} width={720}
        footer={dialogMode === 'view' ? [<Button key="close" onClick={() => setDialogOpen(false)}>关闭</Button>] : [
          <Button key="cancel" onClick={() => setDialogOpen(false)}>取消</Button>,
          <Button key="save" type="primary" loading={dialogSaving} onClick={handleSave}>保存</Button>,
        ]}>
        <Row gutter={[12, 12]}>
          <Col span={12}><label style={{ fontSize: 13, fontWeight: 500 }}>任务名称</label>
            <Input value={dialogForm.task_name} disabled={dialogMode === 'view'}
              onChange={(e) => setDialogForm((f) => ({ ...f, task_name: e.target.value }))} /></Col>
          <Col span={12}><label style={{ fontSize: 13, fontWeight: 500 }}>任务类型</label>
            <Select value={dialogForm.task_type} disabled={dialogMode !== 'create'} style={{ width: '100%' }}
              onChange={(v) => setDialogForm((f) => ({ ...f, task_type: v }))}
              options={[{ value: 'periodic', label: '周期任务' }, { value: 'one_time', label: '一次性任务' }]} /></Col>
          <Col span={12}><label style={{ fontSize: 13, fontWeight: 500 }}>范围</label>
            <Select value={dialogForm.scope} disabled={dialogMode === 'view'} style={{ width: '100%' }}
              onChange={(v) => setDialogForm((f) => ({ ...f, scope: v }))}
              options={[{ value: 'system', label: '系统级' }, { value: 'user', label: '用户级' }]} /></Col>
          <Col span={12}><label style={{ fontSize: 13, fontWeight: 500 }}>执行器类型</label>
            <Select value={dialogForm.executor_kind} disabled={dialogMode === 'view'} style={{ width: '100%' }}
              onChange={(v) => setDialogForm((f) => ({ ...f, executor_kind: v }))}
              options={['builtin', 'bot', 'platform_agent'].map((v) => ({ value: v, label: executorLabel(v) }))} /></Col>
          {dialogForm.task_type === 'periodic' && (
            <Col span={12}><label style={{ fontSize: 13, fontWeight: 500 }}>调度表达式 (cron)</label>
              <Input value={dialogForm.schedule} disabled={dialogMode === 'view'}
                onChange={(e) => setDialogForm((f) => ({ ...f, schedule: e.target.value }))} placeholder="0 * * * *" /></Col>
          )}
          <Col span={24}><label style={{ fontSize: 13, fontWeight: 500 }}>处理器名称</label>
            <Input value={dialogForm.handler_name} disabled={dialogMode === 'view'}
              onChange={(e) => setDialogForm((f) => ({ ...f, handler_name: e.target.value }))} /></Col>
          <Col span={24}><label style={{ fontSize: 13, fontWeight: 500 }}>提示文本/Prompt</label>
            <Input.TextArea value={dialogForm.prompt_text} disabled={dialogMode === 'view'} rows={6}
              onChange={(e) => setDialogForm((f) => ({ ...f, prompt_text: e.target.value }))} /></Col>
        </Row>
      </Modal>
    </section>
  );
}
