# AGENTS.md — notebooklm-brief 项目操作手册

> 本文件是项目级 agent 指引。任何 agent 在此项目工作前请先读本文件。
> 同步自 Hermes skill `notebooklm-brief`（修改时两边保持一致）。

## 项目是什么

链接/文件 → Google NotebookLM → 结构化输出的自动化工具。支持两种用法：

1. **单来源分析 + 持续对话**：一个链接一个独立笔记本，分析后可无限轮对话，所有 Q&A 自动归档为对话记录
2. **单来源学习产物**：生成 NotebookLM 原生内容（导图/报告/学习指南）

## 快速使用（命令大全）

⚠️ **必须用 venv python**（见"关键坑"）：

```bash
cd "E:\AI project\06-工具项目\notebooklm-brief"
VPY="/c/Users/lenovo/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe"

# 首次完整分析（五段式，自动建独立笔记本 笔记-<标题>）
"$VPY" main.py "<链接或文件路径>"

# 单轮对话（保持上下文，追加到分析文件）
"$VPY" main.py "<同一链接>" --ask "你的问题"

# 交互式对话（连续提问，输入 exit 退出）
"$VPY" main.py "<同一链接>" --chat

# 一次生成 导图+报告+学习指南（输出到 output/artifacts/）
"$VPY" main.py "<链接>" --learn

# 单个生成：--artifact mindmap | report | studyguide（--lang en 切语言）
"$VPY" main.py "<链接>" --artifact report

# 其他
"$VPY" main.py --prompt-file prompts/analysis.md <链接>   # 自定义模板
"$VPY" main.py --notebook 指定笔记本名 <链接>             # 手动指定笔记本
```

## 输出约定

| 文件 | 说明 |
|---|---|
| `output/<日期>-<标题>.md` | 分析文件（首次五段式 + --ask 追问段落追加） |
| `output/<日期>-<标题>.对话记录.md` | 全部轮次 Q&A 归档（每次运行全量覆盖更新） |
| `output/artifacts/<标题>-mindmap.json` | 导图（JSON 树） |
| `output/artifacts/<标题>-report.md` | 报告（简报文档） |
| `output/artifacts/<标题>-studyguide.md` | 学习指南 |

## 环境与登录

- 依赖：notebooklm-py[browser] + yt-dlp，装在 Hermes venv（`C:\Users\lenovo\AppData\Local\hermes\hermes-agent\venv`）
- 登录态：`~/.notebooklm/profiles/default/storage_state.json`（Google 账号 qinqiang316@gmail.com）
- **登录态失效全自动处理**：main.py 捕获 auth 错误 → 自动 `python -m notebooklm login --browser msedge` → 重试（Playwright profile 保留登录，无人值守）
- 需代理访问 Google：v2rayN 开启（127.0.0.1:10808 系统代理），否则超时

## 关键坑

1. **必须用 venv python**：bash 的 `python`（C:\Python314）PYTHONPATH 被污染——`import types` 命中 site-packages 的 notebooklm/types.py，导致 `import playwright.sync_api` 挂掉、login 误报 "Playwright not installed"。venv python（3.11.15）无此问题
2. **`--browser-cookies edge` 不可用**：App-Bound Encryption 解密失败；必须走 Playwright profile 登录
3. **pip 装大包**：`pip install --proxy '' -i https://mirrors.aliyun.com/pypi/simple/`（系统代理下直连 PyPI 超时）
4. **B站链接**：NotebookLM 不认，yt-dlp 先下载音频再上传，需 1-3 分钟
5. **artifact 不自动回流**：云端手动改的导图/报告不会同步本地；需要时重新跑 --learn/--artifact

## 文件结构

```
main.py              # 入口：来源识别 → NotebookLM → 保存
src/pipeline.py      # NotebookLM 通道封装（笔记本/来源/提问/history/artifact）
src/source.py        # 输入类型识别 + B站音频下载
src/output.py        # 保存分析/对话记录/artifact 命名
prompts/analysis.md  # 五段式分析模板
output/              # 生成结果（不入库）
```
