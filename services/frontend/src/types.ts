export type MoveStatus = 'DeferMove' | 'MoveComplete' | 'RenameRequested';

export type TrackKind = 'video' | 'audio' | 'subtitles';

/** Whether a filename told muxarr what this track was, or a language model did. */
export type TrackSource = 'heuristic' | 'ai';

export interface AddedTrack {
  kind: TrackKind;
  label: string;
  language: string;
  name: string | null;
  forced: boolean;
  hearing_impaired: boolean;
  variant: string | null;
  file: string;
  source: TrackSource;
}

export interface RejectedTrack {
  track: string;
  reason: string;
  kind: TrackKind;
  language: string;
  source: TrackSource;
}

/** A track the source already held that the keep lists stripped. */
export interface RemovedTrack {
  index: number;
  kind: TrackKind;
  language: string;
  name: string | null;
  codec: string;
  forced: boolean;
  reason: string;
}

export type LogStage =
  | 'guard'
  | 'probe'
  | 'discovery'
  | 'ai'
  | 'selection'
  | 'mux'
  | 'placement'
  | 'outcome';

export interface LogEntry {
  ts: string;
  level: string;
  component: string;
  message: string;
  // Set on the records that make up the narrative; null on the rest.
  stage: LogStage | null;
  context: Record<string, string>;
}

export interface Operation {
  id: number;
  created_at: string;
  app: string;
  title: string;
  move_status: MoveStatus;
  reason: string;
  source_path: string;
  destination_path: string;
  media_file: string | null;
  transfer_mode: string;
  season: number | null;
  episodes: number[];
  added_tracks: AddedTrack[];
  rejected_tracks: RejectedTrack[];
  removed_tracks: RemovedTrack[];
  log: LogEntry[];
  duration_ms: number;
  source_bytes: number | null;
  output_bytes: number | null;
  dry_run: boolean;
}

export type JobState = 'pending' | 'running' | 'succeeded' | 'failed';

export interface Job {
  id: string;
  state: JobState;
  error: string | null;
  history_id: number | null;
  app: string;
  title: string;
  source_path: string;
  destination_path: string;
  transfer_mode: string;
  dry_run: boolean;
  created_at: string;
  updated_at: string;
  log: LogEntry[];
}

export interface JobPage {
  items: Job[];
  total: number;
  limit: number;
  offset: number;
}

export interface HistoryPage {
  items: Operation[];
  total: number;
  limit: number;
  offset: number;
}

export interface Stats {
  total: number;
  muxed: number;
  deferred: number;
  tracks_added: number;
  last_24h: number;
}

export interface Health {
  status: string;
  version: string;
  read_roots: string[];
  auth_required: boolean;
}

export interface WorkerStatus {
  alive: boolean;
  last_seen_at: string | null;
  stale_after_seconds: number;
  max_concurrent_muxes: number;
}

export interface QueueStatus {
  pending: number;
  running: number;
  succeeded: number;
  failed: number;
}

export interface SystemStatus {
  version: string;
  worker: WorkerStatus;
  queue: QueueStatus;
}

export interface HistoryFilters {
  status: MoveStatus | null;
  app: string | null;
  query: string;
}

export type DedupeMode = 'off' | 'language' | 'language_codec';
export type AiMode = 'off' | 'fallback' | 'always' | 'verify';
export type LogLevel =
  | 'TRACE'
  | 'DEBUG'
  | 'INFO'
  | 'SUCCESS'
  | 'WARNING'
  | 'ERROR'
  | 'CRITICAL';

/** The settings the UI owns. Anything else is environment-only by design. */
export interface EditableSettings {
  dedupe: DedupeMode;
  skip_image_subtitles: boolean;
  skip_undetermined_language: boolean;
  max_external_tracks: number;
  sub_charset: string | null;
  // Empty keeps every language.
  keep_audio_languages: string[];
  keep_subtitle_languages: string[];

  mux_timeout_seconds: number;
  free_space_factor: number;
  preserve_ownership: boolean;

  max_concurrent_muxes: number;
  job_ttl_seconds: number;
  history_max_records: number;
  operation_log_max_entries: number;

  ai_mode: AiMode;
  ai_base_url: string;
  ai_model: string;
  ai_timeout_seconds: number;
  ai_max_entries: number;
  ai_name_tracks: boolean;

  log_level: LogLevel;
}

export type SettingsField = keyof EditableSettings;

export interface ServiceSettings extends EditableSettings {
  // The key itself is write-only; this is all the daemon will say about it.
  ai_api_key_set: boolean;
  // Pinned by an environment variable, so not editable here.
  locked: SettingsField[];
}

export type SettingsPatch = Partial<EditableSettings> & { ai_api_key?: string | null };

export interface AiTestRequest {
  base_url: string;
  model: string;
  // Omitted means "use the key already stored".
  api_key?: string | null;
  timeout_seconds?: number;
}

export interface AiTestResult {
  ok: boolean;
  message: string;
  latency_ms: number;
}
