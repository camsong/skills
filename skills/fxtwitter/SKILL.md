---
name: fxtwitter
description: Fetch X posts and X Articles via api.fxtwitter.com, including article text, images, the replied-to post, and posts embedded in an article. Use when the user pastes an x.com or twitter.com status link, asks to read, summarize, or save a tweet, or asks for an X Article.
---

# fxtwitter

Fetch one status with `scripts/fetch.py`. The script calls `https://api.fxtwitter.com` (no API key). An X Article is the `article` object on the status that shares it.

## Fetch

The script lives at `scripts/fetch.py` inside this skill's directory, which the harness injects when the skill loads.

```bash
FX=<this skill's directory>
python3 "$FX/scripts/fetch.py" "<status URL or id>" --expand-parent --expand-embeds
```

Add `--download <dir>` when the user wants the photo files saved. Write that directory outside the repo. The script stores photos only. Video stays a URL on `media`.

Done when stdout is one JSON object with `"ok": true`, `post.text` is present, and a present `post.article` has non-empty `markdown` or `preview_text`.

`/i/article/<id>` has no status body. The script exits 1. Ask for the status URL that shares the article.

## Read the result

Answer in the user's language from these fields:

- `post` — author, text, time, stats, `media`
- `post.article` — title and `markdown`; images sit in `article.images` and inside the markdown
- `post.parent` — the status this post replies to, when `--expand-parent` found one
- `post.embeds` — posts embedded in the article, when `--expand-embeds` found any
- `path` on a photo — local file, only after `--download`

Lead with the article markdown when `post.article` is present. Otherwise lead with `post.text`, then `parent` when the status is only a reply. Include photo and video URLs the user would need to see the post.

## Failures

A failed run prints `{"ok": false, "error": ...}` to stderr and exits 1. Success JSON stays on stdout.

- `PRIVATE_TWEET` or api code 401: the account is protected. Say it cannot be read.
- `NOT_FOUND` or api code 404: the status is missing or deleted.
- Any other `error`: report that message.

## Requirements

Python 3.9 or newer. The script uses the standard library only.

The public API is free and unauthenticated. Keep requests to the posts the user asked for. `--max-embeds` defaults to 10.
