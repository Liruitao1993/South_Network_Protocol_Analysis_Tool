# PRD: 协议8 GET-Response 解析失败修复 + 版本信息深度解析

## 背景

用户实测帧（GUI 协议8）：
`68 47 00 C3 05 09 00 00 00 00 00 00 DC 40 85 01 01 43 00 03 00 01 02 06 ...`

当前 GUI 输出：`APDU类型 GET-Response 失败` + `解析错误: 类型 '未知类型(0x44)' 的解码器尚未实现`。
版本信息对象（OI=0x4000，属性2=设备描述符）的厂商/型号/版本/日期/产地全部丢失。

## 根因

`dl_t698_45_apdu_parser.py::_parse_get_response` choice=0x01 分支：
- 帧结构 `85 01 PIID OAD(4B) [GetResult]`，本帧 GetResult = `00`(Data) + `02`(structure tag)
- 现代码把 res_tag 当 enum 判断：`==0x00 → Data`，**else 一律当 DAR 按 A-XDR 解码**
- structure 元素标签 `43`('C') 撞上未实现类型 → 抛异常 → 整包丢弃

标准（表47 GetResult::=CHOICE {Data[0], DataAccessResult[1..9]}）：res_tag∈1..9 才是 DAR；tag=0 后跟完整 A-XDR Data。enum 编码为 octet-string 包裹，裸字节 01..09 与之区分。

## 需求

1. 修 `_parse_get_response`（Normal/NormalList）GetResult 判别：≤0x09 视为 DAR，否则按 A-XDR 数据解析
2. 新增版本信息业务解码（dl_t698_45_data_decode.py）：
   - OI 0x4000 属性2 设备描述符 structure{visible-string×7} → 厂商名/设备型号/软件版本/生产日期/硬件版本/固件日期/生产厂商
   - 兜底：任意 structure/array 全 visible-string 时按描述符语义标注
3. GUI 表格展开「数据业务」子行（复用 _add_axdr_item_rows 路径）
4. 测试：test/test_dl_t698_45_fujian.py 或新文件，用用户真实帧断言 JCDZ/1.5/250901/V1.0/230602/SHANDONG 全部出现

## 验收

- 用户帧解析不再报错，表格出现 版本信息-厂商名称=JCDZ、生产日期=2025-09-01 等
- 回归 test_dl_t698_45*.py / test_web_frame_gen_utils.py 全过
