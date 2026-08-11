# -*- coding: utf-8 -*-
"""main.run() 集成测试：MockNotebookLMProvider，验证 Source Identity + 三层资产。

覆盖（V3 验收）：
- 首次运行：新建笔记本 + metadata.json + source/ + generated/ + knowledge/
- 相同来源（URL 参数变化）：复用已有笔记本
- 不同来源（相同标题）：独立笔记本不串
- B站身份：基于原始 bilibili canonical
"""
import asyncio
import os

import pytest

from src.models import load_metadata, source_id_for_file, source_id_for_url
from src.output import generated_dir
from src.provider import MockNotebookLMProvider

from main import run


@pytest.fixture(autouse=True)
def _reset_mock_shared():
    MockNotebookLMProvider._shared = None
    yield
    MockNotebookLMProvider._shared = None


def _notebook_dirs(out):
    return sorted(d for d in os.listdir(out)
                  if os.path.isdir(os.path.join(out, d)) and d.startswith('笔记-'))


def _run(target, out, **kw):
    return asyncio.run(run(target, '分析模板内容', str(out), None,
                           artifacts=[], archive_dir=None,
                           provider=MockNotebookLMProvider(share_state=True),
                           **kw))


class TestRunSourceIdentity:
    def test_first_run_creates_three_layers(self, tmp_path):
        src = tmp_path / '报告.pdf'
        src.write_bytes(b'%PDF-1.4 fake')
        out = tmp_path / 'output'

        _run(str(src), out)

        dirs = _notebook_dirs(out)
        assert len(dirs) == 1
        nb = str(out / dirs[0])
        rec = load_metadata(nb)
        assert rec is not None
        assert rec.source_id == source_id_for_file(str(src))
        assert rec.source_type == 'file'
        assert rec.notebook_id          # 已关联云端笔记本 id
        # 三层结构
        assert os.path.isfile(os.path.join(nb, 'source', 'source.md'))
        assert os.path.isfile(os.path.join(nb, 'generated', 'analysis.md'))
        assert os.path.isfile(os.path.join(nb, 'generated', 'conversation.md'))
        assert os.path.isfile(os.path.join(nb, '归档笔记.md'))
        assert os.path.isfile(os.path.join(nb, 'knowledge', 'README.md'))

    def test_same_source_reuses_notebook(self, tmp_path):
        out = tmp_path / 'output'
        _run('https://example.com/article?id=42', out)
        assert len(_notebook_dirs(out)) == 1

        # 相同内容、不同跟踪参数：应复用同一笔记本
        _run('https://example.com/article?id=42&utm_source=twitter', out)
        dirs = _notebook_dirs(out)
        assert len(dirs) == 1

    def test_same_source_reuses_even_title_changed(self, tmp_path):
        out = tmp_path / 'output'
        _run('https://example.com/stable/path', out)
        before = _notebook_dirs(out)
        assert len(before) == 1

        _run('https://example.com/stable/path', out)
        after = _notebook_dirs(out)
        assert after == before
        rec = load_metadata(str(out / after[0]))
        assert rec.source_id == source_id_for_url('https://example.com/stable/path')

    def test_different_sources_same_title_no_conflict(self, tmp_path):
        out = tmp_path / 'output'
        a = tmp_path / '同名.pdf'
        b = tmp_path / '同名.txt'
        a.write_bytes(b'AAA')
        b.write_bytes(b'BBB')

        _run(str(a), out)
        _run(str(b), out)

        dirs = _notebook_dirs(out)
        assert len(dirs) == 2   # 同名文件不同内容：两个独立笔记本
        sids = {load_metadata(str(out / d)).source_id for d in dirs}
        assert sids == {source_id_for_file(str(a)), source_id_for_file(str(b))}

    def test_bilibili_identity_uses_original_url(self, tmp_path, monkeypatch):
        """B站：source_id 基于原始 bilibili canonical（BV 号）。"""
        out = tmp_path / 'output'

        def fake_download(url, workdir=None):
            f = tmp_path / 'bili_audio.mp3'
            f.write_bytes(b'fake audio')
            return str(f), 'B站视频标题'

        import src.routing as routing
        monkeypatch.setattr(routing, 'bilibili_to_audio', fake_download)
        _run('https://www.bilibili.com/video/BV1xx411c7mD?p=1', out,
             skip_yt_match=True)
        dirs = _notebook_dirs(out)
        assert len(dirs) == 1
        rec = load_metadata(str(out / dirs[0]))
        assert rec.source_id == source_id_for_url(
            'https://www.bilibili.com/video/BV1xx411c7mD')
        assert rec.source_type == 'bilibili'

    def test_ask_appends_analysis(self, tmp_path):
        out = tmp_path / 'output'
        _run('https://example.com/article', out)
        before = open(os.path.join(generated_dir(str(out / _notebook_dirs(out)[0])),
                                   'analysis.md'), encoding='utf-8').read()

        _run('https://example.com/article', out, ask='追问问题')
        after = open(os.path.join(generated_dir(str(out / _notebook_dirs(out)[0])),
                                  'analysis.md'), encoding='utf-8').read()
        assert len(after) > len(before)
        assert '追问' in after
