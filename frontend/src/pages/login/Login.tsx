import { useEffect, useMemo } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Button, Checkbox, Form, Input, message } from 'antd';
import { LockOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons';
import { useUserStore, getLoginErrorMessage } from '@/store/user-store';
import logo from '@/assets/images/avatar/logo.svg';
import presentationArt from '@/assets/images/illustrations/digital-presentation-amico.svg';
import styles from './index.module.css';
import { useRateLimitCountdown } from '@/hooks/use-rate-limit-countdown';
import { getRateLimitRetryAfter } from '@/utils/request';
import ArithmeticCaptchaInput from '@/components/arithmetic-captcha/ArithmeticCaptchaInput';
import { useArithmeticCaptcha } from '@/hooks/use-arithmetic-captcha';
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
  const greeting = useMemo(() => greetingByHour(), []);

  useEffect(() => {
    async function restoreRememberedCredential(): Promise<void> {
      const credential = await loadRememberedCredential();
      if (credential) {
        form.setFieldsValue({
          username: credential.username,
          password: credential.password,
          remember_password: true,
        });
      }
    }
    void restoreRememberedCredential();
  }, [form]);

  const handleSubmit = async (values: LoginFormValues): Promise<void> => {
    if (!challenge) {
      message.error(captchaError ?? '请先获取验证码');
      await refreshCaptcha();
      return;
    }
    try {
      await login({
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
      const mustChangePassword =
        useUserStore.getState().userInfo?.must_change_password === true;
      if (mustChangePassword) {
        message.warning('密码已由管理员重置，请先设置新的登录密码');
        navigate('/system/user/profile', { replace: true });
        return;
      }
      message.success('登录成功');
      const redirect = searchParams.get('redirect') || '/';
      navigate(redirect, { replace: true });
    } catch (error) {
      const retryAfter = getRateLimitRetryAfter(error);
      if (retryAfter) startCountdown(retryAfter);
      message.error(getLoginErrorMessage(error));
      form.setFieldValue('captcha_answer', undefined);
      await refreshCaptcha();
    }
  };

  return (
    <div className={styles.container}>
      <section className={styles.brandPanel} aria-label="品牌展示">
        <div className={styles.brandAtmosphere} aria-hidden="true">
          <span className={`${styles.orb} ${styles.orbA}`} />
          <span className={`${styles.orb} ${styles.orbB}`} />
          <span className={`${styles.orb} ${styles.orbC}`} />
          <span className={styles.wave} />
          <span className={`${styles.spark} ${styles.spark1}`} />
          <span className={`${styles.spark} ${styles.spark2}`} />
          <span className={`${styles.spark} ${styles.spark3}`} />
          <span className={`${styles.spark} ${styles.spark4}`} />
          <span className={styles.sheen} />
        </div>

        <header className={styles.brandHeader}>
          <div className={styles.brandMark}>
            <img src={logo} alt="" className={styles.brandMarkImg} />
          </div>
          <span className={styles.brandName}>Digital Employee</span>
        </header>

        <div className={styles.heroVisual}>
          <div className={styles.heroGlow} />
          <img
            src={presentationArt}
            alt=""
            className={styles.heroArt}
          />
          <span className={styles.heroShadow} />
        </div>

        <div className={styles.brandCopy}>
          <h1 className={styles.brandTitle}>数字员工</h1>
          <p className={styles.brandSubtitle}>
            把重复工作交给始终在线的数字团队，让人回归创造。
          </p>
        </div>

        <footer className={styles.brandFooter}>
          <span>© 2026 Digital Employee</span>
        </footer>
      </section>

      <section className={styles.formPanel}>
        <div className={styles.formAtmosphere} aria-hidden="true">
          <span className={`${styles.formOrb} ${styles.formOrbA}`} />
          <span className={`${styles.formOrb} ${styles.formOrbB}`} />
          <span className={`${styles.formOrb} ${styles.formOrbC}`} />
          <span className={styles.formGrid} />
          <span className={styles.formRing} />
          <span className={styles.formSpeck} />
        </div>

        <div className={styles.formStage}>
          <p className={styles.formGreeting}>{greeting}</p>
          <h2 className={styles.formTitle}>
            继续创造
            <em>从这里开始</em>
          </h2>
          <p className={styles.formSubtitle}>
            登录后编排任务、接入会话，让数字员工替你把事做完。
          </p>

          <Form
            form={form}
            name="login"
            layout="vertical"
            onFinish={handleSubmit}
            initialValues={{
              remember_password: isRememberPasswordEnabled(),
            }}
            autoComplete="off"
            className={styles.form}
            requiredMark={false}
          >
            <Form.Item
              name="username"
              label={<span className={styles.formLabel}>用户名</span>}
              rules={[{ required: true, message: '请输入用户名' }]}
              className={styles.formField}
            >
              <Input
                prefix={<UserOutlined className={styles.inputIcon} />}
                placeholder="你的账号"
                className={styles.formInput}
                size="large"
                autoComplete="username"
              />
            </Form.Item>

            <Form.Item
              name="password"
              label={<span className={styles.formLabel}>密码</span>}
              rules={[{ required: true, message: '请输入密码' }]}
              className={styles.formField}
            >
              <Input.Password
                prefix={<LockOutlined className={styles.inputIcon} />}
                placeholder="登录密码"
                className={styles.formInput}
                size="large"
                autoComplete="current-password"
              />
            </Form.Item>

            <Form.Item
              name="captcha_answer"
              label={
                <span className={styles.formLabel}>
                  <SafetyCertificateOutlined className={styles.labelIcon} />
                  验证码
                </span>
              }
              rules={[
                { required: true, message: '请输入计算结果' },
                { pattern: /^\d{1,3}$/, message: '请输入正确的数字结果' },
              ]}
              className={styles.formField}
            >
              <ArithmeticCaptchaInput
                challenge={challenge}
                loading={captchaLoading}
                error={captchaError}
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

            <Form.Item className={styles.submitField}>
              <Button
                type="primary"
                htmlType="submit"
                loading={loading}
                disabled={remainingSeconds > 0}
                className={styles.submitButton}
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

          <p className={styles.registerLine}>
            还没有账号？
            <button
              type="button"
              className={styles.registerAction}
              onClick={() => navigate('/register')}
            >
              去注册
            </button>
          </p>
        </div>
      </section>
    </div>
  );
}
