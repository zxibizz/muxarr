export type MoveStatus = 'DeferMove' | 'MoveComplete' | 'RenameRequested';

export interface RejectedTrack {
  track: string;
  reason: string;
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
  added_tracks: string[];
  rejected_tracks: RejectedTrack[];
  duration_ms: number;
  source_bytes: number | null;
  output_bytes: number | null;
  dry_run: boolean;
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
