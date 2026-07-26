import { Layout, Menu } from 'antd';
import {
  MonitorOutlined,
  RobotOutlined,
  SendOutlined,
  MessageOutlined,
  ApiOutlined,
  ThunderboltOutlined,
  FileTextOutlined,
  FolderOpenOutlined,
  StarOutlined,
  BookOutlined,
  CalendarOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import brandMark from '/brand/wecom-agent-mark.svg';
import styles from '../index.module.css';

const { Sider } = Layout;

interface MenuItem {
  key: string;
  icon: React.ReactNode;
  label: string;
}

const menuItems: MenuItem[] = [
  { key: 'control', icon: <MonitorOutlined />, label: '工作台' },
  { key: 'agent', icon: <RobotOutlined />, label: 'Agents配置' },
  { key: 'bot', icon: <SendOutlined />, label: 'Bot配置' },
  { key: 'chats', icon: <MessageOutlined />, label: '会话管理' },
  { key: 'mcp', icon: <ApiOutlined />, label: 'MCP配置' },
  { key: 'skills', icon: <ThunderboltOutlined />, label: 'Skills配置' },
  { key: 'projectLogs', icon: <FileTextOutlined />, label: '日志查询' },
  { key: 'data', icon: <FolderOpenOutlined />, label: '数据管理' },
  { key: 'feedback', icon: <StarOutlined />, label: '反馈分析' },
  { key: 'memory', icon: <BookOutlined />, label: '记忆管理' },
  { key: 'tasks', icon: <CalendarOutlined />, label: '任务管理' },
  { key: 'settings', icon: <ToolOutlined />, label: '系统设置' },
];

// Map path segments to menu item keys
const pathToKey: Record<string, string> = {
  '': 'control',
  'agent': 'agent',
  'bot': 'bot',
  'chats': 'chats',
  'mcp': 'mcp',
  'skills': 'skills',
  'projectLogs': 'projectLogs',
  'data': 'data',
  'feedback': 'feedback',
  'memory': 'memory',
  'tasks': 'tasks',
  'settings': 'settings',
};

export default function SiderMenu() {
  const navigate = useNavigate();
  const location = useLocation();

  // Determine active key from path
  const pathSeg = location.pathname.replace(/^\/+/, '').split('/')[0] || '';
  const activeKey = pathToKey[pathSeg] || 'control';

  return (
    <Sider
      theme="dark"
      width={260}
      style={{
        background: 'linear-gradient(180deg, #1f2937 0%, #111827 100%)',
        borderRight: '1px solid #374151',
      }}
    >
      <div className={styles.brand}>
        <img className={styles.brandMark} src={brandMark} alt="WeCom Agent" />
        <div>
          <strong>WeCom Agent</strong>
          <span>Control Console</span>
        </div>
      </div>

      <Menu
        theme="dark"
        mode="inline"
        selectedKeys={[activeKey]}
        onClick={({ key }) => {
          // Use query params or hash for view routing since we're on a single page
          navigate(key === 'control' ? '/' : `/${key}`);
        }}
        items={menuItems.map((item) => ({
          key: item.key,
          icon: item.icon,
          label: item.label,
        }))}
        style={{
          background: 'transparent',
          borderInlineEnd: 'none',
        }}
      />
    </Sider>
  );
}
