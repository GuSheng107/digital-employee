import { Layout, Menu } from 'antd';
import { AppstoreOutlined, BuildOutlined } from '@ant-design/icons';
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
  ];

  return (
    <Sider theme="dark" width={220}>
      <div className={styles.logo}>
        <img src={logo} alt="logo" />
        <span>项目 Logo</span>
      </div>
      <Menu
        theme="dark"
        mode="inline"
        selectedKeys={[location.pathname]}
        onClick={({ key }) => navigate(key)}
        items={menuItems}
      />
    </Sider>
  );
}
