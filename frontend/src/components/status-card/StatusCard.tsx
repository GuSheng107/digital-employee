import styles from './index.module.css';

export type StatusCardState = 'ok' | 'error' | 'unknown';

export interface StatusCardProps {
  title: string;
  status: StatusCardState;
  message?: string;
  latency?: number | null;
}

const STATE_TEXT: Record<StatusCardState, string> = {
  ok: '正常',
  error: '异常',
  unknown: '未检测',
};

// 跨页面复用的状态卡片，用于数据中台 Dashboard 与 SystemConfig
export default function StatusCard({ title, status, message, latency }: StatusCardProps) {
  return (
    <section className={`${styles.statusCard} ${styles[status]}`}>
      <div className={styles.top}>
        <span className={styles.dot} />
        <span className={styles.title}>{title}</span>
      </div>
      <div className={styles.state}>{STATE_TEXT[status]}</div>
      <p className={styles.messageText}>{message || '等待检测'}</p>
      {latency !== null && latency !== undefined && (
        <span className={styles.latency}>{latency} ms</span>
      )}
    </section>
  );
}
