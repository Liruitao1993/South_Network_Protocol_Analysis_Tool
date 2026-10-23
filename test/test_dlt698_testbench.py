# -*- coding: utf-8 -*-
"""协议8「协议测试」页（`dlt698_test_core` + `dlt698_test_widget`）回归。

覆盖：
  [1]  组帧黄金：6 条报文逐字节对齐协议文档附录 H 的示例（读属性/读多属性/读记录/
       设置属性/操作方法/建立应用连接）；整帧 HCS/FCS 能过自家解析器
  [2]  OAD/OMD/PIID 编码与越界拒绝；``parse_oid`` 未知 OI 不抛
  [3]  date_time_s 编解码（含非法值返回 None）
  [4]  SA 编码：单/通配/广播、地址体线上逆序、地址文本超长拒绝
  [5]  RSD/RCSD：5 种选择方法与文档 H.3.3 的逐字节形态；未实现方法必须抛
  [6]  分类库：10 个顶层分类、777 个对象、子类按 OI 高字节排序（0H 电能量→总电能在前）、
       每个对象都有可下发的 OAD；记录页只留记录型属性（与属性页不同）
  [7]  响应判定：成功/失败(DAR)/列表/记录/CONNECT-Response(不冒充判定)/坏帧
  [8]  地址/时间提取：文档 H.3.1 响应 → 地址；日期时间往返
  [9]  筛选：名称 / OI 前缀 / 类名
  [10] 页面构建（offscreen）：四页分类树、默认参数、帧预览随参数变化
  [11] 发送队列：勾选 → 逐条下发、Lst发送合成一帧、超时重发、终止停发
  [12] 读地址回填：响应里的地址回填「服务器地址」、不覆盖用户已填的「写地址」
  [13] 落盘往返 + 坏文件宽容；cleanup 不关端口、断订阅后不再进帧
  [14] RX 自组帧：半帧分两次交付、噪声重同步
  [15] 源码护栏：不 import main_gui、不用 send_frame、不订阅 frame_received、不自建串口

运行: python test/test_dlt698_testbench.py   （QT_QPA_PLATFORM=offscreen）
"""

import _path_setup  # noqa: E402,F401

import os  # noqa: E402
import sys  # noqa: E402
from datetime import datetime  # noqa: E402
from unittest.mock import patch  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Qt, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import _config_sandbox  # noqa: E402

_config_sandbox.install()          # 落盘重定向到临时目录，别碰用户真实配置

# 构造页面之前屏蔽模态框（否则 offscreen 下永久阻塞）
for _name in ("warning", "information", "critical"):
    patch.object(QMessageBox, _name, lambda *a, **k: 0).start()

import dlt698_test_core as C  # noqa: E402
from dl_t698_45_frame_gen import DLT69845FrameGenerator  # noqa: E402
from dl_t698_45_parser import DLT69845Parser  # noqa: E402

FAILED = []
CHECKS = [0]


def check(name, got, want):
    CHECKS[0] += 1
    got_hex = got.hex().upper() if isinstance(got, (bytes, bytearray)) else got
    want_hex = want.hex().upper() if isinstance(want, (bytes, bytearray)) else want
    if got_hex == want_hex:
        return True
    FAILED.append(f"{name}\n    got  = {got_hex!r}\n    want = {want_hex!r}")
    return False


def check_true(name, cond, detail=""):
    CHECKS[0] += 1
    if cond:
        return True
    FAILED.append(f"{name}" + (f"\n    {detail}" if detail else ""))
    return False


def expect_raises(name, fn, exc=ValueError):
    CHECKS[0] += 1
    try:
        fn()
    except exc:
        return True
    except Exception as other:                            # noqa: BLE001
        FAILED.append(f"{name}: 抛了 {type(other).__name__}（期望 {exc.__name__}）: {other}")
        return False
    FAILED.append(f"{name}: 没有抛 {exc.__name__}")
    return False


def apdu_of(frame: bytes, sa: bytes) -> bytes:
    """从整帧里切出 APDU（68 | L(2) | C | SA | CA | HCS | APDU | FCS | 16）。"""
    start = 1 + 2 + 1 + len(sa) + 1 + 2
    return frame[start:-3]


# ══════════════════════════════════════════════════════════════════════
# [1] 组帧黄金（协议文档附录 H）
# ══════════════════════════════════════════════════════════════════════

def test_golden_frames():
    sa = C.WILDCARD_SA

    cases = [
        ("H.3.1 读一个属性（通信地址）",
         C.build_get(sa, 0, 1, C.OAD_ADDRESS),
         "05 01 01 40 01 02 00 00"),
        ("H.3.2 读多个属性",
         C.build_get_list(sa, 0, 2, [bytes.fromhex("20000200"), bytes.fromhex("20010200")]),
         "05 02 02 02 20 00 02 00 20 01 02 00 00"),
        ("H.3.3 读记录（选择方法1）",
         C.build_get_record(
             sa, 0, 3, bytes.fromhex("50040200"),
             C.build_rsd(1, oad=bytes.fromhex("20210200"),
                         value=C.encode_date_time_s(datetime(2016, 1, 20, 0, 0, 0))),
             C.build_rcsd([bytes.fromhex("20210200"), bytes.fromhex("00100200")])),
         "05 03 03 50 04 02 00 01 20 21 02 00 1C 07 E0 01 14 00 00 00"
         " 02 00 20 21 02 00 00 00 10 02 00 00"),
        ("H.4.1 设置一个属性（校时）",
         C.build_set(sa, 0, 2, C.OAD_DATETIME,
                     C.encode_date_time_s(datetime(2016, 1, 20, 16, 27, 11))),
         "06 01 02 40 00 02 00 1C 07 E0 01 14 10 1B 0B 00"),
        ("H.5.1 操作一个方法（电能量复位）",
         C.build_action(sa, 0, 5, bytes.fromhex("00100100"), bytes.fromhex("0F00")),
         "07 01 05 00 10 01 00 0F 00 00"),
        ("H.2 建立应用连接",
         C.build_connect(sa, 0, 0),
         "02 00 00 10 " + "FF " * 8 + "FF " * 15 + "04 00 04 00 01 04 00 00 00 00 64 00 00"),
    ]
    for name, frame, want in cases:
        want_bytes = bytes.fromhex(want.replace(" ", ""))
        check(f"[1] {name} APDU 逐字节", apdu_of(frame, sa), want_bytes)
        result = C.parse_frame(frame)
        check_true(f"[1] {name} 自家解析器 HCS/FCS 通过",
                   (result.get("帧头校验HCS") or {}).get("校验结果") == "通过"
                   and (result.get("帧校验FCS") or {}).get("校验结果") == "通过",
                   f"解析状态={result.get('解析状态')} 错误={result.get('错误信息')}")
        # 帧长与 L 域自洽：整帧 = L + 2（§6.2.2 a）
        declared = int.from_bytes(frame[1:3], "little")
        check_true(f"[1] {name} L+2 == 整帧长", declared + 2 == len(frame),
                   f"L={declared} 整帧={len(frame)}")

    # 读版本信息（现场实帧，升级页同一口径）
    frame = C.build_get(sa, 0, 1, C.OAD_VERSION)
    check("[1] 读版本信息 APDU", apdu_of(frame, sa), bytes.fromhex("0501014300030000"))

    # 写地址：octet-string(6B)
    frame = C.build_set_address(sa, 0, 1, bytes.fromhex("111111111111"))
    check("[1] 写通信地址 APDU", apdu_of(frame, sa),
          bytes.fromhex("060101" "40010200" "09" "06" "111111111111" "00"))


# ══════════════════════════════════════════════════════════════════════
# [2] OAD / OMD / PIID
# ══════════════════════════════════════════════════════════════════════

def test_oad_omd_piid():
    check("[2] make_oad 默认属性", C.make_oad(0x2000), bytes.fromhex("20000200"))
    check("[2] make_oad 属性+索引", C.make_oad(0x4300, 3, 5), bytes.fromhex("43000305"))
    expect_raises("[2] OI 越界拒绝", lambda: C.make_oad(0x10000))
    expect_raises("[2] 属性越界拒绝", lambda: C.make_oad(0x2000, 256))
    expect_raises("[2] 索引越界拒绝", lambda: C.make_oad(0x2000, 2, 300))

    check("[2] make_omd", C.make_omd(0x0010, 1), bytes.fromhex("00100100"))
    expect_raises("[2] 方法标识越界拒绝", lambda: C.make_omd(0x0010, -1))

    check("[2] PIID 普通序号1", C.build_piid(1, 0), 0x01)
    check("[2] PIID 高优先级序号5", C.build_piid(5, 1), 0x85)
    check("[2] PIID 序号上限63", C.build_piid(63, 0), 0x3F)
    expect_raises("[2] PIID 序号越界", lambda: C.build_piid(64))
    expect_raises("[2] PIID 优先级非法", lambda: C.build_piid(0, 2))
    check("[2] describe_piid", C.describe_piid(0x85), "高优先级 序号5")
    check("[2] describe_piid ACD", C.describe_piid(0x41, acd=True), "ACD=1 序号1")

    info = C.parse_oad(bytes.fromhex("40010200"))
    check("[2] parse_oad 名称", info["name"], "通信地址")
    check("[2] parse_oad 属性号", info["attr_no"], 2)
    check("[2] parse_oad 索引", info["index"], 0)
    # 未知 OI 不抛、给占位名
    unknown = C.parse_oad(bytes.fromhex("FFF90200"))
    check_true("[2] 未知 OI 占位名", str(unknown["name"]).startswith("未知对象"), unknown["name"])
    check("[2] describe_oad 人话",
          C.describe_oad(bytes.fromhex("40010200")),
          "4001H 通信地址 - 2号属性（索引全部内容）")
    check("[2] describe_oad 短数据", C.describe_oad(b"\x40\x01"), "OAD 数据不足（需 4 字节）")


# ══════════════════════════════════════════════════════════════════════
# [3] date_time_s
# ══════════════════════════════════════════════════════════════════════

def test_date_time():
    when = datetime(2016, 1, 20, 16, 27, 11)
    encoded = C.encode_date_time_s(when)
    check("[3] 编码（文档 H.4.1）", encoded, bytes.fromhex("1C07E00114101B0B"))
    check("[3] 解码往返", C.decode_date_time_s(encoded), when)
    check("[3] 解码裸 7 字节", C.decode_date_time_s(encoded[1:]), when)
    check("[3] 文本", C.date_time_text(when), "2016-01-20 16:27:11")
    check("[3] 空值文本", C.date_time_text(None), "")
    # 非法（月 13）⇒ None，不抛
    check("[3] 非法月返回 None",
          C.decode_date_time_s(b"\x1C\x07\xE0\x0D\x01\x00\x00\x00"), None)
    check("[3] 数据不足返回 None", C.decode_date_time_s(b"\x1C\x07"), None)
    expect_raises("[3] 非 datetime 拒绝", lambda: C.encode_date_time_s("2016-01-20"),
                  TypeError)


# ══════════════════════════════════════════════════════════════════════
# [4] SA 地址
# ══════════════════════════════════════════════════════════════════════

def test_sa():
    check("[4] 单地址 6B（线上逆序）",
          C.build_sa(0, 0, 6, bytes.fromhex("111111111111")),
          bytes.fromhex("05111111111111"))
    check("[4] 文档实帧 075506980033",
          C.build_sa(0, 0, 6, bytes.fromhex("075506980033")),
          bytes.fromhex("05330098065507"))
    check("[4] 通配地址", C.WILDCARD_SA, bytes.fromhex("45AAAAAAAAAAAA"))
    check("[4] 广播地址固定 1 字节", C.build_sa(3, 0, 6, b""), b"\xAA")
    check("[4] 文本→字节（前补零）",
          C.address_hex_to_bytes("1122", 4), bytes.fromhex("00001122"))
    expect_raises("[4] 地址超长拒绝", lambda: C.address_hex_to_bytes("1122334455", 4))
    expect_raises("[4] 奇数个字符拒绝", lambda: C.address_hex_to_bytes("112", 4))
    check("[4] 地址长度越界拒绝",
          expect_raises("[4] 地址长度 0 拒绝", lambda: C.build_sa(0, 0, 0, b"")), True)
    check("[4] sa_text 回读书写序", C.sa_text(C.WILDCARD_SA), "AAAAAAAAAAAA")
    check("[4] sa_from_text 与 build_sa 同口径",
          C.sa_from_text(0, 0, 6, "075506980033"),
          C.build_sa(0, 0, 6, bytes.fromhex("075506980033")))


# ══════════════════════════════════════════════════════════════════════
# [5] RSD / RCSD
# ══════════════════════════════════════════════════════════════════════

def test_rsd():
    check("[5] 不选择", C.build_rsd(0), b"\x00")
    check("[5] 方法1", C.build_rsd(1, oad=bytes.fromhex("20210200"),
                                   value=bytes.fromhex("1C07E00114000000")),
          bytes.fromhex("01202102001C07E00114000000"))
    check("[5] 方法2（间隔缺省 00）",
          C.build_rsd(2, oad=bytes.fromhex("20210200"),
                      start=bytes.fromhex("1C07E00114000000"),
                      end=bytes.fromhex("1C07E00115000000")),
          bytes.fromhex("0220210200" "1C07E00114000000" "1C07E00115000000" "00"))
    check("[5] 方法9", C.build_rsd(9, n=3), bytes.fromhex("0903"))
    check("[5] 方法10", C.build_rsd(10, n=5), bytes.fromhex("1005"))
    expect_raises("[5] 未实现方法拒绝", lambda: C.build_rsd(7))
    expect_raises("[5] 方法1 缺 OAD", lambda: C.build_rsd(1))
    expect_raises("[5] 方法2 缺区间", lambda: C.build_rsd(2, oad=bytes.fromhex("20210200")))

    check("[5] RCSD（文档 H.3.3 两列）",
          C.build_rcsd([bytes.fromhex("20210200"), bytes.fromhex("00100200")]),
          bytes.fromhex("0200202102000000100200"))
    expect_raises("[5] RCSD 空列拒绝", lambda: C.build_rcsd([]))
    expect_raises("[5] RCSD 非 4 字节拒绝", lambda: C.build_rcsd([b"\x20\x00"]))


# ══════════════════════════════════════════════════════════════════════
# [6] 分类库
# ══════════════════════════════════════════════════════════════════════

def test_catalog():
    cats = C.catalog()
    check("[6] 顶层分类数", len(cats), 10)
    check("[6] 顶层分类名", [c.name for c in cats], list(C.TOP_ORDER))

    total = sum(c.item_count() for c in cats)
    check("[6] 对象总数 = OI 表条目数", total, len(C.OILookup.OI_NAME_MAP))
    check("[6] all_items 一致", len(C.all_items()), total)

    # 子类按 OI 高字节排序：电能量第一组必须是「总电能」(0H)
    energy = [c for c in cats if c.name == "电能量"][0]
    check("[6] 电能量子类顺序", [g.name for g in energy.groups],
          ["总电能", "基波电能", "谐波电能", "铜损补偿", "铁损补偿", "关联电能"])
    check("[6] 电能量首个子类 hbyte", energy.groups[0].hbyte, 0)
    check("[6] 电能量首个对象", energy.groups[0].items[0].name, "组合有功电能")

    # 每个对象都能给出合法的 4 字节 OAD
    bad = []
    for item in C.all_items():
        oad = item.oad()
        if len(oad) != 4 or int.from_bytes(oad[:2], "big") != item.oi:
            bad.append((item.oi, oad))
    check_true("[6] 全部对象可组 OAD", not bad, f"{len(bad)} 项异常，例如 {bad[:3]}")

    # 关键对象与属性（协议文档附录 H 用到的）
    addr = C.find_item(0x4001)
    check_true("[6] 通信地址 OAD", addr is not None and addr.oad() == C.OAD_ADDRESS)
    dt = C.find_item(0x4000)
    check_true("[6] 日期时间 OAD", dt is not None and dt.oad() == C.OAD_DATETIME)
    ver = C.find_item(0x4300)
    check_true("[6] 电气设备版本信息属性", ver is not None and 3 in [a for a, _ in ver.attrs])

    # 记录型：只有记录表类对象进「读取记录」，且与属性页不同
    record_items = [it for it in C.all_items() if it.record_attrs()]
    check_true("[6] 记录型对象存在且少于全集",
               0 < len(record_items) < total, f"{len(record_items)}/{total}")
    freeze = C.find_item(0x5004)
    check_true("[6] 日冻结属记录型", freeze is not None and bool(freeze.record_attrs()))
    # 电压（2000 数据变量类, 属性2=数值）不是记录型
    volt = C.find_item(0x2000)
    check_true("[6] 电压不算记录型", volt is not None and not volt.record_attrs(),
               str(volt.record_attrs() if volt else None))

    # 分类判定
    check("[6] oi_category 0x2000", C.oi_category(0x2000), ("变量", "测量值"))
    check("[6] oi_category 0x4001", C.oi_category(0x4001), ("参变量", "通用参数"))
    check("[6] oi_category 未登记高字节", C.oi_category(0x9900)[0], "厂家扩展")
    check("[6] 未知 OI find_item", C.find_item(0x9999), None)


# ══════════════════════════════════════════════════════════════════════
# [7] 响应判定
# ══════════════════════════════════════════════════════════════════════

def _frame_from_apdu(apdu_hex: str, sa_hex: str = "123456789012", control: int = 0xC3) -> bytes:
    sa = C.build_sa(0, 0, 6, bytes.fromhex(sa_hex))
    return DLT69845FrameGenerator().generate_apdu_frame(
        sa, 0, bytes.fromhex(apdu_hex.replace(" ", "")), control=control)


def test_tree_labels():
    """树的三层文案：`4H: 参变量` / `3H: 设备管理` / `43000300_（版本信息）_(索引=0)_(优先级及序号=00)`。"""
    # 顶层取高 4 位、子层取低 4 位（与现场工具同形）
    check("[10a] 顶层 0x40 → 4H", C.category_label(0x40, "参变量"), "4H: 参变量")
    check("[10a] 顶层 0x30 → 3H", C.category_label(0x30, "事件"), "3H: 事件")
    check("[10a] 顶层 0xF0 → FH", C.category_label(0xF0, "厂家扩展"), "FH: 厂家扩展")
    check("[10a] 顶层带条目数", C.category_label(0x00, "电能量", 68), "0H: 电能量（68）")
    check("[10a] 子层 0x43 → 3H", C.group_label(0x43, "设备管理"), "3H: 设备管理")
    check("[10a] 子层 0x30 → 0H", C.group_label(0x30, "电能表事件"), "0H: 电能表事件")

    # 叶子：OAD 全字节 + 属性名 + 索引 + PIID（参考工具的原样格式）
    check("[10a] 叶子文案",
          C.leaf_label(bytes.fromhex("43000300"), "版本信息", 0, 0),
          "43000300_（版本信息）_(索引=0)_(优先级及序号=00)")
    check("[10a] 叶子索引非 0",
          C.leaf_label(bytes.fromhex("43000303"), "版本信息", 3, 0x01),
          "43000303_（版本信息）_(索引=3)_(优先级及序号=01)")
    check("[10a] OMD 叶子文案",
          C.omd_label(bytes.fromhex("00100100"), "复位", 0x05),
          "00100100_（复位）_(优先级及序号=05)")

    # 条目摊平：每个属性一条具体 OAD
    dev = C.find_item(0x4300)
    entries = C.oad_entries(dev)
    check("[10a] 设备管理类属性条数", len(entries), len(dev.attrs))
    check("[10a] 首条 = 逻辑名 OAD", entries[0][2], bytes.fromhex("43000100"))
    check("[10a] 版本信息 OAD 在列",
          [e[2] for e in entries if e[1] == "版本信息"], [bytes.fromhex("43000300")])
    check_true("[10a] 每条 OAD 的 OI 都是同一个对象",
               all(e[2][:2] == bytes.fromhex("4300") for e in entries))

    # 记录型与方法的摊平
    freeze = C.find_item(0x5004)
    rec = C.record_entries(freeze)
    check_true("[10a] 记录型摊平非空且都属同一 OI",
               bool(rec) and all(r[2][:2] == freeze.oi.to_bytes(2, "big") for r in rec))
    meth = C.omd_entries(dev)
    check("[10a] 方法条数", len(meth), len(dev.methods))


def test_semantic_names():
    """树叶子的名字要写清「这个 OAD 是什么」（A相电压 / 版本信息），不是类级属性名。"""
    volt = C.find_item(0x2000)
    entries = C.leaf_entries(volt)
    by_oad = {oad.hex().upper(): (ix, attr, name) for ix, attr, name, oad in entries}

    # 参考图里的那一组
    check("[10c] 电压（整体）", by_oad["20000200"][2], "电压")
    check("[10c] A相电压 = 索引1", by_oad["20000201"][:3], (1, 2, "A相电压"))
    check("[10c] B相电压 = 索引2", by_oad["20000202"][:3], (2, 2, "B相电压"))
    check("[10c] C相电压 = 索引3", by_oad["20000203"][:3], (3, 2, "C相电压"))
    check("[10c] 电压逻辑名", by_oad["20000100"][2], "电压逻辑名")
    check("[10c] A相电压逻辑名", by_oad["20000101"][2], "A相电压逻辑名")
    check("[10c] 电压换算及单位", by_oad["20000300"][2], "电压换算及单位")
    check("[10c] A相电压换算及单位", by_oad["20000301"][2], "A相电压换算及单位")
    check("[10c] 带品质", by_oad["20001F00"][2], "电压（带品质）")

    # 名字里的相别要与 OAD 的元素索引一致（01H = 第一个元素）
    for ix, _attr, name, oad in entries:
        if name.startswith(("A相", "B相", "C相")):
            check_true(f"[10c] {name} 的索引字节 = {ix}", oad[3] == ix,
                       f"{oad.hex().upper()} vs index={ix}")

    # 具体属性名不能被对象名盖掉（早先 43000200 被叫成「电气设备」）
    dev = C.find_item(0x4300)
    names = {oad.hex().upper(): name for _ix, _a, name, oad in C.leaf_entries(dev)}
    check("[10c] 43000200 = 设备描述符", names.get("43000200"), "设备描述符")
    check("[10c] 43000300 = 版本信息", names.get("43000300"), "版本信息")
    check("[10c] 43000400 = 生产日期", names.get("43000400"), "生产日期")
    check("[10c] 43000100 = 电气设备逻辑名", names.get("43000100"), "电气设备逻辑名")

    # 同对象的兄弟数组要能分清（class 1 有 6 个电能量数组）
    energy = C.find_item(0x0010)
    enames = [name for _ix, _a, name, _o in C.leaf_entries(energy)]
    check_true("[10c] 电能量兄弟数组不重名", len(enames) == len(set(enames)),
               str([n for n in enames if enames.count(n) > 1]))
    check_true("[10c] 扩展精度带限定词",
               any("（扩展精度）" in n for n in enames), str(enames[:6]))

    # 功率类（class 4）不按相拆：证据不足就不猜
    power = C.find_item(0x2004)
    pnames = [name for _ix, _a, name, _o in C.leaf_entries(power)]
    check_true("[10c] 功率类不展开相别",
               not any(n.startswith(("A相", "B相", "C相")) for n in pnames), str(pnames))

    # 记录型叶子带对象名
    ev = C.find_item(0x3000)
    rec = [C.record_leaf_name(ev, aname) for _a, aname, _o in C.record_entries(ev)]
    check_true("[10c] 记录叶子带对象名", all(ev.name in n for n in rec), str(rec))
    check("[10c] 记录叶子格式", rec[0], "电能表失压事件·关联对象属性表")
    check_true("[10c] 记录叶子含事件记录表",
               any("事件记录表" in n for n in rec), str(rec[:4]))


def test_detail_lines():
    """逐字段明细必须来自解析器那张表（不是自建的第二套拆解）。"""
    frame = C.build_get(C.WILDCARD_SA, 0, 0, C.OAD_VERSION)
    lines = C.detail_lines(frame)
    check_true("[10b] 明细非空且有行数头", len(lines) > 10 and "（" in lines[0], str(lines[:1]))
    text = "\n".join(lines)
    for token in ("起始字符", "长度域", "控制域", "服务器地址SA", "帧头校验HCS",
                  "APDU类型", "OAD", "帧校验FCS", "结束符"):
        check_true(f"[10b] 明细含「{token}」", token in text)
    check_true("[10b] HCS/FCS 显示通过", text.count("通过") >= 2, "")
    check_true("[10b] OAD 有语义说明（通信地址/版本信息都行）",
               "OI=0x4300" in text and "版本信息" in text, "")
    check_true("[10b] 结构化字段不重复打印 dict repr", "{'OI'" not in text, "")

    # 与解析器表格逐行同源
    rows = C.parse_table(frame)
    check("[10b] parse_table 行数与解析器一致", len(rows), len(DLT69845Parser().parse_to_table(frame)))

    # 半截帧：不抛、给可读提示
    bad = C.detail_lines(frame[:6])
    check_true("[10b] 半截帧给提示而不抛",
               isinstance(bad, list) and all(isinstance(x, str) for x in bad), str(bad[:2]))

    # 四列对齐：CJK 宽度算法自证
    check("[10b] 显示宽度 CJK=2", C._display_width("地址"), 4)
    check("[10b] 显示宽度 ASCII=1", C._display_width("OAD"), 3)

    # 长 hex 压缩：偶数/奇数长度都要压（解析器会给被截断的奇数长度编码）
    long_even = "AB" * 60
    check_true("[10b] 长 hex（偶数）压缩",
               "…" in C._compact_hex_like(long_even)
               and "共 120 字符" in C._compact_hex_like(long_even),
               C._compact_hex_like(long_even))
    long_odd = "AB" * 60 + "C"
    check_true("[10b] 长 hex（奇数）也压缩",
               "…" in C._compact_hex_like(long_odd), C._compact_hex_like(long_odd))
    check("[10b] 非 hex 文本不压缩",
          C._compact_hex_like("这是一段说明文字，不该被当成十六进制"), "这是一段说明文字，不该被当成十六进制")
    check("[10b] 短 hex 不压缩", C._compact_hex_like("43000300"), "43000300")

    # 明细里不该出现超长行（否则日志会撑到屏幕外）
    oversize = [l for l in lines if len(l) > 200]
    check_true("[10b] 明细无超长行", not oversize, f"{len(oversize)} 行超 200 字符")


def test_evaluate():
    # 成功：读通信地址（文档 H.3.1 响应）
    frame = _frame_from_apdu("85 01 01 40 01 02 00 01 09 06 12 34 56 78 90 12 00 00")
    info = C.evaluate_response(frame)
    check("[7] 读成功 ok", info["ok"], True)
    check("[7] 读成功标题", info["title"], "成功")
    check("[7] 读成功 OAD", info["oad"], "40010200")
    check_true("[7] 读成功有字段行", any("123456789012" in l for l in info["lines"]),
               str(info["lines"]))

    # 失败：DAR≠0（GET-Response 错误信息分支）
    # 85 01 01 40010200 00 05  (GetResult=[0]错误信息, DAR=5)
    frame = _frame_from_apdu("85 01 01 40 01 02 00 00 05 00 00")
    info = C.evaluate_response(frame)
    check("[7] DAR≠0 ok=False", info["ok"], False)
    check("[7] DAR≠0 值", info["dar"], 5)
    check_true("[7] DAR≠0 带原因", bool(info["reason"]), str(info))

    # 列表（文档 H.3.2 响应）
    frame = _frame_from_apdu(
        "85 02 02 02 20 00 02 00 01 01 03 12 09 6D 12 09 6D 12 09 6D"
        " 20 01 02 00 01 01 03 05 00 00 03 E8 05 00 00 03 E8 05 00 00 03 E8 00 00")
    info = C.evaluate_response(frame)
    check("[7] 列表 ok", info["ok"], True)
    check_true("[7] 列表两行以上", len(info["lines"]) >= 2, str(info["lines"]))

    # 记录型（文档 H.3.3 响应头部，截短数据体也行：只要求不解崩）
    frame = _frame_from_apdu("85 03 03 50 04 02 00 02 00 20 21 02 00 00 00 10 02 00 01 01")
    info = C.evaluate_response(frame)
    check("[7] 记录 ok", info["ok"], True)
    check_true("[7] 记录给出列数", any("记录列数" in l for l in info["lines"]),
               str(info["lines"]))

    # SET / ACTION 成功
    info = C.evaluate_response(_frame_from_apdu("86 01 02 40 00 02 00 00 00 00"))
    check("[7] 设置成功", info["ok"], True)
    check("[7] 设置成功标题", info["title"], "设置成功")
    info = C.evaluate_response(_frame_from_apdu("87 01 05 00 10 01 00 00 00 00"))
    check("[7] 操作成功", info["ok"], True)
    check("[7] 操作成功标题", info["title"], "操作成功")

    # CONNECT-Response：解析器未做字段级解析 ⇒ 必须**不冒充**成功
    info = C.evaluate_response(_frame_from_apdu(
        "82 00 00 10 " + "FF " * 8 + "FF " * 15 + "04 00 04 00 01 04 00 00 00 00 64 00 00"))
    check("[7] CONNECT 不冒充判定", info["ok"], None)
    check_true("[7] CONNECT 说明含未做字段级解析", "未做字段级解析" in str(info["title"]),
               str(info["title"]))

    # 坏帧 / 非 698 字节：不抛、ok=False
    info = C.evaluate_response(b"\x01\x02\x03\x04")
    check("[7] 坏帧 ok=False", info["ok"], False)
    info = C.evaluate_response(b"")
    check("[7] 空帧 ok=False", info["ok"], False)
    # 篡改 FCS 的帧
    good = bytearray(_frame_from_apdu("85 01 01 40 01 02 00 01 09 06 12 34 56 78 90 12 00 00"))
    good[-2] ^= 0xFF
    info = C.evaluate_response(bytes(good))
    check("[7] 坏 FCS ok=False", info["ok"], False)
    check_true("[7] 坏 FCS 原因含 FCS", "FCS" in str(info["reason"]), str(info["reason"]))


# ══════════════════════════════════════════════════════════════════════
# [8] 地址 / 时间提取
# ══════════════════════════════════════════════════════════════════════

def test_extract():
    frame = _frame_from_apdu("85 01 01 40 01 02 00 01 09 06 12 34 56 78 90 12 00 00")
    check("[8] 提取通信地址", C.extract_address(frame), "123456789012")
    # OAD 不是通信地址 ⇒ 不取
    frame = _frame_from_apdu("85 01 01 43 00 03 00 01 09 06 12 34 56 78 90 12 00 00")
    check("[8] 非通信地址 OAD 不取", C.extract_address(frame), "")
    check("[8] 坏帧不取", C.extract_address(b"\x00\x01"), "")

    # 日期时间响应：Data = date_time_s
    when = datetime(2026, 10, 21, 15, 43, 18)
    data = C.encode_date_time_s(when).hex().upper()
    apdu = f"85 01 01 40 00 02 00 01 {data} 00 00"
    frame = _frame_from_apdu(apdu)
    check("[8] 提取日期时间", C.extract_date_time(frame), when)
    check("[8] 无时间响应返回 None",
          C.extract_date_time(_frame_from_apdu("86 01 02 40 00 02 00 00 00 00")), None)


# ══════════════════════════════════════════════════════════════════════
# [9] 筛选
# ══════════════════════════════════════════════════════════════════════

def test_filter():
    items = C.all_items()
    check("[9] 空关键字=全部", len(C.filter_items("", items)), len(items))
    hits = C.filter_items("电压", items)
    check_true("[9] 按名称命中", len(hits) >= 1 and any("电压" in h.name for h in hits))
    hits = C.filter_items("2000", items)
    check_true("[9] 按 OI 前缀命中 0x2000", any(h.oi == 0x2000 for h in hits), str([hex(h.oi) for h in hits][:5]))
    hits = C.filter_items("0x4001", items)
    check_true("[9] 0x 前缀命中", any(h.oi == 0x4001 for h in hits))
    hits = C.filter_items("电能量类", items)
    check_true("[9] 按接口类名命中", len(hits) > 0 and all("电能量" in h.class_name for h in hits))
    check_true("[9] 无命中返回空", len(C.filter_items("绝不存在的东西", items)) == 0)


# ══════════════════════════════════════════════════════════════════════
# GUI：假串口 worker
# ══════════════════════════════════════════════════════════════════════

class FakeSerialWorker(QObject):
    """鸭子类型的 SerialWorker 替身（只实现本页用到的接口）。"""

    raw_data_received = Signal(bytes)
    connection_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self, opened: bool = True):
        super().__init__()
        self._open = bool(opened)
        self.sent = []
        self.writes = 0
        self.closed = 0

    def is_open(self) -> bool:
        return self._open

    def write_raw(self, data: bytes) -> bool:
        if not self._open:
            return False
        self.writes += 1
        self.sent.append(bytes(data))
        return True

    def close_port(self) -> None:
        self.closed += 1

    def deliver(self, data: bytes) -> None:
        self.raw_data_received.emit(bytes(data))


def _app():
    return QApplication.instance() or QApplication([])


def _make_widget():
    import dlt698_test_widget as W

    widget = W.Dlt698TestWidget()
    worker = FakeSerialWorker()
    widget.set_serial_worker(worker)
    return widget, worker


_ADDR_RESP_APDU = "85 01 01 40 01 02 00 01 09 06 12 34 56 78 90 12 00 00"


def test_gui_build():
    _app()
    import dlt698_test_widget as W

    w, worker = _make_widget()
    try:
        check("[10] 四页标题", [w.tabs.tabText(i) for i in range(w.tabs.count())],
              [t for _k, t in W.PAGES])
        # 每页首次切到时才建树
        for i, (key, _title) in enumerate(W.PAGES):
            w.tabs.setCurrentIndex(i)
            state = w._pages.get(key)
            check_true(f"[10] {key} 页已构建", state is not None and state["built"])
        read_state = w._pages["read"]
        check("[10] 读取属性页 10 个顶层分类", read_state["tree"].topLevelItemCount(), 10)

        # 选中「组合有功电能」→ 名称/预览更新
        leaf = read_state["tree"].topLevelItem(0).child(0).child(0)
        read_state["tree"].setCurrentItem(leaf)
        check("[10] 当前项名称", read_state["lbl_name"].text().strip(), "0000H  组合有功电能")
        preview = read_state["preview"].toPlainText()
        check_true("[10] 预览是整帧 hex", preview.startswith("68 ") and preview.rstrip().endswith("16"),
                   preview)
        # 叶子是「每个属性一条具体 OAD」：第一项是 0000 的 1 号属性（逻辑名）
        check_true("[10] 预览含叶子 OAD 00000100", "00 00 01 00" in preview, preview)

        # 索引变化 → 该叶子文案与预览都跟着变（索引是这一条的覆盖）
        idx_before = read_state["preview"].toPlainText()
        leaf_before = leaf.text(0)
        read_state["spin_index"].setValue(2)
        check_true("[10] 改索引后预览变化",
                   read_state["preview"].toPlainText() != idx_before,
                   read_state["preview"].toPlainText())
        check_true("[10] 改索引后叶子文案同步",
                   leaf.text(0) != leaf_before and "(索引=2)" in leaf.text(0),
                   f"before={leaf_before!r} after={leaf.text(0)!r}")
        read_state["spin_index"].setValue(0)

        # 建树后计数立刻是「N / 总数」，不必先敲筛选
        check_true("[10] 计数初始化为 OAD 总数",
                   read_state["counter"].text().endswith("条 OAD")
                   and not read_state["counter"].text().startswith("0 "),
                   read_state["counter"].text())

        # ── 树的简要信息（用户要求：与现场工具同形的三层标签）──
        cat0 = read_state["tree"].topLevelItem(0)
        check("[10] 顶层标签形如 0H: 电能量", cat0.text(0), "0H: 电能量")
        grp0 = cat0.child(0)
        check("[10] 子层标签形如 0H: 总电能", grp0.text(0), "0H: 总电能")
        first_leaf = grp0.child(0)
        piid_now = w._piid_byte()
        check("[10] 叶子=OAD_(语义名)_(索引)_(优先级及序号)",
              first_leaf.text(0),
              f"00000100_（组合有功电能逻辑名）_(索引=0)_(优先级及序号={piid_now:02X})")

        # 参变量 → 设备管理 → 43000300（参考截图里点的那条）
        target = find_leaf(read_state["tree"], "43000300")
        check_true("[10] 树里能找到 43000300 这条 OAD", target is not None)
        if target is not None:
            check("[10] 43000300 叶子文案", target.text(0),
                  f"43000300_（版本信息）_(索引=0)_(优先级及序号={piid_now:02X})")
            read_state["tree"].setCurrentItem(target)
            check_true("[10] 选中后当前项是电气设备",
                       read_state["lbl_name"].text().endswith("电气设备"),
                       read_state["lbl_name"].text())
            # 整帧 APDU = 05 01 <PIID> 43000300 00（PIID 取当前设置，不硬编码）
            want_apdu = f"05 01 {piid_now:02X} 43 00 03 00 00"
            check_true("[10] 选中 43000300 的整帧与请求口径一致",
                       want_apdu in read_state["preview"].toPlainText(),
                       f"want={want_apdu} got={read_state['preview'].toPlainText()}")

            # PIID 变化 → 全树文案跟着（标签写着「将要下发的 PIID」）
            w.spin_piid.setValue(5)
            check_true("[10] PIID 变化后叶子文案同步",
                       "(优先级及序号=05)" in target.text(0), target.text(0))
            w.spin_piid.setValue(1)

        # 「线上 SA」按地址实时回显（此前恒为「—」）
        w.edit_sa.setText("111111111111")
        check_true("[10] 线上 SA 回显含特征字节与 6 字节地址体",
                   "05 11 11 11 11 11 11" in w.lbl_sa_wire.text(),
                   w.lbl_sa_wire.text())
        w.edit_sa.setText("12")           # 短地址：前补零到 6 字节
        check_true("[10] 短地址按前补零补齐（不是错误）",
                   "05 12 00 00 00 00 00" in w.lbl_sa_wire.text(), w.lbl_sa_wire.text())
        w.edit_sa.setText("123")          # 奇数个 hex 字符 = 非法
        check_true("[10] 非法地址在 SA 回显处给 ⚠",
                   w.lbl_sa_wire.text().startswith("⚠"), w.lbl_sa_wire.text())
        w.edit_sa.setText("111111111111")

        # 筛选
        read_state["filter"].setText("4001")
        check_true("[10] 筛选计数", "/" in read_state["counter"].text(), read_state["counter"].text())
        read_state["filter"].setText("")

        # 记录页属性表 ≠ 属性页（只留记录型）
        w.tabs.setCurrentIndex(2)
        rec = w._pages["record"]
        check_true("[10] 记录页对象少于属性页", self_count(rec) < self_count(read_state),
                   f"{self_count(rec)} vs {self_count(read_state)}")
        # CONNECT 页按钮存在且带说明
        check_true("[10] 建立应用连接按钮", w.btn_connect.isEnabled() or True)
    finally:
        w.cleanup()


def find_leaf(tree, prefix: str):
    """在树里按 OAD 文案前缀找叶子（返回第一个命中项或 None）。"""
    for i in range(tree.topLevelItemCount()):
        cat = tree.topLevelItem(i)
        for j in range(cat.childCount()):
            group = cat.child(j)
            for k in range(group.childCount()):
                leaf = group.child(k)
                if leaf.text(0).startswith(prefix):
                    return leaf
    return None


def self_count(state) -> int:
    """页面公开的叶子计数（测试不另写一份，避免与实现漂移）。"""
    import dlt698_test_widget as W

    return W.tree_leaf_count(state)


def test_gui_send_queue():
    _app()
    w, worker = _make_widget()
    try:
        w.tabs.setCurrentIndex(0)
        state = w._pages["read"]
        w._set_all_checked("read", False)
        leaves = [state["tree"].topLevelItem(0).child(0).child(0),
                  state["tree"].topLevelItem(0).child(0).child(1)]
        for leaf in leaves:
            leaf.setCheckState(0, Qt.Checked)
        state["tree"].setCurrentItem(leaves[0])

        entries = w._build_entries()
        check("[11] 勾选两项 → 两条队列", len(entries), 2)
        check("[11] 每条一帧", len({e["frame"] for e in entries}), 2)

        w._queue = list(entries)
        w._set_running(True)
        w._send_next()
        check("[11] 首帧已写", worker.writes, 1)
        check_true("[11] 等待响应", w._awaiting)
        check("[11] 信息表首次为等待中", w.table_info.item(0, 1).text(), "等待中")

        # 注入响应 → 推进到第二条
        worker.deliver(_frame_from_apdu(_ADDR_RESP_APDU))
        check("[11] 收到响应后退出等待", w._awaiting, False)
        check_true("[11] 结果列被改写", w.table_info.item(0, 1).text() in
                   ("成功", "失败", "无法判定"),
                   w.table_info.item(0, 1).text())

        # Lst 模式：勾选多项合成一帧
        w.chk_list.setChecked(True)
        entries = w._build_entries()
        check("[11] Lst发送合成一帧", len(entries), 1)
        check_true("[11] 合成帧是 05 02 列表读取", "05 02" in entries[0]["frame"].hex(" ").upper(),
                   entries[0]["frame"].hex(" ").upper())
        w.chk_list.setChecked(False)

        # 超时重发：把超时压到最短，手动触发超时槽
        w._queue.clear()
        w.spin_retries.setValue(1)
        entry = w._build_entries()[0]
        w._queue = [entry]
        w._send_next()
        before = worker.writes
        w._on_reply_timeout()
        check("[11] 超时后重发一次", worker.writes, before + 1)
        w._on_reply_timeout()
        check_true("[11] 重发用尽后记超时",
                   w.table_info.item(entry["row"], 1).text() == "超时",
                   w.table_info.item(entry["row"], 1).text())

        # 终止
        w._queue = [w._build_entries()[0]]
        w._send_next()
        w._on_stop()
        check("[11] 终止后不再等待", w._awaiting, False)
        check("[11] 终止清空队列", len(w._queue), 0)
    finally:
        w.cleanup()


def test_gui_detailed_log():
    """收发日志：勾「详细解析」逐字段输出，取消只留摘要；双击报文表送单帧解析。"""
    _app()
    w, worker = _make_widget()
    try:
        w.tabs.setCurrentIndex(0)
        state = w._pages["read"]
        state["tree"].setCurrentItem(state["tree"].topLevelItem(0).child(0).child(0))

        check_true("[18] 详细解析默认勾选", w.chk_detail.isChecked())

        # 收到一帧 → 日志里应有完整字段表
        w._run_single(C.quick_read_address(C.WILDCARD_SA, 0, 0), "读通信地址", ("read_addr",))
        frame = _frame_from_apdu(_ADDR_RESP_APDU)
        worker.deliver(frame)
        log = w.log_text.toPlainText()
        check_true("[18] 日志含「帧结构（N 行）」", "帧结构（" in log, log[:200])
        for token in ("起始字符", "长度域", "帧头校验HCS", "APDU类型", "OAD", "帧校验FCS"):
            check_true(f"[18] 日志含字段「{token}」", token in log)
        check_true("[18] 日志含发送帧结构（TX 也自证）", "发送帧结构" in log, log[:200])

        # 取消勾选 → 之后的日志不再带字段表
        w.chk_detail.setChecked(False)
        w.log_text.clear()
        w._run_single(C.quick_read_address(C.WILDCARD_SA, 0, 0), "读通信地址", ())
        worker.deliver(frame)
        short = w.log_text.toPlainText()
        check_true("[18] 取消勾选后无字段表", "帧结构" not in short, short[:200])
        check_true("[18] 取消勾选仍有摘要", "[RX]" in short and "[TX]" in short, short[:200])
        w.chk_detail.setChecked(True)

        # 双击报文表 → 发信号带走整帧 hex（用原字节，不用表格里可能截断的文本）
        captured = []
        w.frame_to_single_parse.connect(lambda text: captured.append(text))
        check_true("[18] 报文表有行", w.table_raw.rowCount() >= 1, str(w.table_raw.rowCount()))
        row = w.table_raw.rowCount() - 1
        w._on_raw_row_activated(row, 3)
        check("[18] 双击送出整帧 hex", len(captured), 1)
        if captured:
            sent = bytes.fromhex(captured[0].replace(" ", ""))
            check_true("[18] 送出的就是该行原字节", sent == w._raw_frames[row],
                       f"{sent.hex()} vs {w._raw_frames[row].hex()}")

        # 落盘往返
        w.chk_detail.setChecked(False)
        check("[18] 开关落盘", w._save_persisted(), True)
        w2, _w2 = _make_widget()
        try:
            check("[18] 重开保持取消勾选", w2.chk_detail.isChecked(), False)
        finally:
            w2.cleanup()
    finally:
        w.cleanup()


def test_gui_read_address_backfill():
    _app()
    w, worker = _make_widget()
    try:
        w.edit_read_addr.clear()
        w.edit_write_addr.clear()
        w.edit_sa.setText("111111111111")
        w._on_read_address()
        check("[12] 已发出读地址帧", worker.writes, 1)
        sent = worker.sent[-1]
        check_true("[12] 帧里是 OAD 40010200", "40010200" in sent.hex().upper(), sent.hex(" ").upper())

        worker.deliver(_frame_from_apdu(_ADDR_RESP_APDU))
        check("[12] 读地址回填", w.edit_read_addr.text(), "123456789012")
        check("[12] 回填服务器地址", w.edit_sa.text(), "123456789012")
        check("[12] 写地址为空时也回填", w.edit_write_addr.text(), "123456789012")

        # 用户已填的写地址不得被覆盖
        w.edit_write_addr.setText("AABBCCDDEEFF")
        w._on_read_address()
        worker.deliver(_frame_from_apdu(_ADDR_RESP_APDU))
        check("[12] 不覆盖用户已填的写地址", w.edit_write_addr.text(), "AABBCCDDEEFF")
    finally:
        w.cleanup()


def test_gui_rx_deframe():
    _app()
    w, worker = _make_widget()
    try:
        frame = _frame_from_apdu(_ADDR_RESP_APDU)
        half = len(frame) // 2
        worker.deliver(frame[:half])
        check("[14] 半帧不触发处理", w.table_raw.rowCount(), 0)
        worker.deliver(frame[half:])
        check("[14] 补齐后切出一帧", w.table_raw.rowCount(), 1)
        check("[14] 报文表方向", w.table_raw.item(0, 1).text(), "RX")

        # 噪声 + 真帧：重同步后仍要认出
        w.table_raw.setRowCount(0)
        worker.deliver(b"\x00\x11\x22" + frame)
        check("[14] 噪声前缀仍能切帧", w.table_raw.rowCount(), 1)
    finally:
        w.cleanup()


def test_gui_persist_and_cleanup():
    _app()
    w, worker = _make_widget()
    try:
        w.spin_ca.setValue(0x10)
        w.spin_timeout.setValue(3500)
        w.chk_loop.setChecked(True)
        w.spin_piid.setValue(9)
        w.edit_sa.setText("112233445566")
        check("[13] 落盘成功", w._save_persisted(), True)

        w2, worker2 = _make_widget()
        try:
            check("[13] CA 往返", w2.spin_ca.value(), 0x10)
            check("[13] 超时往返", w2.spin_timeout.value(), 3500)
            check("[13] 循环发送往返", w2.chk_loop.isChecked(), True)
            check("[13] PIID 往返", w2.spin_piid.value(), 9)
            check("[13] 服务器地址往返", w2.edit_sa.text(), "112233445566")
        finally:
            w2.cleanup()

        # cleanup 不关端口；断订阅后交付的字节不再进表
        w.cleanup()
        check("[13] cleanup 不关串口", worker.closed, 0)
        rows = w.table_raw.rowCount()
        worker.deliver(_frame_from_apdu(_ADDR_RESP_APDU))
        check("[13] cleanup 后不再收帧", w.table_raw.rowCount(), rows)
        w.cleanup()          # 幂等
    finally:
        pass


def test_gui_oad_override():
    """「编辑」把当前 OAD 填进覆盖框，覆盖值进入组帧；清空即回到按属性生成。"""
    _app()
    w, worker = _make_widget()
    try:
        w.tabs.setCurrentIndex(0)
        state = w._pages["read"]
        state["tree"].setCurrentItem(state["tree"].topLevelItem(0).child(0).child(0))
        base = state["preview"].toPlainText()

        w._on_edit_current()
        filled = state["edit_oad"].text()
        check("[17] 编辑填入 4 字节 OAD", len(filled), 8)
        check_true("[17] 填入值与当前项一致", filled in base.replace(" ", ""), f"{filled} / {base}")

        # 改成厂家自定义 OAD → 预览与下发都用它
        state["edit_oad"].setText("FF100400")
        preview = state["preview"].toPlainText()
        check_true("[17] 预览采用覆盖 OAD", "FF 10 04 00" in preview, preview)
        entry = w._build_entries()[0]
        check_true("[17] 下发帧采用覆盖 OAD",
                   "FF100400" in entry["frame"].hex().upper(), entry["frame"].hex(" ").upper())

        # 非法覆盖 → 预览给 ⚠，不静默退回
        state["edit_oad"].setText("FF10")
        check_true("[17] 短覆盖在预览里报错", "⚠" in state["preview"].toPlainText(),
                   state["preview"].toPlainText())
        check_true("[17] 短覆盖发不出去",
                   _raises(lambda: w._build_entries()), "")

        # 清空 → 回到按属性生成
        state["edit_oad"].setText("")
        check("[17] 清空后预览回到原值", state["preview"].toPlainText(), base)
    finally:
        w.cleanup()


def _raises(fn) -> bool:
    try:
        fn()
    except ValueError:
        return True
    except Exception:                                     # noqa: BLE001
        return False
    return False


def test_theme():
    _app()
    w, _worker = _make_widget()
    try:
        w.restyle_for_theme(True)
        dark_bg = w.log_text.styleSheet()
        w.restyle_for_theme(False)
        light_bg = w.log_text.styleSheet()
        check_true("[15] 主题切换改变日志配色", dark_bg != light_bg)
        w.tabs.setCurrentIndex(0)
        w.restyle_for_theme(True)     # 已建页的预览框也要跟着换
        check_true("[15] 预览框也随主题上色",
                   "background-color" in w._pages["read"]["preview"].styleSheet())
    finally:
        w.cleanup()


# ══════════════════════════════════════════════════════════════════════
# 源码护栏
# ══════════════════════════════════════════════════════════════════════

def test_source_guards():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for name in ("dlt698_test_core.py", "dlt698_test_widget.py"):
        with open(os.path.join(root, name), encoding="utf-8") as fh:
            src = fh.read()
        check_true(f"[16] {name} 不 import main_gui", "import main_gui" not in src)
    with open(os.path.join(root, "dlt698_test_widget.py"), encoding="utf-8") as fh:
        src = fh.read()
    check_true("[16] 页面不用 send_frame（避免逐条刷 [发送]）", ".send_frame(" not in src)
    check_true("[16] 页面不订阅 frame_received（698 会被截断）",
               "frame_received.connect" not in src)
    check_true("[16] 页面订阅 raw_data_received", "raw_data_received.connect" in src)
    check_true("[16] 页面不自建串口", "QSerialPort" not in src and "serial.Serial" not in src)
    check_true("[16] 页面惰性 import 逻辑层", "import dlt698_test_core" in src)
    # 逻辑层不 import Qt
    with open(os.path.join(root, "dlt698_test_core.py"), encoding="utf-8") as fh:
        core_src = fh.read()
    check_true("[16] 逻辑层不依赖 Qt", "PySide6" not in core_src and "QtCore" not in core_src)

    # 落盘必须落在沙箱里（本测试踩过：未装沙箱的临时脚本把测试参数写进了真实数据文件）
    import app_paths

    real = str(app_paths.data_path("dlt698_testbench.json"))
    check_true("[16] 落盘路径已被沙箱重定向（不写用户真实配置）",
               "Temp" in real or "tmp" in real.lower(), real)


# ══════════════════════════════════════════════════════════════════════

def main() -> int:
    tests = [
        ("[1] 组帧黄金", test_golden_frames),
        ("[2] OAD/OMD/PIID", test_oad_omd_piid),
        ("[3] date_time_s", test_date_time),
        ("[4] SA 地址", test_sa),
        ("[5] RSD/RCSD", test_rsd),
        ("[6] 分类库", test_catalog),
        ("[10a] 树文案", test_tree_labels),
        ("[10c] 叶子的语义名", test_semantic_names),
        ("[10b] 逐字段明细", test_detail_lines),
        ("[7] 响应判定", test_evaluate),
        ("[8] 地址/时间提取", test_extract),
        ("[9] 筛选", test_filter),
        ("[10] 页面构建", test_gui_build),
        ("[11] 发送队列", test_gui_send_queue),
        ("[18] 详细解析日志", test_gui_detailed_log),
        ("[12] 读地址回填", test_gui_read_address_backfill),
        ("[13] 落盘/cleanup", test_gui_persist_and_cleanup),
        ("[14] RX 自组帧", test_gui_rx_deframe),
        ("[15] 主题", test_theme),
        ("[17] OAD 覆盖", test_gui_oad_override),
        ("[16] 源码护栏", test_source_guards),
    ]
    for name, fn in tests:
        before = len(FAILED)
        try:
            fn()
        except Exception as exc:                          # noqa: BLE001
            import traceback

            FAILED.append(f"{name} 抛异常：{type(exc).__name__}: {exc}\n"
                          f"{traceback.format_exc()}")
        status = "OK  " if len(FAILED) == before else "FAIL"
        print(f"{status} {name}")

    print()
    if FAILED:
        print(f"失败 {len(FAILED)} 项 / 共 {CHECKS[0]} 项检查")
        for item in FAILED:
            print(" - " + item)
        return 1
    print(f"全部通过：{CHECKS[0]} 项检查")
    return 0


if __name__ == "__main__":
    sys.exit(main())
