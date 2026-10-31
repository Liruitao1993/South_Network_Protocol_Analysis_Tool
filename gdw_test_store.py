# -*- coding: utf-8 -*-
"""国网协议测试页（协议7）—— **参数存档 / 支持统计 / 收发日志落盘**（纯逻辑，不依赖 Qt）。

三份数据各自独立，落在 :meth:`app_paths.data_path` 同级目录，互不牵连：

1. **参数存档** ``gdw_test_params.json`` 的 ``commands`` / ``eb`` 段
   —— 每条命令一份「数据单元字段值 + 附加数据」，每个 EB 数据标识一份「数据内容字段值 + 裸 HEX」。
   页面切换命令时自动存/取；只有**与默认值不同**（或附加数据非空）才落盘，因此
   「清理所有参数」把控件打回默认后不会又被重新写回存档。
   **全局测试参数**（源/目的地址、序列号、超时、重试、通道、勾选）不在这里，仍由
   ``gdw_testbench.json`` 管。
2. **支持统计**（同文件 ``stats`` 段）—— 每条命令最近一次判定结果：
   ``support`` / ``support_error`` / ``mismatch`` / ``no_reply`` / ``untested`` + 依据 + 时间。
3. **收发日志** ``logs/gdw_test_YYYYMMDD.log`` —— 每条收发/提示行按 ``[时间] 文本`` 追加，
   单文件超过 :data:`LOG_MAX_BYTES` 自动滚到 ``_2``/``_3``…；界面只显示本次会话，
   历史靠「导出日志」「打开日志目录」查。

设计约束：本模块不 import Qt / 主窗口，方便被测试脚本单独跑；所有写盘都经
:mod:`atomic_io` 或追加模式，异常一律不抛给调用方（测试页不该因为磁盘问题崩）。
"""

from __future__ import annotations

import csv
import io
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from atomic_io import atomic_write_json, read_json

PARAMS_NAME = "gdw_test_params.json"
PARAMS_VERSION = 1

#: 日志目录名（相对数据目录）与文件名前缀
LOG_DIR = "logs"
LOG_PREFIX = "gdw_test"
LOG_MAX_BYTES = 8 * 1024 * 1024

# ── 支持状态 ──────────────────────────────────────────────────────────
STATE_SUPPORT = "support"
STATE_SUPPORT_ERROR = "support_error"
STATE_UNSUPPORTED = "unsupported"
STATE_CONFIRM_ONLY = "confirm_only"
STATE_MISMATCH = "mismatch"
STATE_NO_REPLY = "no_reply"
STATE_UNTESTED = "untested"

STATE_LABELS: Dict[str, str] = {
    STATE_SUPPORT: "支持",
    STATE_SUPPORT_ERROR: "支持（执行报错）",
    STATE_UNSUPPORTED: "不支持（设备否认）",
    STATE_CONFIRM_ONLY: "仅确认·无数据",
    STATE_MISMATCH: "非本命令响应",
    STATE_NO_REPLY: "无响应",
    STATE_UNTESTED: "未测",
}
#: 计入「支持该 AFN/Fn」的状态（执行报错说明命令本身是被识别的；
#: 「仅确认·无数据」是抄表类没拿到数据，按用户口径**不算支持**）
SUPPORTED_STATES = (STATE_SUPPORT, STATE_SUPPORT_ERROR)

STATS_HEADERS: Tuple[str, ...] = ("AFN", "Fn", "命令", "从节点", "方向", "状态", "依据", "时间")


def stat_key(key: str, node_addr: str = "") -> str:
    """统计键：同一命令在不同从节点上的结果分开记（``03-1@001122334455``）。"""
    key = str(key or "")
    node = str(node_addr or "")
    return f"{key}@{node}" if node else key


#: 聚合多个节点结果时的优先级（越靠前越「不代表不支持」）
_AGGREGATE_PRIORITY = (
    STATE_SUPPORT, STATE_SUPPORT_ERROR, STATE_CONFIRM_ONLY,
    STATE_MISMATCH, STATE_NO_REPLY, STATE_UNSUPPORTED,
)


def _aggregate_node_stats(key: str, stats: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    """把 ``key@地址`` 的多条记录聚合出一条（任一节点支持即算支持）。

    用于「原来按节点展开记过、现在不展开（或反之）」的历史兼容，避免配置一变旧结论就丢。
    """
    prefix = f"{key}@"
    hits = [dict(v) for k, v in (stats or {}).items()
            if str(k).startswith(prefix) and isinstance(v, Mapping)]
    if not hits:
        return {}
    for want in _AGGREGATE_PRIORITY:
        for rec in hits:
            if str(rec.get("state")) == want:
                return rec
    return hits[0]


def classify_result(result: Mapping[str, Any]) -> Tuple[str, str]:
    """把 :func:`gdw_test_core.evaluate_response` 的结果归一成 ``(状态, 依据)``。

    - ``matched=False`` → ``mismatch``：设备回了别的 AFN/Fn，说明这条命令它不认；
    - ``matched=True`` + ``ok=True`` → ``support``；
    - ``matched=True`` + ``ok=False`` → ``support_error``：命令被识别但执行报错/否认；
    - ``matched=True`` + ``ok=None`` → ``support``：收到了同命令响应（不冒充成功，依据里保留原话）。
    """
    ok = result.get("ok")
    matched = bool(result.get("matched"))
    reason = str(result.get("reason") or "").strip()
    if not matched:
        return STATE_MISMATCH, reason or "回帧 AFN/Fn 与期望不一致"
    if ok is True:
        return STATE_SUPPORT, reason or "设备确认"
    if ok is False:
        return STATE_SUPPORT_ERROR, reason or "设备否认/报错"
    return STATE_SUPPORT, reason or "已收到同命令响应（未做字段级判定）"


def summarize(commands: Sequence[Any],
              stats: Mapping[str, Mapping[str, Any]],
              nodes: Sequence[Any] = ()) -> Dict[str, Any]:
    """生成支持统计行与汇总。

    ``nodes`` 为启用的从节点（``.addr`` / ``.proto``），给出时：
    - **需要按节点逐帧发的命令**（含单个节点地址字段）按「命令 × 从节点」各出一行；
    - 其余命令只出一行（从节点列留空）。
    AFN 汇总按**命令去重**：某条命令任一个节点支持就算该命令支持。
    """
    from gdw_test_network import is_node_scoped  # 避免循环 import（network 不依赖本模块）

    node_addrs = [str(getattr(n, "addr", "") or "") for n in nodes]
    node_addrs = [a for a in node_addrs if a]
    rows: List[List[str]] = []
    counts: Dict[str, int] = {state: 0 for state in STATE_LABELS}
    per_afn: Dict[int, Dict[str, Any]] = {}
    for cmd in commands:
        key = str(getattr(cmd, "key", "") or "")
        afn = int(getattr(cmd, "afn", 0) or 0)
        fn = int(getattr(cmd, "fn", 0) or 0)
        name = str(getattr(cmd, "name", "") or "")
        source = str(getattr(cmd, "source", "") or "")
        if source and source != "标准":
            name = f"[{source}] {name}"
        direction = "下行" if str(getattr(cmd, "direction", "")) == "down" else "上行"

        targets: List[str] = (
            list(node_addrs) if (node_addrs and is_node_scoped(cmd)) else [""]
        )
        cmd_states: List[str] = []
        for node in targets:
            rec = dict(stats.get(stat_key(key, node)) or {})
            if not rec and node:
                # 兼容「改配组网前按命令记的旧结果」，避免历史统计凭空消失
                rec = dict(stats.get(key) or {})
            if not rec and not node:
                # 反向兼容：曾经按节点记过、现在不展开 ⇒ 聚合该命令的各节点结果
                rec = _aggregate_node_stats(key, stats)
            state = str(rec.get("state") or STATE_UNTESTED)
            if state not in STATE_LABELS:
                state = STATE_UNTESTED
            counts[state] += 1
            cmd_states.append(state)
            rows.append([
                f"{afn:02X}H", f"F{fn}", name, node or "—", direction,
                STATE_LABELS[state],
                str(rec.get("reason") or ""),
                str(rec.get("at") or ""),
            ])
        slot = per_afn.setdefault(afn, {"total": 0, "supported": 0, "tested": 0})
        slot["total"] += 1
        if any(s in SUPPORTED_STATES for s in cmd_states):
            slot["supported"] += 1
        if any(s != STATE_UNTESTED for s in cmd_states):
            slot["tested"] += 1
    rows.sort(key=lambda r: (r[0], int(r[1][1:]), r[3]))
    return {"rows": rows, "counts": counts, "per_afn": per_afn, "total": len(rows)}


def summary_text(summary: Mapping[str, Any]) -> str:
    """汇总一行文案（界面标签 / CSV 头注释共用）。"""
    counts = summary.get("counts") or {}
    total = int(summary.get("total") or 0)
    support = int(counts.get(STATE_SUPPORT, 0))
    support_err = int(counts.get(STATE_SUPPORT_ERROR, 0))
    unsupported = int(counts.get(STATE_UNSUPPORTED, 0))
    confirm_only = int(counts.get(STATE_CONFIRM_ONLY, 0))
    mismatch = int(counts.get(STATE_MISMATCH, 0))
    no_reply = int(counts.get(STATE_NO_REPLY, 0))
    untested = int(counts.get(STATE_UNTESTED, 0))
    return (f"共 {total} 条 · 支持 {support + support_err}"
            f"（其中执行报错 {support_err}）· 不支持 {unsupported}"
            f" · 仅确认无数据 {confirm_only} · 非本命令响应 {mismatch}"
            f" · 无响应 {no_reply} · 未测 {untested}")


def per_afn_text(summary: Mapping[str, Any], limit: int = 12) -> str:
    """按 AFN 汇总文案（``03H 4/4 · 04H 3/3``，未测的标 ``0/8``）。"""
    per_afn = summary.get("per_afn") or {}
    parts: List[str] = []
    for afn in sorted(per_afn):
        slot = per_afn[afn]
        parts.append(f"{afn:02X}H {slot['supported']}/{slot['total']}")
    if limit and len(parts) > limit:
        parts = parts[:limit] + [f"…（共 {len(per_afn)} 个 AFN）"]
    return "按 AFN：" + " · ".join(parts)


def stats_csv(summary: Mapping[str, Any]) -> str:
    """支持统计 → CSV 文本（带 UTF-8 BOM，Excel 直接双击不乱码）。"""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow([f"# {summary_text(summary)}"])
    writer.writerow(list(STATS_HEADERS))
    for row in summary.get("rows") or ():
        writer.writerow(list(row))
    return buf.getvalue()


class ParamStore:
    """命令参数存档 + 支持统计（同一份 JSON，两个段）。"""

    def __init__(self, path) -> None:
        self._path = Path(path)
        self._data: Dict[str, Any] = self._blank()
        self.last_error = ""
        self.load()

    @staticmethod
    def _blank() -> Dict[str, Any]:
        return {"version": PARAMS_VERSION, "commands": {}, "eb": {}, "stats": {},
                "network": {}}

    # ── 读写 ──────────────────────────────────────────────────────────
    def load(self) -> None:
        data = read_json(self._path, default=None)
        if not isinstance(data, dict):
            return
        out = self._blank()
        for section in ("commands", "eb", "stats"):
            part = data.get(section)
            if isinstance(part, dict):
                out[section] = {str(k): v for k, v in part.items() if isinstance(v, dict)}
        # network 是混合结构（含 slaves 列表/标量），不做逐项过滤
        net = data.get("network")
        if isinstance(net, dict):
            out["network"] = dict(net)
        self._data = out

    def save(self) -> bool:
        try:
            atomic_write_json(self._path, self._data)
            self.last_error = ""
            return True
        except Exception as exc:  # noqa: BLE001 - 存档失败不该炸页面
            self.last_error = f"{type(exc).__name__}: {exc}"
            return False

    def path(self) -> Path:
        return self._path

    # ── 参数 ──────────────────────────────────────────────────────────
    def get_command(self, key: str) -> Dict[str, Any]:
        rec = self._data["commands"].get(str(key))
        return dict(rec) if isinstance(rec, dict) else {}

    def set_command(self, key: str, values: Mapping[str, Any],
                    ui: Mapping[str, Any], raw: str = "",
                    dirty: Sequence[str] = ()) -> bool:
        """存一条命令参数；``dirty`` 记下用户手改过的字段（自动填充不覆盖它们）。"""
        key = str(key)
        self._data["commands"][key] = {
            "values": dict(values or {}),
            "ui": dict(ui or {}),
            "raw": str(raw or ""),
            "dirty": [str(n) for n in (dirty or ())],
        }
        return True

    def dirty_fields(self, key: str) -> List[str]:
        rec = self._data["commands"].get(str(key))
        if not isinstance(rec, dict):
            return []
        dirty = rec.get("dirty")
        return [str(n) for n in dirty] if isinstance(dirty, list) else []

    def drop_command(self, key: str) -> None:
        self._data["commands"].pop(str(key), None)

    def get_eb(self, di: str) -> Dict[str, Any]:
        rec = self._data["eb"].get(str(di))
        return dict(rec) if isinstance(rec, dict) else {}

    def set_eb(self, di: str, values: Mapping[str, Any],
               ui: Mapping[str, Any], raw: str = "") -> None:
        self._data["eb"][str(di)] = {
            "values": dict(values or {}), "ui": dict(ui or {}), "raw": str(raw or ""),
        }

    def drop_eb(self, di: str) -> None:
        self._data["eb"].pop(str(di), None)

    def clear_params(self) -> int:
        """清掉所有命令参数与 EB 数据内容（支持统计保留），返回清掉的条数。"""
        removed = len(self._data["commands"]) + len(self._data["eb"])
        self._data["commands"] = {}
        self._data["eb"] = {}
        return removed

    def param_count(self) -> int:
        return len(self._data["commands"]) + len(self._data["eb"])

    # ── 组网参数 ──────────────────────────────────────────────────────
    def get_network(self) -> Dict[str, Any]:
        net = self._data.get("network")
        return dict(net) if isinstance(net, dict) else {}

    def set_network(self, data: Mapping[str, Any]) -> None:
        self._data["network"] = dict(data or {})

    # ── 支持统计 ──────────────────────────────────────────────────────
    def get_stat(self, key: str) -> Dict[str, Any]:
        rec = self._data["stats"].get(str(key))
        return dict(rec) if isinstance(rec, dict) else {}

    def set_stat(self, key: str, state: str, reason: str, at: str = "") -> None:
        self._data["stats"][str(key)] = {
            "state": str(state),
            "reason": str(reason or ""),
            "at": str(at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        }

    def clear_stats(self) -> int:
        removed = len(self._data["stats"])
        self._data["stats"] = {}
        return removed

    def stats(self) -> Dict[str, Dict[str, Any]]:
        return self._data["stats"]


class SessionLog:
    """本次会话的日志缓冲 + 落盘（按天一个文件，超限自动滚动）。"""

    def __init__(self, directory, *, prefix: str = LOG_PREFIX,
                 max_bytes: int = LOG_MAX_BYTES) -> None:
        self._dir = Path(directory)
        self._prefix = prefix
        self._max_bytes = int(max_bytes)
        self._lines: List[str] = []
        self._handle = None
        self.last_error = ""

    # ── 落盘 ──────────────────────────────────────────────────────────
    def _path_for(self, when: Optional[datetime] = None) -> Path:
        day = (when or datetime.now()).strftime("%Y%m%d")
        return self._dir / f"{self._prefix}_{day}.log"

    def path(self) -> Path:
        return self._path_for()

    def _rotate(self, path: Path) -> Path:
        """超限时把当前文件改名成 ``_xxx_2.log``/``_3``…，返回可写的新路径。"""
        try:
            if not path.exists() or path.stat().st_size < self._max_bytes:
                return path
        except OSError:
            return path
        stem, suffix = path.stem, path.suffix
        for idx in range(2, 1000):
            alt = path.with_name(f"{stem}_{idx}{suffix}")
            if not alt.exists():
                try:
                    path.rename(alt)
                except OSError:
                    pass
                return path
        return path

    def _ensure_handle(self, path: Path):
        if self._handle is not None:
            return self._handle
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path = self._rotate(path)
            self._handle = open(path, "a", encoding="utf-8")
            self.last_error = ""
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"{type(exc).__name__}: {exc}"
            self._handle = None
        return self._handle

    def append(self, text: str, *, stamp: Optional[str] = None) -> str:
        """追加一行（返回带时间戳的整行，界面/导出都用它）。"""
        stamp = stamp or datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{stamp}] {text}"
        self._lines.append(line)
        path = self._path_for()
        # 每行写入前检查体量：句柄已打开的长期会话也要能滚动，否则单文件会无限长
        if self._handle is not None:
            try:
                if self._handle.tell() >= self._max_bytes:
                    self._handle.close()
                    self._handle = None
            except OSError:
                self._handle = None
        handle = self._ensure_handle(path)
        if handle is not None:
            try:
                handle.write(line + "\n")
                handle.flush()
            except Exception as exc:  # noqa: BLE001
                self.last_error = f"{type(exc).__name__}: {exc}"
        return line

    # ── 导出 ──────────────────────────────────────────────────────────
    def lines(self) -> List[str]:
        return list(self._lines)

    def text(self) -> str:
        return "\n".join(self._lines)

    def export(self, dst) -> int:
        """把本次会话日志写到 ``dst``（UTF-8），返回行数。"""
        dst = Path(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        body = self.text()
        dst.write_text(body + ("\n" if body else ""), encoding="utf-8")
        return len(self._lines)

    def clear(self) -> None:
        self._lines.clear()

    def close(self) -> None:
        if self._handle is not None:
            try:
                self._handle.close()
            except Exception:  # noqa: BLE001
                pass
            self._handle = None
