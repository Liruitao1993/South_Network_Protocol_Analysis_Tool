# -*- coding: utf-8 -*-
"""Reflex 配置文件"""
import reflex as rx

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
