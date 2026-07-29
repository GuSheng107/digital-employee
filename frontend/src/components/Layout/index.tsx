import { Layout as AntdLayout } from 'antd';
import SiderMenu from './components/SiderMenu';
import HeaderBar from './components/HeaderBar';
import MainContent from './components/MainContent';
import styles from './index.module.css';
import { RouteLoadingIndicator } from '@/components/page-loading/PageLoading';

export default function Layout(): React.ReactElement {
  return (
    <AntdLayout className={styles.mainLayout}>
      <SiderMenu />
      <AntdLayout className={styles.workspaceLayout}>
        <RouteLoadingIndicator />
        <HeaderBar />
        <MainContent />
      </AntdLayout>
    </AntdLayout>
  );
}
