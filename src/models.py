# -*- coding: utf-8 -*-
"""Source Identity（V3 Phase 1）：来源唯一身份、URL 规范化、metadata 读写。

设计原则：
- Notebook 名称 ≠ Notebook 身份。真正的关联关系是 source_id → notebook_id。
- 网络资源：canonical_url（规范化后的稳定 URL）-> SHA256 -> source_id
- 本地文件：文件内容 SHA256 -> source_id
- 每个笔记本目录保存 metadata.json，用于跨天/跨标题复用笔记本。
"""
import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# 常见跟踪参数（URL 参数变化不产生无意义重复）
TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'fbclid', 'gclid', 'gclsrc', 'dclid', 'spm', 'from', 'ref', 'refer',
    'referrer', 'source', 'si', 'feature', 'mc_cid', 'mc_eid', 'yclid',
    'igshid', 'soc_src', 'soc_trk',
}

# 仅身份识别用（不涉及 NotebookLM 抓取行为差异）
_YOUTUBE_HOSTS = ('youtube.com', 'www.youtube.com', 'm.youtube.com',
                  'music.youtube.com')
_BILIBILI_HOSTS = ('bilibili.com', 'www.bilibili.com')


@dataclass
class SourceRecord:
    """一个来源（链接/视频/文件）的唯一记录。"""
    source_id: str
    source_type: str            # url / youtube / bilibili / file / text（用户输入类型）
    original_url: str = ''      # 用户输入的原始链接（B站保留 bilibili 地址）
    canonical_url: str = ''     # 规范化后的稳定 URL（身份基础）
    title: str = ''             # 来源标题（NotebookLM 真实标题 / B站/YouTube 预取标题）
    duration: float | None = None
    local_path: str = ''        # 本地文件路径（B站音频等）
    created_at: str = ''
    updated_at: str = ''
    version: int = 0            # 生成内容版本（0=未设置，保存时规范化为实际版本并递增）
    notebook_id: str = ''       # 关联的云端笔记本 id
    notebook_title: str = ''    # 云端笔记本展示名（笔记-<标题>）


def canonicalize_url(url: str) -> str:
    """URL 规范化 -> 稳定 canonical URL（同一内容的不同 URL 形式映射到同一结果）。

    - YouTube：youtu.be / /shorts/ / 带 list/start 等参数 -> https://www.youtube.com/watch?v=<id>
    - B站：/video/BVxxx 保留 BV 号，去分P参数（同一视频不同分P视为同一来源）
    - 通用：去锚点、去跟踪参数（utm_*/fbclid 等）、query 参数排序
    """
    if not url:
        return ''
    url = url.strip()
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    if not parsed.scheme:
        return url

    netloc = parsed.netloc.lower()

    # YouTube 视频：各种形式统一为 watch?v=
    if netloc == 'youtu.be':
        vid = parsed.path.strip('/').split('/')[0]
        return f'https://www.youtube.com/watch?v={vid}' if vid else url
    if netloc in _YOUTUBE_HOSTS or netloc.endswith('.youtube.com'):
        if parsed.path in ('/watch', '/watch/'):
            q = dict(parse_qsl(parsed.query))
            v = q.get('v', '')
            return f'https://www.youtube.com/watch?v={v}' if v else url
        m = re.match(r'^/shorts/([0-9A-Za-z_-]{6,})', parsed.path)
        if m:
            return f'https://www.youtube.com/watch?v={m.group(1)}'

    # B站视频：保留 BV 号，去分P/跟踪参数
    if netloc in _BILIBILI_HOSTS:
        m = re.match(r'^/video/(BV[0-9A-Za-z]+)', parsed.path)
        if m:
            return f'https://www.bilibili.com/video/{m.group(1)}'

    # 通用：去锚点、去跟踪参数、query 排序（保持 path 稳定）
    query = parse_qsl(parsed.query, keep_blank_values=True)
    kept = sorted((k, v) for k, v in query if k.lower() not in TRACKING_PARAMS)
    qs = urlencode(kept)
    path = parsed.path or '/'
    return urlunparse((parsed.scheme.lower(), netloc, path, '', qs, ''))


def source_id_for_url(canonical_url: str) -> str:
    """网络资源 source_id：canonical_url -> SHA256 前 16 位。"""
    return hashlib.sha256(canonical_url.encode('utf-8')).hexdigest()[:16]


def source_id_for_file(path: str, chunk_size: int = 65536) -> str:
    """本地文件 source_id：文件内容 SHA256 前 16 位（分块读，支持大文件）。"""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()[:16]


def source_id_for_text(text: str) -> str:
    """直接文本输入 source_id：内容 SHA256 前 16 位。"""
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


# ---------- metadata.json 读写 ----------

def save_metadata(nb_dir: str, record: SourceRecord) -> str:
    """把 SourceRecord 写入 <nb_dir>/metadata.json，自动刷新 updated_at 并递增 version。返回路径。"""
    now = datetime.now().isoformat(timespec='seconds')
    if not record.created_at:
        record.created_at = now
    record.updated_at = now
    # 版本递增：同一 source 每次更新 version +1（执行计划 §11 第一版）
    # 旧数据（无 version 字段）读取后为默认 0，视为 v0，首次保存归一为 1
    old = load_metadata(nb_dir)
    if old is not None and old.source_id == record.source_id:
        record.version = (old.version or 0) + 1
    elif not record.version:
        record.version = 1
    path = os.path.join(nb_dir, 'metadata.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(asdict(record), f, ensure_ascii=False, indent=2)
    return path


def load_metadata(nb_dir: str) -> SourceRecord | None:
    """读取 <nb_dir>/metadata.json；不存在或损坏返回 None。"""
    path = os.path.join(nb_dir, 'metadata.json')
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        valid = {f.name for f in fields(SourceRecord)}
        return SourceRecord(**{k: v for k, v in data.items() if k in valid})
    except Exception:
        return None


def find_notebook_by_source_id(output_dir: str, source_id: str) -> tuple[str, SourceRecord] | None:
    """在 output/ 下按 source_id 找已有笔记本目录。返回 (目录路径, record)；未找到返回 None。"""
    if not os.path.isdir(output_dir):
        return None
    for d in sorted(os.listdir(output_dir)):
        p = os.path.join(output_dir, d)
        if not os.path.isdir(p):
            continue
        rec = load_metadata(p)
        if rec and rec.source_id == source_id:
            return p, rec
    return None
