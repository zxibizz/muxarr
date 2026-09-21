import { Button, Group, Select, TextInput } from '@mantine/core';
import type { HistoryFilters, MoveStatus } from '../types';

interface Props {
  filters: HistoryFilters;
  onChange: (next: HistoryFilters) => void;
  onClearHistory: () => void;
  busy: boolean;
}

const STATUS_OPTIONS = [
  { value: 'RenameRequested', label: 'Muxed' },
  { value: 'DeferMove', label: 'Skipped' },
  { value: 'MoveComplete', label: 'Move complete' },
];

const APP_OPTIONS = [
  { value: 'radarr', label: 'Radarr' },
  { value: 'sonarr', label: 'Sonarr' },
];

export function Filters({ filters, onChange, onClearHistory, busy }: Props) {
  return (
    <Group gap="sm" align="flex-end" wrap="wrap">
      <TextInput
        label="Search"
        placeholder="Title, path or reason"
        value={filters.query}
        onChange={(event) => onChange({ ...filters, query: event.currentTarget.value })}
        w={260}
      />
      <Select
        label="Result"
        placeholder="Any"
        data={STATUS_OPTIONS}
        value={filters.status}
        onChange={(value) => onChange({ ...filters, status: value as MoveStatus | null })}
        clearable
        w={170}
      />
      <Select
        label="Source"
        placeholder="Any"
        data={APP_OPTIONS}
        value={filters.app}
        onChange={(value) => onChange({ ...filters, app: value })}
        clearable
        w={150}
      />
      <Button variant="default" onClick={onClearHistory} disabled={busy} ml="auto">
        Clear history
      </Button>
    </Group>
  );
}
