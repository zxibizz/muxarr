import { Alert, Group, Pagination, Stack } from '@mantine/core';
import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { useAuthGate } from '../auth-context';
import { ActiveJobs } from '../components/ActiveJobs';
import { Filters } from '../components/Filters';
import { HistoryTable } from '../components/HistoryTable';
import { JobDetail } from '../components/JobDetail';
import { OperationDetail } from '../components/OperationDetail';
import { StatsCards } from '../components/StatsCards';
import type { HistoryFilters, Job, Operation, Stats } from '../types';

const PAGE_SIZE = 25;
const POLL_INTERVAL_MS = 10_000;
// The newest jobs are the unfinished ones; anything older has a history row.
const JOB_WINDOW = 20;

export function HistoryPage() {
  const { needsToken, retryKey, reportError } = useAuthGate();
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
  const [unsettled, setUnsettled] = useState<Job[]>([]);
  const [watched, setWatched] = useState<Job | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Kept in a ref so the polling effect does not restart on every keystroke.
  const requestRef = useRef({ filters, page });
  requestRef.current = { filters, page };

  const refresh = useCallback(async () => {
    const { filters: active, page: activePage } = requestRef.current;
    try {
      const [historyPage, nextStats, jobs] = await Promise.all([
        api.history(active, PAGE_SIZE, (activePage - 1) * PAGE_SIZE),
        api.stats(),
        api.jobs(undefined, JOB_WINDOW),
      ]);
      setOperations(historyPage.items);
      setTotal(historyPage.total);
      setStats(nextStats);
      setUnsettled(jobs.items.filter((job) => job.state !== 'succeeded'));
      setError(null);
    } catch (caught) {
      if (!reportError(caught)) {
        setError(caught instanceof Error ? caught.message : String(caught));
      }
    } finally {
      setLoading(false);
    }
  }, [reportError]);

  useEffect(() => {
    setLoading(true);
    void refresh();
  }, [filters, page, refresh, retryKey]);

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
    <Stack gap="lg">
      <StatsCards stats={stats} />

      <ActiveJobs jobs={unsettled} onSelect={setWatched} />

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

      <HistoryTable operations={operations} loading={loading} onSelect={setSelected} />

      {pageCount > 1 && (
        <Group justify="center">
          <Pagination value={page} onChange={setPage} total={pageCount} />
        </Group>
      )}

      <OperationDetail operation={selected} onClose={() => setSelected(null)} />
      <JobDetail job={watched} onClose={() => setWatched(null)} />
    </Stack>
  );
}
