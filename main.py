# -*- coding: utf-8 -*-
"""notebooklm-brief 入口。

用法（第一种：单来源分析 + 持续对话）：
    python main.py <链接或文件路径>                    # 完整分析（每个链接自动独立笔记本）
    python main.py <链接或文件路径> --ask "问题"        # 单轮对话（保持上下文，追加到分析文件）
    python main.py <链接或文件路径> --chat              # 交互对话：连续提问，exit 退出
    # 每次运行后自动生成 <标题>.对话记录.md，汇总所有轮次 问题+回答

其他：
    python main.py --prompt-file prompts/analysis.md <链接>   # 自定义分析模板
    python main.py --notebook 指定笔记本名 <链接>      # 手动指定笔记本

流程：识别来源类型 -> NotebookLM 添加来源 -> 提问 -> 保存分析 + 对话记录到 output/
"""
import argparse
import asyncio
import os
import re
import subprocess
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.source import classify, bilibili_to_audio
from src.pipeline import NotebookLM
from src.output import save_answer, save_chat_log

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROMPT_FILE = os.path.join(BASE_DIR, 'prompts', 'analysis.md')
DEFAULT_OUTPUT = os.path.join(BASE_DIR, 'output')


def resolve_notebook_name(target: str, kind: str, src_title: str = None,
                          local_path: str = None, explicit: str = None) -> str:
    """笔记本名：显式指定优先；否则按来源自动生成 笔记-<标题>（每链接独立笔记本）。"""
    if explicit:
        return explicit
    base = None
    if src_title:
        base = src_title
    elif local_path:
        base = os.path.splitext(os.path.basename(local_path))[0]
    elif kind in ('url', 'youtube'):
        p = urlparse(target)
        seg = p.path.rstrip('/').split('/')[-1] if p.path else ''
        if seg and seg not in ('watch', 'index', 'home'):
            base = seg
        else:
            base = p.netloc
    else:
        base = target
    slug = re.sub(r'[\\/:*?"<>|\s]+', '-', base).strip('-')
    return f'笔记-{slug[:40] or "untitled"}'


async def run(target: str, prompt: str, output_dir: str, notebook: str,
              ask: str = None, chat: bool = False) -> str:
    kind = classify(target)
    print(f'[1/4] 来源识别：{kind}')
    local_path = None
    src_title = None
    if kind == 'bilibili':
        print('[2/4] B站视频：下载音频...')
        local_path, src_title = bilibili_to_audio(target)
        kind = 'file'
        print(f'      音频：{local_path}')
        if src_title:
            print(f'      标题：{src_title}')
    elif kind == 'file':
        print(f'[2/4] 本地文件：{target}')
        local_path = target
    else:
        print('[2/4] 直接使用链接/文件')

    nb_name = resolve_notebook_name(target, kind, src_title, local_path, notebook)
    print(f'      笔记本：{nb_name}')

    chat_mode = bool(ask) or chat
    answer = None
    history: list[tuple[str, str]] = []

    async with NotebookLM(notebook_name=nb_name) as nlm:
        if chat_mode:
            print('[3/4] 对话模式：复用笔记本已有来源...')
            sources = await nlm.list_sources()
            if not sources:
                raise ValueError('笔记本里没有来源：请先不带 --ask/--chat 跑一次完整分析')
            src_ids = [sid for sid, _ in sources]
            title = sources[0][1] or None
            conv_id = await nlm.get_conversation_id()
            if chat:
                print('      交互对话：直接输入问题回车提问，输入 exit 退出')
                while True:
                    q = input('      你 > ').strip()
                    if not q:
                        continue
                    if q.lower() in ('exit', 'quit', '退出', 'q'):
                        break
                    a = await nlm.ask(q, source_ids=src_ids, conversation_id=conv_id)
                    print(f'      NotebookLM > {a}\n')
            else:
                print('      提问中（保持对话上下文）...')
                answer = await nlm.ask(ask, source_ids=src_ids,
                                       conversation_id=conv_id)
            history = await nlm.get_history()
        else:
            print('[3/4] 添加来源到 NotebookLM...')
            src_id, title = await nlm.add_source(target, kind, local_path)
            if src_title:  # B站真实视频标题优先于文件名
                title = src_title
            print('      提问中...')
            answer = await nlm.ask(prompt, source_ids=[src_id])
            history = await nlm.get_history()

    # 保存：首次分析新建文件；--ask 单轮追加到分析文件；--chat 内容都在对话记录里
    if not chat_mode:
        path = save_answer(target, answer, output_dir, title, append=False)
        print(f'[4/4] 分析已保存：{path}')
    elif ask:
        path = save_answer(target, answer, output_dir, title, append=True)
        print(f'[4/4] 追问已追加：{path}')
    log_path = save_chat_log(target, title, nb_name, history, output_dir)
    print(f'      对话记录已更新：{log_path}')
    return log_path


def _relogin() -> bool:
    """登录态失效时自动重登录（Playwright profile 已保留 Google 登录，全程自动）。"""
    print('[!] 登录态失效，自动重新登录...')
    try:
        r = subprocess.run(
            [sys.executable, '-m', 'notebooklm', 'login', '--browser', 'msedge'],
            capture_output=True, text=True, timeout=180)
        out = (r.stdout or '') + (r.stderr or '')
        print(out.strip())
        return r.returncode == 0 and 'saved' in out.lower()
    except Exception as e:
        print(f'    重登录失败：{e}')
        return False


def main():
    parser = argparse.ArgumentParser(description='链接 -> NotebookLM -> 固定流程总结')
    parser.add_argument('target', help='链接（文章/YouTube/B站）或本地文件路径')
    parser.add_argument('--prompt-file', default=DEFAULT_PROMPT_FILE,
                        help='分析模板文件（默认 prompts/analysis.md）')
    parser.add_argument('--output', default=DEFAULT_OUTPUT, help='输出目录（默认 output/）')
    parser.add_argument('--notebook', default=None,
                        help='NotebookLM 笔记本名（默认自动：每个链接独立 笔记-<标题>）')
    parser.add_argument('--ask', default=None,
                        help='单轮对话：对同一来源追加一个问题（保持对话上下文）')
    parser.add_argument('--follow-up', default=None,
                        help='（--ask 的别名，兼容旧命令）')
    parser.add_argument('--chat', action='store_true',
                        help='交互式对话模式：连续提问，输入 exit 退出；结束后自动汇总对话记录')
    args = parser.parse_args()

    with open(args.prompt_file, encoding='utf-8') as f:
        prompt = f.read()

    question = args.ask or args.follow_up
    for attempt in range(2):
        try:
            path = asyncio.run(run(args.target, prompt, args.output,
                                   args.notebook, question, args.chat))
            print(f'\n总结已生成：{path}')
            return
        except (ValueError, FileNotFoundError) as e:
            msg = str(e)
            if attempt == 0 and ('Authentication' in msg or 'Storage' in msg) and _relogin():
                continue
            raise


if __name__ == '__main__':
    main()
