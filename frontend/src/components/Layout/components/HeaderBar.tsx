import { Layout, Dropdown, Avatar, Flex } from 'antd';
import { UserOutlined, DownOutlined, KeyOutlined, LogoutOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import styles from '../index.module.css';
import { useUserStore } from '@/store/user-store';

const { Header } = Layout;

export default function HeaderBar(): React.ReactElement {
  const navigate = useNavigate();

  const userActionItems = [
    { key: 'profile', icon: <UserOutlined />, label: '用户管理' },
    { key: 'password', icon: <KeyOutlined />, label: '修改密码' },
    { type: 'divider' as const },
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', danger: true },
  ];

  const handleUserClick = async ({ key }: { key: string }): Promise<void> => {
    if (key === 'logout') {
      await logout();
      navigate('/login', { replace: true });
    }
  };

  const userInfo = useUserStore((state) => state.userInfo);
  const avatar = useUserStore((state) => state.avatar);
  const logout = useUserStore((state) => state.logout);

  const displayName = userInfo?.nickname || userInfo?.username || '未登录';

  return (
    <Header className={styles.header}>
      <Flex justify="space-between" align="center" className={styles.headerFlex}>
        <div className={styles.projectName}>企微数字员工v1.0</div>
        <Dropdown menu={{ items: userActionItems, onClick: handleUserClick }} placement="bottomRight">
          <span className={styles.userDropdown}>
            <Avatar src={avatar} icon={<UserOutlined />} size="small" className={styles.avatar} />
            <span className={styles.username}>{displayName}</span>
            <DownOutlined className={styles.downIcon} />
          </span>
        </Dropdown>
      </Flex>
    </Header>
  );
}
