import { useEffect, useState } from 'react';
import { Button, Popconfirm, Table, Tag, message } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { deleteAgent, fetchAgents, type AgentItem } from '@/api/agent-api';
import SystemPage from '@/components/system-page/SystemPage';
import { getRequestErrorMessage } from '@/utils/request';
import AgentFormModal from './components/AgentFormModal';

const DEFAULT_PAGE_SIZE = 20;

export default function AgentManagement(): React.ReactElement {
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<AgentItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  // 弹窗状态
  const [modalOpen, setModalOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<AgentItem | null>(null);

  async function loadData(targetPage: number = page, targetPageSize: number = pageSize): Promise<void> {
    setLoading(true);
    try {
      const res = await fetchAgents(targetPage, targetPageSize);
      setItems(res.items);
      setTotal(res.total);
      setPage(res.page);
      setPageSize(res.page_size);
    } catch (error) {
      message.error(getRequestErrorMessage(error, '获取 Agent 列表失败'));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    // 组件挂载时加载首页数据，setState 在异步回调中执行，属于合理的 effect 用法
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadData(1, DEFAULT_PAGE_SIZE);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleCreate(): void {
    setEditingAgent(null);
    setModalOpen(true);
  }

  function handleEdit(record: AgentItem): void {
    setEditingAgent(record);
    setModalOpen(true);
  }

  async function handleDelete(agentId: string): Promise<void> {
    try {
      await deleteAgent(agentId);
      message.success(`已成功移除 Agent '${agentId}'`);
      void loadData(page, pageSize);
    } catch (error) {
      message.error(getRequestErrorMessage(error, '删除失败'));
    }
  }

  const columns: ColumnsType<AgentItem> = [
    {
      title: 'Agent 唯一标识',
      dataIndex: 'agent_id',
      key: 'agent_id',
      render: (text: string) => <strong>{text}</strong>,
    },
    {
      title: '显示名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: number) => {
        return status === 1 ? (
          <Tag color="success">启用</Tag>
        ) : (
          <Tag color="default">禁用</Tag>
        );
      },
    },
    {
      title: '创建者',
      dataIndex: 'created_by_name',
      key: 'created_by_name',
      render: (name: string | null) => name || '系统',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (text: string | null) => (text ? text.replace('T', ' ').slice(0, 19) : '-'),
    },
    {
      title: '操作',
      key: 'action',
      render: (_: unknown, record: AgentItem) => (
        <span style={{ display: 'inline-flex', gap: 8 }}>
          <Button type="link" size="small" onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确认要删除此 Agent 吗？"
            description="删除后同名 agent_id 可再次重新创建。"
            onConfirm={() => void handleDelete(record.agent_id)}
            okText="确认删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button type="link" size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </span>
      ),
    },
  ];

  return (
    <SystemPage
      title="Agent 管理"
      sectionLabel="数字员工"
      actions={
        <span style={{ display: 'inline-flex', gap: 8 }}>
          <Button icon={<ReloadOutlined />} onClick={() => void loadData()}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            新建 Agent
          </Button>
        </span>
      }
    >
      <Table
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={items}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          onChange: (p, ps) => void loadData(p, ps),
        }}
      />

      <AgentFormModal
        open={modalOpen}
        editingAgent={editingAgent}
        onCancel={() => setModalOpen(false)}
        onSuccess={() => {
          setModalOpen(false);
          void loadData(page, pageSize);
        }}
      />
    </SystemPage>
  );
}
