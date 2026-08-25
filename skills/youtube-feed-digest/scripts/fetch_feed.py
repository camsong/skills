#!/usr/bin/env -S uv run --quiet --native-tls --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["yt-dlp>=2025.1.1"]
# ///
"""List YouTube recommendations / subscription updates for the logged-in user.

Self-contained: the PEP 723 header declares the dependency, so uv resolves and
caches yt-dlp on first run. No venv, nothing installed globally.

Authentication is borrowed from a browser that is already logged in to
YouTube; no password, token or cookie is ever written to disk by this script.

Usage:
    fetch_feed.py [--source rec|subs|both] [options]

Options:
    --source S       rec (home recommendations) | subs (subscription uploads)
                     | both (default)
    --limit N        Max videos per source (default 20)
    --browser B      Browser to borrow cookies from: chrome (default), safari,
                     firefox, edge, brave, chromium, opera, vivaldi
    --profile P      Browser profile name, when not the default one
    --format FMT     table (default, for reading) | json (for machines)
    --min-duration S Skip anything shorter, in seconds (default 0; use 90 to
                     drop Shorts)

Rows go to stdout; status and errors to stderr.
Exit codes: 0 ok, 2 usage error, 3 cookie/auth failure, 4 fetch failure.
"""
import argparse
import json
import re
import sys

VIDEO_ID = re.compile(r"^[0-9A-Za-z_-]{11}$")

SOURCES = {
    "rec": (":ytrec", "首页推荐"),
    "subs": (":ytsubs", "订阅更新"),
}

EXIT_OK, EXIT_USAGE, EXIT_AUTH, EXIT_FETCH = 0, 2, 3, 4

COOKIE_HELP = """\
Could not read YouTube cookies from the browser.

  1. Open the browser and make sure you are logged in to youtube.com.
  2. On macOS the first read asks for your login keychain password. That
     prompt is the OS unlocking the browser's cookie store; approve it.
  3. If the browser is running and holding a lock on its cookie database,
     quit it and try again.
  4. Using a non-default profile? Pass --profile "<name>".

Nothing is written to disk: the cookies are read into memory for this one
request.\
"""


def human_duration(seconds):
    if not seconds:
        return "?"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def human_count(n):
    if n is None:
        return "?"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def clip(text, width):
    text = (text or "").replace("\n", " ").strip()
    # Wide glyphs (CJK) eat two columns; approximate so the table stays aligned.
    out, used = [], 0
    for ch in text:
        w = 2 if ord(ch) > 0x2E80 else 1
        if used + w > width:
            out.append("…")
            break
        out.append(ch)
        used += w
    return "".join(out)


def display_width(text):
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)


def pad(text, width):
    return text + " " * max(0, width - display_width(text))


def normalize(entry, source_key):
    vid = entry.get("id") or ""
    return {
        "source": source_key,
        "video_id": vid,
        "title": entry.get("title") or "",
        "channel": entry.get("channel") or entry.get("uploader") or "",
        "channel_id": entry.get("channel_id") or "",
        "duration_seconds": entry.get("duration"),
        "duration": human_duration(entry.get("duration")),
        "view_count": entry.get("view_count"),
        "live": entry.get("live_status") in ("is_live", "is_upcoming"),
        "url": f"https://www.youtube.com/watch?v={vid}" if vid else entry.get("url", ""),
    }


def fetch(url, limit, browser, profile):
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    opts = {
        "extract_flat": "in_playlist",
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "playlistend": limit,
        "cookiesfrombrowser": (browser, profile or None, None, None),
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        raise RuntimeError(str(exc)) from exc
    return [e for e in (info or {}).get("entries") or [] if e]


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--source", default="both", choices=["rec", "subs", "both"])
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--browser", default="chrome")
    ap.add_argument("--profile", default="")
    ap.add_argument("--format", default="table", choices=["table", "json"])
    ap.add_argument("--min-duration", type=int, default=0, dest="min_duration")
    args = ap.parse_args()

    if args.limit <= 0:
        print("--limit must be positive", file=sys.stderr)
        return EXIT_USAGE

    keys = ["rec", "subs"] if args.source == "both" else [args.source]

    rows, failures = [], []
    for key in keys:
        url, label = SOURCES[key]
        print(f"fetching {label} ({url}) …", file=sys.stderr)
        try:
            entries = fetch(url, args.limit, args.browser, args.profile)
        except RuntimeError as exc:
            failures.append((key, label, str(exc)))
            continue
        for entry in entries:
            row = normalize(entry, key)
            # Mixes, radios and channel rows ride along in these feeds. They
            # have no transcript to summarize, so drop them here rather than
            # letting the user pick one and fail two steps later.
            if not VIDEO_ID.match(row["video_id"]):
                continue
            if args.min_duration and (row["duration_seconds"] or 0) < args.min_duration:
                continue
            rows.append(row)

    if failures and not rows:
        message = "; ".join(m for _, _, m in failures)
        lowered = message.lower()
        if "cookie" in lowered or "keyring" in lowered or "could not copy" in lowered:
            print(COOKIE_HELP, file=sys.stderr)
            print(f"\nyt-dlp said: {message}", file=sys.stderr)
            return EXIT_AUTH
        if "sign in" in lowered or "login" in lowered or "not a bot" in lowered:
            print(COOKIE_HELP, file=sys.stderr)
            print(f"\nyt-dlp said: {message}", file=sys.stderr)
            return EXIT_AUTH
        print(f"error: {message}", file=sys.stderr)
        return EXIT_FETCH

    for key, label, message in failures:
        print(f"warning: {label} failed: {message}", file=sys.stderr)

    # Same video can appear in both feeds; keep the first occurrence.
    seen, unique = set(), []
    for row in rows:
        if row["video_id"] in seen:
            continue
        seen.add(row["video_id"])
        unique.append(row)

    if args.format == "json":
        print(json.dumps(unique, ensure_ascii=False, indent=2))
    else:
        print(
            f"{'#':>3}  {'ID':<11}  {pad('来源', 4)}  {'时长':>6}  "
            f"{pad('频道', 22)}  标题"
        )
        print("-" * 100)
        for i, row in enumerate(unique, 1):
            tag = "推荐" if row["source"] == "rec" else "订阅"
            live = " [直播]" if row["live"] else ""
            print(
                f"{i:>3}  {row['video_id']:<11}  {pad(tag, 4)}  "
                f"{row['duration']:>8}  {pad(clip(row['channel'], 22), 22)}  "
                f"{clip(row['title'], 60)}{live}"
            )

    print(f"\n{len(unique)} videos.", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
