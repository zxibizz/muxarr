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
  completely normal import. The shim always exits 0.
- **Staging lives in the destination directory**, so the final step is an atomic
  rename rather than a cross-device copy.

## How it fits together

```
Radarr/Sonarr  --exec-->  muxarr-import.sh  --HTTP-->  muxarr daemon
 (import)                 (in *arr container)          (owns mkvmerge)
      ^                                                      |
      +---------- [MoveStatus] RenameRequested <-------------+
```

The shim is dependency-free POSIX `sh` (needs only `curl` or `wget`). All the
heavy dependencies live in the muxarr container.

## Web UI

The daemon serves a React/Mantine UI on the same port (default
<http://localhost:8710>) showing every import it has been handed — including the
ones it skipped, which is usually the question you actually have.

Each row expands into the full decision: the paths involved, which tracks were
embedded, and which sidecars were passed over *and why*. Set `MUXARR_DATA_DIR`
to a mounted volume or the history is in memory and dies with the container; the
UI shows a warning banner when that is the case.

If `MUXARR_TOKEN` is set, the UI asks for it once and keeps it in the browser's
local storage.

## Setup

1. **Deploy.** Copy `compose.example.yaml` to `compose.yaml`, set `MUXARR_TOKEN`
   in a `.env` file, and adjust the volume paths.

   > Every media path must be mounted at the **same path** in the \*arr
   > containers and in muxarr. Radarr/Sonarr pass absolute paths; if they mean
   > different things in each container, muxarr rejects them and defers.

2. **Mount the shim** into the \*arr container (the example compose does this)
   and make sure it is executable.

3. **Configure Radarr/Sonarr.** Settings → Media Management → *show Advanced* →
   Importing:
   - tick **Import Using Script**
   - set **Import Script Path** to `/config/scripts/muxarr-import.sh`
   - leave **Import Extra Files** as you had it; muxarr suppresses the duplicate
     sidecar copy only for imports it actually muxed

4. **Check it.** `curl http://muxarr:8710/healthz` from inside the \*arr
   container, then import something and watch the muxarr logs.

## Configuration

All settings are environment variables on the **daemon**:

| Variable | Default | Meaning |
| --- | --- | --- |
| `MUXARR_READ_ROOTS` | *required* | Colon-separated paths muxarr may read |
| `MUXARR_TOKEN` | *unset* | Bearer token; unauthenticated if unset |
| `MUXARR_HOST` / `MUXARR_PORT` | `0.0.0.0` / `8710` | Bind address |
| `MUXARR_MAX_CONCURRENT` | `1` | Simultaneous remuxes |
| `MUXARR_SCRATCH_DIR` | destination dir | Only change for NFS/SMB/union FS |
| `MUXARR_DEDUPE` | `language_codec` | `off`, `language`, `language_codec` |
| `MUXARR_SKIP_IMAGE_SUBTITLES` | `false` | Exclude PGS/VobSub |
| `MUXARR_SKIP_UNDETERMINED` | `false` | Exclude tracks with unknown language |
| `MUXARR_MAX_TRACKS` | `24` | Cap on embedded tracks |
| `MUXARR_PRESERVE_OWNERSHIP` | `true` | chown output to match the source |
| `MUXARR_DATA_DIR` | *unset* | Where `history.db` lives; unset = in-memory |
| `MUXARR_HISTORY_RETENTION_DAYS` | `90` | Pruned on startup; `0` keeps everything |
| `MUXARR_WEB_DIR` | `/app/web` | Built UI to serve; skipped if absent |
| `MUXARR_LOG_LEVEL` | `INFO` | |

And on the **shim**: `MUXARR_URL`, `MUXARR_TOKEN`, `MUXARR_TIMEOUT`.

## CLI

```sh
muxarr inspect video.mkv          # list tracks in a container
muxarr plan   video.mkv           # show what would be embedded, writes nothing
muxarr mux    video.mkv --out out.mkv
muxarr serve                      # run the daemon
```

## Development

```sh
uv venv --python 3.11 .venv
uv pip install -e '.[dev]'
.venv/bin/ruff check .
.venv/bin/mypy
.venv/bin/python -m pytest
```

Tests needing real `mkvmerge`/`ffmpeg` are marked and skipped when those tools
are absent. The container has them, so the full suite runs there:

```sh
docker build --target test -t muxarr:test .
docker run --rm muxarr:test
```

### Frontend

The UI lives in `web/` (React 18, Mantine 7, Vite) and is built automatically by
the Docker image. For a local dev loop you need Node 18+:

```sh
muxarr serve &          # API on :8710
cd web && npm install && npm run dev
```

`vite.config.ts` proxies `/v1` and `/healthz` to the daemon.

## Requirements

`mkvtoolnix` is required at runtime. `ffmpeg` is optional, used as a probe
fallback and to generate test fixtures.
