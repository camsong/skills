#!/usr/bin/env bash
# Download a YouTube video's audio (16 kHz mono wav) and/or a <=720p video file.
#
# Usage:
#   fetch_media.sh <URL_OR_ID> <WORK_DIR> [audio|video|both]   (default: both)
#
# Writes WORK_DIR/audio_full.wav and/or WORK_DIR/video.mp4.
# Needs ffmpeg and yt-dlp (falls back to `uvx --native-tls yt-dlp`; --native-tls
# matters on machines behind a TLS-inspecting proxy).
# If YouTube answers "Sign in to confirm you're not a bot", rerun with
# YTDLP_ARGS="--cookies-from-browser chrome" after the user has signed in.
set -euo pipefail
URL="$1"; DIR="$2"; WHAT="${3:-both}"
mkdir -p "$DIR"
if command -v yt-dlp >/dev/null; then YTDLP=(yt-dlp); else YTDLP=(uvx --native-tls yt-dlp); fi
EXTRA=(${YTDLP_ARGS:-})
if [ "$WHAT" != video ]; then
  "${YTDLP[@]}" "${EXTRA[@]}" -q --no-progress -f bestaudio -o "$DIR/audio_src.%(ext)s" --no-playlist "$URL"
  ffmpeg -v error -y -i "$DIR"/audio_src.* -vn -ac 1 -ar 16000 -c:a pcm_s16le "$DIR/audio_full.wav"
  echo "audio: $DIR/audio_full.wav"
fi
if [ "$WHAT" != audio ]; then
  "${YTDLP[@]}" "${EXTRA[@]}" -q --no-progress -f "bestvideo[height<=720][ext=mp4]/bestvideo[height<=720]" \
    -o "$DIR/video.%(ext)s" --no-playlist "$URL"
  echo "video: $(ls "$DIR"/video.*)"
fi
