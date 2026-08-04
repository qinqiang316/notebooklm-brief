# -*- coding: utf-8 -*-
"""来源预处理：识别输入类型并准备 NotebookLM 可接收的来源。"""
import os
import re
import subprocess
import tempfile


def classify(target: str) -> str:
    """判断输入类型：url / youtube / bilibili / file / text"""
    if re.match(r'^https?://', target, re.I):
        if 'youtube.com' in target or 'youtu.be' in target:
            return 'youtube'
        if 'bilibili.com' in target or 'b23.tv' in target:
            return 'bilibili'
        return 'url'
    if os.path.isfile(target):
        return 'file'
    return 'text'


def bilibili_to_audio(url: str, workdir: str = None) -> tuple[str, str]:
    """B站视频链接 -> 下载音频文件（NotebookLM 不认 bilibili 链接，需转音频上传）。
    依赖 yt-dlp。返回 (本地音频文件路径, 视频标题)。"""
    tmp = workdir or tempfile.gettempdir()
    # 先拿视频真实标题（用于输出命名）
    title = None
    try:
        tc = ['python', '-m', 'yt_dlp', '--get-title', '--no-playlist', url]
        tr = subprocess.run(tc, capture_output=True, text=True, timeout=60)
        if tr.returncode == 0 and tr.stdout.strip():
            title = tr.stdout.strip()
    except Exception:
        pass

    cmd = ['python', '-m', 'yt_dlp', '-f', 'ba/b', '--no-playlist',
           '-o', os.path.join(tmp, 'bili_%(id)s.%(ext)s'), url]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise RuntimeError(f'B站音频下载失败: {r.stderr[-500:]}')
    m = re.search(r'Destination: (.+\.\w+)', r.stdout)
    if not m:
        # 已下载过的情况：yt-dlp 输出 "[download] <path> has already been downloaded"
        m = re.search(r'\[download\] (.+\.\w+) has already been downloaded', r.stdout)
    if not m:
        raise RuntimeError(f'B站音频下载完成但未找到文件: {r.stdout[-300:]}')
    path = m.group(1).strip()
    if not os.path.isfile(path):
        raise RuntimeError(f'B站音频文件不存在: {path}')
    return path, title
