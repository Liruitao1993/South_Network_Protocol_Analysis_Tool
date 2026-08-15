# -*- coding: utf-8 -*-
"""临时脚本：用 Word COM 将国网新一代协议 .doc 转为 docx（供后续文本提取）"""
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import win32com.client

BASE = os.path.abspath('国网新一代协议')
TARGETS = [
    '双模通信互联互通技术规范 第4-2部分：数据链路层通信协议.doc',
    '第4-1部分：物理层通信协议_智芯合稿_20260108.doc',
]

word = win32com.client.Dispatch('Word.Application')
word.Visible = False
word.DisplayAlerts = 0
try:
    for name in TARGETS:
        src = os.path.join(BASE, name)
        dst = os.path.splitext(src)[0] + '.docx'
        if os.path.exists(dst):
            print('已存在，跳过:', dst)
            continue
        print('转换中:', name)
        doc = word.Documents.Open(src, ReadOnly=True)
        doc.SaveAs2(dst, FileFormat=16)  # wdFormatXMLDocument
        doc.Close(False)
        print('完成:', dst)
finally:
    word.Quit()
print('全部完成')
