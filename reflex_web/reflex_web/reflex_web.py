# -*- coding: utf-8 -*-
"""多协议解析平台 - Reflex Web 完整版

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

from . import web_utils


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
    gw_channel: str = "plc"
    gw_strip_head: int = 0
    gw_strip_tail: int = 0
    hdc10_parse_level: str = "auto"
    hdc10_channel: str = "plc"

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
    # 文件拖拽上传信息
    batch_upload_name: str = ""
    batch_upload_size: int = 0
    batch_file_lines: int = 0
    # 批量解析进度
    batch_progress: int = 0
    batch_total: int = 0
    # 解析出的总帧数（batch_results 可能被截断，此字段始终为真实总数）
    batch_total_frames: int = 0
    # 摘要列表显示上限（防止大文件渲染卡死，导出仍包含全部）
    batch_display_limit: int = 300
    # 预处理命令链（pp_cli 管道式命令）
    batch_pp_commands: str = ""
    batch_pp_last_result: str = ""
    # 预设命令列表
    pp_preset_options: List[Dict[str, str]] = []
    # ── 批量解析：后端专用数据（单下划线前缀 → 不发送到前端）──
    # 上传文件内容：大文件（可达50MB）只存后端，避免 WebSocket 同步卡死
    _batch_file_content: str = ""
    # 全部帧的解析结果（完整数据存后端，前端只显示摘要列表）
    _batch_all_results: List[Dict[str, Any]] = []

    # ── 组帧 ─────────────────────────────────────────────────
    gen_di_key: str = ""
    gen_afn_fn: str = ""
    gen_dlt698_apdu: str = ""
    gen_dlt698_sub: str = ""
    gen_fields: Dict[str, str] = {}
    gen_field_schema: List[Dict[str, Any]] = []
    gen_src_addr: str = "000000000000"
    gen_dst_addr: str = "000000000000"
    gen_seq: int = 0
    gen_dir: int = 0
    gen_prm: int = 1
    gen_result: str = ""
    gen_result_hex: str = ""
    gen_preview: str = ""
    # 组帧模式（predefined | custom | axdr）与编辑器状态
    gen_mode: str = "predefined"
    gen_field_values: List[str] = []                      # [字段索引] 简单字段原始值，位置对齐
    gen_list_rows: List[List[List[str]]] = []             # [字段索引][行][item] 位置对齐
    gen_sub_fields: List[List[str]] = []                  # [字段索引][子字段索引] 位置对齐
    # 渲染模型（全部 str 类型，供 Reflex foreach）
    gen_field_meta: List[Dict[str, str]] = []             # [i] = {name,type,default,description,has_sub,has_list,ftype}
    gen_field_enum: List[List[Dict[str, str]]] = []       # [i] = [{value,label}] enum 选项
    gen_field_items: List[List[Dict[str, str]]] = []      # [i] = [{name,type,default}] list 的 item_fields
    gen_field_items_enum: List[List[List[Dict[str, str]]]] = []  # [i][item] = enum 选项
    gen_field_subs: List[List[Dict[str, str]]] = []       # [i] = [{name,type,default}] sub_fields
    gen_field_subs_enum: List[List[List[Dict[str, str]]]] = []   # [i][sub] = enum 选项
    gen_axdr_fixed: Dict[str, str] = {}                   # 698.45 A-XDR 固定字段（PIID/OI/属性/索引等）
    gen_custom_templates: List[Dict[str, Any]] = []       # [{name,length,ftype,endian,display,reverse,value}]
    gen_axdr_items: List[Dict[str, Any]] = []             # A-XDR 树 [{tag,type,length,value,children}]
    gen_preview_rows: List[Dict[str, str]] = []           # 实时回读预览 [{field,raw,parsed,comment}]
    # 698.45 SA/控制字段
    gen_dlt698_addr_type: int = 0
    gen_dlt698_logic_addr: int = 0
    gen_dlt698_addr_len: int = 0
    gen_dlt698_sa_raw: str = ""
    gen_dlt698_seg: int = 0
    gen_dlt698_sc: int = 0
    gen_dlt698_func: int = 3
    # 国网中继地址（逗号分隔）与预设按钮
    gen_gdw_relay_addrs_text: str = ""
    gen_preset_buttons: List[Dict[str, str]] = []         # [{name,group,frame_hex,id,description}]
    gen_preset_groups: List[str] = []
    # 预设命令管理（保存表单/搜索/编辑）
    gen_preset_name: str = ""          # 添加到预设-名称
    gen_preset_group: str = ""         # 添加到预设-分组
    gen_preset_search: str = ""        # 预设搜索过滤词
    gen_preset_edit_id: str = ""       # 正在编辑的预设按钮 id（空=未编辑）
    gen_preset_edit_name: str = ""     # 编辑-名称
    gen_preset_edit_group: str = ""    # 编辑-分组
    # DI/AFN 选项列表
    di_options: List[Dict[str, str]] = []
    afn_fn_options: List[Dict[str, str]] = []
    dlt698_apdu_options: List[str] = []
    dlt698_sub_options: List[Dict[str, str]] = []
    # 可搜索下拉：搜索词 + 过滤结果
    gen_di_search: str = ""               # DI 搜索过滤词
    di_filtered: List[Dict[str, str]] = []   # DI 过滤结果
    gen_afn_search: str = ""              # AFN+Fn 搜索过滤词
    afn_filtered: List[Dict[str, str]] = []  # AFN+Fn 过滤结果
    gen_dlt698_search: str = ""           # 698.45 APDU 搜索过滤词
    dlt698_filtered: List[Dict[str, str]] = []  # 698.45 APDU 过滤结果
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

    # ── 报文工具 ─────────────────────────────────────────────
    tool_input: str = ""
    tool_output: str = ""
    tool_hex_mode: bool = True
    tool_endian: str = "little"

    # ── 通用 ─────────────────────────────────────────────────
    message: str = ""
    message_type: str = "info"
    is_loading: bool = False
    active_tab: str = "single"

    # 协议列表（label 带索引号，对齐 PySide6 版下拉）
    PROTOCOL_OPTIONS: List[Dict[str, str]] = [
        {"label": "[0] 南网协议 (Q/CSG1209021-2019)", "value": "0"},
        {"label": "[1] PLC RF协议 (万胜海外 V1_04)", "value": "1"},
        {"label": "[2] HDLC/国网DLMS (IEC 62056-46)", "value": "2"},
        {"label": "[3] DLMS-APDU(国网)", "value": "3"},
        {"label": "[4] DLMS Wrapper裸报文", "value": "4"},
        {"label": "[5] DLMS-APDU裸报文", "value": "5"},
        {"label": "[6] DLT645-2007 电表协议", "value": "6"},
        {"label": "[7] 国网协议 (Q/GDW 10376.2-2024)", "value": "7"},
        {"label": "[8] 698.45协议 (DL/T 698.45-2017)", "value": "8"},
        {"label": "[9] 新一代载波协议 (通感一体化)", "value": "9"},
        {"label": "[10] 国网新一代双模通信互联互通", "value": "10"},
        {"label": "[11] HDC 1.0 双模互联互通 (Q/GDW 12087.42-2020)", "value": "11"},
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
        # 预设命令跟随当前协议（协议 0 读 NW_command.json，7 读 GW_command.json）
        self._load_preset_buttons()
        # 组帧选项随协议刷新（DI/AFN+Fn/698.45 APDU），对齐 GUI 切协议即重载下拉
        self._load_di_options()
        self._load_afn_fn_options()
        self._load_dlt698_options()

    def set_csg_level(self, value: str):
        self.csg_parse_level = value

    def set_gw_level(self, value: str):
        self.gw_parse_level = value

    def set_gw_channel(self, value: str):
        """设置国网新一代通道（PLC/HRF）"""
        self.gw_channel = value

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

    def set_hdc10_level(self, value: str):
        """设置 HDC 1.0 解析级别"""
        self.hdc10_parse_level = value

    def set_hdc10_channel(self, value: str):
        """设置 HDC 1.0 通道（PLC/HRF）"""
        self.hdc10_channel = value

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
        elif p == 11:
            from hdc10_parser import HDC10Parser
            return HDC10Parser()
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
            from validator.hdc10_validator import HDC10Validator
            validators = {
                0: NWValidator, 1: PLCRFValidator,
                2: HDLCValidator, 3: HDLCValidator, 4: HDLCValidator, 5: HDLCValidator,
                6: DLT645Validator, 7: GDWValidator, 8: DLT69845Validator, 9: CSGNewGenValidator,
                10: GWNewGenValidator, 11: HDC10Validator,
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

            # 新一代载波/国网新一代/HDC 1.0 需要 parse_level
            if self.current_protocol == 9:
                result = parser.parse_to_table(frame_bytes, parse_level=self.csg_parse_level)
            elif self.current_protocol == 10:
                result = parser.parse_to_table(
                    frame_bytes,
                    parse_level=self.gw_parse_level,
                    channel=self.gw_channel,
                )
            elif self.current_protocol == 11:
                result = parser.parse_to_table(
                    frame_bytes,
                    parse_level=self.hdc10_parse_level,
                    channel=self.hdc10_channel,
                )
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

    async def handle_batch_upload(self, files: List[rx.UploadFile]):
        """处理拖拽/选择上传的日志文件

        大文件（可达50MB）内容只存后端（_batch_file_content），
        不写入 batch_input / textarea，避免状态同步到前端导致页面卡死。
        """
        if not files:
            return
        try:
            parts = []
            total_size = 0
            names = []
            for f in files:
                data = await f.read()
                text = data.decode("utf-8", errors="replace")
                parts.append(text)
                total_size += len(data)
                names.append(getattr(f, "filename", None) or getattr(f, "name", None) or "文件")
            content = "\n".join(parts).strip("\n")
            # 只存后端，不同步前端
            self._batch_file_content = content
            self._batch_all_results = []
            self.batch_input = ""
            self.batch_results = []
            self.batch_upload_name = ", ".join(names)
            self.batch_upload_size = total_size
            self.batch_file_lines = len(content.splitlines())
            size_mb = total_size / (1024 * 1024)
            # 超大文件保护提示
            self.message = (
                f"已加载 {self.batch_upload_name}（{size_mb:.1f} MB，{self.batch_file_lines} 行）"
                + "\n文件内容已保存到服务器端，点击「批量解析」即可处理。"
                + ("\n⚠️ 文件较大，解析可能需要一些时间，请耐心等待" if size_mb > 5 else "")
            )
            self.message_type = "success"
        except Exception as e:
            self.message = f"读取文件失败: {e}"
            self.message_type = "error"

    def remove_batch_file(self):
        """移除已上传的文件（清空后端内容，回到手动输入模式）"""
        self._batch_file_content = ""
        self._batch_all_results = []
        self.batch_upload_name = ""
        self.batch_upload_size = 0
        self.batch_file_lines = 0
        self.batch_input = ""
        self.batch_results = []
        self.batch_selected_idx = -1
        self.batch_detail_rows = []
        self.batch_detail_hex = ""
        self.batch_progress = 0
        self.batch_total = 0
        self.batch_total_frames = 0
        self.message = "已移除上传文件，可手动粘贴或重新上传"
        self.message_type = "info"

    async def parse_batch(self):
        """批量解析（支持帧提取、监控日志剥离）

        输入源优先级：已上传文件内容（_batch_file_content，存后端）> 输入框（batch_input）。
        完整解析结果存后端（_batch_all_results），前端只同步摘要列表（≤batch_display_limit）。
        作为异步生成器：每个分块边界 yield，实时向前端发送进度更新，避免大文件卡死。
        """
        has_file = bool(self._batch_file_content)
        has_text = bool(self.batch_input.strip())
        if not has_file and not has_text:
            self.message = "请先输入报文或上传日志文件"
            self.message_type = "warning"
            return

        self.is_loading = True
        self.message = ""
        self.batch_results = []
        self.batch_detail_rows = []
        self.batch_detail_hex = ""
        self.batch_selected_idx = -1
        self.batch_progress = 0
        self.batch_total = 0
        self.batch_total_frames = 0
        self._batch_all_results = []

        try:
            from .web_utils import (
                strip_csg_new_gen_prefix, strip_gw_new_gen_prefix,
                extract_frames_for_protocol, get_frame_summary,
                clean_hex_input,
            )
            import re

            # 输入源：文件内容优先
            input_text = self._batch_file_content if has_file else self.batch_input

            # 步骤0：CLI 预处理命令链（用户输入的 pp_cli 管道命令）
            if self.batch_pp_commands.strip():
                try:
                    import shlex
                    from pp_cli import parse_and_run
                    cmds = shlex.split(self.batch_pp_commands)
                    input_text = parse_and_run(input_text, cmds)
                    self.batch_pp_last_result = f"预处理完成（{' '.join(cmds)}）：{len(input_text.splitlines())} 行"
                    # 预处理结果回写：文件源写回后端，避免大内容进前端
                    if has_file:
                        self._batch_file_content = input_text
                except Exception as pe:
                    self.batch_pp_last_result = f"预处理失败: {pe}"
                    self.message = f"预处理命令执行失败: {pe}"
                    self.message_type = "error"
                    self.is_loading = False
                    return

            # 步骤1：前缀剥离（协议9/10/11）
            if self.current_protocol == 9:
                input_text = strip_csg_new_gen_prefix(input_text, self.csg_parse_level)
            elif self.current_protocol == 10:
                input_text = strip_gw_new_gen_prefix(input_text, self.gw_parse_level)
            elif self.current_protocol == 11:
                input_text = strip_gw_new_gen_prefix(input_text, self.hdc10_parse_level)

            # 步骤1.5：全局 hex 清洗（对齐 GUI 的 _clean_hex_input(keep_newlines=True)）
            input_text = clean_hex_input(input_text, keep_newlines=True)

            # 步骤2：帧提取
            frame_hexes = extract_frames_for_protocol(input_text, self.current_protocol)
            if not frame_hexes:
                self.message = "未找到有效帧数据"
                self.message_type = "warning"
                self.is_loading = False
                return

            total = len(frame_hexes)
            self.batch_total = total
            parser = self._get_parser()

            # 分块处理：每 N 帧 yield 一次，让出事件循环并向前端发送进度
            CHUNK_SIZE = 100

            # 完整结果（含 frame_bytes + 解析明细）存后端，不发送前端
            all_results = []
            # 前端只展示摘要（截断到显示上限）
            display_results = []

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
                        result = parser.parse_to_table(
                            frame_bytes,
                            parse_level=self.gw_parse_level,
                            channel=self.gw_channel,
                        )
                    elif self.current_protocol == 11:
                        result = parser.parse_to_table(
                            frame_bytes,
                            parse_level=self.hdc10_parse_level,
                            channel=self.hdc10_channel,
                        )
                    else:
                        result = parser.parse_to_table(frame_bytes)

                    status = "成功" if result and (not result[0] or "❌" not in str(result[0][0])) else "失败"
                    proto_name = get_frame_summary(result, self.current_protocol)

                    all_results.append({
                        "id": idx,
                        "frame_bytes": frame_bytes,
                        "result": result,
                        "status": status,
                        "proto": proto_name,
                        "summary": proto_name[:120],
                        "len": len(frame_bytes),
                    })
                except Exception as ex:
                    all_results.append({
                        "id": idx,
                        "frame_bytes": b"",
                        "result": [],
                        "status": "错误",
                        "proto": "解析错误",
                        "summary": str(ex)[:100],
                        "len": 0,
                    })

                # 前端只保留摘要行（限显示上限），避免大结果同步卡死
                if len(display_results) < self.batch_display_limit:
                    display_results.append({
                        "id": all_results[-1]["id"],
                        "status": all_results[-1]["status"],
                        "proto": all_results[-1]["proto"],
                        "summary": all_results[-1]["summary"],
                        "len": all_results[-1]["len"],
                    })

                # 每块 yield：让出事件循环 + 向前端发送进度 delta
                self.batch_progress = idx + 1
                if (idx + 1) % CHUNK_SIZE == 0 or (idx + 1) == total:
                    yield None

            # 结果落地：后端存全量，前端存摘要
            self._batch_all_results = all_results
            self.batch_results = display_results
            self.batch_total_frames = len(all_results)

            success_count = sum(1 for r in all_results if r["status"] == "成功")
            fail_count = len(all_results) - success_count
            self.message = f"批量解析完成 — 共 {len(all_results)} 帧（✅ {success_count} 成功，❌ {fail_count} 失败）"
            self.message_type = "success" if fail_count == 0 else "warning"
            self.batch_pp_last_result = ""
            # 发送完成 delta（结果 + 完成消息）
            yield None

        except Exception as e:
            self.message = f"批量解析失败: {str(e)}"
            self.message_type = "error"
            import traceback
            traceback.print_exc()
        finally:
            self.is_loading = False

    def select_batch_item(self, idx: int):
        """选择批量解析结果项，显示详细解析（完整结果从后端 _batch_all_results 读取）"""
        if idx < 0 or idx >= len(self.batch_results):
            return

        self.batch_selected_idx = idx
        # 显示列表条目只含摘要，完整明细（frame_bytes/result）在后端
        display_item = self.batch_results[idx]
        frame_id = display_item.get("id", idx)
        item = None
        if 0 <= frame_id < len(self._batch_all_results):
            item = self._batch_all_results[frame_id]
        if item is None:
            self.batch_detail_hex = ""
            self.batch_detail_rows = []
            return
        result = item.get("result", [])
        frame_bytes = item.get("frame_bytes", b"")

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
        self.batch_pp_commands = ""
        self.batch_pp_last_result = ""
        self.batch_upload_name = ""
        self.batch_upload_size = 0
        self.batch_file_lines = 0
        self.batch_progress = 0
        self.batch_total = 0
        self.batch_total_frames = 0
        self._batch_file_content = ""
        self._batch_all_results = []

    # ── 预处理（pp_cli 命令链）────────────────────────────────
    def set_batch_pp_commands(self, value: str):
        """设置预处理命令链"""
        self.batch_pp_commands = value

    def apply_pp_preset(self, value: str):
        """应用预设预处理命令"""
        if not value:
            return
        if value == "__custom__":
            return
        self.batch_pp_commands = value

    def load_pp_presets(self):
        """加载预处理命令预设"""
        presets = [
            {"label": "提取 tcp data 帧", "value": "find tcp data: tcp_extract"},
            {"label": "提取监控日志帧", "value": "find > 接收机 Has Get hex_extract"},
            {"label": "合并跨行 payload", "value": "merge_payloads"},
            {"label": "提取最长 hex 序列", "value": "hex_extract"},
            {"label": "去重复行", "value": "dedup"},
            {"label": "过滤含 60F0 的行", "value": "find 60F0"},
            {"label": "过滤含 60F0 + 去重", "value": "find 60F0 dedup"},
        ]
        self.pp_preset_options = presets

    async def run_preprocess(self):
        """执行预处理命令链（文件源写回后端，文本源回填输入框）"""
        has_file = bool(self._batch_file_content)
        has_text = bool(self.batch_input.strip())
        if not has_file and not has_text:
            self.message = "请先输入报文或上传文件"
            self.message_type = "warning"
            return
        if not self.batch_pp_commands.strip():
            self.message = "请输入预处理命令"
            self.message_type = "warning"
            return
        try:
            import shlex
            from pp_cli import parse_and_run
            source = self._batch_file_content if has_file else self.batch_input
            cmds = shlex.split(self.batch_pp_commands)
            result = parse_and_run(source, cmds)
            if has_file:
                # 大文件内容写回后端，不进入前端
                self._batch_file_content = result
                self.batch_file_lines = len(result.splitlines())
                self.batch_pp_last_result = f"预处理完成（{' '.join(cmds)}）：{self.batch_file_lines} 行（已保存到服务器端）"
            else:
                self.batch_input = result
                self.batch_pp_last_result = f"预处理完成（{' '.join(cmds)}）：{len(result.splitlines())} 行"
            self.message = "预处理完成"
            self.message_type = "success"
        except Exception as e:
            self.batch_pp_last_result = f"预处理失败: {e}"
            self.message = f"预处理失败: {e}"
            self.message_type = "error"

    def clear_preprocess(self):
        """清空预处理结果"""
        self.batch_pp_commands = ""
        self.batch_pp_last_result = ""

    def export_batch_json(self):
        """导出批量解析结果为 JSON（从后端全量数据导出）"""
        if not self._batch_all_results:
            self.message = "无批量结果可导出"
            self.message_type = "warning"
            return
        from .web_utils import export_frames_to_json
        data = export_frames_to_json(self._batch_all_results)
        return rx.download(
            data=data,
            filename="batch_parse_result.json",
        )

    def export_batch_csv(self):
        """导出批量解析结果为 CSV（从后端全量数据导出）"""
        if not self._batch_all_results:
            self.message = "无批量结果可导出"
            self.message_type = "warning"
            return
        from .web_utils import export_frames_to_csv
        data = export_frames_to_csv(self._batch_all_results)
        return rx.download(
            data=data,
            filename="batch_parse_result.csv",
        )


    def _reset_gen_editor(self):
        """重置组帧编辑器状态（命令切换时调用）"""
        self.gen_mode = "predefined"
        self.gen_field_values = []
        self.gen_list_rows = []
        self.gen_sub_fields = []
        self.gen_axdr_fixed = {}
        self.gen_custom_templates = []
        self.gen_axdr_items = []
        self.gen_preview_rows = []

    def set_gen_di_key(self, value: str):
        """设置 DI"""
        self.gen_di_key = value
        self.gen_fields = {}
        self._reset_gen_editor()
        self._load_di_field_schema()
        self._update_gen_preview()

    def set_gen_di_search(self, value: str):
        """DI 可搜索下拉：按关键词过滤选项（匹配 value 或 label）"""
        self.gen_di_search = value
        kw = value.strip().lower()
        if not kw:
            self.di_filtered = []
            return
        self.di_filtered = [
            o for o in self.di_options
            if kw in o["value"].lower() or kw in o["label"].lower()
        ]

    def select_di(self, value: str):
        """选择 DI 选项（可搜索下拉）"""
        self.gen_di_search = ""
        self.di_filtered = []
        self.set_gen_di_key(value)

    def set_gen_afn_fn(self, value: str):
        """设置 AFN+Fn"""
        self.gen_afn_fn = value
        self.gen_fields = {}
        self._reset_gen_editor()
        self._load_gdw_field_schema()
        self._update_gen_preview()

    def set_gen_afn_search(self, value: str):
        """AFN+Fn 可搜索下拉：按关键词过滤选项"""
        self.gen_afn_search = value
        kw = value.strip().lower()
        if not kw:
            self.afn_filtered = []
            return
        self.afn_filtered = [
            o for o in self.afn_fn_options
            if kw in o["value"].lower() or kw in o["label"].lower()
        ]

    def select_afn(self, value: str):
        """选择 AFN+Fn 选项（可搜索下拉）"""
        self.gen_afn_search = ""
        self.afn_filtered = []
        self.set_gen_afn_fn(value)

    def set_gen_dlt698_apdu(self, value: str):
        """设置 698.45 APDU 类型"""
        self.gen_dlt698_apdu = value
        self.gen_dlt698_sub = ""
        self.gen_fields = {}
        self._reset_gen_editor()
        self._load_dlt698_sub_options()
        self._load_dlt698_field_schema()
        self._update_gen_preview()

    def set_gen_dlt698_search(self, value: str):
        """698.45 APDU 可搜索下拉：按关键词过滤选项"""
        self.gen_dlt698_search = value
        kw = value.strip().lower()
        if not kw:
            self.dlt698_filtered = []
            return
        self.dlt698_filtered = [
            {"value": o, "label": o}
            for o in self.dlt698_apdu_options
            if kw in o.lower()
        ]

    def select_dlt698(self, value: str):
        """选择 698.45 APDU 选项（可搜索下拉）"""
        self.gen_dlt698_search = ""
        self.dlt698_filtered = []
        self.set_gen_dlt698_apdu(value)

    def set_gen_dlt698_sub(self, value: str):
        """设置 698.45 子选项"""
        self.gen_dlt698_sub = value
        self.gen_fields = {}
        self._reset_gen_editor()
        self._load_dlt698_field_schema()
        self._update_gen_preview()

    def set_gen_mode(self, value: str):
        """切换组帧模式（predefined | custom | axdr）"""
        self.gen_mode = value
        self._update_gen_preview()

    def set_gen_field(self, idx, value: str):
        """设置组帧简单字段值（idx = gen_field_schema 索引）"""
        try:
            idx = int(idx)
        except (ValueError, TypeError):
            return
        if 0 <= idx < len(self.gen_field_values):
            self.gen_field_values[idx] = value
        self._update_gen_preview()

    def set_gen_sub_field(self, fi, si, value: str):
        """设置子字段值（fi = 字段索引，si = 子字段索引）"""
        try:
            fi, si = int(fi), int(si)
        except (ValueError, TypeError):
            return
        if 0 <= fi < len(self.gen_sub_fields) and 0 <= si < len(self.gen_sub_fields[fi]):
            self.gen_sub_fields[fi][si] = value
        self._update_gen_preview()

    def add_gen_list_row(self, fi):
        """为 list 字段（索引 fi）添加一行（默认值来自 schema item_fields）。

        注意：必须重建后整体回写 self.gen_list_rows[fi]（而非原地 .append），
        否则 Reflex 检测不到内层 list 变化，rx.foreach 不重渲染、UI 不新增行。
        """
        try:
            fi = int(fi)
        except (ValueError, TypeError):
            return
        if 0 <= fi < len(self.gen_field_schema):
            field = self.gen_field_schema[fi]
            defaults = [str(it.get("default", "")) for it in field.get("item_fields", [])]
            rows = list(self.gen_list_rows[fi]) if fi < len(self.gen_list_rows) else []
            rows.append(defaults)
            while len(self.gen_list_rows) <= fi:
                self.gen_list_rows.append([])
            self.gen_list_rows[fi] = rows
        self._update_gen_preview()

    def remove_gen_list_row(self, fi, row_idx):
        """删除 list 字段某一行（重建后整体回写，触发 UI 重渲染）"""
        try:
            fi, row_idx = int(fi), int(row_idx)
        except (ValueError, TypeError):
            return
        if 0 <= fi < len(self.gen_list_rows) and 0 <= row_idx < len(self.gen_list_rows[fi]):
            rows = list(self.gen_list_rows[fi])
            rows.pop(row_idx)
            self.gen_list_rows[fi] = rows
        self._update_gen_preview()

    def set_gen_list_item(self, fi, row_idx, item_idx, value: str):
        """设置 list 字段某行某项值（重建后整体回写，触发 UI 重渲染）"""
        try:
            fi, row_idx, item_idx = int(fi), int(row_idx), int(item_idx)
        except (ValueError, TypeError):
            return
        if (0 <= fi < len(self.gen_list_rows)
                and 0 <= row_idx < len(self.gen_list_rows[fi])
                and 0 <= item_idx < len(self.gen_list_rows[fi][row_idx])):
            rows = list(self.gen_list_rows[fi])
            rows[row_idx] = list(rows[row_idx])
            rows[row_idx][item_idx] = value
            self.gen_list_rows[fi] = rows
        self._update_gen_preview()


    def set_gen_axdr_fixed(self, key: str, value: str):
        """设置 698.45 A-XDR 固定字段（PIID/OI/属性/索引等）"""
        self.gen_axdr_fixed[key] = value
        self._update_gen_preview()

    def add_gen_custom_template(self):
        """自定义模板添加一行"""
        self.gen_custom_templates.append({
            "name": "", "length": 1, "ftype": "bytes",
            "endian": "little", "display": "hex", "reverse": False, "value": "",
        })

    def remove_gen_custom_template(self, idx: int):
        """自定义模板删除一行"""
        if 0 <= idx < len(self.gen_custom_templates):
            self.gen_custom_templates.pop(idx)

    def set_gen_custom_template(self, idx: int, key: str, value: str):
        """自定义模板设置某字段"""
        if 0 <= idx < len(self.gen_custom_templates):
            tpl = self.gen_custom_templates[idx]
            if key in ("length", "ftype", "endian", "display", "reverse"):
                if key == "length":
                    try:
                        tpl[key] = int(value) if value else 1
                    except ValueError:
                        tpl[key] = 1
                elif key == "reverse":
                    tpl[key] = value in ("true", "True", "1", "on")
                else:
                    tpl[key] = value
            else:
                tpl[key] = value

    def add_gen_axdr_item(self, parent_idx: str = ""):
        """A-XDR 添加一项（parent_idx 为点分路径，空表示根级）"""
        new_item = {"type": "unsigned", "tag": 0x11, "length": 0, "value": 0, "children": []}
        if not parent_idx:
            self.gen_axdr_items.append(new_item)
            return
        parts = [int(p) for p in parent_idx.split(".")]
        target = self.gen_axdr_items
        for p in parts[:-1]:
            target = target[p].get("children", [])
        if 0 <= parts[-1] < len(target):
            target[parts[-1]].setdefault("children", []).append(new_item)

    def remove_gen_axdr_item(self, idx: str):
        """A-XDR 删除一项（点分路径）"""
        if not idx:
            return
        parts = [int(p) for p in idx.split(".")]
        if len(parts) == 1:
            if 0 <= parts[0] < len(self.gen_axdr_items):
                self.gen_axdr_items.pop(parts[0])
            return
        target = self.gen_axdr_items
        for p in parts[:-1]:
            if 0 <= p < len(target):
                target = target[p].get("children", [])
            else:
                return
        if 0 <= parts[-1] < len(target):
            target.pop(parts[-1])

    def set_gen_axdr_item(self, idx: str, key: str, value: str):
        """A-XDR 设置某项的属性（key in tag/type/length/value）"""
        parts = [int(p) for p in idx.split(".")]
        target = self.gen_axdr_items
        for p in parts:
            if 0 <= p < len(target):
                target = target[p]
            else:
                return
        if key == "type":
            from frame_gen_utils import TYPE_TO_TAG, COMPOUND_TYPES
            target["type"] = value
            target["tag"] = TYPE_TO_TAG.get(value, target.get("tag", 0x11))
            if value in COMPOUND_TYPES:
                target.setdefault("children", [])
        elif key == "tag":
            try:
                target["tag"] = int(value, 0) if value else target.get("tag", 0x11)
            except ValueError:
                pass
        elif key == "length":
            try:
                target["length"] = int(value) if value else 0
            except ValueError:
                target["length"] = 0
        else:  # value
            target["value"] = value

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

    def set_gen_gdw_relay_addrs(self, value: str):
        """设置国网中继地址（逗号分隔）"""
        self.gen_gdw_relay_addrs_text = value
        self._update_gen_preview()

    def set_gen_dlt698_sa(self, key: str, value: str):
        """设置 698.45 SA/控制字段"""
        try:
            int_val = int(value) if value else 0
        except ValueError:
            int_val = 0
        if key == "addr_type":
            self.gen_dlt698_addr_type = int_val
        elif key == "logic_addr":
            self.gen_dlt698_logic_addr = int_val
        elif key == "addr_len":
            self.gen_dlt698_addr_len = int_val
        elif key == "seg":
            self.gen_dlt698_seg = int_val
        elif key == "sc":
            self.gen_dlt698_sc = int_val
        elif key == "func":
            self.gen_dlt698_func = int_val
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


    def _convert_enum_map(self, enum_map: Any) -> List[Dict[str, str]]:
        """把 enum_map 字典转为 Reflex 可遍历的 [{value,label}] 列表。

        GUI 中 enum_map 是 {int/str: 中文名} 字典；Reflex `rx.foreach` 只能遍历列表，
        故转换为有序列表。label 格式与 GUI 一致 `{注释} (0x{val:02X})`。
        """
        if not isinstance(enum_map, dict):
            return []
        items = []
        for k, text in enum_map.items():
            try:
                val = int(k)
            except (ValueError, TypeError):
                val = 0
            items.append({
                "value": str(k),
                "label": f"{text} (0x{val:02X})",
            })
        return items

    def _fill_gen_field_schema(self, fields: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """将源字段 dict 整体拷贝到 gen_field_schema，保留全部元信息。

        - `default`/`description` 转字符串供输入框绑定
        - 顶层字段与 sub_fields 的 `enum_map` 字典转为 [{value,label}] 列表（供 Reflex 遍历）
        """
        result = []
        for f in fields:
            item = dict(f)
            if "default" in item:
                item["default"] = str(item["default"])
            if "description" in item:
                item["description"] = str(item["description"])
            if "enum_map" in item:
                item["enum_map"] = self._convert_enum_map(item["enum_map"])
            if "sub_fields" in item:
                subs = []
                for sub in item["sub_fields"]:
                    s = dict(sub)
                    if "default" in s:
                        s["default"] = str(s["default"])
                    if "enum_map" in s:
                        s["enum_map"] = self._convert_enum_map(s["enum_map"])
                    subs.append(s)
                item["sub_fields"] = subs
            if "item_fields" in item:
                item_fields = []
                for it in item["item_fields"]:
                    iit = dict(it)
                    if "default" in iit:
                        iit["default"] = str(iit["default"])
                    if "enum_map" in iit:
                        iit["enum_map"] = self._convert_enum_map(iit["enum_map"])
                    item_fields.append(iit)
                item["item_fields"] = item_fields
            result.append(item)
        return result

    def _init_gen_editors(self):
        """命令切换/加载 schema 后初始化位置对齐的字段编辑器状态与渲染模型。"""
        self.gen_field_values = []
        self.gen_sub_fields = []
        self.gen_list_rows = []
        self.gen_field_meta = []
        self.gen_field_enum = []
        self.gen_field_items = []
        self.gen_field_items_enum = []
        self.gen_field_subs = []
        self.gen_field_subs_enum = []
        for f in self.gen_field_schema:
            # 简单字段默认值
            self.gen_field_values.append(str(f.get("default", "")))
            # 子字段默认值
            if "sub_fields" in f:
                self.gen_sub_fields.append([str(s.get("default", "")) for s in f.get("sub_fields", [])])
            else:
                self.gen_sub_fields.append([])
            # 列表行（空）
            self.gen_list_rows.append([])
            # —— 渲染模型 ——
            self.gen_field_meta.append({
                "name": f.get("name", ""),
                "type": f.get("type", "bytes"),
                "default": str(f.get("default", "")),
                "description": str(f.get("description", "")),
                "has_sub": "1" if "sub_fields" in f else "0",
                "has_list": "1" if f.get("type") == "list" else "0",
            })
            # enum 选项
            self.gen_field_enum.append(
                [dict(o) for o in f.get("enum_map", [])] if f.get("type") == "enum" else []
            )
            # item_fields（list）
            item_fields = f.get("item_fields", [])
            items_meta = []
            items_enum = []
            for it in item_fields:
                items_meta.append({
                    "name": it.get("name", ""),
                    "type": it.get("type", "bytes"),
                    "default": str(it.get("default", "")),
                })
                items_enum.append([dict(o) for o in it.get("enum_map", [])] if it.get("type") == "enum" else [])
            self.gen_field_items.append(items_meta)
            self.gen_field_items_enum.append(items_enum)
            # sub_fields
            subs_meta = []
            subs_enum = []
            for s in f.get("sub_fields", []):
                subs_meta.append({
                    "name": s.get("name", ""),
                    "type": s.get("type", "bytes"),
                    "default": str(s.get("default", "")),
                })
                subs_enum.append([dict(o) for o in s.get("enum_map", [])] if s.get("type") == "enum" else [])
            self.gen_field_subs.append(subs_meta)
            self.gen_field_subs_enum.append(subs_enum)

    def _load_di_field_schema(self):
        """加载南网 DI 字段 schema 到 gen_field_schema（保留完整字段 dict）"""
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
                self.gen_field_schema = self._fill_gen_field_schema(schema["fields"])
            else:
                self.gen_field_schema = []
            self._init_gen_editors()
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
                self.gen_field_schema = self._fill_gen_field_schema(schema["fields"])
            else:
                self.gen_field_schema = []
            self._init_gen_editors()
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
            self.gen_field_schema = self._fill_gen_field_schema(fields)
            self._init_gen_editors()
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
            for i, f in enumerate(self.gen_field_schema):
                val = self.gen_field_values[i] if i < len(self.gen_field_values) else f.get("default", "")
                parts.append(f"  {f['name']}: {val}")

        self.gen_preview = "\n".join(parts) if parts else "请选择命令类型"

        # 实时回读预览：尝试按当前状态重新生成帧并解析（失败静默，不打断输入）
        try:
            frame_bytes = self._build_frame_bytes()
            self.gen_result_hex = " ".join(f"{b:02X}" for b in frame_bytes)
            self._refresh_gen_preview()
        except Exception:
            # 状态不完整时清空预览，保留文本摘要
            self.gen_preview_rows = []

    def _refresh_gen_preview(self):
        """实时解析回读预览：把生成的帧字节送回解析器产出一行行字段。"""
        if not self.gen_result_hex:
            self.gen_preview_rows = []
            return
        try:
            frame_bytes = bytes.fromhex("".join(self.gen_result_hex.split()))
            parser = self._get_parser()
            result = parser.parse_to_table(frame_bytes)
            rows = []
            for idx, row in enumerate(result):
                if len(row) < 4:
                    continue
                field_name = str(row[0]) if row[0] else ""
                indent_level = 0
                stripped = field_name.lstrip()
                if stripped != field_name:
                    indent_level = (len(field_name) - len(stripped)) // 2
                    prefix = "　" * (indent_level - 1) + "└ " if indent_level > 0 else ""
                    display_field = prefix + stripped
                else:
                    display_field = field_name
                rows.append({
                    "id": idx,
                    "field": display_field,
                    "raw": str(row[1]) if row[1] else "",
                    "parsed": str(row[2]) if row[2] else "",
                    "comment": str(row[3]) if row[3] else "",
                    "is_child": indent_level > 0,
                    "indent": indent_level,
                })
            self.gen_preview_rows = rows
        except Exception:
            self.gen_preview_rows = []

    def _build_frame_bytes(self) -> bytes:
        """按当前状态生成帧字节（同步，供 generate_frame 与实时预览共用）。

        协议/模式不支持或必需命令未选择时抛 ValueError，由调用方提示。
        """
        p = self.current_protocol

        if p == 0:  # 南网
            if not self.gen_di_key:
                raise ValueError("请先选择 DI")
            from frame_gen_utils import collect_field_values, generate_custom_data
            from send_frame_lib import ProtocolFrameGenerator
            gen = ProtocolFrameGenerator()
            key = self.gen_di_key
            di_key = (int(key[0:2], 16), int(key[2:4], 16), int(key[4:6], 16), int(key[6:8], 16))

            src_text = self.gen_src_addr.strip().replace(" ", "")
            dst_text = self.gen_dst_addr.strip().replace(" ", "")
            if len(src_text) != 12 or len(dst_text) != 12:
                raise ValueError("源地址和目的地址必须为12位十六进制字符（6字节）")
            try:
                src = bytes.fromhex(src_text)
                dst = bytes.fromhex(dst_text)
            except ValueError:
                raise ValueError("地址格式错误，请输入有效的十六进制字符串")

            if self.gen_mode == "custom":
                data = generate_custom_data(self.gen_custom_templates)
                di3, di2, di1, di0 = di_key
                return gen._build_frame(
                    di3, di2, di1, di0,
                    src_addr=src, dst_addr=dst, data=data,
                    dir_flag=self.gen_dir, prm=self.gen_prm, add_flag=1,
                )
            schema = gen.get_di_schema(di_key)
            field_values = collect_field_values(
                schema.get("fields", []) if schema else [],
                self.gen_field_values, self.gen_list_rows, self.gen_sub_fields,
            )
            return gen.generate_frame(
                di_key=di_key,
                field_values=field_values,
                src_addr=src,
                dst_addr=dst,
                dir_flag=self.gen_dir,
                prm=self.gen_prm,
                add_flag=1,
            )

        if p == 7:  # 国网
            if not self.gen_afn_fn:
                raise ValueError("请先选择 AFN+Fn")
            from frame_gen_utils import collect_field_values
            from gdw_send_frame_lib import GDWFrameGenerator
            gen = GDWFrameGenerator()
            afn = int(self.gen_afn_fn[0:2], 16)
            fn = int(self.gen_afn_fn[2:4], 16)

            schema = gen.get_schema(afn, fn)
            field_values = collect_field_values(
                schema.get("fields", []) if schema else [],
                self.gen_field_values, self.gen_list_rows, self.gen_sub_fields,
            )

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

            relay_addrs = [a.strip() for a in self.gen_gdw_relay_addrs_text.split(",") if a.strip()]
            return gen.generate_frame(
                afn=afn,
                fn=fn,
                field_values=field_values,
                info_config=info_config,
                src_addr=self.gen_src_addr,
                dst_addr=self.gen_dst_addr,
                relay_addrs=relay_addrs,
            )

        if p == 8:  # 698.45
            if not self.gen_dlt698_apdu:
                raise ValueError("请先选择 APDU 类型")
            from frame_gen_utils import (
                collect_field_values, build_dlt698_sa,
                build_dlt698_axdr_apdu, encode_axdr_items,
            )
            from dl_t698_45_frame_gen import DLT69845FrameGenerator
            from dl_t698_45_frame_schema import DLT69845_FIELD_SCHEMA
            gen = DLT69845FrameGenerator()

            apdu_type = self.gen_dlt698_apdu
            sub_type = self.gen_dlt698_sub or "get_normal"
            schema_key = (apdu_type, sub_type)
            schema = DLT69845_FIELD_SCHEMA.get(schema_key, {})

            sa = build_dlt698_sa(
                self.gen_dlt698_addr_type, self.gen_dlt698_logic_addr,
                self.gen_dlt698_addr_len, self.gen_dlt698_sa_raw,
            )
            if not sa:
                raise ValueError("请输入有效的SA地址")
            ca = self.gen_seq & 0xFF

            if self.gen_mode == "axdr":
                axdr_data = encode_axdr_items(self.gen_axdr_items)
                field_values = collect_field_values(
                    schema.get("fields", []), self.gen_field_values,
                    self.gen_list_rows, self.gen_sub_fields,
                )
                priority = int(self.gen_axdr_fixed.get("PIID_优先级", 0) or 0) & 0x01
                seq = int(self.gen_axdr_fixed.get("PIID_序号", 1) or 1) & 0x7F
                piid = (priority << 7) | seq
                oi_hex = self.gen_axdr_fixed.get("OI", "0000")
                apdu = build_dlt698_axdr_apdu(
                    apdu_type, sub_type, piid, oi_hex,
                    field_values, axdr_data,
                    is_custom=(apdu_type == "_custom_"),
                )
                return gen._assemble_frame(
                    sa, ca,
                    gen.build_control(
                        dir_bit=self.gen_dir, prm_bit=self.gen_prm,
                        seg_bit=self.gen_dlt698_seg, sc_bit=self.gen_dlt698_sc,
                        func_code=self.gen_dlt698_func,
                    ),
                    apdu,
                )
            field_values = collect_field_values(
                schema.get("fields", []), self.gen_field_values,
                self.gen_list_rows, self.gen_sub_fields,
            )
            return gen.generate_frame(
                apdu_type=apdu_type,
                sub_type=sub_type,
                field_values=field_values,
                sa=sa,
                ca=ca,
                dir_bit=self.gen_dir,
                prm_bit=self.gen_prm,
                seg_bit=self.gen_dlt698_seg,
                sc_bit=self.gen_dlt698_sc,
                func_code=self.gen_dlt698_func,
            )

        raise ValueError(f"协议 {p} 暂不支持组帧")

    async def generate_frame(self):
        """生成报文帧（按 gen_mode 分派：predefined / custom / axdr）"""
        self.is_loading = True
        self.message = ""
        self.gen_result = ""
        self.gen_result_hex = ""

        try:
            frame_bytes = self._build_frame_bytes()
            self.gen_result_hex = " ".join(f"{b:02X}" for b in frame_bytes)
            self.gen_result = f"生成成功！共 {len(frame_bytes)} 字节\n\n{self.gen_result_hex}"
            self._refresh_gen_preview()
            self.message = "组帧完成"
            self.message_type = "success"
        except ValueError as e:
            self.message = str(e)
            self.message_type = "warning"
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
    # ── 预设命令按钮 ─────────────────────────────────────────
    def _load_preset_buttons(self):
        """加载预设按钮（协议 0 读 NW_command.json，协议 7 读 GW_command.json）"""
        try:
            import json as _json
            from pathlib import Path
            p = self.current_protocol
            if p not in (0, 7):
                self.gen_preset_buttons = []
                self.gen_preset_groups = []
                return
            fname = "NW_command.json" if p == 0 else "GW_command.json"
            path = Path(ROOT) / fname
            if not path.exists():
                self.gen_preset_buttons = []
                self.gen_preset_groups = []
                return
            data = _json.loads(path.read_text(encoding="utf-8"))
            commands = data.get("commands", []) if isinstance(data, dict) else []
            buttons = []
            groups = []
            for c in commands:
                buttons.append({
                    "name": c.get("button_name", ""),
                    "group": c.get("group_name", "其他"),
                    "frame_hex": c.get("frame_hex", ""),
                    "id": c.get("id", ""),
                    "description": c.get("description", ""),
                })
                g = c.get("group_name", "其他")
                if g not in groups:
                    groups.append(g)
            self.gen_preset_buttons = buttons
            self.gen_preset_groups = groups
        except Exception:
            self.gen_preset_buttons = []
            self.gen_preset_groups = []

    def apply_preset(self, frame_hex: str):
        """应用预设命令（把 frame_hex 填入结果区并刷新预览）"""
        self.gen_result_hex = frame_hex
        self.gen_result = f"预设命令\n\n{frame_hex}"
        self._refresh_gen_preview()
        self.message = "已应用预设命令"
        self.message_type = "success"

    async def save_preset(self):
        """保存当前生成结果到预设命令 JSON（名称/分组取自表单字段）"""
        name = self.gen_preset_name
        group = self.gen_preset_group
        if not name.strip():
            self.message = "请输入预设命令名称"
            self.message_type = "warning"
            return
        if not self.gen_result_hex:
            self.message = "请先生成一条报文"
            self.message_type = "warning"
            return
        try:
            import json as _json
            import uuid
            from pathlib import Path
            p = self.current_protocol
            if p not in (0, 7):
                self.message = "当前协议不支持预设命令"
                self.message_type = "warning"
                return
            fname = "NW_command.json" if p == 0 else "GW_command.json"
            path = Path(ROOT) / fname
            data = {}
            if path.exists():
                data = _json.loads(path.read_text(encoding="utf-8"))
            commands = data.get("commands", []) if isinstance(data, dict) else []
            new_cmd = {
                "protocol": "south" if p == 0 else "gdw",
                "button_name": name.strip(),
                "group_name": group.strip() or "常用查询",
                "frame_hex": self.gen_result_hex,
                "description": "",
                "config": {},
                "id": str(uuid.uuid4())[:8],
            }
            commands.append(new_cmd)
            data["commands"] = commands
            path.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.gen_preset_name = ""
            self.gen_preset_group = ""
            self._load_preset_buttons()
            self.message = "预设命令已保存"
            self.message_type = "success"
        except Exception as e:
            self.message = f"保存预设失败: {str(e)}"
            self.message_type = "error"

    def set_gen_preset_save_field(self, key: str, value: str):
        """设置保存预设表单字段（name/group）"""
        if key == "name":
            self.gen_preset_name = value
        elif key == "group":
            self.gen_preset_group = value

    def set_gen_preset_search(self, value: str):
        """设置预设命令搜索过滤词"""
        self.gen_preset_search = value

    def start_edit_preset(self, cmd_id: str):
        """进入预设编辑模式（回填当前名称/分组）"""
        for b in self.gen_preset_buttons:
            if b.get("id") == cmd_id:
                self.gen_preset_edit_id = cmd_id
                self.gen_preset_edit_name = b.get("name", "")
                self.gen_preset_edit_group = b.get("group", "")
                return

    def set_gen_preset_edit_field(self, key: str, value: str):
        """设置预设编辑表单字段（name/group）"""
        if key == "name":
            self.gen_preset_edit_name = value
        elif key == "group":
            self.gen_preset_edit_group = value

    def cancel_edit_preset(self):
        """取消预设编辑"""
        self.gen_preset_edit_id = ""

    async def save_preset_edit(self):
        """保存预设编辑（改名/分组）"""
        cmd_id = self.gen_preset_edit_id
        if not cmd_id or not self.gen_preset_edit_name.strip():
            self.message = "请输入预设命令名称"
            self.message_type = "warning"
            return
        try:
            import json as _json
            from pathlib import Path
            p = self.current_protocol
            if p not in (0, 7):
                return
            fname = "NW_command.json" if p == 0 else "GW_command.json"
            path = Path(ROOT) / fname
            if not path.exists():
                return
            data = _json.loads(path.read_text(encoding="utf-8"))
            commands = data.get("commands", []) if isinstance(data, dict) else []
            for c in commands:
                if c.get("id") == cmd_id:
                    c["button_name"] = self.gen_preset_edit_name.strip()
                    c["group_name"] = self.gen_preset_edit_group.strip() or "常用查询"
                    break
            data["commands"] = commands
            path.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.gen_preset_edit_id = ""
            self._load_preset_buttons()
            self.message = "预设命令已更新"
            self.message_type = "success"
        except Exception as e:
            self.message = f"更新预设失败: {str(e)}"
            self.message_type = "error"

    async def remove_preset(self, cmd_id: str):
        """删除预设命令"""
        if not cmd_id:
            return
        try:
            import json as _json
            from pathlib import Path
            p = self.current_protocol
            if p not in (0, 7):
                return
            fname = "NW_command.json" if p == 0 else "GW_command.json"
            path = Path(ROOT) / fname
            if not path.exists():
                return
            data = _json.loads(path.read_text(encoding="utf-8"))
            commands = data.get("commands", []) if isinstance(data, dict) else []
            commands = [c for c in commands if c.get("id") != cmd_id]
            data["commands"] = commands
            path.write_text(_json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            if self.gen_preset_edit_id == cmd_id:
                self.gen_preset_edit_id = ""
            self._load_preset_buttons()
            self.message = "预设命令已删除"
            self.message_type = "success"
        except Exception as e:
            self.message = f"删除预设失败: {str(e)}"
            self.message_type = "error"

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
            self._load_preset_buttons()

    # ── 报文工具 ─────────────────────────────────────────────
    def set_tool_input(self, value: str):
        self.tool_input = value

    def set_tool_hex_mode(self, value: bool):
        self.tool_hex_mode = value

    def set_tool_endian(self, value: str):
        self.tool_endian = value

    def clear_tool(self):
        self.tool_input = ""
        self.tool_output = ""

    def copy_tool_output(self):
        return rx.set_clipboard(self.tool_output)

    def run_tool(self, op: str):
        """执行报文工具操作"""
        if not self.tool_input.strip():
            self.tool_output = "请输入内容"
            return
        func = getattr(web_utils, f"tool_{op}", None)
        if op == "hex_to_decimal":
            self.tool_output = web_utils.tool_hex_to_decimal(
                self.tool_input, little_endian=(self.tool_endian == "little")
            )
            return
        if op == "ascii_to_hex":
            self.tool_output = web_utils.tool_ascii_to_hex(self.tool_input)
            return
        if op == "char_count":
            self.tool_output = web_utils.tool_char_count(self.tool_input)
            return
        if op in ("to_upper", "to_lower", "remove_spaces"):
            self.tool_output = func(self.tool_input) if func else "未知操作"
            return
        # 默认按 HEX 解析处理
        if func:
            try:
                self.tool_output = func(self.tool_input)
            except Exception as e:
                self.tool_output = f"错误: {e}"
        else:
            self.tool_output = f"未知操作: {op}"


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
                rx.heading("多协议解析平台", size="4", color="white", font_weight="bold"),
                spacing="2",
            ),
            rx.spacer(),
            # 协议选择器（索引号对齐 PySide6 版）
            rx.el.select(
                rx.el.option("[0] 南网协议 (Q/CSG1209021-2019)", value="0"),
                rx.el.option("[1] PLC RF协议 (万胜海外 V1_04)", value="1"),
                rx.el.option("[2] HDLC/国网DLMS (IEC 62056-46)", value="2"),
                rx.el.option("[3] DLMS-APDU(国网)", value="3"),
                rx.el.option("[4] DLMS Wrapper裸报文", value="4"),
                rx.el.option("[5] DLMS-APDU裸报文", value="5"),
                rx.el.option("[6] DLT645-2007 电表协议", value="6"),
                rx.el.option("[7] 国网协议 (Q/GDW 10376.2-2024)", value="7"),
                rx.el.option("[8] 698.45协议 (DL/T 698.45-2017)", value="8"),
                rx.el.option("[9] 新一代载波协议 (通感一体化)", value="9"),
                rx.el.option("[10] 国网新一代双模通信互联互通", value="10"),
                rx.el.option("[11] HDC 1.0 双模互联互通 (Q/GDW 12087.42-2020)", value="11"),
                default_value="0",
                on_change=State.set_protocol,
                width="300px",
                class_name="rounded-md border border-white/30 bg-white/10 px-3 py-2 text-sm text-white focus:border-white/50",
            ),
            # 版本徽章
            rx.badge("v1.13.0", color_scheme="indigo", variant="soft", size="2"),
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
    """新一代载波/国网新一代/HDC 1.0 控制条（协议9/10/11显示）"""
    return rx.cond(
        (State.current_protocol == 9) | (State.current_protocol == 10) | (State.current_protocol == 11),
        rx.card(
            rx.hstack(
                rx.icon("sliders_horizontal", size=18, color="#2563eb"),
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
                # HDC 1.0（协议11）解析级别
                rx.cond(
                    State.current_protocol == 11,
                    rx.el.select(
                        rx.el.option("自动识别", value="auto"),
                        rx.el.option("FC+PB解析(完整MPDU)", value="fc_pb"),
                        rx.el.option("仅FC解析", value="fc_only"),
                        rx.el.option("仅MAC帧", value="mac_only"),
                        rx.el.option("仅物理块PB", value="pb_only"),
                        rx.el.option("FC+MAC头", value="fc_mac"),
                        rx.el.option("应用层报文", value="app"),
                        default_value="auto",
                        on_change=State.set_hdc10_level,
                        class_name="rounded border border-gray-300 px-2 py-1 text-sm",
                    ),
                ),
                # 国网新一代/HDC 1.0 通道下拉（PLC/HRF）
                rx.cond(
                    (State.current_protocol == 10) | (State.current_protocol == 11),
                    rx.hstack(
                        rx.text("通道:", size="2", font_weight="medium"),
                        rx.cond(
                            State.current_protocol == 10,
                            rx.el.select(
                                rx.el.option("PLC 载波", value="plc"),
                                rx.el.option("HRF 无线", value="hrf"),
                                default_value="plc",
                                on_change=State.set_gw_channel,
                                class_name="rounded border border-gray-300 px-2 py-1 text-sm",
                            ),
                            rx.el.select(
                                rx.el.option("PLC 载波", value="plc"),
                                rx.el.option("HRF 无线", value="hrf"),
                                default_value="plc",
                                on_change=State.set_hdc10_channel,
                                class_name="rounded border border-gray-300 px-2 py-1 text-sm",
                            ),
                        ),
                        spacing="2",
                        align="center",
                    ),
                ),
                # 剔除前/尾（仅协议9 有效，对齐 GUI）
                rx.cond(
                    State.current_protocol == 9,
                    rx.hstack(
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
                ),
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
                        rx.icon("circle_check", size=20, color="#059669"),
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
                # ── 拖拽上传区域 ──
                rx.upload(
                    rx.vstack(
                        rx.hstack(
                            rx.icon("upload", size=20, color="#2563eb"),
                            rx.text("将日志文件拖拽到此处，或点击选择文件", size="2", font_weight="medium"),
                            spacing="2",
                            align="center",
                        ),
                        rx.text("支持 .log / .txt / 纯文本文件；大文件会自动分块解析", size="1", color="gray"),
                        spacing="1",
                        align="center",
                        justify="center",
                    ),
                    on_drop=State.handle_batch_upload,
                    multiple=False,
                    max_files=1,
                    max_size=50 * 1024 * 1024,
                    class_name="rounded-lg border-2 border-dashed border-blue-300 bg-blue-50/50 p-4 w-full hover:border-blue-500 transition-colors",
                ),
                # 已加载文件信息（文件内容存后端，仅显示元信息）
                rx.cond(
                    State.batch_upload_name != "",
                    rx.card(
                        rx.hstack(
                            rx.icon("file_check", size=16, color="#059669"),
                            rx.vstack(
                                rx.text(
                                    f"{State.batch_upload_name}（{round(State.batch_upload_size / (1024 * 1024), 2)} MB，{State.batch_file_lines} 行）",
                                    size="1", font_weight="medium",
                                ),
                                rx.text("文件内容已保存在服务器端（不加载到页面），点击「批量解析」即可处理", size="1", color="gray"),
                                spacing="0",
                            ),
                            rx.spacer(),
                            rx.button(
                                rx.icon("trash_2", size=14),
                                "移除文件",
                                on_click=State.remove_batch_file,
                                size="1",
                                variant="soft",
                                color_scheme="red",
                            ),
                            spacing="2",
                            align="center",
                            width="100%",
                        ),
                        variant="surface",
                        padding="2",
                        width="100%",
                    ),
                ),
                rx.text_area(
                    placeholder="粘贴监控日志或十六进制报文，每行一帧（已上传文件时以文件内容为解析源）",
                    value=State.batch_input,
                    on_change=State.set_batch_input,
                    height="120px",
                    width="100%",
                    font_family="monospace",
                    font_size="13px",
                ),
                # ── 预处理面板（pp_cli 命令链）──
                rx.card(
                    rx.vstack(
                        rx.hstack(
                            rx.icon("wand", size=16, color="#7c3aed"),
                            rx.text("预处理（命令链）", size="2", font_weight="semibold"),
                            rx.spacer(),
                            rx.text("支持: find / excluding / replace / head / tail / skip / hex_extract / tcp_extract / merge_payloads / dedup",
                                    size="1", color="gray"),
                            spacing="2",
                            align="center",
                        ),
                        rx.hstack(
                            rx.el.select(
                                rx.el.option("-- 选择预设 --", value="__custom__"),
                                rx.el.option("提取 tcp data 帧", value="find tcp data: tcp_extract"),
                                rx.el.option("提取监控日志帧", value="find > 接收机 Has Get hex_extract"),
                                rx.el.option("合并跨行 payload", value="merge_payloads"),
                                rx.el.option("提取最长 hex 序列", value="hex_extract"),
                                rx.el.option("去重复行", value="dedup"),
                                rx.el.option("过滤含 60F0 的行", value="find 60F0"),
                                default_value="__custom__",
                                on_change=State.apply_pp_preset,
                                width="220px",
                                class_name="rounded border border-gray-300 px-2 py-1 text-sm",
                            ),
                            rx.input(
                                placeholder="如: find 60F0 hex_extract（管道式，空格分隔命令）",
                                value=State.batch_pp_commands,
                                on_change=State.set_batch_pp_commands,
                                width="100%",
                                font_family="monospace",
                                size="1",
                            ),
                            rx.button(
                                rx.icon("play", size=14),
                                "执行",
                                on_click=State.run_preprocess,
                                color_scheme="violet",
                                size="1",
                                variant="soft",
                            ),
                            rx.button(
                                rx.icon("eraser", size=14),
                                "清空",
                                on_click=State.clear_preprocess,
                                size="1",
                                variant="ghost",
                            ),
                            spacing="2",
                            width="100%",
                            align="center",
                        ),
                        rx.cond(
                            State.batch_pp_last_result != "",
                            rx.text(State.batch_pp_last_result, size="1", color="violet"),
                        ),
                        spacing="2",
                        width="100%",
                    ),
                    width="100%",
                    variant="surface",
                    padding="2",
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
                    rx.button(
                        rx.icon("download", size=16),
                        "导出JSON",
                        on_click=State.export_batch_json,
                        variant="outline",
                        color_scheme="green",
                        size="2",
                    ),
                    rx.button(
                        rx.icon("download", size=16),
                        "导出CSV",
                        on_click=State.export_batch_csv,
                        variant="outline",
                        color_scheme="green",
                        size="2",
                    ),
                    rx.spacer(),
                    rx.text(f"共 {State.batch_results.length()} 帧", size="1", color="gray"),
                    spacing="3",
                ),
                # ── 解析进度条 ──
                rx.cond(
                    (State.batch_total > 0) & (State.batch_progress < State.batch_total),
                    rx.hstack(
                        rx.progress(
                            value=State.batch_progress,
                            max=State.batch_total,
                            width="100%",
                            size="1",
                            color_scheme="blue",
                        ),
                        rx.text(
                            f"{State.batch_progress} / {State.batch_total}",
                            size="1", color="gray", white_space="nowrap",
                        ),
                        spacing="2",
                        width="100%",
                        align="center",
                    ),
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
                        rx.vstack(
                            rx.scroll_area(
                                rx.vstack(
                                    rx.foreach(
                                        State.batch_results[: State.batch_display_limit],
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
                                height="360px",
                                width="100%",
                            ),
                            # 超出显示上限提示（导出仍包含全部）
                            rx.cond(
                                State.batch_total_frames > State.batch_display_limit,
                                rx.text(
                                    f"仅显示前 {State.batch_display_limit} 条，共 {State.batch_total_frames} 帧（导出包含全部）",
                                    size="1", color="amber", font_weight="medium",
                                ),
                            ),
                            spacing="1",
                            width="100%",
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

def _oi_options() -> list:
    """698.45 OI 预设选项（供 oi 字段下拉）"""
    try:
        from dl_t698_45_frame_schema import OI_PRESET_LIST
        return [{"value": f"0x{v:04X}", "label": f"{name} (0x{v:04X})"} for v, name in OI_PRESET_LIST]
    except Exception:
        return []


def _axdr_type_options() -> list:
    """A-XDR 类型下拉选项"""
    from frame_gen_utils import A_XDR_TYPE_LIST
    return [{"value": name, "label": f"{desc} (0x{tag:02X})"} for name, tag, desc in A_XDR_TYPE_LIST]

def _is_compound(t) -> bool:
    """A-XDR 复合类型判断（返回 Var 布尔，供 rx.cond）"""
    return rx.match(t, ("array", True), ("structure", True), False)


def _is_var_len(t) -> bool:
    """A-XDR 变长类型判断（返回 Var 布尔，供 rx.cond）"""
    return rx.match(
        t,
        ("array", True), ("structure", True), ("octet-string", True),
        ("visible-string", True), ("UTF8-string", True), ("bit-string", True),
        False,
    )
def _searchable_select(
    label: str,
    search_query: Any,
    set_search: Any,
    filtered: Any,
    on_select: Any,
    selected: Any,
    placeholder: str,
) -> rx.Component:
    """可搜索下拉：输入框实时过滤 + 点击选择（对齐 GUI QCompleter 行为）

    search_query / filtered / selected 为 State Var；set_search / on_select 为事件。
    过滤结果统一为 [{"value": ..., "label": ...}]。
    """
    return rx.vstack(
        rx.hstack(
            rx.text(label, size="2", font_weight="medium", width="60px"),
            rx.input(
                placeholder=placeholder,
                value=search_query,
                on_change=set_search,
                class_name="flex-1 rounded border border-gray-300 px-3 py-2",
            ),
            spacing="2",
            width="100%",
        ),
        # 已选提示
        rx.cond(
            selected != "",
            rx.hstack(
                rx.icon("check", size=14, color="#16a34a"),
                rx.text("已选: ", size="1", color="#16a34a"),
                rx.text(selected, size="1", color="#16a34a", font_family="monospace"),
                spacing="1",
            ),
        ),
        # 过滤结果列表（仅搜索时有）
        rx.cond(
            search_query != "",
            rx.box(
                rx.cond(
                    filtered.length() > 0,
                    rx.scroll_area(
                        rx.vstack(
                            rx.foreach(
                                filtered,
                                lambda opt: rx.button(
                                    opt["label"],
                                    on_click=on_select(opt["value"]),
                                    variant="ghost",
                                    size="1",
                                    width="100%",
                                    text_align="left",
                                    justify="start",
                                    class_name="hover:bg-blue-50",
                                ),
                            ),
                            spacing="1",
                        ),
                        max_height="180px",
                        class_name="w-full",
                    ),
                    rx.text("无匹配选项", size="1", color="gray"),
                ),
                class_name="w-full rounded border border-gray-200",
            ),
        ),
        spacing="2",
        width="100%",
    )


def _field_input(f: Any = None, name: str = "", ftype: str = "bytes", default: str = "",
                 enum_map: Any = None, on_change=None, placeholder: str = "",
                 monospace: bool = True) -> rx.Component:
    """按字段类型渲染单个输入控件（用于顶层字段与列表项字段）。"""
    if ftype == "enum":
        opts = enum_map or []
        return rx.el.select(
            rx.el.option("请选择", value=""),
            rx.foreach(opts, lambda o: rx.el.option(o["label"], value=o["value"])),
            default_value=str(default),
            on_change=on_change,
            class_name="w-full rounded border border-gray-300 px-3 py-1.5",
            size="1",
        )
    if ftype in ("uint8", "uint16", "uint32"):
        return rx.input(
            value=State.gen_fields[name].to(str) if name else default,
            on_change=on_change,
            placeholder=default,
            font_family="monospace",
            size="1",
            type="number",
        )
    return rx.input(
        value=State.gen_fields[name].to(str) if name else default,
        on_change=on_change,
        placeholder=placeholder or default,
        font_family="monospace",
        size="1",
    )


def frame_gen_tab() -> rx.Component:
    """协议组帧（南网/国网/698.45）"""

    # ── 模式选择（predefined / custom / axdr）──
    def mode_selector() -> rx.Component:
        return rx.cond(
            (State.current_protocol == 0) | (State.current_protocol == 7) | (State.current_protocol == 8),
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("layers", size=18, color="#2563eb"),
                        rx.heading("组帧模式", size="3", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.hstack(
                        rx.cond(
                            State.current_protocol == 8,
                            # 698.45：predefined / axdr（custom 禁用，对齐 GUI :644）
                            rx.hstack(
                                rx.button("预定字段", on_click=lambda: State.set_gen_mode("predefined"),
                                          color_scheme=rx.cond(State.gen_mode == "predefined", "blue", "gray"),
                                          variant=rx.cond(State.gen_mode == "predefined", "solid", "soft"), size="2"),
                                rx.button("A-XDR", on_click=lambda: State.set_gen_mode("axdr"),
                                          color_scheme=rx.cond(State.gen_mode == "axdr", "purple", "gray"),
                                          variant=rx.cond(State.gen_mode == "axdr", "solid", "soft"), size="2"),
                                spacing="2",
                            ),
                            # 南网/国网：predefined / custom
                            rx.hstack(
                                rx.button("预定字段", on_click=lambda: State.set_gen_mode("predefined"),
                                          color_scheme=rx.cond(State.gen_mode == "predefined", "blue", "gray"),
                                          variant=rx.cond(State.gen_mode == "predefined", "solid", "soft"), size="2"),
                                rx.button("自定义模板", on_click=lambda: State.set_gen_mode("custom"),
                                          color_scheme=rx.cond(State.gen_mode == "custom", "orange", "gray"),
                                          variant=rx.cond(State.gen_mode == "custom", "solid", "soft"), size="2"),
                                spacing="2",
                            ),
                        ),
                        spacing="2",
                    ),
                    spacing="3",
                    width="100%",
                ),
                width="100%",
            ),
        )

    # ── 预设命令按钮 ──
    def preset_panel() -> rx.Component:
        return rx.cond(
            (State.current_protocol == 0) | (State.current_protocol == 7),
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("bookmark", size=18, color="#2563eb"),
                        rx.heading("预设命令", size="3", font_weight="semibold"),
                        rx.spacer(),
                        rx.input(
                            value=State.gen_preset_search,
                            on_change=State.set_gen_preset_search,
                            placeholder="搜索命令...",
                            size="1",
                            width="180px",
                        ),
                        spacing="2",
                    ),
                    rx.cond(
                        State.gen_preset_buttons.length() > 0,
                        rx.foreach(
                            State.gen_preset_groups,
                            lambda g: rx.vstack(
                                rx.text(g, size="2", font_weight="semibold", color="gray"),
                                rx.flex(
                                    rx.foreach(
                                        State.gen_preset_buttons,
                                        lambda b: rx.cond(
                                            (b["group"] == g) & (
                                                b["name"].contains(State.gen_preset_search)
                                                | b["group"].contains(State.gen_preset_search)
                                            ),
                                            rx.hstack(
                                                rx.button(
                                                    b["name"],
                                                    on_click=lambda: State.apply_preset(b["frame_hex"]),
                                                    variant="outline", size="1",
                                                ),
                                                rx.cond(
                                                    State.gen_preset_edit_id == b["id"],
                                                    rx.hstack(
                                                        rx.input(
                                                            value=State.gen_preset_edit_name,
                                                            on_change=lambda v: State.set_gen_preset_edit_field("name", v),
                                                            size="1", width="120px", placeholder="名称",
                                                        ),
                                                        rx.input(
                                                            value=State.gen_preset_edit_group,
                                                            on_change=lambda v: State.set_gen_preset_edit_field("group", v),
                                                            size="1", width="110px", placeholder="分组",
                                                        ),
                                                        rx.button(
                                                            "保存",
                                                            on_click=State.save_preset_edit,
                                                            size="1", color_scheme="green",
                                                        ),
                                                        rx.button(
                                                            "取消",
                                                            on_click=State.cancel_edit_preset,
                                                            size="1", variant="ghost",
                                                        ),
                                                        spacing="1",
                                                        align="center",
                                                    ),
                                                    rx.hstack(
                                                        rx.button(
                                                            rx.icon("pencil", size=12),
                                                            on_click=lambda: State.start_edit_preset(b["id"]),
                                                            variant="ghost", size="1",
                                                        ),
                                                        rx.button(
                                                            rx.icon("trash", size=12),
                                                            on_click=lambda: State.remove_preset(b["id"]),
                                                            variant="ghost", size="1", color_scheme="red",
                                                        ),
                                                        spacing="1",
                                                        align="center",
                                                    ),
                                                ),
                                                spacing="1",
                                                align="center",
                                            ),
                                        ),
                                    ),
                                    spacing="1",
                                ),
                                spacing="2",
                            ),
                        ),
                        rx.text("暂无预设命令", size="2", color="gray"),
                    ),
                    rx.divider(),
                    rx.hstack(
                        rx.text("添加到预设:", size="2", font_weight="medium"),
                        rx.input(
                            value=State.gen_preset_name,
                            on_change=lambda v: State.set_gen_preset_save_field("name", v),
                            placeholder="命令名称",
                            size="1",
                            width="150px",
                        ),
                        rx.input(
                            value=State.gen_preset_group,
                            on_change=lambda v: State.set_gen_preset_save_field("group", v),
                            placeholder="分组(默认常用查询)",
                            size="1",
                            width="170px",
                        ),
                        rx.button(
                            rx.icon("plus", size=14),
                            "保存",
                            on_click=State.save_preset,
                            size="1",
                            color_scheme="blue",
                        ),
                        spacing="2",
                        align="center",
                    ),
                    spacing="3",
                    width="100%",
                ),
                width="100%",
            ),
        )

    # ── 动态字段表单（按字段类型分派）──
    def dynamic_fields() -> rx.Component:
        return rx.cond(
            State.gen_field_meta.length() > 0,
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("list_tree", size=18, color="#2563eb"),
                        rx.heading("数据字段", size="3", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.grid(
                        rx.foreach(
                            State.gen_field_meta,
                            lambda f, i: rx.vstack(
                                rx.hstack(
                                    rx.text(f["name"], size="1", font_weight="medium"),
                                    rx.badge(f["type"], variant="soft", size="1", color_scheme="gray"),
                                    spacing="1",
                                ),
                                rx.cond(
                                    f["has_list"] == "1",
                                    _list_editor(i),
                                    rx.cond(
                                        f["has_sub"] == "1",
                                        _sub_fields_editor(i),
                                        _simple_field_editor(i),
                                    ),
                                ),
                                rx.cond(f["description"] != "", rx.text(f["description"], size="1", color="gray")),
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
    # 简单字段编辑器（uint/enum/bytes/ascii/bcd/oi/oad_list），i = 字段索引
    def _simple_field_editor(i: int) -> rx.Component:
        return rx.cond(
            State.gen_field_meta[i]["type"] == "enum",
            rx.el.select(
                rx.el.option("请选择", value=""),
                rx.foreach(State.gen_field_enum[i], lambda o: rx.el.option(o["label"], value=o["value"])),
                default_value=State.gen_field_meta[i]["default"],
                on_change=lambda val, idx=i: State.set_gen_field(idx, val),
                class_name="w-full rounded border border-gray-300 px-3 py-1.5",
                size="1",
            ),
            rx.cond(
                State.gen_field_meta[i]["type"] == "oi",
                rx.el.select(
                    rx.el.option("-- 选择OI --", value=""),
                    rx.foreach(_oi_options(), lambda o: rx.el.option(o["label"], value=o["value"])),
                    default_value=State.gen_field_meta[i]["default"],
                    on_change=lambda val, idx=i: State.set_gen_field(idx, val),
                    class_name="w-full rounded border border-gray-300 px-3 py-1.5",
                    size="1",
                ),
                rx.cond(
                    State.gen_field_meta[i]["type"] == "oad_list",
                    rx.text_area(
                        value=State.gen_field_values[i].to(str),
                        on_change=lambda val, idx=i: State.set_gen_field(idx, val),
                        placeholder="每行一个 OAD，如 00000100",
                        font_family="monospace",
                        size="1",
                        width="100%",
                    ),
                    rx.input(
                        value=State.gen_field_values[i].to(str),
                        on_change=lambda val, idx=i: State.set_gen_field(idx, val),
                        placeholder=State.gen_field_meta[i]["default"],
                        font_family="monospace",
                        size="1",
                    ),
                ),
            ),
        )

    # 子字段编辑器（位域），i = 字段索引
    def _sub_fields_editor(i: int) -> rx.Component:
        return rx.box(
            rx.text("由子字段组合", size="1", color="gray"),
            rx.flex(
                rx.foreach(
                    State.gen_field_subs[i],
                    lambda s, j: rx.vstack(
                        rx.text(s["name"], size="1", color="gray"),
                        rx.cond(
                            s["type"] == "enum",
                            rx.el.select(
                                rx.el.option("请选择", value=""),
                                rx.foreach(State.gen_field_subs_enum[i][j], lambda o: rx.el.option(o["label"], value=o["value"])),
                                default_value=s["default"],
                                on_change=lambda val, fi=i, si=j: State.set_gen_sub_field(fi, si, val),
                                class_name="w-full rounded border border-gray-300 px-3 py-1.5",
                                size="1",
                            ),
                            rx.input(
                                value=State.gen_sub_fields[i][j].to(str),
                                on_change=lambda val, fi=i, si=j: State.set_gen_sub_field(fi, si, val),
                                placeholder=s["default"],
                                font_family="monospace",
                                size="1",
                            ),
                        ),
                        spacing="1",
                    ),
                ),
                spacing="2",
            ),
            width="100%",
        )

    # 列表字段编辑器，i = 字段索引
    def _list_editor(i: int) -> rx.Component:
        return rx.vstack(
            rx.foreach(
                State.gen_list_rows[i],
                lambda row, r: rx.hstack(
                    rx.foreach(
                        State.gen_field_items[i],
                        lambda it, j: rx.vstack(
                            rx.text(it["name"], size="1", color="gray"),
                            rx.cond(
                                it["type"] == "enum",
                                rx.el.select(
                                    rx.el.option("请选择", value=""),
                                    rx.foreach(State.gen_field_items_enum[i][j], lambda o: rx.el.option(o["label"], value=o["value"])),
                                    default_value=it["default"],
                                    on_change=lambda val, fi=i, ri=r, ji=j: State.set_gen_list_item(fi, ri, ji, val),
                                    class_name="w-full rounded border border-gray-300 px-3 py-1.5",
                                    size="1",
                                ),
                                rx.input(
                                    value=State.gen_list_rows[i][r][j].to(str),
                                    on_change=lambda val, fi=i, ri=r, ji=j: State.set_gen_list_item(fi, ri, ji, val),
                                    placeholder=it["default"],
                                    font_family="monospace",
                                    size="1",
                                ),
                            ),
                            spacing="1",
                        ),
                    ),
                    rx.button(
                        rx.icon("trash", size=14),
                        on_click=lambda: State.remove_gen_list_row(i, r),
                        variant="ghost",
                        size="1",
                        color_scheme="red",
                    ),
                    spacing="2",
                    align="end",
                    width="100%",
                ),
            ),
            rx.hstack(
                rx.button(
                    rx.icon("plus", size=14),
                    "添加一项",
                    on_click=lambda: State.add_gen_list_row(i),
                    variant="outline",
                    size="1",
                ),
                spacing="2",
            ),
            spacing="2",
            width="100%",
        )
    # ── 自定义模板编辑器 ──
    def custom_template_editor() -> rx.Component:
        return rx.cond(
            State.gen_mode == "custom",
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("table_2", size=18, color="#f97316"),
                        rx.heading("自定义字段模板", size="3", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.foreach(
                        State.gen_custom_templates,
                        lambda tpl, i: rx.hstack(
                            rx.input(
                                value=tpl["name"].to(str),
                                on_change=lambda val, idx=i: State.set_gen_custom_template(idx, "name", val),
                                placeholder="名称",
                                size="1",
                                width="15%",
                            ),
                            rx.input(
                                value=tpl["length"].to_string(),
                                on_change=lambda val, idx=i: State.set_gen_custom_template(idx, "length", val),
                                placeholder="长度",
                                size="1",
                                width="8%",
                                type="number",
                            ),
                            rx.el.select(
                                rx.el.option("bytes", value="bytes"),
                                rx.el.option("uint8", value="uint8"),
                                rx.el.option("uint16", value="uint16"),
                                rx.el.option("uint32", value="uint32"),
                                rx.el.option("checksum", value="checksum"),
                                default_value=tpl["ftype"],
                                on_change=lambda val, idx=i: State.set_gen_custom_template(idx, "ftype", val),
                                class_name="rounded border border-gray-300 px-2 py-1",
                                size="1",
                                width="12%",
                            ),
                            rx.el.select(
                                rx.el.option("little", value="little"),
                                rx.el.option("big", value="big"),
                                default_value=tpl["endian"],
                                on_change=lambda val, idx=i: State.set_gen_custom_template(idx, "endian", val),
                                class_name="rounded border border-gray-300 px-2 py-1",
                                size="1",
                                width="10%",
                            ),
                            rx.el.select(
                                rx.el.option("hex", value="hex"),
                                rx.el.option("dec", value="dec"),
                                default_value=tpl["display"],
                                on_change=lambda val, idx=i: State.set_gen_custom_template(idx, "display", val),
                                class_name="rounded border border-gray-300 px-2 py-1",
                                size="1",
                                width="10%",
                            ),
                            rx.input(
                                value=tpl["value"].to(str),
                                on_change=lambda val, idx=i: State.set_gen_custom_template(idx, "value", val),
                                placeholder="值",
                                font_family="monospace",
                                size="1",
                                width="25%",
                            ),
                            rx.button(
                                rx.icon("trash", size=14),
                                on_click=lambda: State.remove_gen_custom_template(i),
                                variant="ghost",
                                size="1",
                                color_scheme="red",
                            ),
                            spacing="2",
                            width="100%",
                        ),
                    ),
                    rx.button(
                        rx.icon("plus", size=14),
                        "添加字段",
                        on_click=State.add_gen_custom_template,
                        variant="outline",
                        size="1",
                    ),
                    spacing="3",
                    width="100%",
                ),
                width="100%",
            ),
        )

    # ── A-XDR 编辑器（第一版：单层非复合项；复合类型由纯函数完整支持）──
    def _axdr_item_editor(items: Any) -> rx.Component:
        return rx.foreach(
            items,
            lambda item, i: rx.hstack(
                rx.el.select(
                    rx.foreach(
                        _axdr_type_options(),
                        lambda o: rx.el.option(o["label"], value=o["value"]),
                    ),
                    default_value=item["type"],
                    on_change=lambda val, idx=i: State.set_gen_axdr_item(idx.to_string(), "type", val),
                    class_name="rounded border border-gray-300 px-2 py-1",
                    size="1",
                    width="180px",
                ),
                rx.input(
                    value=item["value"].to(str),
                    on_change=lambda val, idx=i: State.set_gen_axdr_item(idx.to_string(), "value", val),
                    placeholder="值",
                    font_family="monospace",
                    size="1",
                    width="120px",
                ),
                rx.cond(
                    _is_var_len(item["type"]),
                    rx.input(
                        value=item["length"].to_string(),
                        on_change=lambda val, idx=i: State.set_gen_axdr_item(idx.to_string(), "length", val),
                        placeholder="长度/个数",
                        size="1",
                        width="70px",
                        type="number",
                    ),
                ),
                rx.cond(
                    _is_compound(item["type"]),
                    rx.button(
                        rx.icon("plus", size=14),
                        "子项",
                        on_click=lambda: State.add_gen_axdr_item(i.to_string()),
                        variant="outline",
                        size="1",
                    ),
                ),
                rx.button(
                    rx.icon("trash", size=14),
                    on_click=lambda: State.remove_gen_axdr_item(i.to_string()),
                    variant="ghost",
                    size="1",
                    color_scheme="red",
                ),
                spacing="2",
                width="100%",
            ),
        )

    def axdr_editor() -> rx.Component:
        return rx.cond(
            State.gen_mode == "axdr",
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("braces", size=18, color="#7c3aed"),
                        rx.heading("A-XDR 数据编辑器", size="3", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.grid(
                        rx.vstack(
                            rx.text("服务优先级:", size="1", font_weight="medium"),
                            rx.el.select(
                                rx.el.option("0-普通", value="0"),
                                rx.el.option("1-高优先级", value="1"),
                                default_value="0",
                                on_change=lambda v: State.set_gen_axdr_fixed("PIID_优先级", v),
                                class_name="rounded border border-gray-300 px-2 py-1",
                                size="1",
                            ),
                            spacing="1",
                        ),
                        rx.vstack(
                            rx.text("服务序号:", size="1", font_weight="medium"),
                            rx.input(
                                value=State.gen_axdr_fixed["PIID_序号"].to(str),
                                on_change=lambda v: State.set_gen_axdr_fixed("PIID_序号", v),
                                size="1",
                                type="number",
                            ),
                            spacing="1",
                        ),
                        rx.vstack(
                            rx.text("OI (HEX):", size="1", font_weight="medium"),
                            rx.input(
                                value=State.gen_axdr_fixed["OI"].to(str),
                                on_change=lambda v: State.set_gen_axdr_fixed("OI", v),
                                placeholder="如 0000",
                                font_family="monospace",
                                size="1",
                            ),
                            spacing="1",
                        ),
                        rx.cond(
                            State.gen_dlt698_apdu == "ACTION-Request",
                            rx.vstack(
                                rx.text("方法标识:", size="1", font_weight="medium"),
                                rx.input(
                                    value=State.gen_axdr_fixed["方法标识"].to(str),
                                    on_change=lambda v: State.set_gen_axdr_fixed("方法标识", v),
                                    size="1",
                                    type="number",
                                ),
                                spacing="1",
                            ),
                            rx.vstack(
                                rx.text("属性标识:", size="1", font_weight="medium"),
                                rx.input(
                                    value=State.gen_axdr_fixed["属性标识"].to(str),
                                    on_change=lambda v: State.set_gen_axdr_fixed("属性标识", v),
                                    size="1",
                                    type="number",
                                ),
                                spacing="1",
                            ),
                        ),
                        rx.cond(
                            State.gen_dlt698_apdu == "ACTION-Request",
                            rx.vstack(
                                rx.text("操作模式:", size="1", font_weight="medium"),
                                rx.input(
                                    value=State.gen_axdr_fixed["操作模式"].to(str),
                                    on_change=lambda v: State.set_gen_axdr_fixed("操作模式", v),
                                    size="1",
                                    type="number",
                                ),
                                spacing="1",
                            ),
                            rx.vstack(
                                rx.text("索引:", size="1", font_weight="medium"),
                                rx.input(
                                    value=State.gen_axdr_fixed["索引"].to(str),
                                    on_change=lambda v: State.set_gen_axdr_fixed("索引", v),
                                    size="1",
                                    type="number",
                                ),
                                spacing="1",
                            ),
                        ),
                        columns="4",
                        spacing="3",
                        width="100%",
                    ),
                    _axdr_item_editor(State.gen_axdr_items),
                    rx.button(
                        rx.icon("plus", size=14),
                        "添加数据项",
                        on_click=lambda: State.add_gen_axdr_item(""),
                        variant="outline",
                        size="1",
                    ),
                    spacing="3",
                    width="100%",
                ),
                width="100%",
            ),
        )

    # ── 698.45 SA/控制字段 ──
    def dlt698_sa_panel() -> rx.Component:
        return rx.cond(
            State.current_protocol == 8,
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("server", size=18, color="#2563eb"),
                        rx.heading("SA 与控制字段", size="3", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.grid(
                        rx.vstack(
                            rx.text("地址类型:", size="1", font_weight="medium"),
                            rx.el.select(
                                rx.el.option("单地址(0)", value="0"),
                                rx.el.option("组地址(1)", value="1"),
                                rx.el.option("广播地址(3)", value="3"),
                                default_value="0",
                                on_change=lambda v: State.set_gen_dlt698_sa("addr_type", v),
                                class_name="rounded border border-gray-300 px-2 py-1",
                                size="1",
                            ),
                            spacing="1",
                        ),
                        rx.vstack(
                            rx.text("逻辑地址:", size="1", font_weight="medium"),
                            rx.el.select(
                                rx.el.option("0", value="0"),
                                rx.el.option("1", value="1"),
                                rx.el.option("2", value="2"),
                                rx.el.option("3", value="3"),
                                default_value="0",
                                on_change=lambda v: State.set_gen_dlt698_sa("logic_addr", v),
                                class_name="rounded border border-gray-300 px-2 py-1",
                                size="1",
                            ),
                            spacing="1",
                        ),
                        rx.vstack(
                            rx.text("地址长度(字节):", size="1", font_weight="medium"),
                            rx.input(
                                type="number",
                                value=State.gen_dlt698_addr_len.to_string(),
                                on_change=lambda v: State.set_gen_dlt698_sa("addr_len", v),
                                size="1",
                                placeholder="0=自动6字节",
                            ),
                            spacing="1",
                        ),
                        rx.vstack(
                            rx.text("SA (HEX):", size="1", font_weight="medium"),
                            rx.input(
                                value=State.gen_dlt698_sa_raw,
                                on_change=lambda v: State.set_gen_dlt698_sa("sa_raw", v),
                                placeholder="010203040506",
                                font_family="monospace",
                                size="1",
                            ),
                            spacing="1",
                        ),
                        rx.vstack(
                            rx.text("分帧(seg):", size="1", font_weight="medium"),
                            rx.el.select(
                                rx.el.option("完整(0)", value="0"),
                                rx.el.option("分帧(1)", value="1"),
                                default_value="0",
                                on_change=lambda v: State.set_gen_dlt698_sa("seg", v),
                                class_name="rounded border border-gray-300 px-2 py-1",
                                size="1",
                            ),
                            spacing="1",
                        ),
                        rx.vstack(
                            rx.text("扰码(sc):", size="1", font_weight="medium"),
                            rx.el.select(
                                rx.el.option("不加扰(0)", value="0"),
                                rx.el.option("加扰(1)", value="1"),
                                default_value="0",
                                on_change=lambda v: State.set_gen_dlt698_sa("sc", v),
                                class_name="rounded border border-gray-300 px-2 py-1",
                                size="1",
                            ),
                            spacing="1",
                        ),
                        rx.vstack(
                            rx.text("功能码:", size="1", font_weight="medium"),
                            rx.el.select(
                                rx.el.option("链路管理(1)", value="1"),
                                rx.el.option("用户数据(3)", value="3"),
                                default_value="3",
                                on_change=lambda v: State.set_gen_dlt698_sa("func", v),
                                class_name="rounded border border-gray-300 px-2 py-1",
                                size="1",
                            ),
                            spacing="1",
                        ),
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

    # ── 国网中继地址 ──
    def gdw_relay_panel() -> rx.Component:
        return rx.cond(
            State.current_protocol == 7,
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("git_branch", size=18, color="#2563eb"),
                        rx.heading("中继地址 A2", size="3", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.input(
                        value=State.gen_gdw_relay_addrs_text,
                        on_change=State.set_gen_gdw_relay_addrs,
                        placeholder="中继地址，逗号分隔，如 123456789012,234567890123",
                        font_family="monospace",
                        size="1",
                    ),
                    spacing="3",
                    width="100%",
                ),
                width="100%",
            ),
        )

    # ── 实时预览表格 ──
    def preview_table() -> rx.Component:
        return rx.cond(
            State.gen_preview_rows.length() > 0,
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("scan_eye", size=18, color="#059669"),
                        rx.heading("实时回读解析", size="3", font_weight="semibold"),
                        spacing="2",
                    ),
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
                                State.gen_preview_rows,
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
        # 预设命令（置顶，便于快速选择/查找历史命令）
        preset_panel(),
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
                    _searchable_select(
                        "DI:",
                        State.gen_di_search,
                        State.set_gen_di_search,
                        State.di_filtered,
                        State.select_di,
                        State.gen_di_key,
                        "输入 DI 码/名称过滤，如 E8",
                    ),
                ),
                # 国网 AFN+Fn 选择 (协议 7)
                rx.cond(
                    State.current_protocol == 7,
                    _searchable_select(
                        "AFN+Fn:",
                        State.gen_afn_search,
                        State.set_gen_afn_search,
                        State.afn_filtered,
                        State.select_afn,
                        State.gen_afn_fn,
                        "输入 AFN/Fn 码或名称过滤，如 0101",
                    ),
                ),
                # 698.45 APDU 选择 (协议 8)
                rx.cond(
                    State.current_protocol == 8,
                    rx.vstack(
                        _searchable_select(
                            "APDU:",
                            State.gen_dlt698_search,
                            State.set_gen_dlt698_search,
                            State.dlt698_filtered,
                            State.select_dlt698,
                            State.gen_dlt698_apdu,
                            "输入 APDU 类型过滤，如 GET",
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
        # 模式选择
        mode_selector(),
        # 帧配置区（公共参数）
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("grid_3x_3", size=20, color="#2563eb"),
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
        # 698.45 SA/控制字段（协议8）
        dlt698_sa_panel(),
        # 国网信息域配置（协议7）
        gdw_info_panel(),
        gdw_relay_panel(),
        # 数据字段（predefined）或自定义模板/A-XDR 编辑器
        rx.cond(
            State.gen_mode == "custom",
            custom_template_editor(),
            rx.cond(
                State.gen_mode == "axdr",
                axdr_editor(),
                dynamic_fields(),
            ),
        ),
        # 预览和结果
        rx.hstack(
            # 预览
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("eye", size=20, color="#2563eb"),
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
                        rx.icon("square_arrow_out_up_right", size=20, color="#059669"),
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
                                rx.icon("building", size=48, color="#9ca3af"),
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
        # 实时回读解析
        preview_table(),
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
                rx.cond(State.is_loading, rx.spinner(size="1"), rx.icon("git_compare", size=16)),
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
                            rx.icon("git_compare", size=40, color="#9ca3af"),
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
# 报文工具 Tab
# ═══════════════════════════════════════════════════════════════

def message_tool_tab() -> rx.Component:
    """报文工具（对齐 GUI 版功能）"""

    def tool_button(label: str, op: str, **kwargs) -> rx.Component:
        return rx.button(
            label,
            on_click=lambda: State.run_tool(op),
            size="2",
            variant="outline",
            color_scheme="blue",
            **kwargs,
        )

    def tool_grid_button(label: str, op: str) -> rx.Component:
        return rx.button(
            label,
            on_click=lambda: State.run_tool(op),
            size="2",
            variant="outline",
            color_scheme="blue",
            width="100%",
        )

    return rx.vstack(
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("wrench", size=20, color="#2563eb"),
                    rx.heading("报文工具", size="3", font_weight="semibold"),
                    rx.spacer(),
                    spacing="2",
                ),
                # 输入区
                rx.hstack(
                    rx.text("输入", font_weight="medium"),
                    rx.checkbox(
                        "16进制",
                        checked=State.tool_hex_mode,
                        on_change=State.set_tool_hex_mode,
                        size="2",
                    ),
                    rx.spacer(),
                    rx.button(
                        rx.icon("eraser", size=16),
                        "清空",
                        on_click=State.clear_tool,
                        variant="soft",
                        color_scheme="gray",
                        size="2",
                    ),
                    width="100%",
                ),
                rx.text_area(
                    placeholder="输入十六进制报文或文本...",
                    value=State.tool_input,
                    on_change=State.set_tool_input,
                    height="100px",
                    width="100%",
                    font_family="monospace",
                    font_size="13px",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
        # 基础工具
        rx.card(
            rx.vstack(
                rx.heading("基础工具", size="3", font_weight="semibold"),
                # 第一行
                rx.grid(
                    tool_grid_button("按字节倒序", "byte_reverse"),
                    tool_grid_button("+0x33H", "hex_add_33"),
                    tool_grid_button("倒序+0x33H", "reverse_add_33"),
                    tool_grid_button("ASCII→字符", "hex_to_ascii"),
                    tool_grid_button("字节长度", "byte_length"),
                    tool_grid_button("转大写", "to_upper"),
                    tool_grid_button("去空格", "remove_spaces"),
                    tool_grid_button("报文转Pn", "msg_to_pn"),
                    tool_grid_button("Pn转报文", "pn_to_msg"),
                    columns="3",
                    spacing="2",
                    width="100%",
                ),
                # 第二行
                rx.grid(
                    tool_grid_button("和校验", "checksum8"),
                    tool_grid_button("-0x33H", "hex_sub_33"),
                    tool_grid_button("倒序-0x33H", "reverse_sub_33"),
                    tool_grid_button("字符→ASCII", "ascii_to_hex"),
                    tool_grid_button("字符个数", "char_count"),
                    tool_grid_button("转小写", "to_lower"),
                    tool_grid_button("字节间加空格", "add_spaces"),
                    tool_grid_button("报文转Fn", "msg_to_fn"),
                    tool_grid_button("Fn转报文", "fn_to_msg"),
                    columns="3",
                    spacing="2",
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
        # 扩展工具
        rx.card(
            rx.vstack(
                rx.heading("扩展工具", size="3", font_weight="semibold"),
                rx.grid(
                    tool_grid_button("HEX→bitstring", "hex_to_bitstring"),
                    tool_grid_button("bitstring→HEX", "bitstring_to_hex"),
                    tool_grid_button("字节正序", "byte_normal"),
                    tool_grid_button("CRC-16(698.45)", "crc16_698"),
                    tool_grid_button("CRC-32", "crc32_newgen"),
                    tool_grid_button("CRC-24", "crc24_newgen"),
                    columns="3",
                    spacing="2",
                    width="100%",
                ),
                rx.hstack(
                    rx.el.select(
                        rx.el.option("小端(低字节在前)", value="little"),
                        rx.el.option("大端(高字节在前)", value="big"),
                        default_value="little",
                        on_change=State.set_tool_endian,
                        class_name="rounded border border-gray-300 px-2 py-1",
                    ),
                    tool_button("HEX→十进制", "hex_to_decimal"),
                    rx.spacer(),
                    rx.button(
                        rx.icon("copy", size=16),
                        "复制输出",
                        on_click=State.copy_tool_output,
                        variant="soft",
                        color_scheme="gray",
                        size="2",
                    ),
                    width="100%",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
        # 输出区
        rx.card(
            rx.vstack(
                rx.heading("输出", size="3", font_weight="semibold"),
                rx.text_area(
                    value=State.tool_output,
                    is_read_only=True,
                    height="150px",
                    width="100%",
                    font_family="monospace",
                    font_size="13px",
                    background="#f8fafc",
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
# ══════════════════════════════════════════════════════════════

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
                    data_testid="tab-single",
                ),
                rx.button(
                    rx.icon("list", size=16),
                    "批量解析",
                    on_click=lambda: State.set_tab("batch"),
                    variant=rx.cond(State.active_tab == "batch", "solid", "soft"),
                    color_scheme=rx.cond(State.active_tab == "batch", "blue", "gray"),
                    size="2",
                    data_testid="tab-batch",
                ),
                rx.button(
                    rx.icon("square_pen", size=18, color="#2563eb"),
                    "协议组帧",
                    on_click=lambda: State.set_tab("frame"),
                    variant=rx.cond(State.active_tab == "frame", "solid", "soft"),
                    color_scheme=rx.cond(State.active_tab == "frame", "blue", "gray"),
                    size="2",
                    data_testid="tab-frame",
                ),
                rx.button(
                    rx.icon("git_compare", size=16),
                    "报文对比",
                    on_click=lambda: State.set_tab("diff"),
                    variant=rx.cond(State.active_tab == "diff", "solid", "soft"),
                    color_scheme=rx.cond(State.active_tab == "diff", "blue", "gray"),
                    size="2",
                    data_testid="tab-diff",
                ),
                rx.button(
                    rx.icon("search", size=16),
                    "查询",
                    on_click=lambda: State.set_tab("lookup"),
                    variant=rx.cond(State.active_tab == "lookup", "solid", "soft"),
                    color_scheme=rx.cond(State.active_tab == "lookup", "blue", "gray"),
                    size="2",
                    data_testid="tab-lookup",
                ),
                rx.button(
                    rx.icon("wrench", size=16),
                    "报文工具",
                    on_click=lambda: State.set_tab("tool"),
                    variant=rx.cond(State.active_tab == "tool", "solid", "soft"),
                    color_scheme=rx.cond(State.active_tab == "tool", "blue", "gray"),
                    size="2",
                    data_testid="tab-tool",
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
                            rx.cond(
                                State.active_tab == "tool",
                                message_tool_tab(),
                                lookup_tab(),
                            ),
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

app.add_page(index, route="/", title="多协议解析平台")
