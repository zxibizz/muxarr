# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The HTTP surface used by the shims — `POST /v1/import` and
`GET /v1/jobs/{id}/protocol` — is treated as the public API for versioning
purposes. A shim from an older release must keep working against a newer daemon
within the same major version.

## [Unreleased]

## [0.10.2] - 2026-09-24

### Changed

Now bump_version.py also handles `openapi.json` and `uv.lock`

## [0.10.1] - 2026-09-24

### Added

- **Run the API and the worker as separate containers.** One image, three modes:
  `MUXARR_MODE=all` (the default, unchanged), `web` (API and UI, never muxes)
  and `worker` (muxes, serves nothing). `compose.split.example.yaml` wires the
  two up with Postgres. The web container runs the migrations; the worker waits
  for them. In worker mode the healthcheck reads the worker's heartbeat.
- **Postgres support.** `MUXARR_DB_URL=postgresql+asyncpg://...` (a bare
  `postgres://` URL works too). An unsupported URL now fails at startup, without
  echoing the password.
- `python -m src.cli wait-for-schema` and `python -m src.cli worker-alive`, which
  the container uses for the above.
- **Keep only the languages you want.** `MUXARR_KEEP_AUDIO_LANGUAGES` and
  `MUXARR_KEEP_SUBTITLE_LANGUAGES` (also editable in the UI) strip every other
  audio or subtitle track from the source during the remux, and stop sidecars
  in those languages from being embedded or handed back to *arr. A release
  with no sidecars is now remuxed when there is something to strip. An import
  that would lose every audio track is left to *arr instead. Each operation
  lists the tracks it removed (a new `removed_tracks` column, migrated on start).
- **A redesigned web UI.** A sidebar layout with a live worker indicator, a
  **System** page (worker, queue, daemon), icon-led stat cards, compact track
  chips, and an operation drawer split into Overview, Tracks and What happened.
  Rows open from the keyboard, the history search is debounced, clearing the
  history asks first, and a banner on every page says when the worker is
  offline. Settings are laid out as label-and-control rows split into tabs (a
  burger menu on phones, the open tab kept in `?section=`), a tab holding
  unsaved edits is marked, a pinned variable is named next to its field, and
  changes collect in a sticky save bar instead of saving on a button at the
  bottom of the page.
- **Every passed-over sidecar carries a reason code** (`code` on
  `rejected_tracks` in the JSON API: `already_present`, `language_not_kept`,
  `file_missing`, ...), which the UI shows as a label. Older rows keep their
  text reason and a `null` code.
- `python -m src.cli openapi` prints the API schema; the UI's types are
  generated from it.

### Changed

- **Authentication works the way it does in the \*arr apps.** `MUXARR_TOKEN`
  is gone, replaced by two separate credentials:
  - an **API key** for Radarr/Sonarr, generated on first start and shown (and
    regenerable) under Settings → Security, or pinned with `MUXARR_API_KEY`.
    The shims now read `MUXARR_API_KEY` and send it as `X-Api-Key`;
    `Authorization: Bearer` is still accepted from older shims.
  - a **UI login** (username and password, 30-day session cookie), created on
    the first visit or pinned with `MUXARR_USERNAME`/`MUXARR_PASSWORD`.

  `MUXARR_AUTH_METHOD` (`forms` or `external`, for an authenticating reverse
  proxy) and `MUXARR_AUTH_REQUIRED` (`enabled` or
  `disabled_for_local_addresses`) are editable in the UI too. There is no longer
  an unauthenticated mode, and `/healthz` no longer reports `auth_required`.
- **`Dockerfile.all-in-one` is now `Dockerfile`** (its s6 overlay moved to
  `cicd/containers/prod/`). Only matters if you build the image yourself.
- History search ignores case on every database (it already did on SQLite).
- The UI now runs on React 19, Mantine 9 and TanStack Query, which replaces
  three hand-rolled polling loops.
- The README was cut to what a new user needs; the configuration reference,
  troubleshooting, upgrading and architecture moved to `docs/`.
- The two shims are rendered from one template (`scripts/src/`), so a fix can
  no longer land in one and not the other. Their behaviour is unchanged.
- `make` targets for the common loops, a pre-commit config, `.editorconfig`, and
  `ruff format` enforced in CI.

### Fixed

- **File sizes are stored as 64-bit integers** (migrated on start), which
  Postgres needs for anything over 2 GiB.
- **A sidecar that disappeared before muxing is no longer handed back to *arr**
  as an extra file.
- **An `MUXARR_AI_API_KEY` set in the environment now pins the key field** in
  the UI; it used to be tied to `MUXARR_AI_MODE` instead, so saving could fail
  with a 409.
- **The version guard now covers the image tags pinned in the docs**, which had
  drifted to three different releases.
- **Sidecars in a Matroska container (`.mka`) are now addressed by their real
  track number.** mkvmerge keeps a file's own numbering, so a `.mka` whose track
  is not numbered 0 had its language, title and flags silently ignored, and the
  import was deferred after a full remux had already run.
- **A sidecar mkvmerge can read no track out of is now rejected up front**,
  with the reason recorded against it, instead of sinking the whole import.
  The remaining tracks are embedded as normal.
- **mkvmerge's diagnostics are no longer discarded.** It writes warnings to
  stdout and only errors to stderr, so the message explaining a bad mux never
  reached the log.
- **The image no longer fails to start after the Python 3.14 base-image bump.**
  The dependencies were still installed for Python 3.11, so the 3.14
  interpreter could not import any of them. They are now installed on the same
  base image the container runs, and the build fails if they don't import.

### Changed

- Runtime is Python 3.14. Frontend toolchain moved to Vite 8, Vitest 5,
  ESLint 10 and jsdom 30, and the router to react-router 7.

## [0.9.2] - 2026-09-22

### Added

- **Every history entry now carries the log of the import that produced it.**
  Opening an operation shows what Muxarr did, in order: what the source already
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
  the scratch directory stay environment-only: they decide what Muxarr may
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
  names a file Muxarr already listed on disk, the track kind still comes from
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

[Unreleased]: https://github.com/zxibizz/muxarr/compare/v0.10.2...HEAD
[0.10.2]: https://github.com/zxibizz/muxarr/releases/tag/v0.10.2
[0.10.1]: https://github.com/zxibizz/muxarr/releases/tag/v0.10.1
[0.9.2]: https://github.com/zxibizz/muxarr/releases/tag/v0.9.2
[0.9.1]: https://github.com/zxibizz/muxarr/releases/tag/v0.9.1
[0.9.0]: https://github.com/zxibizz/muxarr/releases/tag/v0.9.0
