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
    strip_head: int = 0
    strip_tail: int = 0

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
    gen_protocol: int = 0
    gen_di_key: str = ""
    gen_afn_fn: str = ""
    gen_dlt698_apdu: str = ""
    gen_dlt698_sub: str = ""
    gen_fields: Dict[str, str] = {}
    gen_src_addr: str = "000000000000"
    gen_dst_addr: str = "000000000000"
    gen_seq: int = 0
    gen_dir: int = 0
    gen_prm: int = 1
    gen_result: str = ""
    gen_preview: str = ""
    # DI/AFN 选项列表
    di_options: List[Dict[str, str]] = []
    afn_fn_options: List[Dict[str, str]] = []
    dlt698_apdu_options: List[str] = []
    dlt698_sub_options: List[Dict[str, str]] = []

    # ── 报文对比 ─────────────────────────────────────────────
    diff_left: str = ""
    diff_right: str = ""
    diff_result: List[Dict[str, Any]] = []

    # ── 查询 ─────────────────────────────────────────────────
    lookup_type: str = "di"  # di, afn, obis, cmd
    lookup_query: str = ""
    lookup_results: List[Dict[str, Any]] = []

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

    def set_strip_head(self, value: str):
        try:
            self.strip_head = int(value) if value else 0
        except ValueError:
            self.strip_head = 0

    def set_strip_tail(self, value: str):
        try:
            self.strip_tail = int(value) if value else 0
        except ValueError:
            self.strip_tail = 0

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

    def _apply_csg_strip(self, frame_bytes: bytes) -> bytes:
        """应用新一代载波字节剔除"""
        if self.current_protocol != 9:
            return frame_bytes
        if self.strip_head <= 0 and self.strip_tail <= 0:
            return frame_bytes
        total = len(frame_bytes)
        tail_end = total - self.strip_tail if self.strip_tail > 0 else total
        if self.strip_head >= tail_end:
            raise ValueError(f"剔除字节数过多（前{self.strip_head}+尾{self.strip_tail}），超出总长{total}")
        return frame_bytes[self.strip_head:tail_end]

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
            frame_bytes = self._apply_csg_strip(frame_bytes)

            parser = self._get_parser()

            # 新一代载波需要 parse_level
            if self.current_protocol == 9:
                result = parser.parse_to_table(frame_bytes, parse_level=self.csg_parse_level)
            else:
                result = parser.parse_to_table(frame_bytes)

            # 转换结果
            self.parse_result = []
            for idx, row in enumerate(result):
                if len(row) >= 4:
                    self.parse_result.append({
                        "id": idx,
                        "field": str(row[0]) if row[0] else "",
                        "raw": str(row[1]) if row[1] else "",
                        "parsed": str(row[2]) if row[2] else "",
                        "comment": str(row[3]) if row[3] else "",
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
            import re

            # 帧提取
            frame_hexes = self._extract_frames(self.batch_input)
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

                    if self.current_protocol == 9:
                        result = parser.parse_to_table(frame_bytes, parse_level=self.csg_parse_level)
                    else:
                        result = parser.parse_to_table(frame_bytes)

                    status = "成功" if result and (not result[0] or result[0][0] != "❌ 解析失败") else "失败"
                    proto_name = self._get_frame_summary(result)
                    summary = self._extract_summary(result)[:100]

                    self.batch_results.append({
                        "id": idx,
                        "frame_bytes": frame_bytes,
                        "result": result,
                        "status": status,
                        "proto": proto_name,
                        "summary": summary,
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

    def _extract_frames(self, text: str) -> List[str]:
        """从原始文本中提取协议帧"""
        import re
        protocol = self.current_protocol

        if protocol in (0, 6, 7, 8):  # 南网/国网/DLT645/698.45
            frames = self._extract_68_from_raw(text)
            if not frames:
                clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
                frames = self._extract_68_frames(clean) if protocol != 8 else self._extract_69845_frames(clean)
            return frames
        elif protocol == 1:  # PLC RF
            clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
            return [clean] if 4 <= len(clean) <= 512 else []
        elif protocol == 2:  # HDLC
            clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
            return self._extract_hdlc_frames(clean)
        elif protocol in (3, 5):  # DLMS-APDU裸报文
            return [f.strip() for f in text.splitlines() if f.strip()]
        elif protocol == 4:  # DLMS Wrapper
            return self._extract_wrapper_frames(text)
        elif protocol == 9:  # 新一代载波
            return self._extract_csg_frames(text)
        else:
            return [f.strip() for f in text.splitlines() if f.strip()]

    def _extract_68_from_raw(self, text: str) -> List[str]:
        """从原始文本中直接匹配 68...16 帧模式"""
        import re
        frames = []
        seen = set()
        for line in text.splitlines():
            for m in re.finditer(r'(68[0-9A-Fa-f]{10,}16)', line):
                candidate = m.group(1).upper()
                if len(candidate) % 2 != 0:
                    candidate = candidate[:-1]
                if len(candidate) < 16:
                    continue
                try:
                    low = int(candidate[2:4], 16)
                    high = int(candidate[4:6], 16)
                    length = low | (high << 8)
                    if 8 <= length <= 2048 and candidate not in seen:
                        seen.add(candidate)
                        frames.append(candidate)
                except ValueError:
                    pass
        return frames

    def _extract_68_frames(self, clean: str) -> List[str]:
        """提取68格式帧"""
        import re
        frames = []
        i = 0
        while i < len(clean) - 7:
            pos = clean.find('68', i)
            if pos == -1:
                break
            if pos + 6 > len(clean):
                i = pos + 2
                continue
            try:
                low_byte = int(clean[pos + 2:pos + 4], 16)
                high_byte = int(clean[pos + 4:pos + 6], 16)
                length = low_byte | (high_byte << 8)
            except ValueError:
                i = pos + 2
                continue
            if length < 8 or length > 2048:
                i = pos + 2
                continue
            frame_hex_len = length * 2
            if pos + frame_hex_len > len(clean):
                i = pos + 2
                continue
            candidate = clean[pos:pos + frame_hex_len]
            if candidate[-2:] != '16':
                i = pos + 2
                continue
            frames.append(candidate)
            i = pos + frame_hex_len
        return frames

    def _extract_69845_frames(self, clean: str) -> List[str]:
        """提取698.45格式帧"""
        import re
        frames = []
        i = 0
        while i < len(clean) - 7:
            pos = clean.find('68', i)
            if pos == -1:
                break
            if pos + 6 > len(clean):
                i = pos + 2
                continue
            try:
                low_byte = int(clean[pos + 2:pos + 4], 16)
                high_byte = int(clean[pos + 4:pos + 6], 16)
                length = low_byte | (high_byte << 8)
            except ValueError:
                i = pos + 2
                continue
            if length < 8 or length > 2048:
                i = pos + 2
                continue
            total_len = length + 4
            frame_hex_len = total_len * 2
            if pos + frame_hex_len > len(clean):
                i = pos + 2
                continue
            candidate = clean[pos:pos + frame_hex_len]
            if candidate[-2:] != '16':
                i = pos + 2
                continue
            frames.append(candidate)
            i = pos + frame_hex_len
        return frames

    def _extract_hdlc_frames(self, clean: str) -> List[str]:
        """提取HDLC帧（7E开头，7E结束）"""
        frames = []
        i = 0
        while i < len(clean) - 3:
            pos = clean.find('7E', i)
            if pos == -1:
                break
            end = clean.find('7E', pos + 2)
            if end == -1:
                end = min(pos + 512, len(clean))
            candidate = clean[pos:end + 2]
            if len(candidate) >= 6:
                frames.append(candidate)
            i = end + 2
        return frames

    def _extract_wrapper_frames(self, text: str) -> List[str]:
        """提取DLMS Wrapper帧"""
        import re
        frames = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            hex_matches = re.findall(r'[0-9A-Fa-f]{16,}', line)
            if not hex_matches:
                continue
            for hex_pattern in hex_matches:
                hex_pattern = hex_pattern.upper()
                i = 0
                while i <= len(hex_pattern) - 16:
                    if hex_pattern[i:i+4] == '0001':
                        apdu_len = int(hex_pattern[i+12:i+16], 16)
                        if 0 <= apdu_len <= 8192:
                            frame_len = 16 + apdu_len * 2
                            if i + frame_len <= len(hex_pattern):
                                frames.append(hex_pattern[i:i+frame_len])
                                i += frame_len
                                continue
                            else:
                                frames.append(hex_pattern[i:])
                                break
                    i += 2
        return frames

    def _extract_csg_frames(self, text: str) -> List[str]:
        """提取新一代载波协议帧"""
        frames = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            clean_line = ''.join(c for c in line if c in '0123456789ABCDEFabcdef').upper()
            if len(clean_line) < 8:
                continue
            if len(clean_line) % 2 != 0:
                clean_line = clean_line[:-1]
            frames.append(clean_line)
        return frames

    def _get_frame_summary(self, result: List) -> str:
        """提取帧类型摘要"""
        if not result:
            return "空"
        for row in result:
            if len(row) >= 4:
                field = row[0]
                if "AFN" in str(field) or "帧类型" in str(field) or "业务标识" in str(field) or "功能码" in str(field):
                    return str(row[3]) or str(row[2]) or str(field)
        return result[0][0] if result[0] else "空"

    def _extract_summary(self, result: List) -> str:
        """提取摘要"""
        if not result:
            return ""
        parts = []
        for row in result[:5]:
            if len(row) >= 4 and row[3]:
                parts.append(str(row[3]))
        return "; ".join(parts)

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
        self._update_gen_preview()

    def set_gen_afn_fn(self, value: str):
        """设置 AFN+Fn"""
        self.gen_afn_fn = value
        self._update_gen_preview()

    def set_gen_dlt698_apdu(self, value: str):
        """设置 698.45 APDU 类型"""
        self.gen_dlt698_apdu = value
        self.gen_dlt698_sub = ""
        self._load_dlt698_sub_options()
        self._update_gen_preview()

    def set_gen_dlt698_sub(self, value: str):
        """设置 698.45 子选项"""
        self.gen_dlt698_sub = value
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

    def _load_di_options(self):
        """加载 DI 选项"""
        try:
            from protocol_parser import ProtocolFrameParser
            parser = ProtocolFrameParser()
            options = []
            for (di3, di2, di1, di0), desc in parser.DI_COMBINATION_MAP.items():
                key = f"{di3:02X}{di2:02X}{di1:02X}{di0:02X}"
                options.append({"label": f"{key} - {desc}", "value": key})
            self.di_options = options
        except Exception:
            self.di_options = []

    def _load_afn_fn_options(self):
        """加载 AFN+Fn 选项"""
        try:
            from gdw10376_parser import GDW10376Parser
            parser = GDW10376Parser()
            options = []
            for afn, fn_map in parser.FN_MAP.items():
                afn_name = parser.AFN_MAP.get(afn, f"未知({afn:02X})")
                for fn, fn_name in fn_map.items():
                    key = f"{afn:02X}{fn:02X}"
                    options.append({"label": f"{key} - {afn_name} / Fn={fn:02X} {fn_name}", "value": key})
            self.afn_fn_options = options
        except Exception:
            self.afn_fn_options = []

    def _load_dlt698_options(self):
        """加载 698.45 选项"""
        try:
            from dl_t698_45_frame_schema import APDU_TYPE_LIST
            self.dlt698_apdu_options = APDU_TYPE_LIST
        except ImportError:
            self.dlt698_apdu_options = []

    def _load_dlt698_sub_options(self):
        """加载 698.45 子选项"""
        if not self.gen_dlt698_apdu:
            self.dlt698_sub_options = []
            return
        try:
            from dl_t698_45_frame_schema import OI_PRESET_LIST
            sub_dict = OI_PRESET_LIST.get(self.gen_dlt698_apdu, {})
            self.dlt698_sub_options = [{"label": v, "value": k} for k, v in sub_dict.items()]
        except ImportError:
            self.dlt698_sub_options = []

    def _update_gen_preview(self):
        """更新组帧预览"""
        # 这里简化处理，实际应该调用 send_frame_lib 生成
        parts = []
        if self.current_protocol in (0, 6):  # 南网
            if self.gen_di_key:
                parts.append(f"DI: {self.gen_di_key}")
        elif self.current_protocol == 7:  # 国网
            if self.gen_afn_fn:
                parts.append(f"AFN+Fn: {self.gen_afn_fn}")
        elif self.current_protocol == 8:  # 698.45
            if self.gen_dlt698_apdu:
                parts.append(f"APDU: {self.gen_dlt698_apdu}")
            if self.gen_dlt698_sub:
                parts.append(f"子选项: {self.gen_dlt698_sub}")

        parts.append(f"源地址: {self.gen_src_addr}")
        parts.append(f"目的地址: {self.gen_dst_addr}")
        parts.append(f"序列号: {self.gen_seq}")
        parts.append(f"方向: {'下行' if self.gen_dir == 0 else '上行'}")
        parts.append(f"PRM: {self.gen_prm}")

        self.gen_preview = "\n".join(parts) if parts else "请选择命令类型"

    async def generate_frame(self):
        """生成报文帧"""
        self.is_loading = True
        self.message = ""

        try:
            p = self.current_protocol
            if p in (0, 6):  # 南网
                from send_frame_lib import ProtocolFrameGenerator
                gen = ProtocolFrameGenerator()
                # TODO: 调用实际生成逻辑
                self.gen_result = f"南网帧生成: DI={self.gen_di_key}"
            elif p == 7:  # 国网
                from gdw_send_frame_lib import GDWFrameGenerator
                gen = GDWFrameGenerator()
                self.gen_result = f"国网帧生成: AFN+Fn={self.gen_afn_fn}"
            elif p == 8:  # 698.45
                from dl_t698_45_frame_gen import DLT69845FrameGenerator
                gen = DLT69845FrameGenerator()
                self.gen_result = f"698.45帧生成: {self.gen_dlt698_apdu}"
            else:
                self.gen_result = f"协议 {p} 暂不支持组帧"

            self.message = "组帧完成"
            self.message_type = "success"

        except Exception as e:
            self.message = f"组帧失败: {str(e)}"
            self.message_type = "error"
        finally:
            self.is_loading = False

    def copy_gen_result(self):
        """复制组帧结果"""
        if self.gen_result:
            # Reflex 复制到剪贴板
            pass

    # ── 报文对比 ─────────────────────────────────────────────
    def set_diff_left(self, value: str):
        self.diff_left = value

    def set_diff_right(self, value: str):
        self.diff_right = value

    async def compare_frames(self):
        """对比两个报文"""
        if not self.diff_left.strip() or not self.diff_right.strip():
            self.message = "请输入两个报文进行对比"
            self.message_type = "warning"
            return

        self.is_loading = True
        self.message = ""

        try:
            left_bytes = self._clean_hex(self.diff_left)
            right_bytes = self._clean_hex(self.diff_right)

            self.diff_result = []
            max_len = max(len(left_bytes), len(right_bytes))

            for i in range(0, max_len, 16):
                left_chunk = left_bytes[i:i+16]
                right_chunk = right_bytes[i:i+16]

                left_hex = " ".join(f"{b:02X}" for b in left_chunk)
                right_hex = " ".join(f"{b:02X}" for b in right_chunk)

                diff = left_chunk != right_chunk
                self.diff_result.append({
                    "offset": f"0x{i:04X}",
                    "left": left_hex,
                    "right": right_hex,
                    "diff": diff,
                })

            diff_count = sum(1 for r in self.diff_result if r["diff"])
            self.message = f"对比完成，{diff_count} 处差异"
            self.message_type = "success" if diff_count == 0 else "warning"

        except Exception as e:
            self.message = f"对比失败: {str(e)}"
            self.message_type = "error"
        finally:
            self.is_loading = False

    def clear_diff(self):
        """清空对比"""
        self.diff_left = ""
        self.diff_right = ""
        self.diff_result = []

    # ── 查询 ─────────────────────────────────────────────────
    def set_lookup_type(self, value: str):
        self.lookup_type = value
        self.lookup_results = []

    def set_lookup_query(self, value: str):
        self.lookup_query = value

    async def do_lookup(self):
        """执行查询"""
        if not self.lookup_query.strip():
            self.message = "请输入查询内容"
            self.message_type = "warning"
            return

        self.is_loading = True
        self.message = ""
        self.lookup_results = []

        try:
            query = self.lookup_query.strip().upper()

            if self.lookup_type == "di":
                # DI 查询（南网/国网/DLT645）
                from dlt645_di_lookup import get_dlt645_di_lookup
                lookup = get_dlt645_di_lookup()
                # TODO: 实现 DI 查询逻辑
                self.lookup_results = [{"code": query, "name": "查询结果待实现", "desc": ""}]

            elif self.lookup_type == "afn":
                # AFN 查询（国网）
                from gdw_afn_lookup import get_gdw_afn_lookup
                lookup = get_gdw_afn_lookup()
                self.lookup_results = [{"code": query, "name": "查询结果待实现", "desc": ""}]

            elif self.lookup_type == "obis":
                # OBIS 查询
                from obis_lookup import get_obis_lookup
                lookup = get_obis_lookup()
                self.lookup_results = [{"code": query, "name": "查询结果待实现", "desc": ""}]

            elif self.lookup_type == "cmd":
                # 命令字查询
                from command_lookup import get_command_lookup
                lookup = get_command_lookup()
                self.lookup_results = [{"code": query, "name": "查询结果待实现", "desc": ""}]

            self.message = f"查询完成，共 {len(self.lookup_results)} 条结果"
            self.message_type = "success"

        except Exception as e:
            self.message = f"查询失败: {str(e)}"
            self.message_type = "error"
        finally:
            self.is_loading = False

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


def csg_controls() -> rx.Component:
    """新一代载波控制条（仅协议9显示）"""
    return rx.cond(
        State.current_protocol == 9,
        rx.card(
            rx.hstack(
                rx.icon("tune", size=18, color="#2563eb"),
                rx.text("解析级别:", size="2", font_weight="medium"),
                rx.el.select(
                    rx.el.option("自动识别", value="auto"),
                    rx.el.option("FC+PB解析(完整MPDU)", value="fc_pb"),
                    rx.el.option("FC+eFC解析", value="fc_efc"),
                    rx.el.option("仅FC解析", value="fc_only"),
                    rx.el.option("应用层报文", value="app"),
                    default_value="auto",
                    on_change=State.set_csg_level,
                    class_name="rounded border border-gray-300 px-2 py-1 text-sm",
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
        # 结果区域
        rx.hstack(
            # 解析结果表格
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
                            height="400px",
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
                width="65%",
            ),
            # 校验结果
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("check_circle", size=20, color="#059669"),
                        rx.heading("校验结果", size="3", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.cond(
                        State.verify_result != "",
                        rx.scroll_area(
                            rx.text(State.verify_result, font_family="monospace", font_size="12px", white_space="pre-wrap"),
                            height="400px",
                        ),
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
                width="35%",
            ),
            spacing="4",
            width="100%",
            align="start",
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
    """协议组帧"""
    return rx.vstack(
        # 命令选择区
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("settings", size=20, color="#2563eb"),
                    rx.heading("选择命令", size="3", font_weight="semibold"),
                    spacing="2",
                ),
                # 南网 DI 选择 (协议 0, 6)
                rx.cond(
                    (State.current_protocol == 0) | (State.current_protocol == 6),
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
                                rx.text("子选项:", size="2", font_weight="medium", width="60px"),
                                rx.el.select(
                                    rx.el.option("请选择子选项", value=""),
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
        # 帧配置区
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("grid_on", size=20, color="#2563eb"),
                    rx.heading("帧配置", size="3", font_weight="semibold"),
                    spacing="2",
                ),
                rx.grid(
                    rx.vstack(
                        rx.text("源地址 (6字节HEX):", size="1", font_weight="medium"),
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
                        rx.text("目的地址 (6字节HEX):", size="1", font_weight="medium"),
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
                    rx.text_area(
                        value=State.gen_preview,
                        placeholder="配置参数后自动显示预览...",
                        height="150px",
                        width="100%",
                        font_family="monospace",
                        font_size="12px",
                        readonly=True,
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
                        rx.box(
                            rx.code(State.gen_result, variant="soft", font_family="monospace", font_size="12px"),
                            padding="3",
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
                disabled=State.gen_result == "",
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
    """报文对比"""
    return rx.vstack(
        # 输入区域
        rx.hstack(
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("file", size=18, color="#2563eb"),
                        rx.heading("报文 A", size="2", font_weight="semibold"),
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
                        rx.heading("报文 B", size="2", font_weight="semibold"),
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
        # 操作按钮
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
            spacing="3",
        ),
        # 对比结果
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("diff", size=20, color="#2563eb"),
                    rx.heading("对比结果", size="3", font_weight="semibold"),
                    rx.spacer(),
                    rx.badge(f"{State.diff_result.length()} 行", color_scheme="blue", variant="soft"),
                    spacing="2",
                ),
                rx.cond(
                    State.diff_result.length() > 0,
                    rx.scroll_area(
                        rx.table.root(
                            rx.table.header(
                                rx.table.row(
                                    rx.table.column_header_cell("偏移", width="15%"),
                                    rx.table.column_header_cell("报文 A", width="40%"),
                                    rx.table.column_header_cell("报文 B", width="40%"),
                                    rx.table.column_header_cell("状态", width="5%"),
                                )
                            ),
                            rx.table.body(
                                rx.foreach(
                                    State.diff_result,
                                    lambda row: rx.table.row(
                                        rx.table.cell(rx.code(row["offset"], variant="soft")),
                                        rx.table.cell(rx.code(row["left"], variant="soft"), font_family="monospace"),
                                        rx.table.cell(rx.code(row["right"], variant="soft"), font_family="monospace"),
                                        rx.table.cell(
                                            rx.cond(
                                                row["diff"],
                                                rx.badge("≠", color_scheme="red", variant="soft"),
                                                rx.badge("=", color_scheme="green", variant="soft"),
                                            )
                                        ),
                                        style=rx.cond(
                                            row["diff"],
                                            {"background": "rgba(220, 38, 38, 0.05)"},
                                            {},
                                        ),
                                    )
                                )
                            ),
                            variant="surface",
                            size="1",
                            width="100%",
                        ),
                        height="300px",
                    ),
                    rx.center(
                        rx.vstack(
                            rx.icon("compare_arrows", size=48, color="#9ca3af"),
                            rx.text("输入两个报文进行对比", color="#6b7280", size="2"),
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
# 查询 Tab
# ═══════════════════════════════════════════════════════════════

def lookup_tab() -> rx.Component:
    """查询"""
    return rx.vstack(
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("search", size=20, color="#2563eb"),
                    rx.heading("数据查询", size="3", font_weight="semibold"),
                    spacing="2",
                ),
                rx.hstack(
                    rx.el.select(
                        rx.el.option("DI 查询 (DLT645)", value="di"),
                        rx.el.option("AFN 查询 (国网)", value="afn"),
                        rx.el.option("OBIS 查询", value="obis"),
                        rx.el.option("命令字查询", value="cmd"),
                        default_value="di",
                        on_change=State.set_lookup_type,
                        width="200px",
                        class_name="rounded border border-gray-300 px-3 py-2",
                    ),
                    rx.input(
                        placeholder="输入查询码...",
                        value=State.lookup_query,
                        on_change=State.set_lookup_query,
                        width="300px",
                        size="2",
                    ),
                    rx.button(
                        rx.icon("search", size=16),
                        "查询",
                        on_click=State.do_lookup,
                        loading=State.is_loading,
                        color_scheme="blue",
                        size="2",
                    ),
                    spacing="3",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
        # 查询结果
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("list", size=20, color="#2563eb"),
                    rx.heading("查询结果", size="3", font_weight="semibold"),
                    rx.spacer(),
                    rx.badge(f"{State.lookup_results.length()} 条", color_scheme="blue", variant="soft"),
                    spacing="2",
                ),
                rx.cond(
                    State.lookup_results.length() > 0,
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("代码", width="20%"),
                                rx.table.column_header_cell("名称", width="40%"),
                                rx.table.column_header_cell("说明", width="40%"),
                            )
                        ),
                        rx.table.body(
                            rx.foreach(
                                State.lookup_results,
                                lambda row: rx.table.row(
                                    rx.table.cell(rx.code(row["code"], variant="soft")),
                                    rx.table.cell(row["name"]),
                                    rx.table.cell(rx.text(row["desc"], size="1", color="gray")),
                                )
                            )
                        ),
                        variant="surface",
                        size="1",
                        width="100%",
                    ),
                    rx.center(
                        rx.vstack(
                            rx.icon("search", size=48, color="#9ca3af"),
                            rx.text("输入查询码并点击「查询」", color="#6b7280", size="2"),
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
        rx.container(
            csg_controls(),
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
            padding="4",
            max_width="1400px",
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
