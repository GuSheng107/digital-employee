import { useNavigate } from 'react-router';
import { Button, Form, Input, message } from 'antd';
import {
  GiftOutlined,
  LockOutlined,
  MailOutlined,
  PhoneOutlined,
  SafetyCertificateOutlined,
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
import innovationArt from '@/assets/images/illustrations/innovation-pana.svg';
import AuthPageShell from '@/components/auth-page-shell/AuthPageShell';
import shell from '@/components/auth-page-shell/index.module.css';
import styles from './index.module.css';
import { useRateLimitCountdown } from '@/hooks/use-rate-limit-countdown';
import { getRateLimitRetryAfter } from '@/utils/request';
import ArithmeticCaptchaInput from '@/components/arithmetic-captcha/ArithmeticCaptchaInput';
import { useArithmeticCaptcha } from '@/hooks/use-arithmetic-captcha';
import { registerFormTheme } from '@/components/auth-page-shell/auth-form-theme';

interface RegisterFormValues {
  username: string;
  password: string;
  confirmPassword: string;
  email: string;
  phone: string;
  invite_code: string;
  captcha_answer: string;
}

export default function Register(): React.ReactElement {
  const navigate = useNavigate();
  const [form] = Form.useForm<RegisterFormValues>();
  const register = useUserStore((state) => state.register);
  const loading = useUserStore((state) => state.loading);
  const { remainingSeconds, startCountdown } = useRateLimitCountdown();
  const {
    challenge,
    loading: captchaLoading,
    error: captchaError,
    refreshCaptcha,
  } = useArithmeticCaptcha();

  const handleSubmit = async (values: RegisterFormValues): Promise<void> => {
    const normalizedPhone = normalizePhoneNumber(values.phone);
    if (!normalizedPhone) {
      message.error(`请输入有效的 ${PHONE_DIAL_PREFIX} 手机号码`);
      return;
    }
    if (!challenge) {
      message.error(captchaError ?? '请先获取验证码');
      await refreshCaptcha();
      return;
    }
    try {
      await register({
        username: values.username.trim(),
        password: values.password,
        email: values.email.trim().toLowerCase(),
        phone: normalizedPhone,
        invite_code: values.invite_code.trim().toUpperCase(),
        captcha_id: challenge.captcha_id,
        captcha_answer: values.captcha_answer,
      });
      message.success('注册成功');
      navigate('/', { replace: true });
    } catch (error) {
      const retryAfter = getRateLimitRetryAfter(error);
      if (retryAfter) startCountdown(retryAfter);
      message.error(getRegisterErrorMessage(error));
      form.setFieldValue('captcha_answer', undefined);
      await refreshCaptcha();
    }
  };

  return (
    <AuthPageShell
      theme={registerFormTheme}
      density="compact"
      heroSrc={innovationArt}
      brandTitle="加入团队"
      brandSubtitle="几分钟完成注册，让数字员工开始替你处理重复工作。"
      formGreeting="欢迎加入"
      formTitle={
        <>
          创建账号
          <em>开启你的协作中枢</em>
        </>
      }
      formSubtitle="填写基础信息与邀请码，注册后即可登录使用。"
      footer={
        <>
          <p className={shell.registerLine}>
            已有账号？
            <button
              type="button"
              className={shell.registerAction}
              onClick={() => navigate('/login')}
            >
              返回登录
            </button>
          </p>
          <p className={styles.formNote}>注册即代表同意遵守平台使用规范</p>
        </>
      }
    >
      <Form
        form={form}
        name="register"
        layout="vertical"
        onFinish={handleSubmit}
        autoComplete="off"
        className={shell.form}
        requiredMark={false}
      >
        <Form.Item
          name="username"
          label={<span className={shell.formLabel}>用户名</span>}
          rules={[
            { required: true, message: '请输入用户名' },
            { min: 4, max: 64, message: '用户名长度需为 4-64 个字符' },
          ]}
          className={shell.formField}
        >
          <Input
            prefix={<UserOutlined className={shell.inputIcon} />}
            placeholder="4-64 个字符"
            className={shell.formInput}
            size="large"
            autoComplete="username"
          />
        </Form.Item>

        <div className={styles.fieldPair}>
          <Form.Item
            name="email"
            label={<span className={shell.formLabel}>邮箱</span>}
            rules={[
              { required: true, message: '请输入邮箱' },
              { pattern: EMAIL_PATTERN, message: '请输入有效的邮箱地址' },
            ]}
            className={shell.formField}
          >
            <Input
              prefix={<MailOutlined className={shell.inputIcon} />}
              placeholder="name@company.com"
              className={shell.formInput}
              size="large"
              autoComplete="email"
            />
          </Form.Item>

          <Form.Item
            name="phone"
            label={<span className={shell.formLabel}>手机号</span>}
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
            className={shell.formField}
          >
            <Input
              prefix={
                <span className={styles.phonePrefix}>
                  <PhoneOutlined className={shell.inputIcon} />
                  <span>{PHONE_DIAL_PREFIX}</span>
                </span>
              }
              placeholder="手机号码"
              className={shell.formInput}
              size="large"
              autoComplete="tel"
            />
          </Form.Item>
        </div>

        <div className={styles.fieldPair}>
          <Form.Item
            name="password"
            label={<span className={shell.formLabel}>密码</span>}
            rules={[
              { required: true, message: '请输入密码' },
              {
                pattern: PASSWORD_COMPLEXITY_PATTERN,
                message: PASSWORD_COMPLEXITY_MESSAGE,
              },
            ]}
            className={shell.formField}
          >
            <Input.Password
              prefix={<LockOutlined className={shell.inputIcon} />}
              placeholder="设置密码"
              className={shell.formInput}
              size="large"
              autoComplete="new-password"
            />
          </Form.Item>

          <Form.Item
            name="confirmPassword"
            label={<span className={shell.formLabel}>确认密码</span>}
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
            className={shell.formField}
          >
            <Input.Password
              prefix={<LockOutlined className={shell.inputIcon} />}
              placeholder="再次输入"
              className={shell.formInput}
              size="large"
              autoComplete="new-password"
            />
          </Form.Item>
        </div>

        <Form.Item
          name="invite_code"
          label={<span className={shell.formLabel}>邀请码</span>}
          rules={[
            { required: true, message: '请输入邀请码' },
            {
              pattern: INVITE_CODE_PATTERN,
              message: INVITE_CODE_MESSAGE,
            },
          ]}
          className={shell.formField}
        >
          <Input
            prefix={<GiftOutlined className={shell.inputIcon} />}
            placeholder="请输入邀请码"
            className={shell.formInput}
            size="large"
            autoComplete="off"
            maxLength={32}
          />
        </Form.Item>

        <Form.Item
          name="captcha_answer"
          label={
            <span className={shell.formLabel}>
              <SafetyCertificateOutlined className={shell.labelIcon} />
              验证码
            </span>
          }
          rules={[
            { required: true, message: '请输入计算结果' },
            { pattern: /^\d{1,3}$/, message: '请输入正确的数字结果' },
          ]}
          className={shell.formField}
        >
          <ArithmeticCaptchaInput
            challenge={challenge}
            loading={captchaLoading}
            error={captchaError}
            tone="lightCompact"
            onRefresh={() => {
              form.setFieldValue('captcha_answer', undefined);
              void refreshCaptcha();
            }}
          />
        </Form.Item>

        <Form.Item className={shell.submitField}>
          <Button
            type="primary"
            htmlType="submit"
            loading={loading}
            disabled={remainingSeconds > 0}
            className={shell.submitButton}
            size="large"
          >
            {loading
              ? '正在注册...'
              : remainingSeconds > 0
                ? `${remainingSeconds} 秒后重试`
                : '注册'}
          </Button>
        </Form.Item>
      </Form>
    </AuthPageShell>
  );
}
