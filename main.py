# -*- coding: utf-8 -*-
"""notebooklm-brief V3 入口：基于 NotebookLM 的个人研究与学习 Agent。

子命令：
    analyze <source>                  # 首次完整分析（五段式 + 默认 导图+学习指南）
    ask <source> "问题"                # 单轮追问（保持 NotebookLM 上下文）
    chat <source>                     # 交互式对话（exit 退出）
    learn <source>                    # 学习闭环第一版：分析 + 导图 + 学习指南 + 测验
    test <source>                     # 学习闭环第二版：根据来源内容测验（保存 generated/quiz.md）
    review <source>                   # 学习闭环第三版：按测验结果给出复习建议（generated/review.md）
    sync [--delete-notebooks]         # 按本地 output/ 同步云端笔记本
    doctor                            # 环境自检
    setup                             # 首次使用引导

旧式 flag 调用（main.py <source> --ask/--chat/...）自动翻译为子命令，保持兼容。

架构：Agent 负责资源调度与知识沉淀，NotebookLM 负责资源理解。
输出三层资产（Source 原文 / Generated 生成物 / Human 个人笔记）。
"""
import argparse
import asyncio
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src import config as cfg
from src.models import (SourceRecord, save_metadata, load_metadata,
                        find_notebook_by_source_id)
from src.output import (save_answer, save_chat_log, slugify, notebook_dir,
                        build_note_file, archive_to_raw, save_source_fulltext,
                        ensure_knowledge_readme, generated_dir,
                        mindmap_json_to_md, quiz_json_to_md)
from src.pipeline import NotebookLM
from src.routing import resolve_input

# 默认学习产物：完整分析自动生成 内容大纲导图 + 学习指南
DEFAULT_LEARN = ['mindmap', 'studyguide']
# 学习闭环第一版：分析 + 导图 + 学习指南 + 测验
FULL_LEARN = ['mindmap', 'studyguide', 'quiz']

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

COMMANDS = ('analyze', 'ask', 'chat', 'learn', 'test', 'review',
            'sync', 'doctor', 'setup')


# ---------- 输入准备（Router + 笔记本定位 + 三层目录） ----------

def prepare_source(target: str, output_dir: str, notebook: str,
                   skip_yt_match: bool = False, confirm_fn=None) -> dict:
    """统一输入路由 -> SourceInput -> 笔记本复用/新建 -> 三层目录。"""
    src = resolve_input(target, skip_yt_match=skip_yt_match, confirm_fn=confirm_fn)
    kind = src.type
    print(f'[1/4] 来源识别：{src.original_type}' + (f'（处理：{kind}）' if kind != src.original_type else ''))

    # B站 -> YouTube 原片命中展示
    if src.yt_match:
        cand, conf = src.yt_match
        print(f'      ✓ 命中原片：{cand.url}')
        print(f'      标题：{cand.title}   匹配度：{conf * 100:.0f}%')
    if src.local_path:
        print(f'      本地文件：{src.local_path}')
    if src.title:
        print(f'      标题：{src.title}')

    original_url = src.original if src.original.startswith('http') else None

    # Source Identity：按 source_id 复用已有笔记本
    existing = find_notebook_by_source_id(output_dir, src.source_id) if src.source_id else None
    existing_nb_id = None
    if existing:
        nb_dir, rec = existing
        nb_name = rec.notebook_title or os.path.basename(nb_dir)
        existing_nb_id = rec.notebook_id or None
        print(f'      复用已有笔记本：{nb_name}（source {src.source_id[:8]}）')
    else:
        nb_name = resolve_notebook_name(src, notebook)
        nb_dir = notebook_dir(output_dir, nb_name)
        # 目录名冲突：同名但不同 source_id -> 加短 id 后缀区分
        if os.path.isdir(nb_dir):
            existing_rec = load_metadata(nb_dir)
            if existing_rec is not None and existing_rec.source_id != src.source_id:
                nb_name = f'{nb_name}-{src.source_id[:6]}'
                nb_dir = notebook_dir(output_dir, nb_name)
        print(f'      笔记本：{nb_name}')
    print(f'      输出目录：{nb_dir}')

    # Human 层初始化（AI 不覆盖）
    ensure_knowledge_readme(nb_dir, nb_name)

    return {
        'src': src, 'kind': kind, 'original_url': original_url,
        'source_id': src.source_id, 'canonical': src.canonical,
        'local_path': src.local_path, 'src_title': src.title,
        'input_kind': src.original_type, 'duration': src.duration,
        'nb_name': nb_name, 'nb_dir': nb_dir, 'existing_nb_id': existing_nb_id,
    }


def resolve_notebook_name(src, explicit: str = None) -> str:
    """笔记本名：显式指定优先；否则按来源自动生成 笔记-<短标题>（每来源独立笔记本）。

    - URL/YouTube/B站：预取标题，截短（max_len=24）
    - 本地文件：用文件名（去扩展名），不要完整路径
    """
    if explicit:
        return explicit
    if src.local_path and not src.title:
        base = os.path.splitext(os.path.basename(src.local_path))[0]
    else:
        base = src.title or src.original
    return f'笔记-{slugify(base, max_len=24) or "untitled"}'


def _confirm_yt(cand, score) -> bool:
    """B站中等置信度匹配：交互确认。非交互环境（EOFError）回退下载音频。"""
    print()
    print('发现可能的 YouTube 原片：')
    print(f'  标题：{cand.title}')
    if cand.duration:
        print(f'  时长：{int(cand.duration // 60)}分{int(cand.duration % 60)}秒')
    if cand.channel:
        print(f'  频道：{cand.channel}')
    print(f'  匹配度：{score * 100:.0f}%')
    try:
        r = input('  是否使用该 YouTube 原片？[y/N] ').strip().lower()
        return r in ('y', 'yes', '是')
    except EOFError:
        return False


# ---------- 核心流程 ----------

async def run(target: str, prompt: str, output_dir: str, notebook: str,
              ask: str = None, chat: bool = False,
              artifacts: list[str] = None, lang: str = 'zh',
              artifact_only: bool = False,
              skip_yt_match: bool = False,
              archive_dir: str = None,
              archive_template: str = None,
              confirm_fn=None, provider=None) -> str:
    prep = prepare_source(target, output_dir, notebook, skip_yt_match, confirm_fn)
    src = prep['src']
    kind = prep['kind']
    original_url = prep['original_url']
    source_id = prep['source_id']
    canonical = prep['canonical']
    local_path = prep['local_path']
    src_title = prep['src_title']
    input_kind = prep['input_kind']
    duration = prep['duration']
    nb_name = prep['nb_name']
    nb_dir = prep['nb_dir']
    existing_nb_id = prep['existing_nb_id']
    target_for_nlm = local_path if kind == 'file' else src.original

    chat_mode = bool(ask) or chat
    answer = None
    history: list[tuple[str, str]] = []
    last_src_id = None

    # 默认学习产物：完整分析自动生成 导图+学习指南；追问/对话/纯产物模式不默认生成
    if artifacts is None and not chat_mode and not artifact_only:
        artifacts = DEFAULT_LEARN

    async with NotebookLM(notebook_name=nb_name, notebook_id=existing_nb_id,
                          provider=provider) as nlm:
        if chat_mode:
            print('[3/4] 对话模式：复用笔记本已有来源...')
            sources = await nlm.list_sources()
            if not sources:
                raise ValueError('笔记本里没有来源：请先不带 ask/chat 跑一次完整分析')
            src_ids = [sid for sid, _ in sources]
            if src_ids:
                last_src_id = src_ids[0]
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
                src_id, title = await nlm.add_source(target_for_nlm, kind, local_path)
                if src_title:
                    title = src_title
                sources = await nlm.list_sources()
            src_ids = [sid for sid, _ in sources]
            if not title:
                title = src_title or sources[0][1] or 'untitled'
            paths = await _generate_artifacts(nlm, artifacts, lang, src_ids,
                                              nb_dir)
            print(f'[4/4] 完成：{len(paths)} 个文件')
        else:
            print('[3/4] 添加来源到 NotebookLM...')
            src_id, title = await nlm.add_source(target_for_nlm, kind, local_path)
            if src_title:  # B站/YouTube 真实标题优先于 NotebookLM 源名
                title = src_title
            last_src_id = src_id
            print('      提问中...')
            answer = await nlm.ask(prompt, source_ids=[src_id])
            history = await nlm.get_history()
            if artifacts:
                print(f'      生成学习产物：{", ".join(artifacts)}...')
                paths = await _generate_artifacts(nlm, artifacts, lang, [src_id],
                                                  nb_dir)
                print(f'      学习产物已保存：{len(paths)} 个文件')

    # V3 Source Identity：保存/更新 metadata.json（含 notebook_id 关联）
    if source_id:
        rec = SourceRecord(
            source_id=source_id,
            source_type=input_kind,
            original_url=original_url or '',
            canonical_url=canonical or '',
            title=title or '',
            duration=duration,
            local_path=local_path or '',
            notebook_id=nlm.notebooks._notebook_id or '',
            notebook_title=nb_name,
        )
        save_metadata(nb_dir, rec)
        print(f'      metadata 已更新：{nb_dir}/metadata.json')

    if artifact_only:
        return paths

    # Generated 层：分析 + 对话记录
    if not chat_mode:
        path = save_answer(src.original, answer, nb_dir, title, append=False)
        print(f'[4/4] 分析已保存：{path}')
    elif ask:
        path = save_answer(src.original, answer, nb_dir, title, append=True)
        print(f'[4/4] 追问已追加：{path}')
    log_path = save_chat_log(src.original, title, nb_name, history, nb_dir)
    print(f'      对话记录已更新：{log_path}')

    # Source 层（原文，不可变）+ 合并笔记 + 归档
    if title and answer:
        fulltext = None
        if kind == 'url':
            from src.fetch_fulltext import fetch_clipper_fulltext
            fulltext = await fetch_clipper_fulltext(src.original)
            if fulltext:
                print('      原文提取：Obsidian Clipper 路线（完整正文）')
        if not fulltext and last_src_id:
            async with NotebookLM(notebook_name=nb_name, provider=provider) as nlm:
                fulltext = await nlm.get_source_fulltext(last_src_id)
                if fulltext and kind == 'url':
                    print('      (Clipper 提取不可用，已回退 NotebookLM 原文)')
        src_path = save_source_fulltext(nb_dir, fulltext)
        meta = {'original_url': original_url} if original_url else None
        note_path = build_note_file(nb_dir, title, src.original, fulltext,
                                    answer, history, meta)
        print(f'      合并笔记已更新：{note_path}')
        if archive_dir:
            archived = archive_to_raw(nb_dir, archive_dir, title, meta,
                                      src.original, archive_template)
            if archived:
                print(f'      已归档：{archived}')
    return log_path


async def _generate_artifacts(nlm, artifacts: list[str], lang: str,
                              src_ids: list[str], nb_dir: str) -> list[str]:
    """生成并下载 artifact 到 generated/（固定名，可重新生成）。
    导图（mindmap）与测验（quiz）额外转一份易读 .md。"""
    paths = []
    gdir = generated_dir(nb_dir)
    for a in artifacts:
        print(f'      生成 {a}...')
        akind, aid = await nlm.generate_artifact(a, lang, src_ids)
        fname = f'{akind}.{ARTIFACT_EXT.get(akind, "bin")}'
        apath = await nlm.download_artifact(akind, aid, os.path.join(gdir, fname))
        if akind == 'mindmap' and apath.endswith('.json'):
            md_path = mindmap_json_to_md(apath)
            print(f'      ✓ {apath}')
            print(f'      ✓ 导图 Markdown：{md_path}')
        elif akind == 'quiz' and apath.endswith('.json'):
            md_path = quiz_json_to_md(apath)
            print(f'      ✓ {apath}')
            print(f'      ✓ 测验 Markdown：{md_path}')
        else:
            print(f'      ✓ {apath}')
        paths.append(apath)
    return paths


# ---------- 学习闭环 ----------

async def run_test(target: str, output_dir: str, notebook: str, lang: str,
                   skip_yt_match: bool, confirm_fn, provider) -> str:
    """第二版：NotebookLM 根据来源内容测验用户，保存 generated/quiz.md。"""
    prep = prepare_source(target, output_dir, notebook, skip_yt_match, confirm_fn)
    nb_name, nb_dir, existing_nb_id = prep['nb_name'], prep['nb_dir'], prep['existing_nb_id']
    async with NotebookLM(notebook_name=nb_name, notebook_id=existing_nb_id,
                          provider=provider) as nlm:
        sources = await nlm.list_sources()
        if not sources:
            raise ValueError('笔记本里没有来源：请先 analyze/learn 建立内容')
        src_ids = [sid for sid, _ in sources]
        paths = await _generate_artifacts(nlm, ['quiz'], lang, src_ids, nb_dir)
    quiz_md = os.path.join(nb_dir, 'generated', 'quiz.md')
    if os.path.isfile(quiz_md):
        print('\n' + open(quiz_md, encoding='utf-8').read())
    print(f'测验已保存：{quiz_md}')
    return quiz_md


def _ask_quiz_interactively(quiz_text: str) -> str:
    """解析 quiz.md 逐题作答，返回"题号 - 我的答案"文本。非交互环境给"未作答"。"""
    lines = quiz_text.splitlines()
    questions = []
    cur = []
    for ln in lines:
        if ln.startswith('## 第'):
            if cur:
                questions.append('\n'.join(cur))
            cur = [ln]
        elif cur:
            cur.append(ln)
    if cur:
        questions.append('\n'.join(cur))
    answers = []
    print('\n========== 测验作答 ==========')
    for i, q in enumerate(questions, 1):
        print(f'\n--- 第 {i} 题 ---')
        print(q)
        try:
            a = input(f'  你的答案（回车跳过）> ').strip()
        except EOFError:
            a = ''
        answers.append(f'第 {i} 题：{a or "（未作答）"}')
    print('================================')
    return '\n'.join(answers)


async def run_review(target: str, output_dir: str, notebook: str, lang: str,
                     skip_yt_match: bool, confirm_fn, provider) -> str:
    """第三版：根据用户作答 + Quiz 结果，NotebookLM 给出薄弱点分析与复习建议。"""
    prep = prepare_source(target, output_dir, notebook, skip_yt_match, confirm_fn)
    nb_name, nb_dir, existing_nb_id = prep['nb_name'], prep['nb_dir'], prep['existing_nb_id']
    quiz_md = os.path.join(nb_dir, 'generated', 'quiz.md')
    if not os.path.isfile(quiz_md):
        print('未找到测验，先生成 quiz...')
        await run_test(target, output_dir, notebook, lang, skip_yt_match,
                       confirm_fn, provider)
    if not os.path.isfile(quiz_md):
        raise ValueError('测验生成失败，无法复习')

    quiz_text = open(quiz_md, encoding='utf-8').read()
    answers = _ask_quiz_interactively(quiz_text)
    prompt = (
        '我刚刚完成了一次针对本材料内容的测验。请基于测验题目和我的作答：\n'
        '1) 判断我哪些题目答错或没把握，指出对应薄弱知识点；\n'
        '2) 针对薄弱点给出具体复习建议（结合材料内容）；\n'
        '3) 建议我接下来应该继续追问的 2-3 个问题。\n\n'
        f'=== 测验内容 ===\n{quiz_text}\n\n'
        f'=== 我的作答 ===\n{answers}'
    )
    async with NotebookLM(notebook_name=nb_name, notebook_id=existing_nb_id,
                          provider=provider) as nlm:
        sources = await nlm.list_sources()
        if not sources:
            raise ValueError('笔记本里没有来源：请先 analyze/learn 建立内容')
        src_ids = [sid for sid, _ in sources]
        print('      分析薄弱点并生成复习建议（NotebookLM）...')
        review = await nlm.ask(prompt, source_ids=src_ids)

    review_path = os.path.join(nb_dir, 'generated', 'review.md')
    with open(review_path, 'w', encoding='utf-8') as f:
        f.write(f'# 复习建议\n\n- 来源：{target}\n'
                f'- 更新：{datetime.now().strftime("%Y-%m-%d %H:%M")}\n\n---\n\n'
                f'{review}\n')
    print(f'\n{review}')
    print(f'复习建议已保存：{review_path}')
    return review_path


# ---------- 笔记本同步 ----------

def local_notebook_dirs(output_dir: str) -> set[str]:
    """本地 output/ 下的笔记本文件夹名集合（兼容入口，逻辑在 NotebookManager）。"""
    from src.notebook import NotebookManager
    return NotebookManager(None).local_notebook_dirs(output_dir)


async def sync_notebooks(output_dir: str, delete: bool = False) -> list[tuple[str, str]]:
    """按本地笔记本文件夹同步云端（委托 NotebookManager.sync）。"""
    async with NotebookLM(notebook_name='') as nlm:
        return await nlm.notebooks.sync(output_dir, delete=delete)


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


# ---------- CLI ----------

def _translate_legacy(argv: list[str]) -> list[str]:
    """旧式 flag 调用 -> 子命令形式（保持兼容）。

    例：main.py <url> --ask "问题"  ->  ask <url> "问题"
        main.py <url> --chat        ->  chat <url>
        main.py <url> --learn       ->  learn <url>
        main.py --sync-notebooks    ->  sync
    """
    if not argv or argv[0] in COMMANDS:
        return argv
    flags = [a for a in argv if a.startswith('-')]
    if '--sync-notebooks' in flags:
        rest = [a for a in argv if a not in ('--sync-notebooks',)]
        return ['sync', *rest]
    if '--doctor' in flags:
        return ['doctor', *[a for a in argv if a != '--doctor']]
    if '--setup' in flags:
        return ['setup', *[a for a in argv if a != '--setup']]

    target = None
    rest = []
    for a in argv:
        if a.startswith('-'):
            rest.append(a)
        elif target is None:
            target = a
        else:
            rest.append(a)
    if target is None:
        return argv

    if '--chat' in flags:
        return ['chat', target, *[a for a in rest if a != '--chat']]
    if '--test' in flags:
        return ['test', target, *[a for a in rest if a != '--test']]
    if '--review' in flags:
        return ['review', target, *[a for a in rest if a != '--review']]

    for fl in ('--ask', '--follow-up'):
        if fl in rest:
            i = rest.index(fl)
            question = rest[i + 1] if i + 1 < len(rest) else ''
            rest = rest[:i] + rest[i + 2:]
            return ['ask', target, question, *rest]

    if '--artifact' in flags or '--learn' in flags:
        return ['learn', target, *[a for a in rest if a != '--learn']]
    return ['analyze', target, *rest]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='notebooklm-brief',
        description='基于 NotebookLM 的个人研究与学习 Agent：资源调度 + 知识沉淀，'
                    'NotebookLM 负责资源理解。')
    sub = parser.add_subparsers(dest='command')

    def common(p, need_target=True, with_no_learn=False, with_artifact=False):
        if need_target:
            p.add_argument('target', help='链接（文章/YouTube/B站）或本地文件路径')
        p.add_argument('--notebook', default=None, help='指定笔记本名（默认自动 笔记-<标题>）')
        p.add_argument('--output', default=DEFAULT_OUTPUT, help='输出目录（默认 output/）')
        p.add_argument('--lang', default='zh', help='artifact 生成语言（默认 zh 中文）')
        p.add_argument('--no-yt-match', action='store_true',
                       help='跳过 B站->YouTube 原片匹配，直接下载音频')
        p.add_argument('--prompt-file', default=DEFAULT_PROMPT_FILE,
                       help='分析模板文件（默认 prompts/analysis.md）')
        p.add_argument('--archive', nargs='?', const=None, default=None,
                       help='归档合并笔记到本地目录（默认读 config.yaml 的 archive_dir）')
        p.add_argument('--no-archive', action='store_true', help='跳过归档')
        if with_no_learn:
            p.add_argument('--no-learn', action='store_true',
                           help='跳过默认学习产物（快速模式）')
        if with_artifact:
            p.add_argument('--artifact', choices=list(ARTIFACT_EXT),
                           help='仅生成指定产物（不做分析）')

    p = sub.add_parser('analyze', help='首次完整分析（五段式 + 默认 导图+学习指南）')
    common(p, with_no_learn=True)
    p = sub.add_parser('ask', help='单轮追问（保持 NotebookLM 上下文）')
    common(p)
    p.add_argument('question', help='追问的问题')
    p = sub.add_parser('chat', help='交互式对话（exit 退出）')
    common(p)
    p = sub.add_parser('learn', help='学习闭环第一版：分析 + 导图 + 学习指南 + 测验')
    common(p, with_artifact=True)
    p = sub.add_parser('test', help='学习闭环第二版：根据来源内容测验（generated/quiz.md）')
    common(p)
    p = sub.add_parser('review', help='学习闭环第三版：按测验结果给出复习建议（generated/review.md）')
    common(p)
    p = sub.add_parser('sync', help='按本地 output/ 同步云端笔记本')
    p.add_argument('--output', default=DEFAULT_OUTPUT, help='输出目录（默认 output/）')
    p.add_argument('--delete-notebooks', action='store_true', help='执行删除（默认 dry-run）')
    sub.add_parser('doctor', help='环境自检')
    sub.add_parser('setup', help='首次使用引导')
    return parser


def main():
    argv = _translate_legacy(sys.argv[1:])
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == 'setup':
        from src.setup import run_setup
        sys.exit(run_setup())
    if args.command == 'doctor':
        from src.setup import run_doctor
        sys.exit(run_doctor())

    if args.command == 'sync':
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

    # analyze/ask/chat/learn/test/review 需要 target
    if not hasattr(args, 'target') or not args.target:
        parser.error('需要提供 <链接或文件路径>')

    with open(args.prompt_file, encoding='utf-8') as f:
        prompt = f.read()

    # 归档：--no-archive 跳过；否则 --archive 显式目录或 config.yaml 的 archive_dir
    if getattr(args, 'no_archive', False):
        archive_dir = None
    elif getattr(args, 'archive', None) is not None:
        archive_dir = args.archive
    else:
        archive_dir = cfg.get_archive_dir() or None
    archive_template = cfg.get_archive_template() or None
    skip_yt = args.no_yt_match or not cfg.get_yt_match()
    lang = args.lang

    try:
        if args.command in ('test', 'review'):
            fn = run_test if args.command == 'test' else run_review
            path = asyncio.run(fn(args.target, args.output, args.notebook,
                                  lang, skip_yt, _confirm_yt, None))
            print(f'\n完成：{path}')
            return
        if args.command == 'learn':
            if getattr(args, 'artifact', None):
                artifacts = [args.artifact]
                artifact_only = True
            else:
                artifacts = FULL_LEARN
                artifact_only = False
            path = asyncio.run(run(args.target, prompt, args.output,
                                   args.notebook, None, False,
                                   artifacts, lang, artifact_only,
                                   skip_yt, archive_dir, archive_template,
                                   _confirm_yt, None))
            print(f'\n完成：{path}')
            return
        if args.command == 'ask':
            path = asyncio.run(run(args.target, prompt, args.output,
                                   args.notebook, args.question, False,
                                   None, lang, False,
                                   skip_yt, archive_dir, archive_template,
                                   _confirm_yt, None))
        elif args.command == 'chat':
            path = asyncio.run(run(args.target, prompt, args.output,
                                   args.notebook, None, True,
                                   None, lang, False,
                                   skip_yt, archive_dir, archive_template,
                                   _confirm_yt, None))
        else:  # analyze
            artifacts = [] if getattr(args, 'no_learn', False) else None
            path = asyncio.run(run(args.target, prompt, args.output,
                                   args.notebook, None, False,
                                   artifacts, lang, False,
                                   skip_yt, archive_dir, archive_template,
                                   _confirm_yt, None))
        print(f'\n完成：{path}')
    except (ValueError, FileNotFoundError) as e:
        msg = str(e)
        if ('Authentication' in msg or 'Storage' in msg) and _relogin():
            # 重登录后重试一次
            if args.command == 'ask':
                path = asyncio.run(run(args.target, prompt, args.output,
                                       args.notebook, args.question, False,
                                       None, lang, False,
                                       skip_yt, archive_dir, archive_template,
                                       _confirm_yt, None))
            elif args.command == 'chat':
                path = asyncio.run(run(args.target, prompt, args.output,
                                       args.notebook, None, True,
                                       None, lang, False,
                                       skip_yt, archive_dir, archive_template,
                                       _confirm_yt, None))
            else:
                artifacts = [] if getattr(args, 'no_learn', False) else None
                path = asyncio.run(run(args.target, prompt, args.output,
                                       args.notebook, None, False,
                                       artifacts, lang, False,
                                       skip_yt, archive_dir, archive_template,
                                       _confirm_yt, None))
            print(f'\n完成：{path}')
            return
        raise


if __name__ == '__main__':
    main()
