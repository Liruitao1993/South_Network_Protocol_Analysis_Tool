# -*- coding: utf-8 -*-
"""协议9 组帧「仿照模板」本地存储（``csg_frame_templates``）纯逻辑测试（无 Qt）。

重点覆盖：

1. 存档往返：save → get / load → delete / rename；
2. 同名覆盖（不产生重复条目）与 ``created`` 保留；
3. 名称校验：空 / 超长 / 非法字符被拒，正常名通过 + 空白清洗；
4. **坏文件宽容**：非 JSON / 顶层不是对象 / 条目缺字段 ⇒ 返回空表并给出原因，绝不抛栈；
5. 原子写：不残留 ``.tmp``；空文件按空表处理；
6. 数量上限保护；参数集为空时拒绝保存。

每个用例把 ``store_path`` 指到独立临时文件，**不碰真实数据目录**。

运行：``python test/test_csg_frame_templates.py``（无 Qt，无需显示器）。
"""

import _path_setup  # noqa: E402,F401

import json
import tempfile
from pathlib import Path

import csg_frame_templates as tpl  # noqa: E402

_FAILURES = []
_CHECKS = []
_ORIGINAL_STORE_PATH = tpl.store_path
_TMP_DIR = None


def check(name, condition, detail=""):
    _CHECKS.append(name)
    if not condition:
        _FAILURES.append(f"{name} —— {detail}")


def setup_temp_store():
    """把模板存档指向独立临时文件；返回该路径。"""
    global _TMP_DIR
    _TMP_DIR = Path(tempfile.mkdtemp(prefix="csg_tpl_test_"))
    path = _TMP_DIR / "templates.json"
    tpl.store_path = lambda: path
    return path


def state_of(marker: str):
    return {"version": 1, "frame": {"kind": "sof", "output": "mpdu"},
            "link": {"src_tei": 0x123, "dest_tei": 0x456}, "header": {}, "ed": {},
            "mode": {"key": "legacy_6", "params": {"value": 1}}, "note": marker}


# ----------------------------------------------------------------------
# 1. 存档往返
# ----------------------------------------------------------------------
def test_save_load_delete_roundtrip():
    setup_temp_store()
    check("往返：初始为空表", tpl.load_templates()[0] == [])
    check("往返：空表无告警", tpl.load_templates()[1] == "", tpl.load_templates()[1])

    error = tpl.save_template("频段切换A", state_of("a"), reference_hex="ED 1E", label="SOF/1.0")
    check("往返：保存成功无错误", error == "", error)
    error = tpl.save_template("频段切换B", state_of("b"))
    check("往返：第二个模板保存成功", error == "", error)
    items, warn = tpl.load_templates()
    check("往返：两个模板都在且顺序稳定",
          [i["name"] for i in items] == ["频段切换A", "频段切换B"],
          str([i["name"] for i in items]))
    check("往返：load 无告警", warn == "", warn)

    item = tpl.get_template("频段切换A")
    check("往返：get 拿得到", item is not None and item["state"]["note"] == "a")
    check("往返：参考报文与 label 存档", item["reference_hex"] == "ED 1E" and item["label"] == "SOF/1.0")
    check("往返：created 已填", bool(item["created"]), str(item.get("created")))
    check("往返：不存在的名字返回 None", tpl.get_template("没有这个") is None)

    check("往返：删除成功", tpl.delete_template("频段切换A") == "")
    check("往返：删除后只剩一个",
          [i["name"] for i in tpl.load_templates()[0]] == ["频段切换B"])
    check("往返：删除不存在的名字也算成功", tpl.delete_template("没有这个") == "")


def test_save_overwrites_same_name():
    setup_temp_store()
    tpl.save_template("同名", state_of("first"))
    created = tpl.get_template("同名")["created"]
    tpl.save_template("同名", state_of("second"), label="改过")
    items = tpl.load_templates()[0]
    check("覆盖：不产生重复条目", len(items) == 1, str([i["name"] for i in items]))
    check("覆盖：参数集被替换", tpl.get_template("同名")["state"]["note"] == "second")
    check("覆盖：created 保留原值", tpl.get_template("同名")["created"] == created)


def test_rename():
    setup_temp_store()
    tpl.save_template("旧名", state_of("x"))
    check("重命名：成功", tpl.rename_template("旧名", "新名") == "")
    check("重命名：新名可取到", tpl.get_template("新名") is not None)
    check("重命名：旧名没了", tpl.get_template("旧名") is None)
    check("重命名：源不存在报错", tpl.rename_template("没有", "随意") != "")
    tpl.save_template("占用", state_of("y"))
    check("重命名：目标已存在则拒绝（不静默覆盖）", tpl.rename_template("新名", "占用") != "")
    check("重命名：拒绝后目标内容未变", tpl.get_template("占用")["state"]["note"] == "y")


# ----------------------------------------------------------------------
# 2. 名称校验
# ----------------------------------------------------------------------
def test_name_validation():
    check("校验：空名被拒", tpl.validate_name("") != "")
    check("校验：纯空白被拒", tpl.validate_name("   ") != "")
    check("校验：超长被拒", tpl.validate_name("x" * (tpl.MAX_NAME_LEN + 1)) != "")
    check("校验：刚好上限通过", tpl.validate_name("x" * tpl.MAX_NAME_LEN) == "")
    for bad in ("a/b", "a\\b", "a:b", "a*b", "a?b", 'a"b', "a<b", "a>b", "a|b"):
        check(f"校验：非法字符 {bad!r} 被拒", tpl.validate_name(bad) != "")
    check("校验：正常中文名通过", tpl.validate_name("频段切换 001") == "")
    check("校验：清洗首尾与连续空白", tpl.normalize_name("  a \t b  ") == "a b",
          tpl.normalize_name("  a \t b  "))
    check("校验：保存时也拦非法名",
          tpl.save_template("a/b", state_of("z")) != "")


def test_reject_empty_state():
    setup_temp_store()
    check("保存：空参数集被拒", tpl.save_template("空", {}) != "")
    check("保存：非字典参数集被拒", tpl.save_template("空", "不是字典") != "")
    check("保存：被拒后没有产生条目", tpl.load_templates()[0] == [])


# ----------------------------------------------------------------------
# 3. 坏文件宽容
# ----------------------------------------------------------------------
def test_broken_file_is_tolerated():
    path = setup_temp_store()
    path.write_text("这不是 JSON {{{", encoding="utf-8")
    items, warn = tpl.load_templates()
    check("坏文件：非 JSON 返回空表", items == [], str(items))
    check("坏文件：给出可读原因", "JSON" in warn, warn)
    check("坏文件：不抛异常即可写入（保存后恢复）",
          tpl.save_template("救回来", state_of("ok")) == "")
    check("坏文件：保存后能取到", tpl.get_template("救回来") is not None)

    path.write_text("[1, 2, 3]", encoding="utf-8")
    items, warn = tpl.load_templates()
    check("坏文件：顶层是数组按空表处理", items == [], str(items))

    path.write_text("", encoding="utf-8")
    items, warn = tpl.load_templates()
    check("坏文件：空文件按空表处理且无告警", items == [] and warn == "", f"{items} / {warn}")

    path.write_text(json.dumps({"version": 1, "templates": [
        {"name": "", "state": {}},                       # 名字为空 → 跳过
        {"name": "好条目", "state": {"frame": {}}},       # 合法
        {"name": "缺 state"},                            # 没有 state → 跳过
        "不是对象",                                        # 非字典 → 跳过
    ]}, ensure_ascii=False), encoding="utf-8")
    items, warn = tpl.load_templates()
    check("坏文件：坏条目被跳过、好条目保留",
          [i["name"] for i in items] == ["好条目"], str([i["name"] for i in items]))
    check("坏文件：坏条目缺失字段被补默认值",
          items[0]["reference_hex"] == "" and items[0]["label"] == "",
          str(items[0]))


def test_missing_file_is_not_an_error():
    setup_temp_store()
    items, warn = tpl.load_templates()
    check("缺文件：返回空表", items == [])
    check("缺文件：不算告警", warn == "", warn)


# ----------------------------------------------------------------------
# 4. 原子写与上限
# ----------------------------------------------------------------------
def test_atomic_write_leaves_no_tmp():
    path = setup_temp_store()
    tpl.save_template("原子", state_of("a"))
    check("原子写：目标文件存在", path.exists())
    check("原子写：不残留 .tmp", not path.with_name(path.name + ".tmp").exists(),
          str(list(path.parent.iterdir())))
    check("原子写：内容是合法 JSON",
          isinstance(json.loads(path.read_text(encoding="utf-8")), dict))


def test_store_path_contract():
    tpl.store_path = _ORIGINAL_STORE_PATH
    path = tpl.store_path()
    check("路径：文件名固定", path.name == tpl.FILENAME, path.name)
    check("路径：位于应用数据目录（可写数据不与内置资源混放）",
          path.parent == tpl.app_paths.app_data_dir(), str(path.parent))


def test_max_templates_guard():
    setup_temp_store()
    original_max = tpl.MAX_TEMPLATES
    tpl.MAX_TEMPLATES = 3
    try:
        for index in range(3):
            check(f"上限：第 {index + 1} 个可存",
                  tpl.save_template(f"t{index}", state_of(str(index))) == "")
        error = tpl.save_template("t3", state_of("over"))
        check("上限：超出被拒", error != "", error)
        check("上限：被拒后条目数不变", len(tpl.load_templates()[0]) == 3)
        check("上限：覆盖已存在的名字不受上限影响",
              tpl.save_template("t0", state_of("rewrite")) == "")
    finally:
        tpl.MAX_TEMPLATES = original_max


def cleanup():
    tpl.store_path = _ORIGINAL_STORE_PATH
    if _TMP_DIR is not None and _TMP_DIR.exists():
        for child in _TMP_DIR.iterdir():
            try:
                child.unlink()
            except OSError:
                pass
        try:
            _TMP_DIR.rmdir()
        except OSError:
            pass


def main():
    tests = [value for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    try:
        for test in tests:
            test()
    finally:
        cleanup()
    print(f"检查项：{len(_CHECKS)} 项，失败 {len(_FAILURES)} 项")
    if _FAILURES:
        for item in _FAILURES:
            print(f"  [FAIL] {item}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
