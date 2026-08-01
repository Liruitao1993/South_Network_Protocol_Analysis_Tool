# -*- coding: utf-8 -*-
"""南网协议解析工具 - Reflex Web 完整版

包含功能：
- 单帧解析
- 批量解析
- 协议组帧
- 报文对比
- 查询 (DI/AFN/OBIS/命令字)
"""
import reflex as rx
from typing import List, Dict, Any, Optional, Tuple
import sys
import re
import json
from pathlib import Path

# 添加项目根目录到路径
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


# ═══════════════════════════════════════════════════════════════
# 状态管理
# ═══════════════════════════════════════════════════════════════

class State(rx.State):
    """全局应用状态"""

    # ── 协议选择 ─────────────────────────────────────────────
    current_protocol: int = 0
    csg_parse_level: str = "auto"
    csg_strip_head: int = 0
    csg_strip_tail: int = 0
    gw_parse_level: str = "auto"
    gw_strip_head: int = 0
    gw_strip_tail: int = 0

    # ── 单帧解析 ─────────────────────────────────────────────
    frame_hex: str = ""
    parse_result: List[Dict[str, Any]] = []
    verify_result: str = ""

    # ── 批量解析 ─────────────────────────────────────────────
    batch_input: str = ""
    batch_results: List[Dict[str, Any]] = []
    batch_selected_idx: int = -1
    batch_detail_rows: List[Dict[str, Any]] = []
    batch_detail_hex: str = ""

    # ── 组帧 ─────────────────────────────────────────────────
    gen_di_key: str = ""
    gen_afn_fn: str = ""
    gen_dlt698_apdu: str = ""
    gen_dlt698_sub: str = ""
    gen_fields: Dict[str, str] = {}
    gen_field_schema: List[Dict[str, str]] = []
    gen_src_addr: str = "000000000000"
    gen_dst_addr: str = "000000000000"
    gen_seq: int = 0
    gen_dir: int = 0
    gen_prm: int = 1
    gen_result: str = ""
    gen_result_hex: str = ""
    gen_preview: str = ""
    # DI/AFN 选项列表
    di_options: List[Dict[str, str]] = []
    afn_fn_options: List[Dict[str, str]] = []
    dlt698_apdu_options: List[str] = []
    dlt698_sub_options: List[Dict[str, str]] = []
    # 国网信息域配置
    gen_gdw_info: Dict[str, str] = {
        "通信方式": "3",
        "路由标识": "0",
        "附属节点标识": "0",
        "通信模块标识": "1",
        "冲突检测": "0",
        "中继级别": "0",
        "纠错编码标识": "0",
        "信道标识": "0",
        "预计应答字节数": "0",
        "通信速率": "0",
        "速率单位标识": "0",
        "报文序列号": "0",
    }

    # ── 报文对比 ─────────────────────────────────────────────
    diff_left: str = ""
    diff_right: str = ""
    diff_ignore_checksum: bool = False
    diff_ignore_sequence: bool = False
    diff_only_diff: bool = False
    diff_byte_rows: List[Dict[str, Any]] = []   # 字节级对比行
    diff_field_rows: List[Dict[str, Any]] = []  # 字段级对比行
    diff_explanations: List[str] = []           # 差异说明
    diff_stats: Dict[str, Any] = {}             # 统计信息

    # ── 查询 ─────────────────────────────────────────────────
    lookup_query: str = ""
    lookup_results: List[Dict[str, Any]] = []
    lookup_columns: List[str] = ["DI3", "DI2", "DI1", "DI0", "AFN", "中文含义"]
    lookup_title: str = "DI 查询"

    # ── 通用 ─────────────────────────────────────────────────
    message: str = ""
    message_type: str = "info"
    is_loading: bool = False
    active_tab: str = "single"

    # 协议列表
    PROTOCOL_OPTIONS: List[Dict[str, str]] = [
        {"label": "南网协议 (Q/CSG1209021-2019)", "value": "0"},
        {"label": "PLC RF协议 (万胜海外 V1_04)", "value": "1"},
        {"label": "HDLC/国网DLMS (IEC 62056-46)", "value": "2"},
        {"label": "DLMS-APDU(国网)", "value": "3"},
        {"label": "DLMS Wrapper裸报文", "value": "4"},
        {"label": "DLMS-APDU裸报文", "value": "5"},
        {"label": "DLT645-2007 电表协议", "value": "6"},
        {"label": "国网协议 (Q/GDW 10376.2-2024)", "value": "7"},
        {"label": "698.45协议 (DL/T 698.45-2017)", "value": "8"},
        {"label": "新一代载波协议 (通感一体化)", "value": "9"},
        {"label": "国网新一代双模通信互联互通", "value": "10"},
    ]

    # ── 协议切换 ─────────────────────────────────────────────
    def set_protocol(self, value: str):
        """切换协议"""
        try:
            self.current_protocol = int(value)
        except ValueError:
            for opt in self.PROTOCOL_OPTIONS:
                if opt["label"] == value:
                    self.current_protocol = int(opt["value"])
                    return
            self.current_protocol = 0

    def set_csg_level(self, value: str):
        self.csg_parse_level = value

    def set_gw_level(self, value: str):
        self.gw_parse_level = value

    def set_csg_strip_head(self, value: str):
        try:
            self.csg_strip_head = int(value) if value else 0
        except ValueError:
            self.csg_strip_head = 0

    def set_csg_strip_tail(self, value: str):
        try:
            self.csg_strip_tail = int(value) if value else 0
        except ValueError:
            self.csg_strip_tail = 0

    def set_gw_strip_head(self, value: str):
        try:
            self.gw_strip_head = int(value) if value else 0
        except ValueError:
            self.gw_strip_head = 0

    def set_gw_strip_tail(self, value: str):
        try:
            self.gw_strip_tail = int(value) if value else 0
        except ValueError:
            self.gw_strip_tail = 0

    def set_strip_head(self, value: str):
        """根据当前协议分发到对应的剔除头部字节数 setter"""
        if self.current_protocol == 9:
            self.set_csg_strip_head(value)
        elif self.current_protocol == 10:
            self.set_gw_strip_head(value)

    def set_strip_tail(self, value: str):
        """根据当前协议分发到对应的剔除尾部字节数 setter"""
        if self.current_protocol == 9:
            self.set_csg_strip_tail(value)
        elif self.current_protocol == 10:
            self.set_gw_strip_tail(value)

    # ── 单帧解析 ─────────────────────────────────────────────
    def set_frame_hex(self, value: str):
        self.frame_hex = value

    def _get_parser(self):
        """获取解析器"""
        p = self.current_protocol
        if p == 0:
            from protocol_parser import ProtocolFrameParser
            return ProtocolFrameParser()
        elif p == 1:
            from plc_rf_parser import PLCRFProtocolParser
            return PLCRFProtocolParser()
        elif p in (2, 3, 4, 5):
            from hdlc_parser import HDLCParser
            return HDLCParser()
        elif p == 6:
            from dlt645_parser import DLT645Parser
            return DLT645Parser()
        elif p == 7:
            from gdw10376_parser import GDW10376Parser
            return GDW10376Parser()
        elif p == 8:
            from dl_t698_45_parser import DLT69845Parser
            return DLT69845Parser()
        elif p == 9:
            from csg_new_gen_parser import CSGNewGenParser
            return CSGNewGenParser()
        elif p == 10:
            from gw_new_gen_parser import GWNewGenParser
            return GWNewGenParser()
        else:
            from protocol_parser import ProtocolFrameParser
            return ProtocolFrameParser()

    def _get_validator(self):
        """获取校验器"""
        p = self.current_protocol
        try:
            from validator import (
                NWValidator, PLCRFValidator, HDLCValidator,
                DLT645Validator, GDWValidator, DLT69845Validator, CSGNewGenValidator,
            )
            from validator.gw_new_gen_validator import GWNewGenValidator
            validators = {
                0: NWValidator, 1: PLCRFValidator,
                2: HDLCValidator, 3: HDLCValidator, 4: HDLCValidator, 5: HDLCValidator,
                6: DLT645Validator, 7: GDWValidator, 8: DLT69845Validator, 9: CSGNewGenValidator,
                10: GWNewGenValidator,
            }
            return validators.get(p, NWValidator)()
        except ImportError:
            return None

    def _clean_hex(self, hex_str: str) -> bytes:
        """清洗并转换 hex 字符串"""
        cleaned = "".join(hex_str.split()).upper()
        if len(cleaned) % 2 != 0:
            cleaned = cleaned[:-1]
        if not cleaned:
            raise ValueError("报文为空")
        try:
            return bytes.fromhex(cleaned)
        except ValueError as e:
            raise ValueError(f"十六进制格式错误: {e}")

    def _apply_strip(self, frame_bytes: bytes) -> bytes:
        """应用新一代载波/国网新一代字节剔除"""
        if self.current_protocol == 9:
            head, tail = self.csg_strip_head, self.csg_strip_tail
        elif self.current_protocol == 10:
            head, tail = self.gw_strip_head, self.gw_strip_tail
        else:
            return frame_bytes
        if head <= 0 and tail <= 0:
            return frame_bytes
        total = len(frame_bytes)
        tail_end = total - tail if tail > 0 else total
        if head >= tail_end:
            raise ValueError(f"剔除字节数过多（前{head}+尾{tail}），超出总长{total}")
        return frame_bytes[head:tail_end]

    async def parse_frame(self):
        """解析单帧报文"""
        if not self.frame_hex.strip():
            self.message = "请输入十六进制报文"
            self.message_type = "warning"
            return

        self.is_loading = True
        self.message = ""
        self.verify_result = ""

        try:
            frame_bytes = self._clean_hex(self.frame_hex)
            frame_bytes = self._apply_strip(frame_bytes)

            parser = self._get_parser()

            # 新一代载波/国网新一代需要 parse_level
            if self.current_protocol == 9:
                result = parser.parse_to_table(frame_bytes, parse_level=self.csg_parse_level)
            elif self.current_protocol == 10:
                result = parser.parse_to_table(frame_bytes, parse_level=self.gw_parse_level)
            else:
                result = parser.parse_to_table(frame_bytes)

            # 转换结果
            self.parse_result = []
            for idx, row in enumerate(result):
                if len(row) >= 4:
                    field_name = str(row[0]) if row[0] else ""
                    # 判断子字段：字段名以空格开头（桌面版用空格缩进表示层级）
                    indent_level = 0
                    stripped = field_name.lstrip()
                    if stripped != field_name:
                        indent_level = (len(field_name) - len(stripped)) // 2
                        prefix = "　" * (indent_level - 1) + "└ " if indent_level > 0 else ""
                        display_field = prefix + stripped
                    else:
                        display_field = field_name

                    self.parse_result.append({
                        "id": idx,
                        "field": display_field,
                        "raw": str(row[1]) if row[1] else "",
                        "parsed": str(row[2]) if row[2] else "",
                        "comment": str(row[3]) if row[3] else "",
                        "is_child": indent_level > 0,
                        "indent": indent_level,
                    })

            self.message = f"解析成功，共 {len(self.parse_result)} 个字段"
            self.message_type = "success"

        except Exception as e:
            self.message = f"解析失败: {str(e)}"
            self.message_type = "error"
            import traceback
            traceback.print_exc()
        finally:
            self.is_loading = False

    async def verify_frame(self):
        """校验报文"""
        if not self.frame_hex.strip():
            self.message = "请输入报文"
            self.message_type = "warning"
            return

        self.is_loading = True
        try:
            frame_bytes = self._clean_hex(self.frame_hex)
            validator = self._get_validator()
            if validator is None:
                self.message = "当前协议不支持校验"
                self.message_type = "warning"
                return

            result = validator.verify(frame_bytes)
            lines = [f"[{'通过' if result.valid else '失败'}] {result.summary()}"]
            for check in result.checks:
                icon = "✅" if check.level.value == "pass" else "❌" if check.level.value == "fail" else "⚠️"
                lines.append(f"  {icon} {check.name}: 期望={check.expected}, 实际={check.actual} - {check.message}")
            if result.warnings:
                for w in result.warnings:
                    lines.append(f"  ⚠️ {w}")
            if result.errors:
                for e in result.errors:
                    lines.append(f"  ❌ {e}")

            self.verify_result = "\n".join(lines)
            self.message = result.summary()
            self.message_type = "success" if result.valid else "error"

        except Exception as e:
            self.message = f"校验出错: {str(e)}"
            self.message_type = "error"
        finally:
            self.is_loading = False

    def clear_input(self):
        """清空输入"""
        self.frame_hex = ""
        self.parse_result = []
        self.verify_result = ""
        self.message = ""

    # ── 批量解析 ─────────────────────────────────────────────
    def set_batch_input(self, value: str):
        self.batch_input = value

    async def parse_batch(self):
        """批量解析（支持帧提取、监控日志剥离）"""
        if not self.batch_input.strip():
            self.message = "请输入批量报文"
            self.message_type = "warning"
            return

        self.is_loading = True
        self.message = ""
        self.batch_results = []
        self.batch_detail_rows = []
        self.batch_detail_hex = ""
        self.batch_selected_idx = -1

        try:
            from .web_utils import (
                strip_csg_new_gen_prefix, strip_gw_new_gen_prefix,
                extract_frames_for_protocol, get_frame_summary,
                clean_hex_input,
            )
            import re

            # 步骤1：前缀剥离（协议9/10）
            input_text = self.batch_input
            if self.current_protocol == 9:
                input_text = strip_csg_new_gen_prefix(input_text, self.csg_parse_level)
            elif self.current_protocol == 10:
                input_text = strip_gw_new_gen_prefix(input_text, self.gw_parse_level)

            # 步骤1.5：全局 hex 清洗（对齐 GUI 的 _clean_hex_input(keep_newlines=True)）
            input_text = clean_hex_input(input_text, keep_newlines=True)

            # 步骤2：帧提取
            frame_hexes = extract_frames_for_protocol(input_text, self.current_protocol)
            if not frame_hexes:
                self.message = "未找到有效帧数据"
                self.message_type = "warning"
                self.is_loading = False
                return

            parser = self._get_parser()

            for idx, frame_hex in enumerate(frame_hexes):
                try:
                    clean = re.sub(r'[^0-9A-Fa-f]', '', frame_hex).upper()
                    if len(clean) % 2 != 0:
                        clean = clean[:-1]
                    frame_bytes = bytes.fromhex(clean)

                    # 按协议类型传解析级别
                    if self.current_protocol == 9:
                        result = parser.parse_to_table(frame_bytes, parse_level=self.csg_parse_level)
                    elif self.current_protocol == 10:
                        result = parser.parse_to_table(frame_bytes, parse_level=self.gw_parse_level)
                    else:
                        result = parser.parse_to_table(frame_bytes)

                    status = "成功" if result and (not result[0] or "❌" not in str(result[0][0])) else "失败"
                    proto_name = get_frame_summary(result, self.current_protocol)

                    self.batch_results.append({
                        "id": idx,
                        "frame_bytes": frame_bytes,
                        "result": result,
                        "status": status,
                        "proto": proto_name,
                        "summary": proto_name[:120],
                        "len": len(frame_bytes),
                    })
                except Exception as ex:
                    self.batch_results.append({
                        "id": idx,
                        "frame_bytes": b"",
                        "result": [],
                        "status": "错误",
                        "proto": "解析错误",
                        "summary": str(ex)[:100],
                        "len": 0,
                    })

            success_count = sum(1 for r in self.batch_results if r["status"] == "成功")
            fail_count = len(self.batch_results) - success_count
            self.message = f"批量解析完成 — 共 {len(self.batch_results)} 帧（✅ {success_count} 成功，❌ {fail_count} 失败）"
            self.message_type = "success" if fail_count == 0 else "warning"

        except Exception as e:
            self.message = f"批量解析失败: {str(e)}"
            self.message_type = "error"
            import traceback
            traceback.print_exc()
        finally:
            self.is_loading = False

    def select_batch_item(self, idx: int):
        """选择批量解析结果项，显示详细解析"""
        if idx < 0 or idx >= len(self.batch_results):
            return

        self.batch_selected_idx = idx
        item = self.batch_results[idx]
        result = item["result"]
        frame_bytes = item["frame_bytes"]

        # 显示原始帧 HEX
        if frame_bytes:
            self.batch_detail_hex = " ".join(f"{b:02X}" for b in frame_bytes)
        else:
            self.batch_detail_hex = ""

        # 填充详细解析表格
        self.batch_detail_rows = []
        for row in result:
            if len(row) >= 4:
                field = str(row[0]) if row[0] else ""
                raw = str(row[1]) if row[1] is not None else ""
                parsed = str(row[2]) if row[2] is not None else ""
                comment = str(row[3]) if row[3] is not None else ""
                is_child = row[6] if len(row) > 6 else False
                if is_child:
                    field = "  └ " + field
                self.batch_detail_rows.append({
                    "field": field,
                    "raw": raw,
                    "parsed": parsed,
                    "comment": comment,
                })

    def select_batch_by_index(self, index: int):
        """通过索引选择（用于 rx.foreach 回调）"""
        self.select_batch_item(index)

    def clear_batch(self):
        """清空批量解析"""
        self.batch_input = ""
        self.batch_results = []
        self.batch_selected_idx = -1
        self.batch_detail_rows = []
        self.batch_detail_hex = ""

    # ── 组帧 ─────────────────────────────────────────────────
    def set_gen_di_key(self, value: str):
        """设置 DI"""
        self.gen_di_key = value
        self.gen_fields = {}
        self._load_di_field_schema()
        self._update_gen_preview()

    def set_gen_afn_fn(self, value: str):
        """设置 AFN+Fn"""
        self.gen_afn_fn = value
        self.gen_fields = {}
        self._load_gdw_field_schema()
        self._update_gen_preview()

    def set_gen_dlt698_apdu(self, value: str):
        """设置 698.45 APDU 类型"""
        self.gen_dlt698_apdu = value
        self.gen_dlt698_sub = ""
        self.gen_fields = {}
        self._load_dlt698_sub_options()
        self._load_dlt698_field_schema()
        self._update_gen_preview()

    def set_gen_dlt698_sub(self, value: str):
        """设置 698.45 子选项"""
        self.gen_dlt698_sub = value
        self.gen_fields = {}
        self._load_dlt698_field_schema()
        self._update_gen_preview()

    def set_gen_field(self, key: str, value: str):
        """设置组帧字段"""
        self.gen_fields[key] = value
        self._update_gen_preview()

    def set_gen_src_addr(self, value: str):
        self.gen_src_addr = value
        self._update_gen_preview()

    def set_gen_dst_addr(self, value: str):
        self.gen_dst_addr = value
        self._update_gen_preview()

    def set_gen_seq(self, value: str):
        try:
            self.gen_seq = int(value) if value else 0
        except ValueError:
            self.gen_seq = 0
        self._update_gen_preview()

    def set_gen_dir(self, value: str):
        try:
            self.gen_dir = int(value) if value else 0
        except ValueError:
            self.gen_dir = 0
        self._update_gen_preview()

    def set_gen_prm(self, value: str):
        try:
            self.gen_prm = int(value) if value else 1
        except ValueError:
            self.gen_prm = 1
        self._update_gen_preview()

    def set_gen_gdw_info(self, key: str, value: str):
        """设置国网信息域字段"""
        self.gen_gdw_info[key] = value
        self._update_gen_preview()

    def _load_di_options(self):
        """加载 DI 选项"""
        try:
            from send_frame_lib import ProtocolFrameGenerator
            gen = ProtocolFrameGenerator()
            options = []
            for di_key in gen.get_supported_di_keys():
                di3, di2, di1, di0 = di_key
                key_hex = f"{di3:02X}{di2:02X}{di1:02X}{di0:02X}"
                schema = gen.get_di_schema(di_key)
                name = schema.get("name", key_hex) if schema else key_hex
                options.append({"label": f"{key_hex} - {name}", "value": key_hex})
            self.di_options = sorted(options, key=lambda x: x["value"])
        except Exception:
            self.di_options = []

    def _load_afn_fn_options(self):
        """加载 AFN+Fn 选项"""
        try:
            from gdw_send_frame_lib import GDWFrameGenerator
            gen = GDWFrameGenerator()
            options = []
            for afn, fn, name in gen.get_supported_afn_fn():
                key = f"{afn:02X}{fn:02X}"
                options.append({"label": f"{key} - {name}", "value": key})
            self.afn_fn_options = sorted(options, key=lambda x: x["value"])
        except Exception:
            self.afn_fn_options = []

    def _load_dlt698_options(self):
        """加载 698.45 APDU 类型选项"""
        try:
            from dl_t698_45_frame_schema import APDU_TYPE_LIST
            self.dlt698_apdu_options = [item[1] for item in APDU_TYPE_LIST]
        except ImportError:
            self.dlt698_apdu_options = []

    def _load_dlt698_sub_options(self):
        """加载 698.45 子选项"""
        if not self.gen_dlt698_apdu:
            self.dlt698_sub_options = []
            return
        try:
            from dl_t698_45_frame_schema import (
                GET_REQUEST_LIST, SET_REQUEST_LIST, ACTION_REQUEST_LIST,
            )
            sub_lists = {
                "GET-Request": GET_REQUEST_LIST,
                "SET-Request": SET_REQUEST_LIST,
                "ACTION-Request": ACTION_REQUEST_LIST,
            }
            sub_list = sub_lists.get(self.gen_dlt698_apdu, [])
            self.dlt698_sub_options = [{"label": name, "value": key} for key, name in sub_list]
        except ImportError:
            self.dlt698_sub_options = []

    def _load_di_field_schema(self):
        """加载南网 DI 字段 schema 到 gen_field_schema"""
        if not self.gen_di_key:
            self.gen_field_schema = []
            return
        try:
            from send_frame_lib import ProtocolFrameGenerator
            gen = ProtocolFrameGenerator()
            key = self.gen_di_key
            di_key = (int(key[0:2], 16), int(key[2:4], 16), int(key[4:6], 16), int(key[6:8], 16))
            schema = gen.get_di_schema(di_key)
            if schema and "fields" in schema:
                self.gen_field_schema = [
                    {
                        "name": f["name"],
                        "type": f.get("type", "uint8"),
                        "default": str(f.get("default", "")),
                        "desc": f.get("desc", ""),
                    }
                    for f in schema["fields"]
                ]
            else:
                self.gen_field_schema = []
        except Exception:
            self.gen_field_schema = []

    def _load_gdw_field_schema(self):
        """加载国网 AFN+Fn 字段 schema"""
        if not self.gen_afn_fn:
            self.gen_field_schema = []
            return
        try:
            from gdw_send_frame_lib import GDWFrameGenerator
            gen = GDWFrameGenerator()
            afn = int(self.gen_afn_fn[0:2], 16)
            fn = int(self.gen_afn_fn[2:4], 16)
            schema = gen.get_schema(afn, fn)
            if schema and "fields" in schema:
                self.gen_field_schema = [
                    {
                        "name": f["name"],
                        "type": f.get("type", "uint8"),
                        "default": str(f.get("default", "")),
                        "desc": f.get("desc", ""),
                    }
                    for f in schema["fields"]
                ]
            else:
                self.gen_field_schema = []
        except Exception:
            self.gen_field_schema = []

    def _load_dlt698_field_schema(self):
        """加载 698.45 字段 schema"""
        if not self.gen_dlt698_apdu or not self.gen_dlt698_sub:
            self.gen_field_schema = []
            return
        try:
            from dl_t698_45_frame_schema import DLT69845_FIELD_SCHEMA
            key = (self.gen_dlt698_apdu, self.gen_dlt698_sub)
            schema = DLT69845_FIELD_SCHEMA.get(key, {})
            fields = schema.get("fields", [])
            self.gen_field_schema = [
                {
                    "name": f["name"],
                    "type": f.get("type", "uint8"),
                    "default": str(f.get("default", "")),
                    "desc": f.get("desc", ""),
                }
                for f in fields
            ]
        except Exception:
            self.gen_field_schema = []

    def _parse_field_value(self, value: str, field_type: str):
        """将字符串值转换为对应类型"""
        field_type = field_type.lower()
        if field_type in ("uint8", "uint16", "uint32", "int"):
            try:
                if value.startswith("0x") or value.startswith("0X"):
                    return int(value, 16)
                return int(value)
            except (ValueError, TypeError):
                return 0
        elif field_type == "bytes":
            try:
                clean = "".join(value.split())
                return bytes.fromhex(clean) if clean else b""
            except ValueError:
                return b""
        elif field_type == "ascii":
            return value
        elif field_type == "bcd":
            return value
        elif field_type == "enum":
            try:
                return int(value)
            except (ValueError, TypeError):
                return 0
        elif field_type == "list":
            return []
        elif field_type == "oi":
            try:
                if value.startswith("0x") or value.startswith("0X"):
                    return int(value, 16)
                return int(value)
            except (ValueError, TypeError):
                return 0
        else:
            return value

    def _update_gen_preview(self):
        """更新组帧预览"""
        parts = []
        p = self.current_protocol
        if p == 0:  # 南网
            if self.gen_di_key:
                parts.append(f"DI: {self.gen_di_key}")
        elif p == 7:  # 国网
            if self.gen_afn_fn:
                parts.append(f"AFN+Fn: {self.gen_afn_fn}")
        elif p == 8:  # 698.45
            if self.gen_dlt698_apdu:
                parts.append(f"APDU: {self.gen_dlt698_apdu}")
            if self.gen_dlt698_sub:
                parts.append(f"子类型: {self.gen_dlt698_sub}")

        parts.append(f"源地址: {self.gen_src_addr}")
        parts.append(f"目的地址: {self.gen_dst_addr}")
        parts.append(f"序列号: {self.gen_seq}")
        parts.append(f"方向: {'下行' if self.gen_dir == 0 else '上行'}")
        parts.append(f"PRM: {self.gen_prm}")

        if self.gen_field_schema:
            parts.append(f"\n数据字段 ({len(self.gen_field_schema)}个):")
            for f in self.gen_field_schema:
                val = self.gen_fields.get(f["name"], f["default"])
                parts.append(f"  {f['name']}: {val}")

        self.gen_preview = "\n".join(parts) if parts else "请选择命令类型"

    async def generate_frame(self):
        """生成报文帧"""
        self.is_loading = True
        self.message = ""
        self.gen_result = ""
        self.gen_result_hex = ""

        try:
            p = self.current_protocol

            if p == 0:  # 南网
                if not self.gen_di_key:
                    self.message = "请先选择 DI"
                    self.message_type = "warning"
                    self.is_loading = False
                    return
                from send_frame_lib import ProtocolFrameGenerator
                gen = ProtocolFrameGenerator()
                key = self.gen_di_key
                di_key = (int(key[0:2], 16), int(key[2:4], 16), int(key[4:6], 16), int(key[6:8], 16))

                # 收集字段值
                field_values = {}
                schema = gen.get_di_schema(di_key)
                if schema and "fields" in schema:
                    for f in schema["fields"]:
                        name = f["name"]
                        str_val = self.gen_fields.get(name, str(f.get("default", "")))
                        field_values[name] = self._parse_field_value(str_val, f.get("type", "uint8"))

                src = bytes.fromhex(self.gen_src_addr) if self.gen_src_addr else b"\x00" * 6
                dst = bytes.fromhex(self.gen_dst_addr) if self.gen_dst_addr else b"\x00" * 6

                frame_bytes = gen.generate_frame(
                    di_key=di_key,
                    field_values=field_values,
                    src_addr=src,
                    dst_addr=dst,
                    dir_flag=self.gen_dir,
                    prm=self.gen_prm,
                    add_flag=1,
                )
                self.gen_result_hex = " ".join(f"{b:02X}" for b in frame_bytes)
                self.gen_result = f"生成成功！共 {len(frame_bytes)} 字节\n\n{self.gen_result_hex}"

            elif p == 7:  # 国网
                if not self.gen_afn_fn:
                    self.message = "请先选择 AFN+Fn"
                    self.message_type = "warning"
                    self.is_loading = False
                    return
                from gdw_send_frame_lib import GDWFrameGenerator
                gen = GDWFrameGenerator()
                afn = int(self.gen_afn_fn[0:2], 16)
                fn = int(self.gen_afn_fn[2:4], 16)

                # 收集字段值
                field_values = {}
                schema = gen.get_schema(afn, fn)
                if schema and "fields" in schema:
                    for f in schema["fields"]:
                        name = f["name"]
                        str_val = self.gen_fields.get(name, str(f.get("default", "")))
                        field_values[name] = self._parse_field_value(str_val, f.get("type", "uint8"))

                # 信息域配置
                info_config = {
                    "dir": self.gen_dir,
                    "prm": self.gen_prm,
                    "通信方式": int(self.gen_gdw_info.get("通信方式", "3")),
                    "路由标识": int(self.gen_gdw_info.get("路由标识", "0")),
                    "附属节点标识": int(self.gen_gdw_info.get("附属节点标识", "0")),
                    "通信模块标识": int(self.gen_gdw_info.get("通信模块标识", "1")),
                    "冲突检测": int(self.gen_gdw_info.get("冲突检测", "0")),
                    "中继级别": int(self.gen_gdw_info.get("中继级别", "0")),
                    "纠错编码标识": int(self.gen_gdw_info.get("纠错编码标识", "0")),
                    "信道标识": int(self.gen_gdw_info.get("信道标识", "0")),
                    "预计应答字节数": int(self.gen_gdw_info.get("预计应答字节数", "0")),
                    "通信速率": int(self.gen_gdw_info.get("通信速率", "0")),
                    "速率单位标识": int(self.gen_gdw_info.get("速率单位标识", "0")),
                    "报文序列号": int(self.gen_gdw_info.get("报文序列号", "0")),
                }

                frame_bytes = gen.generate_frame(
                    afn=afn,
                    fn=fn,
                    field_values=field_values,
                    info_config=info_config,
                    src_addr=self.gen_src_addr,
                    dst_addr=self.gen_dst_addr,
                )
                self.gen_result_hex = " ".join(f"{b:02X}" for b in frame_bytes)
                self.gen_result = f"生成成功！共 {len(frame_bytes)} 字节\n\n{self.gen_result_hex}"

            elif p == 8:  # 698.45
                if not self.gen_dlt698_apdu:
                    self.message = "请先选择 APDU 类型"
                    self.message_type = "warning"
                    self.is_loading = False
                    return
                from dl_t698_45_frame_gen import DLT69845FrameGenerator
                gen = DLT69845FrameGenerator()

                # 收集字段值
                from dl_t698_45_frame_schema import DLT69845_FIELD_SCHEMA
                schema_key = (self.gen_dlt698_apdu, self.gen_dlt698_sub or "get_normal")
                schema = DLT69845_FIELD_SCHEMA.get(schema_key, {})
                field_values = {}
                for f in schema.get("fields", []):
                    name = f["name"]
                    str_val = self.gen_fields.get(name, str(f.get("default", "")))
                    field_values[name] = self._parse_field_value(str_val, f.get("type", "uint8"))

                sa = bytes.fromhex(self.gen_src_addr) if self.gen_src_addr else bytes([0x01] * 7)
                ca = self.gen_seq & 0xFF

                frame_bytes = gen.generate_frame(
                    apdu_type=self.gen_dlt698_apdu,
                    sub_type=self.gen_dlt698_sub or "get_normal",
                    field_values=field_values,
                    sa=sa,
                    ca=ca,
                    dir_bit=self.gen_dir,
                    prm_bit=self.gen_prm,
                )
                self.gen_result_hex = " ".join(f"{b:02X}" for b in frame_bytes)
                self.gen_result = f"生成成功！共 {len(frame_bytes)} 字节\n\n{self.gen_result_hex}"

            else:
                self.gen_result = f"协议 {p} 暂不支持组帧"
                self.message_type = "warning"

            self.message = "组帧完成"
            self.message_type = "success"

        except Exception as e:
            self.message = f"组帧失败: {str(e)}"
            self.message_type = "error"
            import traceback
            traceback.print_exc()
        finally:
            self.is_loading = False

    def copy_gen_result(self):
        """复制组帧结果到剪贴板（Web 端由前端处理）"""
        if self.gen_result_hex:
            # 在 Reflex 中，复制可以通过 rx.set_clipboard 或前端 JS 实现
            pass

    # ── 报文对比 ─────────────────────────────────────────────
    def set_diff_left(self, value: str):
        self.diff_left = value

    def set_diff_right(self, value: str):
        self.diff_right = value

    def toggle_diff_ignore_checksum(self, value: bool):
        self.diff_ignore_checksum = value

    def toggle_diff_ignore_sequence(self, value: bool):
        self.diff_ignore_sequence = value

    def toggle_diff_only_diff(self, value: bool):
        self.diff_only_diff = value

    async def compare_frames(self):
        """对比两个报文（使用 FrameDiffEngine）"""
        if not self.diff_left.strip() or not self.diff_right.strip():
            self.message = "请输入两个报文进行对比"
            self.message_type = "warning"
            return

        self.is_loading = True
        self.message = ""
        self.diff_byte_rows = []
        self.diff_field_rows = []
        self.diff_explanations = []
        self.diff_stats = {}

        try:
            from frame_diff_engine import FrameDiffEngine

            # 获取当前协议的解析器
            parser = self._get_parser()
            engine = FrameDiffEngine(parser=parser)

            result = engine.compare(
                self.diff_left,
                self.diff_right,
                ignore_checksum=self.diff_ignore_checksum,
                ignore_sequence=self.diff_ignore_sequence,
            )

            if not result.get('success', False):
                self.message = f"对比失败: {result.get('error', '未知错误')}"
                self.message_type = "error"
                return

            # 字节级对比行（按字段分组）
            byte_rows = []
            for field_group in result.get('byte_diff', []):
                field_name = field_group.get('field_name', '')
                status = field_group.get('status', 'same')
                # 过滤：仅显示差异模式
                if self.diff_only_diff and status == 'same':
                    continue
                # 字段标题行
                byte_rows.append({
                    "is_field_header": True,
                    "field_name": field_name,
                    "status": status,
                    "offset": "",
                    "left": "",
                    "right": "",
                })
                # 逐字节行（每行 8 字节）
                details = field_group.get('byte_details', [])
                for i in range(0, len(details), 8):
                    chunk = details[i:i+8]
                    offset = chunk[0].get('offset', 0) if chunk else 0
                    left_hex = " ".join(
                        f"{d['byte_a']:02X}" if d.get('byte_a') is not None else "  "
                        for d in chunk
                    )
                    right_hex = " ".join(
                        f"{d['byte_b']:02X}" if d.get('byte_b') is not None else "  "
                        for d in chunk
                    )
                    row_status = "same"
                    if any(d.get('status') == 'modified' for d in chunk):
                        row_status = "modified"
                    elif any(d.get('status') == 'added' for d in chunk):
                        row_status = "added"
                    elif any(d.get('status') == 'removed' for d in chunk):
                        row_status = "removed"
                    byte_rows.append({
                        "is_field_header": False,
                        "field_name": "",
                        "status": row_status,
                        "offset": f"0x{offset:04X}",
                        "left": left_hex,
                        "right": right_hex,
                    })
            self.diff_byte_rows = byte_rows

            # 字段级对比行
            field_rows = []
            for f in result.get('field_diff', []):
                diff_type = f.get('diff_type', '相同')
                # 仅显示差异模式
                if self.diff_only_diff and diff_type == '相同':
                    continue
                field_rows.append({
                    "field_name": f.get('field_name', ''),
                    "offset_a": str(f.get('offset_a', -1)),
                    "offset_b": str(f.get('offset_b', -1)),
                    "offset_display": f"{f.get('offset_a', -1)}/{f.get('offset_b', -1)}",
                    "length_a": str(f.get('length_a', 0)),
                    "length_b": str(f.get('length_b', 0)),
                    "length_display": f"{f.get('length_a', 0)}/{f.get('length_b', 0)}",
                    "value_a": str(f.get('value_a', '')),
                    "value_b": str(f.get('value_b', '')),
                    "diff_type": diff_type,
                })
            self.diff_field_rows = field_rows

            # 差异说明
            self.diff_explanations = result.get('explanation', [])

            # 统计信息
            stats = result.get('stats', {})
            self.diff_stats = stats

            field_modified = stats.get('field_modified', 0)
            field_added = stats.get('field_added', 0)
            field_removed = stats.get('field_removed', 0)
            total = field_modified + field_added + field_removed
            if total == 0:
                self.message = "对比完成，两报文完全一致"
                self.message_type = "success"
            else:
                self.message = f"对比完成，{field_modified} 个字段修改，{field_added} 个新增，{field_removed} 个删除"
                self.message_type = "warning"

        except Exception as e:
            self.message = f"对比失败: {str(e)}"
            self.message_type = "error"
            import traceback
            traceback.print_exc()
        finally:
            self.is_loading = False

    def clear_diff(self):
        """清空对比"""
        self.diff_left = ""
        self.diff_right = ""
        self.diff_byte_rows = []
        self.diff_field_rows = []
        self.diff_explanations = []
        self.diff_stats = {}

    # ── 查询 ─────────────────────────────────────────────────
    def set_lookup_query(self, value: str):
        self.lookup_query = value

    async def do_lookup(self):
        """执行查询（根据当前协议自动选择查询类型）"""
        self.is_loading = True
        self.message = ""
        self.lookup_results = []

        try:
            from .lookup_utils import get_query_config, get_lookup_data

            config = get_query_config(self.current_protocol)
            self.lookup_title = config["title"]
            self.lookup_columns = config["columns"]

            results = get_lookup_data(self.current_protocol, self.lookup_query)
            self.lookup_results = results

            self.message = f"查询完成，共 {len(self.lookup_results)} 条结果"
            self.message_type = "success"

        except Exception as e:
            self.message = f"查询失败: {str(e)}"
            self.message_type = "error"
            import traceback
            traceback.print_exc()
        finally:
            self.is_loading = False

    def load_lookup_default(self):
        """加载默认查询数据（切换到查询页时自动加载）"""
        try:
            from .lookup_utils import get_query_config, get_lookup_data
            config = get_query_config(self.current_protocol)
            self.lookup_title = config["title"]
            self.lookup_columns = config["columns"]
            # 只加载前 100 条避免页面太大
            results = get_lookup_data(self.current_protocol, "")
            self.lookup_results = results[:100]
        except Exception as e:
            self.lookup_results = []
            self.lookup_title = "查询"
            self.lookup_columns = []

    # ── Tab 切换 ─────────────────────────────────────────────
    def set_tab(self, tab: str):
        """切换标签页"""
        self.active_tab = tab
        self.message = ""
        # 切换到组帧页面时加载选项
        if tab == "frame":
            self._load_di_options()
            self._load_afn_fn_options()
            self._load_dlt698_options()
        # 切换到查询页面时加载默认数据
        elif tab == "lookup":
            self.load_lookup_default()


# ═══════════════════════════════════════════════════════════════
# 组件定义
# ═══════════════════════════════════════════════════════════════

def header() -> rx.Component:
    """顶部导航栏"""
    return rx.box(
        rx.hstack(
            # Logo + 标题
            rx.hstack(
                rx.icon("zap", size=28, color="white"),
                rx.heading("南网协议解析工具", size="4", color="white", font_weight="bold"),
                spacing="2",
            ),
            rx.spacer(),
            # 协议选择器
            rx.el.select(
                rx.el.option("南网协议 (Q/CSG1209021-2019)", value="0"),
                rx.el.option("PLC RF协议 (万胜海外 V1_04)", value="1"),
                rx.el.option("HDLC/国网DLMS (IEC 62056-46)", value="2"),
                rx.el.option("DLMS-APDU(国网)", value="3"),
                rx.el.option("DLMS Wrapper裸报文", value="4"),
                rx.el.option("DLMS-APDU裸报文", value="5"),
                rx.el.option("DLT645-2007 电表协议", value="6"),
                rx.el.option("国网协议 (Q/GDW 10376.2-2024)", value="7"),
                rx.el.option("698.45协议 (DL/T 698.45-2017)", value="8"),
                rx.el.option("新一代载波协议 (通感一体化)", value="9"),
                rx.el.option("国网新一代双模通信互联互通", value="10"),
                default_value="0",
                on_change=State.set_protocol,
                width="280px",
                class_name="rounded-md border border-white/30 bg-white/10 px-3 py-2 text-sm text-white focus:border-white/50",
            ),
            # 版本徽章
            rx.badge("v1.8.2", color_scheme="indigo", variant="soft", size="2"),
            # 状态指示
            rx.hstack(
                rx.box(
                    width="8px",
                    height="8px",
                    border_radius="50%",
                    background="#22c55e",
                ),
                rx.text("就绪", size="1", color="white"),
                spacing="1",
            ),
            spacing="4",
            width="100%",
            padding_x="6",
            padding_y="3",
        ),
        background="linear-gradient(135deg, #1e40af 0%, #2563eb 50%, #3b82f6 100%)",
        box_shadow="0 2px 16px rgba(30, 64, 175, 0.25)",
        position="sticky",
        top="0",
        z_index="1000",
    )


def newgen_controls() -> rx.Component:
    """新一代载波/国网新一代控制条（协议9或10显示）"""
    return rx.cond(
        (State.current_protocol == 9) | (State.current_protocol == 10),
        rx.card(
            rx.hstack(
                rx.icon("tune", size=18, color="#2563eb"),
                rx.text("解析级别:", size="2", font_weight="medium"),
                # 南网新一代（协议9）解析级别
                rx.cond(
                    State.current_protocol == 9,
                    rx.el.select(
                        rx.el.option("自动识别", value="auto"),
                        rx.el.option("FC+PB解析(完整MPDU)", value="fc_pb"),
                        rx.el.option("FC+eFC解析", value="fc_efc"),
                        rx.el.option("仅FC解析", value="fc_only"),
                        rx.el.option("仅物理块PB", value="pb_only"),
                        rx.el.option("应用层报文", value="app"),
                        default_value="auto",
                        on_change=State.set_csg_level,
                        class_name="rounded border border-gray-300 px-2 py-1 text-sm",
                    ),
                ),
                # 国网新一代（协议10）解析级别
                rx.cond(
                    State.current_protocol == 10,
                    rx.el.select(
                        rx.el.option("自动识别", value="auto"),
                        rx.el.option("FC+PB解析(完整MPDU)", value="fc_pb"),
                        rx.el.option("仅FC解析", value="fc_only"),
                        rx.el.option("仅MAC帧", value="mac_only"),
                        rx.el.option("仅物理块PB", value="pb_only"),
                        rx.el.option("FC+MAC头", value="fc_mac"),
                        rx.el.option("应用层报文", value="app"),
                        default_value="auto",
                        on_change=State.set_gw_level,
                        class_name="rounded border border-gray-300 px-2 py-1 text-sm",
                    ),
                ),
                rx.divider(orientation="vertical", size="2"),
                rx.text("剔除前:", size="2"),
                rx.input(
                    type="number",
                    default_value="0",
                    on_change=State.set_strip_head,
                    width="70px",
                    size="1",
                ),
                rx.text("字节", size="1", color="gray"),
                rx.text("尾部:", size="2"),
                rx.input(
                    type="number",
                    default_value="0",
                    on_change=State.set_strip_tail,
                    width="70px",
                    size="1",
                ),
                rx.text("字节", size="1", color="gray"),
                spacing="3",
                align="center",
            ),
            padding="2",
            margin_bottom="2",
        ),
    )


def message_banner() -> rx.Component:
    """消息提示"""
    return rx.cond(
        State.message != "",
        rx.callout(
            State.message,
            icon=rx.cond(
                State.message_type == "success", "check_circle",
                rx.cond(State.message_type == "error", "x_circle",
                rx.cond(State.message_type == "warning", "alert_triangle", "info"))
            ),
            color_scheme=rx.cond(
                State.message_type == "success", "green",
                rx.cond(State.message_type == "error", "red",
                rx.cond(State.message_type == "warning", "amber", "blue"))
            ),
            size="1",
            width="100%",
            margin_bottom="3",
        ),
    )


# ═══════════════════════════════════════════════════════════════
# 单帧解析 Tab
# ═══════════════════════════════════════════════════════════════

def single_parse_tab() -> rx.Component:
    """单帧解析"""
    return rx.vstack(
        # 输入卡片
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("file_input", size=20, color="#2563eb"),
                    rx.heading("报文输入", size="3", font_weight="semibold"),
                    spacing="2",
                ),
                rx.text_area(
                    placeholder="请输入十六进制报文，如: 68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16",
                    value=State.frame_hex,
                    on_change=State.set_frame_hex,
                    height="80px",
                    width="100%",
                    font_family="monospace",
                    font_size="13px",
                ),
                rx.hstack(
                    rx.button(
                        rx.cond(State.is_loading, rx.spinner(size="1"), rx.icon("play", size=16)),
                        "解析报文",
                        on_click=State.parse_frame,
                        loading=State.is_loading,
                        color_scheme="blue",
                        size="2",
                    ),
                    rx.button(
                        rx.icon("shield_check", size=16),
                        "校验报文",
                        on_click=State.verify_frame,
                        variant="outline",
                        color_scheme="cyan",
                        size="2",
                    ),
                    rx.button(
                        rx.icon("eraser", size=16),
                        "清空",
                        on_click=State.clear_input,
                        variant="outline",
                        color_scheme="gray",
                        size="2",
                    ),
                    spacing="3",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
        # 结果区域（纵向布局：解析结果全宽在上，校验结果在下，充分利用 Web 纵向空间）
        rx.vstack(
            # 解析结果表格（全宽，无固定高度，自然纵向展开）
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("table", size=20, color="#2563eb"),
                        rx.heading("解析结果", size="3", font_weight="semibold"),
                        rx.spacer(),
                        rx.badge(f"{State.parse_result.length()} 条", color_scheme="blue", variant="soft"),
                        spacing="2",
                    ),
                    rx.cond(
                        State.parse_result.length() > 0,
                        rx.table.root(
                            rx.table.header(
                                rx.table.row(
                                    rx.table.column_header_cell("字段", width="30%"),
                                    rx.table.column_header_cell("原始值", width="20%"),
                                    rx.table.column_header_cell("解析值", width="20%"),
                                    rx.table.column_header_cell("说明", width="30%"),
                                )
                            ),
                            rx.table.body(
                                rx.foreach(
                                    State.parse_result,
                                    lambda row: rx.table.row(
                                        rx.table.cell(row["field"], font_weight="medium"),
                                        rx.table.cell(rx.code(row["raw"], variant="soft")),
                                        rx.table.cell(row["parsed"]),
                                        rx.table.cell(rx.text(row["comment"], size="1", color="gray")),
                                    )
                                )
                            ),
                            variant="surface",
                            size="1",
                            width="100%",
                        ),
                        rx.center(
                            rx.vstack(
                                rx.icon("inbox", size=48, color="#9ca3af"),
                                rx.text("暂无解析结果", color="#6b7280", size="2"),
                                spacing="2",
                                padding="8",
                            ),
                            width="100%",
                        ),
                    ),
                    spacing="3",
                    width="100%",
                ),
                width="100%",
            ),
            # 校验结果（全宽，放在解析结果下方，无固定高度）
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("check_circle", size=20, color="#059669"),
                        rx.heading("校验结果", size="3", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.cond(
                        State.verify_result != "",
                        rx.text(State.verify_result, font_family="monospace", font_size="12px", white_space="pre-wrap"),
                        rx.center(
                            rx.vstack(
                                rx.icon("shield", size=48, color="#9ca3af"),
                                rx.text("点击「校验报文」进行协议一致性校验", color="#6b7280", size="2"),
                                spacing="2",
                                padding="8",
                            ),
                            width="100%",
                        ),
                    ),
                    spacing="3",
                    width="100%",
                ),
                width="100%",
            ),
            spacing="4",
            width="100%",
        ),
        spacing="4",
        width="100%",
    )


# ═══════════════════════════════════════════════════════════════
# 批量解析 Tab
# ═══════════════════════════════════════════════════════════════

def batch_parse_tab() -> rx.Component:
    """批量解析"""
    return rx.vstack(
        # 输入卡片
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("list", size=20, color="#2563eb"),
                    rx.heading("批量报文输入", size="3", font_weight="semibold"),
                    rx.spacer(),
                    rx.text("(支持监控日志/纯HEX)", size="1", color="gray"),
                    spacing="2",
                ),
                rx.text_area(
                    placeholder="粘贴监控日志或十六进制报文，每行一帧",
                    value=State.batch_input,
                    on_change=State.set_batch_input,
                    height="120px",
                    width="100%",
                    font_family="monospace",
                    font_size="13px",
                ),
                rx.hstack(
                    rx.button(
                        rx.cond(State.is_loading, rx.spinner(size="1"), rx.icon("play", size=16)),
                        "批量解析",
                        on_click=State.parse_batch,
                        loading=State.is_loading,
                        color_scheme="blue",
                        size="2",
                    ),
                    rx.button(
                        rx.icon("eraser", size=16),
                        "清空",
                        on_click=State.clear_batch,
                        variant="outline",
                        color_scheme="gray",
                        size="2",
                    ),
                    rx.spacer(),
                    rx.text(f"共 {State.batch_results.length()} 帧", size="1", color="gray"),
                    spacing="3",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
        # 结果区域：左右分割
        rx.hstack(
            # 左侧：摘要列表
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("table", size=18, color="#2563eb"),
                        rx.heading("批量解析摘要", size="2", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.cond(
                        State.batch_results.length() > 0,
                        rx.scroll_area(
                            rx.vstack(
                                rx.foreach(
                                    State.batch_results,
                                    lambda item, idx: rx.card(
                                        rx.hstack(
                                            rx.badge(
                                                item["status"],
                                                color_scheme=rx.cond(item["status"] == "成功", "green",
                                                    rx.cond(item["status"] == "失败", "red", "amber")),
                                                variant="soft",
                                                size="1",
                                            ),
                                            rx.text("#" + (idx + 1).to_string(), size="1", font_weight="bold"),
                                            rx.text(item["len"].to_string() + "B", size="1", color="gray"),
                                            rx.text(item["proto"], size="1", font_weight="medium"),
                                            rx.spacer(),
                                            spacing="2",
                                            align="center",
                                        ),
                                        rx.text(item["summary"], size="1", color="gray", no_of_lines=2),
                                        padding="2",
                                        width="100%",
                                        cursor="pointer",
                                        _hover={"background": "rgba(37, 99, 235, 0.05)"},
                                        style=rx.cond(
                                            State.batch_selected_idx == item["id"],
                                            {"border": "2px solid #2563eb"},
                                            {},
                                        ),
                                        on_click=lambda: State.select_batch_by_index(idx),
                                    )
                                ),
                                spacing="1",
                                width="100%",
                            ),
                            height="400px",
                        ),
                        rx.center(
                            rx.vstack(
                                rx.icon("inbox", size=48, color="#9ca3af"),
                                rx.text("暂无批量解析结果", color="#6b7280", size="2"),
                                spacing="2",
                                padding="8",
                            ),
                            width="100%",
                        ),
                    ),
                    spacing="2",
                    width="100%",
                ),
                width="45%",
            ),
            # 右侧：详细解析
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("zoom_in", size=18, color="#2563eb"),
                        rx.heading("选中帧详细解析", size="2", font_weight="semibold"),
                        spacing="2",
                    ),
                    # 原始帧 HEX
                    rx.cond(
                        State.batch_detail_hex != "",
                        rx.box(
                            rx.text("原始帧:", size="1", font_weight="medium", color="gray"),
                            rx.code(State.batch_detail_hex, variant="soft", font_family="monospace", font_size="11px"),
                            padding="2",
                            background="rgba(37, 99, 235, 0.05)",
                            border_radius="6px",
                            width="100%",
                        ),
                    ),
                    # 详细解析表格
                    rx.cond(
                        State.batch_detail_rows.length() > 0,
                        rx.scroll_area(
                            rx.table.root(
                                rx.table.header(
                                    rx.table.row(
                                        rx.table.column_header_cell("字段", width="30%"),
                                        rx.table.column_header_cell("原始值", width="20%"),
                                        rx.table.column_header_cell("解析值", width="20%"),
                                        rx.table.column_header_cell("说明", width="30%"),
                                    )
                                ),
                                rx.table.body(
                                    rx.foreach(
                                        State.batch_detail_rows,
                                        lambda row: rx.table.row(
                                            rx.table.cell(row["field"], font_weight="medium", size="1"),
                                            rx.table.cell(rx.code(row["raw"], variant="soft"), size="1"),
                                            rx.table.cell(row["parsed"], size="1"),
                                            rx.table.cell(rx.text(row["comment"], size="1", color="gray")),
                                        )
                                    )
                                ),
                                variant="surface",
                                size="1",
                                width="100%",
                            ),
                            height="350px",
                        ),
                        rx.center(
                            rx.vstack(
                                rx.icon("mouse_pointer", size=48, color="#9ca3af"),
                                rx.text("点击左侧摘要行查看详细解析", color="#6b7280", size="2"),
                                spacing="2",
                                padding="8",
                            ),
                            width="100%",
                        ),
                    ),
                    spacing="2",
                    width="100%",
                ),
                width="55%",
            ),
            spacing="4",
            width="100%",
            align="start",
        ),
        spacing="4",
        width="100%",
    )


# ═══════════════════════════════════════════════════════════════
# 组帧 Tab
# ═══════════════════════════════════════════════════════════════

def frame_gen_tab() -> rx.Component:
    """协议组帧（南网/国网/698.45）"""

    # 动态字段表单
    def dynamic_fields() -> rx.Component:
        return rx.cond(
            State.gen_field_schema.length() > 0,
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("list_alt", size=18, color="#2563eb"),
                        rx.heading("数据字段", size="3", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.grid(
                        rx.foreach(
                            State.gen_field_schema,
                            lambda f: rx.vstack(
                                rx.hstack(
                                    rx.text(f["name"], size="1", font_weight="medium"),
                                    rx.badge(f["type"], variant="soft", size="1", color_scheme="gray"),
                                    spacing="1",
                                ),
                                rx.input(
                                    value=State.gen_fields[f["name"]].to(str),
                                    on_change=lambda val, name=f["name"]: State.set_gen_field(name, val),
                                    placeholder=f["default"],
                                    font_family="monospace",
                                    size="1",
                                ),
                                rx.text(f["desc"], size="1", color="gray"),
                                spacing="1",
                            ),
                        ),
                        columns="2",
                        spacing="3",
                        width="100%",
                    ),
                    spacing="3",
                    width="100%",
                ),
                width="100%",
            ),
        )

    # 国网信息域配置
    def gdw_info_panel() -> rx.Component:
        info_items = [
            ("通信方式", "3"),
            ("路由标识", "0"),
            ("附属节点标识", "0"),
            ("通信模块标识", "1"),
            ("冲突检测", "0"),
            ("中继级别", "0"),
            ("纠错编码标识", "0"),
            ("信道标识", "0"),
            ("预计应答字节数", "0"),
            ("通信速率", "0"),
            ("速率单位标识", "0"),
            ("报文序列号", "0"),
        ]
        return rx.cond(
            State.current_protocol == 7,
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("info", size=18, color="#2563eb"),
                        rx.heading("信息域配置", size="3", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.grid(
                        *[
                            rx.vstack(
                                rx.text(name, size="1", font_weight="medium"),
                                rx.input(
                                    value=State.gen_gdw_info[name].to(str),
                                    on_change=lambda val, n=name: State.set_gen_gdw_info(n, val),
                                    default_value=default,
                                    size="1",
                                    type="number",
                                ),
                                spacing="1",
                            )
                            for name, default in info_items
                        ],
                        columns="4",
                        spacing="3",
                        width="100%",
                    ),
                    spacing="3",
                    width="100%",
                ),
                width="100%",
            ),
        )

    return rx.vstack(
        # 命令选择区
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("settings", size=20, color="#2563eb"),
                    rx.heading("选择命令", size="3", font_weight="semibold"),
                    rx.spacer(),
                    rx.cond(
                        (State.current_protocol == 0) | (State.current_protocol == 7) | (State.current_protocol == 8),
                        rx.badge("支持组帧", color_scheme="green", variant="soft"),
                        rx.badge("当前协议暂不支持组帧", color_scheme="gray", variant="soft"),
                    ),
                    spacing="2",
                ),
                # 南网 DI 选择 (协议 0)
                rx.cond(
                    State.current_protocol == 0,
                    rx.hstack(
                        rx.text("DI:", size="2", font_weight="medium", width="60px"),
                        rx.el.select(
                            rx.el.option("请选择 DI", value=""),
                            rx.foreach(
                                State.di_options,
                                lambda opt: rx.el.option(opt["label"], value=opt["value"])
                            ),
                            default_value="",
                            on_change=State.set_gen_di_key,
                            class_name="flex-1 rounded border border-gray-300 px-3 py-2",
                        ),
                        spacing="2",
                        width="100%",
                    ),
                ),
                # 国网 AFN+Fn 选择 (协议 7)
                rx.cond(
                    State.current_protocol == 7,
                    rx.hstack(
                        rx.text("AFN+Fn:", size="2", font_weight="medium", width="60px"),
                        rx.el.select(
                            rx.el.option("请选择 AFN+Fn", value=""),
                            rx.foreach(
                                State.afn_fn_options,
                                lambda opt: rx.el.option(opt["label"], value=opt["value"])
                            ),
                            default_value="",
                            on_change=State.set_gen_afn_fn,
                            class_name="flex-1 rounded border border-gray-300 px-3 py-2",
                        ),
                        spacing="2",
                        width="100%",
                    ),
                ),
                # 698.45 APDU 选择 (协议 8)
                rx.cond(
                    State.current_protocol == 8,
                    rx.vstack(
                        rx.hstack(
                            rx.text("APDU:", size="2", font_weight="medium", width="60px"),
                            rx.el.select(
                                rx.el.option("请选择 APDU 类型", value=""),
                                rx.foreach(
                                    State.dlt698_apdu_options,
                                    lambda opt: rx.el.option(opt, value=opt)
                                ),
                                default_value="",
                                on_change=State.set_gen_dlt698_apdu,
                                class_name="flex-1 rounded border border-gray-300 px-3 py-2",
                            ),
                            spacing="2",
                            width="100%",
                        ),
                        rx.cond(
                            State.gen_dlt698_apdu != "",
                            rx.hstack(
                                rx.text("子类型:", size="2", font_weight="medium", width="60px"),
                                rx.el.select(
                                    rx.el.option("请选择子类型", value=""),
                                    rx.foreach(
                                        State.dlt698_sub_options,
                                        lambda opt: rx.el.option(opt["label"], value=opt["value"])
                                    ),
                                    default_value="",
                                    on_change=State.set_gen_dlt698_sub,
                                    class_name="flex-1 rounded border border-gray-300 px-3 py-2",
                                ),
                                spacing="2",
                                width="100%",
                            ),
                        ),
                        spacing="2",
                        width="100%",
                    ),
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
        # 帧配置区（公共参数）
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("grid_on", size=20, color="#2563eb"),
                    rx.heading("帧配置", size="3", font_weight="semibold"),
                    spacing="2",
                ),
                rx.grid(
                    rx.vstack(
                        rx.text("源地址 (HEX):", size="1", font_weight="medium"),
                        rx.input(
                            value=State.gen_src_addr,
                            on_change=State.set_gen_src_addr,
                            placeholder="000000000000",
                            font_family="monospace",
                            size="2",
                        ),
                        spacing="1",
                    ),
                    rx.vstack(
                        rx.text("目的地址 (HEX):", size="1", font_weight="medium"),
                        rx.input(
                            value=State.gen_dst_addr,
                            on_change=State.set_gen_dst_addr,
                            placeholder="000000000000",
                            font_family="monospace",
                            size="2",
                        ),
                        spacing="1",
                    ),
                    rx.vstack(
                        rx.text("帧序列号:", size="1", font_weight="medium"),
                        rx.input(
                            type="number",
                            value=State.gen_seq.to_string(),
                            on_change=State.set_gen_seq,
                            size="2",
                        ),
                        spacing="1",
                    ),
                    rx.vstack(
                        rx.text("传输方向:", size="1", font_weight="medium"),
                        rx.el.select(
                            rx.el.option("下行(主站→终端)", value="0"),
                            rx.el.option("上行(终端→主站)", value="1"),
                            default_value="0",
                            on_change=State.set_gen_dir,
                            class_name="rounded border border-gray-300 px-3 py-2",
                        ),
                        spacing="1",
                    ),
                    rx.vstack(
                        rx.text("启动标志(PRM):", size="1", font_weight="medium"),
                        rx.el.select(
                            rx.el.option("启动站发起(1)", value="1"),
                            rx.el.option("从动站发起(0)", value="0"),
                            default_value="1",
                            on_change=State.set_gen_prm,
                            class_name="rounded border border-gray-300 px-3 py-2",
                        ),
                        spacing="1",
                    ),
                    columns="3",
                    spacing="4",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
        # 国网信息域配置（仅协议7）
        gdw_info_panel(),
        # 数据字段（动态，根据选择的命令生成）
        dynamic_fields(),
        # 预览和结果
        rx.hstack(
            # 预览
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("visibility", size=20, color="#2563eb"),
                        rx.heading("生成预览", size="3", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.scroll_area(
                        rx.text(State.gen_preview, font_family="monospace", font_size="12px", white_space="pre-wrap"),
                        height="200px",
                        width="100%",
                    ),
                    spacing="3",
                    width="100%",
                ),
                width="50%",
            ),
            # 结果
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("output", size=20, color="#059669"),
                        rx.heading("生成结果", size="3", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.cond(
                        State.gen_result != "",
                        rx.scroll_area(
                            rx.text(State.gen_result, font_family="monospace", font_size="12px", white_space="pre-wrap"),
                            height="200px",
                            padding="2",
                            background="rgba(5, 150, 105, 0.05)",
                            border_radius="8px",
                            width="100%",
                        ),
                        rx.center(
                            rx.vstack(
                                rx.icon("build", size=48, color="#9ca3af"),
                                rx.text("点击「生成帧」查看结果", color="#6b7280", size="2"),
                                spacing="2",
                                padding="8",
                            ),
                            width="100%",
                        ),
                    ),
                    spacing="3",
                    width="100%",
                ),
                width="50%",
            ),
            spacing="4",
            width="100%",
            align="start",
        ),
        # 操作按钮
        rx.hstack(
            rx.button(
                rx.cond(State.is_loading, rx.spinner(size="1"), rx.icon("play", size=16)),
                "生成帧",
                on_click=State.generate_frame,
                loading=State.is_loading,
                color_scheme="blue",
                size="2",
            ),
            rx.button(
                rx.icon("copy", size=16),
                "复制结果",
                on_click=State.copy_gen_result,
                variant="outline",
                color_scheme="gray",
                size="2",
                disabled=State.gen_result_hex == "",
            ),
            spacing="3",
        ),
        spacing="4",
        width="100%",
    )


# ═══════════════════════════════════════════════════════════════
# 报文对比 Tab
# ═══════════════════════════════════════════════════════════════

def diff_tab() -> rx.Component:
    """报文对比（协议感知，字段级+字节级+差异说明）"""
    return rx.vstack(
        # 输入区域
        rx.hstack(
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("file", size=18, color="#2563eb"),
                        rx.heading("报文 A (基准)", size="2", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.text_area(
                        placeholder="输入第一个报文...",
                        value=State.diff_left,
                        on_change=State.set_diff_left,
                        height="100px",
                        width="100%",
                        font_family="monospace",
                        font_size="12px",
                    ),
                    spacing="2",
                    width="100%",
                ),
                width="50%",
            ),
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("file", size=18, color="#d97706"),
                        rx.heading("报文 B (对比)", size="2", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.text_area(
                        placeholder="输入第二个报文...",
                        value=State.diff_right,
                        on_change=State.set_diff_right,
                        height="100px",
                        width="100%",
                        font_family="monospace",
                        font_size="12px",
                    ),
                    spacing="2",
                    width="100%",
                ),
                width="50%",
            ),
            spacing="4",
            width="100%",
        ),
        # 操作按钮 + 选项
        rx.hstack(
            rx.button(
                rx.cond(State.is_loading, rx.spinner(size="1"), rx.icon("compare_arrows", size=16)),
                "开始对比",
                on_click=State.compare_frames,
                loading=State.is_loading,
                color_scheme="blue",
                size="2",
            ),
            rx.button(
                rx.icon("eraser", size=16),
                "清空",
                on_click=State.clear_diff,
                variant="outline",
                color_scheme="gray",
                size="2",
            ),
            rx.divider(orientation="vertical", size="2"),
            rx.checkbox(
                "忽略校验和",
                checked=State.diff_ignore_checksum,
                on_change=State.toggle_diff_ignore_checksum,
                size="2",
            ),
            rx.checkbox(
                "忽略序列号",
                checked=State.diff_ignore_sequence,
                on_change=State.toggle_diff_ignore_sequence,
                size="2",
            ),
            rx.checkbox(
                "仅显示差异",
                checked=State.diff_only_diff,
                on_change=State.toggle_diff_only_diff,
                size="2",
            ),
            spacing="3",
            width="100%",
        ),
        # 差异说明（人话解读）
        rx.cond(
            State.diff_explanations.length() > 0,
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("lightbulb", size=18, color="#f59e0b"),
                        rx.heading("差异说明", size="3", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.vstack(
                        rx.foreach(
                            State.diff_explanations,
                            lambda exp: rx.hstack(
                                rx.icon("info", size=14, color="#f59e0b", flex_shrink="0"),
                                rx.text(exp, size="2"),
                                spacing="2",
                                padding_x="2",
                                padding_y="1",
                                width="100%",
                                background="rgba(245, 158, 11, 0.05)",
                                border_left="3px solid #f59e0b",
                                border_radius="4px",
                            ),
                        ),
                        spacing="2",
                        width="100%",
                    ),
                    spacing="2",
                    width="100%",
                ),
                width="100%",
            ),
        ),
        # 字段级对比
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("table", size=18, color="#2563eb"),
                    rx.heading("字段级对比", size="3", font_weight="semibold"),
                    rx.spacer(),
                    rx.badge(
                        f"{State.diff_field_rows.length()} 个字段",
                        color_scheme="blue",
                        variant="soft",
                    ),
                    spacing="2",
                ),
                rx.cond(
                    State.diff_field_rows.length() > 0,
                    rx.scroll_area(
                        rx.table.root(
                            rx.table.header(
                                rx.table.row(
                                    rx.table.column_header_cell("字段名", width="22%"),
                                    rx.table.column_header_cell("偏移(A/B)", width="12%"),
                                    rx.table.column_header_cell("长度(A/B)", width="12%"),
                                    rx.table.column_header_cell("报文A值", width="22%"),
                                    rx.table.column_header_cell("报文B值", width="22%"),
                                    rx.table.column_header_cell("差异类型", width="10%"),
                                )
                            ),
                            rx.table.body(
                                rx.foreach(
                                    State.diff_field_rows,
                                    lambda row: rx.table.row(
                                        rx.table.cell(row["field_name"], font_weight="medium"),
                                        rx.table.cell(rx.code(row["offset_display"], variant="soft")),
                                        rx.table.cell(rx.code(row["length_display"], variant="soft")),
                                        rx.table.cell(rx.code(row["value_a"], variant="soft"), font_size="11px"),
                                        rx.table.cell(rx.code(row["value_b"], variant="soft"), font_size="11px"),
                                        rx.table.cell(
                                            rx.badge(
                                                row["diff_type"],
                                                color_scheme=rx.cond(
                                                    row["diff_type"] == "相同", "green",
                                                    rx.cond(
                                                        row["diff_type"] == "修改", "red",
                                                        rx.cond(
                                                            row["diff_type"] == "A独有", "gray",
                                                            "amber",
                                                        ),
                                                    ),
                                                ),
                                                variant="soft",
                                                size="1",
                                            ),
                                        ),
                                        style=rx.cond(
                                            row["diff_type"] != "相同",
                                            {"background": "rgba(220, 38, 38, 0.03)"},
                                            {},
                                        ),
                                    ),
                                )
                            ),
                            variant="surface",
                            size="1",
                            width="100%",
                        ),
                        height="280px",
                    ),
                    rx.center(
                        rx.vstack(
                            rx.icon("compare_arrows", size=40, color="#9ca3af"),
                            rx.text("点击「开始对比」查看字段级差异", color="#6b7280", size="2"),
                            spacing="2",
                            padding="6",
                        ),
                        width="100%",
                    ),
                ),
                spacing="2",
                width="100%",
            ),
            width="100%",
        ),
        # 字节级对比
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("binary", size=18, color="#2563eb"),
                    rx.heading("字节级对比 (按字段分组)", size="3", font_weight="semibold"),
                    rx.spacer(),
                    rx.badge(
                        f"{State.diff_byte_rows.length()} 行",
                        color_scheme="blue",
                        variant="soft",
                    ),
                    spacing="2",
                ),
                rx.cond(
                    State.diff_byte_rows.length() > 0,
                    rx.scroll_area(
                        rx.table.root(
                            rx.table.header(
                                rx.table.row(
                                    rx.table.column_header_cell("偏移", width="12%"),
                                    rx.table.column_header_cell("报文 A (HEX)", width="38%"),
                                    rx.table.column_header_cell("报文 B (HEX)", width="38%"),
                                    rx.table.column_header_cell("状态", width="12%"),
                                )
                            ),
                            rx.table.body(
                                rx.foreach(
                                    State.diff_byte_rows,
                                    lambda row: rx.cond(
                                        row["is_field_header"],
                                        rx.table.row(
                                            rx.table.cell(
                                                rx.text(row["field_name"], font_weight="bold", size="1"),
                                                col_span=4,
                                                background=rx.cond(
                                                    row["status"] == "same",
                                                    "rgba(156, 163, 175, 0.1)",
                                                    rx.cond(
                                                        row["status"] == "modified",
                                                        "rgba(220, 38, 38, 0.1)",
                                                        rx.cond(
                                                            row["status"] == "added",
                                                            "rgba(217, 119, 6, 0.1)",
                                                            "rgba(229, 231, 235, 0.2)",
                                                        ),
                                                    ),
                                                ),
                                            ),
                                        ),
                                        rx.table.row(
                                            rx.table.cell(rx.code(row["offset"], variant="soft"), font_size="11px"),
                                            rx.table.cell(rx.code(row["left"], variant="soft"), font_family="monospace", font_size="11px"),
                                            rx.table.cell(rx.code(row["right"], variant="soft"), font_family="monospace", font_size="11px"),
                                            rx.table.cell(
                                                rx.badge(
                                                    rx.cond(
                                                        row["status"] == "same", "=",
                                                        rx.cond(
                                                            row["status"] == "modified", "≠",
                                                            rx.cond(
                                                                row["status"] == "added", "+",
                                                                "-",
                                                            ),
                                                        ),
                                                    ),
                                                    color_scheme=rx.cond(
                                                        row["status"] == "same", "green",
                                                        rx.cond(
                                                            row["status"] == "modified", "red",
                                                            rx.cond(
                                                                row["status"] == "added", "amber",
                                                                "gray",
                                                            ),
                                                        ),
                                                    ),
                                                    variant="soft",
                                                    size="1",
                                                ),
                                            ),
                                            style=rx.cond(
                                                row["status"] != "same",
                                                {"background": "rgba(220, 38, 38, 0.03)"},
                                                {},
                                            ),
                                        ),
                                    ),
                                )
                            ),
                            variant="surface",
                            size="1",
                            width="100%",
                        ),
                        height="280px",
                    ),
                    rx.center(
                        rx.vstack(
                            rx.icon("binary", size=40, color="#9ca3af"),
                            rx.text("点击「开始对比」查看字节级差异", color="#6b7280", size="2"),
                            spacing="2",
                            padding="6",
                        ),
                        width="100%",
                    ),
                ),
                spacing="2",
                width="100%",
            ),
            width="100%",
        ),
        spacing="4",
        width="100%",
    )


# ═══════════════════════════════════════════════════════════════
# 查询 Tab
# ═══════════════════════════════════════════════════════════════

def lookup_tab() -> rx.Component:
    """查询（根据当前协议自动切换查询类型）"""
    return rx.vstack(
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("search", size=20, color="#2563eb"),
                    rx.heading(State.lookup_title, size="3", font_weight="semibold"),
                    rx.spacer(),
                    rx.badge(f"{State.lookup_results.length()} 条", color_scheme="blue", variant="soft"),
                    spacing="2",
                ),
                rx.hstack(
                    rx.input(
                        placeholder="输入关键词过滤（DI码/名称/说明等）...",
                        value=State.lookup_query,
                        on_change=State.set_lookup_query,
                        width="400px",
                        size="2",
                    ),
                    rx.button(
                        rx.icon("search", size=16),
                        "搜索",
                        on_click=State.do_lookup,
                        loading=State.is_loading,
                        color_scheme="blue",
                        size="2",
                    ),
                    spacing="3",
                ),
                rx.text("提示：切换协议会自动切换查询类型（DI/AFN/OBIS/OI/业务标识等）", size="1", color="gray"),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
        # 查询结果 - 动态列表格
        rx.card(
            rx.vstack(
                rx.cond(
                    State.lookup_results.length() > 0,
                    rx.scroll_area(
                        rx.table.root(
                            rx.table.header(
                                rx.table.row(
                                    rx.foreach(
                                        State.lookup_columns,
                                        lambda col: rx.table.column_header_cell(col),
                                    )
                                )
                            ),
                            rx.table.body(
                                rx.foreach(
                                    State.lookup_results,
                                    lambda row: rx.table.row(
                                        rx.foreach(
                                            State.lookup_columns,
                                            lambda col: rx.table.cell(
                                                rx.code(row[col], variant="soft"),
                                                font_size="12px",
                                            ),
                                        )
                                    )
                                )
                            ),
                            variant="surface",
                            size="1",
                            width="100%",
                        ),
                        height="500px",
                    ),
                    rx.center(
                        rx.vstack(
                            rx.icon("search", size=48, color="#9ca3af"),
                            rx.text("点击「搜索」或切换协议查看查询数据", color="#6b7280", size="2"),
                            spacing="2",
                            padding="8",
                        ),
                        width="100%",
                    ),
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
        spacing="4",
        width="100%",
    )


# ═══════════════════════════════════════════════════════════════
# 主页面
# ═══════════════════════════════════════════════════════════════

def index() -> rx.Component:
    """主页面"""
    return rx.box(
        header(),
        rx.box(
            newgen_controls(),
            message_banner(),
            # Tab 切换按钮
            rx.hstack(
                rx.button(
                    rx.icon("file_input", size=16),
                    "单帧解析",
                    on_click=lambda: State.set_tab("single"),
                    variant=rx.cond(State.active_tab == "single", "solid", "soft"),
                    color_scheme=rx.cond(State.active_tab == "single", "blue", "gray"),
                    size="2",
                ),
                rx.button(
                    rx.icon("list", size=16),
                    "批量解析",
                    on_click=lambda: State.set_tab("batch"),
                    variant=rx.cond(State.active_tab == "batch", "solid", "soft"),
                    color_scheme=rx.cond(State.active_tab == "batch", "blue", "gray"),
                    size="2",
                ),
                rx.button(
                    rx.icon("edit_note", size=16),
                    "协议组帧",
                    on_click=lambda: State.set_tab("frame"),
                    variant=rx.cond(State.active_tab == "frame", "solid", "soft"),
                    color_scheme=rx.cond(State.active_tab == "frame", "blue", "gray"),
                    size="2",
                ),
                rx.button(
                    rx.icon("compare_arrows", size=16),
                    "报文对比",
                    on_click=lambda: State.set_tab("diff"),
                    variant=rx.cond(State.active_tab == "diff", "solid", "soft"),
                    color_scheme=rx.cond(State.active_tab == "diff", "blue", "gray"),
                    size="2",
                ),
                rx.button(
                    rx.icon("search", size=16),
                    "查询",
                    on_click=lambda: State.set_tab("lookup"),
                    variant=rx.cond(State.active_tab == "lookup", "solid", "soft"),
                    color_scheme=rx.cond(State.active_tab == "lookup", "blue", "gray"),
                    size="2",
                ),
                spacing="2",
                margin_bottom="4",
            ),
            # Tab 内容
            rx.cond(
                State.active_tab == "single",
                single_parse_tab(),
                rx.cond(
                    State.active_tab == "batch",
                    batch_parse_tab(),
                    rx.cond(
                        State.active_tab == "frame",
                        frame_gen_tab(),
                        rx.cond(
                            State.active_tab == "diff",
                            diff_tab(),
                            lookup_tab(),
                        ),
                    ),
                ),
            ),
            padding_x="10%",
            padding_y="4",
            width="100%",
        ),
        background="#f5f7fa",
        min_height="100vh",
    )


# ═══════════════════════════════════════════════════════════════
# 应用入口
# ═══════════════════════════════════════════════════════════════

app = rx.App(
    theme=rx.theme(
        appearance="light",
        accent_color="blue",
        gray_color="slate",
        radius="medium",
        scaling="100%",
    ),
    stylesheets=[
        "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&display=swap",
    ],
)

app.add_page(index, route="/", title="南网协议解析工具")
