import { Spin } from 'antd';

export default function PageLoader() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 200 }}>
      <Spin />
    </div>
  );
}
