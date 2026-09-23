#!/bin/sh
# Generated from scripts/src/muxarr-import.sh.in by scripts/build_shims.py. Edit that.
#
# muxarr import shim for Radarr.
#
# Set as: Settings > Media Management > Importing > Import Using Script
#         "Import Script Path" -> /path/to/muxarr-import-radarr.sh
#
# Radarr calls this as:  script "<sourcePath>" "<destinationPath>"
# and reads protocol lines from stdout.
#
# The daemon does the remux asynchronously: this script queues a job, then polls
# until it finishes. Each poll is a short request the daemon holds open until the
# job changes state, so completion is picked up within a second without any
# single request living long enough for a proxy to time it out.
#
# Exit codes are load-bearing. Radarr FAILS the import on a non-zero exit, and an
# unrecognised/missing [MoveStatus] line makes it assume the file was already
# moved. So:
#   * nothing queued yet -> exit 0 with [MoveStatus] DeferMove, and Radarr
#     imports the file itself; muxarr never touched it.
#   * queued, then lost  -> exit 1. A mux may be in flight and about to replace
#     the destination, so a native import here would race it.
#
# It deliberately does no JSON parsing: the daemon renders the protocol itself.
#
# Configuration (environment):
#   MUXARR_URL            default http://muxarr:8710
#   MUXARR_TOKEN          bearer token; omit if the daemon is unauthenticated
#   MUXARR_TIMEOUT        total seconds to wait for a remux, default 14400 (4h)
#   MUXARR_POLL_WAIT      seconds the daemon holds each poll open, default 25
#   MUXARR_POLL_INTERVAL  seconds to back off after a failed request, default 5
#   MUXARR_MAX_RETRIES    consecutive request failures tolerated, default 10

# No `set -e`: a failed command must fall through to defer()/fail(), not abort.
# No `set -u`: every Radarr variable is referenced with an explicit default anyway.

MUXARR_URL="${MUXARR_URL:-http://muxarr:8710}"
MUXARR_TOKEN="${MUXARR_TOKEN:-}"
MUXARR_TIMEOUT="${MUXARR_TIMEOUT:-14400}"
MUXARR_POLL_WAIT="${MUXARR_POLL_WAIT:-25}"
MUXARR_POLL_INTERVAL="${MUXARR_POLL_INTERVAL:-5}"
MUXARR_MAX_RETRIES="${MUXARR_MAX_RETRIES:-10}"

SUBMIT_ENDPOINT="${MUXARR_URL%/}/v1/import"

# Leaves the daemon room to answer at the end of its hold before the client
# gives up on the connection.
REQUEST_TIMEOUT=$((MUXARR_POLL_WAIT + 10))

log() {
    printf 'muxarr: %s\n' "$1" >&2
}

# Nothing has been queued: let Radarr do a normal import.
defer() {
    if [ -n "$1" ]; then
        log "$1"
    fi
    printf '[MoveStatus] DeferMove\n'
    exit 0
}

# A mux was queued and its result is unknown: fail the import rather than let
# Radarr move a file muxarr may still be rewriting.
fail() {
    log "$1"
    exit 1
}

json_escape() {
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

# Generated once and reused for every retry, so a resubmission after a lost reply
# re-attaches to the running mux instead of starting a second one.
new_job_id() {
    if [ -r /proc/sys/kernel/random/uuid ]; then
        tr -d '\n' < /proc/sys/kernel/random/uuid
    elif [ -r /dev/urandom ] && command -v od >/dev/null 2>&1; then
        od -An -tx1 -N16 /dev/urandom | tr -d ' \n'
    else
        printf '%s-%s' "$$" "$(date +%s)"
    fi
}

http_post() {
    _endpoint="$1"
    _payload="$2"
    if [ "$HTTP_CLIENT" = curl ]; then
        set -- -sS -X POST --max-time "$REQUEST_TIMEOUT" \
            -H 'Content-Type: application/json'
        [ -n "$MUXARR_TOKEN" ] && set -- "$@" -H "Authorization: Bearer $MUXARR_TOKEN"
        curl "$@" --data "$_payload" "$_endpoint" 2>/dev/null
    else
        set -- -q -O - --timeout="$REQUEST_TIMEOUT" \
            --header='Content-Type: application/json'
        [ -n "$MUXARR_TOKEN" ] && set -- "$@" --header="Authorization: Bearer $MUXARR_TOKEN"
        wget "$@" --post-data="$_payload" "$_endpoint" 2>/dev/null
    fi
}

http_get() {
    _endpoint="$1"
    if [ "$HTTP_CLIENT" = curl ]; then
        set -- -sS --max-time "$REQUEST_TIMEOUT"
        [ -n "$MUXARR_TOKEN" ] && set -- "$@" -H "Authorization: Bearer $MUXARR_TOKEN"
        curl "$@" "$_endpoint" 2>/dev/null
    else
        set -- -q -O - --timeout="$REQUEST_TIMEOUT"
        [ -n "$MUXARR_TOKEN" ] && set -- "$@" --header="Authorization: Bearer $MUXARR_TOKEN"
        wget "$@" "$_endpoint" 2>/dev/null
    fi
}

SOURCE="${1:-}"
DESTINATION="${2:-}"
TRANSFER="${Radarr_TransferMode:-Move}"

if [ -z "$SOURCE" ] || [ -z "$DESTINATION" ]; then
    defer "missing source or destination argument"
fi

if command -v curl >/dev/null 2>&1; then
    HTTP_CLIENT=curl
elif command -v wget >/dev/null 2>&1; then
    HTTP_CLIENT=wget
else
    defer "neither curl nor wget is available in this container"
fi

JOB_ID=$(new_job_id)
POLL_ENDPOINT="${MUXARR_URL%/}/v1/jobs/${JOB_ID}/protocol?wait=${MUXARR_POLL_WAIT}"

PAYLOAD=$(printf '{"job_id":"%s","app":"radarr","source_path":"%s","destination_path":"%s","transfer_mode":"%s"}' \
    "$JOB_ID" \
    "$(json_escape "$SOURCE")" \
    "$(json_escape "$DESTINATION")" \
    "$(json_escape "$TRANSFER")")

DEADLINE=$(( $(date +%s) + MUXARR_TIMEOUT ))

ATTEMPTS=0
QUEUED=0
while [ "$ATTEMPTS" -lt "$MUXARR_MAX_RETRIES" ]; do
    ATTEMPTS=$((ATTEMPTS + 1))
    RESPONSE=$(http_post "$SUBMIT_ENDPOINT" "$PAYLOAD")
    STATUS=$?
    # The daemon echoes the job id back; anything else (an error page, a 401)
    # means it did not take the job.
    if [ "$STATUS" -eq 0 ] && printf '%s' "$RESPONSE" | grep -q "\"$JOB_ID\""; then
        QUEUED=1
        break
    fi
    if [ "$ATTEMPTS" -lt "$MUXARR_MAX_RETRIES" ]; then
        sleep "$MUXARR_POLL_INTERVAL"
    fi
done

if [ "$QUEUED" -ne 1 ]; then
    defer "could not queue import with muxarr at $SUBMIT_ENDPOINT"
fi

FAILURES=0
while :; do
    STARTED=$(date +%s)
    if [ "$STARTED" -ge "$DEADLINE" ]; then
        fail "gave up after ${MUXARR_TIMEOUT}s waiting for job $JOB_ID"
    fi

    RESPONSE=$(http_get "$POLL_ENDPOINT")
    STATUS=$?
    STATE=""
    if [ "$STATUS" -eq 0 ]; then
        STATE=$(printf '%s\n' "$RESPONSE" | tr -d '\r' \
            | sed -n 's/^\[MuxarrState\] \([a-z]*\)$/\1/p' | head -n 1)
    fi

    case "$STATE" in
    done)
        # Echo only well-formed protocol lines, so the state line, an HTML error
        # page or a stray log line can never reach Radarr's parser.
        LINES=$(printf '%s\n' "$RESPONSE" | tr -d '\r' \
            | grep -E '^\[(MediaFile|ExtraFile|PreventExtraImport|MoveStatus)\]')
        if ! printf '%s\n' "$LINES" \
            | grep -qE '^\[MoveStatus\] (DeferMove|MoveComplete|RenameRequested)$'; then
            fail "job $JOB_ID finished without a valid [MoveStatus] line"
        fi
        printf '%s\n' "$LINES"
        exit 0
        ;;
    running)
        FAILURES=0
        # Only bites if the daemon is not honouring the hold; otherwise the poll
        # itself has already blocked for MUXARR_POLL_WAIT.
        if [ "$(date +%s)" -le "$STARTED" ]; then
            sleep 1
        fi
        ;;
    error)
        fail "muxarr reported a failure for job $JOB_ID"
        ;;
    unknown)
        fail "muxarr no longer knows job $JOB_ID; it may have restarted mid-remux"
        ;;
    *)
        FAILURES=$((FAILURES + 1))
        if [ "$FAILURES" -ge "$MUXARR_MAX_RETRIES" ]; then
            fail "lost contact with muxarr after $FAILURES attempts (job $JOB_ID)"
        fi
        sleep "$MUXARR_POLL_INTERVAL"
        ;;
    esac
done
