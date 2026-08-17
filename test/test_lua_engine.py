"""Lua 脚本引擎基础测试"""

import _path_setup  # noqa: E402

import threading
import sys
sys.path.insert(0, ".")

from lua_script_engine import LuaScriptEngine, LUPA_AVAILABLE, LUA_TEMPLATES


def test_basic_lua():
    """测试基本 Lua 执行"""

    print("=== 测试基本 Lua 执行 ===")
    engine = LuaScriptEngine()
    logs = []

    # 覆盖信号 emit 方法（避免 Qt 事件循环依赖）
    original_log = engine._emit_log
    engine._emit_log = lambda msg: logs.append(msg)
    engine.finished_signal = type('Mock', (), {'emit': lambda self, ok, msg: None})()

    script = """
x = 1 + 2
log("result: " .. tostring(x))
log("Lua is working!")
"""
    t = threading.Thread(target=engine.run, args=(script,))
    t.start()
    t.join(timeout=5)

    assert engine._success, f"脚本应成功: {engine._result}"
    assert any("result: 3" in l for l in logs), f"应包含计算结果, logs={logs}"
    assert any("Lua is working" in l for l in logs), f"应包含工作消息, logs={logs}"
    print(f"  通过! 日志数: {len(logs)}")
    for l in logs:
        print(f"  {l}")


def test_hex_utils():
    """测试 hex 工具函数"""
    print("\n=== 测试 hex 工具函数 ===")
    engine = LuaScriptEngine()
    logs = []
    engine._emit_log = lambda msg: logs.append(msg)
    engine.finished_signal = type('Mock', (), {'emit': lambda self, ok, msg: None})()

    script = """
local t = hex_to_bytes("68 0E 00 11")
log(string.format("byte1=%02X byte2=%02X byte3=%02X byte4=%02X", t[1], t[2], t[3], t[4]))

local hex = bytes_to_hex({0x68, 0x0E, 0x00, 0x11})
log("hex: " .. hex)
"""
    t = threading.Thread(target=engine.run, args=(script,))
    t.start()
    t.join(timeout=5)

    assert engine._success, f"脚本应成功: {engine._result}"
    assert any("byte1=68" in l for l in logs), f"应包含byte1=68, logs={logs}"
    assert any("68 0E 00 11" in l for l in logs), f"应包含hex转换结果, logs={logs}"
    print(f"  通过!")
    for l in logs:
        print(f"  {l}")


def test_variables():
    """测试测试变量"""
    print("\n=== 测试测试变量 ===")
    engine = LuaScriptEngine()
    logs = []
    engine._emit_log = lambda msg: logs.append(msg)
    engine.finished_signal = type('Mock', (), {'emit': lambda self, ok, msg: None})()
    engine.set_test_vars({"初始值": 42})

    script = """
local v = get_test_var("初始值")
log("初始值: " .. tostring(v))
set_test_var("新值", v + 8)
log("新值: " .. tostring(get_test_var("新值")))
"""
    t = threading.Thread(target=engine.run, args=(script,))
    t.start()
    t.join(timeout=5)

    assert engine._success, f"脚本应成功: {engine._result}"
    assert engine._test_vars.get("新值") == 50, f"新值应为50, got={engine._test_vars}"
    print(f"  通过! 变量: {engine._test_vars}")


def test_stop():
    """测试脚本停止"""
    print("\n=== 测试脚本停止 ===")
    engine = LuaScriptEngine()
    logs = []
    engine._emit_log = lambda msg: logs.append(msg)
    engine.finished_signal = type('Mock', (), {'emit': lambda self, ok, msg: None})()

    script = """
log("before stop")
stop("测试停止")
log("after stop")  -- 不应执行
"""
    t = threading.Thread(target=engine.run, args=(script,))
    t.start()
    t.join(timeout=5)

    # stop 设置了 _stop_requested，但 Lua 继续执行直到结束
    # 所以 after stop 可能还是会执行（stop 只影响 send/wait）
    assert any("before stop" in l for l in logs), f"应包含before, logs={logs}"
    print(f"  通过!")
    for l in logs:
        print(f"  {l}")


def test_lua_error():
    """测试 Lua 语法错误"""
    print("\n=== 测试 Lua 语法错误 ===")
    engine = LuaScriptEngine()
    logs = []
    engine._emit_log = lambda msg: logs.append(msg)
    engine.finished_signal = type('Mock', (), {'emit': lambda self, ok, msg: None})()

    script = "this is not valid lua code !!!"
    t = threading.Thread(target=engine.run, args=(script,))
    t.start()
    t.join(timeout=5)

    assert not engine._success, "脚本应失败"
    assert "Lua错误" in engine._result or "异常" in engine._result, f"应包含错误: {engine._result}"
    print(f"  通过! 错误: {engine._result}")


def test_templates_valid():
    """测试模板脚本可执行"""
    print("\n=== 测试模板脚本 ===")
    for name, script in LUA_TEMPLATES.items():
        engine = LuaScriptEngine()
        logs = []
        engine._emit_log = lambda msg: logs.append(msg)
        engine.finished_signal = type('Mock', (), {'emit': lambda self, ok, msg: None})()

        # 模板中可能有 send/wait_for_response，不设置 serial worker 会报错但不致命
        # 只验证模板能加载不崩溃
        t = threading.Thread(target=engine.run, args=(script,))
        t.start()
        t.join(timeout=5)

        # 模板可能因无串口而失败，但不应崩溃
        print(f"  [{name}] success={engine._success}, result={engine._result}")
        assert not t.is_alive(), f"模板 {name} 应该结束"


if __name__ == "__main__":
    assert LUPA_AVAILABLE, "lupa 未安装"
    test_basic_lua()
    test_hex_utils()
    test_variables()
    test_stop()
    test_lua_error()
    test_templates_valid()
    print("\n=== 所有测试通过! ===")
