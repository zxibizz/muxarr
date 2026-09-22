<!-- Keep it to one topic. See CONTRIBUTING.md and AGENTS.md. -->

## What this changes

<!-- And why. Link the issue if there is one: Fixes #123 -->

## How it was verified

<!--
Which of these you ran, and anything you exercised by hand.
Note if the mkvmerge/ffmpeg tests skipped on your machine.
-->

- [ ] `uv run ruff check .`
- [ ] `uv run python -m mypy`
- [ ] `uv run pytest -q`
- [ ] `npm run lint && npm run test && npm run build` (if the frontend changed)

## Checklist

- [ ] New behaviour has a test; a bug fix has the test that fails without it
- [ ] `CHANGELOG.md` updated under `Unreleased`
- [ ] README config table updated (if an environment variable was added)
- [ ] A migration is included and its downgrade tested (if the schema changed)
- [ ] The layering rules in AGENTS.md still hold

## Anything a reviewer should look at closely

<!-- Trade-offs, things you were unsure about, anything you want a second opinion on. -->
