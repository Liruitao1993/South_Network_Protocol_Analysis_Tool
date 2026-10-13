# -*- coding: utf-8 -*-
"""串口工具「批量替换通信地址」纯逻辑回归测试（任务 10-14-serial-batch-addr）。

覆盖：
  [1] 常量与三态（HEX_MATCH_TYPES / FE_WAKEUP_PROTOCOLS / ADDR_BATCH_LOG_LIMIT / AddrBatchItem 默认值）
  [2] fix_frame_text：六协议**真帧** oracle（地址已变 + 该协议校验器 0 fail + 非地址/校验字节不变）
      + 前导 FE 门控（只对 6/8 剥离并恢复）+ 错误矩阵
  [3] batch_fix_commands：三态 / 作用范围 / 协议列开关 / 预期响应四类 / 混合协议 / **不修改入参**
  [4] addr_batch_summary：计数与明细上限
  [5] 反例自检：改了地址但不重算校验 → 校验器必红（证明 oracle 有效）

帧夹具与 `test/test_bluetooth_addr_fix.py` 同源（六协议真帧；国网用仓库自身组帧器造，
组帧器即布局权威）—— 这里只关心「串口命令表这层编排」，地址/校验算法本身由 `frame_addr_fix` 负责。

运行: python test/test_serial_addr_fix.py
"""

import _path_setup  # noqa: E402,F401

import copy  # noqa: E402
import sys  # noqa: E402

import protocol_registry  # noqa: E402
import serial_tool_widget as stw  # noqa: E402

PASS = 0
FAIL = 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [NG] {name}" + (f"  -> {detail}" if detail else ""))


def section(title):
    print()
    print(f"-- {title} " + "-" * max(0, 56 - len(title)))


def hx(text):
    return bytes.fromhex(text.replace(" ", ""))


def unhex(text):
    return bytes.fromhex(str(text).replace(" ", ""))


def validator_for(index):
    return protocol_registry.make_validator(index)


def v_fail(index, frame):
    """校验器的失败项数量（0 = 通过）。"""
    result = validator_for(index).verify(frame)
    return result.fail_count, result


# ── 真帧夹具（南网/645/698/依瓦/南网上行取自 test_bluetooth_addr_fix.py 的 oracle 帧）──

#: 南网（协议0）带地址域（控制域 D5=1）：源 00×6，目的 22 00 00 00 00 00
SOUTH_ADDR = hx("68 28 00 20 00 00 00 00 00 00 22 00 00 00 00 00 02 00 01 02 02 "
                "E8 00 00 00 1E 00 09 00 01 02 03 04 05 06 07 08 09 85 16")
#: 南网（协议0）无地址域（控制域 D5=0）
SOUTH_NOADDR = hx("68 0C 00 00 02 00 03 02 00 E8 EF 16")
#: 645（协议6）读正向有功总电能（表地址 00×6）
DLT645 = hx("68 00 00 00 00 00 00 68 11 04 33 33 34 33 B2 16")
#: 698.45（协议8）柔控命令（地址特征 0x04 + SA=33 00 00 00 00 + CA=00）
T698 = hx("68 1F 00 43 04 33 00 00 00 00 00 0C 57 06 01 01 80 02 02 00 02 02 05 "
          "D0 07 00 00 11 05 00 32 4D 16")
#: 依瓦645（协议13）透传模式请求（表号 045000000013）
YW645 = hx("68 04 50 00 00 00 13 68 30 02 37 14 B4 16")
#: 南网上行（协议14）读当前数据·正向有功总电能（A1=00 00 00，A2=1，A3=0）
CSG_UPLINK = hx("68 10 00 10 00 68 4B 00 00 00 01 00 00 00 0C 60 01 01 00 00 01 00 BB 16")

FE4 = b"\xfe\xfe\xfe\xfe"


def gdw_frame():
    """国网（协议7）带地址域的帧：用仓库自身组帧器造（组帧器即布局权威）。"""
    from gdw_send_frame_lib import GDWFrameGenerator

    gen = GDWFrameGenerator()
    return gen.generate_frame(
        afn=1, fn=1, field_values={},
        info_config={"通信模块标识": 1, "中继级别": 0},
        src_addr="000000000001", dst_addr="000000000002",
    )


def cmd(data, **kw):
    """一条命令记录（与 `normalize_command` 的键一致）。"""
    base = {
        "name": kw.pop("name", "命令"),
        "data_hex": stw.bytes_to_hex(data) if isinstance(data, (bytes, bytearray)) else str(data),
        "match_type": "none",
        "match_hex": "",
        "protocol": None,
        "enabled": True,
        "send_count": 1,
    }
    base.update(kw)
    return base


# ── [1] 常量与三态 ──────────────────────────────────────────────────────────

def test_constants():
    section("[1] 常量与三态")
    check("HEX_MATCH_TYPES = 四种纯 HEX 匹配方式",
          tuple(stw.HEX_MATCH_TYPES) == ("contains", "equals", "starts_with", "ends_with"),
          stw.HEX_MATCH_TYPES)
    check("前导 FE 只对 6/8（规范依据：645 §5.3.1 / 698.45 §6.3.1 b）",
          tuple(stw.FE_WAKEUP_PROTOCOLS) == (6, 8), stw.FE_WAKEUP_PROTOCOLS)
    check("三种状态常量互不相同",
          len({stw.ADDR_STATUS_OK, stw.ADDR_STATUS_KEPT, stw.ADDR_STATUS_SKIPPED}) == 3)
    item = stw.AddrBatchItem(index=0, name="n", status=stw.ADDR_STATUS_SKIPPED,
                             data_hex="", protocol=None, match_hex="", match_changed=False)
    check("AddrBatchItem：notes/error 有默认值（构造不必传）",
          item.notes == [] and item.error == "" and item.match_changed is False)
    check("备注：日志明细上限是正数", stw.ADDR_BATCH_LOG_LIMIT > 0, stw.ADDR_BATCH_LOG_LIMIT)


# ── [2] fix_frame_text：六协议 oracle ───────────────────────────────────────

def oracle(title, frame, index, values, span, expect_addr, extra_changed=frozenset()):
    """替换后：① 帧长不变 ② 地址 span == 期望 ③ 校验器 0 fail ④ 只有地址/校验字节变。"""
    new_hex, notes, error = stw.fix_frame_text(stw.bytes_to_hex(frame), index, values)
    if error:
        check(f"{title}：替换成功", False, error)
        return
    new = unhex(new_hex)
    check(f"{title}：替换成功且帧长不变", len(new) == len(frame),
          f"{len(frame)} → {len(new)}")
    check(f"{title}：地址域写入期望字节", new[span[0]:span[1]] == expect_addr,
          new[span[0]:span[1]].hex(" "))
    changed = {i for i in range(len(frame)) if frame[i] != new[i]}
    allowed = set(range(*span)) | set(extra_changed)
    check(f"{title}：只有地址域/校验字节变化", changed <= allowed,
          f"changed={sorted(changed)} allowed={sorted(allowed)}")
    fails, _res = v_fail(index, new)
    check(f"{title}：**该协议校验器 0 fail**", fails == 0, f"fail={fails}")
    check(f"{title}：notes 非空（地址/校验旧→新）", bool(notes), notes)


def test_oracle_frames():
    section("[2] fix_frame_text 六协议真帧 oracle")

    oracle("南网(0)", SOUTH_ADDR, 0, {"dst": "000000000010"}, (10, 16),
           bytes.fromhex("100000000000"), {len(SOUTH_ADDR) - 2})
    oracle("645(6)", DLT645, 6, {"addr": "000000000033"}, (1, 7),
           bytes.fromhex("330000000000"), {len(DLT645) - 2})
    oracle("698.45(8)", T698, 8, {"sa": "0000000099", "ca": "7"}, (5, 11),
           bytes.fromhex("9900000000") + b"\x07",
           set(range(4, 5)) | {11, 12, len(T698) - 3, len(T698) - 2})
    oracle("依瓦645(13)", YW645, 13, {"addr": "450000000099"}, (1, 7),
           bytes.fromhex("450000000099"), {len(YW645) - 2})
    oracle("南网上行(14)", CSG_UPLINK, 14, {"a2": "1234567"}, (7, 14),
           bytes.fromhex("000000") + (1234567).to_bytes(3, "little") + b"\x00",
           {len(CSG_UPLINK) - 2})

    frame = gdw_frame()
    alen = 12 + 6 * ((frame[4] >> 4) & 0x0F)
    oracle("国网(7)", frame, 7, {"dst": "000000000010"}, (10, 10 + alen),
           bytes.fromhex("010000000000") + bytes.fromhex("100000000000"),
           {len(frame) - 2})

    # 南网无地址域：明确报错，不得静默返回原帧
    _new, _notes, error = stw.fix_frame_text(stw.bytes_to_hex(SOUTH_NOADDR), 0,
                                             {"src": "000000000009"})
    check("南网 D5=0：报「不含地址域」", "不含地址域" in error, error)


def test_fe_prefix():
    section("[2b] 前导 FEH（只对协议 6/8 剥离并原样恢复）")

    for index, frame, values, label in (
        (8, T698, {"sa": "0000000099"}, "698.45"),
        (6, DLT645, {"addr": "000000000033"}, "645"),
    ):
        raw = FE4 + frame
        new_hex, notes, error = stw.fix_frame_text(stw.bytes_to_hex(raw), index, values)
        check(f"{label}：带前导 FE 也能替换", not error, error)
        if error:
            continue
        new = unhex(new_hex)
        check(f"{label}：前导 FE 原样保留", new[:4] == FE4, new[:4].hex(" "))
        check(f"{label}：前导之后就是 68H", new[4:5] == b"\x68", new[4:5].hex(" "))
        fails, _res = v_fail(index, new)
        check(f"{label}：带前导的新帧校验器 0 fail", fails == 0, f"fail={fails}")
        check(f"{label}：notes 非空", bool(notes), notes)

    # 其余协议规范里没有前导码 ⇒ 带 FE 就报错（不得被「救活」）
    for index, frame, values, label in (
        (0, SOUTH_ADDR, {"dst": "000000000010"}, "南网(0)"),
        (7, gdw_frame(), {"dst": "000000000010"}, "国网(7)"),
    ):
        new_hex, _notes, error = stw.fix_frame_text(stw.bytes_to_hex(FE4 + frame), index, values)
        check(f"{index} {label}：带前导 FE 拒绝替换（规范无前导码）", bool(error), error)
        check(f"{index} {label}：拒绝时原样返回", new_hex == stw.bytes_to_hex(FE4 + frame))


def test_frame_text_errors():
    section("[2c] fix_frame_text 错误矩阵")

    _new, _notes, error = stw.fix_frame_text("68 12 0G", 6, {"addr": "000000000033"})
    check("非法 HEX：报具体字符", "非 HEX" in error, error)

    _new, _notes, error = stw.fix_frame_text("", 6, {"addr": "000000000033"})
    check("空数据：报空", bool(error), error)

    _new, _notes, error = stw.fix_frame_text(stw.bytes_to_hex(DLT645), None, {"addr": "x"})
    check("未选协议：报「未选择协议」", "未选择协议" in error, error)

    _new, _notes, error = stw.fix_frame_text(stw.bytes_to_hex(DLT645), 9, {"addr": "x"})
    check("协议9 不支持：给可读原因（不静默）", "暂不支持" in error, error)

    _new, _notes, error = stw.fix_frame_text(stw.bytes_to_hex(DLT645), 6, {"addr": "00 00"})
    check("645 地址长度不符：报错", "6 字节" in error, error)

    _new, _notes, error = stw.fix_frame_text(stw.bytes_to_hex(DLT645), 6, {})
    check("645 未填地址：报错", bool(error), error)


# ── [3] batch_fix_commands ─────────────────────────────────────────────────

def test_batch_basic():
    section("[3] batch_fix_commands 基本行为")
    commands = [
        cmd(DLT645, name="读电能"),
        cmd(SOUTH_ADDR, name="南网帧"),
        cmd("68 12 0G", name="坏 HEX"),
    ]
    snapshot = copy.deepcopy(commands)
    items = stw.batch_fix_commands(commands, [0, 1, 2], 6, {"addr": "000000000033"},
                                   write_protocol=True, fix_match=True)

    check("作用范围顺序与 indices 一致", [it.index for it in items] == [0, 1, 2],
          [it.index for it in items])
    check("**不修改入参**", commands == snapshot,
          [c.get("data_hex") for c in commands[:1]])
    check("第 1 条（645 帧）→ ok", items[0].status == stw.ADDR_STATUS_OK, items[0].error)
    check("第 2 条（南网帧按 645 替换）→ kept（结构自证失败）",
          items[1].status == stw.ADDR_STATUS_KEPT, items[1].status)
    check("第 2 条原因可读（结构/校验自证失败）",
          any(k in items[1].error for k in ("结构", "校验", "起始")), items[1].error)
    check("第 3 条（坏 HEX）→ skipped", items[2].status == stw.ADDR_STATUS_SKIPPED,
          items[2].status)
    check("kept 条目的 data_hex 仍是原值",
          items[1].data_hex == stw.bytes_to_hex(SOUTH_ADDR), items[1].data_hex[:20])
    check("skipped 条目的 data_hex 仍是原值", items[2].data_hex == "68 12 0G",
          items[2].data_hex)
    check("ok 条目 data_hex 已替换（地址 33）",
          unhex(items[0].data_hex)[1:7] == bytes.fromhex("330000000000"),
          unhex(items[0].data_hex)[:8].hex(" "))
    check("ok 条目 notes 非空", bool(items[0].notes), items[0].notes)
    check("协议列写入所有条目（含未替换的）",
          [it.protocol for it in items] == [6, 6, 6], [it.protocol for it in items])


def test_batch_scope_and_protocol_switch():
    section("[3b] 作用范围 / 协议列开关 / 无效下标")

    commands = [cmd(DLT645, name="a"), cmd(DLT645, name="b"), cmd(DLT645, name="c")]
    items = stw.batch_fix_commands(commands, [1], 6, {"addr": "000000000033"})
    check("只处理 indices 给的下标", [it.index for it in items] == [1], [it.index for it in items])

    items = stw.batch_fix_commands(commands, [0, 99, -1, "x", True, None], 6,
                                   {"addr": "000000000033"})
    check("越界 / 非 int / bool 下标被忽略",
          [it.index for it in items] == [0], [it.index for it in items])

    items = stw.batch_fix_commands(commands, [], 6, {"addr": "000000000033"})
    check("空作用范围 → 空结果", items == [], items)

    items = stw.batch_fix_commands(commands, [0], 6, {"addr": "000000000033"},
                                   write_protocol=False)
    check("write_protocol=False → 不动协议列", items[0].protocol is None, items[0].protocol)

    items = stw.batch_fix_commands(commands, [0], None, {"addr": "000000000033"},
                                   write_protocol=True)
    check("协议非法(None) → 不写协议列", items[0].protocol is None, items[0].protocol)
    check("协议非法(None) → 替换失败但原因可读",
          items[0].status == stw.ADDR_STATUS_KEPT and "未选择协议" in items[0].error,
          items[0].error)


def test_batch_expected_response():
    section("[3c] 预期响应（只在发送数据替换成功时、且只动纯 HEX 写法）")

    # equals + 可自证整帧 → 同步替换
    frame = DLT645
    commands = [cmd(DLT645, name="可自证", match_type="equals",
                    match_hex=stw.bytes_to_hex(frame))]
    items = stw.batch_fix_commands(commands, [0], 6, {"addr": "000000000033"})
    check("可自证整帧：预期响应被同步替换",
          items[0].match_changed and unhex(items[0].match_hex)[1:7] == bytes.fromhex("330000000000"),
          items[0].match_hex[:24])
    check("notes 说明预期响应已同步替换",
          any("预期响应已同步替换" in n for n in items[0].notes), items[0].notes)
    fails, _res = v_fail(6, unhex(items[0].match_hex))
    check("同步替换后的预期响应该校验器 0 fail", fails == 0, f"fail={fails}")

    # contains + 片段（自证失败）→ 保持原样 + 说明
    commands = [cmd(DLT645, name="片段", match_type="contains", match_hex="68 D0")]
    items = stw.batch_fix_commands(commands, [0], 6, {"addr": "000000000033"})
    check("片段式预期响应保持原样",
          items[0].match_hex == "68 D0" and not items[0].match_changed, items[0].match_hex)
    check("片段式预期响应记入 notes（未替换原因）",
          any("预期响应未替换" in n for n in items[0].notes), items[0].notes)

    # hex_wildcard / regex / none → 一律不动 + 说明
    for match_type, match_hex in (("hex_wildcard", "68 D0 XX 16"),
                                  ("regex", "\\x68\\xD0"),
                                  ("none", "68 D0")):
        commands = [cmd(DLT645, name=match_type, match_type=match_type, match_hex=match_hex)]
        items = stw.batch_fix_commands(commands, [0], 6, {"addr": "000000000033"})
        check(f"{match_type}：预期响应原样保留",
              items[0].match_hex == match_hex and not items[0].match_changed,
              items[0].match_hex)
        check(f"{match_type}：记入 notes",
              any("预期响应未替换" in n for n in items[0].notes), items[0].notes)

    # fix_match=False → 完全不碰预期响应
    commands = [cmd(DLT645, name="关掉", match_type="equals",
                    match_hex=stw.bytes_to_hex(DLT645))]
    items = stw.batch_fix_commands(commands, [0], 6, {"addr": "000000000033"},
                                   fix_match=False)
    check("fix_match=False：预期响应原样保留",
          items[0].match_hex == stw.bytes_to_hex(DLT645) and not items[0].match_changed)
    check("fix_match=False：不产生预期响应相关 notes",
          not any("预期响应" in n for n in items[0].notes), items[0].notes)

    # 发送数据替换失败 → 预期响应不得被动
    commands = [cmd(SOUTH_ADDR, name="南网帧", match_type="equals",
                    match_hex=stw.bytes_to_hex(DLT645))]
    items = stw.batch_fix_commands(commands, [0], 6, {"addr": "000000000033"})
    check("发送数据未替换成功时不动预期响应",
          items[0].status == stw.ADDR_STATUS_KEPT
          and items[0].match_hex == stw.bytes_to_hex(DLT645)
          and not items[0].match_changed, items[0].status)


def test_batch_mixed_and_unsupported():
    section("[3d] 混合协议 / 不支持协议")

    frame = gdw_frame()
    commands = [
        cmd(DLT645, name="645"),
        cmd(T698, name="698"),
        cmd(YW645, name="依瓦"),
        cmd(CSG_UPLINK, name="南网上行"),
        cmd(SOUTH_ADDR, name="南网"),
        cmd(frame, name="国网"),
    ]
    values = {"addr": "000000000033"}
    items = stw.batch_fix_commands(commands, range(len(commands)), 6, values)
    # 注意：依瓦定制645 的帧结构/校验与 645 **同形**（就是定制 645），故按 645 处理同样成功
    # —— 这是 `frame_addr_fix` 的既有口径（v1 靠结构+原校验自证区分，无法区分这两者）；
    # 用户选错协议时地址字节序会按所选协议编码，故界面上要选对协议。
    check("按 645 处理：645 帧 + 同形的依瓦帧 ok，其余 kept",
          [it.status for it in items] == [stw.ADDR_STATUS_OK, stw.ADDR_STATUS_KEPT,
                                          stw.ADDR_STATUS_OK, stw.ADDR_STATUS_KEPT,
                                          stw.ADDR_STATUS_KEPT, stw.ADDR_STATUS_KEPT],
          [it.status for it in items])

    items = stw.batch_fix_commands(commands, range(len(commands)), 14, {"a2": "1234567"})
    check("同一批用南网上行的地址口径：只有南网上行帧成功",
          [it.status for it in items] == [stw.ADDR_STATUS_KEPT, stw.ADDR_STATUS_KEPT,
                                          stw.ADDR_STATUS_KEPT, stw.ADDR_STATUS_OK,
                                          stw.ADDR_STATUS_KEPT, stw.ADDR_STATUS_KEPT],
          [it.status for it in items])

    items = stw.batch_fix_commands(commands, [0], 9, values)
    check("协议9（v1 不支持）：kept + 可读原因",
          items[0].status == stw.ADDR_STATUS_KEPT and "暂不支持" in items[0].error,
          items[0].error)
    check("协议9：协议列仍写入（用户声明），但帧未改",
          items[0].protocol == 9 and items[0].data_hex == stw.bytes_to_hex(DLT645),
          (items[0].protocol, items[0].data_hex[:12]))

    items = stw.batch_fix_commands([{}], [0], 6, values)
    check("空命令 dict：name 回落「命令1」且不抛异常",
          items[0].name == "命令1" and items[0].status == stw.ADDR_STATUS_SKIPPED,
          (items[0].name, items[0].status))


def test_batch_never_raises():
    section("[3e] 兜底：任何异常都不许中断整批")

    broken = cmd(DLT645, name="异常帧")
    broken["data_hex"] = 12345          # 非字符串（手改配置的极端情况）
    commands = [broken, cmd(DLT645, name="正常帧")]
    items = stw.batch_fix_commands(commands, [0, 1], 6, {"addr": "000000000033"})
    check("非字符串 data_hex：不抛异常且给出条目", len(items) == 2, len(items))
    check("非字符串 data_hex：该条 skipped/kept",
          items[0].status in (stw.ADDR_STATUS_SKIPPED, stw.ADDR_STATUS_KEPT), items[0].status)
    check("后续条目仍正常处理（未被前一条打断）",
          items[1].status == stw.ADDR_STATUS_OK, items[1].error)

    items = stw.batch_fix_commands([cmd(DLT645)], [0], 6, {"addr": object()})
    check("地址值非法类型：kept + 可读原因（不抛异常）",
          items[0].status == stw.ADDR_STATUS_KEPT and bool(items[0].error), items[0].error)


# ── [4] 汇总文案 ───────────────────────────────────────────────────────────

def test_summary():
    section("[4] addr_batch_summary")

    commands = [cmd(DLT645, name="好的"), cmd(SOUTH_ADDR, name="坏的"), cmd("ZZ", name="脏的")]
    items = stw.batch_fix_commands(commands, [0, 1, 2], 6, {"addr": "000000000033"})
    head, detail = stw.addr_batch_summary(items)
    check("首行含三态计数",
          "已替换 1 条" in head and "未替换" in head and "跳过 1 条" in head, head)
    check("明细列出未替换条目及原因",
          "坏的" in detail and "脏的" in detail, detail)

    check("空结果：明确说「没有命令」", stw.addr_batch_summary([])[0] == "作用范围内没有命令")

    many = stw.batch_fix_commands([cmd("ZZ", name=f"c{i}") for i in range(6)],
                                 list(range(6)), 6, {"addr": "000000000033"})
    head, detail = stw.addr_batch_summary(many)
    check("明细最多 3 条 + 一条汇总",
          len(detail.splitlines()) == 4 and "另有 3 条" in detail, detail)

    # 预期响应同步替换的计数
    commands = [cmd(DLT645, name="带响应", match_type="equals",
                    match_hex=stw.bytes_to_hex(DLT645))]
    items = stw.batch_fix_commands(commands, [0], 6, {"addr": "000000000033"})
    head, _detail = stw.addr_batch_summary(items)
    check("首行提示有多少条的预期响应也替换了", "预期响应也同步替换" in head, head)


# ── [5] 反例自检（证明 oracle 有效）────────────────────────────────────────

def test_counter_example():
    section("[5] 反例自检：改地址不重算校验 → 校验器必红")

    tampered = bytearray(DLT645)
    tampered[1:7] = bytes.fromhex("330000000000")     # 只改地址，不动 CS
    fails, res = v_fail(6, bytes(tampered))
    check("645：手改地址不算校验 → 校验器报错（oracle 有效）", fails > 0,
          f"fail={fails} valid={res.valid}")

    tampered = bytearray(T698)
    tampered[5:10] = bytes.fromhex("9900000000")
    fails, _res = v_fail(8, bytes(tampered))
    check("698：手改 SA 不重算 HCS/FCS → 校验器报错", fails > 0, f"fail={fails}")

    # 反例 2：把前导 FE 当成「协议0 的合法帧」也过不去（结构自证）
    _new, _notes, error = stw.fix_frame_text(stw.bytes_to_hex(FE4 + SOUTH_ADDR), 0,
                                             {"dst": "000000000010"})
    check("反例：南网带前导 FE → 结构自证失败（不是「救活」）", bool(error), error)


def main():
    print("=" * 74)
    print("串口工具批量替换通信地址 纯逻辑回归（test_serial_addr_fix.py）")
    print("=" * 74)
    test_constants()
    test_oracle_frames()
    test_fe_prefix()
    test_frame_text_errors()
    test_batch_basic()
    test_batch_scope_and_protocol_switch()
    test_batch_expected_response()
    test_batch_mixed_and_unsupported()
    test_batch_never_raises()
    test_summary()
    test_counter_example()
    print()
    print("=" * 74)
    print(f"PASS={PASS} FAIL={FAIL}")
    print("=" * 74)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
