import { Button, DatePicker, Form, Input, Select, Space } from 'antd';
import type { Dayjs } from 'dayjs';
import type {
  CallStatus,
  ObservabilityMetadata,
} from '../types/observability';
import {
  CALL_STATUS_LABELS,
  TRACE_SERVICE_LABELS,
  TRACE_TRIGGER_LABELS,
} from '../constants/observability';

const { RangePicker } = DatePicker;

export interface LogSearchValues {
  traceId?: string;
  timeRange?: [Dayjs, Dayjs];
  trigger?: string;
  service?: string;
  callStatus?: CallStatus;
  keyword?: string;
}

interface LogSearchFormProps {
  metadata: ObservabilityMetadata;
  loading: boolean;
  onSearch: (values: LogSearchValues) => void;
}

function options(values: string[], labels: Readonly<Record<string, string>>) {
  return values.map((value) => ({ value, label: labels[value] ?? value }));
}

export default function LogSearchForm({
  metadata,
  loading,
  onSearch,
}: LogSearchFormProps): React.ReactElement {
  const [form] = Form.useForm<LogSearchValues>();

  return (
    <Form
      form={form}
      layout="vertical"
      onFinish={onSearch}
      className="log-query-search-form"
    >
      <div className="log-query-filter-grid">
        <Form.Item name="traceId" label="Trace ID">
          <Input allowClear placeholder="输入完整 Trace ID" />
        </Form.Item>
        <Form.Item name="timeRange" label="开始时间">
          <RangePicker showTime allowClear style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="trigger" label="触发来源">
          <Select
            allowClear
            placeholder="全部来源"
            options={options(metadata.triggers, TRACE_TRIGGER_LABELS)}
          />
        </Form.Item>
        <Form.Item name="service" label="服务">
          <Select
            allowClear
            placeholder="全部服务"
            options={options(metadata.services, TRACE_SERVICE_LABELS)}
          />
        </Form.Item>
        <Form.Item name="callStatus" label="调用状态">
          <Select
            allowClear
            placeholder="全部调用状态"
            options={options(
              metadata.call_statuses,
              CALL_STATUS_LABELS,
            )}
          />
        </Form.Item>
        <Form.Item name="keyword" label="内容关键字">
          <Input allowClear placeholder="请求体、响应体、IM 或模型正文" />
        </Form.Item>
        <Form.Item label=" ">
          <Space>
            <Button type="primary" htmlType="submit" loading={loading}>
              查询
            </Button>
            <Button
              onClick={() => {
                form.resetFields();
                onSearch({});
              }}
            >
              重置
            </Button>
          </Space>
        </Form.Item>
      </div>
    </Form>
  );
}
