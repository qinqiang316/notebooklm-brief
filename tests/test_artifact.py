# -*- coding: utf-8 -*-
"""Artifact 语言规范化测试。"""
from src.artifact import normalize_lang


class TestNormalizeLang:
    def test_default(self):
        assert normalize_lang('') == 'zh_Hans'
        assert normalize_lang(None) == 'zh_Hans'

    def test_zh_aliases(self):
        for alias in ('zh', 'zh-cn', 'zh_cn', 'zh-hans', 'ZH'):
            assert normalize_lang(alias) == 'zh_Hans'

    def test_traditional(self):
        for alias in ('zh-hant', 'zh-tw', 'zh_tw'):
            assert normalize_lang(alias) == 'zh_Hant'

    def test_passthrough(self):
        assert normalize_lang('en') == 'en'
        assert normalize_lang('ja') == 'ja'
