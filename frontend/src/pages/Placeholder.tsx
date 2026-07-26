import { Result } from 'antd';

export default function Placeholder() {
  return (
    <Result
      status="info"
      title="页面迁移中"
      subTitle="该页面正在从 Vue 迁移到 React，请稍后查看。"
    />
  );
}
