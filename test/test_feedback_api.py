"""问题反馈 HTTP API 服务端逻辑测试（feedback_model.submit_from_api / parse_multipart / 限流）

覆盖：
- submit_from_api：无图正常提交（source=gui）、带截图提交、非法类型/空描述/超长/缺协议、
  非法截图（非图片字节/错误扩展名/超 5MB/超过 3 张）回滚不留脏文件、sys_info 落库
- parse_multipart：multipart/form-data 二进制安全往返（文本字段 + 中文 + 二进制图片字节）
- FeedbackRateLimiter：60s 窗口内第 6 次拒绝
- 旧库迁移：无 source/sys_info 列的老库打开后自动补列

运行（项目根）：
    python test/test_feedback_api.py
"""

import os
import sys
import tempfile
from pathlib import Path

import _path_setup  # noqa: F401,E402

ROOT = Path(_path_setup.__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="fb_api_test_"))
os.environ["FEEDBACK_DATA_DIR"] = str(_TMP / "data")

from reflex_web import feedback_model as fm  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40


def main():
    fm.FeedbackStore.reset()
    store = fm.FeedbackStore.instance()

    print("== submit_from_api：正常提交 ==")
    ok, rid, st = fm.submit_from_api(
        {
            "issue_type": "功能异常",
            "protocol": "南网协议",
            "description": "API 无图测试",
            "contact": "qq123",
            "sys_info": "软件版本: 1.20.0",
            "source": "gui",
        },
        [],
    )
    check("无图提交成功", ok and st == 200, f"got {ok},{rid},{st}")
    item = store.get(int(rid))
    check("落库 source=gui", item is not None and item.source == "gui",
          f"source={getattr(item, 'source', None)}")
    check("sys_info 落库", item is not None and "1.20.0" in (item.sys_info or ""))
    check("contact 落库", item is not None and item.contact == "qq123")

    print("== submit_from_api：带截图 ==")
    ok2, rid2, st2 = fm.submit_from_api(
        {"issue_type": "解析错误", "protocol": "698.45协议", "description": "带图测试"},
        [("shot.png", PNG)],
    )
    check("带图提交成功", ok2 and st2 == 200, f"got {ok2},{rid2},{st2}")
    item2 = store.get(int(rid2))
    check("截图文件名落库", item2 is not None and bool(item2.screenshots),
          f"screenshots={getattr(item2, 'screenshots', None)}")
    up = fm.uploads_dir()
    check("截图文件落盘", up.exists() and any(p.suffix == ".png" for p in up.iterdir()))
    # 默认 source
    ok3, rid3, st3 = fm.submit_from_api(
        {"issue_type": "其他", "protocol": "不确定", "description": "默认source"}, []
    )
    item3 = store.get(int(rid3))
    check("缺省 source=gui", item3 is not None and item3.source == "gui")

    print("== submit_from_api：字段校验 ==")
    ok, msg, st = fm.submit_from_api(
        {"issue_type": "瞎写", "protocol": "南网协议", "description": "x"}, []
    )
    check("非法类型 400", not ok and st == 400, f"got {ok},{st},{msg}")
    ok, msg, st = fm.submit_from_api(
        {"issue_type": "功能异常", "protocol": "南网协议", "description": "   "}, []
    )
    check("空描述 400", not ok and st == 400, f"got {ok},{st}")
    ok, msg, st = fm.submit_from_api(
        {"issue_type": "功能异常", "protocol": "", "description": "x"}, []
    )
    check("缺协议 400", not ok and st == 400, f"got {ok},{st}")
    ok, msg, st = fm.submit_from_api(
        {"issue_type": "功能异常", "protocol": "p", "description": "x" * 2001}, []
    )
    check("描述超长 400", not ok and st == 400, f"got {ok},{st}")
    ok, msg, st = fm.submit_from_api(
        {"issue_type": "功能异常", "protocol": "p", "description": "x",
         "contact": "c" * 101},
        [],
    )
    check("联系方式超长 400", not ok and st == 400, f"got {ok},{st}")
    ok, msg, st = fm.submit_from_api(
        {"issue_type": "功能异常", "protocol": "p", "description": "x",
         "sys_info": "s" * 2001},
        [],
    )
    check("sys_info 超长 400", not ok and st == 400, f"got {ok},{st}")

    print("== submit_from_api：截图校验与回滚 ==")
    before = len(list(up.glob("fb_*")))
    ok, msg, st = fm.submit_from_api(
        {"issue_type": "功能异常", "protocol": "p", "description": "坏图"},
        [("a.png", b"not-an-image")],
    )
    check("非图片字节 400", not ok and st == 400, f"got {ok},{st},{msg}")
    ok, msg, st = fm.submit_from_api(
        {"issue_type": "功能异常", "protocol": "p", "description": "坏扩展名"},
        [("a.exe", PNG)],
    )
    check("错误扩展名 400", not ok and st == 400, f"got {ok},{st},{msg}")
    ok, msg, st = fm.submit_from_api(
        {"issue_type": "功能异常", "protocol": "p", "description": "超大图"},
        [("a.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * (5 * 1024 * 1024 + 10))],
    )
    check("超 5MB 413", not ok and st == 413, f"got {ok},{st}")
    ok, msg, st = fm.submit_from_api(
        {"issue_type": "功能异常", "protocol": "p", "description": "太多图"},
        [("a.png", PNG)] * 4,
    )
    check("超过 3 张 400", not ok and st == 400, f"got {ok},{st}")
    after = len(list(up.glob("fb_*")))
    check("失败回滚无脏文件", after == before, f"before={before} after={after}")
    items, total = store.list_all(limit=100)
    check("失败记录不入库", all("坏" not in i.description for i in items))

    print("== parse_multipart：二进制往返 ==")
    boundary = b"----WebKitFormBoundaryABC123"
    head = b"--" + boundary
    crlf = b"\r\n"
    parts = []
    for k, v in [("issue_type", "功能异常"), ("protocol", "南网协议"),
                 ("description", "中文描述 ok")]:
        parts.append(
            head + crlf
            + f'Content-Disposition: form-data; name="{k}"'.encode() + crlf + crlf
            + v.encode("utf-8") + crlf
        )
    parts.append(
        head + crlf
        + b'Content-Disposition: form-data; name="screenshots"; filename="s.png"' + crlf
        + b"Content-Type: image/png" + crlf + crlf + PNG + crlf
    )
    body = b"".join(parts) + head + b"--" + crlf
    fields, files = fm.parse_multipart(body, boundary)
    check("文本字段解析", fields.get("issue_type") == "功能异常"
          and fields.get("description") == "中文描述 ok", f"fields={fields}")
    check("文件字段解析", len(files) == 1 and files[0][0] == "s.png"
          and files[0][1] == PNG, f"files={len(files)} match={files[0][1]==PNG if files else '-'}")
    # 解析结果可直接喂给 submit_from_api
    files_t = [(n, d) for n, d in files]
    ok, rid, st = fm.submit_from_api(dict(fields, source="gui"), files_t)
    check("multipart 解析后可直接提交", ok and st == 200, f"got {ok},{rid},{st}")

    print("== FeedbackRateLimiter：滑动窗口限流 ==")
    rl = fm.FeedbackRateLimiter(max_calls=5, window=60)
    results = [rl.check("1.2.3.4", now=1000 + i) for i in range(7)]
    check("前 5 次放行", results[:5] == [True] * 5, f"{results}")
    check("第 6/7 次拒绝", results[5:] == [False, False], f"{results}")
    check("窗口外恢复", rl.check("1.2.3.4", now=1000 + 200) is True)
    check("不同 IP 独立计数", rl.check("9.9.9.9", now=1001) is True)

    print("== api_config ==")
    cfg = fm.api_config()
    check("config ok", cfg.get("ok") is True and cfg.get("max_screenshots") == 3
          and "功能异常" in cfg.get("issue_types", []), f"{cfg}")

    print("== 旧库迁移（缺列自动补） ==")
    import sqlite3

    old_db = _TMP / "old" / "feedback.db"
    old_db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(old_db))
    con.execute(
        "CREATE TABLE feedbackitem (id INTEGER PRIMARY KEY, created_at VARCHAR,"
        " issue_type VARCHAR, protocol VARCHAR, description VARCHAR, contact VARCHAR,"
        " screenshots VARCHAR, status VARCHAR)"
    )
    con.execute(
        "INSERT INTO feedbackitem VALUES (1,'2026-01-01 00:00:00','其他','p','老记录','','','待处理')"
    )
    con.commit()
    con.close()
    os.environ["FEEDBACK_DATA_DIR"] = str(_TMP / "old")
    fm.FeedbackStore.reset()
    s2 = fm.FeedbackStore.instance()  # 触发迁移
    con = sqlite3.connect(str(old_db))
    cols = {r[1] for r in con.execute("PRAGMA table_info(feedbackitem)").fetchall()}
    con.close()
    check("迁移补 source 列", "source" in cols, f"cols={cols}")
    check("迁移补 sys_info 列", "sys_info" in cols, f"cols={cols}")
    old = s2.get(1)
    check("老记录 source 默认 web", old is not None and old.source == "web",
          f"source={getattr(old, 'source', None)}")

    print(f"\n{'='*50}")
    print(f"结果: {PASS} 通过, {FAIL} 失败")
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
