# -*- coding: utf-8 -*-
"""协议6 645 转表字节偏移矩阵（任务 09-17-web-gui-parity-sync R2.2）

背景：`protocol_registry.DLT645GuiParser.parse_to_table` 的字节偏移原用帧内**声明长度**
`total_len = 10 + data_len + 2`。1.23.22 起「声明长度与实际不符」的帧不再拒解析
（AGENTS §8 陷阱 49）→ 该公式必然越界：实测帧 `68AAAAAAAAAAAA6811082CDD32375316`
只有 16 字节，校验和偏移却算成 18。

本测试钉住（对应 prd R2.2 与 implement 步骤 3.3）：
  A 合法帧输出**逐行不变**（硬约束）——偏移同时满足新旧两式
  B 声明长度不符帧：校验和 / ⚠校验和错误 = 实际帧长-2；帧结束符 = 实际帧长-1；
    数据内容/数据域末端受实际帧长约束（不超过 帧长-3）
  C 声明长度过长（截断帧）：末端被夹取，不越界
  D frame_len < 12 降级路径：不抛异常、不产生负偏移
  E 单一来源守卫：645 转表只剩 protocol_registry 一份，reflex_web / 测试不得再有复制体

直接运行: python test/test_dlt645_table_offsets.py
"""

import _path_setup  # noqa: E402,F401

import re
import sys
from pathlib import Path

from dlt645_frame_gen import DLT645FrameGenerator  # noqa: E402
from dlt645_parser import DLT645Parser  # noqa: E402
import protocol_registry  # noqa: E402

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


ROOT = Path(__file__).resolve().parent.parent
GUI = protocol_registry.DLT645GuiParser(DLT645Parser())

GEN = DLT645FrameGenerator()
ADDR = "000000000001"

# 合法帧：读电压块应答，DI=02E60101 + 6 字节数据 → data_len=0x0A → 帧长 10+10+2 = 22
LEGAL = GEN.build_frame(ADDR, 0x91, bytes.fromhex("0101E602") + b"\x00" * 6)
# 用户现场实测：声明 L=08，实际 16 字节
MISMATCH_SHORT = bytes.fromhex("68AAAAAAAAAAAA6811082CDD32375316")


def _set_data_length(frame: bytes, value: int) -> bytes:
    """只改数据长度声明字节（索引 9），其余原样，用于隔离单一变量。"""
    b = bytearray(frame)
    b[9] = value
    return bytes(b)


def _row(table, field_name):
    for row in table:
        if row[0] == field_name:
            return row
    return None


def _row_containing(table, keyword):
    for row in table:
        if keyword in str(row[0]):
            return row
    return None


# ═══════════════════════════════════════════════════════════════
# A 合法帧：偏移与新式/旧式同时成立（= 逐行不变）
# ═══════════════════════════════════════════════════════════════

def test_legal_frame_unchanged():
    print("\n[1] A 合法帧输出逐行不变（新旧公式在合法帧上等价）")

    table = GUI.parse_to_table(LEGAL)
    frame_len = len(LEGAL)
    data_len = LEGAL[9]
    declared_total = 10 + data_len + 2

    check("A 合法帧满足 frame_len == 声明总长",
          frame_len == declared_total, f"{frame_len} vs {declared_total}")

    cs = _row(table, "校验和")
    end = _row(table, "帧结束符")
    check("A 校验和行存在", cs is not None)
    check("A 帧结束符行存在", end is not None)
    if cs and end:
        check("A 校验和偏移 == 声明总长-2 == 实际帧长-2",
              cs[4] == declared_total - 2 and cs[5] == declared_total - 2
              and cs[4] == frame_len - 2,
              f"{cs[4]}~{cs[5]}")
        check("A 帧结束符偏移 == 声明总长-1 == 实际帧长-1",
              end[4] == declared_total - 1 and end[5] == declared_total - 1
              and end[4] == frame_len - 1,
              f"{end[4]}~{end[5]}")

    data_row = _row(table, "数据内容") or _row(table, "数据域")
    if data_row is not None:
        check("A 数据内容/数据域末端 == 声明值（合法帧未被夹取）",
              data_row[5] == 10 + data_len - 1, str(data_row))
    else:
        # 645 扩展 DI 帧会被深度展开成子行，不再有字面「数据内容」行
        check("A 合法帧无「数据内容/数据域」行（已深度展开）", True)

    check("A 表内每行 6 列（GUI/Web 同一形状）", all(len(r) == 6 for r in table),
          str([len(r) for r in table]))
    check("A 合法帧不含任何 ⚠/❌ 提示行",
          not any(str(r[0]).startswith(("⚠", "❌")) for r in table),
          str([r[0] for r in table])[:150])


# ═══════════════════════════════════════════════════════════════
# B 声明长度不符（过短声明）：偏移必须用实际帧长
# ═══════════════════════════════════════════════════════════════

def test_declared_shorter_offsets():
    print("\n[2] B 声明 L=08 / 实际 16 字节：校验和 14 · 帧结束符 15")

    table = GUI.parse_to_table(MISMATCH_SHORT)
    frame_len = len(MISMATCH_SHORT)
    check("B 实测帧长 = 16", frame_len == 16, str(frame_len))
    check("B 转表非空（不空白）", len(table) > 0, str(len(table)))

    cs = _row(table, "校验和")
    warn = _row_containing(table, "校验和错误")
    end = _row(table, "帧结束符")

    check("B 校验和偏移 == 帧长-2 = [14,14]",
          cs is not None and cs[4] == 14 and cs[5] == 14, str(cs))
    check("B ⚠校验和错误偏移 == [14,14]（行名含「校验和」→ 落到 CS 字节）",
          warn is not None and warn[4] == 14 and warn[5] == 14, str(warn))
    check("B 帧结束符偏移 == 帧长-1 = [15,15]",
          end is not None and end[4] == 15 and end[5] == 15, str(end))

    # 越界回归：任一行的偏移不得超过帧尾
    worst = max((max(r[4], r[5]) for r in table), default=0)
    check("B 无任何偏移越过帧尾（旧公式会算到 18/19）",
          worst <= frame_len - 1, f"max={worst} frame_len-1={frame_len - 1}")

    # 数据内容/数据域末端受实际帧长约束
    data_row = _row_containing(table, "数据内容") or _row_containing(table, "数据域")
    if data_row is not None:
        check("B 数据内容/数据域末端不超过 帧长-3",
              data_row[5] <= frame_len - 3, str(data_row))
    else:
        check("B 数据内容/数据域行缺失（该帧无业务数据域）", True)

    # DI 偏移固定（与长度声明无关）
    di = _row(table, "数据标识 DI")
    check("B 数据标识 DI 偏移恒为 [10,13]", di is not None and di[4] == 10 and di[5] == 13,
          str(di))


# ═══════════════════════════════════════════════════════════════
# C 声明长度过长（截断帧）：末端被夹取
# ═══════════════════════════════════════════════════════════════

def test_declared_longer_offsets():
    print("\n[3] C 声明 L=20H / 实际短帧：末端夹取到 帧长-3，校验和 帧长-2")

    over = _set_data_length(LEGAL, 0x20)
    table = GUI.parse_to_table(over)
    check("C 声明长度不符时仍出表", len(table) > 0, str(len(table)))

    cs = _row(table, "校验和")
    end = _row(table, "帧结束符")
    check("C 校验和偏移 == 实际帧长-2",
          cs is not None and cs[4] == len(over) - 2 and cs[5] == len(over) - 2, str(cs))
    check("C 帧结束符偏移 == 实际帧长-1",
          end is not None and end[4] == len(over) - 1 and end[5] == len(over) - 1, str(end))

    data_row = _row_containing(table, "数据内容") or _row_containing(table, "数据域")
    if data_row is not None:
        check("C 数据内容/数据域末端夹取到 帧长-3",
              data_row[5] == len(over) - 3, str(data_row))

    worst = max((max(r[4], r[5]) for r in table), default=0)
    check("C 无任何偏移越过帧尾", worst <= len(over) - 1, f"max={worst}")


# ═══════════════════════════════════════════════════════════════
# D 降级路径：短帧 / 空输入不抛异常、不产生负偏移
# ═══════════════════════════════════════════════════════════════

def test_degrade_no_negative_offsets():
    print("\n[4] D frame_len < 12 降级：不抛异常 + 无负偏移")

    cases = {
        "空输入": b"",
        "1 字节": b"\x68",
        "8 字节": bytes.fromhex("68AAAAAAAAAAAA68"),
        "11 字节": bytes.fromhex("68AAAAAAAAAAAA681108")[:11],
    }
    for label, data in cases.items():
        try:
            table = GUI.parse_to_table(data)
        except Exception as ex:  # noqa: BLE001 - 测试需捕获任意异常
            check(f"D {label} 不抛异常", False, f"{type(ex).__name__}: {ex}")
            continue
        check(f"D {label} 不抛异常", True)
        all_offsets = [v for r in table for v in (r[4], r[5])]
        check(f"D {label} 无负偏移", all(v >= 0 for v in all_offsets),
              f"min={min(all_offsets) if all_offsets else '-'} rows={len(table)}")
        if data:
            check(f"D {label} 偏移不超过帧尾", max(all_offsets, default=0) <= len(data) - 1,
                  f"max={max(all_offsets, default=0)} len-1={len(data) - 1}")

    # 校准：合法帧在降级测试区间外仍正常（避免只测坏路径）
    check("D 合法帧仍为 13 行基线", len(GUI.parse_to_table(LEGAL)) == 13,
          str(len(GUI.parse_to_table(LEGAL))))


# ═══════════════════════════════════════════════════════════════
# E 单一来源守卫（防复制体回潮）
# ═══════════════════════════════════════════════════════════════

def test_single_source_guard():
    print("\n[5] E 单一来源守卫：645 转表只剩 protocol_registry 一份")

    web_src = (ROOT / "reflex_web" / "reflex_web" / "reflex_web.py").read_text(
        encoding="utf-8")
    all_proto_src = (ROOT / "test" / "test_web_all_protocols.py").read_text(
        encoding="utf-8")
    reg_src = (ROOT / "protocol_registry.py").read_text(encoding="utf-8")

    # 复制体的两个特征：①「声明长度」赋值语句（行首锚定，不误伤注释/文档/守卫串）
    #                      ② 转表独有的 fields 访问
    copy_stmt = re.compile(r"^\s*total_len\s*=\s*10\s*\+\s*data_len\s*\+\s*2\s*$", re.M)
    copy_fields = 'dlt645_result.get("fields", [])'

    check("E reflex_web 无「声明长度」偏移公式复制体", not copy_stmt.search(web_src))
    check("E reflex_web 无转表字段循环复制体", copy_fields not in web_src)
    check("E reflex_web 调用同一实现 DLT645GuiParser",
          "from protocol_registry import DLT645GuiParser" in web_src
          and "DLT645GuiParser(parser).parse_to_table(frame_bytes)" in web_src)

    check("E 测试侧无转表复制体（test_web_all_protocols 已改 import 产品实现）",
          not copy_stmt.search(all_proto_src) and copy_fields not in all_proto_src)

    check("E protocol_registry 已用实际帧长（frame_len/cs_pos/end_pos）",
          "frame_len = len(data)" in reg_src
          and "cs_pos = max(0, frame_len - 2)" in reg_src
          and "end_pos = max(0, frame_len - 1)" in reg_src)
    check("E protocol_registry 已不再有声明长度赋值语句", not copy_stmt.search(reg_src))

    # 全仓（根目录 / test / reflex_web）不得再出现转表复制体
    hits = []
    targets = (
        list(ROOT.glob("*.py"))
        + list((ROOT / "test").glob("*.py"))
        + list((ROOT / "reflex_web" / "reflex_web").glob("*.py"))
    )
    for path in targets:
        if path.name == Path(__file__).name:
            continue  # 本文件以字面量形式持守卫特征，跳过自身
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if copy_stmt.search(src) or copy_fields in src:
            hits.append(path.name)
    check("E 全仓无残留 645 转表复制体", not hits, str(hits))


def main():
    print("=" * 74)
    print("协议6 645 转表字节偏移矩阵（R2.2：声明长度不符时用实际帧长）")
    print("=" * 74)
    test_legal_frame_unchanged()
    test_declared_shorter_offsets()
    test_declared_longer_offsets()
    test_degrade_no_negative_offsets()
    test_single_source_guard()
    print()
    print("=" * 74)
    if FAILURES:
        print(f"✗ 失败 {len(FAILURES)} 项 / 通过 {PASS} 项")
        for name in FAILURES:
            print(f"   - {name}")
    else:
        print(f"✓ 全部通过：{PASS} 项")
    print("=" * 74)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
