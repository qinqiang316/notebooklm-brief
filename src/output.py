# -*- coding: utf-8 -*-
"""结果输出（V3 Phase 4）：三层知识资产落盘。

output/<笔记本>/
├── metadata.json          # Source Identity（来源唯一身份）
├── source/source.md       # Source 层：原文全文（不可变，首次写入后不覆盖）
├── generated/             # Generated 层：NotebookLM 生成物（可重新生成）
│   ├── analysis.md        #   五段式分析（首次 + --ask 追加）
│   ├── conversation.md    #   对话记录（每次全量覆盖更新）
│   ├── mindmap.json/.md   #   内容大纲导图
│   ├── studyguide.md      #   学习指南
│   ├── report.md          #   简报
│   ├── quiz.md            #   测验（--test）
│   ├── review.md          #   复习建议（--review）
│   └── <标题>.笔记.md      #   合并笔记（综合视图，供归档）
└── knowledge/             # Human 层：用户笔记（AI 默认不覆盖）
    └── README.md
"""
import json
import os
import re
from datetime import datetime


def slugify(title: str, max_len: int = 40) -> str:
    """标题 -> 文件名安全片段。"""
    t = re.sub(r'[\\/:*?"<>|\s]+', '-', title).strip('-')
    return t[:max_len] or 'untitled'


def notebook_dir(output_dir: str, nb_name: str) -> str:
    """按笔记本建独立文件夹：output/<笔记本名 slug>/。"""
    d = os.path.join(output_dir, slugify(nb_name, max_len=80))
    os.makedirs(d, exist_ok=True)
    return d


# ---------- 三层目录 ----------

def source_dir(nb_dir: str) -> str:
    """Source 层目录（原文，不可变）。"""
    d = os.path.join(nb_dir, 'source')
    os.makedirs(d, exist_ok=True)
    return d


def generated_dir(nb_dir: str) -> str:
    """Generated 层目录（NotebookLM 生成物）。"""
    d = os.path.join(nb_dir, 'generated')
    os.makedirs(d, exist_ok=True)
    return d


def knowledge_dir(nb_dir: str) -> str:
    """Human 层目录（用户笔记，AI 不覆盖）。"""
    d = os.path.join(nb_dir, 'knowledge')
    os.makedirs(d, exist_ok=True)
    return d


def save_source_fulltext(nb_dir: str, fulltext: str) -> str | None:
    """原文写入 source/source.md。Source 层不可变：已存在则不覆盖。返回路径或 None。"""
    if not fulltext:
        return None
    d = source_dir(nb_dir)
    path = os.path.join(d, 'source.md')
    if os.path.isfile(path):
        return path  # 不可变：保留首次提取的原文
    with open(path, 'w', encoding='utf-8') as f:
        f.write(fulltext)
    return path


def ensure_knowledge_readme(nb_dir: str, title: str = '') -> str:
    """Human 层初始说明（knowledge/README.md）。已存在不覆盖。返回路径。"""
    d = knowledge_dir(nb_dir)
    path = os.path.join(d, 'README.md')
    if os.path.isfile(path):
        return path
    lines = [
        f'# 个人笔记：{title or "未命名"}',
        '',
        '> 本目录是 **Human 层**：属于你自己的笔记，AI 默认不会覆盖。',
        '> 你可以在这里记录对这份材料的理解、批注、延伸思考。',
        '',
    ]
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return path


# ---------- Generated 层 ----------

def save_answer(target: str, answer: str, nb_dir: str,
                title: str = None, append: bool = False) -> str:
    """保存分析到 generated/analysis.md（固定名，跨天追问追加同一文件）。

    append=True 时在同名文件末尾追加追问段落（不重建 header）。
    """
    d = generated_dir(nb_dir)
    path = os.path.join(d, 'analysis.md')

    if append and os.path.isfile(path):
        with open(path, 'a', encoding='utf-8') as f:
            f.write('\n\n---\n\n')
            f.write(f'## 追问：{datetime.now().strftime("%Y-%m-%d %H:%M")}\n\n')
            f.write(answer)
            f.write('\n')
        return path

    header = [
        f'# 链接总结：{title or target}',
        '',
        f'- 来源：{target}',
        f'- 生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}',
        f'- 通道：Google NotebookLM（Gemini Notebook）',
        '',
        '---',
        '',
    ]
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(header))
        f.write(answer)
        f.write('\n')
    return path


def save_chat_log(target: str, title: str, nb_name: str,
                  qa_pairs: list[tuple[str, str]], nb_dir: str) -> str:
    """渲染完整对话记录到 generated/conversation.md（每次全量覆盖更新）。"""
    d = generated_dir(nb_dir)
    path = os.path.join(d, 'conversation.md')

    lines = [
        f'# 对话记录：{title}',
        '',
        f'- 来源：{target}',
        f'- 笔记本：{nb_name}',
        f'- 轮次：{len(qa_pairs)}',
        f'- 更新时间：{datetime.now().strftime("%Y-%m-%d %H:%M")}',
        '',
        '---',
        '',
    ]
    for i, (q, a) in enumerate(qa_pairs, 1):
        lines += [
            f'## 第 {i} 轮',
            '',
            '**提问**：',
            '',
            q,
            '',
            '**NotebookLM 回答**：',
            '',
            a,
            '',
            '---',
            '',
        ]
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return path


def mindmap_json_to_md(json_path: str, md_path: str = None) -> str:
    """NotebookLM 导图 JSON（{name, children[]} 树）-> 易读 Markdown 大纲。"""
    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)

    lines: list[str] = []
    root = data.get('name') or '内容大纲'
    lines.append(f'# {root}')
    lines.append('')

    def walk(node, depth):
        name = node.get('name', '')
        if depth == 1:
            lines.append(f'## {name}')
            lines.append('')
        else:
            lines.append('  ' * (depth - 2) + f'- {name}')
        for child in node.get('children') or []:
            walk(child, depth + 1)

    for child in data.get('children') or []:
        walk(child, 1)
    if md_path is None:
        md_path = os.path.splitext(json_path)[0] + '.md'
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return md_path


def quiz_json_to_md(json_path: str, md_path: str = None) -> str:
    """NotebookLM 测验 JSON -> 可读 Markdown（题目 + 选项 + 答案）。

    容错解析多种结构：{"questions": [...]} / {"quiz": [...]} / 直接数组 /
    [{"question": ...}]。md_path 缺省时与 json 同目录同名 .md。
    """
    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)

    questions = data
    if isinstance(data, dict):
        questions = (data.get('questions') or data.get('quiz')
                     or data.get('items') or data.get('questionsList') or [])
    if not isinstance(questions, list):
        questions = []

    lines = ['# 测验（Quiz）', '']
    if not questions:
        lines.append('> 未解析到题目（JSON 结构未知，原始文件保留）。')
    for i, q in enumerate(questions, 1):
        if not isinstance(q, dict):
            lines.append(f'## 第 {i} 题\n\n{q}\n')
            continue
        question = (q.get('question') or q.get('prompt')
                    or q.get('text') or q.get('title') or '')
        options = (q.get('options') or q.get('choices')
                   or q.get('answers') or [])
        correct = (q.get('correctAnswer') or q.get('answer')
                   or q.get('correct') or q.get('answerIndex'))
        lines.append(f'## 第 {i} 题\n')
        lines.append(question)
        if options:
            lines.append('')
            for oi, opt in enumerate(options):
                if isinstance(opt, dict):
                    opt = opt.get('text') or opt.get('option') or str(opt)
                lines.append(f'- {opt}')
        if correct is not None:
            if isinstance(correct, int) and options:
                try:
                    correct = options[correct]
                except Exception:
                    pass
            lines.append('')
            lines.append(f'**答案**：{correct}')
        lines.append('')
        lines.append('---')
        lines.append('')
    if md_path is None:
        md_path = os.path.splitext(json_path)[0] + '.md'
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return md_path


# ---------- 合并笔记（综合视图，供归档） ----------

def build_note_file(nb_dir: str, title: str, target: str,
                    fulltext: str | None, answer: str,
                    qa_pairs: list[tuple[str, str]],
                    meta: dict | None = None) -> str:
    """把 原文/分析/导图/学习指南/对话记录 合并为 generated/<标题>.笔记.md。"""
    d = generated_dir(nb_dir)
    fname = f'{slugify(title)}.笔记.md'
    path = os.path.join(d, fname)

    lines = [
        f'# 笔记：{title}',
        '',
        f'- 来源：{target}',
        f'- 更新：{datetime.now().strftime("%Y-%m-%d %H:%M")}',
        f'- 通道：Google NotebookLM（Gemini Notebook）',
    ]
    if meta and meta.get('original_url'):
        lines.append(f'- 原始链接：{meta["original_url"]}')
    lines += ['', '---', '']

    if fulltext:
        lines += ['## 原文（来源全文）', '', fulltext.strip(), '', '---', '']
    else:
        lines += ['## 原文（来源全文）', '', '> 原文提取失败或来源不支持提取。', '', '---', '']

    lines += ['## 分析', '', answer.strip(), '', '---', '']

    mmd = os.path.join(d, 'mindmap.md')
    if os.path.isfile(mmd):
        lines += ['## 内容大纲导图', '', open(mmd, encoding='utf-8').read().strip(), '', '---', '']

    sg = os.path.join(d, 'studyguide.md')
    if os.path.isfile(sg):
        lines += ['## 学习指南', '', open(sg, encoding='utf-8').read().strip(), '', '---', '']

    if qa_pairs:
        lines += ['## 对话记录', '']
        for i, (q, a) in enumerate(qa_pairs, 1):
            lines += [f'### 第 {i} 轮', '', '**提问**：', '', q, '',
                      '**回答**：', '', a, '', '---', '']
    else:
        lines += ['## 对话记录', '', '> 暂无对话记录。', '']

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return path


# ---------- 归档到 Obsidian 库（查重：原始链接优先，其次标题；相同则覆盖） ----------

def render_archive_note(template_path: str, title: str, source: str,
                        meta: dict | None = None) -> str:
    """用 Obsidian 模板渲染归档笔记的 frontmatter + 模板正文部分。"""
    with open(template_path, encoding='utf-8') as f:
        text = f.read()

    m = re.match(r'^---\s*\n(.*?)\n---\s*\n?(.*)$', text, re.S)
    if not m:
        return text  # 无 frontmatter，原样返回

    fm_body, rest = m.group(1), m.group(2)
    meta = meta or {}
    values = {
        'title': title,
        'source': source or meta.get('original_url') or '',
        'author': meta.get('author') or '',
        'published': meta.get('published') or '',
        'created': datetime.now().strftime('%Y-%m-%d'),
        'description': meta.get('description') or '',
        'tags': meta.get('tags') or '',
    }
    lines = []
    for line in fm_body.split('\n'):
        km = re.match(r'^(\s*)([\w.-]+)\s*:\s*(.*)$', line)
        if km and not line.lstrip().startswith('#'):
            indent, key, val = km.group(1), km.group(2), km.group(3)
            if not val.strip() and key in values and values[key]:
                if key == 'tags' and isinstance(values[key], (list, tuple)):
                    rendered = ', '.join(str(t) for t in values[key])
                    lines.append(f'{indent}{key}: [{rendered}]')
                else:
                    rendered = str(values[key]).replace('\n', ' ').strip()
                    lines.append(f'{indent}{key}: {rendered}')
                continue
        lines.append(line)

    return '---\n' + '\n'.join(lines) + '\n---\n' + rest


def archive_to_raw(nb_dir: str, archive_dir: str,
                   title: str, meta: dict | None = None,
                   target: str = None,
                   template_path: str = None) -> str | None:
    """归档合并笔记到 archive_dir（Obsidian 库目录）。
    - 笔记文件：generated/<标题>.笔记.md（V3 三层结构）
    - 查重：优先原始链接（meta.original_url），其次标题；相同则用最新覆盖
    - 返回归档路径；无笔记文件返回 None。"""
    note_file = os.path.join(nb_dir, 'generated', f'{slugify(title)}.笔记.md')
    if not os.path.isfile(note_file):
        return None
    os.makedirs(archive_dir, exist_ok=True)

    src_url = (meta or {}).get('original_url') or ''
    target_name = None
    if src_url:
        for f in os.listdir(archive_dir):
            if not f.endswith('.md'):
                continue
            p = os.path.join(archive_dir, f)
            try:
                head = open(p, encoding='utf-8').read(2000)
            except Exception:
                continue
            if f'原始链接：{src_url}' in head or f'source: {src_url}' in head:
                target_name = f
                break
    if target_name is None:
        slug_title = slugify(title, max_len=80)
        for f in os.listdir(archive_dir):
            if not f.endswith('.md'):
                continue
            stem = os.path.splitext(f)[0]
            try:
                head = open(os.path.join(archive_dir, f), encoding='utf-8').read(2000)
            except Exception:
                continue
            if stem == slug_title or f'# 笔记：{title}' in head or f'title: {title}' in head:
                target_name = f
                break
    dest = os.path.join(archive_dir, f'{slugify(title, max_len=80)}.笔记.md')
    if target_name and os.path.basename(dest) != target_name:
        try:
            os.remove(os.path.join(archive_dir, target_name))
        except OSError:
            pass
    note_content = open(note_file, encoding='utf-8').read()
    if template_path and os.path.isfile(template_path):
        rendered = render_archive_note(template_path, title, target or src_url, meta)
        with open(dest, 'w', encoding='utf-8') as f:
            f.write(rendered.rstrip('\n'))
            f.write('\n\n')
            f.write(note_content)
    else:
        import shutil
        shutil.copy2(note_file, dest)
    return dest
