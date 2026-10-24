# -*- coding: utf-8 -*-
"""GitHub Issue 反馈功能回归（1.23.94）。

覆盖点：
  1. **与仓库模板对拍** —— `FORM_PROTOCOL_OPTIONS` 必须与 `.github/ISSUE_TEMPLATE/bug.yml`
     里 protocol 下拉的选项**逐字一致**（GitHub 下拉预填要求完全相同才会选中）；
     `FORM_FIELDS` 必须与两张 yml 的字段 id 集合一致。模板改了这边没跟上 → 直接变红。
  2. **正文/标题拼装** —— 段标题与表单 label 一致、空段不占位、标题前缀 [Bug]/[Feature]。
  3. **API 建单** —— 成功返回编号与链接；401/403/404/422/429 翻译成中文；
     标签不存在导致 422 时**自动去掉 labels 重试一次**（不能因为标签建不出 issue）。
  4. **浏览器预填 URL** —— template 指对表单、字段 id 映射正确、中文与换行被正确编码。
  5. **令牌优先级** —— 显式 > 环境变量 > config.json；令牌落 config.json 后能被脱敏。
  6. **崩溃摘要脱敏** —— 本机路径行被替换（不能把 Windows 用户名发到公开仓库）。
  7. **offscreen 对话框** —— 两种形态、预填协议/报文、浏览器兜底按钮、令牌回写。

运行: QT_QPA_PLATFORM=offscreen python -u test/test_github_issue.py
"""

import os
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import github_issue as gi  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / ".github" / "ISSUE_TEMPLATE"


# ── 1. 与仓库模板对拍 ──────────────────────────────────────────────

def _parse_yml_protocol_options(text: str):
    """从 bug.yml 里抠出 protocol 下拉的选项文本（不引 yaml 依赖）。

    结构（YAML 缩进敏感，故按「行内容 + 出现顺序」判定，不做通用 YAML 解析）：
        - type: dropdown
          id: protocol
          attributes:
            options:
              - 0 南网协议
              - ...
    """
    opts = []
    in_protocol = False
    in_options = False
    for raw in text.splitlines():
        line = raw.strip()
        if not in_protocol:
            if line == "id: protocol":
                in_protocol = True
            continue
        if not in_options:
            if line.startswith("options:"):
                in_options = True
            continue
        if line.startswith("- "):
            opts.append(line[2:].strip())
        elif line:
            break                      # 遇到下一个键（validations: 等）即结束
    return opts


def test_form_protocol_options_match_bug_yml():
    path = TEMPLATE_DIR / "bug.yml"
    assert path.exists(), f"缺少 {path}"
    expected = _parse_yml_protocol_options(path.read_text(encoding="utf-8"))
    assert expected, "未能从 bug.yml 解析出 protocol 选项（解析器或模板结构变了）"
    assert gi.FORM_PROTOCOL_OPTIONS == expected, (
        "FORM_PROTOCOL_OPTIONS 与 bug.yml 的 protocol 下拉不一致：\n"
        f"  代码：{gi.FORM_PROTOCOL_OPTIONS}\n"
        f"  模板：{expected}"
    )


def test_form_protocol_options_cover_all_protocols():
    """16 种协议（0~15）+ 「与具体协议无关」，与项目协议注册表口径一致。"""
    import protocol_registry

    count = protocol_registry.protocol_count()
    assert count == 16, count
    assert len(gi.FORM_PROTOCOL_OPTIONS) == count + 1
    # 每个协议索引都能取到对应选项
    for index in range(count):
        option = gi.protocol_option(index)
        assert option.startswith(f"{index} "), (index, option)


def test_form_fields_match_yml_ids():
    """FORM_FIELDS 的字段 id 必须真实存在于对应 yml 模板里。"""
    for kind, template in (("bug", "bug.yml"), ("feature", "feature.yml")):
        text = (TEMPLATE_DIR / template).read_text(encoding="utf-8")
        for field_id in gi.FORM_FIELDS[kind]:
            assert f"id: {field_id}" in text, (kind, field_id, template)


def test_issue_kinds_labels_exist_in_repo_template():
    """标签名要与模板里声明的一致（标签不存在时 GitHub 会 422）。"""
    bug = (TEMPLATE_DIR / "bug.yml").read_text(encoding="utf-8")
    feature = (TEMPLATE_DIR / "feature.yml").read_text(encoding="utf-8")
    assert "bug" in gi.ISSUE_KINDS["bug"]["labels"]
    assert "enhancement" in gi.ISSUE_KINDS["feature"]["labels"]
    assert 'labels: ["bug"]' in bug
    assert 'labels: ["enhancement"]' in feature


# ── 2. 正文与标题 ─────────────────────────────────────────────────

def test_build_title_has_prefix():
    assert gi.build_issue_title("bug", "长度域越界") == "[Bug] 长度域越界"
    assert gi.build_issue_title("feature", "支持新协议") == "[Feature] 支持新协议"
    # 空白摘要也不能返回空标题（GitHub 会 422）
    assert gi.build_issue_title("bug", "   ").strip() != ""


def test_build_body_skips_empty_sections():
    body = gi.build_issue_body(
        "bug",
        version="1.23.94",
        protocol="9 新一代载波协议",
        frame="11 01 01 00",
        expected="应解析出 OFDMA",
        actual="解析不出来",
        steps="",
        env="Windows / exe",
        contact="",
    )
    assert "### 工具版本" in body
    assert "1.23.94" in body
    assert "### 相关协议" in body
    assert "### 报文（十六进制）" in body
    assert "### 期望结果" in body
    assert "### 实际结果" in body
    assert "### 运行环境" in body
    assert "### 复现步骤" not in body      # 空段不占位
    assert "### 联系方式" not in body


def test_build_body_feature_sections():
    body = gi.build_issue_body(
        "feature",
        steps="现场要读新台体的规约",
        expected="希望能解析该台体",
        frame="68 01",
    )
    assert "### 使用场景" in body
    assert "### 你期望的样子" in body
    assert "### 报文 / 协议资料" in body


def test_build_body_never_empty():
    body = gi.build_issue_body("bug")
    assert body.strip() != ""


# ── 3. API 建单 ───────────────────────────────────────────────────

def _fake_post(status: int, body: str):
    calls = []

    def post(url, payload, token, timeout):
        calls.append((url, payload, token, timeout))
        return status, body

    post.calls = calls
    return post


def test_submit_issue_success():
    post = _fake_post(
        201,
        '{"number": 42, "html_url": "https://github.com/o/r/issues/42",'
        ' "title": "[Bug] x", "labels": [{"name": "bug"}]}',
    )
    result = gi.submit_issue("o", "r", "tok", "[Bug] x", "body", ["bug"],
                              http_post=post)
    assert result["number"] == 42
    assert result["html_url"].endswith("/issues/42")
    assert result["labels"] == ["bug"]
    url, payload, token, _ = post.calls[0]
    assert url == "https://api.github.com/repos/o/r/issues"
    assert payload["title"] == "[Bug] x"
    assert payload["labels"] == ["bug"]
    assert token == "tok"


def test_submit_issue_requires_token():
    try:
        gi.submit_issue("o", "r", "", "t", "b", http_post=_fake_post(201, "{}"))
    except gi.IssueSubmitError as exc:
        assert "令牌" in str(exc)
    else:
        raise AssertionError("空令牌应当抛 IssueSubmitError")


def test_submit_issue_requires_title():
    try:
        gi.submit_issue("o", "r", "tok", "  ", "b", http_post=_fake_post(201, "{}"))
    except gi.IssueSubmitError as exc:
        assert "标题" in str(exc)
    else:
        raise AssertionError("空标题应当抛 IssueSubmitError")


def test_submit_issue_error_translated():
    for status, keyword in (
        (401, "令牌"),
        (403, "权限"),
        (404, "仓库"),
        (422, "不合法"),
        (429, "频繁"),
        (500, "服务器"),
    ):
        try:
            gi.submit_issue("o", "r", "tok", "t", "b",
                            http_post=_fake_post(status, '{"message": "raw"}'))
        except gi.IssueSubmitError as exc:
            assert keyword in str(exc), (status, str(exc))
        else:
            raise AssertionError(f"HTTP {status} 应当抛 IssueSubmitError")


def test_submit_issue_retries_without_labels_on_422():
    """标签不存在导致 422 时，自动去掉 labels 重试一次，issue 必须建出来。"""
    calls = []

    def post(url, payload, token, timeout):
        calls.append(payload)
        if "labels" in payload:
            return 422, '{"message": "Validation Failed", "errors": [{"field": "labels", "message": "not found"}]}'
        return 201, '{"number": 7, "html_url": "https://github.com/o/r/issues/7"}'

    result = gi.submit_issue("o", "r", "tok", "t", "b", ["ghost-label"],
                              http_post=post)
    assert result["number"] == 7
    assert len(calls) == 2
    assert "labels" in calls[0]
    assert "labels" not in calls[1], "重试必须去掉 labels"


def test_submit_issue_network_error():
    def post(url, payload, token, timeout):
        raise gi.IssueSubmitError("网络请求失败：boom")

    try:
        gi.submit_issue("o", "r", "tok", "t", "b", http_post=post)
    except gi.IssueSubmitError as exc:
        assert "网络" in str(exc)
    else:
        raise AssertionError("网络异常应当抛 IssueSubmitError")


def test_describe_http_status_covers_common_codes():
    assert "401" in gi.describe_http_status(401)
    assert "权限" in gi.describe_http_status(403)
    assert "仓库" in gi.describe_http_status(404)
    assert "不合法" in gi.describe_http_status(422)
    assert "频繁" in gi.describe_http_status(429)
    assert "服务器" in gi.describe_http_status(500)
    # 非整数输入走「无法识别」分支
    assert "无法识别" in gi.describe_http_status("abc")


# ── 4. 浏览器预填 URL ─────────────────────────────────────────────

def test_prefill_url_uses_right_template():
    url = gi.build_prefill_url("o", "r", "bug", {"version": "1.23.94"})
    assert url.startswith("https://github.com/o/r/issues/new?")
    assert "template=bug.yml" in url
    url = gi.build_prefill_url("o", "r", "feature", {"scenario": "s"})
    assert "template=feature.yml" in url


def test_prefill_url_encodes_fields_by_id():
    url = gi.build_prefill_url(
        "o", "r", "bug",
        {
            "version": "1.23.94",
            "protocol": "9 新一代载波协议",
            "frame": "11 01 01 00",
            "expected": "第一行\n第二行",
        },
    )
    query = urllib.parse.urlparse(url).query
    params = dict(urllib.parse.parse_qsl(query))
    assert params["version"] == "1.23.94"
    assert params["protocol"] == "9 新一代载波协议"
    assert params["frame"] == "11 01 01 00"
    assert params["expected"] == "第一行\n第二行"
    # 空字段不应出现在 URL 里
    assert "steps" not in params
    assert "contact" not in params


def test_prefill_url_only_uses_known_field_ids():
    """未知字段 id 必须被忽略（不能把内部字段名漏到 GitHub 表单里）。"""
    url = gi.build_prefill_url(
        "o", "r", "bug", {"version": "1", "bogus_field": "x", "contact": "qq"}
    )
    assert "bogus_field" not in url
    assert "contact=qq" in url


# ── 5. 令牌与配置 ─────────────────────────────────────────────────

def test_token_priority():
    """优先级：显式 > 环境变量 > config.json。

    注意：开发机环境里**可能真的存在 GH_TOKEN / GITHUB_TOKEN**（本机实测就有），
    故测试必须先把两个变量都摘掉再断言，否则会被真实令牌干扰。
    """
    import tempfile
    import json as _json

    saved = {name: os.environ.pop(name, None) for name in gi.TOKEN_ENV_VARS}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config.json"
            cfg.write_text(
                _json.dumps({"github_issue": {"token": "from-config"}}),
                encoding="utf-8",
            )
            # 环境变量优先于 config.json
            os.environ["GITHUB_TOKEN"] = "from-env"
            assert gi.resolve_token(cfg) == "from-env"
            # 显式传入优先于环境变量
            assert gi.resolve_token(cfg, "explicit") == "explicit"
            # 环境变量没有时回落 config.json
            os.environ.pop("GITHUB_TOKEN", None)
            os.environ.pop("GH_TOKEN", None)
            assert gi.resolve_token(cfg) == "from-config"
            # 都没有时为空串（不是 None）
            empty_cfg = Path(tmp) / "empty.json"
            assert gi.resolve_token(empty_cfg) == ""
    finally:
        for name, value in saved.items():
            if value is not None:
                os.environ[name] = value
            else:
                os.environ.pop(name, None)


def test_save_and_load_issue_config():
    import json as _json
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "config.json"
        cfg.write_text(_json.dumps({"serial": {"port": "COM3"}}), encoding="utf-8")
        assert gi.save_issue_config(cfg, {"token": "abc"})
        data = _json.loads(cfg.read_text(encoding="utf-8"))
        assert data["github_issue"]["token"] == "abc"
        assert data["serial"]["port"] == "COM3", "保存不得丢掉其它配置段"
        assert gi.load_issue_config(cfg)["token"] == "abc"


def test_load_issue_config_tolerates_broken_file():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "config.json"
        cfg.write_text("{not json", encoding="utf-8")
        assert gi.load_issue_config(cfg) == {}


def test_token_is_redacted_in_diagnostics():
    """令牌写进 config.json 后，诊断包必须把它脱敏（不能随包泄露）。"""
    import json as _json
    import tempfile

    import diagnostics

    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "config.json"
        cfg.write_text(
            _json.dumps({"github_issue": {"token": "super-secret-token"}},),
            encoding="utf-8",
        )
        section = gi.load_issue_config(cfg)
        section["token"] = "super-secret-token"
        redacted = diagnostics.redact({"github_issue": section})
        assert redacted["github_issue"]["token"] == diagnostics.REDACTED


def test_resolve_owner_repo_from_url():
    owner, repo = gi.resolve_owner_repo(
        "https://github.com/Liruitao1993/South_Network_Protocol_Analysis_Tool"
    )
    assert owner == "Liruitao1993"
    assert repo == "South_Network_Protocol_Analysis_Tool"
    # 解析不出时回落到内置默认值，不返回空串
    owner2, repo2 = gi.resolve_owner_repo("not a url")
    assert owner2 and repo2


def test_mask_token():
    assert gi.mask_token("") == ""
    assert gi.mask_token("abc") == "***"
    masked = gi.mask_token("github_pat_1234567890abcdef")
    assert "…" in masked
    assert "1234567890abcdef" not in masked


# ── 6. 崩溃摘要脱敏 ───────────────────────────────────────────────

def test_sanitize_crash_summary_hides_paths():
    text = (
        "崩溃报告\n"
        "可执行文件：C:\\Users\\zhangsan\\AppData\\Local\\tool.exe\n"
        "工作目录：C:\\Users\\zhangsan\\Desktop\n"
        "异常类型：ValueError\n"
    )
    out = gi.sanitize_crash_summary(text)
    assert "zhangsan" not in out
    assert "异常类型：ValueError" in out
    assert "本机路径已隐藏" in out


def test_collect_env_info_has_no_personal_data():
    import getpass

    info = gi.collect_env_info("1.23.94", "2026-10-22")
    assert "1.23.94" in info
    assert "exe" in info or "源码运行" in info
    user = getpass.getuser()
    assert user not in info, "环境信息不得包含用户名"


# ── 7. offscreen 对话框 ───────────────────────────────────────────

def test_dialog_smoke():
    from PySide6.QtWidgets import QApplication

    from github_issue_dialog import GitHubIssueDialog

    _app = QApplication.instance() or QApplication([])
    dlg = GitHubIssueDialog(
        parent=None,
        owner="Liruitao1993",
        repo="South_Network_Protocol_Analysis_Tool",
        token="tok",
        app_version="1.23.94",
        build_date="2026-10-22",
        protocol_option="9 新一代载波协议",
        frame_hex="11 01 01 00 00 00 01 00 01 00 00",
    )
    try:
        # 协议与报文预填到位
        assert dlg.protocol_combo.currentText() == "9 新一代载波协议"
        assert "11 01 01 00" in dlg.frame_edit.toPlainText()
        # 环境信息自动收集且含版本
        assert "1.23.94" in dlg.env_edit.toPlainText()
        # 令牌掩码显示
        assert dlg.token_edit.echoMode() == dlg.token_edit.EchoMode.Password
        # 默认是 Bug 形态，切换到建议形态会换页
        assert dlg.current_kind() == "bug"
        assert dlg.stack.currentIndex() == 0
        dlg.kind_combo.setCurrentIndex(1)
        assert dlg.current_kind() == "feature"
        assert dlg.stack.currentIndex() == 1
        # 两种形态都能拼出正文
        dlg.kind_combo.setCurrentIndex(0)
        dlg.actual_edit.setPlainText("解析不出来")
        assert "### 实际结果" in dlg._build_body()
        assert dlg._build_title().startswith("[Bug] ")
    finally:
        dlg.close()
        dlg.deleteLater()


def test_dialog_crash_summary_prefilled():
    from PySide6.QtWidgets import QApplication

    from github_issue_dialog import GitHubIssueDialog

    _app = QApplication.instance() or QApplication([])
    dlg = GitHubIssueDialog(
        parent=None,
        owner="o",
        repo="r",
        app_version="1.23.94",
        crash_summary="异常类型：ValueError\n可执行文件：C:\\Users\\zhangsan\\x.exe",
    )
    try:
        text = dlg.actual_edit.toPlainText()
        assert "ValueError" in text
        assert "zhangsan" not in text, "崩溃摘要里的本机路径必须脱敏"
    finally:
        dlg.close()
        dlg.deleteLater()


def test_dialog_browser_fallback_opens_url():
    from unittest.mock import patch

    from PySide6.QtWidgets import QApplication

    from github_issue_dialog import GitHubIssueDialog

    _app = QApplication.instance() or QApplication([])
    dlg = GitHubIssueDialog(parent=None, owner="o", repo="r", app_version="1.23.94")
    try:
        with patch("github_issue_dialog.QDesktopServices.openUrl", return_value=True) as mocked:
            dlg._on_open_browser()
        assert mocked.called, "浏览器兜底应调用 openUrl"
        url = mocked.call_args[0][0].toString()
        assert "template=bug.yml" in url
        assert dlg.status_label.text().startswith("已打开 GitHub 表单")
    finally:
        dlg.close()
        dlg.deleteLater()


def test_dialog_submit_requires_token():
    from PySide6.QtWidgets import QApplication

    from github_issue_dialog import GitHubIssueDialog

    _app = QApplication.instance() or QApplication([])
    dlg = GitHubIssueDialog(parent=None, owner="o", repo="r", token="")
    try:
        dlg._on_submit()
        assert "令牌" in dlg.status_label.text()
        assert dlg._reply is None, "没有令牌时不应发起网络请求"
    finally:
        dlg.close()
        dlg.deleteLater()


def test_dialog_persist_token():
    from PySide6.QtWidgets import QApplication

    from github_issue_dialog import GitHubIssueDialog

    _app = QApplication.instance() or QApplication([])
    import tempfile
    import json as _json

    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "config.json"
        cfg.write_text(_json.dumps({}), encoding="utf-8")
        dlg = GitHubIssueDialog(parent=None, owner="o", repo="r", config_path=cfg)
        try:
            dlg.token_edit.setText("new-token")
            assert dlg.persist_token() is True
            data = _json.loads(cfg.read_text(encoding="utf-8"))
            assert data["github_issue"]["token"] == "new-token"
        finally:
            dlg.close()
            dlg.deleteLater()


# ── 8. 主程序接线守卫 ─────────────────────────────────────────────

def test_main_gui_wiring():
    """菜单入口与崩溃提交入口必须真实存在（防止改版时被误删）。"""
    source = (ROOT / "main_gui.py").read_text(encoding="utf-8")
    assert "提交问题到 GitHub" in source
    assert "def _show_github_issue_dialog" in source
    assert "def _report_crash_to_github" in source
    assert "github_issue_act.triggered.connect(self._show_github_issue_dialog)" in source
    assert "提交崩溃报告到 GitHub" in source


def run_all():
    tests = [
        v for k, v in sorted(globals().items())
        if k.startswith("test_") and callable(v)
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"  OK  {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"ERR   {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return failures


if __name__ == "__main__":
    sys.exit(1 if run_all() else 0)
