# -*- coding: utf-8 -*-
"""
南网协议解析工具 - Reflex Web 版启动器（用于 PyInstaller 打包 exe）

功能：
- 单进程启动 Reflex 前后端（ASGI + 静态文件）
- 支持 --port 参数修改端口（默认 8080）
- 支持 --host 参数修改监听地址（默认 0.0.0.0）
- PyInstaller 打包后自动从资源目录加载前端静态文件

用法：
    run_app.exe --port 8080 --host 0.0.0.0
"""
import os
import sys
import argparse
import tempfile
import shutil
from pathlib import Path


def _get_resource_dir() -> Path:
    """获取资源根目录（PyInstaller 打包后为 sys._MEIPASS，开发时为脚本所在目录）"""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    # 开发模式：脚本在 reflex_web/ 目录下
    return Path(__file__).resolve().parent


def _setup_frontend_static(resource_dir: Path) -> Path:
    """设置前端静态文件目录，返回 web_workdir

    Reflex 通过 REFLEX_WEB_WORKDIR 环境变量查找前端文件，
    期望结构: web_workdir/build/client/  (即 Dirs.STATIC = BUILD_DIR/client)

    PyInstaller 打包时，静态文件放在 web_static/build/client/
    开发模式下，使用 .web/build/client/
    """
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller 模式：前端静态文件打包在 _MEIPASS/web_static/build/client/
        bundled = resource_dir / "web_static" / "build" / "client"
        if bundled.exists():
            return resource_dir / "web_static"

    # 开发模式：使用 .web/build/client/
    web_static = resource_dir / ".web" / "build" / "client"
    if web_static.exists():
        return resource_dir / ".web"

    raise RuntimeError(
        "未找到前端静态文件！\n"
        "开发模式下请先运行: cd reflex_web && reflex export --frontend-only --env prod --no-zip\n"
        f"期望路径: {web_static}"
    )


def main():
    parser = argparse.ArgumentParser(description="南网协议解析工具 - Reflex Web 版")
    parser.add_argument("--port", type=int, default=8080, help="监听端口（默认 8080）")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="监听地址（默认 0.0.0.0）")
    args = parser.parse_args()

    # 获取资源目录
    resource_dir = _get_resource_dir()

    # 设置前端静态文件目录（必须在导入 Reflex 之前设置）
    web_work_dir = _setup_frontend_static(resource_dir)
    os.environ["REFLEX_WEB_WORKDIR"] = str(web_work_dir)

    # 启用预编译前端挂载模式
    # 注意：internal=True 的 Reflex 环境变量需要加 __ 前缀
    os.environ["__REFLEX_MOUNT_FRONTEND_COMPILED_APP"] = "true"

    # 生产模式
    os.environ["REFLEX_ENV"] = "prod"

    # 禁用遥测
    os.environ["REFLEX_TELEMETRY_ENABLED"] = "false"

    # 将项目根目录加入 sys.path（协议解析器在那里）
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller 模式：所有 Python 模块都在 _MEIPASS 中
        root_dir = resource_dir
    else:
        # 开发模式：resource_dir 是 reflex_web/，父目录是项目根
        root_dir = resource_dir.parent

    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))

    # 延迟导入（环境变量设置后）
    import uvicorn

    # ===== Monkey-patch：跳过前端 npm 包安装 =====
    # 前端已经预编译打包进 exe 了，运行时不需要也不应该再安装 npm 包
    # （目标服务器没有 Node.js，会导致 FileNotFoundError: Bun or npm not found）
    try:
        from reflex.utils import js_runtimes
        js_runtimes.install_frontend_packages = lambda *a, **kw: None
    except Exception:
        pass
    # 也 patch App._get_frontend_packages 作为双重保险
    try:
        from reflex.app import App
        App._get_frontend_packages = lambda self, *a, **kw: None
    except Exception:
        pass

    # 导入应用（触发 Reflex 配置加载）
    from reflex_web.reflex_web import app as rx_app

    # 调用 app() 得到完整 ASGI 应用
    # （包含后端 API + WebSocket + 前端静态文件，前后端共用一个端口）
    asgi_app = rx_app()

    # ===== 包装 ASGI 应用：动态修复前端 env.js 中的硬编码 URL =====
    # 前端编译时把 api_url 硬编码为 localhost:8000，
    # 但部署时端口是动态的（--port 参数）且 host 是服务器 IP。
    # 通过拦截 reflex-env-*.js 的响应，把硬编码 URL 替换为实际访问的 host:port，
    # 让前端自动使用正确地址连接 WebSocket 和 API。
    # 同时处理 gzip 预压缩响应（浏览器 Accept-Encoding: gzip 时 Reflex 返回 .gz 文件）。
    import gzip

    # 匹配要替换的硬编码 URL 模式
    _HTTP_PREFIX = "http://localhost:8000"
    _WS_PREFIX = "ws://localhost:8000"

    def _rewrite_env_js(body_bytes, headers_list, host, scheme):
        """对 env.js 响应体做 URL 替换，返回 (new_body, new_headers)。
        自动处理 gzip 压缩的响应体。
        """
        # 检查 content-encoding
        content_encoding = None
        for k, v in headers_list:
            if k.lower() == b"content-encoding":
                content_encoding = v.decode("latin-1").lower()
                break

        # 解压（如果是 gzip）
        if content_encoding == "gzip":
            try:
                text = gzip.decompress(body_bytes).decode("utf-8")
            except Exception:
                return body_bytes, headers_list
        else:
            try:
                text = body_bytes.decode("utf-8")
            except Exception:
                return body_bytes, headers_list

        # 判断是否是 env.js（包含我们要替换的标记）
        if _HTTP_PREFIX not in text and _WS_PREFIX not in text:
            return body_bytes, headers_list

        # 计算替换后的 URL
        base_url = f"{scheme}://{host}"
        ws_scheme = "wss" if scheme == "https" else "ws"
        ws_base = f"{ws_scheme}://{host}"

        # 替换
        text = text.replace(_HTTP_PREFIX, base_url)
        text = text.replace(_WS_PREFIX, ws_base)

        new_body = text.encode("utf-8")

        # 如果原来是 gzip，重新压缩
        if content_encoding == "gzip":
            new_body = gzip.compress(new_body)

        # 更新 Content-Length
        new_headers = []
        for k, v in headers_list:
            if k.lower() == b"content-length":
                new_headers.append((k, str(len(new_body)).encode()))
            else:
                new_headers.append((k, v))

        return new_body, new_headers

    async def env_rewrite_middleware(scope, receive, send):
        if scope["type"] != "http":
            return await asgi_app(scope, receive, send)

        path = scope.get("path", "")
        # 只拦截 reflex-env JS 文件
        if "/assets/reflex-env-" not in path or not path.endswith(".js"):
            return await asgi_app(scope, receive, send)

        # 获取请求的 host 和 scheme
        host = None
        for key, value in scope.get("headers", []):
            if key == b"host":
                host = value.decode("latin-1")
                break
        if not host:
            return await asgi_app(scope, receive, send)

        scheme = scope.get("scheme", "http")

        # 捕获响应体
        response_body = bytearray()
        response_status = 200
        response_headers = []

        async def send_wrapper(message):
            nonlocal response_status, response_headers, response_body
            if message["type"] == "http.response.start":
                response_status = message["status"]
                response_headers = list(message.get("headers", []))
            elif message["type"] == "http.response.body":
                response_body.extend(message.get("body", b""))
                if not message.get("more_body", False):
                    # 响应完整，进行替换
                    new_body, new_headers = _rewrite_env_js(
                        bytes(response_body), response_headers, host, scheme
                    )
                    # 重新发送
                    await send({
                        "type": "http.response.start",
                        "status": response_status,
                        "headers": new_headers,
                    })
                    await send({
                        "type": "http.response.body",
                        "body": new_body,
                        "more_body": False,
                    })
                # more_body=True 时继续累积，不发送
            else:
                await send(message)

        await asgi_app(scope, receive, send_wrapper)

    # 启动
    print("=" * 60)
    print("  南网协议解析工具 - Reflex Web 版")
    print(f"  访问地址: http://{args.host}:{args.port}")
    print(f"  局域网设备可通过服务器 IP 访问")
    print("=" * 60)
    print()

    uvicorn.run(
        env_rewrite_middleware,
        host=args.host,
        port=args.port,
        log_level="info",
        access_log=True,
        ws="websockets",
    )


if __name__ == "__main__":
    main()
