# -*- coding: utf-8 -*-
"""pytest 公共配置：把项目根加入 sys.path，测试可 import src。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
