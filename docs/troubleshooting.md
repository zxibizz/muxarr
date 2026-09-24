# Troubleshooting

Start with the logs. Muxarr writes one line per import saying what it decided
and why, and the same reasoning is in the UI under each row. `docker logs
muxarr` and the **System** page (or `GET /v1/system`) answer most questions
between them. The System page's **Health** list names the setup problems Muxarr
can detect itself: an unmounted read root, a missing mkvmerge, an unwritable
scratch directory, an offline worker, a login that is switched off.

**Every import is skipped, and the reason mentions read roots.**
The paths Radarr/Sonarr handed over do not exist inside the Muxarr container, or
exist at a different path. Both sides must mount the same library at the same
path. Check with `docker exec muxarr ls <the path from the log line>`, and make
sure `MUXARR_READ_ROOTS` covers both the download and the library path.

**`worker_alive` is `false` and jobs pile up in `pending`.**
The worker process is not running or cannot reach the database. It heartbeats
every 5s and is considered stale after 30s. Look for worker lines in the
container logs; a crash loop usually means `/config` is not writable by
`PUID:PGID`. In a split deployment, check that the worker container is up and
has the same `MUXARR_DB_URL` as the web container.

**The worker container restarts every two minutes, logging `schema not ready`.**
It waits for the web container to migrate the database and gives up after two
minutes. Either the web container is not running, it is on a different database
(compare `MUXARR_DB_URL`), or the two run different image versions.

**Imports fail after roughly a minute, and Radarr/Sonarr report a script error.**
The reverse proxy is cutting the long poll. nginx's `proxy_read_timeout` must be
greater than `MUXARR_MAX_POLL_WAIT`; if you put your own proxy in front of
Muxarr, raise its read timeout too.

**`required binary not found on PATH: mkvmerge`.**
Only relevant outside the official image, which ships mkvtoolnix. Install
`mkvtoolnix` wherever the worker runs — the API does not need it.

**The muxed file lands with the wrong owner, or the mux fails on permissions.**
`PUID`/`PGID` must match the uid that owns your library, the same values your
\*arr containers use. Muxarr creates the output file itself.

**Every import is left to Radarr/Sonarr, and their log says `401`.**
The shim is not sending the API key Muxarr expects. Copy it from Settings →
Security into `MUXARR_API_KEY` on the Radarr/Sonarr container and restart it.
Regenerating the key, or changing a pinned `MUXARR_API_KEY`, needs the same
update. Check from inside the \*arr container with
`curl -H "X-Api-Key: $MUXARR_API_KEY" $MUXARR_URL/v1/system`.

**Locked out of the UI.**
Set `MUXARR_USERNAME` and `MUXARR_PASSWORD` on the Muxarr container and
restart: the stored login is overwritten with them. Remove them again
afterwards to manage the login from the Settings page.

**Nothing happens at all on import.**
Check that the shim is actually wired up: *Settings → Media Management → show
Advanced → Importing → Import Using Script*, with the path pointing at
`/config/scripts/muxarr-import-radarr.sh` (or `-sonarr.sh`), and that the shims
directory is mounted. `docker exec sonarr ls /config/scripts` should list them.

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
