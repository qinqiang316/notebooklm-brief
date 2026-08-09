# -*- coding: utf-8 -*-
"""输出层测试：slug / 路径 / 三层结构 / 保存 / 导图与测验转换。"""
import json
import os

from src.output import (build_note_file, generated_dir, knowledge_dir,
                        mindmap_json_to_md, notebook_dir, quiz_json_to_md,
                        save_answer, save_chat_log, save_source_fulltext,
                        slugify, source_dir)


class TestSlugify:
    def test_basic(self):
        assert slugify('量子计算简介') == '量子计算简介'

    def test_illegal_chars_replaced(self):
        assert slugify('a/b\\c:d') == 'a-b-c-d'

    def test_truncated(self):
        assert len(slugify('x' * 100, max_len=40)) <= 40

    def test_empty(self):
        assert slugify('') == 'untitled'


class TestNotebookDir:
    def test_creates_dir(self, tmp_path):
        d = notebook_dir(str(tmp_path), '笔记-量子计算')
        assert d == str(tmp_path / '笔记-量子计算')
        assert (tmp_path / '笔记-量子计算').is_dir()

    def test_idempotent(self, tmp_path):
        d1 = notebook_dir(str(tmp_path), '笔记-A')
        d2 = notebook_dir(str(tmp_path), '笔记-A')
        assert d1 == d2


class TestThreeLayerDirs:
    def test_dirs_created(self, tmp_path):
        nb = notebook_dir(str(tmp_path), '笔记-A')
        assert source_dir(nb).endswith(os.path.join('source'))
        assert generated_dir(nb).endswith(os.path.join('generated'))
        assert knowledge_dir(nb).endswith(os.path.join('knowledge'))
        assert os.path.isdir(source_dir(nb))
        assert os.path.isdir(generated_dir(nb))
        assert os.path.isdir(knowledge_dir(nb))


class TestSaveSourceFulltext:
    def test_first_write(self, tmp_path):
        nb = notebook_dir(str(tmp_path), '笔记-A')
        p = save_source_fulltext(nb, '原文内容')
        assert p.endswith(os.path.join('source', 'source.md'))
        assert open(p, encoding='utf-8').read() == '原文内容'

    def test_immutable(self, tmp_path):
        nb = notebook_dir(str(tmp_path), '笔记-A')
        save_source_fulltext(nb, '第一版')
        save_source_fulltext(nb, '第二版')
        assert open(os.path.join(source_dir(nb), 'source.md'),
                    encoding='utf-8').read() == '第一版'


class TestSaveAnswer:
    def test_new_file_in_generated(self, tmp_path):
        nb = notebook_dir(str(tmp_path), '笔记-A')
        p = save_answer('https://x.com/a', '内容', nb, title='标题')
        assert p == os.path.join(generated_dir(nb), 'analysis.md')
        text = open(p, encoding='utf-8').read()
        assert '内容' in text

    def test_append_keeps_header(self, tmp_path):
        nb = notebook_dir(str(tmp_path), '笔记-A')
        p1 = save_answer('https://x.com/a', '第一段', nb, title='标题')
        p2 = save_answer('https://x.com/a', '第二段', nb, title='标题', append=True)
        assert p1 == p2
        text = open(p2, encoding='utf-8').read()
        assert text.index('第一段') < text.index('第二段')


class TestSaveChatLog:
    def test_renders_rounds(self, tmp_path):
        nb = notebook_dir(str(tmp_path), '笔记-A')
        qa = [('问1', '答1'), ('问2', '答2')]
        p = save_chat_log('https://x.com/a', '标题', '笔记-A', qa, nb)
        assert p == os.path.join(generated_dir(nb), 'conversation.md')
        text = open(p, encoding='utf-8').read()
        assert '第 1 轮' in text and '第 2 轮' in text
        assert '问1' in text and '答2' in text


class TestMindmapJsonToMd:
    def _write_json(self, path):
        data = {'name': '根', 'children': [
            {'name': '一级A', 'children': [{'name': '二级A1'}]},
            {'name': '一级B'},
        ]}
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return path

    def test_conversion(self, tmp_path):
        jp = self._write_json(tmp_path / 'map.json')
        md = mindmap_json_to_md(str(jp))
        assert md == str(tmp_path / 'map.md')
        text = open(md, encoding='utf-8').read()
        assert '## 一级A' in text
        assert '- 二级A1' in text


class TestQuizJsonToMd:
    def _write_json(self, path):
        data = {'questions': [
            {'question': '问题一', 'options': ['A选项', 'B选项'],
             'correctAnswer': 'A选项'},
        ]}
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        return path

    def test_conversion(self, tmp_path):
        jp = self._write_json(tmp_path / 'quiz.json')
        md = quiz_json_to_md(str(jp))
        assert md == str(tmp_path / 'quiz.md')
        text = open(md, encoding='utf-8').read()
        assert '问题一' in text
        assert 'A选项' in text
        assert '答案' in text

    def test_list_format(self, tmp_path):
        jp = tmp_path / 'q2.json'
        jp.write_text(json.dumps([{'question': '直接数组'}], ensure_ascii=False),
                      encoding='utf-8')
        md = quiz_json_to_md(str(jp))
        assert '直接数组' in open(md, encoding='utf-8').read()


class TestBuildNoteFile:
    def test_build_with_fulltext(self, tmp_path):
        nb = notebook_dir(str(tmp_path), '笔记-A')
        p = build_note_file(nb, '标题', 'https://x.com', '原文全文', '分析内容',
                            [('问', '答')], meta={'original_url': 'https://x.com'})
        assert p == os.path.join(generated_dir(nb), '标题.笔记.md')
        text = open(p, encoding='utf-8').read()
        assert '原文全文' in text
        assert '分析内容' in text
        assert '原始链接：https://x.com' in text
        assert '问' in text and '答' in text
