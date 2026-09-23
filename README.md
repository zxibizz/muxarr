# muxarr

[![CI](https://github.com/zxibizz/muxarr/actions/workflows/ci.yml/badge.svg)](https://github.com/zxibizz/muxarr/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![ghcr.io](https://img.shields.io/badge/ghcr.io-zxibizz%2Fmuxarr-blue?logo=docker&logoColor=white)](https://github.com/zxibizz/muxarr/pkgs/container/muxarr)

**Sidecars in, one clean MKV out.** muxarr embeds external audio and subtitle
tracks into the video container at the moment Radarr/Sonarr import a download,
using the **Import Using Script** hook.

No sidecar `.srt` your player has to be told about. No second file to keep next
to the first one forever. No manual pass with mkvtoolnix after every release
that ships a dub in its own folder.

```
 the release Radarr/Sonarr grabbed        what lands in your library

 Some.Movie.2024.1080p-GRP/               Some Movie (2024)/
 ├── Some.Movie.2024.1080p-GRP.mkv        └── Some Movie (2024) Bluray-1080p.mkv
 ├── Subs/2_English.srt                       ├── video     h264
 ├── Subs/3_English.SDH.srt                   ├── audio     English
 └── RUS Sound [Group]/dub.mka                ├── audio     Russian      <- dub.mka
                                              ├── subtitles English      <- 2_English.srt
                                              └── subtitles English SDH  <- 3_English.SDH.srt
```

It runs where the tracks already are — inside your existing \*arr stack, with no
change to how you download, rename or organise anything.

- **Stream-copy only.** No transcoding, ever. A mux costs one sequential read
  and one sequential write; a 40 GB remux is disk-bound, not CPU-bound.
- **The download folder is read-only.** muxarr never writes, renames or deletes
  anything on the source side, in any transfer mode. Seeding is unaffected, and
  cleanup stays with your download client's Completed Download Handling.
- **Fail safe by construction.** Any error degrades to `DeferMove`, and
  Radarr/Sonarr perform a completely normal import — the worst case is the
  import you would have had anyway. The shim exits 0 on every path up to the
  point a remux is queued; after that, a lost result exits non-zero and fails
  the import, because deferring would race a mux that may still be running.
- **Staging lives in the destination directory**, so the final step is an atomic
  rename rather than a cross-device copy.
- **Every decision is on the record.** Each import keeps the reasoning that
  produced it — what the source already held, which sidecars were found, why
  each was taken or passed over — and the UI shows it back to you.

![The muxarr import history: what was muxed, what was skipped and which tracks went in](docs/images/history.png)

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
embedded and where each came from, which sidecars were passed over *and why*,
and the step-by-step log of the import that produced it — down to the mkvmerge
command line, if you scroll that far.

![An import opened up: the tracks that were embedded and the reasoning behind them](docs/images/operation-detail.png)

Imports that have not settled yet are listed the same way and follow their log
live, so a mux that will take an hour is something you can watch rather than
guess at. The history is stored in SQLite under `/config`, so it survives
restarts — mount that volume or you will lose it.

If `MUXARR_TOKEN` is set, the UI asks for it once and keeps it in the browser's
local storage.

## Setup

1. **Deploy.** Copy `compose.example.yaml` to `compose.yaml`, set `MUXARR_TOKEN`
   in a `.env` file, and adjust the volume paths. The image is published at
   `ghcr.io/zxibizz/muxarr` — pin a version tag rather than `latest`. Set
   `PUID`/`PGID` to the uid that owns your library — muxarr creates the final
   file, so it must match.

   > Every media path must be mounted at the **same path** in the \*arr
   > containers and in muxarr. Radarr/Sonarr pass absolute paths; if they mean
   > different things in each container, muxarr rejects them and defers.

   > `/config` holds the operation history. Migrations run on every start.

2. **Share the shims.** They ship inside the muxarr image, which copies them
   into a `muxarr-shims` volume on every start; the \*arr containers mount it
   read-only at `/config/scripts`. Nothing needs a checkout of this repo, and an
   upgraded image republishes them. Depend on muxarr being *healthy*, not
   merely started, or the \*arr containers can come up before the copy.

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

Most settings can be changed from the **Settings** page in the web UI, which
takes effect within a few seconds — no restart, in either process. The rest are
environment variables on the **daemon**.

A variable that is actually set in your compose file **wins and locks the
field**: the UI renders it read-only and names the variable, so compose stays
the single source of truth for anything you have configured there. Leave a
variable out to manage that setting from the UI instead.

![The settings page, with the fields pinned by the environment called out](docs/images/settings.png)

| Variable | Default | UI | Meaning |
| --- | --- | --- | --- |
| `MUXARR_READ_ROOTS` | *required* | | Colon-separated paths muxarr may read |
| `MUXARR_TOKEN` | *unset* | | Bearer token; unauthenticated if unset |
| `MUXARR_HOST` / `MUXARR_PORT` | `127.0.0.1` / `8710` | | Bind address for `src.cli serve`. Ignored in the container image, where uvicorn binds `127.0.0.1:8000` and nginx serves `:8710` |
| `MUXARR_MAX_CONCURRENT` | `1` | ✓ | Simultaneous remuxes, in the worker |
| `MUXARR_JOB_TTL` | `3600` | ✓ | Seconds a finished job stays readable |
| `MUXARR_HISTORY_MAX_RECORDS` | `200` | ✓ | Newest operations kept; older ones are trimmed |
| `MUXARR_OPERATION_LOG_MAX_ENTRIES` | `500` | ✓ | Log lines stored to explain one import; `0` records none |
| `MUXARR_MAX_POLL_WAIT` | `60` | | Ceiling on how long one poll is held open |
| `MUXARR_SCRATCH_DIR` | destination dir | | Only change for NFS/SMB/union FS |
| `MUXARR_DEDUPE` | `language_codec` | ✓ | `off`, `language`, `language_codec` |
| `MUXARR_SKIP_IMAGE_SUBTITLES` | `false` | ✓ | Exclude PGS/VobSub |
| `MUXARR_SKIP_UNDETERMINED` | `false` | ✓ | Exclude tracks with unknown language |
| `MUXARR_MAX_TRACKS` | `24` | ✓ | Cap on embedded tracks |
| `MUXARR_KEEP_AUDIO_LANGUAGES` | *unset* | ✓ | Comma-separated languages (`eng,rus`, `en`, `russian`) to keep. Every other audio track is stripped from the source and not embedded from sidecars; list `und` to keep untagged tracks. An import that would lose all its audio is left to *arr |
| `MUXARR_KEEP_SUBTITLE_LANGUAGES` | *unset* | ✓ | The same, for subtitles, forced ones included |
| `MUXARR_MUX_TIMEOUT` | `14400` | ✓ | Seconds before a single mkvmerge run is killed |
| `MUXARR_FREE_SPACE_FACTOR` | `1.05` | ✓ | Free space required before a mux, as a multiple of the expected output |
| `MUXARR_SUB_CHARSET` | *unset* | ✓ | Force a `--sub-charset` for text subtitles, e.g. `windows-1251` |
| `MUXARR_PRESERVE_OWNERSHIP` | `true` | ✓ | chown output to match the source |
| `MUXARR_DB_URL` | `sqlite+aiosqlite:////config/muxarr.db` | | Where the history lives |
| `MUXARR_LOG_LEVEL` | `INFO` | ✓ | |
| `MUXARR_LOG_JSON` | `false` | | One JSON object per record, for log shippers |
| `MUXARR_AI_MODE` | `off` | ✓ | `off`, `fallback`, `always`, `verify` — see [AI mode](#ai-mode) |
| `MUXARR_AI_BASE_URL` | `https://api.openai.com/v1` | ✓ | Any OpenAI-compatible endpoint |
| `MUXARR_AI_API_KEY` | *unset* | ✓ | Omit it for a local provider that needs no key |
| `MUXARR_AI_MODEL` | *unset* | ✓ | Required once `MUXARR_AI_MODE` is not `off` |
| `MUXARR_AI_TIMEOUT` | `30` | ✓ | Seconds before the request is abandoned |
| `MUXARR_AI_MAX_ENTRIES` | `200` | ✓ | Skip the call entirely above this many sidecars |
| `MUXARR_AI_NAME_TRACKS` | `false` | ✓ | Let the provider write the track names — see [Track names](#track-names) |
| `PUID` / `PGID` | `1000` / `1000` | | uid/gid the services drop to |

Read roots, the database URL, the bind address, the API token and the scratch
directory stay environment-only on purpose: they decide what muxarr is allowed
to touch and how it is reached, which is not something an HTTP request should
be able to move.

The AI key is write-only over HTTP. The UI can set or clear it and the daemon
will say whether one is stored, but it is never sent back to the browser.

And on the **shim**:

| Variable | Default | Meaning |
| --- | --- | --- |
| `MUXARR_URL` | `http://muxarr:8710` | Daemon address |
| `MUXARR_TOKEN` | *unset* | Bearer token, if the daemon requires one |
| `MUXARR_TIMEOUT` | `14400` | Total seconds to wait for a remux |
| `MUXARR_POLL_WAIT` | `25` | Seconds the daemon holds each poll open |
| `MUXARR_POLL_INTERVAL` | `5` | Back-off after a failed request |
| `MUXARR_MAX_RETRIES` | `10` | Consecutive request failures tolerated |

## AI mode

muxarr normally matches sidecars by filename: episode markers, language tags and
folder names. That covers most releases, but not all of them — a folder called
`Zvuk 1/` holding an untagged `.mka` is unattributable by any rule, and a season
pack whose subtitles are numbered rather than named is ambiguous by design.

AI mode hands that decision to a language model. It is **off by default** and
never required.

```yaml
environment:
  MUXARR_AI_MODE: fallback
  MUXARR_AI_MODEL: gpt-4o-mini
  MUXARR_AI_API_KEY: sk-...
```

Any OpenAI-compatible endpoint works, so nothing has to leave your machine:

```yaml
environment:
  MUXARR_AI_MODE: fallback
  MUXARR_AI_BASE_URL: http://ollama:11434/v1
  MUXARR_AI_MODEL: qwen2.5:7b
  # no API key needed
```

### Modes

| Mode | Behaviour |
| --- | --- |
| `off` | Never calls out. The default. |
| `fallback` | Calls only when the filename rules found nothing, or left a track's language as `und`. Costs nothing on the imports that already work. |
| `always` | Calls on every import; a valid answer wins. |
| `verify` | Calls on every import but **keeps the filename answer**, logging any disagreement. Use it to judge a model against your own library before trusting it. |

### What is sent

One request per import, containing only **names**:

- the video's filename
- the filenames of other videos in the same folder
- the candidate sidecar paths, *relative to the release folder*, with byte sizes
- the season/episode numbers, when Sonarr supplied them

Never the contents of any file, never an absolute path — so nothing about your
library layout above the release folder is disclosed either.

### What it is allowed to decide

The reply is treated as untrusted input:

- a proposed file must be one muxarr already listed on disk; the model cannot
  introduce a path, and a reply naming anything else is discarded
- whether a track is audio or subtitles comes from its extension, not the model
- an unrecognised language becomes `und` rather than a guess
- track names and dub tags are stripped of control characters and length-capped

If the provider is slow, unreachable, or answers with nonsense, muxarr logs a
warning and uses the filename result. An import is never failed because an API
call was.

Tracks the model chose are marked in the history, and the operation detail spells
out which file each one came from and that the provider identified it — so an AI
decision is never something you have to take on faith.

### Track names

The name a player shows in its track menu (`--track-name`) is normally built
from the filename: `Russian (Dublyajnaya, SDH)`. That is accurate but literal —
it can only repeat tokens that were already in the path.

`MUXARR_AI_NAME_TRACKS: true` hands the labelling to the provider:

```yaml
environment:
  MUXARR_AI_MODE: fallback
  MUXARR_AI_MODEL: gpt-4o-mini
  MUXARR_AI_NAME_TRACKS: "true"
```

It changes two things. The provider is now consulted on **every** import, not
only the ones the filenames could not settle — so a release that used to cost
nothing now costs a request. And when the filenames did settle the selection,
only the names come back from the reply: which files are embedded, their
languages and their forced/SDH flags all still come from disk. The model can
relabel a track, never swap one.

It does nothing in `off` mode, and nothing in `verify` mode, which stays a
shadow mode that writes no decision of its own.

## Troubleshooting

Start with the logs. muxarr writes one line per import saying what it decided
and why, and the same reasoning is in the UI under each row. `docker logs
muxarr` and `GET /v1/system` answer most questions between them.

**Every import is skipped, and the reason mentions read roots.**
The paths Radarr/Sonarr handed over do not exist inside the muxarr container, or
exist at a different path. Both sides must mount the same library at the same
path. Check with `docker exec muxarr ls <the path from the log line>`, and make
sure `MUXARR_READ_ROOTS` covers both the download and the library path.

**`worker_alive` is `false` and jobs pile up in `pending`.**
The worker process is not running or cannot reach the database. It heartbeats
every 5s and is considered stale after 30s. Look for worker lines in the
container logs; a crash loop usually means `/config` is not writable by
`PUID:PGID`.

**Imports fail after roughly a minute, and Radarr/Sonarr report a script error.**
The reverse proxy is cutting the long poll. nginx's `proxy_read_timeout` must be
greater than `MUXARR_MAX_POLL_WAIT`; if you put your own proxy in front of
muxarr, raise its read timeout too.

**`required binary not found on PATH: mkvmerge`.**
Only relevant outside the official image, which ships mkvtoolnix. Install
`mkvtoolnix` wherever the worker runs — the API does not need it.

**The muxed file lands with the wrong owner, or the mux fails on permissions.**
`PUID`/`PGID` must match the uid that owns your library, the same values your
\*arr containers use. muxarr creates the output file itself.

**Nothing happens at all on import.**
Check that the shim is actually wired up: *Settings → Media Management → show
Advanced → Importing → Import Using Script*, with the path pointing at
`/config/scripts/muxarr-import-radarr.sh` (or `-sonarr.sh`), and that the shims
volume is mounted. `docker exec sonarr ls /config/scripts` should list them.

**The output is missing a sidecar you expected.**
Open the import in the UI. Rejected sidecars are listed with the reason —
usually de-duplication (`MUXARR_DEDUPE`), an image-subtitle or undetermined
-language skip, or the track cap (`MUXARR_MAX_TRACKS`). If the reason is that
nothing was found at all, the layout may be one the filename rules cannot read;
try [AI mode](#ai-mode).

**AI mode is enabled but nothing changes.**
In `fallback` mode the model is only consulted when the filename rules came up
short, which is the point. Grep the logs for `infra.ai` to see whether it was
called and what it replied; in `verify` mode it is called every time but never
allowed to change the outcome.

## Upgrading

Pin a version tag rather than `latest`, so a restart never changes the version
underneath you:

```yaml
image: ghcr.io/zxibizz/muxarr:0.9.1
```

The published tags are:

| Tag | Moves to | Use it if |
| --- | --- | --- |
| `0.9.1` | nothing, ever | You want restarts to be boring. Recommended |
| `0.9` | the newest `0.9.x` | You want patch fixes without thinking about it |
| `latest` | the newest stable release | You do not mind a major upgrade arriving on a restart |
| `beta` | the newest prerelease | You are testing a release candidate |

`beta` and `latest` never point at the same image: a prerelease is only ever
published as `beta` and its exact version, and never moves `latest`, `0.9` or
`0`.

Then:

1. Read the [changelog](CHANGELOG.md) for the versions you are crossing.
2. Back up `/config/muxarr.db` if the history matters to you.
3. Pull the new tag and recreate the container. Migrations run automatically on
   every start, before the API or worker come up.
4. The shims are republished from the image on every start, so the \*arr
   containers pick up the new ones with no action — as long as they depend on
   muxarr being *healthy* and the shims volume is not mounted over.

Downgrading across a migration is not supported: bring the old database back
from your backup instead.

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

Or the whole stack with hot reload on both sides, in a single container:

```sh
docker compose -f compose.dev.yaml up --build
```

Tests needing real `mkvmerge`/`ffmpeg` are marked and skipped when those tools
are absent. The dev image has them, so the full suite runs there:

```sh
docker compose -f compose.dev.yaml run --rm muxarr pytest -q
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

## Contributing

Bug reports, feature requests and pull requests are welcome. See
[CONTRIBUTING.md](CONTRIBUTING.md) for the development loop and the handful of
architectural rules the test suite enforces, and
[SECURITY.md](SECURITY.md) for the threat model and how to report a
vulnerability privately.

## Licence

[MIT](LICENSE).
