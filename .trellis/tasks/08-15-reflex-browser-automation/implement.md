# Implement：Reflex 版本浏览器自动化测试

## 步骤

1. **准备环境**
   - [ ] 检查是否安装 `pytest` 和 `pytest-playwright`。
   - [ ] 如未安装，安装依赖。

2. **创建测试目录和文件**
   - [ ] 创建 `reflex_web/tests/`。
   - [ ] 创建 `reflex_web/tests/conftest.py`。
   - [ ] 创建 `reflex_web/tests/test_reflex_app.py`。
   - [ ] 创建 `reflex_web/tests/utils.py`。

3. **实现 fixture**
   - [ ] 在 `conftest.py` 中实现 `reflex_app` fixture：
     - 启动 Reflex dev server
     - 等待前端和后端就绪
     - yield base URL
     - 测试结束后终止进程

4. **实现测试用例**
   - [ ] `test_homepage`：访问首页，检查 tab 按钮。
   - [ ] `test_single_parse`：单帧解析流程。
   - [ ] `test_batch_parse`：批量解析流程。
   - [ ] `test_frame_gen`：协议组帧流程（协议 7 或 8）。
   - [ ] `test_diff`：报文对比流程。
   - [ ] `test_lookup`：查询流程。
   - [ ] `test_message_tool`：报文工具流程。

5. **运行测试**
   - [ ] 运行 `pytest reflex_web/tests/test_reflex_app.py`。
   - [ ] 修复失败的用例。
   - [ ] 检查控制台 errors。

6. **收尾**
   - [ ] 更新任务状态。
   - [ ] 提交代码。

## 变更文件

- `reflex_web/tests/conftest.py`
- `reflex_web/tests/test_reflex_app.py`
- `reflex_web/tests/utils.py`
