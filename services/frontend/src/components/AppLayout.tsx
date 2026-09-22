import { AppShell, Badge, Button, Container, Group, Text, Title } from '@mantine/core';
import { useCallback, useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { api } from '../api';
import { useAuthGate } from '../auth-context';
import { SystemDrawer } from './SystemDrawer';
import { TokenPrompt } from './TokenPrompt';
import type { Health, SystemStatus } from '../types';

const POLL_INTERVAL_MS = 10_000;

const PAGES = [
  { to: '/', label: 'History', caption: 'import history' },
  { to: '/settings', label: 'Settings', caption: 'service settings' },
];

export function AppLayout() {
  const { needsToken, retryKey, reportError, submitToken } = useAuthGate();
  const [health, setHealth] = useState<Health | null>(null);
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [systemOpen, setSystemOpen] = useState(false);
  const { pathname } = useLocation();

  const caption = PAGES.find((page) => page.to === pathname)?.caption ?? '';

  const pollSystem = useCallback(async () => {
    try {
      setSystem(await api.system());
    } catch (caught) {
      reportError(caught);
    }
  }, [reportError]);

  useEffect(() => {
    api.health().then(setHealth).catch(() => undefined);
  }, [retryKey]);

  useEffect(() => {
    void pollSystem();
    if (needsToken) return undefined;
    const timer = window.setInterval(() => void pollSystem(), POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [needsToken, pollSystem, retryKey]);

  return (
    <AppShell header={{ height: 60 }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="sm">
            <Title order={3}>muxarr</Title>
            <Text size="sm" c="dimmed">
              {caption}
            </Text>
          </Group>
          <Group gap="xs">
            {PAGES.map((page) => (
              <Button
                key={page.to}
                component={NavLink}
                to={page.to}
                variant={pathname === page.to ? 'light' : 'subtle'}
                size="compact-sm"
              >
                {page.label}
              </Button>
            ))}
            {system && !system.worker.alive && (
              <Badge color="red" variant="filled">
                worker offline
              </Badge>
            )}
            <Button variant="subtle" size="compact-sm" onClick={() => setSystemOpen(true)}>
              System
            </Button>
            {health && (
              <Text size="xs" c="dimmed">
                v{health.version}
              </Text>
            )}
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Main>
        <Container size="xl">
          <Outlet />
        </Container>
      </AppShell.Main>

      <SystemDrawer
        system={system}
        opened={systemOpen}
        onClose={() => setSystemOpen(false)}
      />

      <TokenPrompt opened={needsToken} onSubmit={submitToken} />
    </AppShell>
  );
}
