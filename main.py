# -*- coding: utf-8 -*-
"""notebooklm-brief 入口。

用法：
    python main.py <链接或文件路径>
    python main.py --prompt-file prompts/analysis.md <链接>   # 自定义分析模板

流程：识别来源类型 -> NotebookLM 添加来源 -> 按固定模板提问 -> 保存 Markdown 到 output/
"""
import argparse
import asyncio
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.source import classify, bilibili_to_audio
from src.pipeline import NotebookLM
from src.output import save_answer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROMPT_FILE = os.path.join(BASE_DIR, 'prompts', 'analysis.md')
DEFAULT_OUTPUT = os.path.join(BASE_DIR, 'output')


async def run(target: str, prompt: str, output_dir: str, notebook: str) -> str:
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

    async with NotebookLM(notebook_name=notebook) as nlm:
        print('[3/4] 添加来源到 NotebookLM...')
        src_id, title = await nlm.add_source(target, kind, local_path)
        if src_title:  # B站真实视频标题优先于文件名
            title = src_title
        print('      提问中...')
        answer = await nlm.ask(prompt, source_ids=[src_id])

    path = save_answer(target, answer, output_dir, title)
    print(f'[4/4] 完成：{path}')
    return path


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
    parser.add_argument('--notebook', default='链接总结', help='NotebookLM 笔记本名（默认 链接总结）')
    args = parser.parse_args()

    with open(args.prompt_file, encoding='utf-8') as f:
        prompt = f.read()

    for attempt in range(2):
        try:
            path = asyncio.run(run(args.target, prompt, args.output, args.notebook))
            print(f'\n总结已生成：{path}')
            return
        except (ValueError, FileNotFoundError) as e:
            msg = str(e)
            if attempt == 0 and ('Authentication' in msg or 'Storage' in msg) and _relogin():
                continue
            raise


if __name__ == '__main__':
    main()
