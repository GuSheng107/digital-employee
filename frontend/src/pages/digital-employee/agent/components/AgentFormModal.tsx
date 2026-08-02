import { useEffect } from 'react';
import { Form, Input, Modal, Select, message } from 'antd';
import { createAgent, updateAgent, type AgentItem, type CreateAgentPayload, type UpdateAgentPayload } from '@/api/agent-api';
import { getRequestErrorMessage } from '@/utils/request';

interface AgentFormModalProps {
  open: boolean;
  editingAgent: AgentItem | null;
  onCancel: () => void;
  onSuccess: () => void;
}

export default function AgentFormModal({
  open,
  editingAgent,
  onCancel,
  onSuccess,
}: AgentFormModalProps): React.ReactElement {
  const [form] = Form.useForm();
  const isEdit = Boolean(editingAgent);

  useEffect(() => {
    if (open) {
      if (editingAgent) {
        form.setFieldsValue({
          agent_id: editingAgent.agent_id,
          name: editingAgent.name,
          status: editingAgent.status,
        });
      } else {
        form.resetFields();
        form.setFieldsValue({
          status: 1,
        });
      }
    }
  }, [open, editingAgent, form]);

  async function handleSubmit(): Promise<void> {
    try {
      const values = await form.validateFields();
      if (isEdit && editingAgent) {
        const updatePayload: UpdateAgentPayload = {
          name: values.name,
          status: values.status,
        };
        await updateAgent(editingAgent.agent_id, updatePayload);
        message.success(`更新 Agent '${editingAgent.agent_id}' 成功`);
      } else {
        const createPayload: CreateAgentPayload = {
          agent_id: values.agent_id.trim(),
          name: values.name.trim(),
          status: values.status,
        };
        await createAgent(createPayload);
        message.success('创建 Agent 成功');
      }
      onSuccess();
    } catch (error) {
      if (error && typeof error === 'object' && 'errorFields' in error) {
        return;
      }
      message.error(getRequestErrorMessage(error, isEdit ? '更新 Agent 失败' : '创建 Agent 失败'));
    }
  }

  return (
    <Modal
      title={isEdit ? `编辑 Agent (${editingAgent?.agent_id})` : '新建 Agent'}
      open={open}
      onOk={() => void handleSubmit()}
      onCancel={onCancel}
      destroyOnClose
      okText={isEdit ? '保存更新' : '立即创建'}
      cancelText="取消"
    >
      <Form form={form} layout="vertical">
        <Form.Item
          label="Agent 唯一标识 (agent_id)"
          name="agent_id"
          rules={[
            { required: true, message: '请输入 Agent 唯一标识' },
            { max: 64, message: 'ID 不能超过 64 个字符' },
          ]}
        >
          <Input placeholder="如 agent_customer_service" disabled={isEdit} />
        </Form.Item>

        <Form.Item
          label="显示名称"
          name="name"
          rules={[
            { required: true, message: '请输入显示名称' },
            { max: 128, message: '名称不能超过 128 个字符' },
          ]}
        >
          <Input placeholder="如 智能客服 Agent" />
        </Form.Item>

        <Form.Item label="状态" name="status">
          <Select
            options={[
              { label: '启用 (1)', value: 1 },
              { label: '禁用 (0)', value: 0 },
            ]}
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
