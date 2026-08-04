# -*- coding: utf-8 -*-
"""结果输出：将 NotebookLM 回答格式化保存为 Markdown。"""
import os
import re
from datetime import datetime


def slugify(title: str, max_len: int = 40) -> str:
    """标题 -> 文件名安全片段。"""
    t = re.sub(r'[\\/:*?"<>|\s]+', '-', title).strip('-')
    return t[:max_len] or 'untitled'


def save_chat_log(target: str, title: str, nb_name: str,
                  qa_pairs: list[tuple[str, str]], output_dir: str) -> str:
    """渲染完整对话记录（所有轮次 问题->回答）为 Markdown，返回路径。
    文件名：<日期>-<标题>.对话记录.md（每次运行全量覆盖更新）。"""
    os.makedirs(output_dir, exist_ok=True)
    date = datetime.now().strftime('%Y-%m-%d')
    fname = f'{date}-{slugify(title)}.对话记录.md'
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
    文件名：<日期>-<标题或来源>.md
    append=True 时在同名文件末尾追加追问段落（不重建 header）。"""
    os.makedirs(output_dir, exist_ok=True)
    date = datetime.now().strftime('%Y-%m-%d')
    if not title:
        title = target.split('/')[-1] if '/' in target else target
    fname = f'{date}-{slugify(title)}.md'
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
