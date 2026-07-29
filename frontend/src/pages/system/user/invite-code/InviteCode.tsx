import { useCallback, useEffect, useState } from 'react';
import {
  Button,
  Form,
  Input,
  InputNumber,
  Modal,
  Space,
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
import {
  INVITE_CODE_MESSAGE,
  INVITE_CODE_PATTERN,
} from '@/utils/identity-validation';
import SystemPage from '@/components/system-page/SystemPage';
import {
  createTablePagination,
  DEFAULT_TABLE_PAGE_SIZE,
} from '@/utils/table-pagination';
import styles from './index.module.css';

const { Text } = Typography;

interface CreateInviteCodeFormValues {
  customCode?: string;
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
  const [page, setPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(DEFAULT_TABLE_PAGE_SIZE);
  const [total, setTotal] = useState<number>(0);
  const [inviteCodes, setInviteCodes] = useState<InviteCodeItem[]>([]);

  const [createOpen, setCreateOpen] = useState<boolean>(false);
  const [createSubmitting, setCreateSubmitting] = useState<boolean>(false);
  const [createForm] = Form.useForm<CreateInviteCodeFormValues>();

  const [createdResult, setCreatedResult] = useState<CreateInviteCodeResult | null>(null);

  const fetchPage = useCallback(async (
    pageNumber: number,
    currentPageSize: number,
  ): Promise<void> => {
    setLoading(true);
    try {
      const response = await fetchInviteCodes(pageNumber, currentPageSize);
      setInviteCodes(response.items);
      setTotal(response.total);
      setPage(response.page);
      setPageSize(response.page_size);
    } catch (error) {
      message.error(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, []);

  async function loadInviteCodes(
    pageNumber: number = page,
    currentPageSize: number = pageSize,
  ): Promise<void> {
    await fetchPage(pageNumber, currentPageSize);
  }

  // 把初始请求调度到下一轮任务，避免 effect 同步阶段触发状态级联更新。
  useEffect(() => {
    const timerId = window.setTimeout(() => {
      void fetchPage(1, DEFAULT_TABLE_PAGE_SIZE);
    }, 0);
    return () => window.clearTimeout(timerId);
  }, [fetchPage]);

  function openCreateModal(): void {
    createForm.resetFields();
    setCreateOpen(true);
  }

  async function handleCreateSubmit(values: CreateInviteCodeFormValues): Promise<void> {
    setCreateSubmitting(true);
    try {
      const payload: CreateInviteCodePayload = {
        custom_code: values.customCode?.trim().toUpperCase() || undefined,
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
      fixed: 'right',
      width: 100,
      align: 'center',
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
    <SystemPage
      title="邀请码管理"
      actions={(
        <Space>
          <Button onClick={() => void loadInviteCodes()}>刷新</Button>
          <Button type="primary" onClick={openCreateModal}>
            新建邀请码
          </Button>
        </Space>
      )}
    >
      <div className={styles.container}>

        <div className={styles.tableWrapper}>
          <Table<InviteCodeItem>
            rowKey="code"
            columns={columns}
            dataSource={inviteCodes}
            loading={loading}
            sticky
            scroll={{ x: 1060, y: 'calc(100vh - 250px)' }}
            pagination={createTablePagination({
              current: page,
              pageSize,
              total,
              onChange: (nextPage, nextPageSize) => {
                void loadInviteCodes(nextPage, nextPageSize);
              },
            })}
          />
        </div>
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
            label="自定义邀请码（可选）"
            name="customCode"
            rules={[
              {
                pattern: INVITE_CODE_PATTERN,
                message: INVITE_CODE_MESSAGE,
              },
            ]}
            extra="留空时系统自动生成 8 位邀请码"
          >
            <Input
              maxLength={32}
              placeholder="例如 TEAM-2026"
              autoComplete="off"
            />
          </Form.Item>
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
    </SystemPage>
  );
}
