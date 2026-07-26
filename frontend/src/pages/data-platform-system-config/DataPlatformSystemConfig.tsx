import { useEffect, useMemo, useState } from 'react';
import { Button, Typography, message } from 'antd';
import {
  ensureBucket,
  getSystemConfig,
  listBuckets,
  readRedisTest,
  readTestObject,
  testConnections,
  writeRedisTest,
  writeTestObject,
} from './api/system-api';
import SystemConfigStatusGrid from './components/SystemConfigStatusGrid';
import SystemConfigTable from './components/SystemConfigTable';
import {
  type SystemConfigData,
  type SystemConfigDependencies,
  type SystemConfigRow,
  type TestTarget,
} from './types/system';
import { getDataPlatformErrorMessage } from '@/utils/data-platform-request';
import styles from './index.module.css';

const { Title, Text } = Typography;

interface TestAction {
  label: string;
  target: TestTarget;
}

const TEST_ACTIONS: TestAction[] = [
  { label: '测试全部连接', target: 'all' },
  { label: '测试 PostgreSQL', target: 'postgres' },
  { label: '测试 Redis', target: 'redis' },
  { label: '测试 MinIO', target: 'minio' },
];

interface StorageAction {
  label: string;
  run: () => Promise<unknown>;
}

export default function DataPlatformSystemConfig() {
  const [loading, setLoading] = useState<boolean>(false);
  const [actionLoading, setActionLoading] = useState<string>('');
  const [config, setConfig] = useState<SystemConfigData | null>(null);
  const [dependencies, setDependencies] = useState<SystemConfigDependencies | null>(null);
  const [lastResult, setLastResult] = useState<string>('');

  const configRows = useMemo<SystemConfigRow[]>(() => {
    if (!config) return [];
    return [
      { group: '普通 PostgreSQL', values: config.core_db },
      { group: '向量 PostgreSQL', values: config.vector_db },
      { group: 'Redis', values: config.redis },
      { group: 'MinIO', values: config.minio },
    ];
  }, [config]);

  const storageActions = useMemo<StorageAction[]>(
    () => [
      { label: 'Redis 写入测试', run: writeRedisTest },
      { label: 'Redis 读取测试', run: readRedisTest },
      { label: '确保 Bucket', run: ensureBucket },
      { label: 'MinIO 写入对象', run: writeTestObject },
      { label: 'MinIO 读取对象', run: readTestObject },
      { label: 'Bucket 列表', run: listBuckets },
    ],
    [],
  );

  async function loadConfig(): Promise<void> {
    setLoading(true);
    try {
      const response = await getSystemConfig();
      setConfig(response);
    } catch (error) {
      message.error(getDataPlatformErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  async function runTest(target: TestTarget, label: string): Promise<void> {
    setActionLoading(label);
    try {
      const response = await testConnections(target);
      setDependencies(response);
      setLastResult(JSON.stringify(response, null, 2));
      message.success(`${label}完成`);
    } catch (error) {
      message.error(getDataPlatformErrorMessage(error));
    } finally {
      setActionLoading('');
    }
  }

  async function runAction(label: string, action: () => Promise<unknown>): Promise<void> {
    setActionLoading(label);
    try {
      const response = await action();
      setLastResult(JSON.stringify(response, null, 2));
      message.success(`${label}完成`);
    } catch (error) {
      message.error(getDataPlatformErrorMessage(error));
    } finally {
      setActionLoading('');
    }
  }

  useEffect(() => {
    // 初始数据加载场景：异步函数内部 setState 不会同步触发级联渲染
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadConfig();
  }, []);

  return (
    <div className={styles.page}>
      <div className={styles.pageHeader}>
        <div>
          <Title level={3}>System Config</Title>
          <Text type="secondary">查看脱敏配置并测试外部依赖连接</Text>
        </div>
        <Button loading={loading} onClick={() => void loadConfig()}>
          刷新配置
        </Button>
      </div>

      <div className={styles.toolbar}>
        {TEST_ACTIONS.map((action) => (
          <Button
            key={action.label}
            type="primary"
            loading={actionLoading === action.label}
            onClick={() => void runTest(action.target, action.label)}
          >
            {action.label}
          </Button>
        ))}
      </div>

      <SystemConfigStatusGrid dependencies={dependencies} />

      {configRows.length > 0 && <SystemConfigTable rows={configRows} />}

      <div className={`${styles.toolbar} ${styles.secondary}`}>
        {storageActions.map((action) => (
          <Button
            key={action.label}
            loading={actionLoading === action.label}
            onClick={() => void runAction(action.label, action.run)}
          >
            {action.label}
          </Button>
        ))}
      </div>

      {lastResult && <pre className={styles.resultBox}>{lastResult}</pre>}
    </div>
  );
}
