#!/usr/bin/env bash
# Thin wrapper over the youtube-transcript-api skill, so this skill does not
# have to know where that one is installed.
#
# Usage: transcript.sh <URL_OR_ID> [any get_transcript.py options]
#
# Looks for the sibling skill first, then the usual harness skill directories.
# Override with YT_TRANSCRIPT_SKILL=<path to that skill's directory>.

set -uo pipefail

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

if [ -z "$GET" ]; then
  echo "error: youtube-transcript-api skill not found; set YT_TRANSCRIPT_SKILL to its directory" >&2
  exit 2
fi

if [ -x "$GET" ]; then
  exec "$GET" "$@"
elif command -v uv >/dev/null 2>&1; then
  exec uv run --native-tls --script "$GET" "$@"
else
  echo "error: $GET is not executable and uv is not on PATH" >&2
  exit 2
fi
