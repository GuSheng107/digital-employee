import { useEffect, useState } from 'react';
import { Form, Input, Modal, Select, message } from 'antd';
import { createBot, updateBot, type BotItem, type CreateBotPayload, type UpdateBotPayload } from '../api/bot-api';
import { fetchAgents, type AgentItem } from '../../agent/api/agent-api';
import { getRequestErrorMessage } from '@/utils/request';

interface BotFormModalProps {
  open: boolean;
  editingBot?: BotItem | null;
  onCancel: () => void;
  onSuccess: () => void;
}

export default function BotFormModal({
  open,
  editingBot,
  onCancel,
  onSuccess,
}: BotFormModalProps): React.ReactElement {
  const [form] = Form.useForm();
  const [agents, setAgents] = useState<AgentItem[]>([]);
  const isEditing = Boolean(editingBot);

  useEffect(() => {
    if (open) {
      void fetchAgents(1, 100)
        .then((res) => {
          setAgents(res.items);
        })
        .catch(() => {
          // 忽略无影响的静默失败
        });

      if (editingBot) {
        form.setFieldsValue({
          bot_id: editingBot.bot_id,
          name: editingBot.name,
          platform: editingBot.platform,
          app_id: editingBot.app_id,
          app_secret: '', // 编辑时密码框留空，若填写则更新
          mode: editingBot.mode,
          agent_id: editingBot.agent_id || undefined,
        });
      } else {
        form.resetFields();
        form.setFieldsValue({
          platform: 'feishu',
          mode: 'test',
        });
      }
    }
  }, [open, editingBot, form]);

  async function handleSubmit(): Promise<void> {
    try {
      const values = await form.validateFields();
      if (isEditing && editingBot) {
        const updatePayload: UpdateBotPayload = {
          name: values.name,
          platform: values.platform,
          app_id: values.app_id,
          mode: values.mode,
          agent_id: values.agent_id || null,
        };
        if (values.app_secret) {
          updatePayload.app_secret = values.app_secret;
        }
        await updateBot(editingBot.bot_id, updatePayload);
        message.success('更新机器人成功');
      } else {
        const createPayload: CreateBotPayload = {
          bot_id: values.bot_id,
          name: values.name,
          platform: values.platform,
          app_id: values.app_id,
          app_secret: values.app_secret,
          mode: values.mode,
          agent_id: values.agent_id || null,
        };
        await createBot(createPayload);
        message.success('新增机器人成功');
      }
      onSuccess();
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) {
        return; // 表单校验未通过
      }
      message.error(getRequestErrorMessage(error, '保存机器人配置失败'));
    }
  }

  return (
    <Modal
      title={isEditing ? '编辑机器人配置' : '新增机器人配置'}
      open={open}
      onOk={() => void handleSubmit()}
      onCancel={onCancel}
      destroyOnClose
    >
      <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
        <Form.Item
          name="bot_id"
          label="Bot 唯一标识 (bot_id)"
          rules={[
            { required: true, message: '请输入 Bot 唯一标识' },
            { pattern: /^[a-zA-Z0-9_-]+$/, message: '标识只能包含字母、数字、下划线和中划线' },
          ]}
        >
          <Input placeholder="例如: feishu_bot_1" disabled={isEditing} />
        </Form.Item>

        <Form.Item
          name="name"
          label="Bot 名称"
          rules={[{ required: true, message: '请输入 Bot 显示名称' }]}
        >
          <Input placeholder="例如: 财务助理机器人" />
        </Form.Item>

        <Form.Item
          name="platform"
          label="平台类型"
          rules={[{ required: true, message: '请选择 IM 平台类型' }]}
        >
          <Select
            options={[
              { label: '飞书 (Feishu)', value: 'feishu' },
              { label: '企业微信 (WeChat Work)', value: 'wechat' },
            ]}
          />
        </Form.Item>

        <Form.Item
          name="app_id"
          label="平台 App ID / Bot ID"
          rules={[{ required: true, message: '请输入平台凭证 App ID' }]}
        >
          <Input placeholder="飞书 App ID (cli_xxx) 或企微 Bot ID" />
        </Form.Item>

        <Form.Item
          name="app_secret"
          label="平台 App Secret / Secret"
          rules={isEditing ? [] : [{ required: true, message: '请输入平台凭证 App Secret' }]}
          extra={isEditing ? '修改密钥时请输入新密钥，不修改请留空' : undefined}
        >
          <Input.Password placeholder={isEditing ? '留空表示不更新密钥' : '请输入 App Secret'} />
        </Form.Item>

        <Form.Item
          name="mode"
          label="运行模式"
          rules={[{ required: true, message: '请选择运行模式' }]}
        >
          <Select
            options={[
              { label: '测试模式 (test)', value: 'test' },
              { label: '线上模式 (prod)', value: 'prod' },
            ]}
          />
        </Form.Item>

        <Form.Item
          name="agent_id"
          label="关联 Agent"
          extra="选择该 Bot 所关联下游处理的 Agent 智能体"
        >
          <Select
            placeholder="请选择关联的 Agent (可选)"
            allowClear
            options={agents.map((agent) => ({
              label: `${agent.name} (${agent.agent_id})`,
              value: agent.agent_id,
            }))}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
