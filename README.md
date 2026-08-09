# notebooklm-brief

> **基于 NotebookLM 的个人研究与学习 Agent**（NotebookLM-powered personal research & learning agent）

链接/文件/视频 → Google NotebookLM → 结构化知识资产 + 本地归档 + 学习闭环。

把任意文章链接、YouTube/B站视频、本地文件丢进来，自动走 NotebookLM（Google Gemini Notebook）通道，产出分析、对话、导图、学习指南、测验等学习产物，并按 **Source / Generated / Human 三层结构**沉淀到本地，可归档到 Obsidian。

## 核心架构原则

> **Agent 不负责重新理解资源内容；NotebookLM 负责理解，Agent 负责调度、组织和沉淀。**

- **资源识别与路由**：URL / YouTube / B站 / 文件 / 文本 自动识别，统一路由
- **Source 身份管理**：每个来源有稳定唯一身份（source_id），URL 参数变化/标题变化不丢原笔记本
- **Notebook / Conversation / Artifact 管理**：拆分为独立 Manager，NotebookLM 只做知识处理
- **知识资产沉淀**：Source（原文，不可变）/ Generated（AI 生成，可重生成）/ Human（个人笔记，AI 不覆盖）

## 功能特性

1. **Resource ingestion（资源接入）**：多来源自动识别——文章 URL、YouTube、B站（**先自动匹配 YouTube 原片**，命中则走服务端转写；未命中才下载音频）、本地文件（PDF/文本/音频/视频）、直接文本，无需手动指定类型
2. **Resource routing（资源路由）**：B站→YouTube 匹配带**置信度机制**（评分：标题 50% + 时长 25% + 频道 15% + 其他 10%；≥0.90 自动采用、0.70~0.90 用户确认、<0.70 回退下载音频），杜绝静默错误匹配
3. **NotebookLM processing（知识处理）**：默认五段式分析模板（核心观点 → 论证结构 → 关键数据 → 局限与争议 → 启示与建议）；网页原文优先 Obsidian Clipper 同款提取（Readability+Turndown），失败回退 NotebookLM
4. **Conversation（持续对话）**：ask / chat 长期复用 NotebookLM 上下文，所有 Q&A 自动归档
5. **Learning artifacts（学习产物）**：导图、学习指南、简报、测验（quiz）、复习建议（review）等原生产物
6. **Knowledge archival（知识归档）**：合并笔记自动归档到 Obsidian RAW，套用 frontmatter 模板，按原始链接/标题查重

## 工作原理

```text
输入（链接/文件/文本）
   │
   ▼
[1/4] 来源路由       src/routing.py
   │                  SourceInput + Router：识别类型、规范化 URL、B站匹配/下载
   ▼
[2/4] Source ID     src/models.py
   │                  每个来源唯一身份 source_id -> metadata.json -> notebook_id
   ▼
[3/4] NotebookLM    src/pipeline.py（门面）
   │                  NotebookManager / SourceManager / ConversationManager / ArtifactManager
   │                  分析 + 问答 + 导图/学习指南/测验
   ▼
[4/4] 三层资产       src/output.py
                        source/    原文（不可变）
                        generated/ AI 生成物（分析/对话/导图/指南/测验/复习）
                        knowledge/ 个人笔记（AI 不覆盖）
                        └─ 归档到 Obsidian RAW
```

## 安装与配置

```bash
# 1) 安装 Python 依赖（必须用 venv python，见"常见问题"）
python -m pip install "notebooklm-py[browser]" yt-dlp pyyaml markdownify

# 2) 登录 NotebookLM（Playwright profile 登录，保留登录态）
python -m notebooklm login --browser msedge

# 3) 首次引导（检查依赖、登录、创建目录、生成 config.yaml）
python main.py setup

# 4) 环境自检
python main.py doctor
```

所有机器相关配置集中在项目根 **`config.yaml`**（归档目录/输出目录/代理/语言/账号邮箱/yt_match），代码不硬编码路径。迁移机器：复制 `config.example.yaml` 为 `config.yaml` 修改，或直接跑 `python main.py setup`。

## 使用方法（子命令）

```bash
VPY="C:\Users\lenovo\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"

# 首次完整分析（五段式 + 默认 导图+学习指南）
"$VPY" main.py analyze "https://1q43.blog/post/12564/"

# 单轮追问（保持 NotebookLM 上下文）
"$VPY" main.py ask "https://1q43.blog/post/12564/" "展开讲一下第二个核心观点"

# 交互式对话（exit 退出）
"$VPY" main.py chat "https://1q43.blog/post/12564/"

# 学习闭环第一版：分析 + 导图 + 学习指南 + 测验
"$VPY" main.py learn "https://1q43.blog/post/12564/"

# 学习闭环第二版：根据来源内容测验（保存 generated/quiz.md）
"$VPY" main.py test "https://1q43.blog/post/12564/"

# 学习闭环第三版：按测验结果给出复习建议（保存 generated/review.md）
"$VPY" main.py review "https://1q43.blog/post/12564/"

# 笔记本同步（dry-run；加 --delete-notebooks 执行删除）
"$VPY" main.py sync

# 仅生成单个产物（不分析）
"$VPY" main.py learn "https://example.com/article" --artifact report
```

> 旧式 flag 调用仍兼容：`main.py "<链接>" --ask "问题"` / `--chat` / `--learn` / `--no-learn` / `--no-yt-match` / `--sync-notebooks` / `--doctor` / `--setup` 自动翻译为子命令。

公共参数：`--notebook 指定笔记本名`、`--output 输出目录`、`--lang en`（artifact 语言，默认 zh）、`--no-yt-match`、`--prompt-file`、`--archive 目录` / `--no-archive`。

## 输出约定（三层知识资产）

每个笔记本一个独立文件夹：`output/<笔记本名>/`

| 层 | 文件 | 说明 |
|---|---|---|
| **Source** | `source/source.md` | 原文全文（**不可变**，首次提取后不覆盖） |
| **Identity** | `metadata.json` | 来源唯一身份（source_id / canonical_url / notebook_id 关联） |
| **Generated** | `generated/analysis.md` | 五段式分析（首次 + `ask` 追问追加） |
| | `generated/conversation.md` | 全部轮次 Q&A 归档 |
| | `generated/mindmap.json` / `.md` | 内容大纲导图（JSON + 易读 Markdown） |
| | `generated/studyguide.md` | 学习指南 |
| | `generated/report.md` | 简报（`--artifact report`） |
| | `generated/quiz.md` | 测验（`test` / `learn` 生成） |
| | `generated/review.md` | 复习建议（`review` 生成） |
| | `generated/<标题>.笔记.md` | 合并笔记（综合视图，供归档） |
| **Human** | `knowledge/README.md` | 个人笔记区（**AI 默认不覆盖**） |

Obsidian 归档：`RAW/<标题>.笔记.md`（套用 `config.yaml` 的 `archive_template` frontmatter 模板；查重：原始链接优先，其次标题）。

## 学习闭环（Learn → Test → Review）

1. **Learn**：`learn` —— 分析 + 导图 + 学习指南 + 测验，一次生成完整学习包
2. **Test**：`test` —— NotebookLM 根据来源内容出题测验（含答案），保存 `generated/quiz.md`
3. **Review**：`review` —— 逐题作答后，NotebookLM 分析薄弱点并给出复习建议，保存 `generated/review.md`

## 常见问题

| 问题 | 处理 |
|------|------|
| **必须用 venv python** | bash 的 `python`（如 C:\Python314）PYTHONPATH 被污染，`import types` 会命中 site-packages 的 notebooklm/types.py 导致挂掉；用 Hermes venv（`C:\Users\lenovo\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe`） |
| 登录态失效 | 代码自动重登（`python -m notebooklm login --browser msedge`），必要时手动 |
| 访问 Google 超时 | 确认代理已开启（如 v2rayN 127.0.0.1:10808） |
| Clipper 原文提取不可用 | 确认 Node.js 已安装；`cd clipper && npm install`（缺失时自动回退 NotebookLM 原文） |
| B站下载失败 | 确认 `yt-dlp` 已安装且网络可达 bilibili |
| 微信/部分站点抓不到正文 | NotebookLM 服务端被微信反爬拦截时，本机 Clipper 路线（真实 Edge 抓取）可绕过 |

## 项目结构

```
notebooklm-brief/
├─ main.py                      # 入口：CLI 子命令 + Router + 三层资产 + 学习闭环
├─ config.yaml                  # 本机配置（gitignore）
├─ config.example.yaml          # 配置模板
├─ prompts/
│  └─ analysis.md               # 五段式分析模板
├─ src/
│  ├─ models.py                 # Source Identity：SourceRecord / canonical_url / source_id / metadata
│  ├─ routing.py                # 资源路由：SourceInput + Router（统一输入决策）
│  ├─ source.py                 # 输入识别 + SourceManager + B站匹配评分/置信度
│  ├─ notebook.py               # NotebookManager：笔记本创建/查找/复用/删除/同步
│  ├─ conversation.py           # ConversationManager：ask/chat/history
│  ├─ artifact.py               # ArtifactManager：导图/报告/指南/测验等生成与下载
│  ├─ provider.py               # NotebookLM Provider 抽象（Real / Mock）
│  ├─ pipeline.py               # NotebookLM 门面：组合四个 Manager
│  ├─ output.py                 # 三层资产落盘：source/generated/knowledge + 归档
│  ├─ config.py                 # 配置读取与管理
│  ├─ setup.py                  # setup 引导 + doctor 自检
│  └─ fetch_fulltext.py         # Obsidian Clipper 路线网页原文提取
├─ clipper/
│  ├─ extract.js                # Readability + Turndown 正文提取
│  ├─ package.json
│  └─ node_modules/             # Node 依赖（gitignore）
├─ output/                      # 本地输出（每笔记本一个文件夹，三层资产）
├─ tests/                       # 自动化测试（pytest，92 项：identity/routing/source/output/config/integration）
├─ AGENTS.md                    # agent 项目级操作手册
├─ README.md
└─ .gitignore
```

## 开发与测试

```bash
# 单元/集成测试（不访问真实 NotebookLM，用 MockNotebookLMProvider）
python -m pytest tests/
```
