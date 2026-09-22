import { useCallback, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { ApiError, setToken } from './api';
import { AuthGateContext } from './auth-context';

/**
 * One place decides that a 401 means "prompt for a token".
 * Every page would otherwise repeat the check, and miss it on new endpoints.
 */
export function AuthGateProvider({ children }: { children: ReactNode }) {
  const [needsToken, setNeedsToken] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  const reportError = useCallback((caught: unknown) => {
    const unauthorised = caught instanceof ApiError && caught.unauthorised;
    if (unauthorised) {
      setNeedsToken(true);
    }
    return unauthorised;
  }, []);

  const submitToken = useCallback((token: string) => {
    setToken(token);
    setNeedsToken(false);
    setRetryKey((key) => key + 1);
  }, []);

  const value = useMemo(
    () => ({ needsToken, retryKey, reportError, submitToken }),
    [needsToken, retryKey, reportError, submitToken],
  );

  return <AuthGateContext.Provider value={value}>{children}</AuthGateContext.Provider>;
}
