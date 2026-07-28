import { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  Form,
  InputNumber,
  Modal,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  createInviteCode,
  fetchInviteCodes,
  type CreateInviteCodePayload,
  type CreateInviteCodeResult,
  type InviteCodeItem,
} from '@/api/invite-code-api';
import { getRequestErrorMessage } from '@/utils/request';
import styles from './index.module.css';

const { Title, Text } = Typography;

interface CreateInviteCodeFormValues {
  remaining: number;
  expiresInHours: number;
}

/** 将 Unix 秒级时间戳格式化为本地可读字符串 */
function formatTimestamp(seconds: number): string {
  if (!seconds) return '-';
  const date = new Date(seconds * 1000);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleString();
}

/** 从请求错误中提取用户可读的提示文案 */
function getErrorMessage(error: unknown): string {
  return getRequestErrorMessage(error, '操作失败，请稍后重试');
}

export default function InviteCode(): React.ReactElement {
  const [loading, setLoading] = useState<boolean>(false);
  const [inviteCodes, setInviteCodes] = useState<InviteCodeItem[]>([]);

  const [createOpen, setCreateOpen] = useState<boolean>(false);
  const [createSubmitting, setCreateSubmitting] = useState<boolean>(false);
  const [createForm] = Form.useForm<CreateInviteCodeFormValues>();

  const [createdResult, setCreatedResult] = useState<CreateInviteCodeResult | null>(null);

  const stats = useMemo(() => {
    const total = inviteCodes.length;
    const valid = inviteCodes.filter((item) => item.is_valid).length;
    return { total, valid, invalid: total - valid };
  }, [inviteCodes]);

  async function loadInviteCodes(): Promise<void> {
    setLoading(true);
    try {
      const list = await fetchInviteCodes();
      setInviteCodes(list);
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  // 初始数据加载：effect 仅在挂载时执行一次，loadInviteCodes 内部 setState 为异步流程，
  // 不会在 effect 同步阶段触发级联渲染，符合 react-hooks 规范例外。
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadInviteCodes();
  }, []);

  function openCreateModal(): void {
    createForm.resetFields();
    setCreateOpen(true);
  }

  async function handleCreateSubmit(values: CreateInviteCodeFormValues): Promise<void> {
    setCreateSubmitting(true);
    try {
      const payload: CreateInviteCodePayload = {
        remaining: values.remaining,
        expires_in_hours: values.expiresInHours,
      };
      const result = await createInviteCode(payload);
      message.success(`邀请码创建成功：${result.code}`);
      setCreateOpen(false);
      setCreatedResult(result);
      await loadInviteCodes();
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setCreateSubmitting(false);
    }
  }

  async function handleCopyCode(code: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(code);
      message.success('邀请码已复制到剪贴板');
    } catch {
      message.error('复制失败，请手动复制');
    }
  }

  const columns: ColumnsType<InviteCodeItem> = [
    {
      title: '邀请码',
      dataIndex: 'code',
      width: 160,
      render: (value: string) => <Tag className={styles.codeTag}>{value}</Tag>,
    },
    {
      title: '剩余次数',
      dataIndex: 'remaining',
      width: 100,
      render: (value: number) =>
        value > 0 ? value : <Tag color="red">0</Tag>,
    },
    {
      title: '过期时间',
      dataIndex: 'expires_at',
      width: 180,
      render: (value: number) => formatTimestamp(value),
    },
    {
      title: '状态',
      dataIndex: 'is_valid',
      width: 90,
      render: (value: boolean) =>
        value ? <Tag color="green">有效</Tag> : <Tag color="red">失效</Tag>,
    },
    {
      title: '创建人',
      dataIndex: 'created_by',
      width: 100,
      render: (value: number) => `用户 ${value}`,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 180,
      render: (value: number) => formatTimestamp(value),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_, record) => (
        <Button
          type="link"
          size="small"
          className={styles.copyBtn}
          onClick={() => void handleCopyCode(record.code)}
        >
          复制
        </Button>
      ),
    },
  ];

  return (
    <div className={styles.container}>
      <div className={styles.toolbar}>
        <Title level={3} style={{ margin: 0 }}>
          邀请码管理
        </Title>
        <Space>
          <Button onClick={() => void loadInviteCodes()}>刷新</Button>
          <Button type="primary" onClick={openCreateModal}>
            新建邀请码
          </Button>
        </Space>
      </div>

      <div className={styles.statsCards}>
        <Card className={styles.statCard}>
          <Statistic title="总邀请码数" value={stats.total} />
        </Card>
        <Card className={styles.statCard}>
          <Statistic
            title="有效邀请码"
            value={stats.valid}
            styles={{ content: { color: '#52c41a' } }}
          />
        </Card>
        <Card className={styles.statCard}>
          <Statistic
            title="已用完/过期"
            value={stats.invalid}
            styles={{ content: { color: '#cf1322' } }}
          />
        </Card>
      </div>

      <div className={styles.tableWrapper}>
        <Table<InviteCodeItem>
          rowKey="code"
          columns={columns}
          dataSource={inviteCodes}
          loading={loading}
          pagination={{
            pageSize: 10,
            showTotal: (total) => `共 ${total} 条`,
          }}
        />
      </div>

      <Modal
        open={createOpen}
        title="新建邀请码"
        width={480}
        onCancel={() => setCreateOpen(false)}
        onOk={() => createForm.submit()}
        confirmLoading={createSubmitting}
        okText="创建"
        cancelText="取消"
      >
        <Form<CreateInviteCodeFormValues>
          form={createForm}
          layout="vertical"
          initialValues={{ remaining: 1, expiresInHours: 168 }}
          onFinish={handleCreateSubmit}
        >
          <Form.Item
            label="可用次数"
            name="remaining"
            rules={[{ required: true, message: '请输入可用次数' }]}
          >
            <InputNumber min={1} max={100} precision={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            label="过期时间（小时）"
            name="expiresInHours"
            rules={[{ required: true, message: '请输入过期时间' }]}
            extra="默认 168 小时（7 天），最大 720 小时（30 天）"
          >
            <InputNumber min={1} max={720} precision={0} style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        open={createdResult !== null}
        title="邀请码创建成功"
        width={440}
        onCancel={() => setCreatedResult(null)}
        footer={[
          <Button
            key="copy"
            onClick={() => {
              if (createdResult) void handleCopyCode(createdResult.code);
            }}
          >
            复制邀请码
          </Button>,
          <Button key="close" type="primary" onClick={() => setCreatedResult(null)}>
            关闭
          </Button>,
        ]}
      >
        {createdResult ? (
          <div className={styles.resultContent}>
            <Text>新邀请码：</Text>
            <Tag className={styles.codeTag}>{createdResult.code}</Tag>
            <div className={styles.resultMeta}>
              <Text type="secondary">
                剩余次数：{createdResult.remaining} 过期时间：
                {formatTimestamp(createdResult.expires_at)}
              </Text>
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
