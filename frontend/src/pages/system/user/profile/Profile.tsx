import { useEffect, useState } from 'react';
import { Form, Input, Button, Avatar, Upload, Descriptions, Tag, message, Typography } from 'antd';
import type { UploadProps } from 'antd';
import ImgCrop from 'antd-img-crop';
import { UserOutlined, UploadOutlined } from '@ant-design/icons';
import { useUserStore } from '@/store/user-store';
import { updateProfile, uploadAvatar } from '@/api/user-api';
import { getRequestErrorMessage } from '@/utils/request';
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
  const [form] = Form.useForm<ProfileFormValues>();
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [uploading, setUploading] = useState<boolean>(false);

  useEffect(() => {
    if (userInfo) {
      form.setFieldsValue({
        nickname: userInfo.nickname ?? '',
        email: userInfo.email ?? '',
        phone: userInfo.phone ?? '',
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
      const result = await uploadAvatar(file as File);
      useUserStore.setState({
        avatar: result.avatar_url,
        userInfo: userInfo ? { ...userInfo, avatar_url: result.avatar_url } : userInfo,
      });
      message.success('头像更新成功');
    } catch (error) {
      message.error(getRequestErrorMessage(error, '头像上传失败'));
    } finally {
      setUploading(false);
    }
  };

  const handleSubmit = async (values: ProfileFormValues): Promise<void> => {
    setSubmitting(true);
    try {
      const result = await updateProfile({
        nickname: values.nickname || undefined,
        email: values.email || undefined,
        phone: values.phone || undefined,
        // 密码为空字符串时不传，避免后端把空串当新密码校验
        password: values.password ? values.password : undefined,
      });
      if (userInfo) {
        useUserStore.setState({
          userInfo: {
            ...userInfo,
            nickname: result.nickname,
            email: result.email,
            phone: result.phone,
            avatar_url: result.avatar_url,
          },
        });
      }
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
    || (userInfo.is_vip ? `VIP${userInfo.vip_level}` : '普通用户');
  const isAdmin = userInfo.vip_level === 99;

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
            {isAdmin ? (
              <Tag color="purple">{vipDisplay}</Tag>
            ) : userInfo.is_vip ? (
              <Tag color="gold">{vipDisplay}</Tag>
            ) : (
              <Tag>{vipDisplay}</Tag>
            )}
          </div>
        </div>
        <div className={styles.infoSection}>
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
            <Form.Item label="邮箱" name="email">
              <Input placeholder="请输入邮箱" />
            </Form.Item>
            <Form.Item label="手机号" name="phone">
              <Input placeholder="请输入手机号" />
            </Form.Item>
            <Form.Item
              label="修改密码"
              name="password"
              extra="留空表示不修改密码；填写后需 8-128 位"
              rules={[
                { min: 8, max: 128, message: '密码长度需在 8-128 之间' },
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
                    if (!pwd && !value) return Promise.resolve();
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
