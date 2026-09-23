import { Alert, Button, Grid, Group, NavLink, Paper, Skeleton, Stack, Text } from '@mantine/core';
import { IconAlertTriangle, IconLock } from '@tabler/icons-react';
import { describeError } from '../../api/client';
import { useSettings } from '../../api/queries';
import type { ServiceSettings } from '../../api/types';
import { PageHeader } from '../../components/PageHeader';
import { SECTIONS } from './fields';
import { AiSection } from './sections/AiSection';
import { LoggingSection } from './sections/LoggingSection';
import { MuxingSection } from './sections/MuxingSection';
import { QueueSection } from './sections/QueueSection';
import { SelectionSection } from './sections/SelectionSection';
import classes from './settings.module.css';
import { useSettingsForm } from './useSettingsForm';

function SettingsForm({ settings }: { settings: ServiceSettings }) {
  const editor = useSettingsForm(settings);
  const saveError = describeError(editor.saveError);
  const pinned = settings.locked.length;

  return (
    <form onSubmit={editor.save}>
      <Stack gap="lg">
        {saveError && (
          <Alert color="red" icon={<IconAlertTriangle size={18} />} title="Could not save settings">
            {saveError}
          </Alert>
        )}
        {pinned > 0 && (
          <Alert color="yellow" variant="outline" icon={<IconLock size={18} />}>
            {pinned === 1
              ? 'One setting is pinned by an environment variable in this deployment, so it is managed there rather than here.'
              : `${pinned} settings are pinned by environment variables in this deployment, so they are managed there rather than here.`}
          </Alert>
        )}

        <SelectionSection {...editor.api} />
        <MuxingSection {...editor.api} />
        <QueueSection {...editor.api} />
        <AiSection
          {...editor.api}
          apiKey={editor.apiKey}
          onApiKeyChange={editor.setApiKey}
          keyStored={settings.ai_api_key_set}
          onClearKey={() => void editor.clearKey()}
        />
        <LoggingSection {...editor.api} />

        {editor.dirty && (
          <Paper
            withBorder
            shadow="lg"
            p="sm"
            pl="lg"
            pos="sticky"
            bottom={16}
            style={{ zIndex: 5 }}
          >
            <Group justify="space-between">
              <Text size="sm">You have unsaved changes.</Text>
              <Group gap="sm">
                <Button variant="default" onClick={editor.discard} disabled={editor.saving}>
                  Discard
                </Button>
                <Button type="submit" loading={editor.saving}>
                  Save changes
                </Button>
              </Group>
            </Group>
          </Paper>
        )}
      </Stack>
    </form>
  );
}

export function SettingsPage() {
  const settings = useSettings();
  const loadError = describeError(settings.error);

  return (
    <Stack gap="xl">
      <PageHeader
        title="Settings"
        description="Changes apply to the next import. Nothing needs restarting."
      />

      <Grid gap="xl">
        <Grid.Col span={{ base: 12, md: 3 }} visibleFrom="md">
          <Stack gap={2} className={classes.nav}>
            {SECTIONS.map((section) => (
              <NavLink
                key={section.id}
                component="a"
                href={`#${section.id}`}
                label={section.title}
                variant="subtle"
              />
            ))}
          </Stack>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 9 }}>
          {loadError ? (
            <Alert color="red" icon={<IconAlertTriangle size={18} />} title="Could not load settings">
              {loadError}
            </Alert>
          ) : settings.data ? (
            <SettingsForm settings={settings.data} />
          ) : (
            <Stack gap="lg">
              <Skeleton height={320} radius="lg" />
              <Skeleton height={200} radius="lg" />
            </Stack>
          )}
        </Grid.Col>
      </Grid>
    </Stack>
  );
}
