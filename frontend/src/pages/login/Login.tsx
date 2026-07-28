import { useNavigate, useSearchParams } from 'react-router-dom';
import { Form, Input, Button, message } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useUserStore, getLoginErrorMessage } from '@/store/user-store';
import { HttpError } from '@/utils/request';
import logo from '@/assets/images/avatar/logo.svg';
import styles from './index.module.css';

interface LoginFormValues {
  username: string;
  password: string;
}

export default function Login(): React.ReactElement {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const login = useUserStore((state) => state.login);
  const loading = useUserStore((state) => state.loading);

  const handleSubmit = async (values: LoginFormValues): Promise<void> => {
    try {
      await login(values.username, values.password);
      message.success('登录成功');
      // 登录成功后跳转到 redirect 参数指定的页面，默认首页
      const redirect = searchParams.get('redirect') || '/';
      navigate(redirect, { replace: true });
    } catch (error) {
      // 用 message 全局提示替代 Alert，在深色背景上更醒目
      message.error(getLoginErrorMessage(error));
    }
  };

  return (
    <div className={styles.container}>
      {/* 左侧品牌展示区 */}
      <div className={styles.brandPanel}>
        <div className={styles.brandBg} />
        <div className={`${styles.brandGlow} ${styles.brandGlow1}`} />
        <div className={`${styles.brandGlow} ${styles.brandGlow2}`} />
        <div className={`${styles.brandGlow} ${styles.brandGlow3}`} />

        <div className={styles.brandContent}>
          <div className={styles.brandLogo}>
            <div className={styles.brandLogoIcon}>
              <img src={logo} alt="logo" className={styles.brandLogoImg} />
            </div>
            <span className={styles.brandLogoText}>Digital Employee</span>
          </div>

          <h1 className={styles.brandTitle}>
            数字员工
            <br />
            智能协作平台
          </h1>

          <p className={styles.brandSubtitle}>
            让人<span className={styles.brandSubtitleAccent}>回归创造</span>
            ，把重复交给 AI
          </p>
          <p className={styles.brandTagline}>CREATE · AUTOMATE · ELEVATE</p>
        </div>

        <div className={styles.brandFooter}>© 2026 Digital Employee. All rights reserved.</div>
      </div>

      {/* 右侧登录表单区 */}
      <div className={styles.formPanel}>
        <div className={styles.formCard}>
          <h2 className={styles.formTitle}>欢迎回来</h2>
          <p className={styles.formSubtitle}>登录以开始你的创造之旅</p>

          <Form
            name="login"
            layout="vertical"
            onFinish={handleSubmit}
            autoComplete="off"
            className={styles.form}
          >
            <Form.Item
              name="username"
              rules={[{ required: true, message: '请输入用户名' }]}
              className={styles.formField}
            >
              <div>
                <label className={styles.formLabel}>用户名</label>
                <Input
                  prefix={<UserOutlined style={{ color: '#94a3b8' }} />}
                  placeholder="请输入用户名"
                  className={styles.formInput}
                  size="large"
                  autoComplete="username"
                />
              </div>
            </Form.Item>

            <Form.Item
              name="password"
              rules={[{ required: true, message: '请输入密码' }]}
              className={styles.formField}
            >
              <div>
                <label className={styles.formLabel}>密码</label>
                <Input.Password
                  prefix={<LockOutlined style={{ color: '#94a3b8' }} />}
                  placeholder="请输入密码"
                  className={styles.formInput}
                  size="large"
                  autoComplete="current-password"
                />
              </div>
            </Form.Item>

            <Form.Item className={styles.formField}>
              <Button
                type="primary"
                htmlType="submit"
                loading={loading}
                className={styles.submitButton}
                size="large"
              >
                {loading ? '登录中...' : '登 录'}
              </Button>
            </Form.Item>
          </Form>

          <div className={styles.registerLink}>
            还没有账号？<a onClick={() => navigate('/register')}>立即注册</a>
          </div>

          <div className={styles.formFooter}>
            忘记密码？请联系系统管理员
          </div>
        </div>
      </div>
    </div>
  );
}

/** 类型标记：确保 HttpError 在 bundle 中不被 tree-shake（用于 store 中的 instanceof 判断） */
export type { HttpError };
