# -*- coding: utf-8 -*-
"""帧提取工具：从原始文本中提取协议帧"""
import re
from typing import List


def extract_frames_for_protocol(text: str, protocol_index: int) -> List[str]:
    """根据协议提取对应格式的帧（返回 hex 字符串列表）

    优先从原始文本中用正则匹配帧模式（处理日志行），
    失败时再用清洗+长度域解析方式。
    """
    if protocol_index in (0, 6, 7):
        # 南网/国网/DTL645：68开头，16结束
        frames = _extract_68_from_raw(text)
        if not frames:
            clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
            frames = _extract_68_frames(clean)
        return frames
    elif protocol_index == 8:
        # 698.45
        frames = _extract_68_from_raw(text)
        if not frames:
            clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
            frames = _extract_69845_frames(clean)
        return frames
    elif protocol_index == 1:
        # PLC RF协议
        clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
        return _extract_generic_frames(clean, min_len=4, max_len=256)
    elif protocol_index == 2:
        # HDLC/DLMS协议：7E开头
        clean = re.sub(r'[^0-9A-Fa-f]', '', text).upper()
        return _extract_hdlc_frames(clean)
    elif protocol_index in (3, 5):
        # DLMS-APDU裸报文：按行分割
        return [f.strip() for f in text.splitlines() if f.strip()]
    elif protocol_index == 4:
        # DLMS Wrapper裸报文
        return _extract_wrapper_frames(text)
    elif protocol_index == 9:
        # 新一代载波协议
        return _extract_csg_new_gen_frames(text)
    else:
        return [f.strip() for f in text.splitlines() if f.strip()]


def _extract_68_from_raw(text: str) -> List[str]:
    """从原始文本中直接匹配 68...16 帧模式

    处理日志行中嵌入的帧，如:
      2026-07-08 ... data=...681500420101...12B616]
    """
    frames = []
    seen = set()
    for line in text.splitlines():
        # 宽松匹配: 68 + 至少10字符hex + 16
        for m in re.finditer(r'(68[0-9A-Fa-f]{10,}16)', line):
            candidate = m.group(1).upper()
            # 修正奇数长度（末尾可能截断）
            if len(candidate) % 2 != 0:
                candidate = candidate[:-1]
            if len(candidate) < 16:
                continue
            # 验证长度域
            try:
                low = int(candidate[2:4], 16)
                high = int(candidate[4:6], 16)
                length = low | (high << 8)
                frame_bytes = len(candidate) // 2
                if 8 <= length <= 2048 and candidate not in seen:
                    seen.add(candidate)
                    frames.append(candidate)
            except ValueError:
                pass
    return frames


def _extract_68_frames(clean: str) -> List[str]:
    """提取68格式帧（清洗后的字符串）"""
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


def _extract_69845_frames(clean: str) -> List[str]:
    """提取698.45格式帧"""
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


def _extract_hdlc_frames(clean: str) -> List[str]:
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


def _extract_wrapper_frames(text: str) -> List[str]:
    """提取DLMS Wrapper帧"""
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
    return frames if frames else []


def _extract_generic_frames(clean: str, min_len: int = 4, max_len: int = 512) -> List[str]:
    """通用帧提取"""
    if len(clean) >= min_len * 2 and len(clean) <= max_len * 2:
        return [clean] if len(clean) % 2 == 0 else []
    return []


def _extract_csg_new_gen_frames(text: str) -> List[str]:
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
