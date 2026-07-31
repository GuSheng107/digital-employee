import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { Button, Checkbox, Form, Input, message } from 'antd';
import { LockOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons';
import { useUserStore, getLoginErrorMessage } from '@/store/user-store';
import presentationArt from '@/assets/images/illustrations/digital-presentation-amico.svg';
import AuthPageShell from '@/components/auth-page-shell/AuthPageShell';
import shell from '@/components/auth-page-shell/index.module.css';
import styles from './index.module.css';
import { useRateLimitCountdown } from '@/hooks/use-rate-limit-countdown';
import { getRateLimitRetryAfter } from '@/utils/request';
import { getSafeRedirectPath } from '@/utils/auth-session';
import ArithmeticCaptchaInput from '@/components/arithmetic-captcha/ArithmeticCaptchaInput';
import { useArithmeticCaptcha } from '@/hooks/use-arithmetic-captcha';
import { loginFormTheme } from '@/pages/auth-form-theme';
import {
  forgetCredentialPreference,
  isRememberPasswordEnabled,
  loadRememberedCredential,
  rememberCredential,
} from '@/utils/browser-credentials';

interface LoginFormValues {
  username: string;
  password: string;
  captcha_answer: string;
  remember_password?: boolean;
}

function greetingByHour(): string {
  const hour = new Date().getHours();
  if (hour < 5) return '夜深了';
  if (hour < 11) return '早上好';
  if (hour < 14) return '中午好';
  if (hour < 18) return '下午好';
  return '晚上好';
}

export default function Login(): React.ReactElement {
  const navigate = useNavigate();
  const [form] = Form.useForm<LoginFormValues>();
  const [searchParams] = useSearchParams();
  const login = useUserStore((state) => state.login);
  const loading = useUserStore((state) => state.loading);
  const { remainingSeconds, startCountdown } = useRateLimitCountdown();
  const {
    challenge,
    loading: captchaLoading,
    error: captchaError,
    refreshCaptcha,
  } = useArithmeticCaptcha();
  const [greeting] = useState(() => greetingByHour());

  useEffect(() => {
    let active = true;
    async function restoreRememberedCredential(): Promise<void> {
      const credential = await loadRememberedCredential();
      if (active && credential) {
        form.setFieldsValue({
          username: credential.username,
          password: credential.password,
          remember_password: true,
        });
      }
    }
    void restoreRememberedCredential();
    return () => {
      active = false;
    };
  }, [form]);

  const handleSubmit = async (values: LoginFormValues): Promise<void> => {
    if (!challenge) {
      message.error(captchaError ?? '请先获取验证码');
      await refreshCaptcha();
      return;
    }
    try {
      const tokenPair = await login({
        username: values.username,
        password: values.password,
        captcha_id: challenge.captcha_id,
        captcha_answer: values.captcha_answer,
      });
      if (values.remember_password) {
        await rememberCredential(values.username, values.password);
      } else {
        await forgetCredentialPreference();
      }
      if (tokenPair.must_change_password) {
        message.warning('密码已由管理员重置，请先设置新的登录密码');
        navigate('/system/user/profile', { replace: true });
        return;
      }
      message.success('登录成功');
      navigate(getSafeRedirectPath(searchParams.get('redirect')), { replace: true });
    } catch (error) {
      const retryAfter = getRateLimitRetryAfter(error);
      if (retryAfter) startCountdown(retryAfter);
      message.error(getLoginErrorMessage(error));
      form.setFieldValue('captcha_answer', undefined);
      await refreshCaptcha();
    }
  };

  return (
    <AuthPageShell
      theme={loginFormTheme}
      heroSrc={presentationArt}
      brandTitle="数字员工"
      brandSubtitle="把重复工作交给始终在线的数字团队，让人回归创造。"
      formGreeting={greeting}
      formTitle={
        <>
          继续创造
          <em>从这里开始</em>
        </>
      }
      formSubtitle="登录后编排任务、接入会话，让数字员工替你把事做完。"
      footer={
        <p className={shell.registerLine}>
          还没有账号？
          <button
            type="button"
            className={shell.registerAction}
            onClick={() => navigate('/register')}
          >
            去注册
          </button>
        </p>
      }
    >
      <Form
        form={form}
        name="login"
        layout="vertical"
        onFinish={handleSubmit}
        initialValues={{
          remember_password: isRememberPasswordEnabled(),
        }}
        autoComplete="off"
        className={shell.form}
        requiredMark={false}
      >
        <Form.Item
          name="username"
          label={<span className={shell.formLabel}>用户名</span>}
          rules={[{ required: true, message: '请输入用户名' }]}
          className={shell.formField}
        >
          <Input
            prefix={<UserOutlined className={shell.inputIcon} />}
            placeholder="你的账号"
            className={shell.formInput}
            size="large"
            autoComplete="username"
          />
        </Form.Item>

        <Form.Item
          name="password"
          label={<span className={shell.formLabel}>密码</span>}
          rules={[{ required: true, message: '请输入密码' }]}
          className={shell.formField}
        >
          <Input.Password
            prefix={<LockOutlined className={shell.inputIcon} />}
            placeholder="登录密码"
            className={shell.formInput}
            size="large"
            autoComplete="current-password"
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
            tone="light"
            onRefresh={() => {
              form.setFieldValue('captcha_answer', undefined);
              void refreshCaptcha();
            }}
          />
        </Form.Item>

        <div className={styles.formRow}>
          <Form.Item
            name="remember_password"
            valuePropName="checked"
            className={styles.rememberField}
          >
            <Checkbox className={styles.rememberCheckbox}>记住我</Checkbox>
          </Form.Item>
          <button
            type="button"
            className={styles.helpLink}
            onClick={() => message.info('请联系系统管理员重置密码')}
          >
            忘记密码
          </button>
        </div>

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
              ? '正在登录...'
              : remainingSeconds > 0
                ? `${remainingSeconds} 秒后重试`
                : '登录'}
          </Button>
        </Form.Item>
      </Form>
    </AuthPageShell>
  );
}
