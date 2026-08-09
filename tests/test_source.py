# -*- coding: utf-8 -*-
"""输入识别与 B站->YouTube 匹配纯函数测试。"""
from src.source import (_channel_sim, _duration_close, _norm_title, _title_sim,
                        YouTubeCandidate, classify, pick_youtube_match,
                        score_candidate)


class TestClassify:
    def test_article_url(self):
        assert classify('https://example.com/article') == 'url'

    def test_youtube_url(self):
        assert classify('https://www.youtube.com/watch?v=abc') == 'youtube'
        assert classify('https://youtu.be/abc') == 'youtube'

    def test_bilibili_url(self):
        assert classify('https://www.bilibili.com/video/BV1xx') == 'bilibili'
        assert classify('https://b23.tv/abc') == 'bilibili'

    def test_local_file(self, tmp_path):
        f = tmp_path / 'doc.pdf'
        f.write_bytes(b'%PDF')
        assert classify(str(f)) == 'file'

    def test_plain_text(self):
        assert classify('量子计算简介') == 'text'


class TestNormTitle:
    def test_lowercase_and_punct(self):
        assert _norm_title('Hello, World!') == 'hello world'

    def test_strips_bracket_content(self):
        assert _norm_title('【搬运】量子计算 介绍') == '量子计算 介绍'

    def test_strips_common_suffixes(self):
        assert _norm_title('量子计算简介 [中英字幕]') == '量子计算简介'
        assert _norm_title('超导磁浮技术 - 官方完整版') == '超导磁浮技术'


class TestTitleSim:
    def test_identical(self):
        assert _title_sim('量子计算', '量子计算') >= 0.9

    def test_containment(self):
        assert _title_sim('量子计算入门', '量子计算入门教程') >= 0.9

    def test_translation_variant(self):
        # 【搬运】等前缀被规范化去掉后应视为相同
        assert _title_sim('【搬运】超导磁浮技术解析', '超导磁浮技术解析') >= 0.9

    def test_unrelated(self):
        assert _title_sim('量子计算', '红烧肉做法') < 0.55

    def test_empty(self):
        assert _title_sim('', '量子计算') == 0.0


class TestDurationClose:
    def test_exact(self):
        assert _duration_close(3500, 3500)

    def test_within_15_percent(self):
        assert _duration_close(3500, 3500 * 1.1)

    def test_within_60_seconds(self):
        assert _duration_close(3500, 3540)

    def test_far_apart(self):
        assert not _duration_close(3500, 3500 * 2)

    def test_missing_duration_not_blocking(self):
        assert _duration_close(None, 100)
        assert _duration_close(100, None)


class TestChannelSim:
    def test_same(self):
        assert _channel_sim('科学UP主', '科学UP主') == 1.0

    def test_containment(self):
        assert _channel_sim('科学UP主', '科学UP主官方频道') == 1.0

    def test_different(self):
        assert _channel_sim('科学UP主', '美食家') == 0.0

    def test_missing(self):
        assert _channel_sim(None, '科学UP主') == 0.0


class TestScoreCandidate:
    def _cand(self, title, duration=None, channel=None):
        return YouTubeCandidate('vid1', title, duration, channel)

    def test_high_score_exact_match(self):
        c = self._cand('量子计算入门', 600, '科学UP主')
        s = score_candidate('量子计算入门', 600, '科学UP主', c)
        assert s >= 0.90

    def test_low_score_unrelated(self):
        c = self._cand('红烧肉做法', 600, '美食家')
        s = score_candidate('量子计算入门', 600, '科学UP主', c)
        assert s < 0.70

    def test_mid_score_related_but_differs(self):
        # 标题相近、时长偏差大、频道不同 -> 中等置信
        c = self._cand('量子计算入门教程', 3000, '其他频道')
        s = score_candidate('量子计算入门', 600, '科学UP主', c)
        assert 0.0 <= s < 0.90

    def test_weight_breakdown(self):
        # 标题完全一致（50%*1）但时长完全不符（25%*0）、频道不符（15%*0）、其他（10%*1）
        c = self._cand('量子计算入门', 100000, '完全无关频道')
        s = score_candidate('量子计算入门', 600, '科学UP主', c)
        assert s == round(0.5 * 1.0 + 0.25 * 0.0 + 0.15 * 0.0 + 0.1 * 1.0, 3)


class TestPickYouTubeMatch:
    def _fake_scored(self, cands):
        def fake(query, duration=None, uploader=None, proxy=None, max_results=10):
            for c in cands:
                if c.score == 0:
                    c.score = 0.9
            return sorted(cands, key=lambda c: c.score, reverse=True)
        return fake

    def test_high_confidence_auto(self, monkeypatch):
        import src.source as src
        cand = YouTubeCandidate('v1', '量子计算入门', 600, '科学UP主', 0.95)
        monkeypatch.setattr(src, 'youtube_match_scored', self._fake_scored([cand]))
        got, conf = pick_youtube_match('量子计算入门')
        assert got is cand
        assert conf == 0.95

    def test_mid_confidence_asks_user(self, monkeypatch):
        import src.source as src
        cand = YouTubeCandidate('v1', '量子计算入门教程', 660, '科学UP主', 0.78)
        monkeypatch.setattr(src, 'youtube_match_scored', self._fake_scored([cand]))
        confirmed = []
        got, conf = pick_youtube_match('量子计算入门', confirm_fn=lambda c, s: confirmed.append(s) or True)
        assert got is cand
        assert confirmed == [0.78]

    def test_mid_confidence_rejected_falls_back(self, monkeypatch):
        import src.source as src
        cand = YouTubeCandidate('v1', '量子计算入门教程', 660, '科学UP主', 0.78)
        monkeypatch.setattr(src, 'youtube_match_scored', self._fake_scored([cand]))
        got, conf = pick_youtube_match('量子计算入门', confirm_fn=lambda c, s: False)
        assert got is None
        assert conf == 0.78

    def test_low_confidence_falls_back(self, monkeypatch):
        import src.source as src
        cand = YouTubeCandidate('v1', '无关视频', 999, '无关频道', 0.4)
        monkeypatch.setattr(src, 'youtube_match_scored', self._fake_scored([cand]))
        got, conf = pick_youtube_match('量子计算入门')
        assert got is None
        assert conf == 0.4

    def test_no_candidates(self, monkeypatch):
        import src.source as src
        monkeypatch.setattr(src, 'youtube_match_scored', lambda *a, **k: [])
        got, conf = pick_youtube_match('量子计算入门')
        assert got is None and conf == 0.0
