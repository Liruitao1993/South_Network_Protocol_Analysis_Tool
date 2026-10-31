# -*- coding: utf-8 -*-
"""国网协议测试页 —— **遍历测试报告（单文件 HTML）**（纯逻辑，零 Qt）。

输入都是纯数据（组网参数 + 支持统计汇总 + 交互明细），输出一段自包含的 HTML：
环境信息、AFN 支持汇总、逐条命令结果、交互报文明细。样式内联、无外链，
直接双击即可在任何浏览器打开，也便于压进邮件/报告附件。
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import gdw_test_network as net_mod
import gdw_test_store as store

_NUMERALS = "一二三四五六七八九十"


def _sec(n: int, title: str) -> str:
    """章节序号（一、二、三…），避免手写序数跟条件段落错位。"""
    num = _NUMERALS[n - 1] if 1 <= n <= len(_NUMERALS) else str(n)
    return f"<h2>{num}、{title}</h2>"


_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0; padding: 24px 28px 60px; font: 14px/1.6 -apple-system, "Segoe UI",
       "Microsoft YaHei", sans-serif; color: #1f2328; background: #fff; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 16px; margin: 28px 0 10px; padding-bottom: 6px; border-bottom: 1px solid #d0d7de; }
.meta { color: #6e7781; font-size: 12px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { border: 1px solid #d0d7de; padding: 5px 8px; text-align: left; vertical-align: top; }
th { background: #f6f8fa; font-weight: 600; position: sticky; top: 0; }
tr:nth-child(even) td { background: #fbfcfd; }
.kv td:first-child { width: 160px; color: #57606a; background: #f6f8fa; }
.ok { color: #0a7d28; font-weight: 600; }
.err { color: #b42318; font-weight: 600; }
.warn { color: #9a6700; font-weight: 600; }
.mute { color: #8c959f; }
code, .hex { font-family: Consolas, "Courier New", monospace; font-size: 12px; }
.hex { word-break: break-all; color: #57606a; }
.cards { display: flex; flex-wrap: wrap; gap: 12px; margin: 12px 0 4px; }
.card { flex: 1 1 140px; border: 1px solid #d0d7de; border-radius: 8px; padding: 10px 12px; }
.card b { display: block; font-size: 22px; line-height: 1.2; }
.card span { color: #6e7781; font-size: 12px; }
details { margin: 6px 0; }
summary { cursor: pointer; color: #0969da; }
footer { margin-top: 32px; color: #8c959f; font-size: 12px; }
"""


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _state_class(label: str) -> str:
    if label.startswith("支持（"):
        return "warn"
    if label == "支持":
        return "ok"
    if label in ("不支持（设备否认）", "无响应", "非本命令响应"):
        return "err"
    if label.startswith("仅确认"):
        return "warn"
    return "mute"


def build_report(*, env_rows: Sequence[Tuple[str, str]],
                 summary: Mapping[str, Any],
                 extra_rows: Sequence[Tuple[str, str]] = (),
                 interactions: Sequence[Mapping[str, Any]] = (),
                 uplink_rows: Sequence[Tuple[str, str, str]] = (),
                 log_path: str = "",
                 title: str = "国网协议（AFN/Fn）遍历测试报告") -> str:
    """生成单文件 HTML 报告。

    - ``env_rows``：组网/通道等环境键值对；
    - ``summary``：:func:`gdw_test_store.summarize` 的返回（含 ``rows``/``counts``/``per_afn``）；
    - ``interactions``：``{time, direction, label, node, result, reason, frame}`` 明细；
    - ``log_path``：落盘日志文件路径（便于追溯）。
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    counts = dict(summary.get("counts") or {})
    total = int(summary.get("total") or 0)
    supported = int(counts.get(store.STATE_SUPPORT, 0)) + int(counts.get(store.STATE_SUPPORT_ERROR, 0))
    err = int(counts.get(store.STATE_SUPPORT_ERROR, 0))
    unsupported = int(counts.get(store.STATE_UNSUPPORTED, 0))
    confirm_only = int(counts.get(store.STATE_CONFIRM_ONLY, 0))
    mismatch = int(counts.get(store.STATE_MISMATCH, 0))
    no_reply = int(counts.get(store.STATE_NO_REPLY, 0))
    untested = int(counts.get(store.STATE_UNTESTED, 0))

    parts: List[str] = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN"><head><meta charset="utf-8">',
        f"<title>{_e(title)}</title><style>{_CSS}</style></head><body>",
        f"<h1>{_e(title)}</h1>",
        f'<div class="meta">生成时间 {_e(now)}　·　共 {total} 条命令×节点组合</div>',
        '<div class="cards">',
        f'<div class="card"><span>支持</span><b class="ok">{supported}</b>'
        f'<span>其中执行报错 {err}</span></div>',
        f'<div class="card"><span>不支持</span><b class="err">{unsupported}</b></div>',
        f'<div class="card"><span>仅确认·无数据</span><b class="warn">{confirm_only}</b></div>',
        f'<div class="card"><span>非本命令响应</span><b class="err">{mismatch}</b></div>',
        f'<div class="card"><span>无响应</span><b class="err">{no_reply}</b></div>',
        f'<div class="card"><span>未测</span><b class="mute">{untested}</b></div>',
        "</div>",
        '<div class="meta">判定口径：01H/04H/05H/11H/12H（含福建 51H/54H/55H）与主动上报——收到 '
        'AFN=00H F1 确认即判支持；02H/03H/10H/13H/14H/15H、52H/53H、F0H/F1H——必须收到同 AFN/Fn '
        '上行数据，仅确认超时记「仅确认·无数据」；否认按表 10 错误状态字：4/10 为不支持，'
        '其余为支持但执行报错。</div>',
        _sec(1, "测试环境") + "<table class=\"kv\">",
    ]
    for key, value in list(env_rows) + list(extra_rows):
        parts.append(f"<tr><td>{_e(key)}</td><td>{_e(value)}</td></tr>")
    if log_path:
        parts.append(f'<tr><td>交互日志</td><td class="hex">{_e(log_path)}</td></tr>')
    parts.append("</table>")

    # ── 按 AFN 汇总 ──
    section_no = 1
    per_afn = dict(summary.get("per_afn") or {})
    section_no += 1
    parts.append(_sec(section_no, "AFN 支持汇总") + "<table><tr><th>AFN</th><th>支持</th>"
                 "<th>已测</th><th>命令数</th><th>支持率</th></tr>")
    for afn in sorted(per_afn):
        slot = per_afn[afn]
        total_afn = int(slot.get("total") or 0)
        sup = int(slot.get("supported") or 0)
        tested = int(slot.get("tested") or 0)
        rate = f"{sup * 100 // total_afn}%" if total_afn else "-"
        parts.append(
            f"<tr><td>{afn:02X}H</td><td class=\"{'ok' if sup else 'mute'}\">{sup}</td>"
            f"<td>{tested}</td><td>{total_afn}</td><td>{rate}</td></tr>")
    parts.append("</table>")

    # ── 逐条结果 ──
    headers = ("AFN", "Fn", "命令", "从节点", "方向", "状态", "依据", "时间")
    section_no += 1
    parts.append(_sec(section_no, "逐条命令结果") + "<table><tr>"
                 + "".join(f"<th>{_e(h)}</th>" for h in headers) + "</tr>")
    for row in summary.get("rows") or ():
        cells = list(row) + [""] * (len(headers) - len(row))
        state = str(cells[5])
        parts.append(
            "<tr>"
            + "".join(f"<td>{_e(v)}</td>" for v in cells[:5])
            + f'<td class="{_state_class(state)}">{_e(state)}</td>'
            + f"<td>{_e(cells[6])}</td><td>{_e(cells[7])}</td></tr>")
    parts.append("</table>")

    # ── 交互明细 ──
    if interactions:
        section_no += 1
        parts.append(_sec(section_no, f"交互报文明细（{len(interactions)} 条）")
                     + "<table><tr><th>时间</th><th>方向</th><th>命令</th><th>从节点</th>"
                     "<th>结果</th><th>报文</th></tr>")
        for item in interactions:
            parts.append(
                "<tr>"
                f"<td>{_e(item.get('time'))}</td>"
                f"<td>{_e(item.get('direction'))}</td>"
                f"<td>{_e(item.get('label'))}</td>"
                f"<td>{_e(item.get('node'))}</td>"
                f"<td>{_e(item.get('result') or item.get('reason'))}</td>"
                f"<td class=\"hex\">{_e(item.get('frame'))}</td>"
                "</tr>")
        parts.append("</table>")

    # ── 上行命令（仅接收，不判支持）──
    if uplink_rows:
        parts.append(
            _sec(section_no + 1, "上行命令（仅接收，不判支持）")
            + '<div class="meta">以下报文由被测设备主动发出（应答或上报），测试系统只接收：'
            "本页不下发、也不据此给出支持结论。其中主动上报类还需外部触发条件"
            "（如「上报从节点信息」需先下发启动主动注册并留出注册时间；"
            "「上报从节点事件」需对陪测从节点断电制造停电事件等），"
            "这些场景不纳入自动遍历结论，需单独人工验证。</div>"
            "<table><tr><th>AFN</th><th>Fn</th><th>名称</th></tr>")
        for afn, fn, name in uplink_rows:
            parts.append(f"<tr><td>{_e(afn)}</td><td>{_e(fn)}</td><td>{_e(name)}</td></tr>")
        parts.append("</table>")

    parts.append("<footer>由 MiniMax Code 生成 · 国网协议测试页</footer></body></html>")
    return "\n".join(parts)

def report_env_rows(net: "net_mod.NetworkConfig", *, channel: str = "",
                    src: str = "", dst: str = "", module_flag: Any = "",
                    timeout_ms: Any = "", retries: Any = "",
                    started: str = "", finished: str = "",
                    tx: int = 0, rx: int = 0) -> List[Tuple[str, str]]:
    """报告「测试环境」段的键值对（组网参数 + 链路参数 + 收发计数）。"""
    rows: List[Tuple[str, str]] = list(net_mod.summary_env(net))
    rows += [
        ("发送通道", channel or "（未知）"),
        ("源地址 / 目的地址", f"{src or '-'} / {dst or '-'}"),
        ("通信模块标识", str(module_flag)),
        ("超时 / 重试", f"{timeout_ms} ms / {retries} 次"),
        ("开始时间", started or "-"),
        ("结束时间", finished or "-"),
        ("收发帧数", f"TX {tx} / RX {rx}"),
    ]
    return rows
