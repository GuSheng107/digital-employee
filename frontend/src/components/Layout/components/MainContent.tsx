import { Button, Layout, Result } from 'antd';
import { Outlet, useLocation } from 'react-router';
import styles from '../index.module.css';
import { PageLoading } from '@/components/page-loading/PageLoading';
import {
  AUTH_SERVICE_UNAVAILABLE_MESSAGE,
  useUserStore,
} from '@/store/user-store';

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
    // 服务不可用（连接被拒绝/超时/5xx）：用 warning 状态引导用户重试连接；
    // 其他业务错误（如权限不足）用 error 状态，引导重新加载。
    const isServiceUnavailable =
      profileError === AUTH_SERVICE_UNAVAILABLE_MESSAGE;
    pageContent = (
      <Result
        status={isServiceUnavailable ? 'warning' : 'error'}
        title={isServiceUnavailable ? '认证服务暂时不可用' : '用户信息加载失败'}
        subTitle={profileError}
        extra={(
          <Button
            type="primary"
            onClick={() => void hydrateCurrentUser()}
          >
            {isServiceUnavailable ? '重试连接服务' : '重新加载'}
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
