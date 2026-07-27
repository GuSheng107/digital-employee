import { useEffect } from 'react';
import { Form, Input, Modal } from 'antd';
import type { DataItemFormValues } from '../types/data-items';

export interface DataItemsFormDialogProps {
  open: boolean;
  saving: boolean;
  editingId: string;
  initialValues: DataItemFormValues;
  onCancel: () => void;
  onSave: (values: DataItemFormValues) => void;
}

export default function DataItemsFormDialog({
  open,
  saving,
  editingId,
  initialValues,
  onCancel,
  onSave,
}: DataItemsFormDialogProps): React.ReactElement {
  const [form] = Form.useForm<DataItemFormValues>();

  useEffect(() => {
    if (open) {
      form.setFieldsValue(initialValues);
    }
  }, [open, initialValues, form]);

  return (
    <Modal
      open={open}
      title={editingId ? '编辑数据项' : '新增数据项'}
      width={720}
      onCancel={onCancel}
      onOk={() => form.submit()}
      confirmLoading={saving}
      okText="保存"
      cancelText="取消"
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={initialValues}
        onFinish={onSave}
      >
        <Form.Item label="Namespace" name="namespace" rules={[{ required: true, message: '请输入 Namespace' }]}>
          <Input />
        </Form.Item>
        <Form.Item label="Key" name="itemKey" rules={[{ required: true, message: '请输入 Key' }]}>
          <Input />
        </Form.Item>
        <Form.Item label="描述" name="description">
          <Input />
        </Form.Item>
        <Form.Item
          label="JSON Value"
          name="itemValueText"
          rules={[
            { required: true, message: '请输入 JSON 内容' },
            {
              validator: (_, value) => {
                try {
                  const parsed: unknown = JSON.parse(value || '{}');
                  if (parsed == null || typeof parsed !== 'object') {
                    return Promise.reject(new Error('JSON 必须是对象'));
                  }
                  return Promise.resolve();
                } catch {
                  return Promise.reject(new Error('请输入合法的 JSON 格式'));
                }
              },
            },
          ]}
        >
          <Input.TextArea rows={10} spellCheck={false} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
