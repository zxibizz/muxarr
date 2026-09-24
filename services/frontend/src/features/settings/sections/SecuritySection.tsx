import {
  Alert,
  Button,
  Code,
  CopyButton,
  Group,
  Modal,
  PasswordInput,
  Select,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { IconAlertTriangle, IconCheck, IconCopy, IconRefresh } from '@tabler/icons-react';
import { useState } from 'react';
import {
  useApiKey,
  useAuthStatus,
  useChangeCredentials,
  useRegenerateApiKey,
} from '../../../api/queries';
import { AUTH_METHOD_OPTIONS, AUTH_REQUIRED_OPTIONS } from '../fields';
import { SettingRow, SettingsSection } from '../SettingsSection';
import type { SettingsFormApi } from '../useSettingsForm';

function ApiKeySection() {
  const apiKey = useApiKey();
  const regenerate = useRegenerateApiKey();
  const [confirming, { open, close }] = useDisclosure(false);
  const binding = {
    id: 'setting-api_key',
    envVar: 'MUXARR_API_KEY',
    locked: apiKey.data?.locked ?? false,
  };

  return (
    <SettingsSection
      title="API key"
      description="What Radarr and Sonarr present. Set it as MUXARR_API_KEY in their containers."
    >
      <SettingRow binding={binding} label="Key">
        <Group gap="xs" wrap="nowrap">
          <TextInput
            id={binding.id}
            style={{ flex: 1 }}
            value={apiKey.data?.api_key ?? ''}
            readOnly
            ff="monospace"
          />
          <CopyButton value={apiKey.data?.api_key ?? ''}>
            {({ copied, copy }) => (
              <Button
                variant="default"
                onClick={copy}
                aria-label="Copy API key"
                disabled={!apiKey.data}
              >
                {copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
              </Button>
            )}
          </CopyButton>
          {!binding.locked && (
            <Button
              variant="default"
              color="red"
              onClick={open}
              aria-label="Regenerate API key"
              disabled={!apiKey.data}
            >
              <IconRefresh size={16} />
            </Button>
          )}
        </Group>
      </SettingRow>

      <Modal opened={confirming} onClose={close} title="Regenerate the API key?">
        <Stack gap="md">
          <Text size="sm">
            The current key stops working immediately. Imports fail over to a plain Radarr/Sonarr
            import until their <Code>MUXARR_API_KEY</Code> is updated.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>
              Cancel
            </Button>
            <Button
              color="red"
              loading={regenerate.isPending}
              onClick={() =>
                regenerate.mutate(undefined, {
                  onSuccess: () => {
                    close();
                    notifications.show({
                      color: 'teal',
                      title: 'API key regenerated',
                      message: 'Copy the new key into Radarr and Sonarr.',
                    });
                  },
                })
              }
            >
              Regenerate
            </Button>
          </Group>
        </Stack>
      </Modal>
    </SettingsSection>
  );
}

function LoginSection() {
  const status = useAuthStatus();
  const change = useChangeCredentials();
  const [current, setCurrent] = useState('');
  const [username, setUsername] = useState<string | null>(null);
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');

  const locked = status.data?.credentials_locked ?? false;
  const name = username ?? status.data?.username ?? '';
  const mismatch = confirm.length > 0 && confirm !== password;
  const ready = current !== '' && name.trim() !== '' && password !== '' && confirm === password;
  const binding = (id: string) => ({
    id: `setting-${id}`,
    envVar: 'MUXARR_USERNAME / MUXARR_PASSWORD',
    locked,
  });

  // Not a <form>: the settings page already wraps every section in one.
  const submit = () =>
    change.mutate(
      { current_password: current, username: name.trim(), password },
      {
        onSuccess: () => {
          setCurrent('');
          setPassword('');
          setConfirm('');
          setUsername(null);
          notifications.show({
            color: 'teal',
            title: 'Login changed',
            message: 'Every other browser has been signed out.',
          });
        },
      },
    );

  return (
    <SettingsSection title="Login" description="The account that signs in to this UI.">
      {change.error && (
        <Alert color="red" icon={<IconAlertTriangle size={18} />} mt="md">
          {change.error.message}
        </Alert>
      )}
      <SettingRow binding={binding('username')} label="Username">
        <TextInput
          id="setting-username"
          autoComplete="username"
          value={name}
          onChange={(event) => setUsername(event.currentTarget.value)}
          disabled={locked}
        />
      </SettingRow>
      <SettingRow binding={{ ...binding('new_password'), locked: false }} label="New password">
        <PasswordInput
          id="setting-new_password"
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.currentTarget.value)}
          disabled={locked}
        />
      </SettingRow>
      <SettingRow binding={{ ...binding('confirm_password'), locked: false }} label="Confirm">
        <PasswordInput
          id="setting-confirm_password"
          autoComplete="new-password"
          value={confirm}
          onChange={(event) => setConfirm(event.currentTarget.value)}
          error={mismatch ? 'The passwords do not match' : undefined}
          disabled={locked}
        />
      </SettingRow>
      <SettingRow
        binding={{ ...binding('current_password'), locked: false }}
        label="Current password"
        description="Required to change either."
      >
        <Group gap="xs" wrap="nowrap">
          <PasswordInput
            id="setting-current_password"
            style={{ flex: 1 }}
            autoComplete="current-password"
            value={current}
            onChange={(event) => setCurrent(event.currentTarget.value)}
            disabled={locked}
          />
          <Button onClick={submit} loading={change.isPending} disabled={locked || !ready}>
            Change
          </Button>
        </Group>
      </SettingRow>
    </SettingsSection>
  );
}

export function SecuritySection({ field, bind }: SettingsFormApi) {
  return (
    <Stack gap="lg">
      <SettingsSection title="Authentication">
        <SettingRow
          binding={field('auth_method')}
          label="Method"
          description="External trusts a proxy in front of Muxarr, and leaves the UI and API open to anything that reaches this port directly."
        >
          <Select data={AUTH_METHOD_OPTIONS} allowDeselect={false} {...bind('auth_method')} />
        </SettingRow>
        <SettingRow
          binding={field('auth_required')}
          label="Required"
          description="Local addresses include the Docker networks, and anything forwarded by a reverse proxy on one."
        >
          <Select data={AUTH_REQUIRED_OPTIONS} allowDeselect={false} {...bind('auth_required')} />
        </SettingRow>
      </SettingsSection>
      <ApiKeySection />
      <LoginSection />
    </Stack>
  );
}
