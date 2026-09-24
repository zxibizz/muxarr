import { Alert, Button, Center, Loader, PasswordInput, Stack, TextInput } from '@mantine/core';
import { IconAlertTriangle } from '@tabler/icons-react';
import { useState } from 'react';
import { Navigate, useSearchParams } from 'react-router';
import { useAuthStatus, useLogin } from '../../api/queries';
import { AuthScreen } from './AuthScreen';
import { safeReturnTo } from './returnTo';

export function LoginPage() {
  const status = useAuthStatus();
  const login = useLogin();
  const [params] = useSearchParams();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  if (status.isPending) {
    return (
      <Center h="100vh">
        <Loader />
      </Center>
    );
  }
  if (status.data?.setup_required) return <Navigate to="/setup" replace />;
  if (status.data?.authenticated) {
    return <Navigate to={safeReturnTo(params.get('returnTo'))} replace />;
  }

  return (
    <AuthScreen title="Sign in">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          login.mutate({ username, password });
        }}
      >
        <Stack gap="md">
          {login.error && (
            <Alert color="red" icon={<IconAlertTriangle size={18} />}>
              {login.error.message}
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
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.currentTarget.value)}
            required
          />
          <Button type="submit" loading={login.isPending} fullWidth>
            Sign in
          </Button>
        </Stack>
      </form>
    </AuthScreen>
  );
}
