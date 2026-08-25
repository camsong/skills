# skills

我自己天天在用的 agent skills。装上之后，Claude Code、Codex、Cursor 都能直接调。

一个 skill 就是一个带说明书的文件夹：`SKILL.md` 写清楚它干什么、什么时候该用、怎么跑，旁边放上它要用到的脚本和参考文档。Agent 看描述觉得对得上，就自己把它加载进来，不用你手动喊。

## 里面有什么

| Skill | 干什么 | 什么时候会被触发 |
|---|---|---|
| [youdao-wordbook](skills/youdao-wordbook/SKILL.md) | 把有道单词本导出成 JSONL / CSV / Markdown，带释义、语言方向、添加时间 | 「同步一下我的有道单词本」「备份/分析我的生词」 |
| [youtube-feed-digest](skills/youtube-feed-digest/SKILL.md) | 列出你自己的 YouTube 推荐流和订阅更新，你挑几个，它给每个写一份带时间码的要点摘要 | 「今天 YouTube 推荐了什么」「刷一下 YouTube」「挑几个总结一下」 |
| [youtube-transcript-api](skills/youtube-transcript-api/SKILL.md) | 抓 YouTube 字幕，能挑语言、能翻译，输出纯文本 / 带时间码 / JSON / SRT | 给一个 YouTube 链接，要字幕或文字稿 |
| [youtube-reading-page](skills/youtube-reading-page/SKILL.md) | 把 YouTube 视频重写成一篇能替代观看的中文长文，按主题分节，最后抽出可复用的框架 | 给一个 YouTube 链接，说「整理成文章」「做个阅读版」 |

三个 YouTube skill 是一条链：`youtube-transcript-api` 负责取字幕，`youtube-feed-digest` 和 `youtube-reading-page` 都不自己抓，各自去调它。装在一起就能自动找到对方，不用配路径。

用起来大致是：`youtube-feed-digest` 帮你从一堆推荐里筛出想看的，看完摘要还想细读某一个，再让 `youtube-reading-page` 出长文。

## 怎么装

两条路，按你想不想改它来选。

**拿来就用**：用 skills 安装器，它把文件拷进各家 agent 的 skills 目录。

```bash
npx skills add camsong/skills
```

它会问你装哪几个、装到哪些 agent。不想走交互就把参数给全：

```bash
npx skills add camsong/skills -g -s '*' -a claude-code -y
```

`-a` 一次只认一个 agent，装多家就多跑几遍，agent 名分别是 `claude-code`、`codex`、`cursor`（是 `claude-code`，不是 `claude`）。这条路是拷贝，以后更新靠 `npx skills update`。

**想自己改**：clone 下来建软链。

```bash
git clone https://github.com/camsong/skills.git
cd skills
./scripts/install.sh
```

这样改仓库里的文件，各家 agent 立刻就是改完的版本，`git pull` 一次全都跟着更新。想要一份不会变的拷贝，加 `--copy`。

只装其中一个：

```bash
./scripts/install.sh youdao-wordbook
```

指定装到哪：

```bash
./scripts/install.sh --target ~/.cursor/skills
```

不加 `--target` 的时候，脚本往 `~/.claude/skills`（Claude Code）和 `~/.agents/skills`（Codex、Cursor 以及其他兼容 Agent Skills 的 harness）里装，哪个目录已经存在就装哪个。

看一眼都有什么：

```bash
./scripts/list-skills.sh
```

两条路别混着用，会装成两份。Claude Code 还可以当插件装，仓库里的 `.claude-plugin/` 就是给它用的。

## 跑起来还需要什么

`youdao-wordbook` 只用 Python 标准库，有 Python 3.9 就够了。

三个 YouTube skill 都需要 `uv`。脚本里写了 PEP 723 依赖声明，`uv` 第一次跑的时候自己把依赖拉下来缓存住，不用建 venv，也不往全局装东西。

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

`youtube-feed-digest` 另外还要求你的浏览器已经登录 YouTube。它用 yt-dlp 从浏览器的 cookie 库里借登录态，只读，不落盘任何凭证；macOS 上第一次读可能会弹一次钥匙串授权。默认读 Chrome，用 `--browser safari|firefox|edge|brave` 换别的。

还有一件事得先说：YouTube 的字幕接口会封机房 IP。家里或者办公室的网正常能抓，放在云主机上跑基本必然报 `RequestBlocked`，那种情况得挂一个住宅代理，脚本有 `--proxy` 参数。

## 隐私这块

这是个公开仓库，所以定了几条硬规矩，完整版写在 [AGENTS.md](AGENTS.md)：

- cookie、token、密钥一律不进仓库，文档里出现的值全是假的占位符。
- 导出的个人数据（单词本内容、字幕、笔记）不进仓库，`.gitignore` 已经把这些文件名兜住了。
- 需要凭证的 skill，一律把凭证存到仓库外面。有道那个 skill 的登录 cookie 存在 `~/.config/youdao-wordbook/cookie.json`，权限 0600。

最后一条有具体原因。`install.sh` 默认建软链，skill 目录直接指向 git 工作区；凭证要是照旧存在 skill 目录底下，一次 `git add -A` 就跟着推上去了。所以改成存进配置目录。

## 想自己加一个

目录长这样：

```
skills/<skill-name>/
  SKILL.md          必需，frontmatter 加正文说明
  scripts/          skill 要调的可执行脚本
  references/       按需加载的长文档
  agents/           某些 harness 的额外元信息，比如 openai.yaml
```

`SKILL.md` 的 frontmatter 只有两个必填字段，`name` 和 `description`。`name` 要和目录名一致；`description` 决定了 agent 会不会想起来用它，所以既要写清楚这东西干什么，也要写清楚什么时候该用，最好带上用户真会说出口的那几句话。

跨 harness 能不能跑，就看一条：**别写死路径**。不要出现 `~/.claude/skills/xxx`，SKILL.md 里说「本 skill 所在目录」就行，各家 harness 加载时都会注入；脚本自己用 `$(dirname "${BASH_SOURCE[0]}")` 定位。要引用另一个 skill，先按相对路径找同级目录，找不到再退回去猜各 harness 的 skills 目录。

其余约定在 [AGENTS.md](AGENTS.md)。

## License

MIT
