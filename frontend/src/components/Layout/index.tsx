import { Layout as AntdLayout } from 'antd';
import SiderMenu from './components/SiderMenu';
import HeaderBar from './components/HeaderBar';
import MainContent from './components/MainContent';
import styles from './index.module.css';

export default function Layout(): React.ReactElement {
  return (
    <AntdLayout className={styles.mainLayout}>
      <SiderMenu />
      <AntdLayout>
        <HeaderBar />
        <MainContent />
      </AntdLayout>
    </AntdLayout>
  );
}
