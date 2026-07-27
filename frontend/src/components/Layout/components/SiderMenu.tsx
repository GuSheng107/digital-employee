import { Layout, Menu } from 'antd';
import { AppstoreOutlined, BuildOutlined, DatabaseOutlined, DashboardOutlined, SettingOutlined, TableOutlined } from '@ant-design/icons';
import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import logo from '@/assets/images/avatar/logo.svg';
import styles from '../index.module.css';

const { Sider } = Layout;

const DATA_PLATFORM_KEY = 'data-platform';

export default function SiderMenu(): React.ReactElement {
  const navigate = useNavigate();
  const location = useLocation();

  // 派生 state 模式：路由决定 data-platform 子菜单是否强制展开，
  // 用户在其他页面可手动展开/折叠；在 data-platform 页面时强制展开（符合 UX 预期）
  const [dpManuallyOpen, setDpManuallyOpen] = useState<boolean>(false);
  const isOnDataPlatform = location.pathname.startsWith('/data-platform');
  const openKeys = isOnDataPlatform || dpManuallyOpen ? [DATA_PLATFORM_KEY] : [];

  const handleOpenChange = (keys: string[]): void => {
    setDpManuallyOpen(keys.includes(DATA_PLATFORM_KEY));
  };

  const menuItems = [
    { key: '/', icon: <AppstoreOutlined />, label: '页面 A' },
    { key: '/page-b', icon: <BuildOutlined />, label: '页面 B' },
    {
      key: DATA_PLATFORM_KEY,
      icon: <DatabaseOutlined />,
      label: '数据中台',
      children: [
        { key: '/data-platform/dashboard', icon: <DashboardOutlined />, label: 'Dashboard' },
        { key: '/data-platform/data-items', icon: <TableOutlined />, label: 'Data Items' },
        { key: '/data-platform/system-config', icon: <SettingOutlined />, label: 'System Config' },
      ],
    },
  ];

  const selectedKeys = [location.pathname];

  return (
    <Sider theme="dark" width={220}>
      <div className={styles.logo}>
        <img src={logo} alt="logo" />
        <span>项目 Logo</span>
      </div>
      <Menu
        theme="dark"
        mode="inline"
        selectedKeys={selectedKeys}
        openKeys={openKeys}
        onOpenChange={handleOpenChange}
        onClick={({ key }) => navigate(key)}
        items={menuItems}
      />
    </Sider>
  );
}
