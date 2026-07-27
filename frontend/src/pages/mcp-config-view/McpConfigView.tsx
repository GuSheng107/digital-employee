import { useEffect, useState, useCallback, useRef } from 'react';
import { Card, Button, Switch, Tag, Modal, Input, Select, Table, Divider, message, Space, Empty, Tabs, Popconfirm } from 'antd';
import { PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined, ApiOutlined, ImportOutlined, LinkOutlined } from '@ant-design/icons';
import { getMcpServers, saveMcpServer, deleteMcpServer, toggleMcpServer, importMcpServers, testMcpServerConnection, getMcpTools, refreshMcpTools } from '@/api/skills';
import type { ColumnsType } from 'antd/es/table';

interface McpServer {
  server_id: string;
  name: string;
  server_type: string;
  config: {
    transport?: string;
    command?: string;
    args?: string[];
    url?: string;
    headers?: Record<string, string>;
  };
  tools: Array<{ name: string; description?: string }>;
  is_active: boolean;
  scope?: string;
  is_bound_to_bot?: boolean;
  mounted_bot_names?: string[];
}

const MCP_TYPES = [
  { value: 'stdio', label: '标准输入输出 (stdio)' },
  { value: 'http', label: 'HTTP 服务' },
  { value: 'sse', label: 'SSE' },
  { value: 'streamable_http', label: 'Streamable HTTP' },
];

function emptyServer(): McpServer {
  return {
    server_id: '', name: '', server_type: 'stdio',
    config: { transport: 'stdio', command: '', args: [], url: '', headers: {} },
    tools: [], is_active: false,
  };
}

export default function McpConfigView() {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [loading, setLoading] = useState(false);
  const [tools, setTools] = useState<Array<{ name: string; description?: string }>>([]);
  const [toolsLoading, setToolsLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogMode, setDialogMode] = useState<'new' | 'edit' | 'import'>('new');
  const [editing, setEditing] = useState<McpServer>(emptyServer());
  const [importJson, setImportJson] = useState('');
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<Record<string, boolean>>({});

  const sortedServers = [...servers].sort((a, b) => {
    if (a.scope === 'system' && b.scope !== 'system') return -1;
    if (a.scope !== 'system' && b.scope === 'system') return 1;
    return 0;
  });

  const loadServers = useCallback(async () => {
    setLoading(true);
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result: any = await getMcpServers();
      setServers(result.servers || []);
    } catch (e) { message.error(String(e)); }
    finally { setLoading(false); }
  }, []);

  const loadTools = useCallback(async () => {
    setToolsLoading(true);
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const result: any = await getMcpTools();
      setTools(result.tools || []);
    } catch (e) { message.error(String(e)); }
    finally { setToolsLoading(false); }
  }, []);

  const didMount = useRef(false);
  useEffect(() => {
    if (!didMount.current) { didMount.current = true; loadServers(); loadTools(); }
  }, [loadServers, loadTools]);

  const handleRefreshTools = async () => {
    await refreshMcpTools();
    message.success('工具列表已刷新');
    await loadTools();
  };

  const openNew = () => {
    setDialogMode('new');
    setEditing(emptyServer());
    setImportJson('');
    setDialogOpen(true);
  };

  const openEdit = (server: McpServer) => {
    setDialogMode('edit');
    setEditing(JSON.parse(JSON.stringify(server)));
    setImportJson('');
    setDialogOpen(true);
  };

  const openImport = () => {
    setDialogMode('import');
    setEditing(emptyServer());
    setImportJson('');
    setDialogOpen(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (dialogMode === 'import') {
        if (!importJson.trim()) { message.warning('请粘贴 JSON 配置'); return; }
        await importMcpServers(JSON.parse(importJson));
        message.success('MCP 服务已导入');
      } else {
        const payload = { ...editing };
        if (payload.server_type === 'stdio') {
          payload.config.url = '';
          payload.config.headers = {};
        } else {
          payload.config.command = '';
          payload.config.args = [];
        }
        await saveMcpServer(payload);
        message.success(dialogMode === 'new' ? 'MCP 服务已创建' : 'MCP 服务已更新');
      }
      setDialogOpen(false);
      await loadServers();
    } catch (e) { message.error(String(e)); }
    finally { setSaving(false); }
  };

  const handleToggle = async (server: McpServer, active: boolean) => {
    await toggleMcpServer(server.server_id, active);
    message.success(active ? '已启用' : '已禁用');
    await loadServers();
  };

  const handleDelete = async (server: McpServer) => {
    await deleteMcpServer(server.server_id);
    message.success('MCP 服务已删除');
    await loadServers();
  };

  const handleTest = async (serverId: string) => {
    setTesting((p) => ({ ...p, [serverId]: true }));
    try {
      await testMcpServerConnection(serverId);
      message.success('连接测试成功');
    } catch (e) { message.error(String(e)); }
    finally { setTesting((p) => ({ ...p, [serverId]: false })); }
  };

  const isSystem = (s: McpServer) => s.scope === 'system';

  const toolColumns: ColumnsType<{ name: string; description?: string }> = [
    { title: '工具名称', dataIndex: 'name', key: 'name', width: 240 },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true },
  ];

  return (
    <section>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <h2 style={{ margin: 0 }}>MCP 配置</h2>
        <Space>
          <Button icon={<ReloadOutlined />} loading={loading} onClick={loadServers}>刷新</Button>
          <Button icon={<ImportOutlined />} onClick={openImport}>导入</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openNew}>新增 MCP 服务</Button>
        </Space>
      </div>

      <Tabs defaultActiveKey="servers" items={[
        {
          key: 'servers', label: `MCP 服务 (${servers.length})`,
          children: servers.length === 0 ? (
            <Empty description="暂无 MCP 服务" image={<ApiOutlined style={{ fontSize: 64, color: '#d9d9d9' }} />} />
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: 16 }}>
              {sortedServers.map((server) => (
                <Card key={server.server_id} hoverable size="small"
                  title={<Space>
                    <strong>{server.name || server.server_id}</strong>
                    {isSystem(server) && <Tag color="orange">系统</Tag>}
                    {server.is_bound_to_bot && <Tag color="red">已挂载</Tag>}
                  </Space>}
                  extra={<Switch checked={server.is_active} disabled={isSystem(server) || (server.is_bound_to_bot && server.is_active)}
                    onChange={(v) => handleToggle(server, v)} />}>
                  <p style={{ fontSize: 13, color: '#6b7280', margin: '0 0 8px' }}>
                    类型: {MCP_TYPES.find((t) => t.value === server.server_type)?.label || server.server_type}
                  </p>
                  <p style={{ fontSize: 13, color: '#6b7280', margin: '0 0 12px' }}>
                    工具数: {server.tools?.length || 0}
                  </p>
                  <Space>
                    <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(server)}
                      disabled={isSystem(server)}>{isSystem(server) ? '查看' : '编辑'}</Button>
                    <Button size="small" icon={<LinkOutlined />} loading={testing[server.server_id]}
                      onClick={() => handleTest(server.server_id)}>测试连接</Button>
                    <Popconfirm title="确定删除此 MCP 服务？" onConfirm={() => handleDelete(server)} okButtonProps={{ danger: true }}>
                      <Button size="small" danger icon={<DeleteOutlined />} disabled={isSystem(server)}>删除</Button>
                    </Popconfirm>
                  </Space>
                </Card>
              ))}
            </div>
          ),
        },
        {
          key: 'tools', label: `可用工具 (${tools.length})`,
          children: <>
            <div style={{ marginBottom: 12 }}>
              <Button icon={<ReloadOutlined />} loading={toolsLoading} onClick={handleRefreshTools}>刷新工具列表</Button>
            </div>
            <Table columns={toolColumns} dataSource={tools} rowKey="name" loading={toolsLoading} size="small" pagination={{ pageSize: 20 }} />
          </>,
        },
      ]} />

      {/* Add/Edit/Import Dialog */}
      <Modal title={dialogMode === 'new' ? '新增 MCP 服务' : dialogMode === 'import' ? '导入 MCP 服务' : isSystem(editing) ? '查看 MCP 服务' : '编辑 MCP 服务'}
        open={dialogOpen} onCancel={() => setDialogOpen(false)} width={640}
        footer={[
          <Button key="cancel" onClick={() => setDialogOpen(false)}>取消</Button>,
          !isSystem(editing) && <Button key="save" type="primary" loading={saving} onClick={handleSave}>
            {dialogMode === 'import' ? '导入' : '保存'}
          </Button>,
        ]}>
        {dialogMode === 'import' ? (
          <div>
            <p style={{ color: '#6b7280', marginBottom: 8 }}>粘贴一个 MCP 服务 JSON 配置或包含多个服务的数组</p>
            <Input.TextArea value={importJson} onChange={(e) => setImportJson(e.target.value)} rows={12}
              placeholder={`{"server_id":"...","name":"...","server_type":"stdio","config":{"command":"...","args":["..."]}}`} />
          </div>
        ) : (
          <>
            <div style={{ marginBottom: 12 }}>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>名称</label>
              <Input value={editing.name} disabled={isSystem(editing)}
                onChange={(e) => setEditing((p) => ({ ...p, name: e.target.value }))} placeholder="服务名称" />
            </div>
            <div style={{ marginBottom: 12 }}>
              <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>类型</label>
              <Select value={editing.server_type} disabled={isSystem(editing)} style={{ width: '100%' }}
                onChange={(v) => setEditing((p) => ({ ...p, server_type: v, config: { ...p.config, transport: v } }))}
                options={MCP_TYPES} />
            </div>
            {editing.server_type === 'stdio' ? (
              <>
                <div style={{ marginBottom: 12 }}>
                  <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>命令</label>
                  <Input value={editing.config.command || ''} disabled={isSystem(editing)}
                    onChange={(e) => setEditing((p) => ({ ...p, config: { ...p.config, command: e.target.value } }))} placeholder="例如: npx, python" />
                </div>
                <div style={{ marginBottom: 12 }}>
                  <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>参数（每行一个）</label>
                  <Input.TextArea value={(editing.config.args || []).join('\n')} disabled={isSystem(editing)} rows={4}
                    onChange={(e) => setEditing((p) => ({ ...p, config: { ...p.config, args: e.target.value.split('\n').filter(Boolean) } }))}
                    placeholder="每行一个参数" />
                </div>
              </>
            ) : (
              <div style={{ marginBottom: 12 }}>
                <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>URL</label>
                <Input value={editing.config.url || ''} disabled={isSystem(editing)}
                  onChange={(e) => setEditing((p) => ({ ...p, config: { ...p.config, url: e.target.value } }))} placeholder="https://..." />
              </div>
            )}
            {editing.tools?.length > 0 && (
              <>
                <Divider>工具列表 ({editing.tools.length})</Divider>
                <div style={{ maxHeight: 200, overflow: 'auto' }}>
                  {editing.tools.map((t) => (
                    <div key={t.name} style={{ padding: '4px 0', fontSize: 13 }}>
                      <strong>{t.name}</strong>
                      {t.description && <span style={{ color: '#6b7280', marginLeft: 8 }}>— {t.description}</span>}
                    </div>
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </Modal>
    </section>
  );
}
