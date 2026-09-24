import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import type { ReactNode } from 'react';
import { isUnauthorised } from '../api/client';
import { keys } from '../api/queries';

/**
 * Owns the query client so one place decides that a 401 means "sign in again".
 * Every page would otherwise repeat the check, and miss it on new endpoints.
 */
export function AppProviders({ children }: { children: ReactNode }) {
  const [client] = useState(() => {
    // Re-reading the status is what sends AuthGate to the login page.
    const onError = (error: unknown) => {
      if (isUnauthorised(error)) void client.invalidateQueries({ queryKey: keys.auth });
    };
    const client = new QueryClient({
      queryCache: new QueryCache({ onError }),
      mutationCache: new MutationCache({ onError }),
      defaultOptions: {
        // Polling is the retry: a failed dashboard read is simply tried again next tick.
        queries: { retry: false, refetchOnWindowFocus: false },
      },
    });
    return client;
  });

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
