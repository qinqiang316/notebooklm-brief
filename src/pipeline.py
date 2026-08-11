# -*- coding: utf-8 -*-
"""NotebookLM 通道门面（V3 Phase 2）。

只负责把四个 Manager 串起来形成完整流程：
- notebooks:  NotebookManager（创建/查找/复用/删除/同步）
- sources:    SourceManager（添加/等待/列出/获取/全文）
- conversation: ConversationManager（ask/chat/history/conversation_id）
- artifacts:  ArtifactManager（mindmap/report/studyguide/... 生成与下载）

保持旧方法名（add_source/list_sources/...）作为薄转发，兼容既有调用方。
"""
from .artifact import ArtifactManager, normalize_lang  # noqa: F401（normalize_lang 兼容导出）
from .conversation import ConversationManager
from .notebook import NotebookManager
from .provider import RealNotebookLMProvider
from .source import SourceManager


class NotebookLM:
    """NotebookLM 门面：组合四个 Manager，保持 asynccontextmanager 接口。"""

    def __init__(self, notebook_name: str = "链接总结", notebook_id: str = None,
                 provider=None):
        import httpx
        self.notebook_name = notebook_name
        self.notebook_id = notebook_id
        self._client = None
        if provider is None:
            provider = RealNotebookLMProvider(
                upload_timeout=httpx.Timeout(60.0, read=1800.0, write=1800.0))
        self._provider = provider
        self.notebooks = NotebookManager(self)
        self.sources = SourceManager(self)
        self.conversation = ConversationManager(self)
        self.artifacts = ArtifactManager(self)

    async def __aenter__(self):
        # provider 负责 NotebookLMClient 生命周期（真实 from_storage / Mock 内存）
        self._client = await self._provider.__aenter__()
        return self

    async def __aexit__(self, *exc):
        await self._provider.__aexit__(*exc)

    # ---------- 旧接口薄转发（兼容既有调用方） ----------

    async def add_source(self, target: str, kind: str,
                         local_path: str = None) -> tuple[str, str]:
        return await self.sources.add(target, kind, local_path)

    async def list_sources(self) -> list[tuple[str, str]]:
        return await self.sources.list()

    async def list_all_notebooks(self) -> list[tuple[str, str]]:
        return await self.notebooks.list_all()

    async def delete_notebook(self, notebook_id: str) -> None:
        return await self.notebooks.delete(notebook_id)

    async def get_source_fulltext(self, source_id: str,
                                  output_format: str = 'markdown') -> str | None:
        return await self.sources.get_fulltext(source_id, output_format)

    async def get_conversation_id(self) -> str | None:
        return await self.conversation.get_conversation_id()

    async def get_history(self, limit: int = 100) -> list[tuple[str, str]]:
        return await self.conversation.get_history(limit)

    async def generate_artifact(self, kind: str, lang: str = 'zh',
                                source_ids: list[str] = None):
        return await self.artifacts.generate(kind, lang, source_ids)

    async def download_artifact(self, kind: str, artifact_id: str,
                                output_path: str) -> str:
        return await self.artifacts.download(kind, artifact_id, output_path)

    async def ask(self, prompt: str, source_ids: list[str] = None,
                  conversation_id: str = None) -> str:
        return await self.conversation.ask(prompt, source_ids, conversation_id)
