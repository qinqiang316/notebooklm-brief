# -*- coding: utf-8 -*-
"""项目配置：集中管理环境相关配置（归档目录/输出目录/代理/语言/账号等）。

设计目标——可迁移性：
- 所有机器相关的配置集中在 config.yaml（项目根目录），不在代码里硬编码
- 首次使用运行 `python main.py --setup` 交互式引导生成 config.yaml
- 没有 config.yaml 时使用内置默认值（开箱即用），但归档目录等建议配置
"""
import os

import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.yaml')

# 内置默认值（未配置时兜底）
DEFAULTS = {
    'output_dir': os.path.join(BASE_DIR, 'output'),
    'archive_dir': '',            # 空 = 不归档，需在 --setup 或 config.yaml 配置
    'archive_template': '',       # 归档模板（Obsidian frontmatter 模板 .md），空 = 直接复制
    'proxy': 'http://127.0.0.1:10808',   # v2rayN 本地代理
    'language': 'zh_Hans',        # NotebookLM 生成语言
    'yt_proxy': '',               # 访问 YouTube 的代理（默认同 proxy）
    'yt_match': True,             # B站链接是否先尝试匹配 YouTube 原片
    'account_email': '',          # Google 账号邮箱（提示用）
    'notebooklm_home': '',        # NotebookLM 数据目录（默认 ~/.notebooklm）
}

_loaded: dict | None = None


def _read_config() -> dict:
    """读取 config.yaml；不存在或损坏则返回空 dict。"""
    global _loaded
    if _loaded is not None:
        return _loaded
    _loaded = {}
    if os.path.isfile(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
            if isinstance(data, dict):
                _loaded = data
        except Exception as e:
            print(f'[config] 警告：config.yaml 读取失败（{e}），使用默认配置')
    return _loaded


def get(key: str, default=None):
    """读取配置项（config.yaml 优先，其次内置默认，再其次调用方 default）。"""
    cfg = _read_config()
    if key in cfg and cfg[key] not in (None, ''):
        return cfg[key]
    if key in DEFAULTS and DEFAULTS[key]:
        return DEFAULTS[key]
    return default


def get_archive_dir() -> str:
    """归档目录（Obsidian 库目录）。未配置返回空串（调用方决定是否归档）。"""
    return str(get('archive_dir', '') or '')


def get_archive_template() -> str:
    """归档模板路径（frontmatter 模板 .md）。未配置返回空串（直接复制）。"""
    return str(get('archive_template', '') or '')


def get_output_dir() -> str:
    return str(get('output_dir', DEFAULTS['output_dir']))


def get_proxy() -> str:
    return str(get('proxy', DEFAULTS['proxy']))


def get_yt_proxy() -> str:
    yt = get('yt_proxy', '')
    return str(yt or get('proxy', DEFAULTS['proxy']))


def get_language() -> str:
    return str(get('language', DEFAULTS['language']))


def get_yt_match() -> bool:
    return bool(get('yt_match', True))


def save(config: dict) -> str:
    """写入 config.yaml（保留已有配置，合并更新）。返回路径。"""
    global _loaded
    cfg = _read_config()
    cfg.update({k: v for k, v in config.items() if v is not None})
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    _loaded = cfg
    return CONFIG_PATH


def ensure_config_file() -> str:
    """确保 config.yaml 存在（不存在则创建默认）。返回路径。"""
    if not os.path.isfile(CONFIG_PATH):
        save({})
    return CONFIG_PATH
