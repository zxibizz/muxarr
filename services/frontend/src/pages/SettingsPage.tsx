import {
  Alert,
  Button,
  Card,
  Group,
  Loader,
  NumberInput,
  PasswordInput,
  Select,
  Stack,
  Switch,
  Text,
  TextInput,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { useCallback, useEffect, useState } from 'react';
import { api } from '../api';
import { useAuthGate } from '../auth-context';
import { AiTestButton } from '../components/settings/AiTestButton';
import { SettingsSection } from '../components/settings/SettingsSection';
import type { EditableSettings, ServiceSettings, SettingsField, SettingsPatch } from '../types';

const DEDUPE_OPTIONS = [
  { value: 'language_codec', label: 'By language and codec' },
  { value: 'language', label: 'By language' },
  { value: 'off', label: 'Keep every track' },
];

const AI_MODE_OPTIONS = [
  { value: 'off', label: 'Off' },
  { value: 'fallback', label: 'Fallback — only when the heuristic finds nothing' },
  { value: 'always', label: 'Always' },
  { value: 'verify', label: 'Verify — consult and log, but keep the heuristic answer' },
];

const LOG_LEVELS = ['TRACE', 'DEBUG', 'INFO', 'SUCCESS', 'WARNING', 'ERROR', 'CRITICAL'].map(
  (level) => ({ value: level, label: level }),
);

// Exhaustive by type, so a new setting cannot be added without naming its variable.
const ENV_VARS: Record<SettingsField, string> = {
  dedupe: 'MUXARR_DEDUPE',
  skip_image_subtitles: 'MUXARR_SKIP_IMAGE_SUBTITLES',
  skip_undetermined_language: 'MUXARR_SKIP_UNDETERMINED',
  max_external_tracks: 'MUXARR_MAX_TRACKS',
  sub_charset: 'MUXARR_SUB_CHARSET',
  mux_timeout_seconds: 'MUXARR_MUX_TIMEOUT',
  free_space_factor: 'MUXARR_FREE_SPACE_FACTOR',
  preserve_ownership: 'MUXARR_PRESERVE_OWNERSHIP',
  max_concurrent_muxes: 'MUXARR_MAX_CONCURRENT',
  job_ttl_seconds: 'MUXARR_JOB_TTL',
  history_max_records: 'MUXARR_HISTORY_MAX_RECORDS',
  operation_log_max_entries: 'MUXARR_OPERATION_LOG_MAX_ENTRIES',
  ai_mode: 'MUXARR_AI_MODE',
  ai_base_url: 'MUXARR_AI_BASE_URL',
  ai_model: 'MUXARR_AI_MODEL',
  ai_timeout_seconds: 'MUXARR_AI_TIMEOUT',
  ai_max_entries: 'MUXARR_AI_MAX_ENTRIES',
  log_level: 'MUXARR_LOG_LEVEL',
};

const FIELDS = Object.keys(ENV_VARS) as SettingsField[];

function editableFrom(settings: ServiceSettings): EditableSettings {
  const editable = {} as EditableSettings;
  for (const field of FIELDS) {
    Object.assign(editable, { [field]: settings[field] });
  }
  // Absent on the wire as null, but a controlled input needs a string.
  editable.sub_charset = editable.sub_charset ?? '';
  return editable;
}

export function SettingsPage() {
  const { retryKey, reportError } = useAuthGate();
  const [current, setCurrent] = useState<ServiceSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  // Separate from the form: it is write-only, so there is no value to show.
  const [apiKey, setApiKey] = useState('');

  const form = useForm<EditableSettings>();

  useEffect(() => {
    let cancelled = false;
    api
      .settings()
      .then((loaded) => {
        if (cancelled) return;
        setCurrent(loaded);
        form.setInitialValues(editableFrom(loaded));
        form.setValues(editableFrom(loaded));
        setError(null);
      })
      .catch((caught: unknown) => {
        if (cancelled || reportError(caught)) return;
        setError(caught instanceof Error ? caught.message : String(caught));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [retryKey, reportError]);

  const locked = useCallback(
    (field: SettingsField) => current?.locked.includes(field) ?? false,
    [current],
  );

  const lockProps = useCallback(
    (field: SettingsField) =>
      locked(field)
        ? { disabled: true, description: `Pinned by ${ENV_VARS[field]}` }
        : {},
    [locked],
  );

  const save = useCallback(
    async (values: EditableSettings) => {
      setSaving(true);
      setSaved(false);
      try {
        const patch: SettingsPatch = {};
        for (const field of FIELDS) {
          if (!locked(field)) {
            Object.assign(patch, { [field]: values[field] });
          }
        }
        // Left blank means "leave the stored key alone", not "clear it".
        if (apiKey.trim() && !locked('ai_mode')) {
          patch.ai_api_key = apiKey.trim();
        }

        const updated = await api.updateSettings(patch);
        setCurrent(updated);
        form.setInitialValues(editableFrom(updated));
        form.setValues(editableFrom(updated));
        form.resetDirty();
        setApiKey('');
        setError(null);
        setSaved(true);
      } catch (caught) {
        if (!reportError(caught)) {
          setError(caught instanceof Error ? caught.message : String(caught));
        }
      } finally {
        setSaving(false);
      }
    },
    [apiKey, form, locked, reportError],
  );

  const clearKey = useCallback(async () => {
    try {
      const updated = await api.updateSettings({ ai_api_key: null });
      setCurrent(updated);
      setApiKey('');
    } catch (caught) {
      if (!reportError(caught)) {
        setError(caught instanceof Error ? caught.message : String(caught));
      }
    }
  }, [reportError]);

  if (!current) {
    return (
      <Stack align="center" py="xl">
        {error ? (
          <Alert color="red" title="Could not load settings" w="100%">
            {error}
          </Alert>
        ) : (
          <Loader />
        )}
      </Stack>
    );
  }

  return (
    <form onSubmit={form.onSubmit((values) => void save(values))}>
      <Stack gap="lg" pb="xl">
        {error && (
          <Alert color="red" title="Could not save settings">
            {error}
          </Alert>
        )}
        {saved && !error && (
          <Alert color="green" title="Saved">
            The worker picks these up within a few seconds; no restart needed.
          </Alert>
        )}
        {current.locked.length > 0 && (
          <Alert color="blue" title="Some settings come from the environment">
            {current.locked.map((field) => ENV_VARS[field]).join(', ')} are set in this
            deployment&apos;s environment, so they are managed there rather than here.
          </Alert>
        )}

        <SettingsSection
          title="Track selection"
          description="Which external tracks get embedded, and which are dropped."
        >
          <Select
            label="Duplicate handling"
            data={DEDUPE_OPTIONS}
            allowDeselect={false}
            {...form.getInputProps('dedupe')}
            {...lockProps('dedupe')}
          />
          <NumberInput
            label="Maximum external tracks"
            min={1}
            {...form.getInputProps('max_external_tracks')}
            {...lockProps('max_external_tracks')}
          />
          <TextInput
            label="Subtitle character set"
            placeholder="auto-detect"
            {...form.getInputProps('sub_charset')}
            {...lockProps('sub_charset')}
          />
          <Switch
            label="Skip image subtitles"
            description="Drop VobSub and PGS tracks instead of embedding them."
            {...form.getInputProps('skip_image_subtitles', { type: 'checkbox' })}
            {...lockProps('skip_image_subtitles')}
          />
          <Switch
            label="Skip undetermined languages"
            description="Drop tracks whose language could not be identified."
            {...form.getInputProps('skip_undetermined_language', { type: 'checkbox' })}
            {...lockProps('skip_undetermined_language')}
          />
        </SettingsSection>

        <SettingsSection title="Muxing" description="How the remux itself behaves.">
          <NumberInput
            label="Mux timeout (seconds)"
            min={1}
            {...form.getInputProps('mux_timeout_seconds')}
            {...lockProps('mux_timeout_seconds')}
          />
          <NumberInput
            label="Free space factor"
            description="Multiple of the source size that must be free before muxing."
            min={1}
            step={0.05}
            decimalScale={2}
            {...form.getInputProps('free_space_factor')}
            {...lockProps('free_space_factor')}
          />
          <Switch
            label="Preserve ownership"
            description="Copy the source file's owner and group onto the output."
            {...form.getInputProps('preserve_ownership', { type: 'checkbox' })}
            {...lockProps('preserve_ownership')}
          />
        </SettingsSection>

        <SettingsSection
          title="Queue and retention"
          description="How much work runs at once, and how long records are kept."
        >
          <NumberInput
            label="Concurrent muxes"
            description="Two remuxes on one disk are usually slower than one at a time."
            min={1}
            {...form.getInputProps('max_concurrent_muxes')}
            {...lockProps('max_concurrent_muxes')}
          />
          <NumberInput
            label="Job retention (seconds)"
            description="A finished job must outlast any plausible gap in the shim's polling."
            min={60}
            {...form.getInputProps('job_ttl_seconds')}
            {...lockProps('job_ttl_seconds')}
          />
          <NumberInput
            label="History records kept"
            min={1}
            {...form.getInputProps('history_max_records')}
            {...lockProps('history_max_records')}
          />
          <NumberInput
            label="Log lines kept per import"
            description="The explanation shown on a history entry. 0 records none."
            min={0}
            max={5000}
            {...form.getInputProps('operation_log_max_entries')}
            {...lockProps('operation_log_max_entries')}
          />
        </SettingsSection>

        <SettingsSection
          title="AI track discovery"
          description="Optional. Enabling this sends release folder and file names to the provider."
        >
          <Select
            label="Mode"
            data={AI_MODE_OPTIONS}
            allowDeselect={false}
            {...form.getInputProps('ai_mode')}
            {...lockProps('ai_mode')}
          />
          <TextInput
            label="Base URL"
            placeholder="https://api.openai.com/v1"
            {...form.getInputProps('ai_base_url')}
            {...lockProps('ai_base_url')}
          />
          <TextInput
            label="Model"
            placeholder="gpt-4o-mini"
            {...form.getInputProps('ai_model')}
            {...lockProps('ai_model')}
          />
          <Group align="flex-end" gap="sm" wrap="nowrap">
            <PasswordInput
              style={{ flex: 1 }}
              label="API key"
              placeholder={current.ai_api_key_set ? 'a key is stored' : 'not set'}
              description="Write-only. Leave blank to keep the stored key."
              value={apiKey}
              onChange={(event) => setApiKey(event.currentTarget.value)}
              disabled={locked('ai_mode')}
            />
            {current.ai_api_key_set && (
              <Button
                variant="subtle"
                color="red"
                onClick={() => void clearKey()}
                disabled={locked('ai_mode')}
              >
                Clear
              </Button>
            )}
          </Group>
          <NumberInput
            label="Request timeout (seconds)"
            min={1}
            {...form.getInputProps('ai_timeout_seconds')}
            {...lockProps('ai_timeout_seconds')}
          />
          <NumberInput
            label="Maximum candidate files"
            description="Above this, a release is handled by the heuristic alone."
            min={1}
            {...form.getInputProps('ai_max_entries')}
            {...lockProps('ai_max_entries')}
          />
          <AiTestButton form={form} apiKey={apiKey} keyStored={current.ai_api_key_set} />
        </SettingsSection>

        <SettingsSection title="Logging">
          <Select
            label="Level"
            data={LOG_LEVELS}
            allowDeselect={false}
            {...form.getInputProps('log_level')}
            {...lockProps('log_level')}
          />
        </SettingsSection>

        <Card withBorder padding="md">
          <Group justify="space-between">
            <Text size="sm" c="dimmed">
              Changes apply to the next import. Nothing needs restarting.
            </Text>
            <Group gap="sm">
              <Button
                variant="default"
                onClick={() => {
                  form.reset();
                  setApiKey('');
                }}
                disabled={saving}
              >
                Reset
              </Button>
              <Button type="submit" loading={saving}>
                Save settings
              </Button>
            </Group>
          </Group>
        </Card>
      </Stack>
    </form>
  );
}
