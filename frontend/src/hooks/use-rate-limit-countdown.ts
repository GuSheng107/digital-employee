import { useEffect, useState } from 'react';

/** 使用服务端返回秒数驱动认证按钮倒计时。 */
export function useRateLimitCountdown(): {
  remainingSeconds: number;
  startCountdown: (seconds: number) => void;
} {
  const [remainingSeconds, setRemainingSeconds] = useState(0);

  useEffect(() => {
    if (remainingSeconds <= 0) return undefined;
    const timerId = window.setInterval(() => {
      setRemainingSeconds((current) => Math.max(0, current - 1));
    }, 1000);
    return () => window.clearInterval(timerId);
  }, [remainingSeconds]);

  return {
    remainingSeconds,
    startCountdown: (seconds: number) => {
      setRemainingSeconds(Math.max(1, Math.ceil(seconds)));
    },
  };
}
