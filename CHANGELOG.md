# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The HTTP surface used by the shims — `POST /v1/import` and
`GET /v1/jobs/{id}/protocol` — is treated as the public API for versioning
purposes. A shim from an older release must keep working against a newer daemon
within the same major version.

## [Unreleased]

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
