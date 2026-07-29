import { useCallback, useEffect, useState } from 'react';
import { getCaptcha, type CaptchaChallenge } from '@/api/auth-api';
import { getRequestErrorMessage } from '@/utils/request';

interface ArithmeticCaptchaState {
  challenge: CaptchaChallenge | null;
  loading: boolean;
  error: string | null;
  refreshCaptcha: () => Promise<void>;
}

/** 管理登录与注册页共用的一次性算术验证码。 */
export function useArithmeticCaptcha(): ArithmeticCaptchaState {
  const [challenge, setChallenge] = useState<CaptchaChallenge | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const refreshCaptcha = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      setChallenge(await getCaptcha());
    } catch (requestError) {
      setChallenge(null);
      setError(getRequestErrorMessage(requestError, '验证码加载失败'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void refreshCaptcha();
    }, 0);
    return () => window.clearTimeout(timeoutId);
  }, [refreshCaptcha]);

  return { challenge, loading, error, refreshCaptcha };
}
