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
