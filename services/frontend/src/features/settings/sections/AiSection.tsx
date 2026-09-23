import { Box, Button, Group, NumberInput, PasswordInput, Select, Switch, TextInput } from '@mantine/core';
import { AiTestButton } from '../AiTestButton';
import { AI_MODE_OPTIONS } from '../fields';
import { SettingRow, SettingsSection } from '../SettingsSection';
import type { SettingsFormApi } from '../useSettingsForm';

interface Props extends SettingsFormApi {
  apiKey: string;
  onApiKeyChange: (value: string) => void;
  keyStored: boolean;
  onClearKey: () => void;
}

export function AiSection({ form, field, bind, apiKey, onApiKeyChange, keyStored, onClearKey }: Props) {
  const keyBinding = field('ai_api_key');

  return (
    <SettingsSection
      id="ai"
      title="AI track discovery"
      description="Optional. When enabled, release folder and file names are sent to the provider."
    >
      <SettingRow
        binding={field('ai_mode')}
        label="Mode"
        description="How much of sidecar discovery the provider may decide."
      >
        <Select data={AI_MODE_OPTIONS} allowDeselect={false} {...bind('ai_mode')} />
      </SettingRow>
      <SettingRow
        binding={field('ai_base_url')}
        label="Base URL"
        description="Any OpenAI-compatible chat completions endpoint."
      >
        <TextInput placeholder="https://api.openai.com/v1" {...bind('ai_base_url')} />
      </SettingRow>
      <SettingRow binding={field('ai_model')} label="Model">
        <TextInput placeholder="gpt-4o-mini" {...bind('ai_model')} />
      </SettingRow>
      <SettingRow
        binding={keyBinding}
        label="API key"
        description="Write-only. Leave blank to keep the stored key."
      >
        <Group gap="xs" wrap="nowrap">
          <PasswordInput
            id={keyBinding.id}
            style={{ flex: 1 }}
            placeholder={keyStored ? 'a key is stored' : 'not set'}
            value={apiKey}
            onChange={(event) => onApiKeyChange(event.currentTarget.value)}
            disabled={keyBinding.locked}
          />
          {keyStored && (
            <Button variant="subtle" color="red" onClick={onClearKey} disabled={keyBinding.locked}>
              Clear
            </Button>
          )}
        </Group>
      </SettingRow>
      <SettingRow binding={field('ai_timeout_seconds')} label="Request timeout">
        <NumberInput min={1} suffix=" s" {...bind('ai_timeout_seconds')} />
      </SettingRow>
      <SettingRow
        binding={field('ai_max_entries')}
        label="Maximum candidate files"
        description="Above this, a release is handled by the filename heuristic alone."
      >
        <NumberInput min={1} {...bind('ai_max_entries')} />
      </SettingRow>
      <SettingRow
        binding={field('ai_name_tracks')}
        label="Let the provider name the tracks"
        description="Asks on every import, even when the filenames were conclusive, and uses the provider's label as the track name. Selection stays with the filenames. Ignored in verify mode."
        inline
      >
        <Switch {...bind('ai_name_tracks', { type: 'checkbox' })} />
      </SettingRow>
      <Box py="md">
        <AiTestButton values={form.values} apiKey={apiKey} keyStored={keyStored} />
      </Box>
    </SettingsSection>
  );
}
