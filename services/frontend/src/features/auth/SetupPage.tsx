import { Alert, Button, Center, Loader, PasswordInput, Stack, TextInput } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';
import { useState } from 'react';
import { Navigate } from 'react-router';
import { useAuthStatus, useSetup } from '../../api/queries';
import { AuthScreen } from './AuthScreen';

// Mirrors MIN_PASSWORD_LENGTH in the daemon, which has the final say.
const MIN_PASSWORD = 8;

export function SetupPage() {
  const status = useAuthStatus();
  const setup = useSetup();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');

  if (status.isPending) {
    return (
      <Center h="100vh">
        <Loader />
      </Center>
    );
  }
  if (status.data && !status.data.setup_required) return <Navigate to="/" replace />;

  const tooShort = password.length > 0 && password.length < MIN_PASSWORD;
  const mismatch = confirm.length > 0 && confirm !== password;
  const ready = username.trim() !== '' && password.length >= MIN_PASSWORD && confirm === password;

  return (
    <AuthScreen
      title="Create a login"
      description="Muxarr requires an account for this UI. Radarr and Sonarr keep using the API key from Settings > Security."
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (ready) setup.mutate({ username: username.trim(), password });
        }}
      >
        <Stack gap="md">
          {setup.error && (
            <Alert color="red" icon={<IconAlertTriangle size={18} />}>
              {setup.error.message}
            </Alert>
          )}
          <TextInput
            label="Username"
            autoComplete="username"
            value={username}
            onChange={(event) => setUsername(event.currentTarget.value)}
            required
            data-autofocus
          />
          <PasswordInput
            label="Password"
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.currentTarget.value)}
            error={tooShort ? `At least ${MIN_PASSWORD} characters` : undefined}
            required
          />
          <PasswordInput
            label="Confirm password"
            autoComplete="new-password"
            value={confirm}
            onChange={(event) => setConfirm(event.currentTarget.value)}
            error={mismatch ? 'The passwords do not match' : undefined}
            required
          />
          <Button type="submit" loading={setup.isPending} disabled={!ready} fullWidth>
            Create login
          </Button>
        </Stack>
      </form>
    </AuthScreen>
  );
}
