import { Layout, Menu } from 'antd';
import {
  AppstoreOutlined,
  BuildOutlined,
  DatabaseOutlined,
  DashboardOutlined,
  SettingOutlined,
  TableOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import logo from '@/assets/images/avatar/logo.svg';
import styles from '../index.module.css';

const { Sider } = Layout;

const DATA_PLATFORM_KEY = 'data-platform';

export default function SiderMenu(): React.ReactElement {
  const navigate = useNavigate();
  const location = useLocation();

  // 常规菜单树模式：非受控展开，Menu 内部自管理 openKeys。
  // 默认展开所有父菜单，之后完全由用户点击展开/折叠。
  const defaultOpenKeys = [DATA_PLATFORM_KEY];

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
        defaultOpenKeys={defaultOpenKeys}
        onClick={({ key }) => {
          // 父菜单（含 children）仅负责展开/折叠，不触发路由跳转
          if (key === DATA_PLATFORM_KEY) return;
          navigate(key);
        }}
        items={menuItems}
      />
    </Sider>
  );
}
