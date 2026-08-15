#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convert all GW new gen .docx files to .md"""
import subprocess, sys
result = subprocess.run(
    [sys.executable, 'E:/python/南网解析工具/_convert_gw_new_gen_docs.py'],
    capture_output=True, text=True, encoding='utf-8', errors='replace'
)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)
print("Return code:", result.returncode)
