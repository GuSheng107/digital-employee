import { useEffect, useState } from 'react';
import { Button, Popconfirm, Table, Tag, message } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { deleteBot, fetchBots, type BotItem } from '@/api/bot-api';
import SystemPage from '@/components/system-page/SystemPage';
import { getRequestErrorMessage } from '@/utils/request';
import { hasManagePermission, PERMISSION_CODE } from '@/constants/access-control';
import { useUserStore } from '@/store/user-store';
import BotFormModal from './components/BotFormModal';
import styles from './index.module.css';

const DEFAULT_PAGE_SIZE = 20;

export default function BotManagement(): React.ReactElement {
  const currentUser = useUserStore((state) => state.userInfo);
  /** 是否可管理 Bot（拥有 manage 权限；仅 readonly 时隐藏写操作入口） */
  const canManage = currentUser !== null
    && hasManagePermission(
      currentUser.roles,
      currentUser.permissions,
      PERMISSION_CODE.BOT_MANAGE,
    );

  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<BotItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  // 弹窗状态
  const [modalOpen, setModalOpen] = useState(false);
  const [editingBot, setEditingBot] = useState<BotItem | null>(null);

  async function loadData(targetPage: number = page, targetPageSize: number = pageSize): Promise<void> {
    setLoading(true);
    try {
      const res = await fetchBots(targetPage, targetPageSize);
      setItems(res.items);
      setTotal(res.total);
      setPage(res.page);
      setPageSize(res.page_size);
    } catch (error) {
      message.error(getRequestErrorMessage(error, '获取机器人配置列表失败'));
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
    setEditingBot(null);
    setModalOpen(true);
  }

  function handleEdit(record: BotItem): void {
    setEditingBot(record);
    setModalOpen(true);
  }

  async function handleDelete(botId: string): Promise<void> {
    try {
      await deleteBot(botId);
      message.success(`已成功移除 Bot '${botId}'`);
      void loadData(page, pageSize);
    } catch (error) {
      message.error(getRequestErrorMessage(error, '删除失败'));
    }
  }

  const columns: ColumnsType<BotItem> = [
    {
      title: 'Bot 唯一标识',
      dataIndex: 'bot_id',
      key: 'bot_id',
      render: (text: string) => <strong>{text}</strong>,
    },
    {
      title: '显示名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: '平台',
      dataIndex: 'platform',
      key: 'platform',
      render: (platform: string) => {
        if (platform === 'feishu') {
          return <Tag color="blue" className={styles.platformTag}>飞书</Tag>;
        }
        if (platform === 'wechat') {
          return <Tag color="green" className={styles.platformTag}>企业微信</Tag>;
        }
        return <Tag>{platform}</Tag>;
      },
    },
    {
      title: 'App ID',
      dataIndex: 'app_id',
      key: 'app_id',
      render: (text: string) => text || '-',
    },
    {
      title: 'App Secret',
      dataIndex: 'app_secret',
      key: 'app_secret',
      render: (text: string) => <span className={styles.secretText}>{text || '***'}</span>,
    },
    {
      title: '运行模式',
      dataIndex: 'mode',
      key: 'mode',
      render: (mode: string) => {
        return mode === 'prod' ? (
          <Tag color="success">PROD</Tag>
        ) : (
          <Tag color="warning">TEST</Tag>
        );
      },
    },
    {
      title: '关联 Agent',
      key: 'agent_name',
      render: (_: unknown, record: BotItem) => {
        if (!record.agent_id) {
          return <span style={{ color: '#8c8c8c' }}>-</span>;
        }
        return (
          <Tag color="purple">
            {record.agent_name || record.agent_id}
          </Tag>
        );
      },
    },
    {
      title: '上级部门',
      dataIndex: 'parent_bot_name',
      key: 'parent_bot_name',
      render: (name: string | null | undefined) =>
        name ? <Tag color="geekblue">{name}</Tag> : <span style={{ color: '#8c8c8c' }}>—</span>,
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
      width: 150,
      render: (_, record) => {
        // 只读用户不展示任何写操作入口
        if (!canManage) {
          return <span>—</span>;
        }
        return (
        <div style={{ display: 'flex', gap: 8 }}>
          <Button type="link" size="small" onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确定要软删除此机器人配置吗？"
            description={`删除后 Bot '${record.bot_id}' 将不可用`}
            onConfirm={() => void handleDelete(record.bot_id)}
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button type="link" danger size="small">
              删除
            </Button>
          </Popconfirm>
        </div>
        );
      },
    },
  ];

  return (
    <SystemPage
      title="Bot管理"
      sectionLabel="数字员工"
      actions={
        <div style={{ display: 'flex', gap: 8 }}>
          <Button icon={<ReloadOutlined />} onClick={() => void loadData(page, pageSize)}>
            刷新
          </Button>
          {canManage && (
            <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
              新增 Bot
            </Button>
          )}
        </div>
      }
    >
      <div className={styles.container}>
        <div className={styles.tableWrapper}>
          <Table<BotItem>
            rowKey="bot_id"
            loading={loading}
            columns={columns}
            dataSource={items}
            pagination={{
              current: page,
              pageSize,
              total,
              showSizeChanger: true,
              showTotal: (totalCount) => `共 ${totalCount} 条`,
              onChange: (p, ps) => {
                void loadData(p, ps);
              },
            }}
          />
        </div>
      </div>

      <BotFormModal
        open={modalOpen}
        editingBot={editingBot}
        onCancel={() => setModalOpen(false)}
        onSuccess={() => {
          setModalOpen(false);
          void loadData(1, pageSize);
        }}
      />
    </SystemPage>
  );
}
