# -*- coding: utf-8 -*-
"""协议11（HDC 1.0）通信测试命令 0x006 —— 检测扩展命令解析（A-HS-11-03 表2）

用户（2026-09-20）:
    01 00 00 00 00 F0 FF FE … 11 06 00 00 01 61 30 00 67 2B 0C 98 … EF F1 22
    这个报文为何解析的不对，这个是切频操作，目标频段3。

依据（新提供的规范，已转 MD）:
    ``协议文档/11.HDC协议/A-HS-11-03 国网双模通信测试用例提案_20210414.md``
    - 1.2 检测扩展命令 / 表2 扩展命令
    - 表32 通信测试下行报文格式（协议版本号 / 报文头长度 / 保留 /
      转发数据的规约类型 / 转发数据长度(12bit)）
    - 表2 注意事项第7条：扩展命令格式 nid=0、源TEI=0、目的TEI=FFF

槽位约定（与协议9/10 同构）：``(字段, 原始值, 解析值, 说明, 起, 止)``。
**名称放解析值槽**（协议10 约定），``main_gui._extract_test_mode_content``
按「非数值者即名称」探测；纯元数据行解析值留空（摘要按「解析值非空」过滤）。

覆盖:
  [1] 用户报文端到端：测试模式=6 频段切换操作 + 频段值=3 → 通信频段3
  [2] 表2 各测试模式的 12bit 配置值解释（频段/ToneMask/信道号/MCS/持续时间）
  [3] 普通通信测试（测试模式=0）仍按表32 原义（不得被扩展语义污染）
  [4] 真实帧回归（TMI 日志中同样被误读的 0x006 帧）
  [5] 边界：数据不足 / 模式12 的 MCS 三元组 / 模式13 的安全测试模式名
  [6] 模式表防漂移：EXT_TEST_MODES 与表2 的 15 项取值一一对应

运行: python -X utf8 -u test/test_hdc10_comm_test_ext.py
"""

import os
import pickle
import sys

import _path_setup  # noqa: E402,F401

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hdc10_parser import (  # noqa: E402
    EXT_BAND_RANGES,
    EXT_MAX_DURATION_MIN,
    EXT_SEC_MODES,
    EXT_TEST_MODES,
    HDC10Parser,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

PASS = 0
FAIL = 0
FAILED = []

# 用户给的完整报文：协议11 SOF 帧 + MAC + 应用层(端口0x11 / 报文ID 0x0006)
USER_FRAME = bytes.fromhex(
    "0100000000F0FFFE1D186B4300A7A79AC00000FF1F000400"
    "300800FF00000100001106000001613000672B0C98"
    + "00" * 104
    + "EFF122"
)
# 业务数据（端口1B + 报文ID2B + 控制字1B 之后的 4 字节）
USER_PAYLOAD = bytes.fromhex("01613000")

PICKLE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "hdc10_real_frames.pkl")


def section(title):
    print(f"\n{title}")


def check(desc, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {desc}")
    else:
        FAIL += 1
        FAILED.append(desc)
        print(f"  ✗ {desc}" + (f"\n      {detail}" if detail else ""))


def rows_of(payload):
    return HDC10Parser()._parse_comm_test(payload, 0)


def _cell(rows, name, idx):
    for r in rows:
        if str(r[0]).strip() == name:
            return str(r[idx]).strip()
    return None


def raw(rows, name):
    """原始值列（索引 1）"""
    return _cell(rows, name, 1)


def val(rows, name):
    """解析值列（索引 2）"""
    return _cell(rows, name, 2)


def cmt(rows, name):
    """说明列（索引 3）"""
    return _cell(rows, name, 3)


def build(mode, band_or_val=0, b0=0x01, b1_low=0x01, proto=0x00, sec=0, b5=0):
    """按表2 组装扩展命令载荷：字节0/1 头 + 字节2/3 的 12bit 配置值 + 字节4/5"""
    b1 = ((mode & 0x0F) << 4) | (b1_low & 0x0F)
    b2 = ((band_or_val & 0x0F) << 4) | (proto & 0x0F)
    b3 = (band_or_val >> 4) & 0xFF
    return bytes([b0, b1, b2, b3, sec & 0xFF, b5 & 0xFF])


def main():
    # ── [1] 用户报文端到端 ──────────────────────────────────────
    section("[1] 用户报文：切频操作 / 目标频段3（表2 第6条）")
    p = HDC10Parser()
    all_rows = p.parse_to_table(USER_FRAME)

    check("报文ID = 0x0006 (通信测试)", val(all_rows, "报文ID") == "0x0006",
          str(val(all_rows, "报文ID")))
    check("协议版本号 = 1（本版本固定为1）",
          val(all_rows, "协议版本号") == "1", str(val(all_rows, "协议版本号")))
    check("测试模式/配置操作 = 频段切换操作（原始值 6）",
          val(all_rows, "测试模式/配置操作") == "频段切换操作"
          and raw(all_rows, "测试模式/配置操作") == "6",
          f"{val(all_rows, '测试模式/配置操作')} / "
          f"{raw(all_rows, '测试模式/配置操作')}")
    check("频段值(目标频段) 原始值 = 3", raw(all_rows, "频段值(目标频段)") == "3",
          str(raw(all_rows, "频段值(目标频段)")))
    check("目标频段说明 = 通信频段3（1.758~2.930MHz）",
          val(all_rows, "频段值(目标频段)") == "通信频段3（1.758~2.930MHz）",
          str(val(all_rows, "频段值(目标频段)")))
    check("安全测试模式字段 = 应为0（≠13 时，表2 注意事项第9条）",
          val(all_rows, "安全测试模式字段") == "应为0"
          and raw(all_rows, "安全测试模式字段") == "0",
          f"{val(all_rows, '安全测试模式字段')} / "
          f"{raw(all_rows, '安全测试模式字段')}")
    check("不再出现误读的「转发数据长度」（旧版把 0x3000 当长度）",
          val(all_rows, "转发数据长度") is None,
          str(val(all_rows, "转发数据长度")))

    rows = rows_of(USER_PAYLOAD)
    check("_parse_comm_test(01 61 30 00) 命中切频模式",
          val(rows, "测试模式/配置操作") == "频段切换操作",
          str([r[0] for r in rows]))

    # ── [2] 表2 各模式的 12bit 配置值解释 ────────────────────────
    section("[2] 表2 各测试模式：12bit 配置值按模式解释")
    for band, expect in sorted(EXT_BAND_RANGES.items()):
        r = rows_of(build(6, band))
        check(f"模式6 频段值={band} → {expect}",
              raw(r, "频段值(目标频段)") == str(band)
              and val(r, "频段值(目标频段)") == expect,
              f"{raw(r, '频段值(目标频段)')} / {val(r, '频段值(目标频段)')}")
    r = rows_of(build(7, 2))
    check("模式7 → ToneMask值 原始值 2",
          raw(r, "ToneMask值(目标ToneMask)") == "2"
          and val(r, "ToneMask值(目标ToneMask)") == "目标ToneMask: 2",
          f"{raw(r, 'ToneMask值(目标ToneMask)')} / "
          f"{val(r, 'ToneMask值(目标ToneMask)')}")
    r = rows_of(build(8, 5))
    check("模式8 → 无线信道号 原始值 5",
          raw(r, "无线信道号") == "5"
          and val(r, "无线信道号") == "目标无线信道号: 5",
          f"{raw(r, '无线信道号')} / {val(r, '无线信道号')}")
    for mode in (3, 4, 5, 9, 10, 11):
        r = rows_of(build(mode, 30))
        check(f"模式{mode} → 模式持续时间 = 30分钟",
              val(r, "模式持续时间/配置值") == "30分钟",
              str(val(r, "模式持续时间/配置值")))
    r = rows_of(build(3, 100))
    check(f"模式3 配置值100 → 提示超限限定{EXT_MAX_DURATION_MIN}分钟",
          f"超限,限定{EXT_MAX_DURATION_MIN}分钟"
          in str(val(r, "模式持续时间/配置值")),
          str(val(r, "模式持续时间/配置值")))
    r = rows_of(build(1, 0))
    check("模式1 → 配置值 = 填0即可",
          val(r, "模式持续时间/配置值") == "填0即可",
          str(val(r, "模式持续时间/配置值")))

    # ── [3] 普通通信测试（测试模式=0）保持表32 原义 ───────────────
    section("[3] 测试模式=0：普通通信测试（表32 原义，不被扩展语义污染）")
    # 字节1 = 0x01 → 高4位=0（普通通信测试）、低4位=1（报文头长度续）
    # 字节2 = 0x33 → 规约类型=3(DL/T698.45) + 长度低4位=3
    # 字节3 = 0x00 → 长度高8位=0 → 转发数据长度 = 3 字节
    plain = bytes([0x01, 0x01, 0x33, 0x00, 0xAA, 0xBB, 0xCC])
    r = rows_of(plain)
    check("普通通信测试：保留 原始值 = 0 且解析值留空（摘要不留噪声）",
          raw(r, "保留") == "0" and val(r, "保留") == "",
          f"{raw(r, '保留')!r} / {val(r, '保留')!r}")
    check("普通通信测试：转发数据规约类型 = 3 (DL/T698.45)",
          val(r, "转发数据规约类型") == "3"
          and cmt(r, "转发数据规约类型") == "DL/T698.45",
          f"{val(r, '转发数据规约类型')} / {cmt(r, '转发数据规约类型')}")
    check("普通通信测试：转发数据长度 = 3字节",
          val(r, "转发数据长度") == "3字节", str(val(r, "转发数据长度")))
    check("普通通信测试：测试数据(原始值) = AA BB CC",
          raw(r, "测试数据") == "AA BB CC", str(raw(r, "测试数据")))
    check("普通通信测试：不出现「测试模式/配置操作」",
          val(r, "测试模式/配置操作") is None)
    check("普通通信测试：仍有 协议版本号 / 报文头长度（表32 字段）",
          val(r, "协议版本号") is not None and val(r, "报文头长度") is not None)

    # ── [4] 真实帧回归（TMI 日志中的 0x006 帧）────────────────────
    section("[4] 真实帧回归：TMI 日志中同样被误读的 0x006 帧")
    if os.path.exists(PICKLE):
        with open(PICKLE, "rb") as f:
            frames = pickle.load(f)
        hit = None
        for i, (_fi, fb, _key) in enumerate(frames):
            rr = HDC10Parser()._parse_pb_only(fb, 1)
            if any(str(x[0]).strip() == "通信测试报文" for x in rr):
                hit = (i, rr)
                break
        check("真实夹具中存在 0x006 通信测试帧", hit is not None)
        if hit:
            i, rr = hit
            print(f"    帧#{i}: 测试模式={val(rr, '测试模式/配置操作')} "
                  f"频段值={raw(rr, '频段值(目标频段)')}")
            check("真实帧解出「测试模式/配置操作」",
                  val(rr, "测试模式/配置操作") is not None,
                  str([x[0] for x in rr if "测试" in str(x[0])]))
            check("真实帧为频段切换操作且解出目标频段",
                  val(rr, "测试模式/配置操作") == "频段切换操作"
                  and raw(rr, "频段值(目标频段)") == "1",
                  f"{val(rr, '测试模式/配置操作')} / "
                  f"{raw(rr, '频段值(目标频段)')}")
    else:
        check("真实夹具存在", False, PICKLE)

    # ── [5] 边界 ────────────────────────────────────────────────
    section("[5] 边界：数据不足 / 模式12 MCS / 模式13 安全测试模式")
    check("不足4字节 → 空表（不抛异常）", rows_of(b"\x01\x61\x30") == [])
    check("空载荷 → 空表", rows_of(b"") == [])
    r = rows_of(build(12, 7, sec=0x25, b5=0x31))
    check("模式12 → MCS值 原始值 7",
          raw(r, "MCS值") == "7" and val(r, "MCS值") == "MCS值: 7",
          f"{raw(r, 'MCS值')} / {val(r, 'MCS值')}")
    check("模式12 → PHR_MCS = MCS 2", val(r, "PHR_MCS") == "MCS 2",
          str(val(r, "PHR_MCS")))
    check("模式12 → PSDU_MCS = MCS 1", val(r, "PSDU_MCS") == "MCS 1",
          str(val(r, "PSDU_MCS")))
    check("模式12 → PbSIZE = PbSIZE 3", val(r, "PbSIZE") == "PbSIZE 3",
          str(val(r, "PbSIZE")))
    r = rows_of(build(13, 60, sec=0x07))
    check("模式13 → 安全测试模式 = AES-CBC加密测试（原始值 7）",
          val(r, "安全测试模式") == "AES-CBC加密测试"
          and raw(r, "安全测试模式") == "7",
          f"{val(r, '安全测试模式')} / {raw(r, '安全测试模式')}")
    check("模式13 不再输出「安全测试模式字段」占位行",
          val(r, "安全测试模式字段") is None)
    r = rows_of(build(14, 0))
    check("模式14（表内无）→ 保留(14)",
          val(r, "测试模式/配置操作") == "保留(14)",
          str(val(r, "测试模式/配置操作")))

    # ── [6] 模式表防漂移 ────────────────────────────────────────
    section("[6] 模式表与 A-HS-11-03 表2 一一对应（防漂移）")
    expect_modes = {
        1: "转发应用层报文至应用层串口信道测试模式(暂未使用)",
        2: "转发应用层报文至载波信道测试模式(暂未使用)",
        3: "HPLC物理层透传测试模式",
        4: "HPLC物理层回传测试模式",
        5: "MAC层透传测试模式",
        6: "频段切换操作",
        7: "ToneMask配置操作",
        8: "无线信道切换操作",
        9: "RF物理层回传测试模式",
        10: "RF物理层透传测试模式",
        11: "RF/PLC物理层回传测试模式",
        12: "PLC到RF物理层回传测试模式",
        13: "安全测试模式",
        15: "新一代扩展测试模式",
    }
    check("EXT_TEST_MODES 与表2 完全一致", EXT_TEST_MODES == expect_modes,
          str({k: (EXT_TEST_MODES.get(k), v) for k, v in expect_modes.items()
               if EXT_TEST_MODES.get(k) != v}))
    check("EXT_SEC_MODES 覆盖表2 的 12 个安全测试模式", len(EXT_SEC_MODES) == 12,
          str(sorted(EXT_SEC_MODES)))
    check("EXT_BAND_RANGES 覆盖表2 的 4 个通信频段", len(EXT_BAND_RANGES) == 4,
          str(sorted(EXT_BAND_RANGES)))

    print(f"\n═══ 结果: {PASS} 通过, {FAIL} 失败 ═══")
    for n in FAILED:
        print(f"  - {n}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
