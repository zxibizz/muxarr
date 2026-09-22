import { createContext, useContext } from 'react';

export interface AuthGate {
  needsToken: boolean;
  /** Bumped when a token is accepted, so pages re-run their loads. */
  retryKey: number;
  /** Returns true when the failure was a missing token and has been handled. */
  reportError: (caught: unknown) => boolean;
  submitToken: (token: string) => void;
}

export const AuthGateContext = createContext<AuthGate | null>(null);

export function useAuthGate(): AuthGate {
  const value = useContext(AuthGateContext);
  if (!value) {
    throw new Error('useAuthGate must be used inside an AuthGateProvider');
  }
  return value;
}
