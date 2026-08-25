---
name: youdao-wordbook
description: 获取网易有道单词本词句列表并导出复习数据；当用户要同步、备份、分析、复习有道单词本，或需要记录单词、释义、语言方向、添加时间、itemId 等字段时使用。
---

# Youdao Wordbook

## Overview

Use this skill to export the user's Youdao wordbook from the logged-in web API and turn it into review-friendly JSONL, CSV, or Markdown.

The web page is `https://www.youdao.com/webwordbook/wordlist`; the current list API is documented in `references/api.md`.

## Cookie Lifecycle

The script manages the login cookie for you. It resolves a cookie from, in
order: `--cookie`, `YOUDAO_COOKIE`, `--cookie-file`, then a validated cookie
cached at `~/.config/youdao-wordbook/cookie.json` (owner-only `0600`; outside
the skill directory, so it can never land in a git checkout). It signals what
to do next through exit codes, so **do not ask the user for a cookie up
front** — just run the script and react:

| Exit | Meaning | What to do |
|------|---------|------------|
| `0` | Success. A freshly supplied cookie was validated and cached. | Report the result. Future runs need no cookie. |
| `2` | No cookie anywhere (first use). | Show the user the browser steps the script printed, get a Cookie string, and re-run with `--cookie`. |
| `3` | Cookie invalid or expired (stale cache is auto-cleared). | Tell the user it expired, ask for a fresh Cookie string, and re-run with `--cookie`. |
| `1` | Other error. | Surface the printed message. |

Once a cookie is cached, later runs just work with no cookie argument — never
re-prompt the user unless the script returns exit `2` or `3`.

The exporter is at `scripts/export_youdao_wordbook.py` inside this skill's
directory, which the harness injects when the skill loads. It uses only the
Python standard library — no install step.

## Workflow

1. Confirm where the user wants the exported vocabulary saved. If unspecified, write outside any git repo, for example `~/Documents/youdao-wordbook/`.
2. Run `scripts/export_youdao_wordbook.py` with the desired format and output path, **without** a cookie argument first — the cached cookie is used if present.
3. Branch on the exit code (table above):
   - `2` (first use): relay the printed browser instructions, obtain a Cookie header string from the user, then re-run adding `--cookie '<string>'`. On success the cookie is cached automatically.
   - `3` (expired): tell the user the saved login expired, obtain a fresh Cookie string, then re-run with `--cookie '<string>'`.
   - `0`: done.
4. Check the summary count and inspect the first few rows. If `added_at` is empty, inspect each row's `raw` / `raw_json` because Youdao may rename or omit the add-time field.

To validate and cache a cookie without exporting (e.g. a first-time setup step), run with `--check`:

```bash
python scripts/export_youdao_wordbook.py --check --cookie 'DICT_SESS=...; DICT_LOGIN=...'
```

The user obtains the Cookie string from a logged-in browser: open
`https://www.youdao.com/webwordbook/wordlist`, DevTools → Network → refresh →
click a `dict.youdao.com` request → copy the full Request Headers → Cookie value
(it must contain `DICT_SESS` and `DICT_LOGIN`).

## Quick Commands

Cookie string:

```bash
YOUDAO_COOKIE='DICT_...=...; OUTFOX_SEARCH_USER_ID=...' \
python scripts/export_youdao_wordbook.py \
  --format csv \
  --output "$HOME/Documents/youdao-wordbook/youdao-wordbook.csv"
```

Cookie file:

```bash
python scripts/export_youdao_wordbook.py \
  --cookie-file "$HOME/Downloads/youdao-cookies.txt" \
  --format jsonl \
  --output "$HOME/Documents/youdao-wordbook/youdao-wordbook.jsonl"
```

Markdown review sheet:

```bash
python scripts/export_youdao_wordbook.py \
  --cookie-file "$HOME/Downloads/youdao-storage-state.json" \
  --format md \
  --output "$HOME/Documents/youdao-wordbook/review.md"
```

## Output Fields

The script emits normalized fields:

- `word`
- `translation`
- `item_id`
- `lan_from`
- `lan_to`
- `added_at`
- `added_at_source`
- `fetched_at`
- `raw` for JSONL, or `raw_json` for CSV/Markdown

Keep `raw` when the user cares about auditability or future migrations.

## Safety Notes

- Do not commit exported wordbook data or cookies. The cached cookie lives at `~/.config/youdao-wordbook/cookie.json` (or `$XDG_CONFIG_HOME/youdao-wordbook/cookie.json`), is written `0600`, and is deliberately outside the skill directory — installing this skill as a symlink into a git checkout must never put a live session cookie inside that repo.
- Do not print full cookies in the final answer. When a cookie expires, remind the user the previous credential may still be recoverable from chat history and they can re-login on Youdao to invalidate it.
- The export script only performs read-only GET requests.
- Add/delete endpoints exist, but they mutate the user's Youdao account. Only call them after explicit confirmation.
