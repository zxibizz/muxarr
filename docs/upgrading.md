# Upgrading

Pin a version tag rather than `latest`, so a restart never changes the version
underneath you:

```yaml
image: ghcr.io/zxibizz/muxarr:0.9.2
```

The published tags are:

| Tag | Moves to | Use it if |
| --- | --- | --- |
| `X.Y.Z` | nothing, ever | You want restarts to be boring. Recommended |
| `X.Y` | the newest `X.Y.z` | You want patch fixes without thinking about it |
| `latest` | the newest stable release | You do not mind a major upgrade arriving on a restart |
| `beta` | the newest prerelease | You are testing a release candidate |

`beta` and `latest` never point at the same image: a prerelease is only ever
published as `beta` and its exact version, and never moves `latest`, `X.Y` or
`X`.

Then:

1. Read the [changelog](../CHANGELOG.md) for the versions you are crossing.
2. Back up `/config/muxarr.db` if the history matters to you.
3. Pull the new tag and recreate the container. Migrations run automatically on
   every start, before the API or worker come up.
4. The shims are republished from the image on every start, so the \*arr
   containers pick up the new ones with no action — as long as the shims
   directory is not mounted over.

Downgrading across a migration is not supported: bring the old database back
from your backup instead.

## Moving to Postgres or a split deployment

Pointing `MUXARR_DB_URL` at Postgres starts from an empty database: the history
and the Settings page overrides in `/config/muxarr.db` are not copied over. Note
down any settings you changed in the UI first. Pending imports are not lost as
long as the old container has finished its queue before you switch.

If you build the image yourself: `Dockerfile.all-in-one` is now `Dockerfile`.
