import { Card, Empty, Typography } from 'antd';
import styles from './index.module.css';

const { Title, Text } = Typography;

export default function UserManage(): JSX.Element {
  return (
    <div className={styles.container}>
      <div className={styles.content}>
        <div className={styles.header}>
          <Title level={3}>
            用户管理
          </Title>
          <Text type="secondary">
            轻量模板示例：适合普通页面或简单列表页，不默认引入局部 store。
          </Text>
        </div>

        <Card>
          <Empty
            description="这里保留最小页面骨架。出现独立请求逻辑时，再补 `api/` 和 `types/`。"
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        </Card>
      </div>
    </div>
  );
}
