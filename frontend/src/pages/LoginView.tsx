import { useState } from 'react';
import { Form, Input, Button, Typography } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useUserStore } from '@/store/user';
import { loginConsole } from '@/api/auth';
import brandMark from '/brand/wecom-agent-mark.svg';
import styles from './login-view.module.css';

const { Title } = Typography;

interface LoginForm {
  username: string;
  password: string;
}

export default function LoginView() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const setLoginSession = useUserStore((s) => s.setLoginSession);

  const handleSubmit = async (values: LoginForm) => {
    if (loading) return;
    setError('');
    setLoading(true);

    try {
      const response = await loginConsole(values.username, values.password);
      setLoginSession(response);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '登录失败';
      if (msg.includes('密码') || msg.includes('用户名') || msg.includes('401')) {
        setError('用户名或密码错误，请检查后重试');
      } else {
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className={styles.loginShell}>
      <section className={styles.loginPanel}>
        <div className={styles.loginBrand}>
          <img className={styles.loginBrandMark} src={brandMark} alt="数字员工" />
          <div>
            <p className={styles.loginEyebrow}>Local Runtime</p>
            <Title level={1} className={styles.loginTitle}>企微数字员工V1.0</Title>
          </div>
        </div>

        <Form<LoginForm>
          className={styles.loginForm}
          layout="vertical"
          onFinish={handleSubmit}
          autoComplete="off"
          size="large"
        >
          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: true, message: '请输入用户名' }]}
          >
            <Input prefix={<UserOutlined />} autoComplete="username" placeholder="请输入用户名" />
          </Form.Item>

          <Form.Item
            name="password"
            label="密码"
            rules={[{ required: true, message: '请输入密码' }]}
          >
            <Input.Password
              prefix={<LockOutlined />}
              autoComplete="current-password"
              placeholder="请输入密码"
            />
          </Form.Item>

          {error && (
            <div className={styles.loginError}>{error}</div>
          )}

          <Button
            className={styles.loginSubmit}
            type="primary"
            htmlType="submit"
            loading={loading}
            block
          >
            登录控制台
          </Button>
        </Form>
      </section>
    </main>
  );
}
