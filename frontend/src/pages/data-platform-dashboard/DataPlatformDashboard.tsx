import { useEffect, useRef, useState } from 'react';
import { Button, Typography, message } from 'antd';
import StatusCard from '@/components/status-card/StatusCard';
import type { StatusCardState } from '@/components/status-card/StatusCard';
import { getDataPlatformErrorMessage } from '@/utils/data-platform-request';
import { getDependencies, getServiceInfo } from './api/system-api';
import type { ServiceInfo, DashboardDependencies } from './types/system';
import styles from './index.module.css';

const { Title, Text } = Typography;

const dataPlatformApiBaseUrl =
  import.meta.env.VITE_DATA_PLATFORM_API_BASE_URL || '/data-platform-api';

function cardStatus(ok?: boolean): StatusCardState {
  if (ok === undefined) return 'unknown';
  return ok ? 'ok' : 'error';
}

export default function DataPlatformDashboard(): React.ReactElement {
  const [loading, setLoading] = useState<boolean>(false);
  const [service, setService] = useState<ServiceInfo | null>(null);
  const [dependencies, setDependencies] = useState<DashboardDependencies | null>(null);
  /** 防止 StrictMode 双调导致重复请求与重复 message */
  const initializedRef = useRef(false);

  async function refresh(showSuccess = true): Promise<void> {
    setLoading(true);
    try {
      const [serviceInfo, dependencyResponse] = await Promise.all([
        getServiceInfo(),
        getDependencies(),
      ]);
      setService(serviceInfo);
      setDependencies(dependencyResponse);
      // 初始加载（StrictMode 首次）不弹 success，避免双调弹两次
      if (showSuccess && initializedRef.current) {
        message.success('状态已刷新');
      }
    } catch (error) {
      message.error(getDataPlatformErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  // 初始数据加载：effect 仅在挂载时执行一次
  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;
    void refresh(false);
  }, []);

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <Title level={3}>Dashboard</Title>
          <Text type="secondary">当前 API 地址：{dataPlatformApiBaseUrl}</Text>
        </div>
        <Button type="primary" loading={loading} onClick={() => void refresh()}>
          刷新状态
        </Button>
      </div>

      <div className={styles.statusGrid}>
        <StatusCard
          title="后端服务"
          status={service?.status === 'running' ? 'ok' : 'unknown'}
          message={service ? `${service.name} ${service.version}` : '等待检测'}
        />
        <StatusCard
          title="普通 PostgreSQL"
          status={cardStatus(dependencies?.core_db.ok)}
          message={dependencies?.core_db.message}
          latency={dependencies?.core_db.latency_ms}
        />
        <StatusCard
          title="向量 PostgreSQL"
          status={cardStatus(dependencies?.vector_db.ok)}
          message={dependencies?.vector_db.message}
          latency={dependencies?.vector_db.latency_ms}
        />
        <StatusCard
          title="Redis"
          status={cardStatus(dependencies?.redis.ok)}
          message={dependencies?.redis.message}
          latency={dependencies?.redis.latency_ms}
        />
        <StatusCard
          title="MinIO"
          status={cardStatus(dependencies?.minio.ok)}
          message={dependencies?.minio.message}
          latency={dependencies?.minio.latency_ms}
        />
      </div>
    </div>
  );
}
