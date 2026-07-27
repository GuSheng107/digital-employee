import StatusCard from '@/components/status-card/StatusCard';
import type { StatusCardState } from '@/components/status-card/StatusCard';
import styles from '../index.module.css';
import type { SystemConfigDependencies } from '../types/system';

export interface SystemConfigStatusGridProps {
  dependencies: SystemConfigDependencies | null;
}

function statusOf(ok?: boolean): StatusCardState {
  if (ok === undefined) return 'unknown';
  return ok ? 'ok' : 'error';
}

export default function SystemConfigStatusGrid({ dependencies }: SystemConfigStatusGridProps) {
  return (
    <div className={styles.statusGrid}>
      <StatusCard
        title="普通 PostgreSQL"
        status={statusOf(dependencies?.core_db.ok)}
        message={dependencies?.core_db.message}
        latency={dependencies?.core_db.latency_ms}
      />
      <StatusCard
        title="向量 PostgreSQL"
        status={statusOf(dependencies?.vector_db.ok)}
        message={dependencies?.vector_db.message}
        latency={dependencies?.vector_db.latency_ms}
      />
      <StatusCard
        title="Redis"
        status={statusOf(dependencies?.redis.ok)}
        message={dependencies?.redis.message}
        latency={dependencies?.redis.latency_ms}
      />
      <StatusCard
        title="MinIO"
        status={statusOf(dependencies?.minio.ok)}
        message={dependencies?.minio.message}
        latency={dependencies?.minio.latency_ms}
      />
    </div>
  );
}
