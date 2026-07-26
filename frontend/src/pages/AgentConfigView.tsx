import { useEffect, useState } from 'react';
import { Card, Table, Tag, Button, Modal, Input, Select, InputNumber, Switch, message, Space, Popconfirm } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons';
import { getAgents, saveAgent, toggleAgent, testAgent, batchDeleteAgents } from '@/api/agents';
import { formatTime } from '@/utils/format';
import type { ColumnsType } from 'antd/es/table';

interface Agent {
  provider_key: string;
  label?: string;
  provider_type?: string;
  provider_name?: string;
  model?: string;
  base_url?: string;
  api_key?: string;
  temperature?: number;
  timeout_seconds?: number;
  max_retries?: number;
  reasoning_effort?: string;
  is_active?: boolean;
  is_bound_to_bot?: boolean;
  last_test_status?: string;
  last_test_time?: string;
  last_test_trace_id?: string;
  mounted_bot_names?: string[];
  [key: string]: unknown;
}

const PROVIDER_TYPES = [
  { value: 'openai', label: 'OpenAI' }, { value: 'claude', label: 'Claude (Anthropic)' },
  { value: 'gemini', label: 'Gemini (Google)' }, { value: 'deepseek', label: 'DeepSeek' },
  { value: 'dashscope', label: 'DashScope (通义千问)' }, { value: 'zhipu', label: '智谱 GLM' },
  { value: 'minimax', label: 'MiniMax' }, { value: 'moonshot', label: 'Kimi (Moonshot)' },
  { value: 'openai_compatible', label: '自定义 / 本地模型' },
];

function emptyAgent(): Agent {
  return { provider_key: '', label: '', provider_type: 'openai', provider_name: '', model: '', base_url: '', api_key: '', temperature: 0.2, timeout_seconds: 60, max_retries: 1, reasoning_effort: '', is_active: false };
}

export default function AgentConfigView() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Agent>(emptyAgent());
  const [isEdit, setIsEdit] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);

  const loadAgents = async () => {
    setLoading(true);
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result: any = await getAgents();
      setAgents(result.agents || result || []);
    } catch (e) { message.error(String(e)); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadAgents(); }, []); // eslint-disable-line

  const openNew = () => { setEditing(emptyAgent()); setIsEdit(false); setDialogOpen(true); };
  const openEdit = (agent: Agent) => { setEditing({ ...agent }); setIsEdit(true); setDialogOpen(true); };

  const handleSave = async () => {
    setSaving(true);
    try {
      await saveAgent(editing, isEdit ? 'edit' : 'add');
      message.success(isEdit ? 'Agent 已更新' : 'Agent 已创建');
      setDialogOpen(false);
      loadAgents();
    } catch (e) { message.error(String(e)); }
    finally { setSaving(false); }
  };

  const handleToggle = async (agent: Agent, active: boolean) => {
    await toggleAgent(agent.provider_key, active);
    message.success(active ? '已启用' : '已禁用');
    loadAgents();
  };

  const handleTest = async (key: string) => {
    setTesting(key);
    try { await testAgent(key); message.success('测试请求已发送'); }
    catch (e) { message.error(String(e)); }
    finally { setTesting(null); }
  };

  const handleBatchDelete = async (keys: string[]) => {
    await batchDeleteAgents(keys);
    message.success('已删除');
    loadAgents();
  };

  const isSystemManaged = (agent: Agent) => agent.is_bound_to_bot;

  const columns: ColumnsType<Agent> = [
    { title: '名称', dataIndex: 'label', ellipsis: true, width: 140 },
    { title: 'Provider Key', dataIndex: 'provider_key', ellipsis: true, width: 200 },
    { title: '类型', dataIndex: 'provider_type', width: 140, render: (v: string) => PROVIDER_TYPES.find((t) => t.value === v)?.label || v },
    { title: 'Model', dataIndex: 'model', width: 140, ellipsis: true },
    { title: '状态', dataIndex: 'is_active', width: 70, render: (v: boolean, r) => <Switch checked={v} disabled={isSystemManaged(r) && v} onChange={(val) => handleToggle(r, val)} /> },
    { title: '挂载 Bot', width: 140, render: (_, r) => r.mounted_bot_names?.join(', ') || <span style={{ color: '#9ca3af' }}>-</span> },
    { title: '最后测试', dataIndex: 'last_test_time', width: 100, render: (v: string, r) => <span>{v ? formatTime(v) : '-'}<br /><Tag color={r.last_test_status === 'ok' ? 'green' : 'red'} style={{ fontSize: 10 }}>{r.last_test_status || '-'}</Tag></span> },
    { title: '操作', width: 180, fixed: 'right', render: (_, r) => (
      <Space size="small">
        <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEdit(r)} disabled={isSystemManaged(r)}>编辑</Button>
        <Button size="small" type="link" icon={<PlayCircleOutlined />} loading={testing === r.provider_key} onClick={() => handleTest(r.provider_key)}>测试</Button>
        <Popconfirm title="确定删除？" onConfirm={() => handleBatchDelete([r.provider_key])}>
          <Button size="small" type="link" danger icon={<DeleteOutlined />} disabled={isSystemManaged(r)} />
        </Popconfirm>
      </Space>
    )},
  ];

  return (
    <section>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>Agents 配置</h2>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadAgents}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openNew}>新增 Agent</Button>
        </Space>
      </div>

      <Card className="panel" size="small">
        <Table<Agent> columns={columns} dataSource={agents} rowKey="provider_key"
          loading={loading} size="small" scroll={{ x: 1100 }}
          pagination={{ pageSize: 20, showSizeChanger: true }} />
      </Card>

      <Modal title={isEdit ? '编辑 Agent' : '新增 Agent'} open={dialogOpen} onCancel={() => setDialogOpen(false)} width={640}
        footer={[<Button key="cancel" onClick={() => setDialogOpen(false)}>取消</Button>, <Button key="save" type="primary" loading={saving} onClick={handleSave}>保存</Button>]}>
        <div style={{ display: 'grid', gap: 12 }}>
          <div>
            <label style={{ fontSize: 13, fontWeight: 500 }}>Provider Key</label>
            <Input value={editing.provider_key} disabled={isEdit} onChange={(e) => setEditing((p) => ({ ...p, provider_key: e.target.value }))} placeholder="唯一标识" />
          </div>
          <div>
            <label style={{ fontSize: 13, fontWeight: 500 }}>显示名称</label>
            <Input value={editing.label} onChange={(e) => setEditing((p) => ({ ...p, label: e.target.value }))} />
          </div>
          <div>
            <label style={{ fontSize: 13, fontWeight: 500 }}>提供商类型</label>
            <Select value={editing.provider_type} style={{ width: '100%' }} onChange={(v) => setEditing((p) => ({ ...p, provider_type: v }))}
              options={PROVIDER_TYPES} />
          </div>
          <div>
            <label style={{ fontSize: 13, fontWeight: 500 }}>Model</label>
            <Input value={editing.model} onChange={(e) => setEditing((p) => ({ ...p, model: e.target.value }))} placeholder="例如 gpt-4o, claude-opus-4-8" />
          </div>
          <div>
            <label style={{ fontSize: 13, fontWeight: 500 }}>Base URL</label>
            <Input value={editing.base_url} onChange={(e) => setEditing((p) => ({ ...p, base_url: e.target.value }))} placeholder="留空使用默认地址" />
          </div>
          <div>
            <label style={{ fontSize: 13, fontWeight: 500 }}>API Key</label>
            <Input.Password value={editing.api_key} onChange={(e) => setEditing((p) => ({ ...p, api_key: e.target.value }))} placeholder={isEdit ? '留空保持原值' : ''} />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
            <div><label style={{ fontSize: 13, fontWeight: 500 }}>Temperature</label>
              <InputNumber value={editing.temperature} min={0} max={2} step={0.1} style={{ width: '100%' }} onChange={(v) => setEditing((p) => ({ ...p, temperature: v ?? 0.2 }))} /></div>
            <div><label style={{ fontSize: 13, fontWeight: 500 }}>超时(秒)</label>
              <InputNumber value={editing.timeout_seconds} min={10} max={300} style={{ width: '100%' }} onChange={(v) => setEditing((p) => ({ ...p, timeout_seconds: v ?? 60 }))} /></div>
            <div><label style={{ fontSize: 13, fontWeight: 500 }}>最大重试</label>
              <InputNumber value={editing.max_retries} min={0} max={10} style={{ width: '100%' }} onChange={(v) => setEditing((p) => ({ ...p, max_retries: v ?? 1 }))} /></div>
          </div>
          {editing.provider_type === 'claude' && (
            <div>
              <label style={{ fontSize: 13, fontWeight: 500 }}>思考强度</label>
              <Select value={editing.reasoning_effort || ''} style={{ width: '100%' }} onChange={(v) => setEditing((p) => ({ ...p, reasoning_effort: v }))}
                options={[{ value: '', label: '关闭思考' }, { value: 'low', label: '低' }, { value: 'medium', label: '中' }, { value: 'high', label: '高' }]} />
            </div>
          )}
        </div>
      </Modal>
    </section>
  );
}
