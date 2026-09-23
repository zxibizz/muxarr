import { Select } from '@mantine/core';
import { LOG_LEVELS } from '../fields';
import { SettingRow, SettingsSection } from '../SettingsSection';
import type { SettingsFormApi } from '../useSettingsForm';

export function LoggingSection({ field, bind }: SettingsFormApi) {
  return (
    <SettingsSection title="Logging">
      <SettingRow
        binding={field('log_level')}
        label="Level"
        description="What reaches docker logs. Every import's own log is captured regardless."
      >
        <Select data={LOG_LEVELS} allowDeselect={false} {...bind('log_level')} />
      </SettingRow>
    </SettingsSection>
  );
}
