# -*- coding: utf-8 -*-
"""资源路由测试（V3 Phase 3）：SourceInput / Router 决策。"""
import os

import pytest

from src.routing import SourceInput, resolve_input
from src.source import YouTubeCandidate


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """路由内所有网络操作都走 mock，测试不碰真实 yt-dlp。"""
    def fake_info(url):
        return {'title': '量子计算入门', 'duration': 600, 'uploader': '科学UP主'}

    def fake_download(url, workdir=None):
        f = os.path.join(os.path.dirname(url) if os.path.isdir(url) else os.getcwd(),
                         'bili_audio.mp3')
        return f, '量子计算入门'

    import src.routing as routing
    monkeypatch.setattr(routing, 'bilibili_info', fake_info)
    monkeypatch.setattr(routing, 'bilibili_to_audio', fake_download)


class TestResolveUrl:
    def test_article_url(self):
        s = resolve_input('https://example.com/article?id=1')
        assert s.type == 'url'
        assert s.original_type == 'url'
        assert s.source_id

    def test_youtube(self, monkeypatch):
        import src.source as src_source
        monkeypatch.setattr(src_source, 'youtube_title', lambda u: '视频标题')
        s = resolve_input('https://www.youtube.com/watch?v=abc123')
        assert s.type == 'youtube'
        assert s.title == '视频标题'
        assert 'watch?v=abc123' in s.canonical

    def test_file(self, tmp_path):
        f = tmp_path / 'doc.pdf'
        f.write_bytes(b'%PDF')
        s = resolve_input(str(f))
        assert s.type == 'file'
        assert s.local_path == str(f)

    def test_text(self):
        s = resolve_input('量子计算是什么')
        assert s.type == 'text'
        assert s.source_id


class TestResolveBilibili:
    def test_match_high_confidence_uses_youtube(self, monkeypatch):
        import src.routing as routing

        def fake_pick(query, duration, uploader, confirm_fn=None, **kw):
            cand = YouTubeCandidate('yt123', '量子计算入门', 600, '科学UP主', 0.95)
            return cand, 0.95

        monkeypatch.setattr(routing, 'pick_youtube_match', fake_pick)
        s = resolve_input('https://www.bilibili.com/video/BV1xx411c7mD')
        assert s.type == 'youtube'
        assert s.yt_match is not None
        assert s.yt_match[0].url == 'https://www.youtube.com/watch?v=yt123'
        # 身份仍基于 B站 canonical
        assert s.source_id == routing.source_id_for_url(
            'https://www.bilibili.com/video/BV1xx411c7mD')

    def test_match_rejected_downloads_audio(self, monkeypatch):
        import src.routing as routing

        def fake_pick(query, duration, uploader, confirm_fn=None, **kw):
            return None, 0.55  # 低置信

        monkeypatch.setattr(routing, 'pick_youtube_match', fake_pick)
        s = resolve_input('https://www.bilibili.com/video/BV1xx411c7mD')
        assert s.type == 'file'
        assert s.local_path
        assert s.title == '量子计算入门'

    def test_skip_yt_match_downloads_audio(self):
        s = resolve_input('https://www.bilibili.com/video/BV1xx411c7mD',
                          skip_yt_match=True)
        assert s.type == 'file'
        assert s.local_path
