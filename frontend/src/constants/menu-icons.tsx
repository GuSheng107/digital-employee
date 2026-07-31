import type { ReactNode } from 'react';
import {
  AppstoreOutlined,
  BuildOutlined,
  DatabaseOutlined,
  DashboardOutlined,
  GiftOutlined,
  FileSearchOutlined,
  MenuOutlined,
  ProfileOutlined,
  RobotOutlined,
  SafetyOutlined,
  SettingOutlined,
  TableOutlined,
  TeamOutlined,
  ToolOutlined,
  UserAddOutlined,
  UserOutlined,
} from '@ant-design/icons';

type MenuIconFactory = () => ReactNode;

/**
 * 服务端菜单图标名对应的前端图标工厂。
 *
 * 菜单侧栏和菜单维护页共用同一份映射，避免两处展示结果不一致。
 */
const MENU_ICON_FACTORIES: Readonly<Record<string, MenuIconFactory>> = {
  AppstoreOutlined: () => <AppstoreOutlined />,
  BuildOutlined: () => <BuildOutlined />,
  DatabaseOutlined: () => <DatabaseOutlined />,
  DashboardOutlined: () => <DashboardOutlined />,
  GiftOutlined: () => <GiftOutlined />,
  FileSearchOutlined: () => <FileSearchOutlined />,
  MenuOutlined: () => <MenuOutlined />,
  ProfileOutlined: () => <ProfileOutlined />,
  RobotOutlined: () => <RobotOutlined />,
  SafetyOutlined: () => <SafetyOutlined />,
  SettingOutlined: () => <SettingOutlined />,
  TableOutlined: () => <TableOutlined />,
  TeamOutlined: () => <TeamOutlined />,
  ToolOutlined: () => <ToolOutlined />,
  UserAddOutlined: () => <UserAddOutlined />,
  UserOutlined: () => <UserOutlined />,
};

/** 菜单管理页可配置的图标名，与侧栏实际渲染能力保持一致。 */
export const MENU_ICON_NAMES: readonly string[] = Object.freeze(
  Object.keys(MENU_ICON_FACTORIES),
);

export function getMenuIcon(
  iconName: string | null | undefined,
  fallback: ReactNode = <AppstoreOutlined />,
): ReactNode {
  if (!iconName) {
    return fallback;
  }
  const iconFactory = MENU_ICON_FACTORIES[iconName];
  return iconFactory ? iconFactory() : fallback;
}
