# -*- coding: utf-8 -*-
"""结果输出：将 NotebookLM 回答格式化保存为 Markdown。"""
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


def save_chat_log(target: str, title: str, nb_name: str,
                  qa_pairs: list[tuple[str, str]], output_dir: str) -> str:
    """渲染完整对话记录（所有轮次 问题->回答）为 Markdown，返回路径。
    文件名：<标题>.对话记录.md（固定名，每次运行全量覆盖更新）。"""
    os.makedirs(output_dir, exist_ok=True)
    fname = f'{slugify(title)}.对话记录.md'
    path = os.path.join(output_dir, fname)

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


def save_answer(target: str, answer: str, output_dir: str,
                title: str = None, append: bool = False) -> str:
    """保存回答为 Markdown 文件，返回文件路径。
    文件名：<标题或来源>.md（固定名，跨天追问也能正确追加到同一文件）
    append=True 时在同名文件末尾追加追问段落（不重建 header）。"""
    os.makedirs(output_dir, exist_ok=True)
    if not title:
        title = target.split('/')[-1] if '/' in target else target
    fname = f'{slugify(title)}.md'
    path = os.path.join(output_dir, fname)

    if append and os.path.isfile(path):
        with open(path, 'a', encoding='utf-8') as f:
            f.write('\n\n---\n\n')
            f.write(f'## 追问：{datetime.now().strftime("%Y-%m-%d %H:%M")}\n\n')
            f.write(answer)
            f.write('\n')
        return path

    header = [
        f'# 链接总结：{title}',
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


def mindmap_json_to_md(json_path: str, md_path: str = None) -> str:
    """NotebookLM 导图 JSON（{name, children[]} 树）-> 易读 Markdown 大纲。
    输出层级：根节点作标题，一级节点 H2，二级起列表缩进。返回 md 文件路径。
    md_path 缺省时与 json 同目录同名 .md。"""
    import json
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


# ---------- 合并笔记（原文 + 分析 + 导图 + 学习指南 + 对话记录） ----------

def build_note_file(nb_dir: str, title: str, target: str,
                    fulltext: str | None, answer: str,
                    qa_pairs: list[tuple[str, str]],
                    meta: dict | None = None) -> str:
    """把 原文/分析/导图/学习指南/对话记录 合并为一个笔记文件（实时全量重建）。
    返回笔记文件路径：<标题>.笔记.md。"""
    fname = f'{slugify(title)}.笔记.md'
    path = os.path.join(nb_dir, fname)

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

    # 第一部分：原文（文章全文 / 视频音频转写）
    if fulltext:
        lines += ['## 原文（来源全文）', '', fulltext.strip(), '', '---', '']
    else:
        lines += ['## 原文（来源全文）', '', '> 原文提取失败或来源不支持提取。', '', '---', '']

    # 第二部分：五段式分析
    lines += ['## 分析', '', answer.strip(), '', '---', '']

    # 第三部分：内容大纲导图（md 版，若存在）
    mmd = os.path.join(nb_dir, f'{slugify(title)}-mindmap.md')
    if os.path.isfile(mmd):
        mm_content = open(mmd, encoding='utf-8').read()
        lines += ['## 内容大纲导图', '', mm_content.strip(), '', '---', '']

    # 第四部分：学习指南（若存在）
    sg = os.path.join(nb_dir, f'{slugify(title)}-studyguide.md')
    if os.path.isfile(sg):
        sg_content = open(sg, encoding='utf-8').read()
        lines += ['## 学习指南', '', sg_content.strip(), '', '---', '']

    # 第五部分：对话记录
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
    """用 Obsidian 模板渲染归档笔记的 frontmatter + 模板正文部分。
    - 模板为 Markdown 文件，frontmatter（--- 之间的 YAML）中空值字段按映射填充：
      title=笔记标题, source=原始链接或来源, author/published/description/tags=meta 提供值,
      created=今天日期
    - 模板中已有值的字段、非 frontmatter 部分原样保留；模板无 frontmatter 时原样返回
    - 返回渲染后的模板文本，归档正文由调用方追加。"""
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
                # tags 列表 -> YAML 行内列表；其余值剥掉换行（frontmatter 单行）
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
    """归档笔记文件到 archive_dir（Obsidian 库目录）。
    - template_path 存在时：用模板渲染 frontmatter + 合并笔记正文；否则直接复制
    - 查重：优先原始链接（meta.original_url），其次标题（去 slug 前缀）
    - 相同则用最新覆盖；不同则新增
    - 返回归档路径；无笔记文件返回 None。"""
    note_file = os.path.join(nb_dir, f'{slugify(title)}.笔记.md')
    if not os.path.isfile(note_file):
        return None
    os.makedirs(archive_dir, exist_ok=True)

    # 原始链接查重：扫描已有归档的 metadata（兼容旧格式 `原始链接：` 与新格式 frontmatter `source:`）
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
    # 标题查重（无链接命中时；兼容旧格式 `# 笔记：` 与新格式 frontmatter `title:`）
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
    # 归档文件名：<标题>.笔记.md（与源文件一致）
    dest = os.path.join(archive_dir, f'{slugify(title, max_len=80)}.笔记.md')
    if target_name and os.path.basename(dest) != target_name:
        # 同名异文件：删除旧的（内容被新的覆盖）
        try:
            os.remove(os.path.join(archive_dir, target_name))
        except OSError:
            pass
    note_content = open(note_file, encoding='utf-8').read()
    if template_path and os.path.isfile(template_path):
        # 模板渲染：frontmatter + 模板正文（若有）+ 合并笔记正文
        rendered = render_archive_note(template_path, title, target or src_url, meta)
        with open(dest, 'w', encoding='utf-8') as f:
            f.write(rendered.rstrip('\n'))
            f.write('\n\n')
            f.write(note_content)
    else:
        import shutil
        shutil.copy2(note_file, dest)
    return dest
