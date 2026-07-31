import type { ChangeEvent, ReactElement } from 'react';
import { ReloadOutlined } from '@ant-design/icons';
import { Button, Input, Skeleton, Tooltip } from 'antd';
import type { CaptchaChallenge } from '@/api/auth-api';
import styles from './index.module.css';

export type ArithmeticCaptchaTone = 'default' | 'light' | 'lightCompact';

interface ArithmeticCaptchaInputProps {
  value?: string;
  onChange?: (event: ChangeEvent<HTMLInputElement>) => void;
  challenge: CaptchaChallenge | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  /** 视觉变体：登录用 light，注册用 lightCompact */
  tone?: ArithmeticCaptchaTone;
}

/** 拼接条件类名，过滤 falsy 值。 */
function cx(...classes: (string | false | undefined)[]): string {
  return classes.filter(Boolean).join(' ');
}

/** 数字答案输入框与可刷新算术图片验证码。 */
export default function ArithmeticCaptchaInput({
  value,
  onChange,
  challenge,
  loading,
  error,
  onRefresh,
  tone = 'default',
}: ArithmeticCaptchaInputProps): ReactElement {
  const isLight = tone === 'light' || tone === 'lightCompact';
  const isCompact = tone === 'lightCompact';

  const controlClass = cx(
    styles.control,
    isLight && styles.controlLight,
    isCompact && styles.controlLightCompact,
  );

  const answerClass = cx(
    isLight ? styles.answerLight : styles.answer,
    isCompact && styles.answerLightCompact,
  );

  const imageFrameClass = cx(
    styles.imageFrame,
    isLight && styles.imageFrameLight,
    isCompact && styles.imageFrameLightCompact,
  );

  const refreshClass = cx(
    isLight ? styles.refreshLight : styles.refresh,
    isCompact && styles.refreshLightCompact,
  );

  return (
    <div className={controlClass}>
      <Input
        value={value}
        onChange={onChange}
        className={answerClass}
        placeholder="计算结果"
        inputMode="numeric"
        autoComplete="off"
        maxLength={3}
        size="large"
      />
      <button
        type="button"
        className={imageFrameClass}
        aria-label="点击更换验证码"
        aria-live="polite"
        title="点击更换验证码"
        disabled={loading}
        onClick={onRefresh}
      >
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
      </button>
      <Tooltip title="换一张">
        <Button
          type="text"
          icon={<ReloadOutlined spin={loading} />}
          disabled={loading}
          aria-label="刷新验证码"
          className={refreshClass}
          onClick={onRefresh}
        />
      </Tooltip>
    </div>
  );
}
