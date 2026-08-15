# Design：Reflex 版本浏览器自动化测试

## 架构

```
reflex_web/
  tests/
    conftest.py          # pytest fixture：启动/停止 Reflex 应用
    test_reflex_app.py   # 核心测试用例
    utils.py              # 公共操作封装
```

## 技术选型

- **pytest**：测试框架
- **Playwright (Python)**：浏览器自动化
- **subprocess + requests**：启动 Reflex 并等待就绪

## 测试环境

1. Reflex 以开发模式启动：`reflex run --frontend-port 8082 --backend-port 8083`
2. pytest fixture 在测试前启动 Reflex，测试后关闭。
3. 使用 Playwright 同步 API 编写测试。

## 测试用例设计

| 用例 | 操作 | 断言 |
|------|------|------|
| 首页 | 访问 / | 页面标题、Tab 按钮存在 |
| 单帧解析 | 输入 hex，点解析 | 结果表格行数 > 0 |
| 批量解析 | 输入多行 hex，点解析 | 结果列表有内容 |
| 协议组帧 | 切换协议 7，选命令，生成 | 结果 hex 非空 |
| 报文对比 | 输入两段 hex，点对比 | 差异表格/统计出现 |
| 查询 | 输入关键词，点搜索 | 查询结果表格有数据 |
| 报文工具 | 输入 hex，点转换 | 输出 textarea 非空 |

## 公共封装

- `wait_for_reflex(url, timeout)`：轮询后端/前端是否就绪。
- `switch_tab(page, label)`：点击 tab 按钮。
- `get_console_errors(page)`：收集控制台 errors。

## 兼容性

- 测试脚本仅在本地开发环境运行，不污染生产代码。
- Reflex 应用代码零改动（除非发现 bug）。
