# -*- coding: utf-8 -*-
"""协议7 测试页的 **AFN/Fn 支持判定**（按报文本质，纯逻辑，零 Qt）。

为什么要单独一层
----------------
「这个模块支持不支持 03H F1？」不能只看「有没有回帧」——Q/GDW 10376.2 的应答有两种形态：

1. **确认/否认帧**（AFN=00H，福建增补镜像为 50H）：
   - F1 确认：数据单元 = 4B 信道状态 + 2B 等待时间（表 9）→ 设备**已受理**该命令；
   - F2 否认：数据单元 = 1B 错误状态字（表 10），其中 **4=信息类不存在、10=主节点不支持此命令**
     才是「不支持」，其余（0 通信超时、9 主节点忙、11 从节点不应答、12 从节点不在网内、
     109 超并发、110 超单帧条数、111 正在抄读该表…）是**运行期失败**，命令本身是被识别的。
2. **同 AFN/Fn 的上行数据帧**：抄读/查询类命令的正常应答。

因此判据按命令分类（`EXPECT_CONFIRM_AFNS` / `EXPECT_DATA_AFNS`，每条都在注释里写明文档出处）：

- 「只需确认」类：收到确认 → **支持**；收到否认 → 按错误状态字分「不支持」/「支持但执行报错」。
- 「必须数据」类（抄表/查询/转发）：收到确认只算**已受理**，还要等同 AFN/Fn 的数据；
  只收到确认就超时的，记「仅确认，无数据」——**不算支持**（用户口径）。

`judge()` 是唯一判定入口；同 AFN/Fn 的数据帧仍交给 :func:`gdw_test_core.evaluate_response`
复用既有字段级判据，本模块只补「确认/否认」这一层，不另立协议判据。
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple

import gdw_test_core as core

# ── 命令分类（依据：集中器本地通信模块接口-2024.md + 附件3 福建增补）─────────
#: 只需「确认/否认」即可判支持 —— 文档明写「上行报文为确认/否认报文，详见 6.5.1」
#: 注意：**只列下行命令的 AFN**。06H/56H 是主动上报（上行），由被测设备自己发，
#: 测试系统只能接收，不能下发、也不判支持（见 `is_uplink_only`）。
EXPECT_CONFIRM_AFNS = frozenset({
    0x01,   # §6.5.2 初始化
    0x04,   # §6.5.5 链路接口检测
    0x05,   # §6.5.6 控制命令
    0x11,   # §6.5.9 路由设置类
    0x12,   # §6.5.10 路由控制类
    0x51,   # 附件3：51H 初始化（福建增补 = 标准 +0x50）
    0x54,   # 附件3：54H 链路接口检测
    0x55,   # 附件3：55H 控制命令
})

#: 必须收到「同 AFN/Fn 的上行数据」才算支持 —— 文档上行报文为数据帧
EXPECT_DATA_AFNS = frozenset({
    0x02,   # §6.5.3 数据转发
    0x03,   # §6.5.4 查询数据
    0x10,   # §6.5.8 路由查询类
    0x13,   # §6.5.11 路由数据转发类
    0x14,   # §6.5.12 路由数据抄读类
    0x15,   # §6.5.13 文件传输
    0x52,   # 附件3：52H 数据转发（含 F11 并发抄表「…或否认【AFN=00H_F2】」）
    0x53,   # 附件3：53H 查询数据
    0xF0,   # F0H LME 扩展查询（查询类）
    0xF1,   # F1H 集中器主动并发抄表
})

#: 确认/否认帧的 AFN（50H 为福建增补镜像，文档明确否认走国标 00H_F2，两处都认）
CONFIRM_DENY_AFNS = frozenset({0x00, 0x50})

#: 表 10 错误状态字（原文）
ERROR_STATUS: Dict[int, str] = {
    0: "通信超时",
    1: "无效数据单元",
    2: "长度错",
    3: "校验错误",
    4: "信息类不存在",
    5: "格式错误",
    6: "表号重复",
    7: "表号不存在",
    8: "电能表应用层无应答",
    9: "主节点忙",
    10: "主节点不支持此命令",
    11: "从节点不应答",
    12: "从节点不在网内",
    109: "超过最大并发数",
    110: "超过单个 Q/GDW 10376.2 帧最大允许的电能表协议报文条数",
    111: "正在抄读该表",
}

#: 真正意味着「设备不支持这条命令」的错误状态字
UNSUPPORTED_CODES = frozenset({4, 10})

#: 否认错误码 → 现场处置建议（页面日志里直接给出，避免只报「执行失败」无从下手）
ERROR_HINTS: Dict[int, str] = {
    1: "无效数据单元：核对数据单元字段/长度是否符合协议表（多余或缺少字段都会被判无效）。",
    2: "长度错：本帧 L 为整帧总长（68+L+C+R+AFN+DT+数据+CS+16）。先确认这条命令"\
       "是否真有数据单元（如 10H F104 必须带 节点起始序号(2B)+节点数量(1B)）；"\
       "确需补数据单元时用「附加数据」补，或核对该 CCO 的版本增补要求。",
    5: "格式错误：检查信息域（模块标识/中继级别/信道）与数据单元格式是否与协议一致。",
    6: "表号重复：该表地址已在模块档案里。先下发 01H F2 参数区初始化清空档案"
       "（会连同参数区一起清）再 11H F1 添加；只想去掉单个表可用 11H F2 删除。",
    7: "表号不存在：目标地址/附属节点地址与 CCO 档案不一致。地址按 §5.2 低字节在前，"\
       "界面按正序 12 位输入（如 000000000033）；确认该表已在 CCO 建档（11H F1），"\
       "且命令字段没被手改成旧值（可「清空所有参数」重新套用组网参数）。",
    8: "电能表应用层无应答：表没响应，检查表侧接线/规约类型（645-1997/2007/698.45）。",
    11: "从节点不应答：节点可能未入网，先「准备测试网络」查 10H F2 确认。",
    12: "从节点不在网内：先建档（11H F1）→ 组网（11H F102）→ 用 10H F2/F20 确认入网后再测。",
}


def error_hint(code: Any) -> str:
    """否认错误码 → 处置建议（未收录返回空串）。"""
    try:
        return ERROR_HINTS.get(int(code), "")
    except (TypeError, ValueError):
        return ""

# 判定结论
V_CONFIRM = "confirm"          # 支持（确认）
V_DATA = "data"                # 支持（同命令数据）
V_DENY_FAIL = "deny_fail"      # 支持但执行报错（否认且错误码非「不支持」）
V_UNSUPPORTED = "unsupported"  # 不支持（否认且错误码 4/10）
V_WAITING = "waiting_data"     # 已确认，等待数据（非终态）
V_MISMATCH = "mismatch"        # 收到的帧与当前命令无关（非终态）
V_BAD = "bad_frame"            # 帧结构不合法（非终态）

#: 终态：可以推进队列
FINAL_VERDICTS = frozenset({V_CONFIRM, V_DATA, V_DENY_FAIL, V_UNSUPPORTED})

EXPECT_LABELS = {"confirm": "确认即支持", "data": "需同命令上行数据",
                 "uplink": "上行仅接收（不下发、不判支持）"}

#: 上行帧（确认/否认应答 + 主动上报）：由被测 CCO 自己发出，测试系统只是接收方。
#: **不得作为发送目标**，也**不给支持结论** —— 下发它们属于测试方法错误。
UPLINK_REASON = ("上行帧由被测设备主动发出（应答或上报），测试系统只接收；"
                 "下发它不属于本页测试范围，也不据此判支持")


def is_uplink_only(cmd: Any) -> bool:
    """是否「只能接收、不该由测试系统下发」的命令。

    判据是 schema 的 ``direction == "up"``（06H/56H 上报、00H/50H 确认否认）。
    **只有明确标 up 才算上行**：缺字段的自定义命令按「可下发」处理，
    否则用户自定义的 AFN 会被静默排除在遍历之外。
    """
    return str(getattr(cmd, "direction", "") or "").strip().lower() == "up"


def is_sendable(cmd: Any) -> bool:
    """本页可以下发的命令：只收下行（其余是确认/否认应答或主动上报）。"""
    return not is_uplink_only(cmd)


def sendable_commands(commands: Iterable[Any]) -> list:
    return [cmd for cmd in commands if is_sendable(cmd)]


def uplink_commands(commands: Iterable[Any]) -> list:
    return [cmd for cmd in commands if is_uplink_only(cmd)]


def expect_mode(cmd: Any) -> str:
    """命令期望哪种应答：``confirm``（确认即支持）/ ``data``（必须同命令数据）。

    - 上行命令（确认/否认应答、主动上报）返回 ``uplink``：**不下发、不判支持**；
    - 未收录 AFN 的下行命令（用户自定义）按 ``data`` 处理——宁可不认，也不把「确认」误当抄读成功。
    """
    if is_uplink_only(cmd):
        return "uplink"
    afn = int(getattr(cmd, "afn", -1))
    if afn in EXPECT_CONFIRM_AFNS:
        return "confirm"
    return "data"


def error_status_text(code: Optional[int]) -> str:
    if code is None:
        return ""
    return ERROR_STATUS.get(int(code), f"错误状态字 {code}（未收录）")


def _row_value(rows: Sequence[Tuple], name: str) -> Optional[Tuple]:
    return core._row_value(rows, name)          # noqa: SLF001 - 复用解析行的唯一口径


def _row_int(row: Optional[Tuple]) -> Optional[int]:
    return core._row_int(row)                   # noqa: SLF001


def _row_fn(row: Optional[Tuple]) -> Optional[int]:
    return core._row_fn(row)                    # noqa: SLF001


def _result(kind: str, verdict: str, ok, reason: str, rows: Sequence[Tuple],
            code: Optional[int] = None) -> Dict[str, Any]:
    return {
        "kind": kind,
        "verdict": verdict,
        "final": verdict in FINAL_VERDICTS,
        "ok": ok,
        "reason": reason,
        "rows": list(rows or ()),
        "error_code": code,
        "hint": error_hint(code),
    }


def judge(cmd: Any, frame: bytes) -> Dict[str, Any]:
    """判定一帧对 ``cmd`` 而言意味着什么（唯一入口）。"""
    rows = core.parse_table(bytes(frame or b""))
    if not rows:
        return _result("bad", V_BAD, None, "无法解析（帧长不足或结构不认识）", rows)

    verify = core.verify_frame(bytes(frame or b""))
    if verify is not None:
        for item in getattr(verify, "checks", ()) or ():
            if "fail" in str(getattr(item, "level", "")).lower():
                return _result("bad", V_BAD, None,
                               f"{item.name}未通过：{item.message}", rows)

    afn_row = _row_value(rows, "应用功能码(AFN)")
    afn = _row_int(afn_row)
    if afn is None:
        return _result("bad", V_BAD, None, "缺少应用功能码(AFN)行", rows)
    fn = _row_fn(_row_value(rows, "数据单元标识(DT)"))

    # ── ① 确认/否认帧 ──────────────────────────────────────────────
    if afn in CONFIRM_DENY_AFNS:
        if fn == 2:
            code_row = _row_value(rows, "错误状态字") or _row_value(rows, "错误代码")
            code = _row_int(code_row)
            desc = error_status_text(code)
            label = f"否认（错误状态字={code}" + (f"：{desc}" if desc else "") + "）"
            if code is not None and int(code) in UNSUPPORTED_CODES:
                return _result("deny", V_UNSUPPORTED, False,
                               f"{label} → 设备不支持该命令", rows, code)
            return _result("deny", V_DENY_FAIL, False,
                           f"{label} → 命令被识别，执行未成功", rows, code)
        if fn in (1, 3):
            status_row = _row_value(rows, "命令状态")
            status = str(status_row[2] or "").strip() if status_row else ""
            wait_row = _row_value(rows, "等待时间")
            wait = _row_int(wait_row)
            detail = "".join([
                f"命令状态={status}" if status else "",
                f"，等待时间={wait}s" if wait else "",
            ])
            head = f"确认（{detail}）" if detail else "确认"
            if expect_mode(cmd) == "confirm":
                return _result("confirm", V_CONFIRM, True, head + " → 已受理，判为支持", rows)
            return _result("confirm", V_WAITING, None,
                           head + " → 已受理，等待同命令数据", rows)
        return _result("other", V_MISMATCH, None,
                       f"确认/否认帧的 Fn=F{fn} 无法识别", rows)

    # ── ② 同 AFN/Fn 的上行数据帧 ────────────────────────────────────
    if afn == int(getattr(cmd, "afn", -1)) and fn == int(getattr(cmd, "fn", -1)):
        result = core.evaluate_response(cmd, bytes(frame or b""))
        if not result.get("matched"):
            # evaluate_response 认为结构/校验不对：仍然是不认识的数据，按无关帧处理
            return _result("other", V_MISMATCH, None,
                           str(result.get("reason") or "响应帧与命令不匹配"), rows)
        ok = result.get("ok")
        reason = str(result.get("reason") or "")
        if ok is False:
            return _result("data", V_DENY_FAIL, False,
                           f"同命令响应但执行失败：{reason}", rows)
        return _result("data", V_DATA, True,
                       f"收到同命令上行数据（{reason}）" if reason else "收到同命令上行数据",
                       rows)

    # ── ③ 其它帧：与当前命令无关 ────────────────────────────────────
    return _result(
        "other", V_MISMATCH, None,
        f"非本命令响应（收到 AFN={afn:02X}H"
        + (f" F{fn}" if fn is not None else "") + f"，期望 {int(getattr(cmd, 'afn', 0)):02X}H"
        + f" F{int(getattr(cmd, 'fn', 0))}）", rows)


def verdict_state(verdict: str) -> str:
    """判定结论 → 统计状态（未终态的由调用方决定）。"""
    return {
        V_CONFIRM: "support",
        V_DATA: "support",
        V_DENY_FAIL: "support_error",
        V_UNSUPPORTED: "unsupported",
    }.get(verdict, "untested")


def expect_summary(commands: Iterable[Any]) -> Dict[str, int]:
    """分类计数（界面/报告说明：多少条只需确认、多少条必须数据、多少条只能接收）。"""
    out = {"confirm": 0, "data": 0, "uplink": 0}
    for cmd in commands:
        out[expect_mode(cmd)] = out.get(expect_mode(cmd), 0) + 1
    return out
