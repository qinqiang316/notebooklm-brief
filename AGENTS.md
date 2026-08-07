# AGENTS.md — notebooklm-brief 项目操作手册

> 本文件是项目级 agent 指引。任何 agent 在此项目工作前请先读本文件。
> 同步自 Hermes skill `notebooklm-brief`（修改时两边保持一致）。

## 项目是什么

链接/文件 → Google NotebookLM → 结构化输出的自动化工具。支持三种用法：

1. **单来源分析 + 持续对话**：一个链接一个独立笔记本，分析后可无限轮对话，所有 Q&A 自动归档为对话记录
2. **单来源学习产物**：默认分析自动生成 导图+学习指南（导图自动转易读 md）
3. **笔记本同步**：按本地 output/ 文件夹管理云端笔记本（保留本地有的，清理云端多余的）

### 项目总体目标（agent 工作准则）

**用 agent 做资源学习，分析处理尽可能交给 NotebookLM**：

- 用户发来资源（链接/文件/视频）要求分析/总结/追问时，**默认走 NotebookLM 通道**（本项目的 main.py），而不是 agent 模型自己读全文
- 目的：① 减少实际模型（agent 主模型）的 token 消耗；② 最大化发挥 NotebookLM 自身能力——来源约束（只依据材料回答、带引用锚点）、完整对话上下文、原生 artifact（导图/报告/学习指南）
- 依据：对来源材料的忠实解读，大部分通用模型的能力不一定比 NotebookLM 自身强
- agent 模型只做：调度（调用 main.py）、原样展示 NotebookLM 输出、本地归档（output/）；**不做资源内容的二次加工/转述**

## 快速使用（命令大全）

⚠️ **必须用 venv python**（见"关键坑"）：

```bash
cd "E:\AI project\06-工具项目\notebooklm-brief"
VPY="/c/Users/lenovo/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe"

# 首次完整分析（五段式 + 自动生成 导图+学习指南，自动建独立笔记本 笔记-<标题>）
"$VPY" main.py "<链接或文件路径>"

# 单轮对话（保持上下文，追加到分析文件，不再重复生成学习产物）
"$VPY" main.py "<同一链接>" --ask "你的问题"

# 交互式对话（连续提问，输入 exit 退出）
"$VPY" main.py "<同一链接>" --chat

# 快速模式：只出分析+对话记录，跳过默认学习产物
"$VPY" main.py "<链接>" --no-learn

# 归档：默认每次分析后自动归档合并笔记到 D:\QQ的收藏夹\RAW（--archive 指定目录，--no-archive 跳过）
"$VPY" main.py "<链接>" --no-archive

# 跳过 B站->YouTube 原片匹配，直接下载音频（默认自动尝试匹配）
"$VPY" main.py "<B站链接>" --no-yt-match

# 一次生成 导图+报告+学习指南（仅产物，不做分析；输出到该笔记文件夹）
"$VPY" main.py "<链接>" --learn

# 单个生成：--artifact mindmap | report | studyguide（--lang en 切语言）
"$VPY" main.py "<链接>" --artifact report

# 语言：默认中文（zh_Hans），--lang 可切换（如 --lang en）；所有生成内容跟随语言设置
"$VPY" main.py "<链接>" --lang en

# 笔记本同步：列出云端有但本地没有的笔记本（dry-run，不删）
"$VPY" main.py --sync-notebooks

# 笔记本同步：执行删除（本地 output/ 保留的笔记本，云端多余的删除）
"$VPY" main.py --sync-notebooks --delete-notebooks

# 首次使用引导：检查依赖、登录 NotebookLM、创建目录、生成 config.yaml
"$VPY" main.py --setup

# 环境自检：依赖/登录/目录/代理/配置
"$VPY" main.py --doctor

# 其他
"$VPY" main.py --prompt-file prompts/analysis.md <链接>   # 自定义模板
"$VPY" main.py --notebook 指定笔记本名 <链接>             # 手动指定笔记本
```

## 输入类型（自动识别，无需指定）

| 输入 | 处理 |
|------|------|
| 文章 URL | NotebookLM 直接抓全文 |
| YouTube 链接 | yt-dlp 预取标题命名笔记本 → NotebookLM 服务端自动转写 |
| B站链接（bilibili.com / b23.tv） | **先尝试匹配 YouTube 原片**（标题相似+时长接近双条件，防误配），命中则直接传 YouTube 链接给 NotebookLM 服务端转写（省下载音频）；未命中回退 yt-dlp 下载音频 → 上传转写 |
| 本地文件（PDF/文本/音频/视频） | 直接上传 |

> B站→YouTube 匹配：`src/source.py:youtube_match` 用 `yt-dlp ytsearch` 搜索标题，匹配需同时满足 ①标题规范化相似（去搬运/字幕前后缀，包含或 Jaccard>0.55）②时长接近（±15% 或 ±60s）。走 v2rayN 代理（127.0.0.1:10808），代理不通/搜索失败一律回退下载音频，无副作用。`--no-yt-match` 可强制跳过。

## 输出约定（v2：按笔记分文件夹）

每个笔记本一个独立文件夹，所有产物都归到该笔记文件夹下：

| 文件 | 说明 |
|---|---|
| `output/<笔记本名>/<标题>.md` | 分析文件（首次五段式 + --ask 追问段落追加） |
| `output/<笔记本名>/<标题>.对话记录.md` | 全部轮次 Q&A 归档（每次运行全量覆盖更新） |
| `output/<笔记本名>/<标题>.笔记.md` | **合并笔记**：原文 + 分析 + 导图 + 学习指南 + 对话记录（每次运行全量重建） |
| `output/<笔记本名>/<标题>-studyguide.md` | 学习指南（默认分析自动生成） |
| `output/<笔记本名>/<标题>-mindmap.json` | 内容大纲导图（JSON 树，默认分析自动生成） |
| `output/<笔记本名>/<标题>-mindmap.md` | 导图 Markdown 版（JSON 自动转换，易读大纲） |
| `output/<笔记本名>/<标题>-report.md` | 简报文档（仅 --learn / --artifact report 生成） |

文件名固定不带日期前缀（跨天追问正确追加到同一文件）；日期信息在文件头 metadata 里。

## 合并笔记与归档

- **合并笔记**（`<标题>.笔记.md`）：把 ①原文（NotebookLM get_fulltext 提取文章全文/视频转写，markdown 格式需 markdownify 包，缺失自动回退 text）②五段式分析 ③内容大纲导图(md) ④学习指南 ⑤对话记录 合并为一个文件；每次运行（分析/追问/chat）全量重建，实时更新
- **归档**：默认每次分析后自动复制合并笔记到 `D:\QQ的收藏夹\RAW`（`--archive` 指定目录，`--no-archive` 跳过）
- **查重规则**：优先原始链接（笔记头 `原始链接：` metadata，B站链接保留原始 bilibili 地址），其次标题；相同则用最新覆盖，不同则新增

## 笔记本同步（--sync-notebooks）

- **本地 output/ 下的 `笔记-*` 文件夹 = 应保留的笔记本清单**
- 云端存在但本地没有对应文件夹的笔记本：`--sync-notebooks` 仅列出（dry-run）；加 `--delete-notebooks` 执行删除
- 匹配规则：云端笔记本名 == 本地文件夹名（或 slug 后相等）；精确匹配防误删
- **删除前确认**：涉及之前分析过但本地文件已消失的笔记本时，先跟用户确认再删

## 环境与登录

- 依赖：notebooklm-py[browser] + yt-dlp + pyyaml + markdownify，装在 Hermes venv（`C:\Users\lenovo\AppData\Local\hermes\hermes-agent\venv`）
- 登录态：`~/.notebooklm/profiles/default/storage_state.json`（Google 账号 qinqiang316@gmail.com）
- **登录态失效全自动处理**：main.py 捕获 auth 错误 → 自动 `python -m notebooklm login --browser msedge` → 重试（Playwright profile 保留登录，无人值守）
- 需代理访问 Google：v2rayN 开启（127.0.0.1:10808 系统代理），否则超时

## 配置与迁移（config.yaml）

- **所有机器相关配置集中在项目根 `config.yaml`**（归档目录/输出目录/代理/语言/账号邮箱/yt_match），代码不硬编码路径
- `config.yaml` 已 gitignore（含本地路径）；迁移时复制 `config.example.yaml` 为 `config.yaml` 修改，或直接运行 `python main.py --setup`
- 首次使用新机器：①安装依赖（setup 自动装或手动 pip install "notebooklm-py[browser]" yt-dlp pyyaml markdownify）②`python -m notebooklm login --browser msedge` 登录 ③`python main.py --setup` 交互配置 ④`python main.py --doctor` 自检
- 归档目录未配置时跳过归档；`--archive` 可临时指定

## 关键坑

1. **必须用 venv python**：bash 的 `python`（C:\Python314）PYTHONPATH 被污染——`import types` 命中 site-packages 的 notebooklm/types.py，导致 `import playwright.sync_api` 挂掉、login 误报 "Playwright not installed"。venv python（3.11.15）无此问题
2. **`--browser-cookies edge` 不可用**：App-Bound Encryption 解密失败；必须走 Playwright profile 登录
3. **pip 装大包**：`pip install --proxy '' -i https://mirrors.aliyun.com/pypi/simple/`（系统代理下直连 PyPI 超时）
4. **语言代码坑**：NotebookLM 库要求 BCP-47 标签，简体中文是 `zh_Hans` 而非 `zh`。pipeline 已自动规范化（`normalize_lang`），全局默认语言已设为 zh_Hans（`python -m notebooklm language set zh_Hans`，配置在 ~/.notebooklm/config.json）
5. **B站链接**：NotebookLM 不认 bilibili 链接。默认先尝试匹配 YouTube 原片（标题相似+时长接近双条件防误配，走 v2rayN 代理），命中则直接传 YouTube 链接给 NotebookLM 服务端转写（省下载上传）；未命中才 yt-dlp 下载音频再上传，需 1-3 分钟。`--no-yt-match` 强制跳过匹配
6. **artifact 不自动回流**：云端手动改的导图/报告不会同步本地；需要时重新跑 --learn/--artifact
7. **代码被外部还原**：本项目源码曾整批被还原到 v1（output/ 数据未丢）。发现关键函数缺失（notebook_dir / youtube_match / normalize_lang / sync_notebooks）时，按本文件与 skill 核对重建

## 文件结构

```
main.py              # 入口：来源识别 → NotebookLM → 保存 + 笔记本同步 + 归档
src/config.py        # 配置读取/保存（config.yaml，机器相关集中管理）
src/setup.py         # 首次引导（--setup）+ 环境自检（--doctor）
src/pipeline.py      # NotebookLM 通道封装（笔记本/来源/提问/history/artifact/语言/原文提取）
src/source.py        # 输入类型识别 + B站音频下载 + B站->YouTube 原片匹配
src/output.py        # 保存分析/对话记录/合并笔记/归档 + 导图 JSON→MD 转换
prompts/analysis.md  # 五段式分析模板
config.example.yaml  # 配置模板（迁移时复制为 config.yaml）
config.yaml          # 本机配置（已 gitignore）
output/              # 生成结果（每个笔记本一个文件夹，不入库）
```
