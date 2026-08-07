# -*- coding: utf-8 -*-
"""notebooklm-brief 入口。

用法（第一种：单来源分析 + 持续对话）：
    python main.py <链接或文件路径>                    # 完整分析（每个链接自动独立笔记本）
    python main.py <链接或文件路径> --ask "问题"        # 单轮对话（保持上下文，追加到分析文件）
    python main.py <链接或文件路径> --chat              # 交互对话：连续提问，exit 退出
    python main.py <链接或文件路径> --no-learn          # 快速模式：跳过默认学习产物
    python main.py <链接或文件路径> --artifact report   # 单个生成：mindmap/report/studyguide
    #   每次运行后自动生成 <标题>.对话记录.md，汇总所有轮次 问题+回答

其他：
    python main.py --prompt-file prompts/analysis.md <链接>   # 自定义分析模板
    python main.py --notebook 指定笔记本名 <链接>      # 手动指定笔记本
    python main.py --lang en ...                        # artifact 生成语言（默认 zh 中文）
    python main.py --sync-notebooks [--delete-notebooks]  # 按本地 output/ 同步云端笔记本

流程：识别来源类型 -> (B站先匹配 YouTube 原片) -> NotebookLM 添加来源 -> 提问
      -> 保存分析 + 对话记录 + 默认学习产物（导图+学习指南）到 output/<笔记本名>/
"""
import argparse
import asyncio
import os
import re
import subprocess
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.source import (classify, bilibili_to_audio, bilibili_meta,
                        youtube_match, youtube_title)
from src.pipeline import NotebookLM
from src.output import (save_answer, save_chat_log, slugify, notebook_dir,
                        build_note_file, archive_to_raw)
from src import config as cfg

# 默认学习产物：每次完整分析自动生成 内容大纲导图 + 学习指南
DEFAULT_LEARN = ['mindmap', 'studyguide']

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROMPT_FILE = os.path.join(BASE_DIR, 'prompts', 'analysis.md')
DEFAULT_OUTPUT = cfg.get_output_dir()

# artifact 类型 -> 下载文件扩展名
ARTIFACT_EXT = {
    'report': 'md', 'studyguide': 'md',
    'podcast': 'mp3',
    'mindmap': 'json',
    'quiz': 'json', 'flashcards': 'json',
    'infographic': 'png',
    'slidedeck': 'pdf',
}


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
              ask: str = None, chat: bool = False,
              artifacts: list[str] = None, lang: str = 'zh',
              artifact_only: bool = False,
              skip_yt_match: bool = False,
              archive_dir: str = None) -> str:
    kind = classify(target)
    print(f'[1/4] 来源识别：{kind}')
    local_path = None
    src_title = None
    original_url = target if target.startswith('http') else None
    if kind == 'bilibili':
        # 优化：先尝试 YouTube 原片（NotebookLM 服务端直接转写，省下载音频）
        if not skip_yt_match:
            b_title, b_dur = bilibili_meta(target)
            if b_title:
                print('[2/4] B站视频：尝试匹配 YouTube 原片...')
                yt = youtube_match(b_title, b_dur)
                if yt:
                    print(f'      ✓ 命中原片：{yt}')
                    print(f'      标题：{b_title}')
                    target, kind, src_title = yt, 'youtube', b_title
                else:
                    print('      未匹配到原片，回退下载音频')
            else:
                print('      标题获取失败，直接下载音频')
        else:
            print('[2/4] --no-yt-match：跳过 YouTube 匹配，直接下载音频')
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
    elif kind == 'youtube':
        print('[2/4] YouTube：预取标题用于笔记本命名...')
        src_title = youtube_title(target)
        if src_title:
            print(f'      标题：{src_title}')
        else:
            print('      标题获取失败，回退 URL 命名')
    else:
        print('[2/4] 直接使用链接/文件')

    nb_name = resolve_notebook_name(target, kind, src_title, local_path, notebook)
    print(f'      笔记本：{nb_name}')

    # 按笔记本建独立输出文件夹：output/<笔记本名 slug>/
    nb_dir = notebook_dir(output_dir, nb_name)
    print(f'      输出目录：{nb_dir}')

    chat_mode = bool(ask) or chat
    answer = None
    history: list[tuple[str, str]] = []
    last_src_id = None

    # 默认学习产物：完整分析自动生成 导图+学习指南；追问/对话/纯产物模式不默认生成
    if artifacts is None and not chat_mode and not artifact_only:
        artifacts = DEFAULT_LEARN

    async with NotebookLM(notebook_name=nb_name) as nlm:
        if chat_mode:
            print('[3/4] 对话模式：复用笔记本已有来源...')
            sources = await nlm.list_sources()
            if not sources:
                raise ValueError('笔记本里没有来源：请先不带 --ask/--chat 跑一次完整分析')
            src_ids = [sid for sid, _ in sources]
            if src_ids:
                last_src_id = src_ids[0]
            # 真实标题优先（B站/YouTube 预取标题 > NotebookLM 源名）
            title = src_title or sources[0][1] or None
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
        elif artifact_only:
            print('[3/4] 生成 NotebookLM 内容：' + ', '.join(artifacts) + '...')
            title = None
            sources = await nlm.list_sources()
            if not sources:
                print('      笔记本无来源，先添加...')
                src_id, title = await nlm.add_source(target, kind, local_path)
                if src_title:  # B站真实视频标题优先于文件名
                    title = src_title
                sources = await nlm.list_sources()
            src_ids = [sid for sid, _ in sources]
            if not title:
                title = src_title or sources[0][1] or 'untitled'
            paths = await _generate_artifacts(nlm, artifacts, lang, src_ids,
                                              title, nb_dir)
            print(f'[4/4] 完成：{len(paths)} 个文件')
            return paths
        else:
            print('[3/4] 添加来源到 NotebookLM...')
            src_id, title = await nlm.add_source(target, kind, local_path)
            if src_title:  # B站真实视频标题优先于文件名
                title = src_title
            last_src_id = src_id
            print('      提问中...')
            answer = await nlm.ask(prompt, source_ids=[src_id])
            history = await nlm.get_history()
            # 默认学习产物：内容大纲导图 + 学习指南（导图自动转 md）
            if artifacts:
                print(f'      生成学习产物：{", ".join(artifacts)}...')
                paths = await _generate_artifacts(nlm, artifacts, lang, [src_id],
                                                  title, nb_dir)
                print(f'      学习产物已保存：{len(paths)} 个文件')

    # 保存：首次分析新建文件；--ask 单轮追加到分析文件；--chat 内容都在对话记录里
    if not chat_mode:
        path = save_answer(target, answer, nb_dir, title, append=False)
        print(f'[4/4] 分析已保存：{path}')
    elif ask:
        path = save_answer(target, answer, nb_dir, title, append=True)
        print(f'[4/4] 追问已追加：{path}')
    log_path = save_chat_log(target, title, nb_name, history, nb_dir)
    print(f'      对话记录已更新：{log_path}')

    # 合并笔记：原文 + 分析 + 导图 + 学习指南 + 对话记录（每次运行全量重建，实时更新）
    if title and answer:
        fulltext = None
        if last_src_id:
            async with NotebookLM(notebook_name=nb_name) as nlm:
                fulltext = await nlm.get_source_fulltext(last_src_id)
        meta = {'original_url': original_url} if original_url else None
        note_path = build_note_file(nb_dir, title, target, fulltext,
                                    answer, history, meta)
        print(f'      合并笔记已更新：{note_path}')
        # 归档到 RAW
        if archive_dir:
            archived = archive_to_raw(nb_dir, archive_dir, title, meta)
            if archived:
                print(f'      已归档：{archived}')
    return log_path


async def _generate_artifacts(nlm, artifacts: list[str], lang: str,
                              src_ids: list[str], title: str, out_dir: str) -> list[str]:
    """生成并下载多个 artifact 到 out_dir。导图（mindmap）额外转一份易读 .md。"""
    from src.output import mindmap_json_to_md
    paths = []
    for a in artifacts:
        print(f'      生成 {a}...')
        akind, aid = await nlm.generate_artifact(a, lang, src_ids)
        fname = f'{slugify(title)}-{akind}.{ARTIFACT_EXT.get(akind, "bin")}'
        apath = await nlm.download_artifact(akind, aid, os.path.join(out_dir, fname))
        if akind == 'mindmap' and apath.endswith('.json'):
            md_path = mindmap_json_to_md(apath)
            print(f'      ✓ {apath}')
            print(f'      ✓ 导图 Markdown：{md_path}')
        else:
            print(f'      ✓ {apath}')
        paths.append(apath)
    return paths


def local_notebook_dirs(output_dir: str) -> set[str]:
    """本地 output/ 下的笔记本文件夹名集合（笔记-* 目录 = 要保留的清单）。"""
    if not os.path.isdir(output_dir):
        return set()
    return {d for d in os.listdir(output_dir)
            if os.path.isdir(os.path.join(output_dir, d)) and d.startswith('笔记-')}


async def sync_notebooks(output_dir: str, delete: bool = False) -> list[tuple[str, str]]:
    """按本地笔记本文件夹同步云端：保留本地有的，列出（或删除）本地没有的。

    - 本地 output/ 下每个 笔记-<标题> 文件夹 = 应保留的笔记本
    - 云端存在但本地无对应文件夹的笔记本：dry-run 仅列出；delete=True 执行删除
    - 返回实际删除的 [(id, title)] 列表
    """
    local_dirs = local_notebook_dirs(output_dir)
    print(f'[sync] 本地笔记本文件夹：{len(local_dirs)} 个')
    for d in sorted(local_dirs):
        print(f'      保留：{d}')

    async with NotebookLM(notebook_name='') as nlm:
        cloud = await nlm.list_all_notebooks()

    # 本地文件夹名 = slugify(云端笔记本名, max_len=80)；云端名 = 笔记-<slug>
    # 匹配：云端名本身在本地集合里，或云端名 slug 后与某个本地文件夹 slug 相等
    local_slugs = {slugify(d, max_len=80) for d in local_dirs}

    to_delete = []
    for nb_id, title in cloud:
        if title in local_dirs:
            continue
        if slugify(title, max_len=80) in local_slugs:
            continue
        to_delete.append((nb_id, title))

    print(f'[sync] 云端笔记本：{len(cloud)} 个，待清理：{len(to_delete)} 个')
    for nb_id, title in to_delete:
        print(f'      ✗ {title}  (id={nb_id})')

    if delete:
        async with NotebookLM(notebook_name='') as nlm:
            for nb_id, title in to_delete:
                print(f'[sync] 删除：{title}')
                await nlm.delete_notebook(nb_id)
        print(f'[sync] 已删除 {len(to_delete)} 个笔记本')
    else:
        print('[sync] dry-run：未执行删除（加 --delete-notebooks 执行）')

    return to_delete


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
    parser.add_argument('target', nargs='?', default=None,
                        help='链接（文章/YouTube/B站）或本地文件路径')
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
    parser.add_argument('--artifact',
                        choices=['mindmap', 'report', 'studyguide'],
                        help='生成 NotebookLM 原生内容：mindmap 导图 / report 报告 / '
                             'studyguide 学习指南（仅产物，不做分析）')
    parser.add_argument('--learn', action='store_true',
                        help='生成 导图+报告+学习指南 三个学习产物（仅产物，不做分析）')
    parser.add_argument('--no-learn', action='store_true',
                        help='跳过默认学习产物（只出分析+对话记录，快速模式）')
    parser.add_argument('--no-yt-match', action='store_true',
                        help='跳过 B站->YouTube 原片匹配，直接下载音频')
    parser.add_argument('--lang', default='zh',
                        help='artifact 生成语言（默认 zh 中文）')
    parser.add_argument('--sync-notebooks', action='store_true',
                        help='按本地 output/ 笔记本文件夹同步云端：列出云端有但本地没有的笔记本')
    parser.add_argument('--delete-notebooks', action='store_true',
                        help='配合 --sync-notebooks：执行删除（不带则 dry-run）')
    parser.add_argument('--archive', nargs='?', const=None,
                        default=None,
                        help='归档合并笔记到本地目录（默认读 config.yaml 的 archive_dir；'
                             '查重：原始链接优先，其次标题，相同则覆盖）')
    parser.add_argument('--no-archive', action='store_true',
                        help='跳过归档（默认每次分析后自动归档）')
    parser.add_argument('--setup', action='store_true',
                        help='首次使用引导：检查依赖、登录 NotebookLM、创建目录、生成 config.yaml')
    parser.add_argument('--doctor', action='store_true',
                        help='环境自检：依赖/登录/目录/代理/配置')
    args = parser.parse_args()

    # 首次使用引导 / 环境自检
    if args.setup:
        from src.setup import run_setup
        sys.exit(run_setup())
    if args.doctor:
        from src.setup import run_doctor
        sys.exit(run_doctor())

    # 笔记本同步模式：不需要 target
    if args.sync_notebooks:
        try:
            asyncio.run(sync_notebooks(args.output, delete=args.delete_notebooks))
            return
        except Exception as e:
            msg = str(e)
            if 'Authentication' in msg or 'Storage' in msg:
                if _relogin():
                    asyncio.run(sync_notebooks(args.output, delete=args.delete_notebooks))
                    return
            raise

    if not args.target:
        parser.error('需要提供 <链接或文件路径>（或使用 --sync-notebooks）')

    with open(args.prompt_file, encoding='utf-8') as f:
        prompt = f.read()

    question = args.ask or args.follow_up
    artifact_only = False
    if args.learn:
        artifacts = ['mindmap', 'report', 'studyguide']
        artifact_only = True
    elif args.artifact:
        artifacts = [args.artifact]
        artifact_only = True
    elif args.no_learn:
        # 空列表显式跳过默认学习产物（快速模式：只出分析+对话记录）
        artifacts = []
    else:
        # 默认/追问：artifacts 交给 run() 决定（默认分析自动带 导图+学习指南）
        artifacts = None
    for attempt in range(2):
        try:
            # 归档：--no-archive 跳过；否则 --archive 显式目录或 config.yaml 的 archive_dir
            if args.no_archive:
                archive_dir = None
            elif args.archive is not None:
                archive_dir = args.archive
            else:
                archive_dir = cfg.get_archive_dir() or None
            skip_yt = args.no_yt_match or not cfg.get_yt_match()
            path = asyncio.run(run(args.target, prompt, args.output,
                                   args.notebook, question, args.chat,
                                   artifacts, args.lang, artifact_only,
                                   skip_yt, archive_dir))
            print(f'\n总结已生成：{path}')
            return
        except (ValueError, FileNotFoundError) as e:
            msg = str(e)
            if attempt == 0 and ('Authentication' in msg or 'Storage' in msg) and _relogin():
                continue
            raise


if __name__ == '__main__':
    main()
