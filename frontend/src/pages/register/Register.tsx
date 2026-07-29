import { useNavigate } from 'react-router-dom';
import { Form, Input, Button, message } from 'antd';
import {
  GiftOutlined,
  LockOutlined,
  MailOutlined,
  PhoneOutlined,
  UserOutlined,
} from '@ant-design/icons';
import { useUserStore, getRegisterErrorMessage } from '@/store/user-store';
import { PHONE_DIAL_PREFIX } from '@/config/identity-config';
import {
  EMAIL_PATTERN,
  INVITE_CODE_MESSAGE,
  INVITE_CODE_PATTERN,
  PASSWORD_COMPLEXITY_MESSAGE,
  PASSWORD_COMPLEXITY_PATTERN,
  normalizePhoneNumber,
} from '@/utils/identity-validation';
import logo from '@/assets/images/avatar/logo.svg';
import styles from './index.module.css';

interface RegisterFormValues {
  username: string;
  password: string;
  confirmPassword: string;
  email: string;
  phone: string;
  invite_code: string;
}

export default function Register(): React.ReactElement {
  const navigate = useNavigate();
  const register = useUserStore((state) => state.register);
  const loading = useUserStore((state) => state.loading);

  const handleSubmit = async (values: RegisterFormValues): Promise<void> => {
    const normalizedPhone = normalizePhoneNumber(values.phone);
    if (!normalizedPhone) {
      message.error(`请输入有效的 ${PHONE_DIAL_PREFIX} 手机号码`);
      return;
    }
    try {
      await register({
        username: values.username.trim(),
        password: values.password,
        email: values.email.trim().toLowerCase(),
        phone: normalizedPhone,
        invite_code: values.invite_code.trim().toUpperCase(),
      });
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
              label={<span className={styles.formLabel}>用户名</span>}
              rules={[
                { required: true, message: '请输入用户名' },
                { min: 4, max: 64, message: '用户名长度需为 4-64 个字符' },
              ]}
              className={styles.formField}
            >
              <Input
                prefix={<UserOutlined style={{ color: '#94a3b8' }} />}
                placeholder="请输入用户名"
                className={styles.formInput}
                size="large"
                autoComplete="username"
              />
            </Form.Item>

            <Form.Item
              name="password"
              label={<span className={styles.formLabel}>密码</span>}
              rules={[
                { required: true, message: '请输入密码' },
                {
                  pattern: PASSWORD_COMPLEXITY_PATTERN,
                  message: PASSWORD_COMPLEXITY_MESSAGE,
                },
              ]}
              className={styles.formField}
            >
              <Input.Password
                prefix={<LockOutlined style={{ color: '#94a3b8' }} />}
                placeholder="请输入密码"
                className={styles.formInput}
                size="large"
                autoComplete="new-password"
              />
            </Form.Item>

            <Form.Item
              name="confirmPassword"
              label={<span className={styles.formLabel}>确认密码</span>}
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
              <Input.Password
                prefix={<LockOutlined style={{ color: '#94a3b8' }} />}
                placeholder="请再次输入密码"
                className={styles.formInput}
                size="large"
                autoComplete="new-password"
              />
            </Form.Item>

            <Form.Item
              name="email"
              label={<span className={styles.formLabel}>邮箱</span>}
              rules={[
                { required: true, message: '请输入邮箱' },
                { pattern: EMAIL_PATTERN, message: '请输入有效的邮箱地址' },
              ]}
              className={styles.formField}
            >
              <Input
                prefix={<MailOutlined style={{ color: '#94a3b8' }} />}
                placeholder="请输入邮箱"
                className={styles.formInput}
                size="large"
                autoComplete="email"
              />
            </Form.Item>

            <Form.Item
              name="phone"
              label={<span className={styles.formLabel}>手机号</span>}
              rules={[
                { required: true, message: '请输入手机号' },
                {
                  validator: (_, value: string | undefined) => {
                    if (!value || normalizePhoneNumber(value)) {
                      return Promise.resolve();
                    }
                    return Promise.reject(
                      new Error(`请输入有效的 ${PHONE_DIAL_PREFIX} 手机号码`),
                    );
                  },
                },
              ]}
              className={styles.formField}
            >
              <Input
                prefix={
                  <>
                    <PhoneOutlined style={{ color: '#94a3b8' }} />
                    <span>{PHONE_DIAL_PREFIX}</span>
                  </>
                }
                placeholder="请输入手机号"
                className={styles.formInput}
                size="large"
                autoComplete="tel"
              />
            </Form.Item>

            <Form.Item
              name="invite_code"
              label={<span className={styles.formLabel}>邀请码</span>}
              rules={[
                { required: true, message: '请输入邀请码' },
                {
                  pattern: INVITE_CODE_PATTERN,
                  message: INVITE_CODE_MESSAGE,
                },
              ]}
              className={styles.formField}
            >
              <Input
                prefix={<GiftOutlined style={{ color: '#94a3b8' }} />}
                placeholder="请输入邀请码"
                className={styles.formInput}
                size="large"
                autoComplete="off"
                maxLength={32}
              />
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
