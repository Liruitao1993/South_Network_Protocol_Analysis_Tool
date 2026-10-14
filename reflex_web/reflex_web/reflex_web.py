"""多协议解析平台 - Reflex Web 完整版

包含功能：
- 单帧解析
- 批量解析
- 协议组帧
- 报文对比
- 查询 (DI/AFN/OBIS/命令字)
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import reflex as rx

# 添加项目根目录到路径
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from . import (
    app_data,
    landing_web,
    spectrum_web,
    theme_web,
    web_utils,
)
from . import share_model as sm  # noqa: F401  顶部导入：构建期完成 rx.Model 元数据注册

# 批量摘要每页条数选项（值给 rx.el.option 用字符串，State 侧 int(value)）
PAGE_SIZE_OPTIONS = (100, 200, 500, 1000)

# ═══════════════════════════════════════════════════════════════
# 状态管理
# ═══════════════════════════════════════════════════════════════


class State(rx.State):
    """全局应用状态"""

    # ── 协议选择 ─────────────────────────────────────────────
    current_protocol: int = 0
    csg_parse_level: str = "auto"
    csg_pb_frame_type: str = "sof"
    csg_strip_head: int = 0
    csg_strip_tail: int = 0
    gw_parse_level: str = "auto"
    gw_channel: str = "plc"
    # 国网新一代/HDC 1.0 的物理块帧类型（仅 pb_only 下发；取值见解析器 frame_type）
    gw_pb_frame_type: int = 1
    gw_strip_head: int = 0
    gw_strip_tail: int = 0
    hdc10_parse_level: str = "auto"
    hdc10_channel: str = "plc"

    # ── 单帧解析 ─────────────────────────────────────────────
    frame_hex: str = ""
    parse_result: list[dict[str, Any]] = []
    verify_result: str = ""
    # 最近一次成功解析的报文与协议名（供「分享此帧」带入表单）
    last_parsed_hex: str = ""
    last_protocol_name: str = ""

    # ── 批量解析 ─────────────────────────────────────────────
    batch_input: str = ""
    batch_results: list[dict[str, Any]] = []
    batch_selected_idx: int = -1
    batch_detail_rows: list[dict[str, Any]] = []
    batch_detail_hex: str = ""
    # 文件拖拽上传信息
    batch_upload_name: str = ""
    batch_upload_size: int = 0
    batch_file_lines: int = 0
    # 批量解析进度
    batch_progress: int = 0
    batch_total: int = 0
    # 解析出的总帧数（batch_results 只含当前页，此字段始终为真实总数）
    batch_total_frames: int = 0
    # 摘要分页（前端只放当前页 → 大日志不再整批经 WebSocket 下发）
    batch_page: int = 0
    batch_page_size: int = 100
    batch_page_count: int = 0
    # 关键词搜索 + 状态筛选（与桌面 _on_batch_filter_changed 同口径）
    batch_search: str = ""
    batch_status_filter: str = "all"
    batch_visible_count: int = 0
    # 全部帧的摘要（私有 → 不序列化到前端；过滤/翻页都基于它切片）
    _batch_summaries: list[dict[str, Any]] = []
    _batch_filtered: list[dict[str, Any]] = []
    # 预处理命令链（pp_cli 管道式命令）
    batch_pp_commands: str = ""
    batch_pp_last_result: str = ""
    # 预设命令列表
    pp_preset_options: list[dict[str, str]] = []
    # ── 批量解析：后端专用数据（单下划线前缀 → 不发送到前端）──
    # 上传文件内容：大文件（可达50MB）只存后端，避免 WebSocket 同步卡死
    _batch_file_content: str = ""
    # 全部帧的解析结果（完整数据存后端，前端只显示摘要列表）
    _batch_all_results: list[dict[str, Any]] = []

    # ── 组帧 ─────────────────────────────────────────────────
    gen_di_key: str = ""
    gen_afn_fn: str = ""
    gen_dlt698_apdu: str = ""
    gen_dlt698_sub: str = ""
    gen_fields: dict[str, str] = {}
    gen_field_schema: list[dict[str, Any]] = []
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
    gen_field_values: list[str] = []  # [字段索引] 简单字段原始值，位置对齐
    gen_list_rows: list[list[list[str]]] = []  # [字段索引][行][item] 位置对齐
    gen_sub_fields: list[list[str]] = []  # [字段索引][子字段索引] 位置对齐
    # ── DLT645-2007（协议6）组帧 ──
    dlt645_cmd_options: list[str] = []  # 命令下拉标签（【分组】名称（C=xxH））
    dlt645_cmd_keys: list[list[Any]] = []  # 与上表位置对齐的 [direction, func]
    gen_dlt645_cmd_label: str = ""
    gen_dlt645_dir: str = "req"
    gen_dlt645_func: int = 0x11
    gen_dlt645_di: str = ""
    gen_dlt645_di_label: str = ""
    gen_dlt645_addr: str = "000000000000"
    gen_dlt645_fields: list[dict[str, str]] = []  # [{name,value,hint}] 动态字段
    gen_dlt645_ctrl_label: str = ""
    # 渲染模型（全部 str 类型，供 Reflex foreach）
    gen_field_meta: list[
        dict[str, str]
    ] = []  # [i] = {name,type,default,description,has_sub,has_list,ftype}
    gen_field_enum: list[list[dict[str, str]]] = []  # [i] = [{value,label}] enum 选项
    gen_field_items: list[
        list[dict[str, str]]
    ] = []  # [i] = [{name,type,default}] list 的 item_fields
    gen_field_items_enum: list[list[list[dict[str, str]]]] = []  # [i][item] = enum 选项
    gen_field_subs: list[
        list[dict[str, str]]
    ] = []  # [i] = [{name,type,default}] sub_fields
    gen_field_subs_enum: list[list[list[dict[str, str]]]] = []  # [i][sub] = enum 选项
    gen_axdr_fixed: dict[str, str] = {}  # 698.45 A-XDR 固定字段（PIID/OI/属性/索引等）
    gen_custom_templates: list[
        dict[str, Any]
    ] = []  # [{name,length,ftype,endian,display,reverse,value}]
    gen_axdr_items: list[
        dict[str, Any]
    ] = []  # A-XDR 树 [{tag,type,length,value,children}]
    gen_preview_rows: list[
        dict[str, str]
    ] = []  # 实时回读预览 [{field,raw,parsed,comment}]
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
    gen_preset_buttons: list[
        dict[str, str]
    ] = []  # [{name,group,frame_hex,id,description}]
    gen_preset_groups: list[str] = []
    # 预设命令管理（保存表单/搜索/编辑）
    gen_preset_name: str = ""  # 添加到预设-名称
    gen_preset_group: str = ""  # 添加到预设-分组
    gen_preset_search: str = ""  # 预设搜索过滤词
    gen_preset_edit_id: str = ""  # 正在编辑的预设按钮 id（空=未编辑）
    gen_preset_edit_name: str = ""  # 编辑-名称
    gen_preset_edit_group: str = ""  # 编辑-分组
    # DI/AFN 选项列表
    di_options: list[dict[str, str]] = []
    afn_fn_options: list[dict[str, str]] = []
    dlt698_apdu_options: list[str] = []
    dlt698_all_options: list[dict[str, str]] = []  # dict 版本（供可搜索下拉）
    dlt698_sub_options: list[dict[str, str]] = []
    # 可搜索下拉：搜索词 + 过滤结果 + 展开标志
    gen_di_search: str = ""  # DI 搜索过滤词
    di_filtered: list[dict[str, str]] = []  # DI 过滤结果
    gen_di_open: bool = False  # DI 选项列表展开（输入框聚焦时）
    gen_afn_search: str = ""  # AFN+Fn 搜索过滤词
    afn_filtered: list[dict[str, str]] = []  # AFN+Fn 过滤结果
    gen_afn_open: bool = False  # AFN+Fn 选项列表展开
    gen_dlt698_search: str = ""  # 698.45 APDU 搜索过滤词
    dlt698_filtered: list[dict[str, str]] = []  # 698.45 APDU 过滤结果
    gen_dlt698_open: bool = False  # 698.45 APDU 选项列表展开
    # 已选完整标签（代码+名称，供"已选"提示展示）
    gen_di_selected_label: str = ""
    gen_afn_selected_label: str = ""
    # ── EB 数据标识 645 帧生成器（协议7 透明转发/事件上报报文内容辅助）──
    eb_di_options: list[dict[str, str]] = []  # [{value,label,name}] 全部 EB 数据标识
    gen_eb_di: str = ""  # 选中的 EB 数据标识（如 EB030002）
    gen_eb_di_label: str = ""  # 选中 EB 的完整标签
    gen_eb_ctrl: str = "91"  # 645 控制码（十六进制字符串）
    gen_eb_addr: str = "000000000000"  # 645 地址域 A0~A5（12 位 hex）
    gen_eb_data: str = ""  # 数据内容 hex
    gen_eb_frame: str = ""  # 生成的 645 帧 hex
    gen_eb_msg: str = ""  # 生成提示
    gen_eb_msg_type: str = "info"  # success/error/info
    # ── EB 数据标识 698.45 承载 ──
    gen_eb_format: str = "645"  # 645 / 698
    gen_eb_698_service: str = "SET-Request"  # 698 服务类型
    gen_eb_698_data: str = ""  # 698 数据内容 hex
    # 698 链路层头部配置（完整帧 68 L C SA CA HCS APDU FCS 16）
    gen_eb_addr_type: int = 0  # SA 地址类型 (0单/1通配/2组/3广播)
    gen_eb_logic_addr: int = 0  # SA 逻辑地址
    gen_eb_addr_len: int = 6  # SA 地址长度
    gen_eb_sa_raw: str = "000000000000"  # SA 地址 hex
    gen_eb_ca: str = "0"  # CA 客户机地址
    gen_eb_dir: str = "0"  # 控制域 DIR (0下行/1上行)
    gen_eb_prm: str = "1"  # 控制域 PRM
    gen_eb_func: str = "3"  # 控制域功能码 (1链路/3用户数据)
    # 698 对象配置（OAD/OMD 属性/方法/索引 + PIID + 单多对象）
    gen_eb_piid: str = "0"  # PIID 服务序号
    gen_eb_choice: str = "list"  # one=单对象 / list=多对象
    gen_eb_oi: str = ""  # 自定义 OI（hex，空=EB标识前2字节）
    gen_eb_attr_no: str = ""  # 属性编号（空=EB标识第3字节）
    gen_eb_attr_feat: str = "0"  # 属性特征
    gen_eb_index: str = ""  # 元素索引（空=EB标识第4字节）
    gen_eb_method: str = ""  # 方法标识（ACTION，空=EB标识第3字节）
    gen_eb_mode: str = "0"  # 操作模式（ACTION）
    # ── EB 数据项字段表单（选 OAD 后按字段配置数据内容）──
    eb_di_fields: list[
        dict[str, str]
    ] = []  # [{name,type,length,note,has_enum,has_list}]
    eb_di_field_enum: list[list[dict[str, str]]] = []  # [i] enum 选项
    eb_di_field_vals: list[str] = []  # [i] 字段值（位置对齐）
    eb_di_field_list: list[list[list[str]]] = []  # [i] list 字段行（[行][列]）
    eb_di_field_list_meta: list[list[dict[str, str]]] = []  # [i] list item_fields meta
    eb_di_field_use: bool = False  # 当前 OAD 是否用字段表单
    eb_698_use_field: bool = True  # 698 模式是否用字段表单组装数据
    gen_dlt698_selected_label: str = ""
    # 国网信息域配置
    gen_gdw_info: dict[str, str] = {
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
    diff_byte_rows: list[dict[str, Any]] = []  # 字节级对比行
    diff_field_rows: list[dict[str, Any]] = []  # 字段级对比行
    diff_explanations: list[str] = []  # 差异说明
    diff_stats: dict[str, Any] = {}  # 统计信息

    # ── 查询 ─────────────────────────────────────────────────
    lookup_query: str = ""
    lookup_results: list[dict[str, Any]] = []
    lookup_columns: list[str] = ["DI3", "DI2", "DI1", "DI0", "AFN", "中文含义", "自定义"]
    lookup_title: str = "DI 查询"
    # 自定义 DI 新增/覆盖表单（协议0 查询页；对齐桌面「添加自定义DI」对话框字段）
    lookup_di3: str = ""
    lookup_di2: str = ""
    lookup_di1: str = ""
    lookup_di0: str = ""
    lookup_desc: str = ""
    # 自定义 AFN+Fn 新增表单（协议7 查询页；对齐桌面「添加自定义AFN+Fn」对话框字段）
    lookup_afn: str = ""
    lookup_fn: str = ""
    lookup_fn_name: str = ""
    lookup_afn_name: str = ""
    # 结果表勾选的行键（协议0 = "E8 00 08 03"，协议7 = "03HF01"）——多选批量删除用
    lookup_selected: list[str] = []

    # ── 客户端下载 ────────────────────────────────────────────
    download_exe_available: bool = False  # downloads/ 目录是否有 exe
    download_exe_name: str = ""  # exe 文件名
    download_exe_size_mb: str = ""  # exe 体积（MB，首页 CTA 文案用）
    download_image_available: bool = False  # downloads/ 目录是否有截图
    download_image_data_url: str = ""  # 截图 base64 data URL
    download_readme_available: bool = False  # downloads/ 目录是否有 README
    download_readme_text: str = ""  # README 内容
    download_msg: str = ""  # 提示信息
    download_version: str = ""  # 当前版本号（从 version.json 读取）
    download_version_notes: str = ""  # 当前版本更新说明
    download_version_date: str = ""  # 当前版本发布日期
    download_version_url: str = ""  # 当前版本下载地址（从 version.json 读取）
    download_history: list[dict[str, str]] = []  # 历史版本列表（公开版）

    # ── 管理员发布管理 ────────────────────────────────────────
    admin_logged_in: bool = False  # 是否已登录
    admin_show_login_dialog: bool = False  # 登录对话框显示
    admin_password_input: str = ""  # 登录密码输入
    admin_is_default_pwd: bool = False  # 是否默认密码
    admin_change_old: str = ""  # 修改密码-原密码
    admin_change_new: str = ""  # 修改密码-新密码
    admin_change_confirm: str = ""  # 修改密码-确认
    admin_msg: str = ""  # 管理员操作提示

    release_version: str = ""  # 发布版本号
    release_notes: str = ""  # 更新说明
    release_url: str = ""  # 下载地址
    release_status: str = ""  # 发布状态/结果消息
    release_status_type: str = "info"  # 状态类型: info / success / error
    release_progress: int = 0  # SHA-256 计算进度
    release_publishing: bool = False  # 正在发布中
    release_show_success_dialog: bool = False  # 发布成功弹窗
    release_success_info: dict[str, str] = {  # 发布成功信息（弹窗用）
        "version": "",
        "size_mb": "",
        "exe_name": "",
        "sha256": "",
    }
    release_current: dict[str, str] = {}  # 当前版本信息字典
    release_history: list[dict[str, str]] = []  # 历史版本列表
    release_upload_name: str = ""  # 已上传文件名（前端显示）
    release_upload_size_mb: float = 0.0  # 已上传文件大小（前端显示）
    release_screenshot_uploaded: bool = False  # 是否已上传截图
    release_readme_text: str = ""  # README 内容（来自上传文件或已有文件）
    release_readme_name: str = ""  # 已上传 README 文件名（前端显示）
    # 后端数据（不发送到前端）
    _release_screenshot_data: bytes = b""  # 截图二进制（后端）

    # 后端单例/数据（不发送到前端）
    _release_mgr: Any = None
    _admin_cfg: Any = None
    _release_exe_data: bytes = b""  # 上传的 exe 内容（后端存）

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
    PROTOCOL_OPTIONS: list[dict[str, str]] = [
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
        {"label": "[13] 依瓦定制645 (依瓦定制645协议 V1.0)", "value": "13"},
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
        self._load_dlt645_options()

    def set_csg_level(self, value: str):
        self.csg_parse_level = value

    def set_csg_pb_frame_type(self, value: str):
        self.csg_pb_frame_type = value

    def set_gw_level(self, value: str):
        self.gw_parse_level = value

    def set_gw_channel(self, value: str):
        """设置国网新一代通道（PLC/HRF）"""
        self.gw_channel = value

    def set_gw_pb_frame_type(self, value: str):
        """设置国网新一代/HDC 1.0 物理块帧类型（0=信标 1=SOF 2=SACK 3=NET）"""
        try:
            self.gw_pb_frame_type = int(value)
        except (TypeError, ValueError):
            self.gw_pb_frame_type = 1

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

            if p == 2:
                # 完整 HDLC 帧
                return HDLCParser()
            if p in (3, 5):
                # DLMS-APDU(国网) / DLMS-APDU裸报文：直接解析 APDU（对齐桌面版 APDUParser）
                class APDUParserWeb:
                    def __init__(self, hdlc_parser):
                        self.hdlc_parser = hdlc_parser

                    def parse_to_table(self, data, **kwargs):
                        return self.hdlc_parser.parse_apdu_to_table(data)

                return APDUParserWeb(HDLCParser())

            # p == 4：DLMS Wrapper 裸报文，直接解析 Wrapper+APDU（对齐桌面版 WrapperParser）
            class WrapperParserWeb:
                def __init__(self, hdlc_parser):
                    self.hdlc_parser = hdlc_parser

                def parse_to_table(self, data, **kwargs):
                    return self.hdlc_parser.parse_wrapper_to_table(data)

            return WrapperParserWeb(HDLCParser())
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
        elif p == 13:
            # 依瓦定制645：与桌面同一解析器（yw645_parser），不在 Web 侧另写解析逻辑
            from yw645_parser import YW645Parser

            return YW645Parser()
        elif p == 14:
            # 南网上行通信规约：与桌面同一解析器（csg_uplink_parser）
            from csg_uplink_parser import CSGUplinkParser

            return CSGUplinkParser()
        else:
            from protocol_parser import ProtocolFrameParser

            return ProtocolFrameParser()

    def _safe_parse_to_table(self, parser, frame_bytes, **kwargs):
        """解析帧为表格行；对没有 parse_to_table 的 parser（DLT645）走桌面同一实现。

        645 转表的唯一实现在 ``protocol_registry.DLT645GuiParser``（纯 Python 无 Qt，
        Web 已 import 该模块取校验器），此处原先手抄了一份逐字相同的复制体，
        导致「声明长度与实际不符」帧的字节偏移两端同错（AGENTS §8 陷阱 49/50）。
        """
        if not hasattr(parser, "parse_to_table"):
            from protocol_registry import DLT645GuiParser

            return DLT645GuiParser(parser).parse_to_table(frame_bytes)
        return parser.parse_to_table(frame_bytes, **kwargs)

    def _get_validator(self):
        """获取当前协议的校验器（单一来源：protocol_registry）

        原实现在函数内自建 12 项映射且引用了未定义的 p，导致 12 种协议全部
        报「校验出错: name 'p' is not defined」（异常被 except ImportError 之外的
        verify_frame 兜底吞成文案）。改为走桌面同一份注册表工厂。
        """
        import protocol_registry

        return protocol_registry.make_validator(self.current_protocol)

    def _clean_hex(self, hex_str: str) -> bytes:
        """清洗并转换 hex 字符串（严格：奇数长度/空输入报错，不静默截断）

        支持输入格式（对齐 GUI 版 _clean_hex_input）：
          - 纯 hex: 6811010101
          - 空格分隔: 68 11 01 01 01
          - 逗号/分号/顿号等标点分隔: 68,11,01,01,01 或 68；11；01
          - 0x 前缀: 0x68 0x11 0x01 或 0x68,0x11,0x01
          - 混合分隔: 68, 11 - 01. 01
        """
        return web_utils.hex_to_bytes_strict(hex_str)

    def _apply_strip(self, frame_bytes: bytes) -> bytes:
        """应用新一代载波/国网新一代字节剔除（对原始输入重算，重复点击结果一致）

        桌面用「剔除后回写输入框 + _csg_last_stripped_hex 缓存」保证幂等
        （main_gui.py:5322-5346）；Web 输入框是受控 textarea，回写会打断编辑，
        故改为每次从原始 frame_hex 重算——同一输入恒定得到同一结果，等价幂等。
        """
        if self.current_protocol == 9:
            head, tail = self.csg_strip_head, self.csg_strip_tail
        elif self.current_protocol == 10:
            head, tail = self.gw_strip_head, self.gw_strip_tail
        else:
            return frame_bytes
        return web_utils.strip_frame_bytes(frame_bytes, head, tail)

    def _parse_kwargs(self) -> dict:
        """按当前协议构造 parse_to_table 的级别相关参数（单帧/批量共用）

        协议9 通道暂由 parser 自动判别（channel="auto"）；通道下拉属后续子任务。
        """
        if self.current_protocol == 9:
            return web_utils.parse_kwargs_for(
                9,
                self.csg_parse_level,
                self.csg_pb_frame_type,
                self.gw_pb_frame_type,
                "auto",
            )
        if self.current_protocol == 10:
            return web_utils.parse_kwargs_for(
                10,
                self.gw_parse_level,
                self.csg_pb_frame_type,
                self.gw_pb_frame_type,
                self.gw_channel,
            )
        if self.current_protocol == 11:
            return web_utils.parse_kwargs_for(
                11,
                self.hdc10_parse_level,
                self.csg_pb_frame_type,
                self.gw_pb_frame_type,
                self.hdc10_channel,
            )
        return {}

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
            kwargs = self._parse_kwargs()
            result = self._safe_parse_to_table(parser, frame_bytes, **kwargs)

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
                        prefix = (
                            "　" * (indent_level - 1) + "└ " if indent_level > 0 else ""
                        )
                        display_field = prefix + stripped
                    else:
                        display_field = field_name

                    self.parse_result.append(
                        {
                            "id": idx,
                            "field": display_field,
                            "raw": str(row[1]) if row[1] else "",
                            "parsed": str(row[2]) if row[2] else "",
                            "comment": str(row[3]) if row[3] else "",
                            "is_child": indent_level > 0,
                            "indent": indent_level,
                        }
                    )

            self.message = f"解析成功，共 {len(self.parse_result)} 个字段"
            self.message_type = "success"
            # 缓存本次解析的报文与协议名（供「分享此帧」使用）
            self.last_parsed_hex = " ".join(f"{b:02X}" for b in frame_bytes)
            # 按 value 查标签（**不按位置索引**）：协议下拉存在索引空洞
            # （已支持 13、尚未支持 12），位置索引会让协议13 退成「不确定」。
            self.last_protocol_name = next(
                (
                    str(opt.get("label", ""))
                    for opt in self.PROTOCOL_OPTIONS
                    if str(opt.get("value")) == str(self.current_protocol)
                ),
                "不确定",
            )

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
            # 与 parse_frame 同预处理（清洗 + 剔除）：保证「解析通过但校验失败」
            # 不会因为一个用剔除后字节、一个用原始字节而出现
            frame_bytes = self._apply_strip(self._clean_hex(self.frame_hex))
            validator = self._get_validator()
            if validator is None:
                self.message = "当前协议不支持校验"
                self.message_type = "warning"
                return

            result = validator.verify(frame_bytes)
            lines = [f"[{'通过' if result.valid else '失败'}] {result.summary()}"]
            for check in result.checks:
                icon = (
                    "✅"
                    if check.level.value == "pass"
                    else "❌"
                    if check.level.value == "fail"
                    else "⚠️"
                )
                lines.append(
                    f"  {icon} {check.name}: 期望={check.expected}, 实际={check.actual} - {check.message}"
                )
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

    async def handle_batch_upload(self, files: list[rx.UploadFile]):
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
                names.append(
                    getattr(f, "filename", None) or getattr(f, "name", None) or "文件"
                )
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
                + (
                    "\n⚠️ 文件较大，解析可能需要一些时间，请耐心等待"
                    if size_mb > 5
                    else ""
                )
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
                clean_hex_input,
                extract_frames_for_protocol,
                get_frame_summary,
                strip_csg_new_gen_prefix,
                strip_gw_new_gen_prefix,
            )

            # 输入源：文件内容优先
            input_text = self._batch_file_content if has_file else self.batch_input

            # 步骤0：CLI 预处理命令链（用户输入的 pp_cli 管道命令）
            if self.batch_pp_commands.strip():
                try:
                    from pp_cli import parse_and_run, split_commands

                    cmds = split_commands(self.batch_pp_commands)
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
                input_text = strip_gw_new_gen_prefix(
                    input_text, self.gw_parse_level, 10
                )
            elif self.current_protocol == 11:
                input_text = strip_gw_new_gen_prefix(
                    input_text, self.hdc10_parse_level, 11
                )

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
            parse_kwargs = self._parse_kwargs()

            # 分块处理：每 N 帧 yield 一次，让出事件循环并向前端发送进度
            CHUNK_SIZE = 100

            # 完整结果（含 frame_bytes + 解析明细）存后端，不发送前端
            all_results = []
            # 全量摘要（私有字段；前端只同步当前页 → 大日志不再整批下发）
            summaries = []

            for idx, frame_hex in enumerate(frame_hexes):
                try:
                    # 不静默裁剪奇数长度：交给 bytes.fromhex 报错并由 per-frame
                    # except 记为「异常」（桌面同口径，main_gui.py:7476）
                    frame_bytes = bytes.fromhex(frame_hex)

                    result = self._safe_parse_to_table(
                        parser, frame_bytes, **parse_kwargs
                    )

                    # 状态/类型/摘要：全表扫描 ❌ 行 + 空表判定
                    ok_name = get_frame_summary(result, self.current_protocol, frame_bytes)
                    status, type_name, summary = web_utils.batch_frame_outcome(
                        result, ok_name
                    )

                    all_results.append(
                        {
                            "id": idx,
                            "frame_bytes": frame_bytes,
                            "result": result,
                            "status": status,
                            "proto": type_name,
                            "summary": summary[:120],
                            "len": len(frame_bytes),
                        }
                    )
                except Exception as ex:
                    # 状态字面量与桌面一致（成功/失败/异常），异常另留错误串
                    all_results.append(
                        {
                            "id": idx,
                            "frame_bytes": b"",
                            "result": [],
                            "status": "异常",
                            "proto": "异常",
                            "summary": f"{frame_hex[:40]}… {ex}"[:100],
                            "error": str(ex),
                            "len": 0,
                        }
                    )

                # 摘要行全量收集（私有字段，不下发前端；前端只拿当前页）
                summaries.append(
                    {
                        "id": all_results[-1]["id"],
                        "status": all_results[-1]["status"],
                        "proto": all_results[-1]["proto"],
                        "summary": all_results[-1]["summary"],
                        "len": all_results[-1]["len"],
                        # 供关键词搜索匹配（桌面同口径匹配原始 HEX）；不下发前端。
                        # 取 all_results[-1]（异常分支为 b""）而非局部 frame_bytes：
                        # 该行在 except 之后，异常路径里 frame_bytes 可能未赋值。
                        "hex": all_results[-1]["frame_bytes"].hex().upper(),
                    }
                )

                # 每块 yield：让出事件循环 + 向前端发送进度 delta
                self.batch_progress = idx + 1
                if (idx + 1) % CHUNK_SIZE == 0 or (idx + 1) == total:
                    yield None

            # 结果落地：明细与全量摘要存后端，前端只同步当前页
            self._batch_all_results = all_results
            self._batch_summaries = summaries
            self.batch_total_frames = len(all_results)
            self._batch_filtered = summaries
            self.batch_visible_count = len(summaries)
            self.batch_page = 0
            self._apply_batch_filter()  # 尊重已填的搜索词/状态筛选

            success_count = sum(1 for r in all_results if r["status"] == "成功")
            fail_count = sum(1 for r in all_results if r["status"] == "失败")
            err_count = len(all_results) - success_count - fail_count
            msg = f"批量解析完成 — 共 {len(all_results)} 帧（✅ {success_count} 成功，❌ {fail_count} 失败"
            if err_count:
                msg += f"，⚠️ {err_count} 异常"
            self.message = msg + "）"
            self.message_type = (
                "success" if (fail_count == 0 and err_count == 0) else "warning"
            )
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
        """选择批量解析结果项，显示详细解析（完整结果从后端 _batch_all_results 读取）

        idx 是**当前页内**的下标；明细按该行的全局 id 取，
        batch_selected_idx 存全局 id（跨页高亮仍然正确）。
        """
        if idx < 0 or idx >= len(self.batch_results):
            return

        display_item = self.batch_results[idx]
        frame_id = display_item.get("id", idx)
        self.batch_selected_idx = frame_id
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
                self.batch_detail_rows.append(
                    {
                        "field": field,
                        "raw": raw,
                        "parsed": parsed,
                        "comment": comment,
                    }
                )

    def select_batch_by_index(self, index: int):
        """通过索引选择（用于 rx.foreach 回调）"""
        self.select_batch_item(index)

    # ── 摘要分页 ─────────────────────────────────────────────
    def _load_batch_page(self) -> None:
        """把「过滤后的摘要」的当前页写入 batch_results（前端只同步这一页）。

        行的 `hex`（供搜索匹配用）不下发前端：切片后剔除，前端载荷与改造前一致。
        """
        self.batch_page = web_utils.page_of(self.batch_page, self.batch_page_count)
        rows, page_count = web_utils.paginate(
            self._batch_filtered, self.batch_page, self.batch_page_size
        )
        self.batch_page_count = page_count
        self.batch_results = [
            {k: v for k, v in row.items() if k != "hex"} for row in rows
        ]

    def _apply_batch_filter(self) -> None:
        """重算过滤结果并回到第 1 页（搜索/筛选变化时调用）。

        选中帧若被过滤掉则清空详情，避免「右侧还显示着已看不见的那帧」。
        """
        self._batch_filtered = web_utils.filter_batch_summaries(
            self._batch_summaries, self.batch_search, self.batch_status_filter
        )
        self.batch_visible_count = len(self._batch_filtered)
        self.batch_page = 0
        self._load_batch_page()
        if self.batch_selected_idx >= 0 and not any(
            row.get("id") == self.batch_selected_idx for row in self._batch_filtered
        ):
            self.batch_selected_idx = -1
            self.batch_detail_hex = ""
            self.batch_detail_rows = []

    def set_batch_search(self, value: str):
        """批量结果搜索（摘要 / 类型 / 帧 HEX / #序号）。"""
        self.batch_search = value
        if self._batch_summaries:
            self._apply_batch_filter()

    def set_batch_status_filter(self, value: str):
        """批量结果状态筛选（全部/成功/失败/异常）。"""
        self.batch_status_filter = value or "all"
        if self._batch_summaries:
            self._apply_batch_filter()

    def batch_goto_page(self, page: int):
        """跳页（首页=0 / 上页=当前-1 / 下页=当前+1 / 末页=page_count-1）。"""
        self.batch_page = int(page or 0)
        self._load_batch_page()

    def batch_first_page(self):
        self.batch_goto_page(0)

    def batch_prev_page(self):
        self.batch_goto_page(self.batch_page - 1)

    def batch_next_page(self):
        self.batch_goto_page(self.batch_page + 1)

    def batch_last_page(self):
        self.batch_goto_page(self.batch_page_count - 1)

    def set_batch_page_size(self, value: str):
        """每页条数（100/200/500/1000）：改后回到第一页。"""
        try:
            size = int(value)
        except (TypeError, ValueError):
            size = 100
        self.batch_page_size = size if size > 0 else 100
        self.batch_page = 0
        self._load_batch_page()

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
        self.batch_page = 0
        self.batch_page_count = 0
        self.batch_search = ""
        self.batch_status_filter = "all"
        self.batch_visible_count = 0
        self._batch_summaries = []
        self._batch_filtered = []
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
            from pp_cli import parse_and_run, split_commands

            source = self._batch_file_content if has_file else self.batch_input
            cmds = split_commands(self.batch_pp_commands)
            result = parse_and_run(source, cmds)
            if has_file:
                # 大文件内容写回后端，不进入前端
                self._batch_file_content = result
                self.batch_file_lines = len(result.splitlines())
                self.batch_pp_last_result = f"预处理完成（{' '.join(cmds)}）：{self.batch_file_lines} 行（已保存到服务器端）"
            else:
                self.batch_input = result
                self.batch_pp_last_result = (
                    f"预处理完成（{' '.join(cmds)}）：{len(result.splitlines())} 行"
                )
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
        self.gen_di_selected_label = value
        for o in self.di_options:
            if o["value"] == value:
                self.gen_di_selected_label = o["label"]
                break
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
            o
            for o in self.di_options
            if kw in o["value"].lower() or kw in o["label"].lower()
        ]

    def open_di(self):
        """DI 选项列表展开（输入框聚焦）"""
        self.gen_di_open = True

    def close_di(self):
        """DI 选项列表收起（输入框失焦）"""
        self.gen_di_open = False

    def select_di(self, value: str):
        """选择 DI 选项（可搜索下拉）"""
        self.gen_di_search = ""
        self.di_filtered = []
        self.gen_di_open = False
        self.set_gen_di_key(value)

    def set_gen_afn_fn(self, value: str):
        """设置 AFN+Fn"""
        self.gen_afn_fn = value
        self.gen_afn_selected_label = value
        for o in self.afn_fn_options:
            if o["value"] == value:
                self.gen_afn_selected_label = o["label"]
                break
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
            o
            for o in self.afn_fn_options
            if kw in o["value"].lower() or kw in o["label"].lower()
        ]

    def open_afn(self):
        """AFN+Fn 选项列表展开（输入框聚焦）"""
        self.gen_afn_open = True

    def close_afn(self):
        """AFN+Fn 选项列表收起（输入框失焦）"""
        self.gen_afn_open = False

    def select_afn(self, value: str):
        """选择 AFN+Fn 选项（可搜索下拉）"""
        self.gen_afn_search = ""
        self.afn_filtered = []
        self.gen_afn_open = False
        self.set_gen_afn_fn(value)

    def set_gen_dlt698_apdu(self, value: str):
        """设置 698.45 APDU 类型"""
        self.gen_dlt698_apdu = value
        self.gen_dlt698_selected_label = value
        for o in self.dlt698_all_options:
            if o["value"] == value:
                self.gen_dlt698_selected_label = o["label"]
                break
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
            {"value": o, "label": o, "name": o}
            for o in self.dlt698_apdu_options
            if kw in o.lower()
        ]

    def open_dlt698(self):
        """698.45 APDU 选项列表展开（输入框聚焦）"""
        self.gen_dlt698_open = True

    def close_dlt698(self):
        """698.45 APDU 选项列表收起（输入框失焦）"""
        self.gen_dlt698_open = False

    def select_dlt698(self, value: str):
        """选择 698.45 APDU 选项（可搜索下拉）"""
        self.gen_dlt698_search = ""
        self.dlt698_filtered = []
        self.gen_dlt698_open = False
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

    # ── EB 数据标识 645 帧生成器 ──────────────────────────────
    def load_eb_di_options(self):
        """加载全部 EB 数据标识选项（gdw_eb_di_lookup）"""
        try:
            from gdw_eb_di_lookup import get_eb_di_lookup

            data = get_eb_di_lookup().get_all()
        except Exception:
            data = {}
        options = []
        for code, info in sorted(data.items()):
            options.append(
                {
                    "value": code,
                    "label": f"{code} {info.get('名称', '')}",
                    "name": info.get("名称", ""),
                }
            )
        self.eb_di_options = options

    def set_eb_di(self, value: str):
        """选择 EB 数据标识"""
        self.gen_eb_di = value
        for o in self.eb_di_options:
            if o["value"] == value:
                self.gen_eb_di_label = o["label"]
                break
        self._load_eb_di_field_schema(value)

    def _load_eb_di_field_schema(self, di_code: str):
        """加载 EB 数据项字段 schema（gdw_eb_di_fields.py）"""
        self.eb_di_fields = []
        self.eb_di_field_enum = []
        self.eb_di_field_vals = []
        self.eb_di_field_list = []
        self.eb_di_field_list_meta = []
        self.eb_di_field_use = False
        try:
            from gdw_eb_di_fields import EB_DI_FIELDS

            info = EB_DI_FIELDS.get(di_code)
            if not info:
                return
            fields = info["fields"]
            self.eb_di_field_use = True
            for f in fields:
                ftype = f.get("type", "hex")
                self.eb_di_fields.append(
                    {
                        "name": f.get("name", ""),
                        "type": ftype,
                        "length": str(f.get("length", "")),
                        "note": str(f.get("note", "")),
                        "has_enum": "1" if ftype == "enum" else "0",
                        "has_list": "1" if ftype == "list" else "0",
                        "default": str(f.get("default", "")),
                    }
                )
                if ftype == "enum":
                    self.eb_di_field_enum.append(
                        [
                            {"value": str(k), "label": v}
                            for k, v in f.get("enum_map", {}).items()
                        ]
                    )
                else:
                    self.eb_di_field_enum.append([])
                self.eb_di_field_vals.append(str(f.get("default", "")))
                if ftype == "list":
                    self.eb_di_field_list.append([])
                    self.eb_di_field_list_meta.append(
                        [
                            {
                                "name": it.get("name", ""),
                                "type": it.get("type", "hex"),
                                "length": str(it.get("length", "")),
                            }
                            for it in f.get("item_fields", [])
                        ]
                    )
                else:
                    self.eb_di_field_list.append([])
                    self.eb_di_field_list_meta.append([])
        except Exception:
            self.eb_di_field_use = False

    def set_eb_field(self, idx, value: str):
        """设置 EB 字段值（idx = eb_di_fields 索引）"""
        try:
            idx = int(idx)
        except (ValueError, TypeError):
            return
        if 0 <= idx < len(self.eb_di_field_vals):
            self.eb_di_field_vals[idx] = value

    def add_eb_list_row(self, fi):
        """EB list 字段添加一行"""
        try:
            fi = int(fi)
        except (ValueError, TypeError):
            return
        if 0 <= fi < len(self.eb_di_field_list):
            meta = (
                self.eb_di_field_list_meta[fi]
                if fi < len(self.eb_di_field_list_meta)
                else []
            )
            row = ["" for _ in meta]
            rows = list(self.eb_di_field_list[fi])
            rows.append(row)
            self.eb_di_field_list[fi] = rows

    def set_eb_list_cell(self, fi, row_idx, col_idx, value: str):
        """EB list 字段设置单元格"""
        try:
            fi, row_idx, col_idx = int(fi), int(row_idx), int(col_idx)
        except (ValueError, TypeError):
            return
        if 0 <= fi < len(self.eb_di_field_list):
            rows = [list(r) for r in self.eb_di_field_list[fi]]
            if row_idx < len(rows) and col_idx < len(rows[row_idx]):
                rows[row_idx][col_idx] = value
            self.eb_di_field_list[fi] = rows

    def _collect_eb_field_values(self) -> dict[str, Any]:
        """从字段表单收集 {字段名: 值}"""
        from gdw_eb_di_fields import EB_DI_FIELDS

        info = EB_DI_FIELDS.get(self.gen_eb_di, {})
        fields = info.get("fields", [])
        values = {}
        for i, f in enumerate(fields):
            fname = f.get("name", "")
            ftype = f.get("type", "hex")
            if ftype == "list":
                items = []
                for row in (
                    self.eb_di_field_list[i] if i < len(self.eb_di_field_list) else []
                ):
                    item = {}
                    meta = (
                        self.eb_di_field_list_meta[i]
                        if i < len(self.eb_di_field_list_meta)
                        else []
                    )
                    for j, it in enumerate(meta):
                        item[it["name"]] = row[j] if j < len(row) else ""
                    items.append(item)
                values[fname] = items
            else:
                values[fname] = (
                    self.eb_di_field_vals[i] if i < len(self.eb_di_field_vals) else ""
                )
        return values

    def set_eb_ctrl(self, value: str):
        """设置 645 控制码"""
        self.gen_eb_ctrl = value

    def set_eb_addr(self, value: str):
        """设置 645 地址域"""
        self.gen_eb_addr = value

    def set_eb_data(self, value: str):
        """设置数据内容 hex"""
        self.gen_eb_data = value

    def set_eb_format(self, value: str):
        """切换 EB 承载格式（645 / 698）"""
        self.gen_eb_format = value
        self.gen_eb_frame = ""
        self.gen_eb_msg = ""

    def set_eb_698_service(self, value: str):
        """设置 698 服务类型"""
        self.gen_eb_698_service = value

    def set_eb_698_data(self, value: str):
        """设置 698 数据内容 hex"""
        self.gen_eb_698_data = value

    def set_eb_addr_type(self, value: str):
        try:
            self.gen_eb_addr_type = int(value)
        except (ValueError, TypeError):
            pass

    def set_eb_logic_addr(self, value: str):
        try:
            self.gen_eb_logic_addr = int(value)
        except (ValueError, TypeError):
            pass

    def set_eb_addr_len(self, value: str):
        try:
            self.gen_eb_addr_len = int(value)
        except (ValueError, TypeError):
            pass

    def set_eb_sa_raw(self, value: str):
        self.gen_eb_sa_raw = value

    def set_eb_ca(self, value: str):
        self.gen_eb_ca = value

    def set_eb_dir(self, value: str):
        self.gen_eb_dir = value

    def set_eb_prm(self, value: str):
        self.gen_eb_prm = value

    def set_eb_func(self, value: str):
        self.gen_eb_func = value

    def set_eb_698_use_field(self, value: str):
        """切换 698 数据内容来源（字段表单 / 自由 hex）"""
        self.eb_698_use_field = value == "1"

    def set_eb_piid(self, value: str):
        self.gen_eb_piid = value

    def set_eb_choice(self, value: str):
        self.gen_eb_choice = value

    def set_eb_oi(self, value: str):
        self.gen_eb_oi = value

    def set_eb_attr_no(self, value: str):
        self.gen_eb_attr_no = value

    def set_eb_attr_feat(self, value: str):
        self.gen_eb_attr_feat = value

    def set_eb_index(self, value: str):
        self.gen_eb_index = value

    def set_eb_method(self, value: str):
        self.gen_eb_method = value

    def set_eb_mode(self, value: str):
        self.gen_eb_mode = value

    def gen_eb_645_frame(self):
        """生成 EB 数据标识 645 帧: 68 A0..A5 68 C L DI3 DI2 DI1 DI0 DATA CS 16

        645 数据标识为 4 字节小端（DI3 DI2 DI1 DI0 = EB XX XX XX），
        EB 数据标识字符串如 "EB030002" → 帧内字节 EB 03 00 02。
        """
        if self.gen_eb_format == "698":
            return self._gen_eb_698_frame()
        try:
            from gdw_eb_di_lookup import get_eb_di_lookup

            lookup = get_eb_di_lookup()
        except Exception:
            lookup = None
        di = self.gen_eb_di.strip()
        if not di or not di.startswith("EB") or len(di) != 8:
            self.gen_eb_msg = "请先选择 EB 数据标识（如 EB030002）"
            self.gen_eb_msg_type = "error"
            return
        try:
            ctrl = int(self.gen_eb_ctrl, 16)
            data_bytes = (
                bytes.fromhex(self.gen_eb_data.replace(" ", ""))
                if self.gen_eb_data.strip()
                else b""
            )
            addr_bytes = bytes.fromhex(self.gen_eb_addr.replace(" ", ""))
            if len(addr_bytes) != 6:
                addr_bytes = addr_bytes[:6].ljust(6, b"\x00")
        except ValueError:
            self.gen_eb_msg = "控制码/地址/数据内容格式错误（应为十六进制）"
            self.gen_eb_msg_type = "error"
            return
        # DI 字节: "EB030002" → EB 03 00 02
        try:
            di_bytes = bytes.fromhex(di)
        except ValueError:
            self.gen_eb_msg = f"EB 数据标识格式错误: {di}"
            self.gen_eb_msg_type = "error"
            return
        # 标准口径：数据域逐字节 +0x33、CS 覆盖帧头；统一调用 DLT645FrameGenerator，
        # 与 GUI _build_eb_645_frame 同一实现，避免口径再次分裂
        from dlt645_frame_gen import DLT645FrameGenerator, encode_di

        frame = DLT645FrameGenerator().build_frame(
            addr_bytes, ctrl, encode_di(di) + data_bytes
        )
        self.gen_eb_frame = frame.hex()
        info = lookup.get(di) if lookup else None
        name = info.get("名称", "") if info else ""
        self.gen_eb_msg = f"已生成 {di} {name} 645 帧（{len(frame)} 字节），点击「填入报文内容」写入透明转发字段"
        self.gen_eb_msg_type = "success"

    def _gen_eb_698_frame(self):
        """生成 EB 数据标识 698.45 完整帧（附件1 V3.42 698 承载格式）"""
        try:
            from gdw_eb_di_lookup import get_eb_di_lookup

            lookup = get_eb_di_lookup()
        except Exception:
            lookup = None
        di = self.gen_eb_di.strip()
        if not di or not di.startswith("EB") or len(di) != 8:
            self.gen_eb_msg = "请先选择 EB 数据标识（如 EB030002）"
            self.gen_eb_msg_type = "error"
            return
        try:
            from gdw_eb_di_fields import EB_DI_FIELDS, encode_eb_di_data

            from frame_gen_utils import build_dlt698_sa, build_eb_698_frame

            # 数据内容：优先用字段表单组装，否则用自由 hex
            data_hex = self.gen_eb_698_data
            if self.eb_698_use_field and di in EB_DI_FIELDS:
                values = self._collect_eb_field_values()
                try:
                    data_bytes = encode_eb_di_data(di, values)
                    data_hex = data_bytes.hex()
                except Exception:
                    data_hex = self.gen_eb_698_data

            # 完整帧头部配置（SA 由地址类型/逻辑地址/长度/hex 组装）
            sa = (
                build_dlt698_sa(
                    self.gen_eb_addr_type,
                    self.gen_eb_logic_addr,
                    self.gen_eb_addr_len,
                    self.gen_eb_sa_raw,
                )
                if hasattr(self, "gen_eb_addr_type")
                else None
            )

            frame = build_eb_698_frame(
                di,
                self.gen_eb_698_service,
                data_hex,
                sa=sa,
                ca=int(self.gen_eb_ca or 0),
                dir_bit=int(self.gen_eb_dir or 0),
                prm_bit=int(self.gen_eb_prm or 1),
                func_code=int(self.gen_eb_func or 3),
                piid=int(self.gen_eb_piid or 0),
                choice=self.gen_eb_choice,
                oi_hex=self.gen_eb_oi,
                attr_no=int(self.gen_eb_attr_no) if self.gen_eb_attr_no else None,
                attr_feat=int(self.gen_eb_attr_feat or 0),
                index=int(self.gen_eb_index) if self.gen_eb_index else None,
                method=int(self.gen_eb_method) if self.gen_eb_method else None,
                mode=int(self.gen_eb_mode or 0),
            )
            if isinstance(frame, bytes):
                frame_hex = frame.hex()
            else:
                frame_hex = frame
        except ValueError as e:
            self.gen_eb_msg = str(e)
            self.gen_eb_msg_type = "error"
            return
        self.gen_eb_frame = frame_hex
        info = lookup.get(di) if lookup else None
        name = info.get("名称", "") if info else ""
        self.gen_eb_msg = f"已生成 {di} {name} 698 完整帧（{self.gen_eb_698_service}，{len(frame) if isinstance(frame, bytes) else len(frame_hex) // 2} 字节，含 68 链路层封装），点击「填入报文内容」写入透明转发字段"
        self.gen_eb_msg_type = "success"

    def apply_eb_frame_to_content(self):
        """将生成的 645 帧填入「报文内容」字段（第一个 bytes 类型字段）"""
        if not self.gen_eb_frame:
            self.gen_eb_msg = "请先生成 645 帧"
            self.gen_eb_msg_type = "error"
            return
        # 找 gen_field_meta 中名为「报文内容」或第一个 bytes 字段
        target_idx = None
        for i, meta in enumerate(self.gen_field_meta):
            if meta.get("name") == "报文内容":
                target_idx = i
                break
        if target_idx is None:
            for i, meta in enumerate(self.gen_field_meta):
                if meta.get("type") == "bytes":
                    target_idx = i
                    break
        if target_idx is None:
            self.gen_eb_msg = "当前命令无「报文内容」字段可填入"
            self.gen_eb_msg_type = "error"
            return
        self.gen_field_values[target_idx] = self.gen_eb_frame
        self._update_gen_preview()
        self.gen_eb_msg = f"已填入字段「{self.gen_field_meta[target_idx].get('name')}」（字段 #{target_idx}）"
        self.gen_eb_msg_type = "success"

    def set_gen_sub_field(self, fi, si, value: str):
        """设置子字段值（fi = 字段索引，si = 子字段索引）"""
        try:
            fi, si = int(fi), int(si)
        except (ValueError, TypeError):
            return
        if 0 <= fi < len(self.gen_sub_fields) and 0 <= si < len(
            self.gen_sub_fields[fi]
        ):
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
            defaults = [
                str(it.get("default", "")) for it in field.get("item_fields", [])
            ]
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
        if 0 <= fi < len(self.gen_list_rows) and 0 <= row_idx < len(
            self.gen_list_rows[fi]
        ):
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
        if (
            0 <= fi < len(self.gen_list_rows)
            and 0 <= row_idx < len(self.gen_list_rows[fi])
            and 0 <= item_idx < len(self.gen_list_rows[fi][row_idx])
        ):
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
        self.gen_custom_templates.append(
            {
                "name": "",
                "length": 1,
                "ftype": "bytes",
                "endian": "little",
                "display": "hex",
                "reverse": False,
                "value": "",
            }
        )

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
        new_item = {
            "type": "unsigned",
            "tag": 0x11,
            "length": 0,
            "value": 0,
            "children": [],
        }
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
            from frame_gen_utils import COMPOUND_TYPES, TYPE_TO_TAG

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

    # ------------------------------------------------------------------
    # DLT645-2007（协议6）组帧：与 GUI frame_gen_widget 的 dlt645 模式同构，
    # 共用 dlt645_frame_gen / dlt645_frame_schema，保证同输入同输出（AC7）
    # ------------------------------------------------------------------
    def _load_dlt645_options(self):
        """加载 645 命令下拉（请求/应答/异常三组）"""
        try:
            from dlt645_frame_schema import list_commands

            opts, keys = [], []
            for key, group, text in list_commands():
                opts.append(f"【{group}】{text}")
                keys.append([key[0], int(key[1])])
            self.dlt645_cmd_options = opts
            self.dlt645_cmd_keys = keys
        except Exception:
            self.dlt645_cmd_options = []
            self.dlt645_cmd_keys = []
            return
        if self.dlt645_cmd_options and (
            self.gen_dlt645_cmd_label not in self.dlt645_cmd_options
        ):
            self.select_dlt645_cmd(self.dlt645_cmd_options[0])

    def select_dlt645_cmd(self, label: str):
        """选择 645 命令并重建动态字段"""
        self.gen_dlt645_cmd_label = label
        try:
            idx = self.dlt645_cmd_options.index(label)
            direction, func = self.dlt645_cmd_keys[idx]
        except (ValueError, IndexError):
            return
        self.gen_dlt645_dir = str(direction)
        self.gen_dlt645_func = int(func)
        self._refresh_dlt645_fields()
        self._update_gen_preview()

    def set_dlt645_di(self, value: str):
        self.gen_dlt645_di = (value or "").strip()
        self._refresh_dlt645_fields()
        self._update_gen_preview()

    def set_dlt645_addr(self, value: str):
        self.gen_dlt645_addr = (value or "").strip()
        self._update_gen_preview()

    def set_dlt645_field(self, idx, value: str):
        """设置 645 动态字段值（idx = gen_dlt645_fields 索引）"""
        try:
            idx = int(idx)
        except (ValueError, TypeError):
            return
        if 0 <= idx < len(self.gen_dlt645_fields):
            self.gen_dlt645_fields[idx]["value"] = str(value)
        self._update_gen_preview()

    def _refresh_dlt645_fields(self):
        """按当前命令 + DI 掩码重建动态字段（与 GUI _rebuild_dlt645_fields 同规则）"""
        from dlt645_frame_gen import DLT645FrameGenerator, describe_control
        from dlt645_frame_schema import build_di_fields, get_command, get_di_info

        try:
            spec = get_command((self.gen_dlt645_dir, self.gen_dlt645_func))
        except ValueError:
            self.gen_dlt645_fields = []
            self.gen_dlt645_ctrl_label = ""
            return
        fields = [f for f in (spec.get("fields") or []) if f.get("type") != "di"]
        di = self.gen_dlt645_di.upper()
        if spec.get("has_di") and di:
            derived = build_di_fields(di)
            if self.gen_dlt645_dir == "req" and self.gen_dlt645_func in (0x11, 0x12):
                derived = [f for f in derived if f.get("type") == "lme_entries"]
            fields = derived + [
                f
                for f in fields
                if f.get("type") not in ("di_value", "demand", "demand_time")
            ]
            info = get_di_info(di)
            self.gen_dlt645_di_label = (
                f"{info['name']}｜{info['data_type'] or '未声明'}｜{info['length']}B"
                if info["name"]
                else "不在映射表，按裸字节填写"
            )
        else:
            self.gen_dlt645_di_label = ""
        self.gen_dlt645_fields = [
            {
                "name": f["name"],
                "value": str(f.get("default", "")),
                "hint": f.get("hint", ""),
            }
            for f in fields
        ]
        ctrl = DLT645FrameGenerator.build_control(
            spec["func"], dir_bit=spec["dir"], err=bool(spec.get("err"))
        )
        self.gen_dlt645_ctrl_label = describe_control(ctrl)

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
                options.append(
                    {"label": f"{key_hex} - {name}", "value": key_hex, "name": name}
                )
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
                options.append({"label": f"{key} - {name}", "value": key, "name": name})
            self.afn_fn_options = sorted(options, key=lambda x: x["value"])
        except Exception:
            self.afn_fn_options = []

    def _load_dlt698_options(self):
        """加载 698.45 APDU 类型选项"""
        try:
            from dl_t698_45_frame_schema import APDU_TYPE_LIST

            self.dlt698_apdu_options = [item[1] for item in APDU_TYPE_LIST]
            self.dlt698_all_options = [
                {"value": item[1], "label": item[1], "name": item[1]}
                for item in APDU_TYPE_LIST
            ]
        except ImportError:
            self.dlt698_apdu_options = []
            self.dlt698_all_options = []

    def _load_dlt698_sub_options(self):
        """加载 698.45 子选项"""
        if not self.gen_dlt698_apdu:
            self.dlt698_sub_options = []
            return
        try:
            from dl_t698_45_frame_schema import (
                ACTION_REQUEST_LIST,
                GET_REQUEST_LIST,
                SET_REQUEST_LIST,
            )

            sub_lists = {
                "GET-Request": GET_REQUEST_LIST,
                "SET-Request": SET_REQUEST_LIST,
                "ACTION-Request": ACTION_REQUEST_LIST,
            }
            sub_list = sub_lists.get(self.gen_dlt698_apdu, [])
            self.dlt698_sub_options = [
                {"label": name, "value": key} for key, name in sub_list
            ]
        except ImportError:
            self.dlt698_sub_options = []

    def _convert_enum_map(self, enum_map: Any) -> list[dict[str, str]]:
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
            items.append(
                {
                    "value": str(k),
                    "label": f"{text} (0x{val:02X})",
                }
            )
        return items

    def _fill_gen_field_schema(
        self, fields: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
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
                self.gen_sub_fields.append(
                    [str(s.get("default", "")) for s in f.get("sub_fields", [])]
                )
            else:
                self.gen_sub_fields.append([])
            # 列表行（空）
            self.gen_list_rows.append([])
            # —— 渲染模型 ——
            self.gen_field_meta.append(
                {
                    "name": f.get("name", ""),
                    "type": f.get("type", "bytes"),
                    "default": str(f.get("default", "")),
                    "description": str(f.get("description", "")),
                    "has_sub": "1" if "sub_fields" in f else "0",
                    "has_list": "1" if f.get("type") == "list" else "0",
                }
            )
            # enum 选项
            self.gen_field_enum.append(
                [dict(o) for o in f.get("enum_map", [])]
                if f.get("type") == "enum"
                else []
            )
            # item_fields（list）
            item_fields = f.get("item_fields", [])
            items_meta = []
            items_enum = []
            for it in item_fields:
                items_meta.append(
                    {
                        "name": it.get("name", ""),
                        "type": it.get("type", "bytes"),
                        "default": str(it.get("default", "")),
                    }
                )
                items_enum.append(
                    [dict(o) for o in it.get("enum_map", [])]
                    if it.get("type") == "enum"
                    else []
                )
            self.gen_field_items.append(items_meta)
            self.gen_field_items_enum.append(items_enum)
            # sub_fields
            subs_meta = []
            subs_enum = []
            for s in f.get("sub_fields", []):
                subs_meta.append(
                    {
                        "name": s.get("name", ""),
                        "type": s.get("type", "bytes"),
                        "default": str(s.get("default", "")),
                    }
                )
                subs_enum.append(
                    [dict(o) for o in s.get("enum_map", [])]
                    if s.get("type") == "enum"
                    else []
                )
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
            di_key = (
                int(key[0:2], 16),
                int(key[2:4], 16),
                int(key[4:6], 16),
                int(key[6:8], 16),
            )
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
        elif field_type == "ascii" or field_type == "bcd":
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
        elif p == 6:  # DLT645-2007
            if self.gen_dlt645_cmd_label:
                parts.append(f"命令: {self.gen_dlt645_cmd_label}")
            if self.gen_dlt645_di:
                parts.append(f"DI: {self.gen_dlt645_di}")
            parts.append(f"表地址: {self.gen_dlt645_addr}")

        parts.append(f"源地址: {self.gen_src_addr}")
        parts.append(f"目的地址: {self.gen_dst_addr}")
        parts.append(f"序列号: {self.gen_seq}")
        parts.append(f"方向: {'下行' if self.gen_dir == 0 else '上行'}")
        parts.append(f"PRM: {self.gen_prm}")

        if self.gen_field_schema:
            parts.append(f"\n数据字段 ({len(self.gen_field_schema)}个):")
            for i, f in enumerate(self.gen_field_schema):
                val = (
                    self.gen_field_values[i]
                    if i < len(self.gen_field_values)
                    else f.get("default", "")
                )
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
            result = self._safe_parse_to_table(parser, frame_bytes)
            rows = []
            for idx, row in enumerate(result):
                if len(row) < 4:
                    continue
                field_name = str(row[0]) if row[0] else ""
                indent_level = 0
                stripped = field_name.lstrip()
                if stripped != field_name:
                    indent_level = (len(field_name) - len(stripped)) // 2
                    prefix = (
                        "　" * (indent_level - 1) + "└ " if indent_level > 0 else ""
                    )
                    display_field = prefix + stripped
                else:
                    display_field = field_name
                rows.append(
                    {
                        "id": idx,
                        "field": display_field,
                        "raw": str(row[1]) if row[1] else "",
                        "parsed": str(row[2]) if row[2] else "",
                        "comment": str(row[3]) if row[3] else "",
                        "is_child": indent_level > 0,
                        "indent": indent_level,
                    }
                )
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
            from send_frame_lib import ProtocolFrameGenerator

            from frame_gen_utils import collect_field_values, generate_custom_data

            gen = ProtocolFrameGenerator()
            key = self.gen_di_key
            di_key = (
                int(key[0:2], 16),
                int(key[2:4], 16),
                int(key[4:6], 16),
                int(key[6:8], 16),
            )

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
                    di3,
                    di2,
                    di1,
                    di0,
                    src_addr=src,
                    dst_addr=dst,
                    data=data,
                    dir_flag=self.gen_dir,
                    prm=self.gen_prm,
                    add_flag=1,
                )
            schema = gen.get_di_schema(di_key)
            field_values = collect_field_values(
                schema.get("fields", []) if schema else [],
                self.gen_field_values,
                self.gen_list_rows,
                self.gen_sub_fields,
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
            from gdw_send_frame_lib import GDWFrameGenerator

            from frame_gen_utils import collect_field_values

            gen = GDWFrameGenerator()
            afn = int(self.gen_afn_fn[0:2], 16)
            fn = int(self.gen_afn_fn[2:4], 16)

            schema = gen.get_schema(afn, fn)
            field_values = collect_field_values(
                schema.get("fields", []) if schema else [],
                self.gen_field_values,
                self.gen_list_rows,
                self.gen_sub_fields,
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

            relay_addrs = [
                a.strip() for a in self.gen_gdw_relay_addrs_text.split(",") if a.strip()
            ]
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
            from dl_t698_45_frame_gen import DLT69845FrameGenerator
            from dl_t698_45_frame_schema import DLT69845_FIELD_SCHEMA

            from frame_gen_utils import (
                build_dlt698_axdr_apdu,
                build_dlt698_sa,
                collect_field_values,
                encode_axdr_items,
            )

            gen = DLT69845FrameGenerator()

            apdu_type = self.gen_dlt698_apdu
            sub_type = self.gen_dlt698_sub or "get_normal"
            schema_key = (apdu_type, sub_type)
            schema = DLT69845_FIELD_SCHEMA.get(schema_key, {})

            sa = build_dlt698_sa(
                self.gen_dlt698_addr_type,
                self.gen_dlt698_logic_addr,
                self.gen_dlt698_addr_len,
                self.gen_dlt698_sa_raw,
            )
            if not sa:
                raise ValueError("请输入有效的SA地址")
            ca = self.gen_seq & 0xFF

            if self.gen_mode == "axdr":
                axdr_data = encode_axdr_items(self.gen_axdr_items)
                field_values = collect_field_values(
                    schema.get("fields", []),
                    self.gen_field_values,
                    self.gen_list_rows,
                    self.gen_sub_fields,
                )
                priority = int(self.gen_axdr_fixed.get("PIID_优先级", 0) or 0) & 0x01
                seq = int(self.gen_axdr_fixed.get("PIID_序号", 1) or 1) & 0x7F
                piid = (priority << 7) | seq
                oi_hex = self.gen_axdr_fixed.get("OI", "0000")
                apdu = build_dlt698_axdr_apdu(
                    apdu_type,
                    sub_type,
                    piid,
                    oi_hex,
                    field_values,
                    axdr_data,
                    is_custom=(apdu_type == "_custom_"),
                )
                return gen._assemble_frame(
                    sa,
                    ca,
                    gen.build_control(
                        dir_bit=self.gen_dir,
                        prm_bit=self.gen_prm,
                        seg_bit=self.gen_dlt698_seg,
                        sc_bit=self.gen_dlt698_sc,
                        func_code=self.gen_dlt698_func,
                    ),
                    apdu,
                )
            field_values = collect_field_values(
                schema.get("fields", []),
                self.gen_field_values,
                self.gen_list_rows,
                self.gen_sub_fields,
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

        if p == 6:  # DLT645-2007：与 GUI 同一个生成器，保证同输入同输出
            from dlt645_frame_gen import DLT645FrameGenerator

            fv = {f["name"]: f["value"] for f in self.gen_dlt645_fields}
            if self.gen_dlt645_di:
                fv["数据标识 DI"] = self.gen_dlt645_di.upper()
            return DLT645FrameGenerator().generate_frame(
                (self.gen_dlt645_dir, self.gen_dlt645_func),
                fv,
                addr=self.gen_dlt645_addr or None,
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
            self.gen_result = (
                f"生成成功！共 {len(frame_bytes)} 字节\n\n{self.gen_result_hex}"
            )
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
                buttons.append(
                    {
                        "name": c.get("button_name", ""),
                        "group": c.get("group_name", "其他"),
                        "frame_hex": c.get("frame_hex", ""),
                        "id": c.get("id", ""),
                        "description": c.get("description", ""),
                    }
                )
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
            path.write_text(
                _json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
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
            path.write_text(
                _json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
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
            path.write_text(
                _json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
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

            if not result.get("success", False):
                self.message = f"对比失败: {result.get('error', '未知错误')}"
                self.message_type = "error"
                return

            # 字节级对比行（按字段分组）
            byte_rows = []
            for field_group in result.get("byte_diff", []):
                field_name = field_group.get("field_name", "")
                status = field_group.get("status", "same")
                # 过滤：仅显示差异模式
                if self.diff_only_diff and status == "same":
                    continue
                # 字段标题行
                byte_rows.append(
                    {
                        "is_field_header": True,
                        "field_name": field_name,
                        "status": status,
                        "offset": "",
                        "left": "",
                        "right": "",
                    }
                )
                # 逐字节行（每行 8 字节）
                details = field_group.get("byte_details", [])
                for i in range(0, len(details), 8):
                    chunk = details[i : i + 8]
                    offset = chunk[0].get("offset", 0) if chunk else 0
                    left_hex = " ".join(
                        f"{d['byte_a']:02X}" if d.get("byte_a") is not None else "  "
                        for d in chunk
                    )
                    right_hex = " ".join(
                        f"{d['byte_b']:02X}" if d.get("byte_b") is not None else "  "
                        for d in chunk
                    )
                    row_status = "same"
                    if any(d.get("status") == "modified" for d in chunk):
                        row_status = "modified"
                    elif any(d.get("status") == "added" for d in chunk):
                        row_status = "added"
                    elif any(d.get("status") == "removed" for d in chunk):
                        row_status = "removed"
                    byte_rows.append(
                        {
                            "is_field_header": False,
                            "field_name": "",
                            "status": row_status,
                            "offset": f"0x{offset:04X}",
                            "left": left_hex,
                            "right": right_hex,
                        }
                    )
            self.diff_byte_rows = byte_rows

            # 字段级对比行
            field_rows = []
            for f in result.get("field_diff", []):
                diff_type = f.get("diff_type", "相同")
                # 仅显示差异模式
                if self.diff_only_diff and diff_type == "相同":
                    continue
                field_rows.append(
                    {
                        "field_name": f.get("field_name", ""),
                        "offset_a": str(f.get("offset_a", -1)),
                        "offset_b": str(f.get("offset_b", -1)),
                        "offset_display": f"{f.get('offset_a', -1)}/{f.get('offset_b', -1)}",
                        "length_a": str(f.get("length_a", 0)),
                        "length_b": str(f.get("length_b", 0)),
                        "length_display": f"{f.get('length_a', 0)}/{f.get('length_b', 0)}",
                        "value_a": str(f.get("value_a", "")),
                        "value_b": str(f.get("value_b", "")),
                        "diff_type": diff_type,
                    }
                )
            self.diff_field_rows = field_rows

            # 差异说明
            self.diff_explanations = result.get("explanation", [])

            # 统计信息
            stats = result.get("stats", {})
            self.diff_stats = stats

            field_modified = stats.get("field_modified", 0)
            field_added = stats.get("field_added", 0)
            field_removed = stats.get("field_removed", 0)
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

    # ── 查询 ─────────────────────────────────────────────────
    def set_lookup_query(self, value: str):
        self.lookup_query = value

    async def do_lookup(self):
        """执行查询（根据当前协议自动选择查询类型）"""
        self.is_loading = True
        self.message = ""
        self.lookup_results = []
        self.lookup_selected = []  # 结果刷新即清空勾选（避免误删上一批的行）
        try:
            from .lookup_utils import _is_eb_query, get_lookup_data, get_query_config

            if _is_eb_query(self.current_protocol, self.lookup_query):
                # EB 数据标识查询（协议7）：动态切换标题与列
                self.lookup_title = "EB 数据标识查询（本地通信模块扩展协议）"
                self.lookup_columns = ["数据标识", "名称", "数据格式", "长度", "功能"]
            else:
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
            from .lookup_utils import get_lookup_data, get_query_config

            config = get_query_config(self.current_protocol)
            self.lookup_title = config["title"]
            self.lookup_columns = config["columns"]
            # 只加载前 100 条避免页面太大
            results = get_lookup_data(self.current_protocol, "")
            self.lookup_results = results[:100]
        except Exception:
            self.lookup_results = []
            self.lookup_title = "查询"
            self.lookup_columns = []

    # ── 自定义 DI 增删（协议0 查询页；与桌面 lookup_pages 同规则）──────
    #
    # 落盘位置与桌面一致走 `custom_di_store` 默认路径（`app_paths.data_path`）：
    # **必须**是 Web 端 `ProtocolFrameParser` 构造时读的那一份 `custom_di.json`
    # （见 protocol_parser 合并 DI_COMBINATION_MAP），否则会出现「保存成功但查询
    # 看不到」。Web 的 `app_data` 数据根只管反馈库/发布产物，不含 DI 表。

    def set_lookup_di_field(self, field: str, value: str):
        """设置自定义 DI 输入框（field ∈ di3/di2/di1/di0/desc）"""
        if field == "di3":
            self.lookup_di3 = value
        elif field == "di2":
            self.lookup_di2 = value
        elif field == "di1":
            self.lookup_di1 = value
        elif field == "di0":
            self.lookup_di0 = value
        else:
            self.lookup_desc = value

    def _clear_lookup_di_form(self):
        self.lookup_di3 = ""
        self.lookup_di2 = ""
        self.lookup_di1 = ""
        self.lookup_di0 = ""
        self.lookup_desc = ""

    async def add_custom_di(self):
        """校验并写入一条自定义 DI（新增或覆盖已有键）。

        与桌面 `lookup_pages.apply_custom_di_add` 同规则：四个 DI 字节必须是
        十六进制（00-FF）、中文含义不能为空；键已存在则覆盖其含义（桌面弹确认框，
        Web 无对话框，按按钮文案「添加/覆盖」直接覆盖，并在提示里说明）。
        """
        from custom_di_store import (
            find_entry,
            format_key,
            load_custom_di,
            save_custom_di,
            upsert_entry,
            validate_key_text,
        )

        key, err = validate_key_text(
            self.lookup_di3, self.lookup_di2, self.lookup_di1, self.lookup_di0
        )
        if key is None:
            self.message = err
            self.message_type = "error"
            return

        desc = (self.lookup_desc or "").strip()
        if not desc:
            self.message = "请填写中文含义！"
            self.message_type = "error"
            return

        try:
            entries = load_custom_di()
            entries, replaced = upsert_entry(entries, key, desc)
            save_custom_di(entries)
        except OSError as exc:
            self.message = f"保存自定义DI失败: {exc}"
            self.message_type = "error"
            return

        await self.do_lookup()
        self.message = (
            f"已{'覆盖' if replaced else '添加'}自定义DI: {format_key(key)} → {desc}"
        )
        self.message_type = "success"
        self._clear_lookup_di_form()

    async def delete_custom_di(self, di3: str, di2: str, di1: str, di0: str):
        """删除一条自定义 DI；内置 DI 拒绝删除。

        与桌面 `lookup_pages.delete_selected_custom_di_interactive` 同判据：
        只有存在于 `custom_di.json` 的键才是自定义（内置 DI 只活在
        `DI_COMBINATION_MAP`，不在文件里）。
        """
        from custom_di_store import (
            custom_key_set,
            format_key,
            load_custom_di,
            make_key,
            parse_hex_byte,
            remove_keys,
            save_custom_di,
        )

        values = [parse_hex_byte(t) for t in (di3, di2, di1, di0)]
        if any(v is None for v in values):
            self.message = "该行 DI 无法识别，未执行删除"
            self.message_type = "error"
            return
        key = make_key(*values)
        if key not in custom_key_set():
            self.message = (
                f"{format_key(key)} 是内置DI（带★标记的才是自定义DI），不可删除！"
            )
            self.message_type = "error"
            return

        try:
            entries, removed = remove_keys(load_custom_di(), [key])
            if removed:
                save_custom_di(entries)
        except OSError as exc:
            self.message = f"删除自定义DI失败: {exc}"
            self.message_type = "error"
            return

        await self.do_lookup()
        self.message = (
            f"已删除 {removed} 条自定义DI（{format_key(key)}）"
            if removed
            else f"{format_key(key)} 不存在，未删除"
        )
        self.message_type = "success" if removed else "error"

    def set_lookup_afn_field(self, field: str, value: str):
        """设置自定义 AFN+Fn 输入框（field ∈ afn/fn/name/afn_name）"""
        if field == "afn":
            self.lookup_afn = value
        elif field == "fn":
            self.lookup_fn = value
        elif field == "name":
            self.lookup_fn_name = value
        else:
            self.lookup_afn_name = value

    async def add_custom_afn(self):
        """校验并添加一条自定义 AFN+Fn（与桌面 `_add_custom_gdw_fn` 同规则）。

        规则：AFN 十六进制 00-FF、Fn 十进制 1-248、功能名称必填；与标准定义
        重名的组合拒绝添加；AFN 类别名称可选（填了才写进自定义 AFN 名）。
        """
        from reflex_web.lookup_utils import add_gdw_custom_fn

        ok, msg = add_gdw_custom_fn(
            self.lookup_afn, self.lookup_fn, self.lookup_fn_name, self.lookup_afn_name
        )
        if not ok:
            self.message = msg
            self.message_type = "error"
            return

        await self.do_lookup()
        self.message = msg
        self.message_type = "success"
        self.lookup_afn = ""
        self.lookup_fn = ""
        self.lookup_fn_name = ""
        self.lookup_afn_name = ""

    def toggle_lookup_selection(self, key: str, checked: bool):
        """勾选/取消勾选结果表的一行（key 见 lookup_selected 注释）"""
        current = list(self.lookup_selected)
        if checked:
            if key not in current:
                current.append(key)
        elif key in current:
            current.remove(key)
        self.lookup_selected = current

    async def delete_selected_custom(self):
        """批量删除勾选的自定义条目（协议0 → DI；协议7 → AFN+Fn）。

        与桌面多选删除同语义：勾选里的内置/标准条目**忽略**并在提示里说明条数，
        不做「全内置就拒绝」的额外分支（消息里已含 ignored 计数）。
        """
        from reflex_web import lookup_utils

        keys = list(self.lookup_selected)
        if not keys:
            self.message = "请先勾选要删除的自定义条目！"
            self.message_type = "error"
            return

        if self.current_protocol == 0:
            import custom_di_store

            parsed = [lookup_utils.parse_di_row_key(k) for k in keys]
            parsed = [p for p in parsed if p is not None]
            custom = custom_di_store.custom_key_set()
            targets = [p for p in parsed if p in custom]
            ignored = len(keys) - len(targets)
            try:
                entries, removed = custom_di_store.remove_keys(
                    custom_di_store.load_custom_di(), targets
                )
                if removed:
                    custom_di_store.save_custom_di(entries)
            except OSError as exc:
                self.message = f"删除自定义DI失败: {exc}"
                self.message_type = "error"
                return
            await self.do_lookup()
            self.message = f"已删除 {removed} 条自定义DI" + (
                f"（另有 {ignored} 条内置DI已忽略）" if ignored else ""
            )
            self.message_type = "success" if removed else "error"
            return

        if self.current_protocol == 7:
            parsed = [lookup_utils.parse_gdw_row_key(k) for k in keys]
            parsed = [p for p in parsed if p is not None]
            try:
                removed, ignored = lookup_utils.remove_gdw_custom_fns(parsed)
            except OSError as exc:
                self.message = f"删除自定义AFN失败: {exc}"
                self.message_type = "error"
                return
            await self.do_lookup()
            self.message = f"已删除 {removed} 条自定义AFN+Fn组合" + (
                f"（另有 {ignored} 条标准定义已忽略）" if ignored else ""
            )
            self.message_type = "success" if removed else "error"
            return

        self.message = "当前协议的查询页不支持删除自定义条目"
        self.message_type = "error"
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
            self.load_eb_di_options()
        if tab == "download":
            self.load_download_info()
        # 注：feedback tab 的列表加载由 Tab 按钮 on_click 事件链同时触发
        # FeedbackState.fa_load —— Reflex 中主 State 的事件不能携带其他
        # State 的 delta，直接在这里调 FeedbackState.fa_load() 前端收不到。
        if tab == "release":
            self.load_release_info()

    # ── 客户端下载 ────────────────────────────────────────────
    def load_download_info(self):
        """扫描数据根的 downloads/ 目录，获取 exe 与截图信息"""
        try:
            from pathlib import Path

            # 发布产物目录由 app_data 统一决定（部署态在部署目录之外）
            downloads_dir = app_data.downloads_dir()
            # 复位放在目录存在性判断**之前**：否则「downloads/ 不存在」这条路径会把
            # 上一次扫描到的 exe 名/体积/版本/截图留在 State 里（界面显示陈旧数据）
            self.download_exe_available = False
            self.download_exe_name = ""
            self.download_exe_size_mb = ""
            self.download_image_available = False
            self.download_image_data_url = ""
            self.download_version = ""
            self.download_version_notes = ""
            self.download_version_date = ""
            self.download_version_url = ""
            self.download_readme_available = False
            self.download_readme_text = ""
            if downloads_dir.exists():
                # 先读 version.json 获取文件名和版本信息
                vj = downloads_dir / "version.json"
                vj_data = {}
                if vj.exists():
                    try:
                        import json as _json

                        vj_data = _json.loads(vj.read_text(encoding="utf-8"))
                    except Exception:
                        pass

                # 从 version.json 读 exe_name，找不到再 fallback
                exe_from_vj = vj_data.get("exe_name", "")
                primary_exe = None
                if exe_from_vj:
                    candidate = downloads_dir / exe_from_vj
                    if candidate.exists():
                        primary_exe = candidate
                if primary_exe is None:
                    # fallback: 固定文件名
                    fixed = downloads_dir / "南网协议解析工具.exe"
                    if fixed.exists():
                        primary_exe = fixed
                if primary_exe is None:
                    # fallback: 找第一个 exe
                    exes = sorted(downloads_dir.glob("*.exe"))
                    if exes:
                        primary_exe = exes[0]

                if primary_exe is not None:
                    self.download_exe_available = True
                    self.download_exe_name = primary_exe.name
                    try:
                        self.download_exe_size_mb = str(
                            round(primary_exe.stat().st_size / 1024 / 1024, 2)
                        )
                    except Exception:
                        self.download_exe_size_mb = ""
                # 无 exe 时无需复位：三个字段已在函数开头统一清空
                # 界面截图：数据根优先，缺失时回落「随包资源」（部署产物不含运行时 exe，
                # 但这两样静态资源要随包走，否则新部署的首页 Hero 与客户端说明永久缺失）
                ss_file = app_data.resolve_download_asset("client_screenshot.png")
                if ss_file.exists():
                    self.download_image_available = True
                    try:
                        import base64

                        img_data = ss_file.read_bytes()
                        self.download_image_data_url = f"data:image/png;base64,{base64.b64encode(img_data).decode('ascii')}"
                    except Exception:
                        pass
                # 客户端 README（README.md 或 client_readme.md）——同样带回落
                for readme_name in ("client_readme.md", "README.md"):
                    readme_file = app_data.resolve_download_asset(readme_name)
                    if readme_file.exists():
                        try:
                            self.download_readme_text = readme_file.read_text(
                                encoding="utf-8"
                            )
                            self.download_readme_available = True
                        except Exception:
                            pass
                        break
                # 读取 version.json（前面已读，这里直接用 vj_data）
                if vj_data:
                    try:
                        self.download_version = vj_data.get("version", "")
                        self.download_version_notes = vj_data.get("notes", "")
                        self.download_version_url = vj_data.get("url", "")
                        # 用 exe 的修改时间作发布日期
                        if primary_exe is not None:
                            import time as _time

                            self.download_version_date = _time.strftime(
                                "%Y-%m-%d", _time.localtime(primary_exe.stat().st_mtime)
                            )
                    except Exception:
                        pass
                # 读取归档目录中的历史版本（公开，不含下载链接）
                archive_dir = downloads_dir / "archive"
                if archive_dir.exists():
                    import time as _time

                    hist = []
                    for f in sorted(archive_dir.glob("*.exe")):
                        if f.is_file():
                            mtime = _time.strftime(
                                "%Y-%m-%d", _time.localtime(f.stat().st_mtime)
                            )
                            size_mb = round(f.stat().st_size / 1024 / 1024, 2)
                            hist.append(
                                {
                                    "version": f.stem,
                                    "date": mtime,
                                    "size_mb": str(size_mb),
                                }
                            )
                    # 新版本在上
                    hist.sort(
                        key=lambda x: [
                            int(p) for p in x["version"].split(".") if p.isdigit()
                        ],
                        reverse=True,
                    )
                    self.download_history = hist
                self.download_msg = ""
            else:
                self.download_msg = "downloads/ 目录不存在"
        except Exception as e:
            self.download_msg = f"扫描失败: {e}"

    def _download_origin(self, fallback: str = "") -> str:
        """下载路由所在的主机（`host[:port]`）。

        取**当前请求的真实 host**（Reflex 的 router headers）——生产单端口部署就是浏览器正在访问的
        `服务器:8091`，开发态是后端 `localhost:8000`（下载路由在后端）。拿不到请求上下文时用
        `fallback`，再没有就返回空（调用方回落相对路径）。
        """
        try:
            host = (getattr(self.router.headers, "host", "") or "").strip()
        except Exception:
            host = ""
        return host or (fallback or "").strip()

    def _download_target_url(self) -> str:
        """本次点击「下载客户端」该跳到哪里（判定见 `web_utils.resolve_download_target`）。

        单独成方法：URL 决策可在测试里直接断言（`call_script` 的实参在 EventSpec 里只是占位符）。
        """
        return web_utils.resolve_download_target(
            self.download_version_url,
            self.download_exe_name,
            host=self._download_origin(),
            same_origin_serving=web_utils.is_same_origin_serving(),
        )

    def download_client(self):
        """触发客户端 exe 下载。

        目标地址：同源单端口部署走相对路径 `/download/<exe>`（部署在 8091 或任意端口都对，并顺带
        修正历史 `version.json` 里写死的错误端口）；`version.json` 指向**别的主机**（外部托管）
        时原样使用；开发态（前端 3000 / 后端 8000）带后端主机，因为 Vite 不代理下载路由。
        """
        if not self.download_exe_available:
            self.download_msg = "客户端 exe 未就绪"
            return
        # 用 json.dumps 自动转义，避免特殊字符导致 JS 语法错误
        return rx.call_script(
            f"window.location.href = {json.dumps(self._download_target_url())};"
        )

    # ── 管理员发布管理 ────────────────────────────────────────

    def _get_release_mgr(self):
        """获取 ReleaseManager 单例（懒加载）"""
        if self._release_mgr is not None:
            return self._release_mgr
        try:
            from .admin_release import ReleaseManager

            # 发布产物目录由 app_data 统一决定（部署态在部署目录之外）
            self._release_mgr = ReleaseManager(app_data.downloads_dir())
        except Exception as e:
            self.admin_msg = f"初始化发布管理器失败: {e}"
            self._release_mgr = None
        return self._release_mgr

    def _get_admin_cfg(self):
        """获取 AdminConfig 单例（懒加载）"""
        if self._admin_cfg is not None:
            return self._admin_cfg
        try:
            from .admin_release import AdminConfig

            # 口令文件与 downloads/ 同在数据根（由 app_data 统一决定）
            self._admin_cfg = AdminConfig(app_data.admin_config_path())
        except Exception as e:
            self.admin_msg = f"初始化配置失败: {e}"
            self._admin_cfg = None
        return self._admin_cfg

    def toggle_login_dialog(self):
        self.admin_show_login_dialog = not self.admin_show_login_dialog
        self.admin_password_input = ""
        self.admin_msg = ""

    def set_admin_password_input(self, value: str):
        self.admin_password_input = value

    def set_release_version(self, value: str):
        self.release_version = value

    def set_release_url(self, value: str):
        self.release_url = value

    def set_release_notes(self, value: str):
        self.release_notes = value

    async def handle_screenshot_upload(self, files: list[rx.UploadFile]):
        """处理上传的软件界面截图"""
        if not self.admin_logged_in:
            return
        if not files:
            return
        try:
            f = files[0]
            data = await f.read()
            name = getattr(f, "filename", None) or getattr(f, "name", None) or ""
            # 校验图片格式（png/jpg/jpeg/gif/webp）
            if not name.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                self.release_status = "截图仅支持 png/jpg/jpeg/gif/webp 格式"
                return
            # 简单校验文件头
            if len(data) < 4:
                self.release_status = "截图文件过小"
                return
            self._release_screenshot_data = data
            self.release_screenshot_uploaded = True
            self.release_status = (
                f"截图已上传（{len(data) // 1024} KB），发布时一起更新"
            )
        except Exception as e:
            self.release_status = f"截图上传失败: {e}"

    async def handle_readme_upload(self, files: list[rx.UploadFile]):
        """处理上传的 README 文本文件"""
        if not self.admin_logged_in:
            return
        if not files:
            return
        try:
            f = files[0]
            data = await f.read()
            name = getattr(f, "filename", None) or getattr(f, "name", None) or ""
            if not name.lower().endswith((".md", ".markdown", ".txt")):
                self.release_status = "README 仅支持 md/txt 文本文件"
                self.release_status_type = "error"
                return
            if not data:
                self.release_status = "README 文件为空"
                self.release_status_type = "error"
                return
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = data.decode("gbk", errors="replace")
            self.release_readme_text = text
            self.release_readme_name = name
            self.release_status = (
                f"README 已加载（{name}，{len(text)} 字符），发布时一起更新"
            )
            self.release_status_type = "success"
        except Exception as e:
            self.release_status = f"README 上传失败: {e}"
            self.release_status_type = "error"

    def set_admin_change_old(self, value: str):
        self.admin_change_old = value

    def set_admin_change_new(self, value: str):
        self.admin_change_new = value

    def set_admin_change_confirm(self, value: str):
        self.admin_change_confirm = value

    def admin_login(self):
        """管理员登录"""
        cfg = self._get_admin_cfg()
        if cfg is None:
            self.admin_msg = "配置未就绪"
            return
        pwd = self.admin_password_input
        if cfg.verify_password(pwd):
            self.admin_logged_in = True
            self.admin_show_login_dialog = False
            self.admin_is_default_pwd = cfg.is_default_password
            self.admin_msg = "登录成功"
            self.admin_password_input = ""
        else:
            self.admin_msg = "密码错误"

    def admin_logout(self):
        self.admin_logged_in = False
        self.admin_password_input = ""
        self.admin_msg = ""
        self.active_tab = "single"

    def admin_change_password(self):
        """修改管理员密码"""
        if not self.admin_logged_in:
            self.admin_msg = "请先登录"
            return
        cfg = self._get_admin_cfg()
        if cfg is None:
            return
        if self.admin_change_new != self.admin_change_confirm:
            self.admin_msg = "两次输入的新密码不一致"
            return
        ok, msg = cfg.change_password(self.admin_change_old, self.admin_change_new)
        self.admin_msg = msg
        if ok:
            self.admin_is_default_pwd = False
            self.admin_change_old = ""
            self.admin_change_new = ""
            self.admin_change_confirm = ""

    def load_release_info(self):
        """加载当前版本和历史版本信息"""
        if not self.admin_logged_in:
            return
        mgr = self._get_release_mgr()
        if mgr is None:
            return
        try:
            cur = mgr.get_current_version()
            if cur:
                self.release_current = {
                    "version": cur.version,
                    "url": cur.url,
                    "notes": cur.notes,
                    "sha256": cur.sha256,
                    "size_mb": str(cur.size_mb),
                    "exe_name": cur.exe_name,
                    "published_at": cur.published_at,
                }
            else:
                self.release_current = {}
            self.release_history = mgr.list_history()
            # 默认版本号和 URL
            if not self.release_version and cur:
                # 尝试自增最后一段
                parts = cur.version.split(".")
                if parts and parts[-1].isdigit():
                    parts[-1] = str(int(parts[-1]) + 1)
                    self.release_version = ".".join(parts)
            if not self.release_url and cur and cur.url:
                self.release_url = cur.url.replace("/downloads/", "/download/")
            # 如果还是空的，用**当前访问的真实 host** 生成默认下载地址
            # （曾用 rx.config 的 backend_port + socket 猜 IP ⇒ 单端口部署时会写成 host:8000）
            if not self.release_url:
                exe_name = self.release_upload_name or web_utils.DEFAULT_EXE_NAME
                self.release_url = web_utils.release_absolute_url(
                    self._download_origin(), exe_name
                )
            # 读取 README 内容（供编辑）
            mgr2 = self._get_release_mgr()
            if mgr2:
                dl_dir = mgr2.downloads_dir
                readme = dl_dir / "client_readme.md"
                if not readme.exists():
                    readme = dl_dir / "README.md"
                if readme.exists():
                    try:
                        self.release_readme_text = readme.read_text(encoding="utf-8")
                    except Exception:
                        pass
        except Exception as e:
            self.release_status = f"加载失败: {e}"

    async def handle_release_upload(self, files: list[rx.UploadFile]):
        """处理上传的 exe 文件（内容存后端）"""
        if not self.admin_logged_in:
            return
        if not files:
            return
        try:
            f = files[0]
            data = await f.read()
            name = (
                getattr(f, "filename", None) or getattr(f, "name", None) or "未知文件"
            )

            # 校验 PE 头
            if len(data) < 2 or data[:2] != b"MZ":
                self.release_status = "文件不是有效的 exe（缺少 MZ 头）"
                self.release_upload_name = ""
                self.release_upload_size_mb = 0.0
                self._release_exe_data = b""
                return

            self._release_exe_data = data
            self.release_upload_name = name
            self.release_upload_size_mb = round(len(data) / 1024 / 1024, 2)
            self.release_status = f"已加载 {name}（{self.release_upload_size_mb:.2f} MB），填写版本号后点击发布"
            # 上传后自动更新下载地址中的文件名
            self._update_release_url_filename(name)
        except Exception as e:
            self.release_status = f"读取文件失败: {e}"

    def _update_release_url_filename(self, name: str):
        """更新下载地址中的文件名部分

        - 如果 URL 为空，自动生成完整 URL（后端端口）
        - 如果 URL 已有 /download/ 路径，替换文件名
        - 如果 URL 是其他格式，保持不变
        """
        from urllib.parse import quote

        if not self.release_url:
            # URL 为空：用当前访问的真实 host 生成（不再用 config 端口 / 猜 IP）
            self.release_url = web_utils.release_absolute_url(self._download_origin(), name)
            return

        # 替换 /download/ 后面的文件名
        m = re.sub(
            r"(/download/)[^?#]*",
            lambda m: m.group(1) + quote(name),
            self.release_url,
            count=1,
        )
        if m != self.release_url:
            self.release_url = m

    def publish_release(self):
        """发布新版本

        同步执行，确保状态变更全部推送到前端。
        完成后自动刷新当前版本、历史列表，并弹出成功对话框。
        """
        if not self.admin_logged_in:
            self.release_status = "请先登录"
            self.release_status_type = "error"
            return
        mgr = self._get_release_mgr()
        if mgr is None:
            self.release_status = "发布管理器未就绪"
            self.release_status_type = "error"
            return
        if not self._release_exe_data:
            self.release_status = "请先上传 exe 文件"
            self.release_status_type = "error"
            return
        if not self.release_version:
            self.release_status = "请填写版本号"
            self.release_status_type = "error"
            return
        if not self.release_url:
            self.release_status = "请填写下载地址"
            self.release_status_type = "error"
            return

        self.release_publishing = True
        self.release_progress = 0
        self.release_status = "发布中...请稍候"
        self.release_status_type = "info"
        self.release_show_success_dialog = False

        try:

            def progress_cb(p):
                self.release_progress = int(p)

            ok, msg, vi = mgr.publish(
                exe_data=self._release_exe_data,
                version=self.release_version.strip(),
                notes=self.release_notes.strip(),
                download_url=self.release_url.strip(),
                exe_name=self.release_upload_name or "",
                progress_cb=progress_cb,
            )

            if not ok:
                self.release_status = msg
                self.release_status_type = "error"
                self.release_publishing = False
                return

            status_parts = [msg]

            # 保存截图
            if self._release_screenshot_data:
                try:
                    ss_path = mgr.downloads_dir / "client_screenshot.png"
                    ss_path.write_bytes(self._release_screenshot_data)
                    status_parts.append("截图已更新")
                except Exception as se:
                    status_parts.append(f"截图保存失败: {se}")

            # 保存 README
            if self.release_readme_text.strip():
                try:
                    readme_path = mgr.downloads_dir / "client_readme.md"
                    readme_path.write_text(self.release_readme_text, encoding="utf-8")
                    status_parts.append("README 已更新")
                except Exception as re:
                    status_parts.append(f"README 保存失败: {re}")

            # 清空上传缓存
            self._release_exe_data = b""
            self.release_upload_name = ""
            self.release_upload_size_mb = 0.0
            self._release_screenshot_data = b""
            self.release_screenshot_uploaded = False

            # 刷新数据
            self.load_release_info()
            self.load_download_info()

            # 填充成功信息（弹窗用）
            self.release_success_info = {
                "version": self.release_current.get("version", "")
                if isinstance(self.release_current, dict)
                else "",
                "size_mb": self.release_current.get("size_mb", "")
                if isinstance(self.release_current, dict)
                else "",
                "exe_name": self.release_current.get("exe_name", "")
                if isinstance(self.release_current, dict)
                else "",
                "sha256": self.release_current.get("sha256", "")
                if isinstance(self.release_current, dict)
                else "",
            }

            # 最终状态
            self.release_status = "；".join(status_parts)
            self.release_status_type = "success"
            self.release_progress = 100
            self.release_publishing = False
            self.release_notes = ""
            self.release_show_success_dialog = True

        except Exception as e:
            self.release_status = f"发布异常: {e}"
            self.release_status_type = "error"
            self.release_publishing = False

    def close_release_success_dialog(self):
        """关闭发布成功弹窗"""
        self.release_show_success_dialog = False

    def set_release_show_success_dialog(self, value: bool):
        """设置发布成功弹窗显示状态"""
        self.release_show_success_dialog = value

    def rollback_version(self, version: str):
        """回滚到指定版本"""
        if not self.admin_logged_in:
            self.release_status = "请先登录"
            self.release_status_type = "error"
            return
        mgr = self._get_release_mgr()
        if mgr is None:
            return
        # 确认提示由前端处理，这里直接执行
        url = self.release_url or (
            self.release_current.get("url", "") if self.release_current else ""
        )
        exe_name = (
            self.release_current.get("exe_name", "") if self.release_current else ""
        )
        ok, msg = mgr.rollback(version, download_url=url, exe_name=exe_name)
        self.release_status = msg
        self.release_status_type = "success" if ok else "error"
        if ok:
            self.load_release_info()
            self.load_download_info()

    def delete_history_version(self, version: str):
        """删除历史版本"""
        if not self.admin_logged_in:
            self.release_status = "请先登录"
            self.release_status_type = "error"
            return
        mgr = self._get_release_mgr()
        if mgr is None:
            return
        ok, msg = mgr.delete_history(version)
        self.release_status = msg
        self.release_status_type = "success" if ok else "error"
        if ok:
            self.load_release_info()

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
# 频谱图（常驻，与协议无关）——绘制与测量逻辑复用桌面 spectrum_widget 纯逻辑层
# ═══════════════════════════════════════════════════════════════


class SpectrumState(rx.State):
    """频谱图标签页状态。

    数值/算法全部来自 `spectrum_widget`（桌面 1.23.9 起的纯逻辑层，零 Qt 依赖）：
    参数校验 / trace 清洗 / 刻度 / 标记吸附 / 峰值搜索 / 积分带宽；
    SVG 坐标换算在 `spectrum_web`（纯函数）。本类只做「取输入 → 调纯函数 → 组装前端模型」。
    """

    # ── 参数（用户输入原样保留，解析后交给纯逻辑层校验）──
    sp_start: str = "240"
    sp_stop: str = "960"
    sp_center: str = "600"
    sp_span: str = "720"
    sp_freq_unit: str = "MHz"
    sp_ref: str = "-20"
    sp_dbdiv: str = "10"
    sp_ydivs: str = "8"
    sp_amp_unit: str = "dBm"
    sp_50ohm: bool = False
    sp_detector: str = "峰值"
    sp_auto_y: bool = False
    sp_rbw: str = "7.2"
    sp_rbw_unit: str = "MHz"
    sp_vbw: str = ""
    sp_vbw_unit: str = "kHz"
    sp_trace_text: str = ""
    # ── 图形（前端渲染模型；全部 JSON 可序列化）──
    sp_has_trace: bool = False
    sp_polyline: str = ""
    sp_grid_v: list[dict[str, Any]] = []
    sp_grid_h: list[dict[str, Any]] = []
    sp_x_labels: list[dict[str, Any]] = []
    sp_y_labels: list[dict[str, Any]] = []
    sp_bands: list[dict[str, Any]] = []
    sp_params_note: str = ""
    sp_status: str = ""
    sp_axis_range: str = ""
    sp_note: str = ""
    # ── 标记（以频率为锚点，重绘自动重吸附）──
    sp_markers_svg: list[dict[str, Any]] = []
    sp_marker_rows: list[dict[str, Any]] = []
    sp_marker_count: int = 0
    sp_ref_index: int = 0
    sp_readout: str = ""
    sp_extremes: str = ""
    sp_delta: str = ""
    # ── 积分带宽 ──
    sp_ibw_show: bool = False
    sp_ibw_center: str = "600"
    sp_ibw_bw: str = "100"
    sp_ibw_unit: str = "MHz"
    sp_ibw_rect: dict[str, Any] = {}
    sp_ibw_text: str = ""
    sp_ibw_short: str = ""
    # ── 内部：最近一次成功的 trace（私有字段 → 不进前端序列化）──
    _sp_trace: Any = None
    _sp_marker_freqs: list = []
    # ── 消息 ──
    sp_error: str = ""
    sp_msg: str = ""

    # ------------------------------------------------------------------
    # 输入 → SpectrumParams
    # ------------------------------------------------------------------
    def _sp_freq_hz(self, text: str, name: str) -> float:
        from spectrum_widget import SpectrumInputError, units_to_hz

        raw = (text or "").strip()
        if not raw:
            raise SpectrumInputError(f"{name}不能为空")
        try:
            value = float(raw)
        except ValueError:
            raise SpectrumInputError(f"{name}必须是数值（当前：{raw}）")
        return units_to_hz(value, self.sp_freq_unit)

    def _sp_opt_hz(self, text: str, unit: str, name: str):
        from spectrum_widget import SpectrumInputError, units_to_hz

        raw = (text or "").strip()
        if not raw:
            return None
        try:
            value = float(raw)
        except ValueError:
            raise SpectrumInputError(f"{name}必须是数值（当前：{raw}）")
        return units_to_hz(value, unit)

    def _sp_num(self, text: str, name: str) -> float:
        from spectrum_widget import SpectrumInputError

        raw = (text or "").strip()
        if not raw:
            raise SpectrumInputError(f"{name}不能为空")
        try:
            return float(raw)
        except ValueError:
            raise SpectrumInputError(f"{name}必须是数值（当前：{raw}）")

    def _sp_params(self):
        """把表单字段装配成 SpectrumParams（数值/单位错误直接抛纯逻辑层的异常类型）。"""
        from spectrum_widget import SpectrumInputError, SpectrumParams

        try:
            y_divs = int(float((self.sp_ydivs or "").strip()))
        except ValueError:
            raise SpectrumInputError(f"纵向格数必须是整数（当前：{self.sp_ydivs}）")
        return SpectrumParams(
            start_hz=self._sp_freq_hz(self.sp_start, "起始频率"),
            stop_hz=self._sp_freq_hz(self.sp_stop, "终止频率"),
            ref_level_db=self._sp_num(self.sp_ref, "参考电平"),
            db_per_div=self._sp_num(self.sp_dbdiv, "每格 dB"),
            y_divs=y_divs,
            unit=self.sp_amp_unit,
            convert_50ohm=bool(self.sp_50ohm),
            rbw_hz=self._sp_opt_hz(self.sp_rbw, self.sp_rbw_unit, "RBW"),
            vbw_hz=self._sp_opt_hz(self.sp_vbw, self.sp_vbw_unit, "VBW"),
            detector=self.sp_detector,
        )

    # ------------------------------------------------------------------
    # 参数动作
    # ------------------------------------------------------------------
    def sp_set_param(self, name: str, value: str):
        """通用参数写入（文本类参数）；频率四字段走联动。"""
        setattr(self, f"sp_{name}", value)
        if name in ("start", "stop", "center", "span"):
            self._sp_apply_freq_link(name)
        else:
            self._sp_draw_if_ready()

    def _sp_apply_freq_link(self, changed: str) -> None:
        """起始/终止/中心/扫宽 双向联动（纯逻辑 resolve_freq_inputs）。"""
        from spectrum_widget import (
            SpectrumInputError,
            resolve_freq_inputs,
            to_freq_unit,
        )

        try:
            start, stop, center, span = resolve_freq_inputs(
                changed,
                self._sp_freq_hz(self.sp_start, "起始频率"),
                self._sp_freq_hz(self.sp_stop, "终止频率"),
                self._sp_freq_hz(self.sp_center, "中心频率"),
                self._sp_freq_hz(self.sp_span, "扫宽"),
            )
        except SpectrumInputError as exc:
            self.sp_error = str(exc)
            self.sp_msg = ""
            return
        self.sp_error = ""
        self.sp_msg = "频率参数已联动更新"
        unit = self.sp_freq_unit
        self.sp_start = _fmt_num(to_freq_unit(start, unit))
        self.sp_stop = _fmt_num(to_freq_unit(stop, unit))
        self.sp_center = _fmt_num(to_freq_unit(center, unit))
        self.sp_span = _fmt_num(to_freq_unit(span, unit))
        self._sp_draw_if_ready()

    def sp_set_unit(self, unit: str):
        """频率单位切换：数值按新单位换算（与桌面 _on_freq_unit_changed 同口径）。"""
        from spectrum_widget import FREQ_UNITS

        if unit == self.sp_freq_unit or unit not in FREQ_UNITS:
            return
        factor = FREQ_UNITS[self.sp_freq_unit] / FREQ_UNITS[unit]
        for field in ("sp_start", "sp_stop", "sp_center", "sp_span", "sp_ibw_center"):
            raw = (getattr(self, field) or "").strip()
            try:
                value = float(raw)
            except ValueError:
                continue
            setattr(self, field, _fmt_num(value * factor))
        self.sp_freq_unit = unit
        self.sp_ibw_text = ""
        self._sp_draw_if_ready()

    def sp_set_toggle(self, name: str, value: bool):
        """布尔参数：50Ω 换算 / 纵轴自动适配 / 积分带宽显示。"""
        if name == "ibw_show":
            self.sp_ibw_show = bool(value)
        elif name == "50ohm":
            self.sp_50ohm = bool(value)
        elif name == "auto_y":
            self.sp_auto_y = bool(value)
        self._sp_draw_if_ready()

    def sp_set_select(self, name: str, value: str):
        """下拉参数：幅值单位 / 检波方式 / 积分带宽单位 / RBW·VBW 单位。"""
        mapping = {
            "amp_unit": "sp_amp_unit",
            "detector": "sp_detector",
            "ibw_unit": "sp_ibw_unit",
            "rbw_unit": "sp_rbw_unit",
            "vbw_unit": "sp_vbw_unit",
        }
        attr = mapping.get(name)
        if attr is None:
            return
        setattr(self, attr, value)
        self._sp_draw_if_ready()

    def sp_set_ref_index(self, value: str):
        """Δ 参考标记切换。"""
        try:
            self.sp_ref_index = int(value)
        except (TypeError, ValueError):
            self.sp_ref_index = 0
        self._sp_refresh_markers()

    def sp_set_trace_text(self, value: str):
        """trace 文本输入。"""
        self.sp_trace_text = value

    def sp_draw(self):
        """绘制：参数/trace 校验失败时**保留旧图**，只写错误信息。"""
        from spectrum_widget import SpectrumInputError, build_trace

        if not (self.sp_trace_text or "").strip():
            self.sp_error = "请输入 trace 数值"
            return
        try:
            params = self._sp_params()
            trace = build_trace(self.sp_trace_text, params)
        except SpectrumInputError as exc:
            self.sp_error = str(exc)
            self.sp_msg = ""
            return
        self.sp_error = ""
        self._sp_trace = trace
        self.sp_note = trace.source.note() if trace.source else ""
        self._sp_refresh_markers(redraw=True)

    def sp_clear(self):
        self.sp_trace_text = ""
        self._sp_trace = None
        self._sp_marker_freqs = []
        self.sp_has_trace = False
        self.sp_polyline = ""
        self.sp_markers_svg = []
        self.sp_marker_rows = []
        self.sp_marker_count = 0
        self.sp_readout = ""
        self.sp_extremes = ""
        self.sp_delta = ""
        self.sp_ibw_rect = {}
        self.sp_ibw_text = ""
        self.sp_ibw_short = ""
        self.sp_status = ""
        self.sp_axis_range = ""
        self.sp_note = ""
        self.sp_error = ""
        self.sp_msg = "已清空"

    def _sp_draw_if_ready(self):
        """参数变化时：已有 trace 就自动重绘（否则只清错误）。"""
        if self._sp_trace is None:
            self.sp_error = ""
            return
        self.sp_draw()

    # ------------------------------------------------------------------
    # 渲染模型组装
    # ------------------------------------------------------------------
    def _sp_refresh_markers(self, redraw: bool = False):
        """按频率锚点重建标记（吸附/越界丢弃/重编号）并刷新图表与读数。"""
        from spectrum_widget import markers_for

        trace = self._sp_trace
        if trace is None:
            return
        dropped = 0
        markers = ()
        if self._sp_marker_freqs:
            markers = markers_for(trace, self._sp_marker_freqs)
            dropped = len(self._sp_marker_freqs) - len(markers)
        self._sp_marker_freqs = [m.freq_hz for m in markers]
        if dropped and not self.sp_msg:
            self.sp_msg = f"{dropped} 个标记超出扫描范围已丢弃"
        self._sp_render(trace, markers)

    def _sp_render(self, trace, markers):
        """组装全部前端渲染模型（网格/标签/迹线/注记/标记/IBW）。"""
        from spectrum_widget import (
            axis_range_text,
            count_out_of_range,
            delta_text,
            extremes_text,
            marker_rows,
            note_text,
            status_text,
        )

        params = trace.params
        auto = bool(self.sp_auto_y)
        self.sp_grid_v, self.sp_grid_h = spectrum_web.grid_segments(params)
        self.sp_x_labels = spectrum_web.x_label_items(params)
        self.sp_y_labels = spectrum_web.y_label_items(params, trace.levels, auto)
        self.sp_bands = spectrum_web.band_items()
        self.sp_polyline = spectrum_web.trace_path(trace, auto)
        self.sp_params_note = note_text(params, trace.n_points)
        self.sp_axis_range = axis_range_text(params, trace.levels, auto)

        out_of_range = count_out_of_range(params, trace.levels, auto)
        status = status_text(trace)
        if out_of_range:
            status += f" · ⚠ {out_of_range} 点超出纵轴范围（已裁剪到边缘）"
        if self.sp_note:
            status += f" · {self.sp_note}"
        self.sp_status = status
        self.sp_extremes = extremes_text(trace)

        self.sp_markers_svg = spectrum_web.marker_items(markers, params, trace, auto)
        rows = marker_rows(markers, self.sp_ref_index)
        self.sp_marker_rows = [
            {
                "label": r[0],
                "freq": r[1],
                "level": r[2],
                "d_freq": r[3],
                "d_level": r[4],
                "color": spectrum_web.marker_var(i),
            }
            for i, r in enumerate(rows)
        ]
        self.sp_marker_count = len(markers)
        self.sp_ref_index = min(self.sp_ref_index, max(0, len(markers) - 1))
        self.sp_delta = delta_text(markers, self.sp_ref_index)
        if not markers:
            self.sp_readout = ""
        self.sp_has_trace = True
        self._sp_refresh_ibw(trace)

    def _sp_refresh_ibw(self, trace):
        """积分带宽：边沿 + 带内积分 + 带矩形（画在迹线之下）。"""
        from spectrum_widget import SpectrumInputError, integration_band_for

        if not self.sp_ibw_show:
            self.sp_ibw_rect = {}
            self.sp_ibw_text = ""
            self.sp_ibw_short = ""
            return
        try:
            center = self._sp_freq_hz(self.sp_ibw_center, "积分带宽中心频率")
            from spectrum_widget import units_to_hz

            raw = (self.sp_ibw_bw or "").strip()
            try:
                bandwidth = units_to_hz(float(raw), self.sp_ibw_unit)
            except ValueError:
                raise SpectrumInputError(f"积分带宽必须是数值（当前：{raw}）")
            band, _result = integration_band_for(
                trace, center, bandwidth, trace.params.rbw_hz
            )
        except SpectrumInputError as exc:
            self.sp_ibw_rect = {}
            self.sp_ibw_text = f"⚠ {exc}"
            self.sp_ibw_short = ""
            return
        rect = spectrum_web.band_rect(band.low_hz, band.high_hz, trace.params)
        self.sp_ibw_rect = rect or {}
        self.sp_ibw_text = band.text
        self.sp_ibw_short = band.short_text

    # ------------------------------------------------------------------
    # 测量动作
    # ------------------------------------------------------------------
    def sp_plot_click(self, band_index: int):
        """点击绘图区某一带 → 读数 + 在该带最近数据点加标记。"""
        from spectrum_widget import MAX_MARKERS, nearest_index, readout_text

        trace = self._sp_trace
        if trace is None:
            self.sp_error = "请先绘制图形"
            return
        freq = spectrum_web.band_click_freq(band_index, trace.params)
        idx = nearest_index(trace.freqs, freq)
        self.sp_readout = readout_text(
            trace.freqs[idx], trace.levels[idx], trace.params.unit
        )
        if len(self._sp_marker_freqs) >= MAX_MARKERS:
            self.sp_msg = f"标记已达上限（M1~M{MAX_MARKERS}），请先删除"
        else:
            self.sp_msg = ""
            self._sp_marker_freqs = self._sp_marker_freqs + [trace.freqs[idx]]
        self._sp_refresh_markers()

    def sp_next_peak(self):
        """峰值搜索/下一个峰值（相对最后一个标记；无标记则从起点）。"""
        from spectrum_widget import MAX_MARKERS, next_peak_index

        trace = self._sp_trace
        if trace is None:
            self.sp_error = "请先绘制图形"
            return
        current = (
            min(
                range(trace.n_points),
                key=lambda i: abs(trace.freqs[i] - self._sp_marker_freqs[-1]),
            )
            if self._sp_marker_freqs
            else 0
        )
        idx = next_peak_index(trace.levels, current, 1)
        if idx is None:
            self.sp_msg = "未找到显著峰（显著度阈值 3 dB）"
            return
        if len(self._sp_marker_freqs) >= MAX_MARKERS:
            self.sp_msg = f"标记已达上限（M1~M{MAX_MARKERS}），请先删除"
            return
        self._sp_marker_freqs = self._sp_marker_freqs + [trace.freqs[idx]]
        self.sp_msg = ""
        self._sp_refresh_markers()

    def sp_del_marker(self):
        if self._sp_marker_freqs:
            self._sp_marker_freqs = self._sp_marker_freqs[:-1]
            self._sp_refresh_markers()

    def sp_clear_markers(self):
        if self._sp_marker_freqs:
            self._sp_marker_freqs = []
            self.sp_readout = ""
            self.sp_msg = "已清空标记"
            self._sp_refresh_markers()

    def sp_export_png(self):
        """导出 PNG（纯前端：SVG → canvas → 下载，零新增依赖）。"""
        return rx.call_script(spectrum_web.EXPORT_PNG_JS)


def _fmt_num(value: float) -> str:
    """数值回写表单（去掉多余小数位，避免 599.9999999 这类噪声）。"""
    return f"{round(float(value), 6):g}"


# ═══════════════════════════════════════════════════════════════
# 主题状态（模式 + 预设 + 强调色/灰阶/圆角；浅色 token 与改造前等价）
# ═══════════════════════════════════════════════════════════════


class ThemeState(rx.State):
    """Web 主题：模式（浅/深/跟随系统）+ 预设（外观组合）+ 三维微调。

    单一真相：本 State + `html.light|dark` 类 + `localStorage['nw-theme']`（见 `theme_web`）。
    模式切换不依赖 Radix Provider 的内存状态——类由我们设置，并同步它读取的 `theme` 键。
    """

    mode: str = "light"
    preset: str = "classic-light"
    accent: str = theme_web.DEFAULT_ACCENT
    gray: str = theme_web.DEFAULT_GRAY
    radius: str = theme_web.DEFAULT_RADIUS
    preset_options: list[dict[str, str]] = theme_web.preset_options()
    accent_options: list[dict[str, str]] = [
        {"label": label, "value": value} for value, label in theme_web.ACCENTS
    ]
    mode_options: list[dict[str, str]] = [
        {"label": "浅色", "value": "light"},
        {"label": "深色", "value": "dark"},
        {"label": "跟随系统", "value": "system"},
    ]

    @rx.var
    def root_class(self) -> str:
        """页面根容器 class（强调色 token 作用域）。"""
        return theme_web.theme_class(self.accent)

    @rx.var
    def preset_label(self) -> str:
        for p in theme_web.PRESETS:
            if p["id"] == self.preset:
                return p["label"]
        return "自定义"

    @rx.var
    def theme_choice(self) -> str:
        """主题下拉的当前值（预设 id 或 accent:xxx）。"""
        if self.preset != theme_web.CUSTOM_PRESET:
            return theme_web.PRESET_PREFIX + self.preset
        return theme_web.ACCENT_PREFIX + self.accent

    @rx.var
    def mode_button_label(self) -> str:
        return theme_web.mode_label(self.mode)

    @rx.var
    def mode_button_icon(self) -> str:
        return theme_web.mode_icon(self.mode)

    def theme_boot(self):
        """页面加载事件：注册跟随系统监听 + 读回本地主题并应用。

        on_load 必须是事件处理器（EventHandler）而非裸 EventSpec，故这里返回
        `rx.call_script(...)` 让它链式执行；脚本返回值交给 `restore`。
        """
        return rx.call_script(theme_web.restore_js(), callback=ThemeState.restore)

    def apply_choice(self, value: str):
        """主题下拉统一入口：`preset:xxx` / `accent:xxx` / `mode:xxx`。"""
        if value.startswith(theme_web.PRESET_PREFIX):
            return self.apply_preset(value[len(theme_web.PRESET_PREFIX) :])
        if value.startswith(theme_web.ACCENT_PREFIX):
            return self.set_dimension("accent", value[len(theme_web.ACCENT_PREFIX) :])
        if value.startswith(theme_web.MODE_PREFIX):
            return self.set_mode(value[len(theme_web.MODE_PREFIX) :])
        return None

    def cycle_mode(self):
        """模式循环按钮：浅色 → 深色 → 跟随系统。"""
        return self.set_mode(theme_web.next_mode(self.mode))

    def apply_preset(self, preset_id: str):
        """套用预设（模式 + 强调色 + 灰阶 + 圆角）。"""
        preset = theme_web.PRESET_BY_ID.get(preset_id)
        if preset is None:
            return
        self.preset = preset["id"]
        self.mode = preset["mode"]
        self.accent = preset["accent"]
        self.gray = preset["gray"]
        self.radius = preset["radius"]
        return rx.call_script(
            theme_web.persist_js(self.mode, self.accent, self.gray, self.radius)
        )

    def set_mode(self, mode: str):
        """模式切换（浅色/深色/跟随系统）。"""
        if mode not in theme_web.MODES:
            return
        self.mode = mode
        return rx.call_script(
            theme_web.persist_js(self.mode, self.accent, self.gray, self.radius)
        )

    def set_dimension(self, name: str, value: str):
        """强调色 / 灰阶 / 圆角 微调（脱离预设 → 「自定义」）。"""
        if name == "accent" and value in [a for a, _ in theme_web.ACCENTS]:
            self.accent = value
        elif name == "gray" and value in theme_web.GRAYS:
            self.gray = value
        elif name == "radius" and value in theme_web.RADII:
            self.radius = value
        else:
            return
        self.preset = theme_web.CUSTOM_PRESET
        return rx.call_script(
            theme_web.persist_js(self.mode, self.accent, self.gray, self.radius)
        )

    def restore(self, raw: str):
        """on_load 读回本地设置（`localStorage['nw-theme']` 的 JSON 串）。"""
        if not raw:
            return
        try:
            saved = json.loads(raw)
        except (TypeError, ValueError):
            return
        if isinstance(saved, dict):
            if saved.get("mode") in theme_web.MODES:
                self.mode = saved["mode"]
            if saved.get("accent") in [a for a, _ in theme_web.ACCENTS]:
                self.accent = saved["accent"]
            if saved.get("gray") in theme_web.GRAYS:
                self.gray = saved["gray"]
            if saved.get("radius") in theme_web.RADII:
                self.radius = saved["radius"]
            # 与某个预设完全一致则回显该预设（而非「自定义」）
            self.preset = theme_web.match_preset(
                self.mode, self.accent, self.gray, self.radius
            )


# ═══════════════════════════════════════════════════════════════
# 全局样式（所有页面共用：基础设计系统 + 主题 token）
# ═══════════════════════════════════════════════════════════════


def theme_style() -> rx.Component:
    """全局样式表（SEARCHABLE_CSS + GLOBAL_CSS + 主题 token）。

    **每个页面都要挂**：独立页面（/share、/feedback 等）此前没有 GLOBAL_CSS，
    而 header 已改用 `var(--accent)` 等 token → 缺样式会让顶栏背景透明、白字不可见。
    """
    return rx.el.style(SEARCHABLE_CSS + GLOBAL_CSS + theme_web.build_theme_css())


# ═══════════════════════════════════════════════════════════════
# 组件定义
# ═══════════════════════════════════════════════════════════════


def _read_published_version() -> str:
    """读数据根 downloads/version.json 里的发布版本（与客户端下载/首页徽章同一数据源）。

    路径由 `app_data.downloads_dir()` 唯一决定（部署态在部署目录之外）。
    读不到就返回空串——顶栏宁可不显示版本，也不要显示一个写死的假版本号。
    """
    vj = app_data.downloads_dir() / "version.json"
    try:
        if vj.exists():
            data = json.loads(vj.read_text(encoding="utf-8"))
            return str(data.get("version", "") or "")
    except Exception:
        pass
    return ""


PUBLISHED_VERSION = _read_published_version()


def version_badge() -> rx.Component:
    """顶栏版本徽章（数据源 = downloads/version.json；无版本信息时不渲染）。"""
    if not PUBLISHED_VERSION:
        return rx.fragment()
    return rx.badge(
        f"v{PUBLISHED_VERSION}", color_scheme="blue", variant="soft", size="2"
    )


def theme_controls_compact() -> rx.Component:
    """主题控件（紧凑：一个预设下拉 + 一个模式循环按钮）。

    工具页顶栏与首页顶栏共用同一实现（单一来源）；两边都不再各写一份。
    """
    return rx.hstack(
        rx.el.select(
            *[
                rx.el.option(o["label"], value=o["value"])
                for o in theme_web.preset_options()
            ],
            value=ThemeState.theme_choice,
            on_change=ThemeState.apply_choice,
            class_name="app-header-select",
            title="主题：预设 / 强调色 / 模式",
            data_testid="theme-preset",
        ),
        rx.el.button(
            rx.hstack(
                rx.icon(ThemeState.mode_button_icon, size=14),
                ThemeState.mode_button_label,
                spacing="1",
            ),
            on_click=ThemeState.cycle_mode,
            class_name="app-header-btn",
            title="切换模式：浅色 → 深色 → 跟随系统",
            data_testid="theme-mode",
        ),
        spacing="2",
        align="center",
    )


def header(show_parse_controls: bool = True) -> rx.Component:
    """顶部导航栏（仅工具页与独立工具页；首页有自己的营销顶栏）

    Args:
        show_parse_controls: 工具页 True（显示协议选择器 + 登录弹窗入口）；
            独立页面（/feedback、/share 等）传 False，协议选择器换成「在线工具」链接，
            管理员按钮直接跳工具页（登录弹窗只挂在工具页）。
    """
    return rx.box(
        rx.box(
            rx.hstack(
                # Logo + 标题（点击回产品首页）
                rx.el.a(
                    rx.hstack(
                        rx.box(
                            rx.icon("zap", size=20, color="white"),
                            style={
                                "width": "38px",
                                "height": "38px",
                                "border_radius": "11px",
                                "background": "rgba(255,255,255,0.16)",
                                "display": "flex",
                                "align_items": "center",
                                "justify_content": "center",
                                "box_shadow": "inset 0 1px 0 rgba(255,255,255,0.25)",
                            },
                        ),
                        rx.vstack(
                            rx.heading(
                                "多协议解析平台",
                                size="3",
                                color="white",
                                font_weight="bold",
                            ),
                            rx.text(
                                "电力通信协议解析 · 支持 12 种协议",
                                size="1",
                                color="rgba(255,255,255,0.72)",
                            ),
                            spacing="0",
                        ),
                        spacing="3",
                    ),
                    href=landing_web.INTERNAL_LINKS["home"],
                    data_testid="nav-brand",
                    style={"text_decoration": "none"},
                ),
                rx.spacer(),
                # 工具页：协议选择器；独立页面：回在线工具（首页另有营销顶栏）
                rx.cond(
                    show_parse_controls,
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
                        rx.el.option(
                            "[11] HDC 1.0 双模互联互通 (Q/GDW 12087.42-2020)",
                            value="11",
                        ),
                        default_value="0",
                        on_change=State.set_protocol,
                        width="320px",
                        class_name="app-header-select",
                    ),
                    rx.el.a(
                        rx.hstack(
                            rx.icon("terminal", size=14),
                            "在线工具",
                            spacing="1",
                        ),
                        href=landing_web.INTERNAL_LINKS["tool"],
                        class_name="app-header-btn",
                        data_testid="nav-tool",
                        style={"text_decoration": "none", "color": "white"},
                    ),
                ),
                # 问题反馈入口
                rx.el.a(
                    rx.hstack(
                        rx.icon("message_square_heart", size=14),
                        "问题反馈",
                        spacing="1",
                    ),
                    href="/feedback",
                    class_name="app-header-btn",
                    data_testid="nav-feedback",
                    style={"text_decoration": "none", "color": "white"},
                ),
                # 作者博客外链（CSDN，新标签页打开）
                rx.el.a(
                    rx.hstack(
                        rx.icon("book_open", size=14),
                        "作者博客",
                        spacing="1",
                    ),
                    href="https://blog.csdn.net/liruitao1993?type=blog",
                    class_name="app-header-btn",
                    data_testid="nav-blog",
                    is_external=True,
                    style={"text_decoration": "none", "color": "white"},
                ),
                # 报文分享页入口
                rx.el.a(
                    rx.hstack(
                        rx.icon("share_2", size=14),
                        "报文分享",
                        spacing="1",
                    ),
                    href="/share",
                    class_name="app-header-btn",
                    data_testid="nav-share",
                    style={"text_decoration": "none", "color": "white"},
                ),
                # 版本徽章（读 downloads/version.json，与首页/客户端下载同源）
                version_badge(),
                # ── 主题控件（仅工具页；独立页面不渲染，避免挤掉导航按钮）──
                rx.cond(
                    show_parse_controls,
                    theme_controls_compact(),
                    rx.fragment(),
                ),
                # 管理员登录/登出按钮（主页开弹窗；独立页面跳回主页弹窗位置）
                rx.cond(
                    State.admin_logged_in,
                    rx.el.button(
                        rx.hstack(rx.icon("log_out", size=14), "退出", spacing="1"),
                        on_click=State.admin_logout,
                        class_name="app-header-btn",
                        data_testid="btn-logout",
                    ),
                    rx.cond(
                        show_parse_controls,
                        rx.el.button(
                            rx.hstack(
                                rx.icon("shield", size=14), "管理员登录", spacing="1"
                            ),
                            on_click=State.toggle_login_dialog,
                            class_name="app-header-btn",
                            data_testid="btn-login",
                        ),
                        rx.el.a(
                            rx.hstack(
                                rx.icon("shield", size=14), "管理员登录", spacing="1"
                            ),
                            href=landing_web.INTERNAL_LINKS["tool"],
                            class_name="app-header-btn",
                            data_testid="btn-login-home",
                            style={"text_decoration": "none", "color": "white"},
                        ),
                    ),
                ),
                # 状态指示
                rx.hstack(
                    rx.box(
                        width="8px",
                        height="8px",
                        border_radius="50%",
                        background="var(--ok)",
                        box_shadow="0 0 6px rgba(74, 222, 128, 0.8)",
                    ),
                    rx.text("就绪", size="1", color="white"),
                    spacing="1",
                ),
                spacing="4",
                width="100%",
                # 板块导航不换行：标题栏高度恒定单行。窄屏时 flex 压缩可收缩项
                # （协议选择器/间距）而非把按钮折到下一行，避免高/矮两种形态跳动
                flex_wrap="nowrap",
            ),
            class_name="app-header-inner",
            width="100%",
            padding_y="3",
        ),
        background="linear-gradient(135deg, var(--accent-ink, #1e40af) 0%, var(--accent, #2563eb) 55%, var(--accent-ink, #3b82f6) 100%)",
        box_shadow="0 2px 16px rgba(30, 64, 175, 0.25)",
        position="sticky",
        top="0",
        z_index="1000",
    )


def newgen_controls() -> rx.Component:
    """新一代载波/国网新一代/HDC 1.0 控制条（协议9/10/11显示）"""
    return rx.cond(
        (State.current_protocol == 9)
        | (State.current_protocol == 10)
        | (State.current_protocol == 11),
        rx.card(
            rx.hstack(
                rx.icon("sliders_horizontal", size=18, color="var(--accent)"),
                rx.text("解析级别:", size="2", font_weight="medium"),
                # 南网新一代（协议9）解析级别
                rx.cond(
                    State.current_protocol == 9,
                    rx.el.select(
                        *[
                            rx.el.option(o["label"], value=o["value"])
                            for o in web_utils.CSG_PARSE_LEVEL_OPTIONS
                        ],
                        default_value="auto",
                        on_change=State.set_csg_level,
                        class_name="app-select",
                    ),
                ),
                # 国网新一代（协议10）解析级别
                rx.cond(
                    State.current_protocol == 10,
                    rx.el.select(
                        *[
                            rx.el.option(o["label"], value=o["value"])
                            for o in web_utils.GW_PARSE_LEVEL_OPTIONS
                        ],
                        default_value="auto",
                        on_change=State.set_gw_level,
                        class_name="app-select",
                    ),
                ),
                # HDC 1.0（协议11）解析级别
                rx.cond(
                    State.current_protocol == 11,
                    rx.el.select(
                        *[
                            rx.el.option(o["label"], value=o["value"])
                            for o in web_utils.GW_PARSE_LEVEL_OPTIONS
                        ],
                        default_value="auto",
                        on_change=State.set_hdc10_level,
                        class_name="app-select",
                    ),
                ),
                # 物理块帧类型：协议9（mac_only/pb_only）与协议10/11（pb_only）
                # 协议9 用 sof/beacon/sack/net，协议10/11 用 1/0/2/3
                rx.cond(
                    (State.current_protocol == 9)
                    & (
                        (State.csg_parse_level == "pb_only")
                        | (State.csg_parse_level == "mac_only")
                    ),
                    rx.hstack(
                        rx.text("PB帧类型:", size="2", font_weight="medium"),
                        rx.el.select(
                            *[
                                rx.el.option(o["label"], value=o["value"])
                                for o in web_utils.CSG_PB_FRAME_TYPE_OPTIONS
                            ],
                            default_value="sof",
                            on_change=State.set_csg_pb_frame_type,
                            class_name="app-select",
                        ),
                        spacing="2",
                        align="center",
                    ),
                ),
                rx.cond(
                    (State.current_protocol == 10)
                    & (State.gw_parse_level == "pb_only"),
                    rx.hstack(
                        rx.text("PB帧类型:", size="2", font_weight="medium"),
                        rx.el.select(
                            *[
                                rx.el.option(o["label"], value=o["value"])
                                for o in web_utils.GW_PB_FRAME_TYPE_OPTIONS
                            ],
                            default_value="1",
                            on_change=State.set_gw_pb_frame_type,
                            class_name="app-select",
                        ),
                        spacing="2",
                        align="center",
                    ),
                ),
                rx.cond(
                    (State.current_protocol == 11)
                    & (State.hdc10_parse_level == "pb_only"),
                    rx.hstack(
                        rx.text("PB帧类型:", size="2", font_weight="medium"),
                        rx.el.select(
                            *[
                                rx.el.option(o["label"], value=o["value"])
                                for o in web_utils.GW_PB_FRAME_TYPE_OPTIONS
                            ],
                            default_value="1",
                            on_change=State.set_gw_pb_frame_type,
                            class_name="app-select",
                        ),
                        spacing="2",
                        align="center",
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
                                class_name="app-select",
                            ),
                            rx.el.select(
                                rx.el.option("PLC 载波", value="plc"),
                                rx.el.option("HRF 无线", value="hrf"),
                                default_value="plc",
                                on_change=State.set_hdc10_channel,
                                class_name="app-select",
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
                State.message_type == "success",
                "check_circle",
                rx.cond(
                    State.message_type == "error",
                    "x_circle",
                    rx.cond(State.message_type == "warning", "alert_triangle", "info"),
                ),
            ),
            color_scheme=rx.cond(
                State.message_type == "success",
                "green",
                rx.cond(
                    State.message_type == "error",
                    "red",
                    rx.cond(State.message_type == "warning", "amber", "blue"),
                ),
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
                    rx.icon("file_input", size=20, color="var(--accent)"),
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
                        rx.cond(
                            State.is_loading,
                            rx.spinner(size="1"),
                            rx.icon("play", size=16),
                        ),
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
                        rx.icon("share_2", size=16),
                        "分享此帧",
                        on_click=ShareState.sf_open_dialog,
                        variant="outline",
                        color_scheme="teal",
                        size="2",
                        disabled=State.last_parsed_hex == "",
                        data_testid="btn-share-frame",
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
                        rx.icon("table", size=20, color="var(--accent)"),
                        rx.heading("解析结果", size="3", font_weight="semibold"),
                        rx.spacer(),
                        rx.badge(
                            f"{State.parse_result.length()} 条",
                            color_scheme="blue",
                            variant="soft",
                        ),
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
                                        rx.table.cell(
                                            row["field"], font_weight="medium"
                                        ),
                                        rx.table.cell(
                                            rx.code(row["raw"], variant="soft")
                                        ),
                                        rx.table.cell(row["parsed"]),
                                        rx.table.cell(
                                            rx.text(
                                                row["comment"], size="1", color="gray"
                                            )
                                        ),
                                    ),
                                )
                            ),
                            variant="surface",
                            size="1",
                            width="100%",
                        ),
                        rx.center(
                            rx.vstack(
                                rx.icon("inbox", size=48, color="var(--muted-2)"),
                                rx.text("暂无解析结果", color="var(--muted)", size="2"),
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
                        rx.icon("circle_check", size=20, color="var(--ok)"),
                        rx.heading("校验结果", size="3", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.cond(
                        State.verify_result != "",
                        rx.text(
                            State.verify_result,
                            font_family="monospace",
                            font_size="12px",
                            white_space="pre-wrap",
                        ),
                        rx.center(
                            rx.vstack(
                                rx.icon("shield", size=48, color="var(--muted-2)"),
                                rx.text(
                                    "点击「校验报文」进行协议一致性校验",
                                    color="var(--muted)",
                                    size="2",
                                ),
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
                    rx.icon("list", size=20, color="var(--accent)"),
                    rx.heading("批量报文输入", size="3", font_weight="semibold"),
                    rx.spacer(),
                    rx.text("(支持监控日志/纯HEX)", size="1", color="gray"),
                    spacing="2",
                ),
                # ── 拖拽上传区域 ──
                rx.upload(
                    rx.vstack(
                        rx.hstack(
                            rx.icon("upload", size=20, color="var(--accent)"),
                            rx.text(
                                "将日志文件拖拽到此处，或点击选择文件",
                                size="2",
                                font_weight="medium",
                            ),
                            spacing="2",
                            align="center",
                        ),
                        rx.text(
                            "支持 .log / .txt / 纯文本文件；大文件会自动分块解析",
                            size="1",
                            color="gray",
                        ),
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
                            rx.icon("file_check", size=16, color="var(--ok)"),
                            rx.vstack(
                                rx.text(
                                    f"{State.batch_upload_name}（{round(State.batch_upload_size / (1024 * 1024), 2)} MB，{State.batch_file_lines} 行）",
                                    size="1",
                                    font_weight="medium",
                                ),
                                rx.text(
                                    "文件内容已保存在服务器端（不加载到页面），点击「批量解析」即可处理",
                                    size="1",
                                    color="gray",
                                ),
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
                            rx.icon("wand", size=16, color="var(--accent)"),
                            rx.text(
                                "预处理（命令链）", size="2", font_weight="semibold"
                            ),
                            rx.spacer(),
                            rx.text(
                                "支持: find / excluding / replace / head / tail / skip / hex_extract / tcp_extract / merge_payloads / dedup（半角空格分隔，全角自动归一化）",
                                size="1",
                                color="gray",
                            ),
                            spacing="2",
                            align="center",
                        ),
                        rx.hstack(
                            rx.el.select(
                                rx.el.option("-- 选择预设 --", value="__custom__"),
                                rx.el.option(
                                    "提取 tcp data 帧",
                                    value="find tcp data: tcp_extract",
                                ),
                                rx.el.option(
                                    "提取监控日志帧",
                                    value="find > 接收机 Has Get hex_extract",
                                ),
                                rx.el.option(
                                    "合并跨行 payload", value="merge_payloads"
                                ),
                                rx.el.option("提取最长 hex 序列", value="hex_extract"),
                                rx.el.option("去重复行", value="dedup"),
                                rx.el.option("过滤含 60F0 的行", value="find 60F0"),
                                default_value="__custom__",
                                on_change=State.apply_pp_preset,
                                width="220px",
                                class_name="app-select",
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
                            rx.text(
                                State.batch_pp_last_result, size="1", color="violet"
                            ),
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
                        rx.cond(
                            State.is_loading,
                            rx.spinner(size="1"),
                            rx.icon("play", size=16),
                        ),
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
                    rx.text(
                        f"共 {State.batch_total_frames} 帧", size="1", color="gray"
                    ),
                    spacing="3",
                ),
                # ── 解析进度条 ──
                rx.cond(
                    (State.batch_total > 0)
                    & (State.batch_progress < State.batch_total),
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
                            size="1",
                            color="gray",
                            white_space="nowrap",
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
                        rx.icon("table", size=18, color="var(--accent)"),
                        rx.heading("批量解析摘要", size="2", font_weight="semibold"),
                        spacing="2",
                    ),
                    # ── 搜索 + 状态筛选（口径同桌面 _on_batch_filter_changed）──
                    rx.hstack(
                        rx.icon("search", size=15, color="var(--muted)"),
                        rx.input(
                            value=State.batch_search,
                            on_change=State.set_batch_search,
                            placeholder="搜索：摘要 / 类型 / 帧HEX / #序号",
                            size="1",
                            width="100%",
                            font_family="monospace",
                            data_testid="batch-search",
                        ),
                        rx.el.select(
                            *[
                                rx.el.option(label, value=value)
                                for value, label in web_utils.BATCH_STATUS_FILTERS
                            ],
                            value=State.batch_status_filter,
                            on_change=State.set_batch_status_filter,
                            class_name="app-select",
                            title="按状态筛选",
                            data_testid="batch-status-filter",
                        ),
                        rx.cond(
                            (State.batch_search != "")
                            | (State.batch_status_filter != "all"),
                            rx.text(
                                f"显示 {State.batch_visible_count} / {State.batch_total_frames}",
                                size="1",
                                color="var(--muted)",
                                white_space="nowrap",
                                data_testid="batch-filter-count",
                            ),
                        ),
                        spacing="2",
                        align="center",
                        width="100%",
                    ),
                    rx.cond(
                        State.batch_results.length() > 0,
                        rx.vstack(
                            # 分页条放在列表上方：不必滚动就能翻页（大列表下方看不到）
                            rx.hstack(
                                rx.text(
                                    f"共 {State.batch_total_frames} 帧",
                                    size="1",
                                    color="gray",
                                ),
                                rx.spacer(),
                                rx.button(
                                    rx.icon("chevrons_left", size=14),
                                    "首页",
                                    on_click=State.batch_first_page,
                                    disabled=State.batch_page <= 0,
                                    size="1",
                                    variant="soft",
                                ),
                                rx.button(
                                    rx.icon("chevron_left", size=14),
                                    "上一页",
                                    on_click=State.batch_prev_page,
                                    disabled=State.batch_page <= 0,
                                    size="1",
                                    variant="soft",
                                ),
                                rx.text(
                                    f"第 {State.batch_page + 1} / {State.batch_page_count} 页",
                                    size="1",
                                    font_weight="medium",
                                    white_space="nowrap",
                                ),
                                rx.button(
                                    "下一页",
                                    rx.icon("chevron_right", size=14),
                                    on_click=State.batch_next_page,
                                    disabled=State.batch_page
                                    >= State.batch_page_count - 1,
                                    size="1",
                                    variant="soft",
                                ),
                                rx.button(
                                    "末页",
                                    rx.icon("chevrons_right", size=14),
                                    on_click=State.batch_last_page,
                                    disabled=State.batch_page
                                    >= State.batch_page_count - 1,
                                    size="1",
                                    variant="soft",
                                ),
                                rx.text("每页", size="1", color="gray"),
                                rx.el.select(
                                    *[
                                        rx.el.option(str(n), value=str(n))
                                        for n in PAGE_SIZE_OPTIONS
                                    ],
                                    default_value="100",
                                    on_change=State.set_batch_page_size,
                                    class_name="app-select",
                                ),
                                spacing="2",
                                align="center",
                                width="100%",
                            ),
                            rx.scroll_area(
                                rx.vstack(
                                    rx.foreach(
                                        State.batch_results,
                                        lambda item, idx: rx.card(
                                            rx.hstack(
                                                rx.badge(
                                                    item["status"],
                                                    color_scheme=rx.cond(
                                                        item["status"] == "成功",
                                                        "green",
                                                        rx.cond(
                                                            item["status"] == "失败",
                                                            "red",
                                                            "amber",
                                                        ),
                                                    ),
                                                    variant="soft",
                                                    size="1",
                                                ),
                                                rx.text(
                                                    # 全局序号（跨页连续）
                                                    "#"
                                                    + (
                                                        item["id"].to(int) + 1
                                                    ).to_string(),
                                                    size="1",
                                                    font_weight="bold",
                                                ),
                                                rx.text(
                                                    item["len"].to_string() + "B",
                                                    size="1",
                                                    color="gray",
                                                ),
                                                rx.text(
                                                    item["proto"],
                                                    size="1",
                                                    font_weight="medium",
                                                ),
                                                rx.spacer(),
                                                spacing="2",
                                                align="center",
                                            ),
                                            rx.text(
                                                item["summary"],
                                                size="1",
                                                color="gray",
                                                no_of_lines=2,
                                            ),
                                            padding="2",
                                            width="100%",
                                            cursor="pointer",
                                            _hover={"background": "var(--accent-soft)"},
                                            # 选中高亮用 class（`style=rx.cond({...})` 在本项目
                                            # 实测不落到 DOM，class_name=rx.cond 是已验证可用的写法）
                                            class_name=rx.cond(
                                                State.batch_selected_idx
                                                == item["id"].to(int),
                                                "batch-row-selected",
                                                "",
                                            ),
                                            on_click=lambda: State.select_batch_by_index(
                                                idx
                                            ),
                                        ),
                                    ),
                                    spacing="1",
                                    width="100%",
                                ),
                                # 高度随视口（一屏尽量多行），短屏保底 320px
                                height="calc(100vh - 400px)",
                                min_height="300px",
                                width="100%",
                            ),
                            spacing="2",
                            width="100%",
                        ),
                        rx.center(
                            rx.vstack(
                                rx.icon("inbox", size=48, color="var(--muted-2)"),
                                rx.cond(
                                    State.batch_visible_count == 0,
                                    rx.text(
                                        "当前搜索/筛选条件下没有匹配的帧",
                                        color="var(--muted)",
                                        size="2",
                                    ),
                                    rx.text(
                                        "暂无批量解析结果",
                                        color="var(--muted)",
                                        size="2",
                                    ),
                                ),
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
                        rx.icon("zoom_in", size=18, color="var(--accent)"),
                        rx.heading("选中帧详细解析", size="2", font_weight="semibold"),
                        spacing="2",
                    ),
                    # 原始帧 HEX
                    rx.cond(
                        State.batch_detail_hex != "",
                        rx.box(
                            rx.text(
                                "原始帧:", size="1", font_weight="medium", color="gray"
                            ),
                            rx.code(
                                State.batch_detail_hex,
                                variant="soft",
                                font_family="monospace",
                                font_size="11px",
                            ),
                            padding="2",
                            background="var(--accent-soft)",
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
                                        rx.table.column_header_cell(
                                            "字段", width="30%"
                                        ),
                                        rx.table.column_header_cell(
                                            "原始值", width="20%"
                                        ),
                                        rx.table.column_header_cell(
                                            "解析值", width="20%"
                                        ),
                                        rx.table.column_header_cell(
                                            "说明", width="30%"
                                        ),
                                    )
                                ),
                                rx.table.body(
                                    rx.foreach(
                                        State.batch_detail_rows,
                                        lambda row: rx.table.row(
                                            rx.table.cell(
                                                row["field"],
                                                font_weight="medium",
                                                size="1",
                                            ),
                                            rx.table.cell(
                                                rx.code(row["raw"], variant="soft"),
                                                size="1",
                                            ),
                                            rx.table.cell(row["parsed"], size="1"),
                                            rx.table.cell(
                                                rx.text(
                                                    row["comment"],
                                                    size="1",
                                                    color="gray",
                                                )
                                            ),
                                        ),
                                    )
                                ),
                                variant="surface",
                                size="1",
                                width="100%",
                            ),
                            # 高度随视口（比摘要区再让出原始帧 HEX 行的高度）
                            height="calc(100vh - 430px)",
                            min_height="300px",
                        ),
                        rx.center(
                            rx.vstack(
                                rx.icon(
                                    "mouse_pointer", size=48, color="var(--muted-2)"
                                ),
                                rx.text(
                                    "点击左侧摘要行查看详细解析",
                                    color="var(--muted)",
                                    size="2",
                                ),
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

        return [
            {"value": f"0x{v:04X}", "label": f"{name} (0x{v:04X})"}
            for v, name in OI_PRESET_LIST
        ]
    except Exception:
        return []


def _axdr_type_options() -> list:
    """A-XDR 类型下拉选项"""
    from frame_gen_utils import A_XDR_TYPE_LIST

    return [
        {"value": name, "label": f"{desc} (0x{tag:02X})"}
        for name, tag, desc in A_XDR_TYPE_LIST
    ]


def _is_compound(t) -> bool:
    """A-XDR 复合类型判断（返回 Var 布尔，供 rx.cond）"""
    return rx.match(t, ("array", True), ("structure", True), False)


def _is_var_len(t) -> bool:
    """A-XDR 变长类型判断（返回 Var 布尔，供 rx.cond）"""
    return rx.match(
        t,
        ("array", True),
        ("structure", True),
        ("octet-string", True),
        ("visible-string", True),
        ("UTF8-string", True),
        ("bit-string", True),
        False,
    )


def _searchable_select(
    label: str,
    search_query: Any,
    set_search: Any,
    options: Any,
    filtered: Any,
    on_select: Any,
    selected: Any,
    selected_label: Any,
    placeholder: str,
    open_flag: Any,
    set_open: Any,
    close: Any,
) -> rx.Component:
    """可搜索下拉：聚焦展开全部选项，输入实时过滤，点击选择（对齐 GUI QComboBox+QCompleter）

    options 为全部选项 Var（未输入时展示），filtered 为过滤结果 Var，
    两者元素统一为 {"value": ..., "label": ...}。
    列表在搜索词非空或输入框聚焦时显示；选项按钮用 on_mouse_down 选择，
    确保先于输入框 blur 触发（blur 会收起列表，避免点击丢失）。
    """

    def _option_btn(opt: Any) -> rx.Component:
        return rx.el.button(
            rx.cond(
                opt["value"] != opt["name"],
                rx.fragment(
                    rx.el.span(opt["value"], class_name="sd-value"),
                    rx.el.span(opt["name"], class_name="sd-name"),
                ),
                rx.el.span(opt["name"], class_name="sd-name"),
            ),
            on_mouse_down=on_select(opt["value"]),
            class_name="sd-row",
        )

    return rx.vstack(
        rx.hstack(
            rx.text(label, size="2", font_weight="medium", width="60px"),
            rx.input(
                placeholder=placeholder,
                value=search_query,
                on_change=set_search,
                on_focus=set_open,
                on_click=set_open,  # 已聚焦时再次点击无 focus 事件，用 click 兜底展开
                on_blur=close,
                style={"flex": "1", "min_width": "0"},
            ),
            spacing="2",
            width="100%",
        ),
        # 已选提示（完整标签：代码+名称）
        rx.cond(
            selected != "",
            rx.hstack(
                rx.icon("check", size=14, color="var(--ok)"),
                rx.text("已选: ", size="1", color="var(--ok)"),
                rx.text(selected_label, size="1", color="var(--ok)"),
                spacing="1",
            ),
        ),
        # 选项列表（搜索词非空或输入框聚焦时显示）
        rx.cond(
            (search_query != "") | open_flag,
            rx.box(
                rx.cond(
                    search_query != "",
                    rx.cond(
                        filtered.length() > 0,
                        rx.vstack(
                            rx.foreach(filtered, _option_btn),
                            spacing="0",
                        ),
                        rx.text("无匹配选项", class_name="sd-empty"),
                    ),
                    rx.vstack(
                        rx.foreach(options, _option_btn),
                        spacing="0",
                    ),
                ),
                class_name="searchable-dropdown",
            ),
        ),
        spacing="2",
        width="100%",
    )


def _field_input(
    f: Any = None,
    name: str = "",
    ftype: str = "bytes",
    default: str = "",
    enum_map: Any = None,
    on_change=None,
    placeholder: str = "",
    monospace: bool = True,
) -> rx.Component:
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
            width="100%",
        )
    if ftype == "bytes":
        # bytes 字段（报文内容/帧数据）用多行 text_area，完整显示长报文
        return rx.text_area(
            value=State.gen_fields[name].to(str) if name else default,
            on_change=on_change,
            placeholder=placeholder or default,
            font_family="monospace",
            size="1",
            width="100%",
            min_height="60px",
        )
    return rx.input(
        value=State.gen_fields[name].to(str) if name else default,
        on_change=on_change,
        placeholder=placeholder or default,
        font_family="monospace",
        size="1",
        width="100%",
    )


def frame_gen_tab() -> rx.Component:
    """协议组帧（南网/国网/698.45）"""

    # ── 模式选择（predefined / custom / axdr）──
    def mode_selector() -> rx.Component:
        return rx.cond(
            (State.current_protocol == 0)
            | (State.current_protocol == 7)
            | (State.current_protocol == 8),
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("layers", size=18, color="var(--accent)"),
                        rx.heading("组帧模式", size="3", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.hstack(
                        rx.cond(
                            State.current_protocol == 8,
                            # 698.45：predefined / axdr（custom 禁用，对齐 GUI :644）
                            rx.hstack(
                                rx.button(
                                    "预定字段",
                                    on_click=lambda: State.set_gen_mode("predefined"),
                                    color_scheme=rx.cond(
                                        State.gen_mode == "predefined", "blue", "gray"
                                    ),
                                    variant=rx.cond(
                                        State.gen_mode == "predefined", "solid", "soft"
                                    ),
                                    size="2",
                                ),
                                rx.button(
                                    "A-XDR",
                                    on_click=lambda: State.set_gen_mode("axdr"),
                                    color_scheme=rx.cond(
                                        State.gen_mode == "axdr", "purple", "gray"
                                    ),
                                    variant=rx.cond(
                                        State.gen_mode == "axdr", "solid", "soft"
                                    ),
                                    size="2",
                                ),
                                spacing="2",
                            ),
                            # 南网/国网：predefined / custom
                            rx.hstack(
                                rx.button(
                                    "预定字段",
                                    on_click=lambda: State.set_gen_mode("predefined"),
                                    color_scheme=rx.cond(
                                        State.gen_mode == "predefined", "blue", "gray"
                                    ),
                                    variant=rx.cond(
                                        State.gen_mode == "predefined", "solid", "soft"
                                    ),
                                    size="2",
                                ),
                                rx.button(
                                    "自定义模板",
                                    on_click=lambda: State.set_gen_mode("custom"),
                                    color_scheme=rx.cond(
                                        State.gen_mode == "custom", "orange", "gray"
                                    ),
                                    variant=rx.cond(
                                        State.gen_mode == "custom", "solid", "soft"
                                    ),
                                    size="2",
                                ),
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
                        rx.icon("bookmark", size=18, color="var(--accent)"),
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
                                rx.text(
                                    g, size="2", font_weight="semibold", color="gray"
                                ),
                                rx.flex(
                                    rx.foreach(
                                        State.gen_preset_buttons,
                                        lambda b: rx.cond(
                                            (b["group"] == g)
                                            & (
                                                b["name"].contains(
                                                    State.gen_preset_search
                                                )
                                                | b["group"].contains(
                                                    State.gen_preset_search
                                                )
                                            ),
                                            rx.hstack(
                                                rx.button(
                                                    b["name"],
                                                    on_click=lambda: State.apply_preset(
                                                        b["frame_hex"]
                                                    ),
                                                    variant="outline",
                                                    size="1",
                                                ),
                                                rx.cond(
                                                    State.gen_preset_edit_id == b["id"],
                                                    rx.hstack(
                                                        rx.input(
                                                            value=State.gen_preset_edit_name,
                                                            on_change=lambda v: State.set_gen_preset_edit_field(
                                                                "name", v
                                                            ),
                                                            size="1",
                                                            width="120px",
                                                            placeholder="名称",
                                                        ),
                                                        rx.input(
                                                            value=State.gen_preset_edit_group,
                                                            on_change=lambda v: State.set_gen_preset_edit_field(
                                                                "group", v
                                                            ),
                                                            size="1",
                                                            width="110px",
                                                            placeholder="分组",
                                                        ),
                                                        rx.button(
                                                            "保存",
                                                            on_click=State.save_preset_edit,
                                                            size="1",
                                                            color_scheme="green",
                                                        ),
                                                        rx.button(
                                                            "取消",
                                                            on_click=State.cancel_edit_preset,
                                                            size="1",
                                                            variant="ghost",
                                                        ),
                                                        spacing="1",
                                                        align="center",
                                                    ),
                                                    rx.hstack(
                                                        rx.button(
                                                            rx.icon("pencil", size=12),
                                                            on_click=lambda: State.start_edit_preset(
                                                                b["id"]
                                                            ),
                                                            variant="ghost",
                                                            size="1",
                                                        ),
                                                        rx.button(
                                                            rx.icon("trash", size=12),
                                                            on_click=lambda: State.remove_preset(
                                                                b["id"]
                                                            ),
                                                            variant="ghost",
                                                            size="1",
                                                            color_scheme="red",
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
                            on_change=lambda v: State.set_gen_preset_save_field(
                                "name", v
                            ),
                            placeholder="命令名称",
                            size="1",
                            width="150px",
                        ),
                        rx.input(
                            value=State.gen_preset_group,
                            on_change=lambda v: State.set_gen_preset_save_field(
                                "group", v
                            ),
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

    # ── EB 数据标识 645/698 帧生成器（协议7 透明转发报文内容辅助）──
    def eb_645_generator() -> rx.Component:
        return rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("layers", size=18, color="var(--accent)"),
                    rx.heading(
                        "EB 数据标识 帧生成器", size="2", font_weight="semibold"
                    ),
                    rx.text(
                        "（附件1 本地通信模块扩展协议 V3.42）", size="1", color="gray"
                    ),
                    spacing="2",
                ),
                rx.text(
                    "用于填充 52H-F1 透明转发 / 56H-F2 事件上报的「报文内容」字段：选择 EB 数据标识后自动生成完整帧（645 或 698.45），一键填入。",
                    size="1",
                    color="gray",
                ),
                rx.hstack(
                    rx.vstack(
                        rx.text("承载格式:", size="1", font_weight="medium"),
                        rx.el.select(
                            rx.el.option("645 帧（68 封装）", value="645"),
                            rx.el.option("698.45 APDU（裸 APDU）", value="698"),
                            default_value="645",
                            on_change=State.set_eb_format,
                            class_name="w-full rounded border border-gray-300 px-3 py-1.5",
                            size="1",
                        ),
                        spacing="1",
                        width="100%",
                    ),
                    rx.vstack(
                        rx.text("EB 数据标识:", size="1", font_weight="medium"),
                        rx.el.select(
                            rx.el.option("-- 选择 EB 数据标识 --", value=""),
                            rx.foreach(
                                State.eb_di_options,
                                lambda o: rx.el.option(o["label"], value=o["value"]),
                            ),
                            default_value="",
                            on_change=State.set_eb_di,
                            class_name="w-full rounded border border-gray-300 px-3 py-1.5",
                            size="1",
                        ),
                        spacing="1",
                        width="100%",
                    ),
                    columns="2",
                    spacing="3",
                    width="100%",
                ),
                # ── 645 格式控件 ──
                rx.cond(
                    State.gen_eb_format == "645",
                    rx.vstack(
                        rx.hstack(
                            rx.vstack(
                                rx.text("645 控制码:", size="1", font_weight="medium"),
                                rx.el.select(
                                    rx.el.option("91H 读数据响应", value="91"),
                                    rx.el.option("11H 读数据请求", value="11"),
                                    rx.el.option("14H 写数据请求", value="14"),
                                    rx.el.option("94H 写数据响应", value="94"),
                                    rx.el.option("81H 主动上报", value="81"),
                                    rx.el.option("01H 上报确认", value="01"),
                                    default_value="91",
                                    on_change=State.set_eb_ctrl,
                                    class_name="w-full rounded border border-gray-300 px-3 py-1.5",
                                    size="1",
                                ),
                                spacing="1",
                                width="100%",
                            ),
                            rx.vstack(
                                rx.text(
                                    "地址域 A0~A5 (hex):",
                                    size="1",
                                    font_weight="medium",
                                ),
                                rx.input(
                                    value=State.gen_eb_addr,
                                    on_change=State.set_eb_addr,
                                    placeholder="12位hex，如 000000000000",
                                    font_family="monospace",
                                    size="1",
                                ),
                                spacing="1",
                                width="100%",
                            ),
                            columns="2",
                            spacing="3",
                            width="100%",
                        ),
                        rx.vstack(
                            rx.text(
                                "数据内容 (hex，可留空):",
                                size="1",
                                font_weight="medium",
                            ),
                            rx.input(
                                value=State.gen_eb_data,
                                on_change=State.set_eb_data,
                                placeholder="如 01 01 11 22 33 44 55 66（停上电类型+数量+地址）",
                                font_family="monospace",
                                size="1",
                                width="100%",
                            ),
                            spacing="1",
                            width="100%",
                        ),
                        spacing="3",
                        width="100%",
                    ),
                ),
                # ── 698 格式控件 ──
                rx.cond(
                    State.gen_eb_format == "698",
                    rx.vstack(
                        # 数据内容来源切换
                        rx.hstack(
                            rx.vstack(
                                rx.text(
                                    "数据内容来源:", size="1", font_weight="medium"
                                ),
                                rx.el.select(
                                    rx.el.option("按字段配置（推荐）", value="1"),
                                    rx.el.option("直接填 hex", value="0"),
                                    default_value="1",
                                    on_change=State.set_eb_698_use_field,
                                    class_name="w-full rounded border border-gray-300 px-3 py-1.5",
                                    size="1",
                                ),
                                spacing="1",
                                width="100%",
                            ),
                            rx.vstack(
                                rx.text(
                                    "698 服务类型:", size="1", font_weight="medium"
                                ),
                                rx.el.select(
                                    rx.el.option(
                                        "GET-Request 读取", value="GET-Request"
                                    ),
                                    rx.el.option(
                                        "GET-Response 读响应", value="GET-Response"
                                    ),
                                    rx.el.option(
                                        "SET-Request 设置/配置", value="SET-Request"
                                    ),
                                    rx.el.option(
                                        "SET-Response 写确认", value="SET-Response"
                                    ),
                                    rx.el.option(
                                        "ACTION-Request 操作", value="ACTION-Request"
                                    ),
                                    rx.el.option(
                                        "ACTION-Response 操作响应",
                                        value="ACTION-Response",
                                    ),
                                    rx.el.option(
                                        "REPORT-Notification 主动上报",
                                        value="REPORT-Notification",
                                    ),
                                    rx.el.option(
                                        "REPORT-Response 上报确认",
                                        value="REPORT-Response",
                                    ),
                                    default_value="SET-Request",
                                    on_change=State.set_eb_698_service,
                                    class_name="w-full rounded border border-gray-300 px-3 py-1.5",
                                    size="1",
                                ),
                                spacing="1",
                                width="100%",
                            ),
                            columns="2",
                            spacing="3",
                            width="100%",
                        ),
                        # ── 按字段配置数据内容 ──
                        rx.cond(
                            State.eb_698_use_field
                            & (State.eb_di_field_use)
                            & (State.gen_eb_di != ""),
                            rx.vstack(
                                rx.text(
                                    "数据内容字段（按附件1 V3.42 定义）:",
                                    size="1",
                                    font_weight="medium",
                                ),
                                rx.foreach(
                                    State.eb_di_fields,
                                    lambda f, i: rx.vstack(
                                        rx.hstack(
                                            rx.text(
                                                f["name"],
                                                size="1",
                                                font_weight="medium",
                                                width="200px",
                                            ),
                                            rx.cond(
                                                f["has_enum"] == "1",
                                                rx.el.select(
                                                    rx.el.option(
                                                        "-- 选择 --", value=""
                                                    ),
                                                    rx.foreach(
                                                        State.eb_di_field_enum[i],
                                                        lambda o: rx.el.option(
                                                            o["label"], value=o["value"]
                                                        ),
                                                    ),
                                                    default_value=State.eb_di_field_vals[
                                                        i
                                                    ],
                                                    on_change=lambda val,
                                                    idx=i: State.set_eb_field(idx, val),
                                                    class_name="flex-1 rounded border border-gray-300 px-3 py-1.5",
                                                    size="1",
                                                ),
                                                rx.cond(
                                                    f["has_list"] == "1",
                                                    rx.vstack(
                                                        rx.foreach(
                                                            State.eb_di_field_list[i],
                                                            lambda row, r: rx.hstack(
                                                                rx.foreach(
                                                                    State.eb_di_field_list_meta[
                                                                        i
                                                                    ],
                                                                    lambda it,
                                                                    c: rx.input(
                                                                        value=row[c].to(
                                                                            str
                                                                        ),
                                                                        on_change=lambda val,
                                                                        fi=i,
                                                                        rr=r,
                                                                        cc=c: State.set_eb_list_cell(
                                                                            fi,
                                                                            rr,
                                                                            cc,
                                                                            val,
                                                                        ),
                                                                        placeholder=it[
                                                                            "name"
                                                                        ],
                                                                        font_family="monospace",
                                                                        size="1",
                                                                        width="140px",
                                                                    ),
                                                                ),
                                                                spacing="1",
                                                            ),
                                                        ),
                                                        rx.button(
                                                            "添加一行",
                                                            on_click=lambda fi=i: State.add_eb_list_row(
                                                                fi
                                                            ),
                                                            size="1",
                                                            variant="soft",
                                                        ),
                                                        spacing="1",
                                                    ),
                                                    rx.input(
                                                        value=State.eb_di_field_vals[
                                                            i
                                                        ].to(str),
                                                        on_change=lambda val,
                                                        idx=i: State.set_eb_field(
                                                            idx, val
                                                        ),
                                                        placeholder=f["note"],
                                                        font_family="monospace",
                                                        size="1",
                                                        width="100%",
                                                    ),
                                                ),
                                            ),
                                            spacing="2",
                                            width="100%",
                                        ),
                                        spacing="1",
                                        width="100%",
                                    ),
                                ),
                                spacing="2",
                                width="100%",
                            ),
                        ),
                        # ── 自由 hex 数据 ──
                        rx.cond(
                            ~State.eb_698_use_field,
                            rx.vstack(
                                rx.text(
                                    "数据内容 (hex，A-XDR octet-string):",
                                    size="1",
                                    font_weight="medium",
                                ),
                                rx.input(
                                    value=State.gen_eb_698_data,
                                    on_change=State.set_eb_698_data,
                                    placeholder="如 00 00 05（台区识别方法+时长）",
                                    font_family="monospace",
                                    size="1",
                                    width="100%",
                                ),
                                spacing="1",
                                width="100%",
                            ),
                        ),
                        # ── 链路层头部配置 ──
                        rx.text(
                            "698.45 链路层头部（完整帧 68 L C SA CA HCS APDU FCS 16）:",
                            size="1",
                            font_weight="medium",
                        ),
                        rx.hstack(
                            rx.vstack(
                                rx.text("SA 地址类型:", size="1", font_weight="medium"),
                                rx.el.select(
                                    rx.el.option("单地址(0)", value="0"),
                                    rx.el.option("通配地址(1)", value="1"),
                                    rx.el.option("组地址(2)", value="2"),
                                    rx.el.option("广播地址(3)", value="3"),
                                    default_value="0",
                                    on_change=State.set_eb_addr_type,
                                    class_name="w-full rounded border border-gray-300 px-3 py-1.5",
                                    size="1",
                                ),
                                spacing="1",
                                width="100%",
                            ),
                            rx.vstack(
                                rx.text("SA 地址长度:", size="1", font_weight="medium"),
                                rx.input(
                                    value=State.gen_eb_addr_len.to(str),
                                    on_change=State.set_eb_addr_len,
                                    placeholder="6",
                                    size="1",
                                    width="70px",
                                ),
                                spacing="1",
                                width="100%",
                            ),
                            rx.vstack(
                                rx.text(
                                    "SA 地址 (hex):", size="1", font_weight="medium"
                                ),
                                rx.input(
                                    value=State.gen_eb_sa_raw,
                                    on_change=State.set_eb_sa_raw,
                                    placeholder="000000000000",
                                    font_family="monospace",
                                    size="1",
                                ),
                                spacing="1",
                                width="100%",
                            ),
                            rx.vstack(
                                rx.text(
                                    "CA 客户机地址:", size="1", font_weight="medium"
                                ),
                                rx.input(
                                    value=State.gen_eb_ca,
                                    on_change=State.set_eb_ca,
                                    placeholder="0",
                                    size="1",
                                    width="60px",
                                ),
                                spacing="1",
                                width="100%",
                            ),
                            columns="4",
                            spacing="3",
                            width="100%",
                        ),
                        rx.hstack(
                            rx.vstack(
                                rx.text("DIR:", size="1", font_weight="medium"),
                                rx.el.select(
                                    rx.el.option("0-客户机→服务器", value="0"),
                                    rx.el.option("1-服务器→客户机", value="1"),
                                    default_value="0",
                                    on_change=State.set_eb_dir,
                                    class_name="w-full rounded border border-gray-300 px-3 py-1.5",
                                    size="1",
                                ),
                                spacing="1",
                                width="100%",
                            ),
                            rx.vstack(
                                rx.text("PRM:", size="1", font_weight="medium"),
                                rx.el.select(
                                    rx.el.option("1-启动站", value="1"),
                                    rx.el.option("0-从动站", value="0"),
                                    default_value="1",
                                    on_change=State.set_eb_prm,
                                    class_name="w-full rounded border border-gray-300 px-3 py-1.5",
                                    size="1",
                                ),
                                spacing="1",
                                width="100%",
                            ),
                            rx.vstack(
                                rx.text("功能码:", size="1", font_weight="medium"),
                                rx.el.select(
                                    rx.el.option("3-用户数据", value="3"),
                                    rx.el.option("1-链路管理", value="1"),
                                    default_value="3",
                                    on_change=State.set_eb_func,
                                    class_name="w-full rounded border border-gray-300 px-3 py-1.5",
                                    size="1",
                                ),
                                spacing="1",
                                width="100%",
                            ),
                            columns="3",
                            spacing="3",
                            width="100%",
                        ),
                        # ── 对象配置（OAD/OMD 属性/方法/索引 + PIID + 单多对象）──
                        rx.text(
                            "698 对象配置（OAD=OI+属性编号+属性特征+元素索引，ACTION 用 OMD=OI+方法标识+操作模式）:",
                            size="1",
                            font_weight="medium",
                        ),
                        rx.hstack(
                            rx.vstack(
                                rx.text("对象个数:", size="1", font_weight="medium"),
                                rx.el.select(
                                    rx.el.option("一个对象(01)", value="one"),
                                    rx.el.option("若干对象(02, 列表)", value="list"),
                                    default_value="list",
                                    on_change=State.set_eb_choice,
                                    class_name="w-full rounded border border-gray-300 px-3 py-1.5",
                                    size="1",
                                ),
                                spacing="1",
                                width="100%",
                            ),
                            rx.vstack(
                                rx.text(
                                    "PIID 服务序号:", size="1", font_weight="medium"
                                ),
                                rx.input(
                                    value=State.gen_eb_piid,
                                    on_change=State.set_eb_piid,
                                    placeholder="0",
                                    size="1",
                                    width="60px",
                                ),
                                spacing="1",
                                width="100%",
                            ),
                            rx.vstack(
                                rx.text(
                                    "OI (hex, 空=EB标识):",
                                    size="1",
                                    font_weight="medium",
                                ),
                                rx.input(
                                    value=State.gen_eb_oi,
                                    on_change=State.set_eb_oi,
                                    placeholder="EB03",
                                    font_family="monospace",
                                    size="1",
                                ),
                                spacing="1",
                                width="100%",
                            ),
                            columns="3",
                            spacing="3",
                            width="100%",
                        ),
                        rx.cond(
                            State.gen_eb_698_service.startswith("ACTION"),
                            # ACTION: 方法标识 + 操作模式
                            rx.hstack(
                                rx.vstack(
                                    rx.text(
                                        "方法标识(空=EB标识):",
                                        size="1",
                                        font_weight="medium",
                                    ),
                                    rx.input(
                                        value=State.gen_eb_method,
                                        on_change=State.set_eb_method,
                                        placeholder="0",
                                        size="1",
                                        width="70px",
                                    ),
                                    spacing="1",
                                    width="100%",
                                ),
                                rx.vstack(
                                    rx.text(
                                        "操作模式:", size="1", font_weight="medium"
                                    ),
                                    rx.input(
                                        value=State.gen_eb_mode,
                                        on_change=State.set_eb_mode,
                                        placeholder="0",
                                        size="1",
                                        width="70px",
                                    ),
                                    spacing="1",
                                    width="100%",
                                ),
                                columns="2",
                                spacing="3",
                                width="100%",
                            ),
                            # GET/SET: 属性编号 + 属性特征 + 元素索引
                            rx.hstack(
                                rx.vstack(
                                    rx.text(
                                        "属性编号(空=EB标识):",
                                        size="1",
                                        font_weight="medium",
                                    ),
                                    rx.input(
                                        value=State.gen_eb_attr_no,
                                        on_change=State.set_eb_attr_no,
                                        placeholder="0",
                                        size="1",
                                        width="70px",
                                    ),
                                    spacing="1",
                                    width="100%",
                                ),
                                rx.vstack(
                                    rx.text(
                                        "属性特征:", size="1", font_weight="medium"
                                    ),
                                    rx.input(
                                        value=State.gen_eb_attr_feat,
                                        on_change=State.set_eb_attr_feat,
                                        placeholder="0",
                                        size="1",
                                        width="70px",
                                    ),
                                    spacing="1",
                                    width="100%",
                                ),
                                rx.vstack(
                                    rx.text(
                                        "元素索引(空=EB标识):",
                                        size="1",
                                        font_weight="medium",
                                    ),
                                    rx.input(
                                        value=State.gen_eb_index,
                                        on_change=State.set_eb_index,
                                        placeholder="0",
                                        size="1",
                                        width="70px",
                                    ),
                                    spacing="1",
                                    width="100%",
                                ),
                                columns="3",
                                spacing="3",
                                width="100%",
                            ),
                        ),
                        rx.text(
                            "OAD 默认 = EB 数据标识原样（如 EB030002 → OI=EB03, 属性=00, 索引=02）；可自定义属性/方法/索引。",
                            size="1",
                            color="gray",
                        ),
                        spacing="3",
                        width="100%",
                    ),
                ),
                rx.hstack(
                    rx.button(
                        "生成帧",
                        on_click=State.gen_eb_645_frame,
                        color_scheme="blue",
                        size="2",
                    ),
                    rx.button(
                        "填入报文内容字段",
                        on_click=State.apply_eb_frame_to_content,
                        color_scheme="green",
                        size="2",
                    ),
                    spacing="2",
                ),
                rx.cond(
                    State.gen_eb_msg != "",
                    rx.text(
                        State.gen_eb_msg,
                        color_scheme=rx.cond(
                            State.gen_eb_msg_type == "error", "red", "green"
                        ),
                        size="1",
                    ),
                ),
                rx.cond(
                    State.gen_eb_frame != "",
                    rx.vstack(
                        rx.text("生成的帧:", size="1", font_weight="medium"),
                        rx.scroll_area(
                            rx.text(
                                State.gen_eb_frame,
                                font_family="monospace",
                                font_size="12px",
                                white_space="pre-wrap",
                            ),
                            max_height="80px",
                            width="100%",
                        ),
                        spacing="1",
                        width="100%",
                    ),
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        )

    # ── 动态字段表单（按字段类型分派）──
    def dynamic_fields() -> rx.Component:
        return rx.cond(
            State.gen_field_meta.length() > 0,
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("list_tree", size=18, color="var(--accent)"),
                        rx.heading("数据字段", size="3", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.grid(
                        rx.foreach(
                            State.gen_field_meta,
                            lambda f, i: rx.vstack(
                                rx.hstack(
                                    rx.text(f["name"], size="1", font_weight="medium"),
                                    rx.badge(
                                        f["type"],
                                        variant="soft",
                                        size="1",
                                        color_scheme="gray",
                                    ),
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
                                rx.cond(
                                    f["description"] != "",
                                    rx.text(f["description"], size="1", color="gray"),
                                ),
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
                rx.foreach(
                    State.gen_field_enum[i],
                    lambda o: rx.el.option(o["label"], value=o["value"]),
                ),
                default_value=State.gen_field_meta[i]["default"],
                on_change=lambda val, idx=i: State.set_gen_field(idx, val),
                class_name="w-full rounded border border-gray-300 px-3 py-1.5",
                size="1",
            ),
            rx.cond(
                State.gen_field_meta[i]["type"] == "oi",
                rx.el.select(
                    rx.el.option("-- 选择OI --", value=""),
                    rx.foreach(
                        _oi_options(),
                        lambda o: rx.el.option(o["label"], value=o["value"]),
                    ),
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
                    rx.cond(
                        State.gen_field_meta[i]["type"] == "bytes",
                        rx.text_area(
                            value=State.gen_field_values[i].to(str),
                            on_change=lambda val, idx=i: State.set_gen_field(idx, val),
                            placeholder=State.gen_field_meta[i]["default"],
                            font_family="monospace",
                            size="1",
                            width="100%",
                            min_height="60px",
                            height="auto",
                        ),
                        rx.input(
                            value=State.gen_field_values[i].to(str),
                            on_change=lambda val, idx=i: State.set_gen_field(idx, val),
                            placeholder=State.gen_field_meta[i]["default"],
                            font_family="monospace",
                            size="1",
                            width="100%",
                        ),
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
                                rx.foreach(
                                    State.gen_field_subs_enum[i][j],
                                    lambda o: rx.el.option(
                                        o["label"], value=o["value"]
                                    ),
                                ),
                                default_value=s["default"],
                                on_change=lambda val,
                                fi=i,
                                si=j: State.set_gen_sub_field(fi, si, val),
                                class_name="w-full rounded border border-gray-300 px-3 py-1.5",
                                size="1",
                            ),
                            rx.input(
                                value=State.gen_sub_fields[i][j].to(str),
                                on_change=lambda val,
                                fi=i,
                                si=j: State.set_gen_sub_field(fi, si, val),
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
                                    rx.foreach(
                                        State.gen_field_items_enum[i][j],
                                        lambda o: rx.el.option(
                                            o["label"], value=o["value"]
                                        ),
                                    ),
                                    default_value=it["default"],
                                    on_change=lambda val,
                                    fi=i,
                                    ri=r,
                                    ji=j: State.set_gen_list_item(fi, ri, ji, val),
                                    class_name="w-full rounded border border-gray-300 px-3 py-1.5",
                                    size="1",
                                ),
                                rx.input(
                                    value=State.gen_list_rows[i][r][j].to(str),
                                    on_change=lambda val,
                                    fi=i,
                                    ri=r,
                                    ji=j: State.set_gen_list_item(fi, ri, ji, val),
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
                        rx.icon("table_2", size=18, color="var(--warn)"),
                        rx.heading("自定义字段模板", size="3", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.foreach(
                        State.gen_custom_templates,
                        lambda tpl, i: rx.hstack(
                            rx.input(
                                value=tpl["name"].to(str),
                                on_change=lambda val,
                                idx=i: State.set_gen_custom_template(idx, "name", val),
                                placeholder="名称",
                                size="1",
                                width="15%",
                            ),
                            rx.input(
                                value=tpl["length"].to_string(),
                                on_change=lambda val,
                                idx=i: State.set_gen_custom_template(
                                    idx, "length", val
                                ),
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
                                on_change=lambda val,
                                idx=i: State.set_gen_custom_template(idx, "ftype", val),
                                class_name="app-select",
                                size="1",
                                width="12%",
                            ),
                            rx.el.select(
                                rx.el.option("little", value="little"),
                                rx.el.option("big", value="big"),
                                default_value=tpl["endian"],
                                on_change=lambda val,
                                idx=i: State.set_gen_custom_template(
                                    idx, "endian", val
                                ),
                                class_name="app-select",
                                size="1",
                                width="10%",
                            ),
                            rx.el.select(
                                rx.el.option("hex", value="hex"),
                                rx.el.option("dec", value="dec"),
                                default_value=tpl["display"],
                                on_change=lambda val,
                                idx=i: State.set_gen_custom_template(
                                    idx, "display", val
                                ),
                                class_name="app-select",
                                size="1",
                                width="10%",
                            ),
                            rx.input(
                                value=tpl["value"].to(str),
                                on_change=lambda val,
                                idx=i: State.set_gen_custom_template(idx, "value", val),
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
                    on_change=lambda val, idx=i: State.set_gen_axdr_item(
                        idx.to_string(), "type", val
                    ),
                    class_name="app-select",
                    size="1",
                    width="180px",
                ),
                rx.input(
                    value=item["value"].to(str),
                    on_change=lambda val, idx=i: State.set_gen_axdr_item(
                        idx.to_string(), "value", val
                    ),
                    placeholder="值",
                    font_family="monospace",
                    size="1",
                    width="120px",
                ),
                rx.cond(
                    _is_var_len(item["type"]),
                    rx.input(
                        value=item["length"].to_string(),
                        on_change=lambda val, idx=i: State.set_gen_axdr_item(
                            idx.to_string(), "length", val
                        ),
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
                        rx.icon("braces", size=18, color="var(--accent)"),
                        rx.heading(
                            "A-XDR 数据编辑器", size="3", font_weight="semibold"
                        ),
                        spacing="2",
                    ),
                    rx.grid(
                        rx.vstack(
                            rx.text("服务优先级:", size="1", font_weight="medium"),
                            rx.el.select(
                                rx.el.option("0-普通", value="0"),
                                rx.el.option("1-高优先级", value="1"),
                                default_value="0",
                                on_change=lambda v: State.set_gen_axdr_fixed(
                                    "PIID_优先级", v
                                ),
                                class_name="app-select",
                                size="1",
                            ),
                            spacing="1",
                        ),
                        rx.vstack(
                            rx.text("服务序号:", size="1", font_weight="medium"),
                            rx.input(
                                value=State.gen_axdr_fixed["PIID_序号"].to(str),
                                on_change=lambda v: State.set_gen_axdr_fixed(
                                    "PIID_序号", v
                                ),
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
                                    on_change=lambda v: State.set_gen_axdr_fixed(
                                        "方法标识", v
                                    ),
                                    size="1",
                                    type="number",
                                ),
                                spacing="1",
                            ),
                            rx.vstack(
                                rx.text("属性标识:", size="1", font_weight="medium"),
                                rx.input(
                                    value=State.gen_axdr_fixed["属性标识"].to(str),
                                    on_change=lambda v: State.set_gen_axdr_fixed(
                                        "属性标识", v
                                    ),
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
                                    on_change=lambda v: State.set_gen_axdr_fixed(
                                        "操作模式", v
                                    ),
                                    size="1",
                                    type="number",
                                ),
                                spacing="1",
                            ),
                            rx.vstack(
                                rx.text("索引:", size="1", font_weight="medium"),
                                rx.input(
                                    value=State.gen_axdr_fixed["索引"].to(str),
                                    on_change=lambda v: State.set_gen_axdr_fixed(
                                        "索引", v
                                    ),
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
                        rx.icon("server", size=18, color="var(--accent)"),
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
                                on_change=lambda v: State.set_gen_dlt698_sa(
                                    "addr_type", v
                                ),
                                class_name="app-select",
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
                                on_change=lambda v: State.set_gen_dlt698_sa(
                                    "logic_addr", v
                                ),
                                class_name="app-select",
                                size="1",
                            ),
                            spacing="1",
                        ),
                        rx.vstack(
                            rx.text("地址长度(字节):", size="1", font_weight="medium"),
                            rx.input(
                                type="number",
                                value=State.gen_dlt698_addr_len.to_string(),
                                on_change=lambda v: State.set_gen_dlt698_sa(
                                    "addr_len", v
                                ),
                                size="1",
                                placeholder="0=自动6字节",
                            ),
                            spacing="1",
                        ),
                        rx.vstack(
                            rx.text("SA (HEX):", size="1", font_weight="medium"),
                            rx.input(
                                value=State.gen_dlt698_sa_raw,
                                on_change=lambda v: State.set_gen_dlt698_sa(
                                    "sa_raw", v
                                ),
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
                                class_name="app-select",
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
                                class_name="app-select",
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
                                class_name="app-select",
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

    # ── DLT645-2007（协议6）帧配置 ──
    def dlt645_panel() -> rx.Component:
        return rx.cond(
            State.current_protocol == 6,
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("gauge", size=18, color="var(--accent)"),
                        rx.text("DLT645-2007 帧配置", font_weight="bold"),
                        spacing="2",
                    ),
                    rx.hstack(
                        rx.text("命令:", size="2"),
                        rx.select(
                            State.dlt645_cmd_options,
                            value=State.gen_dlt645_cmd_label,
                            on_change=State.select_dlt645_cmd,
                            size="2",
                        ),
                        spacing="2",
                    ),
                    rx.hstack(
                        rx.text("表地址:", size="2"),
                        rx.input(
                            value=State.gen_dlt645_addr,
                            on_change=State.set_dlt645_addr,
                            placeholder="12 位地址；校时 99…9 / 地址命令 AA…AA",
                            width="180px",
                            size="2",
                        ),
                        rx.text("数据标识:", size="2"),
                        rx.input(
                            value=State.gen_dlt645_di,
                            on_change=State.set_dlt645_di,
                            placeholder="8 位 DI，如 00010000",
                            width="160px",
                            size="2",
                        ),
                        rx.text(
                            State.gen_dlt645_di_label, size="1", color="var(--muted)"
                        ),
                        spacing="2",
                    ),
                    rx.foreach(
                        State.gen_dlt645_fields,
                        lambda f, i: rx.hstack(
                            rx.text(f["name"], size="2", width="130px"),
                            rx.input(
                                value=f["value"],
                                on_change=lambda v: State.set_dlt645_field(i, v),
                                placeholder=f["hint"],
                                size="2",
                            ),
                            spacing="2",
                        ),
                    ),
                    rx.text(
                        State.gen_dlt645_ctrl_label, size="1", color="var(--muted)"
                    ),
                    spacing="3",
                ),
            ),
        )

    # ── 国网中继地址 ──
    def gdw_relay_panel() -> rx.Component:
        return rx.cond(
            State.current_protocol == 7,
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("git_branch", size=18, color="var(--accent)"),
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
                        rx.icon("scan_eye", size=18, color="var(--ok)"),
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
                                    rx.table.cell(
                                        rx.text(row["comment"], size="1", color="gray")
                                    ),
                                ),
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
                        rx.icon("info", size=18, color="var(--accent)"),
                        rx.heading("信息域配置", size="3", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.grid(
                        *[
                            rx.vstack(
                                rx.text(name, size="1", font_weight="medium"),
                                rx.input(
                                    value=State.gen_gdw_info[name].to(str),
                                    on_change=lambda val,
                                    n=name: State.set_gen_gdw_info(n, val),
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
                    rx.icon("settings", size=20, color="var(--accent)"),
                    rx.heading("选择命令", size="3", font_weight="semibold"),
                    rx.spacer(),
                    rx.cond(
                        (State.current_protocol == 0)
                        | (State.current_protocol == 7)
                        | (State.current_protocol == 8),
                        rx.badge("支持组帧", color_scheme="green", variant="soft"),
                        rx.badge(
                            "当前协议暂不支持组帧", color_scheme="gray", variant="soft"
                        ),
                    ),
                    spacing="2",
                ),
                # 协议13（依瓦定制645）：Web 端组帧本期未实现（prd R7.4 范围声明），
                # 在组帧页给可见提示，不得静默缺失。
                rx.cond(
                    State.current_protocol == 13,
                    rx.callout(
                        "协议13（依瓦定制645）的组帧暂未在 Web 端提供，请使用桌面版「协议组帧」页；"
                        "另注：协议文档未定义写模式命令码，桌面版亦仅提供占位项。",
                        icon="info",
                        color_scheme="amber",
                        size="1",
                        width="100%",
                    ),
                ),
                # 南网 DI 选择 (协议 0)
                rx.cond(
                    State.current_protocol == 0,
                    _searchable_select(
                        "DI:",
                        State.gen_di_search,
                        State.set_gen_di_search,
                        State.di_options,
                        State.di_filtered,
                        State.select_di,
                        State.gen_di_key,
                        State.gen_di_selected_label,
                        "输入 DI 码/名称过滤，如 E8",
                        State.gen_di_open,
                        State.open_di,
                        State.close_di,
                    ),
                ),
                # 国网 AFN+Fn 选择 (协议 7)
                rx.cond(
                    State.current_protocol == 7,
                    _searchable_select(
                        "AFN+Fn:",
                        State.gen_afn_search,
                        State.set_gen_afn_search,
                        State.afn_fn_options,
                        State.afn_filtered,
                        State.select_afn,
                        State.gen_afn_fn,
                        State.gen_afn_selected_label,
                        "输入 AFN/Fn 码或名称过滤，如 0101",
                        State.gen_afn_open,
                        State.open_afn,
                        State.close_afn,
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
                            State.dlt698_all_options,
                            State.dlt698_filtered,
                            State.select_dlt698,
                            State.gen_dlt698_apdu,
                            State.gen_dlt698_selected_label,
                            "输入 APDU 类型过滤，如 GET",
                            State.gen_dlt698_open,
                            State.open_dlt698,
                            State.close_dlt698,
                        ),
                        rx.cond(
                            State.gen_dlt698_apdu != "",
                            rx.hstack(
                                rx.text(
                                    "子类型:",
                                    size="2",
                                    font_weight="medium",
                                    width="60px",
                                ),
                                rx.el.select(
                                    rx.el.option("请选择子类型", value=""),
                                    rx.foreach(
                                        State.dlt698_sub_options,
                                        lambda opt: rx.el.option(
                                            opt["label"], value=opt["value"]
                                        ),
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
                    rx.icon("grid_3x_3", size=20, color="var(--accent)"),
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
                            class_name="app-select",
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
                            class_name="app-select",
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
        # DLT645-2007 帧配置（协议6，内部自带 rx.cond）
        dlt645_panel(),
        # EB 数据标识 645 帧生成器（协议7 透明转发/事件上报报文内容辅助）
        rx.cond(
            State.current_protocol == 7,
            eb_645_generator(),
        ),
        # 预览和结果
        rx.hstack(
            # 预览
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("eye", size=20, color="var(--accent)"),
                        rx.heading("生成预览", size="3", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.scroll_area(
                        rx.text(
                            State.gen_preview,
                            font_family="monospace",
                            font_size="12px",
                            white_space="pre-wrap",
                        ),
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
                        rx.icon(
                            "square_arrow_out_up_right", size=20, color="var(--ok)"
                        ),
                        rx.heading("生成结果", size="3", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.cond(
                        State.gen_result != "",
                        rx.scroll_area(
                            rx.text(
                                State.gen_result,
                                font_family="monospace",
                                font_size="12px",
                                white_space="pre-wrap",
                            ),
                            height="200px",
                            padding="2",
                            background="rgba(5, 150, 105, 0.05)",
                            border_radius="8px",
                            width="100%",
                        ),
                        rx.center(
                            rx.vstack(
                                rx.icon("building", size=48, color="var(--muted-2)"),
                                rx.text(
                                    "点击「生成帧」查看结果",
                                    color="var(--muted)",
                                    size="2",
                                ),
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
                rx.cond(
                    State.is_loading, rx.spinner(size="1"), rx.icon("play", size=16)
                ),
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
                        rx.icon("file", size=18, color="var(--accent)"),
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
                        rx.icon("file", size=18, color="var(--warn)"),
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
                rx.cond(
                    State.is_loading,
                    rx.spinner(size="1"),
                    rx.icon("git_compare", size=16),
                ),
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
                        rx.icon("lightbulb", size=18, color="var(--warn)"),
                        rx.heading("差异说明", size="3", font_weight="semibold"),
                        spacing="2",
                    ),
                    rx.vstack(
                        rx.foreach(
                            State.diff_explanations,
                            lambda exp: rx.hstack(
                                rx.icon(
                                    "info",
                                    size=14,
                                    color="var(--warn)",
                                    flex_shrink="0",
                                ),
                                rx.text(exp, size="2"),
                                spacing="2",
                                padding_x="2",
                                padding_y="1",
                                width="100%",
                                background="rgba(245, 158, 11, 0.05)",
                                border_left="3px solid var(--warn)",
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
                    rx.icon("table", size=18, color="var(--accent)"),
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
                                    rx.table.column_header_cell(
                                        "偏移(A/B)", width="12%"
                                    ),
                                    rx.table.column_header_cell(
                                        "长度(A/B)", width="12%"
                                    ),
                                    rx.table.column_header_cell("报文A值", width="22%"),
                                    rx.table.column_header_cell("报文B值", width="22%"),
                                    rx.table.column_header_cell(
                                        "差异类型", width="10%"
                                    ),
                                )
                            ),
                            rx.table.body(
                                rx.foreach(
                                    State.diff_field_rows,
                                    lambda row: rx.table.row(
                                        rx.table.cell(
                                            row["field_name"], font_weight="medium"
                                        ),
                                        rx.table.cell(
                                            rx.code(
                                                row["offset_display"], variant="soft"
                                            )
                                        ),
                                        rx.table.cell(
                                            rx.code(
                                                row["length_display"], variant="soft"
                                            )
                                        ),
                                        rx.table.cell(
                                            rx.code(row["value_a"], variant="soft"),
                                            font_size="11px",
                                        ),
                                        rx.table.cell(
                                            rx.code(row["value_b"], variant="soft"),
                                            font_size="11px",
                                        ),
                                        rx.table.cell(
                                            rx.badge(
                                                row["diff_type"],
                                                color_scheme=rx.cond(
                                                    row["diff_type"] == "相同",
                                                    "green",
                                                    rx.cond(
                                                        row["diff_type"] == "修改",
                                                        "red",
                                                        rx.cond(
                                                            row["diff_type"] == "A独有",
                                                            "gray",
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
                            rx.icon("git_compare", size=40, color="var(--muted-2)"),
                            rx.text(
                                "点击「开始对比」查看字段级差异",
                                color="var(--muted)",
                                size="2",
                            ),
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
                    rx.icon("binary", size=18, color="var(--accent)"),
                    rx.heading(
                        "字节级对比 (按字段分组)", size="3", font_weight="semibold"
                    ),
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
                                    rx.table.column_header_cell(
                                        "报文 A (HEX)", width="38%"
                                    ),
                                    rx.table.column_header_cell(
                                        "报文 B (HEX)", width="38%"
                                    ),
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
                                                rx.text(
                                                    row["field_name"],
                                                    font_weight="bold",
                                                    size="1",
                                                ),
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
                                            rx.table.cell(
                                                rx.code(row["offset"], variant="soft"),
                                                font_size="11px",
                                            ),
                                            rx.table.cell(
                                                rx.code(row["left"], variant="soft"),
                                                font_family="monospace",
                                                font_size="11px",
                                            ),
                                            rx.table.cell(
                                                rx.code(row["right"], variant="soft"),
                                                font_family="monospace",
                                                font_size="11px",
                                            ),
                                            rx.table.cell(
                                                rx.badge(
                                                    rx.cond(
                                                        row["status"] == "same",
                                                        "=",
                                                        rx.cond(
                                                            row["status"] == "modified",
                                                            "≠",
                                                            rx.cond(
                                                                row["status"]
                                                                == "added",
                                                                "+",
                                                                "-",
                                                            ),
                                                        ),
                                                    ),
                                                    color_scheme=rx.cond(
                                                        row["status"] == "same",
                                                        "green",
                                                        rx.cond(
                                                            row["status"] == "modified",
                                                            "red",
                                                            rx.cond(
                                                                row["status"]
                                                                == "added",
                                                                "amber",
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
                                                {
                                                    "background": "rgba(220, 38, 38, 0.03)"
                                                },
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
                            rx.icon("binary", size=40, color="var(--muted-2)"),
                            rx.text(
                                "点击「开始对比」查看字节级差异",
                                color="var(--muted)",
                                size="2",
                            ),
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
# 客户端下载 Tab
# ═══════════════════════════════════════════════════════════════


def download_tab() -> rx.Component:
    """客户端下载（GUI 版 exe 下载）"""
    return rx.vstack(
        # 标题
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("download", size=22, color="var(--accent)"),
                    rx.heading("客户端下载", size="4", font_weight="bold"),
                    spacing="2",
                ),
                rx.text(
                    "下载 Windows 桌面版（PySide6 GUI），功能与 Web 版一致，支持全部 12 种协议解析、组帧、串口通信与实时监控。",
                    size="2",
                    color="gray",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
        # 下载按钮（最显眼，放前面）
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.cond(
                        State.download_exe_available,
                        rx.button(
                            rx.hstack(
                                rx.icon("download", size=18),
                                rx.text("下载客户端 (exe)"),
                                spacing="2",
                            ),
                            on_click=State.download_client,
                            color_scheme="blue",
                            size="3",
                            cursor="pointer",
                        ),
                        rx.button(
                            rx.hstack(
                                rx.icon("download", size=18),
                                rx.text("客户端 exe 未就绪"),
                                spacing="2",
                            ),
                            disabled=True,
                            color_scheme="gray",
                            size="3",
                        ),
                    ),
                    spacing="3",
                    align_items="center",
                ),
                rx.cond(
                    State.download_exe_name != "",
                    rx.text(f"文件: {State.download_exe_name}", size="1", color="gray"),
                ),
                rx.cond(
                    State.download_msg != "",
                    rx.text(State.download_msg, size="1", color="gray"),
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
        # 当前版本信息
        rx.cond(
            State.download_version != "",
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("info", size=20, color="var(--accent)"),
                        rx.heading("当前版本", size="3", font_weight="bold"),
                        rx.spacer(),
                        rx.badge(
                            State.download_version,
                            color_scheme="blue",
                            variant="soft",
                            size="2",
                        ),
                        spacing="2",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.text("发布日期:", size="2", color="gray", width="90px"),
                        rx.text(State.download_version_date, size="2"),
                        width="100%",
                    ),
                    rx.cond(
                        State.download_version_notes != "",
                        rx.vstack(
                            rx.text("更新说明:", size="2", color="gray"),
                            rx.text(
                                State.download_version_notes,
                                size="2",
                                white_space="pre-wrap",
                                line_height="1.8",
                            ),
                            spacing="1",
                            width="100%",
                        ),
                    ),
                    spacing="3",
                    width="100%",
                ),
                width="100%",
            ),
        ),
        # 历史版本
        rx.cond(
            State.download_history.length() > 0,
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("history", size=20, color="var(--muted)"),
                        rx.heading("版本历史", size="3", font_weight="bold"),
                        rx.spacer(),
                        rx.badge(
                            f"{State.download_history.length()} 个历史版本",
                            color_scheme="gray",
                            variant="soft",
                            size="1",
                        ),
                        spacing="2",
                        width="100%",
                    ),
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("版本号", width="25%"),
                                rx.table.column_header_cell("发布日期", width="25%"),
                                rx.table.column_header_cell("大小", width="20%"),
                                rx.table.column_header_cell("说明", width="30%"),
                            ),
                        ),
                        rx.table.body(
                            rx.foreach(
                                State.download_history,
                                lambda item: rx.table.row(
                                    rx.table.cell(
                                        item["version"], font_weight="medium"
                                    ),
                                    rx.table.cell(item["date"], size="1"),
                                    rx.table.cell(item["size_mb"] + " MB", size="1"),
                                    rx.table.cell(
                                        rx.text("历史版本归档", size="1", color="gray"),
                                    ),
                                ),
                            ),
                        ),
                        width="100%",
                        size="2",
                    ),
                    spacing="3",
                    width="100%",
                ),
                width="100%",
            ),
        ),
        # 软件界面截图
        rx.card(
            rx.vstack(
                rx.text("软件界面", size="2", font_weight="semibold"),
                rx.cond(
                    State.download_image_available,
                    rx.image(
                        src=State.download_image_data_url,
                        alt="客户端软件界面",
                        border_radius="8px",
                        border="1px solid var(--border)",
                        width="100%",
                        max_width="960px",
                        object_fit="contain",
                    ),
                    rx.box(
                        rx.center(
                            rx.vstack(
                                rx.icon("image_off", size=40, color="var(--muted-2)"),
                                rx.text(
                                    "暂无界面截图", size="2", color="var(--muted-2)"
                                ),
                                spacing="2",
                            ),
                            min_height="200px",
                        ),
                        border="1px dashed var(--border-strong)",
                        border_radius="8px",
                    ),
                ),
                spacing="2",
                width="100%",
            ),
            width="100%",
        ),
        # 客户端说明（README）
        rx.cond(
            State.download_readme_available,
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("file_text", size=18, color="var(--accent)"),
                        rx.heading(
                            "客户端说明 (README)", size="3", font_weight="semibold"
                        ),
                        spacing="2",
                    ),
                    rx.scroll_area(
                        rx.markdown(
                            State.download_readme_text,
                            font_size="13px",
                            line_height="1.7",
                            max_height="480px",
                            width="100%",
                        ),
                        width="100%",
                    ),
                    spacing="3",
                    width="100%",
                ),
                width="100%",
            ),
        ),
        spacing="3",
        width="100%",
    )


# ═══════════════════════════════════════════════════════════════
# 问题反馈（用户提交 + 管理页）
# ═══════════════════════════════════════════════════════════════

FEEDBACK_PROTOCOL_OPTIONS = [
    "不确定",
    "南网协议",
    "PLC RF协议",
    "HDLC/国网DLMS",
    "DLMS-APDU(国网)",
    "DLMS Wrapper裸报文",
    "DLMS-APDU裸报文",
    "DLT645-2007 电表协议",
    "国网协议",
    "698.45协议",
    "新一代载波协议",
    "国网新一代双模",
    "HDC 1.0 双模",
]
FEEDBACK_PAGE_SIZE = 20


class FeedbackState(State):
    """问题反馈：用户提交表单 + 列表查看（Tab 页）+ 管理操作（仅登录后）

    权限分层：列表/详情所有人可见；修改状态/删除仅管理员。
    继承主 State（Reflex 子 State）：直接通过 self 访问父类的
    admin_logged_in 登录态（跨 State 实例属性不可互访，唯有继承可行）。
    """

    # ── 提交表单 ──
    fb_type: str = "功能异常"
    fb_protocol: str = "不确定"
    fb_desc: str = ""
    fb_contact: str = ""
    fb_files: list[str] = []  # 已选截图文件名（展示用）
    # 后端专用：暂存上传的截图字节（下划线前缀 → 不发送到前端），提交时统一落盘
    _fb_pending_data: list[bytes] = []
    fb_msg: str = ""
    fb_msg_type: str = "info"  # info/success/error

    # ── 反馈列表（Tab 页，所有人可见）──
    fa_items: list[dict[str, Any]] = []
    fa_total: int = 0
    fa_page: int = 0  # 0-based 页号
    fa_msg: str = ""
    fa_detail_open: bool = False
    fa_detail: dict[str, Any] = {}
    # 详情内状态操作提示（区分于 fa_msg 列表加载提示）
    fa_detail_msg: str = ""

    # ── 提交表单事件 ──

    def set_fb_type(self, value: str):
        self.fb_type = value

    def set_fb_protocol(self, value: str):
        self.fb_protocol = value

    def set_fb_desc(self, value: str):
        self.fb_desc = value

    def set_fb_contact(self, value: str):
        self.fb_contact = value

    async def handle_fb_files(self, files: list[rx.UploadFile]):
        """截图选择暂存：字节存后端 _fb_pending_data，提交时才落盘"""
        if not files:
            return
        if len(files) > 3:
            self.fb_msg = "最多上传 3 张截图"
            self.fb_msg_type = "error"
            return
        names = []
        datas = []
        total = 0
        for f in files:
            data = await f.read()
            total += len(data)
            if len(data) > 5 * 1024 * 1024:
                self.fb_msg = f"截图 {getattr(f, 'filename', '') or '文件'} 超过 5MB"
                self.fb_msg_type = "error"
                self.fb_files = []
                self._fb_pending_data = []
                return
            names.append(
                getattr(f, "filename", None) or getattr(f, "name", None) or "截图"
            )
            datas.append(data)
        self.fb_files = names
        self._fb_pending_data = datas
        self.fb_msg = (
            f"已选择 {len(names)} 张截图（共 {total // 1024} KB），点击提交后上传"
        )
        self.fb_msg_type = "info"

    def clear_fb_files(self):
        self.fb_files = []
        self._fb_pending_data = []
        if self.fb_msg_type != "error":
            self.fb_msg = ""

    async def submit_feedback(self):
        """提交反馈：服务端校验 → 截图落盘 → 写库 → 清空表单"""
        from . import feedback_model as fm

        desc = (self.fb_desc or "").strip()
        contact = (self.fb_contact or "").strip()
        if not desc:
            self.fb_msg = "请填写问题描述"
            self.fb_msg_type = "error"
            return
        if len(desc) > fm.MAX_DESC_LEN:
            self.fb_msg = (
                f"问题描述不能超过 {fm.MAX_DESC_LEN} 字（当前 {len(desc)} 字）"
            )
            self.fb_msg_type = "error"
            return
        if len(contact) > fm.MAX_CONTACT_LEN:
            self.fb_msg = f"联系方式不能超过 {fm.MAX_CONTACT_LEN} 字"
            self.fb_msg_type = "error"
            return
        if self.fb_type not in fm.ISSUE_TYPES:
            self.fb_msg = "请选择有效的问题类型"
            self.fb_msg_type = "error"
            return

        saved_names = []
        try:
            for i, data in enumerate(self._fb_pending_data):
                orig = self.fb_files[i] if i < len(self.fb_files) else ""
                saved_names.append(fm.save_screenshot(data, orig))
        except ValueError as e:
            fm.delete_screenshots(saved_names)
            self.fb_msg = f"截图保存失败: {e}"
            self.fb_msg_type = "error"
            return
        except Exception as e:
            fm.delete_screenshots(saved_names)
            self.fb_msg = f"截图上传异常: {e}"
            self.fb_msg_type = "error"
            return

        try:
            item = fm.FeedbackItem(
                created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                issue_type=self.fb_type,
                protocol=self.fb_protocol,
                description=desc,
                contact=contact,
                screenshots=";".join(saved_names),
                status="待处理",
                source="web",
            )
            fm.FeedbackStore.instance().add(item)
        except Exception as e:
            fm.delete_screenshots(saved_names)
            self.fb_msg = f"保存失败: {e}"
            self.fb_msg_type = "error"
            return

        # 成功：清空表单
        saved = len(saved_names)
        self.fb_desc = ""
        self.fb_contact = ""
        self.fb_files = []
        self._fb_pending_data = []
        self.fb_msg = "反馈提交成功，感谢您的支持！" + (
            f"（含 {saved} 张截图）" if saved else ""
        )
        self.fb_msg_type = "success"

    # ── 列表 / 管理事件 ──

    def fa_load(self):
        """加载当前页反馈列表（切到列表 Tab 时自动调用）"""
        from . import feedback_model as fm

        try:
            items, total = fm.FeedbackStore.instance().list_all(
                offset=self.fa_page * FEEDBACK_PAGE_SIZE, limit=FEEDBACK_PAGE_SIZE
            )
            self.fa_items = [
                {
                    "id": int(it.id),
                    "created_at": it.created_at,
                    "issue_type": it.issue_type,
                    "protocol": it.protocol,
                    "description": it.description,
                    "contact": it.contact,
                    "screenshots": it.screenshots,
                    "status": it.status,
                    "source": getattr(it, "source", "web") or "web",
                    "sys_info": getattr(it, "sys_info", "") or "",
                }
                for it in items
            ]
            self.fa_total = total
        except Exception as e:
            self.fa_msg = f"加载失败: {e}"

    def fa_first_page(self):
        self.fa_page = 0
        self.fa_load()

    def fa_prev_page(self):
        if self.fa_page > 0:
            self.fa_page -= 1
        self.fa_load()

    def fa_next_page(self):
        if (self.fa_page + 1) * FEEDBACK_PAGE_SIZE < self.fa_total:
            self.fa_page += 1
        self.fa_load()

    def fa_open_detail(self, item: dict[str, Any]):
        self.fa_detail = item
        self.fa_detail_msg = ""
        self.fa_detail_open = True

    def fa_close_detail(self):
        self.fa_detail_open = False

    def fa_on_open_change(self, is_open: bool):
        """弹窗 open 状态变化（点遮罩/Esc 时 Radix 发出 False，同步回 State）"""
        if not is_open:
            self.fa_detail_open = False

    def fa_set_status(self, status: str):
        """修改详情对应反馈的状态（仅管理员：UI 上按钮仅登录后渲染，此处双保险校验）"""
        from . import feedback_model as fm

        if not self.admin_logged_in:
            self.fa_detail_msg = "需要管理员登录后才能修改状态"
            return
        item_id = self.fa_detail.get("id")
        if item_id is None:
            return
        if fm.FeedbackStore.instance().update_status(int(item_id), status):
            self.fa_detail = {**self.fa_detail, "status": status}
            self.fa_detail_msg = f"已标记为「{status}」"
            self.fa_load()
        else:
            self.fa_detail_msg = "状态修改失败"

    def fa_delete_current(self):
        """删除详情对应反馈含截图文件（仅管理员）"""
        from . import feedback_model as fm

        if not self.admin_logged_in:
            self.fa_detail_msg = "需要管理员登录后才能删除"
            return
        item_id = self.fa_detail.get("id")
        if item_id is None:
            return
        names = fm.FeedbackStore.instance().delete(int(item_id))
        removed = fm.delete_screenshots(names)
        self.fa_detail_open = False
        self.fa_detail_msg = ""
        self.fa_msg = f"已删除反馈 #{item_id}" + (
            f"（清理 {removed} 张截图）" if removed else ""
        )
        # 若当前页删空则回退一页
        if self.fa_items and len(self.fa_items) == 1 and self.fa_page > 0:
            self.fa_page -= 1
        self.fa_load()


class ShareState(State):
    """报文分享：列表/搜索（/share 页，所有人可见）+ 提交表单（主页弹窗）

    继承主 State：分享页管理员删除需要 admin_logged_in（与 FeedbackState 同款
    模式）；主页「分享此帧」弹窗内的 last_parsed_hex / last_protocol_name 来自
    主 State（继承后方可访问）。协议下拉用主 State 的 PROTOCOL_OPTIONS 只读
    渲染（Var 跨 State 读是允许的，仅写入受限），提交走本 State 事件。
    """

    # ── 列表（/share 页）──
    sh_items: list[dict[str, Any]] = []
    sh_page: int = 1
    sh_pages: int = 1
    sh_total: int = 0
    sh_keyword: str = ""
    sh_msg: str = ""
    sh_detail_open: bool = False
    sh_detail: dict[str, Any] = {}

    # ── 提交表单（主页弹窗）──
    sf_open: bool = False
    sf_hex: str = ""
    sf_protocol: str = ""
    sf_sharer: str = ""
    sf_note: str = ""
    sf_msg: str = ""
    sf_msg_type: str = "info"

    # ── 管理员删除（/share 页，仅 admin_logged_in 可见）──
    sh_delete_id: int = 0  # 待确认删除的记录 id
    sh_confirm_open: bool = False  # 删除确认弹窗开关
    sh_admin_msg: str = ""  # 删除操作提示（未登录/失败）

    # ── 列表事件 ──

    def sh_load(self):
        """加载当前页分享列表（页面上 on_load 或翻页时调用）"""

        try:
            items, total, pages = sm.ShareStore.instance().list_page(
                self.sh_page, sm.PER_PAGE, self.sh_keyword
            )
            self.sh_items = items
            self.sh_total = total
            self.sh_pages = pages
            self.sh_page = min(self.sh_page, pages)
        except Exception as e:
            self.sh_msg = f"加载失败: {e}"

    def set_sh_keyword(self, value: str):
        """搜索词变化：重置到第 1 页并重新加载（rx.input on_change 触发）"""
        self.sh_keyword = value
        self.sh_page = 1
        self.sh_load()

    def sh_next(self):
        if self.sh_page < self.sh_pages:
            self.sh_page += 1
        self.sh_load()

    def sh_prev(self):
        if self.sh_page > 1:
            self.sh_page -= 1
        self.sh_load()

    def sh_open_detail(self, item: dict[str, Any]):
        self.sh_detail = item
        self.sh_detail_open = True

    def sh_close_detail(self):
        self.sh_detail_open = False

    def sh_on_open_change(self, is_open: bool):
        if not is_open:
            self.sh_detail_open = False

    def copy_detail_hex(self):
        return rx.set_clipboard(self.sh_detail.get("frame_hex", ""))

    # ── 管理员删除事件 ──

    def sh_ask_delete(self, item_id: int):
        """点列表「删除」：记录待删 id 并打开确认弹窗（不立即删除）"""
        self.sh_delete_id = int(item_id)
        self.sh_confirm_open = True

    def sh_cancel_delete(self):
        """取消删除：关闭确认弹窗"""
        self.sh_confirm_open = False
        self.sh_delete_id = 0

    def sh_confirm_delete(self):
        """确认删除：校验管理员态 → 删除 → 刷新列表"""
        if not self.admin_logged_in:
            self.sh_admin_msg = "请先登录管理员"
            self.sh_confirm_open = False
            return
        ok = sm.ShareStore.instance().delete(self.sh_delete_id)
        self.sh_confirm_open = False
        self.sh_delete_id = 0
        if ok:
            self.sh_msg = "已删除该记录"
            self.sh_load()  # 删空当前页时 list_page 自动回退页码
        else:
            self.sh_msg = "删除失败：记录不存在或已被删除"

    # ── 提交表单事件（主页弹窗）──

    def sf_open_dialog(self):
        """打开分享表单（主页「分享此帧」按钮：从主 State 读最近解析缓存）"""
        if not self.last_parsed_hex.strip():
            self.sf_msg = "请先解析一个报文再分享"
            self.sf_msg_type = "error"
            self.sf_open = True
            return
        self.sf_hex = self.last_parsed_hex
        self.sf_protocol = self.last_protocol_name
        self.sf_sharer = ""
        self.sf_note = ""
        self.sf_msg = ""
        self.sf_open = True

    def set_sf_sharer(self, value: str):
        self.sf_sharer = value

    def set_sf_note(self, value: str):
        self.sf_note = value

    def set_sf_protocol(self, value: str):
        self.sf_protocol = value

    def sf_close(self):
        self.sf_open = False

    def sf_on_open_change(self, is_open: bool):
        if not is_open:
            self.sf_open = False

    async def sf_submit(self):
        """提交分享（source=web）：服务端校验 + 落库"""

        if not (self.sf_sharer or "").strip():
            self.sf_msg = "请填写分享人"
            self.sf_msg_type = "error"
            return
        ok, result, status = sm.submit_share(
            {
                "frame_hex": self.sf_hex,
                "protocol": self.sf_protocol,
                "sharer": self.sf_sharer,
                "note": self.sf_note,
                "source": "web",
            }
        )
        if ok:
            self.sf_open = False
            self.sf_msg = f"分享成功（#{int(result)}），可在「报文分享」页查看"
            self.sf_msg_type = "success"
        else:
            self.sf_msg = str(result)
            self.sf_msg_type = "error"


class FeedbackUploads(rx.State):
    """保留空占位（历史遗留命名空间，无状态）"""


# ── 反馈页面组件 ──


def _fb_msg_banner() -> rx.Component:
    """反馈表单消息提示条"""
    return rx.cond(
        FeedbackState.fb_msg != "",
        rx.hstack(
            rx.icon(
                rx.cond(
                    FeedbackState.fb_msg_type == "error", "circle_alert", "circle_check"
                ),
                size=16,
                color=rx.cond(
                    FeedbackState.fb_msg_type == "error", "var(--danger)", "var(--ok)"
                ),
            ),
            rx.text(
                FeedbackState.fb_msg,
                size="2",
                color=rx.cond(
                    FeedbackState.fb_msg_type == "error", "var(--danger)", "var(--ok)"
                ),
            ),
            spacing="2",
            padding="8px 12px",
            border_radius="8px",
            background=rx.cond(
                FeedbackState.fb_msg_type == "error",
                "var(--danger)",
                "var(--ok-soft)",
            ),
            width="100%",
        ),
    )


def feedback_page() -> rx.Component:
    """问题反馈提交页（用户侧，无需登录）"""
    return rx.box(
        theme_style(),
        rx.el.style(GLOBAL_CSS),
        header(show_parse_controls=False),
        rx.box(
            rx.vstack(
                # 页面标题
                rx.hstack(
                    rx.icon("message_square_heart", size=24, color="var(--accent)"),
                    rx.heading("问题反馈", size="5", font_weight="bold"),
                    spacing="2",
                    margin_bottom="4px",
                ),
                rx.text(
                    "使用中遇到问题或有改进建议，请在此反馈。我们会尽快处理。",
                    size="2",
                    color="var(--muted)",
                    margin_bottom="12px",
                ),
                # 表单卡片
                rx.card(
                    rx.vstack(
                        rx.hstack(
                            rx.vstack(
                                rx.text("问题类型", size="2", font_weight="medium"),
                                rx.select(
                                    [
                                        "功能异常",
                                        "解析错误",
                                        "界面体验",
                                        "新功能建议",
                                        "其他",
                                    ],
                                    value=FeedbackState.fb_type,
                                    on_change=FeedbackState.set_fb_type,
                                    width="200px",
                                    data_testid="fb-type",
                                ),
                                spacing="1",
                                align="start",
                            ),
                            rx.vstack(
                                rx.text("涉及协议", size="2", font_weight="medium"),
                                rx.select(
                                    FEEDBACK_PROTOCOL_OPTIONS,
                                    value=FeedbackState.fb_protocol,
                                    on_change=FeedbackState.set_fb_protocol,
                                    width="260px",
                                    data_testid="fb-protocol",
                                ),
                                spacing="1",
                                align="start",
                            ),
                            spacing="6",
                            wrap="wrap",
                            width="100%",
                        ),
                        rx.vstack(
                            rx.hstack(
                                rx.text("问题描述", size="2", font_weight="medium"),
                                rx.badge(
                                    "必填", color_scheme="red", variant="soft", size="1"
                                ),
                                rx.spacer(),
                                rx.text(
                                    f"{FeedbackState.fb_desc.length()} / 2000",
                                    size="1",
                                    color="var(--muted-2)",
                                ),
                                spacing="2",
                                width="100%",
                            ),
                            rx.text_area(
                                placeholder="请描述遇到的问题：什么操作、预期结果、实际结果（可附报文样例）",
                                value=FeedbackState.fb_desc,
                                on_change=FeedbackState.set_fb_desc,
                                min_height="120px",
                                width="100%",
                                data_testid="fb-desc",
                            ),
                            spacing="1",
                            align="start",
                            width="100%",
                        ),
                        rx.vstack(
                            rx.text("联系方式（选填）", size="2", font_weight="medium"),
                            rx.input(
                                placeholder="如 QQ / 微信 / 邮箱，方便我们回访",
                                value=FeedbackState.fb_contact,
                                on_change=FeedbackState.set_fb_contact,
                                width="320px",
                                max_length=100,
                                data_testid="fb-contact",
                            ),
                            spacing="1",
                            align="start",
                        ),
                        # 截图上传
                        rx.vstack(
                            rx.text(
                                "截图（选填，最多 3 张，jpg/png/webp，单张 ≤5MB）",
                                size="2",
                                font_weight="medium",
                            ),
                            rx.upload(
                                rx.hstack(
                                    rx.icon("image_up", size=20, color="var(--accent)"),
                                    rx.text("拖拽截图到此处，或点击选择", size="2"),
                                    spacing="2",
                                    align="center",
                                ),
                                on_drop=FeedbackState.handle_fb_files,
                                multiple=True,
                                max_files=3,
                                accept={
                                    "image/png": [".png"],
                                    "image/jpeg": [".jpg", ".jpeg"],
                                    "image/webp": [".webp"],
                                },
                                max_size=5 * 1024 * 1024,
                                class_name="rounded-lg border-2 border-dashed border-blue-300 bg-blue-50/50 p-4 w-full hover:border-blue-500 transition-colors",
                                data_testid="fb-upload",
                            ),
                            rx.cond(
                                FeedbackState.fb_files.length() > 0,
                                rx.hstack(
                                    rx.icon("paperclip", size=14, color="var(--muted)"),
                                    rx.text(
                                        "已选 "
                                        + FeedbackState.fb_files.length().to_string()
                                        + " 张截图",
                                        size="1",
                                        color="var(--muted)",
                                    ),
                                    rx.button(
                                        "清除",
                                        size="1",
                                        variant="soft",
                                        color_scheme="gray",
                                        on_click=FeedbackState.clear_fb_files,
                                    ),
                                    spacing="2",
                                ),
                            ),
                            spacing="2",
                            align="start",
                            width="100%",
                        ),
                        _fb_msg_banner(),
                        rx.hstack(
                            rx.spacer(),
                            rx.button(
                                rx.hstack(
                                    rx.icon("send", size=16), "提交反馈", spacing="2"
                                ),
                                on_click=FeedbackState.submit_feedback,
                                color_scheme="blue",
                                size="2",
                                data_testid="fb-submit",
                            ),
                            width="100%",
                        ),
                        spacing="4",
                        width="100%",
                    ),
                    max_width="760px",
                    width="100%",
                ),
                spacing="2",
                width="100%",
                max_width="760px",
            ),
            class_name="app-container",
            width="100%",
        ),
        background="var(--bg)",
        min_height="100vh",
        class_name=ThemeState.root_class,
    )


def _fa_status_badge(status: str) -> rx.Component:
    """状态徽章配色"""
    return rx.match(
        status,
        ("待处理", rx.badge("待处理", color_scheme="orange", variant="soft", size="1")),
        ("已确认", rx.badge("已确认", color_scheme="blue", variant="soft", size="1")),
        ("已修复", rx.badge("已修复", color_scheme="green", variant="soft", size="1")),
        ("已忽略", rx.badge("已忽略", color_scheme="gray", variant="soft", size="1")),
        rx.badge(status, color_scheme="gray", variant="soft", size="1"),
    )


def _fa_item_row(item: dict[str, Any]) -> rx.Component:
    """反馈列表行（vstack 卡片行，点击打开详情）"""
    return rx.card(
        rx.hstack(
            rx.vstack(
                rx.hstack(
                    _fa_status_badge(item["status"]),
                    rx.badge(
                        item["issue_type"],
                        color_scheme="purple",
                        variant="soft",
                        size="1",
                    ),
                    rx.text(item["protocol"], size="1", color="var(--muted)"),
                    # 桌面端 GUI 提交标记（Web 表单提交 source=web，不显示）
                    rx.cond(
                        item.get("source", "web") == "gui",
                        rx.badge(
                            "桌面端", color_scheme="cyan", variant="solid", size="1"
                        ),
                    ),
                    spacing="2",
                ),
                rx.text(
                    item["description"],
                    size="2",
                    color="var(--text-2)",
                    no_of_lines=2,
                    width="100%",
                ),
                rx.hstack(
                    rx.text(
                        "#" + item["id"].to_string(), size="1", color="var(--muted-2)"
                    ),
                    rx.text(item["created_at"], size="1", color="var(--muted-2)"),
                    spacing="3",
                ),
                spacing="1",
                align="start",
                flex="1",
            ),
            rx.icon("chevron_right", size=18, color="var(--muted-2)"),
            spacing="3",
            align="center",
            width="100%",
            cursor="pointer",
            on_click=lambda: FeedbackState.fa_open_detail(item),
        ),
        width="100%",
        padding="12px 16px",
    )


def _fa_detail_dialog() -> rx.Component:
    """反馈详情弹窗：完整信息 + 截图预览 + 状态/删除操作

    注：fa_detail 空时字段用 rx.cond 包裹或空串 fallback —— 详情弹窗仅在
    fa_open_detail 设置后打开，实际打开时字段必有值；这里用
    rx.cond(FeedbackState.fa_detail_open, ...) 已在外层 root open 控制，
    内部直接用 safe getter var（空 dict 取值返回空串）。
    """
    d = FeedbackState.fa_detail
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("反馈详情"),
            rx.vstack(
                rx.hstack(
                    _fa_status_badge(d["status"]),
                    rx.badge(
                        d["issue_type"],
                        color_scheme="purple",
                        variant="soft",
                        size="1",
                    ),
                    rx.text(
                        d["protocol"],
                        size="2",
                        color="var(--muted)",
                    ),
                    spacing="2",
                ),
                rx.text(
                    "#" + d["id"].to_string() + "  ·  " + d["created_at"].to_string(),
                    size="1",
                    color="var(--muted-2)",
                ),
                rx.text(
                    d["description"],
                    size="2",
                    color="var(--text)",
                    style={"white_space": "pre-wrap"},
                    width="100%",
                ),
                rx.cond(
                    d["contact"] != "",
                    rx.text(
                        "联系方式: " + d["contact"].to_string(),
                        size="2",
                        color="var(--text-2)",
                    ),
                ),
                # GUI 桌面端提交的环境信息（Web 表单提交无此字段）
                rx.cond(
                    (d.get("source", "web") == "gui") & (d.get("sys_info", "") != ""),
                    rx.vstack(
                        rx.text(
                            "客户端环境",
                            size="2",
                            font_weight="medium",
                            color="var(--text-2)",
                        ),
                        rx.code(
                            d.get("sys_info", "").to(str),
                            size="1",
                            white_space="pre-wrap",
                            width="100%",
                            background="var(--bg)",
                            padding="8px",
                            border_radius="6px",
                        ),
                        spacing="1",
                        align="start",
                        width="100%",
                    ),
                ),
                # 截图预览
                rx.cond(
                    d["screenshots"].to(str) != "",
                    rx.vstack(
                        rx.text("截图", size="2", font_weight="medium"),
                        rx.foreach(
                            d["screenshots"].to(str).split(";"),
                            lambda name: rx.cond(
                                name != "",
                                rx.image(
                                    src="/fbimg/" + name,
                                    max_height="320px",
                                    max_width="100%",
                                    border_radius="8px",
                                    border="1px solid var(--border)",
                                ),
                            ),
                        ),
                        spacing="2",
                        align="start",
                    ),
                ),
                # 详情内提示（状态修改结果等）
                rx.cond(
                    FeedbackState.fa_detail_msg != "",
                    rx.text(
                        FeedbackState.fa_detail_msg,
                        size="2",
                        color=rx.cond(
                            FeedbackState.fa_detail_msg.contains("需要管理员"),
                            "var(--danger)",
                            "var(--ok)",
                        ),
                    ),
                ),
                # 状态操作（仅管理员登录后可见；未登录用户只读）
                rx.cond(
                    State.admin_logged_in,
                    rx.hstack(
                        rx.text("标记状态:", size="2", color="var(--muted)"),
                        rx.button(
                            "已确认",
                            size="1",
                            variant="soft",
                            color_scheme="blue",
                            on_click=lambda: FeedbackState.fa_set_status("已确认"),
                        ),
                        rx.button(
                            "已修复",
                            size="1",
                            variant="soft",
                            color_scheme="green",
                            on_click=lambda: FeedbackState.fa_set_status("已修复"),
                        ),
                        rx.button(
                            "已忽略",
                            size="1",
                            variant="soft",
                            color_scheme="gray",
                            on_click=lambda: FeedbackState.fa_set_status("已忽略"),
                        ),
                        rx.spacer(),
                        rx.button(
                            rx.hstack(rx.icon("trash_2", size=14), "删除", spacing="1"),
                            size="1",
                            variant="soft",
                            color_scheme="red",
                            on_click=FeedbackState.fa_delete_current,
                        ),
                        spacing="2",
                        width="100%",
                    ),
                    rx.hstack(
                        rx.icon("info", size=14, color="var(--muted-2)"),
                        rx.text(
                            "管理员登录后可修改状态或删除",
                            size="1",
                            color="var(--muted-2)",
                        ),
                        spacing="1",
                    ),
                ),
                rx.dialog.close(
                    rx.hstack(
                        rx.spacer(),
                        rx.button(
                            "关闭",
                            variant="soft",
                            size="2",
                            on_click=FeedbackState.fa_close_detail,
                        ),
                        spacing="2",
                    ),
                    top="auto",
                ),
                spacing="3",
                width="100%",
            ),
            max_width="680px",
            max_height="80vh",
            style={"overflow_y": "auto"},
        ),
        open=FeedbackState.fa_detail_open,
        # 点遮罩/Esc 关闭：受控弹窗必须显式同步 State，
        # 否则 Radix 内部关闭请求不会改 fa_detail_open，弹窗永远关不掉
        on_open_change=FeedbackState.fa_on_open_change,
    )


def feedback_list_tab() -> rx.Component:
    """问题反馈列表 Tab（主页内，所有人可见；管理操作仅登录后）"""
    return rx.vstack(
        rx.hstack(
            rx.icon("message_square_heart", size=20, color="var(--accent)"),
            rx.heading("问题反馈", size="4", font_weight="bold"),
            rx.spacer(),
            rx.el.a(
                rx.hstack(rx.icon("send", size=14), "我要反馈", spacing="1"),
                href="/feedback",
                class_name="app-header-btn",
                style={
                    "text_decoration": "none",
                    "color": "white",
                    "background": "linear-gradient(135deg, var(--accent, #2563eb), var(--accent-ink, #3b82f6))",
                    "padding": "6px 14px",
                    "border_radius": "8px",
                    "font_size": "13px",
                },
                data_testid="tab-feedback-submit",
            ),
            spacing="2",
            width="100%",
        ),
        rx.cond(
            State.admin_logged_in,
            rx.badge(
                "管理员模式：可修改状态/删除",
                color_scheme="blue",
                variant="soft",
                size="1",
            ),
            rx.badge(
                "查看模式：管理员登录后可处理反馈",
                color_scheme="gray",
                variant="soft",
                size="1",
            ),
        ),
        rx.cond(
            FeedbackState.fa_msg != "",
            rx.text(FeedbackState.fa_msg, size="2", color="var(--muted)"),
        ),
        rx.cond(
            FeedbackState.fa_total > 0,
            rx.vstack(
                rx.foreach(FeedbackState.fa_items, _fa_item_row),
                spacing="2",
                width="100%",
            ),
            rx.vstack(
                rx.icon("inbox", size=36, color="var(--border-strong)"),
                rx.text(
                    "暂无反馈，点击右上角「我要反馈」提交第一条",
                    size="3",
                    color="var(--muted-2)",
                ),
                spacing="2",
                align="center",
                padding="48px 0",
                width="100%",
            ),
        ),
        # 分页
        rx.cond(
            FeedbackState.fa_total > 20,
            rx.hstack(
                rx.button(
                    "« 首页",
                    size="1",
                    variant="soft",
                    on_click=FeedbackState.fa_first_page,
                    disabled=FeedbackState.fa_page == 0,
                ),
                rx.button(
                    "‹ 上一页",
                    size="1",
                    variant="soft",
                    on_click=FeedbackState.fa_prev_page,
                    disabled=FeedbackState.fa_page == 0,
                ),
                rx.text(
                    "第 "
                    + (FeedbackState.fa_page + 1).to_string()
                    + " 页 / 共 "
                    + (((FeedbackState.fa_total + 19) // 20).to_string())
                    + " 页（"
                    + FeedbackState.fa_total.to_string()
                    + " 条）",
                    size="1",
                    color="var(--muted)",
                ),
                rx.button(
                    "下一页 ›",
                    size="1",
                    variant="soft",
                    on_click=FeedbackState.fa_next_page,
                    disabled=(FeedbackState.fa_page + 1) * 20 >= FeedbackState.fa_total,
                ),
                spacing="2",
                align="center",
            ),
        ),
        _fa_detail_dialog(),
        spacing="3",
        width="100%",
        max_width="1000px",
    )


def feedback_admin_page() -> rx.Component:
    """反馈管理页（历史入口，现列表已迁至主页「问题反馈」Tab，此页保留链接兼容）"""
    return rx.box(
        theme_style(),
        rx.el.style(GLOBAL_CSS),
        header(show_parse_controls=False),
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.icon("inbox", size=24, color="var(--accent)"),
                    rx.heading("反馈管理", size="5", font_weight="bold"),
                    spacing="2",
                ),
                rx.text(
                    "反馈列表已迁移至主页「问题反馈」标签页（与发布管理同级）。",
                    size="2",
                    color="var(--muted)",
                ),
                rx.text(
                    "在该标签页中所有人可查看反馈列表与状态；管理员登录后可修改状态/删除。",
                    size="2",
                    color="var(--muted)",
                ),
                rx.el.a(
                    rx.hstack(
                        rx.icon("terminal", size=16),
                        "前往在线工具 · 问题反馈",
                        spacing="2",
                    ),
                    href=landing_web.INTERNAL_LINKS["tool"],
                    data_testid="admin-goto-tool",
                    style={
                        "text_decoration": "none",
                        "color": "white",
                        "background": "linear-gradient(135deg, var(--accent, #2563eb), var(--accent-ink, #3b82f6))",
                        "padding": "10px 20px",
                        "border_radius": "10px",
                        "font_weight": "medium",
                    },
                ),
                spacing="3",
                align="start",
                max_width="640px",
            ),
            class_name="app-container",
            width="100%",
        ),
        background="var(--bg)",
        min_height="100vh",
        class_name=ThemeState.root_class,
    )


# ═══════════════════════════════════════════════════════════════
# 报文分享（列表页 /share + 主页分享表单弹窗）
# ═══════════════════════════════════════════════════════════════


def _sh_source_badge(source: str) -> rx.Component:
    """来源徽章：gui → 青色「桌面端」；web 不显示（与反馈列表口径一致）"""
    return rx.cond(
        source == "gui",
        rx.badge("桌面端", color_scheme="cyan", variant="solid", size="1"),
    )


def _sh_item_card(item: dict[str, Any]) -> rx.Component:
    """分享列表卡片（点击开详情）"""
    return rx.card(
        rx.hstack(
            rx.vstack(
                rx.hstack(
                    rx.badge(
                        item["protocol"],
                        color_scheme="purple",
                        variant="soft",
                        size="1",
                    ),
                    _sh_source_badge(item.get("source", "web")),
                    rx.text(
                        "分享人: ",
                        size="1",
                        color="var(--text-2)",
                        font_weight="medium",
                    ),
                    rx.text(
                        item["sharer"],
                        size="1",
                        color="var(--text-2)",
                        font_weight="medium",
                    ),
                    spacing="2",
                ),
                rx.code(
                    item["frame_hex"],
                    size="1",
                    font_family="monospace",
                    style={
                        "white_space": "nowrap",
                        "overflow": "hidden",
                        "text_overflow": "ellipsis",
                        "max_width": "100%",
                        "display": "block",
                    },
                ),
                rx.hstack(
                    rx.cond(
                        item.get("note", "") != "",
                        rx.text(item["note"], size="1", color="var(--muted)"),
                    ),
                    rx.text(
                        "#",
                        size="1",
                        color="var(--muted-2)",
                    ),
                    rx.text(
                        item["id"].to_string(),
                        size="1",
                        color="var(--muted-2)",
                    ),
                    rx.text("·", size="1", color="var(--muted-2)"),
                    rx.text(
                        item["created_at"],
                        size="1",
                        color="var(--muted-2)",
                    ),
                    spacing="3",
                ),
                spacing="1",
                align="start",
                flex="1",
            ),
            rx.icon("chevron_right", size=18, color="var(--muted-2)"),
            spacing="3",
            align="center",
            width="100%",
            cursor="pointer",
            on_click=lambda: ShareState.sh_open_detail(item),
        ),
        # 管理员删除按钮（仅登录后显示；stop_propagation 防止触发卡片开详情）
        # 放在卡片 on_click 容器之外，删除点击不冒泡到详情
        rx.cond(
            ShareState.admin_logged_in,
            rx.button(
                rx.hstack(rx.icon("trash", size=14), "删除", spacing="1"),
                size="1",
                color_scheme="red",
                variant="soft",
                on_click=[
                    rx.stop_propagation,
                    lambda: ShareState.sh_ask_delete(item["id"]),
                ],
                data_testid="sh-delete-btn",
            ),
        ),
        width="100%",
        padding="12px 16px",
    )


def _sh_delete_confirm_dialog() -> rx.Component:
    """删除确认弹窗（受控三件套：on_open_change 同步 + 显式关闭按钮）"""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("确认删除"),
            rx.dialog.description("确定删除这条分享记录？删除后不可恢复。"),
            rx.vstack(
                rx.cond(
                    ShareState.sh_admin_msg != "",
                    rx.text(
                        ShareState.sh_admin_msg,
                        size="2",
                        color="var(--danger)",
                    ),
                ),
                rx.hstack(
                    rx.spacer(),
                    rx.button(
                        "取消",
                        variant="soft",
                        size="2",
                        on_click=ShareState.sh_cancel_delete,
                    ),
                    rx.button(
                        rx.hstack(rx.icon("trash", size=14), "确认删除", spacing="1"),
                        color_scheme="red",
                        size="2",
                        on_click=ShareState.sh_confirm_delete,
                    ),
                    spacing="2",
                ),
                spacing="3",
                width="100%",
            ),
            max_width="420px",
        ),
        open=ShareState.sh_confirm_open,
        on_open_change=ShareState.sh_cancel_delete,
    )


def _sh_detail_dialog() -> rx.Component:
    """分享详情弹窗：完整 hex + 复制 + 协议信息"""
    d = ShareState.sh_detail
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("报文分享详情"),
            rx.vstack(
                rx.hstack(
                    rx.badge(
                        d["protocol"], color_scheme="purple", variant="soft", size="1"
                    ),
                    _sh_source_badge(d.get("source", "web")),
                    rx.text("#", size="1", color="var(--muted-2)"),
                    rx.text(d["id"].to_string(), size="1", color="var(--muted-2)"),
                    rx.text("·", size="1", color="var(--muted-2)"),
                    rx.text(d["created_at"], size="1", color="var(--muted-2)"),
                    spacing="2",
                ),
                rx.hstack(
                    rx.text("分享人:", size="2", font_weight="medium"),
                    rx.text(d["sharer"], size="2", font_weight="medium"),
                    spacing="2",
                ),
                rx.cond(
                    d.get("note", "") != "",
                    rx.text(
                        d["note"],
                        size="2",
                        color="var(--text-2)",
                        style={"white_space": "pre-wrap"},
                        width="100%",
                    ),
                ),
                rx.vstack(
                    rx.hstack(
                        rx.text("报文:", size="2", font_weight="medium"),
                        rx.spacer(),
                        rx.button(
                            rx.hstack(rx.icon("copy", size=14), "复制", spacing="1"),
                            size="1",
                            variant="soft",
                            on_click=ShareState.copy_detail_hex,
                        ),
                        spacing="2",
                        width="100%",
                    ),
                    rx.code(
                        d["frame_hex"],
                        size="1",
                        font_family="monospace",
                        style={
                            "white_space": "pre-wrap",
                            "word_break": "break-all",
                            "width": "100%",
                            "padding": "8px",
                            "background": "var(--bg)",
                            "border_radius": "6px",
                        },
                    ),
                    spacing="1",
                    align="start",
                    width="100%",
                ),
                rx.dialog.close(
                    rx.hstack(
                        rx.spacer(),
                        rx.button(
                            "关闭",
                            variant="soft",
                            size="2",
                            on_click=ShareState.sh_close_detail,
                        ),
                        spacing="2",
                    ),
                    top="auto",
                ),
                spacing="3",
                width="100%",
            ),
            max_width="760px",
            max_height="80vh",
            style={"overflow_y": "auto"},
        ),
        open=ShareState.sh_detail_open,
        on_open_change=ShareState.sh_on_open_change,
    )


def _share_submit_dialog() -> rx.Component:
    """主页「分享此帧」表单弹窗（受控三件套）"""
    return rx.dialog.root(
        rx.dialog.content(
            rx.dialog.title("分享此帧"),
            rx.dialog.description("分享后所有用户可在「报文分享」页查看与搜索。"),
            rx.vstack(
                rx.vstack(
                    rx.text("报文", size="2", font_weight="medium"),
                    rx.code(
                        ShareState.sf_hex,
                        size="1",
                        font_family="monospace",
                        style={
                            "white_space": "pre-wrap",
                            "word_break": "break-all",
                            "width": "100%",
                            "padding": "8px",
                            "background": "var(--bg)",
                            "border_radius": "6px",
                            "max_height": "120px",
                            "overflow_y": "auto",
                        },
                    ),
                    spacing="1",
                    align="start",
                    width="100%",
                ),
                rx.vstack(
                    rx.text("协议", size="2", font_weight="medium"),
                    rx.select(
                        FEEDBACK_PROTOCOL_OPTIONS,
                        value=ShareState.sf_protocol,
                        on_change=ShareState.set_sf_protocol,
                        width="100%",
                        data_testid="sf-protocol",
                    ),
                    spacing="1",
                    align="start",
                    width="100%",
                ),
                rx.vstack(
                    rx.hstack(
                        rx.text("分享人", size="2", font_weight="medium"),
                        rx.badge("必填", color_scheme="red", variant="soft", size="1"),
                        spacing="2",
                    ),
                    rx.input(
                        placeholder="你的名字/昵称（≤50 字）",
                        value=ShareState.sf_sharer,
                        on_change=ShareState.set_sf_sharer,
                        max_length=50,
                        width="100%",
                        data_testid="sf-sharer",
                    ),
                    spacing="1",
                    align="start",
                    width="100%",
                ),
                rx.vstack(
                    rx.text("说明（选填，≤500 字）", size="2", font_weight="medium"),
                    rx.text_area(
                        placeholder="这帧报文的用途/场景，方便他人理解",
                        value=ShareState.sf_note,
                        on_change=ShareState.set_sf_note,
                        min_height="80px",
                        width="100%",
                        data_testid="sf-note",
                    ),
                    spacing="1",
                    align="start",
                    width="100%",
                ),
                rx.cond(
                    ShareState.sf_msg != "",
                    rx.text(
                        ShareState.sf_msg,
                        size="2",
                        color=rx.cond(
                            ShareState.sf_msg_type == "error",
                            "var(--danger)",
                            "var(--ok)",
                        ),
                    ),
                ),
                rx.hstack(
                    rx.spacer(),
                    rx.button(
                        "取消", variant="soft", size="2", on_click=ShareState.sf_close
                    ),
                    rx.button(
                        rx.hstack(rx.icon("share_2", size=14), "分享", spacing="1"),
                        on_click=ShareState.sf_submit,
                        color_scheme="teal",
                        size="2",
                        data_testid="sf-submit",
                    ),
                    spacing="2",
                ),
                spacing="3",
                width="100%",
            ),
            max_width="620px",
            max_height="85vh",
            style={"overflow_y": "auto"},
        ),
        open=ShareState.sf_open,
        on_open_change=ShareState.sf_on_open_change,
    )


def share_page() -> rx.Component:
    """报文分享页（所有人可浏览/搜索；提交入口在主页单帧解析）"""
    return rx.box(
        theme_style(),
        rx.el.style(GLOBAL_CSS),
        header(show_parse_controls=False),
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.icon("share_2", size=24, color="var(--accent)"),
                    rx.heading("报文分享", size="5", font_weight="bold"),
                    rx.badge(
                        ShareState.sh_total.to_string() + " 条",
                        color_scheme="blue",
                        variant="soft",
                        size="2",
                    ),
                    spacing="2",
                ),
                rx.text(
                    "在主页单帧解析后点击「分享此帧」，即可把有价值的命令帧分享到这里，供所有人查阅。",
                    size="2",
                    color="var(--muted)",
                ),
                # 搜索框
                rx.hstack(
                    rx.input(
                        placeholder="搜索：报文 hex（支持连续无空格）/ 协议 / 分享人 / 说明",
                        value=ShareState.sh_keyword,
                        on_change=ShareState.set_sh_keyword,
                        width="420px",
                        data_testid="sh-search",
                    ),
                    rx.el.a(
                        rx.hstack(
                            rx.icon("home", size=14), "去解析并分享", spacing="1"
                        ),
                        href=landing_web.INTERNAL_LINKS["tool"],
                        data_testid="share-goto-tool",
                        class_name="app-header-btn",
                        style={
                            "text_decoration": "none",
                            "color": "white",
                            "background": "linear-gradient(135deg, var(--accent, #2563eb), var(--accent-ink, #3b82f6))",
                        },
                    ),
                    spacing="3",
                    wrap="wrap",
                ),
                rx.cond(
                    ShareState.sh_msg != "",
                    rx.text(ShareState.sh_msg, size="2", color="var(--danger)"),
                ),
                # 列表
                rx.cond(
                    ShareState.sh_total > 0,
                    rx.vstack(
                        rx.foreach(ShareState.sh_items, _sh_item_card),
                        spacing="2",
                        width="100%",
                    ),
                    rx.vstack(
                        rx.icon("inbox", size=36, color="var(--border-strong)"),
                        rx.text(
                            rx.cond(
                                ShareState.sh_keyword != "",
                                "没有匹配的分享记录，换个关键词试试",
                                "暂无分享，去主页解析报文后点击「分享此帧」",
                            ),
                            size="3",
                            color="var(--muted-2)",
                        ),
                        spacing="2",
                        align="center",
                        padding="48px 0",
                        width="100%",
                    ),
                ),
                # 分页
                rx.cond(
                    ShareState.sh_pages > 1,
                    rx.hstack(
                        rx.button(
                            "‹ 上一页",
                            size="1",
                            variant="soft",
                            on_click=ShareState.sh_prev,
                            disabled=ShareState.sh_page <= 1,
                        ),
                        rx.text(
                            "第 "
                            + ShareState.sh_page.to_string()
                            + " / "
                            + ShareState.sh_pages.to_string()
                            + " 页（"
                            + ShareState.sh_total.to_string()
                            + " 条）",
                            size="1",
                            color="var(--muted)",
                        ),
                        rx.button(
                            "下一页 ›",
                            size="1",
                            variant="soft",
                            on_click=ShareState.sh_next,
                            disabled=ShareState.sh_page >= ShareState.sh_pages,
                        ),
                        spacing="2",
                        align="center",
                    ),
                ),
                _sh_detail_dialog(),
                _sh_delete_confirm_dialog(),
                spacing="3",
                width="100%",
                max_width="1000px",
            ),
            class_name="app-container",
            width="100%",
        ),
        background="var(--bg)",
        min_height="100vh",
        class_name=ThemeState.root_class,
    )


# ═══════════════════════════════════════════════════════════════
# 管理员登录对话框
# ═══════════════════════════════════════════════════════════════


def admin_login_dialog() -> rx.Component:
    """管理员登录对话框（模态）"""
    return rx.cond(
        State.admin_show_login_dialog,
        rx.dialog.root(
            rx.dialog.content(
                rx.dialog.title("管理员登录"),
                rx.dialog.description("输入管理员密码以访问发布管理功能。"),
                rx.vstack(
                    rx.input(
                        type="password",
                        placeholder="请输入管理员密码",
                        value=State.admin_password_input,
                        on_change=State.set_admin_password_input,
                        width="100%",
                    ),
                    rx.cond(
                        State.admin_msg != "",
                        rx.text(State.admin_msg, size="1", color="red"),
                    ),
                    rx.text(
                        "默认密码: admin123（首次登录后请及时修改）",
                        size="1",
                        color="gray",
                    ),
                    spacing="3",
                    width="100%",
                    padding_top="12px",
                ),
                rx.dialog.close(
                    rx.hstack(
                        rx.spacer(),
                        rx.button("取消", variant="soft", size="2"),
                        rx.button(
                            "登录",
                            on_click=State.admin_login,
                            color_scheme="blue",
                            size="2",
                        ),
                        spacing="2",
                    ),
                    top="auto",
                ),
                max_width="420px",
            ),
            open=State.admin_show_login_dialog,
        ),
    )


# ═══════════════════════════════════════════════════════════════
# 发布管理 Tab
# ═══════════════════════════════════════════════════════════════


def release_tab() -> rx.Component:
    """发布管理页面（管理员登录后可见）"""
    return rx.vstack(
        # 当前版本信息卡片
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("package", size=22, color="var(--ok)"),
                    rx.heading("当前版本", size="4", font_weight="bold"),
                    rx.spacer(),
                    rx.button(
                        rx.icon("refresh_ccw", size=14),
                        size="1",
                        variant="soft",
                        on_click=State.load_release_info,
                        cursor="pointer",
                    ),
                    rx.cond(
                        State.admin_is_default_pwd,
                        rx.badge(
                            "使用默认密码，请修改", color_scheme="red", variant="soft"
                        ),
                    ),
                    spacing="2",
                    width="100%",
                ),
                rx.cond(
                    State.release_current != {},
                    rx.vstack(
                        rx.hstack(
                            rx.text(
                                "版本号:",
                                font_weight="medium",
                                width="100px",
                                color="gray",
                            ),
                            rx.text(
                                State.release_current["version"],
                                size="2",
                                font_weight="semibold",
                            ),
                            width="100%",
                        ),
                        rx.hstack(
                            rx.text(
                                "文件名:",
                                font_weight="medium",
                                width="100px",
                                color="gray",
                            ),
                            rx.text(State.release_current["exe_name"], size="2"),
                            width="100%",
                        ),
                        rx.hstack(
                            rx.text(
                                "大小:",
                                font_weight="medium",
                                width="100px",
                                color="gray",
                            ),
                            rx.text(State.release_current["size_mb"] + " MB", size="2"),
                            width="100%",
                        ),
                        rx.hstack(
                            rx.text(
                                "发布时间:",
                                font_weight="medium",
                                width="100px",
                                color="gray",
                            ),
                            rx.text(State.release_current["published_at"], size="2"),
                            width="100%",
                        ),
                        rx.hstack(
                            rx.text(
                                "下载地址:",
                                font_weight="medium",
                                width="100px",
                                color="gray",
                            ),
                            rx.text(
                                State.release_current["url"],
                                size="1",
                                color="blue",
                                word_break="break-all",
                            ),
                            width="100%",
                        ),
                        rx.hstack(
                            rx.text(
                                "SHA-256:",
                                font_weight="medium",
                                width="100px",
                                color="gray",
                            ),
                            rx.code(
                                State.release_current["sha256"],
                                size="1",
                                word_break="break-all",
                            ),
                            width="100%",
                        ),
                        rx.hstack(
                            rx.text(
                                "更新说明:",
                                font_weight="medium",
                                width="100px",
                                color="gray",
                                align_self="flex-start",
                            ),
                            rx.text(
                                State.release_current["notes"],
                                size="2",
                                white_space="pre-wrap",
                            ),
                            width="100%",
                        ),
                        spacing="2",
                        width="100%",
                        padding_top="8px",
                    ),
                    rx.text("暂无已发布版本", size="2", color="gray", padding="20px"),
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
        # 发布新版本卡片
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("upload", size=20, color="var(--accent)"),
                    rx.heading("发布新版本", size="4", font_weight="bold"),
                    spacing="2",
                ),
                # exe 上传
                rx.vstack(
                    rx.text("exe 文件:", size="2", font_weight="medium"),
                    rx.upload(
                        rx.vstack(
                            rx.icon("upload", size=32, color="var(--muted-2)"),
                            rx.text(
                                "拖拽 exe 到此处，或点击选择文件",
                                size="2",
                                color="gray",
                            ),
                            rx.text(
                                "支持 .exe，最大 500MB",
                                size="1",
                                color="var(--muted-2)",
                            ),
                            spacing="2",
                            align="center",
                            justify="center",
                            padding="20px",
                        ),
                        border="1px dashed var(--border-strong)",
                        border_radius="8px",
                        padding="20px",
                        on_drop=State.handle_release_upload,
                        accept={
                            ".exe": [
                                "application/octet-stream",
                                "application/x-msdownload",
                                "application/x-dosexec",
                                "application/vnd.microsoft.portable-executable",
                            ]
                        },
                        max_files=1,
                        max_size=500 * 1024 * 1024,
                        width="100%",
                        id="release-upload",
                    ),
                    # 已上传文件信息
                    rx.cond(
                        State.release_upload_name != "",
                        rx.hstack(
                            rx.icon("file_check", size=18, color="var(--ok)"),
                            rx.text(
                                State.release_upload_name,
                                size="2",
                                font_weight="medium",
                            ),
                            rx.text(
                                f"（{State.release_upload_size_mb} MB）",
                                size="1",
                                color="gray",
                            ),
                            spacing="2",
                            align="center",
                        ),
                    ),
                    spacing="2",
                    width="100%",
                ),
                # 版本号
                rx.vstack(
                    rx.text("版本号:", size="2", font_weight="medium"),
                    rx.input(
                        placeholder="如 1.14.0",
                        value=State.release_version,
                        on_change=State.set_release_version,
                        width="100%",
                    ),
                    spacing="1",
                    width="100%",
                ),
                # 下载地址
                rx.vstack(
                    rx.text("下载地址:", size="2", font_weight="medium"),
                    rx.input(
                        placeholder="http://服务器地址/download/南网协议解析工具.exe",
                        value=State.release_url,
                        on_change=State.set_release_url,
                        width="100%",
                    ),
                    rx.text(
                        "必须是完整 URL（含 http://），客户端 auto_updater 直接使用此字段下载。默认继承上一版本的地址。",
                        size="1",
                        color="gray",
                    ),
                    spacing="1",
                    width="100%",
                ),
                # 更新说明
                rx.vstack(
                    rx.text("更新说明:", size="2", font_weight="medium"),
                    rx.text_area(
                        placeholder="本次更新内容...",
                        value=State.release_notes,
                        on_change=State.set_release_notes,
                        min_height="80px",
                        width="100%",
                    ),
                    spacing="1",
                    width="100%",
                ),
                # 软件界面截图上传
                rx.vstack(
                    rx.text("软件界面截图:", size="2", font_weight="medium"),
                    rx.upload(
                        rx.vstack(
                            rx.icon("image", size=24, color="var(--muted-2)"),
                            rx.text(
                                "拖拽截图到此处，或点击选择", size="2", color="gray"
                            ),
                            rx.text(
                                "支持 png/jpg/jpeg/gif/webp",
                                size="1",
                                color="var(--muted-2)",
                            ),
                            spacing="1",
                            align="center",
                            justify="center",
                            padding="12px",
                        ),
                        border="1px dashed var(--border-strong)",
                        border_radius="8px",
                        padding="12px",
                        on_drop=State.handle_screenshot_upload,
                        accept={
                            "image/*": [".png", ".jpg", ".jpeg", ".gif", ".webp"],
                        },
                        max_files=1,
                        max_size=10 * 1024 * 1024,
                        width="100%",
                        id="screenshot-upload",
                    ),
                    rx.cond(
                        State.release_screenshot_uploaded,
                        rx.hstack(
                            rx.icon("check_check", size=16, color="var(--ok)"),
                            rx.text(
                                "截图已上传，发布时一起更新",
                                size="1",
                                color="var(--ok)",
                            ),
                            spacing="1",
                        ),
                    ),
                    rx.text(
                        "发布后显示在客户端下载页的「软件界面」区域，文件名固定为 client_screenshot.png",
                        size="1",
                        color="gray",
                    ),
                    spacing="1",
                    width="100%",
                ),
                # README 上传
                rx.vstack(
                    rx.text("客户端说明 (README):", size="2", font_weight="medium"),
                    rx.upload(
                        rx.vstack(
                            rx.icon("file-text", size=24, color="var(--muted-2)"),
                            rx.text(
                                "拖拽 README 文件到此处，或点击选择",
                                size="2",
                                color="gray",
                            ),
                            rx.text(
                                "支持 md/markdown/txt 文本文件",
                                size="1",
                                color="var(--muted-2)",
                            ),
                            spacing="1",
                            align="center",
                            justify="center",
                            padding="12px",
                        ),
                        border="1px dashed var(--border-strong)",
                        border_radius="8px",
                        padding="12px",
                        on_drop=State.handle_readme_upload,
                        accept={
                            "text/markdown": [".md", ".markdown"],
                            "text/plain": [".txt"],
                        },
                        max_files=1,
                        max_size=2 * 1024 * 1024,
                        width="100%",
                        id="readme-upload",
                    ),
                    rx.cond(
                        State.release_readme_name != "",
                        rx.hstack(
                            rx.icon("check_check", size=16, color="var(--ok)"),
                            rx.text(
                                f"已加载 {State.release_readme_name}，发布时一起更新",
                                size="1",
                                color="var(--ok)",
                            ),
                            spacing="1",
                        ),
                    ),
                    rx.text(
                        "发布后显示在客户端下载页底部，留空则不更新（保留已有 README）。",
                        size="1",
                        color="gray",
                    ),
                    spacing="1",
                    width="100%",
                ),
                # 进度条
                rx.cond(
                    State.release_publishing,
                    rx.vstack(
                        rx.progress(value=State.release_progress, width="100%"),
                        rx.text(
                            f"SHA-256 计算中... {State.release_progress}%",
                            size="1",
                            color="gray",
                        ),
                        spacing="1",
                        width="100%",
                    ),
                ),
                # 状态消息
                rx.cond(
                    State.release_status != "",
                    rx.vstack(
                        rx.cond(
                            State.release_status_type == "success",
                            rx.text(
                                State.release_status,
                                size="2",
                                color="green",
                                font_weight="semibold",
                            ),
                        ),
                        rx.cond(
                            State.release_status_type == "error",
                            rx.text(State.release_status, size="2", color="red"),
                        ),
                        rx.cond(
                            State.release_status_type == "info",
                            rx.text(State.release_status, size="2", color="blue"),
                        ),
                        spacing="1",
                        width="100%",
                    ),
                ),
                # 发布按钮
                rx.hstack(
                    rx.spacer(),
                    rx.button(
                        rx.hstack(rx.icon("rocket", size=16), "发布", spacing="2"),
                        on_click=State.publish_release,
                        color_scheme="blue",
                        size="3",
                        disabled=State.release_publishing,
                        cursor="pointer",
                    ),
                    spacing="2",
                    width="100%",
                ),
                spacing="4",
                width="100%",
            ),
            width="100%",
        ),
        # 发布成功弹窗
        rx.dialog.root(
            rx.dialog.content(
                rx.dialog.title(
                    rx.hstack(
                        rx.icon("check_check", size=24, color="green"),
                        "发布成功",
                        spacing="2",
                    ),
                ),
                rx.dialog.description(
                    rx.vstack(
                        rx.text(
                            State.release_success_info["version"],
                            size="3",
                            font_weight="medium",
                        ),
                        rx.text(
                            State.release_success_info["size_mb"],
                            size="2",
                            color="gray",
                        ),
                        rx.text(
                            State.release_success_info["exe_name"],
                            size="2",
                            color="gray",
                        ),
                        rx.vstack(
                            rx.text("SHA-256:", size="2", color="gray"),
                            rx.code(
                                State.release_success_info["sha256"],
                                size="1",
                                word_break="break-all",
                                background="var(--bg)",
                                padding="8px",
                                border_radius="4px",
                                width="100%",
                            ),
                            spacing="1",
                            width="100%",
                        ),
                        spacing="3",
                        width="100%",
                        align="start",
                    ),
                ),
                rx.dialog.close(
                    rx.button(
                        "知道了",
                        color_scheme="green",
                        size="3",
                        width="100%",
                        cursor="pointer",
                    ),
                ),
                spacing="4",
                width="100%",
                max_width="500px",
            ),
            open=State.release_show_success_dialog,
            on_open_change=State.set_release_show_success_dialog,
        ),
        # 历史版本卡片
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("history", size=20, color="var(--warn)"),
                    rx.heading("历史版本", size="4", font_weight="bold"),
                    spacing="2",
                ),
                rx.cond(
                    State.release_history.length() > 0,
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("版本号", width="20%"),
                                rx.table.column_header_cell("大小", width="15%"),
                                rx.table.column_header_cell("归档时间", width="25%"),
                                rx.table.column_header_cell("操作", width="40%"),
                            ),
                        ),
                        rx.table.body(
                            rx.foreach(
                                State.release_history,
                                lambda item: rx.table.row(
                                    rx.table.cell(
                                        item["version"], font_weight="medium"
                                    ),
                                    rx.table.cell(item["size_mb"] + " MB"),
                                    rx.table.cell(item["archived_at"], size="1"),
                                    rx.table.cell(
                                        rx.hstack(
                                            rx.button(
                                                "回滚到此版本",
                                                size="1",
                                                variant="soft",
                                                color_scheme="amber",
                                                on_click=lambda: State.rollback_version(
                                                    item["version"]
                                                ),
                                            ),
                                            rx.button(
                                                "删除",
                                                size="1",
                                                variant="soft",
                                                color_scheme="red",
                                                on_click=lambda: State.delete_history_version(
                                                    item["version"]
                                                ),
                                            ),
                                            spacing="2",
                                        ),
                                    ),
                                ),
                            ),
                        ),
                        width="100%",
                        size="2",
                    ),
                    rx.text("暂无历史版本", size="2", color="gray", padding="20px"),
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
        # 修改密码卡片
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("key", size=20, color="var(--accent)"),
                    rx.heading("修改密码", size="4", font_weight="bold"),
                    spacing="2",
                ),
                rx.vstack(
                    rx.text("原密码:", size="2", font_weight="medium"),
                    rx.input(
                        type="password",
                        value=State.admin_change_old,
                        on_change=State.set_admin_change_old,
                        width="100%",
                    ),
                    spacing="1",
                    width="100%",
                ),
                rx.vstack(
                    rx.text("新密码:", size="2", font_weight="medium"),
                    rx.input(
                        type="password",
                        value=State.admin_change_new,
                        on_change=State.set_admin_change_new,
                        width="100%",
                    ),
                    spacing="1",
                    width="100%",
                ),
                rx.vstack(
                    rx.text("确认新密码:", size="2", font_weight="medium"),
                    rx.input(
                        type="password",
                        value=State.admin_change_confirm,
                        on_change=State.set_admin_change_confirm,
                        width="100%",
                    ),
                    spacing="1",
                    width="100%",
                ),
                rx.cond(
                    State.admin_msg != "",
                    rx.text(State.admin_msg, size="2", color="blue"),
                ),
                rx.hstack(
                    rx.spacer(),
                    rx.button(
                        "修改密码",
                        on_click=State.admin_change_password,
                        color_scheme="indigo",
                        size="2",
                        cursor="pointer",
                    ),
                    spacing="2",
                    width="100%",
                ),
                spacing="3",
                width="100%",
                max_width="480px",
            ),
            width="100%",
        ),
        spacing="3",
        width="100%",
    )


# ═══════════════════════════════════════════════════════════════
# 查询 Tab
# ═══════════════════════════════════════════════════════════════


def _lookup_row_key(row):
    """结果表行键（勾选与批量删除共用）：协议7 → ``"03HF01"``；协议0 → ``"E8 00 08 03"``。

    键格式与 `lookup_utils.parse_gdw_row_key` / `parse_di_row_key` 一一对应。
    """
    return rx.cond(
        State.current_protocol == 7,
        row["AFN"].to(str) + row["Fn"].to(str),
        row["DI3"].to(str)
        + " "
        + row["DI2"].to(str)
        + " "
        + row["DI1"].to(str)
        + " "
        + row["DI0"].to(str),
    )


def lookup_tab() -> rx.Component:
    """查询（根据当前协议自动切换查询类型）"""
    return rx.vstack(
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("search", size=20, color="var(--accent)"),
                    rx.heading(State.lookup_title, size="3", font_weight="semibold"),
                    rx.spacer(),
                    rx.badge(
                        f"{State.lookup_results.length()} 条",
                        color_scheme="blue",
                        variant="soft",
                    ),
                    # 批量删除勾选的自定义条目（协议0 → DI；协议7 → AFN+Fn）
                    rx.cond(
                        (State.current_protocol == 0) | (State.current_protocol == 7),
                        rx.button(
                            rx.icon("trash-2", size=14),
                            "删除选中",
                            on_click=State.delete_selected_custom,
                            color_scheme="red",
                            variant="soft",
                            size="1",
                        ),
                    ),
                    spacing="2",
                ),
                rx.hstack(
                    rx.input(
                        placeholder="输入关键词过滤（DI码/名称/说明等）；国网协议下输入 EB 前缀查扩展数据标识...",
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
                rx.text(
                    "提示：切换协议会自动切换查询类型（DI/AFN/OBIS/OI/业务标识等）",
                    size="1",
                    color="gray",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
        # 自定义 DI 增删（协议0 南网 DI 查询；对齐桌面查询页的「添加/删除自定义DI」按钮）
        rx.cond(
            State.current_protocol == 0,
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("plus", size=18, color="var(--accent)"),
                        rx.heading("自定义 DI", size="3", font_weight="semibold"),
                        rx.text(
                            "（★ 为自定义条目，可删除；同键再次添加即覆盖其含义）",
                            size="1",
                            color="gray",
                        ),
                        spacing="2",
                        wrap="wrap",
                    ),
                    rx.hstack(
                        rx.input(
                            placeholder="DI3",
                            value=State.lookup_di3,
                            on_change=lambda v: State.set_lookup_di_field("di3", v),
                            width="90px",
                            size="2",
                        ),
                        rx.input(
                            placeholder="DI2",
                            value=State.lookup_di2,
                            on_change=lambda v: State.set_lookup_di_field("di2", v),
                            width="90px",
                            size="2",
                        ),
                        rx.input(
                            placeholder="DI1",
                            value=State.lookup_di1,
                            on_change=lambda v: State.set_lookup_di_field("di1", v),
                            width="90px",
                            size="2",
                        ),
                        rx.input(
                            placeholder="DI0",
                            value=State.lookup_di0,
                            on_change=lambda v: State.set_lookup_di_field("di0", v),
                            width="90px",
                            size="2",
                        ),
                        rx.input(
                            placeholder="中文含义（如：查询采集任务号）",
                            value=State.lookup_desc,
                            on_change=lambda v: State.set_lookup_di_field("desc", v),
                            width="320px",
                            size="2",
                        ),
                        rx.button(
                            rx.icon("plus", size=16),
                            "添加/覆盖",
                            on_click=State.add_custom_di,
                            color_scheme="blue",
                            size="2",
                        ),
                        spacing="2",
                        wrap="wrap",
                    ),
                    rx.text(
                        "DI 为十六进制（00-FF）；内置 DI 不可删除。保存后立即重新查询。",
                        size="1",
                        color="gray",
                    ),
                    spacing="3",
                    width="100%",
                ),
                width="100%",
            ),
        ),
        # 自定义 AFN+Fn 增删（协议7 国网查询页；对齐桌面「添加/删除自定义AFN+Fn」按钮）
        rx.cond(
            State.current_protocol == 7,
            rx.card(
                rx.vstack(
                    rx.hstack(
                        rx.icon("plus", size=18, color="var(--accent)"),
                        rx.heading("自定义 AFN+Fn", size="3", font_weight="semibold"),
                        rx.text(
                            "（★ 为自定义组合，可勾选后删除；标准定义不可删）",
                            size="1",
                            color="gray",
                        ),
                        spacing="2",
                        wrap="wrap",
                    ),
                    rx.hstack(
                        rx.input(
                            placeholder="AFN (十六进制，如 03)",
                            value=State.lookup_afn,
                            on_change=lambda v: State.set_lookup_afn_field("afn", v),
                            width="200px",
                            size="2",
                        ),
                        rx.input(
                            placeholder="Fn (1-248)",
                            value=State.lookup_fn,
                            on_change=lambda v: State.set_lookup_afn_field("fn", v),
                            width="120px",
                            size="2",
                        ),
                        rx.input(
                            placeholder="功能名称（必填）",
                            value=State.lookup_fn_name,
                            on_change=lambda v: State.set_lookup_afn_field("name", v),
                            width="260px",
                            size="2",
                        ),
                        rx.input(
                            placeholder="AFN类别名称（可选）",
                            value=State.lookup_afn_name,
                            on_change=lambda v: State.set_lookup_afn_field("afn_name", v),
                            width="220px",
                            size="2",
                        ),
                        rx.button(
                            rx.icon("plus", size=16),
                            "添加",
                            on_click=State.add_custom_afn,
                            color_scheme="blue",
                            size="2",
                        ),
                        spacing="2",
                        wrap="wrap",
                    ),
                    rx.text(
                        "AFN 十六进制 00-FF、Fn 十进制 1-248；与标准定义重名的组合会被拒绝。保存后立即重新查询。",
                        size="1",
                        color="gray",
                    ),
                    spacing="3",
                    width="100%",
                ),
                width="100%",
            ),
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
                                    # 「选择」列：协议0/7 的查询页支持勾选后批量删除自定义条目
                                    rx.cond(
                                        (State.current_protocol == 0)
                                        | (State.current_protocol == 7),
                                        rx.table.column_header_cell("选择"),
                                    ),
                                    rx.foreach(
                                        State.lookup_columns,
                                        lambda col: rx.table.column_header_cell(col),
                                    ),
                                    # 「操作」列仅协议0（南网 DI）显示：与桌面查询页
                                    # 的「删除选中自定义DI」按钮同语义，只是粒度到行。
                                    rx.cond(
                                        State.current_protocol == 0,
                                        rx.table.column_header_cell("操作"),
                                    ),
                                )
                            ),
                            rx.table.body(
                                rx.foreach(
                                    State.lookup_results,
                                    lambda row: rx.table.row(
                                        rx.cond(
                                            (State.current_protocol == 0)
                                            | (State.current_protocol == 7),
                                            rx.table.cell(
                                                rx.checkbox(
                                                    checked=State.lookup_selected.contains(
                                                        _lookup_row_key(row)
                                                    ),
                                                    on_change=lambda v: State.toggle_lookup_selection(
                                                        _lookup_row_key(row),
                                                        v,
                                                    ),
                                                    size="1",
                                                ),
                                                font_size="12px",
                                            ),
                                        ),
                                        rx.foreach(
                                            State.lookup_columns,
                                            lambda col: rx.table.cell(
                                                rx.code(row[col], variant="soft"),
                                                font_size="12px",
                                            ),
                                        ),
                                        rx.cond(
                                            State.current_protocol == 0,
                                            rx.table.cell(
                                                rx.cond(
                                                    row["自定义"] == "★",
                                                    rx.button(
                                                        "删除",
                                                        on_click=lambda: State.delete_custom_di(
                                                            row["DI3"], row["DI2"],
                                                            row["DI1"], row["DI0"],
                                                        ),
                                                        size="1",
                                                        color_scheme="red",
                                                        variant="soft",
                                                    ),
                                                    rx.text("—", size="1", color="var(--muted)"),
                                                ),
                                                font_size="12px",
                                            ),
                                        ),
                                    ),
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
                            rx.icon("search", size=48, color="var(--muted-2)"),
                            rx.text(
                                "点击「搜索」或切换协议查看查询数据",
                                color="var(--muted)",
                                size="2",
                            ),
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
            size="1",
            variant="outline",
            color_scheme="blue",
            width="100%",
        )

    return rx.vstack(
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("wrench", size=20, color="var(--accent)"),
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
                    columns="6",
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
                    columns="6",
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
                    columns="6",
                    spacing="2",
                    width="100%",
                ),
                rx.hstack(
                    rx.el.select(
                        rx.el.option("小端(低字节在前)", value="little"),
                        rx.el.option("大端(高字节在前)", value="big"),
                        default_value="little",
                        on_change=State.set_tool_endian,
                        class_name="app-select",
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
                    background="var(--code-bg)",
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
# 频谱图 Tab（SVG 自绘；与协议无关）
# ═══════════════════════════════════════════════════════════════


def _sp_field(label: str, name: str, value, width: str = "90px") -> rx.Component:
    """参数输入（文本，改动即联动/重绘）。"""
    return rx.hstack(
        rx.text(label, size="1", color="gray", white_space="nowrap"),
        rx.input(
            value=value,
            on_change=lambda v: SpectrumState.sp_set_param(name, v),
            width=width,
            size="1",
            font_family="monospace",
        ),
        spacing="1",
        align="center",
    )


def spectrum_tab() -> rx.Component:
    """频谱图：参数 → trace → SVG 网格图 → 测量 → 积分带宽。"""
    from spectrum_widget import DETECTORS, LEVEL_UNITS, RBW_UNITS

    return rx.vstack(
        # ── 参数 ──
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("sliders_horizontal", size=18, color="var(--accent)"),
                    rx.heading("频谱仪参数", size="2", font_weight="semibold"),
                    rx.spacer(),
                    rx.text(
                        "频率字段双向联动（改起始/终止→重算中心与扫宽）",
                        size="1",
                        color="gray",
                    ),
                    spacing="2",
                    width="100%",
                ),
                rx.hstack(
                    _sp_field("起始", "start", SpectrumState.sp_start),
                    _sp_field("终止", "stop", SpectrumState.sp_stop),
                    _sp_field("中心", "center", SpectrumState.sp_center),
                    _sp_field("扫宽", "span", SpectrumState.sp_span),
                    rx.el.select(
                        *[rx.el.option(u, value=u) for u in ("kHz", "MHz", "GHz")],
                        value=SpectrumState.sp_freq_unit,
                        on_change=SpectrumState.sp_set_unit,
                        class_name="app-select",
                    ),
                    spacing="3",
                    align="center",
                    wrap="wrap",
                    width="100%",
                ),
                rx.hstack(
                    _sp_field("参考电平", "ref", SpectrumState.sp_ref, "70px"),
                    _sp_field("每格dB", "dbdiv", SpectrumState.sp_dbdiv, "60px"),
                    _sp_field("纵格数", "ydivs", SpectrumState.sp_ydivs, "50px"),
                    _sp_field("RBW", "rbw", SpectrumState.sp_rbw, "70px"),
                    rx.el.select(
                        *[rx.el.option(u, value=u) for u in RBW_UNITS],
                        value=SpectrumState.sp_rbw_unit,
                        on_change=lambda v: SpectrumState.sp_set_select("rbw_unit", v),
                        class_name="app-select",
                    ),
                    _sp_field("VBW", "vbw", SpectrumState.sp_vbw, "70px"),
                    rx.el.select(
                        *[rx.el.option(u, value=u) for u in RBW_UNITS],
                        value=SpectrumState.sp_vbw_unit,
                        on_change=lambda v: SpectrumState.sp_set_select("vbw_unit", v),
                        class_name="app-select",
                    ),
                    spacing="3",
                    align="center",
                    wrap="wrap",
                    width="100%",
                ),
                rx.hstack(
                    rx.text("幅值单位", size="1", color="gray"),
                    rx.el.select(
                        *[rx.el.option(u, value=u) for u in LEVEL_UNITS],
                        value=SpectrumState.sp_amp_unit,
                        on_change=lambda v: SpectrumState.sp_set_select("amp_unit", v),
                        class_name="app-select",
                    ),
                    rx.checkbox(
                        "输入按 dBm，50Ω 换算",
                        checked=SpectrumState.sp_50ohm,
                        on_change=lambda v: SpectrumState.sp_set_toggle("50ohm", v),
                        size="2",
                    ),
                    rx.text("检波", size="1", color="gray"),
                    rx.el.select(
                        *[rx.el.option(d, value=d) for d in DETECTORS],
                        value=SpectrumState.sp_detector,
                        on_change=lambda v: SpectrumState.sp_set_select("detector", v),
                        class_name="app-select",
                    ),
                    rx.checkbox(
                        "纵轴自动适配",
                        checked=SpectrumState.sp_auto_y,
                        on_change=lambda v: SpectrumState.sp_set_toggle("auto_y", v),
                        size="2",
                    ),
                    spacing="3",
                    align="center",
                    wrap="wrap",
                    width="100%",
                ),
                rx.text(
                    SpectrumState.sp_axis_range,
                    size="1",
                    color="var(--muted)",
                ),
                spacing="3",
                width="100%",
            ),
            width="100%",
        ),
        # ── trace 输入 ──
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.icon("waves", size=18, color="var(--accent)"),
                    rx.heading("Trace 数值", size="2", font_weight="semibold"),
                    rx.spacer(),
                    rx.text(
                        "分隔符任意（空格/逗号/换行）；支持带日志前缀的行，自动取行尾电平",
                        size="1",
                        color="gray",
                    ),
                    spacing="2",
                    width="100%",
                ),
                rx.text_area(
                    value=SpectrumState.sp_trace_text,
                    on_change=SpectrumState.sp_set_trace_text,
                    placeholder="粘贴单条 trace 的全部扫频点数值，例如：-51.5 -52.1 -53.0 …",
                    height="110px",
                    width="100%",
                    font_family="monospace",
                    font_size="12px",
                ),
                rx.hstack(
                    rx.button(
                        rx.icon("chart_spline", size=16),
                        "绘制",
                        on_click=SpectrumState.sp_draw,
                        color_scheme="blue",
                        size="2",
                    ),
                    rx.button(
                        rx.icon("eraser", size=16),
                        "清空",
                        on_click=SpectrumState.sp_clear,
                        variant="outline",
                        color_scheme="gray",
                        size="2",
                    ),
                    rx.button(
                        rx.icon("download", size=16),
                        "导出 PNG",
                        on_click=SpectrumState.sp_export_png,
                        variant="outline",
                        color_scheme="green",
                        size="2",
                    ),
                    rx.spacer(),
                    rx.text(SpectrumState.sp_status, size="1", color="gray"),
                    spacing="3",
                    align="center",
                    width="100%",
                ),
                rx.cond(
                    SpectrumState.sp_error != "",
                    rx.callout(
                        SpectrumState.sp_error,
                        icon="triangle_alert",
                        color_scheme="red",
                        size="1",
                        width="100%",
                    ),
                ),
                rx.cond(
                    SpectrumState.sp_msg != "",
                    rx.text(SpectrumState.sp_msg, size="1", color="var(--accent)"),
                ),
                spacing="2",
                width="100%",
            ),
            width="100%",
        ),
        # ── 画布 + 测量 ──
        rx.hstack(
            rx.card(
                rx.vstack(
                    rx.el.svg(
                        # 网格
                        rx.el.rect(
                            x=spectrum_web.PLOT_X0,
                            y=spectrum_web.PLOT_Y0,
                            width=spectrum_web.PLOT_X1 - spectrum_web.PLOT_X0,
                            height=spectrum_web.PLOT_Y1 - spectrum_web.PLOT_Y0,
                            fill="var(--plot-bg)",
                            stroke="var(--border-strong)",
                            stroke_width="1",
                        ),
                        rx.foreach(
                            SpectrumState.sp_grid_v,
                            lambda g: rx.el.line(
                                x1=g["x"],
                                y1=spectrum_web.PLOT_Y0,
                                x2=g["x"],
                                y2=spectrum_web.PLOT_Y1,
                                stroke="var(--grid)",
                                stroke_width="1",
                            ),
                        ),
                        rx.foreach(
                            SpectrumState.sp_grid_h,
                            lambda g: rx.el.line(
                                x1=spectrum_web.PLOT_X0,
                                y1=g["y"],
                                x2=spectrum_web.PLOT_X1,
                                y2=g["y"],
                                stroke="var(--grid)",
                                stroke_width="1",
                            ),
                        ),
                        # 积分带宽带（画在迹线之下：半透明填充 + 两条点划线边沿）
                        rx.cond(
                            SpectrumState.sp_ibw_rect["w"] != None,
                            rx.el.g(
                                rx.el.rect(
                                    x=SpectrumState.sp_ibw_rect["x"],
                                    y=spectrum_web.PLOT_Y0,
                                    width=SpectrumState.sp_ibw_rect["w"],
                                    height=spectrum_web.PLOT_Y1 - spectrum_web.PLOT_Y0,
                                    fill="var(--accent-soft)",
                                    stroke="none",
                                ),
                                rx.el.line(
                                    x1=SpectrumState.sp_ibw_rect["low_x"],
                                    y1=spectrum_web.PLOT_Y0,
                                    x2=SpectrumState.sp_ibw_rect["low_x"],
                                    y2=spectrum_web.PLOT_Y1,
                                    stroke="var(--accent)",
                                    stroke_width="1",
                                    stroke_dasharray="5 3",
                                ),
                                rx.el.line(
                                    x1=SpectrumState.sp_ibw_rect["high_x"],
                                    y1=spectrum_web.PLOT_Y0,
                                    x2=SpectrumState.sp_ibw_rect["high_x"],
                                    y2=spectrum_web.PLOT_Y1,
                                    stroke="var(--accent)",
                                    stroke_width="1",
                                    stroke_dasharray="5 3",
                                ),
                            ),
                        ),
                        # 迹线（单条 path；越界点已裁到边缘）
                        rx.cond(
                            SpectrumState.sp_polyline != "",
                            rx.el.path(
                                d=SpectrumState.sp_polyline,
                                fill="none",
                                stroke="var(--trace)",
                                stroke_width="1.4",
                            ),
                        ),
                        # 标记（竖虚线 + 圆点 + 标签；颜色与标记表同源）
                        rx.foreach(
                            SpectrumState.sp_markers_svg,
                            lambda m: rx.el.g(
                                rx.el.line(
                                    x1=m["x"],
                                    y1=spectrum_web.PLOT_Y0,
                                    x2=m["x"],
                                    y2=spectrum_web.PLOT_Y1,
                                    stroke=m["color"],
                                    stroke_width="1",
                                    stroke_dasharray="4 3",
                                ),
                                rx.el.circle(
                                    cx=m["x"], cy=m["y"], r="3.6", fill=m["color"]
                                ),
                                rx.el.text(
                                    m["label"],
                                    x=m["x"],
                                    y=spectrum_web.PLOT_Y0 - 6,
                                    fill=m["color"],
                                    font_size="12",
                                    text_anchor="middle",
                                    font_weight="bold",
                                ),
                            ),
                        ),
                        # 参数注记 / 状态行 / 纵轴标签
                        rx.el.text(
                            SpectrumState.sp_params_note,
                            x=spectrum_web.PLOT_X0,
                            y="22",
                            fill="var(--text-2)",
                            font_size="12",
                        ),
                        rx.el.text(
                            SpectrumState.sp_status,
                            x=spectrum_web.PLOT_X0,
                            y=spectrum_web.VIEW_H - 12,
                            fill="var(--muted)",
                            font_size="11",
                        ),
                        rx.foreach(
                            SpectrumState.sp_y_labels,
                            lambda t: rx.el.text(
                                t["text"],
                                x=spectrum_web.PLOT_X0 - 8,
                                y=t["ty"],
                                fill="var(--text-2)",
                                font_size="11",
                                text_anchor="end",
                            ),
                        ),
                        rx.foreach(
                            SpectrumState.sp_x_labels,
                            lambda t: rx.el.text(
                                t["text"],
                                x=t["x"],
                                y=t["ty"],
                                fill="var(--text-2)",
                                font_size="11",
                                text_anchor=t["anchor"],
                            ),
                        ),
                        # 积分带宽短注记（窄画布下不压纵轴刻度）
                        rx.cond(
                            SpectrumState.sp_ibw_short != "",
                            rx.el.text(
                                SpectrumState.sp_ibw_short,
                                x=spectrum_web.PLOT_X1 - 4,
                                y=spectrum_web.PLOT_Y0 + 14,
                                fill="var(--accent-ink)",
                                font_size="11",
                                text_anchor="end",
                            ),
                        ),
                        # 点击带（透明，承载 click）
                        rx.foreach(
                            SpectrumState.sp_bands,
                            lambda b: rx.el.rect(
                                id=b["id"],
                                x=b["x"],
                                y=spectrum_web.PLOT_Y0,
                                width=b["w"],
                                height=spectrum_web.PLOT_Y1 - spectrum_web.PLOT_Y0,
                                fill="transparent",
                                cursor="crosshair",
                                on_click=lambda: SpectrumState.sp_plot_click(
                                    b["index"]
                                ),
                            ),
                        ),
                        id="spectrum-svg",
                        view_box=spectrum_web.view_box(),
                        width="100%",
                        height="min(72vh, 620px)",
                        style={"background": "var(--card)"},
                    ),
                    spacing="2",
                    width="100%",
                ),
                width="62%",
            ),
            rx.vstack(
                rx.card(
                    rx.vstack(
                        rx.heading("测量", size="2", font_weight="semibold"),
                        rx.text(
                            SpectrumState.sp_readout, size="1", color="var(--text)"
                        ),
                        rx.text(SpectrumState.sp_extremes, size="1", color="gray"),
                        rx.text(SpectrumState.sp_delta, size="1", color="var(--text)"),
                        rx.hstack(
                            rx.button(
                                "峰值搜索",
                                on_click=SpectrumState.sp_next_peak,
                                size="1",
                                variant="soft",
                            ),
                            rx.button(
                                "删除标记",
                                on_click=SpectrumState.sp_del_marker,
                                size="1",
                                variant="soft",
                            ),
                            rx.button(
                                "清空标记",
                                on_click=SpectrumState.sp_clear_markers,
                                size="1",
                                variant="soft",
                            ),
                            spacing="2",
                        ),
                        rx.hstack(
                            rx.text("Δ 参考", size="1", color="gray"),
                            rx.el.select(
                                *[
                                    rx.el.option(f"M{i + 1}", value=str(i))
                                    for i in range(6)
                                ],
                                default_value="0",
                                on_change=SpectrumState.sp_set_ref_index,
                                class_name="app-select",
                            ),
                            spacing="2",
                            align="center",
                        ),
                        spacing="2",
                        width="100%",
                    ),
                    width="100%",
                ),
                rx.card(
                    rx.vstack(
                        rx.heading("标记", size="2", font_weight="semibold"),
                        rx.cond(
                            SpectrumState.sp_marker_rows.length() > 0,
                            rx.table.root(
                                rx.table.header(
                                    rx.table.row(
                                        rx.table.column_header_cell("标记"),
                                        rx.table.column_header_cell("频率"),
                                        rx.table.column_header_cell("幅值"),
                                        rx.table.column_header_cell("Δ频率"),
                                        rx.table.column_header_cell("Δ幅值"),
                                    )
                                ),
                                rx.table.body(
                                    rx.foreach(
                                        SpectrumState.sp_marker_rows,
                                        lambda r: rx.table.row(
                                            rx.table.cell(
                                                rx.text(
                                                    r["label"],
                                                    color=r["color"],
                                                    font_weight="bold",
                                                    size="1",
                                                )
                                            ),
                                            rx.table.cell(rx.text(r["freq"], size="1")),
                                            rx.table.cell(
                                                rx.text(r["level"], size="1")
                                            ),
                                            rx.table.cell(
                                                rx.text(r["d_freq"], size="1")
                                            ),
                                            rx.table.cell(
                                                rx.text(r["d_level"], size="1")
                                            ),
                                        ),
                                    )
                                ),
                                variant="surface",
                                size="1",
                                width="100%",
                            ),
                            rx.text(
                                "点击左侧图形即可添加标记（M1~M6，标记吸附到最近数据点）",
                                size="1",
                                color="gray",
                            ),
                        ),
                        spacing="2",
                        width="100%",
                    ),
                    width="100%",
                ),
                rx.card(
                    rx.vstack(
                        rx.hstack(
                            rx.checkbox(
                                "积分带宽",
                                checked=SpectrumState.sp_ibw_show,
                                on_change=lambda v: SpectrumState.sp_set_toggle(
                                    "ibw_show", v
                                ),
                                size="2",
                            ),
                            rx.spacer(),
                            spacing="2",
                            width="100%",
                        ),
                        rx.hstack(
                            _sp_field(
                                "中心",
                                "ibw_center",
                                SpectrumState.sp_ibw_center,
                                "80px",
                            ),
                            _sp_field(
                                "带宽", "ibw_bw", SpectrumState.sp_ibw_bw, "70px"
                            ),
                            rx.el.select(
                                *[
                                    rx.el.option(u, value=u)
                                    for u in ("kHz", "MHz", "GHz")
                                ],
                                value=SpectrumState.sp_ibw_unit,
                                on_change=lambda v: SpectrumState.sp_set_select(
                                    "ibw_unit", v
                                ),
                                class_name="app-select",
                            ),
                            spacing="2",
                            align="center",
                            wrap="wrap",
                        ),
                        rx.text(
                            SpectrumState.sp_ibw_text,
                            size="1",
                            color="var(--accent-ink)",
                        ),
                        spacing="2",
                        width="100%",
                    ),
                    width="100%",
                ),
                spacing="3",
                width="38%",
            ),
            spacing="4",
            width="100%",
            align="start",
        ),
        spacing="4",
        width="100%",
    )


# ═══════════════════════════════════════════════════════════════
# 主页面
# ═══════════════════════════════════════════════════════════════

# 可搜索下拉列表样式（项目未启用 Tailwind，class_name 仅作钩子，样式在此定义）
SEARCHABLE_CSS = """
.searchable-dropdown {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  max-height: 240px;
  overflow-y: auto;
  scrollbar-width: thin;
}
.searchable-dropdown::-webkit-scrollbar { width: 6px; }
.searchable-dropdown::-webkit-scrollbar-track { background: transparent; }
.searchable-dropdown::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 3px; }
.searchable-dropdown::-webkit-scrollbar-thumb:hover { background: var(--muted-2); }
.sd-row {
  display: block;
  width: 100%;
  text-align: left;
  padding: 6px 12px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  color: var(--text);
  transition: background-color 0.1s;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sd-row:hover { background: var(--card-hover); }
.sd-value {
  color: var(--accent);
  font-weight: 600;
  font-family: Consolas, 'Courier New', monospace;
  font-size: 12px;
  min-width: 72px;
  display: inline-block;
  margin-right: 8px;
  vertical-align: middle;
}
.sd-name {
  vertical-align: middle;
}
.sd-empty {
  padding: 10px 12px;
  text-align: center;
  color: var(--muted-2);
  font-size: 13px;
}
"""

GLOBAL_CSS = """
/* ===== 基础 ===== */
body {
  background: var(--bg);
  -webkit-font-smoothing: antialiased;
}
/* 内容容器（占满浏览器宽度；窄屏自动收窄） */
.app-container {
  max-width: 100%;
  margin: 0 auto;
  padding: 20px 28px 64px;
  width: 100%;
  box-sizing: border-box;
}
/* 顶栏容器 */
.app-header-inner {
  max-width: 100%;
  margin: 0 auto;
  padding: 0 28px;
  width: 100%;
  box-sizing: border-box;
}
/* ===== 卡片 ===== */
.rt-Card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  box-shadow: 0 1px 3px var(--shadow), 0 1px 2px var(--shadow);
  padding: 18px 22px;
}
/* 批量摘要：选中行高亮（class 版，见批量面板注释） */
.batch-row-selected {
  border: 2px solid var(--accent) !important;
  background: var(--accent-soft);
}
/* ===== 表格 ===== */
.rt-TableRoot {
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  background: var(--card);
}
.rt-TableRoot .rt-TableColumnHeaderCell {
  background: var(--code-bg);
  color: var(--text-2);
  font-weight: 600;
  font-size: 12px;
  letter-spacing: 0.02em;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.rt-TableRoot .rt-TableCell {
  padding: 8px 14px;
  border-bottom: 1px solid var(--bg);
  font-size: 13px;
  vertical-align: middle;
  /* 所有单元格（含解析值/说明纯文本）自动换行，避免长内容撑爆列宽 */
  white-space: normal;
  word-break: break-all;
  overflow-wrap: anywhere;
}
/* 表格内等宽文本（hex 原始值等）自动换行 */
.rt-TableRoot .rt-TableCell code {
  white-space: normal;
  word-break: break-all;
  overflow-wrap: anywhere;
  max-width: 100%;
}
.rt-TableRoot .rt-TableRow:last-child .rt-TableCell { border-bottom: none; }
.rt-TableRoot .rt-TableRow:hover .rt-TableCell { background: var(--code-bg); }
/* ===== 按钮 ===== */
.rt-Button { border-radius: 8px; font-weight: 600; }
/* ===== 输入框 / 文本域 ===== */
.rt-TextFieldRoot, .rt-TextAreaRoot {
  border-radius: 8px;
  transition: box-shadow 0.15s, border-color 0.15s;
}
.rt-TextFieldRoot:focus-within, .rt-TextAreaRoot:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}
/* ===== 原生 select ===== */
.app-select {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 10px;
  background: var(--card);
  font-size: 13px;
  color: var(--text-2);
  outline: none;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.app-select:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}
/* 顶栏内 select（深色背景） */
.app-header-select {
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.28);
  color: var(--card);
  border-radius: 8px;
  padding: 7px 12px;
  font-size: 13px;
  outline: none;
  cursor: pointer;
  backdrop-filter: blur(4px);
  transition: background 0.15s;
}
.app-header-select:hover { background: rgba(255, 255, 255, 0.22); }
.app-header-select option { color: var(--text); background: var(--card); }
.app-header-btn {
  background: rgba(255, 255, 255, 0.15);
  color: white;
  border: 1px solid rgba(255, 255, 255, 0.25);
  border-radius: 8px;
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  /* 板块文字永不折行 + 不被压缩：标题栏保持单行恒定高度，
     窄屏时由 flex 压缩可收缩项（协议选择器）而非换行 */
  white-space: nowrap;
  flex-shrink: 0;
  transition: background 0.15s;
}
.app-header-btn:hover { background: rgba(255, 255, 255, 0.25); }
/* ===== Tab 导航 ===== */
.app-tabbar {
  display: flex;
  gap: 2px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 18px;
  background: var(--card);
  border-radius: 12px 12px 0 0;
  box-shadow: 0 1px 3px var(--shadow);
  /* 仅横向滚动（窄屏时）；纵向必须 hidden —— overflow-x:auto 会让
     overflow-y 的 visible 变 auto，Tab 按钮高度略超容器时右侧
     会出现一条无意义的垂直滚动条 */
  overflow-x: auto;
  overflow-y: hidden;
  align-items: stretch;
  padding: 0 8px;
}
.app-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: none;
  background: transparent;
  padding: 12px 16px;
  font-size: 14px;
  color: var(--muted);
  cursor: pointer;
  font-weight: 500;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  white-space: nowrap;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}
.app-tab:hover { color: var(--accent); background: var(--bg); }
.app-tab-active {
  color: var(--accent);
  border-bottom-color: var(--accent);
  font-weight: 600;
  background: var(--accent-soft);
}
.app-tab svg { width: 16px; height: 16px; flex-shrink: 0; }
/* ===== 消息条 ===== */
.rt-Callout { border-radius: 10px; }
/* ===== 全局滚动条 ===== */
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: var(--muted-2); }
::-webkit-scrollbar-track { background: transparent; }
"""

# 全局设计系统：页面背景/容器/卡片/表格/按钮/输入控件/Tab 导航
# 项目未启用 Tailwind，Radix 组件通过 .rt-* 类覆盖，自定义类直接定义


def tool_page() -> rx.Component:
    """在线工具页（原主页，1.23.14 起让位给产品首页，路由改为 /app）"""
    return rx.theme(
        rx.box(
            theme_style(),
            header(),
            rx.box(
                newgen_controls(),
                message_banner(),
                # Tab 导航
                rx.hstack(
                    rx.el.button(
                        rx.hstack(
                            rx.icon("file_input", size=16), "单帧解析", spacing="1"
                        ),
                        on_click=lambda: State.set_tab("single"),
                        class_name=rx.cond(
                            State.active_tab == "single",
                            "app-tab app-tab-active",
                            "app-tab",
                        ),
                        data_testid="tab-single",
                    ),
                    rx.el.button(
                        rx.hstack(rx.icon("list", size=16), "批量解析", spacing="1"),
                        on_click=lambda: State.set_tab("batch"),
                        class_name=rx.cond(
                            State.active_tab == "batch",
                            "app-tab app-tab-active",
                            "app-tab",
                        ),
                        data_testid="tab-batch",
                    ),
                    rx.el.button(
                        rx.hstack(
                            rx.icon("square_pen", size=16), "协议组帧", spacing="1"
                        ),
                        on_click=lambda: State.set_tab("frame"),
                        class_name=rx.cond(
                            State.active_tab == "frame",
                            "app-tab app-tab-active",
                            "app-tab",
                        ),
                        data_testid="tab-frame",
                    ),
                    rx.el.button(
                        rx.hstack(
                            rx.icon("git_compare", size=16), "报文对比", spacing="1"
                        ),
                        on_click=lambda: State.set_tab("diff"),
                        class_name=rx.cond(
                            State.active_tab == "diff",
                            "app-tab app-tab-active",
                            "app-tab",
                        ),
                        data_testid="tab-diff",
                    ),
                    rx.el.button(
                        rx.hstack(rx.icon("search", size=16), "查询", spacing="1"),
                        on_click=lambda: State.set_tab("lookup"),
                        class_name=rx.cond(
                            State.active_tab == "lookup",
                            "app-tab app-tab-active",
                            "app-tab",
                        ),
                        data_testid="tab-lookup",
                    ),
                    # 频谱图（常驻，与协议无关；状态在 SpectrumState）
                    rx.el.button(
                        rx.hstack(
                            rx.icon("chart_spline", size=16), "频谱图", spacing="1"
                        ),
                        on_click=lambda: State.set_tab("spectrum"),
                        class_name=rx.cond(
                            State.active_tab == "spectrum",
                            "app-tab app-tab-active",
                            "app-tab",
                        ),
                        data_testid="tab-spectrum",
                    ),
                    rx.el.button(
                        rx.hstack(rx.icon("wrench", size=16), "报文工具", spacing="1"),
                        on_click=lambda: State.set_tab("tool"),
                        class_name=rx.cond(
                            State.active_tab == "tool",
                            "app-tab app-tab-active",
                            "app-tab",
                        ),
                        data_testid="tab-tool",
                    ),
                    rx.el.button(
                        rx.hstack(
                            rx.icon("download", size=16), "客户端下载", spacing="1"
                        ),
                        on_click=lambda: State.set_tab("download"),
                        class_name=rx.cond(
                            State.active_tab == "download",
                            "app-tab app-tab-active",
                            "app-tab",
                        ),
                        data_testid="tab-download",
                    ),
                    # 发布管理 tab（仅登录后显示）
                    rx.cond(
                        State.admin_logged_in,
                        rx.el.button(
                            rx.hstack(
                                rx.icon("rocket", size=16), "发布管理", spacing="1"
                            ),
                            on_click=lambda: State.set_tab("release"),
                            class_name=rx.cond(
                                State.active_tab == "release",
                                "app-tab app-tab-active",
                                "app-tab",
                            ),
                            data_testid="tab-release",
                        ),
                    ),
                    # 问题反馈列表 tab（所有人可见；管理操作仅登录后）
                    # on_click 事件链：主 State 切 tab + FeedbackState 拉取列表 ——
                    # Reflex 中各 State 的 delta 随各自事件推送，主 State 事件内
                    # 直接改 FeedbackState 前端收不到，故必须双事件触发
                    rx.el.button(
                        rx.hstack(
                            rx.icon("message_square_heart", size=16),
                            "问题反馈",
                            spacing="1",
                        ),
                        on_click=[
                            lambda: State.set_tab("feedback"),
                            FeedbackState.fa_load,
                        ],
                        class_name=rx.cond(
                            State.active_tab == "feedback",
                            "app-tab app-tab-active",
                            "app-tab",
                        ),
                        data_testid="tab-feedback",
                    ),
                    class_name="app-tabbar",
                    width="100%",
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
                                    rx.cond(
                                        State.active_tab == "download",
                                        download_tab(),
                                        rx.cond(
                                            State.active_tab == "feedback",
                                            feedback_list_tab(),
                                            rx.cond(
                                                State.active_tab == "release",
                                                release_tab(),
                                                rx.cond(
                                                    State.active_tab == "spectrum",
                                                    spectrum_tab(),
                                                    lookup_tab(),
                                                ),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
                class_name="app-container",
                width="100%",
            ),
            # 管理员登录对话框
            admin_login_dialog(),
            # 分享此帧弹窗（单帧解析结果区按钮触发）
            _share_submit_dialog(),
            background="var(--bg)",
            min_height="100vh",
            class_name=ThemeState.root_class,
            data_testid="tool-root",
        ),
        # Radix 主题包裹：模式交给 html.light/.dark 类（appearance=inherit），
        # 强调色/灰阶/圆角由 ThemeState 驱动 → Radix 组件随之换色
        appearance="inherit",
        accent_color=ThemeState.accent,
        gray_color=ThemeState.gray,
        radius=ThemeState.radius,
    )


# ═══════════════════════════════════════════════════════════════
# 应用入口
# ═══════════════════════════════════════════════════════════════


def landing_page() -> rx.Component:
    """产品首页（落地页）：介绍桌面客户端 + 在线工具入口。

    页面内容与组件在 `landing_web.py`（纯展示、不依赖 State）；此处只做两件事：
    把 `State` 的运行时值注入进去，以及套上工具页同一套主题（token + 强调色作用域）。
    """
    return rx.theme(
        rx.box(
            theme_style(),
            landing_web.landing_page(
                version=State.download_version,
                version_date=State.download_version_date,
                exe_name=State.download_exe_name,
                exe_size_mb=State.download_exe_size_mb,
                exe_available=State.download_exe_available,
                image_src=State.download_image_data_url,
                image_available=State.download_image_available,
                on_download=State.download_client,
                theme_controls=theme_controls_compact(),
            ),
            background="var(--bg)",
            min_height="100vh",
            class_name=ThemeState.root_class,
        ),
        # Radix 主题包裹（与工具页一致）：模式交给 html.light/.dark 类
        appearance="inherit",
        accent_color=ThemeState.accent,
        gray_color=ThemeState.gray,
        radius=ThemeState.radius,
    )


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

app.add_page(
    landing_page,
    route="/",
    title="多协议解析平台 - 电力通信协议解析与调试工具",
    description="支持南网、国网、DLT645、698.45、新一代载波与双模互联互通等 12 种电力通信协议的解析、校验、组帧、串口监控与 TCP 抓包调试工具。",
    # 读回浏览器本地主题（模式 + 外观）+ 拉取 downloads/ 实况（版本/体积/截图）
    on_load=[ThemeState.theme_boot, State.load_download_info],
)
app.add_page(
    tool_page,
    route="/app",
    title="在线工具 - 多协议解析平台",
    # 读回浏览器本地主题（模式 + 外观）并即时应用
    on_load=ThemeState.theme_boot,
)
app.add_page(
    feedback_page,
    route="/feedback",
    title="问题反馈 - 多协议解析平台",
    on_load=ThemeState.theme_boot,
)
app.add_page(
    feedback_admin_page,
    route="/feedback-admin",
    title="反馈管理 - 多协议解析平台",
    on_load=ThemeState.theme_boot,
)
app.add_page(
    share_page,
    route="/share",
    title="报文分享 - 多协议解析平台",
    # 页面首次加载：读回本地主题 + 拉取分享列表（缺了 sh_load 列表永远为空）
    on_load=[ThemeState.theme_boot, ShareState.sh_load],
)


# ═══════════════════════════════════════════════════════════════
# 开发模式下载路由（生产模式由 run_app.py 的 ASGI 中间件提供）
# ═══════════════════════════════════════════════════════════════


def _get_downloads_dir() -> Path:
    """发布产物目录（由 `app_data` 统一决定；部署态在部署目录之外）。"""
    return app_data.downloads_dir()


async def _dev_download_handler(request):
    """Starlette 路由：开发模式下提供 /download/ 静态文件

    生产模式（run_app.py）由 ASGI 中间件 _serve_download 提供。
    """
    import mimetypes
    from urllib.parse import unquote

    from starlette.responses import FileResponse, PlainTextResponse

    path = request.path_params.get("path", "")
    filename = unquote(path)

    # 防目录穿越
    if not filename or ".." in filename or filename.startswith("/") or "\\" in filename:
        return PlainTextResponse("Invalid filename", status_code=404)

    # archive/ 历史版本归档目录不对外公开
    if filename.startswith("archive/") or filename == "archive":
        return PlainTextResponse("Forbidden", status_code=403)

    # 只允许文件名（不允许子目录）—— 但支持 archive/ 前缀已被禁
    # 这里再做一次路径规范化校验
    downloads_dir = _get_downloads_dir()
    file_path = (downloads_dir / filename).resolve()
    try:
        file_path.relative_to(downloads_dir.resolve())
    except ValueError:
        return PlainTextResponse("Invalid filename", status_code=404)

    if not file_path.exists() or not file_path.is_file():
        return PlainTextResponse(f"File not found: {filename}", status_code=404)

    mime, _ = mimetypes.guess_type(str(file_path))
    content_type = mime or "application/octet-stream"

    # exe 强制下载
    if file_path.suffix.lower() == ".exe":
        from urllib.parse import quote

        ascii_name = file_path.name.encode("ascii", "ignore").decode("ascii")
        if ascii_name == file_path.name:
            disp = f'attachment; filename="{file_path.name}"'
        else:
            disp = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(file_path.name)}"
        return FileResponse(
            str(file_path),
            media_type="application/octet-stream",
            filename=file_path.name,
            headers={"Content-Disposition": disp},
        )

    return FileResponse(str(file_path), media_type=content_type)


# 注册到 Reflex 的 Starlette 后端（开发模式生效）
# 同时注册 /download/ 和 /api/download/：
#   /download/       —— 生产模式（run_app.py 中间件）直连
#   /api/download/   —— 开发模式 Vite 会把 /api/* 代理到后端
from starlette.routing import Route

app._api.routes.insert(
    0, Route("/download/{path:path}", _dev_download_handler, methods=["GET"])
)
app._api.routes.insert(
    0, Route("/api/download/{path:path}", _dev_download_handler, methods=["GET"])
)


def _get_fbimg_dir() -> Path:
    """反馈截图目录 `<数据根>/data/uploads/feedback/`（由 `app_data` 统一决定）。"""
    return app_data.uploads_dir()


async def _dev_fbimg_handler(request):
    """Starlette 路由：开发模式下提供 /fbimg/ 反馈截图

    生产模式（run_app.py）由 ASGI 中间件 _serve_fbimg 提供。
    """
    import mimetypes
    from urllib.parse import unquote

    from starlette.responses import FileResponse, PlainTextResponse

    path = request.path_params.get("path", "")
    filename = unquote(path)

    # 防目录穿越：仅允许纯文件名
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        return PlainTextResponse("Invalid filename", status_code=404)

    fb_dir = _get_fbimg_dir().resolve()
    file_path = (fb_dir / filename).resolve()
    try:
        file_path.relative_to(fb_dir)
    except ValueError:
        return PlainTextResponse("Invalid filename", status_code=404)

    if not file_path.exists() or not file_path.is_file():
        return PlainTextResponse("File not found", status_code=404)

    mime, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(str(file_path), media_type=mime or "application/octet-stream")


app._api.routes.insert(
    0, Route("/fbimg/{path:path}", _dev_fbimg_handler, methods=["GET"])
)
app._api.routes.insert(
    0, Route("/api/fbimg/{path:path}", _dev_fbimg_handler, methods=["GET"])
)


# ═══════════════════════════════════════════════════════════════
# 反馈提交 HTTP API（GUI 客户端等外部调用，dev 模式路由；
# 生产模式由 run_app.py 中间件提供同名 /api/feedback 分支）
# ═══════════════════════════════════════════════════════════════

# 简单滑动窗口频率限制：{ip: [timestamps]}，60 秒内最多 5 条
_FEEDBACK_RATE: dict = {}
_FEEDBACK_RATE_WINDOW = 60.0
_FEEDBACK_RATE_MAX = 5


def _feedback_rate_check(ip: str) -> bool:
    """True=允许提交；False=超频（60s 窗口内第 6 条起拒绝）。"""
    import time as _time

    now = _time.time()
    bucket = [t for t in _FEEDBACK_RATE.get(ip, []) if now - t < _FEEDBACK_RATE_WINDOW]
    if len(bucket) >= _FEEDBACK_RATE_MAX:
        _FEEDBACK_RATE[ip] = bucket
        return False
    bucket.append(now)
    _FEEDBACK_RATE[ip] = bucket
    return True


def _feedback_json_response(payload: dict, status: int = 200, request=None):
    """JSON 响应（CORS 反射 Origin；GUI Qt 网络栈不校验 CORS，浏览器调试需要）。

    反射 Origin 而非通配 *：接口无凭据（无 cookie/登录态），任意源反射
    等价于 * 且通过 no-wildcard-cors 规则；无 Origin（Qt/curl）时不带头。
    """
    import json as _json

    from starlette.responses import Response

    headers = {}
    origin = request.headers.get("origin") if request is not None else ""
    if origin:
        headers["Access-Control-Allow-Origin"] = origin
    return Response(
        content=_json.dumps(payload, ensure_ascii=False),
        status_code=status,
        media_type="application/json; charset=utf-8",
        headers=headers,
    )


async def _dev_feedback_api_handler(request):
    """Starlette 路由：POST /api/feedback（dev 模式）。

    生产模式（run_app.py）由 ASGI 中间件 _handle_feedback_api 提供，
    两者共用 feedback_model.submit_from_api 纯逻辑。
    """
    from . import feedback_model as fm

    if request.method == "OPTIONS":
        return _feedback_json_response({}, 204, request)

    ip = request.client.host if request.client else "unknown"
    if not _feedback_rate_check(ip):
        return _feedback_json_response(
            {"ok": False, "error": "提交过于频繁，请稍后再试"}, 429, request
        )

    try:
        form = await request.form()
    except Exception as e:
        return _feedback_json_response(
            {"ok": False, "error": f"请求体解析失败: {e}"}, 400, request
        )

    fields = {
        "issue_type": form.get("issue_type", ""),
        "protocol": form.get("protocol", ""),
        "description": form.get("description", ""),
        "contact": form.get("contact", ""),
        "sys_info": form.get("sys_info", ""),
        "source": form.get("source", "gui"),
    }
    files = []
    for key in ("screenshots", "screenshot"):
        for up in form.getlist(key):
            data = await up.read()
            name = getattr(up, "filename", None) or "shot.png"
            files.append((name, data))

    ok, result, status = fm.submit_from_api(fields, files)
    if ok:
        return _feedback_json_response({"ok": True, "id": int(result)}, status, request)
    return _feedback_json_response({"ok": False, "error": str(result)}, status, request)


async def _dev_feedback_config_handler(request):
    """GET /api/feedback/config：GUI 拉取字段约束（失败不阻塞 GUI 提交）。"""
    from . import feedback_model as fm

    return _feedback_json_response(
        {
            "ok": True,
            "issue_types": fm.ISSUE_TYPES,
            "max_desc_len": fm.MAX_DESC_LEN,
            "max_contact_len": fm.MAX_CONTACT_LEN,
            "max_screenshots": fm.MAX_SCREENSHOTS,
            "max_size_mb": fm.MAX_SCREENSHOT_SIZE // (1024 * 1024),
        }
    )


from starlette.routing import Route as _FbRoute

app._api.routes.insert(
    0,
    _FbRoute(
        "/api/feedback",
        _dev_feedback_api_handler,
        methods=["POST", "OPTIONS"],
    ),
)
app._api.routes.insert(
    0, _FbRoute("/api/feedback/config", _dev_feedback_config_handler, methods=["GET"])
)


# ═══════════════════════════════════════════════════════════════
# 报文分享 HTTP API（GUI 客户端等外部调用，dev 模式路由；
# 生产模式由 run_app.py 中间件提供同名 /api/frameshare 分支）
# ═══════════════════════════════════════════════════════════════

# 滑动窗口频率限制：60 秒内同 IP 最多 10 条（分享比反馈高频，放宽）
_SHARE_RATE: dict = {}
_SHARE_RATE_WINDOW = 60.0
_SHARE_RATE_MAX = 10


def _share_rate_check(ip: str) -> bool:
    import time as _time

    now = _time.time()
    bucket = [t for t in _SHARE_RATE.get(ip, []) if now - t < _SHARE_RATE_WINDOW]
    if len(bucket) >= _SHARE_RATE_MAX:
        _SHARE_RATE[ip] = bucket
        return False
    bucket.append(now)
    _SHARE_RATE[ip] = bucket
    return True


async def _dev_frameshare_api_handler(request):
    """POST /api/frameshare（dev 模式，JSON body）。

    生产模式（run_app.py）由 ASGI 中间件 _handle_frameshare_api 提供，
    两者共用 share_model.submit_share 纯逻辑。
    """
    import json as _json

    from . import share_model as sm

    if request.method == "OPTIONS":
        return _feedback_json_response({}, 204, request)

    ip = request.client.host if request.client else "unknown"
    if not _share_rate_check(ip):
        return _feedback_json_response(
            {"ok": False, "error": "分享过于频繁，请稍后再试"}, 429, request
        )

    try:
        body = await request.body()
        if len(body) > 64 * 1024:
            return _feedback_json_response(
                {"ok": False, "error": "请求体过大"}, 413, request
            )
        fields = _json.loads(body.decode("utf-8"))
        if not isinstance(fields, dict):
            return _feedback_json_response(
                {"ok": False, "error": "JSON 对象格式错误"}, 400, request
            )
    except _json.JSONDecodeError:
        return _feedback_json_response(
            {"ok": False, "error": "JSON 解析失败"}, 400, request
        )
    except Exception as e:
        return _feedback_json_response(
            {"ok": False, "error": f"请求体读取失败: {e}"}, 400, request
        )

    ok, result, status = sm.submit_share(fields)
    if ok:
        # 分享页 URL：dev 前后端分端口（页面在前端端口），prod 单端口同源。
        # GUI 成功后用此 URL 开浏览器，不能用 API 地址直接拼 /share。
        import os as _os

        mounted = _os.environ.get("__REFLEX_MOUNT_FRONTEND_COMPILED_APP") == "true"
        frontend_port = None
        if not mounted:
            import reflex as _rx

            frontend_port = getattr(_rx.config.get_config(), "frontend_port", None)
        share_url = sm.share_page_url(
            request.headers.get("host", ""),
            request.url.scheme,
            frontend_port,
            mounted,
        )
        return _feedback_json_response(
            {"ok": True, "id": int(result), "share_url": share_url},
            status,
            request,
        )
    return _feedback_json_response({"ok": False, "error": str(result)}, status, request)


async def _dev_frameshare_config_handler(request):
    """GET /api/frameshare/config：GUI 拉取字段约束。"""
    from . import share_model as sm

    return _feedback_json_response(sm.share_config())


app._api.routes.insert(
    0,
    _FbRoute(
        "/api/frameshare",
        _dev_frameshare_api_handler,
        methods=["POST", "OPTIONS"],
    ),
)
app._api.routes.insert(
    0,
    _FbRoute("/api/frameshare/config", _dev_frameshare_config_handler, methods=["GET"]),
)
