import type { EditableSettings, ServiceSettings, SettingsField } from '../../api/types';

// Exhaustive by type, so a new setting cannot be added without naming its variable.
export const ENV_VARS: Record<SettingsField, string> = {
  dedupe: 'MUXARR_DEDUPE',
  skip_image_subtitles: 'MUXARR_SKIP_IMAGE_SUBTITLES',
  skip_undetermined_language: 'MUXARR_SKIP_UNDETERMINED',
  max_external_tracks: 'MUXARR_MAX_TRACKS',
  sub_charset: 'MUXARR_SUB_CHARSET',
  keep_audio_languages: 'MUXARR_KEEP_AUDIO_LANGUAGES',
  keep_subtitle_languages: 'MUXARR_KEEP_SUBTITLE_LANGUAGES',
  skip_tags: 'MUXARR_SKIP_TAGS',
  require_tags: 'MUXARR_REQUIRE_TAGS',
  mux_timeout_seconds: 'MUXARR_MUX_TIMEOUT',
  free_space_factor: 'MUXARR_FREE_SPACE_FACTOR',
  preserve_ownership: 'MUXARR_PRESERVE_OWNERSHIP',
  max_concurrent_muxes: 'MUXARR_MAX_CONCURRENT',
  job_ttl_seconds: 'MUXARR_JOB_TTL',
  history_max_records: 'MUXARR_HISTORY_MAX_RECORDS',
  operation_log_max_entries: 'MUXARR_OPERATION_LOG_MAX_ENTRIES',
  ai_mode: 'MUXARR_AI_MODE',
  ai_base_url: 'MUXARR_AI_BASE_URL',
  ai_model: 'MUXARR_AI_MODEL',
  ai_timeout_seconds: 'MUXARR_AI_TIMEOUT',
  ai_max_entries: 'MUXARR_AI_MAX_ENTRIES',
  ai_name_tracks: 'MUXARR_AI_NAME_TRACKS',
  log_level: 'MUXARR_LOG_LEVEL',
  auth_required: 'MUXARR_AUTH_REQUIRED',
};

export const FIELDS = Object.keys(ENV_VARS) as SettingsField[];

export const API_KEY_ENV = 'MUXARR_AI_API_KEY';

// The key is write-only, so it is not part of the form, but its variable can still pin it.
export type LockableField = SettingsField | 'ai_api_key';

interface Section {
  id: string;
  title: string;
  fields: readonly LockableField[];
}

export const SECTIONS = [
  {
    id: 'selection',
    title: 'Track selection',
    fields: [
      'dedupe',
      'keep_audio_languages',
      'keep_subtitle_languages',
      'max_external_tracks',
      'sub_charset',
      'skip_image_subtitles',
      'skip_undetermined_language',
      'skip_tags',
      'require_tags',
    ],
  },
  {
    id: 'muxing',
    title: 'Muxing',
    fields: ['mux_timeout_seconds', 'free_space_factor', 'preserve_ownership'],
  },
  {
    id: 'queue',
    title: 'Queue and retention',
    fields: [
      'max_concurrent_muxes',
      'job_ttl_seconds',
      'history_max_records',
      'operation_log_max_entries',
    ],
  },
  {
    id: 'ai',
    title: 'AI track discovery',
    fields: [
      'ai_mode',
      'ai_base_url',
      'ai_model',
      'ai_api_key',
      'ai_timeout_seconds',
      'ai_max_entries',
      'ai_name_tracks',
    ],
  },
  { id: 'logging', title: 'Logging', fields: ['log_level'] },
  { id: 'security', title: 'Security', fields: ['auth_required'] },
] as const satisfies readonly Section[];

export type SectionId = (typeof SECTIONS)[number]['id'];

export function isSectionId(value: string | null): value is SectionId {
  return SECTIONS.some((section) => section.id === value);
}

export const DEDUPE_OPTIONS = [
  { value: 'language_codec', label: 'By language and codec' },
  { value: 'language', label: 'By language' },
  { value: 'off', label: 'Keep every track' },
];

export const AI_MODE_OPTIONS = [
  { value: 'off', label: 'Off' },
  { value: 'fallback', label: 'Fallback: only when filenames say nothing' },
  { value: 'always', label: 'Always' },
  { value: 'verify', label: 'Verify: consult and log, keep the filename answer' },
];

export const LOG_LEVELS = ['TRACE', 'DEBUG', 'INFO', 'SUCCESS', 'WARNING', 'ERROR', 'CRITICAL'];

export const AUTH_METHOD_LABELS = {
  forms: 'Login page',
  external: 'External: a reverse proxy signs users in',
} as const;

export const AUTH_REQUIRED_OPTIONS = [
  { value: 'enabled', label: 'Always' },
  { value: 'disabled_for_local_addresses', label: 'Not for local addresses' },
];

export function editableFrom(settings: ServiceSettings): EditableSettings {
  const editable = {} as EditableSettings;
  for (const field of FIELDS) {
    Object.assign(editable, { [field]: settings[field] });
  }
  // Absent on the wire as null, but a controlled input needs a string.
  editable.sub_charset = editable.sub_charset ?? '';
  return editable;
}
