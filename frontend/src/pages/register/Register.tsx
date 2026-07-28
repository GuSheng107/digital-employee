import { useNavigate } from 'react-router-dom';
import { Form, Input, Button, message } from 'antd';
import { UserOutlined, LockOutlined, GiftOutlined } from '@ant-design/icons';
import { useUserStore, getRegisterErrorMessage } from '@/store/user-store';
import logo from '@/assets/images/avatar/logo.svg';
import styles from './index.module.css';

interface RegisterFormValues {
  username: string;
  password: string;
  confirmPassword: string;
  invite_code: string;
}

export default function Register(): React.ReactElement {
  const navigate = useNavigate();
  const register = useUserStore((state) => state.register);
  const loading = useUserStore((state) => state.loading);

  const handleSubmit = async (values: RegisterFormValues): Promise<void> => {
    try {
      await register(values.username, values.password, values.invite_code);
      message.success('注册成功');
      // 注册成功后自动登录，跳转首页
      navigate('/', { replace: true });
    } catch (error) {
      // 用 message 全局提示替代 Alert，在深色背景上更醒目
      message.error(getRegisterErrorMessage(error));
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
            加入我们
            <br />
            开启创造之旅
          </h1>

          <p className={styles.brandSubtitle}>
            让人<span className={styles.brandSubtitleAccent}>回归创造</span>
            ，把重复交给 AI
          </p>
          <p className={styles.brandTagline}>JOIN · CREATE · ELEVATE</p>
        </div>

        <div className={styles.brandFooter}>© 2026 Digital Employee. All rights reserved.</div>
      </div>

      {/* 右侧注册表单区 */}
      <div className={styles.formPanel}>
        <div className={styles.formCard}>
          <h2 className={styles.formTitle}>创建账号</h2>
          <p className={styles.formSubtitle}>填写信息完成注册</p>

          <Form
            name="register"
            layout="vertical"
            onFinish={handleSubmit}
            autoComplete="off"
            className={styles.form}
          >
            <Form.Item
              name="username"
              rules={[
                { required: true, message: '请输入用户名' },
                { min: 4, max: 64, message: '用户名长度需为 4-64 个字符' },
              ]}
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
              rules={[
                { required: true, message: '请输入密码' },
                { min: 8, max: 128, message: '密码长度需为 8-128 个字符' },
              ]}
              className={styles.formField}
            >
              <div>
                <label className={styles.formLabel}>密码</label>
                <Input.Password
                  prefix={<LockOutlined style={{ color: '#94a3b8' }} />}
                  placeholder="请输入密码"
                  className={styles.formInput}
                  size="large"
                  autoComplete="new-password"
                />
              </div>
            </Form.Item>

            <Form.Item
              name="confirmPassword"
              dependencies={['password']}
              rules={[
                { required: true, message: '请再次输入密码' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('password') === value) {
                      return Promise.resolve();
                    }
                    return Promise.reject(new Error('两次输入的密码不一致'));
                  },
                }),
              ]}
              className={styles.formField}
            >
              <div>
                <label className={styles.formLabel}>确认密码</label>
                <Input.Password
                  prefix={<LockOutlined style={{ color: '#94a3b8' }} />}
                  placeholder="请再次输入密码"
                  className={styles.formInput}
                  size="large"
                  autoComplete="new-password"
                />
              </div>
            </Form.Item>

            <Form.Item
              name="invite_code"
              rules={[
                { required: true, message: '请输入邀请码' },
                { len: 8, message: '邀请码长度需为 8 个字符' },
              ]}
              className={styles.formField}
            >
              <div>
                <label className={styles.formLabel}>邀请码</label>
                <Input
                  prefix={<GiftOutlined style={{ color: '#94a3b8' }} />}
                  placeholder="请输入邀请码"
                  className={styles.formInput}
                  size="large"
                  autoComplete="off"
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
                {loading ? '注册中...' : '注 册'}
              </Button>
            </Form.Item>
          </Form>

          <div className={styles.registerLink}>
            已有账号？<a onClick={() => navigate('/login')}>返回登录</a>
          </div>

          <div className={styles.formFooter}>
            注册即代表同意遵守平台使用规范
          </div>
        </div>
      </div>
    </div>
  );
}
