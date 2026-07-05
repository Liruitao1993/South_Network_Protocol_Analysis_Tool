# 测试方案 Lua 脚本使用说明书

## 一、功能概述

测试方案现支持 **Lua 脚本** 类型测试项，允许您在测试流程中嵌入可编程逻辑，实现：

- **条件分支**：根据响应内容决定下一步操作
- **循环遍历**：批量发送不同地址/参数的帧
- **数据解析**：解析响应帧中的字节并做逻辑判断
- **变量共享**：多个 Lua 步骤之间共享数据
- **动态组帧**：运行时计算帧内容
- **延时控制**：精确控制帧发送间隔

Lua 是一种轻量级脚本语言，语法简洁，非常适合测试自动化场景。

---

## 二、环境要求

需要安装 `lupa` 库（Python-Lua 桥接）：

```bash
pip install lupa
```

安装后重启软件即可使用 Lua 脚本功能。

---

## 三、如何添加 Lua 脚本测试项

1. 在测试方案页面，点击工具栏的 **"添加"** 按钮
2. 在弹出的编辑对话框中，将 **"性质"** 下拉框选择为 **"Lua脚本"**
3. 此时帧相关字段自动隐藏，显示 Lua 脚本编辑器
4. 填写 **名称**（如"遍历地址发送"）
5. 在 **Lua 脚本** 编辑框中编写代码
6. 点击 **确定** 保存

> 编辑已有的 Lua 脚本项：选中行后点击 **"编辑选中"** 按钮。

---

## 四、Lua API 函数参考

以下函数可在 Lua 脚本中直接调用：

### 4.1 日志输出

```lua
log(msg)
```
输出消息到测试日志窗口。`msg` 为字符串。

**示例：**
```lua
log("开始测试")
log("收到数据: " .. resp)
```

### 4.2 发送帧

```lua
ok = send(hex_str)
```
通过串口发送十六进制帧。`hex_str` 为 hex 字符串（支持空格），返回 `true/false`。

**示例：**
```lua
send("68 0E 00 00 00 00 68 11 04 33 33 33 33 16")
send("680E000000006811043333333316")  -- 无空格也可以
```

### 4.3 等待响应

```lua
resp = wait_for_response(timeout_ms)
```
阻塞等待串口响应帧，超时返回空字符串 `""`，成功返回 hex 字符串（大写无空格）。

**示例：**
```lua
local resp = wait_for_response(3000)  -- 等待 3 秒
if resp ~= "" then
    log("收到: " .. resp)
else
    log("超时")
end
```

### 4.4 延时等待

```lua
wait(ms)
```
等待指定毫秒数，用于帧间间隔控制。

**示例：**
```lua
send("68 0E ...")
wait(500)  -- 等待 500ms
send("68 0F ...")
```

### 4.5 停止脚本

```lua
stop(msg)
```
请求停止脚本执行（实际在下次 send/wait 时生效），`msg` 为停止原因。

### 4.6 获取最近响应

```lua
hex = get_last_response()
```
返回最近一次 `wait_for_response` 收到的帧 hex 字符串。

### 4.7 Hex 工具函数

```lua
-- hex 字符串 → Lua 字节表（1-based 索引）
byte_table = hex_to_bytes("68 0E 00 11")
-- 结果: {0x68, 0x0E, 0x00, 0x11}
-- byte_table[1] = 0x68

-- 字节表 → hex 字符串
hex = bytes_to_hex({0x68, 0x0E, 0x00, 0x11})
-- 结果: "68 0E 00 11"
```

**解析响应帧示例：**
```lua
local resp = wait_for_response(3000)
if resp ~= "" then
    local bytes = hex_to_bytes(resp)
    local byte1 = bytes[1]   -- 第 1 字节
    local byte5 = bytes[5]   -- 第 5 字节
    log(string.format("帧头: %02X, 第5字节: %02X", byte1, byte5))
end
```

### 4.8 测试变量

```lua
-- 设置变量（可在后续步骤中读取）
set_test_var("名称", 值)

-- 获取变量
值 = get_test_var("名称")
```
变量在不同 Lua 脚本步骤之间共享，每次"开始测试"时重置。

**示例：**
```lua
-- 步骤1: 统计成功数
set_test_var("成功数", 0)

-- 步骤2: 累加
local count = get_test_var("成功数") or 0
set_test_var("成功数", count + 1)
```

---

## 五、Lua 语法速查

```lua
-- 注释用两个减号

-- 变量赋值
local x = 10           -- 局部变量
name = "test"          -- 全局变量

-- 字符串拼接
local s = "hello" .. " " .. "world"

-- 条件判断
if x > 5 then
    log("大于5")
elseif x == 5 then
    log("等于5")
else
    log("小于5")
end

-- for 循环
for i = 1, 10 do
    log("i = " .. tostring(i))
end

-- 函数定义
local function check_response(resp)
    if resp == "" then return false end
    local bytes = hex_to_bytes(resp)
    return bytes[1] == 0x68
end

-- 格式化输出
log(string.format("地址: %02X, 长度: %d", addr, len))
```

---

## 六、实战示例

### 6.1 遍历地址发送

```lua
-- 遍历地址 01~10，逐帧发送并等待响应
for addr = 1, 10 do
    local addr_hex = string.format("%02X", addr)
    local frame = "68 0E 00 " .. addr_hex .. " 00 00 68 11 04 33 33 33 33 16"

    log(string.format("发送地址 %02d: %s", addr, frame))
    send(frame)

    local resp = wait_for_response(2000)
    if resp ~= "" then
        log(string.format("地址 %02d 响应: %s", addr, resp))
    else
        log(string.format("地址 %02d 超时", addr))
    end

    wait(200)  -- 帧间隔 200ms
end
```

### 6.2 条件判断

```lua
-- 先查询设备，根据响应决定后续操作
log("步骤1: 查询设备信息")
send("68 0E 00 00 00 00 68 11 04 33 33 33 33 16")
local resp = wait_for_response(3000)

if resp == "" then
    stop("设备无响应")
    return
end

local bytes = hex_to_bytes(resp)
if bytes[5] == 0x68 then
    log("设备正常，继续配置")
    wait(500)
    send("68 12 00 00 00 00 68 11 04 33 33 33 33 33 33 16")
    resp = wait_for_response(3000)
    if resp ~= "" then
        log("配置成功")
    else
        log("配置超时")
    end
else
    log("设备异常，跳过配置")
end
```

### 6.3 批量数据采集

```lua
local success = 0
local fail = 0

for i = 1, 5 do
    log(string.format("第 %d 次采集", i))
    send("68 0E 00 00 00 00 68 11 04 33 33 33 33 16")
    local resp = wait_for_response(2000)

    if resp ~= "" then
        log("采集成功")
        success = success + 1
    else
        log("采集超时")
        fail = fail + 1
    end

    wait(300)
end

log(string.format("采集完成: 成功 %d, 失败 %d", success, fail))
set_test_var("采集成功数", success)
set_test_var("采集失败数", fail)
```

### 6.4 与发送帧混合使用

测试方案中可以同时包含"发送帧"和"Lua脚本"两种类型的项，执行时按顺序混合运行：

```
序号 1: [发送帧] 查询基本信息
序号 2: [Lua脚本] 根据响应判断是否需要配置
序号 3: [发送帧] 配置参数
序号 4: [Lua脚本] 遍历地址读取数据
```

---

## 七、测试方案执行流程

1. 点击 **"开始测试"**，按序号顺序执行每个测试项
2. 遇到 **发送帧**：发送后等待响应匹配（原有逻辑不变）
3. 遇到 **Lua脚本**：在独立线程中执行脚本，脚本完成后继续下一项
4. Lua 脚本的超时时间由该项的"超时(ms)"设置决定（默认 60 秒）
5. 点击 **"停止测试"** 可中断执行中的 Lua 脚本
6. 勾选 **"失败时停止"**：Lua 脚本出错时停止后续测试

---

## 八、注意事项

1. **串口占用**：Lua 脚本执行期间独占串口发送权限，其他测试项无法同时发送
2. **超时控制**：脚本最大执行时间受"超时(ms)"字段限制，超时后会请求停止
3. **变量重置**：每次"开始测试"时，`set_test_var` / `get_test_var` 的变量会重置
4. **帧格式**：`send()` 中的 hex 字符串支持空格分隔或无空格格式
5. **错误处理**：Lua 语法错误不会崩溃软件，会在日志中显示错误信息
6. **持久化**：Lua 脚本内容随测试方案自动保存/加载（JSON 格式）
7. **导出/导入**：导出 JSON 时包含 `script` 字段，导入时自动识别 Lua 脚本项

---

## 九、依赖说明

| 组件 | 说明 |
|------|------|
| `lupa` 库 | Python-Lua 桥接，包含 Lua 5.4+ 运行时，Windows 预编译 |
| 大小 | 约 1.9 MB（wheel），打包后增加约 2-3 MB |
| 安装 | `pip install lupa` |
| PyInstaller | 自动打包 Lua DLL，无需额外配置 |

如未安装 lupa，选择“Lua脚本”时会提示安装。

---

## 十、内置 Vim 编辑器

Lua 脚本编辑器内置了轻量级 Vim 模式，支持常用的 Vim 键绑定。

### 10.1 模式切换

| 操作 | 按键 | 说明 |
|------|------|------|
| 进入普通模式 | `ESC` 或 `Ctrl+[` | 从插入模式切换到普通模式 |
| 进入插入模式 | `i` | 在光标前插入 |
| 进入插入模式 | `a` | 在光标后插入 |
| 进入插入模式 | `I` | 在行首插入 |
| 进入插入模式 | `A` | 在行尾插入 |
| 下方新建行 | `o` | 在下方新建行并进入插入 |
| 上方新建行 | `O` | 在上方新建行并进入插入 |
| 进入可视模式 | `v` | 字符选择 |
| 进入可视模式 | `V` | 行选择 |

### 10.2 普通模式导航

| 按键 | 功能 |
|------|------|
| `h` `j` `k` `l` | 左/下/上/右移动 |
| `w` | 跳到下一个单词 |
| `b` | 跳到上一个单词 |
| `0` | 跳到行首 |
| `$` | 跳到行尾 |
| `gg` | 跳到文件开头 |
| `G` | 跳到文件末尾 |

### 10.3 编辑操作

| 按键 | 功能 |
|------|------|
| `x` | 删除光标处字符 |
| `dd` | 删除当前行 |
| `yy` | 复制当前行 |
| `p` | 粘贴到下方 |
| `P` | 粘贴到上方 |
| `u` | 撤销 |
| `Ctrl+r` | 重做 |

### 10.4 可视模式操作

| 按键 | 功能 |
|------|------|
| `h/j/k/l` | 扩展选择范围 |
| `y` | 复制选中内容 |
| `d` 或 `x` | 删除选中内容 |
| `>` | 增加缩进 |
| `<` | 减少缩进 |
| `ESC` | 退出可视模式 |

### 10.5 命令模式

在普通模式下按 `:` 进入命令模式：

| 命令 | 功能 |
|------|------|
| `:w` | 保存脚本内容 |
| `:q` | 关闭编辑器 |
| `:wq` | 保存并关闭 |

### 10.6 模式指示器

编辑器右上角显示当前模式：
- **INSERT**（蓝色背景）：插入模式，正常输入
- **NORMAL**（灰色背景）：普通模式，Vim 命令
- **VISUAL**（橙色背景）：可视模式，选择文本
- **:**（深灰背景）：命令模式
