# muxarr

Embeds external audio and subtitle tracks into video containers at the moment
Radarr/Sonarr import a download, using the **Import Using Script** hook.

When a release ships `Subs/2_English.srt`, a separate `.ac3` dub, or a folder of
alternate dubs like `RUS Sound [Group]/`, muxarr remuxes them into a single MKV
as the file lands in your library — so the tracks are embedded rather than
scattered as sidecars, and the filename reflects the tracks actually in the file.

## Design rules

- **Stream-copy only.** No transcoding, ever. A mux costs one sequential read
  and one sequential write.
- **The download folder is read-only.** muxarr never writes, renames or deletes
  anything on the source side, in any transfer mode. Cleanup of the original
  stays with your download client's Completed Download Handling.
- **Fail safe.** Any error degrades to `DeferMove`, and Radarr/Sonarr perform a
  completely normal import. The shim exits 0 on every path up to the point a
  remux is queued — after that, a lost result exits non-zero and fails the
  import, because deferring would race a mux that may still be running.
- **Staging lives in the destination directory**, so the final step is an atomic
  rename rather than a cross-device copy.

## How it fits together

```
Radarr/Sonarr  --exec-->  muxarr-import-*.sh  --HTTP-->  muxarr API
 (import)                 (in *arr container)            (queues the job)
      ^                                                        |
      |                                                   jobs table
      |                                                        |
      |                                                        v
      +---------- [MoveStatus] RenameRequested <--------  muxarr worker
                                                          (owns mkvmerge)
```

The API and the worker are separate processes. The API only queues work and
reports on it; the worker claims a job, muxes, and writes the result back. That
split means a worker crash or restart cannot take the API down with it, and a
long mux never blocks the shim's polls.

The shim queues the remux and then long-polls for the result: each request is
held open by the API until the job changes state, so the shim learns about
completion within a second while no single request lives long enough for a
reverse proxy to time it out. A dropped connection is simply retried against the
same job id, which the API treats idempotently.

There is one shim per app — `muxarr-import-radarr.sh` and
`muxarr-import-sonarr.sh` — because each reads a different set of \*arr
environment variables. Both are dependency-free POSIX `sh` (needs only `curl` or
`wget`). All the heavy dependencies live in the muxarr container.

## Web UI

nginx inside the container serves a React/Mantine UI on the same port (default
<http://localhost:8710>) and reverse-proxies the API behind it, showing every
import it has been handed — including the ones it skipped, which is usually the
question you actually have.

Each row expands into the full decision: the paths involved, which tracks were
embedded, and which sidecars were passed over *and why*. The history is stored
in SQLite under `/config`, so it survives restarts — mount that volume or you
will lose it.

If `MUXARR_TOKEN` is set, the UI asks for it once and keeps it in the browser's
local storage.

## Setup

1. **Deploy.** Copy `compose.example.yaml` to `compose.yaml`, set `MUXARR_TOKEN`
   in a `.env` file, and adjust the volume paths. Set `PUID`/`PGID` to the uid
   that owns your library — muxarr creates the final file, so it must match.

   > Every media path must be mounted at the **same path** in the \*arr
   > containers and in muxarr. Radarr/Sonarr pass absolute paths; if they mean
   > different things in each container, muxarr rejects them and defers.

   > `/config` holds the operation history. Migrations run on every start.

2. **Share the shims.** They ship inside the muxarr image; the example compose
   republishes them into a `muxarr-shims` volume that the \*arr containers mount
   read-only at `/config/scripts`. Nothing needs a checkout of this repo.

3. **Configure Radarr/Sonarr.** Settings → Media Management → *show Advanced* →
   Importing:
   - tick **Import Using Script**
   - set **Import Script Path** to `/config/scripts/muxarr-import-radarr.sh` in
     Radarr, or `/config/scripts/muxarr-import-sonarr.sh` in Sonarr
   - leave **Import Extra Files** as you had it; muxarr suppresses the duplicate
     sidecar copy only for imports it actually muxed

4. **Check it.** `curl http://muxarr:8710/healthz` from inside the \*arr
   container, then import something and watch the muxarr logs.

   > `worker_alive` in that response must be `true`. If it is not, imports will
   > queue with nothing to run them and every one of them will eventually fail.

## Configuration

All settings are environment variables on the **daemon**:

| Variable | Default | Meaning |
| --- | --- | --- |
| `MUXARR_READ_ROOTS` | *required* | Colon-separated paths muxarr may read |
| `MUXARR_TOKEN` | *unset* | Bearer token; unauthenticated if unset |
| `MUXARR_HOST` / `MUXARR_PORT` | `0.0.0.0` / `8710` | Bind address |
| `MUXARR_MAX_CONCURRENT` | `1` | Simultaneous remuxes, in the worker |
| `MUXARR_JOB_TTL` | `3600` | Seconds a finished job stays readable |
| `MUXARR_MAX_POLL_WAIT` | `60` | Ceiling on how long one poll is held open |
| `MUXARR_SCRATCH_DIR` | destination dir | Only change for NFS/SMB/union FS |
| `MUXARR_DEDUPE` | `language_codec` | `off`, `language`, `language_codec` |
| `MUXARR_SKIP_IMAGE_SUBTITLES` | `false` | Exclude PGS/VobSub |
| `MUXARR_SKIP_UNDETERMINED` | `false` | Exclude tracks with unknown language |
| `MUXARR_MAX_TRACKS` | `24` | Cap on embedded tracks |
| `MUXARR_PRESERVE_OWNERSHIP` | `true` | chown output to match the source |
| `MUXARR_DB_URL` | `sqlite+aiosqlite:////config/muxarr.db` | Where the history lives |
| `MUXARR_LOG_LEVEL` | `INFO` | |
| `MUXARR_LOG_JSON` | `false` | One JSON object per record, for log shippers |
| `PUID` / `PGID` | `1000` / `1000` | uid/gid the services drop to |

And on the **shim**:

| Variable | Default | Meaning |
| --- | --- | --- |
| `MUXARR_URL` | `http://muxarr:8710` | Daemon address |
| `MUXARR_TOKEN` | *unset* | Bearer token, if the daemon requires one |
| `MUXARR_TIMEOUT` | `14400` | Total seconds to wait for a remux |
| `MUXARR_POLL_WAIT` | `25` | Seconds the daemon holds each poll open |
| `MUXARR_POLL_INTERVAL` | `5` | Back-off after a failed request |
| `MUXARR_MAX_RETRIES` | `10` | Consecutive request failures tolerated |

## Repository layout

```
services/backend    FastAPI daemon: api | application | domain | infrastructure
services/frontend   React + Vite SPA
scripts/            the *arr-side shims
cicd/containers/    s6-overlay service definitions for the production image
```

The backend follows a layered architecture — dependencies point inward, and a
test enforces it. See [AGENTS.md](AGENTS.md) for the rules.

## CLI

```sh
cd services/backend
uv run python -m src.cli inspect video.mkv    # list tracks in a container
uv run python -m src.cli plan    video.mkv    # show what would be embedded
uv run python -m src.cli mux     video.mkv --out out.mkv
uv run python -m src.cli serve                # run the API
uv run python -m src.worker                   # run the worker
```

## Development

```sh
cd services/backend
uv sync
uv run ruff check .
uv run python -m mypy
uv run pytest -q
uv run alembic upgrade head
```

```sh
cd services/frontend
npm install
npm run dev
```

Or the whole stack with hot reload on both sides:

```sh
docker compose -f compose.dev.yaml up --build
```

Tests needing real `mkvmerge`/`ffmpeg` are marked and skipped when those tools
are absent. The dev image has them, so the full suite runs there:

```sh
docker compose -f compose.dev.yaml run --rm backend pytest -q
```

### Frontend

The UI lives in `services/frontend/` (React 18, Mantine 7, Vite) and is built
into the image by `Dockerfile.all-in-one`, where nginx serves it. For a local
dev loop you need Node 20+:

```sh
cd services/backend && uv run python -m src.cli serve &   # API on :8710
cd services/frontend && npm install && npm run dev
```

`vite.config.ts` proxies `/v1` and `/healthz` to the daemon, or to
`VITE_API_PROXY_TARGET` when set.

## Requirements

`mkvtoolnix` is required at runtime. `ffmpeg` is optional, used as a probe
fallback and to generate test fixtures.
