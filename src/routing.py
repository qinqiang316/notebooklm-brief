# -*- coding: utf-8 -*-
"""资源路由（V3 Phase 3）：统一输入 -> SourceInput -> Router 决定处理路径。

设计目标：main.py 不直接承担资源类型判断和下载逻辑。
所有输入统一进入 resolve_input()，返回 SourceInput；Router 决定：
  网页     -> NotebookLM URL（Clipper 仅用于原文归档）
  YouTube  -> NotebookLM URL
  B站      -> YouTube 原片匹配（置信度机制）或下载音频
  文件     -> NotebookLM File
  文本     -> NotebookLM Text
"""
from dataclasses import dataclass, field

from .models import canonicalize_url, source_id_for_file, source_id_for_text, source_id_for_url
from .source import (bilibili_info, bilibili_to_audio, classify,
                     pick_youtube_match)


@dataclass
class SourceInput:
    """统一输入表示（V3 Phase 3.1）。"""
    type: str                       # 处理类型：url / youtube / file / text
    original: str                   # 用户原始输入（链接/路径/文本）
    original_type: str              # 输入类型：url / youtube / bilibili / file / text
    canonical: str = ''             # 规范化 URL（身份基础）
    source_id: str = ''             # 稳定唯一身份
    local_path: str | None = None   # 本地文件路径（B站音频等）
    title: str | None = None        # 预取标题（B站/YouTube）
    duration: float | None = None
    uploader: str | None = None
    yt_match: tuple | None = None   # B站命中 YouTube 原片 (candidate, confidence)


def resolve_input(target: str, skip_yt_match: bool = False,
                  confirm_fn=None) -> SourceInput:
    """识别输入类型并路由到可交付 NotebookLM 的 SourceInput。

    confirm_fn(candidate, score) -> bool：B站中等置信度（0.70~0.90）时
    是否采用候选（None 表示不确认 -> 回退下载音频）。
    """
    kind = classify(target)
    if kind in ('url', 'youtube'):
        canonical = canonicalize_url(target)
        src = SourceInput(type=kind, original=target, original_type=kind,
                          canonical=canonical, source_id=source_id_for_url(canonical or target))
        if kind == 'youtube':
            # 预取标题用于笔记本命名（失败不阻断）
            from .source import youtube_title
            src.title = youtube_title(target)
        return src

    if kind == 'bilibili':
        return _resolve_bilibili(target, skip_yt_match, confirm_fn)

    if kind == 'file':
        return SourceInput(type='file', original=target, original_type='file',
                           local_path=target, source_id=source_id_for_file(target))

    # text
    return SourceInput(type='text', original=target, original_type='text',
                       source_id=source_id_for_text(target))


def _resolve_bilibili(target: str, skip_yt_match: bool, confirm_fn) -> SourceInput:
    """B站路由：身份基于原始 bilibili canonical（BV 号，跨匹配成功/失败统一）。"""
    canonical = canonicalize_url(target)
    src = SourceInput(type='bilibili', original=target, original_type='bilibili',
                      canonical=canonical, source_id=source_id_for_url(canonical or target))
    if skip_yt_match:
        return _download_bilibili_audio(src)

    info = bilibili_info(target)
    src.title = info.get('title')
    src.duration = info.get('duration')
    src.uploader = info.get('uploader')
    if not src.title:
        return _download_bilibili_audio(src)

    cand, confidence = pick_youtube_match(src.title, src.duration,
                                          src.uploader, confirm_fn=confirm_fn)
    if cand:
        src.type = 'youtube'
        src.canonical = canonicalize_url(cand.url)
        src.yt_match = (cand, confidence)
        return src
    return _download_bilibili_audio(src)


def _download_bilibili_audio(src: SourceInput) -> SourceInput:
    """B站未匹配到原片 -> 下载音频，交 NotebookLM 转写。"""
    local_path, title = bilibili_to_audio(src.original)
    src.type = 'file'
    src.local_path = local_path
    if title:
        src.title = title
    return src
