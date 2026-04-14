# 电力协议解析工具

多种电力通信协议图形化解析工具，基于 Python/PySide6 开发。

## 支持协议

| 协议 | 说明 |
|------|------|
| 南网协议 | 南方电网 Q/CSG1209021-2019 标准 |
| PLC RF 协议 | 万胜海外 V1_04 |
| HDLC/DLMS | IEC 62056-46 标准 |
| DLMS Wrapper 裸报文 | 直接解析 Wrapper + APDU |
| DLMS-APDU 裸报文 | 直接解析 APDU |

## 主要功能

- **单帧解析**：输入十六进制报文，一键解析，表格展示分层结构
- **批量解析**：从文本文件/剪贴板批量导入多帧报文自动解析，支持导出 JSON
- **DI 查询**：南网协议专用，搜索 DI 编码或中文含义，支持添加自定义 DI
- **DLMS 深度解析**：双击 `DLMS APDU` 行自动提取整段 APDU 弹出深度解析
- **字节高亮**：点击表格行自动在输入报文中高亮对应字节范围
- **位域详细拆解**：控制域每个 bit 位单独显示二进制+十进制结果
- **紧凑美观**：表格字体缩小+行高压缩，相同窗口展示更多内容
- **交替行颜色**：macOS 风格淡雅交替背景色，阅读舒适

## 运行需求

- Python 3.8+
- PySide6

## 安装依赖

```bash
pip install pyside6
```

## 运行

```bash
python main_gui.py
```

## 打包 exe

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "协议解析工具" main_gui.py
```

打包完成后 exe 在 `dist/协议解析工具.exe`

## 使用说明

### 基本使用

1. 在顶部下拉框选择要解析的协议类型
2. 在「输入报文」文本框粘贴十六进制报文（支持带空格/无空格混合格式）
3. 点击「解析报文」按钮
4. 下方表格显示分层解析结果
5. 点击表格行，输入框自动高亮对应字节范围
6. 对于 DLMS/HDLC 协议，如果有 `DLMS APDU` 行，可以**双击**该行提取整个 APDU 弹出深度解析窗口

### DLMS 深度解析

当解析 HDLC 帧时，`DLMS APDU` 行会自动覆盖整个 APDU 的完整字节范围，**双击该行**即可：
- 自动提取完整 APDU 字节
- 弹出新窗口深度解析 APDU 结构
- 支持 Get-Request/Set-Request/Action-Request 等各种 APDU 类型
- 支持 BER-TLV 编码递归解析

### 南网 DI 查询

切换到「DI查询」标签页：
- 输入 DI 编码（如 `E8020201`）或中文关键词搜索
- 表格实时过滤匹配结果
- 支持添加/删除自定义 DI

### 批量解析

切换到「批量解析」标签页：
- 支持从文件加载或剪贴板粘贴
- 自动从混杂文本（日志）中提取完整 68 起始帧
- 点击「开始批量解析」批量处理所有帧
- 点击表格行弹出详情窗口
- 支持导出全部结果到 JSON 文件

## 项目结构

```
├── main_gui.py          # GUI 主程序
├── protocol_parser.py   # 南网协议解析器
├── plc_rf_parser.py     # PLC RF 协议解析器
├── hdlc_parser.py       # HDLC/DLMS 解析器
└── README.md           # 本文档
```

## 截图

![界面截图](screenshot.png)

## 许可证

MIT
