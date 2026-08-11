#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同步 metadata.json 标题 + 云端笔记本名（与本地新文件夹名一致，2026-08-11 一次性）。

显式映射（云端旧名 -> 本地新文件夹名），避免模糊匹配误改。
"""
import asyncio
import json
import os
import re
import httpx

from notebooklm import NotebookLMClient

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'output')

# 云端旧名 -> 本地新文件夹名（重命名映射；云端旧名 == 迁移前的文件夹名）
CLOUD_RENAME = {
    '笔记-12564': '笔记-AI不会带来超级组织',
    'AI 不会带来超级组织': '笔记-AI不会带来超级组织',  # 与上同源，改名后需处理重复
    '笔记-AI为什么那么聪明？人是怎么创造AI的？-从零入门，讲讲人与AI的故事': '笔记-AI为什么那么聪明',
    '笔记-Andrej-Karpathy-Just-Fixed-Claude-Code’s': '笔记-Karpathy修复ClaudeCode',
    '笔记-Why-Agentic-Systems-Need-Ontologies-—-Fr': '笔记-Agentic系统为何需要本体论',
    '笔记-Why-Graph-Engineering-will-10x-your-Clau': '笔记-图工程十倍提升Claude',
    '笔记-tmp-xyztmp-E42降码率.m4a': '笔记-孟岩对话韦青-沉默的主角',
    '笔记-【半佛】5本让你怀疑世界的好书': '笔记-半佛-5本让你怀疑世界的好书',
    '笔记-【半佛】你知道奶茶加盟到底有多坑人吗？': '笔记-半佛-奶茶加盟有多坑',
    '笔记-【半佛】营养工厂，暴打保健品': '笔记-半佛-营养工厂暴打保健品',
    '笔记-【双语音】如何通过人工智能实现高效的自主学习-p01-中文语音': '笔记-AI高效自主学习-双语音',
    '笔记-我雇了三个AI员工开发我的产品，今天正式开源！【B站AI创造公开赛】': '笔记-我雇了三个AI员工开发产品',
    '笔记-杰夫·迪恩：构建人工智能的1%原则': '笔记-杰夫迪恩-AI的1%原则',
    '笔记-硬核的半佛仙人-活着就是熬着，活下去就是一切': '笔记-半佛-活着就是熬着',
}

def main():
    # 1. 本地 metadata：notebook_title = 新文件夹名，title = 归档笔记里的标题
    for d in sorted(os.listdir(OUT)):
        full = os.path.join(OUT, d)
        mp = os.path.join(full, 'metadata.json')
        if not os.path.isdir(full) or not os.path.isfile(mp):
            continue
        with open(mp, encoding='utf-8') as f:
            rec = json.load(f)
        rec['notebook_title'] = d
        note = os.path.join(full, '归档笔记.md')
        if os.path.isfile(note):
            try:
                head = open(note, encoding='utf-8').read(3000)
                m = re.search(r'^#\s*(?:笔记[：:]?\s*)?(.*)$', head, re.M)
                if m:
                    t = m.group(1).strip()
                    if t and not t.startswith('bili_'):
                        rec['title'] = t
            except Exception:
                pass
        with open(mp, 'w', encoding='utf-8') as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        print(f'[本地] {d}: title={rec.get("title","")[:30]!r}')

    # 2. 云端改名（显式映射）
    async def _cloud():
        async with NotebookLMClient.from_storage(upload_timeout=httpx.Timeout(60.0, read=1800.0, write=1800.0)) as client:
            nbs = await client.notebooks.list()
            print(f'\n[云端] 共 {len(nbs)} 个笔记本')
            # 先按旧名找 id
            by_title = {getattr(nb, 'title', ''): nb.id for nb in nbs}
            renamed = set()
            for oldt, newt in CLOUD_RENAME.items():
                if oldt not in by_title:
                    print(f'[云端] 跳过（云端无此名）：{oldt!r}')
                    continue
                nid = by_title[oldt]
                # 目标名已存在（如 12564 与 AI 不会带来超级组织 都指向同一新名）
                if newt in renamed:
                    # 保留第一个，删除重复的云端笔记本
                    try:
                        await client.notebooks.delete(nid)
                        print(f'[云端] 删除重复：{oldt!r}（已并入 {newt!r}）')
                    except Exception as e:
                        print(f'[云端] 删除失败 {oldt!r}: {e}')
                    continue
                try:
                    await client.notebooks.rename(nid, newt)
                    renamed.add(newt)
                    print(f'[云端] 改名：{oldt[:40]!r} -> {newt!r}')
                except Exception as e:
                    print(f'[云端] 改名失败 {oldt!r}: {e}')

            # 3. 检查本地文件夹是否都有对应云端笔记本
            print('\n[检查] 本地文件夹 vs 云端：')
            nbs2 = await client.notebooks.list()
            cloud_titles = {getattr(nb, 'title', '') for nb in nbs2}
            for d in sorted(os.listdir(OUT)):
                if os.path.isdir(os.path.join(OUT, d)):
                    if d not in cloud_titles:
                        print(f'  ⚠ 本地 {d} 无同名云端笔记本')

    asyncio.run(_cloud())

if __name__ == '__main__':
    main()
