# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The HTTP surface used by the shims — `POST /v1/import` and
`GET /v1/jobs/{id}/protocol` — is treated as the public API for versioning
purposes. A shim from an older release must keep working against a newer daemon
within the same major version.

## [Unreleased]

### Added

- A `beta` image tag, moved by every prerelease. `latest` continues to track
  stable releases only.

### Added

- Optional **AI mode** for sidecar discovery (`MUXARR_AI_MODE`, off by default).
  When a release layout defeats the filename rules, a model behind any
  OpenAI-compatible endpoint can match and label the sidecars instead. Four
  modes: `off`, `fallback` (only when the filename rules come up short),
  `always`, and `verify` (consult but keep the filename answer, logging
  disagreements). Configured by `MUXARR_AI_BASE_URL`, `MUXARR_AI_API_KEY`,
  `MUXARR_AI_MODEL`, `MUXARR_AI_TIMEOUT` and `MUXARR_AI_MAX_ENTRIES`.
  Only file and folder *names* are sent, relative to the release folder; never
  file contents and never absolute paths. A proposal is only accepted if it
  names a file muxarr already listed on disk, the track kind still comes from
  the extension, and an unrecognised language falls back to `und`. Any provider
  failure degrades to the filename result rather than failing the import.
  AI-chosen tracks are marked `[ai]` in the history.

## [0.9.0] - 2026-09-22

First public release. Pre-1.0 while the upgrade path and the published image
get a soak in the wild; the shim protocol is already considered stable.

### Added

- Embeds external audio and subtitle sidecars into a single MKV during a
  Radarr/Sonarr import, via the *Import Using Script* hook. Stream-copy only.
- POSIX `sh` shims for Radarr and Sonarr, published into a shared volume by the
  container on every start.
- Split API/worker daemon: the API queues and reports, the worker is the only
  process that muxes.
- Language, forced-subtitle, SDH and dub-variant inference from sidecar
  filenames, with de-duplication modes (`off`, `language`, `language_codec`).
- Web UI on the same port: import history with filters and search, per-import
  decision detail including rejected sidecars and the reason, summary stats,
  and a system drawer with worker liveness and queue depth.
- Bearer-token authentication (`MUXARR_TOKEN`), optional and loud when unset.
- Path guard restricting all reads and writes to `MUXARR_READ_ROOTS`.
- Job and history retention, swept by the worker.
- `GET /healthz` and `GET /v1/system` for liveness and queue depth.
- Structured logging via loguru, with `MUXARR_LOG_JSON` for log shippers.
- Multi-arch (amd64, arm64) container image published to
  `ghcr.io/zxibizz/muxarr`.
- MIT licence, contribution and security policies, and CI running ruff, mypy,
  pytest and the frontend build.

[Unreleased]: https://github.com/zxibizz/muxarr/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/zxibizz/muxarr/releases/tag/v0.9.0
