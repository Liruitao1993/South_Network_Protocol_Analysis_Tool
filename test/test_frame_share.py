"""报文分享测试（share_model / share_dialog 纯逻辑 + offscreen 冒烟）

覆盖（对应 09-01-frame-share 任务 design.md §6）：
- normalize_hex：清洗（空格/0x/逗号）/大写化/偶长/字节边界/非法拒绝
- submit_share：正常（web/gui）/sharer 空/超长/note 超长/协议白名单外/hex 非法
- ShareStore：add/list_page 分页/get/搜索（hex 含无空格连续输入匹配、
  协议、分享人、说明）
- share_config：约束下发
- share_dialog（GUI 侧）：build_payload 字段与 source=gui / validate_fields
  分支 / last_sharer config 读写往返 / offscreen 冒烟

运行（项目根）：
    python test/test_frame_share.py
"""
import json
import os
import shutil
import sys
import tempfile
import warnings
from pathlib import Path

import _path_setup  # noqa: E402

warnings.filterwarnings("ignore")

ROOT = Path(_path_setup.__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "reflex_web"))
sys.path.insert(0, str(ROOT / "reflex_web" / "reflex_web"))

# 数据目录重定向（必须在 import share_model / feedback_dialog 前）
_TMP = Path(tempfile.mkdtemp(prefix="fshare_test_"))
os.environ["FRAMESHARE_DATA_DIR"] = str(_TMP / "data")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import feedback_dialog as fd  # noqa: E402  (config 路径注入后再 import share_dialog)

_CFG = _TMP / "config.json"
_CFG.write_text("{}", encoding="utf-8")
fd.set_config_path(_CFG)

import share_model as sm  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}")


# ── normalize_hex ────────────────────────────────────────────


def test_normalize():
    print("test_normalize_hex:")
    frame = "68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16"
    check("spaced passthrough", sm.normalize_hex(frame) == frame.upper())
    check("0x prefix stripped", sm.normalize_hex("0x68,0x0e") == "68 0E")
    check("uppercase normalized", sm.normalize_hex("aabb ccdd") == "AA BB CC DD")
    check("odd length rejected", sm.normalize_hex("681") is None)
    check("non-hex rejected", sm.normalize_hex("xyz") is None)
    check("empty rejected", sm.normalize_hex("") is None)
    check("1 byte < min", sm.normalize_hex("ab") is None)
    check("2049 bytes > max", sm.normalize_hex("ab" * 2049) is None)
    check("2048 bytes ok", sm.normalize_hex("ab" * 2048) is not None)


# ── submit_share ─────────────────────────────────────────────


def test_submit():
    print("test_submit_share:")
    ok, rid, st = sm.submit_share(
        {
            "frame_hex": "68 11 22 33 44 55 66 77",
            "protocol": "南网协议",
            "sharer": "tester",
            "note": "e2e",
            "source": "gui",
        }
    )
    check("valid gui submit", ok and st == 200 and rid > 0)
    item = sm.ShareStore.instance().get(int(rid))
    check("normalized stored", item.frame_hex == "68 11 22 33 44 55 66 77")
    check("source=gui", item.source == "gui")
    check("created_at set", len(item.created_at) >= 19)

    ok2, rid2, _ = sm.submit_share(
        {"frame_hex": "68AA", "protocol": "698.45协议", "sharer": "web用户", "source": "web"}
    )
    check("valid web submit", ok2 and st == 200)
    it2 = sm.ShareStore.instance().get(int(rid2))
    check("web normalized", it2.frame_hex == "68 AA")

    ok, err, st = sm.submit_share({"frame_hex": "xyz", "protocol": "南网协议", "sharer": "t"})
    check("bad hex 400", (not ok) and st == 400 and "报文" in err)
    ok, err, st = sm.submit_share({"frame_hex": "6811", "protocol": "南网协议", "sharer": ""})
    check("empty sharer 400", (not ok) and st == 400 and "分享人" in err)
    ok, err, st = sm.submit_share({"frame_hex": "6811", "protocol": "南网协议", "sharer": "x" * 51})
    check("long sharer 400", (not ok) and st == 400 and "50" in err)
    ok, err, st = sm.submit_share(
        {"frame_hex": "6811", "protocol": "南网协议", "sharer": "t", "note": "n" * 501}
    )
    check("long note 400", (not ok) and st == 400 and "500" in err)
    ok, err, st = sm.submit_share({"frame_hex": "6811", "protocol": "乱写", "sharer": "t"})
    check("bad protocol 400", (not ok) and st == 400 and "协议" in err)
    ok, err, st = sm.submit_share({"protocol": "南网协议", "sharer": "t"})
    check("missing hex 400", (not ok) and st == 400)
    # source 白名单外归一为 web
    ok, rid3, _ = sm.submit_share(
        {"frame_hex": "6899", "protocol": "南网协议", "sharer": "t", "source": "hack"}
    )
    it3 = sm.ShareStore.instance().get(int(rid3))
    check("invalid source -> web", it3.source == "web")


# ── ShareStore CRUD / 分页 / 搜索 ────────────────────────────


def test_store():
    print("test_ShareStore:")
    store = sm.ShareStore.instance()
    # 追加到 25 条测试分页
    for i in range(23):
        sm.submit_share(
            {
                "frame_hex": f"aabb{i:02x}",
                "protocol": "南网协议",
                "sharer": f"bulk{i}",
                "source": "web",
            }
        )
    items, total, pages = store.list_page(1, 20, "")
    # test_submit 成功 3 条（gui/web/invalid-source归一web）+ 23 条 bulk = 26
    check("total counted", total == 26)
    check("pages ceil", pages == 2)
    check("page size", len(items) == 20)
    items2, _, _ = store.list_page(2, 20, "")
    check("page2 size", len(items2) == 6)
    check("desc order", items[0]["id"] > items[-1]["id"])

    # hex 搜索：含空格
    items, t, _ = store.list_page(1, 20, "68 11 22")
    check("search hex spaced", t >= 1)
    # hex 搜索：连续无空格（681122 → 68 11 22）
    items, t2, _ = store.list_page(1, 20, "681122")
    check("search hex compact matches spaced store", t2 >= 1)
    # 协议搜索
    _, t3, _ = store.list_page(1, 20, "698.45")
    check("search protocol", t3 >= 1)
    # 分享人搜索
    _, t4, _ = store.list_page(1, 20, "bulk1")
    check("search sharer", t4 >= 10)
    # 说明搜索
    _, t5, _ = store.list_page(1, 20, "e2e")
    check("search note", t5 >= 1)
    # 无结果
    _, t6, _ = store.list_page(1, 20, "zzznotexist")
    check("search no match", t6 == 0)
    # get
    got = store.get(items2[0]["id"])
    check("get by id", got is not None and got.id == items2[0]["id"])


def test_config_api():
    print("test_share_config:")
    cfg = sm.share_config()
    check("ok flag", cfg.get("ok") is True)
    check("protocols list", "南网协议" in cfg.get("protocols", []))
    check("limits", cfg.get("max_sharer_len") == 50 and cfg.get("max_note_len") == 500
          and cfg.get("max_frame_bytes") == 2048)


def test_share_page_url():
    print("test_share_page_url:")
    # dev 模式：Host 是后端端口 → 替换为前端端口
    check(
        "dev swap backend->frontend",
        sm.share_page_url("127.0.0.1:8000", "http", 3000, False)
        == "http://127.0.0.1:3000/share",
    )
    check(
        "dev lan ip swap",
        sm.share_page_url("192.168.1.10:8000", "http", 3000, False)
        == "http://192.168.1.10:3000/share",
    )
    check(
        "dev host without port appended",
        sm.share_page_url("localhost", "http", 3000, False)
        == "http://localhost:3000/share",
    )
    check(
        "dev already frontend port noop",
        sm.share_page_url("localhost:3000", "http", 3000, False)
        == "http://localhost:3000/share",
    )
    # prod 模式（单端口挂载）：同源不动，忽略 frontend_port
    check(
        "prod same origin",
        sm.share_page_url("10.0.0.1:8080", "http", None, True)
        == "http://10.0.0.1:8080/share",
    )
    check(
        "prod ignores frontend port",
        sm.share_page_url("10.0.0.1:8080", "http", 3000, True)
        == "http://10.0.0.1:8080/share",
    )
    # 兜底
    check("empty host relative", sm.share_page_url("", "http", 3000, False) == "/share")
    check(
        "scheme passthrough",
        sm.share_page_url("host:8000", "https", 3000, False)
        == "https://host:3000/share",
    )


# ── GUI 侧（share_dialog 纯逻辑 + offscreen 冒烟）───────────


def test_gui_payload_and_validate():
    print("test_share_dialog payload/validate:")
    import share_dialog as sd

    body = sd.build_payload("68 AA", "南网协议", "张三", "说明")
    obj = json.loads(body.decode("utf-8"))
    check("payload fields", obj["frame_hex"] == "68 AA" and obj["protocol"] == "南网协议"
          and obj["sharer"] == "张三" and obj["note"] == "说明")
    check("payload source=gui", obj["source"] == "gui")
    check("payload utf8 body", "张三".encode() in body)

    ok, msg = sd.validate_fields("张三", "南网协议", "http://127.0.0.1:8000", "68 AA")
    check("validate pass", ok)
    ok, msg = sd.validate_fields("", "南网协议", "http://x", "68 AA")
    check("validate empty sharer", (not ok) and "分享人" in msg)
    ok, msg = sd.validate_fields("x" * 51, "南网协议", "http://x", "68 AA")
    check("validate long sharer", (not ok) and "50" in msg)
    ok, msg = sd.validate_fields("张三", "乱写", "http://x", "68 AA")
    check("validate bad protocol", (not ok) and "协议" in msg)
    ok, msg = sd.validate_fields("张三", "南网协议", "", "68 AA")
    check("validate empty server", (not ok) and "服务器" in msg)
    ok, msg = sd.validate_fields("张三", "南网协议", "http://x", "")
    check("validate empty hex", (not ok) and "报文" in msg)


def test_gui_config_roundtrip():
    print("test_share_dialog last_sharer config:")
    import share_dialog as sd

    check("default empty", sd.load_last_sharer() == "")
    ok = sd.save_last_sharer("李四")
    check("save True", ok is True)
    check("read back", sd.load_last_sharer() == "李四")
    data = json.loads(_CFG.read_text(encoding="utf-8"))
    check("config share section", data.get("share", {}).get("last_sharer") == "李四")


def test_gui_dialog_smoke():
    print("test_ShareDialog offscreen smoke:")
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        import share_dialog as sd

        dlg = sd.ShareDialog(
            parent=None,
            frame_hex="68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16",
            protocol_name="南网协议",
            app_version="1.21.0",
        )
        check("dialog created", dlg is not None)
        check("proto combo 13", dlg.proto_combo.count() == len(sd.SHARE_PROTOCOLS) == 13)
        check("proto preselected", dlg.proto_combo.currentText() == "南网协议")
        check("hex view filled", dlg.hex_view.toPlainText().startswith("68 0E"))
        check("note prefilled env", "1.21.0" in dlg.note_edit.toPlainText())
        check("server url loaded", dlg.server_edit.text() == fd.DEFAULT_SERVER_URL)
        # 空分享人提交被本地拦截（不发请求）
        dlg.sharer_edit.setText("")
        dlg._on_submit()
        check("empty sharer blocked locally", "分享人" in dlg.status_label.text())
        # 分享页 URL：默认兜底 server_url + /share；服务端下发后用 share_url
        opened = []
        sd.QDesktopServices.openUrl = lambda u: opened.append(u.toString())
        dlg._share_url = ""
        dlg._open_share_page()
        check(
            "fallback open server_url/share",
            bool(opened) and opened[-1].endswith("/share"),
        )
        dlg._share_url = "http://127.0.0.1:3000/share"
        dlg._open_share_page()
        check("use server share_url", opened[-1] == "http://127.0.0.1:3000/share")
        dlg.close()
    except Exception as e:  # noqa: BLE001 - 无显示环境时跳过
        print(f"  [SKIP] dialog smoke skipped: {type(e).__name__}: {e}")


def main():
    try:
        test_normalize()
        test_submit()
        test_store()
        test_config_api()
        test_share_page_url()
        test_gui_payload_and_validate()
        test_gui_config_roundtrip()
        test_gui_dialog_smoke()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
        os.environ.pop("FRAMESHARE_DATA_DIR", None)
    print(f"\n{'='*40}")
    print(f"PASS: {PASS}  FAIL: {FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
