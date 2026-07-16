# -*- coding: utf-8 -*-
"""字节高亮工具：生成带高亮标记的十六进制字符串"""
from typing import List, Tuple, Optional


class ByteHighlighter:
    """生成带 HTML 高亮标记的十六进制显示字符串"""
    
    @staticmethod
    def highlight_bytes(
        frame_bytes: bytes,
        highlight_ranges: List[Tuple[int, int]],
        bytes_per_line: int = 16,
        show_ascii: bool = True,
        show_offset: bool = True,
    ) -> str:
        """生成带高亮的十六进制字符串 (HTML)
        
        Args:
            frame_bytes: 原始帧字节
            highlight_ranges: 高亮范围列表 [(start, end), ...] 闭区间
            bytes_per_line: 每行字节数
            show_ascii: 是否显示 ASCII
            show_offset: 是否显示偏移地址
        """
        if not frame_bytes:
            return "<span style='color:#999'>(空数据)</span>"
        
        # 合并重叠范围
        merged = ByteHighlighter._merge_ranges(highlight_ranges)
        
        lines = []
        for i in range(0, len(frame_bytes), bytes_per_line):
            chunk = frame_bytes[i:i + bytes_per_line]
            line_parts = []
            
            if show_offset:
                line_parts.append(f"<span style='color:#666;font-family:monospace'>{i:04X}: </span>")
            
            # 十六进制部分
            hex_parts = []
            for j, b in enumerate(chunk):
                offset = i + j
                is_highlighted = any(start <= offset <= end for start, end in merged)
                cls = "byte-highlight" if is_highlighted else ""
                hex_parts.append(f"<span class='{cls}' style='font-family:monospace'>{b:02X}</span>")
            
            line_parts.append(" ".join(hex_parts))
            
            # ASCII 部分
            if show_ascii:
                ascii_parts = []
                for j, b in enumerate(chunk):
                    offset = i + j
                    is_highlighted = any(start <= offset <= end for start, end in merged)
                    cls = "byte-highlight" if is_highlighted else ""
                    char = chr(b) if 32 <= b <= 126 else "."
                    ascii_parts.append(f"<span class='{cls}' style='font-family:monospace'>{char}</span>")
                line_parts.append("  <span style='color:#666'>|</span>  " + "".join(ascii_parts))
            
            lines.append("".join(line_parts))
        
        return "<br>".join(lines)
    
    @staticmethod
    def _merge_ranges(ranges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        if not ranges:
            return []
        sorted_ranges = sorted(ranges, key=lambda x: x[0])
        merged = [sorted_ranges[0]]
        for start, end in sorted_ranges[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end + 1:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        return merged
    
    @staticmethod
    def diff_highlight(
        bytes_a: bytes,
        bytes_b: bytes,
        bytes_per_line: int = 16,
    ) -> Tuple[str, str]:
        """生成两帧对比高亮 HTML (A基准, B对比)
        
        Returns:
            (html_a, html_b) - 两个高亮后的 HTML 字符串
        """
        max_len = max(len(bytes_a), len(bytes_b))
        lines_a = []
        lines_b = []
        
        for i in range(0, max_len, bytes_per_line):
            chunk_a = bytes_a[i:i + bytes_per_line]
            chunk_b = bytes_b[i:i + bytes_per_line]
            
            # 十六进制行
            hex_a = []
            hex_b = []
            for j in range(bytes_per_line):
                offset = i + j
                a_val = chunk_a[j] if j < len(chunk_a) else None
                b_val = chunk_b[j] if j < len(chunk_b) else None
                
                if a_val is not None and b_val is not None:
                    if a_val == b_val:
                        cls = ""
                    else:
                        cls = "byte-highlight-modified"
                elif a_val is None:
                    cls = "byte-highlight-added"
                else:
                    cls = "byte-highlight-deleted"
                
                a_str = f"{a_val:02X}" if a_val is not None else "  "
                b_str = f"{b_val:02X}" if b_val is not None else "  "
                hex_a.append(f"<span class='{cls}' style='font-family:monospace'>{a_str}</span>")
                hex_b.append(f"<span class='{cls}' style='font-family:monospace'>{b_str}</span>")
            
            lines_a.append(f"<span style='color:#666;font-family:monospace'>{i:04X}: </span>" + " ".join(hex_a))
            lines_b.append(f"<span style='color:#666;font-family:monospace'>{i:04X}: </span>" + " ".join(hex_b))
        
        return "<br>".join(lines_a), "<br>".join(lines_b)
