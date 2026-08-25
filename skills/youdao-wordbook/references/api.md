# Youdao Wordbook API Notes

Observed on 2026-05-11 from `https://www.youdao.com/webwordbook/wordlist`.

Base URL:

```text
https://dict.youdao.com/wordbook
```

Endpoints used by the current web UI:

```text
GET /webapi/v2/word/list
GET /webapi/v2/opts
GET /webapi/books
GET /webapi/v2/ajax/collect
GET /webapi/v2/ajax/add
GET /webapi/v2/ajax/del
GET /webapi/v2/word/del
```

The list endpoint is read-only and requires logged-in Youdao cookies.

List parameters:

```text
limit   page size; the web UI uses 48
offset  zero-based row offset
sort    time or alpha; empty is accepted by the UI
lanFrom optional source language filter
lanTo   optional target language filter
```

Expected response shape:

```json
{
  "code": 0,
  "msg": "",
  "data": {
    "itemList": [
      {
        "itemId": "...",
        "word": "...",
        "trans": "...",
        "lanFrom": "en",
        "lanTo": "zh-CHS"
      }
    ],
    "total": 1
  }
}
```

Unauthenticated response:

```json
{"code":401,"msg":"用户未登录","data":null}
```

The web UI only displays `word`, `trans`, `lanFrom`, `lanTo`, and `itemId`. If the API returns add-time metadata, the exporter normalizes common field names such as `createTime`, `createdTime`, `addTime`, `time`, `date`, and timestamp variants into `added_at`, while preserving the complete raw item.

## Add and Delete Notes

Observed from the result page frontend bundle on 2026-05-11:

```text
GET /webapi/v2/ajax/collect?word=<word>&lan=<language>
GET /webapi/v2/ajax/add?word=<word>&lan=<language>
GET /webapi/v2/ajax/del?word=<word>
GET /webapi/v2/word/del?itemId=<itemId>
```

Behavior inferred from the web UI:

- `ajax/collect` checks whether a result-page word is already collected.
- `ajax/add` adds the word to the wordbook. The result page passes `word` and `lan`; if `lan` is absent, the frontend defaults to `eng`.
- `ajax/del` removes a collected result-page word by `word`.
- `word/del` removes a wordbook list item by `itemId`.

Unauthenticated calls return:

```json
{"code":401,"msg":"用户未登录","data":null}
```

These endpoints mutate the user's Youdao account. Require explicit user confirmation before calling `ajax/add`, `ajax/del`, or `word/del`; prefer `collect` and `list` first to avoid duplicate or accidental changes.
