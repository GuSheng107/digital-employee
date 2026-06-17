import { Layout } from 'antd';
import { Outlet } from 'react-router-dom';
import styles from '../index.module.css';

const { Content } = Layout;

export default function MainContent() {
  return (
    <Content className={styles.content}>
      <div className={styles.pageContainer}>
        <Outlet />
      </div>
    </Content>
  );
}
