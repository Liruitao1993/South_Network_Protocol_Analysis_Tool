# -*- coding: utf-8 -*-
"""HDC 1.0（协议索引11）应用层分派与「未识别内容」收口回归

缺陷（均为既有，非本次引入）：
  P0-1/P0-2  `0x00A0 鉴权安全`（端口 0x1A）/ `0x00A4 配电信息上报`（端口 0x11）：
             `APP_PORTS` 与 `MSG_ID_NAMES` 里有名字，`_parse_app_payload` 分派链却无分支
             → 落 fallback 显示「未识别的业务数据(0x0A0)」。fallback 本身也不查名字表
             （**名字表与分派链是两份手写清单**，漂移即根因）。
  P1-3       `_parse_app_only` 硬编码端口白名单 `(0x11,0x12,0x1A)`，非白名单端口连通用头
             （端口/报文ID/安全模式/控制字）都不解析，直接判「未识别格式的应用层数据」。
  P1-4       `_parse_msdu_payload` 只看首字节启发式、无视 MAC 头的 msdu_type → 双向误判：
             真实帧 `msdu_type=48`（表10「应用层报文」）反而显示「类型48: 未定义」，
             `msdu_type=47`（不在表内）反而进了应用层解析。
  P1-5       `sec_mode` 已正确取出却未参与提示 → 受信道安全机制保护的报文仍按明文逐字段
             解析，输出「看起来正常的错误数值」（真实夹具 idx=50 即 `sec_mode=1`）。

修复（对应 design.md D1~D5）：
  D1 值域单一来源：`APP_MSDU_TYPES={48,128}` / `IPV4_MSDU_TYPES={49,129}`；
  D2 分派以 **MAC 头类型字段**为准，首字节启发式仅作 `msdu_type=None` 时的回退；
  D3 `_parse_app_only` 收口：长度不足报错 → 端口表命中/控制字合规 → 完整 MPDU 走 FC
     → 其余按应用层解释并注明「推测解析」；
  D4 fallback 查 `MSG_ID_NAMES`：规范已命名但无字段格式定义的业务 → 报业务名 +
     「⚠ 格式未定义」+ 原始数据；表外 ID 明确注明「未在本规范报文ID表中定义」；
  D5 `sec_mode != 0` → 插入醒目「⚠ 安全保护」提示行（**不跳过**业务解析，陷阱23）。

协议依据：
  第4-2部分 表10（标准MAC头 MSDU类型 0/48/49）、表13（单跳帧头 0/128/129）；
  第4-3部分 §5.2.2（端口号）、§5.2.3（报文ID 高4位=信道安全机制）、
  §5.2.4（报文控制字「默认设置为0」）、表2（报文ID 名称；`0x00A0`/`0x00A4` 无字段格式定义）。

夹具说明（`test/hdc10_real_frames.pkl`）：60 帧中 43 帧是 TMI 填充帧（随机数据），
其「未定义(厂商扩展)」「未识别的业务数据(0x347)」**不是缺陷** —— 本套件只对
`key[1] != '-'` 的真实业务帧与「MAC 头声明类型」做断言，填充帧只断言「不抛异常」。

运行：
    python -X utf8 test/test_hdc10_app_dispatch.py
"""

import os
import sys

import _path_setup  # noqa: E402,F401 —— F401 必须一并抑制，否则 ruff --fix 会删掉它

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import hashlib  # noqa: E402
import inspect  # noqa: E402
import json  # noqa: E402
import pickle  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "reflex_web"))

import hdc10_parser  # noqa: E402
import main_gui  # noqa: E402
from reflex_web import web_utils  # noqa: E402

from hdc10_parser import (  # noqa: E402
    APP_MSDU_TYPES,
    APP_PORTS,
    HDC10Parser,
    IPV4_MSDU_TYPES,
    MSG_ID_NAMES,
    MSG_ID_NO_FORMAT_DEFINED,
    MSDU_TYPES,
    SINGLEHOP_MSG_TYPES,
)

try:  # Windows 控制台中文
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

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


def section(title):
    print(f"\n--- {title} ---")


# ══════════════════════════════════════════════════════════════
# 样本
# ══════════════════════════════════════════════════════════════
# A1: 端口 0x1A + 业务ID 0x0A0（鉴权安全）；A2: 端口 0x11 + 业务ID 0x0A4（配电信息上报）
APP_AUTH = "1A A0 00 00 11 22 33 44 55 66 77 88"
APP_DIST = "11 A4 00 00 11 22 33 44 55 66 77 88"
# A3: 端口 0x13（既有白名单之外）；A3b: 同一端口但控制字非0（走「推测解析」兜底）
APP_PORT13 = "13 05 00 00 11 22 33 44 55 66 77 88"
APP_PORT13_CTRL = "13 05 00 77 11 22 33 44 55 66 77 88"
# 表外业务ID（不在 MSG_ID_NAMES）→ 仍应显示「未识别的业务数据」并注明依据
APP_UNKNOWN_ID = "11 05 00 00 11 22 33 44 55 66 77 88"
# A7: 校时 0x2004（安全模式=2 数据完整性保护）；对照 0x0004（明文）
APP_TS_SEC2 = "11 04 20 00 01 01 40 00 AA BB CC DD"
APP_TS_SEC0 = "11 04 00 00 01 01 40 00 AA BB CC DD"
# A6: 完整 MPDU（FC 帧，与 test_hdc10.py 的用户帧同源，142 字节）
FC_FRAME = bytes.fromhex(
    (
        "00 3A CF 9E E0 A8 12 69 A7 A0 BE 06 00 42 6D 29 "
        "C8 42 00 01 02 21 45 19 53 2D 01 00 B7 03 00 00 00 00 00 00 "
        "04 00 0F A7 A0 01 5E 01 01 59 51 94 88 21 00 03 01 0A "
        "F0 00 3C 00 14 00 18 00 03 04 78 05 "
        "C0 23 00 19 33 00 09 1E 32 00 00 00 00 80 A4 66 68 10 27 00 00 2E 00 "
        "ED 0B 00 01 ED 0B 00 02 EE 0B 00 03 "
        "81 10 A7 70 4B 00 1F 00 53 00 51 00 4C 00 38 00 79 00 8E 00 "
        "A0 00 78 00 70 00 3A 00 6E 00 89 00 9A 00 88 00 "
        "F7 0B 00 01 F7"
    ).replace(" ", "")
)

PICKLE = ROOT / "test" / "hdc10_real_frames.pkl"

# 真实夹具中输出发生变化的帧（改动前基线 vs 改动后逐帧对拍得出，仅此 3 帧）：
#   9  msdu_type=47（表外）→ 不再按首字节启发式进应用层解析（P1-4 误判修复）
#   48 msdu_type=128 → 由「类型128: 未定义」变为应用层解析（D2）
#   50 msdu_type=48  → 由「类型48: 未定义」变为应用层解析（D2）
#      且 sec_mode=1 → 新增「⚠ 安全保护」提示行（D5）
DIFF_FRAMES = (9, 48, 50)
# 其余 57 帧的行序列指纹（改动前基线 == 改动后，R6「已知业务输出不变」）
UNCHANGED_FRAMES_SHA256 = (
    "e20b9e23cd5ef839c44df9eede7db9c836ab3e0181393d7fbb26f95f3ed99631"
)

# A7 golden：改动前 0x2004 校时帧的完整行序列（步骤 0 基线，逐行内嵌）
A7_SEC2_GOLDEN = (
    ("── 应用层报文 ──", "", "12字节", "通用报文头 + 业务报文体", 0, 11),
    ("  报文端口号", "0x11", "17", "普通业务(抄表/校时/事件/注册等)", 0, 0),
    ("  报文ID", "04 20", "0x2004", "安全模式: 数据完整性保护, 业务ID: 0x004", 1, 2),
    ("  安全模式", "0x2", "2", "数据完整性保护", 1, 2),
    ("  业务报文ID", "0x004", "4", "业务类型ID: 0x004", 1, 2),
    ("  报文控制字", "0x00", "0", "控制字: 0x00", 3, 3),
    ("── 业务数据 ──", "", "8字节", "报文ID: 0x004", 4, 11),
    ("  校时报文", "", "4字节头", "校时命令", 4, 7),
    ("    转发数据长度", "0x004", "4字节", "校时报文数据长度: 4字节", 6, 7),
    ("    数据(DATA)", "AA BB CC DD", "4字节", "校时应用报文数据", 8, 11),
)


# ══════════════════════════════════════════════════════════════
# 工具
# ══════════════════════════════════════════════════════════════
PARSER = HDC10Parser()


def parse_hex(hex_str, level="app"):
    return PARSER.parse_to_table(
        bytes.fromhex(hex_str.replace(" ", "")), parse_level=level
    )


def row_names(rows):
    return [str(r[0]).strip() for r in rows]


def find(rows, name):
    """按「去缩进后精确相等」取行；找不到时报出表内字段名便于定位"""
    for r in rows:
        if str(r[0]).strip() == name:
            return r
    raise AssertionError(f"未找到字段: {name}；表内字段={row_names(rows)}")


def try_find(rows, name):
    """不抛异常的查找：变异反证时保证套件跑完、FAIL 清单完整"""
    for r in rows:
        if str(r[0]).strip() == name:
            return r
    return None


def all_comments(rows):
    return " | ".join(str(r[3]) for r in rows)


def row_tuples(rows):
    return tuple(tuple(r) for r in rows)


def code_only(func):
    """函数源码去掉 `#` 注释（静态守卫用：注释里的示例值不应触发/掩盖断言）"""
    return "\n".join(
        line.split("#", 1)[0] for line in inspect.getsource(func).splitlines()
    )


def load_frames():
    with open(PICKLE, "rb") as fp:
        return pickle.load(fp)


def with_msdu_type(frame_bytes, type_byte):
    """把标准 MAC 头（PBH 之后 byte7）的 MSDU 类型字段改为指定值"""
    mut = bytearray(frame_bytes)
    mut[8] = type_byte
    return bytes(mut)


def fingerprint_unchanged_frames(frames):
    payload = [
        [i, [list(r) for r in PARSER._parse_pb_only(fb, 1)]]
        for i, (_fi, fb, _key) in enumerate(frames)
        if i not in DIFF_FRAMES
    ]
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def main():
    global PASS
    frames = load_frames()

    # ── [1] D1：类型值域单一来源 ─────────────────────────────
    section("[1] D1 值域常量（单一来源，值域取自表10/表13）")
    check("APP_MSDU_TYPES == {48, 128}", APP_MSDU_TYPES == frozenset({48, 128}),
          str(sorted(APP_MSDU_TYPES)))
    check("IPV4_MSDU_TYPES == {49, 129}", IPV4_MSDU_TYPES == frozenset({49, 129}),
          str(sorted(IPV4_MSDU_TYPES)))
    check("表10：48=应用层报文 / 49=IP报文",
          MSDU_TYPES.get(48) == "应用层报文" and MSDU_TYPES.get(49) == "IP报文",
          str(MSDU_TYPES))
    check("表13：128=应用层报文 / 129=IPV4报文",
          SINGLEHOP_MSG_TYPES.get(128) == "应用层报文"
          and SINGLEHOP_MSG_TYPES.get(129) == "IPV4报文",
          str(SINGLEHOP_MSG_TYPES))
    check("值域常量与类型表一致（48/128 均指向应用层报文）",
          MSDU_TYPES.get(48) == SINGLEHOP_MSG_TYPES.get(128))
    check("分派使用 APP_MSDU_TYPES（静态守卫）",
          "APP_MSDU_TYPES" in code_only(HDC10Parser._parse_msdu_payload))

    # ── [2] A1 / A2：规范已命名但无字段格式定义的业务 ────────
    section("[2] A1/A2 已命名业务不再显示「未识别的业务数据」")
    rows_a1 = parse_hex(APP_AUTH)
    names_a1 = row_names(rows_a1)
    check("A1 端口 0x1A 解析出端口名「鉴权安全」",
          find(rows_a1, "报文端口号")[3] == "鉴权安全")
    check("A1 出现业务名行「鉴权安全」", "鉴权安全" in names_a1, str(names_a1))
    check("A1 业务名与 MSG_ID_NAMES 同源（单一来源）",
          "鉴权安全" == MSG_ID_NAMES[0x0A0])
    name_row_a1 = try_find(rows_a1, "鉴权安全")
    check("A1 同行说明含业务ID 0x0A0",
          name_row_a1 is not None and "0x0A0" in str(name_row_a1[3]),
          repr(name_row_a1))
    warn_row_a1 = try_find(rows_a1, "⚠ 格式未定义")
    check("A1 出现「⚠ 格式未定义」并注明依据",
          warn_row_a1 is not None
          and "未给出该报文的字段格式" in str(warn_row_a1[3]),
          repr(warn_row_a1))
    check("A1 不再出现「未识别的业务数据(0x0A0)」",
          "未识别的业务数据(0x0A0)" not in all_comments(rows_a1))
    check("A1 原始数据仍完整展示（不丢内容）",
          warn_row_a1 is not None
          and str(warn_row_a1[1]).startswith("11 22 33 44"),
          repr(warn_row_a1))

    rows_a2 = parse_hex(APP_DIST)
    names_a2 = row_names(rows_a2)
    check("A2 出现业务名行「配电信息上报」（端口 0x11）",
          "配电信息上报" in names_a2, str(names_a2))
    check("A2 业务名与 MSG_ID_NAMES 同源",
          "配电信息上报" == MSG_ID_NAMES[0x0A4])
    check("A2「⚠ 格式未定义」行存在", "⚠ 格式未定义" in names_a2)
    check("A2 不再出现「未识别的业务数据(0x0A4)」",
          "未识别的业务数据(0x0A4)" not in all_comments(rows_a2))

    # 0x00A0 / 0x00A4 不得新增专用分支（D4 的理由：两份手写清单漂移即 P0 根因）
    src_payload = code_only(HDC10Parser._parse_app_payload)
    check("D4 fallback 走 MSG_ID_NAMES 查表（静态守卫）",
          "MSG_ID_NAMES.get" in src_payload)
    check("0x00A0/0x00A4 无专用分支（静态守卫，防第二份清单复发）",
          "0x0A0" not in src_payload and "0x0A4" not in src_payload)

    # 反向：表外业务ID 仍应明确报「未识别」+ 注明依据
    rows_unk = parse_hex(APP_UNKNOWN_ID)
    check("表外业务ID 0x005 仍报「未识别的业务数据(0x005)」",
          "未识别的业务数据(0x005)" in all_comments(rows_unk))
    check("表外业务ID 注明「未在本规范报文ID表中定义」",
          "未在本规范报文ID表中定义" in all_comments(rows_unk))
    check("表外业务ID 不显示业务名行（不臆造名字）",
          "原始数据" in row_names(rows_unk))

    # ── A13（F1 回归）：有字段定义但端口不匹配时，不得声称「规范未给出格式」──
    # 独立检查发现：初版 fallback 对**任意**命名业务都说「规范未给出该报文的字段格式」，
    # 但 24 个业务ID 中只有 MSG_ID_NO_FORMAT_DEFINED 的两个真无定义，其余属「有定义、
    # 只是当前端口未命中已实现分支」→ 错误依据（R1 要求依据必须成立）。
    # 本段表驱动扫全 24×3 组合，把两种措辞钉死。
    bad_basis = []
    fallback_hits = 0
    for _biz in sorted(MSG_ID_NAMES):
        for _port in (0x11, 0x12, 0x1A):
            _raw = bytes([_port]) + _biz.to_bytes(2, "little") + b"\x00" + bytes(range(8))
            _rows = PARSER.parse_to_table(_raw, parse_level="app")
            _c = all_comments(_rows)      # 说明列
            _names = row_names(_rows)     # 行名列（措辞在行名，依据在说明）
            if f"业务ID 0x{_biz:03X}：" not in _c:
                continue  # 已命中已实现分支（有真实字段行），本断言不适用
            fallback_hits += 1
            if _biz in MSG_ID_NO_FORMAT_DEFINED:
                _ok = (any("格式未定义" in _n for _n in _names)
                       and "未给出该报文的字段格式" in _c)
            else:
                _ok = (any("未按业务格式解析" in _n for _n in _names)
                       and "未给出该报文的字段格式" not in _c)
            if not _ok:
                bad_basis.append((hex(_port), hex(_biz), _names[-2:], _c[-90:]))
    check("A13 命名 fallback 的依据与「该业务是否真有格式定义」一致（F1 回归）",
          not bad_basis, repr(bad_basis[:2]))
    check("A13 覆盖到「有定义但端口不匹配」的组合（≥20 个）",
          fallback_hits >= 20, f"命中命名 fallback 的组合数={fallback_hits}")
    check("A13 两个真无定义的业务ID 仍在集合内（防扩张）",
          MSG_ID_NO_FORMAT_DEFINED == frozenset({0x0A0, 0x0A4}),
          str(sorted(MSG_ID_NO_FORMAT_DEFINED)))

    # ── [3] A3：端口不再是「是否解析通用头」的开关 ──────────
    section("[3] A3 非白名单端口的应用层报文仍解出完整通用头")
    rows_a3 = parse_hex(APP_PORT13)
    names_a3 = row_names(rows_a3)
    port_row_a3 = try_find(rows_a3, "报文端口号")
    check("A3 端口行显示「保留(0x13)」（不再整段未识别）",
          port_row_a3 is not None and port_row_a3[3] == "保留(0x13)",
          repr(port_row_a3))
    check("A3 报文ID 行存在", "报文ID" in names_a3, str(names_a3))
    check("A3 安全模式行存在", "安全模式" in names_a3)
    check("A3 报文控制字行存在", "报文控制字" in names_a3)
    check("A3 不再出现「未识别格式的应用层数据」",
          "未识别格式的应用层数据" not in all_comments(rows_a3))
    check("A3 弱校验命中（控制字=0）→ 不误标「推测解析」",
          "⚠ 推测解析" not in names_a3, str(names_a3))

    rows_a3c = parse_hex(APP_PORT13_CTRL)
    ctrl_row_a3c = try_find(rows_a3c, "报文控制字")
    check("A3b 控制字非0（0x77）仍解出通用头",
          "报文ID" in row_names(rows_a3c)
          and ctrl_row_a3c is not None and ctrl_row_a3c[3] == "控制字: 0x77",
          repr(ctrl_row_a3c))
    check("A3b 走兜底并注明「⚠ 推测解析」",
          "⚠ 推测解析" in row_names(rows_a3c), str(row_names(rows_a3c)))

    src_app_only = code_only(HDC10Parser._parse_app_only)
    check("D3 判据走 APP_PORTS（单一来源，静态守卫）",
          "APP_PORTS" in src_app_only)
    check("D3 端口白名单三元组硬编码已移除（静态守卫）",
          "(0x11, 0x12, 0x1A)" not in src_app_only)
    check("D3 含控制字弱校验（静态守卫）", "data[3] == 0" in src_app_only)

    # ── [4] A4/A5：分派以 MAC 头类型字段为准 ────────────────
    section("[4] A4/A5 MSDU 分派以 MAC 头声明为准（双向误判修复）")
    # 夹具 idx=0 是标准 MAC 头 + MME（类型 0）帧；只改类型字段看分派是否跟随
    base_frame = frames[0][1]
    base_rows = PARSER._parse_pb_only(base_frame, 1)
    base_type_row = try_find(base_rows, "MSDU类型")
    check("夹具 idx=0 标准头类型字段位置确认（byte8）",
          base_type_row is not None and base_type_row[2] == "0",
          repr(base_type_row))

    rows_48 = PARSER._parse_pb_only(with_msdu_type(base_frame, 0x30), 1)
    names_48 = row_names(rows_48)
    check("A4 msdu_type=48（表10 应用层报文）→ 进入应用层解析",
          "── 应用层报文 ──" in names_48, str(names_48))
    port_row_48 = try_find(rows_48, "报文端口号")
    check("A4 该帧 MSDU 载荷首字节非端口白名单（证明判据不是首字节）",
          port_row_48 is not None and str(port_row_48[1]) == "0x00",
          repr(port_row_48))
    check("A4 不再显示「类型48: 未定义(厂商扩展/待扩展)」",
          "类型48: 未定义" not in all_comments(rows_48))

    rows_128 = PARSER._parse_pb_only(with_msdu_type(base_frame, 0x80), 1)
    check("A4b msdu_type=128（表13 应用层报文）→ 进入应用层解析",
          "── 应用层报文 ──" in row_names(rows_128))

    rows_47 = PARSER._parse_pb_only(with_msdu_type(base_frame, 0x2F), 1)
    check("A4c msdu_type=47（表外）→ **不**进入应用层解析（另一半误判修复）",
          "── 应用层报文 ──" not in row_names(rows_47))
    check("A4c 保留原始数据 + 声明类型提示",
          "类型47: 未定义(厂商扩展/待扩展), 原始数据" in all_comments(rows_47),
          all_comments(rows_47))

    # A5：无 MAC 头上下文（msdu_type=None）时首字节启发式只作为回退
    rows_n1 = PARSER._parse_msdu_payload(bytes.fromhex("2536373809"), 0, msdu_type=None)
    check("A5 msdu_type=None + 首字节 0x25 → 不判为应用层",
          "── 应用层报文 ──" not in row_names(rows_n1), str(row_names(rows_n1)))
    check("A5 回退分支显示 MSDU原始数据行",
          row_names(rows_n1) == ["MSDU数据"], str(row_names(rows_n1)))
    rows_n2 = PARSER._parse_msdu_payload(bytes.fromhex("11010100"), 0, msdu_type=None)
    check("A5b msdu_type=None + 首字节 0x11 → 回退判为应用层",
          "── 应用层报文 ──" in row_names(rows_n2), str(row_names(rows_n2)))
    rows_n3 = PARSER._parse_msdu_payload(b"\x00\x01\x02\x03", 0, msdu_type=None)
    check("A5c msdu_type=None + 首字节 0x00 → 仍判为 MME",
          "── 网络管理消息 ──" in row_names(rows_n3), str(row_names(rows_n3)))

    # IPv4 类型：本次只给明确提示，不展开载荷
    for t, label in ((49, "IP报文"), (129, "IPV4报文")):
        rows_ip = PARSER._parse_msdu_payload(bytes.fromhex("4142434445464748"), 0,
                                             msdu_type=t)
        check(f"类型{t} → 明确提示「{label}」且不展开载荷",
              row_names(rows_ip) == [label]
              and label in str(rows_ip[0][3])
              and "暂不展开IP载荷" in str(rows_ip[0][3]),
              str(rows_ip))

    # ── [5] A6：完整 MPDU 仍走 FC 检测路径 ──────────────────
    section("[5] A6 app 级别收到完整 MPDU 仍走 FC 路径")
    check("A6 _detect_fc(FC 帧) == True", PARSER._detect_fc(FC_FRAME) is True)
    rows_fc = PARSER._parse_app_only(FC_FRAME)
    names_fc = row_names(rows_fc)
    check("A6 首行为 FC 字段（非应用层）",
          names_fc[0] == "定界符类型(DT)", str(names_fc[:3]))
    check("A6 解出 FCCS 行", "帧控制校验序列(FCCS)" in names_fc)
    check("A6 行数与改动前基线一致（78 行）", len(rows_fc) == 78, str(len(rows_fc)))
    check("A6 不出现「未识别格式的应用层数据」",
          "未识别格式的应用层数据" not in all_comments(rows_fc))

    # A6d：FC 的 byte3 是网络标识(NID)高字节，取 0 时**不能**被「控制字弱校验」抢走。
    # 这是 D3 判据里 `and not has_fc` 的存在理由（A6：完整 MPDU 仍走 FC 路径）。
    fc_zero_nid = bytearray(FC_FRAME)
    fc_zero_nid[3] = 0x00
    fc_zero_nid[13:16] = hdc10_parser._crc24(bytes(fc_zero_nid[:13])).to_bytes(3, "little")
    check("A6d 构造帧仍通过 FCCS（前提前置）",
          PARSER._detect_fc(bytes(fc_zero_nid)) is True)
    check("A6d NID 高字节=0 的完整 MPDU 仍走 FC 路径（弱校验不抢）",
          row_names(PARSER._parse_app_only(bytes(fc_zero_nid)))[0] == "定界符类型(DT)",
          str(row_names(PARSER._parse_app_only(bytes(fc_zero_nid)))[:3]))

    rows_short = PARSER._parse_app_only(bytes.fromhex("1120"))
    check("A6b 长度<4 明确报错（不返回空白结果）",
          str(rows_short[0][0]).startswith("❌")
          and "长度不足4字节" in str(rows_short[0][3]),
          str(rows_short[0]))
    try:
        rows_empty = PARSER._parse_app_only(b"")
        ok_empty = str(rows_empty[0][0]).startswith("❌")
    except Exception as exc:  # pragma: no cover - 仅记录异常
        ok_empty = False
        print(f"      [异常] 空输入: {type(exc).__name__}: {exc}")
    check("A6c 空输入不抛异常", ok_empty)

    # ── [6] A7：安全模式提示 + 既有字段逐行不变 ─────────────
    section("[6] A7 sec_mode != 0 醒目提示，且业务字段逐行不变")
    rows_ts2 = parse_hex(APP_TS_SEC2)
    names_ts2 = row_names(rows_ts2)
    check("A7 出现「⚠ 安全保护」提示行", "⚠ 安全保护" in names_ts2, str(names_ts2))
    warn = try_find(rows_ts2, "⚠ 安全保护")
    check("A7 提示行解析值/说明标明安全模式名",
          warn is not None and warn[2] == "数据完整性保护"
          and "可能无效" in str(warn[3]),
          repr(warn))
    check("A7 提示行紧跟在「安全模式」行之后",
          "⚠ 安全保护" in names_ts2
          and names_ts2.index("⚠ 安全保护") == names_ts2.index("安全模式") + 1,
          str(names_ts2))
    check("A7 提示行高亮范围 = 报文ID 字段（偏移 1~2）",
          warn is not None and (warn[4], warn[5]) == (1, 2) and warn[1] == "0x2",
          repr(warn))

    # 去掉新提示行后必须与改动前基线**逐行逐字节一致**（R6）
    stripped = tuple(r for r in row_tuples(rows_ts2) if str(r[0]).strip() != "⚠ 安全保护")
    check("A7 去除提示行后与改动前基线逐行一致（10 行）",
          stripped == A7_SEC2_GOLDEN,
          f"\n      实际={stripped}\n      基线={A7_SEC2_GOLDEN}")

    rows_ts0 = parse_hex(APP_TS_SEC0)
    check("A7 sec_mode=0（0x0004）不插入提示行",
          "⚠ 安全保护" not in row_names(rows_ts0), str(row_names(rows_ts0)))
    biz_i2 = row_names(rows_ts2).index("── 业务数据 ──")
    biz_i0 = row_names(rows_ts0).index("── 业务数据 ──")
    check("A7 业务数据段逐行一致（安全模式不影响业务解析）",
          row_tuples(rows_ts2)[biz_i2 + 1:] == row_tuples(rows_ts0)[biz_i0 + 1:],
          f"{row_tuples(rows_ts2)[biz_i2 + 1:]} != {row_tuples(rows_ts0)[biz_i0 + 1:]}")
    check("A7 提示行源码守卫（静态守卫）",
          "⚠ 安全保护" in code_only(HDC10Parser._parse_application_layer))

    # ── [7] A8：真实夹具全量回归 ───────────────────────────
    section("[7] A8 真实帧夹具（60 帧）")
    crashed = []
    for i, (_fi, fb, _key) in enumerate(frames):
        try:
            out = PARSER._parse_pb_only(fb, 1)
            if not isinstance(out, list):
                crashed.append((i, "非 list"))
        except Exception as exc:  # pragma: no cover - 仅记录异常
            crashed.append((i, f"{type(exc).__name__}: {exc}"))
    check("A8 全部 60 帧解析不抛异常", not crashed, str(crashed))

    # 分派语义：MAC 头声明的类型决定是否应用层（逐帧对拍，无硬编码 idx）
    sem_violations = []
    for i, (_fi, fb, _key) in enumerate(frames):
        rows = PARSER._parse_pb_only(fb, 1)
        names = row_names(rows)
        trow = next((r for r in rows if str(r[0]).strip() in ("MSDU类型", "消息类型")), None)
        if trow is None:
            sem_violations.append((i, "无类型行"))
            continue
        t = int(str(trow[2]).strip())
        has_app = "── 应用层报文 ──" in names
        if t in APP_MSDU_TYPES and not has_app:
            sem_violations.append((i, f"类型{t} 应进应用层却未进"))
        elif t not in APP_MSDU_TYPES and t != 0 and has_app:
            sem_violations.append((i, f"类型{t} 非应用层却进了"))
        elif t == 0 and "── 网络管理消息 ──" not in names:
            sem_violations.append((i, "类型0 应进 MME 却未进"))
    check("A8 分派与 MAC 头声明类型逐帧一致", not sem_violations,
          str(sem_violations))

    app_idx = {
        i for i, (_fi, fb, _k) in enumerate(frames)
        if "── 应用层报文 ──" in row_names(PARSER._parse_pb_only(fb, 1))
    }
    decl_idx = {i for i, (_fi, _fb, k) in enumerate(frames)
                if k[0].isdigit() and int(k[0]) in APP_MSDU_TYPES}
    check("A8 进入应用层的帧集合 == 夹具声明类型 ∈ {48,128} 的帧集合",
          app_idx == decl_idx, f"实际={sorted(app_idx)} 声明={sorted(decl_idx)}")
    check("A8 该集合正是 {3, 48, 50}（改动前为 {3, 9}）",
          app_idx == {3, 48, 50}, str(sorted(app_idx)))

    # 真实业务帧（key[1] != '-'）应仍解出 MME 类型（MME 路径不回归）
    real_biz = [k for _fi, _fb, k in frames if k[1] != "-"]
    found_mmtype = set()
    for _fi, fb, k in frames:
        if k[1] == "-":
            continue
        for r in PARSER._parse_pb_only(fb, 1):
            if str(r[0]).strip() == "消息类型(MMTYPE)":
                found_mmtype.add(str(r[2]).strip())
    check("A8 真实业务帧（%d 帧）MMTYPE 解析未回归" % len(real_biz),
          {"0x0008", "0x000B", "0x0001"} <= found_mmtype, str(sorted(found_mmtype)))

    # R6：除 DIFF_FRAMES 三帧外，其余 57 帧输出与改动前基线逐字节一致
    check("A8 其余 57 帧输出指纹与改动前基线一致（R6）",
          fingerprint_unchanged_frames(frames) == UNCHANGED_FRAMES_SHA256,
          fingerprint_unchanged_frames(frames))

    # ── [8] A9：Fuzz 936 组合零崩溃 ────────────────────────
    section("[8] A9 Fuzz：业务ID × 端口 × 长度 零崩溃")
    # 936 = 24 个业务ID（MSG_ID_NAMES 全集）× 3 个端口 × 13 个长度（0~12）
    fuzz_ids = sorted(MSG_ID_NAMES)
    fuzz_ports = tuple(APP_PORTS)  # 3 个
    fuzz_lens = range(13)  # 0~12
    total = len(fuzz_ids) * len(fuzz_ports) * len(fuzz_lens)
    check("A9 组合数 == 936（%d 业务ID × 3 端口 × 13 长度）" % len(fuzz_ids),
          total == 936, str(total))
    bad = []
    for port in fuzz_ports:
        for mid in fuzz_ids:
            for n in fuzz_lens:
                payload = bytes((i * 37 + n * 11) & 0xFF for i in range(n))
                frame = bytes([port]) + mid.to_bytes(2, "little") + b"\x00" + payload
                try:
                    rows = PARSER._parse_app_only(frame)
                except Exception as exc:  # pragma: no cover - 仅记录异常
                    bad.append((port, hex(mid), n, f"{type(exc).__name__}: {exc}"))
                    continue
                if not rows:
                    bad.append((port, hex(mid), n, "空表"))
                elif any(len(r) < 4 for r in rows):
                    bad.append((port, hex(mid), n, "行字段数不足4"))
    check("A9 936 组合全部无异常且产出完整行", not bad, str(bad[:5]))

    # 表外业务ID（不在 MSG_ID_NAMES）与端口表外端口同样不得崩溃
    extra_bad = []
    for mid in (0x000, 0x347):
        for port in fuzz_ports:
            for n in fuzz_lens:
                payload = bytes((i * 29 + n) & 0xFF for i in range(n))
                frame = bytes([port]) + mid.to_bytes(2, "little") + b"\x00" + payload
                try:
                    if not PARSER._parse_app_only(frame):
                        extra_bad.append((port, hex(mid), n, "空表"))
                except Exception as exc:  # pragma: no cover - 仅记录异常
                    extra_bad.append((port, hex(mid), n, f"{type(exc).__name__}: {exc}"))
    check("A9b 表外业务ID（0x000/0x347）额外 78 组合同样零崩溃",
          not extra_bad, str(extra_bad[:5]))

    # 安全模式覆盖 0~3：提示行出现 当且仅当 sec_mode != 0
    sec_bad = []
    for sec in range(4):
        for port in fuzz_ports:
            for n in (0, 3, 6):
                mid = (sec << 12) | 0x004  # 业务ID 0x004「校时」
                payload = bytes((i * 13 + n) & 0xFF for i in range(n))
                frame = bytes([port]) + mid.to_bytes(2, "little") + b"\x00" + payload
                rows = PARSER._parse_app_only(frame)
                has_warn = "⚠ 安全保护" in row_names(rows)
                if has_warn != bool(sec):
                    sec_bad.append((sec, port, n, has_warn))
    check("A9 安全模式 0~3：提示行出现当且仅当 sec_mode != 0",
          not sec_bad, str(sec_bad))

    # ── [9] 摘要：两端黑名单同步 + 不挤占关键业务字段 ───────
    section("[9] 摘要（陷阱44：两端黑名单同步、新行不挤占关键字段位）")
    desktop_meta = main_gui._GW_APP_META_FIELDS
    web_meta = web_utils._GW_APP_META_FIELDS
    check("两端黑名单集合一致（防单边改）",
          set(desktop_meta) == set(web_meta),
          f"仅桌面={set(desktop_meta) - set(web_meta)} 仅Web={set(web_meta) - set(desktop_meta)}")
    check("两端黑名单均含「⚠ 安全保护」",
          "⚠ 安全保护" in desktop_meta and "⚠ 安全保护" in web_meta)

    for tag, rows in (("A1", rows_a1), ("A2", rows_a2), ("A7", rows_ts2),
                      ("A3b", rows_a3c)):
        d_biz, d_fields = main_gui._gw_app_biz_summary(rows)
        w_biz, w_fields = web_utils._gw_app_biz_summary(rows)
        check(f"摘要 {tag}：两端业务名一致（{d_biz!r}）", d_biz == w_biz,
              f"{d_biz!r} != {w_biz!r}")
        check(f"摘要 {tag}：关键字段两头一致且不含新提示行",
              d_fields == w_fields
              and not any("安全保护" in f or "格式未定义" in f for f in d_fields),
              f"桌面={d_fields} Web={w_fields}")
    check("摘要 A1 业务名 = 鉴权安全（提示行不挤占业务名）",
          main_gui._gw_app_biz_summary(rows_a1)[0] == "鉴权安全",
          repr(main_gui._gw_app_biz_summary(rows_a1)))
    check("摘要 A2 业务名 = 配电信息上报",
          main_gui._gw_app_biz_summary(rows_a2)[0] == "配电信息上报",
          repr(main_gui._gw_app_biz_summary(rows_a2)))
    check("摘要 A7 安全提示不挤占业务名（仍为校时报文）",
          main_gui._gw_app_biz_summary(rows_ts2)[0] == "校时报文",
          repr(main_gui._gw_app_biz_summary(rows_ts2)))

    # ── [10] ED 包装/其它常量未受影响（防误伤） ─────────────
    section("[10] 相邻能力未受影响")
    check("APP_PORTS 仍为 {0x11, 0x12, 0x1A}（批量前缀剥离依赖它）",
          tuple(sorted(APP_PORTS)) == (0x11, 0x12, 0x1A), str(sorted(APP_PORTS)))
    check("MSG_ID_NAMES 仍含 0x0A0/0x0A4（名字表未删）",
          0x0A0 in MSG_ID_NAMES and 0x0A4 in MSG_ID_NAMES)
    check("MSDU_TYPES/SINGLEHOP_MSG_TYPES 内容未改（字段名单一来源）",
          MSDU_TYPES == {0: "网络管理消息", 48: "应用层报文", 49: "IP报文"}
          and SINGLEHOP_MSG_TYPES == {0: "发现列表消息", 128: "应用层报文",
                                      129: "IPV4报文"})
    check("顶格字段名与旧值 reg 一致（报文端口号/报文ID/安全模式/报文控制字）",
          all(n in row_names(rows_ts2)
              for n in ("报文端口号", "报文ID", "安全模式", "业务报文ID", "报文控制字")))
    check("hdc10_parser 无未定义名（F821 守卫，复用 1.23.19 的手段）",
          "F821" not in _ruff_f821())

    print(f"\n结果：PASS={PASS}  FAIL={len(FAILURES)}")
    if FAILURES:
        for name in FAILURES:
            print(f"  FAIL: {name}")
    return 0 if not FAILURES else 1


def _ruff_f821():
    """对 hdc10_parser.py 跑 ruff F821（环境无 ruff 时返回空串，不误报失败）"""
    import subprocess

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--select", "F821",
             "--no-cache", "hdc10_parser.py"],
            cwd=str(ROOT), capture_output=True, text=True,
        )
    except Exception:
        return ""
    out = (proc.stdout or "") + (proc.stderr or "")
    if "No module named" in out or "unrecognized" in out:
        return ""
    return out


if __name__ == "__main__":
    sys.exit(main())
