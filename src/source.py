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


class YouTubeCandidate:
    """YouTube 候选视频（评分用）。"""

    def __init__(self, vid: str, title: str, duration: float = None,
                 channel: str = None, score: float = 0.0):
        self.id = vid
        self.title = title
        self.duration = duration
        self.channel = channel
        self.score = score

    @property
    def url(self) -> str:
        return f'https://www.youtube.com/watch?v={self.id}'

    def __repr__(self):
        return f'<YouTubeCandidate {self.id} {self.title!r} score={self.score}>'


# 英文 stopword（用 \b 词边界）与中文 stopword（中文无词边界，直接替换）
_EN_STOPWORDS = r'\b(upload|sub|cc|en|official)\b'
_ZH_STOPWORDS = ('搬运', '中英字幕', '双语字幕', '字幕', '翻译', '官方',
                 '完整版', '完整', '全集', '熟肉', '生肉', '转载')


def _norm_title(s: str) -> str:
    """标题规范化：小写、去括号内容（【】[]()）、去标点、去常见搬运/字幕前后缀。"""
    s = s.lower()
    s = re.sub(r'[【\[\]()（）][^】\[\]()（）]*[】\[\]()（）]', ' ', s)
    s = re.sub(_EN_STOPWORDS, ' ', s)
    for w in _ZH_STOPWORDS:
        s = s.replace(w, ' ')
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


def _channel_sim(a: str | None, b: str | None) -> float:
    """频道/作者匹配：规范化后包含或相同 -> 1.0；否则 0.0。缺信息返回 0.0。"""
    if not a or not b:
        return 0.0
    na = re.sub(r'[^\w\u4e00-\u9fff]+', '', a.lower())
    nb = re.sub(r'[^\w\u4e00-\u9fff]+', '', b.lower())
    if not na or not nb:
        return 0.0
    return 1.0 if (na in nb or nb in na or na == nb) else 0.0


def _duration_score(d1: float | None, d2: float | None) -> float:
    """时长评分：相差 ≤20% 线性给分；缺信息给中性 0.5。"""
    if d1 is None or d2 is None or d1 <= 0 or d2 <= 0:
        return 0.5
    ratio = abs(d1 - d2) / max(d1, d2)
    return max(0.0, 1.0 - ratio / 0.2)


def bilibili_meta(url: str) -> tuple[str | None, float | None]:
    """B站链接 -> (标题, 时长秒)。失败返回 (None, None)。（兼容旧接口）"""
    info = bilibili_info(url)
    return info.get('title'), info.get('duration')


def bilibili_info(url: str) -> dict:
    """B站链接 -> {title, duration, uploader}。失败返回空 dict。"""
    try:
        r = subprocess.run(
            ['python', '-m', 'yt_dlp', '-J', '--no-playlist', url],
            capture_output=True, text=True, timeout=90)
        if r.returncode == 0 and r.stdout.strip():
            import json
            d = json.loads(r.stdout)
            return {
                'title': d.get('title'),
                'duration': d.get('duration'),
                'uploader': d.get('uploader') or d.get('channel')
                            or d.get('creator') or d.get('artist'),
            }
    except Exception:
        pass
    return {}


def youtube_search(query: str, proxy: str = None, max_results: int = 10,
                   timeout: int = 60) -> list[YouTubeCandidate]:
    """在 YouTube 搜索候选视频，返回排序前候选列表（含频道/时长）。失败返回 []。"""
    if proxy is None:
        try:
            from .config import get_yt_proxy
            proxy = get_yt_proxy()
        except Exception:
            proxy = ''
    try:
        cmd = ['python', '-m', 'yt_dlp', '-J', '--flat-playlist']
        if proxy:
            cmd += ['--proxy', proxy]
        cmd.append(f'ytsearch{max_results}:{query}')
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            return []
        import json
        data = json.loads(r.stdout)
        entries = data.get('entries') or []
    except Exception:
        return []
    cands = []
    for e in entries:
        t = (e.get('title') or '').strip()
        vid = e.get('id')
        if not t or not vid:
            continue
        cands.append(YouTubeCandidate(
            vid, t,
            duration=e.get('duration'),
            channel=e.get('channel') or e.get('uploader'),
        ))
    return cands


def score_candidate(query: str, duration: float | None,
                    uploader: str | None, cand: YouTubeCandidate) -> float:
    """候选综合评分（0~1）：标题 50% + 时长 25% + 频道 15% + 其他 10%。"""
    title_score = min(_title_sim(query, cand.title) / 0.9, 1.0)
    dur_score = _duration_score(duration, cand.duration)
    chan_score = _channel_sim(uploader, cand.channel) if (uploader and cand.channel) else 0.5
    other = 1.0 if (query and cand.title) else 0.0
    score = title_score * 0.5 + dur_score * 0.25 + chan_score * 0.15 + other * 0.1
    return round(score, 3)


def youtube_match_scored(query: str, duration: float | None = None,
                         uploader: str | None = None,
                         proxy: str = None, max_results: int = 10) -> list[YouTubeCandidate]:
    """搜索并按综合评分排序候选，返回列表（高分在前）。失败返回 []。"""
    cands = youtube_search(query, proxy, max_results)
    for c in cands:
        c.score = score_candidate(query, duration, uploader, c)
    cands.sort(key=lambda c: c.score, reverse=True)
    return cands


def pick_youtube_match(query: str, duration: float | None = None,
                       uploader: str | None = None, proxy: str = None,
                       confirm_fn=None, max_results: int = 10
                       ) -> tuple[YouTubeCandidate | None, float]:
    """B站->YouTube 匹配决策（V3 置信度机制）。

    策略：
      - 置信度 ≥ 0.90：自动采用
      - 0.70 ~ 0.90：调用 confirm_fn(candidate, score) 用户确认（返回 True 采用）
      - < 0.70：不采用，回退 B站原视频（下载音频）

    返回 (候选, 置信度)；未命中/未采用返回 (None, 0.0)。
    """
    cands = youtube_match_scored(query, duration, uploader, proxy, max_results)
    if not cands:
        return None, 0.0
    top = cands[0]
    if top.score >= 0.90:
        return top, top.score
    if top.score >= 0.70:
        if confirm_fn is not None and confirm_fn(top, top.score):
            return top, top.score
        return None, top.score  # 用户未确认 -> 回退
    return None, top.score


def youtube_match(query: str, duration: float | None = None,
                  proxy: str = None, max_results: int = 10) -> str | None:
    """兼容旧接口：仅在高置信（≥0.90）自动采用时返回 youtube 链接，否则 None。
    V3 起推荐使用 pick_youtube_match（支持中等置信度确认）。"""
    cand, score = pick_youtube_match(query, duration, None, proxy,
                                     confirm_fn=lambda c, s: False,
                                     max_results=max_results)
    if cand and score >= 0.90:
        return cand.url
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


# ---------- SourceManager（V3 Phase 2）：NotebookLM 来源操作 ----------


class SourceManager:
    """Notebook 内来源管理：添加/等待/列出/获取/全文提取。"""

    def __init__(self, nlm):
        self._nlm = nlm

    async def add(self, target: str, kind: str, local_path: str = None,
                  notebook_name: str = None) -> tuple[str, str]:
        """添加来源并等待处理就绪。返回 (source_id, 标题)。"""
        nb_id = await self._nlm.notebooks._ensure_notebook_id(name=notebook_name)
        if kind in ('url', 'youtube'):
            # NotebookLM 的 URL 来源自动识别网页与 YouTube（自动转写）
            src = await self._nlm.notebooks.client.sources.add_url(nb_id, target)
        elif kind == 'file':
            src = await self._nlm.notebooks.client.sources.add_file(nb_id, local_path)
        elif kind == 'text':
            src = await self._nlm.notebooks.client.sources.add_text(nb_id, '粘贴文本', target)
        else:
            raise ValueError(f'未知来源类型: {kind}')

        # 等待来源处理完成（NotebookLM 抓取/转写）
        try:
            await self._nlm.notebooks.client.sources.wait_until_ready(nb_id, src.id, timeout=180)
        except Exception as e:
            print(f'      (来源处理等待：{type(e).__name__})')

        # 获取来源标题（NotebookLM 抓取的真实标题）
        title = None
        try:
            s = await self._nlm.notebooks.client.sources.get(nb_id, src.id)
            title = getattr(s, 'title', None) or None
        except Exception:
            pass
        return src.id, title

    async def list(self, notebook_name: str = None) -> list[tuple[str, str]]:
        """返回笔记本内所有来源 (source_id, title)。追问时复用，不重复添加。"""
        nb_id = await self._nlm.notebooks._ensure_notebook_id(name=notebook_name)
        sources = await self._nlm.notebooks.client.sources.list(nb_id)
        return [(s.id, getattr(s, 'title', '') or '') for s in sources]

    async def get_fulltext(self, source_id: str,
                           output_format: str = 'markdown',
                           notebook_name: str = None) -> str | None:
        """提取来源原文/转写全文（文章全文、YouTube/B站音频转写文本）。
        返回文本内容；失败返回 None（不阻断主流程）。
        markdown 格式需要 markdownify 包，缺失时自动回退 text。"""
        nb_id = await self._nlm.notebooks._ensure_notebook_id(name=notebook_name)
        client = self._nlm.notebooks.client
        for fmt in (output_format, 'text'):
            try:
                ft = await client.sources.get_fulltext(nb_id, source_id, output_format=fmt)
                content = getattr(ft, 'content', None)
                if content:
                    return content
            except ImportError:
                # markdown 格式缺依赖 -> 回退 text
                if fmt == 'text':
                    print('      (原文提取：markdown 依赖缺失，已回退纯文本)')
            except Exception as e:
                if fmt == 'text':
                    print(f'      (原文提取失败：{type(e).__name__})')
        return None
