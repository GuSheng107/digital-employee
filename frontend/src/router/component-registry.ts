import { lazy, type ComponentType } from 'react';

/**
 * 自动发现所有页面组件。
 *
 * 约定：每个页面目录下必须有 ``index.tsx``（默认导出主组件），
 * 目录路径即为菜单表 ``component`` 字段的值。
 *
 * 通过 Vite 的 ``import.meta.glob`` 在构建时扫描，无需手动注册。
 * 在菜单管理页面新增菜单时，只需创建目录和 ``index.tsx`` 即可。
 */
const modules = import.meta.glob<{ default: ComponentType<Record<string, never>> }>(
  '@/pages/**/index.tsx',
);

type LazyPage = React.LazyExoticComponent<ComponentType<Record<string, never>>>;

function toComponentKey(path: string): string {
  // '@/pages/system/user/profile/index.tsx' → 'system/user/profile'
  return path.replace(/^@\/pages\//, '').replace(/\/index\.tsx$/, '');
}

const REGISTRY: Record<string, LazyPage> = {};
for (const [path, loader] of Object.entries(modules)) {
  const key = toComponentKey(path);
  REGISTRY[key] = lazy(loader);
}

/** 根据 component 字段解析对应的页面组件，未注册则返回 null */
export function resolveComponent(componentKey: string | null | undefined): LazyPage | null {
  if (!componentKey) return null;
  // 兼容以 / 开头的旧数据
  const normalized = componentKey.replace(/^\//, '');
  return REGISTRY[normalized] ?? null;
}
