# AGENTS.md — notebooklm-brief 项目操作手册

> 本文件是项目级 agent 指引。任何 agent 在此项目工作前请先读本文件。
> 同步自 Hermes skill `notebooklm-brief`（修改时两边保持一致）。

## 项目是什么

**基于 NotebookLM 的个人研究与学习 Agent**：链接/文件/视频 → Google NotebookLM → 结构化知识资产 + 本地归档 + 学习闭环。

支持用法：

1. **单来源分析 + 持续对话**：一个链接一个独立笔记本，分析后可无限轮对话，所有 Q&A 自动归档
2. **学习闭环**：learn（分析+导图+学习指南+测验）→ test（测验）→ review（薄弱点复习建议）
3. **三层知识资产**：Source（原文不可变）/ Generated（AI 生成可重生成）/ Human（个人笔记 AI 不覆盖）
4. **笔记本同步**：按本地 output/ 文件夹管理云端笔记本（保留本地有的，清理云端多余的）

### 项目总体目标（agent 工作准则）

**用 agent 做资源学习，分析处理尽可能交给 NotebookLM**：

- 用户发来资源（链接/文件/视频）要求分析/总结/追问时，**默认走 NotebookLM 通道**（本项目的 main.py），而不是 agent 模型自己读全文
- 目的：① 减少实际模型（agent 主模型）的 token 消耗；② 最大化发挥 NotebookLM 自身能力——来源约束（只依据材料回答、带引用锚点）、完整对话上下文、原生 artifact（导图/报告/学习指南/测验）
- agent 模型只做：调度（调用 main.py）、原样展示 NotebookLM 输出、本地归档（output/）；**不做资源内容的二次加工/转述**

### 项目边界（与其他项目过程文件独立）

- **本项目的 output/ 只存放本项目自己分析的内容**；不建立其他项目（如 be_air）的笔记本和相关过程文件
- **be_air 项目**：可以借鉴本项目的分析流程（把分析交给 NotebookLM），但 be_air 的 NotebookLM 分析/转写过程文件统一放到 **`/Users/qqiang/AI project/06-工具项目/be_air/notebooklm-output/`**（独立目录），云端对应笔记本也不由本项目的 sync 管理
- 半佛相关内容（`笔记-半佛-*` 4 个 + 播客转写 5 个）已全部归入 be_air/notebooklm-output/；不要在本项目 output/ 重新生成

## 快速使用（命令大全）

⚠️ **必须用 venv python**（见"关键坑"）：

```bash
cd "/Users/qqiang/AI project/06-工具项目/notebooklm-brief"
VPY="/Users/qqiang/.hermes/hermes-agent/venv/bin/python"

# 首次完整分析（五段式 + 自动生成 导图+学习指南）
"$VPY" main.py analyze "<链接或文件路径>"

# 单轮对话（保持上下文，追加到分析文件）
"$VPY" main.py ask "<同一链接>" "你的问题"

# 交互式对话（连续提问，输入 exit 退出）
"$VPY" main.py chat "<同一链接>"

# 学习闭环第一版：分析 + 导图 + 学习指南 + 测验
"$VPY" main.py learn "<链接>"

# 学习闭环第二版：NotebookLM 根据来源内容测验（保存 generated/quiz.md）
"$VPY" main.py test "<链接>"

# 学习闭环第三版：按测验结果给出复习建议（保存 generated/review.md）
"$VPY" main.py review "<链接>"

# 仅生成单个产物（不分析）：--artifact mindmap | report | studyguide | quiz ...
"$VPY" main.py learn "<链接>" --artifact report

# 笔记本同步：列出云端有但本地没有的笔记本（dry-run，不删）
"$VPY" main.py sync

# 笔记本同步：执行删除（本地 output/ 保留的笔记本，云端多余的删除）
"$VPY" main.py sync --delete-notebooks

# 首次使用引导 / 环境自检
"$VPY" main.py setup
"$VPY" main.py doctor

# 其他
"$VPY" main.py analyze --prompt-file prompts/analysis.md "<链接>"   # 自定义模板
"$VPY" main.py analyze --notebook 指定笔记本名 "<链接>"             # 手动指定笔记本
"$VPY" main.py analyze "<链接>" --no-learn                          # 快速模式
"$VPY" main.py analyze "<链接>" --lang en                           # artifact 语言
```

> 旧式 flag 调用仍兼容（自动翻译为子命令）：`main.py "<链接>" --ask "问题"` / `--chat` / `--learn` / `--no-learn` / `--no-yt-match` / `--sync-notebooks` / `--doctor` / `--setup`。

## 输入类型（自动识别，无需指定）

| 输入 | 处理 |
|------|------|
| 文章 URL | NotebookLM 直接抓全文；原文提取优先 Clipper（详见"合并笔记与归档"） |
| YouTube 链接 | yt-dlp 预取标题命名笔记本 → NotebookLM 服务端自动转写 |
| B站链接（bilibili.com / b23.tv） | **先匹配 YouTube 原片**（评分+置信度机制），命中则直接传 YouTube 链接给 NotebookLM 服务端转写；未命中回退 yt-dlp 下载音频 → 上传转写 |
| 本地文件（PDF/文本/音频/视频） | 直接上传 |
| 直接文本 | NotebookLM Text 来源 |

> B站→YouTube 匹配（V3 置信度机制，`src/source.py`）：`youtube_search` 搜候选 → `score_candidate` 综合评分（**标题 50% + 时长 25% + 频道/作者 15% + 其他 10%**）→ `pick_youtube_match` 决策：**≥0.90 自动采用 / 0.70~0.90 用户确认（[y/N]）/ <0.70 回退下载音频**。走 v2rayN 代理（127.0.0.1:10808），代理不通/搜索失败一律回退下载音频，无副作用。`--no-yt-match` 可强制跳过。旧函数 `youtube_match` 保留为兼容（仅 ≥0.90 返回）。

## Source Identity（V3）

- 每个笔记本目录保存 `metadata.json`：source_id / source_type / original_url / canonical_url / title / duration / local_path / notebook_id / notebook_title / created_at / updated_at
- **source_id 生成**：网络资源 = canonical_url 的 SHA256 前 16 位；本地文件 = 文件内容 SHA256 前 16 位；直接文本 = 内容 SHA256
- **canonical_url 规范化**（`src/models.py`）：去跟踪参数（utm_*/fbclid 等）、去锚点、query 排序；YouTube 统一为 `watch?v=<id>`（youtu.be/shorts/m 域名均归一）；B站保留 BV 号去分P
- **Notebook 名称 ≠ Notebook 身份**：名称只负责展示（`笔记-<标题>`），真正关联是 source_id → notebook_id
- **复用规则**：每次运行前按 source_id 扫描 output/ 的 metadata.json，命中则复用已有笔记本（标题变化不丢原笔记本、URL 参数变化不产生无意义重复、相同标题不同来源不串笔记本）；未命中新建
- B站以**原始 bilibili canonical（BV 号）**为身份，跨 YouTube 匹配成功/失败统一（同一视频不会因路线不同建两个笔记本）

## 输出约定（V3：三层知识资产）

每个笔记本一个独立文件夹，所有产物归到该笔记文件夹下：

```
output/<笔记本名>/
├── metadata.json            # Source Identity（来源唯一身份）
├── 归档笔记.md               # ★ 最终归档笔记（放顶层，与过程文件区分；供归档）
├── source/source.md         # Source 层：原文全文（不可变，首次写入后不覆盖）
├── generated/               # Generated 层：NotebookLM 生成物（过程文件，可重新生成）
│   ├── analysis.md          #   五段式分析（首次 + ask 追问追加）
│   ├── conversation.md      #   全部轮次 Q&A 归档（每次全量覆盖更新）
│   ├── mindmap.json/.md     #   内容大纲导图（JSON + 易读 Markdown）
│   ├── studyguide.md        #   学习指南
│   ├── report.md            #   简报（--artifact report）
│   ├── quiz.md              #   测验（test / learn 生成）
│   └── review.md            #   复习建议（review 生成）
└── knowledge/               # Human 层：个人笔记（AI 默认不覆盖；归档笔记自动并入）
    └── README.md
```

文件名固定不带日期前缀（跨天追问正确追加到同一文件）；日期信息在 metadata/文件头里。

> **归档笔记 = 最终可归档产物**（`output/<笔记本>/归档笔记.md`）：由 build_note_file 合并 ①原文 ②五段式分析 ③内容大纲导图(md) ④学习指南 ⑤对话记录 ⑥knowledge/ 个人笔记，每次运行全量重建。`source/`、`generated/`、`knowledge/` 均为过程文件，与归档笔记区分。

## 合并笔记与归档

- **归档笔记**（`output/<笔记本>/归档笔记.md`）：放笔记本顶层，把 ①原文 ②五段式分析 ③内容大纲导图(md) ④学习指南 ⑤对话记录 ⑥knowledge/ 个人笔记 合并为一个文件；每次运行全量重建
- **原文提取双路线**：文章 URL 优先用 **Obsidian Clipper 同款**（`clipper/extract.js`，Mozilla Readability 正文提取 + Turndown 转 Markdown，Playwright msedge 抓全页）——内容更完整、结构更易读（NotebookLM get_fulltext 对部分站点只返回标题无正文，微信文章会被反爬拦截）；失败自动回退 NotebookLM get_fulltext。需 Node.js + `clipper/node_modules`（`setup` 自动装；`config.yaml` 的 `fulltext_clipper: false` 可关闭）。视频/文件来源仍走 NotebookLM 转写文本
- **归档**：默认每次分析后自动归档顶层 归档笔记.md 到 `/Users/qqiang/Library/CloudStorage/坚果云-981921361@qq.com/QQ的收藏夹/RAW`（Obsidian 库目录），套用 `/Users/qqiang/Library/CloudStorage/坚果云-981921361@qq.com/QQ的收藏夹/moban/模版1.md` 的 frontmatter 模板（`--archive` 指定目录，`--no-archive` 跳过；config.yaml 的 `archive_template` 可换模板，留空=直接复制归档笔记）
- **模板属性填充**：title=笔记标题、source=原始链接、created=当天；author/published/description/tags 优先从来源链接收集（B站 API：owner/pubdate/desc/标签；YouTube oEmbed：频道名/标题），拿不到的字段留空不编造；tags 列表渲染为 YAML 行内 `[a, b]`
- **查重规则**：优先原始链接（笔记头 `原始链接：` metadata / 归档 frontmatter `source:`，B站链接保留原始 bilibili 地址），其次标题；相同则用最新覆盖，不同则新增

## 学习闭环（Learn → Test → Review）

1. **Learn**：`learn` —— 分析 + 导图 + 学习指南 + 测验，一次生成完整学习包
2. **Test**：`test` —— NotebookLM 根据来源内容出题测验（含答案），保存 `generated/quiz.md`
3. **Review**：`review` —— 逐题作答后，NotebookLM 分析薄弱点并给出复习建议，保存 `generated/review.md`

## 笔记本同步（sync）

- **本地 output/ 下的 `笔记-*` 文件夹 = 应保留的笔记本清单**
- 云端存在但本地没有对应文件夹的笔记本：`sync` 仅列出（dry-run）；加 `--delete-notebooks` 执行删除
- 匹配规则：云端笔记本名 == 本地文件夹名（或 slug 后相等）；精确匹配防误删
- **删除前确认**：涉及之前分析过但本地文件已消失的笔记本时，先跟用户确认再删

## 环境与登录

- 依赖：notebooklm-py[browser] + yt-dlp + pyyaml + markdownify（+ pytest 开发依赖），装在 Hermes venv（`/Users/qqiang/.hermes/hermes-agent/venv`）
- 登录态：`~/.notebooklm/profiles/default/storage_state.json`（Google 账号 qinqiang316@gmail.com）
- **登录态失效全自动处理**：main.py 捕获 auth 错误 → 自动 `python -m notebooklm login --browser msedge` → 重试（Playwright profile 保留登录，无人值守）
- **macOS 代理**：Shadowrocket 隧道模式全局接管流量（无本地 HTTP 代理端口），config.yaml 的 `proxy` 留空=直连；config.py 默认 proxy 已改为 ''。Windows 才需要 v2rayN 127.0.0.1:10808

## 配置与迁移（config.yaml）

- **所有机器相关配置集中在项目根 `config.yaml`**（归档目录/输出目录/代理/语言/账号邮箱/yt_match），代码不硬编码路径
- `config.yaml` 已 gitignore（含本地路径）；迁移时复制 `config.example.yaml` 为 `config.yaml` 修改，或直接运行 `python main.py setup`
- 首次使用新机器：①安装依赖（setup 自动装或手动 pip install "notebooklm-py[browser]" yt-dlp pyyaml markdownify pytest）②`python -m notebooklm login --browser msedge` 登录 ③`python main.py setup` 交互配置 ④`python main.py doctor` 自检
- 归档目录未配置时跳过归档；`--archive` 可临时指定

## 关键坑

1. **必须用 venv python**：bash 的 `python`（C:\Python314）PYTHONPATH 被污染——`import types` 命中 site-packages 的 notebooklm/types.py，导致 `import playwright.sync_api` 挂掉、login 误报 "Playwright not installed"。venv python（3.11.15）无此问题
2. **`--browser-cookies edge` 不可用**：App-Bound Encryption 解密失败；必须走 Playwright profile 登录
3. **pip 装大包**：`pip install --proxy '' -i https://mirrors.aliyun.com/pypi/simple/`（系统代理下直连 PyPI 超时）
4. **语言代码坑**：NotebookLM 库要求 BCP-47 标签，简体中文是 `zh_Hans` 而非 `zh`。pipeline 已自动规范化（`normalize_lang`），全局默认语言已设为 zh_Hans（`python -m notebooklm language set zh_Hans`，配置在 ~/.notebooklm/config.json）
5. **B站链接**：NotebookLM 不认 bilibili 链接。默认先尝试匹配 YouTube 原片（置信度机制），命中则直接传 YouTube 链接给 NotebookLM 服务端转写（省下载上传）；未命中才 yt-dlp 下载音频再上传，需 1-3 分钟。`--no-yt-match` 强制跳过匹配
6. **artifact 不自动回流**：云端手动改的导图/报告不会同步本地；需要时重新跑 learn/--artifact
7. **代码被外部还原**：本项目源码曾整批被还原到 v1/v2（output/ 数据未丢）。**V3 完整备份在 `.worktrees/gpt/`（git worktree 副本，含全部 src 13 模块 + tests/）**——根目录被还原时直接 `cp .worktrees/gpt/main.py .worktrees/gpt/src/*.py` + `cp -r .worktrees/gpt/tests` 恢复，然后 `pytest tests/ -q`（93 个用例）验证。发现关键函数缺失（notebook_dir / youtube_match / normalize_lang / sync_notebooks / prepare_source / resolve_input）时，按本文件与 skill 核对重建
8. **Clipper 原文提取依赖 Node**：`clipper/node_modules` 缺失时 `doctor` 会提示、原文自动回退 NotebookLM（不报错）；新机器迁移后跑 `setup` 或 `cd clipper && npm install` 恢复

## 文件结构

```
main.py              # 入口：CLI 子命令（analyze/ask/chat/learn/test/review/sync/doctor/setup）+ 学习闭环
src/models.py        # V3 Source Identity：SourceRecord / canonical_url / source_id / metadata.json
src/routing.py       # V3 资源路由：SourceInput + Router（统一输入决策，main 不承担类型判断/下载）
src/source.py        # 输入识别 + SourceManager（来源添加/列表/全文）+ B站匹配评分/置信度
src/notebook.py      # V3 NotebookManager：笔记本创建/查找/复用/删除/同步
src/conversation.py  # V3 ConversationManager：ask/chat/history/conversation_id
src/artifact.py      # V3 ArtifactManager：导图/报告/指南/测验等生成与下载 + 语言规范化
src/provider.py      # V3 NotebookLM Provider 抽象：RealNotebookLMProvider / MockNotebookLMProvider
src/config.py        # 配置读取/保存（config.yaml，机器相关集中管理）
src/setup.py         # 首次引导（setup）+ 环境自检（doctor）
src/pipeline.py      # NotebookLM 门面：组合四个 Manager（保留旧接口转发）
src/output.py        # 三层资产落盘：source/generated/knowledge + 顶层归档笔记/归档 + 导图/测验转换
src/fetch_fulltext.py # 网页原文提取（Obsidian Clipper 同款：Playwright 抓页 + Readability/Turndown）
clipper/extract.js   # Clipper 提取核心（Mozilla Readability + Turndown，npm 依赖 @mozilla/readability turndown jsdom）
prompts/analysis.md  # 五段式分析模板
config.example.yaml  # 配置模板（迁移时复制为 config.yaml）
config.yaml          # 本机配置（已 gitignore）
output/              # 生成结果（每个笔记本一个文件夹，三层资产，不入库）
tests/               # 自动化测试（pytest：identity/routing/source/output/config/integration）
```
