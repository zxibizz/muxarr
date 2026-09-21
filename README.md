# muxarr

Embeds external audio and subtitle tracks into video containers at the moment
Radarr/Sonarr import a download, using the **Import Using Script** hook.

When a release ships `Subs/2_English.srt` or a separate `.ac3` dub alongside the
video, muxarr remuxes them into a single MKV as the file lands in your library —
so the tracks are embedded rather than scattered as sidecars, and the filename
reflects the tracks that are actually in the file.

## Design rules

- **Stream-copy only.** No transcoding, ever. A mux costs one sequential read
  and one sequential write.
- **The download folder is read-only.** muxarr never writes, renames or deletes
  anything on the source side, in any transfer mode. Cleanup of the original
  stays with your download client's Completed Download Handling.
- **Fail safe.** Any error at all degrades to `DeferMove`, and Radarr/Sonarr
  perform a completely normal import. The shim always exits 0.
- **Staging lives in the destination directory**, so the final step is an atomic
  rename rather than a cross-device copy.

## Layout

| Path | Role |
| --- | --- |
| `src/muxarr/probe.py` | container inspection via `mkvmerge -J`, `ffprobe` fallback |
| `src/muxarr/discovery.py` | find sidecar files next to the download |
| `src/muxarr/language.py` | infer language + forced/SDH flags from filenames |
| `src/muxarr/selection.py` | drop tracks already present, order the rest |
| `src/muxarr/mux.py` | build and run the `mkvmerge` command |
| `src/muxarr/placement.py` | free-space check, atomic placement, permissions |
| `src/muxarr/cli.py` | `muxarr inspect` / `plan` / `mux` |

## Development

```sh
uv venv --python 3.11 .venv
uv pip install -e '.[dev]'
.venv/bin/ruff check .
.venv/bin/mypy
.venv/bin/pytest
```

Tests that need real `mkvmerge`/`ffmpeg` binaries are marked and skipped when
those tools are absent:

```sh
brew install mkvtoolnix ffmpeg   # optional, enables the integration tests
```

## Requirements

`mkvtoolnix` (for `mkvmerge`) is required at runtime. `ffmpeg` is optional and
used only as a probe fallback.
