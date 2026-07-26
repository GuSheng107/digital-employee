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
}: DataItemsFormDialogProps) {
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
        <Form.Item label="Namespace" name="namespace">
          <Input />
        </Form.Item>
        <Form.Item label="Key" name="itemKey">
          <Input />
        </Form.Item>
        <Form.Item label="描述" name="description">
          <Input />
        </Form.Item>
        <Form.Item label="JSON Value" name="itemValueText">
          <Input.TextArea rows={10} spellCheck={false} />
        </Form.Item>
      </Form>
    </Modal>
  );
}
