# Security Policy

## Supported versions

Muxarr is pre-1.0. Only the latest released tag receives fixes.

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

Muxarr is designed to run on a private network alongside Radarr/Sonarr, and its
security properties are sized for that:

- **The API is not hardened for the public internet.** Authentication is an
  API key for scripts and a single UI account; there is no rate limiting on
  sign-in and no audit log. Do not port-forward it. If you need remote access,
  put it behind a VPN or an authenticating reverse proxy.
- **An authenticated caller can cause writes inside `MUXARR_READ_ROOTS`.**
  That is the feature: the caller names a destination and Muxarr writes a muxed
  file there. Keep `MUXARR_READ_ROOTS` as narrow as your library actually needs,
  and treat the API key and the UI login as credentials to your media storage.
- **The login can be waived, deliberately.** `MUXARR_AUTH_METHOD=external`
  trusts a reverse proxy in front, and
  `MUXARR_AUTH_REQUIRED=disabled_for_local_addresses` trusts private addresses.
  Either one opens the API to whatever reaches the port on those terms.
- **A fresh instance's setup page is open** until the first account is
  created. Create it before exposing the port, or pin it with
  `MUXARR_USERNAME`/`MUXARR_PASSWORD`.

Things that are in scope and that we do want to hear about:

- Escaping `MUXARR_READ_ROOTS` — reading or writing a path outside the
  configured roots, including via symlinks, `..`, or the staging/rename path.
- Command injection into `mkvmerge`/`ffprobe` (every invocation is an argv list
  with no shell, so this would be a real bug).
- Bypassing the API key or session check, cross-site request forgery against
  the UI, or leaking the key, a session or a password hash via an endpoint, a
  log line or an error message.
- Anything that lets an unauthenticated caller reach the worker.

Out of scope:

- Exposing Muxarr to the internet with the login waived, and being reached.
- Denial of service from an authenticated caller queueing many jobs.
- Vulnerabilities in `mkvtoolnix`, `ffmpeg`, Radarr or Sonarr themselves.
