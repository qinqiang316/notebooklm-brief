# -*- coding: utf-8 -*-
"""配置模块测试（config.yaml 读写与默认值）。"""
import pytest

import src.config as cfg


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    """把 CONFIG_PATH 指向临时目录并重置缓存。"""
    monkeypatch.setattr(cfg, 'CONFIG_PATH', str(tmp_path / 'config.yaml'))
    monkeypatch.setattr(cfg, '_loaded', None)
    yield
    monkeypatch.setattr(cfg, '_loaded', None)


class TestConfig:
    def test_defaults_when_missing(self):
        assert cfg.get_output_dir() == cfg.DEFAULTS['output_dir']
        assert cfg.get_archive_dir() == ''
        assert cfg.get_language() == 'zh_Hans'
        assert cfg.get_yt_match() is True

    def test_save_and_get(self):
        cfg.save({'archive_dir': 'D:/RAW', 'yt_match': False})
        assert cfg.get_archive_dir() == 'D:/RAW'
        assert cfg.get_yt_match() is False

    def test_save_merges_not_overwrites(self):
        cfg.save({'archive_dir': 'D:/RAW'})
        cfg.save({'language': 'en'})
        assert cfg.get_archive_dir() == 'D:/RAW'
        assert cfg.get_language() == 'en'

    def test_get_priority(self):
        # 配置值优先于默认值
        cfg.save({'proxy': 'http://x:1'})
        assert cfg.get('proxy') == 'http://x:1'
        # 显式 default 最后兜底
        assert cfg.get('不存在键', 'fallback') == 'fallback'

    def test_yt_proxy_falls_back_to_proxy(self):
        cfg.save({'proxy': 'http://127.0.0.1:10808'})
        assert cfg.get_yt_proxy() == 'http://127.0.0.1:10808'
        cfg.save({'yt_proxy': 'http://special:1'})
        assert cfg.get_yt_proxy() == 'http://special:1'
