import { NumberInput } from '@mantine/core';
import { SettingRow, SettingsSection } from '../SettingsSection';
import type { SettingsFormApi } from '../useSettingsForm';

export function QueueSection({ field, bind }: SettingsFormApi) {
  return (
    <SettingsSection
      id="queue"
      title="Queue and retention"
      description="How much work runs at once, and how long records are kept."
    >
      <SettingRow
        binding={field('max_concurrent_muxes')}
        label="Concurrent muxes"
        description="Two remuxes on one disk are usually slower than one at a time."
      >
        <NumberInput min={1} {...bind('max_concurrent_muxes')} />
      </SettingRow>
      <SettingRow
        binding={field('job_ttl_seconds')}
        label="Job retention"
        description="A finished job must outlast any plausible gap in the shim's polling."
      >
        <NumberInput min={60} suffix=" s" {...bind('job_ttl_seconds')} />
      </SettingRow>
      <SettingRow
        binding={field('history_max_records')}
        label="History records kept"
        description="Older operations are pruned while the worker is idle."
      >
        <NumberInput min={1} {...bind('history_max_records')} />
      </SettingRow>
      <SettingRow
        binding={field('operation_log_max_entries')}
        label="Log lines kept per import"
        description="The explanation shown on a history entry. 0 records none."
      >
        <NumberInput min={0} max={5000} {...bind('operation_log_max_entries')} />
      </SettingRow>
    </SettingsSection>
  );
}
