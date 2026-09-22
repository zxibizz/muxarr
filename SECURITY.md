# Security Policy

## Supported versions

muxarr is pre-1.0. Only the latest released tag receives fixes.

| Version | Supported |
| --- | --- |
| latest release | yes |
| anything older | no |

## Reporting a vulnerability

Please report privately via GitHub's
[private vulnerability reporting](https://github.com/zxibizz/muxarr/security/advisories/new)
rather than opening a public issue.

Include what you did, what happened, and the version from `GET /healthz`. A
proof of concept helps but is not required. Expect an acknowledgement within a
week.

## Threat model

muxarr is designed to run on a private network alongside Radarr/Sonarr, and its
security properties are sized for that:

- **The API is not hardened for the public internet.** Authentication is a
  single shared bearer token (`MUXARR_TOKEN`), there is no rate limiting, no
  account model and no audit log. Do not port-forward it. If you need remote
  access, put it behind a VPN or an authenticating reverse proxy.
- **An authenticated caller can cause writes inside `MUXARR_READ_ROOTS`.**
  That is the feature: the caller names a destination and muxarr writes a muxed
  file there. Keep `MUXARR_READ_ROOTS` as narrow as your library actually needs,
  and treat the token as a credential to your media storage.
- **Unauthenticated mode exists and is loud about it.** If `MUXARR_TOKEN` is
  unset, every endpoint except `/healthz` is open and the daemon logs a warning
  at startup. It is intended for a host-only bind, not a shared network.

Things that are in scope and that we do want to hear about:

- Escaping `MUXARR_READ_ROOTS` — reading or writing a path outside the
  configured roots, including via symlinks, `..`, or the staging/rename path.
- Command injection into `mkvmerge`/`ffprobe` (every invocation is an argv list
  with no shell, so this would be a real bug).
- Bypassing the bearer token check, or leaking it via an endpoint, a log line or
  an error message.
- Anything that lets an unauthenticated caller reach the worker.

Out of scope:

- Exposing muxarr to the internet and being reached without a token.
- Denial of service from an authenticated caller queueing many jobs.
- Vulnerabilities in `mkvtoolnix`, `ffmpeg`, Radarr or Sonarr themselves.
