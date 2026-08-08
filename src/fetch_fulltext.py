# -*- coding: utf-8 -*-
"""网页全文提取：Obsidian Web Clipper 同款路线（Readability 正文 + Turndown 转 MD）。

NotebookLM get_fulltext 对部分网页（如 1q43.blog）提取不完整（只有标题没正文）；
本模块用 Playwright(msedge) 抓取完整 HTML -> clipper/extract.js（同 Obsidian
Web Clipper 官方扩展的核心逻辑）提取正文转 Markdown，内容更完整、结构更易读。

失败（网页抓不到 / Readability 提取不到正文 / Node 依赖缺失）返回 None，
由调用方回退到 NotebookLM get_fulltext，不阻断主流程。
"""
import os
import subprocess
import tempfile

from src import config

BASE_DIR = config.BASE_DIR
EXTRACT_JS = os.path.join(BASE_DIR, 'clipper', 'extract.js')
GOTO_TIMEOUT = 45000
WAIT_MS = 2500


def _check_ready() -> bool:
    """Node 依赖是否可用（clipper/node_modules 存在 + extract.js 存在）。"""
    if not os.path.isfile(EXTRACT_JS):
        return False
    nm = os.path.join(BASE_DIR, 'clipper', 'node_modules')
    return os.path.isdir(nm)


async def _fetch_html(url: str) -> str | None:
    """Playwright(msedge) 抓取页面完整 HTML；失败返回 None。"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return None
    proxy = config.get('proxy') or None
    try:
        async with async_playwright() as p:
            kwargs = dict(channel='msedge', headless=True)
            if proxy:
                kwargs['proxy'] = {'server': proxy}
            browser = await p.chromium.launch(**kwargs)
            try:
                page = await browser.new_page()
                await page.goto(url, timeout=GOTO_TIMEOUT,
                                wait_until='domcontentloaded')
                await page.wait_for_timeout(WAIT_MS)  # 等 JS 渲染
                return await page.content()
            finally:
                await browser.close()
    except Exception:
        return None


def _extract_md(html: str) -> str | None:
    """Readability + Turndown 提取正文 Markdown；失败返回 None。"""
    with tempfile.NamedTemporaryFile('w', suffix='.html', delete=False,
                                     encoding='utf-8') as f:
        f.write(html)
        html_path = f.name
    out_path = html_path + '.md'
    try:
        r = subprocess.run(
            ['node', EXTRACT_JS, html_path, out_path],
            capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return None
        with open(out_path, encoding='utf-8') as f:
            md = f.read()
        return md if md.strip() else None
    except Exception:
        return None
    finally:
        for p in (html_path, out_path):
            try:
                os.unlink(p)
            except OSError:
                pass


async def fetch_clipper_fulltext(url: str) -> str | None:
    """网页 URL -> 完整 Markdown 全文；任何失败返回 None（回退 NotebookLM）。"""
    if not _check_ready():
        return None
    html = await _fetch_html(url)
    if not html:
        return None
    return _extract_md(html)
