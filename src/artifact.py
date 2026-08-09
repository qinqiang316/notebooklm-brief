# -*- coding: utf-8 -*-
"""ArtifactManager（V3 Phase 2）：NotebookLM 原生内容（导图/报告/学习指南等）生成与下载。"""
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


class ArtifactManager:
    """NotebookLM 原生内容管理：mindmap/report/studyguide/quiz/flashcards/
    infographic/slidedeck/podcast 的生成与下载。"""

    def __init__(self, nlm):
        self._nlm = nlm

    async def generate(self, kind: str, lang: str = 'zh',
                       source_ids: list[str] = None,
                       notebook_name: str = None):
        """生成 NotebookLM 原生内容，等待完成。
        kind: report|podcast|mindmap|quiz|flashcards|studyguide|infographic|slidedeck
        返回 (kind, artifact_id)。lang 自动规范化（zh -> zh_Hans）。"""
        nb_id = await self._nlm.notebooks._ensure_notebook_id(name=notebook_name)
        arts = self._nlm.notebooks.client.artifacts
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

    async def download(self, kind: str, artifact_id: str,
                       output_path: str,
                       notebook_name: str = None) -> str:
        """下载已生成的 artifact 到本地，返回实际路径。"""
        nb_id = await self._nlm.notebooks._ensure_notebook_id(name=notebook_name)
        arts = self._nlm.notebooks.client.artifacts
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
