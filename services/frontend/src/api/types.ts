// Aliases over the generated schema; regenerate it with `npm run gen:api`.
import type { components } from './schema.gen';

type Schemas = components['schemas'];

export type Operation = Schemas['OperationModel'];
export type HistoryPage = Schemas['HistoryPage'];
export type Stats = Schemas['StatsModel'];
export type AddedTrack = Schemas['TrackModel'];
export type RejectedTrack = Schemas['RejectedTrackModel'];
export type RemovedTrack = Schemas['RemovedTrackModel'];
export type LogEntry = Schemas['LogEntryModel'];
export type LogStage = Schemas['LogStage'];
export type Job = Schemas['JobDetailModel'];
export type JobPage = Schemas['JobPageModel'];
export type Health = Schemas['Health'];
export type SystemStatus = Schemas['SystemStatus'];
export type ServiceSettings = Schemas['SettingsView'];
export type SettingsPatch = Schemas['SettingsPatch'];
export type AiTestRequest = Schemas['AiTestRequest'];
export type AiTestResult = Schemas['AiTestResult'];
export type AuthStatus = Schemas['AuthStatusView'];
export type Credentials = Schemas['Credentials'];
export type CredentialsChange = Schemas['CredentialsChange'];
export type UserView = Schemas['UserView'];
export type ApiKey = Schemas['ApiKeyView'];

export type App = Operation['app'];
export type MoveStatus = Operation['move_status'];
export type JobState = Job['state'];
export type TrackKind = AddedTrack['kind'];
export type RejectCode = NonNullable<RejectedTrack['code']>;
export type DedupeMode = ServiceSettings['dedupe'];
export type AiMode = ServiceSettings['ai_mode'];
export type LogLevel = NonNullable<SettingsPatch['log_level']>;
export type AuthMethod = ServiceSettings['auth_method'];
export type AuthRequired = ServiceSettings['auth_required'];

/** The settings the UI owns. Anything else is environment-only by design. */
export type EditableSettings = Omit<ServiceSettings, 'ai_api_key_set' | 'locked' | 'auth_method'>;
export type SettingsField = keyof EditableSettings;

export interface HistoryFilters {
  status: MoveStatus | null;
  app: App | null;
  query: string;
}
