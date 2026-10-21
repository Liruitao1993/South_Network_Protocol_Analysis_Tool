"""auto_updater 单元测试：版本比较 / 更新源 JSON 解析 / update.bat 生成 / GitHub 源。

用法：
    python test/test_auto_updater.py
"""
import json
import sys
import tempfile
from pathlib import Path

# 让项目根可导入
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _path_setup  # noqa: E402,F401

from auto_updater import (  # noqa: E402
    DEFAULT_UPDATE_CONFIG,
    GITHUB_RELEASE_TIMEOUT,
    VersionChecker,
    build_update_bat,
    check_for_update,
    compare_versions,
    default_github_api,
    default_github_releases_api,
    describe_http_status,
    describe_source,
    is_update_needed,
    merge_update_config,
    Opdater,
    parse_github_repo_url,
    summarize_notes,
    _digest_to_sha256,
    _extract_release_info,
)


# ── 版本比较 ─────────────────────────────────────────────
def test_compare_equal():
    assert compare_versions("1.14.4", "1.14.4") == 0
    assert compare_versions("1.0.0", "1.0.0") == 0


def test_compare_newer():
    assert compare_versions("1.0.0", "1.0.1") < 0   # 需要更新
    assert compare_versions("1.14.4", "1.15.0") < 0
    assert compare_versions("1.9.9", "1.14.0") < 0   # 逐段数字比较，非字典序
    assert compare_versions("2.0.0", "1.99.99") > 0  # 不更新


def test_compare_v_prefix():
    assert compare_versions("v1.14.4", "1.14.4") == 0
    assert compare_versions("1.14.4", "v1.15.0") < 0


def test_is_update_needed():
    assert is_update_needed("1.14.4", "1.15.0") is True
    assert is_update_needed("1.15.0", "1.15.0") is False
    assert is_update_needed("1.16.0", "1.15.0") is False


# ── 更新源 JSON 解析 ─────────────────────────────────────
def test_extract_gitee_release():
    data = {
        "tag_name": "v1.15.0",
        "name": "v1.15.0",
        "body": "修复若干问题",
        "assets": [
            {"name": "source.zip", "browser_download_url": "https://gitee.com/x/src.zip"},
            {"name": "南网协议解析工具.exe",
             "browser_download_url": "https://gitee.com/x/南网协议解析工具.exe",
             "size": 101000000},
        ],
    }
    info = _extract_release_info(data)
    assert info["version"] == "v1.15.0"
    assert "南网协议解析工具.exe" in info["url"]
    assert "修复" in info["notes"]
    # 多个资产时优先 exe
    assert "src.zip" not in info["url"]


def test_extract_private_json():
    data = {"version": "1.2.0", "url": "http://10.0.0.8/app.exe",
            "notes": "内网版", "sha256": "a" * 64}
    info = _extract_release_info(data)
    assert info["version"] == "1.2.0"
    assert info["url"] == "http://10.0.0.8/app.exe"
    assert info["sha256"] == "a" * 64


def test_extract_missing_fields():
    try:
        _extract_release_info({})
        assert False, "应抛 UpdateSourceError"
    except Exception:
        pass


# ── VersionChecker ─────────────────────────────────────────
def test_checker_private_source():
    def fake_get(url):
        return json.dumps({"version": "2.0.0", "url": "http://x/app.exe"})
    cfg = merge_update_config({"source_type": "private", "private_url": "http://x/ver.json"})
    checker = VersionChecker(cfg, http_get=fake_get)
    result = checker.check("1.14.4")
    assert result["available"] is True
    assert result["latest"]["version"] == "2.0.0"


def test_checker_already_latest():
    def fake_get(url):
        return json.dumps({"version": "1.14.4", "url": "http://x/app.exe"})
    cfg = merge_update_config({"source_type": "private", "private_url": "http://x/ver.json"})
    result = VersionChecker(cfg, http_get=fake_get).check("1.14.4")
    assert result["available"] is False


def test_checker_network_error_degrades():
    """网络失败由顶层 check_for_update 降级（error 字段），不抛异常。"""
    def bad_get(url):
        raise OSError("timeout")
    cfg = merge_update_config({"source_type": "private", "private_url": "http://x/ver.json"})
    result = check_for_update("1.0.0", cfg, http_get=bad_get)
    assert result["needed"] is False
    assert result["error"] is not None  # 降级并携带错误原因


# ── update.bat 生成 ───────────────────────────────────────
def test_build_update_bat_contains_replacement():
    new = Path(r"C:\tmp\new.exe")
    old = Path(r"D:\tools\南网协议解析工具.exe")
    bat = build_update_bat(new, old)
    assert "D:\\tools\\南网协议解析工具.exe" in bat
    assert "C:\\tmp\\new.exe" in bat
    # 批处理占位词应被替换，无残留 __
    assert "__NEW__" not in bat
    assert "__OLD__" not in bat
    assert "南网协议解析工具.exe" in bat  # IMAGENAME 用老 exe 名轮询等待


# ── 下载 + 校验 ──────────────────────────────────────────
def test_opdater_verify_sha256():
    tmp = Path(tempfile.gettempdir()) / "auto_update_test.txt"
    tmp.write_bytes(b"hello")
    sha = __import__("hashlib").sha256(b"hello").hexdigest()
    updater = Opdater()
    assert updater.verify(tmp, sha) is True
    assert updater.verify(tmp, "f" * 64) is False
    assert updater.verify(tmp, "") is True       # 无预期值视为通过
    assert updater.verify(tmp, "abc") is False   # 非法长度
    tmp.unlink(missing_ok=True)


def test_update_bat_roundtrip_syntax():
    """生成的 bat 至少是合法的批处理骨架（含 tasklist 轮询与 copy）。"""
    new = Path(r"C:\new.exe")
    old = Path(r"C:\old.exe")
    bat = build_update_bat(new, old)
    assert "tasklist" in bat
    assert "copy /y /b" in bat
    assert "start \"\"" in bat


# ── GitHub 源（默认）：默认值 / 地址解析 ──────────────────
def github_release_payload(**over):
    """GitHub `releases/latest` 的真实形状（字段名照抄 2026-10 实测响应）。"""
    data = {
        "tag_name": "1.23.86",
        "name": "1.23.86",
        "draft": False,
        "prerelease": False,
        "html_url": "https://github.com/o/r/releases/tag/1.23.86",
        "published_at": "2026-10-18T13:21:41Z",
        "created_at": "2026-10-18T13:17:06Z",
        "body": "# 南网协议解析工具 1.23.86\n\n## ⬇️ 下载\n\n| 文件 | 说明 |\n| --- | --- |\n| `x.exe` | 免安装 |\n",
        "assets": [
            {
                "name": "v1.23.86_20261018211215.exe",
                "browser_download_url": "https://github.com/o/r/releases/download/1.23.86/v1.23.86.exe",
                "digest": "sha256:" + "cb4f" + "0" * 60,
            }
        ],
    }
    data.update(over)
    return data


def test_default_source_is_github():
    """默认更新源已改为作者 GitHub Release（用户诉求：默认查 GitHub）。"""
    assert DEFAULT_UPDATE_CONFIG["source_type"] == "github"
    assert DEFAULT_UPDATE_CONFIG["github_owner"] == "Liruitao1993"
    assert DEFAULT_UPDATE_CONFIG["github_repo"] == "South_Network_Protocol_Analysis_Tool"
    # 无需鉴权的公开接口，超时给足（GitHub 国内直连偶尔慢）
    assert GITHUB_RELEASE_TIMEOUT >= 10


def test_parse_github_repo_url():
    base = "https://github.com/Liruitao1993/South_Network_Protocol_Analysis_Tool"
    want = {
        "github_owner": "Liruitao1993",
        "github_repo": "South_Network_Protocol_Analysis_Tool",
    }
    assert parse_github_repo_url(base) == want
    assert parse_github_repo_url(base + "/") == want
    assert parse_github_repo_url(base + "/releases/tag/1.23.86") == want
    assert parse_github_repo_url(base + ".git") == want
    assert parse_github_repo_url("http://www.github.com/o/r?x=1#y") == {
        "github_owner": "o",
        "github_repo": "r",
    }
    # 非 GitHub / 空值 → 空字典（调用方据此保留默认值）
    assert parse_github_repo_url("https://gitee.com/o/r") == {}
    assert parse_github_repo_url("") == {}
    assert parse_github_repo_url(None) == {}


def test_merge_update_config_repo_url_and_priority():
    """repo_url 只作为**默认值**；用户配置与空串回落的优先级要正确。"""
    url = "https://github.com/Other/repo"
    merged = merge_update_config(None, repo_url=url)
    assert merged["github_owner"] == "Other" and merged["github_repo"] == "repo"

    # 用户显式配置优先于 repo_url
    merged = merge_update_config(
        {"source_type": "github", "github_owner": "Me", "github_repo": "Mine"},
        repo_url=url,
    )
    assert (merged["github_owner"], merged["github_repo"]) == ("Me", "Mine")

    # 空串视为「未设置」→ 回落到 repo_url（设置对话框清空输入框 = 用默认）
    merged = merge_update_config(
        {"source_type": "github", "github_owner": "", "github_repo": "   "},
        repo_url=url,
    )
    assert (merged["github_owner"], merged["github_repo"]) == ("Other", "repo")

    # 不给 repo_url 也要有内置默认（离了 main_gui 也能独立工作）
    merged = merge_update_config({"enabled": False})
    assert merged["github_owner"] == DEFAULT_UPDATE_CONFIG["github_owner"]
    assert merged["enabled"] is False


def test_describe_source():
    assert describe_source({"source_type": "github"}).startswith("GitHub Releases（Liruitao1993/")
    assert "Gitee" in describe_source(
        {"source_type": "gitee", "gitee_owner": "a", "gitee_repo": "b"}
    )
    assert "Gitee" in describe_source({"source_type": "gitee"})
    assert "私有" in describe_source({"source_type": "private", "private_url": "http://x/v.json"})
    assert "私有" in describe_source({"source_type": "private"})


def test_describe_http_status():
    assert "404" in describe_http_status(404) and "Release" in describe_http_status(404)
    assert "鉴权" in describe_http_status(401)
    assert "频率" in describe_http_status(403)
    assert "频率" in describe_http_status(429)
    assert "服务器错误" in describe_http_status(503)
    assert "HTTP 418" in describe_http_status(418)
    assert describe_http_status(None)  # 不给栈，也要给一句人话


# ── GitHub 源：Release 解析 ──────────────────────────────
def test_extract_github_release_picks_exe_and_digest():
    info = _extract_release_info(github_release_payload())
    assert info["version"] == "1.23.86"
    assert info["url"].endswith("v1.23.86.exe")
    assert info["asset_name"] == "v1.23.86_20261018211215.exe"
    # digest: sha256:… → 裸 sha256（供 Opdater.verify 直接用）
    assert info["sha256"] == "cb4f" + "0" * 60
    assert info["html_url"].endswith("/releases/tag/1.23.86")
    assert info["published_at"].startswith("2026-10-18")
    # 更新说明来自 body（markdown），GUI 负责渲染
    assert "南网协议解析工具 1.23.86" in info["notes"]


def test_extract_github_release_skips_source_archive():
    """源码压缩包即便名字里带 exe 关键字也不能被当成安装包。"""
    data = github_release_payload()
    data["assets"] = [
        {"name": "source code.exe.zip", "browser_download_url": "https://x/src.zip"},
        {"name": "app.exe", "browser_download_url": "https://x/app.exe"},
    ]
    info = _extract_release_info(data)
    assert info["url"] == "https://x/app.exe"
    assert info["asset_name"] == "app.exe"


def test_extract_github_release_without_asset_raises():
    """没有安装包资产 → 报错（GUI 会提示该版本不可下载），不能拿 html_url 当下载地址。"""
    data = github_release_payload()
    data["assets"] = []
    data.pop("url", None)
    try:
        _extract_release_info(data)
        assert False, "应抛 UpdateSourceError"
    except Exception as e:
        assert "没有可下载的安装包资产" in str(e)


def test_extract_release_never_uses_api_endpoint_as_download_url():
    """**回归（1.23.87 独立验证发现的阻塞缺陷）**：GitHub release 对象顶层 `url`
    是 API 端点；无资产的旧版本（实测 1.8.2 就是这个形态）曾被它当成下载地址
    ⇒ 会把接口 JSON 当新 exe 覆盖自身。现在必须报错。"""
    data = github_release_payload(
        tag_name="1.8.2",
        name="1.8.2",
        assets=[],
        # GitHub 真实响应里就有这个字段（指向 API 自身，不是资产直链）
        url="https://api.github.com/repos/Liruitao1993/South_Network_Protocol_Analysis_Tool/releases/123456",
        assets_url="https://api.github.com/repos/o/r/releases/123456/assets",
    )
    try:
        info = _extract_release_info(data)
        assert False, f"API 端点不能被当下载地址，却得到 {info['url']}"
    except Exception as e:
        assert "没有可下载的安装包资产" in str(e)

    # 顶层 browser_download_url 若指向端点也要拒绝
    data2 = github_release_payload(assets=[])
    data2["browser_download_url"] = "https://gitee.com/api/v5/repos/o/r/releases/1"
    try:
        _extract_release_info(data2)
        assert False, "Gitee 端点同样不能当下载地址"
    except Exception:
        pass


def test_extract_private_json_url_still_allowed():
    """私有 version.json（非 release 对象）的顶层 url 必须继续可用。"""
    info = _extract_release_info(
        {"version": "3.0.0", "url": "http://10.0.0.8/app.exe", "notes": "内网"}
    )
    assert info["url"] == "http://10.0.0.8/app.exe"
    info2 = _extract_release_info(
        {"version": "3.0.1", "download_url": "http://10.0.0.8/b.exe"}
    )
    assert info2["url"] == "http://10.0.0.8/b.exe"


def test_fetch_all_releases_skips_release_without_asset():
    """版本列表必须剔除「没有安装包资产」的版本（不能选到不可下载的版本）。"""
    payload = [
        github_release_payload(tag_name="1.23.86", name="1.23.86"),
        github_release_payload(
            tag_name="1.8.2",
            name="1.8.2",
            assets=[],
            url="https://api.github.com/repos/o/r/releases/9",
        ),
    ]
    rels = VersionChecker(
        merge_update_config({}), http_get=lambda url: json.dumps(payload)
    ).fetch_all_releases()
    assert [r["version"] for r in rels] == ["1.23.86"]
    assert all("api.github.com" not in r["url"] for r in rels)


def test_is_pe_executable_guard():
    """替换 exe 前的兜底：JSON/HTML/小文件都不是可执行程序。"""
    from auto_updater import MIN_PE_BYTES, is_pe_executable

    tmp = Path(tempfile.gettempdir()) / "pe_guard_test"
    tmp.mkdir(exist_ok=True)
    exe = tmp / "fake.exe"
    exe.write_bytes(b"MZ" + b"\x00" * MIN_PE_BYTES)
    assert is_pe_executable(exe) is True

    js = tmp / "release.json"
    js.write_bytes(json.dumps(github_release_payload()).encode("utf-8"))
    assert is_pe_executable(js) is False  # 接口 JSON 想覆盖 exe？拦住

    html = tmp / "login.html"
    html.write_bytes(b"<html><body>please sign in" + b"x" * MIN_PE_BYTES + b"</body></html>")
    assert is_pe_executable(html) is False

    tiny = tmp / "tiny.exe"
    tiny.write_bytes(b"MZ")
    assert is_pe_executable(tiny) is False  # 迷你假 MZ 也不算

    assert is_pe_executable(tmp / "missing.exe") is False
    assert is_pe_executable(tmp) is False  # 目录
    for f in (exe, js, html, tiny):
        f.unlink()
    tmp.rmdir()


def test_github_fields_for_save_collapses_defaults():
    """设置对话框保存：与默认相同的 owner/repo 必须存空串，否则改 AUTHOR_GITHUB_URL 会失效。"""
    from auto_updater import github_fields_for_save

    url = "https://github.com/Liruitao1993/South_Network_Protocol_Analysis_Tool"
    # 用户没改（等于默认）→ 存空，继续跟随 AUTHOR_GITHUB_URL
    assert github_fields_for_save("Liruitao1993", "South_Network_Protocol_Analysis_Tool", url) == {
        "github_owner": "",
        "github_repo": "",
    }
    # 用户改过 → 原样保存
    assert github_fields_for_save("Me", "Mine", url) == {
        "github_owner": "Me",
        "github_repo": "Mine",
    }
    # 只改一个：另一个仍回落默认
    got = github_fields_for_save("Me", "South_Network_Protocol_Analysis_Tool", url)
    assert got["github_owner"] == "Me" and got["github_repo"] == ""
    # 无 repo_url 时以内置常量为默认
    assert github_fields_for_save("Liruitao1993", "South_Network_Protocol_Analysis_Tool") == {
        "github_owner": "",
        "github_repo": "",
    }
    # 存空后合并回去仍是可用配置（不是空 owner 去打接口）
    merged = merge_update_config(
        {"source_type": "github", **github_fields_for_save("Liruitao1993", "South_Network_Protocol_Analysis_Tool", url)},
        repo_url=url,
    )
    assert merged["github_owner"] == "Liruitao1993"


def test_safe_file_stem():
    """tag 里的路径分隔符/非法字符不能拼进临时文件名（否则下载报 OSError）。"""
    from auto_updater import safe_file_stem

    assert safe_file_stem("1.23.86") == "1.23.86"
    assert safe_file_stem("release/1.24") == "release_1.24"
    assert safe_file_stem("v1:24*?") == "v1_24__"
    assert "/" not in safe_file_stem("a/b/c") and "\\" not in safe_file_stem("a\\b")
    assert safe_file_stem("") == "new"
    assert safe_file_stem(None) == "new"
    assert safe_file_stem("   ") == "new"
    assert safe_file_stem("...") == "new"
    # 生成的路径确实落在临时目录内（不越界成子目录）
    stem = safe_file_stem("release/1.24")
    assert Path(tempfile.gettempdir(), f"x_{stem}.exe").parent == Path(tempfile.gettempdir())


def test_digest_to_sha256():
    assert _digest_to_sha256("sha256:" + "A" * 64) == "a" * 64
    assert _digest_to_sha256("A" * 64) == "a" * 64
    assert _digest_to_sha256("sha512:" + "a" * 128) == ""  # 非 sha256 不用
    assert _digest_to_sha256("sha256:xyz") == ""
    assert _digest_to_sha256("") == ""
    assert _digest_to_sha256(None) == ""


def test_extract_private_sha256_still_wins():
    """私有 version.json 顶层 sha256 优先于资产 digest（老源行为不变）。"""
    data = {
        "version": "1.2.0",
        "url": "http://10.0.0.8/app.exe",
        "sha256": "B" * 64,
        "assets": [{"name": "a.exe", "browser_download_url": "http://x/a.exe",
                    "digest": "sha256:" + "c" * 64}],
    }
    info = _extract_release_info(data)
    assert info["sha256"] == "b" * 64


# ── GitHub 源：地址构造 ──────────────────────────────────
def test_checker_github_urls():
    cfg = merge_update_config(
        {}, repo_url="https://github.com/Liruitao1993/South_Network_Protocol_Analysis_Tool"
    )
    c = VersionChecker(cfg)
    assert c.build_url() == (
        "https://api.github.com/repos/Liruitao1993/"
        "South_Network_Protocol_Analysis_Tool/releases/latest"
    )
    assert c.build_list_url() == (
        "https://api.github.com/repos/Liruitao1993/"
        "South_Network_Protocol_Analysis_Tool/releases?per_page=30"
    )
    assert c.release_page_url().endswith("/South_Network_Protocol_Analysis_Tool/releases")
    assert default_github_api("o", "r").endswith("/repos/o/r/releases/latest")
    assert default_github_releases_api("o", "r", 5).endswith("?per_page=5")


def test_checker_gitee_still_supported():
    c = VersionChecker({"source_type": "gitee", "gitee_owner": "a", "gitee_repo": "b"})
    assert c.build_url() == "https://gitee.com/api/v5/repos/a/b/releases/latest"
    assert c.build_list_url() == "https://gitee.com/api/v5/repos/a/b/releases"
    assert c.release_page_url() == "https://gitee.com/a/b/releases"


def test_checker_private_has_no_list():
    c = VersionChecker({"source_type": "private", "private_url": "http://x/v.json"})
    assert c.build_url() == "http://x/v.json"
    assert c.release_page_url() == ""
    try:
        c.build_list_url()
        assert False, "私有源没有版本列表"
    except Exception:
        pass


def test_checker_missing_github_repo_raises_readable_error():
    # 显式 source_type=github 但 owner/repo 都解析不出来 → 报「未配置」
    c = VersionChecker.__new__(VersionChecker)
    c.source_config = {"source_type": "github", "github_owner": "", "github_repo": ""}
    for method in (c.build_url, c.build_list_url, c.release_page_url):
        try:
            method()
            assert False, f"{method.__name__} 应抛 UpdateSourceError"
        except Exception as e:
            assert "github_owner" in str(e)


# ── GitHub 源：检查与版本列表 ────────────────────────────
def test_check_for_update_github_reports_notes():
    cfg = merge_update_config({})
    res = check_for_update(
        "1.23.74", cfg, http_get=lambda url: json.dumps(github_release_payload())
    )
    assert res["needed"] is True and res["error"] is None
    assert res["latest"]["version"] == "1.23.86"
    assert res["latest"]["notes"]  # 更新说明必须带出来（对话框要展示）


def test_check_for_update_github_same_version_no_update():
    cfg = merge_update_config({})
    res = check_for_update(
        "1.23.86", cfg, http_get=lambda url: json.dumps(github_release_payload())
    )
    assert res["needed"] is False


def test_fetch_all_releases_github_sorted_and_filters():
    """版本列表：降序、草稿剔除、无安装包剔除、预发布标记保留。"""
    payload = [
        github_release_payload(tag_name="1.23.80", name="1.23.80"),
        github_release_payload(tag_name="1.23.86", name="1.23.86", prerelease=True),
        github_release_payload(tag_name="1.23.90", name="1.23.90", draft=True),
        github_release_payload(tag_name="1.23.84", name="1.23.84", assets=[]),
        github_release_payload(tag_name="1.23.87", name="1.23.87"),
    ]
    checker = VersionChecker(merge_update_config({}), http_get=lambda url: json.dumps(payload))
    rels = checker.fetch_all_releases()
    assert [r["version"] for r in rels] == ["1.23.87", "1.23.86", "1.23.80"]
    assert rels[1]["prerelease"] is True
    assert rels[0]["created_at"].startswith("2026-10-18")


def test_fetch_all_releases_private_falls_back_to_latest():
    checker = VersionChecker(
        {"source_type": "private", "private_url": "http://x/ver.json"},
        http_get=lambda url: json.dumps({"version": "2.0.0", "url": "http://x/a.exe"}),
    )
    rels = checker.fetch_all_releases()
    assert len(rels) == 1 and rels[0]["version"] == "2.0.0"


def test_fetch_all_releases_rejects_non_array():
    checker = VersionChecker(
        merge_update_config({}), http_get=lambda url: json.dumps({"message": "Not Found"})
    )
    try:
        checker.fetch_all_releases()
        assert False, "非数组应报错"
    except Exception as e:
        assert "数组" in str(e)


def test_check_for_update_surfaces_status_message():
    """更新源报错（404 等）时，error 里应是中文人话，不是英文 urllib 栈。"""
    from auto_updater import UpdateSourceError

    def bad_get(url):
        raise UpdateSourceError(describe_http_status(404))

    res = check_for_update("1.0.0", merge_update_config({}), http_get=bad_get)
    assert res["needed"] is False
    assert "404" in res["error"] and "Release" in res["error"]


# ── 更新说明摘要（状态栏/提示用） ────────────────────────
def test_summarize_notes_strips_markdown():
    notes = "# 标题\n\n> 引用\n\n| 文件 | 说明 |\n| --- | --- |\n| `a.exe` | 免安装 |\n\n**要点**\n"
    s = summarize_notes(notes, 60)
    assert "#" not in s and "**" not in s and "`" not in s and "|" not in s
    assert "标题" in s and "要点" in s
    assert len(s) <= 61  # 截断到 limit（可能带一个省略号）
    assert summarize_notes("") == ""
    assert summarize_notes(None) == ""
    # 长说明必须被截断并带省略号
    assert summarize_notes("甲" * 500, 20).endswith("…")


def run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  OK  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"ERR   {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return failures


if __name__ == "__main__":
    sys.exit(1 if run_all() else 0)