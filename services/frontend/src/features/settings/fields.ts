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
};

export const FIELDS = Object.keys(ENV_VARS) as SettingsField[];

export const API_KEY_ENV = 'MUXARR_AI_API_KEY';

export const SECTIONS = [
  { id: 'selection', title: 'Track selection' },
  { id: 'muxing', title: 'Muxing' },
  { id: 'queue', title: 'Queue and retention' },
  { id: 'ai', title: 'AI track discovery' },
  { id: 'logging', title: 'Logging' },
] as const;

export type SectionId = (typeof SECTIONS)[number]['id'];

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

export function editableFrom(settings: ServiceSettings): EditableSettings {
  const editable = {} as EditableSettings;
  for (const field of FIELDS) {
    Object.assign(editable, { [field]: settings[field] });
  }
  // Absent on the wire as null, but a controlled input needs a string.
  editable.sub_charset = editable.sub_charset ?? '';
  return editable;
}
