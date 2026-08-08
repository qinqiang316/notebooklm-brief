# -*- coding: utf-8 -*-
"""首次使用引导（--setup）与环境自检（--doctor）。

可迁移性目标：新机器上跑一次 `python main.py --setup` 即可完成
依赖检查、NotebookLM 登录、目录创建、config.yaml 生成。
"""
import importlib
import os
import shutil
import subprocess
import sys

from . import config as cfg

# 必需依赖 -> 导入名
REQUIRED_DEPS = {
    'notebooklm': 'notebooklm',
    'yt_dlp': 'yt_dlp',
    'yaml': 'yaml',
    'markdownify': 'markdownify',
    'playwright': 'playwright',
}

# 可选依赖（缺失提示但不阻断）
OPTIONAL_DEPS = {}


def _py() -> str:
    return sys.executable


def _check_deps() -> dict[str, bool]:
    """检查必需依赖，返回 {包名: 是否可用}。"""
    result = {}
    for name, import_name in REQUIRED_DEPS.items():
        try:
            importlib.import_module(import_name)
            result[name] = True
        except ImportError:
            result[name] = False
    return result


def _check_login() -> tuple[bool, str]:
    """检查 NotebookLM 登录态文件。返回 (是否已登录, 说明)。"""
    home = os.path.expanduser('~')
    storage = os.path.join(home, '.notebooklm', 'profiles', 'default',
                           'storage_state.json')
    if os.path.isfile(storage):
        return True, storage
    return False, storage


def _check_dirs() -> dict[str, bool]:
    """检查关键目录。返回 {说明: 是否存在}。"""
    output_dir = cfg.get_output_dir()
    archive_dir = cfg.get_archive_dir()
    template_path = cfg.get_archive_template()
    result = {
        f'output 目录（{output_dir}）': os.path.isdir(output_dir),
    }
    if archive_dir:
        result[f'归档目录（{archive_dir}）'] = os.path.isdir(archive_dir)
    if template_path:
        result[f'归档模板（{template_path}）'] = os.path.isfile(template_path)
    return result


def _check_proxy() -> tuple[bool, str]:
    """检查代理是否可达（config 的 proxy）。"""
    proxy = cfg.get_proxy()
    if not proxy:
        return True, '未配置代理（访问 Google 可能失败）'
    try:
        import urllib.request
        opener = urllib.request.build_opener(urllib.request.ProxyHandler(
            {'http': proxy, 'https': proxy}))
        opener.open('https://www.google.com', timeout=8)
        return True, f'代理 {proxy} 可达'
    except Exception as e:
        return False, f'代理 {proxy} 不可达（{type(e).__name__}）'


def _check_clipper() -> tuple[bool, str]:
    """检查 Obsidian Clipper 路线（网页全文提取）是否可用。"""
    node = shutil.which('node')
    if not node:
        return False, '未安装 Node.js（网页原文提取将回退 NotebookLM）'
    nm = os.path.join(cfg.BASE_DIR, 'clipper', 'node_modules')
    js = os.path.join(cfg.BASE_DIR, 'clipper', 'extract.js')
    if not os.path.isdir(nm) or not os.path.isfile(js):
        return False, 'clipper 依赖缺失（cd clipper && npm install）'
    return True, '可用（Readability+Turndown 网页原文提取）'


def _print_table(items: list[tuple[str, str, bool]]):
    """打印检查结果表：[(项, 说明, 是否OK)]。"""
    for name, detail, ok in items:
        mark = '✓' if ok else '✗'
        print(f'  {mark} {name}：{detail}')


def run_doctor() -> int:
    """环境自检。返回退出码（0=全部通过，1=有失败）。"""
    print('=' * 50)
    print('notebooklm-brief 环境自检（--doctor）')
    print('=' * 50)

    # 1. 配置
    print('\n[1] 配置')
    cfg_path = cfg.CONFIG_PATH
    if os.path.isfile(cfg_path):
        print(f'  ✓ config.yaml：{cfg_path}')
    else:
        print(f'  ✗ config.yaml 不存在：{cfg_path}')
        print('    运行 `python main.py --setup` 生成')
    print(f'  · 输出目录：{cfg.get_output_dir()}')
    archive = cfg.get_archive_dir()
    print(f'  · 归档目录：{archive or "（未配置）"}')
    tpl = cfg.get_archive_template()
    print(f'  · 归档模板：{tpl or "（未配置，直接复制合并笔记）"}')
    print(f'  · 语言：{cfg.get_language()}')
    print(f'  · 代理：{cfg.get_proxy()}')

    # 2. 依赖
    print('\n[2] 依赖')
    deps = _check_deps()
    missing = [k for k, v in deps.items() if not v]
    _print_table([(k, '已安装' if v else '缺失', v) for k, v in deps.items()])
    if missing:
        print(f'  缺失依赖：{", ".join(missing)}')
        print(f'  安装：{_py()} -m pip install "notebooklm-py[browser]" yt-dlp pyyaml markdownify')

    # 3. 登录态
    print('\n[3] NotebookLM 登录态')
    ok_login, login_path = _check_login()
    print(f'  {"✓" if ok_login else "✗"} 登录文件：{login_path}')
    if not ok_login:
        print('  登录：python -m notebooklm login --browser msedge')

    # 4. 目录
    print('\n[4] 目录')
    dirs = _check_dirs()
    _print_table([(k, '存在' if v else '不存在（运行 --setup 创建）', v)
                  for k, v in dirs.items()])

    # 5. 代理
    print('\n[5] 代理')
    ok_proxy, proxy_detail = _check_proxy()
    print(f'  {"✓" if ok_proxy else "✗"} {proxy_detail}')

    # 6. Clipper 路线（网页原文提取）
    print('\n[6] Obsidian Clipper 网页原文提取')
    ok_clipper, clipper_detail = _check_clipper()
    print(f'  {"✓" if ok_clipper else "✗"} {clipper_detail}')

    # 汇总
    failed = (not os.path.isfile(cfg.CONFIG_PATH)) or bool(missing) \
        or not ok_login or any(not v for v in dirs.values()) or not ok_proxy \
        or not ok_clipper
    print('\n' + '=' * 50)
    if failed:
        print('自检发现待处理项（见上方 ✗），可运行 `python main.py --setup` 引导修复')
        return 1
    print('自检全部通过 ✓')
    return 0


def _ask(question: str, default: str = '') -> str:
    """交互式提问，返回输入（空串时返回 default）。"""
    suffix = f' [{default}]' if default else ''
    try:
        val = input(f'  ? {question}{suffix}：').strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return val or default


def run_setup() -> int:
    """首次使用引导。返回退出码。"""
    print('=' * 50)
    print('notebooklm-brief 首次使用引导（--setup）')
    print('=' * 50)
    print('本项目把任意链接/视频/文件交给 Google NotebookLM 生成')
    print('结构化分析，并本地归档。首次使用需要：')
    print('  1) Python 3.11+ 与依赖包')
    print('  2) 一个 Google 账号（NotebookLM 登录）')
    print('  3) 归档目录（可选，不配则跳过归档）')
    print('  4) 访问 Google 的代理（可选，不配则直连）')
    print()

    # 1. 依赖
    print('[1/4] 依赖检查')
    deps = _check_deps()
    missing = [k for k, v in deps.items() if not v]
    if missing:
        print(f'  缺失：{", ".join(missing)}')
        print(f'  正在安装...')
        r = subprocess.run(
            [_py(), '-m', 'pip', 'install', '--proxy', '',
             '-i', 'https://mirrors.aliyun.com/pypi/simple/',
             'notebooklm-py[browser]', 'yt-dlp', 'pyyaml', 'markdownify'],
            capture_output=True, text=True)
        if r.returncode != 0:
            print(f'  安装失败：{r.stderr[-300:]}')
            print('  请手动执行：')
            print(f'    {_py()} -m pip install "notebooklm-py[browser]" yt-dlp pyyaml markdownify')
            return 1
        print('  安装完成 ✓')
    else:
        print('  依赖齐全 ✓')

    # Clipper 路线（网页全文提取，可选增强）
    ok_clipper, clipper_detail = _check_clipper()
    if not ok_clipper:
        print(f'  · Obsidian Clipper 网页原文提取：{clipper_detail}')
        if shutil.which('node'):
            print('  正在安装 clipper 依赖（npm install）...')
            r = subprocess.run(
                ['npm', 'install'], cwd=os.path.join(cfg.BASE_DIR, 'clipper'),
                capture_output=True, text=True, timeout=300)
            if r.returncode == 0:
                print('  clipper 依赖安装完成 ✓')
            else:
                print(f'  安装失败：{r.stderr[-300:]}')
                print('  可手动执行：cd clipper && npm install')
        else:
            print('  需安装 Node.js（https://nodejs.org），否则网页原文提取回退 NotebookLM')

    # 2. 登录
    print('\n[2/4] NotebookLM 登录')
    ok_login, login_path = _check_login()
    if ok_login:
        print(f'  已检测到登录态：{login_path}')
    else:
        print('  未检测到登录态，正在打开浏览器登录...')
        r = subprocess.run(
            [_py(), '-m', 'notebooklm', 'login', '--browser', 'msedge'],
            capture_output=True, text=True, timeout=300)
        out = (r.stdout or '') + (r.stderr or '')
        print('  ' + out.strip()[:500])
        if r.returncode != 0 or 'saved' not in out.lower():
            print('  登录未完成。请手动执行：')
            print(f'    {_py()} -m notebooklm login --browser msedge')
            print('  登录后重新运行 --setup 或直接使用。')

    # 3. 配置（归档目录等）
    print('\n[3/4] 配置文件 config.yaml')
    archive_default = cfg.get_archive_dir()
    archive = _ask('归档目录（合并笔记归档到本地 Obsidian 库，如 RAW；留空跳过归档）',
                   archive_default or '')
    tpl_default = cfg.get_archive_template()
    tpl = _ask('归档模板 .md 路径（frontmatter 模板，留空 = 直接复制合并笔记）',
               tpl_default or '')
    output_default = cfg.get_output_dir()
    output = _ask('输出目录', output_default)
    proxy_default = cfg.get_proxy()
    proxy = _ask('Google 代理地址（留空直连）', proxy_default)
    email_default = cfg.get('account_email', '')
    email = _ask('Google 账号邮箱（提示用，可留空）', email_default)
    cfg.save({
        'archive_dir': archive,
        'archive_template': tpl,
        'output_dir': output,
        'proxy': proxy,
        'account_email': email,
        'language': cfg.get_language(),
        'yt_match': cfg.get_yt_match(),
    })
    print(f'  已写入：{cfg.CONFIG_PATH}')

    # 4. 目录
    print('\n[4/4] 目录创建')
    os.makedirs(cfg.get_output_dir(), exist_ok=True)
    print(f'  ✓ 输出目录：{cfg.get_output_dir()}')
    if cfg.get_archive_dir():
        os.makedirs(cfg.get_archive_dir(), exist_ok=True)
        print(f'  ✓ 归档目录：{cfg.get_archive_dir()}')
    else:
        print(f'  · 归档目录未配置（后续可改 config.yaml 的 archive_dir）')

    print('\n' + '=' * 50)
    print('引导完成！开始使用：')
    print(f'  {_py()} main.py "https://example.com/article"')
    print(f'  {_py()} main.py --doctor    # 随时自检环境')
    print(f'  配置在 {cfg.CONFIG_PATH}，迁移机器时复制该文件即可')
    print('=' * 50)
    return 0
