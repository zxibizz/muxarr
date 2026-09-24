# Configuration

Most settings can be changed from the **Settings** page in the web UI, which
takes effect within a few seconds — no restart, in either process. The rest are
environment variables on the **daemon**.

A variable that is actually set in your compose file **wins and locks the
field**: the UI renders it read-only and names the variable, so compose stays
the single source of truth for anything you have configured there. Leave a
variable out to manage that setting from the UI instead.

![The settings page, with the fields pinned by the environment called out](images/settings.png)

## Daemon

| Variable | Default | UI | Meaning |
| --- | --- | --- | --- |
| `MUXARR_READ_ROOTS` | *required* | | Colon-separated paths Muxarr may read |
| `MUXARR_API_KEY` | *generated* | | Pins the API key; unset, one is generated on first start and shown in Settings → Security — see [Authentication](#authentication) |
| `MUXARR_AUTH_METHOD` | `forms` | | `forms` (login page) or `external` (a reverse proxy signs users in) — see [Authentication](#authentication) |
| `MUXARR_AUTH_REQUIRED` | `enabled` | ✓ | `enabled` or `disabled_for_local_addresses` |
| `MUXARR_LOCAL_NETWORKS` | loopback, RFC 1918, ULA, link-local | | Comma-separated addresses and CIDRs that `disabled_for_local_addresses` lets in. Replaces the default list |
| `MUXARR_TRUSTED_PROXIES` | *unset* | | Comma-separated addresses and CIDRs of reverse proxies whose `X-Forwarded-For` is believed — see [Behind a reverse proxy](#behind-a-reverse-proxy) |
| `MUXARR_USERNAME` / `MUXARR_PASSWORD` | *unset* | | Set together to pin the UI login; rewritten into the database on every start |
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
| `MUXARR_KEEP_AUDIO_LANGUAGES` | *unset* | ✓ | Comma-separated languages (`eng,rus`, `en`, `russian`) to keep. Every other audio track is stripped from the source and not embedded from sidecars; list `und` to keep untagged tracks, `original` for the movie's or series' original language as \*arr reports it. An import that would lose all its audio is left to *arr |
| `MUXARR_KEEP_SUBTITLE_LANGUAGES` | *unset* | ✓ | The same, for subtitles, forced ones included |
| `MUXARR_SKIP_TAGS` | *unset* | ✓ | Comma-separated \*arr tags. A movie or series carrying any of them is imported as though Muxarr were absent |
| `MUXARR_REQUIRE_TAGS` | *unset* | ✓ | Comma-separated \*arr tags. When set, only a movie or series carrying one of them is muxed |
| `MUXARR_MUX_TIMEOUT` | `14400` | ✓ | Seconds before a single mkvmerge run is killed |
| `MUXARR_FREE_SPACE_FACTOR` | `1.05` | ✓ | Free space required before a mux, as a multiple of the expected output |
| `MUXARR_SUB_CHARSET` | *unset* | ✓ | Force a `--sub-charset` for text subtitles, e.g. `windows-1251` |
| `MUXARR_PRESERVE_OWNERSHIP` | `true` | ✓ | chown output to match the source |
| `MUXARR_DB_URL` | `sqlite+aiosqlite:////config/muxarr.db` | | History, job queue and UI settings. `postgresql+asyncpg://user:pass@host:5432/db` (or plain `postgres://…`) for Postgres, which a split deployment needs — see [Container modes](#container-modes) |
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
| `TZ` | `UTC` | | Time zone for log timestamps, e.g. `Europe/Berlin`; the UI always shows your browser's |
| `MUXARR_MODE` | `all` | | Container image only: `all`, `web` or `worker` — see [Container modes](#container-modes) |
| `MUXARR_URL_BASE` | *unset* | | Container image only: serve the UI and API under a sub-path such as `/muxarr` — see [URL base](#url-base) |

Read roots, the database URL, the bind address, the API key, the login, the
auth method, the local and proxy networks and the scratch directory stay
environment-only on purpose: they decide what Muxarr is allowed to touch and
who is let in, which is not something an HTTP request should be able to move.
(The API key can still be *regenerated* from the UI when the environment does
not pin it.)

The AI key is write-only over HTTP. The UI can set or clear it and the daemon
will say whether one is stored, but it is never sent back to the browser.

## Authentication

Muxarr follows the \*arr apps: two independent ways in.

- **The API key** is what Radarr and Sonarr present, as `X-Api-Key` (the
  legacy `Authorization: Bearer` header is accepted too). One is generated on
  first start and shown under Settings → Security, where it can be copied or
  regenerated. Set `MUXARR_API_KEY` to pin it instead, for example to share one
  value through a `.env` file. The key always works, whatever the settings below
  say, and scripts should always send it.
- **The UI login** is a username and password. The first visit to a fresh
  instance asks you to create them; until then the setup page is open to
  whoever reaches it first, so do that before exposing the port. A sign-in
  lasts 30 days from the last visit. Changing the login signs every other
  browser out.

`MUXARR_USERNAME` and `MUXARR_PASSWORD` pin the login: the Settings page then
cannot change it, and the stored account is overwritten with them on every
start. That is also how a forgotten password is reset — set both, restart,
then remove them again if you would rather manage it from the UI.

**Method** `external` skips the login page entirely, for an authenticating
reverse proxy (Authelia, Authentik, oauth2-proxy, …) in front of Muxarr. It
opens the whole UI and API to anything that reaches port 8710 *without* going
through that proxy, including every container on the same Docker network. As in
Sonarr, it can only be chosen with `MUXARR_AUTH_METHOD=external`: the Settings
page shows the method but cannot switch the login off.

**Required** `disabled_for_local_addresses` skips the login for callers on
loopback, RFC 1918, ULA and link-local addresses. Set `MUXARR_LOCAL_NETWORKS`
to choose the networks yourself, for example `100.64.0.0/10` for a Tailscale
tailnet; the list replaces the default rather than adding to it. Docker
networks are local by default, and so is a reverse proxy on one — see below.

### Behind a reverse proxy

Muxarr judges a caller by the address it connects from. Behind Traefik, SWAG,
Caddy or nginx that is the proxy's, usually a Docker address, so with
`disabled_for_local_addresses` *every* request would look local, the ones from
the internet included. List the proxy in `MUXARR_TRUSTED_PROXIES`:

```yaml
MUXARR_TRUSTED_PROXIES: 172.18.0.2   # or the proxy network's subnet, 172.18.0.0/16
```

Muxarr then believes that proxy's `X-Forwarded-For` and judges the caller it
names instead. The header is read from the right and only through trusted hops,
so what a client writes into it itself is never taken. A proxy that is not
listed is judged as the caller, as before. The login page and the API key work
the same either way; this only matters for `disabled_for_local_addresses`.

Writes from the browser must carry an `X-Requested-With` header, which the UI
always sends and a cross-site form cannot; the API key is exempt.

### URL base

`MUXARR_URL_BASE=/muxarr` serves the UI and the API under that sub-path, the
way the \*arr apps' URL Base does, for a proxy that routes `example.com/muxarr`
to the container without stripping the prefix. The API also stays at the root,
so the shims keep working with a `MUXARR_URL` that has no base in it; one that
includes it works too.

## What Radarr/Sonarr tell Muxarr

Besides the two paths, the shims forward what \*arr puts in the import script's
environment: the instance name, the movie or series title, its original
language and tags, and \*arr's own URL. The history shows them and links back to
the movie or series when Settings → General → Application URL is set in \*arr.
They also drive `original` in the keep lists and the tag rules above. An import
from an older shim carries none of it: `original` then keeps every language of
its kind, and `MUXARR_REQUIRE_TAGS` defers.

## Container modes

The image runs any part of Muxarr, picked by `MUXARR_MODE`:

| Mode | Runs | Needs |
| --- | --- | --- |
| `all` (default) | nginx on `:8710`, the API, the worker | the media mounts, `/config` |
| `web` | nginx on `:8710`, the API | the database; no media mounts |
| `worker` | the worker | the database, the media mounts |

[compose.example.yaml](../compose.example.yaml) is the single `all` container on
SQLite. [compose.split.example.yaml](../compose.split.example.yaml) runs `web` and
`worker` apart, on Postgres. When split:

- **Give both containers the same environment.** They read the same Settings
  page overrides from the database, and a variable set on only one of them locks
  the field there but not in the other.
- **The web container migrates the database**; the worker waits up to two
  minutes for the schema to catch up, then exits so its restart policy retries.
- **Run exactly one worker.** A starting worker fails every job left `running`,
  on the assumption that it is the worker that died mid-mux.
- **The \*arr containers talk to the web container**, and only the worker needs
  the media mounted at the same paths as the \*arr containers.
- SQLite still works if both containers share one `/config` volume on one host;
  they log a warning, because it does not work across machines.

In worker mode nothing listens on `:8710`; the healthcheck reads the worker's
heartbeat from the database instead.

## Shim

Set these in the Radarr/Sonarr container, where the shim runs.

| Variable | Default | Meaning |
| --- | --- | --- |
| `MUXARR_URL` | `http://muxarr:8710` | Daemon address |
| `MUXARR_API_KEY` | *unset* | Muxarr's API key, from Settings → Security |
| `MUXARR_TIMEOUT` | `14400` | Total seconds to wait for a remux |
| `MUXARR_POLL_WAIT` | `25` | Seconds the daemon holds each poll open |
| `MUXARR_POLL_INTERVAL` | `5` | Back-off after a failed request |
| `MUXARR_MAX_RETRIES` | `10` | Consecutive request failures tolerated |

## AI mode

Muxarr normally matches sidecars by filename: episode markers, language tags and
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

- a proposed file must be one Muxarr already listed on disk; the model cannot
  introduce a path, and a reply naming anything else is discarded
- whether a track is audio or subtitles comes from its extension, not the model
- an unrecognised language becomes `und` rather than a guess
- track names and dub tags are stripped of control characters and length-capped

If the provider is slow, unreachable, or answers with nonsense, Muxarr logs a
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
