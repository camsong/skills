#!/usr/bin/env bash
# Fetch everything needed to write a reading version of a YouTube video:
# metadata (title / channel / upload date) plus the transcript in three formats.
#
# Usage:
#   fetch_source.sh <URL_OR_ID> [OUT_DIR] [--lang en,zh-Hans,zh]
#
# Writes into OUT_DIR (default: ./yt-<id>/):
#   <id>.meta.txt   title / author / uploadDate / transcript languages
#   <id>.ts.txt     [mm:ss] line   <- the one you actually read and cite
#   <id>.srt        subtitle file
#   <id>.txt        one-paragraph plain text
#
# Depends on the youtube-transcript-api skill. It is looked up as a sibling
# skill first, then in the usual harness skill directories. Override with
# YT_TRANSCRIPT_SKILL=<path to that skill's directory>.

set -uo pipefail

die() { echo "error: $*" >&2; exit 2; }

TARGET="${1:-}"
[ -n "$TARGET" ] || die "usage: fetch_source.sh <URL_OR_ID> [OUT_DIR] [--lang a,b,c]"
shift

OUT_DIR=""
LANGS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --lang) LANGS="${2:-}"; shift 2 ;;
    --lang=*) LANGS="${1#*=}"; shift ;;
    *) [ -z "$OUT_DIR" ] && OUT_DIR="$1"; shift ;;
  esac
done

# --- locate the youtube-transcript-api skill ----------------------------
# Sibling first: in this repo (and after scripts/install.sh) both skills sit
# in the same skills directory, so the relative hop works on every harness.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CANDIDATES=(
  "${YT_TRANSCRIPT_SKILL:-}"
  "$HERE/../../youtube-transcript-api"
  "$HOME/.claude/skills/youtube-transcript-api"
  "$HOME/.agents/skills/youtube-transcript-api"
  "$HOME/.codex/skills/youtube-transcript-api"
  "$HOME/.cursor/skills/youtube-transcript-api"
)

GET=""
for base in "${CANDIDATES[@]}"; do
  [ -n "$base" ] || continue
  for rel in scripts/get_transcript.py get_transcript.py; do
    if [ -f "$base/$rel" ]; then GET="$base/$rel"; break 2; fi
  done
done
[ -n "$GET" ] || die "youtube-transcript-api skill not found; set YT_TRANSCRIPT_SKILL to its directory"

# Executable => its uv shebang runs it. Otherwise drive uv ourselves.
if [ -x "$GET" ]; then
  get() { "$GET" "$@"; }
elif command -v uv >/dev/null 2>&1; then
  get() { uv run --native-tls --script "$GET" "$@"; }
else
  die "$GET is not executable and uv is not on PATH"
fi

# --- video id -----------------------------------------------------------
if [[ "$TARGET" =~ ^[0-9A-Za-z_-]{11}$ ]]; then
  VID="$TARGET"
else
  VID=$(printf '%s' "$TARGET" | sed -nE 's|.*(v=\|/v/\|youtu\.be/\|/embed/\|/shorts/\|/live/)([0-9A-Za-z_-]{11}).*|\2|p')
fi
[ -n "$VID" ] || die "could not extract an 11-char video id from: $TARGET"

OUT_DIR="${OUT_DIR:-./yt-$VID}"
mkdir -p "$OUT_DIR" || die "cannot create $OUT_DIR"

URL="https://www.youtube.com/watch?v=$VID"
META="$OUT_DIR/$VID.meta.txt"

# --- metadata -----------------------------------------------------------
# The transcript API returns no title/author, so scrape the watch page once
# and reuse the HTML for every field.
HTML=$(curl -sL --max-time 30 "$URL" || true)

field() { printf '%s' "$HTML" | grep -o "$1" | head -1 | sed -E "$2"; }

TITLE=$(field '<meta name="title" content="[^"]*"' 's|.*content="(.*)"|\1|')
AUTHOR=$(field '"author":"[^"]*"' 's|"author":"(.*)"|\1|')
UPLOAD=$(field '"uploadDate":"[^"]*"' 's|"uploadDate":"(.*)"|\1|')
SECONDS_LEN=$(field '"lengthSeconds":"[0-9]*"' 's|"lengthSeconds":"([0-9]*)"|\1|')

DURATION=""
if [ -n "${SECONDS_LEN:-}" ]; then
  DURATION=$(printf '%d:%02d:%02d' $((SECONDS_LEN/3600)) $(((SECONDS_LEN%3600)/60)) $((SECONDS_LEN%60)))
fi

{
  echo "video_id:    $VID"
  echo "url:         $URL"
  echo "title:       ${TITLE:-<not found — ask the user or leave unstated>}"
  echo "author:      ${AUTHOR:-<not found>}"
  echo "upload_date: ${UPLOAD:-<not found>}"
  echo "duration:    ${DURATION:-<not found>}"
  echo ""
  echo "available transcripts:"
} > "$META"

get "$VID" --list >> "$META" 2>>"$META" || die "no transcript available for $VID (see $META)"

# --- transcripts --------------------------------------------------------
LANG_ARG=()
[ -n "$LANGS" ] && LANG_ARG=(--lang "$LANGS")

fetch() { get "$VID" "${LANG_ARG[@]+"${LANG_ARG[@]}"}" --format "$1" > "$2" 2>/dev/null; }

fetch ts   "$OUT_DIR/$VID.ts.txt" || die "transcript fetch failed"
fetch srt  "$OUT_DIR/$VID.srt"
fetch text "$OUT_DIR/$VID.txt"

LINES=$(wc -l < "$OUT_DIR/$VID.ts.txt" | tr -d ' ')
LAST=$(tail -1 "$OUT_DIR/$VID.ts.txt" | sed -nE 's|^\[([0-9:]+)\].*|\1|p')

{
  echo ""
  echo "snippets:    $LINES"
  echo "last_stamp:  ${LAST:-?}"
} >> "$META"

cat "$META" >&2
echo "" >&2
echo "files written to $OUT_DIR/" >&2
echo "read $OUT_DIR/$VID.ts.txt in full before writing anything." >&2
