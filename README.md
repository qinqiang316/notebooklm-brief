# notebooklm-brief

链接 → NotebookLM → 固定五段式中文分析报告。

把任意文章链接、YouTube/B站视频、本地文件丢进来，自动走 NotebookLM（Google Gemini Notebook）通道，按固定模板生成结构化 Markdown 分析报告，存到 `output/` 目录。

## 项目总体目标

**用 agent 做资源学习，分析处理尽可能交给 NotebookLM**：

- 用户发来的资源（链接/文件/视频），由 agent 调度，**尽可能调用 NotebookLM 按用户要求分析处理**，而不是 agent 模型自己读全文
- 目的：① 减少实际模型（agent 主模型）的 token 消耗；② 最大化发挥 NotebookLM 自身能力——来源约束（只依据材料回答，带引用锚点）、完整对话上下文、原生 artifact（导图/报告/学习指南）
- 依据：对来源材料的忠实解读，大部分通用模型的能力不一定比 NotebookLM 自身强；NotebookLM 不越来源、可追溯，更适合学习场景
- 实践准则：用户要求"分析/总结/追问某个资源"时，**默认走 NotebookLM 通道**；agent 模型只做调度、展示、本地归档，不做资源内容的二次加工

## 功能特性

- **多来源自动识别**：文章 URL、YouTube、B站（**先自动匹配 YouTube 原片**，命中则直接走服务端转写；未命中才下载音频）、本地文件（PDF/文本/音频/视频），无需手动指定类型
- **固定五段式分析**：核心观点 → 论证结构 → 关键数据 → 局限与争议 → 启示与建议
- **中文输出**：分析报告为中文 Markdown，带来源引用标注
- **可自定义**：分析模板、目标笔记本均可替换

## 工作原理

```
输入（链接/文件）
   │
   ▼
[1/4] 来源识别     src/source.py    分类：文章 / YouTube / B站 / 本地文件
   │                                    （B站：yt-dlp 下载音频）
   ▼
[2/4] 添加来源     src/pipeline.py  上传到 NotebookLM 笔记本
   │
   ▼
[3/4] 按模板提问   src/pipeline.py  用 prompts/analysis.md 提问
   │
   ▼
[4/4] 保存报告     src/output.py    输出 Markdown 到 output/
```

## 配置与迁移

所有机器相关配置集中在项目根 **`config.yaml`**（归档目录 / 输出目录 / 代理 / 语言 / 账号邮箱），代码不硬编码路径。

```yaml
output_dir: .../output                  # 输出目录
archive_dir: D:\QQ的收藏夹\RAW          # 归档目录（本地 Obsidian 库，留空=不归档）
archive_template: D:\QQ的收藏夹\moban\模版1.md  # 归档 frontmatter 模板（title/source/created 自动填充，留空=直接复制合并笔记）
proxy: http://127.0.0.1:10808           # 访问 Google 的代理
language: zh_Hans                       # NotebookLM 生成语言
yt_match: true                          # B站是否先匹配 YouTube 原片
account_email: ...                      # Google 账号（提示用）
```

### 首次使用 / 迁移到新机器

```bash
# 1) 安装依赖
pip install "notebooklm-py[browser]" yt-dlp pyyaml markdownify

# 2) 登录 NotebookLM（Google 账号）
python -m notebooklm login --browser msedge

# 3) 交互式引导（检查依赖、登录、创建目录、生成 config.yaml）
python main.py --setup

# 4) 环境自检（依赖/登录/目录/代理/配置）
python main.py --doctor
```

- 迁移：复制项目目录 + `config.example.yaml` 为 `config.yaml` 改路径即可；NotebookLM 登录态在 `~/.notebooklm/`（新机器需重新登录）
- `config.yaml` 已 gitignore（含本机路径）；归档目录未配置时跳过归档；归档套用 `archive_template` 指定的 Obsidian frontmatter 模板（无模板时直接复制合并笔记）

## 环境要求

- Python 3.11+
- `notebooklm-py`（NotebookLM 客户端，已装 0.8.0）
- `yt-dlp`（B站视频音频下载）
- 访问 Google 需要代理（本机 v2rayN，127.0.0.1:10808 系统代理）

## 安装与配置

```bash
# 1) 安装依赖
pip install notebooklm-py yt-dlp

# 2) 登录 NotebookLM（首次）
python -m notebooklm login --browser msedge
# 登录态保存在 ~/.notebooklm/profiles/default/storage_state.json

# 3) 确认代理已开启（访问 Google 必需）
```

## 使用方法

```bash
# 基础用法：直接给链接或文件路径（每个链接自动使用独立笔记本 笔记-<标题>）
python main.py "https://example.com/article"
python main.py "https://www.youtube.com/watch?v=..."
python main.py "https://www.bilibili.com/video/BV..."
python main.py "D:\docs\paper.pdf"

# 单轮对话：对同一来源追加一个问题（保持对话上下文，追加到分析文件）
python main.py "https://www.youtube.com/watch?v=..." --ask "展开讲一下第一个核心观点"

# 交互式对话：连续提问，输入 exit 退出
python main.py "https://www.youtube.com/watch?v=..." --chat

# 快速模式：只出分析+对话记录，跳过默认学习产物
python main.py "https://www.youtube.com/watch?v=..." --no-learn

# 跳过 B站->YouTube 原片匹配，直接下载音频（默认自动尝试匹配）
python main.py "https://www.bilibili.com/video/BV..." --no-yt-match

# 仅生成学习产物（不重复分析）：导图+报告+学习指南
python main.py "https://www.youtube.com/watch?v=..." --learn

# 单个生成（可选）：--artifact mindmap / report / studyguide
python main.py "https://www.youtube.com/watch?v=..." --artifact report

# 笔记本同步：列出云端有但本地没有的笔记本（dry-run）
python main.py --sync-notebooks

# 笔记本同步：执行删除（本地 output/ 保留的，云端多余的删除）
python main.py --sync-notebooks --delete-notebooks

# 自定义分析模板
python main.py --prompt-file prompts/analysis.md <链接>

# 指定输出目录 / 手动指定笔记本（覆盖自动命名）
python main.py --output ./output --notebook 链接总结 <链接>
```

- 默认每个链接一个独立笔记本（`笔记-<标题>`），**每个笔记本一个独立输出文件夹**：`output/<笔记本名>/`，所有产物都归到该文件夹
- 首次完整分析自动生成：**分析(`<标题>.md`) + 对话记录(`<标题>.对话记录.md`) + 学习指南(`<标题>-studyguide.md`) + 内容大纲导图(`<标题>-mindmap.json` 及自动转换的 `<标题>-mindmap.md`)**
- 文件名固定不带日期前缀（跨天追问正确追加到同一文件），日期信息在文件头 metadata 里
- `--ask` 单轮追问结果追加到分析文件；`--chat` 多轮内容都在对话记录里（追问/对话不重复生成学习产物）
- `--learn` / `--artifact` 仅生成产物（不做分析），输出到对应笔记文件夹：导图(JSON+MD)、报告(简报 md)、学习指南(md)
- 所有生成内容默认中文（NotebookLM 库语言代码 zh_Hans，`--lang en` 可切换）
- 旧参数 `--follow-up` 是 `--ask` 的别名，兼容

B站视频默认先尝试匹配 YouTube 原片（标题相似+时长接近双条件，走 v2rayN 代理），命中则直接传 YouTube 链接给 NotebookLM 服务端转写；未命中才下载音频再上传，耗时约 1-3 分钟。`--no-yt-match` 可强制跳过匹配。

## 项目结构

```
notebooklm-brief/
├─ main.py              # 入口：来源识别 → 添加来源 → 提问 → 保存
├─ prompts/
│  └─ analysis.md       # 默认五段式分析模板（可替换）
├─ src/
│  ├─ source.py         # 来源分类 + B站音频下载
│  ├─ pipeline.py       # NotebookLM 客户端封装
│  └─ output.py         # 保存报告/对话记录 + 导图 JSON→MD 转换
├─ output/              # 生成结果（每个笔记本一个文件夹，已 gitignore）
└─ .gitignore
```

## 输出示例

每份报告为 `output/<笔记本名>/<标题>.md`，头部带来源链接与生成时间，正文按模板五段展开：

```markdown
# 链接总结：<标题>
- 来源：<原始链接>
- 生成时间：<时间>
- 通道：Google NotebookLM（Gemini Notebook）

### ① 核心观点
...
### ② 论证结构
...
### ③ 关键数据/事实
...
### ④ 局限与争议
...
### ⑤ 对本领域的启示与可操作建议
...
```

## 常见问题

| 问题 | 处理 |
|------|------|
| 报 auth / 登录态失效 | 重新执行 `python -m notebooklm login --browser msedge` |
| B站下载失败 | 确认 yt-dlp 已安装、网络可达 bilibili |
| 访问 Google 超时 | 确认 v2rayN 代理已开启（127.0.0.1:10808） |
