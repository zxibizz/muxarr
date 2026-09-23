import { createContext, useContext } from 'react';

export interface AuthGate {
  needsToken: boolean;
  submitToken: (token: string) => void;
}

export const AuthGateContext = createContext<AuthGate | null>(null);

export function useAuthGate(): AuthGate {
  const value = useContext(AuthGateContext);
  if (!value) {
    throw new Error('useAuthGate must be used inside AppProviders');
  }
  return value;
}
