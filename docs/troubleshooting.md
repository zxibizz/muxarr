# Troubleshooting

Start with the logs. muxarr writes one line per import saying what it decided
and why, and the same reasoning is in the UI under each row. `docker logs
muxarr` and the **System** page (or `GET /v1/system`) answer most questions
between them.

**Every import is skipped, and the reason mentions read roots.**
The paths Radarr/Sonarr handed over do not exist inside the muxarr container, or
exist at a different path. Both sides must mount the same library at the same
path. Check with `docker exec muxarr ls <the path from the log line>`, and make
sure `MUXARR_READ_ROOTS` covers both the download and the library path.

**`worker_alive` is `false` and jobs pile up in `pending`.**
The worker process is not running or cannot reach the database. It heartbeats
every 5s and is considered stale after 30s. Look for worker lines in the
container logs; a crash loop usually means `/config` is not writable by
`PUID:PGID`.

**Imports fail after roughly a minute, and Radarr/Sonarr report a script error.**
The reverse proxy is cutting the long poll. nginx's `proxy_read_timeout` must be
greater than `MUXARR_MAX_POLL_WAIT`; if you put your own proxy in front of
muxarr, raise its read timeout too.

**`required binary not found on PATH: mkvmerge`.**
Only relevant outside the official image, which ships mkvtoolnix. Install
`mkvtoolnix` wherever the worker runs — the API does not need it.

**The muxed file lands with the wrong owner, or the mux fails on permissions.**
`PUID`/`PGID` must match the uid that owns your library, the same values your
\*arr containers use. muxarr creates the output file itself.

**Nothing happens at all on import.**
Check that the shim is actually wired up: *Settings → Media Management → show
Advanced → Importing → Import Using Script*, with the path pointing at
`/config/scripts/muxarr-import-radarr.sh` (or `-sonarr.sh`), and that the shims
volume is mounted. `docker exec sonarr ls /config/scripts` should list them.

**The output is missing a sidecar you expected.**
Open the import in the UI and look at its **Tracks** tab. Every sidecar that was
passed over is listed with the reason — usually de-duplication
(`MUXARR_DEDUPE`), an image-subtitle or undetermined-language skip, a keep list,
or the track cap (`MUXARR_MAX_TRACKS`). If the reason is that nothing was found
at all, the layout may be one the filename rules cannot read; try
[AI mode](configuration.md#ai-mode).

**AI mode is enabled but nothing changes.**
In `fallback` mode the model is only consulted when the filename rules came up
short, which is the point. Grep the logs for `infra.ai` to see whether it was
called and what it replied; in `verify` mode it is called every time but never
allowed to change the outcome.
