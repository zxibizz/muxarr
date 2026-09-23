import { Alert, Button, Group, Text } from '@mantine/core';
import { IconPlugConnected } from '@tabler/icons-react';
import { describeError } from '../../api/client';
import { useTestAi } from '../../api/queries';
import type { EditableSettings } from '../../api/types';

interface Props {
  values: Pick<EditableSettings, 'ai_base_url' | 'ai_model' | 'ai_timeout_seconds'>;
  /** Typed but not yet saved; blank means the daemon should use the stored key. */
  apiKey: string;
  keyStored: boolean;
}

export function AiTestButton({ values, apiKey, keyStored }: Props) {
  const probe = useTestAi();
  const { ai_base_url: baseUrl, ai_model: model, ai_timeout_seconds: timeout } = values;
  const ready = Boolean(baseUrl.trim() && model.trim() && (apiKey.trim() || keyStored));

  const run = () =>
    probe.mutate({
      base_url: baseUrl,
      model,
      api_key: apiKey.trim() || undefined,
      timeout_seconds: timeout,
    });

  const result = probe.data;
  const failure = describeError(probe.error);

  return (
    <div>
      <Group gap="sm">
        <Button
          variant="light"
          leftSection={<IconPlugConnected size={16} />}
          onClick={run}
          loading={probe.isPending}
          disabled={!ready}
        >
          Test provider
        </Button>
        {!ready && (
          <Text size="xs" c="dimmed">
            Fill in the base URL, model and key first.
          </Text>
        )}
      </Group>

      {(result || failure) && (
        <Alert
          mt="sm"
          color={result?.ok ? 'teal' : 'red'}
          title={result?.ok ? 'Provider reachable' : 'Provider test failed'}
        >
          {result ? result.message : failure}
          {result?.ok && ` (${result.latency_ms} ms)`}
        </Alert>
      )}
    </div>
  );
}
