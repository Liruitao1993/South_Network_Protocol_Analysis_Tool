# -*- coding: utf-8 -*-
"""转换单个 .doc -> .docx（逐个启动 Word 实例避免 RPC 崩溃）"""
import os, sys, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import win32com.client

BASE = os.path.abspath('国网新一代协议')

# List all .doc files and check which need conversion
for f in sorted(os.listdir(BASE)):
    if not f.endswith('.doc') or f.endswith('.docx'):
        continue
    docx_path = os.path.join(BASE, f.replace('.doc', '.docx'))
    if os.path.exists(docx_path):
        print(f'跳过（已有docx）: {f}')
        continue
    
    print(f'转换: {f}')
    word = win32com.client.Dispatch('Word.Application')
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        doc = word.Documents.Open(os.path.join(BASE, f), ReadOnly=True)
        doc.SaveAs2(docx_path, FileFormat=16)
        doc.Close(False)
        print(f'  完成: {os.path.basename(docx_path)}')
    except Exception as e:
        print(f'  错误: {e}')
    finally:
        try:
            word.Quit()
        except:
            pass
    time.sleep(2)  # Wait between instances

print('\n全部完成')
