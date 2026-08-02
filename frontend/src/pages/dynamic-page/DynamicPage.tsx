import { Component, Suspense, useMemo, type ComponentType, type ReactNode } from 'react';
import { useLocation, Navigate } from 'react-router';
import { Result, Button, Typography } from 'antd';
import { useUserStore } from '@/store/user-store';
import { resolveComponent } from '@/router/component-registry';
import { PageLoading } from '@/components/page-loading/PageLoading';
import type { MenuNode } from '@/api/auth-api';
import RequirePermission from '@/components/require-permission/RequirePermission';

const { Paragraph } = Typography;

/** 菜单树最大遍历深度，防止环路或异常数据导致栈溢出。 */
const MAX_MENU_DEPTH = 50;

/**
 * 在菜单树中递归查找 path 匹配的节点。
 *
 * 返回匹配节点及其所有祖先节点（根→父→当前）。带深度和已访问节点双重防护，
 * 应对数据库被带外篡改产生环路的极端情况。
 */
function findMenuByPath(
  nodes: MenuNode[],
  targetPath: string,
  ancestors: MenuNode[] = [],
  visited: Set<number> = new Set(),
  depth: number = 0,
): { node: MenuNode; ancestors: MenuNode[] } | null {
  if (depth > MAX_MENU_DEPTH) return null;
  for (const node of nodes) {
    if (visited.has(node.id)) return null;
    visited.add(node.id);
    const chain = [...ancestors, node];
    if (node.path === targetPath) {
      return { node, ancestors: chain };
    }
    if (node.children?.length) {
      const found = findMenuByPath(node.children, targetPath, chain, visited, depth + 1);
      if (found) return found;
    }
  }
  return null;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

/**
 * 递归查找目录节点下第一个拥有路由 path 的叶子菜单路径。
 *
 * 目录节点本身没有页面组件，需逐层下钻直到找到 menu_type !== 1 的子菜单，
 * 避免目录下第一个子菜单仍是目录时形成连续重定向。带深度上限防护。
 */
function findFirstLeafPath(node: MenuNode, depth: number = 0): string | null {
  if (depth > MAX_MENU_DEPTH) return null;
  if (node.menu_type !== 1 && node.path != null) return node.path;
  for (const child of node.children ?? []) {
    const leaf = findFirstLeafPath(child, depth + 1);
    if (leaf) return leaf;
  }
  return null;
}

/**
 * 动态懒加载页面的错误捕获边界。
 *
 * React.lazy 在 chunk 加载失败（如部署后 hash 变更导致 404）时会 reject，
 * Suspense 只处理 pending 状态，不会捕获 rejection。本组件兜底防止白屏。
 */
class ErrorBoundary extends Component<
  { children: ReactNode; fallback?: ReactNode },
  ErrorBoundaryState
> {
  constructor(props: { children: ReactNode; fallback?: ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  override render(): ReactNode {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <Result
            status="error"
            title="页面加载失败"
            subTitle="可能是资源版本已更新，请刷新页面后重试"
            extra={(
              <Button type="primary" onClick={() => window.location.reload()}>
                刷新页面
              </Button>
            )}
          />
        )
      );
    }
    return this.props.children;
  }
}

/**
 * 渲染已解析的动态懒加载组件。
 *
 * 抽出独立组件以规避 react-hooks 规则对「在 render 中直接渲染变量组件」的误判：
 * 组件引用实际来自模块级 REGISTRY，并非每次渲染创建。
 */
function ResolvedPage({
  component: PageComponent,
  permission,
}: {
  component: ComponentType;
  permission?: string | null;
}): React.ReactElement {
  const content = (
    <Suspense fallback={<PageLoading label="正在加载页面" />}>
      <PageComponent />
    </Suspense>
  );
  // 菜单绑定了权限码时，加权限守卫
  if (permission) {
    return <RequirePermission required={[permission]}>{content}</RequirePermission>;
  }
  return content;
}

/** 动态路由兜底页面（真实渲染逻辑），由 ErrorBoundary 包裹使用。 */
function DynamicPageInner(): React.ReactElement {
  const location = useLocation();
  const menus = useUserStore((s) => s.menus);

  const result = useMemo(
    () => findMenuByPath(menus, location.pathname),
    [menus, location.pathname],
  );

  // 路径与任何菜单都不匹配 → 返回首页
  if (!result) {
    return <Navigate to="/" replace />;
  }

  const { node } = result;

  // 目录节点 → 递归下钻到第一个叶子菜单，避免连续重定向
  if (node.menu_type === 1) {
    const leafPath = findFirstLeafPath(node);
    if (leafPath) {
      return <Navigate to={leafPath} replace />;
    }
  }

  // 尝试解析组件
  const PageComponent = resolveComponent(node.component);

  if (PageComponent) {
    return <ResolvedPage component={PageComponent} permission={node.permission} />;
  }

  // 无匹配组件 → 建设中占位
  return (
    <Result
      status="info"
      title={node.title}
      subTitle={(
        <Paragraph style={{ marginTop: 16 }}>
          该页面尚未实现。请在 <code>pages/</code> 下按菜单 component 字段创建目录，
          并添加默认导出的 <code>index.tsx</code> 文件：
          <pre style={{ background: '#f5f5f5', padding: '8px 16px', borderRadius: 4, marginTop: 8 }}>
            {`pages/${node.component || 'your-page'}/index.tsx`}
          </pre>
          Vite 构建时会自动扫描 <code>pages/**/index.tsx</code>，无需额外注册。
        </Paragraph>
      )}
      extra={(
        <Button type="primary" onClick={() => window.history.back()}>
          返回上一页
        </Button>
      )}
    />
  );
}

/** 动态路由兜底页面，包一层 ErrorBoundary 防止懒加载 chunk 失败后白屏。 */
export default function DynamicPage(): React.ReactElement {
  return (
    <ErrorBoundary>
      <DynamicPageInner />
    </ErrorBoundary>
  );
}
