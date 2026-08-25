---
name: youtube-reading-page
description: Turn a YouTube video into a long-form Chinese "reading version" — a blog-style article organized by topic, published as a shareable page (an Artifact Page on Claude Code, a self-contained HTML file elsewhere). Use whenever the user gives a YouTube URL or video id and wants it 重写成阅读版 / 精读版 / 博客版, 整理成文章, 做成 Page, 拆成小节, 提炼 framework，or says they want to understand the video without watching it. Also use for "把这个视频整理一下" / "帮我读一下这个演讲" / "总结成一篇文章" when a YouTube link is present. Not for a two-line summary — this skill deliberately produces long, detailed prose. For raw captions only, use youtube-transcript-api instead.
---

# YouTube → 阅读版 Page

把一段 YouTube 视频重写成可以替代观看的长文，再出成一个能直接读的页面。

读者的验收标准只有一条：**读完这篇就不需要再回去看视频了。** 所有取舍都服务于这一条——这也是为什么下面反复强调"不要浓缩"。浓缩是这个任务的失败模式，不是优点。

## 流程

### 1. 取源

一条命令拿到元数据和三种格式的字幕（`$SKILL` = 本 skill 所在目录，加载时由 harness 注入）：

```bash
"$SKILL/scripts/fetch_source.sh" "<URL>" <工作目录>
```

工作目录用 scratchpad，不要污染用户仓库。脚本会打印标题、频道、上传日期、时长、可用字幕语言和 snippet 数量。

脚本依赖 `youtube-transcript-api` skill 取字幕。它会先在同级 skill 目录里找，
找不到再去各 harness 的 skills 目录找；都没有就报错，此时用
`YT_TRANSCRIPT_SKILL=<那个 skill 的目录>` 显式指定。

如果视频有中文字幕，加 `--lang zh-Hans,zh,en` 优先取中文——从中文原文改写比从英文转译更保真。

脚本失败的两种常见情况：字幕被关闭（`TranscriptsDisabled`），或 IP 被封（`RequestBlocked`，机房 IP 必然触发）。两种都要如实告诉用户，不要转而去猜视频内容或从别处找摘要来填。

### 2. 完整读一遍 `.ts.txt`

**这一步不能跳，也不能只读开头和结尾。** 用 Read 分段把整个带时间戳的转录读完。

原因很直接：这个任务要求每个小节都足够详细，而细节只存在于转录的中间部分。只读首尾会写出一篇"看起来像那么回事"但没有信息量的文章——那恰好是这个 skill 要避免的东西。一小时的视频通常 1200–1600 条 snippet，分三到四次 Read 读完。

边读边记三样东西：

- **主题边界**——话题在哪一刻转向了。这些位置就是小节的分界，对应的时间码就是小节锚点。
- **硬数字**——倍数、百分比、年份、时长、成本。它们是后面"量级带"的素材，也是文章可信度的来源。
- **原话**——值得直接引用的句子。挑那些"改写会损失力量"的，不要挑普通陈述句。

### 3. 补元数据，但不要编

`fetch_source.sh` 给出标题、频道、上传日期。**转录里没有的信息一律不猜**：

- 主持人 / 访谈者姓名如果自始至终没被念出来，就写"转录中未具名"。写一个看起来合理的名字是编造事实。
- 嘉宾头衔同理，只写转录或页面元数据里出现过的。

### 4. 规划小节

按**主题**切，不按时间均分。一个小节 = 一个完整的论题，含它的背景、展开、数字、结论。

- 一小时的对谈通常落在 8–12 个小节。
- 每个小节挂一个时间码（该主题的起始位置），让读者能跳回原片核对。时间码是诚实的结构——素材本来就是带时间戳的；不要另外叠加 01/02/03 这类编号，除非内容真的是一个有序流程。
- 演讲类内容（单人、有讲稿）通常主题边界更清晰；对谈类需要你自己合并——同一个主题被主持人打断后又拐回来的情况很常见，合并进同一节。

### 5. 写

输出结构固定为四段。写作要求见 [references/writing-guide.md](references/writing-guide.md)，**动笔前读它**——那里是这个 skill 的实质内容，讲怎么把一节写到位、怎么处理转录错误、怎么抽 framework。

```
1. 元数据    标题 / 作者 / 网址（另可加发布日期、时长、字幕语言）
2. Overview  一段话点明核心论题与结论
3. 主题小节  按主题展开，每节挂时间码
4. 框架 & 心智模型  从内容中抽象出的可复用结构
```

### 6. 出页面

先定设计基调：当前 harness 有 `artifact-design` 这类设计 skill 就先调它，没有就按
writing-guide 的「页面设计」一节自己定。

**能发布 Artifact 的 harness（Claude Code）**

1. 页面写成 HTML 文件放 scratchpad，不要写 `<!DOCTYPE>` / `<html>` / `<head>` / `<body>`，
   只写页面内容，第一行给 `<title>`。
2. 调 Artifact 工具发布，带上 `favicon` 和一句话 `description`。
3. 把链接给用户，并说明 Page 默认私有。

**没有 Artifact 工具的 harness（Codex、Cursor 等）**

写成一个自包含的完整 HTML 文件——这次要带 `<!DOCTYPE html>` 和完整 head，CSS 内联，
不引外部资源，双击就能在浏览器里打开。默认写到用户指定的位置，没指定就问；不要往
用户的代码仓库里塞。最后把文件路径给用户。

两条路的正文内容完全一样，只有外壳不同。

页面设计的落地建议在 writing-guide 里，包括哪些视觉结构对这类长文真正有用（时间码栏、硬数字带）以及要避开的默认审美。

## 语言

默认**用英文思考、用中文输出**。专有名词保留英文原文，首次出现时在括号里给中文释义——`inference（推理）`、`context engineering（上下文工程）`。技术名词不要硬翻成生僻中文。

用户明确要求英文或其它语言时按用户的来。

## 三条不可让步的规则

**不新增事实。** 页面里的每一个论断都必须能在转录或视频元数据里找到出处。不要补充你知道的背景知识，不要引入视频没提到的例子，不要把"他大概是这个意思"写成他说了。转录含混的地方，保持原意并注明不确定。

**不浓缩。** 这是唯一一个"写长"优先于"写短"的任务。当你想把三段合成一句时，方向反了——应该是把一句展开成三段，用的是转录里本来就有的因果链、数字、限定条件和反例。

**转录错误要还原并标注。** 自动字幕的音近错误几乎必然存在（人名、机构名、缩写）。按上下文还原，并在正文相应位置用一个小的说明块标出原始转写和还原依据。悄悄改掉等于让读者无法核对，标注出来才是诚实的做法。
