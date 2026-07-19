# -*- coding: utf-8 -*-
"""Reflex 配置文件"""
import reflex as rx

config = rx.Config(
    app_name="reflex_web",
    title="南网协议解析工具",
    description="南方电网协议解析与调试",
    # 使用自定义端口避免冲突
    frontend_port=3000,
    backend_port=8000,
    # 禁用遥测
    telemetry_enabled=False,
    # 开发模式
    env=rx.Env.DEV,
)
