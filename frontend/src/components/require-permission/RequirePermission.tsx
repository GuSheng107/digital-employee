import { Button, Result } from 'antd';
import { useNavigate } from 'react-router-dom';
import { hasAnyPermission } from '@/constants/access-control';
import { useUserStore } from '@/store/user-store';
import { PageLoading } from '@/components/page-loading/PageLoading';

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
    return <PageLoading label="正在核验访问权限" />;
  }

  if (!hasAnyPermission(userInfo.roles, userInfo.permissions, required)) {
    return (
      <Result
        status="403"
        title="无权访问"
        subTitle="当前账号无权访问此页面。"
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
