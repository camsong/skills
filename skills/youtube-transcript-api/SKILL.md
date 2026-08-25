---
name: youtube-transcript-api
description: Fetch the transcript/subtitles of a YouTube video. Use when the user gives a YouTube URL or video id and wants its transcript, captions, subtitles, or a text version of the talk — including listing available languages or translating the transcript.
---

# YouTube Transcript

Fetches a YouTube video's transcript using the `youtube-transcript-api` Python
library. `scripts/get_transcript.py` declares its own dependency inline
(PEP 723), so there is no venv to create and nothing installed globally — `uv`
resolves and caches the dependency on first run.

## Run

The script lives at `scripts/get_transcript.py` inside this skill's directory,
which the harness injects when the skill loads. Set a shorthand to that
directory, then call the script directly — it is executable and its shebang
routes through `uv`:

```bash
YT=<this skill's directory>
"$YT/scripts/get_transcript.py" "<URL_OR_ID>" [options]
```

Accepts a full URL (`watch?v=`, `youtu.be/`, `/shorts/`, `/embed/`, `/live/`) or a bare 11-char video id. Extra URL params like `&t=851s` are fine.

If the shebang fails because `uv` is not on `PATH`, call it explicitly:

```bash
uv run --native-tls --script "$YT/scripts/get_transcript.py" "<URL_OR_ID>" [options]
```

### Options

| Option | Meaning |
|--------|---------|
| `--list` | List available transcript languages, then exit |
| `--lang en,zh-Hans,zh` | Preferred language codes in priority order; falls back to first available |
| `--translate en` | Translate the chosen transcript to a language code (transcript must be translatable) |
| `--format text` | `text` (default, one clean paragraph), `ts` (`[mm:ss] line`), `json` (`{text,start,duration}`), `srt` (subtitles) |
| `--proxy URL` | Route through a proxy (`http://[user:pass@]host:port`). Also auto-reads `HTTPS_PROXY`/`HTTP_PROXY` env vars. Needed when the IP is blocked (see Notes) |

Transcript prints to **stdout**; status/metadata to **stderr**. Redirect to save: `... > transcript.txt`.

Write output into a scratch directory, not into the user's repo.

### Examples

```bash
# Plain text transcript
"$YT/scripts/get_transcript.py" "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

# See which languages exist first
"$YT/scripts/get_transcript.py" "dQw4w9WgXcQ" --list

# Prefer Chinese, fall back to anything; timestamped output
"$YT/scripts/get_transcript.py" "dQw4w9WgXcQ" --lang zh-Hans,zh,en --format ts

# Translate an English auto-caption to Chinese
"$YT/scripts/get_transcript.py" "dQw4w9WgXcQ" --lang en --translate zh-Hans
```

## Requirements

`uv` on `PATH`. Nothing else — the first run downloads the dependency into uv's
cache.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Keep `scripts/get_transcript.py` executable (`chmod +x`) if you copy this skill
around by hand. Never copy a `.venv/` directory between machines — virtualenv
scripts hardcode absolute paths and break.

## Notes

- The library scrapes YouTube's timed-text endpoint — no API key needed. It is **IP-blocked** by YouTube on cloud/datacenter IPs (`RequestBlocked`/`IpBlocked`); from a normal home/office (residential) IP it works.
- If you hit an IP block, either run the command from a machine with a residential IP, or pass a proxy with a clean residential IP via `--proxy` (or export `HTTPS_PROXY`). Free datacenter proxies will also be blocked — a residential proxy is what works reliably.
- `--native-tls` is baked into the shebang. It makes uv use the system certificate store, which is required behind a TLS-intercepting corporate proxy (without it: `invalid peer certificate: UnknownIssuer` when uv reaches PyPI) and harmless everywhere else.
- Some videos have transcripts disabled (`TranscriptsDisabled`) or none in the requested language — use `--list` to inspect, then pick a `--lang`.
- Exit codes: `0` ok, `2` bad usage/url, `3` no transcript / fetch error.
