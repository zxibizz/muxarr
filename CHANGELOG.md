# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The HTTP surface used by the shims — `POST /v1/import` and
`GET /v1/jobs/{id}/protocol` — is treated as the public API for versioning
purposes. A shim from an older release must keep working against a newer daemon
within the same major version.

## [Unreleased]

## [0.9.2] - 2026-09-22

### Added

- **Every history entry now carries the log of the import that produced it.**
  Opening an operation shows what muxarr did, in order: what the source already
  contained, which sidecars were found and how each was identified, the verdict
  and reason for every candidate, the remux itself, and the outcome — followed
  by the full log it was distilled from. Kept per import and trimmed with the
  history, capped by `MUXARR_OPERATION_LOG_MAX_ENTRIES` (default 500, `0`
  disables the capture). Needs a migration, which the container runs on start.
- **In-flight imports are visible while they run.** The history page lists jobs
  that have not settled yet and follows their log live, which is also the only
  way to read a job that failed before it could write a history entry. Backed
  by `GET /v1/jobs` and `GET /v1/jobs/{id}/detail`.
- **AI-written track names** (`MUXARR_AI_NAME_TRACKS`, default off). The label a
  player shows for an embedded track is normally assembled from the filename;
  with this on, the provider writes it instead. It only relabels: which files
  are embedded, their languages and their forced/SDH flags still come from disk
  whenever the filenames were conclusive. The provider is consulted on every
  import as a result, so this costs a request per import. Ignored in `verify`
  mode.

### Changed

- Embedded tracks are recorded as structured data — kind, label, language,
  flags, file and how it was identified — instead of a display string with an
  uninformative `[ai]` suffix. The UI marks an AI-identified track with a dot
  and explains it in full in the operation detail. Entries written by earlier
  versions still render. `added_tracks` and `rejected_tracks` in
  `GET /v1/history` and `GET /v1/jobs/{id}` are objects rather than strings;
  the shim protocol on `GET /v1/jobs/{id}/protocol` is unchanged.

### Fixed

- An AI-identified track whose reply carried no title was embedded with no name
  at all. It now falls back to the name built from the language and flags, so an
  AI-selected track is never labelled worse than a filename-selected one.

## [0.9.1] - 2026-09-22

### Added

- A **Settings page** in the web UI. Track selection, muxing, queue and
  retention, AI and the log level can now be changed from the browser and take
  effect within seconds — in both the API and the worker process, with no
  restart. Read roots, the database URL, the bind address, the API token and
  the scratch directory stay environment-only: they decide what muxarr may
  touch and how it is reached.
  A variable that is actually set in the environment **wins and locks its
  field**, which is rendered read-only and names the variable, so an existing
  compose file remains the source of truth for whatever it configures.
  Backed by `GET`/`PATCH /v1/settings`; overrides live in a new `app_settings`
  table, so this needs a migration (the container runs it on start).
- A **Test provider** button for the AI settings, backed by
  `POST /v1/settings/ai/test`. It probes the endpoint, model and key currently
  typed into the form — so a key can be checked before it is saved — and
  reports the provider's own error when it fails. The stored key is used when
  the field is left blank. The AI key is write-only over HTTP: the daemon
  reports whether one is set and never sends it back.
- A `beta` image tag, moved by every prerelease. `latest` continues to track
  stable releases only.
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

[Unreleased]: https://github.com/zxibizz/muxarr/compare/v0.9.2...HEAD
[0.9.2]: https://github.com/zxibizz/muxarr/releases/tag/v0.9.2
[0.9.1]: https://github.com/zxibizz/muxarr/releases/tag/v0.9.1
[0.9.0]: https://github.com/zxibizz/muxarr/releases/tag/v0.9.0
