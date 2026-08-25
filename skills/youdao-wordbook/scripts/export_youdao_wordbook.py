#!/usr/bin/env python3
"""Export Youdao wordbook entries for review.

The script uses only Python standard-library modules. Authentication is supplied
through an existing logged-in Cookie header, a cookie jar, Playwright
storage_state.json, or a validated cookie cached under the skill.

Cookie lifecycle
----------------
1. A cookie is resolved from (in order) --cookie, YOUDAO_COOKIE, --cookie-file,
   or the cached cookie saved under the skill.
2. If no cookie is available at all, the script exits with EXIT_NO_COOKIE (2)
   and prints browser instructions so the agent can ask the user for one.
3. The first API request validates the cookie. If Youdao reports the session is
   not logged in, the script exits with EXIT_AUTH_FAILED (3), clearing any stale
   cached cookie so the agent asks for a fresh one.
4. When a freshly supplied cookie works, it is saved to the cache so later runs
   need no cookie input. The cache lives in the user's config directory
   (~/.config/youdao-wordbook/cookie.json, mode 0600), never inside the skill,
   so a credential can't end up in a git checkout of the skill.

Exit codes
----------
0  success
1  generic error
2  no cookie supplied (ask the user to fetch one from the browser)
3  cookie invalid or expired (ask the user for a fresh cookie)
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable


BASE_URL = "https://dict.youdao.com/wordbook"
LIST_URL = f"{BASE_URL}/webapi/v2/word/list"
OPTS_URL = f"{BASE_URL}/webapi/v2/opts"
REFERER = "https://www.youdao.com/webwordbook/wordlist"

SKILL_DIR = Path(__file__).resolve().parent.parent


def default_cookie_store() -> Path:
    """Cache the cookie in the user's config dir, never inside the skill.

    The skill directory is often a symlink into a git checkout, so writing a
    live session cookie there is one `git add -A` away from being published.
    """
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base).expanduser() / "youdao-wordbook" / "cookie.json"


DEFAULT_COOKIE_STORE = default_cookie_store()
# Older versions cached here. Read it if it is still around, never write it.
LEGACY_COOKIE_STORE = SKILL_DIR / ".youdao_cookie.json"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NO_COOKIE = 2
EXIT_AUTH_FAILED = 3

BROWSER_COOKIE_HELP = """\
No saved Youdao login was found. Get a fresh cookie from a logged-in browser:

  1. Open https://www.youdao.com/webwordbook/wordlist and make sure you are
     logged in (your words are visible).
  2. Open DevTools (F12 / Cmd+Option+I) -> Network tab, then refresh the page.
  3. Click any request to dict.youdao.com, find Request Headers -> Cookie, and
     copy the entire Cookie value.
  4. Hand that Cookie string back so it can be saved for future runs.

The cookie must include DICT_SESS and DICT_LOGIN, or the session is not valid.\
"""

REAUTH_COOKIE_HELP = """\
The saved Youdao cookie is invalid or expired (Youdao says you are not logged
in). Fetch a fresh cookie the same way:

  1. Open https://www.youdao.com/webwordbook/wordlist logged in.
  2. DevTools -> Network -> refresh -> click a dict.youdao.com request.
  3. Copy the full Request Headers -> Cookie value (needs DICT_SESS + DICT_LOGIN).
  4. Provide it so it can replace the stale cookie.\
"""

TIME_KEYS = (
    "createTime",
    "createdTime",
    "createdAt",
    "addTime",
    "addedTime",
    "addedAt",
    "time",
    "date",
    "timestamp",
    "updateTime",
    "modifiedTime",
)
CSV_FIELDS = (
    "word",
    "translation",
    "item_id",
    "lan_from",
    "lan_to",
    "added_at",
    "added_at_source",
    "fetched_at",
    "raw_json",
)


class YoudaoError(RuntimeError):
    pass


class YoudaoAuthError(YoudaoError):
    """Raised when Youdao rejects the cookie as not logged in / expired."""


class NoCookieError(YoudaoError):
    """Raised when no cookie could be resolved from any source."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export logged-in Youdao wordbook entries.")
    parser.add_argument("--cookie", help="Raw Cookie header. Defaults to YOUDAO_COOKIE.")
    parser.add_argument("--cookie-file", help="Cookie string, Netscape cookie jar, or Playwright storage_state.json.")
    parser.add_argument(
        "--cookie-store",
        help=f"Where to cache a validated cookie. Defaults to {DEFAULT_COOKIE_STORE}.",
    )
    parser.add_argument(
        "--no-save-cookie",
        action="store_true",
        help="Do not cache a freshly supplied cookie after it validates.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate (and cache) the cookie, then report status without exporting.",
    )
    parser.add_argument("--format", choices=("jsonl", "csv", "md"), default="jsonl")
    parser.add_argument("--output", help="Output file. Defaults to stdout.")
    parser.add_argument("--limit", type=int, default=100, help="Page size for the API.")
    parser.add_argument("--sort", choices=("time", "alpha", ""), default="time")
    parser.add_argument("--lan-from", default="", help="Optional source language filter.")
    parser.add_argument("--lan-to", default="", help="Optional target language filter.")
    parser.add_argument("--sleep", type=float, default=0.15, help="Seconds to sleep between page requests.")
    parser.add_argument("--max-pages", type=int, default=0, help="Optional cap for debugging.")
    parser.add_argument("--include-opts", action="store_true", help="Fetch language options before exporting.")
    return parser.parse_args()


def cookie_store_path(args: argparse.Namespace) -> Path:
    if args.cookie_store:
        return Path(args.cookie_store).expanduser()
    return DEFAULT_COOKIE_STORE


def resolve_cookie(args: argparse.Namespace) -> tuple[str, str]:
    """Return (cookie, source) where source is arg/env/file/cache.

    Fresh sources (arg/env/file) take priority over the cache so a newly
    supplied cookie can replace a stale one. Raises NoCookieError if nothing is
    available.
    """
    if args.cookie:
        return args.cookie.strip(), "arg"
    if os.environ.get("YOUDAO_COOKIE"):
        return os.environ["YOUDAO_COOKIE"].strip(), "env"
    if args.cookie_file:
        return cookie_from_file(Path(args.cookie_file)), "file"
    cached = load_cached_cookie(cookie_store_path(args))
    if cached:
        return cached, "cache"
    legacy = load_cached_cookie(LEGACY_COOKIE_STORE)
    if legacy:
        return legacy, "legacy-cache"
    raise NoCookieError("No cookie supplied and no cached cookie found.")


def cookie_from_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise YoudaoError(f"Cookie file is empty: {path}")

    if text.startswith("{") or text.startswith("["):
        return cookie_from_json(json.loads(text))
    if "\t" in text:
        jar_cookie = cookie_from_netscape(text)
        if jar_cookie:
            return jar_cookie
    return text


def cookie_from_json(data: Any) -> str:
    cookies = data.get("cookies", []) if isinstance(data, dict) else data
    pairs: list[str] = []
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        domain = str(cookie.get("domain", ""))
        if "youdao.com" not in domain:
            continue
        name = cookie.get("name")
        value = cookie.get("value")
        if name and value is not None:
            pairs.append(f"{name}={value}")
    if not pairs:
        raise YoudaoError("No youdao.com cookies found in JSON cookie file.")
    return "; ".join(pairs)


def cookie_from_netscape(text: str) -> str:
    pairs: list[str] = []
    now = int(time.time())
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _flag, _path, _secure, expires, name, value = parts[:7]
        if "youdao.com" not in domain:
            continue
        try:
            if int(expires) and int(expires) < now:
                continue
        except ValueError:
            pass
        pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def load_cached_cookie(path: Path) -> str:
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return ""
    if not raw:
        return ""
    if raw.startswith("{"):
        try:
            cookie = json.loads(raw).get("cookie", "")
        except json.JSONDecodeError:
            return ""
        return str(cookie).strip()
    return raw


def save_cached_cookie(path: Path, cookie: str) -> bool:
    payload = json.dumps(
        {"cookie": cookie, "saved_at": dt.datetime.now(dt.timezone.utc).isoformat()},
        ensure_ascii=False,
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600, owner-only
        return True
    except OSError as exc:
        print(f"warning: could not cache cookie at {path}: {exc}", file=sys.stderr)
        return False


def clear_cached_cookie(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        print(f"warning: could not remove stale cookie at {path}: {exc}", file=sys.stderr)


def request_json(url: str, cookie: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if params:
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v != ""})
        url = f"{url}?{query}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json, text/plain, */*",
            "Cookie": cookie,
            "Referer": REFERER,
            "User-Agent": "Mozilla/5.0 YoudaoWordbookExporter/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code in (401, 403):
            raise YoudaoAuthError(f"HTTP {exc.code} from Youdao: {body[:200]}") from exc
        raise YoudaoError(f"HTTP {exc.code} from Youdao: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise YoudaoError(f"Failed to reach Youdao: {exc}") from exc

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise YoudaoError(f"Non-JSON response from Youdao: {body[:300]}") from exc

    code = data.get("code")
    if code not in (0, "0", None):
        msg = data.get("msg") or data.get("message") or "unknown error"
        if str(code) == "401" or "未登录" in str(msg) or "登录" in str(msg):
            raise YoudaoAuthError(f"Youdao says not logged in (code={code}): {msg}")
        raise YoudaoError(f"Youdao API returned code={code}: {msg}")
    return data


def validate_cookie(cookie: str) -> int:
    """Probe the list API with a tiny request. Returns the reported total.

    Raises YoudaoAuthError if the session is not logged in.
    """
    data = request_json(LIST_URL, cookie, {"limit": 1, "offset": 0, "sort": "time"})
    payload = data.get("data") or {}
    total_value = payload.get("total")
    return int(total_value) if str(total_value).isdigit() else 0


def export_words(args: argparse.Namespace, cookie: str) -> list[dict[str, Any]]:
    if args.limit <= 0:
        raise YoudaoError("--limit must be positive.")

    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()
    if args.include_opts:
        request_json(OPTS_URL, cookie)

    records: list[dict[str, Any]] = []
    offset = 0
    page = 0
    total: int | None = None

    while True:
        page += 1
        params = {
            "limit": args.limit,
            "offset": offset,
            "sort": args.sort,
            "lanFrom": args.lan_from,
            "lanTo": args.lan_to,
        }
        data = request_json(LIST_URL, cookie, params)
        payload = data.get("data") or {}
        items = payload.get("itemList") or []
        if total is None:
            total_value = payload.get("total")
            total = int(total_value) if str(total_value).isdigit() else None
        for item in items:
            if isinstance(item, dict):
                records.append(normalize_item(item, fetched_at))

        if not items:
            break
        offset += len(items)
        if total is not None and offset >= total:
            break
        if args.max_pages and page >= args.max_pages:
            break
        time.sleep(args.sleep)

    return records


def normalize_item(item: dict[str, Any], fetched_at: str) -> dict[str, Any]:
    added_at, source = find_added_time(item)
    return {
        "word": item.get("word") or item.get("query") or item.get("name") or "",
        "translation": item.get("trans") or item.get("translation") or item.get("explain") or "",
        "item_id": item.get("itemId") or item.get("id") or "",
        "lan_from": item.get("lanFrom") or item.get("from") or "",
        "lan_to": item.get("lanTo") or item.get("to") or "",
        "added_at": added_at,
        "added_at_source": source,
        "fetched_at": fetched_at,
        "raw": item,
    }


def find_added_time(item: dict[str, Any]) -> tuple[str, str]:
    for key in TIME_KEYS:
        if key in item and item[key] not in (None, ""):
            parsed = parse_time(item[key])
            return parsed, key
    for key, value in walk_scalars(item):
        lower_key = key.lower()
        if ("time" in lower_key or "date" in lower_key) and value not in (None, ""):
            return parse_time(value), key
    return "", ""


def walk_scalars(value: Any, prefix: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            yield from walk_scalars(child, child_prefix)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_scalars(child, f"{prefix}[{index}]")
    else:
        yield prefix, value


def parse_time(value: Any) -> str:
    if isinstance(value, (int, float)):
        return epoch_to_iso(float(value))
    text = str(value).strip()
    if not text:
        return ""
    if text.isdigit():
        return epoch_to_iso(float(text))
    normalized = text.replace("/", "-")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        return dt.datetime.fromisoformat(normalized).isoformat()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(normalized, fmt).isoformat()
        except ValueError:
            continue
    return text


def epoch_to_iso(value: float) -> str:
    if value > 10_000_000_000:
        value = value / 1000
    return dt.datetime.fromtimestamp(value, tz=dt.timezone.utc).isoformat()


def write_records(records: list[dict[str, Any]], fmt: str, output: str | None) -> None:
    if output:
        path = Path(output).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("w", encoding="utf-8", newline="")
        should_close = True
    else:
        handle = sys.stdout
        should_close = False
    try:
        if fmt == "jsonl":
            write_jsonl(records, handle)
        elif fmt == "csv":
            write_csv(records, handle)
        elif fmt == "md":
            write_markdown(records, handle)
    finally:
        if should_close:
            handle.close()


def serializable(record: dict[str, Any]) -> dict[str, Any]:
    return record


def write_jsonl(records: list[dict[str, Any]], handle: Any) -> None:
    for record in records:
        handle.write(json.dumps(serializable(record), ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def write_csv(records: list[dict[str, Any]], handle: Any) -> None:
    writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for record in records:
        row = {key: record.get(key, "") for key in CSV_FIELDS if key != "raw_json"}
        row["raw_json"] = json.dumps(record.get("raw", {}), ensure_ascii=False, sort_keys=True)
        writer.writerow(row)


def write_markdown(records: list[dict[str, Any]], handle: Any) -> None:
    handle.write("| word | translation | added_at | lan_from | lan_to | item_id |\n")
    handle.write("|---|---|---|---|---|---|\n")
    for record in records:
        values = [
            record.get("word", ""),
            record.get("translation", ""),
            record.get("added_at", ""),
            record.get("lan_from", ""),
            record.get("lan_to", ""),
            record.get("item_id", ""),
        ]
        handle.write("| " + " | ".join(escape_md(str(v)) for v in values) + " |\n")


def escape_md(text: str) -> str:
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def run(args: argparse.Namespace) -> int:
    store = cookie_store_path(args)

    try:
        cookie, source = resolve_cookie(args)
    except NoCookieError:
        print(BROWSER_COOKIE_HELP, file=sys.stderr)
        return EXIT_NO_COOKIE
    except YoudaoError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    # A legacy-cache cookie is re-saved so it migrates out of the skill dir.
    is_fresh = source != "cache"
    should_save = is_fresh and not args.no_save_cookie

    # --check: validate (and cache) the cookie, then stop.
    if args.check:
        try:
            total = validate_cookie(cookie)
        except YoudaoAuthError:
            if source == "cache":
                clear_cached_cookie(store)
            elif source == "legacy-cache":
                clear_cached_cookie(LEGACY_COOKIE_STORE)
            print(REAUTH_COOKIE_HELP, file=sys.stderr)
            return EXIT_AUTH_FAILED
        except YoudaoError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_ERROR
        if should_save and save_cached_cookie(store, cookie):
            print(f"cookie valid ({total} words); saved to {store}", file=sys.stderr)
        else:
            print(f"cookie valid ({total} words); source={source}", file=sys.stderr)
        return EXIT_OK

    # Normal export. The first request doubles as cookie validation.
    try:
        records = export_words(args, cookie)
    except YoudaoAuthError:
        if source == "cache":
            clear_cached_cookie(store)
        elif source == "legacy-cache":
            clear_cached_cookie(LEGACY_COOKIE_STORE)
        print(REAUTH_COOKIE_HELP, file=sys.stderr)
        return EXIT_AUTH_FAILED
    except YoudaoError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    write_records(records, args.format, args.output)

    if should_save:
        save_cached_cookie(store, cookie)

    destination = args.output or "stdout"
    print(f"exported {len(records)} records to {destination}", file=sys.stderr)
    return EXIT_OK


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
