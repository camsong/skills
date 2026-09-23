---
name: youtube-reading-page
description: Turn a YouTube video into a long-form Chinese "reading version" — a blog-style article organized by topic, built from a corrected transcript (re-transcribed with Gemini and cross-checked against YouTube captions when a Gemini key is available), illustrated with slide screenshots from the video, and published as a shareable page (an Artifact Page on Claude Code, a Lark/飞书 doc when the user asks for one, a self-contained HTML file elsewhere). Use whenever the user gives a YouTube URL or video id and wants it 重写成阅读版 / 精读版 / 博客版, 整理成文章, 做成 Page, 拆成小节, 提炼 framework，or says they want to understand the video without watching it. Also use for "把这个视频整理一下" / "帮我读一下这个演讲" / "总结成一篇文章" when a YouTube link is present. Not for a two-line summary — this skill deliberately produces long, detailed prose. For raw captions only, use youtube-transcript-api instead.
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

### 1a. 问一句有没有原版幻灯片

演讲类视频，开工前问用户一次：手上有没有讲者的原版幻灯片（PDF、HTML 或分享链接）。视频里一两秒就翻过的页、
被摄像头挡住的字、讲者没念出来的数字，原版里都在。

- **有**：按页抽出文字，存成 `<工作目录>/deck.txt`，每页前面标页码（PDF 用 `pdftotext -layout`；
  HTML 按每页的容器元素去掉标签，常见是 `<section>`）。之后名字怎么拼、数字多少、一张列表有几条，
  都以它为准，它比字幕和 Gemini 转写都可靠。截图也从原版渲染，见第 5b 步。
- **没有**：照常往下走，第 5b 步从视频里清点幻灯片。

原版幻灯片和音视频一样只放工作目录。

### 1b. 用 Gemini 做字幕双校验（仅当用户有 Gemini key）

YouTube 自动字幕是纯声学解码，人名、产品名、缩写和新术语经常整个听错，而且错法在全片不统一。
能直接听音频的大模型会结合上下文，这类词的准确率明显更高。所以只要用户有 Gemini 3.8 这类能听音频的模型的 key，就先用它重新转写，
和字幕逐处对比、投票，合成一份修正版 transcript，**第 2 步读的是这份，不是原始字幕**。
按公开价两轮合计约每小时音频 0.5 美元，耗时十来分钟。

**先确认有没有 key，没有就整步跳过。** 看环境变量 `GEMINI_KEY`（Vertex AI express mode 的 API key）。
非交互 shell 看不到时，再用用户的登录 shell 查一次（`$SHELL -ic 'echo ${GEMINI_KEY:+set}'`），不要打印 key 本身。

- **有 key**：按下面的流程做字幕双校验。换别的 Gemini 模型用 `GEMINI_MODEL=<模型名>`。
  音频会发到 Google 的公网端点，公开的 YouTube 视频没问题。
- **没有 key**：不做双校验，直接进第 2 步读 YouTube 字幕，专有名词按上下文还原（规则见 writing-guide
  「处理转录错误」）。不要为此向用户要 key，也不要改用别的转写服务。

```bash
"$SKILL/scripts/fetch_media.sh" "<URL>" <工作目录> audio
python3 "$SKILL/scripts/gemini_asr.py" <工作目录>                          # 不带提示一轮（主证据）
python3 "$SKILL/scripts/gemini_asr.py" <工作目录> --terms "术语1, 术语2"   # 带提示一轮（投票用）
python3 "$SKILL/scripts/merge_transcript.py" <工作目录> <工作目录>/<id>.ts.txt
```

术语提示从视频标题、简介和字幕里明显的专有名词里取，十来个就够。两轮可以并行跑。

**合并怎么判。** `merge_transcript.py` 以不带提示那轮的文本为底（标点干净、名字较准），
时间戳从字幕逐词继承（保留句子级精度）。三方在实词上不一致的地方按投票决定：

| 情况 | 采用 | 含义 |
|---|---|---|
| 两轮 Gemini 一致 | Gemini | 字幕听错了 |
| 字幕和带提示那轮一致 | 带提示那轮 | 不带提示那轮听错了 |
| 字幕和不带提示那轮一致 | 不带提示那轮 | 带提示那轮被提示带偏了 |
| 三方都不同 | 不带提示那轮，后面标 `[?]` | 有分歧，需要人工定 |

只差语气词、口吃和标点的地方不算分歧。每一处决定都记在 `corrections.md` 里。

**合并之后还要做两件事**，脚本会把线索打印出来：

1. **处理 `DISPUTED`。** 对有分歧的名字，用 `asr_probe.py` 切 15–25 秒短片段、不带提示采样两次：
   ```bash
   python3 "$SKILL/scripts/asr_probe.py" <工作目录> <m:ss-m:ss> <m:ss-m:ss> ...
   ```
   两次一致才算定。幻灯片上的文字（原版 `deck.txt`，或第 5b 步截图里读到的）比两种转写都可靠，写明了就直接采纳。
2. **统一 `NAME VARIANTS`。** 脚本会把拼写相近的大写词列成一组（同一个产品名的大小写变体、音近变体会落在一组）。
   投票挡不住这种错：字幕和 Gemini 可能独立地听成同一个错误的词，两票一致也不代表对。
   按幻灯片或短片段采样定下正确写法，再重跑合并并加上覆盖规则：
   ```bash
   python3 "$SKILL/scripts/merge_transcript.py" <工作目录> <工作目录>/<id>.ts.txt \
     --override "<错误写法>=><正确写法>" ...
   ```
   覆盖规则会顺带清掉紧跟的 `[?]`。

剩下的 `[?]` 如果只是小词，写作时忽略即可。**定不下来的名字，不写进正文**，改用不依赖它的说法，
不要按语境猜成一个知名产品，尤其不要猜成讲者自己的公司或产品——语境越"顺"，越容易猜错。
几次采样结果各不相同的名字，就说明它定不下来。

`fetch_media.sh` 被 YouTube 要求登录（"Sign in to confirm you're not a bot"）时，请用户在浏览器登录后
用 `YTDLP_ARGS="--cookies-from-browser chrome"` 重试；仍然不行就跳过这一步并告诉用户。

### 2. 完整读一遍 transcript

有 Gemini key、做了第 1b 步：读 `<工作目录>/final.ts.txt`。没有 key：读 YouTube 字幕 `<id>.ts.txt`。

**这一步不能跳，也不能只读开头和结尾。** 用 Read 分段把整个带时间戳的转录读完。

原因很直接：这个任务要求每个小节都足够详细，而细节只存在于转录的中间部分。只读首尾会写出一篇"看起来像那么回事"但没有信息量的文章——那恰好是这个 skill 要避免的东西。一小时的视频通常 1200–1600 条字幕 snippet（合并后约 250 行），分几次 Read 读完。

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

输出结构固定如下。写作要求见 [references/writing-guide.md](references/writing-guide.md)，**动笔前读它**——那里是这个 skill 的实质内容，讲怎么把一节写到位、怎么起标题和 TL;DR、怎么处理转录错误、怎么抽 framework、怎么选插图。

```
0. 标题      用全场最反直觉的具体做法当钩子，不用"XX 谈 YY"
1. TL;DR     3–5 条反共识，每条一句判断 + 一句理由 + 时间码
2. 元数据    讲者 / 频道 / 网址 / 日期 / 时长，一张小表
3. Overview  一段话点明核心论题与结论
4. 主题小节  按主题展开，每节挂时间码，配幻灯片截图
5. 框架 & 心智模型  从内容中抽象出的可复用结构
```

标题和 TL;DR 最后写：等全文写完、知道哪些点真正反直觉之后再定。

### 5b. 截图

读者喜欢有图的版本。演讲类视频的幻灯片本身就是讲者画好的图，比自己重画可靠。

先拿到**完整的幻灯片清单**，再选图。清单是第 5d 步对账的底账：讲者一两秒就翻过的页，
常常正是反面案例、证据清单这类没口头展开的内容，只在小节起点附近取帧一定会漏。

**有原版幻灯片（第 1a 步）**：按页渲染，不从视频截。渲染图没有鼠标、选区高亮和摄像头。

- PDF：`pdftoppm -r 200 -png <deck.pdf> <工作目录>/slide`
- HTML：用无头 Chrome / Chromium 逐页截图。先看一眼 deck 的脚本怎么跳页，多数支持 URL hash（`#N` 或 `#/N`）。
  deck 按窗口缩放或给页面加了阴影时，复制一份，注入一段 CSS 把舞台固定成原始尺寸、去掉阴影，再截：
  ```bash
  "$CHROME" --headless=new --hide-scrollbars --window-size=<页宽>,<页高> --force-device-scale-factor=2 \
    --virtual-time-budget=4000 --screenshot=<工作目录>/slide-NN.png "file://<deck.html>#N"
  ```
  `$CHROME` 指本机 Chrome 或 Chromium 的可执行文件。
- 清单就是原版的页码。

**只有视频**：

```bash
"$SKILL/scripts/fetch_media.sh" "<URL>" <工作目录> video
python3 "$SKILL/scripts/slides.py" scan  <video> <工作目录>/scan [--region x0,y0,x1,y1]  # 全片去重，得到清单
python3 "$SKILL/scripts/slides.py" sheet <video> <sheet.png> <m:ss> <m:ss> ...           # 放大看清单里的帧
python3 "$SKILL/scripts/slides.py" grid  <video> <m:ss> <grid.png>                         # 选中的帧逐张加坐标网格
python3 "$SKILL/scripts/slides.py" crop  <video> <m:ss> <x0,y0,x1,y1> <out.png> [--mask <cx,cy,r> --bg <x,y>]
```

- `scan` 每秒取一帧，画面一变就收进清单，写出 `times.txt` 和联系表 `scan_NN.png`。一小时约半分钟。
  讲者摄像头或字幕在动时，用 `--region` 只比较幻灯片区域，不然它们的变化也会算成新的一页。
- 幻灯片页脚有"n / N"页码时，用它对账：清单要覆盖 1 到 N 每一页。缺页就在相邻两页之间用 `sheet` 逐秒补看。
- 用 Read 看 sheet 选帧，看 grid 读裁剪坐标。不要凭缩略图估坐标，那样很容易把标题或边框切掉。
- 讲者摄像头圆框常压在幻灯片右下角。裁剪框要按**幻灯片内容**的完整范围定，重叠处用
  `--mask` 以幻灯片底色填平，不要为了躲摄像头把标题或框切掉。字幕条一律裁掉。

两条路最后都跑 `python3 "$SKILL/scripts/slides.py" check <check.png> <所有图>` 并看一遍：
每张的标题、边框、脚注都完整，没有摄像头、字幕和鼠标选区残留。选图标准和数量见 writing-guide 的「插图」一节。

### 5c. 自查措辞

TL;DR 和标题最容易说满。逐条回到原话核对：不要加原话里没有的顺序（"她做的第一件事"）、
不要放大数字（原话给的是具体数字，就不要改写成"几千""上万"）、不要加原话没有的限定词（"专职""唯一""所有"）。

### 5d. 覆盖审计

出页面前对三本账。三本都对平才算写完：

1. **幻灯片账**：清单里每一页，要么正文里有对应内容，要么记下不收的理由（封面、目录、分隔页、和别页重复）。
   只在幻灯片上出现、讲者没口头展开的内容写进正文时，说明它来自幻灯片。
2. **问答账**：把 Q&A 里每个真实提问列出来，带时间码。每一条要么写进正文，要么并进某一组，要么记下为什么不收。
   问答部分只收现场真问过的问题，主讲和幻灯片里的内容留在各自的小节。
3. **论断账**：把正文、transcript 和幻灯片文字交给一个新上下文的子代理（harness 不支持子代理就自己换个视角逐条过），
   让它逐条找四类问题：引号里不是原话，或说话人归错了；数字和原文对不上；讲者的限定、条件或"我不确定"被删掉了；
   transcript 和幻灯片里都找不到出处。它交回的清单逐条改完，清单清零。

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

**用户要飞书 / Lark 文档时**

走 `lark-doc` skill 的创建工作流，用 XML 写。注意几点：

- 在工作目录（scratchpad）里执行 `init-draft`，否则草稿文件夹会落进用户仓库根目录。
- 截图用 `<img path="@<路径>" caption="一句话说明"/>` 插在对应段落后，图注格式见 writing-guide「插图」。
  路径在执行目录内可写成 `@./相对路径`，否则写绝对路径。
- 之后的修改一律用 `docs +update` 局部改（`block_replace` / `block_insert_after` / `block_delete`），
  不要重建文档。换图时对原来的 img 块逐张 `block_replace`，位置不变。改标题用 `block_replace` 替换 title 块，
  服务端可能回"没有变更"的警告，重新 fetch 确认即可。

三条路的正文内容完全一样，只有外壳不同。

页面设计的落地建议在 writing-guide 里，包括哪些视觉结构对这类长文真正有用（时间码栏、硬数字带）以及要避开的默认审美。

## 语言

默认**用英文思考、用中文输出**。专有名词保留英文原文，首次出现时在括号里给中文释义——`inference（推理）`、`context engineering（上下文工程）`。技术名词不要硬翻成生僻中文。

用户明确要求英文或其它语言时按用户的来。

## 三条不可让步的规则

**不新增事实。** 页面里的每一个论断都必须能在转录、幻灯片（原版或画面上的）或视频元数据里找到出处。不要补充你知道的背景知识，不要引入视频没提到的例子，不要把"他大概是这个意思"写成他说了。转录含混的地方，换成不依赖那个词的说法，不要猜。

**不浓缩。** 这是唯一一个"写长"优先于"写短"的任务。当你想把三段合成一句时，方向反了——应该是把一句展开成三段，用的是转录里本来就有的因果链、数字、限定条件和反例。

**转录错误要还原，但不要打扰读者。** 自动字幕的音近错误几乎必然存在（人名、机构名、缩写）。做了第 1b 步就按它的结果还原，没做就按上下文还原；正文直接写正确的词。不要在正文里放逐处的说明块、括号注释或文末对照表——读者反馈这些"对读者没啥帮助"，只会打断阅读。只在开头元数据附近留一句话，说明本文基于自动字幕（做了第 1b 步才补一句"专有名词经过音频核对"）。还原依据记在工作目录里供自查。定不下来的名字不写进正文，换成不依赖这个名字的说法。
