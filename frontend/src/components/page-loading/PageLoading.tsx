import type { ReactElement } from 'react';
import { useLocation } from 'react-router';
import logo from '@/assets/images/avatar/logo.svg';
import styles from './index.module.css';

interface PageLoadingProps {
  fullScreen?: boolean;
  label?: string;
}

/** 统一的页面级加载反馈。 */
export function PageLoading({
  fullScreen = false,
  label = '正在加载',
}: PageLoadingProps): ReactElement {
  return (
    <div
      className={fullScreen ? styles.fullScreen : styles.page}
      role="status"
      aria-live="polite"
    >
      <div className={styles.loader} aria-hidden="true">
        <span className={`${styles.ring} ${styles.ringOuter}`} />
        <span className={`${styles.ring} ${styles.ringInner}`} />
        <img src={logo} alt="" />
      </div>
      <span className={styles.label}>{label}</span>
    </div>
  );
}

/** 每次路由切换时重播的轻量顶部进度动画。 */
export function RouteLoadingIndicator(): ReactElement {
  const location = useLocation();
  return (
    <div
      key={location.key || location.pathname}
      className={styles.routeIndicator}
      aria-hidden="true"
    >
      <span />
    </div>
  );
}
