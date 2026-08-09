# -*- coding: utf-8 -*-
"""NotebookManager（V3 Phase 2）：Notebook 生命周期管理。

职责：
- 创建 / 查找 / 复用 Notebook（名称只负责展示，身份靠 notebook_id）
- 删除 Notebook、同步 Notebook（按本地 output/ 文件夹管理云端笔记本）

与门面（pipeline.NotebookLM）共享 client；通过 nlm.notebooks 访问。
"""
import os

from src.output import slugify


class NotebookManager:
    """Notebook 生命周期管理。"""

    def __init__(self, nlm):
        self._nlm = nlm
        self._notebook_id: str | None = None

    @property
    def client(self):
        return self._nlm._client

    async def _ensure_notebook_id(self, name: str = None,
                                  notebook_id: str = None) -> str:
        """解析 Notebook 身份，按优先级复用：

        1. 本实例已解析的 _notebook_id
        2. 显式 notebook_id（来自 metadata，云端仍存在才用）
        3. 同名笔记本（名称复用，兼容旧数据）
        4. 新建
        """
        if self._notebook_id:
            return self._notebook_id
        target_id = notebook_id or self._nlm.notebook_id
        if target_id:
            try:
                notebooks = await self.client.notebooks.list()
                if any(getattr(nb, 'id', '') == target_id for nb in notebooks):
                    self._notebook_id = target_id
                    return target_id
            except Exception:
                pass  # 云端不可用时按名称回退
        name = name or self._nlm.notebook_name
        if name:
            notebooks = await self.client.notebooks.list()
            for nb in notebooks:
                if (getattr(nb, 'title', '') or '') == name:
                    self._notebook_id = nb.id
                    return nb.id
        nb = await self.client.notebooks.create(name or '链接总结')
        self._notebook_id = nb.id
        return nb.id

    async def list_all(self) -> list[tuple[str, str]]:
        """列出云端所有笔记本，返回 [(id, title)]。"""
        notebooks = await self.client.notebooks.list()
        return [(nb.id, getattr(nb, 'title', '') or '') for nb in notebooks]

    async def delete(self, notebook_id: str) -> None:
        """删除云端笔记本（幂等）。"""
        await self.client.notebooks.delete(notebook_id)

    # ---------- 笔记本同步（按本地 output/ 文件夹管理云端） ----------

    def local_notebook_dirs(self, output_dir: str) -> set[str]:
        """本地 output/ 下的笔记本文件夹名集合（笔记-* 目录 = 要保留的清单）。"""
        if not os.path.isdir(output_dir):
            return set()
        return {d for d in os.listdir(output_dir)
                if os.path.isdir(os.path.join(output_dir, d)) and d.startswith('笔记-')}

    async def sync(self, output_dir: str, delete: bool = False) -> list[tuple[str, str]]:
        """按本地笔记本文件夹同步云端：保留本地有的，列出（或删除）本地没有的。

        - 本地 output/ 下每个 笔记-<标题> 文件夹 = 应保留的笔记本
        - 云端存在但本地无对应文件夹的笔记本：dry-run 仅列出；delete=True 执行删除
        - 返回实际删除的 [(id, title)] 列表
        """
        local_dirs = self.local_notebook_dirs(output_dir)
        print(f'[sync] 本地笔记本文件夹：{len(local_dirs)} 个')
        for d in sorted(local_dirs):
            print(f'      保留：{d}')

        cloud = await self.list_all()

        # 本地文件夹名 = slugify(云端笔记本名, max_len=80)；云端名 = 笔记-<slug>
        local_slugs = {slugify(d, max_len=80) for d in local_dirs}

        to_delete = []
        for nb_id, title in cloud:
            if title in local_dirs:
                continue
            if slugify(title, max_len=80) in local_slugs:
                continue
            to_delete.append((nb_id, title))

        print(f'[sync] 云端笔记本：{len(cloud)} 个，待清理：{len(to_delete)} 个')
        for nb_id, title in to_delete:
            print(f'      ✗ {title}  (id={nb_id})')

        if delete:
            for nb_id, title in to_delete:
                print(f'[sync] 删除：{title}')
                await self.delete(nb_id)
            print(f'[sync] 已删除 {len(to_delete)} 个笔记本')
        else:
            print('[sync] dry-run：未执行删除（加 --delete-notebooks 执行）')

        return to_delete
