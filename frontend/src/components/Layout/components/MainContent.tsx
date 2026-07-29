import { Layout } from 'antd';
import { Outlet, useLocation } from 'react-router-dom';
import styles from '../index.module.css';

const { Content } = Layout;

export default function MainContent(): React.ReactElement {
  const location = useLocation();
  const isDataPlatformPage = location.pathname.startsWith('/data-platform/');
  const contentClassName = isDataPlatformPage
    ? `${styles.content} ${styles.legacyScrollableContent}`
    : styles.content;
  const containerClassName = isDataPlatformPage
    ? `${styles.pageContainer} ${styles.legacyPageContainer}`
    : styles.pageContainer;

  return (
    <Content className={contentClassName}>
      <div className={containerClassName}>
        <Outlet />
      </div>
    </Content>
  );
}
