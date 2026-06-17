import { Layout, Dropdown, Avatar, Flex } from 'antd';
import { UserOutlined, DownOutlined, KeyOutlined, LogoutOutlined } from '@ant-design/icons';
import styles from '../index.module.css';
import { useUserStore } from '@/store/user';

const { Header } = Layout;

export default function HeaderBar() {
  const userActionItems = [
    { key: 'profile', icon: <UserOutlined />, label: '用户管理' },
    { key: 'password', icon: <KeyOutlined />, label: '修改密码' },
    { type: 'divider' as const },
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', danger: true },
  ];

  const handleUserClick = ({ key }: { key: string }) => {
    if (key === 'logout') {
      clearUserInfo();
    }
  };

  const username = useUserStore((state) => state.username);
  const avatar = useUserStore((state) => state.avatar);
  const clearUserInfo = useUserStore((state) => state.clearUserInfo);

  return (
    <Header className={styles.header}>
      <Flex justify="space-between" align="center" style={{ height: '100%' }}>
        <div className={styles.projectName}>企微数字员工v1.0</div>
        <Dropdown menu={{ items: userActionItems, onClick: handleUserClick }} placement="bottomRight">
          <span className={styles.userDropdown}>
            <Avatar src={avatar} icon={<UserOutlined />} size="small" style={{ marginRight: 8 }} />
            <span className={styles.username}>{username || '未登录'}</span>
            <DownOutlined style={{ fontSize: 10, marginLeft: 4 }} />
          </span>
        </Dropdown>
      </Flex>
    </Header>
  );
}
