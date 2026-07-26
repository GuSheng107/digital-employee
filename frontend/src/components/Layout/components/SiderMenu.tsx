import { Layout, Menu } from 'antd';
import { AppstoreOutlined, BuildOutlined, DatabaseOutlined, DashboardOutlined, SettingOutlined, TableOutlined } from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import logo from '@/assets/images/avatar/logo.svg';
import styles from '../index.module.css';

const { Sider } = Layout;

export default function SiderMenu() {
  const navigate = useNavigate();
  const location = useLocation();

  const menuItems = [
    { key: '/', icon: <AppstoreOutlined />, label: '页面 A' },
    { key: '/page-b', icon: <BuildOutlined />, label: '页面 B' },
    {
      key: 'data-platform',
      icon: <DatabaseOutlined />,
      label: '数据中台',
      children: [
        { key: '/data-platform/dashboard', icon: <DashboardOutlined />, label: 'Dashboard' },
        { key: '/data-platform/data-items', icon: <TableOutlined />, label: 'Data Items' },
        { key: '/data-platform/system-config', icon: <SettingOutlined />, label: 'System Config' },
      ],
    },
  ];

  // 当前路径匹配父级菜单，便于子菜单自动展开与高亮
  const selectedKeys = [location.pathname];
  const openKeys = location.pathname.startsWith('/data-platform') ? ['data-platform'] : [];

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
        defaultOpenKeys={openKeys}
        onClick={({ key }) => navigate(key)}
        items={menuItems}
      />
    </Sider>
  );
}
