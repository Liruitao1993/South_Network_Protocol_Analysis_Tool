"""Web 版问题反馈模块测试（feedback_model + 部署脚本 data/ 保留逻辑）

覆盖：
- save_screenshot：正常保存 / 非法扩展名 / 非法魔数 / 超大文件 / 空内容
- generate_filename：服务端重生成文件名（不含用户原始名）+ 防穿越模式
- delete_screenshots：正常清理 / 路径穿越拒绝 / 保留非 fb_* 文件
- FeedbackStore CRUD：add / list_all 分页 / count_pending / update_status / delete
- 部署脚本：build_offline_deploy.preserve_data_dir / restore_data_dir
           build_embedded_deploy.preserve_data_dirs / restore_data_dirs
- run_app.py：py_compile 语法验证（fbimg 路由接入）

运行（项目根）：
    python test/test_web_feedback.py
"""

import os
import py_compile
import shutil
import sys
import tempfile
import warnings
from pathlib import Path

import _path_setup  # noqa: E402

warnings.filterwarnings("ignore")

ROOT = Path(_path_setup.__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 数据目录重定向到临时目录（必须在 import feedback_model 前设置）
_TMP = Path(tempfile.mkdtemp(prefix="fb_test_"))
os.environ["FEEDBACK_DATA_DIR"] = str(_TMP / "data")

from reflex_web import feedback_model as fm  # noqa: E402

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


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff\xe0" + b"\x00" * 20
WEBP_MAGIC = b"RIFF\x24\x00\x00\x00WEBPVP8 "


# ── save_screenshot ──────────────────────────────────────────


def test_save_screenshot():
    print("test_save_screenshot:")
    name = fm.save_screenshot(PNG_MAGIC + b"x" * 8 * 100, "screen shot 1.PNG")
    check("png saved with fb_ prefix", name.startswith("fb_") and name.endswith(".png"))
    check("no user filename in generated name", "screen" not in name)
    path = fm.uploads_dir() / name
    check("file exists on disk", path.is_file())
    check("content intact", path.read_bytes() == PNG_MAGIC + b"x" * 8 * 100)

    n2 = fm.save_screenshot(JPEG_MAGIC + b"x", "b.jpg")
    check("jpeg saved", n2.endswith(".jpg"))
    n3 = fm.save_screenshot(WEBP_MAGIC + b"x", "c.webp")
    check("webp saved", n3.endswith(".webp"))

    # 文件名格式：fb_YYYYmmdd_HHMMSS_<8hex>.<ext>
    import re

    check(
        "filename matches fb_* pattern",
        bool(re.match(r"^fb_\d{8}_\d{6}_[0-9a-f]{8}\.(png|jpe?g|webp)$", name)),
    )


def test_save_screenshot_rejects():
    print("test_save_screenshot_rejects:")
    ok = True
    try:
        fm.save_screenshot(PNG_MAGIC, "a.exe")
        ok = False
    except ValueError:
        pass
    check("bad extension rejected", ok)

    ok = True
    try:
        fm.save_screenshot(b"MZ" + b"\x00" * 20, "a.png")
        ok = False
    except ValueError:
        pass
    check("bad magic rejected", ok)

    ok = True
    try:
        fm.save_screenshot(b"", "a.png")
        ok = False
    except ValueError:
        pass
    check("empty content rejected", ok)

    ok = True
    try:
        fm.save_screenshot(PNG_MAGIC + b"x" * 8 * (fm.MAX_SCREENSHOT_SIZE + 1), "a.png")
        ok = False
    except ValueError:
        pass
    check("oversize rejected", ok)

    ok = True
    try:
        fm.save_screenshot(b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b", "a.png")
        ok = False
    except ValueError:
        pass
    check("random bytes rejected", ok)

    ok = True
    try:
        fm.save_screenshot(PNG_MAGIC, "../evil.png")
        ok = False
    except ValueError:
        pass
    check("traversal orig name rejected (no valid ext dir)", ok)


# ── delete_screenshots ───────────────────────────────────────


def test_delete_screenshots():
    print("test_delete_screenshots:")
    n1 = fm.save_screenshot(PNG_MAGIC + b"x" * 8, "a.png")
    n2 = fm.save_screenshot(PNG_MAGIC + b"x" * 8, "b.png")
    check(
        "two files saved",
        (fm.uploads_dir() / n1).is_file() and (fm.uploads_dir() / n2).is_file(),
    )

    removed = fm.delete_screenshots([n1])
    check("delete one", removed == 1 and not (fm.uploads_dir() / n1).is_file())

    # 防穿越：路径分隔符 / .. / 非 fb_* 文件名
    check("traversal ../ rejected", fm.delete_screenshots(["../feedback.db"]) == 0)
    check("slash rejected", fm.delete_screenshots(["sub/dir.png"]) == 0)
    check("backslash rejected", fm.delete_screenshots(["sub\\dir.png"]) == 0)
    check("non-fb name rejected", fm.delete_screenshots(["important.db"]) == 0)
    check("empty name ignored", fm.delete_screenshots([""]) == 0)

    removed = fm.delete_screenshots([n2, "nonexistent.png"])
    check("delete remaining + skip missing", removed == 1)


# ── FeedbackStore CRUD ──────────────────────────────────────


def test_store_crud():
    print("test_store_crud:")
    store = fm.FeedbackStore.instance()

    ids = []
    for i in range(5):
        item = fm.FeedbackItem(
            created_at=f"2026-08-31 10:0{i}:00",
            issue_type=fm.ISSUE_TYPES[i % len(fm.ISSUE_TYPES)],
            protocol="南网协议",
            description=f"问题 {i}",
            contact=f"qq:{i}",
            screenshots="",
            status="待处理",
        )
        ids.append(store.add(item))
    check("add returns increasing ids", ids == sorted(set(ids)))

    items, total = store.list_all(offset=0, limit=20)
    check("total after 5 adds", total == 5)
    check("list newest first", items[0].created_at.endswith("10:04:00"))

    items_p1, _ = store.list_all(offset=0, limit=2)
    items_p2, _ = store.list_all(offset=2, limit=2)
    check(
        "pagination slices",
        len(items_p1) == 2 and len(items_p2) == 2 and items_p1[0].id != items_p2[0].id,
    )

    check("count_pending 5", store.count_pending() == 5)
    check("update_status valid", store.update_status(ids[0], "已修复"))
    check("count_pending after update", store.count_pending() == 4)
    check("update_status invalid value", not store.update_status(ids[0], "不存在状态"))
    check("update_status missing id", not store.update_status(99999, "已确认"))

    got = store.get(ids[1])
    check("get returns item", got is not None and got.description == "问题 1")
    check("get missing returns None", store.get(99999) is None)

    # 删除含截图的记录 → 返回截图名列表
    shot = fm.save_screenshot(PNG_MAGIC + b"x" * 8, "del.png")
    item = fm.FeedbackItem(
        created_at="2026-08-31 11:00:00",
        issue_type="其他",
        protocol="698.45协议",
        description="带截图",
        contact="",
        screenshots=shot,
        status="待处理",
    )
    fid = store.add(item)
    names = store.delete(fid)
    check("delete returns screenshot names", names == [shot])
    check("deleted record gone", store.get(fid) is None)
    fm.delete_screenshots(names)
    check("screenshot file cleaned", not (fm.uploads_dir() / shot).is_file())

    check("delete missing returns []", store.delete(99999) == [])


# ── 部署脚本 data/ 保留 ─────────────────────────────────────


def test_deploy_preserve():
    print("test_deploy_preserve:")
    import build_embedded_deploy as bed
    import build_offline_deploy as bod

    base = _TMP / "deploy"
    out = base / "reflex_web_embedded"
    (out / "data" / "uploads" / "feedback").mkdir(parents=True)
    (out / "data" / "feedback.db").write_text("OLD_DB")
    (out / "data" / "uploads" / "feedback" / "fb_1.png").write_bytes(b"png")

    # offline
    moved = bod.preserve_data_dir(out)
    check("offline moves data/", moved is not None and moved.name == "data")
    check("data/ gone from out_dir", not (out / "data").exists())
    shutil.rmtree(out)
    out.mkdir()
    bod.restore_data_dir(out, moved)
    check("offline restores db", (out / "data" / "feedback.db").read_text() == "OLD_DB")
    check(
        "offline restores screenshot",
        (out / "data" / "uploads" / "feedback" / "fb_1.png").is_file(),
    )

    # embedded
    moved2 = bed.preserve_data_dirs(out)
    check("embedded moves data/", len(moved2) == 1)
    shutil.rmtree(out)
    out.mkdir()
    bed.restore_data_dirs(out, moved2)
    check(
        "embedded restores db", (out / "data" / "feedback.db").read_text() == "OLD_DB"
    )

    # 无 data/ 场景
    fresh = base / "fresh_out"
    fresh.mkdir()
    check("embedded no-data returns []", bed.preserve_data_dirs(fresh) == [])
    check("offline no-data returns None", bod.preserve_data_dir(fresh) is None)
    bed.restore_data_dirs(fresh, [])
    bod.restore_data_dir(fresh, None)
    check("restore with nothing is no-op", True)


# ── run_app.py / 模块编译验证 ────────────────────────────────


def test_compile():
    print("test_compile:")
    for f in [
        "reflex_web/run_app.py",
        "reflex_web/reflex_web/feedback_model.py",
        "reflex_web/build_embedded_deploy.py",
        "reflex_web/build_offline_deploy.py",
    ]:
        try:
            py_compile.compile(str(ROOT / f), doraise=True)
            check(f"{f} compiles", True)
        except py_compile.PyCompileError as e:
            check(f"{f} compiles: {e}", False)


def main():
    try:
        test_save_screenshot()
        test_save_screenshot_rejects()
        test_delete_screenshots()
        test_store_crud()
        test_deploy_preserve()
        test_compile()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
        os.environ.pop("FEEDBACK_DATA_DIR", None)
    print(f"\n{'=' * 40}")
    print(f"PASS: {PASS}  FAIL: {FAIL}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
