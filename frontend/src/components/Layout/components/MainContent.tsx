import { Button, Layout, Result } from 'antd';
import { Outlet, useLocation } from 'react-router';
import styles from '../index.module.css';
import { PageLoading } from '@/components/page-loading/PageLoading';
import { useUserStore } from '@/store/user-store';

const { Content } = Layout;

export default function MainContent(): React.ReactElement {
  const location = useLocation();
  const userInfo = useUserStore((state) => state.userInfo);
  const profileLoading = useUserStore((state) => state.profileLoading);
  const profileError = useUserStore((state) => state.profileError);
  const profileErrorKind = useUserStore((state) => state.profileErrorKind);
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
    // 按结构化 errorKind 分支（替代字符串匹配），文案调整或追加 traceId 不会影响判别：
    //   - service-unavailable（连接被拒绝/超时/5xx）：warning 状态，引导重试连接服务；
    //   - business（如权限不足/用户被禁用）：error 状态，引导重新加载。
    const isServiceUnavailable = profileErrorKind === 'service-unavailable';
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
