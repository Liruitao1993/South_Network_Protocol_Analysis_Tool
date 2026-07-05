"""Lua 脚本引擎 —— 测试方案 Lua 脚本执行支持

依赖：lupa（pip install lupa）

Lua 脚本可用 API：
    log(msg)                    — 输出日志到测试日志窗口
    send(hex_str)               — 发送十六进制帧（如 "68 0E 00 ..."）
    wait_for_response(timeout_ms) — 等待响应帧，返回 hex 字符串或 ""
    wait(ms)                    — 延时等待（毫秒）
    hex_to_bytes(hex_str)       — hex 字符串 → Lua 字节表 {b1, b2, ...}
    bytes_to_hex(byte_table)    — Lua 字节表 → hex 字符串
    get_last_response()         — 获取最近一次收到的响应 hex
    get_test_var(name)          — 获取测试变量
    set_test_var(name, value)   — 设置测试变量（跨步骤共享）
    stop(msg)                   — 停止脚本并记录消息
"""

import threading
import time
from datetime import datetime
from typing import Optional, Dict, Any

from PySide6.QtCore import QObject, Qt, Signal

try:
    import lupa
    LUPA_AVAILABLE = True
except ImportError:
    LUPA_AVAILABLE = False


class LuaEngineBridge(QObject):
    """Qt 信号桥接：在串口读取线程中接收原始数据，转发给 Lua 引擎"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frame_event = threading.Event()
        self._last_frame: Optional[bytes] = None
        self._lock = threading.Lock()

    def on_raw_data_received(self, data: bytes):
        """由 SerialWorker.raw_data_received 信号直接调用（DirectConnection）
        接收串口原始数据，不依赖 FT1.2 帧解析"""
        with self._lock:
            self._last_frame = bytes(data)
        self._frame_event.set()

    def wait_for_frame(self, timeout_ms: int) -> Optional[bytes]:
        """阻塞等待串口数据，超时返回 None"""
        self._frame_event.clear()
        if self._frame_event.wait(timeout=timeout_ms / 1000.0):
            with self._lock:
                frame = self._last_frame
                self._last_frame = None
            return frame
        return None


class LuaScriptEngine(QObject):
    """Lua 脚本执行引擎

    在独立线程中运行 Lua 脚本，通过信号与 GUI 通信。
    """

    log_signal = Signal(str)          # 日志消息
    finished_signal = Signal(bool, str)  # (成功, 结果描述)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._serial_worker = None
        self._stop_requested = False
        self._last_response: str = ""
        self._lua = None
        self._result: str = ""
        self._success: bool = False
        self._bridge: Optional[LuaEngineBridge] = None
        self._test_vars: Dict[str, Any] = {}  # 测试变量（跨步骤共享）
        self._send_log_callback = None  # 外部日志回调（可选）

    def set_serial_worker(self, worker):
        """设置串口工作线程"""
        self._serial_worker = worker
        if worker and self._bridge is None:
            self._bridge = LuaEngineBridge()
            # 连接原始数据信号（不依赖 FT1.2 帧解析，任何串口数据都会触发）
            worker.raw_data_received.connect(
                self._bridge.on_raw_data_received, Qt.ConnectionType.DirectConnection
            )

    def set_test_vars(self, variables: Dict[str, Any]):
        """设置共享测试变量"""
        self._test_vars = variables

    def set_send_log_callback(self, callback):
        """设置额外的发送日志回调"""
        self._send_log_callback = callback

    def _create_lua_runtime(self):
        """创建 Lua 运行时并注册 API"""
        if not LUPA_AVAILABLE:
            raise ImportError(
                "lupa 库未安装，请运行: pip install lupa"
            )
        self._lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        self._register_api()

    def _register_api(self):
        """注册 Lua 可调用的 API 函数"""
        g = self._lua.globals()

        def lua_log(msg):
            text = str(msg) if msg is not None else ""
            self._emit_log(text)

        def lua_send(hex_str):
            if self._stop_requested:
                return False
            if not self._serial_worker or not self._serial_worker.is_open():
                self._emit_log("[Lua错误] 串口未打开")
                return False
            hex_clean = str(hex_str).replace(" ", "").replace("\n", "").strip()
            try:
                frame_bytes = bytes.fromhex(hex_clean)
            except ValueError:
                self._emit_log(f"[Lua错误] 无效的十六进制: {hex_str}")
                return False
            ok = self._serial_worker.send_frame(frame_bytes)
            if ok:
                formatted = " ".join(f"{b:02X}" for b in frame_bytes)
                self._emit_log(f"[Lua发送] {formatted}")
                if self._send_log_callback:
                    self._send_log_callback(formatted)
            return ok

        def lua_wait_for_response(timeout_ms):
            if self._stop_requested:
                return ""
            if not self._bridge:
                self._emit_log("[Lua错误] 串口桥接未初始化")
                return ""
            ms = int(timeout_ms) if timeout_ms else 2000
            frame = self._bridge.wait_for_frame(ms)
            if frame:
                hex_str = frame.hex().upper()
                self._last_response = hex_str
                formatted = " ".join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
                self._emit_log(f"[Lua接收] {formatted}")
                return hex_str
            else:
                self._emit_log(f"[Lua超时] 等待 {ms}ms 无响应")
                return ""

        def lua_wait(ms):
            if self._stop_requested:
                return
            ms = int(ms) if ms else 1000
            # 分段等待，便于检查停止标志
            end_time = time.time() + ms / 1000.0
            while time.time() < end_time:
                if self._stop_requested:
                    return
                remaining = end_time - time.time()
                time.sleep(min(0.1, remaining) if remaining > 0 else 0)

        def lua_hex_to_bytes(hex_str):
            """hex 字符串 → Lua table {b1, b2, ...}"""
            try:
                data = bytes.fromhex(str(hex_str).replace(" ", ""))
                t = self._lua.eval("{}")
                for i, b in enumerate(data):
                    t[i + 1] = b  # Lua 1-based index
                return t
            except ValueError:
                return self._lua.eval("{}")

        def lua_bytes_to_hex(byte_table):
            """Lua table {b1, b2, ...} → hex 字符串"""
            try:
                parts = []
                i = 1
                while True:
                    val = byte_table[i]
                    if val is None:
                        break
                    parts.append(f"{int(val):02X}")
                    i += 1
                return " ".join(parts)
            except Exception:
                return ""

        def lua_get_last_response():
            return self._last_response

        def lua_get_test_var(name):
            """获取测试变量"""
            key = str(name) if name else ""
            return self._test_vars.get(key)

        def lua_set_test_var(name, value):
            """设置测试变量"""
            key = str(name) if name else ""
            self._test_vars[key] = value

        def lua_stop(msg):
            """停止脚本执行"""
            self._stop_requested = True
            if msg:
                self._emit_log(f"[Lua停止] {msg}")

        # 注册到 Lua 全局环境
        g.log = lua_log
        g.send = lua_send
        g.wait_for_response = lua_wait_for_response
        g.wait = lua_wait
        g.hex_to_bytes = lua_hex_to_bytes
        g.bytes_to_hex = lua_bytes_to_hex
        g.get_last_response = lua_get_last_response
        g.get_test_var = lua_get_test_var
        g.set_test_var = lua_set_test_var
        g.stop = lua_stop

    def _emit_log(self, msg: str):
        """发送日志消息到 GUI"""
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_signal.emit(f"[{ts}] {msg}")

    def request_stop(self):
        """请求停止脚本执行"""
        self._stop_requested = True
        if self._bridge:
            self._bridge._frame_event.set()  # 唤醒等待

    def run(self, script: str):
        """执行 Lua 脚本（应在子线程中调用）"""
        self._stop_requested = False
        self._result = ""
        self._success = False

        try:
            if not LUPA_AVAILABLE:
                self._result = "lupa 库未安装，请运行: pip install lupa"
                self._emit_log(f"[Lua错误] {self._result}")
                self.finished_signal.emit(False, self._result)
                return

            self._create_lua_runtime()

            self._emit_log("[Lua] 脚本开始执行...")
            start_time = datetime.now()

            result = self._lua.execute(script)

            elapsed = (datetime.now() - start_time).total_seconds()

            if self._stop_requested:
                self._result = "用户停止"
                self._emit_log(f"[Lua] 脚本被停止 ({elapsed:.1f}s)")
                self._success = False
            else:
                self._result = f"执行成功 ({elapsed:.1f}s)"
                self._emit_log(f"[Lua] 脚本执行完成 ({elapsed:.1f}s)")
                self._success = True

        except lupa.LuaError as e:
            error_msg = str(e)
            self._result = f"Lua错误: {error_msg}"
            self._emit_log(f"[Lua错误] {error_msg}")
            self._success = False
        except Exception as e:
            self._result = f"异常: {str(e)}"
            self._emit_log(f"[Lua异常] {str(e)}")
            self._success = False
        finally:
            self.finished_signal.emit(self._success, self._result)

    @staticmethod
    def is_available() -> bool:
        """检查 lupa 是否可用"""
        return LUPA_AVAILABLE


# --------------------------------------------------------------------------
# Lua 脚本模板（供编辑器预置）
# --------------------------------------------------------------------------
LUA_TEMPLATES = {
    "空脚本": """\
-- Lua 脚本模板
-- 可用 API: log, send, wait, wait_for_response, stop
--         hex_to_bytes, bytes_to_hex, get_last_response
--         get_test_var, set_test_var

log("脚本开始")

-- 发送帧并等待响应
send("68 0E 00 00 00 00 68 11 04 33 33 33 33 16")
local resp = wait_for_response(3000)

if resp ~= "" then
    log("收到响应: " .. resp)
else
    log("超时未收到响应")
end

log("脚本结束")
""",
    "遍历地址发送": """\
-- 遍历地址发送示例
-- 从地址 01 到 10 逐帧发送并等待响应

local start_addr = 1
local end_addr = 10
local timeout = 2000  -- 每帧超时 2 秒

for addr = start_addr, end_addr do
    -- 构造地址字节（2 位十六进制）
    local addr_hex = string.format("%02X", addr)
    local frame = "68 0E 00 " .. addr_hex .. " 00 00 68 11 04 33 33 33 33 16"

    log(string.format("发送地址 %02d: %s", addr, frame))
    send(frame)

    local resp = wait_for_response(timeout)
    if resp ~= "" then
        log(string.format("地址 %02d 响应: %s", addr, resp))
    else
        log(string.format("地址 %02d 超时", addr))
    end

    wait(200)  -- 帧间隔 200ms
end

log("遍历完成")
""",
    "条件判断": """\
-- 条件判断示例
-- 先查询设备信息，根据结果决定后续操作

log("步骤1: 查询设备信息")
send("68 0E 00 00 00 00 68 11 04 33 33 33 33 16")
local resp = wait_for_response(3000)

if resp == "" then
    log("设备无响应，停止")
    stop("设备无响应")
    return
end

-- 检查响应中的某个字节
local resp_bytes = hex_to_bytes(resp)
local byte5 = resp_bytes[5]  -- 第 5 个字节

if byte5 == 0x68 then
    log("设备响应正常，继续操作")
    wait(500)
    log("步骤2: 发送配置命令")
    send("68 12 00 00 00 00 68 11 04 33 33 33 33 33 33 16")
    resp = wait_for_response(3000)
    if resp ~= "" then
        log("配置成功")
    else
        log("配置超时")
    end
else
    log("设备响应异常，跳过配置")
end

log("脚本完成")
""",
    "数据解析与变量": """\
-- 数据解析与变量使用示例

log("开始数据采集")

-- 使用变量记录统计
local success_count = 0
local fail_count = 0

for i = 1, 5 do
    log(string.format("第 %d 次采集", i))
    send("68 0E 00 00 00 00 68 11 04 33 33 33 33 16")
    local resp = wait_for_response(2000)

    if resp ~= "" then
        -- 解析响应长度
        local resp_bytes = hex_to_bytes(resp)
        local resp_len = 0
        while resp_bytes[resp_len + 1] ~= nil do
            resp_len = resp_len + 1
        end
        log(string.format("响应长度: %d 字节", resp_len))
        success_count = success_count + 1
    else
        fail_count = fail_count + 1
    end

    wait(300)
end

log(string.format("采集完成: 成功 %d, 失败 %d", success_count, fail_count))

-- 保存统计到测试变量（可被后续步骤读取）
set_test_var("采集成功数", success_count)
set_test_var("采集失败数", fail_count)
""",
}
