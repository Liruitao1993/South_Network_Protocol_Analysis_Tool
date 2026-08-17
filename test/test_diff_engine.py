"""报文对比功能完整验证"""

import _path_setup  # noqa: E402

import sys
sys.stdout.reconfigure(encoding='utf-8')

from frame_diff_engine import FrameDiffEngine
from diff_widget import DiffWidget
from protocol_parser import ProtocolFrameParser

parser = ProtocolFrameParser()
engine = FrameDiffEngine(parser)

# 测试1: 两帧都解析成功
hex_a = '68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16'
hex_b = '68 0E 00 00 E9 00 00 01 00 01 00 0A F5 16'
r1 = engine.compare(hex_a, hex_b)
assert r1['success'], 'Test1 failed: ' + str(r1.get('error'))
assert r1['stats']['bytes_a_len'] == 14
assert r1['stats']['bytes_b_len'] == 14
assert r1['stats']['field_modified'] >= 2
print('Test1 PASS: 两帧解析成功，字段对齐对比正常')

# 测试2: 忽略校验和
r2 = engine.compare(hex_a, hex_b, ignore_checksum=True)
assert r2['success']
cs_fields = [f for f in r2['field_diff'] if '校验' in f['field_name']]
assert len(cs_fields) == 0, '校验和未被忽略'
print('Test2 PASS: ignore_checksum 选项正常')

# 测试3: 仅显示差异
r3 = engine.compare(hex_a, hex_b, show_only_diff=True)
assert r3['success']
same_fields = [f for f in r3['field_diff'] if f['diff_type'] == '相同']
assert len(same_fields) == 0, '相同字段未过滤'
print('Test3 PASS: show_only_diff 选项正常')

# 测试4: 解析失败回退
hex_bad = '68 14 00 14 00 4D 01 01 E8 03 03 74 00 00 02 00 7B 16'
r4 = engine.compare(hex_a, hex_bad)
assert r4['success']
assert r4['stats']['bytes_a_len'] == 14
assert r4['stats']['bytes_b_len'] == 18
print('Test4 PASS: 解析失败回退到字节对比正常')

# 测试5: 导出报告
report = engine.export_report(r1)
assert '报文对比报告' in report
assert '字段级对比' in report
assert '差异说明' in report
print('Test5 PASS: 导出报告正常')

# 测试6: DiffWidget 可实例化
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)
widget = DiffWidget()
assert widget is not None
widget.set_protocol(0)
widget.set_parser(parser)
widget.load_frame_a(hex_a)
widget.load_frame_b(hex_b)
print('Test6 PASS: DiffWidget 实例化和接口正常')

# 测试7: main_gui 可导入（验证集成无循环依赖）
import main_gui
assert hasattr(main_gui, 'DiffWidget')
assert hasattr(main_gui, 'APP_VERSION')
print('Test7 PASS: main_gui 导入正常，DiffWidget 已集成')

print()
print('All 7 tests PASSED')
"""验证帧对比引擎"""

from protocol_parser import ProtocolFrameParser
from frame_diff_engine import FrameDiffEngine

parser = ProtocolFrameParser()
engine = FrameDiffEngine(parser)

hex_a = '68 14 00 14 00 4D 01 01 E8 03 03 74 00 00 02 00 7B 16'
hex_b = '68 16 00 16 00 8D 01 01 E8 03 03 74 00 00 02 00 9A 8C 16'

result = engine.compare(hex_a, hex_b)
print('Success:', result['success'])
if result.get('error'):
    print('Error:', result['error'])
print()
print('Stats:', result['stats'])
print()
print('Field diff:')
for fd in result['field_diff']:
    print(f"  {fd['field_name']:10s} | {fd['diff_type']:6s} | A={fd['value_a']:20s} | B={fd['value_b']}")
print()
print('Explanation:')
for line in result['explanation']:
    print(f"  - {line}")
print()

# 测试忽略校验和
result2 = engine.compare(hex_a, hex_b, ignore_checksum=True)
print('With ignore_checksum=True:')
for fd in result2['field_diff']:
    if fd['diff_type'] != '相同':
        print(f"  {fd['field_name']:10s} | {fd['diff_type']}")

print()
# 测试仅显示差异
result3 = engine.compare(hex_a, hex_b, show_only_diff=True)
print('With show_only_diff=True:')
for fd in result3['field_diff']:
    print(f"  {fd['field_name']:10s} | {fd['diff_type']}")

print()
print('Export report:')
print(engine.export_report(result))
