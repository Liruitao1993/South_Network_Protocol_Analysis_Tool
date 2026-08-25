# -*- coding: utf-8 -*-
"""Reflex 配置文件"""
import os
from pathlib import Path

import reflex as rx

# dev 模式热重载排除 downloads/：发布管理往该目录写 100MB+ 的 exe/tmp 文件，
# 若被热重载监视会触发后端重启，发布线程被杀、前端表现为点击无反应
# 注意：该环境变量按冒号切分，Windows 绝对路径盘符会被误切，必须用相对路径
os.environ.setdefault(
    "REFLEX_HOT_RELOAD_EXCLUDE_PATHS",
    os.path.relpath(Path(__file__).resolve().parent / "downloads"),
)

config = rx.Config(
    app_name="reflex_web",
    title="多协议解析平台",
    description="电力通信多协议解析与调试（南网/国网/DLT645/698.45/新一代载波等）",
    # 使用自定义端口避免冲突
    frontend_port=3000,
    backend_port=8000,
    # 禁用遥测
    telemetry_enabled=False,
    # 开发模式
    env=rx.Env.DEV,
)
