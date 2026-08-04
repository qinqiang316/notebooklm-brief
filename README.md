# notebooklm-brief

链接 → NotebookLM → 固定五段式中文分析报告。

把任意文章链接、YouTube/B站视频、本地文件丢进来，自动走 NotebookLM（Google Gemini Notebook）通道，按固定模板生成结构化 Markdown 分析报告，存到 `output/` 目录。

## 功能特性

- **多来源自动识别**：文章 URL、YouTube、B站（自动下载音频转写）、本地文件（PDF/文本/音频/视频），无需手动指定类型
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

# 单来源学习：一次生成 导图(mindmap.json)+报告(report.md)+学习指南(studyguide.md)
python main.py "https://www.youtube.com/watch?v=..." --learn

# 单个生成（可选）：--artifact mindmap / report / studyguide
python main.py "https://www.youtube.com/watch?v=..." --artifact report

# 自定义分析模板
python main.py --prompt-file prompts/analysis.md <链接>

# 指定输出目录 / 手动指定笔记本（覆盖自动命名）
python main.py --output ./output --notebook 链接总结 <链接>
```

- 默认每个链接一个独立笔记本（`笔记-<标题>`），对话只在对应笔记本的上下文里进行，互不污染
- 每次运行后自动生成 **`<标题>.对话记录.md`**：汇总 NotebookLM 里所有轮次的问题和回答（首次模板分析 + 每次 --ask/--chat），全量覆盖更新
- `--ask` 单轮追问结果同时追加到分析文件；`--chat` 多轮内容都在对话记录里
- `--learn` / `--artifact` 输出到 `output/artifacts/`：导图(JSON 树)、报告(简报 md)、学习指南(md)
- 旧参数 `--follow-up` 是 `--ask` 的别名，兼容

B站视频会先下载音频再转写，耗时约 1-3 分钟，属正常。

## 项目结构

```
notebooklm-brief/
├─ main.py              # 入口：来源识别 → 添加来源 → 提问 → 保存
├─ prompts/
│  └─ analysis.md       # 默认五段式分析模板（可替换）
├─ src/
│  ├─ source.py         # 来源分类 + B站音频下载
│  ├─ pipeline.py       # NotebookLM 客户端封装
│  └─ output.py         # 保存 Markdown 报告
├─ output/              # 生成的报告（已 gitignore）
└─ .gitignore
```

## 输出示例

每份报告为 `output/<日期>-<标题>.md`，头部带来源链接与生成时间，正文按模板五段展开：

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
