import { NumberInput, Switch } from '@mantine/core';
import { SettingRow, SettingsSection } from '../SettingsSection';
import type { SettingsFormApi } from '../useSettingsForm';

export function MuxingSection({ field, bind }: SettingsFormApi) {
  return (
    <SettingsSection title="Muxing" description="How the remux itself behaves.">
      <SettingRow
        binding={field('mux_timeout_seconds')}
        label="Mux timeout"
        description="Seconds before a remux is abandoned and the import left to *arr."
      >
        <NumberInput min={1} suffix=" s" {...bind('mux_timeout_seconds')} />
      </SettingRow>
      <SettingRow
        binding={field('free_space_factor')}
        label="Free space factor"
        description="Multiple of the source size that must be free before muxing starts."
      >
        <NumberInput min={1} step={0.05} decimalScale={2} suffix="×" {...bind('free_space_factor')} />
      </SettingRow>
      <SettingRow
        binding={field('preserve_ownership')}
        label="Preserve ownership"
        description="Copy the source file's owner and group onto the output."
        inline
      >
        <Switch {...bind('preserve_ownership', { type: 'checkbox' })} />
      </SettingRow>
    </SettingsSection>
  );
}
