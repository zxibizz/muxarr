import {
  Alert,
  AppShell,
  Badge,
  Burger,
  Button,
  Container,
  Group,
  NavLink,
  Stack,
  Text,
  UnstyledButton,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import {
  IconAlertTriangle,
  IconHistory,
  IconLogout,
  IconServer2,
  IconSettings,
} from '@tabler/icons-react';
import { Link, Outlet, useLocation } from 'react-router';
import { useAuthStatus, useHealth, useLogout, useSystem } from '../api/queries';
import type { SystemStatus } from '../api/types';
import { LogoMark } from '../components/LogoMark';
import classes from './layout.module.css';

const NAV = [
  { to: '/', label: 'History', icon: IconHistory },
  { to: '/system', label: 'System', icon: IconServer2 },
  { to: '/settings', label: 'Settings', icon: IconSettings },
];

function Brand() {
  return (
    <Group gap={10} wrap="nowrap">
      <LogoMark size={30} />
      <Text fw={700} size="lg" lts={-0.2}>
        Muxarr
      </Text>
    </Group>
  );
}

function WorkerStatus({ system, onNavigate }: { system: SystemStatus | undefined; onNavigate: () => void }) {
  if (!system) return null;
  const { alive } = system.worker;
  const { pending, running } = system.queue;
  const activity =
    pending + running === 0 ? 'Idle' : `${running} running · ${pending} queued`;

  return (
    <UnstyledButton component={Link} to="/system" className={classes.status} onClick={onNavigate}>
      <Group gap="sm" wrap="nowrap">
        <span className={`${classes.dot} ${alive ? classes.alive : classes.dead}`} />
        <Stack gap={0}>
          <Text size="sm" fw={600}>
            {alive ? 'Worker online' : 'Worker offline'}
          </Text>
          <Text size="xs" c="dimmed">
            {alive ? activity : 'Imports are queueing'}
          </Text>
        </Stack>
      </Group>
    </UnstyledButton>
  );
}

export function AppLayout() {
  const [opened, { toggle, close }] = useDisclosure(false);
  const { pathname } = useLocation();
  const { data: system } = useSystem();
  const { data: health } = useHealth();
  const { data: auth } = useAuthStatus();
  const logout = useLogout();

  const queued = system ? system.queue.pending + system.queue.running : 0;
  const offline = system !== undefined && !system.worker.alive;

  return (
    <AppShell
      header={{ height: { base: 56, sm: 0 } }}
      navbar={{ width: 248, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding={{ base: 'md', sm: 'xl' }}
    >
      <AppShell.Header hiddenFrom="sm" px="md">
        <Group h="100%" justify="space-between">
          <Brand />
          <Burger opened={opened} onClick={toggle} size="sm" aria-label="Toggle navigation" />
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="md">
        <AppShell.Section visibleFrom="sm" px={6} pt={4} pb="lg">
          <Brand />
        </AppShell.Section>

        <AppShell.Section grow>
          <Stack gap={4}>
            {NAV.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                component={Link}
                to={to}
                label={label}
                active={pathname === to}
                leftSection={<Icon size={18} stroke={1.75} />}
                rightSection={
                  to === '/system' && queued > 0 ? (
                    <Badge size="sm" circle variant="filled">
                      {queued}
                    </Badge>
                  ) : undefined
                }
                onClick={close}
                style={{ borderRadius: 'var(--mantine-radius-md)' }}
              />
            ))}
          </Stack>
        </AppShell.Section>

        <AppShell.Section>
          <Stack gap="sm">
            <WorkerStatus system={system} onNavigate={close} />
            {auth?.method === 'forms' && auth.username && (
              <Group justify="space-between" wrap="nowrap" px={6}>
                <Text size="xs" c="dimmed" truncate>
                  Signed in as {auth.username}
                </Text>
                <Button
                  size="compact-xs"
                  variant="subtle"
                  color="gray"
                  leftSection={<IconLogout size={14} />}
                  loading={logout.isPending}
                  onClick={() => logout.mutate()}
                >
                  Sign out
                </Button>
              </Group>
            )}
            {health && (
              <Text size="xs" c="dimmed" px={6}>
                Muxarr v{health.version}
              </Text>
            )}
          </Stack>
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main>
        <Container size="xl" px={0}>
          <Stack gap="xl">
            {offline && pathname !== '/system' && (
              <Alert
                color="red"
                variant="light"
                icon={<IconAlertTriangle size={18} />}
                title="The worker is offline"
              >
                Imports are queueing with nothing to run them. Radarr and Sonarr keep waiting until it
                is back.
              </Alert>
            )}
            <Outlet />
          </Stack>
        </Container>
      </AppShell.Main>
    </AppShell>
  );
}
