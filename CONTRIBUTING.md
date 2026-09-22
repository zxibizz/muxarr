# Contributing to muxarr

Thanks for taking an interest. muxarr sits in the path of someone's media
library, so the bar for correctness is higher than the size of the project
suggests — a bug here does not produce a stack trace, it produces a wrong file
where a good one used to be.

## Before you start

Read [AGENTS.md](AGENTS.md). It is short, and it is the actual contract: the
layering rules, the frozen HTTP surface, and the handful of invariants that the
test suite enforces. Most review comments on a first PR are one of those rules.

## Development setup

```sh
git clone https://github.com/zxibizz/muxarr.git
cd muxarr/services/backend
uv sync
```

You need [uv](https://docs.astral.sh/uv/) and Python 3.11+. `mkvtoolnix` is
required to run the mux tests; `ffmpeg` is optional and used as a probe fallback
and to generate fixtures. Without them, eleven tests skip rather than fail.

The loop:

```sh
uv run ruff check .          # lint
uv run python -m mypy        # strict, src/ only
uv run pytest -q             # ~30s
```

The frontend:

```sh
cd services/frontend
npm install
npm run lint
npm run test
npm run build
```

Or run the whole stack with hot reload on both sides, in one container that
already has mkvtoolnix and ffmpeg:

```sh
docker compose -f compose.dev.yaml up --build
docker compose -f compose.dev.yaml run --rm muxarr pytest -q
```

## The rules that will get a PR sent back

These are enforced by `services/backend/tests/test_architecture.py` and by
review. They are explained in full in [AGENTS.md](AGENTS.md).

- **Dependencies point inward.** `domain/` imports nothing from the other
  layers, `application/` never imports `infrastructure/` or FastAPI,
  `infrastructure/` never imports `api/`.
- **The HTTP contract is frozen.** Shims already deployed in the wild POST
  `/v1/import` and poll `/v1/jobs/{id}/protocol`. Add endpoints; do not rename
  or repurpose those two.
- **`HandleImportUseCase.execute` never raises.** Every unexpected condition
  becomes a `DeferMove`, and Radarr/Sonarr import the file themselves as though
  muxarr were not installed. Failing loudly is the wrong answer here.
- **The download folder is never written to.** There is a parametrised test
  asserting a byte-for-byte snapshot across every transfer mode.
- **New external dependencies go behind a Protocol** in
  `application/interfaces/`, with the adapter in `infrastructure/` and the
  wiring in `core/container.py`.
- **Subprocesses are argv lists.** No `shell=True`, anywhere.
- **The shims stay POSIX sh.** No `[[`, no `local`, no `function name()`; they
  run under dash and busybox ash, and `tests/integration/test_shim.py` greps for
  the banned constructs.
- **Logging is loguru**, with context as keyword arguments:
  `log.info("import settled", job_id=..., status=...)`. Never `%s`.
- **Comments explain why, not what.**

## Database changes

Schema changes need a migration:

```sh
cd services/backend
uv run alembic revision --autogenerate -m "describe the change"
uv run alembic upgrade head
```

Check the generated file by hand — autogenerate does not know about SQLite's
`ALTER TABLE` limits, and existing users will run your migration against a
database with real data in it. Test the downgrade too.

## Pull requests

- One topic per PR.
- `ruff`, `mypy` and `pytest` all green; CI runs the same three plus the
  frontend build.
- New behaviour comes with a test. Bug fixes come with the test that fails
  without the fix.
- Add a line to the `Unreleased` section of [CHANGELOG.md](CHANGELOG.md).
- Update the config table in the README if you add an environment variable.

## Reporting bugs

Open an issue with the bug template. The single most useful thing you can
include is the output of `GET /v1/system` and the muxarr logs around the
import — the daemon logs the decision it made and why.

Security issues go to [SECURITY.md](SECURITY.md) instead, not to the issue
tracker.
