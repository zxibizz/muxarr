import { Alert, Box, Card, Divider, Group, Pagination, Stack, Text } from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { IconAlertTriangle } from '@tabler/icons-react';
import { useState } from 'react';
import { describeError } from '../../api/client';
import { HISTORY_PAGE_SIZE, useClearHistory, useHistory } from '../../api/queries';
import type { HistoryFilters, Operation } from '../../api/types';
import { PageHeader } from '../../components/PageHeader';
import { ActiveJobs } from './ActiveJobs';
import { HistoryTable } from './HistoryTable';
import { HistoryToolbar } from './HistoryToolbar';
import { JobDrawer } from './JobDrawer';
import { OperationDrawer } from './OperationDrawer';
import { StatsRow } from './StatsRow';

const NO_FILTERS: HistoryFilters = { status: null, app: null, query: '' };

export function HistoryPage() {
  const [filters, setFilters] = useState<HistoryFilters>(NO_FILTERS);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Operation | null>(null);
  const [watched, setWatched] = useState<string | null>(null);

  // Typing should not fire a request per keystroke.
  const [query] = useDebouncedValue(filters.query, 250);
  const history = useHistory({ ...filters, query }, page);
  const clear = useClearHistory();

  const total = history.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / HISTORY_PAGE_SIZE));
  const error = describeError(history.error);
  const filtered = filters.status !== null || filters.app !== null || query.trim() !== '';

  return (
    <Stack gap="xl">
      <PageHeader
        title="History"
        description="Every import Radarr and Sonarr handed to muxarr, including the ones it left alone."
      />

      <StatsRow />

      <ActiveJobs onSelect={setWatched} />

      {error && (
        <Alert color="red" icon={<IconAlertTriangle size={18} />} title="Could not load history">
          {error}
        </Alert>
      )}

      <Card padding={0}>
        <Stack gap={0}>
          <Box p="md">
            <HistoryToolbar
              filters={filters}
              onChange={(next) => {
                setFilters(next);
                setPage(1);
              }}
              onClearHistory={async () => {
                await clear.mutateAsync();
                setPage(1);
              }}
              clearing={clear.isPending}
            />
          </Box>
          <Divider />
          <HistoryTable
            operations={history.data?.items ?? []}
            loading={history.isPending}
            filtered={filtered}
            onSelect={setSelected}
          />
          {total > 0 && (
            <>
              <Divider />
              <Group justify="space-between" px="md" py="sm">
                <Text size="xs" c="dimmed">
                  {total.toLocaleString()} {total === 1 ? 'operation' : 'operations'}
                </Text>
                {pageCount > 1 && (
                  <Pagination value={page} onChange={setPage} total={pageCount} size="sm" />
                )}
              </Group>
            </>
          )}
        </Stack>
      </Card>

      <OperationDrawer operation={selected} onClose={() => setSelected(null)} />
      <JobDrawer jobId={watched} onClose={() => setWatched(null)} />
    </Stack>
  );
}
