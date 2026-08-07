# -*- coding: utf-8 -*-
"""NotebookLM 通道封装：登录态、笔记本、来源、提问。"""
import asyncio
import re
from notebooklm import NotebookLMClient

# 语言代码规范化：用户习惯写 zh，但 NotebookLM 库要求 BCP-47 标签（zh_Hans）
LANG_ALIASES = {
    'zh': 'zh_Hans',
    'zh-cn': 'zh_Hans',
    'zh_cn': 'zh_Hans',
    'zh-hans': 'zh_Hans',
    'zh-hant': 'zh_Hant',
    'zh_tw': 'zh_Hant',
    'zh-tw': 'zh_Hant',
}


def normalize_lang(lang: str) -> str:
    """zh / zh_CN 等别名 -> 库支持的 BCP-47 语言代码（默认 zh_Hans 中文）。"""
    if not lang:
        return 'zh_Hans'
    key = lang.strip().lower()
    return LANG_ALIASES.get(key, key)


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

    async def list_sources(self) -> list[tuple[str, str]]:
        """返回笔记本内所有来源 (source_id, title)。追问时复用，不重复添加。"""
        nb_id = await self._ensure_notebook()
        sources = await self._client.sources.list(nb_id)
        return [(s.id, getattr(s, 'title', '') or '') for s in sources]

    async def list_all_notebooks(self) -> list[tuple[str, str]]:
        """列出云端所有笔记本，返回 [(id, title)]。"""
        notebooks = await self._client.notebooks.list()
        return [(nb.id, getattr(nb, 'title', '') or '') for nb in notebooks]

    async def delete_notebook(self, notebook_id: str) -> None:
        """删除云端笔记本（幂等）。"""
        await self._client.notebooks.delete(notebook_id)

    async def get_source_fulltext(self, source_id: str,
                                  output_format: str = 'markdown') -> str | None:
        """提取来源原文/转写全文（文章全文、YouTube/B站音频转写文本）。
        返回文本内容；失败返回 None（不阻断主流程）。
        markdown 格式需要 markdownify 包，缺失时自动回退 text。"""
        nb_id = await self._ensure_notebook()
        for fmt in (output_format, 'text'):
            try:
                ft = await self._client.sources.get_fulltext(
                    nb_id, source_id, output_format=fmt)
                content = getattr(ft, 'content', None)
                if content:
                    return content
            except ImportError:
                # markdown 格式缺依赖 -> 回退 text
                if fmt == 'text':
                    print('      (原文提取：markdown 依赖缺失，已回退纯文本)')
            except Exception as e:
                if fmt == 'text':
                    print(f'      (原文提取失败：{type(e).__name__})')
        return None

    async def get_conversation_id(self) -> str | None:
        """获取当前对话 ID（追问时传入保持上下文）。"""
        nb_id = await self._ensure_notebook()
        return await self._client.chat.get_conversation_id(nb_id)

    async def get_history(self, limit: int = 100) -> list[tuple[str, str]]:
        """获取笔记本最近对话的完整历史 [(问题, 回答)]，oldest-first。
        用于汇总所有对话内容生成对话记录。"""
        nb_id = await self._ensure_notebook()
        conv_id = await self._client.chat.get_conversation_id(nb_id)
        if not conv_id:
            return []
        return await self._client.chat.get_history(nb_id, limit=limit,
                                                   conversation_id=conv_id)

    async def generate_artifact(self, kind: str, lang: str = 'zh',
                                source_ids: list[str] = None):
        """生成 NotebookLM 原生内容（报告/播客/导图等），等待完成。
        kind: report|podcast|mindmap|quiz|flashcards|studyguide|infographic|slidedeck
        返回 (kind, artifact_id)。lang 自动规范化（zh -> zh_Hans）。"""
        nb_id = await self._ensure_notebook()
        arts = self._client.artifacts
        kind = kind.lower()
        lang = normalize_lang(lang)
        if kind == 'report':
            st = await arts.generate_report(nb_id, source_ids=source_ids, language=lang)
        elif kind == 'podcast':
            st = await arts.generate_audio(nb_id, source_ids=source_ids, language=lang)
        elif kind == 'mindmap':
            result = await arts.generate_mind_map(nb_id, source_ids=source_ids,
                                                  language=lang)
            return kind, getattr(result, 'note_id', None)
        elif kind == 'quiz':
            st = await arts.generate_quiz(nb_id, source_ids=source_ids)
        elif kind == 'flashcards':
            st = await arts.generate_flashcards(nb_id, source_ids=source_ids)
        elif kind == 'studyguide':
            st = await arts.generate_study_guide(nb_id, source_ids=source_ids,
                                                 language=lang)
        elif kind == 'infographic':
            st = await arts.generate_infographic(nb_id, source_ids=source_ids,
                                                 language=lang)
        elif kind == 'slidedeck':
            st = await arts.generate_slide_deck(nb_id, source_ids=source_ids,
                                                language=lang)
        else:
            raise ValueError(
                f'未知类型：{kind}，可选 report/podcast/mindmap/quiz/flashcards/'
                'studyguide/infographic/slidedeck')
        st = await arts.wait_for_completion(nb_id, st.task_id, timeout=600)
        if st.is_failed or st.is_removed:
            raise RuntimeError(f'{kind} 生成失败：{st.error or st.status}')
        return kind, st.task_id

    async def download_artifact(self, kind: str, artifact_id: str,
                                output_path: str) -> str:
        """下载已生成的 artifact 到本地，返回实际路径。"""
        nb_id = await self._ensure_notebook()
        arts = self._client.artifacts
        if kind == 'report':
            return await arts.download_report(nb_id, output_path, artifact_id)
        if kind == 'podcast':
            return await arts.download_audio(nb_id, output_path, artifact_id)
        if kind == 'mindmap':
            return await arts.download_mind_map(nb_id, output_path, artifact_id)
        if kind == 'quiz':
            return await arts.download_quiz(nb_id, output_path, artifact_id)
        if kind == 'flashcards':
            return await arts.download_flashcards(nb_id, output_path, artifact_id)
        if kind == 'studyguide':
            return await arts.download_report(nb_id, output_path, artifact_id)
        if kind == 'infographic':
            return await arts.download_infographic(nb_id, output_path, artifact_id)
        if kind == 'slidedeck':
            return await arts.download_slide_deck(nb_id, output_path, artifact_id)
        raise ValueError(f'未知类型：{kind}')

    async def ask(self, prompt: str, source_ids: list[str] = None,
                  conversation_id: str = None) -> str:
        """按 prompt 提问，返回回答文本。source_ids 指定来源（默认全部）。
        conversation_id 传上次对话 ID 即为追问（保持上下文）。
        非中文提问自动追加中文回答要求（NotebookLM 回答语言跟随提问）。"""
        nb_id = await self._ensure_notebook()
        if prompt and not re.search(r'[\u4e00-\u9fff]', prompt):
            prompt = f'{prompt}\n\n（请用简体中文回答）'
        result = await self._client.chat.ask(nb_id, prompt,
                                             source_ids=source_ids,
                                             conversation_id=conversation_id)
        return getattr(result, 'answer', str(result))
