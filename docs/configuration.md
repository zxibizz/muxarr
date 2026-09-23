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

## Shim

Set these in the Radarr/Sonarr container, where the shim runs.

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
