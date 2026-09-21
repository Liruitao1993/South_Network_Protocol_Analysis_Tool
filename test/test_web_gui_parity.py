# -*- coding: utf-8 -*-
"""Web↔GUI 摘要对拍（任务 09-17-web-gui-parity-sync）

R3（步骤 4.5）：测试类报文摘要片段两端同源
  - 协议9 表61 测试帧 / 2.0 测试帧（业务标识 0xF0）
  - 协议10 检测扩展命令（模式3 / 安全测试模式13 / 新一代测试模式15）
  - 协议11 通信测试扩展（用户真实帧）
  - 非测试帧不得出现该片段（协议9 确认帧 / 协议10 普通通信测试模式0）
  - 单一来源守卫：唯一实现在 batch_core，桌面转发、Web import

对拍口径：R3 交付的是**测试模式片段**本身（两端逐字符一致 + Web 不重复追加）。
整串摘要的其余段落仍有既有差异（协议9 的 MSDU/业务标识渲染、协议11 的 NID 段），
属 09-15-web-shared-parse-core 范围，本测试不断言。

直接运行: python test/test_web_gui_parity.py
"""


import _path_setup  # noqa: E402

import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from csg_new_gen_parser import CSGNewGenParser  # noqa: E402
from gw_new_gen_cmd_payloads import _parse_comm_test  # noqa: E402
from hdc10_parser import HDC10Parser  # noqa: E402
from reflex_web import web_utils  # noqa: E402

import batch_core  # noqa: E402
import main_gui  # noqa: E402

passed = 0
failed = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  [OK] {name}")
    else:
        failed += 1
        print(f"  [XX] {name} {detail}")


class Host:
    """仅提供摘要方法的最小宿主（免 GUI/QApplication 驱动）。"""

    _get_csg_new_gen_summary = main_gui.MainWindow._get_csg_new_gen_summary
    _extract_csg_core_content = main_gui.MainWindow._extract_csg_core_content
    _get_gw_new_gen_summary = main_gui.MainWindow._get_gw_new_gen_summary
    # staticmethod 需显式包裹：直接挂到类体会变成实例方法（多传一个 self）
    _extract_test_mode_content = staticmethod(
        main_gui.MainWindow._extract_test_mode_content
    )
    _TEST_MODE_SENTINELS = main_gui.MainWindow._TEST_MODE_SENTINELS


host = Host()


# ── 真实/构造帧素材（与 test_csg_summary.py、test_hdc10_comm_test_ext.py 同源）──

def _app_frame(ctrl: int, sdu: bytes, sid: int = 0xF0) -> bytes:
    """构造协议9 应用层帧：端口+标识+保留+控制域+业务标识+版本+序号+帧长+SDU"""
    return (
        bytes([0x11, 0x01, 0x01, 0x00])
        + ctrl.to_bytes(2, "little")
        + bytes([sid, 0x01])
        + (0).to_bytes(2, "little")
        + len(sdu).to_bytes(2, "little")
        + sdu
    )


# 1.0 测试帧 SDU：测试ID=0x03 + 保留 + 数据区长度(LE) + 表61（测试模式=3 在字节1高4位）
SDU_TEST_1_0 = bytes([0x03, 0x00, 0x08, 0x00]) + bytes(
    [0x01, 0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
)
# 2.0 测试帧（Bitloading表下发）
SDU_TEST_2_0 = bytes.fromhex(
    "04 00 28 00 01 06 02 00 01 00 02 00 01 03 EA 01 "
    "18 00 48 04 B6 6D DB 24 49 92 24 49 49 92 24 49 "
    "4A 92 24 49 92 00 00 00 00 00 00 00".replace(" ", "")
)
# 协议11 用户真实帧（SOF + MAC + 应用层 端口0x11 / 报文ID 0x0006 通信测试）
HDC_USER_FRAME = bytes.fromhex(
    "0100000000F0FFFE1D186B4300A7A79AC00000FF1F000400"
    "300800FF00000100001106000001613000672B0C98"
)

csg = CSGNewGenParser()
hdc10 = HDC10Parser()


def _pair(protocol_index: int, table_data: list) -> tuple:
    """返回 (桌面摘要, Web 摘要, 共享片段)"""
    if protocol_index == 9:
        desktop = host._get_csg_new_gen_summary(table_data)
    else:
        desktop = host._get_gw_new_gen_summary(table_data)
    web = web_utils.get_frame_summary(table_data, protocol_index)
    return desktop, web, batch_core.extract_test_mode_content(table_data)


def _check_fragment(name: str, protocol_index: int, table_data: list, expect: str) -> None:
    desktop, web, frag = _pair(protocol_index, table_data)
    print(f"\n── {name} ──")
    print(f"   桌面: {desktop}")
    print(f"   Web : {web}")
    check(f"{name}：共享片段非空", bool(frag), f"frag={frag!r}")
    check(f"{name}：片段逐字符符合预期", frag == expect, f"{frag!r} != {expect!r}")
    check(f"{name}：桌面摘要含该片段", frag and frag in desktop, desktop)
    check(f"{name}：Web 摘要含该片段", frag and frag in web, web)
    check(f"{name}：Web 不重复追加", web.count(frag) == 1, f"count={web.count(frag)}")


print("═══ R3：测试类报文摘要片段两端同源 ═══")

_check_fragment(
    "协议9 表61 测试帧",
    9,
    csg.parse_to_table(_app_frame(0x4002, SDU_TEST_1_0), parse_level="app"),
    "测试模式:PLC物理层透传测试模式(3)",
)

_check_fragment(
    "协议9 2.0 测试帧",
    9,
    csg.parse_to_table(_app_frame(0x4002, SDU_TEST_2_0), parse_level="app"),
    "测试ID:2.0测试 | 扩展ID:Bitloading表下发",
)

_check_fragment(
    "协议10 检测扩展命令 模式3",
    10,
    _parse_comm_test(bytes([0x41, 0x30, 0x00, 0x00, 0x00, 0x00]), 0, 0),
    "测试模式:HPLC物理层透传测试模式(3)",
)

_check_fragment(
    "协议10 检测扩展命令 安全测试模式13",
    10,
    _parse_comm_test(bytes([0x41, 0xD0, 0x00, 0x00, 0x02, 0x00]), 0, 0),
    "测试模式:安全测试模式(13) | 安全测试模式:SM3算法测试",
)

_check_fragment(
    "协议10 检测扩展命令 新一代测试模式15",
    10,
    _parse_comm_test(bytes.fromhex("01F01600000001"), 0, 0),
    "测试模式:新一代扩展测试模式(15) | 新一代测试模式:CCO信标机制切换",
)

_check_fragment(
    "协议11 通信测试扩展（用户真实帧）",
    11,
    hdc10.parse_to_table(HDC_USER_FRAME),
    "测试模式:频段切换操作(6)",
)


print("\n── 非测试帧：不得出现测试模式片段 ──")

# 协议9 应用层确认帧
td9_confirm = csg.parse_to_table(bytes.fromhex("1101010000000001000100"), parse_level="app")
d9, w9, f9 = _pair(9, td9_confirm)
print(f"   协议9 确认帧 桌面: {d9}")
print(f"   协议9 确认帧 Web : {w9}")
check("协议9 确认帧：共享片段为空", f9 == "", repr(f9))
check("协议9 确认帧：桌面摘要无「测试模式」", "测试模式" not in d9, d9)
check("协议9 确认帧：Web 摘要无「测试模式」", "测试模式" not in w9, w9)

# 协议10 普通通信测试（测试模式=0）
td10_plain = _parse_comm_test(bytes([0x41, 0x00, 0x00, 0x08]), 0, 0)
d10, w10, f10 = _pair(10, td10_plain)
print(f"   协议10 模式0 桌面: {d10}")
print(f"   协议10 模式0 Web : {w10}")
check("协议10 普通通信测试：共享片段为空", f10 == "", repr(f10))
check("协议10 普通通信测试：桌面摘要无「测试模式」", "测试模式" not in d10, d10)
check("协议10 普通通信测试：Web 摘要无「测试模式」", "测试模式" not in w10, w10)


print("\n── 单一来源守卫 ──")

td_mode = csg.parse_to_table(_app_frame(0x4002, SDU_TEST_1_0), parse_level="app")
check(
    "桌面方法转发到 batch_core（同一结果）",
    host._extract_test_mode_content(td_mode)
    == batch_core.extract_test_mode_content(td_mode),
    "转发结果不一致",
)
check(
    "哨兵常量与 batch_core 同源",
    tuple(main_gui.MainWindow._TEST_MODE_SENTINELS)
    == tuple(batch_core.TEST_MODE_SENTINELS),
    f"{main_gui.MainWindow._TEST_MODE_SENTINELS}",
)

from pathlib import Path  # noqa: E402

root = Path(__file__).resolve().parent.parent
web_src = (root / "reflex_web" / "reflex_web" / "web_utils.py").read_text(encoding="utf-8")
gui_src = (root / "main_gui.py").read_text(encoding="utf-8")
check(
    "Web 侧 import batch_core 取片段",
    "from batch_core import" in web_src
    and "extract_test_mode_content" in web_src,
    "web_utils 未接入共享片段",
)
check(
    "桌面侧不再保留片段实现体（仅转发）",
    "_numeric(text: str)" not in gui_src,
    "main_gui 仍存在第二份实现",
)
# 全仓唯一实现：batch_core 之外不得再有同名函数定义
dupes = [
    p
    for p in root.glob("*.py")
    if p.name != "batch_core.py"
    and "def extract_test_mode_content" in p.read_text(encoding="utf-8")
]
check("全仓唯一实现（根目录模块）", not dupes, f"重复定义: {[p.name for p in dupes]}")



# ═══════════════════════════════════════════════════════════════
# R4：Web 查询页自定义 DI CRUD（与桌面同规则；落盘位置 = Web 解析器读的那一份）
# ═══════════════════════════════════════════════════════════════

print("\n═══ R4：Web 查询页自定义 DI 增删 ═══")

import asyncio  # noqa: E402
import tempfile  # noqa: E402

import app_paths  # noqa: E402
import custom_di_store  # noqa: E402
from reflex_web import lookup_utils  # noqa: E402


class _Sandbox:
    """把 custom_di_store 的落盘/读取路径沙箱到临时目录（不碰真实 custom_di.json）。

    `custom_di_store` 以 `app_paths.data_path(...)` **属性形式**调用，且
    `ProtocolFrameParser` 读 DI 也走 `custom_di_store.load_custom_di()`，
    所以 patch 这两个入口即可同时沙箱「写入」与「查询读取」。
    """

    def __init__(self):
        self.dir = tempfile.TemporaryDirectory(prefix="web_parity_di_")
        self.root = Path(self.dir.name)
        self._orig_data_path = app_paths.data_path
        self._orig_ensure = app_paths.ensure_data_file

    def __enter__(self):
        app_paths.data_path = lambda name: self.root / name
        app_paths.ensure_data_file = lambda name: self.root / name
        return self.root

    def __exit__(self, *exc):
        app_paths.data_path = self._orig_data_path
        app_paths.ensure_data_file = self._orig_ensure
        self.dir.cleanup()
        return False


def _state():
    import reflex_web.reflex_web as app

    return app.State(_reflex_internal_init=True)


with _Sandbox() as sandbox:
    st = _state()
    st.current_protocol = 0

    # ── 1. 新增：写入 → 查询立即能看到（★ 标记）──
    st.lookup_di3, st.lookup_di2, st.lookup_di1, st.lookup_di0 = "E8", "00", "08", "03"
    st.lookup_desc = "查询采集任务号"
    asyncio.run(st.add_custom_di())

    di_file = sandbox / custom_di_store.CUSTOM_DI_FILE
    check("新增后落盘到解析器读取的同一份 custom_di.json", di_file.exists(), str(di_file))
    saved = json.loads(di_file.read_text(encoding="utf-8")) if di_file.exists() else []
    check(
        "落盘条目内容正确",
        saved == [{"di3": 232, "di2": 0, "di1": 8, "di0": 3, "desc": "查询采集任务号"}],
        str(saved),
    )
    check("新增后表单已清空", st.lookup_di3 == "" and st.lookup_desc == "",
          f"{st.lookup_di3}/{st.lookup_desc}")
    check("新增后提示为成功文案",
          "添加自定义DI" in st.message and st.message_type == "success", st.message)

    rows = lookup_utils.get_lookup_data(0, "查询采集任务号")
    hit = next((r for r in rows if r.get("中文含义") == "查询采集任务号"), None)
    check("Web 查询能查到新增 DI", hit is not None, str(rows[:2]))
    check("新增 DI 带「自定义」★ 标记", bool(hit) and hit.get("自定义") == "★", str(hit))
    builtin = next(
        (r for r in lookup_utils.get_lookup_data(0, "添加任务") if r.get("中文含义") == "添加任务"),
        None,
    )
    check("内置 DI 无★标记", bool(builtin) and builtin.get("自定义") == "", str(builtin))

    # ── 2. 覆盖：同键再次添加 → 只改含义 ──
    st.lookup_di3, st.lookup_di2, st.lookup_di1, st.lookup_di0 = "E8", "00", "08", "03"
    st.lookup_desc = "改名后的含义"
    asyncio.run(st.add_custom_di())
    saved2 = json.loads(di_file.read_text(encoding="utf-8"))
    check(
        "同键再次添加 = 覆盖含义（条目数不变）",
        len(saved2) == 1 and saved2[0]["desc"] == "改名后的含义",
        str(saved2),
    )
    check("覆盖提示文案正确", "覆盖自定义DI" in st.message, st.message)

    # ── 3. 校验：非法 DI / 空含义 不落盘 ──
    st.lookup_di3, st.lookup_di2, st.lookup_di1, st.lookup_di0 = "GG", "00", "08", "03"
    st.lookup_desc = "非法"
    asyncio.run(st.add_custom_di())
    check("非法 DI 被拒（提示 + 不落盘）",
          st.message_type == "error" and "十六进制" in st.message
          and len(json.loads(di_file.read_text(encoding="utf-8"))) == 1,
          st.message)
    st.lookup_di3, st.lookup_di2, st.lookup_di1, st.lookup_di0 = "E8", "00", "08", "04"
    st.lookup_desc = "   "
    asyncio.run(st.add_custom_di())
    check("空含义被拒", st.message_type == "error" and "中文含义" in st.message, st.message)
    check("被拒后未新增条目", len(json.loads(di_file.read_text(encoding="utf-8"))) == 1)

    # ── 4. 删除：自定义可删、内置拒删 ──
    asyncio.run(st.delete_custom_di("E8", "00", "08", "03"))
    check("自定义 DI 删除成功", json.loads(di_file.read_text(encoding="utf-8")) == [], st.message)
    check("删除后查询不再命中", not any(
        r.get("中文含义") == "改名后的含义"
        for r in lookup_utils.get_lookup_data(0, "改名后的含义")))

    asyncio.run(st.delete_custom_di("E8", "00", "02", "01"))
    check("内置 DI 拒删（提示可读）",
          st.message_type == "error" and "内置DI" in st.message, st.message)
    check("内置拒删后文件仍为空", json.loads(di_file.read_text(encoding="utf-8")) == [])

    # ── 5. 路径注入：显式 path 可写别处，不影响默认位置 ──
    other = sandbox / "elsewhere.json"
    custom_di_store.save_custom_di(
        [{"di3": 1, "di2": 2, "di1": 3, "di0": 4, "desc": "x"}], path=other)
    check("save_custom_di(path=...) 写入指定文件", other.exists())
    check("load_custom_di(path=...) 读回指定文件",
          custom_di_store.load_custom_di(path=other)[0]["desc"] == "x")
    check("显式 path 不影响默认位置",
          json.loads(di_file.read_text(encoding="utf-8")) == [],
          di_file.read_text(encoding="utf-8"))
    check("custom_key_set(path=...) 透传",
          custom_di_store.custom_key_set(path=other) == {(1, 2, 3, 4)})



# ── R4b：多选批量删除（协议0 DI）+ 国网 AFN+Fn CRUD（协议7）──

print("\n── R4b：多选批量删除 + 国网 AFN+Fn 增删 ──")

import gdw10376_parser  # noqa: E402
import gdw_afn_lookup  # noqa: E402
import parser_registry  # noqa: E402


class _AfnSandbox:
    """把国网自定义 AFN 的落盘/读取路径沙箱到临时目录。

    `gdw10376_parser` 是 `from app_paths import data_path`（直接绑名），所以必须
    patch 它自己模块里的 `data_path`；同时清掉 `parser_registry` 的 gdw 单例与
    `gdw_afn_lookup` 的查询缓存，避免复用旧路径/旧数据。
    """

    def __init__(self):
        self.dir = tempfile.TemporaryDirectory(prefix="web_parity_afn_")
        self.root = Path(self.dir.name)
        self._orig = gdw10376_parser.data_path

    def __enter__(self):
        gdw10376_parser.data_path = lambda name: self.root / name
        parser_registry._INSTANCES.pop("gdw", None)
        gdw_afn_lookup._LOOKUP_INSTANCE = None
        return self.root

    def __exit__(self, *exc):
        gdw10376_parser.data_path = self._orig
        parser_registry._INSTANCES.pop("gdw", None)
        gdw_afn_lookup._LOOKUP_INSTANCE = None
        self.dir.cleanup()
        return False


with _Sandbox() as di_sandbox, _AfnSandbox() as afn_sandbox:
    st = _state()
    st.current_protocol = 0

    # 多选批量删除：两条自定义 + 一条内置（内置应被忽略并计数）
    custom_di_store.save_custom_di([
        {"di3": 232, "di2": 0, "di1": 8, "di0": 3, "desc": "A"},
        {"di3": 234, "di2": 3, "di1": 3, "di0": 32, "desc": "B"},
    ])
    asyncio.run(st.do_lookup())
    st.toggle_lookup_selection("E8 00 08 03", True)
    st.toggle_lookup_selection("EA 03 03 20", True)
    st.toggle_lookup_selection("E8 00 02 01", True)   # 内置（添加任务）
    check("勾选 3 行（含 1 条内置）", len(st.lookup_selected) == 3, str(st.lookup_selected))
    st.toggle_lookup_selection("E8 00 08 03", False)
    check("取消勾选生效", len(st.lookup_selected) == 2, str(st.lookup_selected))
    st.toggle_lookup_selection("E8 00 08 03", True)

    asyncio.run(st.delete_selected_custom())
    remaining = json.loads(
        (di_sandbox / custom_di_store.CUSTOM_DI_FILE).read_text(encoding="utf-8"))
    check("批量删除清掉两条自定义", remaining == [], str(remaining))
    check("内置条目被忽略并计数", "2 条自定义DI" in st.message and "1 条内置DI已忽略" in st.message,
          st.message)
    check("批量删除后勾选清空", st.lookup_selected == [], str(st.lookup_selected))

    # 空勾选提示
    asyncio.run(st.delete_selected_custom())
    check("空勾选给出提示", st.message_type == "error" and "勾选" in st.message, st.message)

    # 国网 AFN+Fn：新增 → 查询可见（★）→ 校验拒绝 → 批量删除
    st.current_protocol = 7
    st.lookup_afn, st.lookup_fn = "84", "9"   # 0x84 不在标准 FN_MAP 内
    st.lookup_fn_name, st.lookup_afn_name = "自定义功能九", "自定义类别"
    asyncio.run(st.add_custom_afn())
    afn_file = afn_sandbox / "gdw_custom_afn.json"
    check("AFN 新增落盘", afn_file.exists(), str(afn_file))
    afn_saved = json.loads(afn_file.read_text(encoding="utf-8")) if afn_file.exists() else {}
    check("AFN 落盘 schema 正确（afn_map + fn_map）",
          afn_saved.get("afn_map", {}).get("84") == "自定义类别"
          and afn_saved.get("fn_map", {}).get("84", {}).get("9") == "自定义功能九",
          str(afn_saved))
    check("AFN 新增后表单清空",
          st.lookup_afn == "" and st.lookup_fn == "" and st.lookup_fn_name == "",
          f"{st.lookup_afn}/{st.lookup_fn}/{st.lookup_fn_name}")

    rows = lookup_utils.get_lookup_data(7, "自定义功能九")
    hit = next((r for r in rows if r.get("功能说明") == "自定义功能九"), None)
    check("Web 查询能查到新增 AFN+Fn", hit is not None, str(rows[:2]))
    check("新增 AFN+Fn 带★标记", bool(hit) and hit.get("自定义") == "★", str(hit))
    std_row = next(
        (r for r in lookup_utils.get_lookup_data(7, "") if r.get("自定义") == ""), None)
    check("标准 AFN+Fn 无★标记", std_row is not None, str(rows[:1]))

    st.lookup_afn, st.lookup_fn = "ZZ", "9"
    st.lookup_fn_name = "非法AFN"
    asyncio.run(st.add_custom_afn())
    check("非法 AFN 被拒", st.message_type == "error" and "十六进制" in st.message, st.message)
    st.lookup_afn, st.lookup_fn = "84", "0"
    asyncio.run(st.add_custom_afn())
    check("Fn 越界被拒", st.message_type == "error" and "1-248" in st.message, st.message)
    st.lookup_afn, st.lookup_fn = "84", "9"
    st.lookup_fn_name = "   "
    asyncio.run(st.add_custom_afn())
    check("功能名称为空被拒", st.message_type == "error" and "功能名称" in st.message, st.message)
    std_pair = std_row
    st.lookup_afn = std_pair["AFN"]
    st.lookup_fn = std_pair["Fn"].lstrip("F")
    st.lookup_fn_name = "重复标准"
    asyncio.run(st.add_custom_afn())
    check("与标准定义重名被拒",
          st.message_type == "error" and "已在标准定义中存在" in st.message, st.message)

    # 批量删除：勾自定义 + 标准各一条
    asyncio.run(st.do_lookup())
    st.toggle_lookup_selection("84HF9", True)
    st.toggle_lookup_selection(std_pair["AFN"] + std_pair["Fn"], True)
    asyncio.run(st.delete_selected_custom())
    afn_after = json.loads(afn_file.read_text(encoding="utf-8"))
    check("AFN 批量删除清掉自定义组合",
          afn_after.get("fn_map", {}).get("84", {}) == {}, str(afn_after))
    check("标准条目被忽略并计数",
          "1 条自定义AFN+Fn组合" in st.message and "1 条标准定义已忽略" in st.message, st.message)
    check("AFN 删除后查询不再命中", not any(
        r.get("功能说明") == "自定义功能九" for r in lookup_utils.get_lookup_data(7, "自定义功能九")))

    # 行键解析（勾选键与解析函数同源）
    check("parse_gdw_row_key('03HF9') == (3, 9)",
          lookup_utils.parse_gdw_row_key("03HF9") == (3, 9))
    check("parse_di_row_key('E8 00 08 03') == (232, 0, 8, 3)",
          lookup_utils.parse_di_row_key("E8 00 08 03") == (232, 0, 8, 3))
    check("非法行键返回 None",
          lookup_utils.parse_gdw_row_key("zzz") is None
          and lookup_utils.parse_di_row_key("E8 00") is None)
print(f"\n═══ 结果: {passed} 通过, {failed} 失败 ═══")
sys.exit(1 if failed else 0)
