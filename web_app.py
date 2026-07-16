# -*- coding: utf-8 -*-
"""南网协议解析工具 - NiceGUI Web版入口

优化点：
- 版本号从 main_gui.py 安全读取（文本解析，避免把 PySide6 GUI 栈拉进 Web 进程）
- 监听地址/端口/深色模式/是否自动打开浏览器均可通过环境变量配置，无需改代码
- 缺少 nicegui 时给出明确提示并退出
"""
import os
import re
import sys
import logging
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("web_app")


def _read_app_version(fallback: str = "0.0.0") -> str:
    """从 main_gui.py 文本中解析 APP_VERSION，避免 import 触发 PySide6 依赖。"""
    try:
        text = (ROOT / "main_gui.py").read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"APP_VERSION\s*=\s*['\"]([^'\"]+)['\"]", text)
        if m:
            return m.group(1)
    except Exception as ex:  # pragma: no cover - 解析失败不影响启动
        log.warning("读取 APP_VERSION 失败，使用兜底值: %s", ex)
    return fallback


def _env_flag(name: str, default: bool) -> bool:
    """读取布尔型环境变量，支持 true/false/1/0/on/off/yes/no（不区分大小写）。"""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def main():
    try:
        from nicegui import ui, app
    except ImportError:
        print("错误: 未安装 nicegui，请运行: pip install nicegui")
        sys.exit(1)

    version = _read_app_version()

    # 外部依赖：Google Fonts（离线时浏览器自动降级，不阻塞）
    ui.add_head_html('<link rel="preconnect" href="https://fonts.googleapis.com">')
    ui.add_head_html('<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>')
    ui.add_head_html(
        '<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500'
        '&family=Microsoft+YaHei:wght@400;500;700&display=swap" rel="stylesheet">'
    )

    css_path = ROOT / "web" / "styles" / "custom.css"
    if css_path.exists():
        ui.add_css(css_path.read_text(encoding="utf-8"))

    @app.get("/health")
    def health():
        return {"status": "ok", "version": version}

    from web.main_page import MainPage

    main_page = MainPage()
    main_page.build()

    host = os.environ.get("WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("WEB_PORT", "8080"))
    dark = _env_flag("WEB_DARK", False)
    show = _env_flag("WEB_SHOW", True)

    log.info("启动 Web 服务: http://%s:%s (版本 %s, 深色=%s)", host, port, version, dark)
    ui.run(
        title="南网协议解析工具",
        host=host,
        port=port,
        dark=dark,
        native=False,
        reload=False,
        show=show,
        favicon="🔌",
    )


if __name__ in {"__main__", "__mp_main__"}:
    main()
