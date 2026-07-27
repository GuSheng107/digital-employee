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

  // 用户显式收起时优先级高于路由强制展开：在 data-platform 页面用户仍可手动折叠子菜单
  // 路由变化时（导航到 data-platform）自动展开，除非用户已手动收起
  const [dpManuallyClosed, setDpManuallyClosed] = useState<boolean>(false);
  const isOnDataPlatform = location.pathname.startsWith('/data-platform');
  const shouldOpen = (isOnDataPlatform && !dpManuallyClosed);
  const openKeys = shouldOpen ? [DATA_PLATFORM_KEY] : [];

  const handleOpenChange = (keys: string[]): void => {
    setDpManuallyClosed(!keys.includes(DATA_PLATFORM_KEY));
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
