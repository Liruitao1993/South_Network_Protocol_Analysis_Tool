# -*- coding: utf-8 -*-
"""GitHub Issue 提交（纯逻辑，无 Qt，可被独立测试）。

背景：作者希望「遇到问题之后自动把问题提交到 GitHub 的 Issue」。本模块把这件事拆成
**两条通道**，由调用方（GUI）按「有没有令牌」择一：

1. **API 直连**（首选，真正的"自动"）：用 GitHub REST API ``POST /repos/{owner}/{repo}/issues``
   建单 —— 令牌需对该仓库有 **Issues: write** 权限（细粒度 PAT）或 ``repo`` 权限（经典 PAT）。
   建单后返回 issue 编号与链接，全程不经过浏览器。
2. **浏览器预填**（兜底，无需任何令牌）：打开 ``/issues/new?template=bug.yml&...``，
   按 **Issue Form 的字段 id** 预填内容，用户在网页上点一次提交即可。
   表单字段 id 与 ``.github/ISSUE_TEMPLATE/*.yml`` 一一对应（见下方 ``FORM_FIELDS``）。

设计要点：
- **不把作者令牌写进 exe**：令牌只从「环境变量」或「本机 config.json」读，
  别人拿到你的 exe 也拿不到你的令牌（也就不能替你在仓库里刷 issue）。
  令牌在本机 config.json 里，``diagnostics.redact`` 会把含 ``token`` 的键脱敏，
  诊断包不会泄露。
- **地址单一来源**：owner/repo 默认由 ``auto_updater.parse_github_repo_url`` 从
  ``main_gui.AUTHOR_GITHUB_URL`` 解析而来，和「关于」按钮、自动升级源同源，
  改地址只改那一处。
- **表单字段 id 与仓库模板强绑定**：``FORM_PROTOCOL_OPTIONS`` 抄的是
  ``.github/ISSUE_TEMPLATE/bug.yml`` 里 protocol 下拉的**逐字**选项文本
  （GitHub 下拉预填要求与选项完全一致才会选中），测试 `test_github_issue.py`
  会拿仓库里的真实 yml 对拍，防止模板改了而这边没跟上。
- **Issue Form 不适用于 API**：API 建的 issue 不会走 YAML 表单，正文由我们自己拼，
  段标题刻意写成与表单一致的 ``### 工具版本`` 等，看起来和网页表单提交的 issue 没差别。

测试：test/test_github_issue.py（纯逻辑 + offscreen 对话框）。
"""

from __future__ import annotations

import json
import os
import platform
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

# ── 常量 ─────────────────────────────────────────────────────────────

GITHUB_API_BASE = "https://api.github.com"
GITHUB_WEB_BASE = "https://github.com"
DEFAULT_TIMEOUT = 15.0

#: 浏览器/服务器对 URL 长度的实际上限（超了会被截断或拒绝）；预留余量
MAX_PREFILL_URL = 6000

#: 细粒度 PAT 需要 Issues: write；经典 PAT 需要 repo 权限
TOKEN_SCOPE_HINT = (
    "令牌需对该仓库有「Issues: write」权限（细粒度 PAT），"
    "或经典 PAT 勾选 repo 权限"
)

#: 两类 issue 对应的表单模板与标签（标签名与仓库现有标签一致）
ISSUE_KINDS: Dict[str, Dict[str, Any]] = {
    "bug": {
        "label": "问题反馈 / Bug report",
        "template": "bug.yml",
        "labels": ["bug"],
        "title_prefix": "[Bug] ",
    },
    "feature": {
        "label": "功能建议 / Feature request",
        "template": "feature.yml",
        "labels": ["enhancement"],
        "title_prefix": "[Feature] ",
    },
}

#: 与 ``.github/ISSUE_TEMPLATE/bug.yml`` 中 protocol 下拉**逐字一致**的选项。
#: GitHub 表单下拉预填要求与选项文本完全相同才会选中，故此处不能改写文案
#: （如「PLC RF 协议」多一个空格、「HDC 1.0」不带「双模互联互通」都不行）。
#: 末项为「与具体协议无关」，用索引 ``-1`` 表示。
FORM_PROTOCOL_OPTIONS: List[str] = [
    "0 南网协议",
    "1 PLC RF 协议",
    "2 HDLC/国网DLMS",
    "3 DLMS-APDU（国网）",
    "4 DLMS Wrapper 裸报文",
    "5 DLMS-APDU 裸报文",
    "6 DLT645-2007",
    "7 国网协议",
    "8 698.45 协议",
    "9 新一代载波协议",
    "10 国网新一代双模",
    "11 HDC 1.0",
    "12 模组化终端功能模块接口",
    "13 依瓦定制645",
    "14 南网上行通信规约",
    "15 Modbus 协议（RTU/TCP）",
    "与具体协议无关（界面 / 系统集成 / 打包）",
]

#: 「与具体协议无关」在 ``FORM_PROTOCOL_OPTIONS`` 中的索引
PROTOCOL_UNRELATED_INDEX = len(FORM_PROTOCOL_OPTIONS) - 1

#: 各类型 issue 的表单字段 id（与仓库 yml 模板一致）
FORM_FIELDS: Dict[str, List[str]] = {
    "bug": ["version", "protocol", "frame", "expected", "actual", "steps", "env", "contact"],
    "feature": ["kind", "scenario", "proposal", "samples"],
}

#: 环境变量里的令牌（``GITHUB_TOKEN`` 是 GitHub 官方约定，``GH_TOKEN`` 是 gh CLI 约定）
TOKEN_ENV_VARS = ("GITHUB_TOKEN", "GH_TOKEN")


class IssueSubmitError(Exception):
    """建单失败（网络错误 / HTTP 状态码 / 返回体异常）。消息面向用户，中文。"""


# ── 小工具 ───────────────────────────────────────────────────────────

def mask_token(token: str) -> str:
    """令牌脱敏显示：只保留前 4 位与后 4 位，中间用省略号（短令牌全掩）。"""
    text = str(token or "").strip()
    if not text:
        return ""
    if len(text) <= 12:
        return "*" * len(text)
    return f"{text[:4]}…{text[-4:]}"


def protocol_option(index: int) -> str:
    """协议索引 → 表单下拉选项文本；越界或负数（除 -1）回落到「与具体协议无关」。"""
    try:
        idx = int(index)
    except (TypeError, ValueError):
        return FORM_PROTOCOL_OPTIONS[PROTOCOL_UNRELATED_INDEX]
    if 0 <= idx < PROTOCOL_UNRELATED_INDEX:
        return FORM_PROTOCOL_OPTIONS[idx]
    return FORM_PROTOCOL_OPTIONS[PROTOCOL_UNRELATED_INDEX]


def collect_env_info(app_version: str = "", build_date: str = "") -> str:
    """运行环境摘要（**不含**用户名 / 机器名等可识别个人的信息）。

    对应 bug.yml 的 env 字段：「Windows 版本 + 是 exe 还是源码运行」。
    """
    system = platform.system() or "未知系统"
    release = platform.release() or ""
    version = platform.version() or ""
    win_part = f"{system} {release}".strip()
    if version:
        win_part = f"{win_part} ({version})"
    running = "exe" if getattr(sys, "frozen", False) else "源码运行"
    parts = [f"{win_part} / {running}"]
    if app_version:
        parts.append(str(app_version))
    if build_date:
        parts.append(f"编译于 {build_date}")
    parts.append(f"Python {platform.python_version()}")
    return " · ".join(parts)


def truncate(text: str, limit: int) -> str:
    """按字符数截断并标注（中文按字计，不按字节）。"""
    value = str(text or "")
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


#: 崩溃报告里含本机路径的行（``C:\Users\<用户名>\...``）—— 提交到**公开仓库**前要去掉，
#: 否则会把提交者的 Windows 用户名暴露给所有人。
_PATH_LINE_PREFIXES = ("可执行文件：", "工作目录：")


def sanitize_crash_summary(text: str) -> str:
    """去掉崩溃报告里的本机路径行（可执行文件 / 工作目录），避免泄露用户名。"""
    lines: List[str] = []
    for line in str(text or "").splitlines():
        if any(line.startswith(prefix) for prefix in _PATH_LINE_PREFIXES):
            lines.append("（本机路径已隐藏）")
            continue
        lines.append(line)
    return "\n".join(lines)



# ── 正文与标题 ───────────────────────────────────────────────────────

def build_issue_title(kind: str, summary: str) -> str:
    """issue 标题：``[Bug] xxx`` / ``[Feature] xxx``（前缀与表单模板的 title 一致）。"""
    spec = ISSUE_KINDS.get(kind, ISSUE_KINDS["bug"])
    text = " ".join(str(summary or "").split())
    if not text:
        text = "（未填写摘要）"
    return f"{spec['title_prefix']}{truncate(text, 120)}"


def build_issue_body(
    kind: str,
    *,
    version: str = "",
    protocol: str = "",
    frame: str = "",
    expected: str = "",
    actual: str = "",
    steps: str = "",
    env: str = "",
    contact: str = "",
) -> str:
    """拼 issue 正文（Markdown）。

    API 建单不经过 YAML 表单，段落标题按表单的 label 写，
    这样在 issue 页面看起来与网页表单提交的完全一致。
    """
    if kind == "feature":
        sections: List[Tuple[str, str]] = [
            ("建议类型", "新增协议 / 协议子集"),
            ("使用场景", steps),
            ("你期望的样子", expected),
            ("报文 / 协议资料", frame),
        ]
    else:
        sections = [
            ("工具版本", version),
            ("相关协议", protocol),
            ("报文（十六进制）", frame),
            ("期望结果", expected),
            ("实际结果", actual),
            ("复现步骤", steps),
            ("运行环境", env),
            ("联系方式", contact),
        ]
    lines: List[str] = []
    for title, value in sections:
        text = str(value or "").strip()
        if not text:
            continue
        lines.append(f"### {title}")
        lines.append("")
        lines.append(text)
        lines.append("")
    if not lines:
        lines.append("（未填写任何内容）")
    return "\n".join(lines).rstrip() + "\n"


def build_prefill_url(
    owner: str,
    repo: str,
    kind: str,
    fields: Dict[str, str],
) -> str:
    """浏览器兜底链接：按表单字段 id 预填（``template=`` 指定用哪张表单）。

    ``fields`` 的键必须是该表单的字段 id（见 ``FORM_FIELDS``），
    值会被 URL 编码（含换行的多行文本用 ``%0A``）。
    """
    spec = ISSUE_KINDS.get(kind, ISSUE_KINDS["bug"])
    params: Dict[str, str] = {"template": spec["template"]}
    for field_id in FORM_FIELDS.get(kind, []):
        value = str((fields or {}).get(field_id, "") or "").strip()
        if value:
            params[field_id] = value
    query = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return f"{GITHUB_WEB_BASE}/{owner}/{repo}/issues/new?{query}"


# ── API 建单 ─────────────────────────────────────────────────────────

def describe_http_status(code: int) -> str:
    """把 HTTP 状态码翻译成用户能看懂的中文原因（不暴露英文栈）。"""
    try:
        code = int(code)
    except (TypeError, ValueError):
        return "GitHub 返回了无法识别的响应"
    if code in (401,):
        return "令牌无效或已过期（HTTP 401）——请检查令牌内容与有效期"
    if code == 403:
        return (
            "GitHub 拒绝了本次请求（HTTP 403）——可能是令牌缺少 "
            "「Issues: write」权限，或触发了频率限制"
        )
    if code == 404:
        return "仓库不存在或令牌无权访问（HTTP 404）——请检查仓库地址与令牌权限"
    if code == 422:
        return "GitHub 认为提交内容不合法（HTTP 422）——请检查标题与正文"
    if code == 429:
        return "请求过于频繁（HTTP 429）——请稍后再试"
    if 500 <= code < 600:
        return f"GitHub 服务器错误（HTTP {code}）——请稍后再试"
    if 400 <= code < 500:
        return f"请求被拒绝（HTTP {code}）"
    return f"GitHub 返回 HTTP {code}"


def _extract_api_message(payload: Any) -> str:
    """从 GitHub 返回体里抠出人话原因（message / errors[].message）。"""
    if not isinstance(payload, dict):
        return ""
    message = str(payload.get("message") or "").strip()
    errors = payload.get("errors")
    details: List[str] = []
    if isinstance(errors, list):
        for item in errors:
            if isinstance(item, dict):
                text = str(item.get("message") or item.get("code") or "").strip()
                if text:
                    details.append(text)
    if details:
        return f"{message}（{'; '.join(details[:3])}）" if message else "; ".join(details[:3])
    return message


def _looks_like_label_error(payload: Any) -> bool:
    """判断 422 是否由「标签不存在」引起（可在去掉 labels 后重试）。"""
    if not isinstance(payload, dict):
        return False
    errors = payload.get("errors")
    if isinstance(errors, list):
        for item in errors:
            if isinstance(item, dict) and "label" in str(item.get("field", "")).lower():
                return True
    return "label" in str(payload.get("message", "")).lower()


def _default_http_post(
    url: str,
    payload: Dict[str, Any],
    token: str,
    timeout: float,
) -> Tuple[int, str]:
    """默认传输：标准库 urllib POST JSON（零依赖）。可被测试注入替换。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "nw-protocol-parser-issue-reporter",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return int(getattr(resp, "status", 200) or 200), body
    except urllib.error.HTTPError as exc:                 # URLError 子类，必须先捕获
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:                                # noqa: BLE001 - 读不到就当空
            body = ""
        return int(getattr(exc, "code", 0) or 0), body
    except urllib.error.URLError as exc:
        raise IssueSubmitError(f"网络请求失败：{getattr(exc, 'reason', exc)}") from exc
    except (TimeoutError, OSError) as exc:
        raise IssueSubmitError(f"网络请求失败：{exc}") from exc


def submit_issue(
    owner: str,
    repo: str,
    token: str,
    title: str,
    body: str,
    labels: Optional[List[str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
    http_post: Optional[Callable[[str, Dict[str, Any], str, float], Tuple[int, str]]] = None,
) -> Dict[str, Any]:
    """通过 GitHub REST API 建一个 issue。

    返回 ``{"number", "html_url", "title", "labels"}``；失败抛 ``IssueSubmitError``。

    标签处理：仓库里没有的标签会让 GitHub 直接 422；此时**自动去掉 labels 重试一次**，
    保证「issue 建不出来」不会只是因为一个可有可无的标签。
    """
    owner = str(owner or "").strip()
    repo = str(repo or "").strip()
    token = str(token or "").strip()
    if not owner or not repo:
        raise IssueSubmitError("未配置仓库地址（owner / repo 为空）")
    if not token:
        raise IssueSubmitError("未配置 GitHub 令牌，无法直接建单")
    if not str(title or "").strip():
        raise IssueSubmitError("issue 标题不能为空")

    post = http_post or _default_http_post
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues"
    want_labels = [str(x) for x in (labels or []) if str(x).strip()]

    payload: Dict[str, Any] = {"title": str(title).strip(), "body": str(body or "")}
    if want_labels:
        payload["labels"] = want_labels

    status, text = post(url, payload, token, timeout)
    try:
        data = json.loads(text) if text else {}
    except (json.JSONDecodeError, TypeError):
        data = {}

    if status == 201 and isinstance(data, dict) and data.get("number"):
        return {
            "number": int(data.get("number")),
            "html_url": str(data.get("html_url") or ""),
            "title": str(data.get("title") or title),
            "labels": [str(x.get("name")) for x in (data.get("labels") or []) if isinstance(x, dict)],
        }

    if status == 422 and want_labels and _looks_like_label_error(data):
        # 仓库里没有这个标签 → 去掉标签再试一次（标签可有可无，issue 必须建出来）
        retry_payload = {"title": str(title).strip(), "body": str(body or "")}
        status, text = post(url, retry_payload, token, timeout)
        try:
            data = json.loads(text) if text else {}
        except (json.JSONDecodeError, TypeError):
            data = {}
        if status == 201 and isinstance(data, dict) and data.get("number"):
            return {
                "number": int(data.get("number")),
                "html_url": str(data.get("html_url") or ""),
                "title": str(data.get("title") or title),
                "labels": [],
            }

    detail = _extract_api_message(data)
    reason = describe_http_status(status)
    if detail:
        reason = f"{reason} —— {detail}"
    raise IssueSubmitError(reason)


# ── 令牌与仓库地址的本地配置 ─────────────────────────────────────────

def resolve_owner_repo(repo_url: str = "") -> Tuple[str, str]:
    """从仓库地址解析 (owner, repo)；解析不出回落到内置默认值。

    复用 ``auto_updater.parse_github_repo_url``，与「关于」按钮、自动升级源同源。
    """
    from auto_updater import (  # 局部导入：避免模块级耦合与循环导入
        DEFAULT_GITHUB_OWNER,
        DEFAULT_GITHUB_REPO,
        parse_github_repo_url,
    )

    parsed = parse_github_repo_url(repo_url) if repo_url else {}
    owner = str(parsed.get("github_owner") or "").strip() or DEFAULT_GITHUB_OWNER
    repo = str(parsed.get("github_repo") or "").strip() or DEFAULT_GITHUB_REPO
    return owner, repo


def read_env_token() -> str:
    """从环境变量读取令牌（``GITHUB_TOKEN`` / ``GH_TOKEN``）。"""
    for name in TOKEN_ENV_VARS:
        value = str(os.environ.get(name, "") or "").strip()
        if value:
            return value
    return ""


def load_issue_config(config_path: Any) -> Dict[str, Any]:
    """读 config.json 的 ``github_issue`` 段（不存在返回 {}，绝不抛）。"""
    if not config_path:
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    section = data.get("github_issue")
    return dict(section) if isinstance(section, dict) else {}


def save_issue_config(config_path: Any, section: Dict[str, Any]) -> bool:
    """把 ``github_issue`` 段写回 config.json（原子写，保留其它段）。"""
    if not config_path:
        return False
    from atomic_io import atomic_write_json

    try:
        data: Dict[str, Any] = {}
        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                data = loaded
        except (OSError, ValueError):
            data = {}
        data["github_issue"] = dict(section or {})
        atomic_write_json(config_path, data)
        return True
    except Exception:                                     # noqa: BLE001 - 存不进去不该崩
        return False


def resolve_token(config_path: Any = None, explicit: str = "") -> str:
    """令牌优先级：显式传入 → 环境变量 → 本机 config.json。"""
    text = str(explicit or "").strip()
    if text:
        return text
    env_token = read_env_token()
    if env_token:
        return env_token
    return str(load_issue_config(config_path).get("token") or "").strip()


__all__ = [
    "GITHUB_API_BASE",
    "GITHUB_WEB_BASE",
    "DEFAULT_TIMEOUT",
    "MAX_PREFILL_URL",
    "TOKEN_SCOPE_HINT",
    "ISSUE_KINDS",
    "FORM_PROTOCOL_OPTIONS",
    "FORM_FIELDS",
    "PROTOCOL_UNRELATED_INDEX",
    "TOKEN_ENV_VARS",
    "IssueSubmitError",
    "mask_token",
    "protocol_option",
    "collect_env_info",
    "truncate",
    "sanitize_crash_summary",
    "build_issue_title",
    "build_issue_body",
    "build_prefill_url",
    "describe_http_status",
    "submit_issue",
    "resolve_owner_repo",
    "read_env_token",
    "load_issue_config",
    "save_issue_config",
    "resolve_token",
]
