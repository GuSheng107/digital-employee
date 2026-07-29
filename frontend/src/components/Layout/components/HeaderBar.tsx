import { Layout, Dropdown, Avatar, Flex, message } from 'antd';
import { UserOutlined, DownOutlined, LogoutOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import styles from '../index.module.css';
import { useUserStore } from '@/store/user-store';

const { Header } = Layout;

export default function HeaderBar(): React.ReactElement {
  const navigate = useNavigate();
  const userInfo = useUserStore((state) => state.userInfo);
  const avatar = useUserStore((state) => state.avatar);
  const logout = useUserStore((state) => state.logout);

  const displayName = userInfo?.nickname || userInfo?.username || '未登录';

  const userActionItems = [
    { key: 'profile', icon: <UserOutlined />, label: '个人信息' },
    { type: 'divider' as const },
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', danger: true },
  ];

  const handleUserClick = async ({ key }: { key: string }): Promise<void> => {
    if (key === 'profile') {
      navigate('/system/user/profile');
    } else if (key === 'logout') {
      await logout();
      message.success('已退出登录');
      navigate('/login', { replace: true });
    }
  };

  return (
    <Header className={styles.header}>
      <Flex justify="space-between" align="center" className={styles.headerFlex}>
        <div className={styles.projectName}>数字员工</div>
        <Dropdown menu={{ items: userActionItems, onClick: handleUserClick }} placement="bottomRight">
          <span className={styles.userDropdown}>
            <Avatar src={avatar} icon={<UserOutlined />} size={32} className={styles.avatar} />
            <span className={styles.username}>{displayName}</span>
            <DownOutlined className={styles.downIcon} />
          </span>
        </Dropdown>
      </Flex>
    </Header>
  );
}
