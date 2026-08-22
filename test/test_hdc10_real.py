# -*- coding: utf-8 -*-
"""HDC 1.0 真实报文回归测试 (来自 TMI模式遍历测试 日志)

数据源: 国网新一代协议/HDC-国网双模协议/TMI模式遍历测试_频段1__All.log
覆盖: 各 MSDU类型/MMTYPE/长度档 的 PB 帧, 验证解析无异常且关键字段稳定。
"""

import _path_setup  # noqa: E402

import pickle
import os
import sys

from hdc10_parser import HDC10Parser

PICKLE = os.path.join(os.path.dirname(__file__), "hdc10_real_frames.pkl")


def load_frames():
    with open(PICKLE, "rb") as f:
        return pickle.load(f)


def test_real_frames_no_exception():
    """全部真实帧解析不抛异常"""
    p = HDC10Parser()
    frames = load_frames()
    assert len(frames) >= 50, f"样本数: {len(frames)}"
    for fi, fbytes, key in frames:
        rows = p._parse_pb_only(fbytes, 1)
        assert isinstance(rows, list)


def test_real_frames_stable_fields():
    """含 MME 头的帧应解出 MMTYPE=0x0008(发现列表)等已知类型"""
    p = HDC10Parser()
    frames = load_frames()
    found_types = set()
    for fi, fbytes, key in frames:
        rows = p._parse_pb_only(fbytes, 1)
        for r in rows:
            if r[0].strip() == "消息类型(MMTYPE)":
                found_types.add(r[2])
    # 样本中至少应覆盖 发现列表(0x0000/0x0008)/关联确认(0x0001)/过零NTB(0x000B)
    for expect in ("0x0008", "0x000B", "0x0001"):
        assert expect in found_types, f"缺少 MMTYPE {expect}, 实际: {sorted(found_types)}"


def test_discover_list_real():
    """真实发现列表帧(表95): 固定头字段完整, 空位图帧不产生明细行(正常)"""
    p = HDC10Parser()
    frames = load_frames()
    fields_ok = 0
    for fi, fbytes, key in frames:
        if key[1] != "0x0008":
            continue
        rows = p._parse_pb_only(fbytes, 1)
        names = [r[0].strip() for r in rows]
        required = ("TEI", "代理TEI", "MAC地址", "CCO MAC地址", "站点总数",
                    "位图大小", "上行路由条目总数")
        if all(any(n.endswith(req) or n == req for n in names) for req in required):
            fields_ok += 1
    assert fields_ok >= 1, f"字段完整的发现列表帧: {fields_ok}"


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL {t.__name__}: {e}")
        except Exception as e:
            print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(tests)} 通过")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
