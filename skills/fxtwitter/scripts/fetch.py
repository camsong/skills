#!/usr/bin/env python3
"""Fetch an X post or X Article through api.fxtwitter.com.

Prints one JSON object to stdout. Exit 0 when ok is true.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.fxtwitter.com"
USER_AGENT = "fxtwitter-skill/1.0"
TIMEOUT = 30

STATUS_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:(?:mobile|www)\.)?(?:x|twitter|fxtwitter|vxtwitter|fixupx)\.com/"
    r"(?:(?P<handle>[A-Za-z0-9_]+)/status(?:es)?|i/web/status)/(?P<id>\d+)",
    re.I,
)
ARTICLE_RE = re.compile(r"(?:x|twitter)\.com/i/article/(?P<id>\d+)", re.I)
ID_RE = re.compile(r"^\d{10,25}$")

HEADERS = {
    "header-one": "#",
    "header-two": "##",
    "header-three": "###",
    "header-four": "####",
    "header-five": "#####",
    "header-six": "######",
}


def emit(payload: dict, code: int = 0) -> None:
    stream = sys.stdout if code == 0 else sys.stderr
    json.dump(payload, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
    raise SystemExit(code)


def fail(message: str, **extra) -> None:
    emit({"ok": False, "error": message, **extra}, 1)


def get_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            fail(f"HTTP {exc.code} from {url}", http_status=exc.code)
        if isinstance(data, dict):
            return data
        fail(f"HTTP {exc.code} from {url}", http_status=exc.code)
    except urllib.error.URLError as exc:
        fail(f"request failed: {exc.reason}")
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        fail("response was not JSON", url=url)
    if not isinstance(data, dict):
        fail("response was not a JSON object", url=url)
    return data


def parse_target(raw: str) -> tuple[str | None, str]:
    text = raw.strip()
    article = ARTICLE_RE.search(text)
    if article and not STATUS_RE.search(text):
        fail(
            "X Article pages are loaded from the status that shares them. Pass that status URL, not /i/article/.",
            article_id=article.group("id"),
        )
    match = STATUS_RE.search(text)
    if match:
        return match.group("handle"), match.group("id")
    if ID_RE.match(text):
        return None, text
    fail("pass a status URL or a numeric status id", input=text)


def fetch_status(status_id: str, handle: str | None) -> dict:
    path = f"/{handle}/status/{status_id}" if handle else f"/status/{status_id}"
    data = get_json(API + path)
    code = data.get("code")
    if code != 200 or "tweet" not in data:
        message = data.get("message") or "fetch failed"
        fail(str(message), api_code=code, status_id=status_id)
    return data["tweet"]


def index_entities(entity_map) -> dict:
    out = {}
    if isinstance(entity_map, dict):
        for key, value in entity_map.items():
            out[str(key)] = value or {}
    elif isinstance(entity_map, list):
        for item in entity_map:
            if isinstance(item, dict) and "key" in item:
                out[str(item["key"])] = item.get("value") or {}
    return out


def index_article_media(media_entities) -> dict:
    out = {}
    for ent in media_entities or []:
        if not isinstance(ent, dict):
            continue
        mid = str(ent.get("media_id") or "")
        info = ent.get("media_info") or {}
        url = info.get("original_img_url")
        if mid and url:
            out[mid] = {
                "type": "photo",
                "url": url,
                "width": info.get("original_img_width"),
                "height": info.get("original_img_height"),
                "alt": info.get("alt_text") or "",
            }
    return out


def entity_link(entity: dict) -> str | None:
    if (entity or {}).get("type") != "LINK":
        return None
    return ((entity.get("data") or {}).get("url")) or None


def render_inline(text: str, block: dict, entities: dict) -> str:
    n = len(text)
    link_at = [None] * n
    bold = [False] * n
    italic = [False] * n
    for rng in block.get("entityRanges") or []:
        url = entity_link(entities.get(str(rng.get("key"))))
        if not url:
            continue
        start = int(rng.get("offset") or 0)
        end = min(n, start + int(rng.get("length") or 0))
        for i in range(max(0, start), end):
            link_at[i] = url
    for rng in block.get("inlineStyleRanges") or []:
        style = rng.get("style")
        start = int(rng.get("offset") or 0)
        end = min(n, start + int(rng.get("length") or 0))
        for i in range(max(0, start), end):
            if style == "Bold":
                bold[i] = True
            elif style == "Italic":
                italic[i] = True

    parts = []
    i = 0
    while i < n:
        j = i + 1
        while j < n and link_at[j] == link_at[i] and bold[j] == bold[i] and italic[j] == italic[i]:
            j += 1
        chunk = text[i:j]
        if bold[i] and italic[i]:
            chunk = f"***{chunk}***"
        elif bold[i]:
            chunk = f"**{chunk}**"
        elif italic[i]:
            chunk = f"*{chunk}*"
        if link_at[i]:
            chunk = f"[{chunk}]({link_at[i]})"
        parts.append(chunk)
        i = j
    return "".join(parts)


def media_items_from_entity(entity: dict, media_index: dict) -> list[dict]:
    data = (entity or {}).get("data") or {}
    caption = data.get("caption") or ""
    items = []
    for item in data.get("mediaItems") or []:
        info = media_index.get(str(item.get("mediaId") or ""))
        if not info:
            continue
        copied = dict(info)
        if caption:
            copied["caption"] = caption
        items.append(copied)
    return items


def first_entity(block: dict, entities: dict) -> dict | None:
    ranges = block.get("entityRanges") or []
    if not ranges:
        return None
    return entities.get(str(ranges[0].get("key")))


def render_article(article: dict) -> tuple[str, list[dict], list[str]]:
    content = article.get("content") or {}
    entities = index_entities(content.get("entityMap"))
    media_index = index_article_media(article.get("media_entities"))
    images: list[dict] = []
    embed_ids: list[str] = []
    lines: list[str] = []

    title = (article.get("title") or "").strip()
    if title:
        lines.append(f"# {title}")
        lines.append("")

    cover = ((article.get("cover_media") or {}).get("media_info") or {})
    cover_url = cover.get("original_img_url")
    if cover_url:
        cover_item = {
            "type": "photo",
            "url": cover_url,
            "width": cover.get("original_img_width"),
            "height": cover.get("original_img_height"),
            "alt": "cover",
        }
        images.append(cover_item)
        lines.append(f"![cover]({cover_url})")
        lines.append("")

    list_kinds = {"unordered-list-item", "ordered-list-item"}
    prev_kind = None
    for block in content.get("blocks") or []:
        kind = block.get("type") or "unstyled"
        text = block.get("text") or ""
        if kind in list_kinds and kind == prev_kind and lines and lines[-1] == "":
            lines.pop()
        if kind == "atomic":
            entity = first_entity(block, entities) or {}
            etype = entity.get("type")
            if etype == "MEDIA":
                for item in media_items_from_entity(entity, media_index):
                    images.append(item)
                    alt = item.get("caption") or item.get("alt") or "image"
                    lines.append(f"![{alt}]({item['url']})")
                    if item.get("caption"):
                        lines.append("")
                        lines.append(item["caption"])
                    lines.append("")
            elif etype == "TWEET":
                tweet_id = str((entity.get("data") or {}).get("tweetId") or "")
                if tweet_id:
                    embed_ids.append(tweet_id)
                    lines.append(f"[embedded post {tweet_id}](https://x.com/i/status/{tweet_id})")
                    lines.append("")
            elif etype == "DIVIDER":
                lines.append("---")
                lines.append("")
            prev_kind = kind
            continue

        style_block = block
        if kind in HEADERS:
            style_block = dict(block)
            style_block["inlineStyleRanges"] = []
        rendered = render_inline(text, style_block, entities).strip()
        if not rendered:
            continue
        if kind in HEADERS:
            lines.append(f"{HEADERS[kind]} {rendered}")
        elif kind == "unordered-list-item":
            lines.append(f"- {rendered}")
        elif kind == "ordered-list-item":
            lines.append(f"1. {rendered}")
        elif kind == "blockquote":
            lines.append("> " + rendered.replace("\n", "\n> "))
        else:
            lines.append(rendered)
        lines.append("")
        prev_kind = kind

    markdown = "\n".join(lines).strip() + ("\n" if lines else "")
    if not markdown.strip():
        preview = (article.get("preview_text") or "").strip()
        if preview:
            markdown = preview + "\n"
    return markdown, images, embed_ids


def status_media(tweet: dict) -> list[dict]:
    media = tweet.get("media") or {}
    items = media.get("all") or []
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "photo":
            out.append(
                {
                    "type": "photo",
                    "url": item.get("url"),
                    "width": item.get("width"),
                    "height": item.get("height"),
                }
            )
        elif kind in ("video", "gif"):
            url = item.get("url")
            formats = item.get("formats") or item.get("variants") or []
            mp4s = [f for f in formats if str(f.get("url", "")).endswith(".mp4") or f.get("container") == "mp4" or f.get("content_type") == "video/mp4"]
            if mp4s:
                mp4s.sort(key=lambda f: int(f.get("bitrate") or 0))
                url = mp4s[-1].get("url") or url
            out.append(
                {
                    "type": kind,
                    "url": url,
                    "thumbnail_url": item.get("thumbnail_url"),
                    "width": item.get("width"),
                    "height": item.get("height"),
                    "duration": item.get("duration"),
                }
            )
    return [item for item in out if item.get("url")]


def summarize(tweet: dict, *, with_article: bool = True) -> dict:
    author = tweet.get("author") or {}
    post = {
        "id": str(tweet.get("id") or ""),
        "url": tweet.get("url"),
        "text": tweet.get("text") or "",
        "created_at": tweet.get("created_at"),
        "author": {
            "name": author.get("name"),
            "screen_name": author.get("screen_name"),
        },
        "stats": {
            "replies": tweet.get("replies"),
            "retweets": tweet.get("retweets"),
            "likes": tweet.get("likes"),
            "bookmarks": tweet.get("bookmarks"),
            "quotes": tweet.get("quotes"),
            "views": tweet.get("views"),
        },
        "replying_to": tweet.get("replying_to"),
        "replying_to_status": tweet.get("replying_to_status"),
        "media": status_media(tweet),
    }
    quote = tweet.get("quote")
    if isinstance(quote, dict) and quote.get("id"):
        post["quote"] = summarize(quote, with_article=False)
    article = tweet.get("article") if with_article else None
    if isinstance(article, dict) and (article.get("title") or article.get("content") or article.get("preview_text")):
        markdown, images, embed_ids = render_article(article)
        post["article"] = {
            "id": article.get("rest_id") or article.get("id"),
            "title": (article.get("title") or "").strip() or None,
            "preview_text": article.get("preview_text"),
            "markdown": markdown,
            "images": images,
        }
        post["embedded_status_ids"] = embed_ids
    else:
        post["embedded_status_ids"] = []
    return post


def download_photos(post: dict, dest: Path, seen: set[str]) -> None:
    dest.mkdir(parents=True, exist_ok=True)

    def save(item: dict, stem: str) -> None:
        url = item.get("url")
        if not url or url in seen or item.get("type") not in (None, "photo"):
            return
        if "video.twimg.com" in url:
            return
        suffix = ".jpg"
        match = re.search(r"\.(jpe?g|png|gif|webp)(?:\?|$)", url, re.I)
        if match:
            suffix = "." + match.group(1).lower().replace("jpeg", "jpg")
        path = dest / f"{stem}{suffix}"
        n = 2
        while path.exists():
            path = dest / f"{stem}-{n}{suffix}"
            n += 1
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                path.write_bytes(resp.read())
        except urllib.error.URLError as exc:
            item["download_error"] = str(exc.reason)
            return
        item["path"] = str(path)
        seen.add(url)

    for index, item in enumerate(post.get("media") or [], start=1):
        if item.get("type") == "photo":
            save(item, f"{post.get('id')}-media-{index}")
    article = post.get("article") or {}
    for index, item in enumerate(article.get("images") or [], start=1):
        save(item, f"{post.get('id')}-article-{index}")
    parent = post.get("parent")
    if isinstance(parent, dict):
        download_photos(parent, dest, seen)
    for embed in post.get("embeds") or []:
        download_photos(embed, dest, seen)
    quote = post.get("quote")
    if isinstance(quote, dict):
        download_photos(quote, dest, seen)


def attach_related(post: dict, *, expand_parent: bool, expand_embeds: bool, max_embeds: int) -> None:
    if expand_parent and post.get("replying_to_status"):
        parent_id = str(post["replying_to_status"])
        if parent_id != post.get("id"):
            parent = fetch_status(parent_id, None)
            post["parent"] = summarize(parent)
    if expand_embeds:
        embeds = []
        for status_id in (post.get("embedded_status_ids") or [])[:max_embeds]:
            if status_id == post.get("id"):
                continue
            embeds.append(summarize(fetch_status(status_id, None)))
        post["embeds"] = embeds
    else:
        post["embeds"] = []


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch an X post or X Article via api.fxtwitter.com")
    parser.add_argument("target", help="status URL or numeric status id")
    parser.add_argument("--expand-parent", action="store_true", help="also fetch the status this post replies to")
    parser.add_argument("--expand-embeds", action="store_true", help="also fetch posts embedded in an X Article")
    parser.add_argument("--max-embeds", type=int, default=10)
    parser.add_argument("--download", help="directory to save photo files into")
    args = parser.parse_args()

    handle, status_id = parse_target(args.target)
    tweet = fetch_status(status_id, handle)
    post = summarize(tweet)
    attach_related(
        post,
        expand_parent=args.expand_parent,
        expand_embeds=args.expand_embeds,
        max_embeds=max(0, args.max_embeds),
    )
    if args.download:
        download_photos(post, Path(args.download), set())
    emit({"ok": True, "post": post})


if __name__ == "__main__":
    main()
