# -*- coding: utf-8 -*-
"""NotebookLM 通道封装：登录态、笔记本、来源、提问。"""
import asyncio
from notebooklm import NotebookLMClient


class NotebookLM:
    """基于 notebooklm-py 的 NotebookLM 通道。"""

    def __init__(self, notebook_name: str = "链接总结"):
        self.notebook_name = notebook_name
        self._client = None
        self._notebook_id = None

    async def __aenter__(self):
        # from_storage() 返回 async context manager，进入后取 client
        self._cm = NotebookLMClient.from_storage()
        self._client = await self._cm.__aenter__()
        return self

    async def __aexit__(self, *exc):
        await self._cm.__aexit__(*exc)

    async def _ensure_notebook(self):
        """复用同名笔记本，不存在则创建。"""
        if self._notebook_id:
            return self._notebook_id
        notebooks = await self._client.notebooks.list()
        for nb in notebooks:
            if (getattr(nb, 'title', '') or '') == self.notebook_name:
                self._notebook_id = nb.id
                return self._notebook_id
        nb = await self._client.notebooks.create(self.notebook_name)
        self._notebook_id = nb.id
        return self._notebook_id

    async def add_source(self, target: str, kind: str, local_path: str = None) -> tuple[str, str]:
        """添加来源并等待处理就绪。返回 (source_id, 标题)。"""
        nb_id = await self._ensure_notebook()
        if kind in ('url', 'youtube'):
            # NotebookLM 的 URL 来源自动识别网页与 YouTube（自动转写）
            src = await self._client.sources.add_url(nb_id, target)
        elif kind == 'file':
            src = await self._client.sources.add_file(nb_id, local_path)
        elif kind == 'text':
            src = await self._client.sources.add_text(nb_id, '粘贴文本', target)
        else:
            raise ValueError(f'未知来源类型: {kind}')

        # 等待来源处理完成（NotebookLM 抓取/转写）
        try:
            await self._client.sources.wait_until_ready(nb_id, src.id, timeout=180)
        except Exception as e:
            print(f'      (来源处理等待：{type(e).__name__})')

        # 获取来源标题（NotebookLM 抓取的真实标题）
        title = None
        try:
            s = await self._client.sources.get(nb_id, src.id)
            title = getattr(s, 'title', None) or None
        except Exception:
            pass
        return src.id, title

    async def ask(self, prompt: str, source_ids: list[str] = None) -> str:
        """按 prompt 提问，返回回答文本。source_ids 指定来源（默认全部）。"""
        nb_id = await self._ensure_notebook()
        result = await self._client.chat.ask(nb_id, prompt, source_ids=source_ids)
        return getattr(result, 'answer', str(result))
