"""
将南网新一代协议文档 (.docx) 批量转换为 .md
- 按文档原始顺序（段落与表格交织）输出
- 通过 style 的 outlineLvl 判断标题层级
- 支持合并单元格的表格转 markdown
"""
import os
import re
import sys
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn
from collections import defaultdict


# ── styles 缓存：styleId -> outlineLvl ──
def build_style_outline_map(doc):
    """遍历文档 styles，建立 styleId -> outlineLevel 映射"""
    style_map = {}
    for style in doc.styles:
        try:
            xml = style._element.xml
            m = re.search(r'w:outlineLvl w:val="(\d+)"', xml)
            if m:
                style_map[style.style_id] = int(m.group(1))
        except Exception:
            pass
    return style_map


def get_para_outline_level(para, style_outline_map):
    """获取段落的 outline 级别，优先从 style 定义读取"""
    # 1. 段落直接定义的 outlineLvl
    pPr = para._element.find(qn('w:pPr'))
    if pPr is not None:
        ol = pPr.find(qn('w:outlineLvl'))
        if ol is not None:
            return int(ol.get(qn('w:val')))

    # 2. 从 style 定义获取
    pStyle = pPr.find(qn('w:pStyle')) if pPr is not None else None
    if pStyle is not None:
        style_id = pStyle.get(qn('w:val'))
        if style_id in style_outline_map:
            return style_outline_map[style_id]

    return None


def para_to_markdown(para, style_outline_map):
    """将段落转换为 markdown 文本。返回 (text, is_heading)"""
    text = para.text.strip()
    if not text:
        return ("", False)

    outline_lvl = get_para_outline_level(para, style_outline_map)

    if outline_lvl is not None:
        level = min(outline_lvl + 1, 6)
        prefix = '#' * level
        return (f"\n{prefix} {text}\n", True)

    # 普通段落
    return (text + "\n", False)


def table_to_markdown(table):
    """将 docx 表格转为 markdown，处理合并单元格"""
    # 构建网格
    rows = table.rows
    cols_count = len(table.columns)
    grid = [["" for _ in range(cols_count)] for _ in range(len(rows))]

    # 填充网格（处理垂直和水平合并）
    # 使用 cell._tc 获取 gridSpan 和 vMerge
    for r_idx, row in enumerate(rows):
        c_idx = 0
        for cell in row.cells:
            tc = cell._tc
            # gridSpan（水平合并列数）
            grid_span = 1
            gridSpan_elem = tc.find(qn('w:tcPr'))
            if gridSpan_elem is not None:
                gs = gridSpan_elem.find(qn('w:gridSpan'))
                if gs is not None:
                    grid_span = int(gs.get(qn('w:val')))

            # 跳过已被上方垂直合并占用的列
            while c_idx < cols_count and grid[r_idx][c_idx] == "<VMERGE>":
                c_idx += 1

            if c_idx >= cols_count:
                break

            # vMerge（垂直合并）
            vmerge = None
            if gridSpan_elem is not None:
                vm = gridSpan_elem.find(qn('w:vMerge'))
                if vm is not None:
                    vmerge = vm.get(qn('w:val'))  # 'restart' or 'continue' or None(=continue)

            cell_text = cell.text.replace('\n', '<br>').replace('|', '\\|').strip()

            if vmerge == 'continue':
                # 继续合并，不写入内容，标记占位
                for span in range(grid_span):
                    if c_idx + span < cols_count:
                        grid[r_idx][c_idx + span] = "<VMERGE>"
                c_idx += grid_span
                continue

            # 正常单元格或 vmerge='restart'
            for span in range(grid_span):
                if c_idx + span < cols_count:
                    if span == 0:
                        grid[r_idx][c_idx + span] = cell_text
                    else:
                        grid[r_idx][c_idx + span] = "<HSPAN>"
            c_idx += grid_span

    # 清理连续空行
    # 移除全部为空的列
    # 构建 markdown 表格
    if not grid:
        return ""

    # 过滤全空行
    filtered_grid = []
    for row_cells in grid:
        if any(c and c not in ("<VMERGE>", "<HSPAN>") for c in row_cells):
            filtered_grid.append(row_cells)

    if not filtered_grid:
        return ""

    # 合并 <VMERGE> 和 <HSPAN> 为 ""
    clean_grid = []
    for row_cells in filtered_grid:
        clean_grid.append([
            c if c not in ("<VMERGE>", "<HSPAN>") else ""
            for c in row_cells
        ])

    # 生成 markdown
    lines = []
    for i, row_cells in enumerate(clean_grid):
        lines.append('| ' + ' | '.join(row_cells) + ' |')
        if i == 0:
            lines.append('| ' + ' | '.join(['---'] * len(row_cells)) + ' |')

    return '\n'.join(lines)


def convert_docx_to_md(docx_path, md_path):
    """转换单个 docx 文件为 markdown"""
    print(f"转换: {Path(docx_path).name} ...", end=" ", flush=True)
    doc = Document(docx_path)

    style_outline_map = build_style_outline_map(doc)

    # 统计 TOC 相关 style
    toc_styles = set()
    for style in doc.styles:
        try:
            if style.style_id and 'TOC' in style.style_id.upper():
                toc_styles.add(style.style_id)
            name = (style.name or "").lower()
            if 'toc' in name:
                toc_styles.add(style.style_id)
        except Exception:
            pass

    # 按 body 顺序遍历段落和表格
    body = doc.element.body
    md_lines = []
    para_count = 0
    table_count = 0
    prev_was_table = False

    # 用于判断段落是否属于 TOC
    def is_toc_para(p):
        pPr = p.find(qn('w:pPr'))
        if pPr is not None:
            pStyle = pPr.find(qn('w:pStyle'))
            if pStyle is not None:
                sid = pStyle.get(qn('w:val'))
                if sid in toc_styles:
                    return True
        return False

    # 需要跳过 TOC 区域（从第一个 TOC 段落到第一个非 TOC 的非空段落）
    in_toc = False
    toc_ended = False

    for child in body:
        tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag

        if tag == 'p':
            # 段落
            # 通过 style 名检查是否为 TOC
            pPr = child.find(qn('w:pPr'))
            style_id = None
            if pPr is not None:
                pStyle = pPr.find(qn('w:pStyle'))
                if pStyle is not None:
                    style_id = pStyle.get(qn('w:val'))

            if style_id and style_id in toc_styles:
                in_toc = True
                continue

            # 收集文本
            text_parts = []
            for t in child.iter(qn('w:t')):
                if t.text:
                    text_parts.append(t.text)
            text = ''.join(text_parts).strip()

            if not text:
                if not in_toc or toc_ended:
                    md_lines.append("")
                continue

            # 如果之前是 TOC 区域且当前非 TOC 段落非空，TOC 结束
            if in_toc and not toc_ended:
                in_toc = False
                toc_ended = True

            # 判断标题级别
            outline_lvl = None
            if pPr is not None:
                ol = pPr.find(qn('w:outlineLvl'))
                if ol is not None:
                    outline_lvl = int(ol.get(qn('w:val')))
                elif style_id and style_id in style_outline_map:
                    outline_lvl = style_outline_map[style_id]

            if outline_lvl is not None:
                level = min(outline_lvl + 1, 6)
                prefix = '#' * level
                if prev_was_table:
                    md_lines.append("")
                md_lines.append(f"{prefix} {text}")
                md_lines.append("")
                para_count += 1
                prev_was_table = False
            else:
                if prev_was_table:
                    md_lines.append("")
                md_lines.append(text)
                md_lines.append("")
                para_count += 1
                prev_was_table = False

        elif tag == 'tbl':
            if in_toc:
                continue  # 跳过 TOC 中的表格
            table_md = table_to_markdown_from_element(child)
            if table_md:
                md_lines.append("")
                md_lines.append(table_md)
                md_lines.append("")
                table_count += 1
                prev_was_table = True

    # 合并输出
    content = '\n'.join(md_lines)
    # 清理连续4个以上空行
    content = re.sub(r'\n{4,}', '\n\n\n', content)

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(content)

    file_size = os.path.getsize(md_path)
    print(f"→ 段落:{para_count} 表格:{table_count} 大小:{file_size:,}B")
    return para_count, table_count


def table_to_markdown_from_element(tbl_element):
    """从 lxml 元素直接解析表格"""
    nsmap = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

    rows = tbl_element.findall('.//w:tr', nsmap)
    if not rows:
        return ""

    # 获取最大列数（基于 gridCol）
    tblGrid = tbl_element.find('w:tblGrid', nsmap)
    max_cols = 0
    if tblGrid is not None:
        gridCols = tblGrid.findall('w:gridCol', nsmap)
        max_cols = len(gridCols)

    if max_cols == 0:
        # 从第一行计算
        for row in rows:
            cells = row.findall('w:tc', nsmap)
            col_count = 0
            for cell in cells:
                tcPr = cell.find('w:tcPr', nsmap)
                span = 1
                if tcPr is not None:
                    gs = tcPr.find('w:gridSpan', nsmap)
                    if gs is not None:
                        span = int(gs.get(qn('w:val')))
                col_count += span
            max_cols = max(max_cols, col_count)

    # 构建网格
    grid = []
    for row in rows:
        row_data = [""] * max_cols
        cells = row.findall('w:tc', nsmap)
        c_idx = 0
        cell_filled = False
        for cell in cells:
            # 跳过已占用的列
            while c_idx < max_cols and row_data[c_idx] == "<SKIP>":
                c_idx += 1
            if c_idx >= max_cols:
                break

            tcPr = cell.find('w:tcPr', nsmap)
            grid_span = 1
            vmerge = None
            if tcPr is not None:
                gs = tcPr.find('w:gridSpan', nsmap)
                if gs is not None:
                    grid_span = int(gs.get(qn('w:val')))
                vm = tcPr.find('w:vMerge', nsmap)
                if vm is not None:
                    vmerge = vm.get(qn('w:val'))  # 'restart' or None (=continue)

            # 提取文本
            text_parts = []
            for p in cell.findall('.//w:t', nsmap):
                if p.text:
                    text_parts.append(p.text)
            cell_text = ''.join(text_parts).replace('\n', '<br>').replace('|', '\\|').strip()

            if vmerge == 'continue':
                for span in range(grid_span):
                    if c_idx + span < max_cols:
                        row_data[c_idx + span] = "<SKIP>"
                c_idx += grid_span
                continue

            for span in range(grid_span):
                if c_idx + span < max_cols:
                    if span == 0:
                        row_data[c_idx + span] = cell_text
                        cell_filled = True
                    else:
                        row_data[c_idx + span] = ""  # 水平合并的空格
                        cell_filled = True
            c_idx += grid_span

        # 只保留有内容的行
        if cell_filled or any(c and c not in ("<SKIP>", "") for c in row_data):
            grid.append([c if c != "<SKIP>" else "" for c in row_data])

    if not grid:
        return ""

    # 清理全空列
    non_empty_cols = set()
    for row_data in grid:
        for i, c in enumerate(row_data):
            if c:
                non_empty_cols.add(i)

    if not non_empty_cols:
        return ""

    # 保留非空列
    sorted_cols = sorted(non_empty_cols)
    clean_grid = []
    for row_data in grid:
        clean_grid.append([row_data[i] for i in sorted_cols])

    # 生成 markdown
    lines = []
    for i, row_data in enumerate(clean_grid):
        lines.append('| ' + ' | '.join(row_data) + ' |')
        if i == 0:
            lines.append('| ' + ' | '.join(['---'] * len(row_data)) + ' |')

    return '\n'.join(lines)


def main():
    base_dir = Path(r"E:\python\南网解析工具\南网新一代20260226校对\南网新一代20260226校对")
    output_dir = base_dir

    files = sorted([
        f for f in os.listdir(base_dir)
        if f.endswith('.docx') and not f.startswith('~$')
    ])

    if not files:
        print("未找到 docx 文件！")
        return

    print(f"找到 {len(files)} 个 docx 文件\n")

    total_paras = 0
    total_tables = 0

    for f in files:
        docx_path = base_dir / f
        md_name = f.replace('.docx', '.md')
        md_path = output_dir / md_name

        try:
            paras, tables = convert_docx_to_md(str(docx_path), str(md_path))
            total_paras += paras
            total_tables += tables
        except Exception as e:
            print(f"  [错误] {e}")
            import traceback
            traceback.print_exc()

    print(f"\n✅ 转换完成！共 {len(files)} 个文件，{total_paras} 段落，{total_tables} 表格")


if __name__ == '__main__':
    main()
