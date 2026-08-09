# -*- coding: utf-8 -*-
"""ConversationManager（V3 Phase 2）：提问/对话/历史管理。"""
import re


class ConversationManager:
    """NotebookLM 对话管理：ask / chat / history / conversation_id。"""

    def __init__(self, nlm):
        self._nlm = nlm

    async def get_conversation_id(self, notebook_name: str = None) -> str | None:
        """获取当前对话 ID（追问时传入保持上下文）。"""
        nb_id = await self._nlm.notebooks._ensure_notebook_id(name=notebook_name)
        return await self._nlm.notebooks.client.chat.get_conversation_id(nb_id)

    async def ask(self, prompt: str, source_ids: list[str] = None,
                  conversation_id: str = None,
                  notebook_name: str = None) -> str:
        """按 prompt 提问，返回回答文本。source_ids 指定来源（默认全部）。
        conversation_id 传上次对话 ID 即为追问（保持上下文）。
        非中文提问自动追加中文回答要求（NotebookLM 回答语言跟随提问）。"""
        nb_id = await self._nlm.notebooks._ensure_notebook_id(name=notebook_name)
        if prompt and not re.search(r'[\u4e00-\u9fff]', prompt):
            prompt = f'{prompt}\n\n（请用简体中文回答）'
        result = await self._nlm.notebooks.client.chat.ask(
            nb_id, prompt, source_ids=source_ids, conversation_id=conversation_id)
        return getattr(result, 'answer', str(result))

    async def get_history(self, limit: int = 100,
                          notebook_name: str = None) -> list[tuple[str, str]]:
        """获取笔记本最近对话的完整历史 [(问题, 回答)]，oldest-first。
        用于汇总所有对话内容生成对话记录。"""
        nb_id = await self._nlm.notebooks._ensure_notebook_id(name=notebook_name)
        conv_id = await self._nlm.notebooks.client.chat.get_conversation_id(nb_id)
        if not conv_id:
            return []
        return await self._nlm.notebooks.client.chat.get_history(
            nb_id, limit=limit, conversation_id=conv_id)
