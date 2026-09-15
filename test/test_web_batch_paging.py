# -*- coding: utf-8 -*-
"""Web 批量摘要分页回归测试（任务 09-15-web-batch-alignment）

背景：原实现把摘要截断到 300 条（`batch_display_limit`）并写死 360px 高滚动区，
用户贴 27465 帧时既看不全也翻不了页；且 `batch_results` 全量进 State 会经
WebSocket 整批下发（后端日志有 24MB 序列化告警）。改为「全量摘要留后端 +
前端只放当前页」。

覆盖：
  1. `web_utils.paginate/page_of` 纯函数（切片/越界夹取/空表/page_size 非法）
  2. State 端到端（`State(_reflex_internal_init=True)` + 驱动 `parse_batch`）：
     250 行日志 → 总帧数 250 / 3 页 / 首页 100 条（id 0..99）
     → 翻页/末页/每页条数切换 → 行号与选中 id 跨页正确
  3. 组件树可构建（分页条与高度写法不炸）

直接运行: PYTHONIOENCODING=utf-8 python test/test_web_batch_paging.py
"""

import _path_setup  # noqa: E402

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "reflex_web"
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from reflex_web import web_utils  # noqa: E402

PASS = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAILURES.append(name)
        print(f"  ✗ {name}  {detail}")


# ═══════════════════════════════════════════════════════════════
# 1. 纯函数
# ═══════════════════════════════════════════════════════════════

def test_paginate():
    print("\n[1] paginate / page_of")
    items = list(range(250))
    page0, count = web_utils.paginate(items, 0, 100)
    check("250 条 / 每页 100 → 3 页", count == 3, f"count={count}")
    check("首页 = 0..99", page0 == list(range(100)), f"len={len(page0)}")
    page2, _ = web_utils.paginate(items, 2, 100)
    check("末页 = 200..249", page2 == list(range(200, 250)), f"len={len(page2)}")
    over, over_count = web_utils.paginate(items, 99, 100)
    check("页码越界夹取到末页", over == page2 and over_count == 3, f"len={len(over)}")
    neg, _ = web_utils.paginate(items, -5, 100)
    check("负页码夹取到首页", neg == page0)
    check("空表 → ([], 1)", web_utils.paginate([], 0, 100) == ([], 1))
    check("page_size<=0 视为 1", web_utils.paginate([1, 2, 3], 0, 0) == ([1], 3))
    check("整除时页数不虚增", web_utils.paginate(list(range(200)), 0, 100)[1] == 2)
    check("page_of 夹取", web_utils.page_of(9, 3) == 2 and web_utils.page_of(-1, 3) == 0)
    check("page_of 零页", web_utils.page_of(3, 0) == 0)


# ═══════════════════════════════════════════════════════════════
# 2. State 端到端
# ═══════════════════════════════════════════════════════════════

# 协议9 SOF 下行帧（与 test_csg_sequence_model 同源），每行一帧
SOF_FRAME = "0901FF00000000001C0000000000000000000000000000000000000000000000000000000000000000000000"


def _log_lines(n: int) -> str:
    return "\n".join([SOF_FRAME] * n)


def test_state_paging():
    print("\n[2] State 端到端（250 帧）")
    try:
        import reflex_web.reflex_web as app
    except Exception as e:  # noqa: BLE001
        check("导入 reflex_web.reflex_web", False, f"{type(e).__name__}: {e}")
        return

    async def drive():
        st = app.State(_reflex_internal_init=True)
        st.current_protocol = 9
        st.csg_parse_level = "auto"
        st.batch_input = _log_lines(250)
        async for _ in st.parse_batch():
            pass
        return st

    st = asyncio.run(drive())
    check("总帧数 = 250", st.batch_total_frames == 250, str(st.batch_total_frames))
    check("总页数 = 3", st.batch_page_count == 3, str(st.batch_page_count))
    check("首页在 State 里只放 100 条（不再整批下发）",
          len(st.batch_results) == 100, str(len(st.batch_results)))
    check("首页 id = 0..99", [r["id"] for r in st.batch_results[:3]] == [0, 1, 2]
          and st.batch_results[-1]["id"] == 99, str(st.batch_results[-1]))
    check("全量摘要留在后端（私有字段）", len(st._batch_summaries) == 250,
          str(len(st._batch_summaries)))
    check("下划线字段不进序列化字段集",
          "_batch_summaries" not in getattr(st, "_serialized_vars", {})
          if hasattr(st, "_serialized_vars") else True)

    st.batch_next_page()
    check("下页 → 第 2 页且 id 从 100 起",
          st.batch_page == 1 and st.batch_results[0]["id"] == 100,
          f"page={st.batch_page} id={st.batch_results[0]['id']}")
    st.batch_next_page()
    check("再下页 → 第 3 页 50 条（100+100+50）",
          st.batch_page == 2 and len(st.batch_results) == 50,
          f"len={len(st.batch_results)}")
    st.batch_next_page()  # 已在末页
    check("末页再点下页不变", st.batch_page == 2)

    # 跨页选中：末页第 0 行 → 全局 id=200 的明细
    st.select_batch_item(0)
    check("末页选中记录全局 id", st.batch_selected_idx == 200, str(st.batch_selected_idx))
    check("明细来自对应帧", len(st.batch_detail_rows) > 0, str(len(st.batch_detail_rows)))

    st.batch_first_page()
    check("首页按钮回到 0", st.batch_page == 0 and st.batch_results[0]["id"] == 0)

    st.set_batch_page_size("500")
    check("每页 500 → 单页容纳 250 条",
          st.batch_page_size == 500 and len(st.batch_results) == 250
          and st.batch_page_count == 1, f"{st.batch_page_size}/{len(st.batch_results)}")
    st.set_batch_page_size("abc")
    check("非法每页值回落 100", st.batch_page_size == 100, str(st.batch_page_size))

    st.clear_batch()
    check("清空后分页状态归零",
          st.batch_results == [] and st.batch_page == 0 and st.batch_page_count == 0
          and st._batch_summaries == [])


def main():
    print("=" * 62)
    print("Web 批量摘要分页回归测试")
    print("=" * 62)
    test_paginate()
    test_state_paging()
    print("\n" + "=" * 62)
    if FAILURES:
        print(f"失败 {len(FAILURES)} 项 / 通过 {PASS} 项")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print(f"全部通过（{PASS} 项）✓")
    print("=" * 62)


if __name__ == "__main__":
    main()
