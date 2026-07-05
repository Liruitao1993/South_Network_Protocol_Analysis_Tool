"""帧对比引擎 — 协议感知的双报文对比分析

核心能力：
  - 字节级对比（按字段对齐，支持长度不同的帧）
  - 字段级语义对比
  - 差异说明（自然语言解读）
  - 选项控制（忽略校验和/序列号、仅显示差异等）
"""

import re
from typing import List, Dict, Any, Optional, Tuple


# 需要忽略的字段名（用于 ignore_checksum / ignore_sequence 选项）
_CHECKSUM_FIELD_NAMES = {"校验和", "校验值", "CS", "Checksum", "FCS", "HCS"}
_SEQUENCE_FIELD_NAMES = {"序列号", "SEQ", "序号", "帧序号"}


def _clean_hex(text: str) -> str:
    """清理 hex 输入，仅保留十六进制字符"""
    return re.sub(r'[^0-9a-fA-F]', '', text)


def _hex_to_bytes(hex_str: str) -> Optional[bytes]:
    """hex 字符串转 bytes，失败返回 None"""
    cleaned = _clean_hex(hex_str)
    if not cleaned or len(cleaned) % 2 != 0:
        return None
    try:
        return bytes.fromhex(cleaned)
    except ValueError:
        return None


def _format_bytes(data: bytes) -> str:
    """字节数组转为空格分隔的大写 hex"""
    return ' '.join(f'{b:02X}' for b in data)


def _format_bytes_html(data: bytes, highlights: Optional[Dict[int, str]] = None) -> str:
    """字节数组转为带高亮的 HTML 格式

    highlights: {字节索引: css_class}，css_class 可为 'mo'(修改)/'ad'(新增)/'de'(删除)
    """
    parts = []
    for i, b in enumerate(data):
        cls = highlights.get(i, '') if highlights else ''
        if cls:
            parts.append(f'<span class="diff-byte {cls}">{b:02X}</span>')
        else:
            parts.append(f'{b:02X}')
    return ' '.join(parts)


class FrameDiffEngine:
    """协议感知的帧对比引擎"""

    def __init__(self, parser=None):
        """
        Args:
            parser: 协议解析器实例，需有 parse_to_table(bytes) -> list 方法
                    返回 [(字段名, 原始值, 解析值, 说明, byte_start, byte_end), ...]
        """
        self.parser = parser

    def set_parser(self, parser):
        """设置/更换解析器"""
        self.parser = parser

    # =========================================================================
    # 核心对比方法
    # =========================================================================

    def compare(
        self,
        hex_a: str,
        hex_b: str,
        field_aware_align: bool = True,
        ignore_checksum: bool = False,
        ignore_sequence: bool = False,
        show_only_diff: bool = False,
    ) -> Dict[str, Any]:
        """执行完整对比，返回结构化结果

        Returns:
            {
                'success': bool,
                'error': str | None,
                'bytes_a': bytes | None,
                'bytes_b': bytes | None,
                'byte_diff': list,          # 字节级对比行
                'field_diff': list,         # 字段级对比行
                'explanation': list[str],   # 差异说明
                'stats': dict,              # 统计信息
            }
        """
        bytes_a = _hex_to_bytes(hex_a)
        bytes_b = _hex_to_bytes(hex_b)

        if bytes_a is None:
            return {'success': False, 'error': '报文 A 不是有效的十六进制数据', 'byte_diff': [], 'field_diff': [], 'explanation': [], 'stats': {}}
        if bytes_b is None:
            return {'success': False, 'error': '报文 B 不是有效的十六进制数据', 'byte_diff': [], 'field_diff': [], 'explanation': [], 'stats': {}}

        if not self.parser:
            return {'success': False, 'error': '未设置协议解析器', 'byte_diff': [], 'field_diff': [], 'explanation': [], 'stats': {}}

        # 解析两帧
        table_a = self._safe_parse(bytes_a)
        table_b = self._safe_parse(bytes_b)

        # 构建字段结构
        fields_a = self._extract_fields(table_a, bytes_a)
        fields_b = self._extract_fields(table_b, bytes_b)

        # 如果任一帧字段提取为空（解析失败），两帧都回退到原始字节对比
        if not fields_a or not fields_b:
            fields_a = self._fallback_raw_fields(bytes_a)
            fields_b = self._fallback_raw_fields(bytes_b)

        # 字节级对比
        byte_diff = self._byte_level_diff(fields_a, fields_b, bytes_a, bytes_b,
                                          ignore_checksum, ignore_sequence, show_only_diff)

        # 字段级语义对比
        field_diff = self._field_level_diff(fields_a, fields_b,
                                            ignore_checksum, ignore_sequence, show_only_diff)

        # 差异说明
        explanation = self._generate_explanation(fields_a, fields_b, byte_diff, field_diff,
                                                 bytes_a, bytes_b, ignore_checksum)

        # 统计
        stats = self._compute_stats(byte_diff, field_diff, bytes_a, bytes_b)

        return {
            'success': True,
            'error': None,
            'bytes_a': bytes_a,
            'bytes_b': bytes_b,
            'byte_diff': byte_diff,
            'field_diff': field_diff,
            'explanation': explanation,
            'stats': stats,
        }

    # =========================================================================
    # 解析辅助
    # =========================================================================

    def _safe_parse(self, data: bytes) -> list:
        """安全调用解析器，返回表格数据"""
        try:
            result = self.parser.parse_to_table(data)
            if isinstance(result, list):
                return result
        except Exception:
            pass
        return []

    def _extract_fields(self, table_data: list, raw_bytes: bytes) -> List[Dict[str, Any]]:
        """从 parse_to_table 输出中提取字段结构

        返回：[{name, offset, length, raw_bytes, display_value, description}, ...]
        """
        fields = []
        for row in table_data:
            if not isinstance(row, (list, tuple)) or len(row) < 6:
                continue
            name, raw_val, parsed_val, desc, byte_start, byte_end = row[:6]
            if byte_start is None or byte_end is None:
                continue
            # 提取该字段的原始字节
            start = min(byte_start, len(raw_bytes))
            end = min(byte_end + 1, len(raw_bytes))  # byte_end 是 inclusive
            if start > end:
                end = start
            field_bytes = raw_bytes[start:end]
            fields.append({
                'name': str(name),
                'offset': byte_start,
                'length': end - start,
                'raw_bytes': field_bytes,
                'raw_hex': _format_bytes(field_bytes),
                'display_value': str(parsed_val) if parsed_val and parsed_val != '-' else raw_val,
                'description': str(desc) if desc else '',
            })
        return fields

    def _fallback_raw_fields(self, raw_bytes: bytes) -> List[Dict[str, Any]]:
        """解析失败时，将每个字节作为独立字段用于对比"""
        fields = []
        for i, b in enumerate(raw_bytes):
            fields.append({
                'name': f'字节{i}',
                'offset': i,
                'length': 1,
                'raw_bytes': bytes([b]),
                'raw_hex': f'{b:02X}',
                'display_value': f'{b:02X}',
                'description': '',
            })
        return fields

    # =========================================================================
    # 字节级对比
    # =========================================================================

    def _byte_level_diff(
        self,
        fields_a: List[Dict],
        fields_b: List[Dict],
        bytes_a: bytes,
        bytes_b: bytes,
        ignore_checksum: bool,
        ignore_sequence: bool,
        show_only_diff: bool,
    ) -> List[Dict[str, Any]]:
        """按字段对齐的字节级对比

        返回：[{field_name, bytes_a_html, bytes_b_html, status, byte_details}, ...]
        byte_details: [{offset, byte_a, byte_b, status}, ...]
        """
        # 构建字段名到字段的映射（用于对齐）
        map_a = {f['name']: f for f in fields_a}
        map_b = {f['name']: f for f in fields_b}

        # 合并所有字段名（保持顺序）
        all_names = []
        seen = set()
        for f in fields_a:
            if f['name'] not in seen:
                all_names.append(f['name'])
                seen.add(f['name'])
        for f in fields_b:
            if f['name'] not in seen:
                all_names.append(f['name'])
                seen.add(f['name'])

        rows = []
        for name in all_names:
            fa = map_a.get(name)
            fb = map_b.get(name)

            # 选项过滤
            if ignore_checksum and name in _CHECKSUM_FIELD_NAMES:
                continue
            if ignore_sequence and name in _SEQUENCE_FIELD_NAMES:
                continue

            byte_details = []
            status = 'same'

            if fa and fb:
                # 两帧都有该字段 — 逐字节比较
                max_len = max(len(fa['raw_bytes']), len(fb['raw_bytes']))
                for i in range(max_len):
                    ba = fa['raw_bytes'][i] if i < len(fa['raw_bytes']) else None
                    bb = fb['raw_bytes'][i] if i < len(fb['raw_bytes']) else None
                    if ba is None:
                        detail_status = 'added'
                        status = 'modified' if status == 'same' else status
                    elif bb is None:
                        detail_status = 'removed'
                        status = 'modified' if status == 'same' else status
                    elif ba != bb:
                        detail_status = 'modified'
                        status = 'modified'
                    else:
                        detail_status = 'same'
                    byte_details.append({
                        'offset': fa['offset'] + i,
                        'byte_a': ba,
                        'byte_b': bb,
                        'status': detail_status,
                    })

            elif fa and not fb:
                # A 独有
                for i, ba in enumerate(fa['raw_bytes']):
                    byte_details.append({
                        'offset': fa['offset'] + i,
                        'byte_a': ba,
                        'byte_b': None,
                        'status': 'removed',
                    })
                status = 'removed'

            elif fb and not fa:
                # B 新增
                for i, bb in enumerate(fb['raw_bytes']):
                    byte_details.append({
                        'offset': fb['offset'] + i,
                        'byte_a': None,
                        'byte_b': bb,
                        'status': 'added',
                    })
                status = 'added'

            if show_only_diff and status == 'same':
                continue

            rows.append({
                'field_name': name,
                'byte_details': byte_details,
                'status': status,
            })

        return rows

    # =========================================================================
    # 字段级语义对比
    # =========================================================================

    def _field_level_diff(
        self,
        fields_a: List[Dict],
        fields_b: List[Dict],
        ignore_checksum: bool,
        ignore_sequence: bool,
        show_only_diff: bool,
    ) -> List[Dict[str, Any]]:
        """字段级语义对比

        返回：[{field_name, offset_a, offset_b, length_a, length_b, value_a, value_b, diff_type}, ...]
        """
        map_a = {f['name']: f for f in fields_a}
        map_b = {f['name']: f for f in fields_b}

        all_names = []
        seen = set()
        for f in fields_a:
            if f['name'] not in seen:
                all_names.append(f['name'])
                seen.add(f['name'])
        for f in fields_b:
            if f['name'] not in seen:
                all_names.append(f['name'])
                seen.add(f['name'])

        rows = []
        for name in all_names:
            fa = map_a.get(name)
            fb = map_b.get(name)

            if ignore_checksum and name in _CHECKSUM_FIELD_NAMES:
                continue
            if ignore_sequence and name in _SEQUENCE_FIELD_NAMES:
                continue

            if fa and fb:
                if fa['raw_bytes'] == fb['raw_bytes']:
                    diff_type = '相同'
                else:
                    diff_type = '修改'
                value_a = fa['display_value']
                value_b = fb['display_value']
                offset_a = fa['offset']
                offset_b = fb['offset']
                length_a = fa['length']
                length_b = fb['length']
            elif fa:
                diff_type = 'A独有'
                value_a = fa['display_value']
                value_b = '-'
                offset_a = fa['offset']
                offset_b = -1
                length_a = fa['length']
                length_b = 0
            else:
                diff_type = 'B新增'
                value_a = '-'
                value_b = fb['display_value']
                offset_a = -1
                offset_b = fb['offset']
                length_a = 0
                length_b = fb['length']

            if show_only_diff and diff_type == '相同':
                continue

            rows.append({
                'field_name': name,
                'offset_a': offset_a,
                'offset_b': offset_b,
                'length_a': length_a,
                'length_b': length_b,
                'value_a': value_a,
                'value_b': value_b,
                'diff_type': diff_type,
                'description_a': fa.get('description', '') if fa else '',
                'description_b': fb.get('description', '') if fb else '',
            })

        return rows

    # =========================================================================
    # 差异说明（人话解读）
    # =========================================================================

    def _generate_explanation(
        self,
        fields_a: List[Dict],
        fields_b: List[Dict],
        byte_diff: list,
        field_diff: list,
        bytes_a: bytes,
        bytes_b: bytes,
        ignore_checksum: bool,
    ) -> List[str]:
        """生成自然语言差异说明"""
        lines = []
        map_a = {f['name']: f for f in fields_a}
        map_b = {f['name']: f for f in fields_b}

        for fd in field_diff:
            name = fd['field_name']
            diff_type = fd['diff_type']

            if diff_type == '相同':
                continue

            if ignore_checksum and name in _CHECKSUM_FIELD_NAMES:
                continue

            fa = map_a.get(name)
            fb = map_b.get(name)

            if diff_type == '修改':
                raw_a = fd['value_a']
                raw_b = fd['value_b']
                desc_a = fd.get('description_a', '')
                desc_b = fd.get('description_b', '')

                # 尝试数值解读
                if fa and fb:
                    try:
                        val_a = int.from_bytes(fa['raw_bytes'], 'little')
                        val_b = int.from_bytes(fb['raw_bytes'], 'little')
                        if val_a != val_b:
                            line = f"{name}：0x{raw_a}({val_a}) → 0x{raw_b}({val_b})"
                            if desc_b:
                                line += f"，{desc_b}"
                            lines.append(line)
                            continue
                    except (ValueError, TypeError):
                        pass

                line = f"{name}：{raw_a} → {raw_b}"
                if desc_b and desc_b != desc_a:
                    line += f"，{desc_b}"
                lines.append(line)

            elif diff_type == 'B新增':
                raw_b = fd['value_b']
                desc_b = fd.get('description_b', '')
                offset = fd['offset_b']
                length = fd['length_b']
                line = f"{name}：B 在偏移 {offset} 处新增 {length} 字节（{raw_b}）"
                if desc_b:
                    line += f"，{desc_b}"
                lines.append(line)

            elif diff_type == 'A独有':
                raw_a = fd['value_a']
                offset = fd['offset_a']
                length = fd['length_a']
                line = f"{name}：A 在偏移 {offset} 处有 {length} 字节（{raw_a}），B 中缺失"
                lines.append(line)

        # 整体长度差异
        if len(bytes_a) != len(bytes_b):
            diff = len(bytes_b) - len(bytes_a)
            if diff > 0:
                lines.insert(0, f"长度差异：B 比 A 多 {diff} 字节（A={len(bytes_a)}字节, B={len(bytes_b)}字节）")
            else:
                lines.insert(0, f"长度差异：B 比 A 少 {-diff} 字节（A={len(bytes_a)}字节, B={len(bytes_b)}字节）")

        if not lines:
            lines.append("两帧完全一致，无差异。")

        return lines

    # =========================================================================
    # 统计
    # =========================================================================

    def _compute_stats(self, byte_diff: list, field_diff: list, bytes_a: bytes, bytes_b: bytes) -> Dict[str, Any]:
        """计算对比统计信息"""
        modified_count = sum(1 for bd in byte_diff if bd['status'] == 'modified')
        added_count = sum(1 for bd in byte_diff if bd['status'] == 'added')
        removed_count = sum(1 for bd in byte_diff if bd['status'] == 'removed')
        same_count = sum(1 for bd in byte_diff if bd['status'] == 'same')

        # 字段级统计
        field_modified = sum(1 for fd in field_diff if fd['diff_type'] == '修改')
        field_added = sum(1 for fd in field_diff if fd['diff_type'] == 'B新增')
        field_removed = sum(1 for fd in field_diff if fd['diff_type'] == 'A独有')
        field_same = sum(1 for fd in field_diff if fd['diff_type'] == '相同')

        return {
            'bytes_a_len': len(bytes_a),
            'bytes_b_len': len(bytes_b),
            'byte_modified_fields': modified_count,
            'byte_added_fields': added_count,
            'byte_removed_fields': removed_count,
            'byte_same_fields': same_count,
            'field_modified': field_modified,
            'field_added': field_added,
            'field_removed': field_removed,
            'field_same': field_same,
        }

    # =========================================================================
    # 导出报告
    # =========================================================================

    def export_report(self, result: Dict[str, Any]) -> str:
        """将对比结果导出为文本报告"""
        lines = []
        lines.append("=" * 60)
        lines.append("报文对比报告")
        lines.append("=" * 60)
        lines.append("")

        stats = result.get('stats', {})
        lines.append(f"报文 A：{stats.get('bytes_a_len', 0)} 字节")
        lines.append(f"报文 B：{stats.get('bytes_b_len', 0)} 字节")
        lines.append(f"修改字段：{stats.get('field_modified', 0)} 处")
        lines.append(f"B 新增字段：{stats.get('field_added', 0)} 处")
        lines.append(f"A 独有字段：{stats.get('field_removed', 0)} 处")
        lines.append("")

        lines.append("--- 字段级对比 ---")
        lines.append(f"{'字段':<16} {'偏移A':>6} {'长度A':>6} {'报文A':<20} {'偏移B':>6} {'长度B':>6} {'报文B':<20} {'差异'}")
        lines.append("-" * 100)
        for fd in result.get('field_diff', []):
            lines.append(
                f"{fd['field_name']:<16} {fd['offset_a']:>6} {fd['length_a']:>6} "
                f"{fd['value_a']:<20} {fd['offset_b']:>6} {fd['length_b']:>6} "
                f"{fd['value_b']:<20} {fd['diff_type']}"
            )
        lines.append("")

        lines.append("--- 差异说明 ---")
        for line in result.get('explanation', []):
            lines.append(f"  - {line}")

        return '\n'.join(lines)
