import { NumberInput, Select, Switch, TagsInput, TextInput } from '@mantine/core';
import { DEDUPE_OPTIONS } from '../fields';
import { SettingRow, SettingsSection } from '../SettingsSection';
import type { SettingsFormApi } from '../useSettingsForm';

export function SelectionSection({ field, bind }: SettingsFormApi) {
  return (
    <SettingsSection
      title="Track selection"
      description="Which external tracks get embedded, and which of the source's own tracks are dropped."
    >
      <SettingRow
        binding={field('dedupe')}
        label="Duplicate handling"
        description="When a sidecar matches a track the file already has, it is skipped."
      >
        <Select data={DEDUPE_OPTIONS} allowDeselect={false} {...bind('dedupe')} />
      </SettingRow>
      <SettingRow
        binding={field('keep_audio_languages')}
        label="Keep audio languages"
        description="Strip every other audio track, in the source and in sidecars. Empty keeps all."
      >
        <TagsInput
          placeholder="eng, rus, und"
          splitChars={[',', ' ']}
          clearable
          {...bind('keep_audio_languages')}
        />
      </SettingRow>
      <SettingRow
        binding={field('keep_subtitle_languages')}
        label="Keep subtitle languages"
        description="Strip every other subtitle track, in the source and in sidecars. Empty keeps all."
      >
        <TagsInput
          placeholder="eng, rus"
          splitChars={[',', ' ']}
          clearable
          {...bind('keep_subtitle_languages')}
        />
      </SettingRow>
      <SettingRow
        binding={field('max_external_tracks')}
        label="Maximum external tracks"
        description="A ceiling on how many sidecars one import can add."
      >
        <NumberInput min={1} {...bind('max_external_tracks')} />
      </SettingRow>
      <SettingRow
        binding={field('sub_charset')}
        label="Subtitle character set"
        description="Force an encoding for text subtitles. Leave empty to let mkvmerge detect it."
      >
        <TextInput placeholder="auto-detect" {...bind('sub_charset')} />
      </SettingRow>
      <SettingRow
        binding={field('skip_image_subtitles')}
        label="Skip image subtitles"
        description="Drop VobSub and PGS tracks instead of embedding them."
        inline
      >
        <Switch {...bind('skip_image_subtitles', { type: 'checkbox' })} />
      </SettingRow>
      <SettingRow
        binding={field('skip_undetermined_language')}
        label="Skip undetermined languages"
        description="Drop tracks whose language could not be identified."
        inline
      >
        <Switch {...bind('skip_undetermined_language', { type: 'checkbox' })} />
      </SettingRow>
    </SettingsSection>
  );
}
