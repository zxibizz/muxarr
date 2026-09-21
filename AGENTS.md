# AGENTS.md

muxarr embeds external audio/subtitle tracks into a video container during a
Radarr/Sonarr import. A POSIX-sh shim runs inside the *arr container, queues a
job with this daemon and long-polls for the verdict.

## Layout

```
services/backend/src/    api | application | domain | infrastructure | db | schemas | settings | core | cli
services/backend/tests/  mirrors the layers, plus integration/
services/frontend/       React + Vite SPA
scripts/                 the *arr-side shims (they run in Sonarr's container, not ours)
cicd/containers/         the s6-overlay overlay copied into the production image
alembic/                 under services/backend/
```

## Hard rules

1. **Dependencies point inward.** `domain/` imports nothing from the other
   layers; `application/` never imports `infrastructure/` or FastAPI;
   `infrastructure/` never imports `api/`. `tests/test_architecture.py` enforces
   this by AST, with one carve-out: `domain/models.py` holds the SQLAlchemy ORM.
2. **The HTTP contract is frozen.** Shims deployed in the wild already POST
   `/v1/import` and poll `/v1/jobs/{id}/protocol`. No `/api` prefix, no renames.
3. **`/v1/jobs/{id}/protocol` always returns 200**, with the state in the body.
   curl and busybox wget surface non-2xx so differently that a sh shim cannot
   tell "unknown job" from "connection refused". The JSON route keeps a real 404.
4. **`HandleImportUseCase.execute` never raises.** Every unexpected condition
   becomes a `DeferMove` outcome, which makes *arr import the file itself as
   though muxarr were absent. A job in state `failed` therefore means the daemon
   itself broke.
5. **`execute` stays synchronous.** A remux runs for minutes to hours; it is
   dispatched with `asyncio.to_thread` so the event loop keeps serving polls.
6. **The download folder is never written to**, in any transfer mode. There is a
   parametrised test asserting a byte-for-byte snapshot across every mode.
7. **New external dependencies go behind a Protocol** in
   `application/interfaces/`, with the adapter in `infrastructure/` and the
   wiring in `core/container.py`. Use cases take the Protocol, never the adapter.
8. **Route handlers stay thin**: schema -> use case -> record -> schema. They do
   not catch domain exceptions; add the mapping to `DOMAIN_ERROR_MAP` in
   `api/errors.py` instead.
9. **Jobs are deliberately in-memory.** A `Job` holds a live `asyncio.Task`; a
   persisted `running` row after a restart would be a lie the shim cannot detect.
   A lost job is reported as `unknown`, which fails the import on purpose -- the
   source may have been half-moved by the mux that died with it.
10. **Never bypass the path guard.** Every path from an HTTP client goes through
    `PathGuard.check_read` / `check_destination` / `check_write` before it
    reaches a subprocess.
11. **Subprocesses are argv lists.** No `shell=True`, anywhere. Everything goes
    through `infrastructure/process/runner.py`.
12. **The shims must stay POSIX sh.** No `[[`, no `local`, no `function name()`;
    they run under dash and busybox ash. `tests/integration/test_shim.py` greps
    for the banned constructs.
13. **Logging is loguru.** `get_logger(LogComponent.X)` at module level, context
    as keyword arguments (`log.info("import settled", job_id=..., status=...)`),
    never `%s` interpolation and never `logging.getLogger`. `LogComponent` is a
    closed enum so a mistyped component fails a type check. stdlib records from
    uvicorn, alembic and sqlalchemy are rerouted by `InterceptHandler`.
14. **Comments explain why, not what.**

## Commands

```bash
cd services/backend
uv sync
uv run ruff check .
uv run python -m mypy          # strict; src/ only
uv run pytest -q               # ~30s; test_shim spawns real /bin/sh + HTTP servers
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "describe the change"
uv run python -m src.cli serve

cd services/frontend
npm run dev                    # proxies /v1 to VITE_API_PROXY_TARGET
npm run build

docker compose -f docker-compose.dev.yaml up --build
docker build -f Dockerfile.all-in-one -t muxarr:latest .
```

The mux integration tests skip without mkvtoolnix and ffmpeg on PATH. The dev
image ships both:

```bash
docker compose -f docker-compose.dev.yaml run --rm backend pytest -q
```

## Container

One image, three processes under s6-overlay: an `01-prepare` init hook that
chowns `/config` to `PUID:PGID`, an `02-migrations` hook running
`alembic upgrade head`, then `api` (uvicorn on 127.0.0.1:8000, started via the
`build_app` ASGI factory) and `nginx` (:8710, serving `/static` with SPA
fallback and proxying `/v1` and `/healthz`).

There is no module-level `app`: it would call `Settings.from_env()` at import
time and make merely importing `src.api.app` depend on a configured
environment, which breaks the test suite.

`proxy_read_timeout` in the nginx vhost **must** exceed
`MUXARR_MAX_POLL_WAIT`, or a healthy long-poll becomes a 504 and the shim fails
a perfectly good import.
