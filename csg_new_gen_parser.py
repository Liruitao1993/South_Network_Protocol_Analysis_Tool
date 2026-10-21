"""
新一代载波协议解析器 (通感一体化低压电力线宽带载波通信规约)
CSG New Generation Protocol Parser

协议文档: 通感一体化低压电力线宽带载波通信规约
- 第4部分: 数据链路层通信协议 (MAC/MSDU 帧格式)
- 第5部分: 应用层通信协议 (业务报文结构)

帧结构层次:
  物理层 → MPDU → MAC帧(12/32字节头 + MSDU + CRC-32)
  MAC帧内部: MSDU头(VLAN标签 + MSDU类型) + 应用层业务报文
  应用层: 报文端口号 + 报文标识符 + 控制域 + 业务标识 + 帧序号 + 帧长 + 数据单元
"""
from typing import Dict, List, Tuple, Any, Optional
import struct
import crcmod
from csg_new_gen_cmd_payloads import parse_command_payload

# ── CRC 算法（基于协议规范）──
_crc24_func = crcmod.mkCrcFun(0x1800063, initCrc=0x000000, rev=True, xorOut=0x000000)
_crc32_func = crcmod.mkCrcFun(0x104C11DB7, initCrc=0x00000000, rev=True, xorOut=0xffffffff)

# ── ED..EE 监控包装（PLC2.0 台体 / 广西台体）──
# 两种包装的数据域公共头布局不同：
#   plc2 = 9 字节：物理信道(1)+时间戳(4)+物理块个数(1)+Payload CRC(1)+物理块长度(2)
#   gx   = 8 字节：时间戳(4)+物理信道(1)+物理块个数(1)+物理块长度(2)（无 Payload CRC）
# 常用物理块尺寸（与帧长一致性推断同口径）
_ED_PB_SIZES = (16, 40, 72, 136, 264, 520)

# (包装名, 数据域公共头长度, 物理块长度字段在数据域内的偏移)
_ED_WRAPPERS = (("plc2", 9, 7), ("gx", 8, 6))


def detect_ed_wrapper(frame_bytes: bytes, fallback: str = "plc2") -> str:
    """判别 ED..EE 监控包装格式：plc2(9B 公共头) / gx(8B 公共头)。

    逐候选格式打分（平局优先 plc2，无正分回退 fallback）：
      +2 剥头后业务帧首字节符合 FC MPDU 特征（bit3 接入指示=1 且 bits0-2 定界符 0~3）
      +1 物理块长度字段（小端）与业务长度自洽：
         (业务长度-16) 为 pb_len 正整数倍且倍数≤5、pb_len 属常用物理块尺寸；
         无业务域（控制报文等）时仅看 pb_len 是否属常用尺寸
    单一实现：桌面 main_gui._detect_ed_wrapper 委托本函数（手动下拉值作 fallback）。
    """
    if not fallback or fallback == "auto":
        fallback = "plc2"
    n = len(frame_bytes)
    if n < 8 or frame_bytes[0] != 0xED:
        return fallback
    frame_len = frame_bytes[1] | (frame_bytes[2] << 8)
    if frame_len < 4 or frame_len > 4096:
        return fallback
    total = frame_len + 4
    if total > n or frame_bytes[5] != 0xEF or frame_bytes[total - 1] != 0xEE:
        return fallback
    data = frame_bytes[6:6 + frame_len - 4]
    best, best_score = None, 0
    for wrapper, hdr_len, pb_off in _ED_WRAPPERS:
        if len(data) < hdr_len:
            continue
        business = data[hdr_len:]
        score = 0
        pb_len = int.from_bytes(data[pb_off:pb_off + 2], "little")
        if business:
            fc = business[0]
            if (fc & 0x08) and (fc & 0x07) <= 3:
                score += 2
            if pb_len in _ED_PB_SIZES:
                rest = len(business) - 16
                if 0 < rest <= pb_len * 5 and rest % pb_len == 0:
                    score += 1
        elif pb_len in _ED_PB_SIZES:
            score += 1
        if score > best_score:
            best, best_score = wrapper, score
    if best is None or best_score <= 0:
        return fallback
    return best


# ── 常量定义 ──

# 报文端口号
MSG_PORT_MAP = {
    0x11: "业务报文(转发)",
    0x13: "管理报文(模块)",
}

# 报文标识符
MSG_ID_MAP = {
    0x0101: "CCO-STA应用层报文",
}

# 帧类型域 (控制域低4位)
FRAME_TYPE_MAP = {
    0x0: "确认/否认",
    0x1: "数据传输帧",
    0x2: "命令帧",
    0x3: "主动上报帧",
    0x4: "抄控器相关协议",
    0x5: "广播命令帧",
    0x6: "数据订阅路由帧",
    0xE: "厂家调试",
}

# 传输方向位 (D15)
DIRECTION_MAP = {
    0: "下行(CCO→STA)",
    1: "上行(STA→CCO)",
}

# 启动标志位 (D14) - PRM
PRM_MAP = {
    0: "来自从动站",
    1: "来自启动站",
}

# 响应标识位 (D13)
RESPONSE_MAP = {
    0: "不需要应答",
    1: "需要应答",
}

# 业务扩展域标识位 (D12)
EXTENSION_MAP = {
    0: "无业务扩展域",
    1: "有业务扩展域",
}

# 业务标识 (根据帧类型不同而不同)
# ── 确认/否认
CONFIRM_SERVICE_MAP = {
    0x00: "确认",
    0x01: "否认",
}

# ── 数据传输
DATA_SERVICE_MAP = {
    0x00: "数据透传至设备",
    0x01: "数据透传至模块",
    0x02: "并发抄读端设备",
    0x03: "站点间通信",
}

# ── 命令帧 (功能性业务)
CMD_FUNC_SERVICE_MAP = {
    0x02: "文件传输",
    0x03: "允许/禁止从节点事件",
}

# ── 命令帧 (通信管理业务)
CMD_COMM_SERVICE_MAP = {
    0x00: "查询终端搜索结果",
    0x01: "下发搜索终端列表",
    0x04: "从节点重启",
    0x05: "从节点信息查询",
    0x06: "下发通信地址映射表列表",
    0x07: "查询从节点运行状态信息",
    0x08: "查询从节点信道信息",
    0x09: "查询模块运行参数",
    0x10: "台区户变关系/相位识别",
    0xF0: "测试帧",
}

# 获取业务标识描述
def get_service_desc(frame_type: int, service_id: int, msg_port: int) -> str:
    """根据帧类型、业务标识和报文端口号获取描述"""
    if frame_type == 0x0:  # 确认/否认
        return CONFIRM_SERVICE_MAP.get(service_id, f"保留(0x{service_id:02X})")
    elif frame_type == 0x1:  # 数据传输
        return DATA_SERVICE_MAP.get(service_id, f"保留(0x{service_id:02X})")
    elif frame_type == 0x2:  # 命令帧
        if msg_port == 0x11:
            if service_id in CMD_FUNC_SERVICE_MAP:
                return CMD_FUNC_SERVICE_MAP[service_id]
            return CMD_COMM_SERVICE_MAP.get(service_id, f"保留(0x{service_id:02X})")
        elif msg_port == 0x13:
            return CMD_COMM_SERVICE_MAP.get(service_id, f"保留(0x{service_id:02X})")
        else:
            return f"保留(0x{service_id:02X})"
    elif frame_type == 0x3:  # 主动上报
        return f"上报类型(0x{service_id:02X})"
    elif frame_type == 0x4:  # 抄控器
        return f"抄控器命令(0x{service_id:02X})"
    elif frame_type == 0x5:  # 广播命令
        return f"广播命令(0x{service_id:02X})"
    elif frame_type == 0x6:  # 数据订阅路由
        return f"数据订阅路由(0x{service_id:02X})"
    else:
        return f"未知(0x{service_id:02X})"


# MSDU 类型
MSDU_TYPE_MAP = {
    0x00: "保留",
    0x01: "应用层报文",
    0x02: "无线发现列表消息",
    0x80: "IPV4报文",
    0x88E1: "网络管理消息",
}

# MAC 帧头类型
MAC_HEADER_TYPE_MAP = {
    0: "32字节长帧头",
    1: "12字节短帧头",
}

# 版本
MAC_VERSION_MAP = {
    0: "保留",
    1: "标准帧协议",
    2: "单跳帧协议",
    3: "保留",
}

# MPDU标准版本号
MPDU_VERSION_MAP = {0: "保留", 1: "BPLC版本", 2: "ISAC-PLC版本"}

# 发送类型
SEND_TYPE_MAP = {
    0: "单播(需确认)",
    1: "全网广播(不确认)",
    2: "本地广播(不确认)",
    3: "全网广播(需确认)",
    4: "本地广播(需确认)",
}

# 广播方向
BROADCAST_DIR_MAP = {
    0: "保留",
    1: "下行广播(CCO→STA)",
    2: "上行广播(STA→CCO)",
}


def is_test_device_control_frame(data) -> bool:
    """``data`` 是否可识别为「测试装置（工装板 / 功能驱动板）通信控制帧」。

    入参**同时接受** ``bytes`` 与**纯 hex 字符串**（前缀剥离层手上是 str，解析层是 bytes；
    字符串容忍空格等分隔符 —— 即 ``bytes.fromhex`` 语义），非法入参返回 ``False`` 而不抛异常。

    用途：批量解析的**前缀剥离层**据此决定「整行原样保留」。这类帧（``FE×n + 05 地址
    命令 6字节数据 校验``，功能驱动板以 ``AA 0D 0A`` 结尾）不是载波 FC/PB 业务帧、没有
    FC 起始签名，若不特判就会被 FC 扫描分支整行丢弃 —— 实测表现为「同一帧单帧解析正常，
    批量却提示『预处理后未保留有效报文内容！』」。

    判据**复用** :meth:`CSGNewGenParser._parse_test_device_control`（帧格式的单一来源），
    调用点（``batch_core`` / ``main_gui`` / Web ``web_utils``）**禁止**另写一份帧格式判据
    （AGENTS.md 陷阱 31 的漂移根因）。
    """
    try:
        raw = bytes.fromhex(data) if isinstance(data, str) else bytes(data)
    except (TypeError, ValueError):
        return False
    try:
        return CSGNewGenParser()._parse_test_device_control(raw) is not None
    except Exception:  # noqa: BLE001 - 判据函数不得把异常抛给调用方
        return False


class CSGNewGenParser:
    """新一代载波协议解析器 (通感一体化)"""

    # 协议信息
    PROTOCOL_NAME = "新一代载波协议 (通感一体化)"
    PROTOCOL_VERSION = "1.0"

    # 测试装置工装板控制协议（《通信控制协议V1.1》，可能封装在 ED..EE 数据域中）
    TEST_DEVICE_CMD_NAMES = {
        0x01: "设置印制板控制单元地址",
        0x02: "模块上下电/8762A连接方式",
        0x03: "设置引脚状态/衰减器A",
        0x04: "设置220V电源/衰减器B",
        0x05: "衰减器C",
    }
    TEST_DEVICE_CCO_MODULE_NAMES = {
        0x01: "三相表模块",
        0x02: "CCO2模块",
        0x03: "CCO1模块",
        0x04: "STA2模块",
        0x05: "STA1模块",
        0x06: "STA3模块",
    }

    # ── 公共工具函数 ──

    @staticmethod
    def _mac_addr(data: bytes, offset: int) -> Tuple[str, str]:
        """解析 6 字节 MAC/地址：返回 (原始十六进制空格分隔, 冒号分隔)."""
        if offset + 6 > len(data):
            return "", ""
        addr_bytes = data[offset:offset + 6]
        raw_hex = ' '.join(f'{b:02X}' for b in addr_bytes)
        colon_hex = ':'.join(f'{b:02X}' for b in addr_bytes)
        return raw_hex, colon_hex

    @staticmethod
    def _bcd_datetime(data: bytes, offset: int) -> Tuple[str, str]:
        """解析 6 字节 BCD 时间 YYMMDDhhmmss（低字节在前），返回 (原始十六进制, 格式化字符串)."""
        if offset + 6 > len(data):
            return "", ""
        raw_bytes = data[offset:offset + 6]
        raw_hex = ' '.join(f'{b:02X}' for b in raw_bytes)
        # 传输顺序低字节在前，但 BCD 每个字节两位数字，显示时按传输顺序反转后读取
        # 规范：秒在低位 => 传输顺序为 ss mm hh DD MM YY（低字节在前）
        dt = raw_bytes[::-1]  # 反转后按 YY MM DD hh mm ss 解析
        bcd = ''.join(f'{b:02X}' for b in dt)
        if len(bcd) == 12 and all(c in '0123456789' for c in bcd):
            parsed = f"20{bcd[0:2]}-{bcd[2:4]}-{bcd[4:6]} {bcd[6:8]}:{bcd[8:10]}:{bcd[10:12]}"
        else:
            parsed = f"非标准BCD: {raw_hex}"
        return raw_hex, parsed

    @staticmethod
    def _uint16_le(data: bytes, offset: int) -> int:
        """读取 2 字节小端序无符号整数。"""
        if offset + 2 > len(data):
            return 0
        return int.from_bytes(data[offset:offset + 2], 'little')

    @staticmethod
    def _uint32_le(data: bytes, offset: int) -> int:
        """读取 4 字节小端序无符号整数。"""
        if offset + 4 > len(data):
            return 0
        return int.from_bytes(data[offset:offset + 4], 'little')

    @staticmethod
    def _bit_field(value: int, start: int, end: int) -> int:
        """提取 value 的 [start, end] 位（含，0-based LSB）。"""
        mask = (1 << (end - start + 1)) - 1
        return (value >> start) & mask

    @staticmethod
    def _hex_space(data: bytes) -> str:
        return " ".join(f"{b:02X}" for b in data)

    def _parse_test_device_control(self, data: bytes, base_offset: int = 0) -> Optional[list]:
        """解析测试装置工装板控制协议。"""
        if not data or data[0] not in (0x05, 0xFE):
            return None

        pos = 0
        while pos < len(data) and data[pos] == 0xFE:
            pos += 1
        if pos >= len(data) or data[pos] != 0x05 or pos > 4:
            return None

        if pos + 13 == len(data) and data[pos + 10:pos + 13] == b"\xAA\x0D\x0A":
            checksum = data[pos + 9]
            calc_checksum = sum(data[pos + 1:pos + 9]) & 0xFF
            address = data[pos + 1]
            command = data[pos + 2]
            if (address in (0x00, 0x01)
                    and checksum == calc_checksum
                    and self._is_valid_function_board_payload(command, data[pos + 3:pos + 9])):
                return self._build_test_device_rows(
                    data[pos:pos + 13], base_offset + pos, "function")

        if pos + 10 == len(data):
            checksum = data[pos + 9]
            calc_checksum = sum(data[pos + 1:pos + 9]) & 0xFF
            address = data[pos + 1]
            command = data[pos + 2]
            if (address in (0x00, 0x01)
                    and checksum == calc_checksum
                    and self._is_valid_fixture_board_payload(command, data[pos + 3:pos + 9])):
                return self._build_test_device_rows(
                    data[pos:pos + 10], base_offset + pos, "fixture")

        return None

    @staticmethod
    def _is_valid_fixture_board_payload(command: int, payload: bytes) -> bool:
        if len(payload) != 6:
            return False
        if command == 0x02:
            return payload[3:6] == b"\x00\x00\x00"
        if command == 0x03:
            return payload[2:6] == b"\x00\x00\x00\x00"
        if command == 0x04:
            return payload[0] in (0x00, 0x01) and payload[1:6] == b"\x00\x00\x00\x00\x00"
        return False

    @staticmethod
    def _is_valid_function_board_payload(command: int, payload: bytes) -> bool:
        if len(payload) != 6:
            return False
        if command == 0x01:
            return payload[1:6] == b"\x00\x00\x00\x00\x00"
        if command == 0x02:
            return all(b in (0x00, 0x01) for b in payload[:4]) and payload[4:6] == b"\x00\x00"
        if command in (0x03, 0x04, 0x05):
            return payload[0] <= 127 and payload[1:6] == b"\x00\x00\x00\x00\x00"
        return False

    def _build_test_device_rows(self, frame: bytes, base: int, board_type: str) -> list:
        address = frame[1]
        command = frame[2]
        payload = frame[3:9]
        checksum = frame[9]
        calc_checksum = sum(frame[1:9]) & 0xFF

        if board_type == "function":
            title = "── 测试装置功能驱动板控制协议 ──"
            board_desc = "射频信号切换/衰减控制（9600 8N1，AA 0D 0A 结尾）"
        else:
            title = "── 测试装置工装板控制协议 ──"
            board_desc = "CCO/STA 仓工装板控制（FE...05 起始，地址+命令+6字节数据+校验）"

        rows = [(title, "", "", board_desc, base, base + len(frame) - 1)]

        if frame[0] == 0xFE:
            preamble_end = frame.find(0x05)
            if preamble_end < 0:
                preamble_end = 0
            rows.append((
                "起始字符", self._hex_space(frame[:preamble_end]),
                f"{preamble_end}字节", "0xFE 前导",
                base, base + preamble_end - 1))
            hdr_base = base + preamble_end
        else:
            preamble_end = 0
            hdr_base = base

        rows.append((
            "帧头", f"0x{frame[preamble_end]:02X}", "05",
            "数据帧开始", hdr_base, hdr_base))
        rows.append((
            "地址", f"0x{address:02X}", str(address),
            "00=广播预留，01=工装板默认地址",
            hdr_base + 1, hdr_base + 1))

        cmd_name = self.TEST_DEVICE_CMD_NAMES.get(command, f"未知命令(0x{command:02X})")
        rows.append((
            "命令码", f"0x{command:02X}", cmd_name,
            "测试装置通信控制协议 V1.1",
            hdr_base + 2, hdr_base + 2))

        data_base = hdr_base + 3
        if board_type == "function":
            rows.extend(self._build_function_board_command_rows(command, payload, data_base))
        else:
            rows.extend(self._build_fixture_board_command_rows(command, payload, data_base))

        rows.append((
            "校验和", f"0x{checksum:02X}",
            "✓ 正确" if checksum == calc_checksum else f"✗ 错误(应为0x{calc_checksum:02X})",
            "地址+命令码+6字节数据累加和取低8位",
            hdr_base + 9, hdr_base + 9))

        if board_type == "function":
            rows.append((
                "结束符", self._hex_space(frame[10:13]), "AA 0D 0A",
                "功能驱动板固定结束符",
                hdr_base + 10, hdr_base + 12))

        return rows

    def _build_function_board_command_rows(self, command: int, payload: bytes, base: int) -> list:
        rows = []
        for i, value in enumerate(payload):
            rows.append((
                f"数据项字节{i + 1}", f"0x{value:02X}", str(value),
                "6字节固定数据域", base + i, base + i))

        if command == 0x01:
            rows.append((
                "印制板控制单元地址", f"0x{payload[0]:02X}", str(payload[0]),
                "D0 表示印制板地址；返回原报文作为应答", base, base))
        elif command == 0x02:
            labels = ["8762-1", "8762-2", "8762-3", "8762-4"]
            values = []
            for idx, label in enumerate(labels):
                value = payload[idx]
                port = "B端" if value == 1 else "A端" if value == 0 else f"未知(0x{value:02X})"
                values.append(f"{label}={port}")
            rows.append((
                "8762A连接方式", self._hex_space(payload[:4]),
                "；".join(values),
                "0x00=接入A端，0x01=接入B端；字节5~6保留为0",
                base, base + 5))
        elif command in (0x03, 0x04, 0x05):
            attenuator = {0x03: "A", 0x04: "B", 0x05: "C"}[command]
            value = payload[0]
            rows.append((
                f"衰减器{attenuator}衰减值", f"0x{value:02X}",
                f"{value} dB" if value <= 127 else "超出范围(0~127dB)",
                f"设置{attenuator}相衰减器，1dB 步进；字节2~6保留为0",
                base, base))
        else:
            rows.append((
                "数据域", self._hex_space(payload), f"{len(payload)}字节",
                "未识别功能驱动板命令，显示原始数据", base, base + 5))
        return rows

    def _build_fixture_board_command_rows(self, command: int, payload: bytes, base: int) -> list:
        rows = []
        for i, value in enumerate(payload):
            rows.append((
                f"数据项字节{i + 1}", f"0x{value:02X}", str(value),
                "6字节固定数据域", base + i, base + i))

        if command == 0x02:
            cco_like = (payload[0] & 0xF8) != 0 or payload[1] == payload[2] == 0
            sta_like = (payload[0] & 0x07) != 0 or payload[1] != 0 or payload[2] != 0
            if cco_like and not sta_like:
                rows.extend(self._build_cco_power_rows(payload, base))
            elif sta_like and not cco_like:
                rows.extend(self._build_sta_power_rows(payload, base))
            else:
                rows.append((
                    "模块电源状态", self._hex_space(payload[:3]),
                    "CCO/STA 仓型无法仅凭报文唯一判定",
                    "CCO仓使用高6位；STA仓使用低20位小端位图",
                    base, base + 2))
                rows.extend(self._build_cco_power_rows(payload, base, "CCO仓解释/"))
                rows.extend(self._build_sta_power_rows(payload, base, "STA仓解释/"))
        elif command == 0x03:
            rows.extend(self._build_cco_pin_rows(payload, base))
            rows.extend(self._build_sta_pin_rows(payload, base))
        elif command == 0x04:
            if payload[0] == 1:
                state = "连接状态"
            elif payload[0] == 0:
                state = "断开状态"
            else:
                state = f"未知(0x{payload[0]:02X})"
            rows.append((
                "工装板220V电源状态", f"0x{payload[0]:02X}", state,
                "仅互操作6号屏蔽箱（CCO工装板）有效；字节2~6保留为0",
                base, base))
        else:
            rows.append((
                "数据域", self._hex_space(payload), f"{len(payload)}字节",
                "未识别工装板命令，显示原始数据", base, base + 5))
        return rows

    def _build_cco_power_rows(self, payload: bytes, base: int, prefix: str = "") -> list:
        power_bits = [
            (7, "STA1模块"), (6, "STA2模块"), (5, "CCO1模块"),
            (4, "CCO2模块"), (3, "三相表模块"), (2, "STA3模块"),
        ]
        states = [f"{name}={'上电' if payload[0] & (1 << bit) else '断电'}"
                  for bit, name in power_bits]
        return [(
            f"{prefix}CCO仓模块电源状态", f"0x{payload[0]:02X}",
            "；".join(states),
            "bit7=STA1, bit6=STA2, bit5=CCO1, bit4=CCO2, bit3=三相表, bit2=STA3；bit1/bit0保留",
            base, base + 2)]

    def _build_sta_power_rows(self, payload: bytes, base: int, prefix: str = "") -> list:
        bitmap = int.from_bytes(payload[:3], "little") & 0x0FFFFF
        on_nodes = [str(i) for i in range(1, 21) if bitmap & (1 << (i - 1))]
        off_count = 20 - len(on_nodes)
        parsed = f"上电:{','.join(on_nodes) if on_nodes else '无'}；断电:{off_count}个"
        return [(
            f"{prefix}STA仓模块电源位图", self._hex_space(payload[:3]), parsed,
            "20位小端位图：bit0~bit19分别对应1~20号STA，1=上电，0=断电",
            base, base + 2)]

    def _build_cco_pin_rows(self, payload: bytes, base: int) -> list:
        module_name = self.TEST_DEVICE_CCO_MODULE_NAMES.get(
            payload[0], f"未知模块(0x{payload[0]:02X})")
        states = [
            f"RST={'高电平' if payload[1] & 0x01 else '低电平'}",
            f"EVT={'高电平' if payload[1] & 0x02 else '低电平'}",
            f"SET={'高电平' if payload[1] & 0x04 else '低电平'}",
        ]
        return [(
            "CCO仓引脚控制", self._hex_space(payload[:2]),
            f"{module_name}；" + "；".join(states),
            "数据字节1=模块类型，数据字节2 bit0/1/2=RST/EVT/SET，0=低电平，1=高电平",
            base, base + 1)]

    def _build_sta_pin_rows(self, payload: bytes, base: int) -> list:
        if payload[0] > 0x13:
            node_name = f"未知STA编号(0x{payload[0]:02X})"
        else:
            node_name = f"STA{payload[0] + 1}"
        states = [
            f"RST={'高电平' if payload[1] & 0x01 else '低电平'}",
            f"EVENT={'高电平' if payload[1] & 0x02 else '低电平'}",
        ]
        return [(
            "STA仓引脚控制", self._hex_space(payload[:2]),
            f"{node_name}；" + "；".join(states),
            "数据字节1=STA编号(0x00~0x13对应1~20号)，数据字节2 bit0/1=RST/EVENT",
            base, base + 1)]

    @staticmethod
    def _plc2_channel_name(ch: int) -> str:
        names = {0x01: "HPLC", 0x02: "RF", 0x03: "HPLC+RF", 0x20: "PLC2.0 OFDMA"}
        if ch in names:
            return names[ch]
        if 0x10 <= ch <= 0x1C:
            return f"PLC2.0 MIMO(0x{ch:02X})"
        return f"保留(0x{ch:02X})"

    def _parse_ed_wrapper(self, frame_bytes: bytes, parse_level: str = "auto",
                          pb_frame_type: str = "sof",
                          channel: str = "auto",
                          wrapper: Optional[str] = None,
                          protocol_index: Optional[int] = None) -> Optional[list]:
        """解析完整 ED..EE 监控包装（PLC2.0 / 广西台体布局），并继续解析其中业务数据。

        wrapper=None → 自动识别（detect_ed_wrapper）；"plc2"/"gx" → 按指定布局。
        protocol_index → 字段解释语言（9=广西台体/PLC2.0；10/11=国网HDC，gx 同构）。
        """
        from batch_core import ed_wrapper_display

        n = len(frame_bytes)
        if n < 8 or frame_bytes[0] != 0xED:
            return None
        if wrapper not in ("plc2", "gx"):
            wrapper = detect_ed_wrapper(frame_bytes)
        ed_lab = ed_wrapper_display(protocol_index if protocol_index is not None else 9,
                                    wrapper)

        def fail(reason: str) -> list:
            return [("❌ 解析失败", "", "", f"ED 监控帧错误：{reason}", 0, n - 1)]

        frame_len = int.from_bytes(frame_bytes[1:3], "little")
        if frame_len < 4 or frame_len > 4096:
            return fail(f"帧长字段非法(0x{frame_len:04X})")
        total = frame_len + 4
        if total > n:
            return fail(f"报文不完整，声明{total}字节，实际{n}字节")
        if frame_bytes[5] != 0xEF:
            return fail("缺少数据域起始符 EF")
        if frame_bytes[total - 1] != 0xEE:
            return fail("缺少结束符 EE")

        ctrl1 = frame_bytes[3]
        ctrl2 = frame_bytes[4]
        data_len = frame_len - 4
        data_start = 6
        data = frame_bytes[data_start:data_start + data_len]
        cs_offset = data_start + data_len
        calc_cs = sum(frame_bytes[:cs_offset]) & 0xFF
        cs = frame_bytes[cs_offset]
        cs_txt = "✓ 正确" if cs == calc_cs else ("保留(0xFF)" if cs == 0xFF else "✗ 错误")

        ctrl1_name = {0x00: "数据报文", 0x01: "控制报文"}.get(
            ctrl1, f"保留(0x{ctrl1:02X})")
        ctrl2_name = {
            0x01: "FC数据", 0x02: "FC+Payload数据", 0x03: "Payload数据",
            0x04: "发送完成", 0x05: "选择确认帧发送完成",
            0x06: "RF和HPLC同时发送FC+Payload", 0x07: "FC+Payload数据",
            0x08: "UL-OFDMA帧(DL-OFDMA的SACK帧)",
        }.get(ctrl2, f"保留(0x{ctrl2:02X})")

        is_gx = wrapper == "gx"
        hdr_title = ed_lab["title"]
        rows = [
            (hdr_title, "", "", ed_lab["header_desc"], None, None),
            ("起始符(ED)", f"0x{frame_bytes[0]:02X}", "ED",
             ed_lab["start_comment"],
             0, 0),
            ("帧长", self._hex_space(frame_bytes[1:3]), f"{frame_len} 字节",
             "控制域1+控制域2+EF+数据域+CS(小端)", 1, 2),
            ("控制域1", f"0x{ctrl1:02X}", ctrl1_name,
             "0x00-数据报文 0x01-控制报文", 3, 3),
            ("控制域2", f"0x{ctrl2:02X}", ctrl2_name, "报文子类型", 4, 4),
            ("数据域起始符(EF)", f"0x{frame_bytes[5]:02X}", "EF",
             "数据域起始标识", 5, 5),
            ("数据域长度", str(data_len), f"{data_len} 字节",
             f"字节 {data_start}~{cs_offset - 1}", data_start, cs_offset - 1),
        ]

        hdr_len = 8 if is_gx else 9
        if ctrl1 == 0x00 and ctrl2 in (0x01, 0x02, 0x03) and data_len >= hdr_len:
            if is_gx:
                ts = int.from_bytes(data[0:4], "little")
                ch = data[4]
                pb_cnt = data[5]
                pb_len = int.from_bytes(data[6:8], "little")
                business = data[8:]
                business_offset = data_start + 8
            else:
                ch = data[0]
                ts = int.from_bytes(data[1:5], "little")
                pb_cnt = data[5]
                flag6 = data[6]
                pb_len = int.from_bytes(data[7:9], "little")
                business = data[9:]
                business_offset = data_start + 9
            rows.extend([
                ("物理信道", f"0x{ch:02X}", self._plc2_channel_name(ch),
                 "0x01-HPLC 0x02-RF 0x03-HPLC+RF 0x10~0x1C-MIMO 0x20-OFDMA",
                 data_start + (4 if is_gx else 0), data_start + (4 if is_gx else 0)),
                ("时间戳", f"0x{ts:08X}", str(ts),
                 "HW→PC 接收开始时间(小端)",
                 data_start + (0 if is_gx else 1), data_start + (3 if is_gx else 4)),
                ("物理块个数", str(pb_cnt), str(pb_cnt), None,
                 data_start + 5, data_start + 5),
            ])
            if not is_gx:
                rows.append(
                    ("Payload CRC", f"0x{flag6:02X}",
                     "错误" if ctrl2 == 0x02 and flag6 == 1 else "正确/保留",
                     "ctrl2=0x02时: 0-正确 1-错误；其余保留",
                     data_start + 6, data_start + 6))
            rows.append(
                ("单个物理块长度", str(pb_len), f"{pb_len} 字节(小端)", None,
                 data_start + (6 if is_gx else 7),
                 data_start + (7 if is_gx else 8)))
        else:
            business = data
            business_offset = data_start

        rows.extend([
            ("校验(CS)", f"0x{cs:02X}", cs_txt,
             "ED..数据域末所有字节求和取低8bit", cs_offset, cs_offset),
            ("结束符(EE)", f"0x{frame_bytes[total - 1]:02X}", "EE",
             ed_lab["end_comment"],
             total - 1, total - 1),
            ("── 业务帧 ──", "", "",
             "以下为 ED 数据域解析结果", business_offset, cs_offset - 1),
        ])

        if business:
            business_table = self.parse_to_table(
                business, parse_level=parse_level,
                pb_frame_type=pb_frame_type, channel=channel)
            for row in business_table:
                if len(row) >= 6 and row[4] is not None and row[5] is not None:
                    row = (row[0], row[1], row[2], row[3],
                           row[4] + business_offset, row[5] + business_offset)
                rows.append(row)
        else:
            rows.append(("业务数据", "", "空", "ED 控制报文或空数据报文",
                         business_offset, cs_offset - 1))

        return rows

    @staticmethod
    def _crc32_ieee(data: bytes) -> int:
        """CRC-32 (IEEE 802.3): poly=0x104C11DB7, init=0, rev=True, xorOut=0xFFFFFFFF"""
        return _crc32_func(data)

    @staticmethod
    def _crc24(data: bytes) -> int:
        """CRC-24: poly=0x1800063, init=0, rev=True, xorOut=0x000000"""
        return _crc24_func(data)

    def parse_to_table(self, frame_bytes: bytes, parse_level: str = "auto",
                    pb_frame_type: str = "sof", channel: str = "auto",
                    ed_wrapper: Optional[str] = None) -> list:
        """
        解析帧为表格数据格式
        返回: [(字段名, 原始值, 解析值, 说明, byte_start, byte_end), ...]

        支持七种输入模式（自动识别）:
        1. 完整 MPDU 帧 (FC帧控制16字节 + 物理块载荷)
        2. 完整 MAC 帧 (MAC头 + MSDU + 完整性校验)
        3. 仅 MSDU 负载 (VLAN标签 + MSDU类型 + 应用层数据)
        4. 仅应用层报文 (报文端口号 + 报文标识符 + ...)
        5. 裸级联聚合帧 (无FC无PB头, 2字节级联头+MAC帧重复)
        6. pb_only 物理块输入 (PB头 + MAC帧 + PBCS)
        7. mac_only 仅MAC帧输入 (输入即MAC帧，不含PBH，从字节0直接解析)

        Args:
            channel: "plc" (载波), "hrf" (高速无线) 或 "auto" (MPDU级输入自动判别)
            ed_wrapper: ED..EE 监控包装格式 "plc2"/"gx"，None=自动识别
        """
        self._channel = channel
        self._detected_channel = None
        # 每帧重置状态, 避免上一帧的 _pb_size / _cmt_index / _pb_count 残留
        self._pb_size = None
        self._cmt_index = 4
        self._std_version = 1
        self._pb_count = 1
        # 重组偏移映射重置：非 PB 帧（信标/直接应用层等）不得沿用上一帧映射
        self._concat_segments = None
        self._concat_origin = 0
        table_data = []
        frame_len = len(frame_bytes)
        self._aggregated = False

        if frame_len < 2:
            table_data.append(("❌ 解析失败", "", "", "帧长度不足（<2字节）", None, None))
            return table_data

        # ED..EE 包装中的测试装置控制协议不是载波 MPDU/MAC 业务帧，优先识别。
        test_control_rows = self._parse_test_device_control(frame_bytes)
        if test_control_rows is not None:
            return test_control_rows

        if frame_bytes[0] == 0xED:
            ed_rows = self._parse_ed_wrapper(
                frame_bytes,
                parse_level=parse_level,
                pb_frame_type=pb_frame_type,
                channel=channel,
                wrapper=ed_wrapper,
            )
            if ed_rows is not None:
                return ed_rows

        # ── 通道识别：MPDU 级输入（接入指示=1）一律按 FC 可变区域结构判别 PLC/HRF。
        # 批量解析中什么帧类型都会遇到，下拉固定值不能代表每帧信道，故以 FC 判别为准；
        # 非 MPDU 级输入（MAC/MSDU/APP）无 FC 头，沿用调用方传入的 channel。
        if ((frame_bytes[0] >> 3) & 0x01) == 1:
            self._channel_pinned = (
                self._channel if channel not in ("auto", None) else None)
            self._channel = self._detect_channel(frame_bytes, frame_len)
            self._detected_channel = self._channel
        else:
            self._channel_pinned = None

        # ── 自动识别帧的起始层次（优先级：MPDU > MAC > MSDU > APP）──
        offset = 0
        mac_data = None
        first_byte = frame_bytes[0]

        is_direct_app = False

        # ── 步骤0: 检测 MPDU 帧（FC帧控制，16字节头）──
        # MPDU特征：bit3=1（接入指示）+ bits0-2=定界符类型(0~3)
        # SACK/信标/NET 帧只有 FC 头（16 字节），但真实抓包常在 FC 之后带尾部字节
        # （FCS/冗余），故统一按 >=16 判定 MPDU；尾字节在 FC 解析后单独展示，
        # 绝不因长度不等于 16 而把 SACK 误送入 MAC 解析路径
        delimiter_type = first_byte & 0x07       # bits 0-2
        access_indicator = (first_byte >> 3) & 0x01  # bit 3
        is_mpdu = (access_indicator == 1 and delimiter_type <= 3 and frame_len >= 16)

        is_pb_only = (parse_level == "pb_only")
        if is_pb_only:
            # 仅物理块输入（无FC帧控制域）：PB头(4B) + MAC帧 + 保留 + PBCS(3B)
            # 无FC无法从定界符得知帧类型，由 pb_frame_type 参数显式指定
            self._delimiter_type = {"sof": 1, "beacon": 0, "sack": 2, "net": 3}.get(pb_frame_type, 1)
            self._cmt_index = 4      # 默认载波映射表索引(PB 136字节)
            self._std_version = 1    # 默认BPLC版本
            self._pb_count = 1       # pb_only 默认单PB

            # 信标帧(定界符类型=0)：无物理块头，FC后直接为信标载荷。
            # pb_only 输入即裸信标载荷，直接按信标载荷解析（表51）
            if self._delimiter_type == 0:
                table_data.append(("── 信标帧载荷（PB-only，无物理块头）──", "", "",
                                   "信标帧无PB块头，输入即信标载荷，直接按表51解析",
                                   0, frame_len - 1))
                table_data.extend(self._parse_beacon_payload(frame_bytes, 0))
                return table_data
            # 选择确认帧(类型2)/网间协调帧(类型3)：仅FC头，无物理块/MSDU
            if self._delimiter_type in (2, 3):
                table_data.append(("❌ 解析失败", "", "",
                                   "选择确认帧(SACK)/网间协调帧无物理块，不适合PB-only解析",
                                   None, None))
                return table_data
            offset, mac_data, msdu_payload = self._parse_pb_block(
                frame_bytes, 0, table_data, frame_len)
        elif parse_level == "mac_only":
            # 仅MAC帧模式：输入即MAC帧数据（不含PBH），从字节0直接解析
            # 信标帧无PBH，输入即信标载荷
            self._delimiter_type = {"sof": 1, "beacon": 0, "sack": 2, "net": 3}.get(pb_frame_type, 1)
            self._cmt_index = 4
            self._std_version = 1
            self._pb_count = 1

            # 信标帧(定界符类型=0)：无物理块头，输入即信标载荷，直接按表51解析
            if self._delimiter_type == 0:
                table_data.append(("── 信标帧载荷（仅MAC帧模式）──", "", "",
                                   "信标帧无PB块头，输入即信标载荷，直接按表51解析",
                                   0, frame_len - 1))
                table_data.extend(self._parse_beacon_payload(frame_bytes, 0))
                return table_data
            # 选择确认帧(类型2)/网间协调帧(类型3)：仅FC头，无物理块/MSDU
            if self._delimiter_type in (2, 3):
                table_data.append(("❌ 解析失败", "", "",
                                   "选择确认帧(SACK)/网间协调帧无物理块，不适合仅MAC帧解析",
                                   None, None))
                return table_data

            table_data.append(("解析模式", "", "仅MAC帧",
                               "输入即MAC帧（不含物理块头），从字节0直接解析", None, None, False))
            # MAC帧从字节0开始（输入不含PBH）
            mac_start = 0
            mac_bytes = frame_bytes
            offset, mac_table = self._parse_mac_frame(mac_bytes, base_offset=mac_start)
            table_data.extend(mac_table)
            # 设置msdu_payload供后续_parse_msdu_payload处理
            first_byte_mac = mac_bytes[0]
            mac_version = (first_byte_mac >> 1) & 0x03
            mac_header_type = first_byte_mac & 0x01
            if mac_version == 2:
                mac_hdr_len = 4
                msdu_payload = b""
            elif mac_header_type == 0:
                mac_hdr_len = 32
                if len(mac_bytes) >= 4:
                    msdu_len = int.from_bytes(mac_bytes[2:4], 'little')
                    msdu_payload = mac_bytes[mac_hdr_len:mac_hdr_len + msdu_len]
                else:
                    msdu_payload = mac_bytes[mac_hdr_len:]
            else:
                mac_hdr_len = 12
                if len(mac_bytes) >= 4:
                    msdu_len = int.from_bytes(mac_bytes[2:4], 'little')
                    msdu_payload = mac_bytes[mac_hdr_len:mac_hdr_len + msdu_len]
                else:
                    msdu_payload = mac_bytes[mac_hdr_len:]
            mac_data = mac_bytes
            offset = mac_start + mac_hdr_len
        elif is_mpdu:
            self._delimiter_type = delimiter_type
            offset, mpdu_table = self._parse_mpdu_frame(frame_bytes, offset)
            table_data.extend(mpdu_table)

            if parse_level == "fc_only":
                return table_data

            # ── eFC 扩展帧控制解析（OFDMA帧，type!=1时）──
            # 预校验 CRC-24：若校验失败说明该帧实际不含 eFC（如非OFDMA帧被误判），跳过eFC解析
            if (getattr(self, '_ofdma_frame_type', -1) >= 0
                    and self._ofdma_frame_type != 1
                    and delimiter_type == 1):  # 仅SOF帧携带eFC
                efc_size = 16
                if offset + efc_size <= frame_len:
                    efc_data = frame_bytes[offset:offset + efc_size]
                    # CRC-24 预校验：前13字节计算，字节13-15为FCS（小端序）
                    efc_crc_calc = self._crc24(efc_data[:13])
                    efc_crc_stored = int.from_bytes(efc_data[13:16], 'little')
                    if efc_crc_calc == efc_crc_stored:
                        efc_end = self._parse_efc(
                            efc_data, offset,
                            self._ofdma_frame_type,
                            self._ofdma_station_count,
                            table_data)
                        offset = efc_end
                    # CRC校验失败时不解析eFC，后续数据作为PB处理
                else:
                    table_data.append(("⚠️ eFC数据不足", "",
                                      "", f"需要{efc_size}字节但仅剩{frame_len - offset}字节",
                                      offset, frame_len - 1))

            # FC+eFC解析模式：解析完FC和eFC后直接返回，不解析物理块
            if parse_level == "fc_efc":
                return table_data

            # 下拉通道与 FC 结构判别不一致时提示（以 FC 判别为准）
            pinned = getattr(self, "_channel_pinned", None)
            if pinned and pinned != self._channel:
                table_data.append((
                    "通道判别", pinned, self._channel,
                    "下拉通道与 FC 可变区域结构判别不一致，以 FC 判别为准",
                    None, None))
            # 信标帧(定界符类型=0)：FC后直接为信标载荷，无物理块头
            if delimiter_type == 0:
                beacon_data = frame_bytes[offset:]
                if beacon_data:
                    table_data.extend(self._parse_beacon_payload(beacon_data, offset))
                return table_data
            # 选择确认帧(定界符类型=2)/网间协调帧(类型3)：仅FC头16字节，无物理块/MSDU。
            # 真实抓包常在 FC 之后带尾部字节（FCS/冗余）：单独展示而不报错，
            # 更不回落到 MAC 解析路径（曾因此误报「MAC帧长度不足(需要≥36字节)」）。
            elif delimiter_type in (2, 3):
                if frame_len > offset:
                    tail = frame_bytes[offset:]
                    fname = "选择确认帧" if delimiter_type == 2 else "网间协调帧"
                    table_data.append((
                        "尾部字节", self._hex_space(tail), f"{len(tail)} 字节",
                        f"{fname}无物理块/MSDU，FC 头之后的尾部字节（疑似 FCS/冗余）",
                        offset, frame_len - 1))
                return table_data
            else:
                offset, mac_data, msdu_payload = self._parse_pb_block(
                    frame_bytes, offset, table_data, frame_len)
        else:
            # ── 步骤1: 先检测直接应用层报文（优先于MAC帧检测）──
            # 端口号(0x11/0x13) + 标识符(0x0101) 的组合足够特异，可避免与MAC帧误判
            is_direct_app = False
            if frame_len >= 3:
                port_byte = frame_bytes[0]
                id_bytes = (frame_bytes[1] << 8) | frame_bytes[2]
                if port_byte in (0x11, 0x13) and id_bytes == 0x0101:
                    is_direct_app = True

            if is_direct_app:
                # 直接应用层报文，跳过MAC帧解析
                msdu_payload = frame_bytes
            else:
                # ── 步骤2: 检测裸级联聚合帧（无FC无PB头，2字节级联头+MAC帧重复）──
                # 特征：前2字节小端低12位 = 一个合理的MAC帧长度，且该长度后又出现2字节级联头
                is_mac_concat = False
                if parse_level == "mac_concat" or (
                    frame_len >= 4
                    and (int.from_bytes(frame_bytes[0:2], 'little') & 0x0FFF) >= 16
                    and (int.from_bytes(frame_bytes[0:2], 'little') & 0x0FFF) + 2 < frame_len
                    and (frame_bytes[2] & 0x01) in (0, 1)
                    and ((frame_bytes[2] >> 1) & 0x03) in (1, 2)
                ):
                    # 再验证第二个级联头
                    first_len = int.from_bytes(frame_bytes[0:2], 'little') & 0x0FFF
                    if first_len + 4 <= frame_len:
                        second_hdr = frame_bytes[first_len + 2:first_len + 4]
                        second_len = int.from_bytes(second_hdr, 'little') & 0x0FFF
                        if second_len >= 12 and second_len + first_len + 2 <= frame_len + 100:
                            is_mac_concat = True

                if is_mac_concat:
                    table_data.append((
                        "── 裸级联聚合帧（无FC无PB头）──",
                        "", "",
                        "2字节级联头 + MAC帧 级联排列",
                        0, frame_len - 1
                    ))
                    self._aggregated = True
                    cascade_offset = 0
                    cascade_idx = 0
                    while cascade_offset + 2 <= frame_len:
                        cascade_hdr = frame_bytes[cascade_offset:cascade_offset + 2]
                        cascade_len = int.from_bytes(cascade_hdr, 'little') & 0x0FFF
                        start_flag = (cascade_hdr[1] >> 4) & 0x01
                        end_flag = (cascade_hdr[1] >> 5) & 0x01
                        table_data.append((
                            f"  级联头({cascade_idx})",
                            ' '.join(f'{b:02X}' for b in cascade_hdr),
                            f"长度:{cascade_len}, 起始:{start_flag}, 结束:{end_flag}",
                            f"级联数据块长度:{cascade_len}字节",
                            cascade_offset, cascade_offset + 1
                        ))
                        cascade_offset += 2
                        if cascade_len == 0 or cascade_offset + cascade_len > frame_len:
                            break
                        mac_seg = frame_bytes[cascade_offset:cascade_offset + cascade_len]
                        _, mac_table = self._parse_mac_frame(
                            mac_seg, base_offset=cascade_offset,
                            parse_msdu_app=True)
                        table_data.extend(mac_table)
                        cascade_offset += cascade_len
                        cascade_idx += 1
                        if end_flag:
                            break
                    self._aggregated = False
                    return table_data

                # ── 步骤3: 检测 MAC 帧 ──
                header_type = (first_byte >> 0) & 0x01
                version = (first_byte >> 1) & 0x03
                # 版本2=单跳帧协议(表12, 4字节头, 仅无线) 帧长下限按头长放宽
                is_mac_frame = (header_type in (0, 1) and version in (1, 2)
                                and frame_len >= (4 if version == 2 else 12))

                if is_mac_frame:
                    mac_header_size = 4 if version == 2 else (12 if header_type == 1 else 32)
                    offset, mac_table = self._parse_mac_frame(frame_bytes, offset)
                    table_data.extend(mac_table)
                    if version == 2:
                        # 单跳帧: MSDU类型在MAC头内，载荷已由 _parse_mac_frame 内联解析
                        msdu_payload = b""
                    elif len(frame_bytes) >= 4:
                        # 读取MSDU长度（MAC帧头 bytes 2-3）
                        msdu_len = int.from_bytes(frame_bytes[2:4], 'little')
                        msdu_payload = frame_bytes[mac_header_size:mac_header_size + msdu_len]
                    else:
                        msdu_payload = frame_bytes[mac_header_size:]
                else:
                    msdu_payload = frame_bytes

        # ── 解析 MSDU 负载（MSDU头判定 + 应用层分派），主流程与聚合帧级联块共用 ──
        # 聚合帧的级联块已在 _parse_pb_block 内各自解析应用层，跳过整帧兜底
        if not getattr(self, '_aggregated', False):
            # MSDU/应用层行偏移处于 concat 空间，仅翻译新增行（之前的行已是原始偏移）
            _before = len(table_data)
            table_data = self._parse_msdu_payload(msdu_payload, offset, mac_data,
                                                  table_data, is_direct_app)
            table_data[_before:] = self._remap_concat_rows(table_data[_before:])

        return table_data

    def _parse_msdu_payload(self, msdu_payload: bytes, offset: int,
                            mac_data: Optional[bytes], table_data: list,
                            is_direct_app: bool = False) -> list:
        """解析 MSDU 负载：判定 MSDU 头（长/短/非标准）并按类型分派应用层解析

        主流程（单MAC帧/直接应用层）与聚合帧级联块解析共用。
        - 短MSDU头(2B): VLAN标签(1B) + MSDU类型(1B)
        - 长MSDU头(18B): 目的MAC 6B + 源MAC 6B + VLAN 4B + 类型 2B
        - 非标准头: 扫描管理消息特征定位
        """
        if not is_direct_app and len(msdu_payload) >= 3:
            # 检测应用层报文特征：端口号(0x11或0x13) + 标识符(0x0101)
            port_byte = msdu_payload[0]
            id_bytes = (msdu_payload[1] << 8) | msdu_payload[2]
            if port_byte in (0x11, 0x13) and id_bytes == 0x0101:
                is_direct_app = True

        # ── 解析 MSDU 头 (长头/短头) ──
        # MAC长头(32字节) → MSDU长头(18字节: 目的MAC 6B + 源MAC 6B + VLAN 4B + 类型 2B)
        # MAC短头(12字节) → MSDU短头(2字节: VLAN 1B + 类型 1B)
        # 注：某些帧（如管理消息）可能使用不标准的MSDU头偏移，需扫描检测
        msdu_hdr_len = 2  # 默认短头
        if mac_data and (mac_data[0] & 0x01) == 0:
            # MAC长头 → MSDU长头(18字节)
            msdu_hdr_len = 18

        is_msdu = False
        vlan_tag = 0
        msdu_type = 0
        msdu_hdr_data = None

        if not is_direct_app and len(msdu_payload) >= msdu_hdr_len:
            if msdu_hdr_len == 18:
                # 长MSDU头：原始目的地址(6B) + 原始源地址(6B) + VLAN标签(4B) + MSDU类型(2B)
                msdu_hdr_data = msdu_payload[:18]
                vlan_tag = int.from_bytes(msdu_payload[12:16], 'little')
                msdu_type = int.from_bytes(msdu_payload[16:18], 'little')
                # 校验长头有效性
                is_msdu = (
                    (0 <= vlan_tag <= 3 and msdu_type in (0x01, 0x02, 0x80))
                    or (vlan_tag == 0x8100 and msdu_type == 0x88E1)
                )
                if not is_msdu:
                    # 长头校验失败，扫描管理消息特征模式 (VLAN=0x8100 + MSDU类型=0x88E1)
                    # 在MSDU负载前32字节内搜索，支持非标准MSDU头偏移
                    mgmt_hdr_off = self._scan_mgmt_msdu_offset(msdu_payload, max_scan=32)
                    if mgmt_hdr_off is not None and mgmt_hdr_off > 0:
                        # 找到管理消息特征，使用扫描偏移确定MSDU头长度
                        msdu_hdr_len = mgmt_hdr_off + 2  # 偏移 + MSDU类型2字节
                        msdu_hdr_data = msdu_payload[:msdu_hdr_len]
                        vlan_tag = 0x8100  # 已知的VLAN标签
                        msdu_type = 0x88E1  # 已知的MSDU类型
                        is_msdu = True
                    else:
                        # 未找到管理消息特征，尝试按短头解析
                        msdu_hdr_len = 2
                        if len(msdu_payload) >= 2:
                            vlan_tag = msdu_payload[0]
                            msdu_type = msdu_payload[1]
                            is_msdu = (
                                (0 <= vlan_tag <= 3 and msdu_type in (0x01, 0x02, 0x80))
                                or (vlan_tag == 0x81 and msdu_type == 0x00)
                            )
            else:
                # 短MSDU头：VLAN标签(1B) + MSDU类型(1B)
                msdu_hdr_data = msdu_payload[:2]
                vlan_tag = msdu_payload[0]
                msdu_type = msdu_payload[1]
                is_msdu = (
                    (0 <= vlan_tag <= 3 and msdu_type in (0x01, 0x02, 0x80))
                    or (vlan_tag == 0x81 and msdu_type == 0x00)
                )

        if is_direct_app:
            app_table = self._parse_application_message(msdu_payload, base_offset=0)
            table_data.extend(app_table)
        elif is_msdu:
            msdu_type_name = MSDU_TYPE_MAP.get(msdu_type, f"保留(0x{msdu_type:02X})")
            
            if msdu_hdr_len == 18:
                # 长MSDU头字段
                orig_dest = ':'.join(f'{b:02X}' for b in msdu_payload[0:6])
                orig_src = ':'.join(f'{b:02X}' for b in msdu_payload[6:12])
                table_data.append((
                    "MSDU头-原始目的地址",
                    orig_dest,
                    orig_dest,
                    "MSDU原始目的MAC地址",
                    offset, offset + 5
                ))
                table_data.append((
                    "MSDU头-原始源地址",
                    orig_src,
                    orig_src,
                    "MSDU原始源MAC地址",
                    offset + 6, offset + 11
                ))
                table_data.append((
                    "VLAN标签",
                    f"0x{vlan_tag:04X}",
                    str(vlan_tag),
                    f"优先级分组 {vlan_tag}",
                    offset + 12, offset + 15
                ))
                table_data.append((
                    "MSDU类型",
                    f"0x{msdu_type:04X}",
                    f"{msdu_type}",
                    msdu_type_name,
                    offset + 16, offset + 17
                ))
                app_base = offset + 18
                payload_data = msdu_payload[18:]
            elif msdu_hdr_len == 2:
                # 短MSDU头字段
                table_data.append((
                    "VLAN标签",
                    f"0x{vlan_tag:02X}",
                    str(vlan_tag),
                    f"优先级分组 {vlan_tag}",
                    offset, offset
                ))
                table_data.append((
                    "MSDU类型",
                    f"0x{msdu_type:02X}",
                    f"{msdu_type}",
                    msdu_type_name,
                    offset + 1, offset + 1
                ))
                app_base = offset + 2
                payload_data = msdu_payload[2:]
            else:
                # 非标准MSDU头（由扫描检测到的管理消息特征）
                # 显示MSDU头原始数据，VLAN和MSDU类型位置由扫描确定
                # VLAN=0x8100在msdu_hdr_len-6位置，MSDU类型在msdu_hdr_len-2位置
                vlan_off = msdu_hdr_len - 6
                type_off = msdu_hdr_len - 2
                if msdu_hdr_data:
                    table_data.append((
                        "MSDU头(原始)",
                        ' '.join(f'{b:02X}' for b in msdu_hdr_data),
                        f"{msdu_hdr_len}字节",
                        "非标准MSDU头（由管理消息特征扫描定位）",
                        offset, offset + msdu_hdr_len - 1
                    ))
                table_data.append((
                    "VLAN标签",
                    ' '.join(f'{b:02X}' for b in msdu_payload[vlan_off:vlan_off + 4]),
                    f"0x{vlan_tag:04X}",
                    f"网络管理子层VLAN标签",
                    offset + vlan_off, offset + vlan_off + 3
                ))
                table_data.append((
                    "MSDU类型",
                    ' '.join(f'{b:02X}' for b in msdu_payload[type_off:type_off + 2]),
                    f"0x{msdu_type:04X}",
                    msdu_type_name,
                    offset + type_off, offset + type_off + 1
                ))
                app_base = offset + msdu_hdr_len
                payload_data = msdu_payload[msdu_hdr_len:]

            if msdu_type == 0x01:
                app_table = self._parse_application_message(payload_data, base_offset=app_base)
                table_data.extend(app_table)
            elif msdu_type == 0x02:
                mgmt_table = self._parse_management_message(payload_data, base_offset=app_base)
                table_data.extend(mgmt_table)
            elif msdu_type == 0x88E1:
                mgmt_table = self._parse_management_message(payload_data, base_offset=app_base)
                table_data.extend(mgmt_table)
            elif msdu_type == 0x80:
                table_data.append((
                    "IPV4数据",
                    ' '.join(f'{b:02X}' for b in payload_data),
                    f"{len(payload_data)}字节",
                    "IPV4报文负载",
                    app_base, offset + len(msdu_payload) - 1
                ))
            else:
                raw_hex = ' '.join(f'{b:02X}' for b in payload_data)
                table_data.append((
                    "MSDU负载",
                    raw_hex[:200] + ("..." if len(raw_hex) > 200 else ""),
                    f"{len(payload_data)}字节",
                    f"MSDU类型{msdu_type}的数据",
                    app_base, offset + len(msdu_payload) - 1
                ))
        elif len(msdu_payload) > 0:
            raw_hex = ' '.join(f'{b:02X}' for b in msdu_payload)
            table_data.append((
                "MSDU负载",
                raw_hex[:200] + ("..." if len(raw_hex) > 200 else ""),
                f"{len(msdu_payload)}字节",
                f"未识别的MSDU类型(首字节0x{msdu_payload[0]:02X})，显示原始数据",
                offset, offset + len(msdu_payload) - 1
            ))

        return table_data

    # ── MPDU (MAC Protocol Data Unit) 帧控制解析 ──
    # ── 载波映射表索引/TMI → 物理块大小映射 ──
    # BPLC版本: 参照GDW ROBO模式表（仅支持PB136/PB520）
    #   CMT 0x0-0x7, 0xE → PB136   CMT 0x8-0xC, 0xF → PB520
    # ISAC-PLC版本: 参照表13 SPLC载荷数据ROBO模式
    # 定界符类型（表15）
    DELIMITER_TYPE_MAP = {
        0: "信标帧",
        1: "SOF帧",
        2: "选择确认帧",
        3: "网间协调帧",
    }

    ISAC_PB_MAP = {
        0:520,1:520,2:520,3:520,4:520,5:520,6:520,7:520,8:520,
        9:264,10:264,11:264,12:264,13:264,14:264,15:264,
        16:136,17:136,18:136,19:136,20:136,
        21:72,22:72,23:72,24:72,25:72,
        26:16,27:16
    }

    # ISAC-PLC Bitloading模式(表23 字节6 bit1-2)物理块大小码: 0:136 1:520 2:72 3:264
    ISAC_BL_PB_SIZE_MAP = {0: 136, 1: 520, 2: 72, 3: 264}

    # HRF（高速无线）MCS 表（表43）
    HRF_MCS_TABLE = {
        0: {"diversity": 4, "modulation": "BPSK", "code_rate": "1/2"},
        1: {"diversity": 2, "modulation": "BPSK", "code_rate": "1/2"},
        2: {"diversity": 2, "modulation": "QPSK", "code_rate": "1/2"},
        3: {"diversity": 1, "modulation": "QPSK", "code_rate": "1/2"},
        4: {"diversity": 1, "modulation": "QPSK", "code_rate": "4/5"},
        5: {"diversity": 1, "modulation": "16QAM", "code_rate": "1/2"},
        6: {"diversity": 1, "modulation": "16QAM", "code_rate": "4/5"},
    }

    # HRF 载荷 PB 大小表（表44），索引4bit
    HRF_PB_SIZE_TABLE = {
        0: 16,
        1: 40,
        2: 72,
        3: 136,
        4: 264,
        5: 520,
    }

    # 物理块大小候选集（帧长一致性推断用）：表13(ISAC)/表44(HRF)/BPLC 的全部可能取值，
    # 由大到小排列。CMT/TMI 映射值与实际帧长不符时用它反推真实 PB 大小。
    PB_SIZE_CANDIDATES = (520, 264, 136, 72, 40, 16)

    @staticmethod
    def _get_pb_size(tmi: int, version: int) -> int:
        """根据TMI/CMT和版本号获取物理块总大小(字节)"""
        if version == 2:  # ISAC-PLC (表13)
            return CSGNewGenParser.ISAC_PB_MAP.get(tmi, 136)
        else:  # BPLC (GDW ROBO)
            if tmi <= 0x7 or tmi == 0xE:
                return 136
            elif tmi in (0x8, 0x9, 0xA, 0xB, 0xC, 0xF):
                return 520
            return 520  # 0xD扩展模式默认520

    @staticmethod
    def _get_pb_body_size(pb_total: int) -> int:
        """物理块体大小 = 物理块总大小 - PB头(4) - 保留(1) - PB检查序列(3)"""
        return pb_total - 4 - 1 - 3

    def _infer_pb_size(self, offset: int, pb_count: int, frame_len: int,
                       cmt_size: int) -> Tuple[int, bool]:
        """按帧长一致性推断物理块大小，返回 (PB大小, 是否覆盖了CMT映射值)。

        判据：SOF MPDU = FC [+eFC] + ΣPB（无尾字节），发送端必然满足
            PB起始偏移 + 物理块个数 × PB大小 == 帧总长
        CMT/TMI 映射值只是先验（BPLC 分支沿用 GDW 老表，实测存在 CMT=1 而
        PB=520 的帧），映射值不满足等式时在候选集中取唯一解覆盖；
        截断日志/SOF 带尾字节/混合 PB 大小 → 等式无解 → 回退映射值（行为同现状）。

        Args:
            offset: 第一个物理块的起始偏移（FC/eFC 之后）
            pb_count: FC 可变区域给出的物理块个数
            frame_len: 帧总长
            cmt_size: CMT/TMI 映射得到的 PB 大小（先验值）
        """
        if pb_count < 1:
            return cmt_size, False
        remain = frame_len - offset
        if remain <= 0:
            return cmt_size, False
        if pb_count * cmt_size == remain:
            return cmt_size, False   # 映射值与帧长自洽，保持现状
        for size in self.PB_SIZE_CANDIDATES:
            if pb_count * size == remain:
                return size, True    # 帧长一致性唯一解，覆盖映射值
        return cmt_size, False       # 无解（截断/带尾字节/混合PB），回退映射值

    def calc_pbcs_fills(self, frame_bytes: bytes) -> list:
        """计算逐物理块 PBCS 的填充计划（供 GUI 「填充CRC-24」一键回填）。

        仅处理 SOF MPDU 帧（接入指示=1 且定界符类型=1），信标/SACK/NET 或非 MPDU
        输入返回空列表。PB 布局与 _parse_pb_block 同口径：物理块个数取 FC
        （BPLC=byte7 低4位；ISAC=byte4[2-5]）；PB 起始偏移在 {16, 32} 中按帧长
        一致性判定（32=含 eFC）；PB 大小 = (帧长-起始)/个数 且须落在
        PB_SIZE_CANDIDATES 内。返回 [(pbcs_offset, crc24_value, pb_index), ...]，
        pbcs_offset 为 3 字节 PBCS 位置（小端写回）；截断的物理块（尾部不足 3 字节）
        不纳入计划。
        """
        fills = []
        frame_len = len(frame_bytes)
        if frame_len < 20:
            return fills
        b0 = frame_bytes[0]
        if (b0 >> 3) & 0x01 != 1 or (b0 & 0x07) != 1:
            return fills  # 非 SOF MPDU
        std_version = (frame_bytes[12] >> 4) & 0x0F
        if std_version == 2:
            pb_count = (frame_bytes[4] >> 2) & 0x0F   # ISAC 表23
        else:
            pb_count = frame_bytes[7] & 0x0F          # BPLC 表20
        if pb_count < 1 or pb_count > 8:
            return fills
        for start in (16, 32):
            remain = frame_len - start
            if remain <= 0 or remain % pb_count:
                continue
            pb_size = remain // pb_count
            if pb_size not in CSGNewGenParser.PB_SIZE_CANDIDATES:
                continue
            for i in range(pb_count):
                pb_off = start + i * pb_size
                pbcs_off = pb_off + pb_size - 3
                if pbcs_off + 3 > frame_len:
                    break  # 截断块不填
                fills.append((pbcs_off, self._crc24(frame_bytes[pb_off:pbcs_off]), i))
            return fills  # 首个自洽布局即生效
        return fills

    def _mac_plausible(self, data: bytes) -> bool:
        """重组后的 PB 体是否具备 MAC 帧特征的粗判（噪声载荷不输出伪解析行）。

        判据（表12 / MSDU 头约定）：
        - 字节0 帧头类型(1b)∈{0,1} 且 版本(2b)∈{1,2}；
        - 版本2 单跳帧：字节1 MSDU类型∈{0x01,0x02,0x80} 且 4+MSDU长度+4(CRC-32)≤总长；
        - 版本1：MSDU 短头(12B头)/长头(32B头) 的 VLAN+类型合法，
          或载荷带应用层特征(0x11/0x13 + 0x0101)，或管理消息特征扫描命中。
        """
        if len(data) < 8:
            return False
        b0 = data[0]
        header_type = b0 & 0x01
        version = (b0 >> 1) & 0x03
        if header_type not in (0, 1) or version not in (1, 2):
            return False
        if version == 2:
            msdu_type = data[1]
            msdu_len = int.from_bytes(data[2:4], 'little')
            return msdu_type in (0x01, 0x02, 0x80) and 4 + msdu_len + 4 <= len(data)
        hdr = 32 if header_type == 0 else 12
        payload = data[hdr:]
        if len(payload) >= 3 and payload[0] in (0x11, 0x13) \
                and ((payload[1] << 8) | payload[2]) == 0x0101:
            return True
        if hdr == 12 and len(payload) >= 2:
            vlan, mtype = payload[0], payload[1]
            if (0 <= vlan <= 3 and mtype in (0x01, 0x02, 0x80)) \
                    or (vlan == 0x81 and mtype == 0x00):
                return True
        if hdr == 32 and len(payload) >= 18:
            vlan = int.from_bytes(payload[12:16], 'little')
            mtype = int.from_bytes(payload[16:18], 'little')
            if (0 <= vlan <= 3 and mtype in (0x01, 0x02, 0x80)) \
                    or (vlan == 0x8100 and mtype == 0x88E1):
                return True
        if len(payload) >= 2:
            return self._scan_mgmt_msdu_offset(payload, max_scan=32) is not None
        return False

    def _concat_to_orig(self, idx: int) -> int:
        """重组 concat 索引 → 原始帧偏移（按 PB 体分段翻译）。

        多 PB 重组后各 PB 体在 concat 中连续，但在原始帧中被
        PBH(4B)+保留(1B)+PBCS(3B) 隔开；重组解析产生的行偏移必须
        分段翻译回原始帧，否则点击行高亮错位。
        """
        segs = getattr(self, '_concat_segments', None)
        if not segs:
            return idx
        for cs, ce, os_ in segs:
            if cs <= idx < ce:
                return os_ + (idx - cs)
        if idx < segs[0][0]:
            return segs[0][2] + idx - segs[0][0]
        cs, ce, os_ = segs[-1]
        return os_ + (idx - cs)

    def _remap_concat_rows(self, rows: list) -> list:
        """将 concat 空间行偏移翻译回原始帧（origin 为第一 PB 体起始；
        偏移为 None 的行原样保留；单 PB 时映射为恒等）"""
        origin = getattr(self, '_concat_origin', 0)
        out = []
        for r in rows:
            if (
                isinstance(r, (tuple, list))
                and len(r) >= 6
                and r[4] is not None
                and r[5] is not None
            ):
                r = (
                    r[0], r[1], r[2], r[3],
                    self._concat_to_orig(r[4] - origin),
                    self._concat_to_orig(r[5] - origin),
                )
            out.append(r)
        return out

    def _parse_pb_block(self, frame_bytes: bytes, offset: int,
                        table_data: list, frame_len: int):
        """解析物理块(PB)：PB头(4B) + PB体(MAC帧) + 保留 + PBCS(3B)

        供 fc_pb 模式(完整MPDU，offset=FC末尾16) 与 pb_only 模式(仅PB，offset=0) 复用。
        物理块头为 4 字节（第4部分表47）：序号(16b)+聚合标志(1b)+保留(15b)。
        支持多物理块重组：MAC帧可跨多个PB，需拼接所有PB体为完整MAC帧后再解析MSDU。
        返回 (new_offset, mac_data, msdu_payload)。
        """
        pb_hdr_len = 4
        pb_count = getattr(self, '_pb_count', 1)
        if pb_count < 1:
            pb_count = 1
        is_hrf = getattr(self, '_channel', 'plc') == 'hrf'
        # HRF 无线 / ISAC Bitloading 模式: FC 可变区域显式给出PB大小, 优先使用
        if hasattr(self, '_pb_size') and isinstance(self._pb_size, int):
            pb_total_size = self._pb_size
        else:
            # CMT/TMI 映射值只是先验，与帧长不符时按帧长一致性覆盖（不静默改判，
            # 覆盖时在表格中追加一行提示，便于核对推断依据）
            cmt_size = self._get_pb_size(
                getattr(self, '_cmt_index', 4),
                getattr(self, '_std_version', 1))
            pb_total_size, pb_size_overridden = self._infer_pb_size(
                offset, pb_count, frame_len, cmt_size)
            if pb_size_overridden:
                table_data.append((
                    "PB大小推断",
                    str(cmt_size),
                    str(pb_total_size),
                    f"CMT映射PB={cmt_size}字节与帧长不符，按 offset({offset})"
                    f"+物理块个数({pb_count})×PB大小==帧长({frame_len}) "
                    f"推断为{pb_total_size}字节",
                    None, None
                ))
        pb_body_size = self._get_pb_body_size(pb_total_size)

        # 遍历所有PB：每块行先缓存，循环后按「PBH → 块体 → 保留/PBCS」逐块交错发射，
        # 避免多PB帧的块体合并成一行堆在表格末尾；同时拼接所有PB体为 mac_concat
        mac_concat = b''
        pb_body_offset = offset + pb_hdr_len  # 第一个PB体起始（MAC帧头所在）
        pb_agg_flag = 0
        multi = pb_count > 1
        pb_sections = []
        for i in range(pb_count):
            pb_off = offset + i * pb_total_size
            pb_data = frame_bytes[pb_off:pb_off + pb_total_size]
            if len(pb_data) < pb_hdr_len:
                break
            pb_seq = int.from_bytes(pb_data[0:2], 'little')
            if i == 0:
                pb_agg_flag = pb_data[2] & 0x01
            pb_agg_desc = "物理块中有多个MAC帧，物理块体中有级联头" if pb_agg_flag else "物理块中只有一个MAC帧，物理块体中没有级联头"
            tag = f"[{i}]" if multi else ""
            head_rows = [
                (
                    f"物理块头{tag}",
                    ' '.join(f'{b:02X}' for b in pb_data[0:pb_hdr_len]),
                    f"序列号:{pb_seq}, 聚合标志:{pb_agg_flag}",
                    f"物理块头{tag}: {pb_agg_desc}",
                    pb_off, pb_off + pb_hdr_len - 1
                ),
                (
                    f"  序列号{tag}",
                    ' '.join(f'{b:02X}' for b in pb_data[0:2]),
                    str(pb_seq),
                    f"MPDU载荷中物理块{tag}的序号",
                    pb_off, pb_off + 1
                ),
                (
                    f"  聚合标志{tag}",
                    f"0b{pb_agg_flag}",
                    str(pb_agg_flag),
                    pb_agg_desc,
                    pb_off + 2, pb_off + 2
                ),
            ]
            pb_reserved = ((pb_data[2] >> 1) & 0x7F) | (pb_data[3] << 7)
            head_rows.append((
                f"  保留{tag}",
                f"0x{pb_reserved:04X}",
                str(pb_reserved),
                "保留",
                pb_off + 2, pb_off + 3
            ))
            # PB体（不足补0）
            raw_body = pb_data[pb_hdr_len:pb_hdr_len + pb_body_size]
            actual_body_len = len(raw_body)
            body = raw_body
            if actual_body_len < pb_body_size:
                body = raw_body + b'\x00' * (pb_body_size - actual_body_len)
            mac_concat += body
            # PBCS: 保留1字节 + 检查序列3字节（行缓存，待块体行之后发射）
            pbcs_rows = []
            pbcs_off = pb_off + pb_hdr_len + pb_body_size
            if pbcs_off + 1 <= frame_len:
                # 保留字节单独成行（R7），便于在 UI 中逐字节核对 CRC-24 计算范围
                pbcs_rows.append((
                    f"  保留{tag}(PB尾)",
                    f"0x{frame_bytes[pbcs_off]:02X}",
                    str(frame_bytes[pbcs_off]),
                    "保留字节，计入PBCS校验范围",
                    pbcs_off, pbcs_off
                ))
            if pbcs_off + 4 <= frame_len:
                pbcs_data = frame_bytes[pbcs_off + 1:pbcs_off + 4]
                stored = int.from_bytes(pbcs_data, 'little')
                # CRC-24 计算范围 = 物理块头 + 物理块体 + 保留（表49「物理块检查序列」），
                # 用帧内真实字节计算，不用零填充后的 body
                calc = self._crc24(frame_bytes[pb_off:pbcs_off + 1])
                crc_len = pbcs_off + 1 - pb_off
                if calc == stored:
                    parsed = f"0x{stored:06X}，校验通过"
                    desc = (f"物理块{tag}CRC-24(物理块头+物理块体+保留共{crc_len}字节)，"
                            f"校验通过")
                elif stored == 0:
                    # 采集/发射机接口普遍不提供 PBCS（整帧置零），单列一态避免满屏误报
                    parsed = "0x000000(置零)"
                    desc = (f"物理块{tag}CRC-24计算值=0x{calc:06X}，存储PBCS=0x000000："
                            f"PBCS置零/采集接口未提供，非校验失败")
                else:
                    parsed = f"0x{stored:06X}"
                    desc = (f"物理块{tag}CRC-24(物理块头+物理块体+保留共{crc_len}字节)，"
                            f"校验失败(计算值=0x{calc:06X})")
                pbcs_rows.append((
                    f"物理块检查序列{tag}",
                    ' '.join(f'{b:02X}' for b in pbcs_data),
                    parsed,
                    desc,
                    pbcs_off + 1, pbcs_off + 3
                ))
            else:
                # 帧截断：尾部不足 保留1+PBCS3 共4字节 → 不计算、不抛异常（R6）
                _t_start = pbcs_off if pbcs_off < frame_len else None
                _t_end = frame_len - 1 if pbcs_off < frame_len else None
                pbcs_rows.append((
                    f"物理块检查序列{tag}",
                    "",
                    "PBCS缺失(帧截断)",
                    f"物理块{tag}尾部不足4字节(保留1+PBCS3)，无法校验",
                    _t_start, _t_end
                ))
            pb_sections.append((tag, head_rows, pb_off, actual_body_len, pbcs_rows))

        # ── 多 PB 重组偏移映射：concat 区间 → 原始帧 PB 体起始 ──
        # （mac_concat 按 pb_body_size 逐块拼接，含截断块的零填充）
        segments = []
        _cs = 0
        for _tag, _heads, _pb_off, _body_len, _pbcs in pb_sections:
            segments.append((_cs, _cs + pb_body_size, _pb_off + pb_hdr_len))
            _cs += pb_body_size
        self._concat_segments = segments
        self._concat_origin = pb_body_offset

        # 重组后判定 PB 体能否按 MAC 帧解析：噪声载荷只按原始报文展示，不输出伪解析行
        is_beacon = getattr(self, '_delimiter_type', 1) == 0
        if not mac_concat:
            mac_plausible = False
        elif is_beacon or pb_agg_flag:
            mac_plausible = True  # 信标载荷/聚合帧走各自既有解析分支
        else:
            mac_plausible = self._mac_plausible(mac_concat)

        # 逐块交错发射：物理块头 → 物理块体 → 保留(PB尾)/物理块检查序列
        for tag, head_rows, pb_off, actual_body_len, pbcs_rows in pb_sections:
            table_data.extend(head_rows)
            body_start = pb_off + pb_hdr_len
            body_bytes = frame_bytes[body_start:body_start + actual_body_len]
            if is_beacon:
                body_desc = "信标帧载荷（无MAC头）"
            elif pb_agg_flag:
                body_desc = "聚合帧载荷（级联头+MAC帧）"
            elif mac_plausible:
                body_desc = f"承载MAC帧数据{'(多PB重组)' if multi else ''}"
            else:
                body_desc = f"无法按MAC帧解析，原始报文展示{'(多PB重组后仍不符)' if multi else ''}"
            table_data.append((
                f"物理块体{tag}",
                ' '.join(f'{b:02X}' for b in body_bytes[:32]) + ("..." if actual_body_len > 32 else ""),
                f"{actual_body_len}字节",
                body_desc,
                body_start, body_start + actual_body_len - 1
            ))
            table_data.extend(pbcs_rows)

        mac_data = None
        if mac_concat:
            if pb_agg_flag:
                # 聚合帧：级联头 + MAC帧
                # 聚合帧的级联块各自解析应用层，主流程不应再对整帧做MSDU兜底
                self._aggregated = True
                cascade_offset = 0
                cascade_idx = 0
                while cascade_offset + 2 <= len(mac_concat):
                    cascade_hdr = mac_concat[cascade_offset:cascade_offset + 2]
                    cascade_len = int.from_bytes(cascade_hdr, 'little') & 0x0FFF
                    start_flag = (cascade_hdr[1] >> 4) & 0x01
                    end_flag = (cascade_hdr[1] >> 5) & 0x01
                    table_data.append((
                        f"  级联头({cascade_idx})",
                        ' '.join(f'{b:02X}' for b in cascade_hdr),
                        f"长度:{cascade_len}, 起始:{start_flag}, 结束:{end_flag}",
                        f"级联数据块长度:{cascade_len}字节",
                        self._concat_to_orig(cascade_offset),
                        self._concat_to_orig(cascade_offset + 1)
                    ))
                    cascade_offset += 2
                    if cascade_offset + cascade_len <= len(mac_concat):
                        mac_seg = mac_concat[cascade_offset:cascade_offset + cascade_len]
                        _, mac_table = self._parse_mac_frame(
                            mac_seg, base_offset=pb_body_offset + cascade_offset,
                            parse_msdu_app=True)
                        table_data.extend(self._remap_concat_rows(mac_table))
                        cascade_offset += cascade_len
                        cascade_idx += 1
                        if end_flag:
                            break
                    else:
                        break
                if cascade_offset < len(mac_concat):
                    remaining = mac_concat[cascade_offset:]
                    table_data.append((
                        "  级联后剩余数据",
                        ' '.join(f'{b:02X}' for b in remaining[:30]) + ("..." if len(remaining) > 30 else ""),
                        f"{len(remaining)}字节",
                        "级联帧解析后的剩余数据",
                        self._concat_to_orig(cascade_offset),
                        self._concat_to_orig(len(mac_concat) - 1)
                    ))
            elif mac_plausible:
                # 单MAC帧（可能跨多PB）
                # 应用层由主流程兜底解析（MSDU头展示 + 分派），此处仅解析MAC头
                self._aggregated = False
                mac_data = mac_concat
                mac_end, mac_table = self._parse_mac_frame(mac_data, base_offset=pb_body_offset)
                table_data.extend(self._remap_concat_rows(mac_table))
                # 填充（MAC帧末尾在最后一个PB体内的位置）
                padding_start = mac_end - pb_body_offset
                if padding_start < len(mac_concat):
                    padding = mac_concat[padding_start:]
                    desc = f"物理块填充({len(padding)}字节，{'全0x00' if all(b==0 for b in padding) else '含非零值'})"
                    table_data.append((
                        "物理块填充",
                        ' '.join(f'{b:02X}' for b in padding[:20]) + ("..." if len(padding) > 20 else ""),
                        f"{len(padding)}字节",
                        desc,
                        self._concat_to_orig(padding_start),
                        self._concat_to_orig(len(mac_concat) - 1)
                    ))
                actual_mac_len = mac_end - pb_body_offset
                mac_data = mac_concat[:actual_mac_len]
            else:
                # 噪声载荷：重组体不符 MAC 帧特征，块体已逐块原始展示，不再输出伪解析行
                self._aggregated = False
                table_data.append((
                    "MAC重组解析", "", "无法解析",
                    "重组后的物理块体不符MAC帧特征(帧头类型/版本/MSDU类型/长度越界)，"
                    "上方各物理块体已按原始报文展示",
                    None, None
                ))

        mac_hdr_len = 12
        if mac_data and ((mac_data[0] >> 1) & 0x03) == 2:
            mac_hdr_len = 4  # 版本2 单跳帧（仅无线，表12）：4字节头
        elif mac_data and (mac_data[0] & 0x01) == 0:
            mac_hdr_len = 32
        if getattr(self, '_delimiter_type', 1) == 0:
            msdu_payload = mac_concat
        elif mac_hdr_len == 4:
            # 版本2 单跳帧：MSDU类型在MAC头内，载荷已由 _parse_mac_frame 内联解析
            msdu_payload = b""
        elif mac_data is not None and len(mac_data) >= 4:
            msdu_len = int.from_bytes(mac_data[2:4], 'little')
            msdu_payload = mac_data[mac_hdr_len:mac_hdr_len + msdu_len]
        elif mac_data is not None:
            msdu_payload = mac_data[mac_hdr_len:]
        else:
            # 无PB体/噪声载荷：不做整帧兜底，避免对MPDU原始字节输出伪MSDU/应用层行
            msdu_payload = b""
        offset += pb_hdr_len + mac_hdr_len
        return offset, mac_data, msdu_payload

    def _detect_channel(self, frame_bytes: bytes, frame_len: int) -> str:
        """MPDU 通道自动识别（plc/hrf），只读 FC 前16字节，无表副作用。

        协议未在 FC 中标记信道（表17 标准版本号仅区分 BPLC/ISAC-PLC），
        但 SOF 帧可变区域在 PLC/HRF 下字段布局不同（表20 BPLC / 表23 ISAC /
        表45 HRF）：按各假设预测的 MPDU 帧长与实际帧长比对，命中者胜。

        强信号优先：
          - 载荷PB大小=40 → HRF（表44 值1 为 HRF 独有，PLC 无 40 字节 PB）
          - 物理块个数>1 → PLC（无线信道仅支持 1 个物理块，图6）
        平局/都不命中 → 默认 plc（与历史行为一致）。
        """
        if frame_len < 16:
            return 'plc'
        delim = frame_bytes[0] & 0x07
        if delim != 1:  # 仅 SOF 帧可变区域可可靠判别；信标/SACK/NET 默认 plc
            return 'plc'
        var = frame_bytes[1:12]
        std_version = (frame_bytes[12] >> 4) & 0x0F

        # HRF 假设（表45）: 载荷PB大小 = byte6[4-7]（表44: 0=16,1=40,2=72,3=136,4=264,5=520）
        hrf_pb = CSGNewGenParser.HRF_PB_SIZE_TABLE.get((var[5] >> 4) & 0x0F, 136)
        if hrf_pb == 40:  # 40 字节 PB 仅 HRF 支持（表44 值1）
            return 'hrf'
        hrf_len = 16 + hrf_pb

        # PLC 假设
        if std_version == 1:
            # BPLC（表20）: 物理块个数 = byte7[0-3], 载波映射表索引 = byte7[4-7] (136/520)
            cnt = var[6] & 0x0F
            tmi = (var[6] >> 4) & 0x0F
            pb = 520 if tmi in (0xD, 15) else 136
            plc_len = 16 + cnt * pb
        else:
            # ISAC-PLC（表23 数据帧）: 物理块个数 = byte4[2-5], TMI = byte6[1-5]
            # (0=136,1=520,2=72,3=264)
            cnt = (var[3] >> 2) & 0x0F
            tmi = (var[5] >> 1) & 0x1F
            pb = {0: 136, 1: 520, 2: 72, 3: 264}.get(tmi, 136)
            plc_len = 16 + cnt * pb

        hr_m = (hrf_len == frame_len)
        pl_m = (plc_len == frame_len)
        if hr_m and not pl_m:
            return 'hrf'
        if pl_m and not hr_m:
            return 'plc'
        # 平局/都不命中: 用强信号打破; 无线仅支持1个物理块（图6）
        if cnt > 1:
            return 'plc'
        return 'plc'  # 默认 plc（与历史行为一致）

    def _parse_mpdu_frame(self, frame_bytes: bytes, base_offset: int = 0) -> Tuple[int, list]:
        """解析 MPDU 帧控制（FC）头部，16字节"""
        table = []
        offset = base_offset

        if len(frame_bytes) < 16:
            table.append(("❌ MPDU解析失败", "", "", "MPDU帧长度不足(<16字节)", None, None))
            return offset, table

        # ── 字节0: 定界符类型(3b) + 接入指示(1b) + 短网络标识低位(4b) ──
        b0 = frame_bytes[offset]
        delimiter_type = b0 & 0x07
        access_indicator = (b0 >> 3) & 0x01
        short_nid_low = (b0 >> 4) & 0x0F

        delimiter_name = self.DELIMITER_TYPE_MAP.get(delimiter_type, f"保留(0x{delimiter_type:X})")
        table.append((
            "定界符类型",
            f"0b{delimiter_type:03b}",
            str(delimiter_type),
            f"{delimiter_name}",
            offset, offset
        ))
        table.append((
            "接入指示",
            f"0b{access_indicator}",
            str(access_indicator),
            "宽带载波通信接入网络" if access_indicator else "保留",
            offset, offset
        ))
        table.append((
            "短网络标识低位(SNID)",
            f"0x{short_nid_low:X}",
            str(short_nid_low),
            f"SNID低4位: {short_nid_low}",
            offset, offset
        ))
        offset += 1
        # 提前读取标准版本号，供可变区域解析载波映射表索引时使用
        self._std_version = (frame_bytes[base_offset + 12] >> 4) & 0x0F

        # 对于SACK帧，提前读取扩展帧类型以确定可变区域格式
        sack_ext_type = None
        if delimiter_type == 2:
            sack_ext_type = frame_bytes[base_offset + 12] & 0x0F

        # ── 字节1-11: 可变区域（取决于定界符类型和通道）──
        var_start = offset
        is_hrf = getattr(self, '_channel', 'plc') == 'hrf'
        if delimiter_type == 1:  # SOF帧
            if is_hrf:
                # HRF 无线 SOF 帧可变区域
                offset = self._parse_mpdu_sof_hrf(frame_bytes, offset, table)
            else:
                # 先解析字节12获取版本号以确定可变区域的格式
                std_version = (frame_bytes[base_offset + 12] >> 4) & 0x0F
                if std_version == 1:  # BPLC版本
                    offset = self._parse_mpdu_sof_bplc(frame_bytes, offset, table)
                elif std_version == 2:  # ISAC-PLC版本
                    offset = self._parse_mpdu_sof_isac(frame_bytes, offset, table)
                else:
                    # 未知版本，跳过可变区域
                    raw_var = ' '.join(f'{b:02X}' for b in frame_bytes[offset:offset+11])
                    table.append((
                        "可变区域(SOF)",
                        raw_var,
                        "11字节",
                        f"未知版本{std_version}",
                        offset, offset + 10
                    ))
                    offset = base_offset + 12
        elif delimiter_type == 0:  # 信标帧
            if is_hrf:
                offset = self._parse_mpdu_beacon_hrf(frame_bytes, offset, table)
            else:
                offset = self._parse_mpdu_beacon(frame_bytes, offset, table)
        elif delimiter_type == 2:  # 选择确认帧(SACK)
            if is_hrf:
                offset = self._parse_mpdu_sack_hrf(frame_bytes, offset, table)
            else:
                # 根据扩展帧类型选择可变区域解析方式
                # 表 33: 0=标准SACK, 1=网络搜索帧(抄控器), 2=同步帧(抄控器), 3=Bitloading扩展帧
                if sack_ext_type == 0:
                    # 标准选择确认帧
                    offset = self._parse_mpdu_sack(frame_bytes, offset, table)
                elif sack_ext_type == 3:
                    # Bitloading扩展帧: 可变区域按Bitloading扩展帧格式解析
                    offset = self._parse_mpdu_sack_bitloading(frame_bytes, offset, table)
                elif sack_ext_type in (1, 2):
                    # 抄控器帧(网络搜索帧/同步帧): 协议文档未提供可变区域详细字段表，按原始字节展示
                    raw_var = ' '.join(f'{b:02X}' for b in frame_bytes[offset:offset + 11])
                    ext_name = self.SACK_EXT_TYPE_MAP.get(sack_ext_type, f"保留({sack_ext_type})")
                    table.append((
                        f"可变区域({ext_name})",
                        raw_var,
                        "11字节",
                        f"抄控器帧可变区域，协议未提供详细字段定义(扩展帧类型={sack_ext_type})",
                        offset, offset + 10
                    ))
                    offset = base_offset + 12
                else:
                    # 保留值: 协议未定义，按原始字节展示，避免误解析为标准SACK
                    raw_var = ' '.join(f'{b:02X}' for b in frame_bytes[offset:offset + 11])
                    table.append((
                        f"可变区域(保留={sack_ext_type})",
                        raw_var,
                        "11字节",
                        f"扩展帧类型为保留值({sack_ext_type})，按原始字节展示",
                        offset, offset + 10
                    ))
                    offset = base_offset + 12
        elif delimiter_type == 3:  # 网间协调帧(表41)
            offset = self._parse_mpdu_net(frame_bytes, offset, table)
        else:  # 保留类型
            raw_var = ' '.join(f'{b:02X}' for b in frame_bytes[offset:offset+12])
            table.append(("可变区域", raw_var[:80] + "..." if len(raw_var) > 80 else raw_var, "12字节",
                         f"定界符类型{delimiter_type}的可变数据(未解析)", offset, offset + 11))
            offset += 12

        # ── 字节12: 公共字段（定界符类型不同含义不同）──
        offset = base_offset + 12  # 确保对齐
        b12 = frame_bytes[offset]
        std_version = (b12 >> 4) & 0x0F
        self._std_version = std_version
        version_name = MPDU_VERSION_MAP.get(std_version, f"保留({std_version})")

        if delimiter_type == 2:
            # SACK帧: 字节12 = 扩展帧类型(4b) + 标准版本号(4b)
            ext_type = b12 & 0x0F
            ext_name = self.SACK_EXT_TYPE_MAP.get(ext_type, f"保留({ext_type})")
            table.append((
                "扩展帧类型",
                f"0x{ext_type:X}",
                str(ext_type),
                f"帧类型: {ext_name}",
                offset, offset
            ))
        elif delimiter_type == 1 and std_version == 1:
            # BPLC SOF帧: 字节12 bit 0-3 = 扩展载波映射表索引（表20）
            ext_cmt = b12 & 0x0F
            table.append((
                "扩展载波映射表索引",
                f"0x{ext_cmt:X}",
                str(ext_cmt),
                f"扩展载波映射表索引: {ext_cmt}",
                offset, offset
            ))
        elif delimiter_type == 1 and std_version == 2:
            # ISAC-PLC SOF帧: 字节12 bit 0 = 短网络标识高位（表23/24/25/26）
            short_nid_high = b12 & 0x01
            full_snid = (short_nid_high << 4) | short_nid_low
            table.append((
                "短网络标识高位",
                f"0b{short_nid_high}",
                str(short_nid_high),
                f"完整SNID=0x{full_snid:02X}({full_snid})",
                offset, offset
            ))
        elif delimiter_type == 3:
            # 网间协调帧: 字节12 bit 0 = 短网络标识高位（表41）
            short_nid_high = b12 & 0x01
            full_snid = (short_nid_high << 4) | short_nid_low
            table.append((
                "短网络标识高位",
                f"0b{short_nid_high}",
                str(short_nid_high),
                f"完整SNID=0x{full_snid:02X}({full_snid})",
                offset, offset
            ))
        # 信标帧(delimiter_type==0): 字节12 bit 0 是符号数bit8，bit 1 才是SNID高位，
        # SNID高位已在 _parse_mpdu_beacon 中处理，此处不再添加。

        table.append((
            "标准版本号",
            f"0x{std_version:X}",
            str(std_version),
            version_name,
            offset, offset
        ))
        offset += 1

        # ── 字节13-15: FC校验序列 (24-bit CRC) ──
        fcs_bytes = frame_bytes[offset:offset + 3]
        fcs_val = int.from_bytes(fcs_bytes, 'little')  # 小端序
        # CRC-24 校验：计算范围 FC 前13字节（字节0-12）
        fc_data_for_crc = frame_bytes[base_offset:base_offset + 13]
        crc24_calc = self._crc24(fc_data_for_crc)
        crc24_match = (crc24_calc == fcs_val)
        fcs_desc = f"24位CRC校验FC前13字节，FCS=0x{fcs_val:06X}"
        fcs_desc += "，校验通过" if crc24_match else f"，校验失败(计算值=0x{crc24_calc:06X})"
        table.append((
            "FC校验序列(FCS)",
            ' '.join(f'{b:02X}' for b in fcs_bytes),
            f"0x{fcs_val:06X}",
            fcs_desc,
            offset, offset + 2
        ))
        offset += 3

        # ── 通道判别结果（MPDU 级输入一律按 FC 判别，下拉通道仅作提示）──
        if getattr(self, '_detected_channel', None) is not None:
            ch = self._detected_channel
            ch_name = "PLC 载波" if ch == "plc" else "HRF 高速无线"
            table.append((
                "通道判定",
                ch,
                ch_name,
                "按FC可变区域结构判别（帧长一致性+PB大小/物理块个数强信号），"
                "下拉通道仅作提示",
                0, 15
            ))

        return offset, table

    def _parse_mpdu_sof_bplc(self, frame_bytes: bytes, offset: int, table: list) -> int:
        """解析 BPLC 版本 SOF 帧可变区域 (字节1-11)"""
        # 源TEI (12b: byte1[0:7] + byte2[0:3])
        src_tei = frame_bytes[offset] | ((frame_bytes[offset + 1] & 0x0F) << 8)
        table.append(("源TEI", f"0x{src_tei:03X}", str(src_tei),
                     f"发送站点TEI: {src_tei}", offset, offset + 1))

        # 目的TEI (12b: byte2[4:7] + byte3[0:7])
        dst_tei = ((frame_bytes[offset + 1] >> 4) & 0x0F) | (frame_bytes[offset + 2] << 4)
        table.append(("目的TEI", f"0x{dst_tei:03X}", str(dst_tei),
                     f"接收站点TEI: {dst_tei}", offset + 1, offset + 2))

        # 链路标识符 (8b: byte4[0:7])
        link_id = frame_bytes[offset + 3]
        table.append(("链路标识符", f"0x{link_id:02X}", str(link_id),
                     f"优先级/业务分类: {link_id}", offset + 3, offset + 3))

        # 短网络标识高位(1b) + 保留(15b): byte5[0] + byte5[1:7] + byte6[0:7]
        short_nid_low = (frame_bytes[offset - 1] >> 4) & 0x0F
        short_nid_high = frame_bytes[offset + 4] & 0x01
        full_snid = (short_nid_high << 4) | short_nid_low
        table.append(("短网络标识高位",
                     f"0b{short_nid_high}",
                     str(short_nid_high),
                     f"SNID高1位, 完整SNID=0x{full_snid:02X}({full_snid})",
                     offset + 4, offset + 4))

        # 物理块个数(4b) + 载波映射表索引(4b): byte7[0:3] + byte7[4:7]
        b7 = frame_bytes[offset + 6]
        pb_count = b7 & 0x0F
        cmt_index = (b7 >> 4) & 0x0F
        table.append(("物理块个数", f"0x{pb_count:X}", str(pb_count),
                     f"{pb_count}个物理块", offset + 6, offset + 6))
        self._pb_count = pb_count
        pb_size = self._get_pb_size(cmt_index, self._std_version)
        table.append(("载波映射表索引", f"0x{cmt_index:X}", str(cmt_index),
                     f"载波映射表索引: {cmt_index}, PB大小: {pb_size}字节", offset + 6, offset + 6))

        # 帧长(12b): byte8[0:7] + byte9[0:3]
        frame_len_pb = frame_bytes[offset + 7] | ((frame_bytes[offset + 8] & 0x0F) << 8)
        table.append(("帧长", f"0x{frame_len_pb:03X}", f"{frame_len_pb * 10}μs",
                     f"占用信道时长: {frame_len_pb * 10}μs", offset + 7, offset + 8))

        # 保留(9b) + TEI过滤标志(1b) + 重传标志(1b) + 符号数(9b): byte9[4:7]+byte10[0:4] + byte10[5]+byte10[6]+byte10[7]+byte11[0:7]
        tei_filter = (frame_bytes[offset + 9] >> 5) & 0x01
        retransmit = (frame_bytes[offset + 9] >> 6) & 0x01
        symbol_count = ((frame_bytes[offset + 9] >> 7) & 0x01) | (frame_bytes[offset + 10] << 1)
        table.append(("TEI过滤标志", f"0b{tei_filter}", str(tei_filter),
                     "不过滤" if tei_filter else "过滤", offset + 9, offset + 9))
        table.append(("重传标志", f"0b{retransmit}", str(retransmit),
                     "重传报文" if retransmit else "非重传", offset + 9, offset + 9))
        table.append(("符号数", f"0x{symbol_count:03X}", str(symbol_count),
                     f"OFDM符号数: {symbol_count}", offset + 9, offset + 10))

        # 存储cmt_index供后续物理块解析使用
        self._cmt_index = cmt_index
        return offset + 11

    def _parse_mpdu_sof_isac(self, frame_bytes: bytes, offset: int, table: list) -> int:
        """解析 ISAC-PLC 版本 SOF 帧可变区域 (字节1-11)"""
        # 源TEI (12b)
        src_tei = frame_bytes[offset] | ((frame_bytes[offset + 1] & 0x0F) << 8)
        table.append(("源TEI", f"0x{src_tei:03X}", str(src_tei),
                     f"发送站点TEI", offset, offset + 1))

        # 目的TEI (12b)
        dst_tei = ((frame_bytes[offset + 1] >> 4) & 0x0F) | (frame_bytes[offset + 2] << 4)
        table.append(("目的TEI", f"0x{dst_tei:03X}", str(dst_tei),
                     f"接收站点TEI", offset + 1, offset + 2))

        # 字节4: bit0 = 多站点帧标识
        b4 = frame_bytes[offset + 3]
        multi_site = b4 & 0x01
        table.append(("多站点帧标识", f"0b{multi_site}", str(multi_site),
                     "多站点帧(OFDMA)" if multi_site else "单站点帧", offset + 3, offset + 3))

        if multi_site:
            # OFDMA帧时 byte4 bit1-7 为 OFDMA专用字段（在下方OFDMA块解析）
            pass
        else:
            # 非OFDMA: bit1=训练帧标识
            training = (b4 >> 1) & 0x01
            table.append(("训练帧标识", f"0b{training}", str(training),
                         "训练帧" if training else "数据帧", offset + 3, offset + 3))
            if training:
                # 训练帧(表24/25): byte4 bit2-7 = PL符号数(6b)
                pl_sym_cfg = (b4 >> 2) & 0x3F
                train_type_peek = frame_bytes[offset + 4] & 0x01
                if train_type_peek:
                    pl_desc = f"Bitloading训练帧, 实际PL符号数: {2 * pl_sym_cfg + 1}"
                else:
                    pl_desc = "MIMO训练帧固定填0"
                table.append(("PL符号数", f"0x{pl_sym_cfg:02X}", str(pl_sym_cfg),
                             pl_desc, offset + 3, offset + 3))
                self._pb_count = 0  # 训练帧不携带物理块
            else:
                # 数据帧(表23): bit2-5=PB数, bit6-7=流数
                pb_count = (b4 >> 2) & 0x0F
                streams = (b4 >> 6) & 0x03
                table.append(("物理块个数", f"0x{pb_count:X}", str(pb_count),
                             f"{pb_count}个PB", offset + 3, offset + 3))
                self._pb_count = pb_count
                table.append(("流数", f"0x{streams:X}", str(streams),
                             f"{streams + 1}流", offset + 3, offset + 3))

        # 存储OFDMA相关状态供后续eFC解析使用
        self._ofdma_frame_type = -1  # -1=非OFDMA
        self._ofdma_station_count = 0
        self._efc_symbol_count = 0

        if multi_site:
            # ── OFDMA帧 (表26) ──
            b4 = frame_bytes[offset + 3]
            ofdma_type = (b4 >> 1) & 0x03
            band_id = (b4 >> 3) & 0x07
            station_count = ((b4 >> 6) & 0x03) + 1
            self._ofdma_frame_type = ofdma_type
            self._ofdma_station_count = station_count
            OFDMA_TYPE_MAP = {0: "DL-OFDMA帧", 1: "DL-OFDMA SACK/UL-OFDMA帧",
                              2: "UL-OFDMA trigger帧", 3: "UL-OFDMA SACK帧"}
            table.append(("OFDMA帧类型", f"0b{ofdma_type:02b}", str(ofdma_type),
                         OFDMA_TYPE_MAP.get(ofdma_type, f"保留({ofdma_type})"),
                         offset + 3, offset + 3))
            table.append(("频段标识", f"0x{band_id:X}", str(band_id),
                         f"频段{band_id}", offset + 3, offset + 3))
            table.append(("站点数", f"0x{station_count:X}", str(station_count),
                         f"{station_count}个站点", offset + 3, offset + 3))
            # eFC符号个数(2b) + 保留(6b)
            b5 = frame_bytes[offset + 4]
            efc_sym_cfg = b5 & 0x03
            efc_sym_map = {0: 2, 1: 4, 2: 8, 3: 12}
            self._efc_symbol_count = efc_sym_map.get(efc_sym_cfg, 2)
            table.append(("eFC符号个数", f"0b{efc_sym_cfg:02b}", str(self._efc_symbol_count),
                         f"{self._efc_symbol_count}个eFC符号", offset + 4, offset + 4))
            # PL符号数(9b): byte6[0:7]+byte7[0]
            b6 = frame_bytes[offset + 5]
            b7 = frame_bytes[offset + 6]
            pl_symbols = b6 | ((b7 & 0x01) << 8)
            table.append(("PL符号数", f"0x{pl_symbols:03X}", str(pl_symbols),
                         f"{pl_symbols}个PL符号", offset + 5, offset + 6))
            # 帧长(12b): byte8[0:7]+byte9[0:3]
            b8 = frame_bytes[offset + 7]
            b9 = frame_bytes[offset + 8]
            frame_len_pb = b8 | ((b9 & 0x0F) << 8)
            table.append(("帧长", f"0x{frame_len_pb:03X}", f"{frame_len_pb * 10}μs",
                         f"占用信道时长", offset + 7, offset + 8))
        elif not training:
            # ── 数据帧(非OFDMA)：TF符号数(3b) + PL频段(3b) + TF扩展频段(1b) + 保留(1b) ──
            b5 = frame_bytes[offset + 4]
            tf_symbols = (b5 & 0x07) * 2 + 2
            pl_band = (b5 >> 3) & 0x07
            tf_ext = (b5 >> 6) & 0x01
            table.append(("TF符号数", f"0x{b5 & 0x07:X}", str(tf_symbols),
                         f"实际符号数: {tf_symbols}", offset + 4, offset + 4))
            table.append(("PL频段标识", f"0x{pl_band:X}", str(pl_band),
                         f"频段{pl_band}", offset + 4, offset + 4))
            table.append(("TF扩展频段", f"0b{tf_ext}", str(tf_ext),
                         "扩展到0.7~12M" if tf_ext else "与PL相同", offset + 4, offset + 4))

            # 字节6(表23): bit0=Bitloading标识, bit1-5=TMI编号(Bitloading=0时)/物理块大小码(Bitloading=1时)
            # 物理块大小码仅2bit(bit1-2)有效: 0:136 1:520 2:72 3:264 (表23 注)
            b6 = frame_bytes[offset + 5]
            bitloading = b6 & 0x01
            tmi = (b6 >> 1) & 0x1F
            pb_size_code = (b6 >> 1) & 0x03  # Bitloading=1 时低2bit为PB大小码
            table.append(("Bitloading标识", f"0b{bitloading}", str(bitloading),
                         "使用Bitloading" if bitloading else "使用TMI",
                         offset + 5, offset + 5))
            if bitloading:
                pb_size = CSGNewGenParser.ISAC_BL_PB_SIZE_MAP.get(pb_size_code, 136)
                # Bitloading模式: 物理块大小不查TMI/ROBO表, 用本字段显式指定, 供PB解析使用
                self._pb_size = pb_size
                table.append(("物理块大小码", f"0x{pb_size_code:X}", str(pb_size_code),
                             f"Bitloading模式PB={pb_size}字节 (0:136 1:520 2:72 3:264)",
                             offset + 5, offset + 5))
            else:
                self._cmt_index = tmi
                pb_size = self._get_pb_size(tmi, 2)
                table.append(("TMI编号", f"0x{tmi:02X}", str(tmi),
                             f"TMI={tmi} (表13 ROBO模式), PB={pb_size}字节",
                             offset + 5, offset + 5))

            # 帧长(12b): byte8[0:7] + byte9[0:3]
            b8 = frame_bytes[offset + 7]
            b9 = frame_bytes[offset + 8]
            frame_len_pb = b8 | ((b9 & 0x0F) << 8)
            table.append(("帧长", f"0x{frame_len_pb:03X}", f"{frame_len_pb * 10}μs",
                         f"占用信道时长", offset + 7, offset + 8))
        else:
            # ── 训练帧(表24 MIMO训练帧 / 表25 Bitloading训练帧)：byte5-9 ──
            b5 = frame_bytes[offset + 4]
            train_type = b5 & 0x01
            tf_sym_cfg = (b5 >> 1) & 0x07
            tf_symbols = (tf_sym_cfg + 1) * 2
            subc_group_cfg = (b5 >> 4) & 0x03
            streams = (b5 >> 6) & 0x03
            table.append(("训练帧类型", f"0b{train_type}", str(train_type),
                         "Bitloading训练帧" if train_type else "MIMO训练帧",
                         offset + 4, offset + 4))
            table.append(("TF符号数", f"0x{tf_sym_cfg:X}", str(tf_symbols),
                         f"实际TF符号数: {tf_symbols}", offset + 4, offset + 4))
            if train_type:
                table.append(("子载波分组大小", f"0b{subc_group_cfg:02b}", str(subc_group_cfg),
                             f"{1 << subc_group_cfg}个子载波为一组", offset + 4, offset + 4))
            else:
                table.append(("子载波分组大小", f"0b{subc_group_cfg:02b}", str(subc_group_cfg),
                             "MIMO训练帧该字段无效(默认填0)", offset + 4, offset + 4))
            table.append(("流数", f"0x{streams:X}", str(streams),
                         f"{streams + 1}流", offset + 4, offset + 4))

            # byte6: bit0-2=频段标识, bit3=RU信噪比估计标识, bit4-7保留
            b6 = frame_bytes[offset + 5]
            band = b6 & 0x07
            ru_snr = (b6 >> 3) & 0x01
            band_name = "PL频段标识" if train_type else "TF频段标识"
            table.append((band_name, f"0x{band:X}", str(band),
                         f"频段{band}", offset + 5, offset + 5))
            ru_desc = "接收端估计频段内各RU平均信噪比" if ru_snr else "不估计RU信噪比"
            if not train_type:
                ru_desc += "（MIMO训练帧固定为1）"
            table.append(("RU信噪比估计标识", f"0b{ru_snr}", str(ru_snr),
                         ru_desc, offset + 5, offset + 5))

            # 帧长(12b): byte8[0:7] + byte9[0:3]
            b8 = frame_bytes[offset + 7]
            b9 = frame_bytes[offset + 8]
            frame_len_pb = b8 | ((b9 & 0x0F) << 8)
            table.append(("帧长", f"0x{frame_len_pb:03X}", f"{frame_len_pb * 10}μs",
                         f"占用信道时长", offset + 7, offset + 8))

        return offset + 11

    # ── 网间协调帧(NET)可变区域 (表41) ──

    def _parse_mpdu_net(self, frame_bytes: bytes, offset: int, table: list) -> int:
        """解析网间协调帧可变区域 (字节1-11, 共11字节; 字节12由公共代码处理)

        依据《第4部分 数据链路层通信协议》表41 网间协调的可变区域:
          邻居网络比特图1(16b) + 本网络无线信道编号(8b) + 邻居网络比特图2(10b)
          + 持续时间(14b) + 邻居网络比特图3(1b) + 带宽结束标志位(1b)
          + 本网络无线option(2b) + 邻居网络比特图4(4b)
          + 带宽结束偏移(16b) + 带宽开始偏移(16b)
        网间协调帧用于 CCO 间带宽协商（多网络共存场景）。
        多字节字段小端序。
        """
        base = offset  # 字节1起始偏移

        # 邻居网络比特图1 (16b: byte1[0:7] + byte2[0:7], 小端)
        nid_map1 = int.from_bytes(frame_bytes[offset:offset + 2], 'little')
        table.append(("邻居网络比特图1",
                      ' '.join(f'{b:02X}' for b in frame_bytes[offset:offset + 2]),
                      f"0x{nid_map1:04X}",
                      "bit0=SNID1 ... bit15=SNID16 (小端)",
                      offset, offset + 1))

        # 本网络无线信道编号 (8b: byte3)
        wchan = frame_bytes[offset + 2]
        table.append(("本网络无线信道编号", f"0x{wchan:02X}", str(wchan),
                      "告知邻居本网络使用的无线信道编号", offset + 2, offset + 2))

        # 邻居网络比特图2 (10b: byte4[0:7] + byte5[0:1])
        nid_map2 = frame_bytes[offset + 3] | ((frame_bytes[offset + 4] & 0x03) << 8)
        table.append(("邻居网络比特图2",
                      f"{frame_bytes[offset + 3]:02X} {frame_bytes[offset + 4] & 0x03:01X}",
                      f"0x{nid_map2:03X}",
                      "bit0=SNID17 ... bit9=SNID26",
                      offset + 3, offset + 4))

        # 持续时间 (14b: byte5[2:7] + byte6[0:7], 小端组合)
        duration = ((frame_bytes[offset + 4] >> 2) & 0x3F) | (frame_bytes[offset + 5] << 6)
        table.append(("持续时间",
                      f"0x{duration:04X}",
                      f"{duration} × 40ms ({duration * 40}ms)",
                      "本网络需申请占用的时隙长度, 单位40ms",
                      offset + 4, offset + 5))

        # 字节7: 邻居网络比特图3(1b) + 带宽结束标志位(1b) + 无线option(2b) + 邻居网络比特图4(4b)
        b7 = frame_bytes[offset + 6]
        nid_map3 = b7 & 0x01
        bw_end_flag = (b7 >> 1) & 0x01
        wireless_option = (b7 >> 2) & 0x03
        nid_map4 = (b7 >> 4) & 0x0F
        table.append(("邻居网络比特图3", f"0b{nid_map3:01b}", str(nid_map3),
                      "bit0=SNID27", offset + 6, offset + 6))
        table.append(("带宽结束标志位", f"0b{bw_end_flag:01b}", str(bw_end_flag),
                      "1=上个带宽时隙已结束 0=未结束", offset + 6, offset + 6))
        table.append(("本网络无线option", f"0b{wireless_option:02b}", str(wireless_option),
                      "告知邻居本网络使用的无线信道option", offset + 6, offset + 6))
        table.append(("邻居网络比特图4", f"0x{nid_map4:X}", f"0b{nid_map4:04b}",
                      "bit0=SNID28 ... bit3=SNID31", offset + 6, offset + 6))

        # 带宽结束偏移 (16b: byte8[0:7] + byte9[0:7], 小端, 单位4ms)
        bw_end_offset = int.from_bytes(frame_bytes[offset + 7:offset + 9], 'little')
        end_desc = "从上个带宽时隙结束到当前时刻" if bw_end_flag else "从当前时刻到当前带宽时隙结束"
        table.append(("带宽结束偏移",
                      f"0x{bw_end_offset:04X}",
                      f"{bw_end_offset} × 4ms ({bw_end_offset * 4}ms)",
                      f"{end_desc}的时间偏移, 单位4ms",
                      offset + 7, offset + 8))

        # 带宽开始偏移 (16b: byte10[0:7] + byte11[0:7], 小端, 单位4ms)
        bw_start_offset = int.from_bytes(frame_bytes[offset + 9:offset + 11], 'little')
        start_desc = ("下个带宽时隙未开始, 从当前时刻到下个时隙开始"
                      if bw_start_offset else "下个带宽时隙已开始")
        table.append(("带宽开始偏移",
                      f"0x{bw_start_offset:04X}",
                      f"{bw_start_offset} × 4ms ({bw_start_offset * 4}ms)",
                      f"{start_desc}的时间偏移, 单位4ms",
                      offset + 9, offset + 10))

        return offset + 11

    # ── eFC 扩展帧控制解析 ──

    @staticmethod
    def _extract_bits(data: bytes, start_bit: int, width: int) -> int:
        """从字节流提取位域，start_bit为绝对位偏移(LSB优先，bit0=byte0.bit0)"""
        val = 0
        for i in range(width):
            bp = start_bit + i
            byte_idx = bp // 8
            bit_idx = bp % 8
            if byte_idx < len(data):
                val |= ((data[byte_idx] >> bit_idx) & 1) << i
        return val

    def _parse_efc(self, efc_data: bytes, base_offset: int, ofdma_type: int,
                   station_count: int, table: list) -> int:
        """解析eFC(扩展帧控制)，16字节。返回eFC结束偏移"""
        if len(efc_data) < 16:
            table.append(("❌ eFC解析失败", "", "", "eFC数据不足16字节", None, None))
            return base_offset + len(efc_data)
        eb = efc_data  # eFC字节(相对偏移)
        table.append(("eFC原始数据",
                     ' '.join(f'{b:02X}' for b in eb[:16]),
                     "16字节", "扩展帧控制",
                     base_offset, base_offset + 15))
        if ofdma_type == 0:
            self._parse_efc_dl_ofdma(eb, base_offset, station_count, table)
        elif ofdma_type == 2:
            self._parse_efc_ul_trigger(eb, base_offset, station_count, table)
        elif ofdma_type == 3:
            self._parse_efc_ul_sack(eb, base_offset, station_count, table)
        else:
            table.append(("eFC(未知类型)", f"type={ofdma_type}", "", "无法解析",
                         base_offset, base_offset + 15))
        return base_offset + 16

    def _parse_efc_dl_ofdma(self, eb: bytes, base_offset: int, sta_count: int, table: list):
        """表27: DL-OFDMA帧eFC"""
        tf_count = self._extract_bits(eb, 0, 2)
        actual_tf = (tf_count + 1) * 2
        table.append(("eFC: TF个数", f"0b{tf_count:02b}", str(actual_tf),
                     f"实际TF个数={actual_tf}", base_offset, base_offset))
        # 每站点25bit: PB个数(1)+TEI(12)+TMI(5)+RU(4)+SACK_RU(3)
        bit_pos = 2
        for s in range(min(sta_count, 4)):
            bp = bit_pos + s * 25
            pb_cnt = self._extract_bits(eb, bp, 1) + 1
            tei = self._extract_bits(eb, bp + 1, 12)
            tmi = self._extract_bits(eb, bp + 13, 5)
            ru = self._extract_bits(eb, bp + 18, 4)
            sack_ru = self._extract_bits(eb, bp + 22, 3)
            start_byte = base_offset + bp // 8
            end_byte = base_offset + (bp + 24) // 8
            table.append((f"eFC: 站点{s} PB个数", f"0b{pb_cnt-1}", str(pb_cnt),
                         f"{pb_cnt}个PB", start_byte, start_byte))
            table.append((f"eFC: 站点{s} TEI", f"0x{tei:03X}", str(tei),
                         f"目的站点TEI", start_byte, end_byte))
            table.append((f"eFC: 站点{s} TMI", f"0x{tmi:02X}", str(tmi),
                         f"TMI={tmi}", start_byte, end_byte))
            table.append((f"eFC: 站点{s} RU", f"0x{ru:X}", str(ru),
                         f"RU{ru}", start_byte, end_byte))
            table.append((f"eFC: 站点{s} SACK_RU", f"0x{sack_ru:X}", str(sack_ru),
                         f"回复SACK用RU{sack_ru}", start_byte, end_byte))
        # CRC: 前13字节CRC-24校验，字节13-15为FCS（小端序）
        crc_val = int.from_bytes(eb[13:16], 'little')
        crc24_calc = self._crc24(eb[:13])
        crc24_match = (crc24_calc == crc_val)
        crc_desc = f"24位CRC校验eFC前13字节，FCS=0x{crc_val:06X}"
        crc_desc += "，校验通过" if crc24_match else f"，校验失败(计算值=0x{crc24_calc:06X})"
        table.append(("eFC CRC校验", ' '.join(f'{b:02X}' for b in eb[13:16]),
                     f"0x{crc_val:06X}", crc_desc,
                     base_offset + 13, base_offset + 15))

    def _parse_efc_ul_trigger(self, eb: bytes, base_offset: int, sta_count: int, table: list):
        """表28: UL-OFDMA trigger帧eFC"""
        TX_PWR_MAP = {i: f"{i*4}dB" for i in range(8)}
        tf_count = self._extract_bits(eb, 0, 2)
        actual_tf = (tf_count + 1) * 2
        table.append(("eFC: TF个数", f"0b{tf_count:02b}", str(actual_tf),
                     f"实际TF个数={actual_tf}", base_offset, base_offset))
        # 每站点25bit: PB个数(1)+TEI(12)+TMI(5)+RU(4)+Tx功率回退(3)
        bit_pos = 2
        for s in range(min(sta_count, 4)):
            bp = bit_pos + s * 25
            pb_cnt = self._extract_bits(eb, bp, 1) + 1
            tei = self._extract_bits(eb, bp + 1, 12)
            tmi = self._extract_bits(eb, bp + 13, 5)
            ru = self._extract_bits(eb, bp + 18, 4)
            tx_backoff = self._extract_bits(eb, bp + 22, 3)
            start_byte = base_offset + bp // 8
            end_byte = base_offset + (bp + 24) // 8
            table.append((f"eFC: 站点{s} PB个数", f"0b{pb_cnt-1}", str(pb_cnt),
                         f"{pb_cnt}个PB", start_byte, start_byte))
            table.append((f"eFC: 站点{s} TEI", f"0x{tei:03X}", str(tei),
                         f"目的站点TEI", start_byte, end_byte))
            table.append((f"eFC: 站点{s} TMI", f"0x{tmi:02X}", str(tmi),
                         f"TMI={tmi}", start_byte, end_byte))
            table.append((f"eFC: 站点{s} RU", f"0x{ru:X}", str(ru),
                         f"RU{ru}", start_byte, end_byte))
            table.append((f"eFC: 站点{s} Tx功率回退",
                         f"0x{tx_backoff:X}", str(tx_backoff),
                         f"回退{TX_PWR_MAP.get(tx_backoff, '?')}",
                         start_byte, end_byte))
        crc_val = int.from_bytes(eb[13:16], 'little')
        crc24_calc = self._crc24(eb[:13])
        crc24_match = (crc24_calc == crc_val)
        crc_desc = f"24位CRC校验eFC前13字节，FCS=0x{crc_val:06X}"
        crc_desc += "，校验通过" if crc24_match else f"，校验失败(计算值=0x{crc24_calc:06X})"
        table.append(("eFC CRC校验", ' '.join(f'{b:02X}' for b in eb[13:16]),
                     f"0x{crc_val:06X}", crc_desc,
                     base_offset + 13, base_offset + 15))

    def _parse_efc_ul_sack(self, eb: bytes, base_offset: int, sta_count: int, table: list):
        """表29: UL-OFDMA SACK帧eFC
        每站点3字节(24bit): TEI(12bit) + 接收状态(4bit) + 保留(8bit)
        """
        for s in range(min(sta_count, 4)):
            base_bit = s * 24  # 每站点24bit
            tei = self._extract_bits(eb, base_bit, 12)
            rx_status = self._extract_bits(eb, base_bit + 12, 4)
            reserved = self._extract_bits(eb, base_bit + 16, 8)
            start_byte = base_offset + base_bit // 8
            end_byte = base_offset + (base_bit + 23) // 8
            pb0 = "OK" if (rx_status & 1) else "FAIL"
            pb1 = "OK" if (rx_status & 2) else "FAIL"
            table.append((f"eFC: 站点{s} TEI", f"0x{tei:03X}", str(tei),
                         f"站点TEI", start_byte, end_byte))
            table.append((f"eFC: 站点{s} 接收状态", f"0x{rx_status:X}",
                         f"PB0:{pb0} PB1:{pb1}",
                         f"PB接收结果(bit0=PB0,bit1=PB1)",
                         start_byte, end_byte))
            table.append((f"eFC: 站点{s} 保留", f"0x{reserved:02X}", str(reserved),
                         "保留字段", start_byte + 2, end_byte))
        crc_val = int.from_bytes(eb[13:16], 'little')
        crc24_calc = self._crc24(eb[:13])
        crc24_match = (crc24_calc == crc_val)
        crc_desc = f"24位CRC校验eFC前13字节，FCS=0x{crc_val:06X}"
        crc_desc += "，校验通过" if crc24_match else f"，校验失败(计算值=0x{crc24_calc:06X})"
        table.append(("eFC CRC校验", ' '.join(f'{b:02X}' for b in eb[13:16]),
                     f"0x{crc_val:06X}", crc_desc,
                     base_offset + 13, base_offset + 15))

    # ── 信标帧可变区域 (字节1-12) ───

    BEACON_PHASE_MAP = {0: "未知相线", 1: "A相线", 2: "B相线", 3: "C相线"}

    def _parse_mpdu_beacon(self, frame_bytes: bytes, offset: int, table: list) -> int:
        """解析信标帧可变区域 (字节1-12, 共12字节)"""
        # 信标时间戳 (32b: bytes 1-4, 小端序)
        beacon_ts = int.from_bytes(frame_bytes[offset:offset + 4], 'little')
        table.append(("信标时间戳",
                     ' '.join(f'{b:02X}' for b in frame_bytes[offset:offset + 4]),
                     f"0x{beacon_ts:08X}",
                     f"网络基准时间: {beacon_ts}",
                     offset, offset + 3))
        offset += 4

        # 信标周期计数 (32b: bytes 5-8, 小端序)
        beacon_cycle = int.from_bytes(frame_bytes[offset:offset + 4], 'little')
        table.append(("信标周期计数",
                     ' '.join(f'{b:02X}' for b in frame_bytes[offset:offset + 4]),
                     f"0x{beacon_cycle:08X}",
                     f"CCO维护的信标周期递增计数: {beacon_cycle}",
                     offset, offset + 3))
        offset += 4

        # 源TEI (12b: byte9[0:7] + byte10[0:3])
        src_tei = frame_bytes[offset] | ((frame_bytes[offset + 1] & 0x0F) << 8)
        table.append(("源TEI",
                     f"0x{src_tei:03X}",
                     str(src_tei),
                     f"发送信标的站点TEI: {src_tei}",
                     offset, offset + 1))

        # 载波映射表索引 (4b: byte10[4:7])
        cmt_index = (frame_bytes[offset + 1] >> 4) & 0x0F
        self._cmt_index = cmt_index
        pb_size = self._get_pb_size(cmt_index, self._std_version)
        table.append(("载波映射表索引",
                     f"0x{cmt_index:X}",
                     str(cmt_index),
                     f"信标帧发送载波映射表索引: {cmt_index}, PB大小: {pb_size}字节",
                     offset + 1, offset + 1))
        offset += 2

        # 符号数 (9b: byte11[0:7] + byte12[0])
        symbol_count = (frame_bytes[offset] << 1) | ((frame_bytes[offset + 1] >> 7) & 0x01)
        table.append(("符号数",
                     f"0x{symbol_count:03X}",
                     str(symbol_count),
                     f"OFDM符号数: {symbol_count}",
                     offset, offset + 1))

        # 短网络标识高位 (1b: byte12[1])
        snid_high = (frame_bytes[offset + 1] >> 1) & 0x01
        table.append(("短网络标识高位",
                     f"0b{snid_high}",
                     str(snid_high),
                     "与低位共同构成5bit SNID",
                     offset + 1, offset + 1))

        # 相线 (2b: byte12[2:3])
        phase = (frame_bytes[offset + 1] >> 2) & 0x03
        phase_name = self.BEACON_PHASE_MAP.get(phase, f"保留({phase})")
        table.append(("相线",
                     f"0b{phase:02b}",
                     str(phase),
                     f"目的相线: {phase_name}",
                     offset + 1, offset + 1))

        return offset + 2  # 字节1-12共12字节

    # ── 信标帧载荷解析（表51）──

    BEACON_TYPE_MAP = {0: "发现信标", 1: "代理信标", 2: "中央信标"}

    def _parse_beacon_payload(self, data: bytes, base_offset: int = 0) -> list:
        """解析信标帧载荷

        - 精简信标（byte0 bit4=1）：表73 布局——标志+组网序列号+CCO MAC+信标周期计数+管理信息+CRC
        - 标准信标：表51 布局——标志+组网序列号+SNID/无线/PLC+信道+通道机制+保留+管理信息+CRC
        """
        table = []
        if len(data) < 6:
            if data:
                table.append(("信标载荷", ' '.join(f'{b:02X}' for b in data),
                               f"{len(data)}字节", "信标载荷(长度不足)", base_offset, base_offset + len(data) - 1))
            return table
        if data[0] & 0x10:  # 精简信标标志（表73）
            return self._parse_compact_beacon_payload(data, base_offset)
        return self._parse_std_beacon_payload(data, base_offset)

    def _parse_compact_beacon_payload(self, data: bytes, base_offset: int = 0) -> list:
        """精简信标帧载荷解析（文档表73）

        布局: 信标类型等标志(1B) + 组网序列号(1B) + CCO MAC(6B)
              + 信标周期计数(4B小端) + 信标管理信息(可变) + BPCS CRC-32(4B)
        """
        table = []
        b0 = data[0]
        bcn_type = b0 & 0x07
        table.append(("信标载荷头(精简)", f"{b0:02X}",
                       f"类型:{self.BEACON_TYPE_MAP.get(bcn_type,'?')}",
                       f"信标类型:{bcn_type} 组网:{(b0>>3)&1} 精简:1 多网络:{(b0>>5)&1} 允许关联:{(b0>>6)&1} 信标使用:{(b0>>7)&1}",
                       base_offset, base_offset))
        table.append(("  组网序列号", f"{data[1]:02X}", str(data[1]),
                       f"组网序列号: {data[1]}", base_offset + 1, base_offset + 1))
        mac_colon = ':'.join(f'{b:02X}' for b in data[2:8])
        table.append(("  CCO MAC地址", ' '.join(f'{b:02X}' for b in data[2:8]),
                       mac_colon, f"CCO MAC={mac_colon}", base_offset + 2, base_offset + 7))
        cycle = int.from_bytes(data[8:12], 'little')
        table.append(("  信标周期计数", ' '.join(f'{b:02X}' for b in data[8:12]),
                       str(cycle), f"信标周期序号: {cycle} (与FC可变区域一致)", base_offset + 8, base_offset + 11))
        remaining = data[12:]
        if remaining:
            bcn_tbl, consumed = self._parse_beacon_entries(remaining, base_offset + 12)
            table.extend(bcn_tbl)
            table.extend(self._beacon_tail_rows(remaining, consumed, base_offset + 12))
        return table

    def _parse_std_beacon_payload(self, data: bytes, base_offset: int = 0) -> list:
        """标准信标帧载荷解析（文档表51）"""
        table = []
        offset = 0
        b0 = data[0]
        bcn_type = b0 & 0x07
        table.append(("信标载荷头", f"{b0:02X}",
                       f"类型:{self.BEACON_TYPE_MAP.get(bcn_type,'?')}",
                       f"信标类型:{bcn_type} 组网:{(b0>>3)&1} 精简:{(b0>>4)&1} 多网络:{(b0>>5)&1} 允许关联:{(b0>>6)&1} SNID高:{(b0>>7)&1}",
                       base_offset, base_offset))
        offset += 1
        table.append(("  组网序列号", f"{data[1]:02X}", str(data[1]),
                       f"组网序列号: {data[1]}", base_offset + 1, base_offset + 1))
        offset += 1
        b2 = data[2]
        table.append(("  短网络标识/无线/PLC", f"{b2:02X}",
                       f"SNID低:{b2&0xF} RFopt:{(b2>>4)&3} PLC:{(b2>>6)&3}",
                       f"SNID低4位:{b2&0xF} 无线option:{(b2>>4)&3} PLC能力:{(b2>>6)&3}",
                       base_offset + 2, base_offset + 2))
        offset += 1
        table.append(("  无线信道编号", f"{data[3]:02X}", str(data[3]),
                       f"本网络无线信道: {data[3]}", base_offset + 3, base_offset + 3))
        offset += 1
        b4 = data[4]
        table.append(("  通道数/版本/信标机制", f"{b4:02X}",
                       f"通道:{'多' if (b4&1) else '单'} 版本:{(b4>>1)&7} {'分散信标' if (b4>>4)&1 else '集中信标'}",
                       f"通道数:{b4&1} 网络版本:{(b4>>1)&7} 信标机制:{(b4>>4)&1} 发现信标使能:{(b4>>5)&1}",
                       base_offset + 4, base_offset + 4))
        offset += 1
        table.append(("  保留", f"{data[5]:02X}", "1字节", "保留",
                       base_offset + 5, base_offset + 5))
        offset += 1
        remaining = data[offset:]
        if remaining:
            bcn_tbl, consumed = self._parse_beacon_entries(remaining, base_offset + offset)
            table.extend(bcn_tbl)
            table.extend(self._beacon_tail_rows(remaining, consumed, base_offset + offset))
        return table

    # ── 信标条目解析（表57-72）──

    # 信标条目头→(名称, 长度字段大小)
    BEACON_ENTRY_MAP = {
        0x01: ("站点能力条目", 1),
        0x02: ("时隙分配条目", 2),
        0x06: ("路由参数条目", 1),
        0x07: ("频段变更条目", 1),
        0x0A: ("频段探测条目", 1),
        0x0B: ("万年历同步条目", 1),
        0x0C: ("无线路由参数条目", 1),
        0x0D: ("无线信道变更条目", 1),
        0x0E: ("精简信标站点信息及时隙条目", 1),
        0x0F: ("信标机制切换条目", 1),
        0x10: ("代理角色条目", 2),
    }

    def _parse_beacon_entries(self, data: bytes, base_offset: int = 0):
        """解析信标管理信息条目列表（表57-72）

        返回 ``(行列表, 已消费字节数)``；已消费字节数供调用方确定其后的
        帧载荷校验序列位置。

        长度字段宽度按表59 取，但**实机存在与表59 不符的条目**（实测 0x10 代理角色
        条目按 1 字节长度发送，表59/表72 写的是 16 比特）：此时按规格宽度读出的
        "长度"会远超剩余字节，自动退回 1 字节长度字段重读（声明长度合法时仍按表59）。
        """
        table = []
        if len(data) < 1:
            return table, 0
        entry_count = data[0]
        table.append(("  信标条目数", f"{entry_count:02X}", str(entry_count),
                      f"共{entry_count}个信标条目", base_offset, base_offset))
        off = 1
        idx = 0
        while off < len(data) and idx < entry_count:
            type_at = off
            entry_type = data[off]
            if entry_type == 0x00:
                # 表59: 0x00 为非法值 —— 其后是补齐字节/校验序列，不应再当条目解析
                break
            entry_info = self.BEACON_ENTRY_MAP.get(
                entry_type, ("厂家自定义" if 0x80 <= entry_type <= 0xEF else f"保留(0x{entry_type:02X})", 1))
            entry_name = entry_info[0]
            len_size = entry_info[1]
            len_at = off + 1
            avail = len(data) - len_at          # 长度字段及内容可用的总字节数
            if avail < len_size:
                break
            entry_len = int.from_bytes(data[len_at:len_at + len_size], 'little')
            note = ""
            content_len = entry_len - 1 - len_size
            if len_size > 1 and (content_len < 0 or content_len > avail - len_size):
                len1 = data[len_at]
                if len1 >= 2 and len1 - 2 <= avail - 1:
                    note = (f" [长度字段实发 1 字节：{len_size} 字节声明值 0x{entry_len:04X}"
                            f" 超出剩余 {avail} 字节，已按 1 字节解析]")
                    entry_len, len_size, content_len = len1, 1, len1 - 2
            content_at = len_at + len_size
            entry_base = base_offset + content_at
            if content_len < 0:
                content_len = 0
                note += " [长度字段非法，按 0 字节处理]"
            if content_at + content_len > len(data):
                content_len = len(data) - content_at
                note += f" [声明长度超出剩余 {content_len} 字节，已按剩余字节解析]"
            entry_data = data[content_at:content_at + content_len]
            off = content_at + content_len

            # 条目类型和长度字段
            table.append(("  条目类型", f"{entry_type:02X}", str(entry_type),
                          f"条目{idx}类型: {entry_name} (0x{entry_type:02X})",
                          base_offset + type_at, base_offset + type_at))
            len_raw = ' '.join(f'{b:02X}' for b in data[len_at:len_at + len_size])
            table.append(("  条目长度", len_raw, str(entry_len),
                          f"条目{idx}长度: {entry_len}字节 (含类型和长度字段){note}",
                          base_offset + len_at, base_offset + len_at + len_size - 1))

            # 详细解析条目内容
            detail = self._parse_beacon_entry_detail(entry_type, entry_data, entry_base)
            if detail:
                table.extend(detail)
            else:
                raw = ' '.join(f'{b:02X}' for b in entry_data[:12]) + ("..." if len(entry_data) > 12 else "")
                table.append(("  信标条目",
                              f"{entry_type:02X} {len_raw} {raw}",
                              f"类型:{entry_name} 长度:{entry_len}",
                              f"条目{idx}: {entry_name} ({entry_len}字节)",
                              base_offset + type_at, base_offset + off - 1))
            idx += 1
        return table, off

    def _beacon_tail_rows(self, remaining: bytes, consumed: int, base: int) -> list:
        """信标管理信息之后的字段：帧载荷校验序列（4B）+ 可能的补齐字节

        **不再无条件把载荷末 4 字节当校验序列**：先按条目解析结果定位条目末尾，
        再在其后的剩余字节里取末 4 字节。实机存在输入载荷已被裁剪到最后一个条目
        （未含校验序列，如只截了 PB 载荷的有效部分）的情况，此时末 4 字节属最后
        一个条目的内容，按旧逻辑会被吞掉、导致该条目少 4 字节。
        """
        rows = []
        tail = remaining[consumed:]
        if len(tail) >= 4:
            crc_bytes = tail[-4:]
            crc_val = int.from_bytes(crc_bytes, 'little')
            desc = f"信标载荷CRC-32=0x{crc_val:08X}"
            if len(tail) > 4:
                desc += f"（条目之后另有 {len(tail) - 4} 字节补齐/保留）"
            rows.append(("  帧载荷校验序列", ' '.join(f'{b:02X}' for b in crc_bytes),
                         f"0x{crc_val:08X}", desc,
                         base + len(remaining) - 4, base + len(remaining) - 1))
        elif tail:
            rows.append(("  信标载荷尾部", ' '.join(f'{b:02X}' for b in tail),
                         f"{len(tail)}字节", "不足4字节，无法作为帧载荷校验序列",
                         base + consumed, base + len(remaining) - 1))
        elif remaining:
            rows.append(("  帧载荷校验序列", "-", "未包含",
                         "输入载荷在最后一个条目处结束，未含4字节帧载荷校验序列（如 PB 载荷已裁剪）",
                         base + len(remaining) - 1, base + len(remaining) - 1))
        return rows

    def _parse_beacon_entry_detail(self, etype: int, data: bytes, base: int) -> list:
        """详细解析单个信标条目内容（data已去除条目类型和长度字段），每字段一行"""
        t = []
        ln = len(data)
        def _f(name, raw, parsed, desc, s, e):
            t.append((f"    {name}", raw, parsed, desc, base + s, base + e))
        if etype == 0x01 and ln >= 20:  # 站点能力条目（表61）
            _f("层级数", f"{(data[0]&0x3F):02X}", str(data[0]&0x3F), f"层级数: {data[0]&0x3F}", 0, 0)
            ph = data[0] >> 6
            _f("相线", f"{ph:02b}", str(ph), self.PHASE_MAP.get(ph, f"保留({ph})"), 0, 0)
            tei = data[1] | ((data[2] & 0x0F) << 8)
            _f("站点TEI", ' '.join(f'{b:02X}' for b in data[1:3]), str(tei), f"站点TEI: {tei}", 1, 2)
            role = (data[2] >> 4) & 0x0F
            _f("角色", f"{role:X}", str(role), f"角色: {role}", 2, 2)
            _f("信标使用标志", f"{data[3]:02X}", str(data[3]), "使用" if data[3] else "不使用", 3, 3)
            if ln >= 10:
                mac_colon = ':'.join(f'{b:02X}' for b in data[4:10])
                mac_raw = ' '.join(f'{b:02X}' for b in data[4:10])
                _f("发送信标MAC", mac_raw, mac_colon, f"MAC={mac_colon}", 4, 9)
            if ln >= 16:
                ptei = data[10] | ((data[11] & 0x0F) << 8)
                rf_hop = data[11] >> 4
                _f("代理站点TEI", ' '.join(f'{b:02X}' for b in data[10:12]), str(ptei), f"代理站点TEI: {ptei}", 10, 11)
                _f("RF跳数", f"{rf_hop:X}", str(rf_hop), f"链路上RF跳数: {rf_hop}", 11, 11)
                rate = self._read_u32_le(data, 12)
                _f("路径最低通信成功率", ' '.join(f'{b:02X}' for b in data[12:16]), f"{rate}%", f"到CCO路径最低成功率: {rate}%", 12, 15)
        elif etype == 0x02 and ln >= 6:  # 时隙分配条目（表62）
            _f("非中央信标时隙总数", f"{data[0]:02X}", str(data[0]), f"非中央信标时隙: {data[0]}", 0, 0)
            _f("中央信标时隙总数", f"{data[1]:02X}", str(data[1]), f"中央信标时隙: {data[1]}", 1, 1)
            _f("CSMA相线个数", f"{data[2]:02X}", str(data[2]), f"CSMA时隙相线: {data[2]}", 2, 2)
            _f("代理信标时隙总数", f"{data[3]:02X}", str(data[3]), f"代理信标时隙: {data[3]}", 3, 3)
            if ln >= 6:
                sl = self._read_u16_le(data, 4)
                _f("信标时隙长度", ' '.join(f'{b:02X}' for b in data[4:6]), f"{sl}x100us", f"信标时隙长度: {sl}*100us", 4, 5)
            if ln >= 7: _f("CSMA时隙大小", f"{data[6]:02X}", f"{data[6]}x10ms", f"CSMA时隙: {data[6]}*10ms", 6, 6)
            if ln >= 8: _f("绑定CSMA相线个数", f"{data[7]:02X}", str(data[7]), f"绑定CSMA相线: {data[7]}", 7, 7)
            if ln >= 9: _f("绑定CSMA链路标识符", f"{data[8]:02X}", str(data[8]), f"绑定CSMA LID: {data[8]}", 8, 8)
            if ln >= 11:
                tl = self._read_u16_le(data, 9)
                _f("TDMA时隙长度", ' '.join(f'{b:02X}' for b in data[9:11]), f"{tl}x100us", f"TDMA时隙长度: {tl}*100us", 9, 10)
            if ln >= 12: _f("TDMA链路标识符", f"{data[11]:02X}", str(data[11]), f"TDMA LID: {data[11]}", 11, 11)
            if ln >= 16:
                ntb = self._read_u32_le(data, 12)
                _f("信标周期起始NTB", ' '.join(f'{b:02X}' for b in data[12:16]), f"0x{ntb:08X}", f"信标周期起始NTB: {ntb}", 12, 15)
            if ln >= 20:
                plen = self._read_u32_le(data, 16)
                _f("信标周期长度", ' '.join(f'{b:02X}' for b in data[16:20]), f"{plen}x100us", f"信标周期长度: {plen}*100us", 16, 19)
            if ln >= 22:
                # 表62：RF信标时隙长度紧跟信标周期长度（条目字节 19-22）之后，占条目字节 23-24。
                # 表62 该行写的字节号“22/23”与信标周期长度重叠，为文档笔误（按 23-24 才自洽：
                # 信标周期长度 19-22 + RF 23-24 + 保留 22bit，固定区恰好 27 字节）
                rf_sl = data[20] | ((data[21] & 0x03) << 8)
                _f("RF信标时隙长度", ' '.join(f'{b:02X}' for b in data[20:22]), f"{rf_sl}ms", f"RF信标时隙长度: {rf_sl}ms", 20, 21)
            # 固定区共 24 字节（条目字节 3-26）；其后按各计数展开可变长时隙信息（表63-65）
            if ln > 24:
                exp_len = data[0] * 2 + data[2] * 4 + data[7] * 4
                _f("可变长时隙信息",
                   ' '.join(f'{b:02X}' for b in data[24:min(ln, 36)]) + ("..." if ln > 36 else ""),
                   f"{ln - 24}字节",
                   f"非中央信标信息×{data[0]}(2B) + CSMA时隙信息×{data[2]}(4B) + 绑定CSMA时隙信息×{data[7]}(4B)"
                   f" = {exp_len}字节（实际 {ln - 24} 字节）", 24, ln - 1)
        elif etype == 0x06 and ln >= 32:  # 路由参数条目（表66）
            rp = self._read_u16_le(data, 0)
            _f("路由周期", ' '.join(f'{b:02X}' for b in data[0:2]), f"{rp}s", f"路由周期: {rp}秒", 0, 1)
            rt = self._read_u16_le(data, 4)
            _f("路由评估剩余时间", ' '.join(f'{b:02X}' for b in data[4:6]), f"{rt}s", f"距离下次评估: {rt}秒", 4, 5)
            cco_mac = ':'.join(f'{b:02X}' for b in data[26:32])
            _f("CCO MAC地址", ' '.join(f'{b:02X}' for b in data[26:32]), cco_mac, f"CCO MAC={cco_mac}", 26, 31)
        elif etype == 0x07 and ln >= 5:  # 频段变更条目（表67）
            _f("目标频段", f"{data[0]:02X}", str(data[0]), f"目标频段: {data[0]}", 0, 0)
            rtime = self._read_u32_le(data, 1)
            _f("切换剩余时间", ' '.join(f'{b:02X}' for b in data[1:5]), f"{rtime}ms", f"频段切换剩余: {rtime}ms", 1, 4)
        elif etype == 0x0B and ln >= 8:  # 万年历同步条目（表68）
            cal = self._read_u32_le(data, 0)
            _f("CCO万年历", ' '.join(f'{b:02X}' for b in data[0:4]), f"{cal}s", f"CCO万年历: {cal}秒", 0, 3)
            ntb = self._read_u32_le(data, 4)
            _f("CCO万年历NTB", ' '.join(f'{b:02X}' for b in data[4:8]), f"0x{ntb:08X}", f"万年历对应NTB: 0x{ntb:08X}", 4, 7)
        elif etype == 0x0D and ln >= 6:  # 无线信道变更条目（表70）
            _f("目标信道号", f"{data[0]:02X}", str(data[0]), f"目标信道: {data[0]}", 0, 0)
            _f("目标option", f"{data[1]&3:02b}", str(data[1]&3), f"目标option: {data[1]&3}", 1, 1)
            rtime = self._read_u32_le(data, 2)
            _f("切换剩余时间", ' '.join(f'{b:02X}' for b in data[2:6]), f"{rtime}ms", f"信道切换剩余: {rtime}ms", 2, 5)
        elif etype == 0x0F and ln >= 5:  # 信标机制切换条目（表71）
            mech = {0: "集中信标", 1: "分散信标"}.get(data[0], f"?({data[0]})")
            _f("切换目标机制", f"{data[0]:02X}", mech, f"目标机制: {mech}", 0, 0)
            ntb = self._read_u32_le(data, 1)
            _f("切换NTB时刻", ' '.join(f'{b:02X}' for b in data[1:5]), f"0x{ntb:08X}", f"切换NTB: 0x{ntb:08X}", 1, 4)
        elif etype == 0x0E and ln >= 16:  # 精简信标站点信息及时隙条目（表74，固定长19=0x13）
            tei = data[0] | ((data[1] & 0x0F) << 8)
            _f("TEI", ' '.join(f'{b:02X}' for b in data[0:2]), str(tei), f"发送信标站点TEI: {tei}", 0, 1)
            ptei = (data[1] >> 4) | (data[2] << 4)
            _f("代理站点TEI", ' '.join(f'{b:02X}' for b in data[1:3]), str(ptei), f"代理站点(PCO) TEI: {ptei}", 1, 2)
            role = data[3] & 0x0F
            level = data[3] >> 4
            role_map_e = {0: "未知", 1: "STA", 2: "PCO", 4: "CCO"}
            _f("角色/层级数", f"{data[3]:02X}",
               f"{role_map_e.get(role, '保留(' + str(role) + ')')} 层级{level}",
               f"角色: {role_map_e.get(role, role)}, 层级数: {level}", 3, 3)
            if ln >= 10:
                mac_colon_e = ':'.join(f'{b:02X}' for b in data[4:10])
                _f("发送信标MAC", ' '.join(f'{b:02X}' for b in data[4:10]),
                   mac_colon_e, f"MAC={mac_colon_e}", 4, 9)
            if ln >= 11:
                rf_hop = data[10] & 0x0F
                band = (data[10] >> 4) & 0x07
                _f("RF跳数/载波频段", f"{data[10]:02X}",
                   f"跳数{rf_hop} 频段{band}",
                   f"链路RF跳数: {rf_hop}, 载波频段: {band}", 10, 10)
            if ln >= 15:
                csma_start_e = self._read_u32_le(data, 11)
                _f("CSMA时隙开始时间", ' '.join(f'{b:02X}' for b in data[11:15]),
                   f"{csma_start_e}NTB", f"CSMA时隙开始NTB: {csma_start_e}", 11, 14)
            if ln >= 17:
                csma_len_e = self._read_u16_le(data, 15)
                _f("CSMA时隙长度", ' '.join(f'{b:02X}' for b in data[15:17]),
                   f"{csma_len_e}ms", f"CSMA时隙持续: {csma_len_e}ms", 15, 16)
        elif etype == 0x10 and ln >= 2:  # 代理角色条目（表72）
            # 表72：长度字段之后是 N 个**连续 12 比特**的代理节点 TEI（LSB 优先位流）——
            #   代理节点1TEI = 表72 字节3 bits0-7 + 字节4 bits0-3（= 本函数的内容字节0/1）
            #   代理节点2TEI = 表72 字节4 bits4-7 + 字节5 bits0-7（= 内容字节1/2）  ……
            # 站点个数不在条目里单独计数，只能由内容比特数推出（表72：内容 = 12N 比特，
            # 奇数个站点时末尾补 4 比特保留位）⇒ N = 内容比特数 // 12。
            # 不能按「每 2 字节一个 TEI」切：实帧 `10 06 00 01 70 00` 的内容是 3 字节 = 2 个
            # 12 比特 TEI（1 和 7），按 2 字节切只解出 1 个、且第 2 个 TEI（内容字节1 高4位 +
            # 内容字节2）会被整段丢掉——这就是现场报的「代理角色 TEI 解析不对」。
            n_nodes = ln * 8 // 12
            used_bits = n_nodes * 12
            rem_bits = ln * 8 - used_bits
            raw_hex = ' '.join(f'{b:02X}' for b in data[:min(8, ln)]) + ("..." if ln > 8 else "")
            _f("代理角色条目", raw_hex, f"{ln}字节",
               f"代理站点数: {n_nodes}（{ln}字节 = {n_nodes}×12bit"
               + ("，尾4bit保留" if rem_bits == 4 else (f"，尾{rem_bits}bit未定义" if rem_bits else "")) + "）",
               0, ln - 1)
            for i in range(n_nodes):
                bit0 = i * 12
                s = bit0 // 8
                e = min((bit0 + 11) // 8, ln - 1)
                tei = self._extract_bits(data, bit0, 12)
                _f(f"代理[{i}]TEI", ' '.join(f'{b:02X}' for b in data[s:e + 1]), str(tei),
                   f"代理站点{i + 1}TEI: {tei}", s, e)
            if rem_bits:
                s = used_bits // 8
                _f("条目尾保留位", ' '.join(f'{b:02X}' for b in data[s:]), f"{rem_bits}bit",
                   f"保留（代理站点个数为奇数，尾 {rem_bits} 比特保留位）", s, ln - 1)
        else:
            return []  # 未识别类型，让调用方显示原始数据
        return t

    # ── 选择确认帧(SACK)可变区域 (字节1-12) ──

    SACK_RESULT_MAP = {0x0: "全部接收成功", 0x1: "物理块CRC校验失败"}
    SACK_SNR_TYPE_MAP = {0x0: "不携带SNR信息", 0x1: "接收当前帧SNR信息", 0x2: "反馈TF评估的基础RU信息"}
    SACK_EXT_TYPE_MAP = {0: "选择确认帧", 1: "网络搜索帧(抄控器)", 2: "同步帧(抄控器)", 3: "Bitloading扩展帧"}

    def _parse_mpdu_sack(self, frame_bytes: bytes, offset: int, table: list) -> int:
        """解析选择确认帧(SACK)可变区域 (字节1-11, 共11字节; 字节12由公共代码处理)"""
        # 字节1: 接收结果(4b) + 接收状态(4b)
        b1 = frame_bytes[offset]
        rx_result = b1 & 0x0F
        rx_status = (b1 >> 4) & 0x0F
        result_name = self.SACK_RESULT_MAP.get(rx_result, f"保留(0x{rx_result:X})")
        table.append(("接收结果",
                     f"0x{rx_result:X}",
                     str(rx_result),
                     f"SOF帧接收结果: {result_name}",
                     offset, offset))
        # 接收状态: 每bit代表一个PB的校验结果
        pb_bits = [(rx_status >> i) & 0x01 for i in range(4)]
        status_desc = " ".join(f"PB{i}:{'成功' if b else '失败'}" for i, b in enumerate(pb_bits) if (rx_status >> i) & 0x01 or rx_status)
        pb_status_parts = [f"PB{i}=OK" if b else f"PB{i}=FAIL" for i, b in enumerate(pb_bits)]
        table.append(("接收状态",
                     f"0b{rx_status:04b}",
                     str(rx_status),
                     f"PB校验: [{', '.join(pb_status_parts)}]",
                     offset, offset))
        offset += 1

        # 字节2-3: 目的TEI(12b) + 接收物理块个数(4b)
        dst_tei = frame_bytes[offset] | ((frame_bytes[offset + 1] & 0x0F) << 8)
        table.append(("目的TEI",
                     f"0x{dst_tei:03X}",
                     str(dst_tei),
                     f"选择确认帧目的终端TEI: {dst_tei}",
                     offset, offset + 1))
        rx_pb_count = (frame_bytes[offset + 1] >> 4) & 0x0F
        table.append(("接收物理块个数",
                     f"0x{rx_pb_count:X}",
                     str(rx_pb_count),
                     f"含解析错误的PB: {rx_pb_count}个",
                     offset + 1, offset + 1))
        offset += 2

        # 字节4: 短网络标识高位(1b) + SNR类型(2b) + 保留(5b)
        b4 = frame_bytes[offset]
        snid_high = b4 & 0x01
        snr_type = (b4 >> 1) & 0x03
        snr_type_name = self.SACK_SNR_TYPE_MAP.get(snr_type, f"保留(0x{snr_type:X})")
        table.append(("短网络标识高位",
                     f"0b{snid_high}",
                     str(snid_high),
                     "与低位共同构成5bit SNID",
                     offset, offset))
        table.append(("SNR类型",
                     f"0x{snr_type:X}",
                     str(snr_type),
                     f"SNR信息类型: {snr_type_name}",
                     offset, offset))
        offset += 1

        # 字节5-8[0:5]: SNR评估信息 (30b)
        # bytes 5,6,7 各8bit = 24bit + byte8[0:5] = 6bit → 共30bit
        snr_raw = frame_bytes[offset:offset + 4]
        snr_30 = int.from_bytes(snr_raw, 'big') >> 2  # byte8[6:7]是保留,所以右移2位取高30bit
        if snr_type == 0x1:
            # 5bit SNR信息
            snr_val = snr_30 & 0x1F
            snr_desc = f"当前帧SNR: {snr_val}"
        elif snr_type == 0x2:
            # 6个5bit RU SNR信息 (RU0-RU5)
            ru_snrs = [(snr_30 >> (i * 5)) & 0x1F for i in range(6)]
            snr_desc = "基础RU SNR: " + ", ".join(f"RU{i}={v}" for i, v in enumerate(ru_snrs))
        else:
            snr_desc = "保留字段"
        table.append(("SNR评估信息",
                     ' '.join(f'{b:02X}' for b in snr_raw),
                     f"0x{snr_30:08X}",
                     snr_desc,
                     offset, offset + 3))
        offset += 4

        # 字节8[6:7] + 字节9-11: 保留 (26b)
        offset += 3  # 跳过保留字节(byte8高2位已包含在上面, byte9-11)


        return offset + 11  # 字节1-11共11字节(字节12由公共代码处理)

    def _parse_mpdu_sack_bitloading(self, frame_bytes: bytes, offset: int, table: list) -> int:
        """解析 Bitloading 扩展帧可变区域 (SACK 定界符类型，扩展帧类型=3)

        帧结构: 字节1-11 为可变区域，定义见《数据链路层通信协议》表34。
        字节12=扩展帧类型(3)+标准版本号，由公共代码处理。
        """
        base = offset  # 字节1起始偏移

        # 字节1-2: 源TEI (12bit: 字节1全部 + 字节2低4bit)
        # 字节2-3: 目的TEI (12bit: 字节2高4bit + 字节3全部)
        src_tei = frame_bytes[offset] | ((frame_bytes[offset + 1] & 0x0F) << 8)
        dst_tei = ((frame_bytes[offset + 1] >> 4) & 0x0F) | (frame_bytes[offset + 2] << 4)
        table.append(("源TEI",
                      ' '.join(f'{b:02X}' for b in frame_bytes[offset:offset + 2]),
                      f"0x{src_tei:03X}",
                      f"Bitloading扩展帧源终端TEI: {src_tei}",
                      offset, offset + 1))
        table.append(("目的TEI",
                      ' '.join(f'{b:02X}' for b in frame_bytes[offset + 1:offset + 3]),
                      f"0x{dst_tei:03X}",
                      f"Bitloading扩展帧目的终端TEI: {dst_tei}",
                      offset + 1, offset + 2))
        offset += 3

        # 字节4: 短网络标识高位(1bit) + Bitloading帧类型(3bit) + 可变区域高4bit
        b4 = frame_bytes[offset]
        snid_high = b4 & 0x01
        bl_frame_type = (b4 >> 1) & 0x07
        bl_type_names = {
            0: "训练指示",
            1: "训练指示拒绝",
            2: "训练请求",
            3: "训练请求拒绝",
            4: "训练取消请求",
            5: "训练取消确认",
        }
        bl_type_name = bl_type_names.get(bl_frame_type, f"保留({bl_frame_type})")
        table.append(("短网络标识高位",
                      f"0b{snid_high}",
                      str(snid_high),
                      "与MPDU帧控制固定字段的短网络标识低位共同构成5bit SNID",
                      offset, offset))
        table.append(("Bitloading帧类型",
                      f"0x{bl_frame_type:X}",
                      str(bl_frame_type),
                      f"Bitloading帧类型: {bl_type_name}",
                      offset, offset))
        offset += 1

        # 字节4高4bit + 字节5-11: 60bit 可变区域，根据Bitloading帧类型解析
        var_data = frame_bytes[offset - 1:offset + 7]  # 字节4-11 (8字节)
        # 取60bit有效数据: 字节4高4bit + 字节5-11
        var_60 = ((var_data[0] >> 4) & 0x0F) | (int.from_bytes(var_data[1:8], 'big') << 4)
        table.append(("Bitloading可变区域",
                      ' '.join(f'{b:02X}' for b in var_data),
                      f"0x{var_60:015X}",
                      f"{bl_type_name}可变区域(60bit)",
                      offset - 1, offset + 6))

        # 根据Bitloading帧类型解析子字段
        if bl_frame_type == 0:
            # 训练指示: 训练控制帧类型固定填0，其余保留
            ctrl_type = (b4 >> 1) & 0x07
            table.append(("训练控制帧类型",
                          f"0x{ctrl_type:X}",
                          str(ctrl_type),
                          "0: 发端站点主动启动训练",
                          offset - 1, offset - 1))
        elif bl_frame_type == 1:
            # 训练指示拒绝: 拒绝原因
            reject_reason = (b4 >> 4) & 0x0F
            reason_names = {1: "站点正在训练", 2: "训练站点已满"}
            reason_name = reason_names.get(reject_reason, f"保留({reject_reason})")
            table.append(("拒绝原因",
                          f"0x{reject_reason:X}",
                          str(reject_reason),
                          f"训练指示拒绝原因: {reason_name}",
                          offset - 1, offset - 1))
        elif bl_frame_type == 2:
            # 训练请求: 流数 + 子载波分组大小
            stream_count = (b4 >> 4) & 0x01
            group_size = (b4 >> 5) & 0x03
            group_names = {0: "1个子载波一组", 1: "2个子载波一组", 2: "4个子载波一组", 3: "8个子载波一组"}
            table.append(("流数",
                          f"0x{stream_count:X}",
                          str(stream_count),
                          f"训练流数: {'双流' if stream_count else '单流'}",
                          offset - 1, offset - 1))
            table.append(("子载波分组大小",
                          f"0x{group_size:X}",
                          str(group_size),
                          f"子载波分组: {group_names.get(group_size, f'保留({group_size})')}",
                          offset - 1, offset - 1))
        elif bl_frame_type == 3:
            # 训练请求拒绝: 拒绝原因
            reject_reason = (b4 >> 4) & 0x0F
            reason_names = {0: "站点正在训练", 1: "训练站点已满"}
            reason_name = reason_names.get(reject_reason, f"保留({reject_reason})")
            table.append(("拒绝原因",
                          f"0x{reject_reason:X}",
                          str(reject_reason),
                          f"训练请求拒绝原因: {reason_name}",
                          offset - 1, offset - 1))
        elif bl_frame_type == 4:
            # 训练取消请求: 无附加字段
            pass
        elif bl_frame_type == 5:
            # 训练取消确认: 无附加字段
            pass

        offset += 7  # 字节5-11共7字节
        return offset  # 返回字节12起始位置

    # ── HRF（高速无线）MPDU 可变区域解析 ──

    def _parse_mpdu_sof_hrf(self, frame_bytes: bytes, offset: int, table: list) -> int:
        """解析 HRF（高速无线）SOF 帧可变区域（92bit = 字节1~11 + 字节12低4位）

        字段分配（bit 以可变区域起始为 bit0）:
        0-11:  源TEI(12b)
        12-23: 目的TEI(12b)
        24-31: 链路标识符(8b)
        32-43: 帧长(12b)，单位 100μs
        44-47: 载荷PB大小(4b)
        48-51: MCS(4b)
        52:    TEI过滤标志(1b)
        53:    重传标志(1b)
        54-55: 保留(2b)
        56-87: 保留(32b)  字节8~字节11
        88:    SNID高位(1b)  字节12[0]
        89-91: 保留(3b)    字节12[1-3]

        返回字节12起始偏移。
        """
        base = offset  # 字节1的偏移
        # 源 TEI (12b): 字节1[0-7] + 字节2[0-3]
        src_tei = frame_bytes[base] | ((frame_bytes[base + 1] & 0x0F) << 8)
        table.append(("源TEI", f"0x{src_tei:03X}", str(src_tei),
                     "发送站点TEI", base, base + 1))

        # 目的 TEI (12b): 字节2[4-7] + 字节3[0-7]
        dst_tei = ((frame_bytes[base + 1] >> 4) & 0x0F) | (frame_bytes[base + 2] << 4)
        table.append(("目的TEI", f"0x{dst_tei:03X}", str(dst_tei),
                     "接收站点TEI", base + 1, base + 2))

        # 链路标识符 (8b): 字节4
        link_id = frame_bytes[base + 3]
        table.append(("链路标识符", f"0x{link_id:02X}", str(link_id),
                     "0-3: 优先级  4-254: 业务分类LID  255: 无效",
                     base + 3, base + 3))

        # 帧长 (12b): 字节5[0-7] + 字节6[0-3]，单位 100μs
        frame_len = frame_bytes[base + 4] | ((frame_bytes[base + 5] & 0x0F) << 8)
        table.append(("帧长", f"0x{frame_len:03X}", str(frame_len),
                     f"{frame_len} × 100μs = {frame_len * 0.1:.1f}ms",
                     base + 4, base + 5))

        # 载荷PB大小 (4b): 字节6[4-7]
        pb_size_idx = (frame_bytes[base + 5] >> 4) & 0x0F
        pb_size = self.HRF_PB_SIZE_TABLE.get(pb_size_idx, f"保留({pb_size_idx})")
        table.append(("载荷PB大小", f"0x{pb_size_idx:X}", str(pb_size_idx),
                     f"{pb_size} 字节" if isinstance(pb_size, int) else pb_size,
                     base + 5, base + 5))
        self._pb_size = pb_size if isinstance(pb_size, int) else 136
        self._pb_count = 1  # 无线仅支持 1 个 PB

        # MCS (4b): 字节7[0-3]
        mcs = frame_bytes[base + 6] & 0x0F
        mcs_info = self.HRF_MCS_TABLE.get(mcs, {})
        if mcs_info:
            mcs_desc = (f"{mcs_info['modulation']} {mcs_info['code_rate']}，"
                        f"{mcs_info['diversity']}分集")
        else:
            mcs_desc = "保留"
        table.append(("MCS", f"0x{mcs:X}", str(mcs), mcs_desc, base + 6, base + 6))

        # TEI过滤标志: 字节7[4]
        tei_filter = (frame_bytes[base + 6] >> 4) & 0x01
        table.append(("TEI过滤标志", f"0b{tei_filter}", str(tei_filter),
                     "不过滤" if tei_filter else "过滤",
                     base + 6, base + 6))

        # 重传标志: 字节7[5]
        retransmit = (frame_bytes[base + 6] >> 5) & 0x01
        table.append(("重传标志", f"0b{retransmit}", str(retransmit),
                     "重传报文" if retransmit else "非重传",
                     base + 6, base + 6))

        # 字节7[6-7] 保留 + 字节8~11 保留(32b) + 字节12[0] SNID高位 + 字节12[1-3]保留
        snid_high = (frame_bytes[base + 11] >> 0) & 0x01  # 字节12 = base + 11
        table.append(("SNID高位", f"0b{snid_high}", str(snid_high),
                     "短网络标识最高位",
                     base + 11, base + 11))

        return base + 11  # 返回字节12起始位置（版本号+扩展帧类型等公共字段在外面解析）

    def _parse_mpdu_beacon_hrf(self, frame_bytes: bytes, offset: int, table: list) -> int:
        """解析 HRF（高速无线）信标帧可变区域（92bit = 字节1~11 + 字节12低4位）

        字段:
        0-31:  信标时间戳(32b)
        32-63: 信标周期计数(32b)
        64-75: 源TEI(12b)
        76-79: MCS(4b)
        80-83: 载荷PB大小(4b)
        84-87: 保留(4b)
        88:    SNID高位(1b)
        89-91: 保留(3b)

        返回字节12起始偏移。
        """
        base = offset
        # 信标时间戳 (32b): 字节1~4，小端
        ts = int.from_bytes(frame_bytes[base:base + 4], 'little')
        table.append(("信标时间戳", f"0x{ts:08X}", str(ts),
                     "网络基准时间", base, base + 3))

        # 信标周期计数 (32b): 字节5~8，小端
        bcn_period = int.from_bytes(frame_bytes[base + 4:base + 8], 'little')
        table.append(("信标周期计数", f"0x{bcn_period:08X}", str(bcn_period),
                     "信标周期序号", base + 4, base + 7))

        # 源 TEI (12b): 字节9[0-7] + 字节10[0-3]
        src_tei = frame_bytes[base + 8] | ((frame_bytes[base + 9] & 0x0F) << 8)
        table.append(("源TEI", f"0x{src_tei:03X}", str(src_tei),
                     "信标发送站点TEI", base + 8, base + 9))

        # MCS (4b): 字节10[4-7]
        mcs = (frame_bytes[base + 9] >> 4) & 0x0F
        mcs_info = self.HRF_MCS_TABLE.get(mcs, {})
        if mcs_info:
            mcs_desc = (f"{mcs_info['modulation']} {mcs_info['code_rate']}，"
                        f"{mcs_info['diversity']}分集")
        else:
            mcs_desc = "保留"
        table.append(("MCS", f"0x{mcs:X}", str(mcs), mcs_desc, base + 9, base + 9))

        # 载荷PB大小 (4b): 字节11[0-3]
        pb_size_idx = frame_bytes[base + 10] & 0x0F
        pb_size = self.HRF_PB_SIZE_TABLE.get(pb_size_idx, f"保留({pb_size_idx})")
        table.append(("载荷PB大小", f"0x{pb_size_idx:X}", str(pb_size_idx),
                     f"{pb_size} 字节" if isinstance(pb_size, int) else pb_size,
                     base + 10, base + 10))
        self._pb_size = pb_size if isinstance(pb_size, int) else 136
        self._pb_count = 1

        # SNID高位: 字节12[0] 即 base + 11 字节
        snid_high = frame_bytes[base + 11] & 0x01
        table.append(("SNID高位", f"0b{snid_high}", str(snid_high),
                     "短网络标识最高位", base + 11, base + 11))

        return base + 11  # 返回字节12起始位置

    def _parse_mpdu_sack_hrf(self, frame_bytes: bytes, offset: int, table: list) -> int:
        """解析 HRF（高速无线）SACK 帧可变区域（92bit = 字节1~11 + 字节12低4位）

        字段:
        0-3:   接收结果(4b)
        4:     SNID高位(1b)
        5-7:   保留(3b)
        8-19:  目的TEI(12b)
        20-23: 保留(4b)
        24-87: 保留(64b)  字节4~11
        88-91: 扩展帧类型(4b)  字节12[0-3]

        返回字节12起始偏移。
        """
        base = offset
        b0 = frame_bytes[base]
        rx_result = b0 & 0x0F
        snid_high = (b0 >> 4) & 0x01
        result_map = {0: "接收成功", 1: "物理块CRC失败"}
        table.append(("接收结果", f"0x{rx_result:X}", str(rx_result),
                     result_map.get(rx_result, f"保留({rx_result})"),
                     base, base))
        table.append(("SNID高位", f"0b{snid_high}", str(snid_high),
                     "短网络标识最高位", base, base))

        # 目的 TEI (12b): 字节2[0-7] + 字节3[0-3]
        dst_tei = frame_bytes[base + 1] | ((frame_bytes[base + 2] & 0x0F) << 8)
        table.append(("目的TEI", f"0x{dst_tei:03X}", str(dst_tei),
                     "接收SACK的站点TEI", base + 1, base + 2))

        return base + 11  # 返回字节12起始位置（扩展帧类型等在外面字节12处读）

    def _parse_mac_frame(self, frame_bytes: bytes, base_offset: int = 0,
                        parse_msdu_app: bool = False) -> Tuple[int, list]:
        """解析 MAC 帧头
        
        注意：frame_bytes 是切片后的数据，内部解析使用相对偏移(offset=0)，
        但 byte_start/byte_end 使用全局偏移(base_offset + offset)
        """
        table = []
        frame_len = len(frame_bytes)
        offset = 0  # 相对偏移，frame_bytes 是切片

        first_byte = frame_bytes[offset]
        header_type = (first_byte >> 0) & 0x01
        version = (first_byte >> 1) & 0x03
        short_nid_high = (first_byte >> 3) & 0x01
        tx_seq_low4 = (first_byte >> 4) & 0x0F  # 发送序号低4位(字节0 bit4-7)

        # 帧头长度：版本2=单跳帧协议(表12, 4字节，帧头类型无意义，仅无线信道使用)
        # 版本1=标准帧协议，按帧头类型分 32B 长头 / 12B 短头
        if version == 2:
            header_size = 4
        else:
            header_size = 12 if header_type == 1 else 32

        if frame_len < header_size + 4:  # 至少需要头部 + 4字节CRC
            table.append(("❌ 解析失败", "", "", f"MAC帧长度不足(需要>{header_size + 4}字节)", None, None))
            return base_offset, table

        # 版本2=单跳帧协议（表12，仅无线信道）：帧头4字节，MSDU类型在MAC头内，载荷内联分派
        if version == 2:
            return self._parse_single_hop_mac(frame_bytes, base_offset, table)

        # 辅助函数：记录全局偏移
        def _g(rel_start: int, rel_end: int) -> Tuple[int, int]:
            return base_offset + rel_start, base_offset + rel_end

        # ── MAC 帧头固定部分 ──
        table.append((
            "帧头类型",
            f"0x{header_type:01X}",
            str(header_type),
            MAC_HEADER_TYPE_MAP.get(header_type, "未知"),
            *_g(offset, offset)
        ))
        table.append((
            "版本",
            f"0x{version:01X}",
            str(version),
            MAC_VERSION_MAP.get(version, f"保留({version})"),
            *_g(offset, offset)
        ))

        # 短网络标识高位 (1 bit: byte0[3])
        table.append((
            "短网络标识高位",
            f"0b{short_nid_high}",
            str(short_nid_high),
            "短网络标识的最高1bit",
            *_g(offset, offset)
        ))

        # 发送序号 (12 bits, 小端: 字节0 bit4-7 为低4位, 字节1 为高8位)
        tx_seq_high8 = frame_bytes[offset + 1]  # 高8位
        tx_seq = (tx_seq_high8 << 4) | tx_seq_low4
        table.append((
            "发送序号",
            f"0x{tx_seq:03X}",
            str(tx_seq),
            f"SOF帧发送序号(含重传)",
            *_g(offset, offset + 1)
        ))

        # MSDU 长度 (2字节, 小端序)
        msdu_len = int.from_bytes(frame_bytes[offset + 2:offset + 4], 'little')
        table.append((
            "MSDU长度",
            ' '.join(f'{b:02X}' for b in frame_bytes[offset + 2:offset + 4]),
            f"{msdu_len}字节",
            f"携带的MSDU长度 ({msdu_len}B)",
            *_g(offset + 2, offset + 3)
        ))

        # 原始目的 TEI (12 bits: byte4[0:7] + byte5[0:3])
        dest_tei = frame_bytes[offset + 4] | ((frame_bytes[offset + 5] & 0x0F) << 8)
        table.append((
            "原始目的TEI",
            f"0x{dest_tei:03X}",
            str(dest_tei),
            f"MSDU目的终端设备标识",
            *_g(offset + 4, offset + 5)
        ))

        # 原始源 TEI (12 bits: byte5[4:7] + byte6[0:7])
        src_tei = ((frame_bytes[offset + 5] >> 4) & 0x0F) | (frame_bytes[offset + 6] << 4)
        table.append((
            "原始源TEI",
            f"0x{src_tei:03X}",
            str(src_tei),
            f"创建该报文站点的TEI",
            *_g(offset + 5, offset + 6)
        ))

        # 短网络标识低位 (4 bits) + 重启次数 (4 bits)
        short_nid_low = frame_bytes[offset + 7] & 0x0F
        reboot_count = (frame_bytes[offset + 7] >> 4) & 0x0F
        short_nid = (short_nid_high << 4) | short_nid_low
        table.append((
            "短网络标识(SNID)",
            f"0x{short_nid:02X}",
            str(short_nid),
            f"网络标识 {short_nid} (有效1-31)",
            *_g(offset + 7, offset + 7)
        ))
        table.append((
            "重启次数",
            f"0x{reboot_count:01X}",
            str(reboot_count),
            f"站点重启次数 {reboot_count}",
            *_g(offset + 7, offset + 7)
        ))

        # 路由跳数 (4 bits) + 广播方向 (4 bits)
        hop_count = frame_bytes[offset + 8] & 0x0F
        broadcast_dir = (frame_bytes[offset + 8] >> 4) & 0x0F
        table.append((
            "路由跳数",
            f"0x{hop_count:01X}",
            str(hop_count),
            f"最大转发跳数: {hop_count}",
            *_g(offset + 8, offset + 8)
        ))
        table.append((
            "广播方向",
            f"0x{broadcast_dir:01X}",
            str(broadcast_dir),
            BROADCAST_DIR_MAP.get(broadcast_dir, f"保留({broadcast_dir})"),
            *_g(offset + 8, offset + 8)
        ))

        # 发送类型 (3 bits) + 发送次数限值 (5 bits)
        send_type = frame_bytes[offset + 9] & 0x07
        max_send = (frame_bytes[offset + 9] >> 3) & 0x1F
        table.append((
            "发送类型",
            f"0x{send_type:01X}",
            str(send_type),
            SEND_TYPE_MAP.get(send_type, f"保留({send_type})"),
            *_g(offset + 9, offset + 9)
        ))
        table.append((
            "发送次数限值",
            f"0x{max_send:02X}",
            str(max_send),
            f"最大发送次数: {max_send}" + (" (使用默认)" if max_send == 0 else ""),
            *_g(offset + 9, offset + 9)
        ))

        # MSDU 序列号 (2字节)
        msdu_seq = int.from_bytes(frame_bytes[offset + 10:offset + 12], 'little')
        table.append((
            "MSDU序列号",
            ' '.join(f'{b:02X}' for b in frame_bytes[offset + 10:offset + 12]),
            str(msdu_seq),
            f"MSDU递增序列号: {msdu_seq}",
            *_g(offset + 10, offset + 11)
        ))

        if header_type == 0:  # 长帧头 (32字节)
            # 目的MAC地址 (6字节)
            dest_mac = ':'.join(f'{b:02X}' for b in frame_bytes[offset + 12:offset + 18])
            table.append((
                "目的MAC地址",
                ' '.join(f'{b:02X}' for b in frame_bytes[offset + 12:offset + 18]),
                dest_mac,
                f"原始目的MAC地址",
                *_g(offset + 12, offset + 17)
            ))
            # 保留字段
            table.append((
                "保留字段1",
                ' '.join(f'{b:02X}' for b in frame_bytes[offset + 18:offset + 22]),
                "4字节",
                "保留",
                *_g(offset + 18, offset + 21)
            ))
            table.append((
                "保留字段2",
                ' '.join(f'{b:02X}' for b in frame_bytes[offset + 22:offset + 32]),
                "10字节",
                "保留",
                *_g(offset + 22, offset + 31)
            ))

        new_offset = offset + header_size
        # 使用MSDU长度字段计算结束位置（如果数据足够），否则回退到frame_len - 4
        if frame_len >= new_offset + msdu_len + 4:
            msdu_end = new_offset + msdu_len
        elif frame_len >= new_offset + 4:
            msdu_end = frame_len - 4
        else:
            msdu_end = frame_len

        # MSDU 负载（含 MSDU头判定 + 应用层解析）
        # 聚合帧级联块(parse_msdu_app=True)在此解析应用层；
        # 单MAC帧路径由调用方(parse_to_table主流程)兜底解析，避免重复
        msdu_bytes = frame_bytes[new_offset:msdu_end]
        if msdu_bytes:
            if parse_msdu_app:
                self._parse_msdu_payload(msdu_bytes, base_offset + new_offset,
                                         frame_bytes[offset:new_offset], table,
                                         False)
            else:
                table.append((
                    "MSDU负载",
                    ' '.join(f'{b:02X}' for b in msdu_bytes[:20]) + ("..." if len(msdu_bytes) > 20 else ""),
                    f"{len(msdu_bytes)}字节",
                    f"MAC业务数据单元",
                    *_g(new_offset, msdu_end - 1)
                ))

        # 完整性校验 (CRC-32, 4字节, 最后4字节)
        if frame_len >= new_offset + 4:
            crc_bytes = frame_bytes[msdu_end:msdu_end + 4]
            crc_val = int.from_bytes(crc_bytes, 'little')
            # CRC-32 校验：计算范围 MSDU 负载（new_offset 已是相对偏移，无需加 base_offset）
            msdu_data_for_crc = frame_bytes[new_offset:msdu_end]
            crc32_calc = self._crc32_ieee(msdu_data_for_crc)
            crc32_match = (crc32_calc == crc_val)
            crc_desc = f"32位循环冗余校验(CRC-32)，计算范围: MSDU负载，CRC32=0x{crc_val:08X}"
            crc_desc += "，校验通过" if crc32_match else f"，校验失败(计算值=0x{crc32_calc:08X})"
            table.append((
                "完整性校验(CRC-32)",
                ' '.join(f'{b:02X}' for b in crc_bytes),
                f"0x{crc_val:08X}",
                crc_desc,
                *_g(msdu_end, msdu_end + 3)
            ))
            new_offset = msdu_end + 4

        return base_offset + new_offset, table

    def _parse_single_hop_mac(self, frame_bytes: bytes, base_offset: int,
                              table: list) -> Tuple[int, list]:
        """解析无线信道单跳MAC帧头（表12，4字节）+ 载荷内联分派 + CRC-32

        MAC帧头固定域（表12）:
          字节0: 帧头类型(1b) + 版本(2b) + 保留(5b)   （帧头类型在单跳帧协议下无意义）
          字节1: MSDU类型(8b)                         （表13）
          字节2-3: MSDU长度(16b, 小端)
        载荷无VLAN+MSDU类型前缀，直接为业务数据，按MSDU类型分派：
          1=应用层报文 / 2=无线发现列表消息 / 128=IPV4报文
        尾部完整性校验 CRC-32（计算范围 MSDU 载荷，同其它MAC帧）。
        仅无线信道使用（版本2 单跳帧协议，表5/表6）。
        """
        offset = 0

        def _g(rel_start: int, rel_end: int) -> Tuple[int, int]:
            return base_offset + rel_start, base_offset + rel_end

        first_byte = frame_bytes[offset]
        header_type = (first_byte >> 0) & 0x01
        version = (first_byte >> 1) & 0x03
        reserved5 = (first_byte >> 3) & 0x1F
        table.append(("帧头类型", f"0x{header_type:01X}", str(header_type),
                     "单跳帧协议下无意义", *_g(offset, offset)))
        table.append(("版本", f"0x{version:01X}", str(version),
                     MAC_VERSION_MAP.get(version, f"保留({version})"), *_g(offset, offset)))
        table.append(("保留", f"0b{reserved5:05b}", str(reserved5),
                     "保留", *_g(offset, offset)))

        msdu_type = frame_bytes[offset + 1]
        table.append(("MSDU类型", f"0x{msdu_type:02X}", str(msdu_type),
                     MSDU_TYPE_MAP.get(msdu_type, f"保留(0x{msdu_type:02X})"),
                     *_g(offset + 1, offset + 1)))

        msdu_len = int.from_bytes(frame_bytes[offset + 2:offset + 4], 'little')
        table.append(("MSDU长度", ' '.join(f'{b:02X}' for b in frame_bytes[offset + 2:offset + 4]),
                     f"{msdu_len}字节", f"携带的MSDU长度 ({msdu_len}B)",
                     *_g(offset + 2, offset + 3)))

        new_offset = offset + 4
        msdu_end = new_offset + msdu_len
        if msdu_end > len(frame_bytes):
            msdu_end = len(frame_bytes)
        payload = frame_bytes[new_offset:msdu_end]

        # 载荷内联分派（无线单跳帧 MSDU 类型在 MAC 头内，载荷无 VLAN/类型前缀）
        if msdu_type == 0x01:
            app_table = self._parse_application_message(payload, base_offset=new_offset)
            table.extend(app_table)
        elif msdu_type == 0x02:
            rf_table = self._parse_rf_discover_node_list(payload, base_offset=new_offset)
            table.extend(rf_table)
        elif msdu_type == 0x80:
            table.append(("IPV4数据", ' '.join(f'{b:02X}' for b in payload),
                         f"{len(payload)}字节", "IPV4报文负载",
                         *_g(new_offset, max(new_offset, new_offset + len(payload) - 1))))
        else:
            raw_hex = ' '.join(f'{b:02X}' for b in payload)
            table.append(("MSDU负载", raw_hex[:200] + ("..." if len(raw_hex) > 200 else ""),
                         f"{len(payload)}字节",
                         f"MSDU类型{msdu_type}的数据",
                         *_g(new_offset, max(new_offset, new_offset + len(payload) - 1))))

        # 完整性校验 (CRC-32, 4字节)
        if len(frame_bytes) >= msdu_end + 4:
            crc_bytes = frame_bytes[msdu_end:msdu_end + 4]
            crc_val = int.from_bytes(crc_bytes, 'little')
            crc32_calc = self._crc32_ieee(payload)
            crc32_match = (crc32_calc == crc_val)
            crc_desc = f"32位循环冗余校验(CRC-32)，计算范围: MSDU负载，CRC32=0x{crc_val:08X}"
            crc_desc += "，校验通过" if crc32_match else f"，校验失败(计算值=0x{crc32_calc:08X})"
            table.append(("完整性校验(CRC-32)", ' '.join(f'{b:02X}' for b in crc_bytes),
                         f"0x{crc_val:08X}", crc_desc, *_g(msdu_end, msdu_end + 3)))
            msdu_end = msdu_end + 4

        return base_offset + msdu_end, table

    # ── 关联请求报文常量映射（文档表78~表91）──

    # 链路类型（表79）
    LINK_TYPE_MAP = {0: "高速载波链路", 1: "无线链路"}

    # 相线值（表80）
    PHASE_MAP = {0: "未知", 1: "A相", 2: "B相", 3: "C相"}

    # 设备类型（表81）
    DEVICE_TYPE_MAP = {
        0x01: "抄控器",
        0x02: "集中器通信模块",
        0x03: "单相电表通信模块",
        0x04: "中继器",
        0x05: "II型采集器",
        0x06: "I型采集器",
        0x07: "三相表通信模块",
    }

    # 扩展特性版本号（表82）
    EXT_FEATURE_MAP = {0x01: "支持应用层多帧抄读"}

    # MAC地址类型（表83）
    MAC_ADDR_TYPE_MAP = {
        0x00: "电能表地址作为入网MAC地址",
        0x01: "通信模块本身MAC地址作为入网MAC地址",
        0x02: "采集器地址作为入网MAC地址",
    }

    # 模块类型（表84）
    MODULE_TYPE_MAP = {
        0: "HPLC单模模块",
        1: "双模HPLC和RF模块",
        2: "无线单模模块",
    }

    # 代理类型（表88）
    PROXY_TYPE_MAP = {
        0x01: "保留",
        0x02: "站点自己动态选择的代理",
    }

    # PLC能力指示（表89）
    PLC_CAPABILITY_MAP = {
        0: "本站点支持BPLC版本",
        1: "本站点支持BPLC版本和ISAC-PLC版本",
    }

    # 通道数（表90）
    CHANNEL_COUNT_MAP = {0: "单通道", 1: "多通道"}

    # 管理消息类型 (MMTYPE, 2字节小端序)
    # 参照《通感一体化低压电力线宽带载波通信规约 第4部分》表77
    MGMT_MSG_TYPE_MAP = {
        0x0030: "关联请求(MMeAssocReq)",
        0x0031: "关联确认(MMeAssocCnf)",
        0x0032: "代理变更请求(MMeChangeProxyReq)",
        0x0034: "关联指示(MMeAssocInd)",
        0x0037: "代理变更确认(MMeChangeProxyCnf)",
        0x003A: "关联汇总指示(MMeAssocGatherInd)",
        0x003B: "代理变更确认(MMeChangeProxyBitMapCnf)",
        0x0049: "离线指示(MMeLeaveInd)",
        0x0051: "心跳检测(MMeHeartBeatCheck)",
        0x0055: "发现列表(MMeDiscoverNodeList)",
        0x005D: "延迟离线指示(MMeDelayLeaveInd)",
        0x005E: "通信成功率上报(MMeSuccessRateReport)",
        0x005F: "网络冲突上报(MMeNetworkConflictReport)",
        0x0062: "过零NTB采集指示(MMeZeroCrossNTBCollectInd)",
        0x0063: "过零NTB上报(MMeZeroCrossNTBReport)",
        0x0064: "网络诊断(MMeDiagnose)",
        0x0070: "无线信道冲突上报(MMeRFChannelConflictReport)",
        0x0080: "Bitloading训练结果更新请求",
        0x0081: "Bitloading训练结果更新确认",
        0x0082: "RU_SNR信息告知",
        0x0083: "站点TEI列表请求",
        0x0084: "站点TEI列表回复",
        0x0085: "扩展网络冲突上报",
    }

    def _scan_mgmt_msdu_offset(self, msdu_payload: bytes, max_scan: int = 32) -> int | None:
        """在MSDU负载中扫描网络管理消息的特征模式。

        网络管理消息特征（依据表185 应用报文分类规则表）:
          VLAN标签 = 0x8100 (4字节小端序: 00 81 00 00)
          MSDU类型 = 0x88E1 (2字节小端序: E1 88)

        返回: MSDU类型字段在payload中的字节偏移（即E1 88的起始位置），
              未找到则返回None。
        """
        if len(msdu_payload) < 8:
            return None
        # 搜索特征: VLAN=0x8100 (4B LE: 00 81 00 00) 紧接着 MSDU类型=0x88E1 (2B LE: E1 88)
        # 特征序列: 00 81 00 00 E1 88
        vlan_tag_le = b'\x00\x81\x00\x00'
        msdu_type_le = b'\xe1\x88'
        scan_end = min(max_scan, len(msdu_payload) - 6)
        for off in range(0, scan_end + 1):
            if msdu_payload[off:off + 4] == vlan_tag_le:
                # VLAN标签找到，检查紧接着的MSDU类型
                type_off = off + 4
                if type_off + 2 <= len(msdu_payload):
                    if msdu_payload[type_off:type_off + 2] == msdu_type_le:
                        return type_off
        return None

    def _parse_management_message(self, mgmt_data: bytes, base_offset: int = 0) -> list:
        """解析管理消息（MSDU类型 0x02/0x88E1）

        管理消息报文头格式（表76）:
          管理消息版本(1B) + 管理消息类型(MMTYPE, 2B, 小端序) + 保留(3B)
        """
        table = []
        if not mgmt_data:
            table.append((
                "❌ 管理消息解析失败", "", "", "管理消息数据为空", None, None
            ))
            return table

        offset = 0

        # ── 管理消息版本 (1字节) ──
        if offset + 1 > len(mgmt_data):
            table.append((
                "❌ 管理消息解析失败", "", "", "管理消息数据长度不足（<1字节）", None, None
            ))
            return table

        mgmt_version = mgmt_data[offset]
        table.append((
            "管理消息版本",
            f"{mgmt_version:02X}",
            str(mgmt_version),
            f"管理消息版本号: {mgmt_version}",
            base_offset + offset, base_offset + offset
        ))
        offset += 1

        # ── 管理消息类型 (MMTYPE, 2字节, 小端序) ──
        if offset + 2 > len(mgmt_data):
            table.append((
                "❌ 管理消息解析失败", "", "", "管理消息数据长度不足（<2字节）", None, None
            ))
            return table

        mgmt_type = int.from_bytes(mgmt_data[offset:offset + 2], 'little')
        type_name = self.MGMT_MSG_TYPE_MAP.get(mgmt_type, f"保留(0x{mgmt_type:04X})")
        table.append((
            "管理消息类型(MMTYPE)",
            ' '.join(f'{b:02X}' for b in mgmt_data[offset:offset + 2]),
            f"0x{mgmt_type:04X}",
            f"管理消息: {type_name}",
            base_offset + offset, base_offset + offset + 1
        ))
        offset += 2

        # ── 保留字段 (3字节) ──
        if offset + 3 <= len(mgmt_data):
            reserved = mgmt_data[offset:offset + 3]
            table.append((
                "保留",
                ' '.join(f'{b:02X}' for b in reserved),
                "3字节",
                "保留字段",
                base_offset + offset, base_offset + offset + 2
            ))
            offset += 3

        # ── 根据管理消息类型分发到具体解析器 ──
        payload = mgmt_data[offset:]
        parser_map = {
            0x0030: self._parse_assoc_req,
            0x0031: self._parse_assoc_cnf,
            0x0032: self._parse_change_proxy_req,
            0x0034: self._parse_assoc_ind,
            0x0037: self._parse_change_proxy_cnf,
            0x003A: self._parse_assoc_gather_ind,
            0x003B: self._parse_change_proxy_bitmap_cnf,
            0x0049: self._parse_leave_ind,
            0x0051: self._parse_heartbeat_check,
            0x0055: self._parse_discover_node_list,
            0x005D: self._parse_delay_leave_ind,
            0x005E: self._parse_success_rate_report,
            0x005F: self._parse_network_conflict_report,
            0x0062: self._parse_zero_cross_ntb_collect_ind,
            0x0063: self._parse_zero_cross_ntb_report,
            0x0064: self._parse_diagnose,
            0x0070: self._parse_rf_channel_conflict_report,
            0x0080: self._parse_bitloading_update_req,
            0x0081: self._parse_bitloading_update_cnf,
            0x0082: self._parse_ru_snr_info,
            0x0083: self._parse_tei_list_req,
            0x0084: self._parse_tei_list_reply,
            0x0085: self._parse_ext_network_conflict_report,
        }
        parser = parser_map.get(mgmt_type)
        if parser:
            parsed = parser(payload, base_offset + offset)
            table.extend(parsed)
        elif payload:
            table.append((
                "管理消息数据",
                ' '.join(f'{b:02X}' for b in payload[:30]) + ("..." if len(payload) > 30 else ""),
                f"{len(payload)}字节",
                f"{type_name}消息原始数据（尚未实现结构化解析）",
                base_offset + offset, base_offset + len(mgmt_data) - 1
            ))
        return table

    def _parse_assoc_req(self, data: bytes, base_offset: int = 0) -> list:
        """解析关联请求报文 MMeAssocReq（文档表78，共68字节）"""
        table = []
        offset = 0
        length = len(data)
        # 规范长度 68 字节；不足时按实际长度解析并提示
        expected_len = 68
        if length < expected_len:
            table.append((
                "⚠️ 关联请求报文",
                f"{length}字节",
                f"{length}字节",
                f"报文长度不足（规范要求 {expected_len} 字节），以下按实际长度解析",
                base_offset, base_offset + length - 1
            ))

        # ── 站点MAC地址 (6字节) ──
        if offset + 6 <= length:
            mac_raw, mac_colon = self._mac_addr(data, offset)
            table.append((
                "  站点MAC地址",
                mac_raw,
                mac_colon,
                "发起关联请求的终端设备地址",
                base_offset + offset, base_offset + offset + 5
            ))
            offset += 6

        # ── 候选代理 TEI (5个，各2字节小端序) ──
        for i in range(5):
            if offset + 2 <= length:
                tei = int.from_bytes(data[offset:offset + 2], 'little')
                desc = f"候选代理{i} TEI" if tei else "保留"
                table.append((
                    f"  候选代理{i} TEI",
                    ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                    str(tei),
                    desc,
                    base_offset + offset, base_offset + offset + 1
                ))
                offset += 2

        # ── 相线评估结果 (3字节) ──
        for i in range(3):
            if offset + 1 <= length:
                phase = data[offset]
                phase_desc = self.PHASE_MAP.get(phase, f"保留(0x{phase:02X})")
                label = "评估出的所属相线" if i == 0 else f"备选相线{i}"
                table.append((
                    f"  相线({label})",
                    f"0x{phase:02X}",
                    str(phase),
                    phase_desc,
                    base_offset + offset, base_offset + offset
                ))
                offset += 1

        # ── 设备类型 (1字节) ──
        if offset + 1 <= length:
            dev_type = data[offset]
            dev_desc = self.DEVICE_TYPE_MAP.get(dev_type, f"保留(0x{dev_type:02X})")
            table.append((
                "  设备类型",
                f"0x{dev_type:02X}",
                str(dev_type),
                dev_desc,
                base_offset + offset, base_offset + offset
            ))
            offset += 1

        # ── 保留 (1字节) ──
        if offset + 1 <= length:
            table.append((
                "  保留",
                f"0x{data[offset]:02X}",
                str(data[offset]),
                "保留",
                base_offset + offset, base_offset + offset
            ))
            offset += 1

        # ── 扩展特性版本号 (1字节) ──
        if offset + 1 <= length:
            ext = data[offset]
            ext_desc = self.EXT_FEATURE_MAP.get(ext, f"保留(0x{ext:02X})")
            table.append((
                "  扩展特性版本号",
                f"0x{ext:02X}",
                str(ext),
                ext_desc,
                base_offset + offset, base_offset + offset
            ))
            offset += 1

        # ── MAC地址类型 (1字节) ──
        if offset + 1 <= length:
            mac_type = data[offset]
            mac_type_desc = self.MAC_ADDR_TYPE_MAP.get(mac_type, f"保留(0x{mac_type:02X})")
            table.append((
                "  MAC地址类型",
                f"0x{mac_type:02X}",
                str(mac_type),
                mac_type_desc,
                base_offset + offset, base_offset + offset
            ))
            offset += 1

        # ── 字节23: 模块类型(2bit)+候选代理链路类型(5bit)+保留(1bit) ──
        if offset + 1 <= length:
            b23 = data[offset]
            module_type = b23 & 0x03           # bit0-1
            link0 = (b23 >> 2) & 0x01          # bit2
            link1 = (b23 >> 3) & 0x01          # bit3
            link2 = (b23 >> 4) & 0x01          # bit4
            link3 = (b23 >> 5) & 0x01          # bit5
            link4 = (b23 >> 6) & 0x01          # bit6
            # bit7 保留
            module_desc = self.MODULE_TYPE_MAP.get(module_type, f"保留(0x{module_type:02X})")
            table.append((
                "  模块类型",
                f"0b{b23 & 0x03:02b}",
                str(module_type),
                module_desc,
                base_offset + offset, base_offset + offset
            ))
            for i, val in enumerate([link0, link1, link2, link3, link4]):
                link_desc = self.LINK_TYPE_MAP.get(val, f"保留(0x{val:02X})")
                table.append((
                    f"  候选代理{i}链路类型",
                    f"0b{val}",
                    str(val),
                    link_desc,
                    base_offset + offset, base_offset + offset
                ))
            offset += 1

        # ── 站点关联随机数 (4字节) ──
        if offset + 4 <= length:
            rand = int.from_bytes(data[offset:offset + 4], 'little')
            table.append((
                "  站点关联随机数",
                ' '.join(f'{b:02X}' for b in data[offset:offset + 4]),
                f"0x{rand:08X}",
                f"模块关联入网的随机数: {rand}",
                base_offset + offset, base_offset + offset + 3
            ))
            offset += 4

        # ── 厂家附加数据 (18字节) ──
        if offset + 18 <= length:
            vendor_data = data[offset:offset + 18]
            table.append((
                "  厂家附加数据",
                ' '.join(f'{b:02X}' for b in vendor_data),
                f"{len(vendor_data)}字节",
                "厂家附加数据",
                base_offset + offset, base_offset + offset + 17
            ))
            offset += 18

        # ── 版本信息 (10字节) ──
        if offset + 10 <= length:
            ver_start = offset
            # 系统启动原因 (1字节)
            boot_reason = data[offset]
            boot_reason_desc = "正常重启" if boot_reason == 0x00 else "保留"
            table.append((
                "  系统启动原因",
                f"0x{boot_reason:02X}",
                str(boot_reason),
                boot_reason_desc,
                base_offset + offset, base_offset + offset
            ))
            offset += 1
            # BOOT版本号 (1字节, BCD)
            if offset < length:
                boot_ver = data[offset]
                table.append((
                    "  BOOT版本号",
                    f"0x{boot_ver:02X}",
                    f"{boot_ver:02X}",
                    "BOOT版本号(BCD)",
                    base_offset + offset, base_offset + offset
                ))
                offset += 1
            # 软件版本号 (2字节, BCD)
            if offset + 2 <= length:
                sw_ver = data[offset:offset + 2]
                table.append((
                    "  软件版本号",
                    ' '.join(f'{b:02X}' for b in sw_ver),
                    f"{sw_ver[1]:02X}{sw_ver[0]:02X}",
                    "软件版本号(BCD)",
                    base_offset + offset, base_offset + offset + 1
                ))
                offset += 2
            # 版本时间 (2字节, BIN)
            if offset + 2 <= length:
                ver_time_raw = data[offset:offset + 2]
                # 7bit年 + 4bit月 + 5bit日
                v0, v1 = ver_time_raw[0], ver_time_raw[1]
                year = v0 & 0x7F
                month = ((v0 >> 7) & 0x01) | ((v1 & 0x07) << 1)
                day = (v1 >> 3) & 0x1F
                table.append((
                    "  版本时间",
                    ' '.join(f'{b:02X}' for b in ver_time_raw),
                    f"20{year:02d}-{month:02d}-{day:02d}",
                    "版本时间(BIN)",
                    base_offset + offset, base_offset + offset + 1
                ))
                offset += 2
            # 厂商代码 (2字节, ASCII)
            if offset + 2 <= length:
                vendor_code = data[offset:offset + 2]
                vendor_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in vendor_code)
                table.append((
                    "  厂商代码",
                    ' '.join(f'{b:02X}' for b in vendor_code),
                    vendor_str[::-1],
                    "厂商代码(ASCII)",
                    base_offset + offset, base_offset + offset + 1
                ))
                offset += 2
            # 芯片代码 (2字节, ASCII)
            if offset + 2 <= length:
                chip_code = data[offset:offset + 2]
                chip_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chip_code)
                table.append((
                    "  芯片代码",
                    ' '.join(f'{b:02X}' for b in chip_code),
                    chip_str[::-1],
                    "芯片代码(ASCII)",
                    base_offset + offset, base_offset + offset + 1
                ))
                offset += 2

        # ── 硬复位累积次数 (2字节, 小端序) ──
        if offset + 2 <= length:
            hard_rst = int.from_bytes(data[offset:offset + 2], 'little')
            table.append((
                "  硬复位累积次数",
                ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                str(hard_rst),
                "硬件复位累计次数",
                base_offset + offset, base_offset + offset + 1
            ))
            offset += 2

        # ── 软复位累积次数 (2字节, 小端序) ──
        if offset + 2 <= length:
            soft_rst = int.from_bytes(data[offset:offset + 2], 'little')
            table.append((
                "  软复位累积次数",
                ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                str(soft_rst),
                "软件复位累计次数",
                base_offset + offset, base_offset + offset + 1
            ))
            offset += 2

        # ── 代理类型 (1字节) ──
        if offset + 1 <= length:
            proxy_type = data[offset]
            proxy_desc = self.PROXY_TYPE_MAP.get(proxy_type, f"保留(0x{proxy_type:02X})")
            table.append((
                "  代理类型",
                f"0x{proxy_type:02X}",
                str(proxy_type),
                proxy_desc,
                base_offset + offset, base_offset + offset
            ))
            offset += 1

        # ── 组网序列号 (1字节) ──
        if offset + 1 <= length:
            table.append((
                "  组网序列号",
                f"0x{data[offset]:02X}",
                str(data[offset]),
                "关联请求报文产生时的组网序列号",
                base_offset + offset, base_offset + offset
            ))
            offset += 1

        # ── 字节62: 保留(1bit)+管理消息版本(4bit)+PLC能力指示(2bit)+通道数(1bit) ──
        if offset + 1 <= length:
            b62 = data[offset]
            # bit0: 保留
            # bit1-4: 管理消息版本 (4bit)
            mm_ver = (b62 >> 1) & 0x0F
            # bit5-6: PLC能力指示 (2bit)
            plc_cap = (b62 >> 5) & 0x03
            # bit7: 通道数 (1bit)
            ch_count = (b62 >> 7) & 0x01
            plc_cap_desc = self.PLC_CAPABILITY_MAP.get(plc_cap, f"保留(0x{plc_cap:02X})")
            ch_count_desc = self.CHANNEL_COUNT_MAP.get(ch_count, f"保留(0x{ch_count:02X})")
            table.append((
                "  管理消息版本",
                f"0x{mm_ver:01X}",
                str(mm_ver),
                f"管理消息版本号: {mm_ver}",
                base_offset + offset, base_offset + offset
            ))
            table.append((
                "  PLC能力指示",
                f"0x{plc_cap:01X}",
                str(plc_cap),
                plc_cap_desc,
                base_offset + offset, base_offset + offset
            ))
            table.append((
                "  通道数",
                f"0x{ch_count:01X}",
                str(ch_count),
                ch_count_desc,
                base_offset + offset, base_offset + offset
            ))
            offset += 1

        # ── 字节63: 支持频段标识(2bit)+保留(6bit) ──
        if offset + 1 <= length:
            b63 = data[offset]
            band_id = b63 & 0x03
            table.append((
                "  支持频段标识",
                f"0x{band_id:01X}",
                str(band_id),
                f"支持频段: {band_id}",
                base_offset + offset, base_offset + offset
            ))
            offset += 1

        # ── 端到端序列号 (4字节, 小端序) ──
        if offset + 4 <= length:
            e2e_seq = int.from_bytes(data[offset:offset + 4], 'little')
            table.append((
                "  端到端序列号",
                ' '.join(f'{b:02X}' for b in data[offset:offset + 4]),
                str(e2e_seq),
                f"端到端序列号: {e2e_seq}",
                base_offset + offset, base_offset + offset + 3
            ))
            offset += 4

        return table

    # ── 管理消息子系统常量映射 ──

    # 关联确认结果（表93）
    ASSOC_RESULT_MAP = {
        0x00: "关联请求成功", 0x01: "该站点不在白名单中", 0x03: "加入的站点个数超过上限",
        0x04: "没有设置白名单列表", 0x05: "代理站点个数超过上限", 0x06: "子站点个数超过上限",
        0x08: "重复的MAC地址", 0x09: "超过拓扑层级", 0x0A: "站点再次关联请求入网成功/曾经入网站点再次入网",
        0x0B: "新的站点试图以自己的子站点为代理来入网", 0x0C: "组网拓扑中存在环路",
        0x0D: "CCO端未知原因出错",
    }

    # 代理类型（表88/105）
    PROXY_TYPE_FULL_MAP = {0x01: "保留", 0x02: "站点自己动态选择的代理(动态代理)"}

    # 代理变更原因（表106）
    PROXY_CHANGE_REASON_MAP = {0x01: "周期代理变更", 0x02: "快速代理变更(周期内快速变更)"}

    # 代理变更结果（表109/112）
    PROXY_CHANGE_RESULT_MAP = {0x00: "变更成功"}

    # 离线原因（表114）
    LEAVE_REASON_MAP = {
        0x00: "CCO判定站点未入网但接收到除关联请求之外的报文",
        0x02: "CCO判断网络拓扑的层级超过上限", 0x04: "CCO通知站点立即离线",
        0x05: "第三方设备认证失败(60分钟内不应再请求)", 0x06: "第三方设备认证超时",
    }

    # 延迟离线原因（表116）
    DELAY_LEAVE_REASON_MAP = {0x03: "CCO判断站点不在最新的白名单中"}

    # 过零NTB采集站点类型（表131）
    ZC_COLLECT_TYPE_MAP = {0: "单站点", 1: "全网站点"}

    # 过零NTB采集周期（表132）
    ZC_PERIOD_MAP = {0: "半个电力线周期", 1: "一个电力线周期"}

    # 芯片厂商ID（表136）
    CHIP_VENDOR_MAP = {0x0001: "HS", 0x0002: "ES", 0x0003: "TC", 0x0004: "LH", 0x0005: "HT", 0x0006: "RS", 0x0007: "SW", 0x0008: "SC"}

    # ── 通用解析辅助方法 ──

    @staticmethod
    def _tei_bytes(data: bytes, offset: int) -> Tuple[int, str]:
        """解析12位TEI（2字节小端序低12位）"""
        if offset + 2 > len(data):
            return 0, "N/A"
        val = int.from_bytes(data[offset:offset + 2], 'little') & 0x0FFF
        return val, f"{val}"

    @staticmethod
    def _read_u16_le(data: bytes, offset: int) -> int:
        if offset + 2 > len(data):
            return 0
        return int.from_bytes(data[offset:offset + 2], 'little')

    @staticmethod
    def _read_u32_le(data: bytes, offset: int) -> int:
        if offset + 4 > len(data):
            return 0
        return int.from_bytes(data[offset:offset + 4], 'little')

    def _append_field(self, table: list, name: str, raw: str, parsed: str, desc: str,
                       start: int, end: int) -> None:
        table.append((f"  {name}", raw, parsed, desc, start, end))

    # ── 管理消息子类型解析器 ──

    def _parse_assoc_cnf(self, data: bytes, base_offset: int = 0) -> list:
        """解析关联确认报文 MMeAssocCnf（文档表92）"""
        table = []
        offset = 0
        length = len(data)

        if offset + 6 <= length:
            mac_raw, mac_colon = self._mac_addr(data, offset)
            self._append_field(table, "站点MAC地址", mac_raw, mac_colon, "关联确认目标终端设备地址",
                               base_offset + offset, base_offset + offset + 5)
            offset += 6

        if offset < length:
            res = data[offset]
            self._append_field(table, "结果", f"{res:02X}", str(res),
                               self.ASSOC_RESULT_MAP.get(res, f"保留(0x{res:02X})"),
                               base_offset + offset, base_offset + offset)
            offset += 1

        if offset < length:
            self._append_field(table, "站点层级", f"{data[offset]:02X}", str(data[offset]),
                               f"新入网站点所属网络层级: {data[offset]}", base_offset + offset, base_offset + offset)
            offset += 1

        if offset + 2 <= length:
            tei = self._read_u16_le(data, offset)
            self._append_field(table, "站点TEI", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(tei), f"CCO分配的TEI: {tei}", base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset + 2 <= length:
            ptei = self._read_u16_le(data, offset)
            self._append_field(table, "代理TEI", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(ptei), f"选定代理站点TEI: {ptei}", base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset < length:
            self._append_field(table, "总分包数", f"{data[offset]:02X}", str(data[offset]),
                               f"分包总个数: {data[offset]}", base_offset + offset, base_offset + offset)
            offset += 1
        if offset < length:
            self._append_field(table, "分包序号", f"{data[offset]:02X}", str(data[offset]),
                               f"分包索引: {data[offset]}", base_offset + offset, base_offset + offset)
            offset += 1
        if offset < length:
            last = data[offset]
            self._append_field(table, "最后一个分包标识", f"{last:02X}", str(last),
                               "是最后一个分包" if last == 1 else "不是最后一个分包",
                               base_offset + offset, base_offset + offset)
            offset += 1

        if offset < length:
            b = data[offset]
            link_type = b & 0x01
            band = (b >> 1) & 0x07
            self._append_field(table, "链路类型/载波频段", f"{b:02X}",
                               f"链路:{self.LINK_TYPE_MAP.get(link_type,'?')} 频段:{band}",
                               f"链路类型:{link_type} 载波频段:{band}",
                               base_offset + offset, base_offset + offset)
            offset += 1

        if offset + 4 <= length:
            rand = self._read_u32_le(data, offset)
            self._append_field(table, "站点关联随机数", ' '.join(f'{b:02X}' for b in data[offset:offset + 4]),
                               f"0x{rand:08X}", f"站点关联请求随机数: {rand}",
                               base_offset + offset, base_offset + offset + 3)
            offset += 4

        if offset + 4 <= length:
            rtime = self._read_u32_le(data, offset)
            self._append_field(table, "重新关联时间", ' '.join(f'{b:02X}' for b in data[offset:offset + 4]),
                               f"{rtime}ms", f"重新发起关联请求间隔: {rtime}ms",
                               base_offset + offset, base_offset + offset + 3)
            offset += 4

        if offset + 4 <= length:
            esn = self._read_u32_le(data, offset)
            self._append_field(table, "端到端序列号", ' '.join(f'{b:02X}' for b in data[offset:offset + 4]),
                               f"0x{esn:08X}", f"端到端管理报文序列号: {esn}",
                               base_offset + offset, base_offset + offset + 3)
            offset += 4

        if offset + 4 <= length:
            pn = self._read_u32_le(data, offset)
            self._append_field(table, "路径序号", ' '.join(f'{b:02X}' for b in data[offset:offset + 4]),
                               f"{pn}", f"路径通知序列号: {pn}", base_offset + offset, base_offset + offset + 3)
            offset += 4

        if offset < length:
            self._append_field(table, "组网序列号", f"{data[offset]:02X}", str(data[offset]),
                               f"组网序列号: {data[offset]}", base_offset + offset, base_offset + offset)
            offset += 1

        if offset < length:
            b = data[offset]
            mm_ver = b & 0x0F
            probe = (b >> 4) & 0x01
            self._append_field(table, "管理消息版本/探测频段", f"{b:02X}",
                               f"版本:{mm_ver} 探测:{probe}",
                               f"管理消息版本:{mm_ver} 探测频段标识:{'探测频段' if probe else '工作频段'}",
                               base_offset + offset, base_offset + offset)
            offset += 1

        # 保留2字节
        if offset + 2 <= length:
            self._append_field(table, "保留", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               "2字节", "保留", base_offset + offset, base_offset + offset + 1)
            offset += 2

        # 路由表信息（可变长）
        remaining = data[offset:]
        if remaining:
            route_table = self._parse_route_info(remaining, base_offset + offset)
            table.extend(route_table)

        return table

    def _parse_change_proxy_req(self, data: bytes, base_offset: int = 0) -> list:
        """解析代理变更请求报文 MMeChangeProxyReq（文档表104）"""
        table = []
        offset = 0
        length = len(data)

        if offset + 2 <= length:
            tei = self._read_u16_le(data, offset)
            self._append_field(table, "站点TEI", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(tei), f"申请代理变更站点TEI: {tei}", base_offset + offset, base_offset + offset + 1)
            offset += 2

        for i in range(5):
            if offset + 2 <= length:
                tei = self._read_u16_le(data, offset)
                self._append_field(table, f"新代理TEI{i}", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                                   str(tei), f"候选代理站点TEI: {tei}" if tei else "未指定",
                                   base_offset + offset, base_offset + offset + 1)
                offset += 2

        if offset + 2 <= length:
            otei = self._read_u16_le(data, offset)
            self._append_field(table, "旧代理TEI", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(otei), f"原代理站点TEI: {otei}", base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset < length:
            ptype = data[offset]
            self._append_field(table, "代理类型", f"{ptype:02X}", str(ptype),
                               self.PROXY_TYPE_FULL_MAP.get(ptype, f"保留(0x{ptype:02X})"),
                               base_offset + offset, base_offset + offset)
            offset += 1

        if offset < length:
            reason = data[offset]
            self._append_field(table, "原因", f"{reason:02X}", str(reason),
                               self.PROXY_CHANGE_REASON_MAP.get(reason, f"保留(0x{reason:02X})"),
                               base_offset + offset, base_offset + offset)
            offset += 1

        for i in range(3):
            if offset < length:
                self._append_field(table, f"站点相线(备选{i})", f"{data[offset]:02X}", str(data[offset]),
                                   self.PHASE_MAP.get(data[offset], f"保留({data[offset]})"),
                                   base_offset + offset, base_offset + offset)
                offset += 1

        if offset < length:
            b = data[offset]
            links = [(b >> i) & 0x01 for i in range(5)]
            for i in range(5):
                self._append_field(table, f"新代理{i}链路类型", f"0b{links[i]}",
                                   self.LINK_TYPE_MAP.get(links[i], "?"),
                                   f"{'高速载波' if links[i]==0 else '无线'}链路",
                                   base_offset + offset, base_offset + offset)
            offset += 1

        if offset + 4 <= length:
            esn = self._read_u32_le(data, offset)
            self._append_field(table, "端到端序列号", ' '.join(f'{b:02X}' for b in data[offset:offset + 4]),
                               f"0x{esn:08X}", f"端到端报文序列号: {esn}",
                               base_offset + offset, base_offset + offset + 3)
            offset += 4

        if offset < length:
            self._append_field(table, "组网序列号", f"{data[offset]:02X}", str(data[offset]),
                               f"组网序列号: {data[offset]}", base_offset + offset, base_offset + offset)
            offset += 1

        remaining = data[offset:]
        if remaining:
            self._append_field(table, "保留", ' '.join(f'{b:02X}' for b in remaining[:16]),
                               f"{len(remaining)}字节", "保留", base_offset + offset, base_offset + len(remaining) - 1)

        return table

    def _parse_assoc_ind(self, data: bytes, base_offset: int = 0) -> list:
        """解析关联指示报文 MMeAssocInd（文档表99）"""
        table = []
        offset = 0
        length = len(data)

        if offset < length:
            res = data[offset]
            self._append_field(table, "结果", f"{res:02X}", str(res),
                               self.ASSOC_RESULT_MAP.get(res, f"保留(0x{res:02X})"),
                               base_offset + offset, base_offset + offset)
            offset += 1

        if offset < length:
            self._append_field(table, "站点层级", f"{data[offset]:02X}", str(data[offset]),
                               f"新入网站点所属网络层级: {data[offset]}", base_offset + offset, base_offset + offset)
            offset += 1

        if offset + 6 <= length:
            mac_raw, mac_colon = self._mac_addr(data, offset)
            self._append_field(table, "站点MAC地址", mac_raw, mac_colon, "新入网站点MAC地址",
                               base_offset + offset, base_offset + offset + 5)
            offset += 6

        if offset + 6 <= length:
            mac_raw, mac_colon = self._mac_addr(data, offset)
            self._append_field(table, "CCO MAC地址", mac_raw, mac_colon, "本网络CCO MAC地址",
                               base_offset + offset, base_offset + offset + 5)
            offset += 6

        if offset + 2 <= length:
            tei = self._read_u16_le(data, offset)
            self._append_field(table, "站点TEI", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(tei), f"CCO分配的TEI: {tei}", base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset + 2 <= length:
            ptei = self._read_u16_le(data, offset)
            self._append_field(table, "代理TEI", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(ptei), f"代理站点TEI: {ptei}", base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset < length:
            b = data[offset]
            lt = b & 0x01
            band = (b >> 1) & 0x07
            self._append_field(table, "链路类型/载波频段", f"{b:02X}",
                               f"链路:{self.LINK_TYPE_MAP.get(lt,'?')} 频段:{band}",
                               f"链路类型:{lt} 载波频段:{band}", base_offset + offset, base_offset + offset)
            offset += 1

        # 保留2字节
        if offset + 2 <= length:
            self._append_field(table, "保留", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               "2字节", "保留", base_offset + offset, base_offset + offset + 1)
            offset += 2

        for name in ["分包序号", "总分包数", "最后一个分包标识"]:
            if offset < length:
                self._append_field(table, name, f"{data[offset]:02X}", str(data[offset]),
                                   f"{name}: {data[offset]}", base_offset + offset, base_offset + offset)
                offset += 1

        if offset + 4 <= length:
            rand = self._read_u32_le(data, offset)
            self._append_field(table, "站点关联随机数", ' '.join(f'{b:02X}' for b in data[offset:offset + 4]),
                               f"0x{rand:08X}", f"站点关联请求随机数: {rand}",
                               base_offset + offset, base_offset + offset + 3)
            offset += 4

        # 保留17字节
        if offset + 17 <= length:
            self._append_field(table, "保留", ' '.join(f'{b:02X}' for b in data[offset:offset + 17]),
                               "17字节", "保留", base_offset + offset, base_offset + offset + 16)
            offset += 17

        if offset < length:
            self._append_field(table, "组网序列号", f"{data[offset]:02X}", str(data[offset]),
                               f"组网序列号: {data[offset]}", base_offset + offset, base_offset + offset)
            offset += 1

        if offset + 2 <= length:
            self._append_field(table, "保留", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               "2字节", "保留", base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset + 4 <= length:
            rtime = self._read_u32_le(data, offset)
            self._append_field(table, "重新关联时间", ' '.join(f'{b:02X}' for b in data[offset:offset + 4]),
                               f"{rtime}ms", f"重新发起关联间隔: {rtime}ms",
                               base_offset + offset, base_offset + offset + 3)
            offset += 4

        if offset + 4 <= length:
            esn = self._read_u32_le(data, offset)
            self._append_field(table, "端到端序列号", ' '.join(f'{b:02X}' for b in data[offset:offset + 4]),
                               f"0x{esn:08X}", f"端到端管理报文序列号: {esn}",
                               base_offset + offset, base_offset + offset + 3)
            offset += 4

        # 保留8字节
        if offset + 8 <= length:
            self._append_field(table, "保留", ' '.join(f'{b:02X}' for b in data[offset:offset + 8]),
                               "8字节", "保留", base_offset + offset, base_offset + offset + 7)
            offset += 8

        # 路由表信息
        remaining = data[offset:]
        if remaining:
            route_table = self._parse_route_info(remaining, base_offset + offset)
            table.extend(route_table)

        return table

    def _parse_change_proxy_cnf(self, data: bytes, base_offset: int = 0) -> list:
        """解析代理变更确认报文 MMeChangeProxyCnf（文档表108）"""
        table = []
        offset = 0
        length = len(data)

        if offset + 4 <= length:
            res = self._read_u32_le(data, offset)
            self._append_field(table, "结果", ' '.join(f'{b:02X}' for b in data[offset:offset + 4]),
                               f"0x{res:08X}", self.PROXY_CHANGE_RESULT_MAP.get(res, f"保留(0x{res:X})"),
                               base_offset + offset, base_offset + offset + 3)
            offset += 4

        for name in ["总分包数", "分包序号"]:
            if offset < length:
                self._append_field(table, name, f"{data[offset]:02X}", str(data[offset]),
                                   f"{name}: {data[offset]}", base_offset + offset, base_offset + offset)
                offset += 1

        if offset + 2 <= length:
            tei = self._read_u16_le(data, offset)
            self._append_field(table, "站点TEI", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(tei), f"申请代理变更站点TEI: {tei}", base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset + 2 <= length:
            ptei = self._read_u16_le(data, offset)
            self._append_field(table, "代理TEI", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(ptei), f"新代理站点TEI: {ptei}", base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset + 2 <= length:
            cnt = self._read_u16_le(data, offset)
            self._append_field(table, "子站点数", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(cnt), f"子站点数目: {cnt}", base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset < length:
            self._append_field(table, "保留", f"{data[offset]:02X}", "1字节", "保留",
                               base_offset + offset, base_offset + offset)
            offset += 1

        if offset < length:
            self._append_field(table, "组网序列号", f"{data[offset]:02X}", str(data[offset]),
                               f"组网序列号: {data[offset]}", base_offset + offset, base_offset + offset)
            offset += 1

        if offset < length:
            b = data[offset]
            lt = b & 0x01
            self._append_field(table, "链路类型", f"{b:02X}", self.LINK_TYPE_MAP.get(lt, "?"),
                               f"{'高速载波' if lt==0 else '无线'}链路", base_offset + offset, base_offset + offset)
            offset += 1

        if offset < length:
            self._append_field(table, "保留", f"{data[offset]:02X}", "1字节", "保留",
                               base_offset + offset, base_offset + offset)
            offset += 1

        if offset + 4 <= length:
            esn = self._read_u32_le(data, offset)
            self._append_field(table, "端到端序列号", ' '.join(f'{b:02X}' for b in data[offset:offset + 4]),
                               f"0x{esn:08X}", f"端到端报文序列号: {esn}",
                               base_offset + offset, base_offset + offset + 3)
            offset += 4

        if offset + 4 <= length:
            pn = self._read_u32_le(data, offset)
            self._append_field(table, "路径序号", ' '.join(f'{b:02X}' for b in data[offset:offset + 4]),
                               f"{pn}", f"路径通知序列号: {pn}", base_offset + offset, base_offset + offset + 3)
            offset += 4

        # 保留8字节
        if offset + 8 <= length:
            self._append_field(table, "保留", ' '.join(f'{b:02X}' for b in data[offset:offset + 8]),
                               "8字节", "保留", base_offset + offset, base_offset + offset + 7)
            offset += 8

        # 子站点条目
        remaining = data[offset:]
        if remaining:
            child_cnt = len(remaining) // 2
            self._append_field(table, "子站点条目", ' '.join(f'{b:02X}' for b in remaining[:20]),
                               f"{child_cnt}个站点", "子站点TEI列表(每2字节一个TEI)",
                               base_offset + offset, base_offset + len(remaining) - 1)
            for i in range(0, min(len(remaining) - 1, 60), 2):
                tei = self._read_u16_le(remaining, i)
                self._append_field(table, f"  子站点[{i // 2}] TEI",
                                   ' '.join(f'{b:02X}' for b in remaining[i:i + 2]),
                                   str(tei), f"子站点TEI: {tei}",
                                   base_offset + offset + i, base_offset + offset + i + 1)

        return table

    def _parse_assoc_gather_ind(self, data: bytes, base_offset: int = 0) -> list:
        """解析关联汇总指示报文 MMeAssocGatherInd（文档表102）"""
        table = []
        offset = 0
        length = len(data)

        if offset < length:
            self._append_field(table, "结果", f"{data[offset]:02X}", str(data[offset]),
                               "允许加入网络" if data[offset] == 0 else f"值:{data[offset]}",
                               base_offset + offset, base_offset + offset)
            offset += 1

        if offset < length:
            self._append_field(table, "站点层级", f"{data[offset]:02X}", str(data[offset]),
                               f"新入网站点网络层级: {data[offset]}", base_offset + offset, base_offset + offset)
            offset += 1

        if offset + 6 <= length:
            mac_raw, mac_colon = self._mac_addr(data, offset)
            self._append_field(table, "CCO MAC地址", mac_raw, mac_colon, "本网络CCO MAC地址",
                               base_offset + offset, base_offset + offset + 5)
            offset += 6

        if offset + 2 <= length:
            ptei = self._read_u16_le(data, offset)
            self._append_field(table, "代理TEI", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(ptei), f"代理站点TEI: {ptei}", base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset < length:
            self._append_field(table, "组网序列号", f"{data[offset]:02X}", str(data[offset]),
                               f"组网序列号: {data[offset]}", base_offset + offset, base_offset + offset)
            offset += 1

        if offset < length:
            cnt = data[offset]
            self._append_field(table, "汇总站点数", f"{cnt:02X}", str(cnt),
                               f"新入网站点个数: {cnt}", base_offset + offset, base_offset + offset)
            offset += 1

        if offset < length:
            b = data[offset]
            band = b & 0x07
            self._append_field(table, "载波频段/保留", f"{b:02X}", f"频段:{band}",
                               f"载波频段:{band}", base_offset + offset, base_offset + offset)
            offset += 1

        # 保留15字节
        if offset + 15 <= length:
            self._append_field(table, "保留", ' '.join(f'{b:02X}' for b in data[offset:offset + 15]),
                               "15字节", "保留", base_offset + offset, base_offset + offset + 14)
            offset += 15

        # 站点信息（每站点8字节: MAC 6B + TEI 2B）
        remaining = data[offset:]
        if remaining:
            site_cnt = len(remaining) // 8
            self._append_field(table, "站点信息", ' '.join(f'{b:02X}' for b in remaining[:20]),
                               f"{site_cnt}个站点", f"每站点8字节(MAC 6B + TEI 2B)",
                               base_offset + offset, base_offset + len(remaining) - 1)
            for i in range(0, min(len(remaining) - 1, 80), 8):
                if i + 8 <= len(remaining):
                    mac_raw, mac_colon = self._mac_addr(remaining, i)
                    tei = self._read_u16_le(remaining, i + 6)
                    self._append_field(table, f"  站点[{i // 8}] MAC+TEI",
                                       ' '.join(f'{b:02X}' for b in remaining[i:i + 8]),
                                       f"{mac_colon} TEI:{tei}", f"站点MAC:{mac_colon} TEI:{tei}",
                                       base_offset + offset + i, base_offset + offset + i + 7)

        return table

    def _parse_change_proxy_bitmap_cnf(self, data: bytes, base_offset: int = 0) -> list:
        """解析代理变更确认报文(位图版) MMeChangeProxyBitMapCnf（文档表111）"""
        table = []
        offset = 0
        length = len(data)

        if offset + 4 <= length:
            res = self._read_u32_le(data, offset)
            self._append_field(table, "结果", ' '.join(f'{b:02X}' for b in data[offset:offset + 4]),
                               f"0x{res:08X}", self.PROXY_CHANGE_RESULT_MAP.get(res, f"保留(0x{res:X})"),
                               base_offset + offset, base_offset + offset + 3)
            offset += 4

        if offset + 2 <= length:
            tei = self._read_u16_le(data, offset)
            self._append_field(table, "站点TEI", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(tei), f"申请代理变更站点TEI: {tei}", base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset + 2 <= length:
            ptei = self._read_u16_le(data, offset)
            self._append_field(table, "代理TEI", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(ptei), f"新代理站点TEI: {ptei}", base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset < length:
            self._append_field(table, "组网序列号", f"{data[offset]:02X}", str(data[offset]),
                               f"组网序列号: {data[offset]}", base_offset + offset, base_offset + offset)
            offset += 1

        # 子站点位图（130字节）
        if offset + 130 <= length:
            bitmap = data[offset:offset + 130]
            # 统计置位的TEI数
            set_bits = sum(1 for byte in bitmap for bit in range(8) if (byte >> bit) & 1)
            self._append_field(table, "子站点位图", ' '.join(f'{b:02X}' for b in bitmap[:16]) + "...",
                               f"130字节({set_bits}个TEI置位)", "子站点TEI位图(比特位=1表示对应TEI有效)",
                               base_offset + offset, base_offset + offset + 129)
            offset += 130

        if offset < length:
            b = data[offset]
            lt = b & 0x01
            self._append_field(table, "链路类型", f"{b:02X}", self.LINK_TYPE_MAP.get(lt, "?"),
                               f"{'高速载波' if lt==0 else '无线'}链路", base_offset + offset, base_offset + offset)
            offset += 1

        if offset + 4 <= length:
            esn = self._read_u32_le(data, offset)
            self._append_field(table, "端到端序列号", ' '.join(f'{b:02X}' for b in data[offset:offset + 4]),
                               f"0x{esn:08X}", f"端到端报文序列号: {esn}",
                               base_offset + offset, base_offset + offset + 3)
            offset += 4

        if offset + 4 <= length:
            pn = self._read_u32_le(data, offset)
            self._append_field(table, "路径序号", ' '.join(f'{b:02X}' for b in data[offset:offset + 4]),
                               f"{pn}", f"路径通知序列号: {pn}", base_offset + offset, base_offset + offset + 3)
            offset += 4

        return table

    def _parse_leave_ind(self, data: bytes, base_offset: int = 0) -> list:
        """解析离线指示报文 MMeLeaveInd（文档表113）"""
        table = []
        offset = 0
        length = len(data)

        if offset + 2 <= length:
            tei = self._read_u16_le(data, offset)
            self._append_field(table, "站点TEI", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(tei), f"离线站点TEI: {tei}", base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset + 2 <= length:
            reason = self._read_u16_le(data, offset)
            self._append_field(table, "原因", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               f"0x{reason:04X}", self.LEAVE_REASON_MAP.get(reason, f"保留(0x{reason:04X})"),
                               base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset + 6 <= length:
            mac_raw, mac_colon = self._mac_addr(data, offset)
            self._append_field(table, "站点MAC地址", mac_raw, mac_colon, "离线站点MAC地址",
                               base_offset + offset, base_offset + offset + 5)
            offset += 6

        if offset + 2 <= length:
            ptei = self._read_u16_le(data, offset)
            self._append_field(table, "代理TEI", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(ptei), f"代理站点TEI: {ptei}", base_offset + offset, base_offset + offset + 1)
            offset += 2

        remaining = data[offset:]
        if remaining:
            self._append_field(table, "保留", ' '.join(f'{b:02X}' for b in remaining[:8]),
                               f"{len(remaining)}字节", "保留", base_offset + offset, base_offset + len(remaining) - 1)

        return table

    def _parse_heartbeat_check(self, data: bytes, base_offset: int = 0) -> list:
        """解析心跳检测报文 MMeHeartBeatCheck（文档表118）"""
        table = []
        offset = 0
        length = len(data)

        if offset + 2 <= length:
            tei = self._read_u16_le(data, offset)
            self._append_field(table, "原始源TEI", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(tei), f"初始产生心跳报文的站点TEI: {tei}",
                               base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset + 2 <= length:
            mtei = self._read_u16_le(data, offset)
            self._append_field(table, "发现站点数最大的站点TEI",
                               ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(mtei), f"发现站点最多的站点TEI: {mtei}",
                               base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset + 4 <= length:
            mcnt = self._read_u32_le(data, offset)
            self._append_field(table, "最大的发现站点数", ' '.join(f'{b:02X}' for b in data[offset:offset + 4]),
                               str(mcnt), f"最大发现站点数量: {mcnt}",
                               base_offset + offset, base_offset + offset + 3)
            offset += 4

        if offset + 130 <= length:
            bitmap = data[offset:offset + 130]
            set_bits = sum(1 for byte in bitmap for bit in range(8) if (byte >> bit) & 1)
            self._append_field(table, "可发现站点TEI(位图)", ' '.join(f'{b:02X}' for b in bitmap[:16]) + "...",
                               f"130字节({set_bits}个TEI)", "可发现站点TEI位图",
                               base_offset + offset, base_offset + offset + 129)
            offset += 130

        remaining = data[offset:]
        if remaining:
            self._append_field(table, "保留", ' '.join(f'{b:02X}' for b in remaining[:4]),
                               f"{len(remaining)}字节", "保留", base_offset + offset, base_offset + len(remaining) - 1)

        return table

    def _parse_discover_node_list(self, data: bytes, base_offset: int = 0) -> list:
        """解析发现列表报文 MMeDiscoverNodeList（文档表119）"""
        table = []
        offset = 0
        length = len(data)

        if offset + 2 <= length:
            tei = self._read_u16_le(data, offset)
            self._append_field(table, "TEI", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(tei), f"发送站点TEI: {tei}", base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset < length:
            self._append_field(table, "角色", f"{data[offset]:02X}", str(data[offset]),
                               f"站点角色: {data[offset]}", base_offset + offset, base_offset + offset)
            offset += 1

        if offset < length:
            self._append_field(table, "层级", f"{data[offset]:02X}", str(data[offset]),
                               f"网络层级: {data[offset]}", base_offset + offset, base_offset + offset)
            offset += 1

        if offset + 6 <= length:
            mac_raw, mac_colon = self._mac_addr(data, offset)
            self._append_field(table, "MAC地址", mac_raw, mac_colon, "发送站点MAC地址",
                               base_offset + offset, base_offset + offset + 5)
            offset += 6

        if offset + 2 <= length:
            ptei = self._read_u16_le(data, offset)
            self._append_field(table, "代理TEI", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(ptei), f"代理站点TEI: {ptei}", base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset + 4 <= length:
            b12 = data[offset]
            plc_cap = b12 & 0x03
            ch_cnt = (b12 >> 2) & 0x01
            self._append_field(table, "PLC能力/通道数", f"{b12:02X}",
                               f"PLC:{self.PLC_CAPABILITY_MAP.get(plc_cap,'?')} 通道:{self.CHANNEL_COUNT_MAP.get(ch_cnt,'?')}",
                               f"PLC:{plc_cap} 通道:{ch_cnt}",
                               base_offset + offset, base_offset + offset)
            self._append_field(table, "保留", ' '.join(f'{b:02X}' for b in data[offset + 1:offset + 4]),
                               "3字节", "保留(含通信成功率完成标志)",
                               base_offset + offset + 1, base_offset + offset + 3)
            offset += 4

        for name, size in [("与代理站点通信成功率", 4), ("与代理站点下行通信成功率", 4),
                           ("站点总数", 2), ("发送发现列表报文个数", 2),
                           ("上行路由条目总数", 2)]:
            if offset + size <= length:
                val = self._read_u32_le(data, offset) if size == 4 else self._read_u16_le(data, offset)
                self._append_field(table, name, ' '.join(f'{b:02X}' for b in data[offset:offset + size]),
                                   str(val), f"{name}: {val}", base_offset + offset, base_offset + offset + size - 1)
                offset += size

        # 接收发现列表信息条目长度 + 保留
        if offset + 3 <= length:
            self._append_field(table, "接收发现列表条目长度/保留",
                               ' '.join(f'{b:02X}' for b in data[offset:offset + 3]),
                               f"条目长度:{data[offset]}", "接收发现列表信息",
                               base_offset + offset, base_offset + offset + 2)
            offset += 3

        if offset + 2 <= length:
            val = self._read_u16_le(data, offset)
            self._append_field(table, "路由周期到期剩余时间", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               f"{val}s", f"路由周期到期剩余: {val}秒",
                               base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset < length:
            self._append_field(table, "相线", f"{data[offset]:02X}", str(data[offset]),
                               f"站点相线评估: {data[offset]}", base_offset + offset, base_offset + offset)
            offset += 1

        if offset < length:
            self._append_field(table, "最小通信成功率", f"{data[offset]:02X}", f"{data[offset]}%",
                               f"到CCO路径最小通信成功率: {data[offset]}%",
                               base_offset + offset, base_offset + offset)
            offset += 1

        # RU_SNR评估信息 4字节（表123）
        if offset + 4 <= length:
            self._append_field(table, "与代理的RU_SNR评估信息",
                               ' '.join(f'{b:02X}' for b in data[offset:offset + 4]),
                               "4字节", "RU SNR评估信息(表123)",
                               base_offset + offset, base_offset + offset + 3)
            offset += 4

        if offset < length:
            self._append_field(table, "保留", f"{data[offset]:02X}", "1字节", "保留",
                               base_offset + offset, base_offset + offset)
            offset += 1

        # 上行路由条目信息（可变长）
        remaining = data[offset:]
        if remaining:
            self._append_field(table, "上行路由/发现列表/位图数据",
                               ' '.join(f'{b:02X}' for b in remaining[:30]) + ("..." if len(remaining) > 30 else ""),
                               f"{len(remaining)}字节", "上行路由条目+发现站点列表位图+接收发现列表信息",
                               base_offset + offset, base_offset + len(remaining) - 1)

        return table

    def _parse_delay_leave_ind(self, data: bytes, base_offset: int = 0) -> list:
        """解析延迟离线指示报文 MMeDelayLeaveInd（文档表115）"""
        table = []
        offset = 0
        length = len(data)

        if offset + 2 <= length:
            reason = self._read_u16_le(data, offset)
            self._append_field(table, "原因", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               f"0x{reason:04X}", self.DELAY_LEAVE_REASON_MAP.get(reason, f"保留(0x{reason:04X})"),
                               base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset + 2 <= length:
            cnt = self._read_u16_le(data, offset)
            self._append_field(table, "站点总数", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(cnt), f"需要离线站点个数: {cnt}", base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset + 2 <= length:
            delay = self._read_u16_le(data, offset)
            self._append_field(table, "延迟时间", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               f"{delay}s", f"延迟离线时间: {delay}秒", base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset + 10 <= length:
            self._append_field(table, "保留", ' '.join(f'{b:02X}' for b in data[offset:offset + 10]),
                               "10字节", "保留", base_offset + offset, base_offset + offset + 9)
            offset += 10

        # 站点MAC地址列表（每6字节一个MAC）
        remaining = data[offset:]
        if remaining:
            mac_cnt = len(remaining) // 6
            self._append_field(table, "站点MAC地址列表", ' '.join(f'{b:02X}' for b in remaining[:18]),
                               f"{mac_cnt}个MAC", f"离线站点MAC地址列表({mac_cnt}个)",
                               base_offset + offset, base_offset + len(remaining) - 1)
            for i in range(0, min(len(remaining), 30), 6):
                if i + 6 <= len(remaining):
                    mac_raw, mac_colon = self._mac_addr(remaining, i)
                    self._append_field(table, f"  MAC[{i // 6}]", mac_raw, mac_colon,
                                       f"离线站点MAC: {mac_colon}",
                                       base_offset + offset + i, base_offset + offset + i + 5)

        return table

    def _parse_success_rate_report(self, data: bytes, base_offset: int = 0) -> list:
        """解析通信成功率上报报文 MMeSuccessRateReport（文档表127）"""
        table = []
        offset = 0
        length = len(data)

        if offset + 2 <= length:
            tei = self._read_u16_le(data, offset)
            self._append_field(table, "TEI", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(tei), f"代理站点TEI: {tei}", base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset + 2 <= length:
            cnt = self._read_u16_le(data, offset)
            self._append_field(table, "站点总数", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(cnt), f"子站点个数: {cnt}", base_offset + offset, base_offset + offset + 1)
            offset += 2

        # 通信成功率信息（每站点4字节: TEI 2B + 下行1B + 上行1B）
        remaining = data[offset:]
        if remaining:
            sta_cnt = len(remaining) // 4
            self._append_field(table, "通信成功率信息", ' '.join(f'{b:02X}' for b in remaining[:20]),
                               f"{sta_cnt}个站点", f"每站点4字节(TEI 2B + 下行1B + 上行1B)",
                               base_offset + offset, base_offset + len(remaining) - 1)
            for i in range(0, min(len(remaining), 40), 4):
                if i + 4 <= len(remaining):
                    tei = self._read_u16_le(remaining, i)
                    down = remaining[i + 2]
                    up = remaining[i + 3]
                    self._append_field(table, f"  站点[{i // 4}] TEI:{tei}",
                                       ' '.join(f'{b:02X}' for b in remaining[i:i + 4]),
                                       f"下行:{down}% 上行:{up}%",
                                       f"TEI={tei} 下行成功率:{down}% 上行成功率:{up}%",
                                       base_offset + offset + i, base_offset + offset + i + 3)

        return table

    def _parse_network_conflict_report(self, data: bytes, base_offset: int = 0) -> list:
        """解析网络冲突上报报文 MMeNetworkConflictReport（文档表129）"""
        table = []
        offset = 0
        length = len(data)

        if offset + 6 <= length:
            mac_raw, mac_colon = self._mac_addr(data, offset)
            self._append_field(table, "冲突网络CCO MAC地址", mac_raw, mac_colon,
                               "邻居网络CCO MAC地址", base_offset + offset, base_offset + offset + 5)
            offset += 6

        if offset < length:
            self._append_field(table, "邻居网络个数", f"{data[offset]:02X}", str(data[offset]),
                               f"周边可见邻居网络个数: {data[offset]}", base_offset + offset, base_offset + offset)
            offset += 1

        if offset + 2 <= length:
            snid_bitmap = self._read_u16_le(data, offset)
            self._append_field(table, "邻居网络SNID位图", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               f"0x{snid_bitmap:04X}", f"邻居SNID占用位图: 0x{snid_bitmap:04X}",
                               base_offset + offset, base_offset + offset + 1)

        return table

    def _parse_zero_cross_ntb_collect_ind(self, data: bytes, base_offset: int = 0) -> list:
        """解析过零NTB采集指示报文 MMeZeroCrossNTBCollectInd（文档表130）"""
        table = []
        offset = 0
        length = len(data)

        if offset + 2 <= length:
            tei = self._read_u16_le(data, offset)
            self._append_field(table, "站点TEI", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(tei), f"采集站点TEI: {tei}" + ("(全网站点)" if tei == 0xFFFF else ""),
                               base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset < length:
            self._append_field(table, "站点类型", f"{data[offset]:02X}", str(data[offset]),
                               self.ZC_COLLECT_TYPE_MAP.get(data[offset], f"保留({data[offset]})"),
                               base_offset + offset, base_offset + offset)
            offset += 1

        if offset < length:
            self._append_field(table, "采集周期", f"{data[offset]:02X}", str(data[offset]),
                               self.ZC_PERIOD_MAP.get(data[offset], f"保留({data[offset]})"),
                               base_offset + offset, base_offset + offset)
            offset += 1

        if offset < length:
            self._append_field(table, "采集数量", f"{data[offset]:02X}", str(data[offset]),
                               f"采集过零NTB值数量: {data[offset]}", base_offset + offset, base_offset + offset)

        return table

    def _parse_zero_cross_ntb_report(self, data: bytes, base_offset: int = 0) -> list:
        """解析过零NTB上报报文 MMeZeroCrossNTBReport（文档表133）"""
        table = []
        offset = 0
        length = len(data)

        if offset + 2 <= length:
            tei = self._read_u16_le(data, offset)
            self._append_field(table, "站点TEI", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(tei), f"上报站点TEI: {tei}", base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset < length:
            self._append_field(table, "上报数量", f"{data[offset]:02X}", str(data[offset]),
                               f"上报过零NTB数量: {data[offset]}", base_offset + offset, base_offset + offset)
            offset += 1

        if offset < length:
            self._append_field(table, "保留", f"{data[offset]:02X}", "1字节", "保留",
                               base_offset + offset, base_offset + offset)
            offset += 1

        if offset + 4 <= length:
            ntb = self._read_u32_le(data, offset)
            self._append_field(table, "基准NTB值", ' '.join(f'{b:02X}' for b in data[offset:offset + 4]),
                               f"0x{ntb:08X}", f"基准NTB(高24位): {ntb}",
                               base_offset + offset, base_offset + offset + 3)
            offset += 4

        remaining = data[offset:]
        if remaining:
            self._append_field(table, "过零NTB差值", ' '.join(f'{b:02X}' for b in remaining[:20]) + ("..." if len(remaining) > 20 else ""),
                               f"{len(remaining)}字节", "过零NTB差值列表(每1.5字节一个12bit差值)",
                               base_offset + offset, base_offset + len(remaining) - 1)

        return table

    def _parse_diagnose(self, data: bytes, base_offset: int = 0) -> list:
        """解析网络诊断报文 MMeDiagnose（文档表135）"""
        table = []
        offset = 0
        length = len(data)

        if offset + 2 <= length:
            vendor_id = self._read_u16_le(data, offset)
            self._append_field(table, "芯片厂商ID", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               f"0x{vendor_id:04X}", self.CHIP_VENDOR_MAP.get(vendor_id, f"保留(0x{vendor_id:04X})"),
                               base_offset + offset, base_offset + offset + 1)
            offset += 2

        remaining = data[offset:]
        if remaining:
            self._append_field(table, "厂家自定义数据", ' '.join(f'{b:02X}' for b in remaining[:30]) + ("..." if len(remaining) > 30 else ""),
                               f"{len(remaining)}字节", "厂家自定义诊断数据",
                               base_offset + offset, base_offset + len(remaining) - 1)

        return table

    def _parse_rf_channel_conflict_report(self, data: bytes, base_offset: int = 0) -> list:
        """解析无线信道冲突上报报文 MMeRFChannelConflictReport（文档表137）"""
        table = []
        offset = 0
        length = len(data)

        if offset + 6 <= length:
            mac_raw, mac_colon = self._mac_addr(data, offset)
            self._append_field(table, "冲突网络CCO MAC地址", mac_raw, mac_colon,
                               "邻居网络CCO MAC地址", base_offset + offset, base_offset + offset + 5)
            offset += 6

        if offset < length:
            cnt = data[offset]
            self._append_field(table, "邻居网络个数", f"{cnt:02X}", str(cnt),
                               f"周边可见邻居网络个数: {cnt}", base_offset + offset, base_offset + offset)
            offset += 1

        # 邻居网络条目（每2字节: 信道号1B + option/保留1B）
        remaining = data[offset:]
        if remaining:
            entry_cnt = len(remaining) // 2
            self._append_field(table, "邻居网络条目", ' '.join(f'{b:02X}' for b in remaining[:20]),
                               f"{entry_cnt}个条目", f"每条目2字节(信道号1B+option2bit)",
                               base_offset + offset, base_offset + len(remaining) - 1)
            for i in range(0, min(len(remaining), 20), 2):
                if i + 2 <= len(remaining):
                    ch = remaining[i]
                    opt = remaining[i + 1] & 0x03
                    self._append_field(table, f"  邻居网络[{i // 2}]",
                                       ' '.join(f'{b:02X}' for b in remaining[i:i + 2]),
                                       f"信道:{ch} option:{opt}", f"无线信道号:{ch} option:{opt}",
                                       base_offset + offset + i, base_offset + offset + i + 1)

        return table

    def _parse_rf_discover_node_list(self, data: bytes, base_offset: int = 0) -> list:
        """解析无线发现列表报文 MMeRF DiscoverNodeList（文档表139）

        格式: 站点MAC地址(6B) + 统计序号(1B) + 信息单元 TLV 链
        信息单元头1B: 类型(bit0-6, 表140) + 长度类型(bit7, 表141: 0=1B长度 1=2B长度)
        长度: 1或2字节(小端); 内容: L字节
        信息单元类型0=站点属性信息（表142，14字节）
        """
        table = []
        length = len(data)
        if length < 7:
            table.append(("无线发现列表", ' '.join(f'{b:02X}' for b in data),
                         f"{length}字节", "数据不足（需至少7字节：MAC 6B + 统计序号 1B）",
                         base_offset, base_offset + max(0, length - 1)))
            return table

        mac = ':'.join(f'{b:02X}' for b in data[0:6])
        table.append(("站点MAC地址", ' '.join(f'{b:02X}' for b in data[0:6]),
                     mac, "发送无线发现列表报文节点的MAC地址",
                     base_offset, base_offset + 5))
        table.append(("统计序号", f"0x{data[6]:02X}", str(data[6]),
                     "发送无线发现列表报文的递增序号(255后环回)",
                     base_offset + 6, base_offset + 6))

        offset = 7
        unit_idx = 0
        while offset + 1 <= length:
            hdr = data[offset]
            unit_type = hdr & 0x7F
            len_type = (hdr >> 7) & 0x01
            type_name = {0: "站点属性信息", 1: "站点路由信息",
                         2: "邻居节点信道信息非位图版",
                         3: "邻居节点信道信息位图版"}.get(unit_type, f"保留({unit_type})")
            len_bytes = 2 if len_type else 1
            if offset + 1 + len_bytes > length:
                break
            content_len = int.from_bytes(data[offset + 1:offset + 1 + len_bytes], 'little')
            content_start = offset + 1 + len_bytes
            content_end = content_start + content_len
            if content_end > length:
                content_end = length
            content = data[content_start:content_end]
            table.append((
                f"信息单元{unit_idx}类型",
                f"0x{unit_type:02X}",
                type_name,
                f"类型{unit_type} 长度类型:{'2字节' if len_type else '1字节'}",
                base_offset + offset, base_offset + offset
            ))
            table.append((
                f"信息单元{unit_idx}长度",
                ' '.join(f'{b:02X}' for b in data[offset + 1:offset + 1 + len_bytes]),
                f"{content_len}字节",
                "内容长度（不含类型/长度字段）",
                base_offset + offset + 1, base_offset + offset + len_bytes
            ))
            if unit_type == 0 and len(content) >= 14:
                # 站点属性信息（表142）: CCO MAC 6B + 代理TEI 12b/角色4b + 层级4b/RF跳数4b
                #                    + 代理上行/下行接收率 + 链路最小接收率 + 发现列表周期 + 老化周期个数
                cco_mac = ':'.join(f'{b:02X}' for b in content[0:6])
                table.append(("  CCO MAC地址", ' '.join(f'{b:02X}' for b in content[0:6]),
                             cco_mac, "所属网络CCO的MAC地址",
                             base_offset + content_start, base_offset + content_start + 5))
                proxy_tei = content[6] | ((content[7] & 0x0F) << 8)
                role = (content[7] >> 4) & 0x0F
                role_map = {0: "CCO", 1: "PCO", 2: "STA", 3: "IoTG", 4: "IoTD"}
                table.append(("  代理TEI", f"0x{proxy_tei:03X}", str(proxy_tei),
                             "站点代理TEI",
                             base_offset + content_start + 6, base_offset + content_start + 7))
                table.append(("  角色", f"0x{role:X}", str(role),
                             role_map.get(role, f"保留({role})"),
                             base_offset + content_start + 7, base_offset + content_start + 7))
                level = content[8] & 0x0F
                rf_hop = (content[8] >> 4) & 0x0F
                table.append(("  层级", f"0x{level:X}", str(level),
                             "站点所处网络层级",
                             base_offset + content_start + 8, base_offset + content_start + 8))
                table.append(("  链路RF跳数", f"0x{rf_hop:X}", str(rf_hop),
                             "到CCO的RF跳数",
                             base_offset + content_start + 8, base_offset + content_start + 8))
                up_rate, down_rate, min_rate = content[9], content[10], content[11]
                table.append(("  代理上行接收率", f"0x{up_rate:02X}", f"{up_rate}%",
                             "到代理站点的上行接收率",
                             base_offset + content_start + 9, base_offset + content_start + 9))
                table.append(("  代理下行接收率", f"0x{down_rate:02X}", f"{down_rate}%",
                             "代理到本站点的下行接收率",
                             base_offset + content_start + 10, base_offset + content_start + 10))
                table.append(("  链路最小接收率", f"0x{min_rate:02X}", f"{min_rate}%",
                             "链路最小接收率",
                             base_offset + content_start + 11, base_offset + content_start + 11))
                table.append(("  无线发现列表周期", f"0x{content[12]:02X}", f"{content[12]}s",
                             "无线发现列表发送周期(秒)",
                             base_offset + content_start + 12, base_offset + content_start + 12))
                table.append(("  无线接收率老化周期个数", f"0x{content[13]:02X}", str(content[13]),
                             "接收率老化周期个数(单位: 发现列表周期)",
                             base_offset + content_start + 13, base_offset + content_start + 13))
                if len(content) > 14:
                    extra = content[14:]
                    table.append(("  属性附加数据", ' '.join(f'{b:02X}' for b in extra),
                                 f"{len(extra)}字节", "站点属性超出14B的附加内容",
                                 base_offset + content_start + 14,
                                 base_offset + content_start + len(content) - 1))
            else:
                raw_hex = ' '.join(f'{b:02X}' for b in content)
                table.append((
                    f"信息单元{unit_idx}内容",
                    raw_hex[:200] + ("..." if len(raw_hex) > 200 else ""),
                    f"{len(content)}字节",
                    f"{type_name}内容",
                    base_offset + content_start, base_offset + max(content_start, content_end - 1)
                ))
            offset = content_end
            unit_idx += 1

        if offset < length:
            remaining = data[offset:]
            table.append(("剩余数据", ' '.join(f'{b:02X}' for b in remaining),
                         f"{len(remaining)}字节", "TLV链解析后的剩余数据",
                         base_offset + offset, base_offset + length - 1))

        return table

    def _parse_bitloading_update_req(self, data: bytes, base_offset: int = 0) -> list:
        """解析Bitloading训练结果更新请求（文档表153）"""
        table = []
        offset = 0
        length = len(data)

        if offset + 3 <= length:
            src_tei = data[offset] | ((data[offset + 1] & 0x0F) << 8)
            dst_tei = ((data[offset + 1] >> 4) & 0x0F) | (data[offset + 2] << 4)
            self._append_field(table, "源TEI/目的TEI", ' '.join(f'{b:02X}' for b in data[offset:offset + 3]),
                               f"源:{src_tei} 目的:{dst_tei}", f"源TEI:{src_tei} 目的TEI:{dst_tei}",
                               base_offset + offset, base_offset + offset + 2)
            offset += 3

        if offset + 2 <= length:
            stream = data[offset] & 0x01
            cutoff_hi = data[offset + 1] & 0x01
            cutoff = ((data[offset] >> 1) & 0x7F) | (cutoff_hi << 7)
            self._append_field(table, "流数/截止载波", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               f"流:{'双流' if stream else '单流'} 截止:{cutoff}",
                               f"{'双流' if stream else '单流'} 截止载波:{cutoff}",
                               base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset + 2 <= length:
            bl_len = self._read_u16_le(data, offset)
            self._append_field(table, "比特加载表长度", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               f"{bl_len}字节", f"比特加载表长度: {bl_len}字节",
                               base_offset + offset, base_offset + offset + 1)
            offset += 2

        remaining = data[offset:]
        if remaining:
            self._append_field(table, "比特加载表", ' '.join(f'{b:02X}' for b in remaining[:20]) + ("..." if len(remaining) > 20 else ""),
                               f"{len(remaining)}字节", "比特加载表数据(每子载波组3bit)",
                               base_offset + offset, base_offset + len(remaining) - 1)

        return table

    def _parse_bitloading_update_cnf(self, data: bytes, base_offset: int = 0) -> list:
        """解析Bitloading训练结果更新确认（文档表157）"""
        table = []
        offset = 0
        length = len(data)

        if offset + 3 <= length:
            src_tei = data[offset] | ((data[offset + 1] & 0x0F) << 8)
            dst_tei = ((data[offset + 1] >> 4) & 0x0F) | (data[offset + 2] << 4)
            self._append_field(table, "源TEI/目的TEI", ' '.join(f'{b:02X}' for b in data[offset:offset + 3]),
                               f"源:{src_tei} 目的:{dst_tei}", f"源TEI:{src_tei} 目的TEI:{dst_tei}",
                               base_offset + offset, base_offset + offset + 2)
            offset += 3

        if offset < length:
            result = data[offset] & 0x01
            self._append_field(table, "更新结果", f"{data[offset]:02X}",
                               "更新成功" if result == 0 else "更新失败",
                               f"{'更新成功' if result == 0 else '更新失败'}",
                               base_offset + offset, base_offset + offset)

        return table

    def _parse_ru_snr_info(self, data: bytes, base_offset: int = 0) -> list:
        """解析RU_SNR信息告知报文（文档表158）"""
        table = []
        offset = 0
        length = len(data)

        if offset + 3 <= length:
            my_tei = data[offset] | ((data[offset + 1] & 0x0F) << 8)
            nb_start_tei = ((data[offset + 1] >> 4) & 0x0F) | (data[offset + 2] << 4)
            self._append_field(table, "本站点TEI/邻居起始TEI", ' '.join(f'{b:02X}' for b in data[offset:offset + 3]),
                               f"本站:{my_tei} 邻居起始:{nb_start_tei}",
                               f"本站点TEI:{my_tei} 邻居站点起始TEI:{nb_start_tei}",
                               base_offset + offset, base_offset + offset + 2)
            offset += 3

        if offset < length:
            ru_group = data[offset]
            ru_desc = "RU分组ID 0(各RU 5bit SNR)" if ru_group == 0 else f"保留({ru_group})"
            self._append_field(table, "RU分组ID", f"{ru_group:02X}", str(ru_group),
                               ru_desc, base_offset + offset, base_offset + offset)
            offset += 1

        if offset + 2 <= length:
            nb_cnt = self._read_u16_le(data, offset)
            self._append_field(table, "告知的邻居站点总数", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               str(nb_cnt), f"告知的邻居站点总数: {nb_cnt}",
                               base_offset + offset, base_offset + offset + 1)
            offset += 2

        if offset + 2 <= length:
            bmp_len = self._read_u16_le(data, offset)
            self._append_field(table, "邻居站点位图长度", ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                               f"{bmp_len}字节", f"邻居站点位图长度: {bmp_len}字节",
                               base_offset + offset, base_offset + offset + 1)
            offset += 2

        remaining = data[offset:]
        if remaining:
            self._append_field(table, "邻居站点位图+RU_SNR数据",
                               ' '.join(f'{b:02X}' for b in remaining[:30]) + ("..." if len(remaining) > 30 else ""),
                               f"{len(remaining)}字节", "邻居站点位图及RU_SNR信息",
                               base_offset + offset, base_offset + len(remaining) - 1)

        return table

    def _parse_tei_list_req(self, data: bytes, base_offset: int = 0) -> list:
        """解析站点TEI列表请求报文（文档表160）"""
        table = []
        offset = 0
        length = len(data)

        if offset < length:
            self._append_field(table, "请求序号", f"{data[offset]:02X}", str(data[offset]),
                               f"请求序号: {data[offset]}", base_offset + offset, base_offset + offset)
            offset += 1

        if offset + 6 <= length:
            mac_raw, mac_colon = self._mac_addr(data, offset)
            self._append_field(table, "发起站点MAC地址", mac_raw, mac_colon,
                               "发起请求的原始站点MAC地址", base_offset + offset, base_offset + offset + 5)
            offset += 6

        if offset < length:
            cnt = data[offset]
            self._append_field(table, "站点数量", f"{cnt:02X}", str(cnt),
                               f"请求的站点数量: {cnt}", base_offset + offset, base_offset + offset)
            offset += 1

        remaining = data[offset:]
        if remaining:
            mac_cnt = len(remaining) // 6
            self._append_field(table, "站点MAC地址列表", ' '.join(f'{b:02X}' for b in remaining[:18]),
                               f"{mac_cnt}个MAC", f"请求查询的站点MAC地址列表",
                               base_offset + offset, base_offset + len(remaining) - 1)
            for i in range(0, min(len(remaining), 30), 6):
                if i + 6 <= len(remaining):
                    mac_raw, mac_colon = self._mac_addr(remaining, i)
                    self._append_field(table, f"  MAC[{i // 6}]", mac_raw, mac_colon,
                                       f"请求站点MAC: {mac_colon}",
                                       base_offset + offset + i, base_offset + offset + i + 5)

        return table

    def _parse_tei_list_reply(self, data: bytes, base_offset: int = 0) -> list:
        """解析站点TEI列表回复报文（文档表161）"""
        table = []
        offset = 0
        length = len(data)

        if offset < length:
            self._append_field(table, "请求序号", f"{data[offset]:02X}", str(data[offset]),
                               f"请求序号: {data[offset]}", base_offset + offset, base_offset + offset)
            offset += 1

        if offset + 6 <= length:
            mac_raw, mac_colon = self._mac_addr(data, offset)
            self._append_field(table, "发起站点MAC地址", mac_raw, mac_colon,
                               "发起请求的原始站点MAC地址", base_offset + offset, base_offset + offset + 5)
            offset += 6

        if offset < length:
            cnt = data[offset]
            self._append_field(table, "站点数量", f"{cnt:02X}", str(cnt),
                               f"回复的站点数量: {cnt}", base_offset + offset, base_offset + offset)
            offset += 1

        # 站点TEI列表（每8字节: MAC 6B + TEI 12bit + 保留4bit）
        remaining = data[offset:]
        if remaining:
            site_cnt = len(remaining) // 8
            self._append_field(table, "站点TEI列表", ' '.join(f'{b:02X}' for b in remaining[:20]),
                               f"{site_cnt}个站点", f"每站点8字节(MAC 6B + TEI 12bit)",
                               base_offset + offset, base_offset + len(remaining) - 1)
            for i in range(0, min(len(remaining), 40), 8):
                if i + 8 <= len(remaining):
                    mac_raw, mac_colon = self._mac_addr(remaining, i)
                    tei = remaining[i + 6] | ((remaining[i + 7] & 0x0F) << 8)
                    self._append_field(table, f"  站点[{i // 8}] MAC+TEI",
                                       ' '.join(f'{b:02X}' for b in remaining[i:i + 8]),
                                       f"{mac_colon} TEI:{tei}", f"站点MAC:{mac_colon} TEI:{tei}",
                                       base_offset + offset + i, base_offset + offset + i + 7)

        return table

    def _parse_ext_network_conflict_report(self, data: bytes, base_offset: int = 0) -> list:
        """解析扩展网络冲突上报报文（文档表163）"""
        table = []
        offset = 0
        length = len(data)

        if offset + 6 <= length:
            mac_raw, mac_colon = self._mac_addr(data, offset)
            self._append_field(table, "冲突网络CCO MAC地址", mac_raw, mac_colon,
                               "邻居网络CCO MAC地址", base_offset + offset, base_offset + offset + 5)
            offset += 6

        if offset < length:
            cnt = data[offset]
            self._append_field(table, "邻居网络个数", f"{cnt:02X}", str(cnt),
                               f"周边可见邻居网络个数: {cnt}", base_offset + offset, base_offset + offset)
            offset += 1

        # 邻居网络条目（每1字节: SNID 5bit + 保留3bit）
        remaining = data[offset:]
        if remaining:
            entry_cnt = len(remaining)
            self._append_field(table, "邻居网络条目", ' '.join(f'{b:02X}' for b in remaining[:20]),
                               f"{entry_cnt}个条目", f"每条目1字节(SNID 5bit + 保留3bit)",
                               base_offset + offset, base_offset + len(remaining) - 1)
            for i in range(min(len(remaining), 20)):
                snid = remaining[i] & 0x1F
                self._append_field(table, f"  邻居网络[{i}] SNID", f"{remaining[i]:02X}", str(snid),
                                   f"邻居网络SNID: {snid}",
                                   base_offset + offset + i, base_offset + offset + i)

        return table

    def _parse_route_info(self, data: bytes, base_offset: int = 0) -> list:
        """解析路由表信息（文档表97/98）"""
        table = []
        if len(data) < 8:
            if data:
                self._append_field(table, "路由表信息", ' '.join(f'{b:02X}' for b in data),
                                   f"{len(data)}字节", "路由表数据(长度不足)", base_offset, base_offset + len(data) - 1)
            return table

        offset = 0
        direct_sta_cnt = self._read_u16_le(data, 0)
        direct_pco_cnt = self._read_u16_le(data, 2)
        route_tbl_size = self._read_u16_le(data, 4)
        self._append_field(table, "路由信息头", ' '.join(f'{b:02X}' for b in data[0:8]),
                           f"直连STA:{direct_sta_cnt} 直连PCO:{direct_pco_cnt}",
                           f"直连站点数:{direct_sta_cnt} 直连代理数:{direct_pco_cnt} 路由表大小:{route_tbl_size}",
                           base_offset, base_offset + 7)

        remaining = data[8:]
        if remaining:
            self._append_field(table, "路由表/子站点表",
                               ' '.join(f'{b:02X}' for b in remaining[:30]) + ("..." if len(remaining) > 30 else ""),
                               f"{len(remaining)}字节", "子站点表(每2字节: TEI 12bit + 链路类型 1bit)",
                               base_offset + 8, base_offset + len(data) - 1)

        return table

    def _parse_application_message(self, app_data: bytes, base_offset: int = 0) -> list:
        """解析应用层业务报文"""
        table = []
        offset = 0
        app_len = len(app_data)

        if app_len < 4:
            table.append((
                "❌ 应用层解析失败",
                "",
                "",
                f"应用层数据长度不足({app_len}字节, 最少需要4字节)",
                None, None
            ))
            return table

        # ── 报文端口号 (1字节) ──
        msg_port = app_data[offset]
        msg_port_name = MSG_PORT_MAP.get(msg_port, f"未知(0x{msg_port:02X})")
        table.append((
            "报文端口号",
            f"0x{msg_port:02X}",
            str(msg_port),
            msg_port_name,
            base_offset + offset, base_offset + offset
        ))
        offset += 1

        # ── 报文标识符 (2字节) ──
        if offset + 2 > app_len:
            return table
        msg_id = int.from_bytes(app_data[offset:offset + 2], 'little')
        msg_id_name = MSG_ID_MAP.get(msg_id, f"未知(0x{msg_id:04X})")
        table.append((
            "报文标识符",
            ' '.join(f'{b:02X}' for b in app_data[offset:offset + 2]),
            f"0x{msg_id:04X}",
            msg_id_name,
            base_offset + offset, base_offset + offset + 1
        ))
        offset += 2

        # ── 保留 (1字节) ──
        if offset >= app_len:
            return table
        reserved = app_data[offset]
        table.append((
            "保留",
            f"0x{reserved:02X}",
            str(reserved),
            "保留字段",
            base_offset + offset, base_offset + offset
        ))
        offset += 1

        if offset >= app_len:
            return table

        # ── 应用层业务报文 ──
        app_table = self._parse_business_message(app_data[offset:], msg_port, base_offset + offset)
        table.extend(app_table)

        return table

    def _parse_business_message(self, data: bytes, msg_port: int, base_offset: int) -> list:
        """解析业务报文 (控制域 + 业务标识 + 版本号 + 帧序号 + 帧长 + 数据单元 + 扩展域)"""
        table = []
        offset = 0
        data_len = len(data)

        if data_len < 2:
            table.append((
                "❌ 业务报文解析失败",
                "",
                "",
                "业务报文长度不足",
                None, None
            ))
            return table

        # ── 控制域 (2字节, 小端序) ──
        control_field = int.from_bytes(data[offset:offset + 2], 'little')
        table.append((
            "控制域（原值）",
            ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
            f"0x{control_field:04X}",
            "应用层控制域",
            base_offset + offset, base_offset + offset + 1
        ))

        # 位域解析
        direction = (control_field >> 15) & 0x01      # D15
        prm = (control_field >> 14) & 0x01             # D14
        response = (control_field >> 13) & 0x01        # D13
        extension = (control_field >> 12) & 0x01       # D12
        priority = (control_field >> 8) & 0x0F         # D11~D8
        reserved_bits = (control_field >> 4) & 0x0F    # D7~D4
        frame_type = control_field & 0x0F              # D3~D0

        # 传输方向位
        table.append((
            "  传输方向位(D15)",
            f"0x{direction:01X}",
            str(direction),
            f"{direction} - {DIRECTION_MAP.get(direction, '未知')}",
            base_offset + offset, base_offset + offset + 1
        ))

        # 启动标志位
        table.append((
            "  启动标志位(D14)",
            f"0x{prm:01X}",
            str(prm),
            f"{prm} - {PRM_MAP.get(prm, '未知')}",
            base_offset + offset, base_offset + offset + 1
        ))

        # 响应标识位
        table.append((
            "  响应标识位(D13)",
            f"0x{response:01X}",
            str(response),
            f"{response} - {RESPONSE_MAP.get(response, '未知')}",
            base_offset + offset, base_offset + offset + 1
        ))

        # 业务扩展域标识位
        table.append((
            "  业务扩展域标识位(D12)",
            f"0x{extension:01X}",
            str(extension),
            f"{extension} - {EXTENSION_MAP.get(extension, '未知')}",
            base_offset + offset, base_offset + offset + 1
        ))

        # 任务优先级
        table.append((
            "  任务优先级(D11~D8)",
            f"0x{priority:01X}",
            str(priority),
            f"优先级: {priority} (0最高, 值越大优先级越低)",
            base_offset + offset, base_offset + offset + 1
        ))

        # 保留位
        table.append((
            "  保留(D7~D4)",
            f"0x{reserved_bits:01X}",
            str(reserved_bits),
            "保留",
            base_offset + offset, base_offset + offset + 1
        ))

        # 帧类型域
        frame_type_name = FRAME_TYPE_MAP.get(frame_type, f"保留(0x{frame_type:01X})")
        table.append((
            "  帧类型域(D3~D0)",
            f"0x{frame_type:01X}",
            str(frame_type),
            f"{frame_type} - {frame_type_name}",
            base_offset + offset, base_offset + offset + 1
        ))

        offset += 2

        # ── 业务标识 (1字节) ──
        if offset >= data_len:
            return table
        service_id = data[offset]
        service_desc = get_service_desc(frame_type, service_id, msg_port)
        table.append((
            "业务标识",
            f"0x{service_id:02X}",
            str(service_id),
            f"业务标识 {service_id} - {service_desc}",
            base_offset + offset, base_offset + offset
        ))
        offset += 1

        # ── 应用版本号 (1字节) ──
        if offset >= data_len:
            return table
        app_version = data[offset]
        table.append((
            "应用版本号",
            f"0x{app_version:02X}",
            str(app_version),
            f"应用版本: {app_version}",
            base_offset + offset, base_offset + offset
        ))
        offset += 1

        # ── 帧序号 (2字节) ──
        if offset + 2 > data_len:
            return table
        frame_seq = int.from_bytes(data[offset:offset + 2], 'little')
        table.append((
            "帧序号",
            ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
            str(frame_seq),
            f"帧序号: {frame_seq}",
            base_offset + offset, base_offset + offset + 1
        ))
        offset += 2

        # ── 帧长 (2字节) ──
        if offset + 2 > data_len:
            return table
        frame_len_val = int.from_bytes(data[offset:offset + 2], 'little')
        table.append((
            "帧长",
            ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
            str(frame_len_val),
            f"业务数据单元长度: {frame_len_val}字节",
            base_offset + offset, base_offset + offset + 1
        ))
        offset += 2

        # ── 业务数据单元 (变长) ──
        sdu_end = offset + frame_len_val
        if sdu_end > data_len:
            sdu_end = data_len

        sdu_bytes = data[offset:sdu_end] if sdu_end <= data_len else data[offset:]
        # 按帧类型 + 业务标识 + 方向 分发到具体业务解析器
        payload_table = self._parse_business_payload(
            sdu_bytes, frame_type, service_id, direction, msg_port, base_offset + offset
        )
        if payload_table:
            table.extend(payload_table)
        elif sdu_end > offset:
            # 没有专用解析器时回退为原始十六进制
            sdu_hex = ' '.join(f'{b:02X}' for b in sdu_bytes)
            display_hex = sdu_hex[:120] + ("..." if len(sdu_hex) > 120 else "")
            table.append((
                "业务数据单元",
                display_hex,
                f"{len(sdu_bytes)}字节",
                "应用层业务数据（尚未实现结构化解析）",
                base_offset + offset, base_offset + sdu_end - 1
            ))
        else:
            table.append((
                "业务数据单元",
                "",
                "0字节",
                "无业务数据",
                base_offset + offset, base_offset + offset
            ))
        offset = sdu_end

        # ── 业务扩展域 (如果有) ──
        if extension == 1 and offset + 2 <= data_len:
            ext_len = int.from_bytes(data[offset:offset + 2], 'little')
            table.append((
                "扩展域数据区长度",
                ' '.join(f'{b:02X}' for b in data[offset:offset + 2]),
                str(ext_len),
                f"扩展域数据区长度: {ext_len}字节",
                base_offset + offset, base_offset + offset + 1
            ))
            offset += 2

            if offset + 2 <= data_len and ext_len > 0:
                vendor_code = data[offset:offset + 2]
                try:
                    vendor_str = vendor_code.decode('ascii', errors='replace')
                except:
                    vendor_str = ' '.join(f'{b:02X}' for b in vendor_code)
                table.append((
                    "厂家编码",
                    ' '.join(f'{b:02X}' for b in vendor_code),
                    vendor_str,
                    f"厂家编码(ASCII)",
                    base_offset + offset, base_offset + offset + 1
                ))
                offset += 2

                ext_data_end = min(offset + max(0, ext_len - 2), data_len)
                if ext_data_end > offset:
                    ext_data = data[offset:ext_data_end]
                    table.append((
                        "扩展数据区载荷",
                        ' '.join(f'{b:02X}' for b in ext_data),
                        f"{len(ext_data)}字节",
                        "业务扩展域数据",
                        base_offset + offset, base_offset + ext_data_end - 1
                    ))
                    offset = ext_data_end

        # ── 剩余数据 ──
        if offset < data_len:
            remaining = data[offset:]
            table.append((
                "剩余数据",
                ' '.join(f'{b:02X}' for b in remaining),
                f"{len(remaining)}字节",
                "未解析数据(可能为填充或后续数据)",
                base_offset + offset, base_offset + data_len - 1
            ))

        return table

    # ── 应用层业务数据单元解析 ──

    def _parse_business_payload(
        self,
        payload: bytes,
        frame_type: int,
        service_id: int,
        direction: int,
        msg_port: int,
        base_offset: int
    ) -> list:
        """
        根据帧类型、业务标识和方向，分发到具体业务数据单元解析器。
        返回 [(字段名, 原始值, 解析值, 说明, byte_start, byte_end), ...]
        """
        if frame_type == 0x0:  # 确认/否认
            return self._parse_payload_confirm(payload, service_id, base_offset)
        elif frame_type == 0x1:  # 数据传输
            return self._parse_payload_data_transfer(payload, service_id, direction, base_offset)
        elif frame_type == 0x2:  # 命令帧
            return self._parse_payload_command(payload, service_id, direction, msg_port, base_offset)
        elif frame_type == 0x3:  # 主动上报
            return self._parse_payload_active_report(payload, service_id, direction, base_offset)
        elif frame_type == 0x4:  # 抄控器协议
            return self._parse_payload_meter_controller(payload, service_id, direction, base_offset)
        elif frame_type == 0x5:  # 广播命令
            return self._parse_payload_broadcast(payload, service_id, direction, base_offset)
        elif frame_type == 0x6:  # 数据订阅路由
            return self._parse_payload_data_subscription(payload, service_id, direction, base_offset)
        # 厂家调试 0xE 等保留
        return []

    # ── 0x0 确认/否认 ──

    def _parse_payload_confirm(self, payload: bytes, service_id: int, base_offset: int) -> list:
        """确认/否认业务数据单元"""
        table = []
        if service_id == 0x00:
            table.append((
                "确认/否认负载",
                "",
                "确认",
                "确认报文，无业务数据",
                base_offset, base_offset
            ))
        elif service_id == 0x01:
            if len(payload) < 1:
                table.append((
                    "❌ 否认报文解析失败",
                    "",
                    "",
                    "否认报文需要1字节原因码",
                    None, None
                ))
                return table
            reason = payload[0]
            reason_map = {
                0x00: "通信超时",
                0x01: "业务标识不支持",
                0x02: "CCO忙",
                0x03: "终端层无应答",
                0x04: "格式错误",
                0xFF: "其他",
            }
            reason_desc = reason_map.get(reason, f"保留(0x{reason:02X})")
            table.append((
                "否认原因码",
                f"0x{reason:02X}",
                str(reason),
                reason_desc,
                base_offset, base_offset
            ))
        return table

    # ── 0x1 数据传输 ──

    # 数据透传业务代码
    DATA_FORWARD_SERVICE_CODE_MAP = {
        0x00: "默认透传",
        0x01: "精准对时",
        0x02: "负荷曲线采集与存储",
    }

    # 负荷曲线数据标识码 → (名称, 数据长度字节)
    _LOAD_CURVE_DATA_ITEM_MAP = {
        (0x06, 0x12, 0x01, 0x01): ("A相电压", 2),
        (0x06, 0x12, 0x01, 0x02): ("B相电压", 2),
        (0x06, 0x12, 0x01, 0x03): ("C相电压", 2),
        (0x06, 0x12, 0x01, 0xFF): ("电压曲线数据块", 6),       # ABC三相×2B
        (0x06, 0x12, 0x02, 0x01): ("A相电流", 3),
        (0x06, 0x12, 0x02, 0x02): ("B相电流", 3),
        (0x06, 0x12, 0x02, 0x03): ("C相电流", 3),
        (0x06, 0x12, 0x02, 0xFF): ("电流曲线数据块", 9),       # ABC三相×3B
        (0x06, 0x12, 0x03, 0x00): ("总有功功率", 3),
        (0x06, 0x12, 0x03, 0x01): ("A相有功功率", 3),
        (0x06, 0x12, 0x03, 0x02): ("B相有功功率", 3),
        (0x06, 0x12, 0x03, 0x03): ("C相有功功率", 3),
        (0x06, 0x12, 0x03, 0xFF): ("有功功率曲线数据块", 12),  # 总+ABC=4项×3B
        (0x06, 0x12, 0x04, 0x00): ("总无功功率", 3),
        (0x06, 0x12, 0x04, 0x01): ("A相无功功率", 3),
        (0x06, 0x12, 0x04, 0x02): ("B相无功功率", 3),
        (0x06, 0x12, 0x04, 0x03): ("C相无功功率", 3),
        (0x06, 0x12, 0x04, 0xFF): ("无功功率曲线数据块", 12),  # 总+ABC=4项×3B
        (0x06, 0x12, 0x05, 0x00): ("总功率因数", 2),
        (0x06, 0x12, 0x05, 0x01): ("A功率因数", 2),
        (0x06, 0x12, 0x05, 0x02): ("B功率因数", 2),
        (0x06, 0x12, 0x05, 0x03): ("C功率因数", 2),
        (0x06, 0x12, 0x05, 0xFF): ("功率因数曲线数据块", 8),  # 总+ABC=4项×2B
        (0x06, 0x12, 0x06, 0x01): ("正向有功总电能", 4),
        (0x06, 0x12, 0x06, 0x02): ("反向有功总电能", 4),
        (0x06, 0x12, 0x06, 0x03): ("组合无功1总电能", 4),
        (0x06, 0x12, 0x06, 0x04): ("组合无功2总电能", 4),
        (0x06, 0x12, 0x06, 0xFF): ("有功无功总电能数据块", 16), # 4项×4B
        (0x06, 0x12, 0x07, 0x01): ("第一象限无功总电能", 4),
        (0x06, 0x12, 0x07, 0x02): ("第二象限无功总电能", 4),
        (0x06, 0x12, 0x07, 0x03): ("第三象限无功总电能", 4),
        (0x06, 0x12, 0x07, 0x04): ("第四象限无功总电能", 4),
        (0x06, 0x12, 0x07, 0xFF): ("四象限无功曲线数据块", 16), # 4象限×4B
        (0x06, 0x12, 0x08, 0x01): ("当前有功需量", 3),
        (0x06, 0x12, 0x08, 0x02): ("当前无功需量", 3),
        (0x06, 0x12, 0x08, 0xFF): ("当前需量曲线数据块", 6),   # 有功+无功=2项×3B
    }

    def _parse_payload_data_transfer(
        self, payload: bytes, service_id: int, direction: int, base_offset: int
    ) -> list:
        """数据传输业务数据单元（按 service_id 和方向分发）"""
        if service_id == 0x00:
            return self._parse_data_transparent_to_device(payload, direction, base_offset)
        elif service_id == 0x01:
            return self._parse_data_transparent_to_module(payload, direction, base_offset)
        elif service_id == 0x02:
            return self._parse_concurrent_meter_read(payload, direction, base_offset)
        elif service_id == 0x03:
            return self._parse_station_to_station(payload, direction, base_offset)
        return []

    def _parse_data_transparent_to_device(
        self, payload: bytes, direction: int, base_offset: int
    ) -> list:
        """0x00 数据透传至设备"""
        table = []
        offset = 0
        # 源地址 6B / 目的地址 6B
        for label in ("源地址", "目的地址"):
            raw, parsed = self._mac_addr(payload, offset)
            table.append((
                label,
                raw,
                parsed,
                f"{label}: {parsed}",
                base_offset + offset, base_offset + offset + 5
            ))
            offset += 6

        if direction == 0:  # 下行
            if offset < len(payload):
                timeout = payload[offset]
                table.append((
                    "设备超时时间",
                    f"0x{timeout:02X}",
                    str(timeout),
                    f"{timeout * 100}毫秒" if timeout else "使用默认超时时间",
                    base_offset + offset, base_offset + offset
                ))
                offset += 1
            if offset < len(payload):
                reserved = payload[offset]
                table.append((
                    "保留",
                    f"0x{reserved:02X}",
                    str(reserved),
                    "保留位默认填0",
                    base_offset + offset, base_offset + offset
                ))
                offset += 1
        else:  # 上行 - 保留2字节(表26: 站点间通信/数据透传 上行报文)
            if offset + 2 <= len(payload):
                reserved = self._uint16_le(payload, offset)
                table.append((
                    "保留",
                    ' '.join(f'{b:02X}' for b in payload[offset:offset + 2]),
                    f"0x{reserved:04X}",
                    "保留位默认填0（2字节）",
                    base_offset + offset, base_offset + offset + 1
                ))
                offset += 2

        if offset + 2 <= len(payload):
            data_len = self._uint16_le(payload, offset)
            table.append((
                "转发数据长度",
                ' '.join(f'{b:02X}' for b in payload[offset:offset + 2]),
                str(data_len),
                f"实际数据域长度: {data_len}字节",
                base_offset + offset, base_offset + offset + 1
            ))
            offset += 2
            if data_len > 0 and offset + data_len <= len(payload):
                data_bytes = payload[offset:offset + data_len]
                table.append((
                    "转发数据内容",
                    ' '.join(f'{b:02X}' for b in data_bytes[:30]) + ("..." if data_len > 30 else ""),
                    f"{data_len}字节",
                    "待转发/已转发的设备数据",
                    base_offset + offset, base_offset + offset + data_len - 1
                ))
                offset += data_len

        if offset < len(payload):
            remaining = payload[offset:]
            table.append((
                "剩余数据",
                ' '.join(f'{b:02X}' for b in remaining),
                f"{len(remaining)}字节",
                "未解析数据",
                base_offset + offset, base_offset + len(payload) - 1
            ))
        return table

    def _parse_data_transparent_to_module(
        self, payload: bytes, direction: int, base_offset: int
    ) -> list:
        """0x01 数据透传至模块"""
        table = []
        offset = 0
        for label in ("源地址", "目的地址"):
            raw, parsed = self._mac_addr(payload, offset)
            table.append((
                label,
                raw,
                parsed,
                f"{label}: {parsed}",
                base_offset + offset, base_offset + offset + 5
            ))
            offset += 6

        if offset < len(payload):
            reserved = payload[offset]
            table.append((
                "保留",
                f"0x{reserved:02X}",
                str(reserved),
                "保留位默认填0",
                base_offset + offset, base_offset + offset
            ))
            offset += 1

        if offset < len(payload):
            svc_code = payload[offset]
            code_desc = self.DATA_FORWARD_SERVICE_CODE_MAP.get(svc_code, f"保留(0x{svc_code:02X})")
            table.append((
                "业务代码",
                f"0x{svc_code:02X}",
                str(svc_code),
                f"业务代码: {code_desc}",
                base_offset + offset, base_offset + offset
            ))
            offset += 1

        if offset + 2 <= len(payload):
            data_len = self._uint16_le(payload, offset)
            table.append((
                "数据转发长度",
                ' '.join(f'{b:02X}' for b in payload[offset:offset + 2]),
                str(data_len),
                f"实际数据域长度: {data_len}字节",
                base_offset + offset, base_offset + offset + 1
            ))
            offset += 2
            if data_len > 0 and offset + data_len <= len(payload):
                fwd_data = payload[offset:offset + data_len]
                # 根据业务代码深入解析转发数据内容
                if svc_code == 0x01:
                    sub = self._parse_precise_timing(fwd_data, base_offset + offset)
                    table.extend(sub)
                elif svc_code == 0x02:
                    sub = self._parse_load_curve(fwd_data, direction, base_offset + offset)
                    table.extend(sub)
                else:
                    table.append((
                        "数据转发内容",
                        ' '.join(f'{b:02X}' for b in fwd_data[:30]) + ("..." if data_len > 30 else ""),
                        f"{data_len}字节",
                        "待转发/已转发的模块数据",
                        base_offset + offset, base_offset + offset + data_len - 1
                    ))
                offset += data_len

        if offset < len(payload):
            remaining = payload[offset:]
            table.append((
                "剩余数据",
                ' '.join(f'{b:02X}' for b in remaining),
                f"{len(remaining)}字节",
                "未解析数据",
                base_offset + offset, base_offset + len(payload) - 1
            ))
        return table

    def _parse_precise_timing(
        self, data: bytes, base_offset: int
    ) -> list:
        """解析精准对时转发数据内容 (业务代码0x01, 表57)"""
        table = []
        offset = 0
        ln = len(data)

        if ln < 8:
            table.append(("精准对时数据", ' '.join(f'{b:02X}' for b in data),
                          f"{ln}字节", "数据不足", base_offset, base_offset + ln - 1 if ln else base_offset))
            return table

        # 端口号 (2B)
        port = self._uint16_le(data, offset)
        table.append(("端口号", f"0x{port:04X}", str(port),
                       "精准对时端口" if port == 0x01 else "",
                       base_offset + offset, base_offset + offset + 1))
        offset += 2

        # 序号 (1B)
        seq = data[offset]
        table.append(("序号", f"0x{seq:02X}", str(seq),
                       "CCO下发广播报文序号", base_offset + offset, base_offset + offset))
        offset += 1

        # 保留 (1B)
        rsv = data[offset]
        table.append(("保留", f"0x{rsv:02X}", str(rsv),
                       "保留", base_offset + offset, base_offset + offset))
        offset += 1

        # CCO网络基准时间 (4B, little-endian)
        ntb = self._read_u32_le(data, offset)
        table.append(("CCO网络基准时间", f"0x{ntb:08X}", str(ntb),
                       "CCO当前NTB (计数频率25MHz)", base_offset + offset, base_offset + offset + 3))
        offset += 4

        # 校时报文 (剩余字节, DL/T 645)
        if offset < ln:
            timing_msg = data[offset:]
            table.append(("校时报文(DL/T645)",
                          ' '.join(f'{b:02X}' for b in timing_msg[:40]) + ("..." if len(timing_msg) > 40 else ""),
                          f"{len(timing_msg)}字节",
                          "DL/T 645广播校时报文",
                          base_offset + offset, base_offset + ln - 1))
        return table

    def _parse_load_curve(
        self, data: bytes, direction: int, base_offset: int
    ) -> list:
        """解析负荷曲线采集与存储转发数据内容 (业务代码0x02, 表65-67)"""
        table = []
        offset = 0
        ln = len(data)
        if ln < 1:
            return table

        # 功能码 (1B)
        func_code = data[offset]
        func_desc = {0x01: "配置采集间隔", 0x02: "抄读数据项"}.get(func_code, f"保留(0x{func_code:02X})")
        table.append(("功能码", f"0x{func_code:02X}", str(func_code),
                       func_desc, base_offset + offset, base_offset + offset))
        offset += 1

        if func_code == 0x01:
            # ---- 配置采集间隔 (表65): 采集间隔(4B) ----
            if offset + 4 <= ln:
                interval = self._read_u32_le(data, offset)
                table.append(("采集间隔", f"0x{interval:08X}", str(interval),
                               f"{interval}分钟", base_offset + offset, base_offset + offset + 3))
                offset += 4
            elif offset < ln:
                rem = data[offset:]
                table.append(("采集间隔(不完整)", ' '.join(f'{b:02X}' for b in rem),
                              f"{len(rem)}字节", "数据不足4字节",
                              base_offset + offset, base_offset + ln - 1))
                offset = ln

        elif func_code == 0x02:
            # ---- 抄读数据项 (表66下行/表67上行) ----
            if offset >= ln:
                return table

            # 表类型 (1B)
            meter_type = data[offset]
            mt_desc = {0x00: "单相表", 0x01: "三相表"}.get(meter_type, f"保留(0x{meter_type:02X})")
            table.append(("表类型", f"0x{meter_type:02X}", str(meter_type),
                           mt_desc, base_offset + offset, base_offset + offset))
            offset += 1

            # 起始点时间 (5B BCD, YYMMDDhhmm)
            if offset + 5 <= ln:
                bcd_bytes = data[offset:offset + 5]
                # 低字节在前: mm hh DD MM YY
                mm, hh, dd, mo, yy = bcd_bytes
                time_str = f"20{yy:02X}-{mo:02X}-{dd:02X} {hh:02X}:{mm:02X}"
                table.append(("起始点时间", ' '.join(f'{b:02X}' for b in bcd_bytes),
                               time_str, "YYMMDDhhmm (BCD, 低字节在前)",
                               base_offset + offset, base_offset + offset + 4))
                offset += 5
            else:
                offset = ln
                return table

            # 采集点数量 (1B)
            if offset >= ln:
                return table
            point_count = data[offset]
            table.append(("采集点数量", f"0x{point_count:02X}", str(point_count),
                           f"{point_count}个采集点", base_offset + offset, base_offset + offset))
            offset += 1

            # 采集时间间隔 (1B)
            if offset >= ln:
                return table
            collect_interval = data[offset]
            table.append(("采集时间间隔", f"0x{collect_interval:02X}", str(collect_interval),
                           f"{collect_interval}分钟", base_offset + offset, base_offset + offset))
            offset += 1

            # 数据项数量 m (1B)
            if offset >= ln:
                return table
            item_count = data[offset]
            table.append(("数据项数量", f"0x{item_count:02X}", str(item_count),
                           f"{item_count}项", base_offset + offset, base_offset + offset))
            offset += 1

            # 解析每个数据标识 (4B) 及其对应的数据(仅上行)
            data_item_sizes = []  # 记录每个标识对应的数据长度
            for i in range(item_count):
                if offset + 4 > ln:
                    break
                di = data[offset:offset + 4]
                di_key = (di[3], di[2], di[1], di[0])  # DI3,DI2,DI1,DI0
                item_name, item_size = self._LOAD_CURVE_DATA_ITEM_MAP.get(
                    di_key, (f"未知标识(0x{di[3]:02X}{di[2]:02X}{di[1]:02X}{di[0]:02X})", 0)
                )
                table.append((f"数据标识{i+1}",
                              f"{di[0]:02X} {di[1]:02X} {di[2]:02X} {di[3]:02X}",
                              item_name,
                              f"DI3={di[3]:02X} DI2={di[2]:02X} DI1={di[1]:02X} DI0={di[0]:02X}",
                              base_offset + offset, base_offset + offset + 3))
                offset += 4
                data_item_sizes.append((item_name, item_size))

                # 上行报文(方向1): 每个数据标识后紧跟 n 个采集点的数据
                if direction == 1 and point_count > 0 and item_size > 0:
                    for pt in range(point_count):
                        if offset + item_size > ln:
                            break
                        pt_data = data[offset:offset + item_size]
                        val_hex = ' '.join(f'{b:02X}' for b in pt_data)
                        # 判断是否全FF(无数据)
                        if all(b == 0xFF for b in pt_data):
                            val_str = "无数据(FF)"
                        else:
                            val_str = val_hex
                        table.append((f"{item_name}-点{pt+1}", val_hex, val_str,
                                       f"第{pt+1}个采集点数据({item_size}字节)",
                                       base_offset + offset, base_offset + offset + item_size - 1))
                        offset += item_size

            # 如果还有剩余数据
            if offset < ln:
                rem = data[offset:]
                table.append(("负荷曲线剩余数据",
                              ' '.join(f'{b:02X}' for b in rem[:30]) + ("..." if len(rem) > 30 else ""),
                              f"{len(rem)}字节", "未解析数据",
                              base_offset + offset, base_offset + ln - 1))

        else:
            # 未知功能码, 输出剩余原始数据
            if offset < ln:
                rem = data[offset:]
                table.append(("功能码数据", ' '.join(f'{b:02X}' for b in rem[:30]) + ("..." if len(rem) > 30 else ""),
                              f"{len(rem)}字节", f"功能码0x{func_code:02X}的数据",
                              base_offset + offset, base_offset + ln - 1))

        return table

    def _parse_concurrent_meter_read(
        self, payload: bytes, direction: int, base_offset: int
    ) -> list:
        """0x02 并发抄读端设备"""
        table = []
        offset = 0
        for label in ("源地址", "目的地址"):
            raw, parsed = self._mac_addr(payload, offset)
            table.append((
                label,
                raw,
                parsed,
                f"{label}: {parsed}",
                base_offset + offset, base_offset + offset + 5
            ))
            offset += 6

        if direction == 0:  # 下行 (表22: 源/目的地址后直接为配置字)
            if offset < len(payload):
                cfg = payload[offset]
                no_ack_retry = (cfg >> 4) & 0x01
                nak_retry = (cfg >> 5) & 0x01
                max_retry = (cfg >> 6) & 0x03
                table.append((
                    "配置字",
                    f"0x{cfg:02X}",
                    str(cfg),
                    f"未应答重试={no_ack_retry}, 否认重试={nak_retry}, 最大重试={max_retry}",
                    base_offset + offset, base_offset + offset
                ))
                offset += 1
            if offset < len(payload):
                interval = payload[offset]
                table.append((
                    "报文间间隔",
                    f"0x{interval:02X}",
                    str(interval),
                    f"{interval * 10}毫秒",
                    base_offset + offset, base_offset + offset
                ))
                offset += 1
            if offset < len(payload):
                timeout = payload[offset]
                table.append((
                    "设备超时时间",
                    f"0x{timeout:02X}",
                    str(timeout),
                    f"{timeout * 100}毫秒",
                    base_offset + offset, base_offset + offset
                ))
                offset += 1
            if offset < len(payload):
                reserved = payload[offset]
                table.append((
                    "保留",
                    f"0x{reserved:02X}",
                    str(reserved),
                    "保留位默认填0",
                    base_offset + offset, base_offset + offset
                ))
                offset += 1
        else:  # 上行 (表24: 源/目的地址后为应答状态+保留2字节)
            if offset < len(payload):
                status = payload[offset] & 0x0F
                table.append((
                    "应答状态",
                    f"0x{status:01X}",
                    str(status),
                    "正常应答" if status == 0 else f"状态{status}",
                    base_offset + offset, base_offset + offset
                ))
                offset += 1
            if offset + 2 <= len(payload):
                reserved = self._uint16_le(payload, offset)
                table.append((
                    "保留",
                    ' '.join(f'{b:02X}' for b in payload[offset:offset + 2]),
                    f"0x{reserved:04X}",
                    "保留位默认填0（2字节）",
                    base_offset + offset, base_offset + offset + 1
                ))
                offset += 2

        if offset + 2 <= len(payload):
            list_len = self._uint16_le(payload, offset)
            table.append((
                "报文列表对象长度",
                ' '.join(f'{b:02X}' for b in payload[offset:offset + 2]),
                str(list_len),
                f"报文列表对象字段长度: {list_len}字节",
                base_offset + offset, base_offset + offset + 1
            ))
            offset += 2

            list_end = offset + list_len
            if list_end > len(payload):
                list_end = len(payload)
            # 报文条数 (表23第一字节)
            if offset < list_end:
                msg_count = payload[offset]
                table.append((
                    "报文条数",
                    f"0x{msg_count:02X}",
                    str(msg_count),
                    f"共{msg_count}条抄读报文",
                    base_offset + offset, base_offset + offset
                ))
                offset += 1
                for msg_idx in range(min(msg_count, 32)):  # 安全上限32
                    if offset + 2 > list_end:
                        break
                    raw_len = self._uint16_le(payload, offset)
                    item_len = raw_len & 0x0FFF  # D15~D12保留, D11~D0长度
                    table.append((
                        f"  报文{msg_idx}长度",
                        ' '.join(f'{b:02X}' for b in payload[offset:offset + 2]),
                        str(item_len),
                        f"第{msg_idx}条报文长度(保留4位+长度12位)",
                        base_offset + offset, base_offset + offset + 1
                    ))
                    offset += 2
                    if item_len > 0 and offset + item_len <= list_end:
                        item_data = payload[offset:offset + item_len]
                        table.append((
                            f"  报文{msg_idx}内容",
                            ' '.join(f'{b:02X}' for b in item_data[:30]) + ("..." if item_len > 30 else ""),
                            f"{item_len}字节",
                            f"第{msg_idx}条抄读报文",
                            base_offset + offset, base_offset + offset + item_len - 1
                        ))
                        offset += item_len

        if offset < len(payload):
            remaining = payload[offset:]
            table.append((
                "剩余数据",
                ' '.join(f'{b:02X}' for b in remaining),
                f"{len(remaining)}字节",
                "未解析数据",
                base_offset + offset, base_offset + len(payload) - 1
            ))
        return table

    def _parse_station_to_station(
        self, payload: bytes, direction: int, base_offset: int
    ) -> list:
        """0x03 站点间通信"""
        table = []
        offset = 0
        for label in ("源地址", "目的地址"):
            raw, parsed = self._mac_addr(payload, offset)
            table.append((
                label,
                raw,
                parsed,
                f"{label}: {parsed}",
                base_offset + offset, base_offset + offset + 5
            ))
            offset += 6

        # offset 12-13：上行(表26)为 保留(2)；下行含 设备超时时间(1)+保留(1)
        # 传输方向位 direction 来自应用层控制域 D15（0=下行, 1=上行）
        if direction == 1:  # 上行(STA->CCO) - 表26 站点间通信业务上行报文
            if offset + 2 <= len(payload):
                reserved = self._uint16_le(payload, offset)
                table.append((
                    "保留",
                    ' '.join(f'{b:02X}' for b in payload[offset:offset + 2]),
                    f"0x{reserved:04X}",
                    "保留位默认填0（2字节）",
                    base_offset + offset, base_offset + offset + 1
                ))
                offset += 2
        else:  # 下行(CCO->STA) - 含设备超时时间
            if offset < len(payload):
                timeout = payload[offset]
                table.append((
                    "设备超时时间",
                    f"0x{timeout:02X}",
                    str(timeout),
                    f"{timeout * 100}毫秒" if timeout else "使用默认超时时间",
                    base_offset + offset, base_offset + offset
                ))
                offset += 1

            if offset < len(payload):
                reserved = payload[offset]
                table.append((
                    "保留",
                    f"0x{reserved:02X}",
                    str(reserved),
                    "保留位默认填0",
                    base_offset + offset, base_offset + offset
                ))
                offset += 1

        if offset + 2 <= len(payload):
            data_len = self._uint16_le(payload, offset)
            table.append((
                "数据转发长度",
                ' '.join(f'{b:02X}' for b in payload[offset:offset + 2]),
                str(data_len),
                f"实际数据域长度: {data_len}字节",
                base_offset + offset, base_offset + offset + 1
            ))
            offset += 2
            if data_len > 0 and offset + data_len <= len(payload):
                data_bytes = payload[offset:offset + data_len]
                table.append((
                    "数据转发内容",
                    ' '.join(f'{b:02X}' for b in data_bytes[:30]) + ("..." if data_len > 30 else ""),
                    f"{data_len}字节",
                    "站点间转发的数据",
                    base_offset + offset, base_offset + offset + data_len - 1
                ))
                offset += data_len

        if offset < len(payload):
            remaining = payload[offset:]
            table.append((
                "剩余数据",
                ' '.join(f'{b:02X}' for b in remaining),
                f"{len(remaining)}字节",
                "未解析数据",
                base_offset + offset, base_offset + len(payload) - 1
            ))
        return table

    # ── 0x2 命令帧（已按第5部分文档实现） ──


    def _parse_payload_command(
        self, payload: bytes, service_id: int, direction: int, msg_port: int, base_offset: int
    ) -> list:
        """命令帧业务数据单元：按第5部分文档解析"""
        return parse_command_payload(payload, service_id, direction, msg_port, base_offset)

    # ── 0x3 主动上报 ──

    # 主动上报事件代码
    ACTIVE_REPORT_EVENT_MAP = {
        0x0000: "保留",
        0x0001: "从节点掉线",
        0x0002: "从节点上线",
        0x0003: "抄表失败",
        0x0004: "从节点异常",
        0x0005: "相位变化",
        0x0006: "拓扑变化",
        0x0007: "通信模块事件",
        0x0008: "停上电事件",
        0xFFFF: "其他事件",
    }

    def _parse_payload_active_report(
        self, payload: bytes, service_id: int, direction: int, base_offset: int
    ) -> list:
        """主动上报业务数据单元"""
        table = []
        offset = 0

        service_names = {
            0x00: "事件主动上报",
            0x01: "停上电事件上报",
            0x02: "通信模块事件上报",
        }
        service_name = service_names.get(service_id, f"上报类型(0x{service_id:02X})")
        table.append((
            "上报业务类型", f"0x{service_id:02X}", str(service_id), service_name,
            base_offset, base_offset
        ))

        if offset + 2 <= len(payload):
            event_code = self._uint16_le(payload, offset)
            event_desc = self.ACTIVE_REPORT_EVENT_MAP.get(event_code, f"保留(0x{event_code:04X})")
            table.append((
                "上报事件代码",
                ' '.join(f'{b:02X}' for b in payload[offset:offset + 2]),
                f"0x{event_code:04X}",
                f"事件: {event_desc}",
                base_offset + offset, base_offset + offset + 1
            ))
            offset += 2

            if offset + 2 <= len(payload):
                data_len = self._uint16_le(payload, offset)
                table.append((
                    "事件数据长度",
                    ' '.join(f'{b:02X}' for b in payload[offset:offset + 2]),
                    str(data_len), f"事件数据长度: {data_len}字节",
                    base_offset + offset, base_offset + offset + 1
                ))
                offset += 2

                if data_len > 0 and offset + data_len <= len(payload):
                    event_data = payload[offset:offset + data_len]
                    # 停上电事件深入解析
                    if service_id == 0x01:
                        sub = self._parse_power_outage_report(
                            event_data, direction, base_offset + offset)
                        table.extend(sub)
                    else:
                        table.append((
                            "事件数据内容",
                            ' '.join(f'{b:02X}' for b in event_data[:30]) + ("..." if data_len > 30 else ""),
                            f"{data_len}字节", "事件原始数据",
                            base_offset + offset, base_offset + offset + data_len - 1
                        ))
                    offset += data_len

        if offset < len(payload):
            remaining = payload[offset:]
            table.append((
                "剩余数据", ' '.join(f'{b:02X}' for b in remaining),
                f"{len(remaining)}字节", "未解析数据",
                base_offset + offset, base_offset + len(payload) - 1
            ))
        return table

    def _parse_power_outage_report(
        self, data: bytes, direction: int, base_offset: int
    ) -> list:
        """解析停上电事件上报数据 (业务标识0x01, 表46-49)"""
        table = []
        offset = 0
        ln = len(data)
        if ln < 9:
            table.append(("停电事件数据", ' '.join(f'{b:02X}' for b in data),
                          f"{ln}字节", "数据不足",
                          base_offset, base_offset + ln - 1 if ln else base_offset))
            return table

        # 帧头长度 (1B)
        hdr_len = data[offset]
        table.append(("帧头长度", f"0x{hdr_len:02X}", str(hdr_len),
                       "除数据域外的长度(通常12字节)",
                       base_offset + offset, base_offset + offset))
        offset += 1

        # STA MAC (6B)
        mac_raw, mac = self._mac_addr(data, offset)
        table.append(("STA MAC", mac_raw, mac, "停电事件源STA地址",
                       base_offset + offset, base_offset + offset + 5))
        offset += 6

        # 功能码 (1B)
        func_code = data[offset]
        func_desc = {1: "STA主动上报(模块触发)", 2: "STA主动上报(采集器触发)"}.get(
            func_code, f"保留(0x{func_code:02X})")
        table.append(("功能码", f"0x{func_code:02X}", str(func_code), func_desc,
                       base_offset + offset, base_offset + offset))
        offset += 1

        # 数据长度 (1B)
        data_len = data[offset]
        table.append(("数据长度", f"0x{data_len:02X}", str(data_len),
                       f"数据域长度: {data_len}字节",
                       base_offset + offset, base_offset + offset))
        offset += 1

        # 数据域
        if offset >= ln:
            return table

        event_type = data[offset]
        if event_type == 1:
            # 位图式停电 (表48)
            table.append(("事件类型", f"0x{event_type:02X}", str(event_type),
                           "停电事件(位图)", base_offset + offset, base_offset + offset))
            offset += 1
            if offset + 2 <= ln:
                start_tei = self._uint16_le(data, offset)
                table.append(("起始TEI", f"0x{start_tei:04X}", str(start_tei),
                               "发生事件站点起始TEI",
                               base_offset + offset, base_offset + offset + 1))
                offset += 2
            if offset < ln:
                bitmap = data[offset:]
                bits_set = []
                for bi, byte in enumerate(bitmap):
                    for bit in range(8):
                        if byte & (1 << bit):
                            bits_set.append(str(start_tei + bi * 8 + bit))
                table.append(("节点位图", ' '.join(f'{b:02X}' for b in bitmap),
                               f"停电TEI: {','.join(bits_set)}" if bits_set else "无停电节点",
                               "对应bit置1表示该TEI节点发生停电",
                               base_offset + offset, base_offset + ln - 1))

        elif event_type in (3, 4):
            # 地址式停电/上电 (表49)
            type_desc = {3: "停电事件(地址)", 4: "上电事件(地址)"}.get(event_type, "")
            table.append(("事件类型", f"0x{event_type:02X}", str(event_type), type_desc,
                           base_offset + offset, base_offset + offset))
            offset += 1
            if offset + 2 <= ln:
                meter_count = self._uint16_le(data, offset)
                table.append(("电表个数", f"0x{meter_count:04X}", str(meter_count),
                               f"{meter_count}只电表",
                               base_offset + offset, base_offset + offset + 1))
                offset += 2
            for mi in range(meter_count):
                if offset + 7 > ln:
                    break
                addr_raw, addr = self._mac_addr(data, offset)
                table.append((f"电表{mi+1}地址", addr_raw, addr,
                               "发生事件的电表地址",
                               base_offset + offset, base_offset + offset + 5))
                offset += 6
                status = data[offset]
                status_desc = "未停电" if status == 1 else "停电" if status == 0 else f"保留(0x{status:02X})"
                table.append((f"电表{mi+1}带电状态", f"0x{status:02X}", str(status),
                               status_desc,
                               base_offset + offset, base_offset + offset))
                offset += 1
        else:
            # 未知事件类型，输出原始数据
            rem = data[offset:]
            table.append(("事件数据", ' '.join(f'{b:02X}' for b in rem[:30]) + ("..." if len(rem) > 30 else ""),
                          f"{len(rem)}字节", f"事件类型0x{event_type:02X}",
                          base_offset + offset, base_offset + ln - 1))

        return table

    # ── 0x4 抄控器协议 ──

    def _parse_payload_meter_controller(
        self, payload: bytes, service_id: int, direction: int, base_offset: int
    ) -> list:
        """抄控器协议业务数据单元"""
        table = []
        offset = 0

        service_names = {
            0x00: "抄控器-CCO协议",
            0x01: "数据透传串口转发",
        }
        table.append((
            "抄控器业务类型", f"0x{service_id:02X}", str(service_id),
            service_names.get(service_id, f"保留(0x{service_id:02X})"),
            base_offset, base_offset
        ))

        if service_id == 0x01:
            for label in ("源地址", "目的地址"):
                if offset + 6 > len(payload):
                    break
                raw, parsed = self._mac_addr(payload, offset)
                table.append((
                    label, raw, parsed, f"{label}: {parsed}",
                    base_offset + offset, base_offset + offset + 5
                ))
                offset += 6
            if offset < len(payload):
                reserved = payload[offset]
                table.append((
                    "保留", f"0x{reserved:02X}", str(reserved), "保留位默认填0",
                    base_offset + offset, base_offset + offset
                ))
                offset += 1
            if offset + 2 <= len(payload):
                data_len = self._uint16_le(payload, offset)
                table.append((
                    "串口转发数据长度",
                    ' '.join(f'{b:02X}' for b in payload[offset:offset + 2]),
                    str(data_len), f"数据长度: {data_len}字节",
                    base_offset + offset, base_offset + offset + 1
                ))
                offset += 2
                if data_len > 0 and offset + data_len <= len(payload):
                    data_bytes = payload[offset:offset + data_len]
                    table.append((
                        "串口转发数据内容",
                        ' '.join(f'{b:02X}' for b in data_bytes[:30]) + ("..." if data_len > 30 else ""),
                        f"{data_len}字节", "串口转发原始数据",
                        base_offset + offset, base_offset + offset + data_len - 1
                    ))
                    offset += data_len
        else:
            # 抄控器-CCO协议：直接dump
            if payload:
                table.append((
                    "抄控器数据",
                    ' '.join(f'{b:02X}' for b in payload[:30]) + ("..." if len(payload) > 30 else ""),
                    f"{len(payload)}字节", "抄控器-CCO协议数据",
                    base_offset, base_offset + len(payload) - 1
                ))
            offset = len(payload)

        if offset < len(payload):
            remaining = payload[offset:]
            table.append((
                "剩余数据", ' '.join(f'{b:02X}' for b in remaining),
                f"{len(remaining)}字节", "未解析数据",
                base_offset + offset, base_offset + len(payload) - 1
            ))
        return table

    # ── 0x5 广播命令 ──

    def _parse_payload_broadcast(
        self, payload: bytes, service_id: int, direction: int, base_offset: int
    ) -> list:
        """广播命令业务数据单元"""
        table = []
        offset = 0
        table.append((
            "广播业务标识", f"0x{service_id:02X}", str(service_id),
            f"广播命令(0x{service_id:02X})",
            base_offset, base_offset
        ))

        # 广播命令帧头：源地址 6B + 目的地址 6B
        for label in ("广播源地址", "广播目的地址"):
            if offset + 6 > len(payload):
                break
            raw, parsed = self._mac_addr(payload, offset)
            table.append((
                label, raw, parsed, f"{label}: {parsed}",
                base_offset + offset, base_offset + offset + 5
            ))
            offset += 6

        # 后续按命令业务 service_id 复用命令帧解析
        inner_payload = payload[offset:]
        if inner_payload:
            inner_table = self._parse_payload_command(
                inner_payload, service_id, direction, 0x11, base_offset + offset
            )
            if inner_table:
                table.extend(inner_table)
            else:
                table.append((
                    "广播命令数据",
                    ' '.join(f'{b:02X}' for b in inner_payload[:30]) + ("..." if len(inner_payload) > 30 else ""),
                    f"{len(inner_payload)}字节", "广播命令原始数据",
                    base_offset + offset, base_offset + len(payload) - 1
                ))
                offset = len(payload)

        return table

    # ── 0x6 数据订阅路由 ──

    def _parse_payload_data_subscription(
        self, payload: bytes, service_id: int, direction: int, base_offset: int
    ) -> list:
        """数据订阅路由业务数据单元"""
        table = []
        offset = 0
        table.append((
            "订阅业务标识", f"0x{service_id:02X}", str(service_id),
            f"数据订阅路由(0x{service_id:02X})",
            base_offset, base_offset
        ))

        for label in ("源地址", "目的地址"):
            if offset + 6 > len(payload):
                break
            raw, parsed = self._mac_addr(payload, offset)
            table.append((
                label, raw, parsed, f"{label}: {parsed}",
                base_offset + offset, base_offset + offset + 5
            ))
            offset += 6

        if offset < len(payload):
            reserved = payload[offset]
            table.append((
                "保留", f"0x{reserved:02X}", str(reserved), "保留位默认填0",
                base_offset + offset, base_offset + offset
            ))
            offset += 1

        if offset < len(payload):
            mail_addr_len = payload[offset]
            table.append((
                "邮件地址长度", f"0x{mail_addr_len:02X}", str(mail_addr_len),
                f"邮件地址长度: {mail_addr_len}字节",
                base_offset + offset, base_offset + offset
            ))
            offset += 1
            if mail_addr_len > 0 and offset + mail_addr_len <= len(payload):
                mail_bytes = payload[offset:offset + mail_addr_len]
                try:
                    mail_str = mail_bytes.decode('ascii', errors='replace')
                except Exception:
                    mail_str = ' '.join(f'{b:02X}' for b in mail_bytes)
                table.append((
                    "邮件地址",
                    ' '.join(f'{b:02X}' for b in mail_bytes),
                    mail_str,
                    "订阅邮件地址(ASCII)",
                    base_offset + offset, base_offset + offset + mail_addr_len - 1
                ))
                offset += mail_addr_len

        if offset + 2 <= len(payload):
            data_len = self._uint16_le(payload, offset)
            table.append((
                "数据转发长度",
                ' '.join(f'{b:02X}' for b in payload[offset:offset + 2]),
                str(data_len), f"数据长度: {data_len}字节",
                base_offset + offset, base_offset + offset + 1
            ))
            offset += 2
            if data_len > 0 and offset + data_len <= len(payload):
                data_bytes = payload[offset:offset + data_len]
                table.append((
                    "数据转发内容",
                    ' '.join(f'{b:02X}' for b in data_bytes[:30]) + ("..." if data_len > 30 else ""),
                    f"{data_len}字节", "订阅数据原始内容",
                    base_offset + offset, base_offset + offset + data_len - 1
                ))
                offset += data_len

        if offset < len(payload):
            remaining = payload[offset:]
            table.append((
                "剩余数据", ' '.join(f'{b:02X}' for b in remaining),
                f"{len(remaining)}字节", "未解析数据",
                base_offset + offset, base_offset + len(payload) - 1
            ))
        return table


# 兼容性别名
CSGNewGenProtocolParser = CSGNewGenParser
