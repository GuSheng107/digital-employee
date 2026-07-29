import type { ReactNode } from 'react';
import styles from './index.module.css';

interface SystemPageProps {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
  contentMode?: 'fixed' | 'scroll';
}

/** 系统设置页面统一骨架：固定标题栏，内容区按页面类型独立滚动。 */
export default function SystemPage({
  title,
  actions,
  children,
  contentMode = 'fixed',
}: SystemPageProps): React.ReactElement {
  const contentClassName = contentMode === 'scroll'
    ? `${styles.content} ${styles.scrollContent}`
    : `${styles.content} ${styles.fixedContent}`;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <span className={styles.sectionLabel}>系统设置</span>
          <h1 className={styles.title}>{title}</h1>
        </div>
        {actions ? <div className={styles.actions}>{actions}</div> : null}
      </header>
      <div className={contentClassName}>{children}</div>
    </div>
  );
}
