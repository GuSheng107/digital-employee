import { Button, Layout, Result } from 'antd';
import { Outlet, useLocation } from 'react-router-dom';
import styles from '../index.module.css';
import { PageLoading } from '@/components/page-loading/PageLoading';
import { useUserStore } from '@/store/user-store';

const { Content } = Layout;

export default function MainContent(): React.ReactElement {
  const location = useLocation();
  const userInfo = useUserStore((state) => state.userInfo);
  const profileLoading = useUserStore((state) => state.profileLoading);
  const profileError = useUserStore((state) => state.profileError);
  const hydrateCurrentUser = useUserStore((state) => state.hydrateCurrentUser);
  const isDataPlatformPage = location.pathname.startsWith('/data-platform/');
  const contentClassName = isDataPlatformPage
    ? `${styles.content} ${styles.legacyScrollableContent}`
    : styles.content;
  const containerClassName = isDataPlatformPage
    ? `${styles.pageContainer} ${styles.legacyPageContainer}`
    : styles.pageContainer;
  let pageContent: React.ReactNode = <Outlet />;
  if (!userInfo && profileLoading) {
    pageContent = <PageLoading label="正在加载用户信息" />;
  } else if (!userInfo && profileError) {
    pageContent = (
      <Result
        status="warning"
        title="用户信息加载失败"
        subTitle={profileError}
        extra={(
          <Button
            type="primary"
            onClick={() => void hydrateCurrentUser()}
          >
            重新加载
          </Button>
        )}
      />
    );
  }

  return (
    <Content className={contentClassName}>
      <div className={containerClassName}>
        {pageContent}
      </div>
    </Content>
  );
}
