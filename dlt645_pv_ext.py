# -*- coding: utf-8 -*-
"""光伏协议转换单元 DL/T 645-2007 扩展协议解析（纯逻辑，无 Qt）

依据文档（唯一规范来源，随库版本化）：
    `协议文档/6.645协议/附件1：协议转换单元【低压分布式光伏协议转换单元】-技术规范书0625.md`
    - `# 协议转换单元DL/T 645-2007扩展协议` §D.1
        （一）变量类（02E6xxxx）/（二）参数类（04E6xxxx）/（三）事件类（03E6xxxx）三张表
    - 附录 I.3.3.1：扩展控制码 0FH（主站请求）/ 8FH（从站应答）无线转发透传帧，
      数据域 = 数据标识(4B) + 数据(N)，L = 04H + N

对外契约（与 `lme_info_entry_parser.parse_lme_dlt645` **完全一致**）：
    parse_pv_di(di_code, ctrl, data) -> (rows | None, 业务名)
    rows 行格式 = (字段, 原始值hex, 解析值, 说明)
    data = 减 0x33 后的完整数据域（含前 4 字节 DI，小端）

DI 表单一来源（R5）：
    本模块 `PV_DI_MAP` 是扩展协议 DI 的**唯一定义处**；
    `dlt645_parser._load_di_map` / `dlt645_di_lookup`（桌面查询页 + Reflex Web 查询页）
    均经 `merge_pv_di_map()` 合并。
    `dlt645_di.json` 是 `generate_dlt645_di.py` 的生成物（AGENTS.md §4.5 禁止手改），
    **不得**把扩展 DI 写进去。

字节切分权威（R2）：
    文档「数据长度（字节）」列是切分权威，该列把**每个值的字节数直接相连**
    （如 `222` = 三个值各 2 字节；全变量块 `222333444444442222` = 3×2B + 3×3B + 8×4B + 4×2B = 18 值）。
    「数据格式」列仅作显示提示（本模块按值拆成 fmt 令牌，逐值用于提示与校验）。

歧义行（R-1，按行内文字描述切分并标注存疑，不臆造字段）：
    - `04E60001`（长度 16「数量 M + 12 路通信地址」）：见 `_parse_addr_table` 注释
    - `04E621xx`（档案，长度列 `13221`）：见 `_PV_ARCHIVE_VALUES` 注释
    - `04E63002`（长度列 `23`）：见 `_PARAM_30_02` 注释
    - `03E61401/02/03/04`（`36464` / `366` / `36……6` / `366……66`）：见 `_parse_proto_unit_records` 注释

本模块为纯函数实现（R8）：不持有跨帧可变实例状态（AGENTS.md 陷阱 41）。
"""

from typing import Dict, List, Optional, Tuple

# 多字节 BCD（低字节在前）→ 数字串；含非 BCD nibble 返回 None。
# 复用 dlt645_data_codec 的同一实现（单一来源，勿在本模块另写一份）。
from dlt645_data_codec import _bcd_digits

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

GROUP_VARIABLE = "变量"
GROUP_PARAMETER = "参数"
GROUP_EVENT = "事件"

# 调控结果枚举（文档 §D.1（三））
RESULT_CODE = {
    0x00: "调控成功",
    0x01: "未调",
    0x02: "调控失败",
    0x03: "调控不支持",
    0x04: "其他问题",
}
# 开关机事件类型枚举（文档 §D.1（三）03E601xx）
ONOFF_TYPE = {0x00: "开机", 0x01: "关机"}
# 有功/无功功率控制事件类型枚举（文档 §D.1（三）03E603xx/03E605xx/03E609xx）
REG_TYPE = {0x00: "功率值调节", 0x01: "百分比调节"}
# 输出类型 / 运行状态枚举（文档 §D.1（二）04E603xx/04E604xx）
OUTPUT_TYPE = {0x00: "单相", 0x01: "三相"}
RUN_STATE = {0x00: "开机", 0x01: "关机"}

_FF_MISSING = "FF（无此项）"

# 逆变器逐字节位图（事件类型/调控结果块）的字节序说明，文档 §D.1（三）原文
INVERTER_BYTE_ORDER_NOTE = (
    "从左往右每个字节分别表示光伏逆变器12、11、…、2、1（文档 §D.1（三））"
)


def _phase_ff(phase: str) -> str:
    """单相设备的 B/C 相为 FF 时的标注（文档 §D.1（一）表下注）"""
    return f"FF（单相设备无{phase}相，文档 §D.1 表下注）"


def _v(name: str, nbytes: int, kind: str = "bcd", decimals: int = 0,
       unit: str = "", fmt: str = "", enum: Optional[dict] = None,
       ff: str = _FF_MISSING, doubt: str = "") -> dict:
    """单个值定义：值名 / 字节数 / 解码类型 / 小数位 / 单位 / 格式令牌 / 枚举 / 存疑说明"""
    return {"name": name, "nbytes": nbytes, "kind": kind, "decimals": decimals,
            "unit": unit, "fmt": fmt, "enum": dict(enum or {}), "ff": ff,
            "doubt": doubt}


# ---------------------------------------------------------------------------
# 各 DI1 的值定义（行模板共用）
# ---------------------------------------------------------------------------

_VOLT_3 = [
    _v("A相电压", 2, "bcd", 1, "V", "XXX.X"),
    _v("B相电压", 2, "bcd", 1, "V", "XXX.X", ff=_phase_ff("B")),
    _v("C相电压", 2, "bcd", 1, "V", "XXX.X", ff=_phase_ff("C")),
]
_CURR_3 = [
    _v("A相电流", 3, "bcd", 2, "A", "XXXX.XX"),
    _v("B相电流", 3, "bcd", 2, "A", "XXXX.XX", ff=_phase_ff("B")),
    _v("C相电流", 3, "bcd", 2, "A", "XXXX.XX", ff=_phase_ff("C")),
]
_P_ACT_4 = [
    _v("瞬时总有功功率", 4, "power", 4, "kW", "XXXX.XXXX"),
    _v("瞬时A有功功率", 4, "power", 4, "kW", "XXXX.XXXX"),
    _v("瞬时B有功功率", 4, "power", 4, "kW", "XXXX.XXXX", ff=_phase_ff("B")),
    _v("瞬时C有功功率", 4, "power", 4, "kW", "XXXX.XXXX", ff=_phase_ff("C")),
]
_P_REACT_4 = [
    _v("瞬时总无功功率", 4, "power", 4, "kvar", "XXXX.XXXX"),
    _v("瞬时A无功功率", 4, "power", 4, "kvar", "XXXX.XXXX"),
    _v("瞬时B无功功率", 4, "power", 4, "kvar", "XXXX.XXXX", ff=_phase_ff("B")),
    _v("瞬时C无功功率", 4, "power", 4, "kvar", "XXXX.XXXX", ff=_phase_ff("C")),
]
_PF_4 = [
    _v("总功率因数", 2, "bcd", 3, "", "X.XXX"),
    _v("A功率因数", 2, "bcd", 3, "", "X.XXX"),
    _v("B功率因数", 2, "bcd", 3, "", "X.XXX", ff=_phase_ff("B")),
    _v("C功率因数", 2, "bcd", 3, "", "X.XXX", ff=_phase_ff("C")),
]

# 04E621xx 光伏逆变器档案（长度列 `13221` = 5 段 1/3/2/2/1 共 9 字节）
# 文字描述只列 4 项（逆变器地址 / 逆变器品牌 / 逆变器规约版本 / 接入端口），
# 长度列却给 5 段 ⇒ 前 4 段按描述顺序归属（1B/3B/2B/2B），末 1 段无从归属，
# 以「保留」呈现并标注存疑（不臆造字段名）。
_PV_ARCHIVE_VALUES = [
    _v("逆变器地址", 1, "inv_addr", 0, "", "N", ff="FF（未接）"),
    _v("逆变器品牌", 3, "ascii", 0, "", "NNN"),
    _v("逆变器规约版本", 2, "bcd_raw", 0, "", "NN", doubt="文档未给版本编码方式，按 BCD 数字呈现"),
    _v("接入端口", 2, "port", 0, "", "NN",
       doubt="文档长度为 2 字节，端口枚举值只有 1/2/3（该行字节切分存疑）"),
    _v("保留", 1, "raw", 0, "", "N",
       doubt="长度列 5 段而文字描述 4 项，末段无从归属，按保留呈现"),
]

# 事件块中「光伏逆变器1..12 调控值」列表（文档 §D.1（三））
def _inv_values(nbytes: int, decimals: int, unit: str, fmt: str) -> List[dict]:
    return [_v(f"光伏逆变器{i}调控值", nbytes, "bcd", decimals, unit, fmt)
            for i in range(1, 13)]


_REG_CTRL_BLOCK = (
    [_v("发生时刻", 6, "time6", 0, "", "YYMMDDhhmmss"),
     _v("结束时刻", 6, "time6", 0, "", "YYMMDDhhmmss"),
     _v("事件类型", 1, "enum", 0, "", "NN", enum=REG_TYPE),
     _v("调控结果", 12, "per_inv", 0, "", "XX...XX", enum=RESULT_CODE)]
    + _inv_values(4, 4, "kW", "XXXX.XXXX")
)
_ONOFF_CTRL_BLOCK = [
    _v("发生时刻", 6, "time6", 0, "", "YYMMDDhhmmss"),
    _v("结束时刻", 6, "time6", 0, "", "YYMMDDhhmmss"),
    _v("事件类型", 12, "per_inv", 0, "", "XX...XX", enum=ONOFF_TYPE),
    _v("调控结果", 12, "per_inv", 0, "", "XX...XX", enum=RESULT_CODE),
]
_PF_CTRL_BLOCK = (
    [_v("发生时刻", 6, "time6", 0, "", "YYMMDDhhmmss"),
     _v("结束时刻", 6, "time6", 0, "", "YYMMDDhhmmss"),
     _v("调控结果", 12, "per_inv", 0, "", "XX...XX", enum=RESULT_CODE)]
    + _inv_values(2, 3, "", "X.XXX")
)
_VOLT_OVERRUN_BLOCK = [
    _v("发生时刻", 6, "time6", 0, "", "YYMMDDhhmmss"),
    _v("结束时刻", 6, "time6", 0, "", "YYMMDDhhmmss"),
    _v("越限A相电压", 2, "bcd", 1, "V", "XXX.X"),
    _v("越限B相电压", 2, "bcd", 1, "V", "XXX.X", ff=_phase_ff("B")),
    _v("越限C相电压", 2, "bcd", 1, "V", "XXX.X", ff=_phase_ff("C")),
    _v("恢复A相电压", 2, "bcd", 1, "V", "XXX.X"),
    _v("恢复B相电压", 2, "bcd", 1, "V", "XXX.X", ff=_phase_ff("B")),
    _v("恢复C相电压", 2, "bcd", 1, "V", "XXX.X", ff=_phase_ff("C")),
]
_COMM_ERR_BLOCK = [
    _v("发生时刻", 6, "time6", 0, "", "YYMMDDhhmmss"),
    _v("结束时刻", 6, "time6", 0, "", "YYMMDDhhmmss"),
    _v("逆变器号", 1, "inv_no", 0, "", "NN"),
]


def _total_count(name: str) -> List[dict]:
    """事件总次数（3 字节 BCD）"""
    return [_v(name, 3, "bcd", 0, "次", "XXXXXX")]


# ---------------------------------------------------------------------------
# DI0 变体生成器
# ---------------------------------------------------------------------------

def _di0_all_inv() -> List[Tuple[str, str]]:
    """01~0C = 逆变器 1~12，FF = 下挂所有光伏逆变器"""
    out = [(f"{i:02X}", f"光伏逆变器{i}") for i in range(1, 13)]
    out.append(("FF", "下挂所有光伏逆变器"))
    return out


def _di0_inv_1_12() -> List[Tuple[str, str]]:
    """01~0C = 逆变器 1~12（02E60Fxx 文档只列 02…0C，无 FF）"""
    return [(f"{i:02X}", f"光伏逆变器{i}") for i in range(1, 13)]


def _di0_seq_50() -> List[Tuple[str, str]]:
    """01~32 = 第 1~50 次记录（文档 §D.1（三）事件记录块）"""
    return [(f"{i:02X}", f"上{i}次") for i in range(1, 51)]


def _di0_fixed(code: str, label: str = "") -> List[Tuple[str, str]]:
    return [(code, label)]


# ---------------------------------------------------------------------------
# 行模板表（三张文档表的逐行登记）
# ---------------------------------------------------------------------------

def _row(group: str, di1: str, di0s, name_tpl: str, fmt_col: str, len_col: str,
         values: List[dict], di0_kind: str, unit: str = "", handler: str = "",
         note: str = "") -> dict:
    if not callable(di0s):
        di0s = (lambda _d=list(di0s): _d)
    return {"group": group, "di1": di1, "di0s": di0s, "name_tpl": name_tpl,
            "fmt_col": fmt_col, "len_col": len_col, "values": values,
            "di0_kind": di0_kind, "unit": unit, "handler": handler, "note": note}


_ROWS: List[dict] = [
    # ---------------- （一）变量类 02E6 ----------------
    _row(GROUP_VARIABLE, "01", _di0_all_inv, "{inv}的电压数据块",
         "XXX.XXXX.XXXX.X", "222", _VOLT_3, "inv"),
    _row(GROUP_VARIABLE, "02", _di0_all_inv, "{inv}的电流数据块",
         "XXXX.XXXXXX.XXXXXX.XX", "333", _CURR_3, "inv"),
    _row(GROUP_VARIABLE, "03", _di0_all_inv, "{inv}的瞬时有功功率数据块",
         "XXXX.XXXXXXXX.XXXXXXXX.XXXXXXXX.XXXX", "4444", _P_ACT_4, "inv"),
    _row(GROUP_VARIABLE, "04", _di0_all_inv, "{inv}的瞬时无功功率数据块",
         "XXXX.XXXXXXXX.XXXXXXXX.XXXXXXXX.XXXX", "4444", _P_REACT_4, "inv"),
    _row(GROUP_VARIABLE, "05", _di0_all_inv, "{inv}的功率因数数据块",
         "X.XXXX.XXXX.XXXX.XXX", "2222", _PF_4, "inv"),
    _row(GROUP_VARIABLE, "0F", _di0_inv_1_12, "{inv}所有变量的数据块",
         "XXX.XXXX.XXXX.XXXXX.XXXXXX.XXXXXX.XXXXXX.XXXXXXXX.XXXXXXXX.XXXXXXXX.XXXXXXXX"
         ".XXXXXXXX.XXXXXXXX.XXXXXXXX.XXXXX.XXXX.XXXX.XXXX.XXX",
         "222333444444442222",
         _VOLT_3 + _CURR_3 + _P_ACT_4 + _P_REACT_4 + _PF_4, "inv",
         note="文档该行 DI0 只列 02…0C（无 FF）"),

    # ---------------- （二）参数类 04E6 ----------------
    _row(GROUP_PARAMETER, "00", _di0_fixed("01"), "有效下挂光伏逆变器数量与通信地址表",
         "NNNNNNNNNNNNNNNNNNNNNNNNNN...NNNNNNNNNNNN", "16", [], "sub",
         handler="addr_table",
         note="长度列 16 字节与文字描述（数量 M + 12 路通信地址）字节切分存疑"),
    _row(GROUP_PARAMETER, "01", _di0_all_inv, "{inv}的额定有功功率", "XXXX.XXXX", "4",
         [_v("额定有功功率", 4, "bcd", 4, "kW", "XXXX.XXXX")], "inv"),
    _row(GROUP_PARAMETER, "02", _di0_all_inv, "{inv}的额定无功功率", "XXXX.XXXX", "4",
         [_v("额定无功功率", 4, "bcd", 4, "kvar", "XXXX.XXXX")], "inv"),
    _row(GROUP_PARAMETER, "03", _di0_all_inv, "{inv}的输出类型", "XX", "1",
         [_v("输出类型", 1, "enum", 0, "", "XX", enum=OUTPUT_TYPE)], "inv"),
    _row(GROUP_PARAMETER, "04", _di0_all_inv, "{inv}的运行状态", "NN", "1",
         [_v("运行状态", 1, "enum", 0, "", "NN", enum=RUN_STATE)], "inv"),
    _row(GROUP_PARAMETER, "05", _di0_all_inv, "{inv}的有功功率调节", "XXXX.XXXX", "4",
         [_v("有功功率调节", 4, "bcd", 4, "kW", "XXXX.XXXX")], "inv"),
    _row(GROUP_PARAMETER, "06", _di0_all_inv, "{inv}的无功功率调节", "XXXX.XXXX", "4",
         [_v("无功功率调节", 4, "bcd", 4, "kvar", "XXXX.XXXX")], "inv"),
    _row(GROUP_PARAMETER, "07", _di0_all_inv, "{inv}的功率因数调节", "X.XXX", "2",
         [_v("功率因数调节", 2, "bcd", 3, "", "X.XXX")], "inv"),
    _row(GROUP_PARAMETER, "08", _di0_all_inv, "{inv}的有功功率百分比调节", "XXX.X", "2",
         [_v("有功功率百分比调节", 2, "bcd", 1, "%", "XXX.X")], "inv"),
    _row(GROUP_PARAMETER, "09", _di0_all_inv, "{inv}的无功功率百分比调节", "XXX.X", "2",
         [_v("无功功率百分比调节", 2, "bcd", 1, "%", "XXX.X")], "inv"),
    _row(GROUP_PARAMETER, "0A", _di0_all_inv, "{inv}的日发电量", "XXXXXX.XX", "4",
         [_v("日发电量", 4, "bcd", 2, "kWh", "XXXXXX.XX")], "inv"),
    _row(GROUP_PARAMETER, "0B", _di0_all_inv, "{inv}的有功功率时段调节数据块",
         "Yyyymmdd-hhmmYyyymmdd-hhmmYyyymmdd-hhmmYyyymmdd-hhmmXXXX.XXXXXXXX.XXXX",
         "444444",
         [_v("第1次调节的开始时间", 4, "mmddhhmm", 0, "", "Yyyymmdd-hhmm"),
          _v("第1次调节的结束时间", 4, "mmddhhmm", 0, "", "Yyyymmdd-hhmm"),
          _v("第2次调节的开始时间", 4, "mmddhhmm", 0, "", "Yyyymmdd-hhmm"),
          _v("第2次调节的结束时间", 4, "mmddhhmm", 0, "", "Yyyymmdd-hhmm"),
          _v("第1次调控值", 4, "bcd", 4, "kW", "XXXX.XXXX",
             ff="FF（本时段不调节，文档备注）"),
          _v("第2次调控值", 4, "bcd", 4, "kW", "XXXX.XXXX",
             ff="FF（本时段不调节，文档备注）")], "inv",
         note="时间值按 4 字节 MMDDhhmm 解读（文档格式列写作 Yyyymmdd-hhmm，4 字节无法容纳年月日时分）",
         ),
    _row(GROUP_PARAMETER, "0C", _di0_all_inv, "{inv}的有功功率百分比时段调节数据块",
         "hhmmhhmmhhmmhhmmXXX.XXXX.X", "222222",
         [_v("第1次调节的开始时间", 2, "hhmm", 0, "", "hhmm"),
          _v("第1次调节的结束时间", 2, "hhmm", 0, "", "hhmm"),
          _v("第2次调节的开始时间", 2, "hhmm", 0, "", "hhmm"),
          _v("第2次调节的结束时间", 2, "hhmm", 0, "", "hhmm"),
          _v("第1次调控值", 2, "bcd", 1, "%", "XXX.X",
             ff="FF（本时段不调节，文档备注）"),
          _v("第2次调控值", 2, "bcd", 1, "%", "XXX.X",
             ff="FF（本时段不调节，文档备注）")], "inv"),
    _row(GROUP_PARAMETER, "21", _di0_fixed("00"), "光伏逆变器档案数", "NN", "1",
         [_v("档案数", 1, "bcd", 0, "", "NN")], "sub"),
    _row(GROUP_PARAMETER, "21", _di0_inv_1_12, "{inv}的档案",
         "NNNN…NNNNNNNN", "13221", _PV_ARCHIVE_VALUES, "inv",
         note="长度列 13221（5 段）与文字描述 4 项不一致，见字段注释"),
    _row(GROUP_PARAMETER, "30", _di0_fixed("01"), "光伏逆变器通信异常事件触发限值",
         "hhmmsshhmmssNNNN,NN", "3321",
         [_v("监测起始时间", 3, "time3", 0, "", "hhmmss"),
          _v("监测结束时间", 3, "time3", 0, "", "hhmmss"),
          _v("监测间隔", 2, "bcd", 0, "分", "NNNN"),
          _v("日发生最大次数", 1, "bcd", 0, "次", "NN")], "sub",
         note="格式列 NNNN,NN 的逗号为文档书写，按 2+1 字节切分"),
    _row(GROUP_PARAMETER, "30", _di0_fixed("02"), "电压越限事件触发限值",
         "NNN.NNNNNNN", "23",
         [_v("越限条件发生限值", 2, "bcd_raw", 0, "V", "NNN.NNN",
             doubt="格式列 NNN.NNN 为 6 位数字，与 2 字节（4 位 BCD）不符，未定小数位"),
          _v("越限条件判定持续时间", 3, "bcd_raw", 0, "秒", "NNNN",
             doubt="文字描述「FF不判断该限值」按 6 位 BCD 呈现，未定小数位")], "sub"),

    # ---------------- （三）事件类 03E6 ----------------
    _row(GROUP_EVENT, "00", _di0_all_inv, "{inv}的开关机控制事件总次数", "XXXXXX", "3",
         _total_count("开关机控制事件总次数"), "inv"),
    _row(GROUP_EVENT, "01", _di0_seq_50, "（{seq}）下挂所有光伏逆变器的开关机控制事件数据块",
         "YYMMDDhhmmssYYMMDDhhmmssXX...XXXX...XX", "661212", _ONOFF_CTRL_BLOCK, "seq"),
    _row(GROUP_EVENT, "02", _di0_all_inv, "{inv}的有功功率控制事件总次数", "XXXXXX", "3",
         _total_count("有功功率控制事件总次数"), "inv"),
    _row(GROUP_EVENT, "03", _di0_seq_50, "（{seq}）下挂所有光伏逆变器的有功功率控制事件数据块",
         "YYMMDDhhmmssYYMMDDhhmmssNNXX...XXXXXX.XXXXXXXX.XXXX...XXXX.XXXX",
         "6611244...4", _REG_CTRL_BLOCK, "seq", unit="kW/%"),
    _row(GROUP_EVENT, "04", _di0_all_inv, "{inv}的无功功率控制事件总次数", "XXXXXX", "3",
         _total_count("无功功率控制事件总次数"), "inv"),
    _row(GROUP_EVENT, "05", _di0_seq_50, "（{seq}）下挂所有光伏逆变器的无功功率控制事件数据块",
         "YYMMDDhhmmssYYMMDDhhmmssNNXX...XXXXXX.XXXXXXXX.XXXX...XXXX.XXXX",
         "6611244...4", _REG_CTRL_BLOCK, "seq", unit="kvar/%"),
    _row(GROUP_EVENT, "06", _di0_all_inv, "{inv}的功率因数控制事件总次数", "XXXXXX", "3",
         _total_count("功率因数控制事件总次数"), "inv"),
    _row(GROUP_EVENT, "07", _di0_seq_50, "（{seq}）下挂所有光伏逆变器的功率因数控制事件数据块",
         "YYMMDDhhmmssYYMMDDhhmmssXX...XXX.XXXX.XXX...X.XXX", "661222...2",
         _PF_CTRL_BLOCK, "seq"),
    _row(GROUP_EVENT, "08", _di0_all_inv, "{inv}的有功功率时段控制事件总次数", "XXXXXX", "3",
         _total_count("有功功率时段控制事件总次数"), "inv"),
    _row(GROUP_EVENT, "09", _di0_seq_50,
         "（{seq}）下挂所有光伏逆变器的有功功率时段控制事件数据块",
         "YYMMDDhhmmssYYMMDDhhmmssNNXX...XXXXXX.XXXXXXXX.XXXX...XXXX.XXXX",
         "6611244...4", _REG_CTRL_BLOCK, "seq", unit="kW/%"),
    _row(GROUP_EVENT, "11", _di0_fixed("00"), "电压越限事件总次数", "XXXXXX", "3",
         _total_count("电压越限事件总次数"), "sub"),
    _row(GROUP_EVENT, "11", _di0_seq_50, "（{seq}）电压越限事件记录",
         "YYMMDDhhmmssYYMMDDhhmmssXXX.XXXX.XXXX.XXXX.XXXX.XXXX.X", "66222222",
         _VOLT_OVERRUN_BLOCK, "seq"),
    _row(GROUP_EVENT, "12", _di0_all_inv, "{inv}的通信异常事件总次数", "XXXXXX", "3",
         _total_count("通信异常事件总次数"), "inv"),
    _row(GROUP_EVENT, "13", _di0_seq_50, "（{seq}）光伏逆变器的通信异常事件记录",
         "YYMMDDhhmmssYYMMDDhhmmssNN", "661", _COMM_ERR_BLOCK, "seq"),
    _row(GROUP_EVENT, "14", _di0_fixed("01"), "协议转换单元电压越线总次数与事件记录（上100次）",
         "XXXXXXYYMMDDhhmmssXXXXXX……YYMMDDhhmmssXXXXXX", "36464", [], "sub",
         handler="proto_records_volt",
         note="长度列 36464 = 总次数 3B + (发生时刻 6B + 电压数据 4B) 重复；实际按数据域长度动态切分"),
    _row(GROUP_EVENT, "14", _di0_fixed("02"), "协议转换单元事件清零总次数与记录（上100次）",
         "XXXXXXYYMMDDhhmmss……YYMMDDhhmmss", "366", [], "sub",
         handler="proto_records_clear",
         note="长度列 366 = 总次数 3B + 发生时刻 6B 重复"),
    _row(GROUP_EVENT, "14", _di0_fixed("03"), "协议转换单元软件在线升级总次数与记录（上100次）",
         "XXXXXXXXXXXXXXXXXX……XXXXXXXXXXXX", "36……6", [], "sub",
         handler="proto_records_upgrade",
         note="长度列 36……6 与格式列（18 个 X + 12 个 X）无法确定单条记录长度，按存疑呈现"),
    _row(GROUP_EVENT, "14", _di0_fixed("04"), "协议转换单元校时总次数与记录（上100次）",
         "XXXXXXYYMMDDhhmmssYYMMDDhhmmss……YYMMDDhhmmssYYMMDDhhmmss", "366……66", [], "sub",
         handler="proto_records_time_sync",
         note="长度列 366……66 = 总次数 3B + (校时前时刻 6B + 校时后时刻 6B) 重复"),
]

# 格式列无法按值唯一复原的行（用 … 省略重复段 / 逗号分隔归属不明 / 长度列与格式列不一致）。
# 这些行的 fmt 令牌不做「逐值拼接 == 文档格式列」断言（在 di-list.md 与测试中列出理由）。
FMT_JOIN_SKIP = {
    "04E60001": "长度列 16 与格式列 26N+…+12N 无法一致切分（歧义行）",
    "04E62101": "格式列 NNNN…NNNNNNNN 与长度列 13221 的 5 段不一致（歧义行）",
    "04E63001": "格式列 NNNN,NN 的逗号无法唯一归属到某个值",
    "04E63002": "格式列 NNN.NNNNNNN 的位数与长度列 23 不符（存疑行）",
    "03E61401": "格式列以 …… 省略重复记录（动态长度）",
    "03E61402": "格式列以 …… 省略重复记录（动态长度）",
    "03E61403": "格式列与长度列均无法确定单条记录长度（存疑行）",
    "03E61404": "格式列以 …… 省略重复记录（动态长度）",
}
for _di1 in ("03", "05", "09"):
    FMT_JOIN_SKIP[f"03E6{_di1}01"] = "格式列以 … 省略重复的 12 个调控值"
FMT_JOIN_SKIP["03E60701"] = "格式列以 … 省略重复的 12 个调控值"


# ---------------------------------------------------------------------------
# DI 表构建（单一来源）
# ---------------------------------------------------------------------------

def _di0_semantics(di0: str, kind: str) -> str:
    """DI0 语义（变量/参数类 = 逆变器序号；事件记录类 = 第 N 次）"""
    if kind == "inv":
        if di0 == "FF":
            return "DI0=FF：下挂所有光伏逆变器（文档 §D.1）"
        return f"DI0={di0}：光伏逆变器{int(di0, 16)}"
    if kind == "seq":
        return f"DI0={di0}：第 {int(di0, 16)} 次记录（0x32=50，文档 §D.1（三））"
    return f"DI0={di0}：子项标识（文档 §D.1 该行）"


_GROUP_PREFIX = {
    GROUP_VARIABLE: "02E6",
    GROUP_PARAMETER: "04E6",
    GROUP_EVENT: "03E6",
}


def _build_di_map() -> Dict[str, dict]:
    di_map: Dict[str, dict] = {}
    for row in _ROWS:
        values: List[dict] = row["values"]
        declared = sum(v["nbytes"] for v in values)
        if row["handler"] == "addr_table":
            declared = 16          # 长度列原文
        elif row["handler"] == "proto_records_volt":
            declared = 3           # 固定前缀（总次数），记录段动态
        elif row["handler"].startswith("proto_records_"):
            declared = 3
        unit = row["unit"] or "/".join(
            dict.fromkeys(v["unit"] for v in values if v["unit"]))
        # 数据格式列：单值行原文；多值行按值用 "|" 连接（保留文档逐值格式，且不让组帧
        # 误把整块拼串当成单值 BCD 掩码 —— dlt645_frame_schema.mask_shape 对含 "|" 的串
        # 返回 (0,0,0)，组帧回退裸字节填写）
        if len(values) <= 1:
            data_type = values[0]["fmt"] if values else ""
        else:
            data_type = "|".join(v["fmt"] for v in values)
        for di0, label in row["di0s"]():
            code = f"{_GROUP_PREFIX[row['group']]}{row['di1']}{di0}"
            if row["di0_kind"] == "seq":
                name = row["name_tpl"].format(seq=label)
            elif row["di0_kind"] == "inv":
                name = row["name_tpl"].format(inv=label)
            else:
                name = row["name_tpl"]
            di_map[code] = {
                "name": name,
                "unit": unit,
                "data_type": data_type,
                "length": declared,
                "group": row["group"],
                "di0": di0,
                "di0_kind": row["di0_kind"],
                "di0_desc": _di0_semantics(di0, row["di0_kind"]),
                "fmt_col": row["fmt_col"],
                "len_col": row["len_col"],
                "values": values,
                "handler": row["handler"],
                "note": row["note"],
            }
    return di_map


PV_DI_MAP: Dict[str, dict] = _build_di_map()

# 合并冲突记录：merge_pv_di_map 遇到已有键（既有 1099 条标准 DI / 自定义 DI）时记入
_merge_conflicts: List[str] = []


def merge_pv_di_map(base: Optional[dict]) -> dict:
    """把扩展 DI 表合并进 645 DI 映射（单源，供解析器与两端查询页共用）

    - 返回 base 的**浅拷贝**再并入 PV_DI_MAP（不修改入参）
    - 键冲突时**保留 base**（不覆盖既有的 645 标准 DI），冲突键记入 `_merge_conflicts`
    - 幂等：对同一入参重复调用结果相同
    """
    merged = dict(base or {})
    _merge_conflicts.clear()
    for code, info in PV_DI_MAP.items():
        if code in merged:
            _merge_conflicts.append(code)
            continue
        merged[code] = dict(info)
    return merged


def is_pv_di(di_code: str) -> bool:
    """是否光伏协议转换单元扩展 DI（8 位 HEX，小端解析后的文档写法）"""
    return str(di_code or "").upper() in PV_DI_MAP


# ---------------------------------------------------------------------------
# 数值解码
# ---------------------------------------------------------------------------

def _fmt_digits(digits: str, decimals: int) -> str:
    """BCD 数字串（高位在前）→ 带小数点文本；decimals<=0 表示整数"""
    digits = digits.lstrip("0") or "0"
    if decimals <= 0:
        return digits
    if len(digits) <= decimals:
        digits = digits.zfill(decimals + 1)
    int_part, frac_part = digits[:-decimals], digits[-decimals:]
    int_part = int_part.lstrip("0") or "0"
    return f"{int_part}.{frac_part}"


def _power_value(b: bytes) -> Tuple[Optional[str], str]:
    """4 字节有符号功率解码（最高位为符号位）

    依据文档 §D.1（一）02E603xx/02E604xx 备注：
      「最高比特用0/1表示正负，0为正表示逆变器发电，1为负表示逆变器用电。
        如最高X为0111，表示+7；X为1111，表示-7，瞬时有功功率取值范围[-7999.9999,7999.9999]。」
    ⇒ 最高半字节 = 符号位(bit3) + 3 位数值（0111=+7 / 1111=-7），
      因此最大值是 7999.9999 而不是 9999.9999（最高位只能取 0~7）。
      BCD 低字节在前 ⇒ 最高半字节位于**线序最后一字节**的高 4 位。
    返回 (解析文本, 说明)；无法按该规则解释时返回 (None, 原因)。
    """
    if len(b) != 4:
        return None, f"长度 {len(b)} 字节，非 4 字节功率值"
    be = b[::-1]
    top = be[0] >> 4
    sign = (top >> 3) & 1
    digit = top & 0x07
    nibbles = "".join(f"{x:02X}" for x in be)
    digits = f"{digit}" + nibbles[1:]
    if any(c not in "0123456789" for c in digits):
        return None, "含非 BCD 半字节，无法按符号位规则解码"
    text = _fmt_digits(digits, 4)
    note = ("最高位为符号位（0=发电/正、1=用电/负，范围 ±7999.9999，"
            "文档 §D.1（一）备注）")
    if digits.strip("0") == "":
        zero_note = note + "；符号位=1 但数值为 0" if sign else note
        return text, zero_note
    return ("-" if sign else "+") + text, note


def _time6_text(b: bytes) -> Optional[str]:
    """6 字节时刻（YYMMDDhhmmss，BCD 低字节在前）→ 可读时刻"""
    d = _bcd_digits(b)
    if not d or len(d) != 12:
        return None
    yy, mm, dd = d[0:2], d[2:4], d[4:6]
    hh, mi, ss = d[6:8], d[8:10], d[10:12]
    return f"20{yy}-{mm}-{dd} {hh}:{mi}:{ss}"


def _time3_text(b: bytes) -> Optional[str]:
    """3 字节时刻（hhmmss，BCD 低字节在前）"""
    d = _bcd_digits(b)
    if not d or len(d) != 6:
        return None
    return f"{d[0:2]}:{d[2:4]}:{d[4:6]}"


def _mmddhhmm_text(b: bytes) -> Optional[str]:
    """4 字节时刻（MMDDhhmm，BCD 低字节在前；DL/T645 同款 4 字节时间编码）"""
    d = _bcd_digits(b)
    if not d or len(d) != 8:
        return None
    return f"{d[0:2]}-{d[2:4]} {d[4:6]}:{d[6:8]}"


def _hhmm_text(b: bytes) -> Optional[str]:
    """2 字节时刻（hhmm，BCD 低字节在前）"""
    d = _bcd_digits(b)
    if not d or len(d) != 4:
        return None
    return f"{d[0:2]}:{d[2:4]}"


def _render_single(spec: dict, chunk: bytes) -> Tuple[str, str]:
    """单值解码 → (解析值文本, 说明)"""
    kind = spec["kind"]
    if not chunk:
        return "（数据不足）", "⚠ 数据不足"
    if all(x == 0xFF for x in chunk):
        return spec["ff"], "整字节 FF = 该项不存在（文档 §D.1）"
    if kind == "power":
        val, why = _power_value(chunk)
        if val is None:
            return chunk.hex().upper(), f"⚠ {why}；按裸 hex 呈现"
        return val, why
    if kind == "time6":
        val = _time6_text(chunk)
        return (val, "BCD 低字节在前（线序 ss mm hh DD MM YY）") if val else \
            (chunk.hex().upper(), "⚠ 非 BCD 或长度不符，按裸 hex 呈现")
    if kind == "time3":
        val = _time3_text(chunk)
        return (val, "BCD 低字节在前（线序 ss mm hh）") if val else \
            (chunk.hex().upper(), "⚠ 非 BCD 或长度不符，按裸 hex 呈现")
    if kind == "mmddhhmm":
        val = _mmddhhmm_text(chunk)
        if val:
            return val, ("BCD 低字节在前；文档格式列写作 Yyyymmdd-hhmm，"
                         "4 字节按 MMDDhhmm 解读（存疑）")
        return chunk.hex().upper(), "⚠ 非 BCD 或长度不符，按裸 hex 呈现"
    if kind == "hhmm":
        val = _hhmm_text(chunk)
        return (val, "BCD 低字节在前") if val else \
            (chunk.hex().upper(), "⚠ 非 BCD 或长度不符，按裸 hex 呈现")
    if kind == "enum":
        code = chunk[0]
        text = spec["enum"].get(code)
        if text:
            return f"{code:02X}（{text}）", f"枚举：{'、'.join(f'{k:02X}={v}' for k, v in spec['enum'].items())}"
        return f"{code:02X}", f"⚠ 未知枚举值（已定义：{'、'.join(f'{k:02X}={v}' for k, v in spec['enum'].items())}）"
    if kind == "inv_no":
        code = chunk[0]
        if 1 <= code <= 12:
            return f"{code:02X}（光伏逆变器{code}）", "01~0C 对应光伏逆变器 1~12"
        if code == 0xFF:
            return "FF（下挂所有光伏逆变器）", "FF = 下挂所有（文档 §D.1（三））"
        return f"{code:02X}", "⚠ 超出 01~0C / FF 范围"
    if kind == "inv_addr":
        code = chunk[0]
        if code == 0xFF:
            return "FF（未接）", "逆变器地址（Modbus 地址），FF = 未接（文档 §D.1（二））"
        return f"{code:02X}", "逆变器地址（Modbus 地址），FF = 未接（文档 §D.1（二））"
    if kind == "port":
        code = int.from_bytes(chunk, "little")
        text = {1: "端口1（RJ45-I）", 2: "端口2（RJ45-II）", 3: "端口3（RS485-II）"}.get(code)
        desc = "接入端口：1=端口1(RJ45-I)、2=端口2(RJ45-II)、3=端口3(RS485-II)（文档 §D.1（二））"
        if spec["doubt"]:
            desc += "；" + spec["doubt"]
        return (f"{code}（{text}）" if text else f"{code}", desc)
    if kind == "ascii":
        text = chunk.decode("ascii", errors="replace").replace("\x00", "").strip()
        return text or chunk.hex().upper(), "ASCII 编码（文档 §D.1（二）档案）"
    if kind == "raw":
        return chunk.hex().upper(), spec["doubt"] or "原始字节（无解码定义）"
    if kind == "bcd_raw":
        d = _bcd_digits(chunk)
        desc = "BCD 低字节在前"
        if spec["doubt"]:
            desc += "；⚠ " + spec["doubt"]
        return (d if d else chunk.hex().upper()), desc
    # 默认：BCD 数值（小数位来自文档数据格式列）
    d = _bcd_digits(chunk)
    if d is None:
        return chunk.hex().upper(), "⚠ 含非 BCD 半字节，按裸 hex 呈现"
    desc = f"BCD 低字节在前，格式 {spec['fmt']}（{spec['nbytes']} 字节）"
    if spec["doubt"]:
        desc += "；⚠ " + spec["doubt"]
    return _fmt_digits(d, spec["decimals"]), desc


def _render_values(specs: List[dict], body: bytes) -> List[Tuple[str, str, str, str]]:
    """按值定义（字节数为切分权威）逐值呈现；长度不符时尽力解析并标注"""
    rows: List[Tuple[str, str, str, str]] = []
    off = 0
    declared = sum(v["nbytes"] for v in specs)
    for spec in specs:
        n = spec["nbytes"]
        chunk = body[off:off + n]
        off += n
        if spec["kind"] == "per_inv":
            rows.extend(_render_per_inverter(spec, chunk, off - n))
            continue
        parsed, desc = _render_single(spec, chunk)
        rows.append(("  └ " + spec["name"], chunk.hex().upper() if chunk else "",
                     parsed, desc))
    if len(body) != declared:
        rows.append(("  └ ⚠ 数据长度不符", body.hex().upper(),
                     f"声明 {declared} 字节 / 实际 {len(body)} 字节",
                     "文档数据长度列与实际数据域长度不一致（已按实际内容尽力解析）"))
    return rows


def _render_per_inverter(spec: dict, chunk: bytes, base_off: int
                         ) -> List[Tuple[str, str, str, str]]:
    """逐逆变器字节位图（事件类型 / 调控结果）：从左往右 = 逆变器 12、11、…、1"""
    rows: List[Tuple[str, str, str, str]] = []
    enum = spec["enum"]
    enum_text = "、".join(f"{k:02X}={v}" for k, v in enum.items())
    rows.append(("  └ ※ " + spec["name"] + "字节序", chunk.hex().upper(),
                 INVERTER_BYTE_ORDER_NOTE,
                 f"{spec['name']}共 {len(chunk)} 字节（首字节对应逆变器 12）"))
    for i, code in enumerate(chunk):
        inv = 12 - i
        if inv < 1:
            label = f"  └ {spec['name']}（第{i + 1}字节·超出12路）"
        else:
            label = f"  └ {spec['name']}（逆变器{inv}）"
        if code == 0xFF:
            rows.append((label, "FF", spec["ff"] + "（文档 §D.1（三））",
                         f"偏移 +{base_off + i}；{enum_text}"))
            continue
        text = enum.get(code)
        rows.append((label, f"{code:02X}", text if text else f"⚠ 未知值 0x{code:02X}",
                     f"偏移 +{base_off + i}；枚举：{enum_text}"))
    return rows


# ---------------------------------------------------------------------------
# 歧义行的专用解码
# ---------------------------------------------------------------------------

def _parse_addr_table(info: dict, body: bytes) -> List[Tuple[str, str, str, str]]:
    """04E60001 有效下挂光伏逆变器数量 M + 12 路通信地址（长度列 16）

    切分依据（歧义行 R-1）：文档该行文字描述为「有效下挂光伏逆变器数量 M(M<=12)，
    光伏接入单元按顺序对应光伏接入单元逻辑地址（01、02、03...）光伏接入单元1的通信地址…
    光伏接入单元12的通信地址」，即 1 个数量 + **12 路**地址；长度列 16 字节。
    16 - 1（数量）- 12（12 路，各 1 字节）= 3 字节无从归属 ⇒ 按「保留」呈现并标注存疑，
    不做等其他切分、不臆造字段（每个候选切法的原始 hex 一并给出）。
    """
    rows: List[Tuple[str, str, str, str]] = []
    if not body:
        return [("  └ 数据单元", "", "无", "读请求无数据单元（应答应为 16 字节）")]
    m_raw = body[0:1]
    m_parsed, m_desc = _render_single(
        _v("有效下挂光伏逆变器数量 M", 1, "bcd", 0, "台", "NN"), m_raw)
    rows.append(("  └ 有效下挂光伏逆变器数量 M（M<=12）", m_raw.hex().upper(),
                 m_parsed, "文档 §D.1（二）04E60001：数量 + 12 路通信地址；" + m_desc))
    off = 1
    for i in range(1, 13):
        chunk = body[off:off + 1]
        off += 1
        if not chunk:
            rows.append((f"  └ 光伏接入单元{i}的通信地址", "", "（数据不足）", "⚠ 数据域不足 16 字节"))
            continue
        code = chunk[0]
        if code == 0xFF:
            rows.append((f"  └ 光伏接入单元{i}的通信地址", "FF",
                         "FF（无此项）", "整字节 FF = 该项不存在（文档 §D.1）"))
        else:
            rows.append((f"  └ 光伏接入单元{i}的通信地址", chunk.hex().upper(),
                         f"{code:02X}", "1 字节通信地址（切分存疑：文档未给地址编码方式）"))
    tail = body[off:]
    if tail:
        rows.append(("  └ 保留（存疑）", tail.hex().upper(), f"{len(tail)} 字节",
                     "⚠ 长度列声明 16 字节 = 数量 1B + 12 路地址 12B + 3B 无归属，"
                     "该 3 字节按保留呈现（文档未定义，不臆造字段）"))
    if len(body) != 16:
        rows.append(("  └ ⚠ 数据长度不符", body.hex().upper(),
                     f"声明 16 字节 / 实际 {len(body)} 字节",
                     "文档数据长度列与实际数据域长度不一致（已按实际内容尽力解析）"))
    return rows


def _parse_proto_unit_records(info: dict, body: bytes) -> List[Tuple[str, str, str, str]]:
    """03E614xx 协议转换单元自身记录（总次数 3B + 记录段）

    长度列（歧义行 R-1）与格式列共同给出：
      - 01 电压越线：`36464` → 总次数 3B + (发生时刻 6B + 电压数据 4B) 重复（文字描述「上100次」）
      - 02 事件清零：`366` / 格式列 XXXXXXYYMMDDhhmmss…… → 总次数 3B + 发生时刻 6B 重复
      - 03 软件升级：`36……6` 与格式列（18 个 X + 12 个 X）**无法确定单条记录长度**
                    ⇒ 只解总次数，其余保留原始 hex + 标注存疑（不臆造字段）
      - 04 校时：`366……66` → 总次数 3B + (校时前时刻 6B + 校时后时刻 6B) 重复
    记录条数按**实际数据域长度**动态切分（声明值仅 100 次上限参考）。
    """
    di0 = info.get("di0", "")
    rows: List[Tuple[str, str, str, str]] = []
    if not body:
        return [("  └ 数据单元", "", "无", "读请求无数据单元")]
    count_raw = body[0:3]
    count_text, count_desc = _render_single(
        _v("总次数", 3, "bcd", 0, "次", "XXXXXX"), count_raw)
    rows.append(("  └ 总次数", count_raw.hex().upper(), count_text, count_desc))
    rest = body[3:]
    if di0 == "03":
        rows.append(("  └ 升级记录数据段（存疑）", rest.hex().upper(),
                     f"{len(rest)} 字节",
                     "⚠ 长度列 `36……6` 与格式列（18 个 X + 12 个 X）无法一致切分，"
                     "无法确定单条记录长度（上 100 次升级后版本信息），按原始 hex 保留，不臆造字段"))
        return rows

    rec_specs = {
        "01": [_v("发生时刻", 6, "time6", 0, "", "YYMMDDhhmmss"),
               _v("电压数据", 4, "bcd_raw", 0, "", "XXXXXX",
                  doubt="文档未给该电压值的小数位/编码说明，按 BCD 数字呈现")],
        "02": [_v("事件清零的发生时刻", 6, "time6", 0, "", "YYMMDDhhmmss")],
        "04": [_v("校时前的时刻", 6, "time6", 0, "", "YYMMDDhhmmss"),
               _v("校时后的时刻", 6, "time6", 0, "", "YYMMDDhhmmss")],
    }[di0]
    rec_len = sum(v["nbytes"] for v in rec_specs)
    n_full = len(rest) // rec_len
    for idx in range(n_full):
        chunk = rest[idx * rec_len:(idx + 1) * rec_len]
        for spec in rec_specs:
            sub = chunk[:spec["nbytes"]]
            chunk = chunk[spec["nbytes"]:]
            parsed, desc = _render_single(spec, sub)
            rows.append((f"  └ （上{idx + 1}次）{spec['name']}", sub.hex().upper(),
                         parsed, desc))
    leftover = rest[n_full * rec_len:]
    if leftover:
        rows.append(("  └ ⚠ 记录段余数", leftover.hex().upper(),
                     f"{len(leftover)} 字节（不足 1 条记录 {rec_len} 字节）",
                     "按实际数据域长度切分后的余数，原样保留"))
    if n_full > 100:
        rows.append(("  └ ⚠ 记录条数超出文档上限", f"{n_full} 条",
                     f"文档为「上100次」，实际 {n_full} 条", "仅作提示，不截断"))
    return rows


_HANDLERS = {
    "addr_table": _parse_addr_table,
    "proto_records_volt": _parse_proto_unit_records,
    "proto_records_clear": _parse_proto_unit_records,
    "proto_records_upgrade": _parse_proto_unit_records,
    "proto_records_time_sync": _parse_proto_unit_records,
}


# ---------------------------------------------------------------------------
# 对外入口（契约与 parse_lme_dlt645 一致）
# ---------------------------------------------------------------------------

def parse_pv_di(di_code: str, ctrl: int, data: bytes
                ) -> Tuple[Optional[List[Tuple[str, str, str, str]]], str]:
    """光伏协议转换单元扩展 DI 解析总入口

    参数：
        di_code: 8 位 HEX DI 编码（小端解析后的文档写法，如 02E60101）
        ctrl: 控制码字节（D7=DIR 方向，D0~D4=功能码）
        data: 减 0x33 后的完整数据域（含 4 字节 DI）
    返回：
        (fields 行列表, 业务名)；非扩展 DI 返回 (None, "")
    """
    info = PV_DI_MAP.get(str(di_code or "").upper())
    if not info:
        return None, ""
    name = info["name"]
    dir_bit = (ctrl >> 7) & 1
    func = ctrl & 0x1F
    rows: List[Tuple[str, str, str, str]] = []
    rows.append(("  └ 数据块", "", name,
                 f"光伏协议转换单元 DL/T645-2007 扩展协议（{info['group']}类）；"
                 f"{info['di0_desc']}；数据长度列 {info['len_col']}，"
                 f"数据格式 {info['fmt_col']}"))
    if info["note"]:
        rows.append(("  └ ※ 切分依据", "", info["note"], "文档 §D.1 该行原文说明"))
    if len(data) < 4:
        rows.append(("  └ ⚠ 数据域不足", data.hex().upper(), f"{len(data)} 字节",
                     "数据域不足 4 字节（DI 本身），无法解析"))
        return rows, name

    body = data[4:]
    if dir_bit == 0 and func == 0x11:
        rows.append(("  └ 数据单元", "", "无（读请求）",
                     f"读数据请求无数据单元；应答应为 {info['len_col']} 列声明的数据块"))
        return rows, name
    if dir_bit == 0 and func == 0x14:
        # 写数据请求（DL/T645 §7.5）：DI + 密码 PA P0P1P2(4) + 操作者代码 C0~C3(4) + 数据
        if len(body) >= 8:
            rows.append(("  └ 密码与操作者代码",
                         body[0:8].hex().upper(),
                         f"PA={body[0]:02X}，密码={' '.join(f'{b:02X}' for b in body[1:4])}，"
                         f"操作者={' '.join(f'{b:02X}' for b in body[4:8])}",
                         "写数据请求：DI 之后 4 字节密码 + 4 字节操作者代码，其后为写入值"))
            body = body[8:]
        else:
            rows.append(("  └ ⚠ 数据域不足", body.hex().upper(),
                         f"{len(body)} 字节",
                         "写数据请求应含 4 字节密码 + 4 字节操作者代码"))
            return rows, name
        rows.append(("  └ ※ 写入方向", "", "按参数设置（写入值）呈现",
                     "控制码 DIR=0 + FUNC=14H（写数据请求）"))

    handler = _HANDLERS.get(info["handler"])
    if handler:
        rows.extend(handler(info, body))
    else:
        rows.extend(_render_values(info["values"], body))
    return rows, name


def di_summary() -> str:
    """DI 表规模摘要（测试/自检用）"""
    groups: Dict[str, int] = {}
    for info in PV_DI_MAP.values():
        groups[info["group"]] = groups.get(info["group"], 0) + 1
    return f"DI 总数 {len(PV_DI_MAP)}（" + "、".join(
        f"{k}类 {v}" for k, v in groups.items()) + ")"
