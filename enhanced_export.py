"""
增强版批量解析导出工具

提供多格式导出（JSON、CSV）、智能文件名生成、验证和错误处理。
Sheet1: 汇总表（帧序号、状态、摘要、原始数据）
Sheet2: 每帧详细解析结果（按帧序号依次排列）
"""

import json
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any


def _detail_of(
    result: dict[str, Any],
    table_data_resolver: Callable[[dict[str, Any]], list] | None = None,
):
    """取一条结果的详情表格数据（返回值 ``None`` = 该帧没有详情）。

    步骤 3（任务 09-15-gui-batch-parse-perf）起 ``batch_results`` 不再常驻
    每帧完整解析表（49,532 帧 = 229 MB），详情改为「按需重解析 + LRU」：

      1. 记录自带 ``_table_data`` → 直接用（兼容旧路径与人工构造的记录）；
      2. 否则交给 ``table_data_resolver``（``main_gui._get_frame_table_data``）；
      3. 都没有 → ``None``。

    用 ``None``／非 ``None`` 区分「有无详情」而不是空列表，是为了保留改动前
    ``"_table_data" in result`` 的判据语义（导出侧据此决定是否写错误信息）。
    解析器返回空列表也表示「无可展示内容」→ 归一为 ``None``。
    """
    if "_table_data" in result:
        return result.get("_table_data") or []
    if table_data_resolver is not None:
        return table_data_resolver(result) or None
    return None


def _sanitize_for_excel(value: Any) -> Any:
    """清洗字符串中的控制字符，使其可安全写入 Excel 单元格

    openpyxl 不允许单元格中包含 ASCII 0x00-0x1F 的控制字符（除 \t \n \r 外）。
    此函数将控制字符替换为可见的 Unicode 替代符。
    """
    if not isinstance(value, str):
        return value
    # 替换控制字符（保留 \t \n \r）
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "□", value)


class ExportCancelled(Exception):
    """用户取消导出（后台线程抛出，由界面转成「已取消」提示）。"""


# ----------------------------------------------------------------------
# Excel 样式常量（**模块级复用**）
# ----------------------------------------------------------------------
# 为什么不用局部 new：62,999 帧 × 每帧约 20 行 × 5 列 ≈ 600 万次单元格写入，
# 若每格各 new 一个 Border/Font，实测建格耗时是复用时的 2.6 倍以上
# （50 万格：3.35 s → 1.26 s），叠加 openpyxl 的样式注册表开销后更明显。
_EXCEL_THIN_BORDER = None
_EXCEL_HEADER_FONT = None
_EXCEL_HEADER_FILL = None
_EXCEL_HEADER_FONT_WHITE = None
_EXCEL_OK_FONT = None
_EXCEL_FAIL_FONT = None
_EXCEL_CENTER_ALIGN = None
_EXCEL_LEFT_ALIGN = None
_EXCEL_FRAME_HEADER_FILL = None
_EXCEL_FRAME_HEADER_FONT = None
_EXCEL_FIELD_HEADER_FILL = None
_EXCEL_FIELD_HEADER_FONT = None


def _init_excel_styles():
    """延迟初始化样式常量（openpyxl 是可选依赖，不能在 import 期强制加载）。"""
    global _EXCEL_THIN_BORDER, _EXCEL_HEADER_FONT, _EXCEL_HEADER_FILL
    global _EXCEL_HEADER_FONT_WHITE, _EXCEL_OK_FONT, _EXCEL_FAIL_FONT
    global _EXCEL_CENTER_ALIGN, _EXCEL_LEFT_ALIGN
    global _EXCEL_FRAME_HEADER_FILL, _EXCEL_FRAME_HEADER_FONT
    global _EXCEL_FIELD_HEADER_FILL, _EXCEL_FIELD_HEADER_FONT
    if _EXCEL_THIN_BORDER is not None:
        return
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    _EXCEL_THIN_BORDER = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )
    _EXCEL_HEADER_FONT = Font(bold=True, size=11)
    _EXCEL_HEADER_FILL = PatternFill(
        start_color="4472C4", end_color="4472C4", fill_type="solid"
    )
    _EXCEL_HEADER_FONT_WHITE = Font(bold=True, size=11, color="FFFFFF")
    _EXCEL_OK_FONT = Font(color="008000")
    _EXCEL_FAIL_FONT = Font(color="FF0000")
    _EXCEL_CENTER_ALIGN = Alignment(horizontal="center")
    _EXCEL_LEFT_ALIGN = Alignment(horizontal="left")
    _EXCEL_FRAME_HEADER_FILL = PatternFill(
        start_color="70AD47", end_color="70AD47", fill_type="solid"
    )
    _EXCEL_FRAME_HEADER_FONT = Font(bold=True, size=11, color="FFFFFF")
    _EXCEL_FIELD_HEADER_FILL = PatternFill(
        start_color="D9E2F3", end_color="D9E2F3", fill_type="solid"
    )
    _EXCEL_FIELD_HEADER_FONT = Font(bold=True, size=10)


class EnhancedBatchResultExporter:
    """
    增强版批量解析结果导出器。

    功能:
    - JSON 格式导出（完整数据 + 元数据）
    - CSV 格式导出（Sheet1 汇总 + Sheet2 详细解析，需安装 pandas + openpyxl）
    - 智能文件名（协议名称 + 时间戳）
    - 验证和错误处理
    """

    def __init__(self, export_dir: str = "."):
        """初始化导出器。"""
        self.export_dir = Path(export_dir)
        self.export_dir.mkdir(exist_ok=True)

    def export_to_json(
        self,
        batch_results: list[dict[str, Any]],
        protocol_name: str = "unknown",
        output_file: str | None = None,
        table_data_resolver: Callable[[dict[str, Any]], list] | None = None,
        progress_cb: Callable[[int, int, str], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> str:
        """
        导出到 JSON 格式。

        Args:
            batch_results: 批量解析结果列表
            protocol_name: 协议名称
            output_file: 输出文件路径
            table_data_resolver: 详情按需解析器（结果 dict → 详情表）；
                None 时只读记录自带的 ``_table_data``（向后兼容）

        Returns:
            保存的 JSON 文件路径
        """
        timestamp = datetime.now()
        if output_file:
            file_path = Path(output_file)
            file_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
            filename = f"batch_parse_{protocol_name}_{timestamp_str}.json"
            file_path = self.export_dir / filename

        export_data = {
            "metadata": {
                "export_time": timestamp.isoformat(),
                "protocol": protocol_name,
                "total_frames": len(batch_results),
                "version": "enhanced_batch_export_v1.0",
            },
            "results": [],
        }

        for i, result in enumerate(batch_results):
            if should_cancel is not None and i % 200 == 0 and should_cancel():
                raise ExportCancelled("导出已取消")
            if progress_cb is not None and i % 200 == 0 and batch_results:
                try:
                    # 与 Excel 同一刻度口径（全局百分比，总刻度 100）
                    progress_cb(
                        int((i + 1) * 95 / len(batch_results)),
                        100,
                        f"汇总数据 {i + 1}/{len(batch_results)}",
                    )
                except Exception:  # noqa: BLE001
                    pass
            table_data = _detail_of(result, table_data_resolver)
            export_result = {
                "帧编号": i + 1,
                "状态": result.get("_status", result.get("状态", "")),
                "摘要": result.get("摘要", result.get("summary", "")),
                "原始数据": result.get("_input", result.get("原始数据", "")),
                # 取值与改动前一致（`_table_data` 在则「是」）；去缓存后改读 _has_detail，
                # 失败帧的 ❌ 行同样算有表格数据 → 「是」（不得整列变「否」）
                "包含表格数据": "是" if table_data is not None else "否",
            }

            if table_data is None and "错误" in result:
                export_result["错误信息"] = result["错误"]

            export_data["results"].append(export_result)

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            # 不吞错：补上失败路径与原因（调用方已有 try/except 会弹「导出失败」）
            raise OSError(f"写入导出文件失败：{file_path}（{e}）") from e

        return str(file_path)

    def export_to_csv(
        self,
        batch_results: list[dict[str, Any]],
        protocol_name: str = "unknown",
        table_data_resolver: Callable[[dict[str, Any]], list] | None = None,
    ) -> str:
        """
        导出到 CSV 格式（仅汇总表）。

        Args:
            batch_results: 批量解析结果列表
            protocol_name: 协议名称
            table_data_resolver: 详情按需解析器（结果 dict → 详情表）

        Returns:
            保存的 CSV 文件路径

        Raises:
            ImportError: 如果 pandas 未安装
        """
        import pandas as pd

        timestamp = datetime.now()
        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
        filename = f"batch_parse_{protocol_name}_{timestamp_str}.csv"
        file_path = self.export_dir / filename

        csv_data = []
        for i, result in enumerate(batch_results):
            row = {
                "帧索引": i + 1,
                "状态": result.get("_status", result.get("状态", "")),
                "摘要": result.get("摘要", result.get("summary", "")),
                "原始数据": result.get("_input", result.get("原始数据", "")),
                "错误信息": result.get("错误", ""),
                "包含表格数据": (
                    "是"
                    if _detail_of(result, table_data_resolver) is not None
                    else "否"
                ),
            }
            csv_data.append(row)

        df = pd.DataFrame(csv_data)
        df.to_csv(file_path, index=False, encoding="utf-8")

        return str(file_path)

    def export_to_excel(
        self,
        batch_results: list[dict[str, Any]],
        protocol_name: str = "unknown",
        output_file: str | None = None,
        table_data_resolver: Callable[[dict[str, Any]], list] | None = None,
        progress_cb: Callable[[int, int, str], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
        raw_log_text: str | None = None,
    ) -> str:
        """
        导出到 Excel 格式（Sheet1 汇总 + Sheet2 每帧详细解析 + 可选 Sheet3 原始日志）。

        Sheet1: 汇总表（帧序号、状态、摘要、原始数据、错误信息、包含详细数据）
        Sheet2: 详细解析（按帧序号依次排列，每帧的所有解析字段）
        Sheet3: 原始日志（用户粘贴的原文逐行落地，**不做任何过滤/截断**）

        **Sheet3 的意义（用户口径 2026-11-19：可以分段导出，但不能损失原始信息）**：
        汇总/详情只覆盖「被识别成帧」的行；现场日志里其余行（流程日志、测试标记、
        主动上报等）同样是排查依据，因此把原始输入全文原样写出一份，导出的文件
        自身就是完整证据，不依赖用户另外保存日志。

        **性能（2026-11-18 用户报障后重做）**：现场 62,999 帧（21,712 帧带详情）
        点「导出 Excel」后程序未响应。原实现用普通 Workbook 逐格 ``ws.cell()`` +
        逐格设样式 + 逐帧两次 ``merge_cells``，实测 21,712 帧要 **875 秒**
        （规模翻倍，耗时涨 4 倍以上，openpyxl 的样式去重缓存是超线性来源）。
        现改为 **write_only 模式 + 行式 append**：同样量级实测 **32.7 秒**
        （约 27 倍加速），且规模增长基本线性。为了不牺牲可读性：
        - 帧标题行保留填充色（绿色）+ 表头行保留填充色；
        - 数据行**不再逐格加边框**（百万级单元格下边框是主要开销之一，
          而无边框在 Excel 里同样可读）；
        - 仅帧标题行做横向合并（原实现每帧两次 merge，现一次）。

        Args:
            batch_results: 批量解析结果列表
            protocol_name: 协议名称
            output_file: 输出文件路径
            table_data_resolver: 详情按需解析器（结果 dict → 详情表）；
                None 时只读记录自带的 ``_table_data``（向后兼容）
            progress_cb: 进度回调 ``(pct, 100, 阶段说明)``；刻度统一为全局
                百分比（Sheet1 0~20 / Sheet2 20~95 / 写盘 96~100），保证界面
                进度条单调、不会回跳
            should_cancel: 取消判据，每 200 帧检查一次；为真则抛 `ExportCancelled`

        Returns:
            保存的 Excel 文件路径

        Raises:
            ImportError: 如果 pandas 或 openpyxl 未安装
            ExportCancelled: 用户取消（已写出的临时文件由调用方处理）
        """
        from openpyxl import Workbook
        from openpyxl.cell import WriteOnlyCell
        from openpyxl.utils import get_column_letter

        # 样式常量（模块级复用，见 `_init_excel_styles` 的说明）
        _init_excel_styles()

        if output_file:
            file_path = Path(output_file)
            file_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            timestamp = datetime.now()
            timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")
            filename = f"batch_parse_{protocol_name}_{timestamp_str}.xlsx"
            file_path = self.export_dir / filename

        total = len(batch_results)

        # 进度刻度：Sheet1 占 0~20%，Sheet2 占 20~95%，写文件 96~100。
        # 用**全局单调**百分比而不是各阶段各自的 done/total —— 否则界面进度条
        # 会在「汇总表 100%」后掉回「详细解析 0%」，看起来像重新开始（实测出现）。
        SHEET1_END = 20
        SHEET2_END = 95

        def _progress(pct: int, phase: str = ""):
            """进度回调（pct 为全局百分比，总刻度固定 100）。异常一律吞掉——
            界面进度条不能影响导出本身。"""
            if progress_cb is None:
                return
            try:
                progress_cb(int(pct), 100, phase)
            except Exception:  # noqa: BLE001
                pass

        # write_only：行式写入，不在内存里攒样式树（27 倍提速的关键）。
        # 注意 writer 持有临时文件句柄，**任何中途退出**都必须 close()，
        # 否则进程退出时 openpyxl 在 atexit 里删不掉临时文件并刷一堆
        # PermissionError / LxmlSyntaxError（取消路径实测会遇到）。
        wb = Workbook(write_only=True)

        def _check_cancel(done: int):
            """每 200 帧查一次取消，避免每帧回调开销。

            取消时必须**让 writer 正常收尾**再删文件：write_only 模式的
            `wb.close()` 不会结束 lxml 的增量写上下文，直接抛异常走人会在
            进程退出时刷一串 `PermissionError` / `LxmlSyntaxError`（实测）。
            这里先 save 出一个临时文件（代价 = 写一次盘），再删掉它。
            """
            if should_cancel is not None and done % 200 == 0 and should_cancel():
                try:
                    wb.save(file_path)
                except Exception:  # noqa: BLE001
                    pass
                try:
                    if file_path.exists():
                        file_path.unlink()
                except Exception:  # noqa: BLE001
                    pass
                raise ExportCancelled("导出已取消")

        header_fill = _EXCEL_HEADER_FILL
        header_font_white = _EXCEL_HEADER_FONT_WHITE
        ok_font = _EXCEL_OK_FONT
        fail_font = _EXCEL_FAIL_FONT

        # ========== Sheet1: 汇总表 ==========
        ws_summary = wb.create_sheet("汇总表")

        summary_headers = [
            "帧序号",
            "状态",
            "摘要",
            "原始数据",
            "错误信息",
            "包含详细数据",
        ]
        head_cells = []
        for header in summary_headers:
            cell = WriteOnlyCell(ws_summary, value=header)
            cell.font = header_font_white
            cell.fill = header_fill
            head_cells.append(cell)
        ws_summary.append(head_cells)

        # 判据口径不变：`_has_detail` 由解析阶段锁存（"该帧能否产出非空详情表"），
        # 与旧实现「调一次 resolver 看是否非 None」结果一致，但**不重复重解析**
        # （旧实现在这里对每帧又跑了一次详情解析，62,999 帧等于解析两遍）。
        for i, result in enumerate(batch_results):
            status = _sanitize_for_excel(result.get("_status", result.get("状态", "")))
            status_cell = WriteOnlyCell(ws_summary, value=status)
            if status == "成功":
                status_cell.font = ok_font
            elif status in ("失败", "异常"):
                status_cell.font = fail_font
            ws_summary.append([
                i + 1,
                status_cell,
                _sanitize_for_excel(result.get("摘要", result.get("summary", ""))),
                _sanitize_for_excel(result.get("_input", result.get("原始数据", ""))),
                _sanitize_for_excel(result.get("错误", "")),
                "是" if result.get("_has_detail") else "否",
            ])

            _check_cancel(i + 1)
            if i % 200 == 0 and total:
                _progress(
                    int((i + 1) * SHEET1_END / total),
                    f"汇总表 {i + 1}/{total}",
                )

        summary_col_widths = [10, 10, 40, 50, 30, 12]
        for i, width in enumerate(summary_col_widths, 1):
            ws_summary.column_dimensions[get_column_letter(i)].width = width

        # ========== Sheet2: 详细解析 ==========
        ws_detail = wb.create_sheet("详细解析")

        frame_header_fill = _EXCEL_FRAME_HEADER_FILL
        frame_header_font = _EXCEL_FRAME_HEADER_FONT
        field_header_fill = _EXCEL_FIELD_HEADER_FILL
        field_header_font = _EXCEL_FIELD_HEADER_FONT

        field_headers = ["字段", "原始值", "解析值", "说明", "字节偏移"]

        for i, result in enumerate(batch_results):
            frame_num = i + 1
            # 详情按需（逐条取用、用完即弃，不物化整批详情）
            table_data = _detail_of(result, table_data_resolver) or []

            # 帧标题行（整行填充；write_only 模式不支持 merge_cells，
            # 标题文字本身已自带「第 N 帧 | 状态 | 摘要」，可读性不受影响）
            status = _sanitize_for_excel(result.get("_status", result.get("状态", "")))
            summary = _sanitize_for_excel(result.get("摘要", result.get("summary", "")))
            title_cell = WriteOnlyCell(
                ws_detail, value=f"第 {frame_num} 帧  |  状态: {status}  |  {summary}"
            )
            title_cell.font = frame_header_font
            title_cell.fill = frame_header_fill
            ws_detail.append([title_cell])

            # 原始数据行
            raw_data = _sanitize_for_excel(
                result.get("_input", result.get("原始数据", ""))
            )
            if raw_data:
                ws_detail.append([f"原始报文: {raw_data}"])

            # 字段表头
            field_head_cells = []
            for header in field_headers:
                cell = WriteOnlyCell(ws_detail, value=header)
                cell.font = field_header_font
                cell.fill = field_header_fill
                field_head_cells.append(cell)
            ws_detail.append(field_head_cells)

            # 字段数据（一条 append 写一整行；不再逐格 set border —— 百万格下
            # 逐格设样式是超线性开销的主要来源，见方法 docstring）
            if table_data:
                for item in table_data:
                    # item 格式: (字段名, 原始值, 解析值, 说明, byte_start, byte_end)
                    byte_offset = ""
                    if len(item) > 5 and item[4] is not None and item[5] is not None:
                        byte_offset = f"{item[4]}-{item[5]}"
                    ws_detail.append([
                        _sanitize_for_excel(str(item[0]) if len(item) > 0 else ""),
                        _sanitize_for_excel(str(item[1]) if len(item) > 1 else ""),
                        _sanitize_for_excel(str(item[2]) if len(item) > 2 else ""),
                        _sanitize_for_excel(str(item[3]) if len(item) > 3 else ""),
                        byte_offset,
                    ])
            else:
                # 无详细数据时显示错误信息
                error_msg = _sanitize_for_excel(result.get("错误", "无详细解析数据"))
                ws_detail.append([f"错误: {error_msg}"])

            # 帧间分隔行
            ws_detail.append([])

            _check_cancel(frame_num)
            if frame_num % 200 == 0 and total:
                _progress(
                    SHEET1_END
                    + int((SHEET2_END - SHEET1_END) * frame_num / total),
                    f"详细解析 {frame_num}/{total}",
                )

        # 调整详细解析列宽
        detail_col_widths = [30, 20, 30, 40, 12]
        for i, width in enumerate(detail_col_widths, 1):
            ws_detail.column_dimensions[get_column_letter(i)].width = width

        # ========== Sheet3: 原始日志（可选，全文原样落地）==========
        # 用户口径 2026-11-19：「可以分段导出，但不能损失我的原始信息，我要分析日志和问题」。
        # 汇总/详情只覆盖「被识别成帧」的行，日志里其余行同样是排查依据
        # （现场 62,999 非空行里只有 21,712 个报文帧），故把原文逐行写全。
        if raw_log_text:
            ws_log = wb.create_sheet("原始日志")
            log_lines = raw_log_text.splitlines()
            log_total = len(log_lines)
            head_num = WriteOnlyCell(ws_log, value="行号")
            head_num.font = header_font_white
            head_num.fill = header_fill
            head_txt = WriteOnlyCell(
                ws_log, value="原始日志内容（未做任何过滤/截断）"
            )
            head_txt.font = header_font_white
            head_txt.fill = header_fill
            ws_log.append([head_num, head_txt])
            for i, line in enumerate(log_lines, 1):
                ws_log.append([i, line])
                if i % 5000 == 0:
                    _progress(
                        SHEET2_END + int(2 * i / max(log_total, 1)),
                        f"原始日志 {i}/{log_total}",
                    )
                    if should_cancel is not None and should_cancel():
                        raise ExportCancelled("导出已取消")
            ws_log.column_dimensions[get_column_letter(1)].width = 8
            ws_log.column_dimensions[get_column_letter(2)].width = 140

        # 保存文件（write_only 下这步才真正落盘，大文件仍要数秒；单独报阶段）
        _progress(96, "正在写入文件…")
        if should_cancel is not None and should_cancel():
            raise ExportCancelled("导出已取消")
        wb.save(file_path)
        _progress(100, "完成")

        return str(file_path)

    def validate_export_data(self, batch_results: list[dict[str, Any]]) -> list[str]:
        """验证导出数据。"""
        errors = []

        if not batch_results:
            errors.append("批量解析结果为空")
            return errors

        for i, result in enumerate(batch_results):
            if not isinstance(result, dict):
                errors.append(f"第 {i + 1} 帧结果不是字典类型")
            elif not result:
                errors.append(f"第 {i + 1} 帧结果为空")

        return errors


# 示例用法
if __name__ == "__main__":
    print("=== 增强版批量解析导出工具测试 ===\n")

    sample_results = [
        {
            "_input": "68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16",
            "_status": "成功",
            "摘要": "主站复位请求",
            "_table_data": [
                ["  协议控制信息", "68", "帧起始符", "固定值0x68", 0, 0],
                ["  长度域", "0E", "14字节", "用户数据长度", 1, 1],
                ["  控制域", "00 00 00 00", "主站→模块", "下行帧", 2, 5],
                ["  地址域", "01 00 01 E8", "地址: 0x010001E8", "集中器地址", 6, 9],
                ["  功能码", "00 05", "复位命令", "主站复位", 10, 11],
                ["  校验码", "EF", "校验和", "算术和校验", 12, 12],
                ["  结束符", "16", "帧结束符", "固定值0x16", 13, 13],
            ],
        },
        {
            "_input": "68 0E 00 00 00 00 01 02 01 28 00 03 01 20 00",
            "_status": "失败",
            "摘要": "查询数据失败",
            "错误": "CRC校验错误",
        },
        {
            "_input": "68 10 00 00 00 00 01 04 01 00 00 01 00 00 00 00 1A 16",
            "_status": "成功",
            "摘要": "读取数据响应",
            "_table_data": [
                ["  协议控制信息", "68", "帧起始符", "固定值0x68", 0, 0],
                ["  长度域", "10", "16字节", "用户数据长度", 1, 1],
                ["  控制域", "00 00 00 00", "模块→主站", "上行帧", 2, 5],
                ["  地址域", "01 04 01 00", "地址: 0x01040100", "模块地址", 6, 9],
                ["  数据标识", "00 00 00 00", "无数据", "空数据", 10, 13],
                ["  校验码", "1A", "校验和", "算术和校验", 14, 14],
                ["  结束符", "16", "帧结束符", "固定值0x16", 15, 15],
            ],
        },
    ]

    exporter = EnhancedBatchResultExporter()

    # 验证
    errors = exporter.validate_export_data(sample_results)
    if errors:
        print(f"验证错误: {errors}")
    else:
        print("✓ 数据验证通过")

    # JSON 导出
    json_path = exporter.export_to_json(sample_results, "南网协议")
    print(f"✓ JSON 导出: {json_path}")

    # Excel 导出（Sheet1 汇总 + Sheet2 详细）
    try:
        excel_path = exporter.export_to_excel(sample_results, "南网协议")
        print(f"✓ Excel 导出: {excel_path}")
        print(f"  - Sheet1: 汇总表（{len(sample_results)} 帧）")
        print("  - Sheet2: 详细解析（每帧按字段逐行展开）")
    except ImportError as e:
        print(f"✗ Excel 导出失败: {e}")

    # CSV 导出
    try:
        csv_path = exporter.export_to_csv(sample_results, "南网协议")
        print(f"✓ CSV 导出: {csv_path}")
    except ImportError as e:
        print(f"✗ CSV 导出失败: {e}")

    print("\n✓ 测试完成")
