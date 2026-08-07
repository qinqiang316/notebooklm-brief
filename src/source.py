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


def youtube_title(url: str) -> str | None:
    """YouTube 链接 -> 视频标题（yt-dlp，用于笔记本命名）。失败返回 None。"""
    try:
        r = subprocess.run(
            ['python', '-m', 'yt_dlp', '--get-title', '--no-playlist', url],
            capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None


# ---------- B站 -> YouTube 原片匹配（省去下载音频） ----------

YT_PROXY = 'http://127.0.0.1:10808'  # v2rayN 本地代理（访问 YouTube 必需）


def _norm_title(s: str) -> str:
    """标题规范化：小写、去括号内容（【】[]()）、去标点、去常见搬运/字幕前后缀。"""
    s = s.lower()
    s = re.sub(r'[【\[\(（][^】\]\)）]*[】\]\)）]', ' ', s)
    s = re.sub(r'\b(搬运|中英字幕|双语字幕|字幕|翻译|官方|完整版|完整|全集|熟肉|生肉|upload|转载|sub|cc|en)\b', ' ', s)
    s = re.sub(r'[^\w\u4e00-\u9fff]+', ' ', s)
    return ' '.join(s.split())


def _title_sim(a: str, b: str) -> float:
    """字符级 Jaccard 相似度 + 包含关系（任一命中即高置信）。"""
    na, nb = _norm_title(a), _norm_title(b)
    if not na or not nb:
        return 0.0
    if na in nb or nb in na:
        return 0.9
    sa, sb = set(na), set(nb)
    return len(sa & sb) / len(sa | sb)


def _duration_close(d1: float | None, d2: float | None) -> bool:
    """时长接近：±15% 或 ±60 秒（搬运视频可能剪辑，允许偏差）。"""
    if d1 is None or d2 is None or d1 <= 0:
        return True  # 无时长信息时不拦截（靠标题匹配兜底）
    return abs(d1 - d2) <= max(d1 * 0.15, 60)


def bilibili_meta(url: str) -> tuple[str | None, float | None]:
    """B站链接 -> (标题, 时长秒)。失败返回 (None, None)。"""
    try:
        r = subprocess.run(
            ['python', '-m', 'yt_dlp', '-J', '--no-playlist', url],
            capture_output=True, text=True, timeout=90)
        if r.returncode == 0 and r.stdout.strip():
            import json
            d = json.loads(r.stdout)
            return d.get('title'), d.get('duration')
    except Exception:
        pass
    return None, None


def youtube_match(query: str, duration: float | None = None,
                  proxy: str = YT_PROXY, max_results: int = 10) -> str | None:
    """在 YouTube 搜索与 B站视频相同的内容。命中返回 youtube 链接，否则 None。

    匹配条件（同时满足）：
      1) 标题规范化后相似（包含 / Jaccard > 0.55）
      2) 时长接近（±15% 或 ±60s）
    代理不可用/搜索失败一律返回 None（调用方回退下载音频，无副作用）。
    """
    try:
        cmd = ['python', '-m', 'yt_dlp', '-J', '--flat-playlist',
               '--proxy', proxy, f'ytsearch{max_results}:{query}']
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return None
        import json
        data = json.loads(r.stdout)
        entries = data.get('entries') or []
    except Exception:
        return None

    for e in entries:
        t = (e.get('title') or '').strip()
        d = e.get('duration')
        vid = e.get('id')
        if not t or not vid:
            continue
        if _title_sim(query, t) >= 0.55 and _duration_close(duration, d):
            return f'https://www.youtube.com/watch?v={vid}'
    return None


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
