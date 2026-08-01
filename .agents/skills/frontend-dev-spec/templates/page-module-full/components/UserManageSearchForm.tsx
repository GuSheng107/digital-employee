import { Button, Form, Input, Select, Space } from 'antd';
import { USER_MANAGE_STATUS_OPTIONS } from '../constants/user-manage-constants';
import type { UserManageSearchValues } from '../types/user-manage';

interface UserManageSearchFormProps {
  initialValues: UserManageSearchValues;
  loading: boolean;
  onSearch: (values: UserManageSearchValues) => void;
  onReset: () => void;
}

export default function UserManageSearchForm({
  initialValues,
  loading,
  onSearch,
  onReset,
}: UserManageSearchFormProps) {
  const [form] = Form.useForm<UserManageSearchValues>();

  const handleFinish = (values: UserManageSearchValues): void => {
    onSearch(values);
  };

  const handleReset = (): void => {
    form.resetFields();
    onReset();
  };

  return (
    <Form
      form={form}
      layout="inline"
      initialValues={initialValues}
      onFinish={handleFinish}
    >
      <Form.Item label="关键词" name="keyword">
        <Input allowClear placeholder="请输入用户名" />
      </Form.Item>
      <Form.Item label="状态" name="status">
        <Select
          style={{ width: 160 }}
          options={USER_MANAGE_STATUS_OPTIONS.map((item) => ({
            label: item.label,
            value: item.value,
          }))}
        />
      </Form.Item>
      <Form.Item>
        <Space>
          <Button htmlType="submit" loading={loading} type="primary">
            查询
          </Button>
          <Button onClick={handleReset}>
            重置
          </Button>
        </Space>
      </Form.Item>
    </Form>
  );
}
