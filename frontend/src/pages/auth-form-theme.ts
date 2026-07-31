import type { ThemeConfig } from 'antd';

/** 登录 / 注册页局部主题：用 token 覆盖 Ant Design，避免 CSS !important。 */
const coral = '#ff725e';
const coralDeep = '#e85a48';
const ink = '#263238';

const sharedAuthTokens: ThemeConfig = {
  token: {
    colorPrimary: coral,
    colorPrimaryHover: coralDeep,
    colorPrimaryActive: coralDeep,
    colorText: ink,
    colorTextPlaceholder: '#9e9e9e',
    fontFamily:
      "system-ui, -apple-system, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif",
  },
  components: {
    Checkbox: {
      colorPrimary: coral,
      colorBorder: 'rgba(255, 114, 94, 0.35)',
      borderRadiusSM: 5,
    },
  },
};

const sharedInputChrome = {
  colorBgContainer: '#f5f5f5',
  colorBorder: 'transparent',
  hoverBorderColor: 'transparent',
  activeBorderColor: 'rgba(255, 114, 94, 0.55)',
  activeShadow: '0 0 0 4px rgba(255, 114, 94, 0.12)',
  colorText: ink,
  colorIcon: '#78909c',
  colorIconHover: coralDeep,
} as const;

export const loginFormTheme: ThemeConfig = {
  ...sharedAuthTokens,
  components: {
    ...sharedAuthTokens.components,
    Input: {
      controlHeightLG: 50,
      borderRadiusLG: 14,
      paddingInlineLG: 14,
      ...sharedInputChrome,
    },
    Button: {
      controlHeightLG: 52,
      borderRadiusLG: 16,
      fontWeight: 700,
      primaryShadow: '0 16px 32px rgba(255, 114, 94, 0.28)',
      defaultBorderColor: 'transparent',
    },
  },
};

export const registerFormTheme: ThemeConfig = {
  ...sharedAuthTokens,
  components: {
    ...sharedAuthTokens.components,
    Input: {
      controlHeightLG: 46,
      borderRadiusLG: 12,
      paddingInlineLG: 12,
      ...sharedInputChrome,
    },
    Button: {
      controlHeightLG: 48,
      borderRadiusLG: 14,
      fontWeight: 700,
      primaryShadow: '0 14px 28px rgba(255, 114, 94, 0.28)',
      defaultBorderColor: 'transparent',
    },
  },
};
