# -*- coding: utf-8 -*-
"""NotebookLM Provider 抽象（V3 Phase 6 / 执行计划 §14）。

测试不访问真实 NotebookLM：注入 MockNotebookLMProvider 即可离线跑全流程。
- RealNotebookLMProvider：包装 notebooklm-py 的 NotebookLMClient.from_storage()
- MockNotebookLMProvider：内存实现（测试/演示用）
"""
import os
import types


class NotebookLMProvider:
    """Provider 基类：async context manager，暴露 .client。"""

    async def __aenter__(self):
        raise NotImplementedError

    async def __aexit__(self, *exc):
        raise NotImplementedError


class RealNotebookLMProvider(NotebookLMProvider):
    """真实 NotebookLM（notebooklm-py 客户端，登录态 from_storage）。

    upload_timeout：覆盖库默认的上传超时（httpx.Timeout）。大文件
    （>100MB 音频）默认 read=300s 不够，会抛 httpx.WriteTimeout。
    """

    def __init__(self, client_factory=None, upload_timeout=None):
        self._client_factory = client_factory
        self._upload_timeout = upload_timeout

    async def __aenter__(self):
        from notebooklm import NotebookLMClient
        import httpx
        factory = self._client_factory or NotebookLMClient.from_storage
        kwargs = {}
        if self._upload_timeout is not None:
            kwargs['upload_timeout'] = self._upload_timeout
        self._cm = factory(**kwargs)
        self.client = await self._cm.__aenter__()
        return self.client

    async def __aexit__(self, *exc):
        await self._cm.__aexit__(*exc)


class MockNotebookLMProvider(NotebookLMProvider):
    """内存 Mock：不访问网络，供测试/演示。

    share_state=True 时所有实例共享同一 client（模拟云端 Notebook 持久，
    跨多次 run() 保留笔记本/来源）；默认 False 每次隔离。
    """

    _shared = None  # 类级共享状态

    def __init__(self, share_state: bool = False):
        self.share_state = share_state
        self.client = None

    async def __aenter__(self):
        if self.share_state:
            if MockNotebookLMProvider._shared is None:
                MockNotebookLMProvider._shared = _MockClient()
            self.client = MockNotebookLMProvider._shared
        else:
            self.client = _MockClient()
        return self.client

    async def __aexit__(self, *exc):
        self.client = None


# ---------- Mock 内部实现 ----------

def _obj(**kw):
    return types.SimpleNamespace(**kw)


def _async_ret(value):
    async def _f(*a, **k):
        return value
    return _f


class _MockSources:
    def __init__(self):
        self._s = {}

    async def add_url(self, nb_id, url):
        return self._add('u' + str(len(self._s) + 1), url)

    async def add_file(self, nb_id, path):
        return self._add('f' + str(len(self._s) + 1), os.path.basename(path))

    async def add_text(self, nb_id, name, content):
        return self._add('t' + str(len(self._s) + 1), name)

    def _add(self, sid, title):
        src = _obj(id=sid, title=title)
        self._s[sid] = src
        return src

    async def wait_until_ready(self, *a, **k):
        return None

    async def get(self, nb_id, sid):
        return self._s.get(sid, _obj(id=sid, title=''))

    async def list(self, nb_id):
        return list(self._s.values())

    async def get_fulltext(self, nb_id, sid, output_format='text'):
        return _obj(content='模拟原文全文内容（Mock NotebookLM）')


class _MockNotebooks:
    def __init__(self):
        self._l = []

    async def list(self):
        return list(self._l)

    async def create(self, name):
        nb = _obj(id='nb' + str(len(self._l) + 1), title=name)
        self._l.append(nb)
        return nb

    async def delete(self, notebook_id):
        self._l = [nb for nb in self._l if nb.id != notebook_id]


class _MockChat:
    async def get_conversation_id(self, nb_id):
        return 'conv1'

    async def ask(self, nb_id, prompt, source_ids=None, conversation_id=None):
        return _obj(answer=f'【Mock 回答】{prompt[:60]}')

    async def get_history(self, nb_id, limit=100, conversation_id=None):
        return [('模拟问题', '模拟回答')]


class _MockArtifacts:
    async def generate_report(self, *a, **k):
        return _obj(task_id='t1', is_failed=False, is_removed=False)

    async def generate_audio(self, *a, **k):
        return _obj(task_id='t2', is_failed=False, is_removed=False)

    async def generate_mind_map(self, *a, **k):
        return _obj(note_id='note1')

    async def generate_quiz(self, *a, **k):
        return _obj(task_id='t3', is_failed=False, is_removed=False)

    async def generate_flashcards(self, *a, **k):
        return _obj(task_id='t4', is_failed=False, is_removed=False)

    async def generate_study_guide(self, *a, **k):
        return _obj(task_id='t5', is_failed=False, is_removed=False)

    async def generate_infographic(self, *a, **k):
        return _obj(task_id='t6', is_failed=False, is_removed=False)

    async def generate_slide_deck(self, *a, **k):
        return _obj(task_id='t7', is_failed=False, is_removed=False)

    async def wait_for_completion(self, nb_id, task_id, timeout=None):
        return _obj(is_failed=False, is_removed=False, status='completed',
                    task_id=task_id)

    async def download_report(self, nb_id, path, aid):
        _write(path, '# Mock 报告\n\n模拟报告内容')
        return path

    async def download_audio(self, nb_id, path, aid):
        _write(path, 'MOCK-AUDIO')
        return path

    async def download_mind_map(self, nb_id, path, aid):
        _write(path, '{"name": "根", "children": [{"name": "一级", "children": []}]}')
        return path

    async def download_quiz(self, nb_id, path, aid):
        _write(path, '{"questions": [{"question": "Q1", "options": ["A", "B"], '
                     '"correctAnswer": "A"}]}')
        return path

    async def download_flashcards(self, nb_id, path, aid):
        _write(path, '[]')
        return path

    async def download_infographic(self, nb_id, path, aid):
        _write(path, 'MOCK-IMG')
        return path

    async def download_slide_deck(self, nb_id, path, aid):
        _write(path, 'MOCK-PDF')
        return path


def _write(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


class _MockClient:
    def __init__(self):
        self.notebooks = _MockNotebooks()
        self.sources = _MockSources()
        self.chat = _MockChat()
        self.artifacts = _MockArtifacts()
