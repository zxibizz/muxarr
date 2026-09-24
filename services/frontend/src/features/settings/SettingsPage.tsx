import { Alert, Button, Group, Paper, Skeleton, Stack, Tabs, Text } from '@mantine/core';
import { IconAlertTriangle, IconLock } from '@tabler/icons-react';
import { useSearchParams } from 'react-router';
import { describeError } from '../../api/client';
import { useSettings } from '../../api/queries';
import type { ServiceSettings } from '../../api/types';
import { PageHeader } from '../../components/PageHeader';
import { isSectionId } from './fields';
import type { SectionId } from './fields';
import { SectionMenu, SectionTabs } from './SectionNav';
import { AiSection } from './sections/AiSection';
import { LoggingSection } from './sections/LoggingSection';
import { MuxingSection } from './sections/MuxingSection';
import { QueueSection } from './sections/QueueSection';
import { SecuritySection } from './sections/SecuritySection';
import { SelectionSection } from './sections/SelectionSection';
import { useSettingsForm } from './useSettingsForm';

interface FormProps {
  settings: ServiceSettings;
  section: SectionId;
  onSectionChange: (id: SectionId) => void;
}

function SettingsForm({ settings, section, onSectionChange }: FormProps) {
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

        <Tabs
          value={section}
          onChange={(value) => {
            if (isSectionId(value)) onSectionChange(value);
          }}
          keepMounted
        >
          <SectionTabs dirty={editor.dirtySection} />
          <SectionMenu current={section} onChange={onSectionChange} dirty={editor.dirtySection} />

          <Tabs.Panel value="selection" pt="lg">
            <SelectionSection {...editor.api} />
          </Tabs.Panel>
          <Tabs.Panel value="muxing" pt="lg">
            <MuxingSection {...editor.api} />
          </Tabs.Panel>
          <Tabs.Panel value="queue" pt="lg">
            <QueueSection {...editor.api} />
          </Tabs.Panel>
          <Tabs.Panel value="ai" pt="lg">
            <AiSection
              {...editor.api}
              apiKey={editor.apiKey}
              onApiKeyChange={editor.setApiKey}
              keyStored={settings.ai_api_key_set}
              onClearKey={() => void editor.clearKey()}
            />
          </Tabs.Panel>
          <Tabs.Panel value="logging" pt="lg">
            <LoggingSection {...editor.api} />
          </Tabs.Panel>
          <Tabs.Panel value="security" pt="lg">
            <SecuritySection {...editor.api} />
          </Tabs.Panel>
        </Tabs>

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
  const [params, setParams] = useSearchParams();
  const requested = params.get('section');
  const section: SectionId = isSectionId(requested) ? requested : 'selection';
  // replace: switching tabs should not fill the Back history.
  const showSection = (id: SectionId) => setParams({ section: id }, { replace: true });

  return (
    <Stack gap="xl">
      <PageHeader
        title="Settings"
        description="Changes apply to the next import. Nothing needs restarting."
      />

      {loadError ? (
        <Alert color="red" icon={<IconAlertTriangle size={18} />} title="Could not load settings">
          {loadError}
        </Alert>
      ) : settings.data ? (
        <SettingsForm settings={settings.data} section={section} onSectionChange={showSection} />
      ) : (
        <Stack gap="lg">
          <Skeleton height={36} radius="md" />
          <Skeleton height={320} radius="lg" />
        </Stack>
      )}
    </Stack>
  );
}
