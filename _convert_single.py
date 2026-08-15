# -*- coding: utf-8 -*-
"""转换单个 .doc -> .docx"""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import win32com.client

BASE = os.path.abspath('国网新一代协议')
name = '第4-1部分：物理层通信协议_智芯合稿_20260108.doc'
src = os.path.join(BASE, name)
dst = os.path.splitext(src)[0] + '.docx'

if os.path.exists(dst):
    print(f'已存在: {dst}')
    sys.exit(0)

print(f'转换: {name}')
word = win32com.client.Dispatch('Word.Application')
word.Visible = False
try:
    doc = word.Documents.Open(src, ReadOnly=True)
    doc.SaveAs2(dst, FileFormat=16)
    doc.Close(False)
    print(f'完成: {os.path.basename(dst)}')
finally:
    word.Quit()
