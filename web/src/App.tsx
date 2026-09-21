import {
  Alert,
  AppShell,
  Badge,
  Container,
  Group,
  Pagination,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, api, setToken } from './api';
import { Filters } from './components/Filters';
import { HistoryTable } from './components/HistoryTable';
import { OperationDetail } from './components/OperationDetail';
import { StatsCards } from './components/StatsCards';
import { TokenPrompt } from './components/TokenPrompt';
import type { Health, HistoryFilters, Operation, Stats } from './types';

const PAGE_SIZE = 25;
const POLL_INTERVAL_MS = 10_000;

export function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [operations, setOperations] = useState<Operation[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<HistoryFilters>({
    status: null,
    app: null,
    query: '',
  });
  const [selected, setSelected] = useState<Operation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [needsToken, setNeedsToken] = useState(false);

  // Kept in a ref so the polling effect does not restart on every keystroke.
  const requestRef = useRef({ filters, page });
  requestRef.current = { filters, page };

  const refresh = useCallback(async () => {
    const { filters: active, page: activePage } = requestRef.current;
    try {
      const [historyPage, nextStats] = await Promise.all([
        api.history(active, PAGE_SIZE, (activePage - 1) * PAGE_SIZE),
        api.stats(),
      ]);
      setOperations(historyPage.items);
      setTotal(historyPage.total);
      setStats(nextStats);
      setError(null);
      setNeedsToken(false);
    } catch (caught) {
      if (caught instanceof ApiError && caught.unauthorised) {
        setNeedsToken(true);
      } else {
        setError(caught instanceof Error ? caught.message : String(caught));
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    api.health().then(setHealth).catch(() => undefined);
  }, []);

  useEffect(() => {
    setLoading(true);
    void refresh();
  }, [filters, page, refresh]);

  useEffect(() => {
    if (needsToken) return undefined;
    const timer = window.setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [needsToken, refresh]);

  const handleClearHistory = useCallback(async () => {
    if (!window.confirm('Delete every recorded operation? This cannot be undone.')) {
      return;
    }
    try {
      await api.clearHistory();
      setPage(1);
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }, [refresh]);

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <AppShell header={{ height: 60 }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="sm">
            <Title order={3}>muxarr</Title>
            <Text size="sm" c="dimmed">
              import history
            </Text>
          </Group>
          {health && (
            <Group gap="xs">
              <Badge color="yellow" variant="light">
                history not persisted
              </Badge>
              <Text size="xs" c="dimmed">
                v{health.version}
              </Text>
            </Group>
          )}
        </Group>
      </AppShell.Header>

      <AppShell.Main>
        <Container size="xl">
          <Stack gap="lg">
            <StatsCards stats={stats} />

            <Alert color="yellow" title="History is in memory">
              Everything here is lost when the container restarts.
            </Alert>

            {error && (
              <Alert color="red" title="Could not load history">
                {error}
              </Alert>
            )}

            <Filters
              filters={filters}
              onChange={(next) => {
                setFilters(next);
                setPage(1);
              }}
              onClearHistory={() => void handleClearHistory()}
              busy={loading}
            />

            <HistoryTable
              operations={operations}
              loading={loading}
              onSelect={setSelected}
            />

            {pageCount > 1 && (
              <Group justify="center">
                <Pagination value={page} onChange={setPage} total={pageCount} />
              </Group>
            )}
          </Stack>
        </Container>
      </AppShell.Main>

      <OperationDetail operation={selected} onClose={() => setSelected(null)} />

      <TokenPrompt
        opened={needsToken}
        onSubmit={(token) => {
          setToken(token);
          setLoading(true);
          void refresh();
        }}
      />
    </AppShell>
  );
}
