# -*- coding: utf-8 -*-
"""Source Identity 测试：canonical_url / source_id / metadata 读写（V3 Phase 1）。"""
import json

import pytest

from src.models import (SourceRecord, canonicalize_url, source_id_for_file,
                        source_id_for_text, source_id_for_url,
                        find_notebook_by_source_id, load_metadata, save_metadata)


# ---------- canonicalize_url ----------

class TestCanonicalizeUrl:
    def test_youtube_watch_drops_tracking_params(self):
        url = 'https://www.youtube.com/watch?v=abc123&list=PLxxx&t=123&si=abc'
        assert canonicalize_url(url) == 'https://www.youtube.com/watch?v=abc123'

    def test_youtu_be_short_link(self):
        assert canonicalize_url('https://youtu.be/abc123') == \
            'https://www.youtube.com/watch?v=abc123'

    def test_youtube_shorts(self):
        assert canonicalize_url('https://www.youtube.com/shorts/abc123') == \
            'https://www.youtube.com/watch?v=abc123'

    def test_youtube_mobile_host(self):
        assert canonicalize_url('https://m.youtube.com/watch?v=abc123') == \
            'https://www.youtube.com/watch?v=abc123'

    def test_bilibili_keeps_bvid_drops_page(self):
        url = 'https://www.bilibili.com/video/BV1xx411c7mD?p=2&spm_id_from=333.999'
        assert canonicalize_url(url) == 'https://www.bilibili.com/video/BV1xx411c7mD'

    def test_generic_drops_utm_and_sorts_query(self):
        a = 'https://example.com/article?utm_source=twitter&id=42'
        b = 'https://example.com/article?id=42&utm_source=twitter'
        assert canonicalize_url(a) == canonicalize_url(b) == \
            'https://example.com/article?id=42'

    def test_generic_drops_fragment(self):
        assert canonicalize_url('https://example.com/page#section') == \
            'https://example.com/page'

    def test_host_lowercased(self):
        assert canonicalize_url('https://EXAMPLE.com/Page') == \
            'https://example.com/Page'

    def test_empty_input(self):
        assert canonicalize_url('') == ''


# ---------- source_id ----------

class TestSourceId:
    def test_url_id_stable(self):
        assert source_id_for_url('https://example.com/a') == \
            source_id_for_url('https://example.com/a')

    def test_url_id_differs_for_diff_urls(self):
        assert source_id_for_url('https://example.com/a') != \
            source_id_for_url('https://example.com/b')

    def test_url_id_length(self):
        assert len(source_id_for_url('https://example.com/a')) == 16

    def test_canonical_forms_same_id(self):
        a = source_id_for_url(canonicalize_url('https://youtu.be/abc123'))
        b = source_id_for_url(canonicalize_url(
            'https://www.youtube.com/watch?v=abc123&list=PLx'))
        assert a == b

    def test_file_id_stable_and_content_sensitive(self, tmp_path):
        f = tmp_path / 'doc.pdf'
        f.write_bytes(b'hello world')
        id1 = source_id_for_file(str(f))
        assert id1 == source_id_for_file(str(f))
        f.write_bytes(b'hello world changed')
        assert source_id_for_file(str(f)) != id1

    def test_file_id_length(self, tmp_path):
        f = tmp_path / 'doc.txt'
        f.write_text('内容', encoding='utf-8')
        assert len(source_id_for_file(str(f))) == 16

    def test_text_id(self):
        assert source_id_for_text('粘贴内容') == source_id_for_text('粘贴内容')
        assert source_id_for_text('粘贴内容') != source_id_for_text('其他内容')


# ---------- metadata ----------

class TestMetadata:
    def _record(self, **over):
        data = dict(source_id='a' * 16, source_type='url', original_url='https://x',
                    canonical_url='https://x', title='标题', notebook_title='笔记-标题')
        data.update(over)
        return SourceRecord(**data)

    def test_save_load_roundtrip(self, tmp_path):
        rec = self._record()
        path = save_metadata(str(tmp_path), rec)
        assert path.endswith('metadata.json')
        loaded = load_metadata(str(tmp_path))
        assert loaded is not None
        assert loaded.source_id == rec.source_id
        assert loaded.source_type == 'url'
        assert loaded.notebook_title == '笔记-标题'
        assert loaded.updated_at  # 自动填充

    def test_load_missing_returns_none(self, tmp_path):
        assert load_metadata(str(tmp_path)) is None

    def test_load_corrupt_returns_none(self, tmp_path):
        (tmp_path / 'metadata.json').write_text('not json', encoding='utf-8')
        assert load_metadata(str(tmp_path)) is None

    def test_created_at_preserved_across_saves(self, tmp_path):
        rec = self._record()
        save_metadata(str(tmp_path), rec)
        created = rec.created_at
        rec.title = '新标题'
        save_metadata(str(tmp_path), rec)
        assert rec.created_at == created
        assert load_metadata(str(tmp_path)).title == '新标题'

    def test_version_increments(self, tmp_path):
        rec = self._record()
        save_metadata(str(tmp_path), rec)
        assert load_metadata(str(tmp_path)).version == 1
        save_metadata(str(tmp_path), rec)
        assert load_metadata(str(tmp_path)).version == 2
        # 不同 source 不继承旧版本
        other = self._record(source_id='b' * 16, title='B')
        save_metadata(str(tmp_path), other)
        assert load_metadata(str(tmp_path)).version == 1

    def test_find_by_source_id(self, tmp_path):
        out = tmp_path / 'output'
        nb1 = out / '笔记-A'
        nb2 = out / '笔记-B'
        nb1.mkdir(parents=True)
        nb2.mkdir(parents=True)
        save_metadata(str(nb1), self._record(source_id='1' * 16, title='A'))
        save_metadata(str(nb2), self._record(source_id='2' * 16, title='B'))
        hit = find_notebook_by_source_id(str(out), '2' * 16)
        assert hit is not None
        assert hit[0] == str(nb2)
        assert hit[1].title == 'B'

    def test_find_by_source_id_missing(self, tmp_path):
        out = tmp_path / 'output'
        out.mkdir()
        assert find_notebook_by_source_id(str(out), 'x' * 16) is None

    def test_find_skips_non_metadata_dirs(self, tmp_path):
        out = tmp_path / 'output'
        (out / '其他目录').mkdir(parents=True)
        assert find_notebook_by_source_id(str(out), 'x' * 16) is None
