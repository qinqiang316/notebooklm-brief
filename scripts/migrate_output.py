#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""output 目录结构迁移脚本（2026-08-11，一次性）。

目标结构（每个笔记本一个文件夹）：
    output/<短名>/
    ├── metadata.json          # Source Identity
    ├── 归档笔记.md             # ★ 最终可归档笔记（放顶层，与过程文件区分）
    ├── source/source.md       # 过程文件：原文/转写
    ├── generated/             # 过程文件：NotebookLM 生成物
    │   ├── analysis.md / conversation.md / mindmap.* / studyguide.md / report.md ...
    └── knowledge/             # Human 层：个人笔记

处理：
- V1 平铺结构（无 metadata.json）→ 升级为新结构（建三层，文件归类，.笔记.md 提升为顶层归档笔记.md）
- V3 结构 → 只把 generated/<标题>.笔记.md 提升为顶层 归档笔记.md
- 文件夹按实际内容短名重命名（笔记-<短名>）
- 重复笔记本合并（AI-不会带来超级组织 与 笔记-12564 同源，保留内容更全者）
"""
import json
import os
import re
import shutil

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'output')

# 旧文件夹名 -> 新短名（基于实际内容；笔记- 前缀保留，sync 依赖）
RENAME = {
    'AI-不会带来超级组织': '笔记-AI不会带来超级组织',
    '笔记-12564': '笔记-AI不会带来超级组织',  # 合并（内容更全：Clipper 完整版）
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

V1_TITLE_HINTS = {
    # 旧目录名 -> 内容标题（用于 V1 无 metadata 时写 title）
    'AI-不会带来超级组织': 'AI不会带来超级组织',
    '笔记-12564': 'AI不会带来超级组织',
    '笔记-AI为什么那么聪明？人是怎么创造AI的？-从零入门，讲讲人与AI的故事': 'AI为什么那么聪明？人是怎么创造AI的？-从零入门，讲讲人与AI的故事',
    '笔记-Andrej-Karpathy-Just-Fixed-Claude-Code’s': 'Andrej Karpathy Just Fixed Claude Code’s',
    '笔记-Why-Agentic-Systems-Need-Ontologies-—-Fr': 'Why Agentic Systems Need Ontologies',
    '笔记-Why-Graph-Engineering-will-10x-your-Clau': 'Why Graph Engineering will 10x your Claude',
    '笔记-【半佛】5本让你怀疑世界的好书': '【半佛】5本让你怀疑世界的好书',
    '笔记-【半佛】你知道奶茶加盟到底有多坑人吗？': '【半佛】你知道奶茶加盟到底有多坑人吗？',
    '笔记-【半佛】营养工厂，暴打保健品': '【半佛】营养工厂，暴打保健品',
    '笔记-【双语音】如何通过人工智能实现高效的自主学习-p01-中文语音': '【双语音】如何通过人工智能实现高效的自主学习-p01-中文语音',
    '笔记-我雇了三个AI员工开发我的产品，今天正式开源！【B站AI创造公开赛】': '我雇了三个AI员工开发我的产品，今天正式开源！【B站AI创造公开赛】',
    '笔记-杰夫·迪恩：构建人工智能的1%原则': '杰夫·迪恩：构建人工智能的1%原则',
    '笔记-硬核的半佛仙人-活着就是熬着，活下去就是一切': '硬核的半佛仙人-活着就是熬着，活下去就是一切',
}

def slugify(s, max_len=40):
    t = re.sub(r'[\\/:*?"<>|\s]+', '-', s).strip('-')
    return t[:max_len] or 'untitled'

def find_note_file(d):
    """找 .笔记.md 或主 .md（V1）或 generated 里的合并笔记（V3）。"""
    # V1 平铺
    for f in sorted(os.listdir(d)):
        if f.endswith('.笔记.md') and os.path.isfile(os.path.join(d, f)):
            return os.path.join(d, f)
    # V3 generated/<标题>.笔记.md
    g = os.path.join(d, 'generated')
    if os.path.isdir(g):
        for f in sorted(os.listdir(g)):
            if f.endswith('.笔记.md'):
                return os.path.join(g, f)
    return None

def read_title(note_path):
    try:
        with open(note_path, encoding='utf-8') as f:
            head = f.read(3000)
        m = re.search(r'^#\s*(?:笔记[：:]?\s*)?(.*)$', head, re.M)
        if m:
            return m.group(1).strip()
        m = re.search(r'title:\s*(.*)$', head, re.M)
        if m:
            return m.group(1).strip()
    except Exception:
        pass
    return None

def main():
    # 1. 确定各目录去向（合并映射）
    merged_target = {}
    dirs = sorted(os.listdir(OUT))
    print('=== 迁移计划 ===')
    plan = []
    for d in dirs:
        full = os.path.join(OUT, d)
        if not os.path.isdir(full):
            continue
        new = RENAME.get(d, d)
        plan.append((d, new))
        print(f'  {d}  ->  {new}')
    print()

    # 2. 先合并重复（AI-不会带来超级组织 内容较少，并入 笔记-12564）
    #    保留 笔记-12564（含 Clipper 完整版 .bak 与更全 .笔记.md）
    dup_src = os.path.join(OUT, 'AI-不会带来超级组织')
    dup_dst = os.path.join(OUT, '笔记-12564')
    if os.path.isdir(dup_src) and os.path.isdir(dup_dst):
        print('=== 合并重复：AI-不会带来超级组织 -> 笔记-12564 ===')
        for f in os.listdir(dup_src):
            sp = os.path.join(dup_src, f)
            dp = os.path.join(dup_dst, f)
            if os.path.isfile(sp):
                if not os.path.exists(dp):
                    shutil.move(sp, dp)
                    print(f'  移动 {f}')
                else:
                    os.remove(sp)
                    print(f'  跳过(已存在) {f}')
        # 清理空目录（含 .DS_Store 等残留）
        for f in os.listdir(dup_src):
            try:
                os.remove(os.path.join(dup_src, f))
            except OSError:
                pass
        try:
            os.rmdir(dup_src)
            print('  已删除空目录 AI-不会带来超级组织')
        except OSError as e:
            print(f'  警告：目录清理失败 {e}')

    # 3. 逐目录迁移
    for old, new in plan:
        if old == 'AI-不会带来超级组织':  # 已合并
            continue
        src = os.path.join(OUT, old)
        if not os.path.isdir(src):
            continue
        dst = os.path.join(OUT, new)
        if os.path.abspath(src) == os.path.abspath(dst):
            migrate_one(dst, dst, old)
        else:
            print(f'=== 重命名：{old} -> {new} ===')
            if os.path.isdir(dst):
                # 目标已存在：把源内容并入目标
                for f in os.listdir(src):
                    sp = os.path.join(src, f)
                    dp = os.path.join(dst, f)
                    if not os.path.exists(dp):
                        shutil.move(sp, dp)
                os.rmdir(src)
            else:
                os.rename(src, dst)
            migrate_one(dst, dst, old)

    print()
    print('=== 完成 ===')

def migrate_one(dst, _full, old):
    """把一个笔记本目录迁移到新结构（幂等）。"""
    os.makedirs(os.path.join(dst, 'source'), exist_ok=True)
    os.makedirs(os.path.join(dst, 'generated'), exist_ok=True)
    os.makedirs(os.path.join(dst, 'knowledge'), exist_ok=True)

    g = os.path.join(dst, 'generated')

    # 归档笔记：把顶层/现有 .笔记.md 提升为 归档笔记.md
    note = find_note_file(dst)
    if note:
        dest_note = os.path.join(dst, '归档笔记.md')
        if os.path.abspath(note) != os.path.abspath(dest_note):
            shutil.move(note, dest_note)
            print(f'  [归档] {os.path.relpath(note, dst)} -> 归档笔记.md')

    # V1 平铺文件归类到 generated/
    for f in sorted(os.listdir(dst)):
        p = os.path.join(dst, f)
        if not os.path.isfile(p):
            continue
        if f in ('metadata.json', '归档笔记.md'):
            continue
        # 归类
        if f.endswith('-mindmap.json'):
            shutil.move(p, os.path.join(g, 'mindmap.json'))
        elif f.endswith('-mindmap.md'):
            shutil.move(p, os.path.join(g, 'mindmap.md'))
        elif f.endswith('-studyguide.md'):
            shutil.move(p, os.path.join(g, 'studyguide.md'))
        elif f.endswith('-report.md') or f.endswith('.report.md'):
            shutil.move(p, os.path.join(g, 'report.md'))
        elif f.endswith('.对话记录.md') or f.endswith('-对话记录.md'):
            shutil.move(p, os.path.join(g, 'conversation.md'))
        elif f.endswith('.md') and not f.endswith('.笔记.md'):
            # V1 主分析文件
            shutil.move(p, os.path.join(g, 'analysis.md'))
        elif f.endswith('.bak'):
            os.remove(p)
        else:
            shutil.move(p, os.path.join(g, f))

    # V3 里 generated 已归类（analysis/conversation/mindmap/studyguide），无需动
    # metadata.json：V1 无则生成
    meta_path = os.path.join(dst, 'metadata.json')
    if not os.path.isfile(meta_path):
        title = V1_TITLE_HINTS.get(old) or read_title(os.path.join(dst, '归档笔记.md')) or old
        rec = {
            'source_id': '',
            'source_type': 'url',
            'original_url': '',
            'canonical_url': '',
            'title': title,
            'duration': None,
            'local_path': '',
            'created_at': '',
            'updated_at': '',
            'version': 0,
            'notebook_id': '',
            'notebook_title': os.path.basename(dst),
        }
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        print(f'  [metadata] 新建 {os.path.basename(dst)}: title={title!r}')

if __name__ == '__main__':
    main()
