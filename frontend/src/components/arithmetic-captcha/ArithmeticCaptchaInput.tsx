import type { ChangeEvent, ReactElement } from 'react';
import { ReloadOutlined } from '@ant-design/icons';
import { Button, Input, Skeleton, Tooltip } from 'antd';
import type { CaptchaChallenge } from '@/api/auth-api';
import styles from './index.module.css';

interface ArithmeticCaptchaInputProps {
  value?: string;
  onChange?: (event: ChangeEvent<HTMLInputElement>) => void;
  challenge: CaptchaChallenge | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}

/** 数字答案输入框与可刷新算术图片验证码。 */
export default function ArithmeticCaptchaInput({
  value,
  onChange,
  challenge,
  loading,
  error,
  onRefresh,
}: ArithmeticCaptchaInputProps): ReactElement {
  return (
    <div className={styles.control}>
      <Input
        value={value}
        onChange={onChange}
        className={styles.answer}
        placeholder="计算结果"
        inputMode="numeric"
        autoComplete="off"
        maxLength={3}
      />
      <div className={styles.imageFrame} aria-live="polite">
        {loading ? (
          <Skeleton.Input active block className={styles.skeleton} />
        ) : challenge ? (
          <img
            src={challenge.image_data_url}
            alt="算术图片验证码"
            draggable={false}
            className={styles.image}
          />
        ) : (
          <span className={styles.error}>{error ?? '加载失败'}</span>
        )}
      </div>
      <Tooltip title="换一张">
        <Button
          type="text"
          icon={<ReloadOutlined spin={loading} />}
          disabled={loading}
          aria-label="刷新验证码"
          className={styles.refresh}
          onClick={onRefresh}
        />
      </Tooltip>
    </div>
  );
}
