# -*- coding: utf-8 -*-
"""协议9（南网新一代载波 / 通感一体）2.0 测试扩展 ID=0x0009「报文聚合传输测试模式」 - 测试

需求来源：《宽带双模通信模块（通感一体物联版）相关测试命令定义_260922》文档 1.4.9
    | 域 | 字节号 | 比特位 | 域大小(比特) | 含义 |
    | 报文聚合数目 | 3 | 0-7 | 8 | 要求聚合发送的MAC帧个数 |

覆盖四条链路的一致性：
  1. 映射表与组帧模式清单（0x0009 必须同时进解析表与组帧模式表）；
  2. 解析 golden（0x00 / 0x01 / 0x05 / 0xFF 边界 + 数据域缺失容错 + 未登记扩展ID 护栏）；
  3. 组帧逐字节 + 取值越界报错；
  4. 组帧 → 解析 闭环、应用层帧 → 仿照回填 闭环、批量摘要片段。

字节口径（与既有扩展 0x0005~0x0008 同约定）：ext_data[x] = 文档字节 x+3
  ⇒ 报文聚合数目 = 扩展数据第 0 字节（整字节，无位域）。

运行：python test/test_csg_test_ext_0009.py
"""

import _path_setup  # noqa: E402,F401

import sys  # noqa: E402

try:  # 控制台为 GBK 时打印 ❌/✓ 会抛 UnicodeEncodeError（同 test_plc_rf.py 的处置）
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001 - 老环境无 reconfigure 时忽略
    pass

import csg_frame_reverse as rev  # noqa: E402
import csg_new_gen_frame_gen as fg  # noqa: E402
from batch_core import extract_test_mode_content  # noqa: E402
from csg_new_gen_cmd_payloads import _TEST_EXT_ID_MAP  # noqa: E402
from csg_new_gen_frame_gen import FrameBuildError  # noqa: E402
from csg_new_gen_parser import CSGNewGenParser  # noqa: E402

EXT_ID = 0x0009
EXT_NAME = "报文聚合传输测试模式"

_FAILURES = []
_CHECKS = []


def check(name, condition, detail=""):
    _CHECKS.append(name)
    if not condition:
        _FAILURES.append(f"{name} —— {detail}")


def field_of(table, label):
    """取解析表某字段的「解析值」列（无该行返回 None）。"""
    for row in table:
        if row[0] == label:
            return row[2]
    return None


def raw_of(table, label):
    for row in table:
        if row[0] == label:
            return row[1]
    return None


def desc_of(table, label):
    for row in table:
        if row[0] == label:
            return row[3]
    return ""


def row_of(table, label):
    for row in table:
        if row[0] == label:
            return row
    return None


def _app_frame(ctrl, sdu, sid=0xF0):
    """构造应用层帧：端口 + 标识 + 保留 + 控制域 + 业务标识 + 版本 + 序号 + 帧长 + SDU。"""
    return (
        bytes([0x11, 0x01, 0x01, 0x00])
        + ctrl.to_bytes(2, "little")
        + bytes([sid, 0x01])
        + (0).to_bytes(2, "little")
        + len(sdu).to_bytes(2, "little")
        + sdu
    )


def _parse_app(sdu, level="app"):
    return CSGNewGenParser().parse_to_table(_app_frame(0x4002, sdu), parse_level=level)


def _sdu(ext_id, ext_data, *, neg_version=1, file_len=None):
    """手工拼 2.0 测试 BDU：测试ID(1) 保留(1) 数据区长度(2,LE) 协商版本号(1) 文件长度(1) 扩展ID(2,LE) 扩展数据。"""
    if file_len is None:
        file_len = len(ext_data)
    data = (
        bytes([neg_version, file_len])
        + int(ext_id).to_bytes(2, "little")
        + bytes(ext_data)
    )
    return bytes([0x04, 0x00]) + len(data).to_bytes(2, "little") + data


# ----------------------------------------------------------------------
# 1. 映射表与组帧模式清单
# ----------------------------------------------------------------------
def test_maps_and_mode_list():
    check("解析侧 _TEST_EXT_ID_MAP 登记 0x0009",
          _TEST_EXT_ID_MAP.get(EXT_ID) == EXT_NAME, str(_TEST_EXT_ID_MAP.get(EXT_ID)))
    check("组帧侧 TEST_EXT_ID_MAP 与解析侧同值",
          fg.TEST_EXT_ID_MAP.get(EXT_ID) == _TEST_EXT_ID_MAP.get(EXT_ID) == EXT_NAME,
          str(fg.TEST_EXT_ID_MAP.get(EXT_ID)))

    modes = fg.test_modes()
    keys = [m.key for m in modes]
    check("模式 key 唯一", len(keys) == len(set(keys)),
          str([k for k in keys if keys.count(k) > 1]))
    check("模式总数 = 25（原 24 + 本次新增 1）", len(modes) == 25, str(len(modes)))

    agg = fg.mode_by_key("ext_agg")
    check("模式清单含 ext_agg", agg is not None)
    if agg is not None:
        check("ext_agg 分组/名称/测试ID/扩展ID 正确",
              agg.group == "B 2.0测试扩展" and agg.name == EXT_NAME
              and agg.test_id == 0x04 and agg.ext_id == EXT_ID,
              f"{agg.group}/{agg.name}/{agg.test_id:#x}/{agg.ext_id}")
        check("ext_agg 唯一参数 = agg_count（默认 1）",
              [f.name for f in agg.fields] == ["agg_count"]
              and agg.fields[0].default == 1,
              str([(f.name, f.default) for f in agg.fields]))


# ----------------------------------------------------------------------
# 2. 解析 golden + 容错 + 护栏
# ----------------------------------------------------------------------
def test_parse_golden():
    for count in (0x00, 0x01, 0x05, 0xFF):
        table = _parse_app(_sdu(EXT_ID, [count], file_len=1))
        check(f"解析：扩展ID 说明 = {EXT_NAME}（数据 0x{count:02X}）",
              desc_of(table, "扩展ID") == EXT_NAME, desc_of(table, "扩展ID"))
        check(f"解析：扩展ID 原始值 = 09 00（数据 0x{count:02X}）",
              raw_of(table, "扩展ID") == "09 00", raw_of(table, "扩展ID"))
        check(f"解析：测试ID 行 = 2.0测试（数据 0x{count:02X}）",
              field_of(table, "测试ID") == "4" and desc_of(table, "测试ID") == "2.0测试",
              f"{field_of(table, '测试ID')}/{desc_of(table, '测试ID')}")
        check(f"解析：报文聚合数目 解析值 = {count}（数据 0x{count:02X}）",
              field_of(table, "报文聚合数目") == str(count),
              str(field_of(table, "报文聚合数目")))
        check(f"解析：报文聚合数目 原始值 = 0x{count:02X}（数据 0x{count:02X}）",
              raw_of(table, "报文聚合数目") == f"0x{count:02X}",
              str(raw_of(table, "报文聚合数目")))
        check(f"解析：报文聚合数目 说明含「聚合发送的MAC帧个数」（数据 0x{count:02X}）",
              "聚合发送的MAC帧个数" in desc_of(table, "报文聚合数目"),
              desc_of(table, "报文聚合数目"))

    # 偏移：应用层帧 = 端口(1)+标识(2)+保留(1)+业务头(8) + BDU
    #   BDU: 测试ID@12 保留@13 数据区长度@14-15 协商版本号@16 文件长度@17 扩展ID@18-19 数据域@20
    table = _parse_app(_sdu(EXT_ID, [0x07], file_len=1))
    check("解析：报文聚合数目 行偏移 = 20（闭区间单字节）",
          row_of(table, "报文聚合数目")[4:6] == (20, 20),
          str(row_of(table, "报文聚合数目")[4:6]))
    check("解析：扩展ID 行偏移 = 18~19",
          row_of(table, "扩展ID")[4:6] == (18, 19),
          str(row_of(table, "扩展ID")[4:6]))


def test_parse_tolerance():
    # 数据区只有 4 字节（协商版本号+文件长度+扩展ID，扩展数据为空）→ 必须给 ❌ 行而不是空白/异常
    table = _parse_app(_sdu(EXT_ID, [], file_len=0))
    check("容错：扩展数据为空 → 出现 ❌ 解析失败 行",
          any("解析失败" in str(r[0]) for r in table), str([r[0] for r in table][-3:]))
    check("容错：扩展数据为空 → 不产生 报文聚合数目 行",
          field_of(table, "报文聚合数目") is None)
    check("容错：扩展数据为空 → 扩展ID 名称仍可读",
          desc_of(table, "扩展ID") == EXT_NAME, desc_of(table, "扩展ID"))

    # 未登记扩展 ID（0x000A）behavior 不变：保留 + 未识别数据行
    table = _parse_app(_sdu(0x000A, [0x55]))
    check("护栏：未登记扩展ID 仍为 保留扩展ID(0x000A)",
          desc_of(table, "扩展ID") == "保留扩展ID(0x000A)", desc_of(table, "扩展ID"))
    check("护栏：未登记扩展ID 输出未识别数据行",
          any("未识别扩展ID 0x000A" in str(r[3]) for r in table),
          str([r[3] for r in table][-2:]))
    check("护栏：未登记扩展ID 不产生 报文聚合数目 行",
          field_of(table, "报文聚合数目") is None)


# ----------------------------------------------------------------------
# 3. 组帧逐字节 + 越界
# ----------------------------------------------------------------------
def test_build_bytes():
    bdu = fg.build_test_pdu(0x04, ext_id=EXT_ID, agg_count=5)
    check("组帧：BDU 逐字节 = 04 00 05 00 00 01 09 00 05",
          bdu == bytes([0x04, 0x00, 0x05, 0x00, 0x00, 0x01, 0x09, 0x00, 0x05]),
          bdu.hex(" ").upper())
    check("组帧：数据区长度 LE = 5（协商版本号+文件长度+扩展ID 2B+数据 1B）",
          int.from_bytes(bdu[2:4], "little") == 5, bdu[2:4].hex(" ").upper())
    check("组帧：协商版本号默认 0、文件长度 = 扩展数据长度 1",
          bdu[4] == 0x00 and bdu[5] == 0x01, bdu[4:6].hex(" ").upper())
    check("组帧：扩展ID 小端 = 09 00", bdu[6:8] == b"\x09\x00", bdu[6:8].hex(" ").upper())
    check("组帧：build_ext_pdu 便捷入口 = 测试数据区（协商版本号+文件长度+扩展ID+数据）",
          fg.build_ext_pdu(EXT_ID, agg_count=0xFF) == bytes([0x00, 0x01, 0x09, 0x00, 0xFF]),
          fg.build_ext_pdu(EXT_ID, agg_count=0xFF).hex(" ").upper())
    check("组帧：agg_count 默认 = 1",
          fg.build_test_pdu(0x04, ext_id=EXT_ID)[8:] == b"\x01")

    for bad in (0x100, -1, "x", None):
        try:
            fg.build_ext_pdu(EXT_ID, agg_count=bad)
        except FrameBuildError:
            ok = True
        except Exception as exc:  # noqa: BLE001
            ok = False
            check(f"组帧：agg_count={bad!r} 抛 FrameBuildError（实际 {type(exc).__name__}）", False)
            continue
        else:
            ok = False
        check(f"组帧：agg_count={bad!r} 抛 FrameBuildError", ok)


# ----------------------------------------------------------------------
# 4. 闭环：组帧 → 解析
# ----------------------------------------------------------------------
def test_build_parse_loop():
    for level in ("app", "auto"):
        app = fg.build_frame_from_mode("ext_agg", {"agg_count": 9}).app_frame
        table = CSGNewGenParser().parse_to_table(app, parse_level=level)
        check(f"闭环({level})：扩展ID = {EXT_NAME}",
              desc_of(table, "扩展ID") == EXT_NAME, desc_of(table, "扩展ID"))
        check(f"闭环({level})：报文聚合数目 = 9",
              field_of(table, "报文聚合数目") == "9",
              str(field_of(table, "报文聚合数目")))
    # 四组取值全量对拍
    bad = []
    for count in (0x00, 0x01, 0x7F, 0xFF):
        app = fg.build_frame_from_mode("ext_agg", {"agg_count": count}).app_frame
        table = CSGNewGenParser().parse_to_table(app, parse_level="app")
        if field_of(table, "报文聚合数目") != str(count):
            bad.append(f"{count}: {field_of(table, '报文聚合数目')}")
    check("闭环：0x00/0x01/0x7F/0xFF 四组取值回读一致", not bad, "; ".join(bad))


# ----------------------------------------------------------------------
# 5. 闭环：应用层帧 → 仿照报文回填
# ----------------------------------------------------------------------
def test_reverse_loop():
    for count in (0x01, 0x2A, 0xFF):
        app = fg.build_frame_from_mode("ext_agg", {"agg_count": count}).app_frame
        result = rev.reverse_frame(app)
        check(f"反解：ok=True（agg_count={count}）", result.ok, result.error)
        check(f"反解：layer=app（agg_count={count}）", result.layer == "app", result.layer)
        mode = (result.state.get("mode") or {})
        check(f"反解：key=ext_agg（agg_count={count}）", mode.get("key") == "ext_agg", str(mode.get("key")))
        check(f"反解：agg_count={count}",
              (mode.get("params") or {}).get("agg_count") == count,
              str(mode.get("params")))
        check(f"反解：unmapped 为空（agg_count={count}）", result.unmapped == [], str(result.unmapped))
        rebuilt = fg.build_frame_from_mode("ext_agg", dict(mode.get("params") or {})).app_frame
        check(f"反解：回填参数重建与原帧逐字节一致（agg_count={count}）",
              rebuilt == app, rebuilt.hex(" ").upper()[:40])

    # 未知扩展 ID 仍走「无对应模式」兜底（不回归；扩展ID 在提示里按十进制显示）
    unknown = rev.reverse_frame(_app_frame(0x4002, _sdu(0x000A, [0x55], neg_version=0)))
    check("反解：未登记扩展ID 记入 unmapped（不静默）",
          unknown.unmapped == ["扩展ID=10 无对应模式"], str(unknown.unmapped))


# ----------------------------------------------------------------------
# 6. 批量摘要片段
# ----------------------------------------------------------------------
def test_summary_segment():
    table = _parse_app(_sdu(EXT_ID, [0x0A], file_len=1))
    text = extract_test_mode_content(table)
    check("摘要：含 测试ID:2.0测试", "测试ID:2.0测试" in text, text)
    check(f"摘要：含 扩展ID:{EXT_NAME}", f"扩展ID:{EXT_NAME}" in text, text)

    # 非测试帧不得被污染（helper 无痕迹返回空串）
    plain = CSGNewGenParser().parse_to_table(
        _app_frame(0x0000, b"", sid=0x00), parse_level="app")
    plain_text = extract_test_mode_content(plain)
    check("摘要：非测试帧不产生测试片段",
          "测试ID" not in plain_text and "扩展ID" not in plain_text and "测试模式" not in plain_text,
          plain_text)


def main():
    test_maps_and_mode_list()
    test_parse_golden()
    test_parse_tolerance()
    test_build_bytes()
    test_build_parse_loop()
    test_reverse_loop()
    test_summary_segment()

    print(f"共 {len(_CHECKS)} 项断言，失败 {len(_FAILURES)} 项")
    for item in _FAILURES:
        print("  ✗ " + item)
    if _FAILURES:
        print("[FAIL] 协议9 2.0 测试扩展 0x0009")
        sys.stdout.flush()
        return 1
    print("[OK] 协议9 2.0 测试扩展 0x0009（报文聚合传输测试模式）")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
