import { useForm } from '@mantine/form';
import type { UseFormReturnType } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { useCallback, useState } from 'react';
import { useUpdateSettings } from '../../api/queries';
import type { EditableSettings, ServiceSettings, SettingsField, SettingsPatch } from '../../api/types';
import { API_KEY_ENV, ENV_VARS, FIELDS, SECTIONS, editableFrom } from './fields';
import type { LockableField, SectionId } from './fields';

type InputProps = ReturnType<UseFormReturnType<EditableSettings>['getInputProps']>;

export interface FieldBinding {
  id: string;
  envVar: string;
  locked: boolean;
}

export interface SettingsFormApi {
  form: UseFormReturnType<EditableSettings>;
  field: (name: LockableField) => FieldBinding;
  bind: (name: SettingsField, options?: { type: 'checkbox' }) => InputProps & {
    id: string;
    disabled: boolean;
  };
}

export function useSettingsForm(settings: ServiceSettings) {
  const update = useUpdateSettings();
  const form = useForm<EditableSettings>({ initialValues: editableFrom(settings) });
  // Separate from the form: it is write-only, so there is no stored value to show.
  const [apiKey, setApiKey] = useState('');

  const locked = useCallback(
    (name: LockableField) => settings.locked.includes(name),
    [settings.locked],
  );

  const field = useCallback(
    (name: LockableField): FieldBinding => ({
      id: `setting-${name}`,
      envVar: name === 'ai_api_key' ? API_KEY_ENV : ENV_VARS[name],
      locked: locked(name),
    }),
    [locked],
  );

  const bind: SettingsFormApi['bind'] = (name, options) => ({
    ...form.getInputProps(name, options),
    id: `setting-${name}`,
    disabled: locked(name),
  });

  const adopt = (next: ServiceSettings) => {
    form.setInitialValues(editableFrom(next));
    form.setValues(editableFrom(next));
    form.resetDirty();
    setApiKey('');
  };

  const save = form.onSubmit(async (values) => {
    const patch: SettingsPatch = {};
    for (const name of FIELDS) {
      if (!locked(name)) Object.assign(patch, { [name]: values[name] });
    }
    // Left blank means "leave the stored key alone", not "clear it".
    if (apiKey.trim() && !locked('ai_api_key')) patch.ai_api_key = apiKey.trim();

    try {
      adopt(await update.mutateAsync(patch));
      notifications.show({
        color: 'teal',
        title: 'Settings saved',
        message: 'The worker picks these up within a few seconds; nothing needs restarting.',
      });
    } catch {
      // Rendered from update.error.
    }
  });

  const clearKey = async () => {
    try {
      await update.mutateAsync({ ai_api_key: null });
      setApiKey('');
      notifications.show({
        color: 'gray',
        title: 'API key cleared',
        message: 'The AI provider is not called again until a new key is saved.',
      });
    } catch {
      // Rendered from update.error.
    }
  };

  const discard = () => {
    form.reset();
    setApiKey('');
  };

  const dirtySection = (id: SectionId) => {
    const section = SECTIONS.find((candidate) => candidate.id === id);
    return (section?.fields ?? []).some((name: LockableField) =>
      name === 'ai_api_key' ? apiKey.trim() !== '' : form.isDirty(name),
    );
  };

  const api: SettingsFormApi = { form, field, bind };

  return {
    api,
    apiKey,
    setApiKey,
    save,
    discard,
    clearKey,
    saving: update.isPending,
    saveError: update.error,
    dirty: form.isDirty() || apiKey.trim() !== '',
    dirtySection,
    locked,
  };
}
