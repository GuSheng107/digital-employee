import { Layout, Dropdown, Avatar, Button, Space } from 'antd';
import {
  UserOutlined,
  DownOutlined,
  KeyOutlined,
  LogoutOutlined,
  SettingOutlined,
  PoweroffOutlined,
} from '@ant-design/icons';
import { useUserStore } from '@/store/user';
import styles from '../index.module.css';

const { Header } = Layout;

interface HeaderBarProps {
  onOpenUsers?: () => void;
  onChangePassword?: () => void;
  onExit?: () => void;
}

export default function HeaderBar({ onOpenUsers, onChangePassword, onExit }: HeaderBarProps) {
  const username = useUserStore((s) => s.username);
  const displayName = useUserStore((s) => s.displayName);
  const avatar = useUserStore((s) => s.avatar);
  const isAdmin = useUserStore((s) => s.isAdmin);
  const isGuest = useUserStore((s) => s.isGuest);
  const permission = useUserStore((s) => s.permission);
  const logout = useUserStore((s) => s.logout);

  const roleLabel =
    permission === 'admin' ? '管理员' :
    permission === 'guest' ? '游客' : '普通用户';

  const userActionItems = [
    ...(isAdmin ? [{ key: 'users', icon: <SettingOutlined />, label: '用户管理' }] : []),
    ...(!isGuest ? [{ key: 'password', icon: <KeyOutlined />, label: '修改密码' }] : []),
    { type: 'divider' as const },
    { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', danger: true },
  ];

  const handleUserClick = async ({ key }: { key: string }) => {
    switch (key) {
      case 'users':
        onOpenUsers?.();
        break;
      case 'password':
        onChangePassword?.();
        break;
      case 'logout':
        await logout();
        break;
    }
  };

  return (
    <Header className={styles.header}>
      <div className={styles.headerInner}>
        <div>
          <p className={styles.eyebrow}>Local Runtime</p>
          <h1 className={styles.title}>企微数字员工V1.0</h1>
        </div>
        <Space>
          {username && (
            <div className={styles.topbarUser}>
              <UserOutlined />
              <span>{displayName || username}</span>
              <em>{roleLabel}</em>
            </div>
          )}
          {isAdmin && (
            <Button icon={<SettingOutlined />} onClick={() => onOpenUsers?.()}>
              用户管理
            </Button>
          )}
          {!isGuest && (
            <Button icon={<KeyOutlined />} onClick={() => onChangePassword?.()}>
              修改密码
            </Button>
          )}
          <Button icon={<LogoutOutlined />} onClick={logout}>
            退出登录
          </Button>
          {!isGuest && (
            <Button danger icon={<PoweroffOutlined />} onClick={() => onExit?.()}>
              退出系统
            </Button>
          )}
          {username && (
            <Dropdown menu={{ items: userActionItems, onClick: handleUserClick }} placement="bottomRight">
              <span className={styles.userDropdown}>
                <Avatar src={avatar} icon={<UserOutlined />} size="small" className={styles.userAvatar} />
                <span className={styles.username}>{displayName || username || '未登录'}</span>
                <DownOutlined className={styles.userCaret} />
              </span>
            </Dropdown>
          )}
        </Space>
      </div>
    </Header>
  );
}
