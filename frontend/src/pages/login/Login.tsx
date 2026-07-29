import { useNavigate, useSearchParams } from 'react-router-dom';
import { Form, Input, Button, message } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useUserStore, getLoginErrorMessage } from '@/store/user-store';
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
      const mustChangePassword =
        useUserStore.getState().userInfo?.must_change_password === true;
      if (mustChangePassword) {
        message.warning('密码已由管理员重置，请先设置新的登录密码');
        navigate('/system/user/profile', { replace: true });
        return;
      }
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
        <div className={styles.brandNoise} />
        <div className={`${styles.brandGlow} ${styles.brandGlow1}`} />
        <div className={`${styles.brandGlow} ${styles.brandGlow2}`} />
        <div className={`${styles.brandGlow} ${styles.brandGlow3}`} />

        <div className={styles.systemStatus}>
          <span className={styles.statusPulse} />
          <span>WORKFORCE OS</span>
          <span className={styles.statusDivider} />
          <span className={styles.statusOnline}>SYSTEM ONLINE</span>
        </div>

        <div className={styles.constellation} aria-hidden="true">
          <div className={`${styles.orbit} ${styles.orbitOuter}`} />
          <div className={`${styles.orbit} ${styles.orbitMiddle}`} />
          <div className={`${styles.orbit} ${styles.orbitInner}`} />

          <svg
            className={styles.signalMap}
            viewBox="0 0 620 620"
            role="presentation"
          >
            <defs>
              <linearGradient id="signal-gradient" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#b9ff66" />
                <stop offset="48%" stopColor="#2dd4bf" />
                <stop offset="100%" stopColor="#38bdf8" />
              </linearGradient>
            </defs>
            <path d="M310 310 L126 165" />
            <path d="M310 310 L488 118" />
            <path d="M310 310 L525 405" />
            <path d="M310 310 L188 515" />
            <circle cx="310" cy="310" r="216" />
          </svg>

          <div className={styles.coreHalo} />
          <div className={styles.coreNode}>
            <span className={styles.coreIndex}>DE</span>
            <img src={logo} alt="" />
            <small>ORCHESTRATOR</small>
          </div>

          <div className={`${styles.agentNode} ${styles.agentNodePlan}`}>
            <span className={styles.agentIndex}>01</span>
            <strong>规划</strong>
            <small>PLAN</small>
          </div>
          <div className={`${styles.agentNode} ${styles.agentNodeKnow}`}>
            <span className={styles.agentIndex}>02</span>
            <strong>知识</strong>
            <small>KNOW</small>
          </div>
          <div className={`${styles.agentNode} ${styles.agentNodeAct}`}>
            <span className={styles.agentIndex}>03</span>
            <strong>执行</strong>
            <small>ACT</small>
          </div>
          <div className={`${styles.agentNode} ${styles.agentNodeLearn}`}>
            <span className={styles.agentIndex}>04</span>
            <strong>进化</strong>
            <small>LEARN</small>
          </div>

          <div className={styles.liveCard}>
            <span className={styles.liveCardLabel}>LIVE FLOW</span>
            <strong>12</strong>
            <span>任务协同中</span>
            <div className={styles.liveBars}>
              <i />
              <i />
              <i />
              <i />
              <i />
            </div>
          </div>
        </div>

        <div className={styles.brandContent}>
          <div className={styles.brandLogo}>
            <div className={styles.brandLogoIcon}>
              <img src={logo} alt="logo" className={styles.brandLogoImg} />
            </div>
            <span className={styles.brandLogoText}>Digital Employee</span>
          </div>

          <p className={styles.brandEyebrow}>
            <span>AI-NATIVE COLLABORATION</span>
            <span>2026.07</span>
          </p>

          <h1 className={styles.brandTitle}>
            数字员工
            <br />
            <span>协作中枢</span>
          </h1>

          <p className={styles.brandSubtitle}>
            让人<span className={styles.brandSubtitleAccent}>回归创造</span>
            <br />
            把重复工作交给始终在线的数字团队
          </p>
          <div className={styles.capabilityList}>
            <span>任务编排</span>
            <span>知识执行</span>
            <span>持续进化</span>
          </div>
        </div>

        <div className={styles.brandFooter}>
          <span>© 2026 DIGITAL EMPLOYEE</span>
          <span className={styles.footerRule} />
          <span>CREATE · AUTOMATE · ELEVATE</span>
        </div>
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
              label={<span className={styles.formLabel}>用户名</span>}
              rules={[{ required: true, message: '请输入用户名' }]}
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
              rules={[{ required: true, message: '请输入密码' }]}
              className={styles.formField}
            >
              <Input.Password
                prefix={<LockOutlined style={{ color: '#94a3b8' }} />}
                placeholder="请输入密码"
                className={styles.formInput}
                size="large"
                autoComplete="current-password"
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
                {loading ? '登录中...' : '登 录'}
              </Button>
            </Form.Item>
          </Form>

          <div className={styles.registerLink}>
            还没有账号？
            <Button type="link" onClick={() => navigate('/register')}>
              立即注册
            </Button>
          </div>

          <div className={styles.formFooter}>
            忘记密码？请联系系统管理员
          </div>
        </div>
      </div>
    </div>
  );
}
