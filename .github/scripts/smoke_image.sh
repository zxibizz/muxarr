#!/bin/sh
# Starts the production image the two ways it is run and checks it comes up:
#   root     - the PUID/PGID way: s6 starts as root, services drop to PUID:PGID
#   nonroot  - already the library's uid, read-only root, no capabilities, as
#              Kubernetes' "restricted" Pod Security profile demands
# Usage: smoke_image.sh IMAGE
set -eu

image="$1"
failed=0

wait_healthy() {
    name="$1"
    i=0
    while [ "$i" -lt 60 ]; do
        if out=$(docker exec "$name" curl -fsS http://127.0.0.1:8710/healthz 2>/dev/null) \
            && printf '%s' "$out" | grep -q '"worker_alive":true'; then
            echo "$name: healthy: $out"
            return 0
        fi
        if [ "$(docker inspect -f '{{.State.Running}}' "$name")" != true ]; then
            echo "$name: exited" >&2
            return 1
        fi
        i=$((i + 1))
        sleep 2
    done
    echo "$name: not healthy after 120s" >&2
    return 1
}

# Every muxarr process must run as the expected uid; nginx's master stays root
# only in the root shape, where it is meant to.
check_uids() {
    name="$1"
    want="$2"
    bad=$(docker exec "$name" sh -c '
        for d in /proc/[0-9]*; do
            # This very shell has the patterns in its own command line.
            [ "${d#/proc/}" = "$$" ] && continue
            cmd=$(tr "\0" " " < "$d/cmdline" 2>/dev/null) || continue
            uid=$(awk "/^Uid:/ {print \$2}" "$d/status" 2>/dev/null) || continue
            case "$cmd" in
                *uvicorn*|*src.worker*) [ "$uid" = "'"$want"'" ] || echo "$uid $cmd" ;;
            esac
        done')
    if [ -n "$bad" ]; then
        echo "$name: processes not running as uid $want:" >&2
        echo "$bad" >&2
        return 1
    fi
    echo "$name: api and worker run as uid $want"
}

check_index() {
    name="$1"
    path="$2"
    href="$3"
    if docker exec "$name" curl -fsSL "http://127.0.0.1:8710$path" | grep -q "<base href=\"$href\""; then
        echo "$name: $path serves index.html with base href $href"
    else
        echo "$name: $path does not serve index.html with base href $href" >&2
        return 1
    fi
}

run() {
    name="$1"
    shift
    docker run -d --name "$name" -e MUXARR_READ_ROOTS=/tmp "$@" "$image" >/dev/null
}

dump() {
    echo "--- logs of $1" >&2
    docker logs "$1" >&2 2>&1 || true
    # Also as an annotation: it shows on the run page without opening the log.
    if [ -n "${GITHUB_ACTIONS:-}" ]; then
        logs=$(docker logs --tail 60 "$1" 2>&1 | sed -e 's/%/%25/g' | awk 'BEGIN{ORS="%0A"} {print}')
        echo "::error title=smoke $1 failed::${logs}"
    fi
}

# 1. root, PUID/PGID
run root -e PUID=1234 -e PGID=1234
if wait_healthy root && check_uids root 1234 && check_index root / /; then :; else
    dump root; failed=1
fi

# 2. non-root, read-only, no capabilities. s6-overlay insists /run belongs to
#    the uid it runs as, and cannot chown it here.
run nonroot \
    --user 1234:1234 --read-only --cap-drop ALL --security-opt no-new-privileges \
    -e S6_READ_ONLY_ROOT=1 \
    --tmpfs /run:exec,mode=0755,uid=1234,gid=1234 --tmpfs /tmp:mode=1777 \
    --mount type=tmpfs,destination=/config,tmpfs-mode=1777
if wait_healthy nonroot && check_uids nonroot 1234 && check_index nonroot / /; then :; else
    dump nonroot; failed=1
fi

# 3. non-root with a URL base: the rendered index.html must carry it
run nonroot-base \
    --user 1234:1234 --read-only --cap-drop ALL --security-opt no-new-privileges \
    -e S6_READ_ONLY_ROOT=1 \
    --tmpfs /run:exec,mode=0755,uid=1234,gid=1234 --tmpfs /tmp:mode=1777 \
    --mount type=tmpfs,destination=/config,tmpfs-mode=1777 \
    -e MUXARR_URL_BASE=/muxarr
if wait_healthy nonroot-base && check_index nonroot-base /muxarr/ /muxarr/; then :; else
    dump nonroot-base; failed=1
fi

docker rm -f root nonroot nonroot-base >/dev/null 2>&1 || true
exit "$failed"
