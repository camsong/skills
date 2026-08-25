#!/usr/bin/env -S uv run --quiet --native-tls --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["youtube-transcript-api>=1.2"]
# ///
"""Fetch a YouTube video transcript via youtube-transcript-api (v1.x).

Self-contained: the PEP 723 header above declares the dependency, so
`uv run --script get_transcript.py ...` resolves and caches it with no venv
to create and nothing to install globally. Copy this file plus SKILL.md to
any machine with uv and it runs.

Usage:
    get_transcript.py <url_or_id> [options]

Options:
    --lang a,b,c     Preferred language codes, in priority order (e.g. en,zh-Hans,zh).
                     If none match, falls back to any available transcript.
    --translate xx   Translate the chosen transcript to language code xx.
    --format FMT     Output format: text (default) | ts | json | srt
                       text -> plain text, paragraphs joined
                       ts   -> "[mm:ss] line" per snippet
                       json -> raw [{text,start,duration}] list
                       srt  -> SubRip subtitle format
    --list           Only list available transcripts for the video, then exit.

Transcript text goes to stdout; status/metadata go to stderr.
Exit codes: 0 ok, 2 usage error, 3 no transcript / fetch error.
"""
import argparse
import json
import os
import re
import sys

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)
from youtube_transcript_api.proxies import GenericProxyConfig


def extract_video_id(s: str) -> str:
    """Accept a raw 11-char id or any common YouTube URL form."""
    s = s.strip()
    if re.fullmatch(r"[0-9A-Za-z_-]{11}", s):
        return s
    patterns = [
        r"(?:v=|/v/|youtu\.be/|/embed/|/shorts/|/live/)([0-9A-Za-z_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, s)
        if m:
            return m.group(1)
    raise ValueError(f"Could not extract a video id from: {s!r}")


def fmt_ts(seconds: float, srt: bool = False) -> str:
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    sec, ms = divmod(rem, 1000)
    if srt:
        return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"
    if h:
        return f"{h:d}:{m:02d}:{sec:02d}"
    return f"{m:d}:{sec:02d}"


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("target", help="YouTube URL or 11-char video id")
    ap.add_argument("--lang", default="")
    ap.add_argument("--translate", default="")
    ap.add_argument("--format", default="text", choices=["text", "ts", "json", "srt"])
    ap.add_argument("--list", action="store_true", dest="list_only")
    ap.add_argument(
        "--proxy",
        default="",
        help="Proxy URL for both http/https (e.g. http://user:pass@host:port). "
        "Falls back to HTTPS_PROXY/HTTP_PROXY env vars. Needed when your IP is "
        "blocked by YouTube (datacenter/cloud egress).",
    )
    args = ap.parse_args()

    try:
        video_id = extract_video_id(args.target)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2

    proxy_url = (
        args.proxy
        or os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
        or ""
    )
    proxy_config = None
    if proxy_url:
        proxy_config = GenericProxyConfig(http_url=proxy_url, https_url=proxy_url)
        print(f"Using proxy: {proxy_url}", file=sys.stderr)

    api = YouTubeTranscriptApi(proxy_config=proxy_config)

    try:
        transcript_list = api.list(video_id)
    except (TranscriptsDisabled, VideoUnavailable, CouldNotRetrieveTranscript) as e:
        print(f"Cannot retrieve transcripts for {video_id}: {e}", file=sys.stderr)
        return 3

    available = list(transcript_list)
    if args.list_only:
        print(f"Available transcripts for {video_id}:", file=sys.stderr)
        for t in available:
            kind = "auto-generated" if t.is_generated else "manual"
            tr = ", translatable" if t.is_translatable else ""
            print(f"  {t.language_code:<8} {t.language} ({kind}{tr})")
        return 0

    langs = [l.strip() for l in args.lang.split(",") if l.strip()]
    transcript = None
    if langs:
        try:
            transcript = transcript_list.find_transcript(langs)
        except NoTranscriptFound:
            transcript = None
    if transcript is None:
        if langs:
            print(
                f"None of {langs} found; falling back to first available.",
                file=sys.stderr,
            )
        transcript = available[0]

    if args.translate:
        if not transcript.is_translatable:
            print(
                f"Transcript '{transcript.language_code}' is not translatable.",
                file=sys.stderr,
            )
            return 3
        transcript = transcript.translate(args.translate)

    try:
        fetched = transcript.fetch()
    except CouldNotRetrieveTranscript as e:
        print(f"Fetch failed: {e}", file=sys.stderr)
        return 3

    snippets = fetched.to_raw_data()  # [{text, start, duration}]
    print(
        f"Fetched {len(snippets)} snippets in '{transcript.language_code}' "
        f"({transcript.language}).",
        file=sys.stderr,
    )

    if args.format == "json":
        print(json.dumps(snippets, ensure_ascii=False, indent=2))
    elif args.format == "ts":
        for s in snippets:
            print(f"[{fmt_ts(s['start'])}] {s['text']}")
    elif args.format == "srt":
        for i, s in enumerate(snippets, 1):
            start = fmt_ts(s["start"], srt=True)
            end = fmt_ts(s["start"] + s["duration"], srt=True)
            print(f"{i}\n{start} --> {end}\n{s['text']}\n")
    else:  # text
        text = " ".join(s["text"].replace("\n", " ").strip() for s in snippets)
        text = re.sub(r"\s+", " ", text).strip()
        print(text)

    return 0


if __name__ == "__main__":
    sys.exit(main())
