# -*- coding: utf-8 -*-
"""下载地址与主机/端口解耦回归测试（任务 09-16-download-url-origin）

背景缺陷：下载地址曾用 `rx.config` 的**构建期**端口（frontend 3000 / backend 8000）拼绝对 URL，
部署成单端口 8091 后地址被改写成 `host:8000` 并写进 version.json ⇒ 首页「下载客户端」跳错端口。

覆盖：
  1. 纯函数矩阵：相对路径编码 / 绝对拼接 / host 为空 / 外部主机保留 / 同主机不同端口→相对
  2. `is_same_origin_serving`（prod 标记）
  3. State 端到端：`download_client()` 生成的跳转串（自愈历史 :8000、外部托管保留、无 version.json 走相对）
  4. 源码守卫：reflex_web.py 不再用 config 端口拼下载地址 / 不再 socket 猜 IP / 死代码已删

直接运行: PYTHONIOENCODING=utf-8 python test/test_web_download_url.py
"""

import _path_setup  # noqa: E402

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "reflex_web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from reflex_web import web_utils as wu  # noqa: E402

PASS = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAILURES.append(name)
        print(f"  ✗ {name}  {detail}")


class _EnvGuard:
    def __init__(self, **env):
        self.env = env
        self.saved = {}

    def __enter__(self):
        for k, v in self.env.items():
            self.saved[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False


# ═══════════════════════════════════════════════════════════════
# 1. 纯函数
# ═══════════════════════════════════════════════════════════════

def test_pure_functions():
    print("\n[1] 纯函数")
    check("相对路径：ASCII 名", wu.release_download_path("a.exe") == "/download/a.exe")
    cn = wu.release_download_path("南网协议解析工具1.23.14.exe")
    check("相对路径：中文名被 URL 编码", cn.startswith("/download/") and "%" in cn, cn)
    from urllib.parse import quote as _q
    check(
        "相对路径：空名回落固定名（并 URL 编码）",
        wu.release_download_path("") == f"/download/{_q(wu.DEFAULT_EXE_NAME)}",
        wu.release_download_path(""),
    )
    check(
        "相对路径：空格被编码",
        " " not in wu.release_download_path("my tool.exe"),
        wu.release_download_path("my tool.exe"),
    )

    check(
        "绝对地址：拼真实 host",
        wu.release_absolute_url("192.168.1.50:8091", "a.exe")
        == "http://192.168.1.50:8091/download/a.exe",
        wu.release_absolute_url("192.168.1.50:8091", "a.exe"),
    )
    check(
        "绝对地址：host 为空 → 相对路径（不猜主机端口）",
        wu.release_absolute_url("", "a.exe") == "/download/a.exe",
        wu.release_absolute_url("", "a.exe"),
    )

    # resolve_download_target 矩阵
    cases = [
        (
            "prod：历史 :8000 地址 → 自愈为相对路径",
            dict(stored_url="http://server:8000/download/a.exe", exe_name="a.exe",
                 host="server:8091", same_origin_serving=True),
            "/download/a.exe",
        ),
        (
            "prod：https 同主机不同端口 → 相对路径",
            dict(stored_url="https://server/download/a.exe", exe_name="a.exe",
                 host="server:8091", same_origin_serving=True),
            "/download/a.exe",
        ),
        (
            "prod：外部主机 → 原样使用（外部托管）",
            dict(stored_url="https://files.example.com/a.exe", exe_name="a.exe",
                 host="server:8091", same_origin_serving=True),
            "https://files.example.com/a.exe",
        ),
        (
            "prod：无 version.json → 相对路径",
            dict(stored_url="", exe_name="a.exe", host="server:8091", same_origin_serving=True),
            "/download/a.exe",
        ),
        (
            "dev：分端口 → 带后端 host 的绝对地址",
            dict(stored_url="", exe_name="a.exe", host="localhost:8000", same_origin_serving=False),
            "http://localhost:8000/download/a.exe",
        ),
        (
            "dev：历史同主机 :8000 → 仍带后端 host",
            dict(stored_url="http://localhost:8000/download/a.exe", exe_name="a.exe",
                 host="localhost:8000", same_origin_serving=False),
            "http://localhost:8000/download/a.exe",
        ),
        (
            "拿不到 host → 回落到相对路径",
            dict(stored_url="", exe_name="a.exe", host="", same_origin_serving=False),
            "/download/a.exe",
        ),
        (
            "存量相对路径 stored → 保持相对",
            dict(stored_url="/download/a.exe", exe_name="a.exe", host="server:8091",
                 same_origin_serving=True),
            "/download/a.exe",
        ),
        (
            "主机名大小写/端口差异不算「外部」",
            dict(stored_url="http://SERVER:8000/download/a.exe", exe_name="a.exe",
                 host="server:8091", same_origin_serving=True),
            "/download/a.exe",
        ),
    ]
    for name, kwargs, expected in cases:
        got = wu.resolve_download_target(**kwargs)
        check(f"resolve_download_target：{name}", got == expected, f"got={got!r} want={expected!r}")


def test_same_origin_flag():
    print("\n[2] 同源部署判定")
    check("prod 标记为真", wu.is_same_origin_serving({"REFLEX_ENV": "prod"}) is True)
    check(
        "挂载标记为真（大小写不敏感）",
        wu.is_same_origin_serving({"__REFLEX_MOUNT_FRONTEND_COMPILED_APP": "TRUE"}) is True,
    )
    check("dev 为假", wu.is_same_origin_serving({"REFLEX_ENV": "dev"}) is False)
    check("空 env 为假", wu.is_same_origin_serving({}) is False)
    check(
        "两个标记任一成立即为真",
        wu.is_same_origin_serving({"REFLEX_ENV": "dev", "__REFLEX_MOUNT_FRONTEND_COMPILED_APP": "true"})
        is True,
    )


# ═══════════════════════════════════════════════════════════════
# 3. State 端到端（真实 State 实例）
# ═══════════════════════════════════════════════════════════════

def test_state_download_client():
    print("\n[3] State.download_client 生成的跳转串")
    try:
        from reflex_web.reflex_web import State
    except Exception as e:  # noqa: BLE001
        check("导入 reflex_web.reflex_web", False, f"{type(e).__name__}: {e}")
        return

    st = State(_reflex_internal_init=True)
    st.download_exe_available = True
    st.download_exe_name = "南网协议解析工具1.23.14.exe"

    # 模拟「浏览器正在访问 host:port」：真机上由 Reflex 的 router headers 提供。
    # 注意：State 禁止给实例设未声明属性（SetUndefinedStateVarError）→ 只能在**类**上打补丁。
    orig_origin = State._download_origin
    try:
        State._download_origin = lambda self, fallback="": "192.168.1.50:8091"  # type: ignore[method-assign]

        with _EnvGuard(REFLEX_ENV="prod", __REFLEX_MOUNT_FRONTEND_COMPILED_APP="true"):
            # 历史 version.json（写死 :8000）→ 应自愈为相对路径
            st.download_version_url = (
                "http://192.168.1.50:8000/download/南网协议解析工具1.23.14.exe"
            )
            url = st._download_target_url()
            check("prod：不再跳到 :8000（自愈历史 version.json）", ":8000" not in url, url)
            check("prod：走同源相对路径", url.startswith("/download/"), url)
            check("prod：文件名被 URL 编码", "%E5%8D%97%E7%BD%91" in url, url)
            check("prod：与具体 host/端口无关", "192.168.1.50" not in url, url)

            st.download_version_url = "https://files.example.com/setup.exe"
            check(
                "外部托管地址原样保留",
                st._download_target_url() == "https://files.example.com/setup.exe",
            )

            st.download_version_url = ""
            check("无 version.json：走相对路径", st._download_target_url().startswith("/download/"))

        State._download_origin = lambda self, fallback="": "localhost:8000"  # type: ignore[method-assign]
        with _EnvGuard(REFLEX_ENV="dev", __REFLEX_MOUNT_FRONTEND_COMPILED_APP=None):
            st.download_version_url = ""
            dev_url = st._download_target_url()
            check(
                "dev：带后端 host（Vite 不代理下载路由）",
                dev_url.startswith("http://localhost:8000/download/"),
                dev_url,
            )

        State._download_origin = lambda self, fallback="": ""  # type: ignore[method-assign]
        with _EnvGuard(REFLEX_ENV="dev", __REFLEX_MOUNT_FRONTEND_COMPILED_APP=None):
            st.download_version_url = ""
            check(
                "拿不到 host（无请求上下文）→ 相对路径兜底",
                st._download_target_url().startswith("/download/"),
                st._download_target_url(),
            )
    finally:
        State._download_origin = orig_origin  # type: ignore[method-assign]

    # exe 未就绪时不跳转
    st.download_exe_available = False
    out = st.download_client()
    check("exe 未就绪：不产生跳转脚本", out is None and st.download_msg == "客户端 exe 未就绪",
          f"out={out!r} msg={st.download_msg!r}")


# ═══════════════════════════════════════════════════════════════
# 4. 源码守卫（旧实现不许回来）
# ═══════════════════════════════════════════════════════════════

def test_source_guards():
    print("\n[4] 源码守卫")
    src = (WEB / "reflex_web" / "reflex_web.py").read_text(encoding="utf-8")
    check(
        "不再用 config 的 backend_port 拼下载地址",
        'getattr(config, "backend_port"' not in src,
        "仍有 getattr(config, \"backend_port\" 用法",
    )
    check("不再 socket 猜本机 IP（8.8.8.8）", "8.8.8.8" not in src)
    check("死代码 set_release_url_from_host 已删", "set_release_url_from_host" not in src)
    check(
        "download_client 走 resolve_download_target",
        "resolve_download_target" in src,
    )
    check(
        "发布页默认地址走 release_absolute_url",
        src.count("release_absolute_url") >= 2,
        f"出现 {src.count('release_absolute_url')} 次",
    )
    # 生成器里的 8080/8000 之类端口不该出现在下载地址拼接中
    check(
        "无 f\"http://{...}/download/ 形式的裸拼接残留",
        not re.search(r'f"http://\{[^}]*\}:/?download/', src),
    )


def main():
    print("=" * 62)
    print("下载地址与主机/端口解耦 回归测试")
    print("=" * 62)
    test_pure_functions()
    test_same_origin_flag()
    test_state_download_client()
    test_source_guards()
    print("\n" + "=" * 62)
    if FAILURES:
        print(f"失败 {len(FAILURES)} 项 / 通过 {PASS} 项")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print(f"全部通过（{PASS} 项）✓")
    print("=" * 62)


if __name__ == "__main__":
    main()
