# -*- coding: utf-8 -*-
"""南网查询页「自定义DI」增删测试（协议0）

覆盖：
- 纯逻辑：DI 字节校验 / DI 键解析 / 格式化（custom_di_store）
- 存储：读写往返、未知字段保留、非法内容容错、upsert 新增与覆盖、remove_keys 批量
- 沙箱：全程 monkeypatch app_paths.data_path 到临时目录，真实 custom_di.json 哈希不变
- GUI（offscreen）：协议0 查询页按钮走真实流程（新增落盘 + 表格 +1 且★标记、
  内置 DI 拒绝删除、多选批量删除、重建窗口后仍在）；简化版查询页 lookup_pages 同样可用
- 反例：全部提示文案中不出现「功能待实现」

运行：python test/test_nanwang_custom_di.py
"""

import hashlib
import io
import json
import os
import shutil
import sys
import tempfile

import _path_setup  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:  # Windows 控制台中文
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import app_paths  # noqa: E402
from custom_di_store import (  # noqa: E402
    custom_key_set,
    find_entry,
    format_key,
    key_of,
    load_custom_di,
    make_key,
    parse_hex_byte,
    remove_keys,
    save_custom_di,
    upsert_entry,
    validate_key_text,
)

PASS = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"[PASS] {name}")
    else:
        FAILURES.append(f"{name} :: {detail}")
        print(f"[FAIL] {name} :: {detail}")


def section(title):
    print(f"\n== {title} ==")


def file_md5(path):
    with open(path, "rb") as fp:
        return hashlib.md5(fp.read()).hexdigest()


class Sandbox:
    """临时数据目录沙箱（app_paths.data_path → tmpdir/<name>）。"""

    def __init__(self, entries=None, raw_text=None):
        self.entries = entries if entries is not None else []
        self.raw_text = raw_text
        self.tmp = None
        self._real = None

    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="nw_custom_di_")
        self.path = os.path.join(self.tmp, "custom_di.json")
        if self.raw_text is not None:
            with io.open(self.path, "w", encoding="utf-8") as fp:
                fp.write(self.raw_text)
        else:
            self.write(self.entries)
        self._real = app_paths.data_path
        app_paths.data_path = lambda name: __import__("pathlib").Path(
            os.path.join(self.tmp, name)
        )
        return self

    def write(self, entries):
        with io.open(self.path, "w", encoding="utf-8") as fp:
            json.dump(entries, fp, ensure_ascii=False, indent=2)

    def __exit__(self, *exc):
        app_paths.data_path = self._real
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False

# ── 1. 纯逻辑：DI 字节校验 ───────────────────────────────────────────

def t_parse_hex_byte():
    section("1. parse_hex_byte 单字节校验")
    check("'E8' → 232", parse_hex_byte("E8") == 232, repr(parse_hex_byte("E8")))
    check("'e8' 小写可用", parse_hex_byte("e8") == 232)
    check("' 8 ' 空白容忍", parse_hex_byte(" 8 ") == 8)
    check("'0' → 0（边界）", parse_hex_byte("0") == 0)
    check("'FF' → 255（边界）", parse_hex_byte("FF") == 255)
    check("'' → None", parse_hex_byte("") is None)
    check("None → None", parse_hex_byte(None) is None)
    check("'GG' → None", parse_hex_byte("GG") is None)
    check("'100' 超 2 位 → None", parse_hex_byte("100") is None)

    key, err = validate_key_text("E8", "00", "08", "03")
    check("validate_key_text 合法", key == (232, 0, 8, 3) and err == "",
          f"{key} / {err}")
    key2, err2 = validate_key_text("E8", "00", "GG", "03")
    check("非法 DI1 → key=None 且提示含 DI1",
          key2 is None and "DI1" in err2, f"{key2} / {err2}")


def t_key_helpers():
    section("2. DI 键解析 / 格式化")
    check("make_key", make_key(232, 0, 8, 3) == (232, 0, 8, 3))
    check("format_key 大写空格分隔", format_key((232, 0, 8, 3)) == "E8 00 08 03",
          format_key((232, 0, 8, 3)))
    check("key_of 正常条目",
          key_of({"di3": 232, "di2": 0, "di1": 8, "di0": 3}) == (232, 0, 8, 3))
    check("key_of 缺字段 → None", key_of({"di3": 232, "di2": 0}) is None)
    check("key_of 越界 → None",
          key_of({"di3": 232, "di2": 0, "di1": 8, "di0": 300}) is None)
    check("key_of 非 dict → None", key_of("x") is None)
    check("key_of 布尔视为非法",
          key_of({"di3": True, "di2": 0, "di1": 8, "di0": 3}) is None)


def t_store_roundtrip():
    section("3. 存储读写往返 / 未知字段保留 / 非法内容容错")
    real_md5 = file_md5(app_paths.data_path("custom_di.json"))
    seed = [
        {"di3": 232, "di2": 0, "di1": 8, "di0": 3, "desc": "查询采集任务号",
         "extra": "KEEP", "nested": {"a": 1}},
        {"di3": 234, "di2": 3, "di1": 3, "di0": 32, "desc": "查询当前工作频段"},
    ]
    with Sandbox(seed) as sb:
        loaded = load_custom_di()
        check("读取条目数", len(loaded) == 2, str(loaded))
        check("未知字段保留（桶式读改写）",
              loaded[0].get("extra") == "KEEP" and loaded[0].get("nested") == {"a": 1},
              str(loaded[0]))
        check("custom_key_set",
              custom_key_set(loaded) == {(232, 0, 8, 3), (234, 3, 3, 32)},
              str(custom_key_set(loaded)))

        loaded.append({"di3": 1, "di2": 2, "di1": 3, "di0": 4, "desc": "新条目"})
        save_custom_di(loaded)
        again = load_custom_di()
        check("写回后条目数 +1", len(again) == 3, str(len(again)))
        check("写回后中文不转义",
              "查询采集任务号" in io.open(sb.path, encoding="utf-8").read())

    with Sandbox(raw_text="{ 这不是 JSON") as sb2:
        check("非法 JSON → 空列表不抛异常", load_custom_di() == [], str(load_custom_di()))
        check("非法 JSON 沙箱文件仍在", os.path.exists(sb2.path))
    with Sandbox(raw_text='{"a": 1}') as sb3:
        check("非列表 JSON → 空列表", load_custom_di() == [], str(load_custom_di()))
        check("非列表沙箱文件仍在", os.path.exists(sb3.path))
    with Sandbox(raw_text='[1, "x", {"di3": 1, "di2": 2, "di1": 3, "di0": 4, "desc": "d"}]'):
        items = load_custom_di()
        check("非 dict 项被过滤、合法项保留", len(items) == 1, str(items))
        check("缺字段条目 key_of 返回 None（不抛异常）", key_of({"di3": 1}) is None)
    check("真实 custom_di.json 未被写坏",
          file_md5(app_paths.data_path("custom_di.json")) == real_md5)


def t_upsert_remove():
    section("4. upsert_entry 新增 / 覆盖（保留未知字段）")
    base = [{"di3": 232, "di2": 0, "di1": 8, "di0": 3, "desc": "旧名", "extra": "KEEP"}]
    added, replaced = upsert_entry(base, (234, 3, 3, 32), "新增")
    check("新增：replaced=False", replaced is False)
    check("新增：条目 +1", len(added) == 2, str(added))
    check("新增：原列表不被就地修改（纯函数）", len(base) == 1, str(base))
    check("新增：新条目字段齐备",
          find_entry(added, (234, 3, 3, 32))
          == {"di3": 234, "di2": 3, "di1": 3, "di0": 32, "desc": "新增"},
          str(find_entry(added, (234, 3, 3, 32))))

    updated, replaced2 = upsert_entry(base, (232, 0, 8, 3), "新名")
    check("覆盖：replaced=True", replaced2 is True)
    check("覆盖：条目数不变", len(updated) == 1, str(updated))
    check("覆盖：desc 已更新", find_entry(updated, (232, 0, 8, 3))["desc"] == "新名")
    check("覆盖：未知字段仍在",
          find_entry(updated, (232, 0, 8, 3))["extra"] == "KEEP")

    section("5. remove_keys 批量删除")
    entries = [
        {"di3": 1, "di2": 0, "di1": 0, "di0": 1, "desc": "a"},
        {"di3": 2, "di2": 0, "di1": 0, "di0": 2, "desc": "b"},
        {"di3": 3, "di2": 0, "di1": 0, "di0": 3, "desc": "c"},
    ]
    left, removed = remove_keys(entries, [(1, 0, 0, 1)])
    check("删单个：removed=1", removed == 1, str(removed))
    check("删单个：余 2 条", len(left) == 2, str(left))
    left2, removed2 = remove_keys(entries, [(1, 0, 0, 1), (3, 0, 0, 3), (9, 9, 9, 9)])
    check("批量：命中 2 条（不存在的不计数）", removed2 == 2, str(removed2))
    check("批量：余 1 条且为 b", len(left2) == 1 and left2[0]["desc"] == "b", str(left2))
    check("remove_keys 不改原列表", len(entries) == 3, str(entries))


def t_store_sandbox_only():
    section("6. 沙箱隔离（真身文件零改动）")
    real = app_paths.data_path("custom_di.json")
    real_md5 = file_md5(real)
    with Sandbox([]) as sb:
        save_custom_di([{"di3": 9, "di2": 9, "di1": 9, "di0": 9, "desc": "临时"}])
        check("沙箱内写入生效", len(load_custom_di()) == 1, str(load_custom_di()))
        check("沙箱路径 ≠ 真身路径",
              os.path.abspath(sb.path) != os.path.abspath(str(real)))
    check("退出沙箱后真身哈希不变", file_md5(real) == real_md5)
    check("退出沙箱后 data_path 已还原",
          os.path.abspath(str(app_paths.data_path("custom_di.json")))
          == os.path.abspath(str(real)))


# ── 7. GUI：MessageBox / 对话框替身 ─────────────────────────────────

class FakeMessageBox:
    """QMessageBox 替身：记录全部文案，question 结果可配置（默认 Yes）。"""

    def __init__(self, real):
        self.Yes = real.Yes
        self.No = real.No
        self.Ok = real.Ok
        self.Cancel = real.Cancel
        self.answer = real.Yes
        self.messages = []  # [(kind, text)]

    def question(self, parent, title, text, *args, **kwargs):
        self.messages.append(("question", text))
        return self.answer

    def warning(self, parent, title, text, *args, **kwargs):
        self.messages.append(("warning", text))
        return self.Ok

    def information(self, parent, title, text, *args, **kwargs):
        self.messages.append(("information", text))
        return self.Ok

    def critical(self, parent, title, text, *args, **kwargs):
        self.messages.append(("critical", text))
        return self.Ok

    def all_text(self):
        return " | ".join(text for _kind, text in self.messages)

    def clear(self):
        self.messages = []


def _make_fake_dialog(qdialog, qlineedit):
    """QDialog 替身：exec() 不阻塞，按 script 依次填入输入框并返回 Accepted。"""

    class _FakeDialog(qdialog):
        script = None
        instances = []

        def __init__(self, parent=None):
            super().__init__(parent)
            _FakeDialog.instances.append(self)

        def exec(self):
            if self.script:
                for box, value in zip(self.findChildren(qlineedit), self.script):
                    box.setText(value)
            return qdialog.Accepted

    return _FakeDialog


#: 预置自定义条目（沙箱初始 custom_di.json）
SEED_CUSTOM = [
    {"di3": 234, "di2": 3, "di1": 3, "di0": 32, "desc": "预置自定义条"},
]
#: 测试新增的 DI：E8 00 09 01（内置表中不存在）
NEW_TEXTS = ["E8", "00", "09", "01"]
NEW_KEY = (0xE8, 0x00, 0x09, 0x01)


def t_gui_mainwindow():
    section("7. GUI（offscreen）：协议0 查询页 添加/删除 走真实流程")
    from PySide6.QtWidgets import (
        QApplication,
        QDialog,
        QLineEdit,
        QMessageBox,
        QPushButton,
        QTableWidget,
        QTableWidgetSelectionRange,
    )

    app = QApplication.instance() or QApplication([])
    import main_gui
    import lookup_pages

    real_file = app_paths.data_path("custom_di.json")
    real_md5 = file_md5(real_file)
    real_mb_main = main_gui.QMessageBox
    real_dlg_main = main_gui.QDialog
    real_mb_lp = lookup_pages.QMessageBox
    fake_mb = FakeMessageBox(QMessageBox)
    fake_dialog = _make_fake_dialog(QDialog, QLineEdit)
    main_gui.QMessageBox = fake_mb
    main_gui.QDialog = fake_dialog
    lookup_pages.QMessageBox = fake_mb

    windows = []
    try:
        with Sandbox(SEED_CUSTOM):
            w = main_gui.MainWindow()
            windows.append(w)
            w.protocol_combo.setCurrentIndex(0)
            app.processEvents()
            check("协议0 查询页已建 DI 表（>100 行）",
                  w.di_table.rowCount() > 100, str(w.di_table.rowCount()))
            # 页面重建时旧按钮走 deleteLater 延迟销毁（AGENTS 陷阱#1 的
            # _clear_layout 时序），先冲掉 DeferredDelete 再找按钮，避免偶发残留
            from PySide6.QtCore import QEvent

            app.sendPostedEvents(None, QEvent.DeferredDelete)
            app.processEvents()
            btns = [
                b
                for b in w.protocol_lookup_tab.findChildren(QPushButton)
                if b.text() in ("添加自定义DI", "删除选中自定义DI")
            ]
            adds = [b for b in btns if b.text() == "添加自定义DI"]
            dels = [b for b in btns if b.text() == "删除选中自定义DI"]
            check("两个按钮存在（当前页取最后一对）", bool(adds) and bool(dels),
                  str([b.text() for b in btns]))
            add_btn = adds[-1]
            del_btn = dels[-1]
            check("DI 表支持多选（批量删除前提）",
                  w.di_table.selectionMode()
                  == QTableWidget.SelectionMode.ExtendedSelection,
                  str(w.di_table.selectionMode()))
            check("预置自定义条目已在表中标记 ★",
                  any(item[7] for item in w._di_data))

            rows0 = w.di_table.rowCount()
            fake_mb.clear()
            fake_dialog.script = NEW_TEXTS + ["新增测试条"]
            add_btn.click()
            app.processEvents()
            entry = find_entry(load_custom_di(), NEW_KEY)
            check("新增：已写入沙箱 custom_di.json", entry is not None, str(load_custom_di()))
            check("新增：表格行数 +1", w.di_table.rowCount() == rows0 + 1,
                  f"{rows0} → {w.di_table.rowCount()}")
            row = next(
                (i for i, item in enumerate(w._di_data)
                 if (item[0], item[1], item[2], item[3]) == NEW_KEY),
                -1,
            )
            check("新增：该行标 ★ 且在表内",
                  row >= 0 and w.di_table.item(row, 5).text().startswith("★"),
                  str(w.di_table.item(row, 5).text()) if row >= 0 else "row=-1")
            check("新增：提示文案含「已添加自定义DI」",
                  "已添加自定义DI" in fake_mb.all_text(), fake_mb.all_text())

            # 重复 DI → 覆盖确认（Yes）
            fake_mb.answer = QMessageBox.Yes
            fake_dialog.script = NEW_TEXTS + ["改后的名字"]
            add_btn.click()
            app.processEvents()
            check("重复 DI：确认后覆盖含义",
                  find_entry(load_custom_di(), NEW_KEY)["desc"] == "改后的名字",
                  str(find_entry(load_custom_di(), NEW_KEY)))
            check("重复 DI：行数不增（覆盖非新增）",
                  w.di_table.rowCount() == rows0 + 1, str(w.di_table.rowCount()))
            check("重复 DI：提示文案含「已覆盖自定义DI」",
                  "已覆盖自定义DI" in fake_mb.all_text(), fake_mb.all_text())

            # 重复 DI → 放弃覆盖（No）
            fake_mb.answer = QMessageBox.No
            fake_dialog.script = NEW_TEXTS + ["不该写入"]
            add_btn.click()
            app.processEvents()
            check("重复 DI：放弃覆盖 → 含义不变",
                  find_entry(load_custom_di(), NEW_KEY)["desc"] == "改后的名字",
                  str(find_entry(load_custom_di(), NEW_KEY)))
            fake_mb.answer = QMessageBox.Yes

            # 非法 DI 码
            fake_mb.clear()
            fake_dialog.script = ["GZ", "00", "09", "01", "非法"]
            add_btn.click()
            app.processEvents()
            check("非法 DI 码被拒（提示含「十六进制」）",
                  "十六进制" in fake_mb.all_text(), fake_mb.all_text())
            check("非法输入不落盘", len(load_custom_di()) == 2, str(load_custom_di()))

            # 空含义
            fake_mb.clear()
            fake_dialog.script = ["E8", "00", "09", "02", "   "]
            add_btn.click()
            app.processEvents()
            check("空含义被拒（提示含「中文含义」）",
                  "中文含义" in fake_mb.all_text(), fake_mb.all_text())

            # 内置 DI 拒绝删除
            builtin_row = next(i for i, item in enumerate(w._di_data) if not item[7])
            w.di_table.clearSelection()
            w.di_table.setRangeSelected(
                QTableWidgetSelectionRange(builtin_row, 0, builtin_row, 5), True
            )
            fake_mb.clear()
            del_btn.click()
            app.processEvents()
            check("内置 DI 删除被拒（提示含「均为内置DI」）",
                  "均为内置DI" in fake_mb.all_text(), fake_mb.all_text())
            check("内置拒绝后文件条目数不变", len(load_custom_di()) == 2,
                  str(load_custom_di()))

            # 未选中
            w.di_table.clearSelection()
            fake_mb.clear()
            del_btn.click()
            app.processEvents()
            check("未选中提示（含「请先选中」）",
                  "请先选中" in fake_mb.all_text(), fake_mb.all_text())

            # 多选批量删除（预置 + 新增）
            custom_rows = [i for i, item in enumerate(w._di_data) if item[7]]
            check("自定义行共 2 条（预置 + 新增）", len(custom_rows) == 2,
                  str(custom_rows))
            w.di_table.clearSelection()
            for r in custom_rows:
                w.di_table.setRangeSelected(
                    QTableWidgetSelectionRange(r, 0, r, 5), True
                )
            check("多选命中 2 行",
                  len(w.di_table.selectionModel().selectedRows()) == 2,
                  str(len(w.di_table.selectionModel().selectedRows())))
            fake_mb.clear()
            del_btn.click()
            app.processEvents()
            check("批量删除：文件清空", load_custom_di() == [], str(load_custom_di()))
            check("批量删除：表格行数 -2",
                  w.di_table.rowCount() == rows0 - 1, str(w.di_table.rowCount()))
            check("批量删除：提示带条数「已删除 2 条自定义DI」",
                  "已删除 2 条自定义DI" in fake_mb.all_text(), fake_mb.all_text())

            # 重启保持：重新添加后新建窗口
            fake_dialog.script = NEW_TEXTS + ["重启后仍在"]
            add_btn.click()
            app.processEvents()
            w2 = main_gui.MainWindow()
            windows.append(w2)
            w2.protocol_combo.setCurrentIndex(0)
            app.processEvents()
            row2 = next(
                (i for i, item in enumerate(w2._di_data)
                 if (item[0], item[1], item[2], item[3]) == NEW_KEY),
                -1,
            )
            check("重建窗口后自定义 DI 仍在（★）",
                  row2 >= 0 and w2.di_table.item(row2, 5).text().startswith("★"),
                  str(row2))
            check("重建窗口后文件内容保持",
                  find_entry(load_custom_di(), NEW_KEY)["desc"] == "重启后仍在",
                  str(find_entry(load_custom_di(), NEW_KEY)))

            check("全程提示文案无「待实现」",
                  "待实现" not in fake_mb.all_text(), fake_mb.all_text())
    finally:
        for win in windows:
            try:
                win.close()
            except Exception:
                pass
        main_gui.QMessageBox = real_mb_main
        main_gui.QDialog = real_dlg_main
        lookup_pages.QMessageBox = real_mb_lp
    check("真实 custom_di.json 哈希不变", file_md5(real_file) == real_md5)


# ── 8. 简化版查询页（lookup_pages）同名按钮同样可用 ──────────────────

def t_gui_lookup_pages():
    section("8. lookup_pages 简化版查询页：按钮走同一份实现")
    from PySide6.QtWidgets import (
        QApplication,
        QDialog,
        QLineEdit,
        QMessageBox,
        QPushButton,
        QTableWidgetSelectionRange,
        QWidget,
    )

    app = QApplication.instance() or QApplication([])
    import lookup_pages

    real_mb = lookup_pages.QMessageBox
    real_dlg = lookup_pages.QDialog
    fake_mb = FakeMessageBox(QMessageBox)
    fake_dialog = _make_fake_dialog(QDialog, QLineEdit)
    lookup_pages.QMessageBox = fake_mb
    lookup_pages.QDialog = fake_dialog
    try:
        with Sandbox([]):
            from parser_registry import get_parser

            parent = QWidget()
            widget, table, di_data, stats_label = lookup_pages.create_di_lookup_page(
                parent, get_parser("south")
            )
            check("页面构建成功且表格有数据", table.rowCount() > 100,
                  str(table.rowCount()))
            check("返回的 di_data 与表格行数一致（构建时快照）",
                  len(di_data) == table.rowCount(),
                  f"{len(di_data)} vs {table.rowCount()}")
            btns = [
                b for b in widget.findChildren(QPushButton)
                if b.text() in ("添加自定义DI", "删除选中自定义DI")
            ]
            check("两个按钮存在", len(btns) == 2, str([b.text() for b in btns]))
            add_btn = next(b for b in btns if b.text() == "添加自定义DI")
            del_btn = next(b for b in btns if b.text() == "删除选中自定义DI")

            def starred_rows():
                """表格中 ★ 自定义行（di_data 是构建时快照，刷新后需读表）"""
                return [
                    r for r in range(table.rowCount())
                    if table.item(r, 5) is not None
                    and table.item(r, 5).text().startswith("★")
                ]

            rows0 = table.rowCount()
            starred0 = starred_rows()
            key_a = (0xE8, 0x00, 0x0A, 0x01)
            key_b = (0xE8, 0x00, 0x0A, 0x02)
            # ① 直接调用共享实现
            ok = lookup_pages.apply_custom_di_add(
                parent, "E8", "00", "0A", "01", "简化页新增",
                on_changed=lambda: None,
            )
            check("简化页：apply 返回 True 且写入沙箱 JSON",
                  ok is True and find_entry(load_custom_di(), key_a) is not None,
                  str(load_custom_di()))
            # ② 走按钮自身的回调（对话框 + 刷新表格）
            fake_mb.clear()
            fake_dialog.script = ["E8", "00", "0A", "02", "简化页按钮新增"]
            add_btn.click()
            app.processEvents()
            check("简化页：按钮新增已落盘",
                  find_entry(load_custom_di(), key_b) is not None,
                  str(load_custom_di()))
            check("简化页：表格行数 +2",
                  table.rowCount() == rows0 + 2,
                  f"{rows0} → {table.rowCount()}")
            starred2 = starred_rows()
            check("简化页：★ 行 +2（表格已按新数据刷新）",
                  len(starred2) == len(starred0) + 2,
                  f"{starred0} → {starred2}")
            check("简化页：按钮新增无「待实现」文案",
                  "待实现" not in fake_mb.all_text(), fake_mb.all_text())

            # ③ 多选批量删除（选中全部 ★ 行）
            table.clearSelection()
            for r in starred2:
                table.setRangeSelected(
                    QTableWidgetSelectionRange(r, 0, r, 5), True
                )
            check("简化页：多选命中全部 ★ 行",
                  len(table.selectionModel().selectedRows()) == len(starred2),
                  f"{len(table.selectionModel().selectedRows())} vs {len(starred2)}")
            fake_mb.clear()
            del_btn.click()
            app.processEvents()
            check("简化页：批量删除后 JSON 清空", load_custom_di() == [],
                  str(load_custom_di()))
            check("简化页：删除后无 ★ 行", starred_rows() == [], str(starred_rows()))
    finally:
        lookup_pages.QMessageBox = real_mb
        lookup_pages.QDialog = real_dlg


# ── 9. 源码层反向验证：不再存在「功能待实现」死按钮 ─────────────────

def t_no_dead_button_text():
    section("9. 源码中不再有「功能待实现」死按钮")
    import lookup_pages

    source = io.open(lookup_pages.__file__, encoding="utf-8").read()
    check("lookup_pages.py 无「待实现」字样", "待实现" not in source)
    for name in (
        "add_custom_di_interactive",
        "apply_custom_di_add",
        "delete_selected_custom_di_interactive",
    ):
        check(f"lookup_pages 导出 {name}", hasattr(lookup_pages, name))

    import main_gui

    gui_source = io.open(main_gui.__file__, encoding="utf-8").read()
    # main_gui 的 CHANGELOG 叙述里会提到旧死按钮，因此只精确匹配旧死按钮文案
    check("main_gui.py 无「待实现」死按钮文案",
          "添加自定义DI功能待实现" not in gui_source
          and "删除自定义DI功能待实现" not in gui_source)
    check("main_gui 复用 lookup_pages.apply_custom_di_add",
          "apply_custom_di_add" in gui_source)
    check("main_gui 复用 lookup_pages.delete_selected_custom_di_interactive",
          "delete_selected_custom_di_interactive" in gui_source)


def main():
    t_parse_hex_byte()
    t_key_helpers()
    t_store_roundtrip()
    t_upsert_remove()
    t_store_sandbox_only()
    t_gui_mainwindow()
    t_gui_lookup_pages()
    t_no_dead_button_text()
    print(f"\n=== {PASS} 项通过，{len(FAILURES)} 项失败 ===")
    for item in FAILURES:
        print("  ✗", item)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())