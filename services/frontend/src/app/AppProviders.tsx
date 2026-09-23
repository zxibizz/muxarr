import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useCallback, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { isUnauthorised, setToken } from '../api/client';
import { AuthGateContext } from './auth-context';

/**
 * Owns the query client so one place decides that a 401 means "prompt for a token".
 * Every page would otherwise repeat the check, and miss it on new endpoints.
 */
export function AppProviders({ children }: { children: ReactNode }) {
  const [needsToken, setNeedsToken] = useState(false);

  const [client] = useState(() => {
    const onError = (error: unknown) => {
      if (isUnauthorised(error)) setNeedsToken(true);
    };
    return new QueryClient({
      queryCache: new QueryCache({ onError }),
      mutationCache: new MutationCache({ onError }),
      defaultOptions: {
        // Polling is the retry: a failed dashboard read is simply tried again next tick.
        queries: { retry: false, refetchOnWindowFocus: false },
      },
    });
  });

  const submitToken = useCallback(
    (token: string) => {
      setToken(token);
      setNeedsToken(false);
      void client.invalidateQueries();
    },
    [client],
  );

  const gate = useMemo(() => ({ needsToken, submitToken }), [needsToken, submitToken]);

  return (
    <QueryClientProvider client={client}>
      <AuthGateContext.Provider value={gate}>{children}</AuthGateContext.Provider>
    </QueryClientProvider>
  );
}
