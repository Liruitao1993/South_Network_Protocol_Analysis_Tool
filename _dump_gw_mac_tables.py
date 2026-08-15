# -*- coding: utf-8 -*-
"""临时脚本：提取国网新一代4-2文档中MAC帧头表格定义"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

d = docx.Document(r'国网新一代协议\双模通信互联互通技术规范 第4-2部分：数据链路层通信协议.docx')
body = d.element.body
items = []
for child in body.iterchildren():
    if child.tag.endswith('}p'):
        items.append(('p', Paragraph(child, d).text))
    elif child.tag.endswith('}tbl'):
        items.append(('tbl', Table(child, d)))


def dump_range(start, end):
    for j in range(start, min(len(items), end)):
        k, o = items[j]
        if k == 'p':
            if o.strip():
                print(j, '[P]', o[:120])
        else:
            print(j, '[TABLE]', len(o.rows), 'rows')
            for r in o.rows:
                cells = [c.text.replace('\n', ' ').strip() for c in r.cells]
                # 去重相邻合并单元格
                dedup = []
                for c in cells:
                    if not dedup or dedup[-1] != c:
                        dedup.append(c)
                print('    |', ' | '.join(dedup))


print('========== SOF/信标/SACK 物理块与载荷格式 ==========')
dump_range(300, 420)
