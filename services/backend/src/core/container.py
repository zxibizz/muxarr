"""Composition root.

Built by both processes: the API uses the enqueue/await half, the worker uses
the execution half. Neither reaches for a global.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import cached_property

from src.application.interfaces.ai import ChatCompleterFactory
from src.application.interfaces.auth import (
    ApiKeyRepository,
    PasswordHasher,
    SessionRepository,
    UserRepository,
)
from src.application.interfaces.history import HistoryRepository
from src.application.interfaces.jobs import JobRepository, WorkerStateRepository
from src.application.interfaces.settings import SettingsRepository
from src.application.interfaces.track_source import TrackDiscovery
from src.application.use_cases.auth.api_key import EnsureApiKeyUseCase, RegenerateApiKeyUseCase
from src.application.use_cases.auth.sessions import (
    ChangeCredentialsUseCase,
    GetAuthStatusUseCase,
    LoginUseCase,
    LogoutUseCase,
    ResolveSessionUseCase,
    SetupUseCase,
    SyncEnvCredentialsUseCase,
)
from src.application.use_cases.history.operations import (
    ClearHistoryUseCase,
    GetOperationUseCase,
    GetStatsUseCase,
    ListOperationsUseCase,
)
from src.application.use_cases.imports.await_job import AwaitJobUseCase
from src.application.use_cases.imports.enqueue_import import EnqueueImportUseCase
from src.application.use_cases.imports.handle_import import HandleImportUseCase
from src.application.use_cases.imports.list_jobs import ListJobsUseCase
from src.application.use_cases.imports.reconcile import ReconcileInterruptedJobsUseCase
from src.application.use_cases.imports.run_job import RunImportJobUseCase
from src.application.use_cases.settings.probe_ai import ProbeAiProviderUseCase
from src.application.use_cases.settings.read import GetSettingsUseCase
from src.application.use_cases.settings.update import UpdateSettingsUseCase
from src.application.use_cases.system.health import CheckWorkerHealthUseCase
from src.application.use_cases.system.status import GetSystemStatusUseCase
from src.core.logging import configure_logging, get_logger
from src.db.session import DBManager
from src.domain.enums import LogComponent
from src.domain.paths import PathGuard
from src.infrastructure.ai.discovery import AiAssistedTrackDiscovery
from src.infrastructure.ai.openai_compat import (
    OpenAICompatibleChatCompleter,
    OpenAICompatibleCompleterFactory,
)
from src.infrastructure.auth.hasher import Pbkdf2PasswordHasher
from src.infrastructure.auth.repository import (
    SqlAlchemyApiKeyRepository,
    SqlAlchemySessionRepository,
    SqlAlchemyUserRepository,
)
from src.infrastructure.filesystem.placement import FilesystemPlacement
from src.infrastructure.filesystem.track_discovery import FilesystemTrackDiscovery
from src.infrastructure.history.repository import SqlAlchemyHistoryRepository
from src.infrastructure.jobs.repository import SqlAlchemyJobRepository
from src.infrastructure.jobs.worker_state import SqlAlchemyWorkerStateRepository
from src.infrastructure.mkvtoolnix.muxer import MkvmergeMuxer
from src.infrastructure.probing import FallbackMediaProber
from src.infrastructure.settings.repository import SqlAlchemySettingsRepository
from src.settings.config import ConfigError, Settings
from src.settings.mutable import apply_overrides, locked_fields
from src.worker.service import WORKER_STALE_AFTER, ImportWorker

log = get_logger(LogComponent.CORE)

# Dropped and rebuilt whenever the stored overrides change. Everything else --
# the engine, the path guard, the repositories -- is environment-derived and so
# cannot change without a restart.
_SETTINGS_DERIVED = (
    "track_discovery",
    "handle_import",
    "run_import_job",
    "reconcile_jobs",
    "system_status",
)


class AppContainer:
    def __init__(
        self,
        settings: Settings,
        *,
        history: HistoryRepository | None = None,
        jobs: JobRepository | None = None,
        worker_state: WorkerStateRepository | None = None,
        settings_store: SettingsRepository | None = None,
        completers: ChatCompleterFactory | None = None,
        users: UserRepository | None = None,
        sessions: SessionRepository | None = None,
        api_keys: ApiKeyRepository | None = None,
        hasher: PasswordHasher | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.settings = settings
        self._history_override = history
        self._jobs_override = jobs
        self._worker_state_override = worker_state
        self._settings_store_override = settings_store
        self._completers_override = completers
        self._users_override = users
        self._sessions_override = sessions
        self._api_keys_override = api_keys
        self._hasher_override = hasher
        # Which fields the environment pins. Snapshotted: a variable cannot
        # appear or vanish without the process restarting anyway.
        self.locked = locked_fields(env)
        self._env_settings = settings
        self._revision = -1
        self._api_key: str | None = None

    @cached_property
    def db(self) -> DBManager:
        return DBManager(self.settings.db_url)

    @cached_property
    def guard(self) -> PathGuard:
        return PathGuard.from_roots(self.settings.read_roots)

    @cached_property
    def history(self) -> HistoryRepository:
        return self._history_override or SqlAlchemyHistoryRepository(self.db)

    @cached_property
    def jobs(self) -> JobRepository:
        return self._jobs_override or SqlAlchemyJobRepository(self.db)

    @cached_property
    def worker_state(self) -> WorkerStateRepository:
        return self._worker_state_override or SqlAlchemyWorkerStateRepository(self.db)

    @cached_property
    def settings_store(self) -> SettingsRepository:
        return self._settings_store_override or SqlAlchemySettingsRepository(self.db)

    @cached_property
    def completers(self) -> ChatCompleterFactory:
        return self._completers_override or OpenAICompatibleCompleterFactory()

    @cached_property
    def users(self) -> UserRepository:
        return self._users_override or SqlAlchemyUserRepository(self.db)

    @cached_property
    def sessions(self) -> SessionRepository:
        return self._sessions_override or SqlAlchemySessionRepository(self.db)

    @cached_property
    def api_keys(self) -> ApiKeyRepository:
        return self._api_keys_override or SqlAlchemyApiKeyRepository(self.db)

    @cached_property
    def hasher(self) -> PasswordHasher:
        return self._hasher_override or Pbkdf2PasswordHasher()

    @property
    def api_key_pinned(self) -> bool:
        return self._env_settings.api_key is not None

    @property
    def credentials_pinned(self) -> bool:
        return self._env_settings.username is not None

    async def api_key(self) -> str:
        """The key in force, read once and then served from memory."""
        if self._api_key is None:
            self._api_key = await EnsureApiKeyUseCase(
                store=self.api_keys, pinned=self._env_settings.api_key
            ).execute()
        return self._api_key

    async def regenerate_api_key(self) -> str:
        self._api_key = await RegenerateApiKeyUseCase(
            store=self.api_keys, pinned=self.api_key_pinned
        ).execute()
        return self._api_key

    async def bootstrap_auth(self) -> None:
        await self.api_key()
        env = self._env_settings
        if env.username is not None and env.password is not None:
            await SyncEnvCredentialsUseCase(
                users=self.users, sessions=self.sessions, hasher=self.hasher
            ).execute(env.username, env.password)

    async def sync_settings(self) -> bool:
        """Re-apply the stored overrides if they have changed.

        Both processes call this on their own schedule; it is the only way a
        change made in the API process reaches the worker without a restart.
        """
        snapshot = await self.settings_store.load()
        if snapshot.revision == self._revision:
            return False
        self._revision = snapshot.revision

        try:
            updated = apply_overrides(self._env_settings, snapshot.overrides, locked=self.locked)
        except ConfigError as exc:
            # Saved through the API, so this should be unreachable; carrying on
            # with the previous settings beats refusing to run imports.
            log.error("stored settings are unusable, keeping the current ones", error=str(exc))
            return False

        if updated == self.settings:
            return False

        if updated.log_level != self.settings.log_level:
            configure_logging(level=updated.log_level, serialize=updated.log_json)

        self.settings = updated
        for name in _SETTINGS_DERIVED:
            self.__dict__.pop(name, None)
        log.info("settings reloaded", revision=snapshot.revision)
        return True

    @cached_property
    def track_discovery(self) -> TrackDiscovery:
        settings = self.settings
        heuristic = FilesystemTrackDiscovery()
        if not settings.ai_enabled:
            return heuristic
        return AiAssistedTrackDiscovery(
            heuristic=heuristic,
            completer=OpenAICompatibleChatCompleter(
                base_url=settings.ai_base_url,
                model=settings.ai_model,
                api_key=settings.ai_api_key,
            ),
            mode=settings.ai_mode,
            max_entries=settings.ai_max_entries,
            timeout=settings.ai_timeout_seconds,
            max_tracks=settings.max_external_tracks,
            name_tracks=settings.ai_name_tracks,
        )

    @cached_property
    def handle_import(self) -> HandleImportUseCase:
        return HandleImportUseCase(
            settings=self.settings,
            guard=self.guard,
            prober=FallbackMediaProber(),
            tracks=self.track_discovery,
            muxer=MkvmergeMuxer(),
            placement=FilesystemPlacement(),
        )

    @cached_property
    def enqueue_import(self) -> EnqueueImportUseCase:
        return EnqueueImportUseCase(self.jobs)

    @cached_property
    def await_job(self) -> AwaitJobUseCase:
        return AwaitJobUseCase(self.jobs)

    @cached_property
    def list_jobs(self) -> ListJobsUseCase:
        return ListJobsUseCase(self.jobs)

    @cached_property
    def run_import_job(self) -> RunImportJobUseCase:
        return RunImportJobUseCase(
            jobs=self.jobs,
            history=self.history,
            handler=self.handle_import,
            log_max_entries=self.settings.operation_log_max_entries,
        )

    @cached_property
    def reconcile_jobs(self) -> ReconcileInterruptedJobsUseCase:
        return ReconcileInterruptedJobsUseCase(
            jobs=self.jobs,
            guard=self.guard,
            placement=FilesystemPlacement(),
            scratch_dir=self.settings.scratch_dir,
        )

    @cached_property
    def import_worker(self) -> ImportWorker:
        return ImportWorker(
            jobs=self.jobs,
            worker_state=self.worker_state,
            history=self.history,
            # Resolved per use, not captured: all three are rebuilt by sync_settings.
            run_job=lambda: self.run_import_job,
            reconcile=lambda: self.reconcile_jobs,
            settings=lambda: self.settings,
            sync=self.sync_settings,
            health=lambda: CheckWorkerHealthUseCase(settings=self.settings, muxer=MkvmergeMuxer()),
        )

    @cached_property
    def list_operations(self) -> ListOperationsUseCase:
        return ListOperationsUseCase(self.history)

    @cached_property
    def get_operation(self) -> GetOperationUseCase:
        return GetOperationUseCase(self.history)

    @cached_property
    def get_stats(self) -> GetStatsUseCase:
        return GetStatsUseCase(self.history)

    @cached_property
    def clear_history(self) -> ClearHistoryUseCase:
        return ClearHistoryUseCase(self.history)

    @cached_property
    def system_status(self) -> GetSystemStatusUseCase:
        return GetSystemStatusUseCase(
            jobs=self.jobs,
            worker_state=self.worker_state,
            stale_after_seconds=WORKER_STALE_AFTER,
            settings=self.settings,
        )

    @cached_property
    def get_settings(self) -> GetSettingsUseCase:
        return GetSettingsUseCase(store=self.settings_store)

    @cached_property
    def update_settings(self) -> UpdateSettingsUseCase:
        return UpdateSettingsUseCase(
            store=self.settings_store,
            locked=self.locked,
            base=lambda: self._env_settings,
        )

    @cached_property
    def probe_ai_provider(self) -> ProbeAiProviderUseCase:
        return ProbeAiProviderUseCase(completers=self.completers)

    @cached_property
    def auth_status(self) -> GetAuthStatusUseCase:
        return GetAuthStatusUseCase(users=self.users)

    @cached_property
    def login(self) -> LoginUseCase:
        return LoginUseCase(users=self.users, sessions=self.sessions, hasher=self.hasher)

    @cached_property
    def logout(self) -> LogoutUseCase:
        return LogoutUseCase(sessions=self.sessions)

    @cached_property
    def resolve_session(self) -> ResolveSessionUseCase:
        return ResolveSessionUseCase(sessions=self.sessions)

    @cached_property
    def setup(self) -> SetupUseCase:
        return SetupUseCase(
            users=self.users,
            sessions=self.sessions,
            hasher=self.hasher,
            pinned=self.credentials_pinned,
        )

    @cached_property
    def change_credentials(self) -> ChangeCredentialsUseCase:
        return ChangeCredentialsUseCase(
            users=self.users,
            sessions=self.sessions,
            hasher=self.hasher,
            pinned=self.credentials_pinned,
        )

    async def shutdown(self) -> None:
        # Only touch the engine if something actually opened it.
        if "db" in self.__dict__:
            await self.db.dispose()
