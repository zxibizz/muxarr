import { Alert, Button, Group, Text } from '@mantine/core';
import type { UseFormReturnType } from '@mantine/form';
import { useCallback, useState } from 'react';
import { api } from '../../api';
import type { AiTestResult, EditableSettings } from '../../types';

interface Props {
  form: UseFormReturnType<EditableSettings>;
  /** Typed but not yet saved; blank means the daemon should use the stored key. */
  apiKey: string;
  keyStored: boolean;
}

export function AiTestButton({ form, apiKey, keyStored }: Props) {
  const [result, setResult] = useState<AiTestResult | null>(null);
  const [busy, setBusy] = useState(false);

  const { ai_base_url: baseUrl, ai_model: model, ai_timeout_seconds: timeout } = form.values;
  const ready = Boolean(baseUrl?.trim() && model?.trim() && (apiKey.trim() || keyStored));

  const run = useCallback(async () => {
    setBusy(true);
    setResult(null);
    try {
      setResult(
        await api.testAi({
          base_url: baseUrl,
          model,
          api_key: apiKey.trim() || undefined,
          timeout_seconds: timeout,
        }),
      );
    } catch (caught) {
      setResult({
        ok: false,
        message: caught instanceof Error ? caught.message : String(caught),
        latency_ms: 0,
      });
    } finally {
      setBusy(false);
    }
  }, [apiKey, baseUrl, model, timeout]);

  return (
    <div>
      <Group gap="sm">
        <Button
          variant="light"
          onClick={() => void run()}
          loading={busy}
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

      {result && (
        <Alert
          mt="sm"
          color={result.ok ? 'green' : 'red'}
          title={result.ok ? 'Provider reachable' : 'Provider test failed'}
        >
          {result.message}
          {result.ok && ` (${result.latency_ms} ms)`}
        </Alert>
      )}
    </div>
  );
}
