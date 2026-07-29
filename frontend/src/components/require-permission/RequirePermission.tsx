import { Button, Result, Spin } from 'antd';
import { useNavigate } from 'react-router-dom';
import { hasAnyPermission } from '@/constants/access-control';
import { useUserStore } from '@/store/user-store';

interface RequirePermissionProps {
  required: readonly string[];
  children: React.ReactElement;
}

/** 静态路由的权限兜底，防止仅隐藏菜单后仍可手输 URL 进入页面。 */
export default function RequirePermission({
  required,
  children,
}: RequirePermissionProps): React.ReactElement {
  const navigate = useNavigate();
  const userInfo = useUserStore((state) => state.userInfo);

  if (!userInfo) {
    return (
      <div style={{ display: 'grid', minHeight: '50vh', placeItems: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!hasAnyPermission(userInfo.roles, userInfo.permissions, required)) {
    return (
      <Result
        status="403"
        title="无权访问"
        subTitle="当前账号未被授予该页面对应的接口权限。"
        extra={(
          <Button type="primary" onClick={() => navigate('/', { replace: true })}>
            返回工作台
          </Button>
        )}
      />
    );
  }
  return children;
}
