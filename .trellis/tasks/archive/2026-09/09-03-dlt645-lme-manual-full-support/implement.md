# Implement：DLT645 LME 自定义接口解析

## 执行清单

### 1. `lme_info_entry_parser.py` 扩展

- [x] 1.1 新增常量：`DI_STA_VERSION_SINGLE="04FFAAF9"`、`DI_DUAL_ENTRY="FF00DD01"`；分类名 MAP（0 基本信息/1 程序信息/2 硬件信息/3 网络信息/4 运行信息/5 CCO运行信息）
- [x] 1.2 新增枚举 MAP：`BAUD_MAP`（0~12: BR_300/600/1200/2400/4800/9600/19200/38400/57600/115200/230400/460800/921600 bps）、`PARITY_MAP`、`PROVINCE_MAP`（0 国网/1 江苏Ⅰ/2 山西/3 四川/4 宁夏/5 陕西/6 湖南/7 安徽/8 重庆/9 辽宁/10 水投/11 北京）、`BAND_MAP`、`SET_RESULT_MAP`（0 成功/1 参数不支持设置/2 参数内容格式错误/3 参数保存失败）、`FUNC_SWITCH_BITS`（b0 即装即采/b1 万年历/b2 低功耗/b3 白名单）
- [x] 1.3 `parse_sta_version_single(data)`：按 design 分派表逐字段解析 4.2 固定布局；版本号/日期/层级标志/频率占空比/Flash 容量/硬件信息变长段；数据不足追加不完整提示
- [x] 1.4 `parse_dual_entry_query_request(data)`：4B DI + 1B 条目信息 + M + M×2B 请求头（数据ID6/分类ID3/保留7）
- [x] 1.5 `parse_dual_entry_response(data)`：由现有 `parse_lme_info_entries` 重构为 3 元组（名称/值/说明），未知条目按头部编码(ASCII/BIN/BCD)解码，名称前缀分类名；保留 `parse_lme_info_entries` 旧签名包装（archive_widget 兼容，内部调新函数）
- [x] 1.6 `parse_dual_entry_set_request(data)`：TLV 结构同响应
- [x] 1.7 `parse_dual_entry_set_response(data)`：M + M×2B 结果头（数据ID6/分类ID3/结果7），结果码中文
- [x] 1.8 语义增强 `_format_semantic()`：波特率/校验位（分类0-15）、功能开关位（0-9）、省份（0-7）、频段（0-16）、过零检测信息（2-20，13B 展开标志位+三相频率占空比）、组网完成标识（5-6）；不破坏 `_format_value` 现有分支
- [x] 1.9 总入口 `parse_lme_dlt645(di_code, ctrl, data)`：按 design 分派矩阵路由，返回 `(fields, 接口名)`；非 LME DI 返回 `(None, "")`

### 2. `dlt645_parser.py` 接线

- [x] 2.1 import `parse_lme_dlt645`
- [x] 2.2 DI 命中后：设置 di_desc 为 LME 接口名；try/except 调分派函数，fields 追加解析子行（缩进前缀）+ 一行原始数据 hex；异常回退裸 hex 并备注
- [x] 2.3 非 LME 路径零改动自检

### 3. `dlt645_di.json`

- [x] 3.1 增加 `04FFAAF9`、`FF00DD01` 两条（name/data_type/length=255），JSON 合法

### 4. `validator/dlt645_validator.py`

- [x] 4.1 data_len>200 WARN 分支：减 0x33 读前 4B 小端 DI，命中两个 LME DI → PASS（消息注明 LME 自定义接口）；否则维持原 WARN

### 5. 测试 `test_dlt645_lme.py`（根目录独立脚本，可 pytest）

- [x] 5.1 手册 4.2 示例帧组帧（CS 自动算）→ 断言厂商 LH/芯片 60/V0A01/日期 191029/MCU V0101/APS A0102/NWK N0205/PHY P1001/DSP V4012/过零 07/频率 50.00Hz/占空比 50.0%
- [x] 5.2 FF00DD01 查询请求帧（DIR=0 FUNC=11，M=1，分类0/数据15）→ 断言条目名含"本地接口默认信息"
- [x] 5.3 FF00DD01 查询应答（M=1，TLV 波特率 B0=5/B1=0）→ 断言值含 BR_9600 与 无校验
- [x] 5.4 FF00DD01 设置请求（M=1 带数据）与设置应答（结果 0）→ 断言"设置成功"
- [x] 5.5 截断帧（数据域砍半）不抛异常、含不完整提示
- [x] 5.6 标准 645 帧（DI=00010000）解析结果与旧行为一致（di_desc=当前正向有功总电能）
- [x] 5.7 LME 255B 数据域 validator 不 WARN；普通超长仍 WARN

### 6. 验证与收尾

- [x] 6.1 `python -m py_compile lme_info_entry_parser.py dlt645_parser.py validator/dlt645_validator.py test_dlt645_lme.py`
- [x] 6.2 `python test_dlt645_lme.py` 全过
- [x] 6.3 `python test/test_feedback_api.py` 等现有 GUI 相关测试不回归（archive_widget 路径）：构造 FF00DD01 应答走 `parse_lme_info_entries` 旧签名返回 2 元组
- [x] 6.4 检查 `南网协议解析工具.spec`：lme_info_entry_parser.py 经 archive_widget/dlt645_parser 隐式 import 已覆盖；dlt645_di.json 已在 datas（确认）
- [x] 6.5 GUI 实跑：`python main_gui.py --parse "<示例帧>" --protocol 6` 目检字段输出
- [x] 6.6 spec 更新（.trellis/spec 中解析器相关索引）+ Trellis finish + commit

## 验证命令

```bash
python -m py_compile lme_info_entry_parser.py dlt645_parser.py validator/dlt645_validator.py
python test_dlt645_lme.py
python main_gui.py --parse "68 10 00 00 00 00 68 91 3A 2C DD 32 37 ..." --protocol 6
```

## 回退点

- dlt645_parser.py 分派块 try/except 包裹，异常自动回退旧显示
- lme_info_entry_parser.py 仅新增函数 + 旧函数包装，删除新调用即恢复
- dlt645_di.json 两条新增可独立删除
