#!/bin/sh
#
# muxarr import shim for Radarr/Sonarr.
#
# Set as: Settings > Media Management > Importing > Import Using Script
#         "Import Script Path" -> /path/to/muxarr-import.sh
#
# *arr calls this as:  muxarr-import.sh "<sourcePath>" "<destinationPath>"
# and reads protocol lines from stdout. A non-zero exit FAILS THE IMPORT, and an
# unrecognised/missing [MoveStatus] line makes *arr assume the file was already
# moved -- so this script exits 0 on every path and always prints exactly one
# valid [MoveStatus].
#
# It deliberately does no JSON parsing: the daemon renders the protocol itself.
#
# Configuration (environment):
#   MUXARR_URL      default http://muxarr:8710
#   MUXARR_TOKEN    bearer token; omit if the daemon is unauthenticated
#   MUXARR_TIMEOUT  seconds to wait for a remux, default 14400 (4h)

# No `set -e`: a failed command must fall through to defer(), not abort.
# No `set -u`: every *arr variable is referenced with an explicit default anyway.

MUXARR_URL="${MUXARR_URL:-http://muxarr:8710}"
MUXARR_TOKEN="${MUXARR_TOKEN:-}"
MUXARR_TIMEOUT="${MUXARR_TIMEOUT:-14400}"
ENDPOINT="${MUXARR_URL%/}/v1/import/protocol"

defer() {
    if [ -n "$1" ]; then
        printf 'muxarr: %s\n' "$1" >&2
    fi
    printf '[MoveStatus] DeferMove\n'
    exit 0
}

json_escape() {
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'
}

digits_or_null() {
    cleaned=$(printf '%s' "$1" | tr -cd '0-9')
    if [ -z "$cleaned" ]; then printf 'null'; else printf '%s' "$cleaned"; fi
}

if [ -n "${Radarr_SourcePath:-}" ]; then
    APP="radarr"
    SOURCE="${Radarr_SourcePath}"
    DESTINATION="${Radarr_DestinationPath}"
    LIBRARY="${Radarr_Movie_Path}"
    TRANSFER="${Radarr_TransferMode:-Move}"
    SEASON="null"
    EPISODES=""
elif [ -n "${Sonarr_SourcePath:-}" ]; then
    APP="sonarr"
    SOURCE="${Sonarr_SourcePath}"
    DESTINATION="${Sonarr_DestinationPath}"
    LIBRARY="${Sonarr_Series_Path}"
    TRANSFER="${Sonarr_TransferMode:-Move}"
    SEASON=$(digits_or_null "${Sonarr_EpisodeFile_SeasonNumber:-}")
    EPISODES=$(printf '%s' "${Sonarr_EpisodeFile_EpisodeNumbers:-}" | tr -cd '0-9,')
else
    defer "neither Radarr_SourcePath nor Sonarr_SourcePath is set"
fi

# argv is the authoritative pair; the env vars should agree but cost nothing to prefer.
[ -n "${1:-}" ] && SOURCE="$1"
[ -n "${2:-}" ] && DESTINATION="$2"

if [ -z "$SOURCE" ] || [ -z "$DESTINATION" ] || [ -z "$LIBRARY" ]; then
    defer "missing source, destination or library path"
fi

# Trim any stray separators so the result is always a valid JSON array body.
EPISODES=$(printf '%s' "$EPISODES" | sed -e 's/,,*/,/g' -e 's/^,//' -e 's/,$//')

PAYLOAD=$(printf '{"app":"%s","source_path":"%s","destination_path":"%s","library_path":"%s","transfer_mode":"%s","season":%s,"episodes":[%s]}' \
    "$APP" \
    "$(json_escape "$SOURCE")" \
    "$(json_escape "$DESTINATION")" \
    "$(json_escape "$LIBRARY")" \
    "$(json_escape "$TRANSFER")" \
    "$SEASON" \
    "$EPISODES")

if command -v curl >/dev/null 2>&1; then
    if [ -n "$MUXARR_TOKEN" ]; then
        RESPONSE=$(curl -sS -X POST --max-time "$MUXARR_TIMEOUT" \
            -H 'Content-Type: application/json' \
            -H "Authorization: Bearer $MUXARR_TOKEN" \
            --data "$PAYLOAD" "$ENDPOINT" 2>/dev/null)
    else
        RESPONSE=$(curl -sS -X POST --max-time "$MUXARR_TIMEOUT" \
            -H 'Content-Type: application/json' \
            --data "$PAYLOAD" "$ENDPOINT" 2>/dev/null)
    fi
    STATUS=$?
elif command -v wget >/dev/null 2>&1; then
    if [ -n "$MUXARR_TOKEN" ]; then
        RESPONSE=$(wget -q -O - --timeout="$MUXARR_TIMEOUT" \
            --header='Content-Type: application/json' \
            --header="Authorization: Bearer $MUXARR_TOKEN" \
            --post-data="$PAYLOAD" "$ENDPOINT" 2>/dev/null)
    else
        RESPONSE=$(wget -q -O - --timeout="$MUXARR_TIMEOUT" \
            --header='Content-Type: application/json' \
            --post-data="$PAYLOAD" "$ENDPOINT" 2>/dev/null)
    fi
    STATUS=$?
else
    defer "neither curl nor wget is available in this container"
fi

if [ "$STATUS" -ne 0 ]; then
    defer "muxarr daemon unreachable at $ENDPOINT (exit $STATUS)"
fi

# Echo only well-formed protocol lines, so an HTML error page or a stray log line
# can never reach *arr's parser.
LINES=$(printf '%s\n' "$RESPONSE" \
    | tr -d '\r' \
    | grep -E '^\[(MediaFile|ExtraFile|PreventExtraImport|MoveStatus)\]')

if ! printf '%s\n' "$LINES" \
    | grep -qE '^\[MoveStatus\] (DeferMove|MoveComplete|RenameRequested)$'; then
    defer "daemon response contained no valid [MoveStatus] line"
fi

printf '%s\n' "$LINES"
exit 0
