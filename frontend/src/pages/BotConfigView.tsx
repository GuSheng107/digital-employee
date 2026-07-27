import { useEffect, useState } from 'react';
import { Card, Table, Button, Modal, Input, Select, Switch, message, Space, Popconfirm, Tabs } from 'antd';
import { PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined, LinkOutlined } from '@ant-design/icons';
import { getBots, saveBot, batchDeleteBots, restoreDeletedBots, toggleBot, rebindBot, unbindBot, getBotSkills, saveBotSkills, getBotMcpServers, saveBotMcpServers, type BotListResponse, type BotSkillsResponse, type BotMcpServersResponse, type SaveBotPayload } from '@/api/bots';
import { getAgents, type AgentListResponse } from '@/api/agents';
import { getSkills } from '@/api/skills';
import { getMcpServers } from '@/api/skills';
import type { ColumnsType } from 'antd/es/table';

interface Bot {
  bot_key: string;
  name?: string;
  agent_provider?: string;
  is_active?: boolean;
  is_deleted?: boolean;
  is_bound?: boolean;
  enabled_mcp_count?: number;
  enabled_skill_count?: number;
  [key: string]: unknown;
}

interface AgentOption { provider_key: string; label?: string; provider_name?: string; }

export default function BotConfigView() {
  const [bots, setBots] = useState<Bot[]>([]);
  const [loading, setLoading] = useState(false);
  const [agents, setAgents] = useState<AgentOption[]>([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [isEdit, setIsEdit] = useState(false);
  const [editing, setEditing] = useState<Partial<Bot>>({});
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState('active');
  const [skillsList, setSkillsList] = useState<string[]>([]);
  const [mcpList, setMcpList] = useState<string[]>([]);
  const [skillDialogOpen, setSkillDialogOpen] = useState(false);
  const [mcpDialogOpen, setMcpDialogOpen] = useState(false);
  const [editBotKey, setEditBotKey] = useState('');
  const [allSkills, setAllSkills] = useState<Array<{ name: string; display_name?: string }>>([]);
  const [allMcp, setAllMcp] = useState<Array<{ server_id: string; name: string }>>([]);

  const loadBots = async () => {
    setLoading(true);
    try {
      const result = await getBots({ include_deleted: true }) as BotListResponse;
      setBots(result.bots || []);
    } catch (e) { message.error(String(e)); }
    finally { setLoading(false); }
  };

  const loadAgents = async () => {
    try {
      const result = await getAgents() as AgentListResponse;
      setAgents(result.agents || []);
    } catch { /* ignore */ }
  };

  const loadSkills = async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    try { const r: any = await getSkills(); setAllSkills(r.skills || []); } catch { /* ignore */ }
  };

  const loadMcp = async () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    try { const r: any = await getMcpServers(); setAllMcp(r.servers || []); } catch { /* ignore */ }
  };

  useEffect(() => { loadBots(); loadAgents(); loadSkills(); loadMcp(); }, []); // eslint-disable-line

  const openNew = () => { setEditing({ name: '', agent_provider: '', is_active: false }); setIsEdit(false); setDialogOpen(true); };
  const openEdit = (bot: Bot) => { setEditing({ ...bot }); setIsEdit(true); setDialogOpen(true); };

  const handleSave = async () => {
    setSaving(true);
    try {
      await saveBot(editing as SaveBotPayload, isEdit ? 'edit' : 'add');
      message.success(isEdit ? 'Bot 已更新' : 'Bot 已创建');
      setDialogOpen(false);
      loadBots();
    } catch (e) { message.error(String(e)); }
    finally { setSaving(false); }
  };

  const handleToggle = async (bot: Bot, active: boolean) => {
    await toggleBot(bot.bot_key, active);
    message.success(active ? '已启用' : '已禁用');
    loadBots();
  };

  const handleDelete = async (keys: string[]) => { await batchDeleteBots(keys); message.success('已删除'); loadBots(); };
  const handleRestore = async (keys: string[]) => { await restoreDeletedBots(keys); message.success('已恢复'); loadBots(); };
  const handleRebind = async (key: string) => { await rebindBot(key); message.success('已重新绑定'); loadBots(); };
  const handleUnbind = async (key: string) => { await unbindBot(key); message.success('已解绑'); loadBots(); };

  const openSkillDialog = async (botKey: string) => {
    setEditBotKey(botKey);
    try {
      const result = await getBotSkills(botKey) as BotSkillsResponse;
      setSkillsList(result.skill_names || []);
    } catch { setSkillsList([]); }
    setSkillDialogOpen(true);
  };

  const saveSkills = async () => { await saveBotSkills(editBotKey, skillsList); message.success('Skills 已保存'); setSkillDialogOpen(false); loadBots(); };

  const openMcpDialog = async (botKey: string) => {
    setEditBotKey(botKey);
    try {
      const result = await getBotMcpServers(botKey) as BotMcpServersResponse;
      setMcpList(result.server_ids || []);
    } catch { setMcpList([]); }
    setMcpDialogOpen(true);
  };

  const filteredBots = bots.filter((b) => tab === 'active' ? !b.is_deleted : b.is_deleted);

  const columns: ColumnsType<Bot> = [
    { title: '名称', dataIndex: 'name', ellipsis: true, width: 140 },
    { title: 'Bot Key', dataIndex: 'bot_key', ellipsis: true, width: 180 },
    { title: 'Agent', dataIndex: 'agent_provider', width: 160, render: (v: string) => agents.find((a) => a.provider_key === v)?.label || agents.find((a) => a.provider_name === v)?.provider_name || v || '-' },
    { title: '状态', dataIndex: 'is_active', width: 70, render: (v: boolean, r) => <Switch checked={v} onChange={(val) => handleToggle(r, val)} /> },
    { title: 'MCP/Skills', width: 120, render: (_, r) => <span>MCP: {r.enabled_mcp_count || 0} Skill: {r.enabled_skill_count || 0}</span> },
    { title: '操作', width: 320, fixed: 'right', render: (_, r) => (
      <Space size="small" wrap>
        <Button size="small" type="link" icon={<EditOutlined />} onClick={() => openEdit(r)}>编辑</Button>
        {tab === 'active' ? (
          <>
            <Button size="small" type="link" onClick={() => openSkillDialog(r.bot_key)}>Skills</Button>
            <Button size="small" type="link" onClick={() => openMcpDialog(r.bot_key)}>MCP</Button>
            <Button size="small" type="link" icon={<LinkOutlined />} onClick={() => handleRebind(r.bot_key)}>重绑</Button>
            <Button size="small" type="link" danger onClick={() => handleUnbind(r.bot_key)}>解绑</Button>
            <Popconfirm title="确定删除？" onConfirm={() => handleDelete([r.bot_key])}><Button size="small" type="link" danger icon={<DeleteOutlined />} /></Popconfirm>
          </>
        ) : (
          <Popconfirm title="恢复此 Bot？" onConfirm={() => handleRestore([r.bot_key])}><Button size="small" type="link">恢复</Button></Popconfirm>
        )}
      </Space>
    )},
  ];

  return (
    <section>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>Bot 配置</h2>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadBots}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openNew}>新增 Bot</Button>
        </Space>
      </div>

      <Card className="panel" size="small">
        <Tabs activeKey={tab} onChange={setTab} items={[
          { key: 'active', label: `启用 Bot (${bots.filter((b) => !b.is_deleted).length})` },
          { key: 'deleted', label: `已删除 (${bots.filter((b) => b.is_deleted).length})` },
        ]} />
        <Table<Bot> columns={columns} dataSource={filteredBots} rowKey="bot_key"
          loading={loading} size="small" scroll={{ x: 1200 }}
          pagination={{ pageSize: 20, showSizeChanger: true }} />
      </Card>

      {/* Add/Edit Dialog */}
      <Modal title={isEdit ? '编辑 Bot' : '新增 Bot'} open={dialogOpen} onCancel={() => setDialogOpen(false)} width={520}
        footer={[<Button key="cancel" onClick={() => setDialogOpen(false)}>取消</Button>, <Button key="save" type="primary" loading={saving} onClick={handleSave}>保存</Button>]}>
        <div style={{ display: 'grid', gap: 12 }}>
          <div><label style={{ fontSize: 13, fontWeight: 500 }}>名称</label>
            <Input value={editing.name} onChange={(e) => setEditing((p) => ({ ...p, name: e.target.value }))} /></div>
          <div><label style={{ fontSize: 13, fontWeight: 500 }}>Agent Provider</label>
            <Select value={editing.agent_provider} style={{ width: '100%' }} showSearch
              onChange={(v) => setEditing((p) => ({ ...p, agent_provider: v }))}
              options={agents.map((a) => ({ value: a.provider_key, label: a.label || a.provider_name || a.provider_key }))} /></div>
          <div><label style={{ fontSize: 13, fontWeight: 500 }}>Bot Key</label>
            <Input value={editing.bot_key} disabled={isEdit} onChange={(e) => setEditing((p) => ({ ...p, bot_key: e.target.value }))} /></div>
        </div>
      </Modal>

      {/* Skills Dialog */}
      <Modal title="配置 Skills" open={skillDialogOpen} onCancel={() => setSkillDialogOpen(false)} width={520}
        footer={[<Button key="cancel" onClick={() => setSkillDialogOpen(false)}>取消</Button>, <Button key="save" type="primary" onClick={saveSkills}>保存</Button>]}>
        <Select mode="multiple" value={skillsList} style={{ width: '100%' }} onChange={setSkillsList}
          options={allSkills.map((s) => ({ value: s.name, label: s.display_name || s.name }))} />
      </Modal>

      {/* MCP Dialog */}
      <Modal title="配置 MCP 服务" open={mcpDialogOpen} onCancel={() => setMcpDialogOpen(false)} width={520}
        footer={[<Button key="cancel" onClick={() => setMcpDialogOpen(false)}>取消</Button>, <Button key="save" type="primary" onClick={() => { saveBotMcpServers(editBotKey, mcpList); message.success('MCP 服务已保存'); setMcpDialogOpen(false); loadBots(); }}>保存</Button>]}>
        <Select mode="multiple" value={mcpList} style={{ width: '100%' }} onChange={setMcpList}
          options={allMcp.map((s) => ({ value: s.server_id, label: s.name || s.server_id }))} />
      </Modal>
    </section>
  );
}
