import {
  ActionIcon,
  Button,
  Group,
  Menu,
  Modal,
  SegmentedControl,
  Select,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconDots, IconSearch, IconTrash } from '@tabler/icons-react';
import type { App, HistoryFilters, MoveStatus } from '../../api/types';

type StatusFilter = MoveStatus | 'all';

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'RenameRequested', label: 'Muxed' },
  { value: 'DeferMove', label: 'Skipped' },
];

const APP_OPTIONS: { value: App; label: string }[] = [
  { value: 'radarr', label: 'Radarr' },
  { value: 'sonarr', label: 'Sonarr' },
];

interface Props {
  filters: HistoryFilters;
  onChange: (next: HistoryFilters) => void;
  onClearHistory: () => Promise<unknown>;
  clearing: boolean;
}

export function HistoryToolbar({ filters, onChange, onClearHistory, clearing }: Props) {
  const [confirming, confirm] = useDisclosure(false);

  return (
    <Group gap="sm" wrap="wrap">
      <TextInput
        aria-label="Search history"
        placeholder="Search title, path or reason"
        leftSection={<IconSearch size={16} />}
        value={filters.query}
        onChange={(event) => onChange({ ...filters, query: event.currentTarget.value })}
        style={{ flex: '1 1 240px' }}
        maw={360}
      />
      <SegmentedControl<StatusFilter>
        aria-label="Result"
        data={STATUS_OPTIONS}
        value={filters.status ?? 'all'}
        onChange={(value) => onChange({ ...filters, status: value === 'all' ? null : value })}
      />
      <Select<App>
        aria-label="Source"
        placeholder="All sources"
        data={APP_OPTIONS}
        value={filters.app}
        onChange={(value) => onChange({ ...filters, app: value })}
        clearable
        w={160}
      />

      <Menu position="bottom-end" withinPortal>
        <Menu.Target>
          <ActionIcon variant="subtle" color="gray" size="lg" ml="auto" aria-label="History actions">
            <IconDots size={18} />
          </ActionIcon>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item color="red" leftSection={<IconTrash size={16} />} onClick={confirm.open}>
            Clear history
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>

      <Modal opened={confirming} onClose={confirm.close} title="Clear the history?">
        <Stack gap="lg">
          <Text size="sm" c="dimmed">
            Every recorded operation and its log is deleted. Imports themselves are not touched,
            and this cannot be undone.
          </Text>
          <Group justify="flex-end" gap="sm">
            <Button variant="default" onClick={confirm.close}>
              Cancel
            </Button>
            <Button
              color="red"
              loading={clearing}
              onClick={() => void onClearHistory().then(confirm.close)}
            >
              Delete everything
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Group>
  );
}
