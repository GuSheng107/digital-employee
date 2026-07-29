import { useEffect, useState } from 'react';
import {
  Alert,
  Avatar,
  Button,
  Descriptions,
  Form,
  Input,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd';
import type { UploadProps } from 'antd';
import ImgCrop from 'antd-img-crop';
import { UserOutlined, UploadOutlined } from '@ant-design/icons';
import { useUserStore } from '@/store/user-store';
import { updateProfile, uploadAvatar } from '@/api/user-api';
import { getRequestErrorMessage } from '@/utils/request';
import { resolveAvatarUrl } from '@/utils/avatar-url';
import { PHONE_DIAL_PREFIX } from '@/config/identity-config';
import {
  EMAIL_PATTERN,
  PASSWORD_COMPLEXITY_MESSAGE,
  PASSWORD_COMPLEXITY_PATTERN,
  formatPhoneNumberForInput,
  normalizePhoneNumber,
} from '@/utils/identity-validation';
import {
  getVipDisplayFallback,
  VIP_LEVEL,
} from '@/constants/access-control';
import styles from './index.module.css';

const { Title } = Typography;

/** 头像大小上限：3MB（与后端一致） */
const AVATAR_MAX_SIZE = 3 * 1024 * 1024;

interface ProfileFormValues {
  nickname: string;
  email: string;
  phone: string;
  /** 修改密码时填入，留空表示不修改 */
  password?: string;
  /** 确认密码，与 password 必须一致 */
  confirmPassword?: string;
}

export default function Profile(): React.ReactElement {
  const userInfo = useUserStore((state) => state.userInfo);
  const avatar = useUserStore((state) => state.avatar);
  const reloadMenus = useUserStore((state) => state.reloadMenus);
  const [form] = Form.useForm<ProfileFormValues>();
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [uploading, setUploading] = useState<boolean>(false);

  useEffect(() => {
    if (userInfo) {
      form.setFieldsValue({
        nickname: userInfo.nickname ?? '',
        email: userInfo.email ?? '',
        phone: formatPhoneNumberForInput(userInfo.phone),
      });
    }
  }, [userInfo, form]);

  const handleUpload: NonNullable<UploadProps['customRequest']> = async (options) => {
    const { file } = options;
    // antd-img-crop 裁剪后返回 File；兼容 Blob 场景
    if (!(file instanceof File) && !(file instanceof Blob)) {
      message.error('请选择有效的图片文件');
      return;
    }
    // 前端预校验大小，避免无效请求
    if (file.size > AVATAR_MAX_SIZE) {
      message.error('头像文件不能超过 3MB');
      return;
    }
    setUploading(true);
    try {
      const result = await uploadAvatar(file);
      useUserStore.setState((state) => ({
        avatar: resolveAvatarUrl(result.avatar_url) ?? state.avatar,
        userInfo: state.userInfo
          ? { ...state.userInfo, avatar_url: result.avatar_url }
          : null,
      }));
      message.success('头像更新成功');
    } catch (error) {
      message.error(getRequestErrorMessage(error, '头像上传失败'));
    } finally {
      setUploading(false);
    }
  };

  const handleSubmit = async (values: ProfileFormValues): Promise<void> => {
    const parsedPhone = values.phone
      ? normalizePhoneNumber(values.phone)
      : null;
    if (values.phone && !parsedPhone) {
      message.error(`请输入有效的 ${PHONE_DIAL_PREFIX} 手机号码`);
      return;
    }
    const normalizedPhone = parsedPhone ?? undefined;
    setSubmitting(true);
    try {
      await updateProfile({
        nickname: values.nickname || undefined,
        email: values.email?.trim().toLowerCase() || undefined,
        phone: normalizedPhone,
        // 密码为空字符串时不传，避免后端把空串当新密码校验
        password: values.password ? values.password : undefined,
      });
      await reloadMenus();
      message.success('个人信息更新成功');
      // 清空密码字段，避免下次提交重复带值
      form.setFieldsValue({ password: undefined, confirmPassword: undefined });
    } catch (error) {
      message.error(getRequestErrorMessage(error, '个人信息更新失败'));
    } finally {
      setSubmitting(false);
    }
  };

  if (!userInfo) {
    return (
      <div className={styles.page}>
        <p className={styles.loading}>加载中...</p>
      </div>
    );
  }

  // VIP 展示文案：优先用后端返回的 vip_level_display，回退到本地映射
  const vipDisplay = userInfo.vip_level_display
    || getVipDisplayFallback(userInfo.vip_level, userInfo.is_vip);
  const isSuperAdmin = userInfo.vip_level === VIP_LEVEL.SUPER_ADMIN;
  const isManager = userInfo.vip_level === VIP_LEVEL.MANAGER;

  return (
    <div className={styles.page}>
      <Title level={3} className={styles.title}>个人信息</Title>
      <div className={styles.layout}>
        <div className={styles.avatarSection}>
          <Avatar src={avatar} icon={<UserOutlined />} size={120} className={styles.avatar} />
          <ImgCrop
            rotationSlider
            aspectSlider
            showReset
            cropShape="round"
            modalTitle="裁剪头像"
            modalOk="确定"
            modalCancel="取消"
            aspect={1}
          >
            <Upload showUploadList={false} accept="image/*" customRequest={handleUpload}>
              <Button icon={<UploadOutlined />} loading={uploading}>
                更换头像
              </Button>
            </Upload>
          </ImgCrop>
          <div className={styles.vipInfo}>
            {isSuperAdmin ? (
              <Tag color="purple">{vipDisplay}</Tag>
            ) : isManager ? (
              <Tag color="blue">{vipDisplay}</Tag>
            ) : userInfo.is_vip ? (
              <Tag color="gold">{vipDisplay}</Tag>
            ) : (
              <Tag>{vipDisplay}</Tag>
            )}
          </div>
        </div>
        <div className={styles.infoSection}>
          {userInfo.must_change_password ? (
            <Alert
              type="warning"
              showIcon
              message="请先修改临时密码"
              description="当前密码由管理员重置。完成密码修改后，才能继续访问其他业务功能。"
            />
          ) : null}
          <Descriptions title="基本信息" bordered column={1} className={styles.descriptions}>
            <Descriptions.Item label="用户名">{userInfo.username}</Descriptions.Item>
            <Descriptions.Item label="用户ID">{userInfo.id}</Descriptions.Item>
            <Descriptions.Item label="VIP 等级">{vipDisplay}</Descriptions.Item>
            <Descriptions.Item label="角色">
              {userInfo.roles.length > 0
                ? userInfo.roles.map((role) => <Tag key={role} color="blue">{role}</Tag>)
                : <Tag>无角色</Tag>}
            </Descriptions.Item>
            <Descriptions.Item label="状态">
              {userInfo.status === 1 ? <Tag color="green">正常</Tag> : <Tag color="red">禁用</Tag>}
            </Descriptions.Item>
          </Descriptions>
          <Form
            form={form}
            layout="vertical"
            onFinish={handleSubmit}
            className={styles.form}
            initialValues={{ password: '', confirmPassword: '' }}
          >
            <Form.Item label="昵称" name="nickname">
              <Input placeholder="请输入昵称" />
            </Form.Item>
            <Form.Item
              label="邮箱"
              name="email"
              rules={[
                { pattern: EMAIL_PATTERN, message: '请输入有效的邮箱地址' },
              ]}
            >
              <Input placeholder="请输入邮箱" />
            </Form.Item>
            <Form.Item
              label="手机号"
              name="phone"
              rules={[
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
            >
              <Input
                prefix={PHONE_DIAL_PREFIX}
                placeholder="请输入手机号"
                autoComplete="tel"
              />
            </Form.Item>
            <Form.Item
              label="修改密码"
              name="password"
              extra={
                userInfo.must_change_password
                  ? '必须设置新密码后才能继续使用系统'
                  : '留空表示不修改密码'
              }
              rules={[
                {
                  required: userInfo.must_change_password,
                  message: '请设置新的登录密码',
                },
                {
                  pattern: PASSWORD_COMPLEXITY_PATTERN,
                  message: PASSWORD_COMPLEXITY_MESSAGE,
                },
              ]}
            >
              <Input.Password placeholder="留空不修改，填写则更新密码" autoComplete="new-password" />
            </Form.Item>
            <Form.Item
              label="确认密码"
              name="confirmPassword"
              dependencies={['password']}
              rules={[
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    const pwd = getFieldValue('password');
                    // 密码为空时不强制校验确认密码
                    if (!pwd && !value && !userInfo.must_change_password) {
                      return Promise.resolve();
                    }
                    if (!value) {
                      return Promise.reject(new Error('请再次输入新密码'));
                    }
                    if (!value || pwd === value) return Promise.resolve();
                    return Promise.reject(new Error('两次输入的密码不一致'));
                  },
                }),
              ]}
            >
              <Input.Password placeholder="请再次输入新密码" autoComplete="new-password" />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" loading={submitting}>
                保存修改
              </Button>
            </Form.Item>
          </Form>
        </div>
      </div>
    </div>
  );
}
