# -*- coding: utf-8 -*-
"""协议8（DL/T 698.45）文件传输升级页 —— 拖入升级包 → 启动传输 → 逐包写文件 → 执行升级。

流程（`协议文档/8.698.45协议/代理升级流程.docx` + design §3）：

    ① ACTION-Request Normal  OMD=F0010700  启动传输（文件信息 / 传输块大小 / 校验）
    ② ACTION-Request Normal  OMD=F0010800  写文件 × N 包（块序号 0 基，逐包等确认）
    ③ ACTION-Request Normal  OMD=F0010D00  执行升级（date_time_s 全 FF = 立即执行）

设备对每帧回 `ACTION-Response Normal`（`87 01`），`DAR=0` 为成功；**逐包确认成功才发
下一包**，任何一包重试用尽即整轮停止（design §1 不变量 6）。

设计约束（改本页前先读）：
- **不自建串口**：端口生命周期归主窗口顶部「串口配置」，本页经
  :meth:`Dlt698UpgradeWidget.set_serial_worker` 借用共享 :class:`serial_worker.SerialWorker`
  （一个 COM 口只能被打开一次）。发送只用 :meth:`SerialWorker.write_raw`（**静默**），
  TX/RX 日志由本页自己写 —— 不用 ``send_frame``，否则逐包 ``[发送]`` 会刷屏（AGENTS §8 陷阱 58）。
- **RX 只用 ``raw_data_received`` 自组帧**：``frame_received`` 由
  ``SerialWorker._process_buffer`` 产生，它只认 645 双 68H 与 FT1.2（``end_pos = pos + L``），
  而 698.45 整帧 = ``L + 2`` ⇒ 698 帧必然落到「找第一个 0x16」的容错分支被**截断**
  （600B 载荷含 0x16 的概率约 90%）。组帧判据复用分帧单一来源 :mod:`frame_deframe`；
  切不出完整帧时先按 :meth:`Dlt698UpgradeWidget._resync_junk` 丢掉**不可能作为帧起点**
  的字节 —— 否则一次线噪（FE 后非 68H / 长度域不可信的错帧 / 末字节非 16H 的错位帧）
  会把后续所有确认卡在缓冲头，整轮升级被误判成超时。
- **``crcmod`` 是可选依赖**：``dl_t698_45_upgrade`` 顶层 import 了 frame_gen/axdr/parser，
  故本页对**它**一律**函数内惰性 import**（AGENTS 模块级导入铁律），失败时给可读提示，
  绝不连带打不开蓝牙/串口页。:mod:`frame_deframe` 只依赖 stdlib + wakeup_prefix ⇒ 可顶层 import。
- 状态机不用 QThread：单发 :class:`QTimer` + 标志位（照 ``test_plan_widget`` 的既有范式，
  无需 ``thread_registry`` 回收）。
- 按钮宽度只走 :func:`gui_utils.fit_btn_width` / :func:`gui_utils.fit_btn_width_for_texts`
  设**下限**，绝不 ``setFixedWidth``/``setMaximumWidth``（本项目字号可配置，写死必裁字，
  AGENTS §8 陷阱 63）。
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import app_paths
import frame_deframe
import gui_utils
from collapsible_section import CollapsibleSection

# ── 常量 ─────────────────────────────────────────────────────────────────

CONFIG_NAME = "dlt698_upgrade_config.json"
CONFIG_VERSION = 1

#: 分帧策略（与串口页同一实现：``dlt698_45`` = ``L + 2`` + 末字节 16H 自证 + 前导 FEH 容忍）
DEFRAME_STRATEGY = "dlt698_45"

#: 收帧缓冲上限（超出且**没有半截帧在等**时丢弃，防止噪声/误码把内存吃光）
RX_BUF_MAX = 262144

#: TX/RX 日志里一帧最多显示的字节数：**不超过就整帧显示**（启动/执行帧只有几十字节，
#: 截断反而让现场看不到校验值等尾部字段）；超过则只显示头尾两段、中间用 ``...`` 省略
#: （600B 起的写文件帧全打出来 ≈1800 字符会淹掉日志）。
HEX_LOG_LIMIT = 200

# 状态机的状态名（design §4）；对外经 `Dlt698UpgradeWidget.state` 只读暴露
STATE_IDLE = "idle"
STATE_STARTING = "starting"
STATE_TRANSFERRING = "transferring"
STATE_FINISHING = "finishing"
STATE_DONE = "done"
STATE_FAILED = "failed"
STATE_ABORTED = "aborted"

#: 终态集合（这些状态下**不再发送**，收到的帧也不当确认）
TERMINAL_STATES = (STATE_IDLE, STATE_DONE, STATE_FAILED, STATE_ABORTED)

#: 三个步骤的名字
PHASE_START = "start"
PHASE_BLOCKS = "blocks"
PHASE_EXEC = "exec"
#: 两个**可选**的诊断步骤（用户需求：升级前/升级完成后读版本信息；默认不勾）
PHASE_VER_PRE = "ver_pre"
PHASE_VER_POST = "ver_post"

#: 读版本信息的两步（失败**不阻断**升级流程；判定走 `check_get_response`）
VER_PHASES = (PHASE_VER_PRE, PHASE_VER_POST)

#: 「读版本内容」候选：`(下拉文案, 持久化键, 日志短名)`。**OAD 字节不在此处** ——
#: 一律经 `_read_oad()` 取协议模块的常量（`OAD_VERSION` / `OAD_INTERNAL_VERSION`），
#: 避免同一份协议事实写两遍（协议模块按需惰性 import，顶层拿不到它）。
READ_TARGETS = (
    ("通用版本信息（OAD 43000300）", "common", "通用"),
    ("内部版本（厂家扩展，OAD FF100400）", "internal", "内部"),
)
DEFAULT_READ_TARGET = "common"

#: 每包字节数上限：与串口页 `_sane_frame_len` 同族判据（design §13-5）
BLOCK_SIZE_MIN, BLOCK_SIZE_MAX = 1, 8192
TIMEOUT_MIN, TIMEOUT_MAX = 100, 600000
RETRY_MIN, RETRY_MAX = 0, 10

#: 校验类型下拉：label / 协议 enum 值 / `calc_checksum_value(kind=…)`
CHECK_TYPES = (("CRC", 0, "crc"), ("md5", 1, "md5"), ("SHA1", 2, "sha1"))

#: 文件类别（表188 属性2：`文件类别 enum{当前设备文件(0)/其他设备文件(1)}`）
FILE_CATEGORIES = (("当前设备文件", 0), ("其他设备文件", 1))

#: SA 地址类型（规范 §6.2.4.2.4：0 单地址 / 1 通配 / 2 组 / 3 广播）
SA_TYPES = (("单地址", 0), ("通配地址", 1), ("组地址", 2), ("广播地址", 3))

#: 缺省值（与 design §4 及任务冻结常量一致；SA 默认**通配** `45 AA AA AA AA AA AA`）
DEFAULTS = {
    "block_size": 600,
    "timeout_ms": 3000,
    "retries": 3,
    "auto_exec": True,
    "read_before": False,               # 升级前读版本信息（可选诊断步骤，默认不勾）
    "read_after": False,                # 升级完成后读版本信息（同上）
    "read_target": DEFAULT_READ_TARGET,  # 读版本内容：common=通用 43000300 / internal=厂家扩展 FF100400
    "sa_type": 1,                       # 通配
    "sa_logic": 0,
    "sa_len": 6,
    "sa_addr": "AAAAAAAAAAAA",
    "ca": 0,
    "source": "",
    "target": "",
    "file_version": "v1.0",
    "attr": "E0",
    "category": 0,
    "size_override": 0,                 # 0 = 用所选文件的真实字节数
    "check_kind": 0,
    "check_value": "",
    "check_endian": "big",
    "exec_mode": "now",                 # now = 立即执行（全 FF）；sched = 指定时间
    "exec_time": "",                    # "YYYY-MM-DD HH:MM:SS"
    "license_hex": "",
    "params_expanded": True,
}

#: 未连接时的提示（同时用作按钮 tooltip 与点击提示；design §10 第 1 行）
TIP_NOT_CONNECTED = "未连接串口：请先在主窗口顶部「串口配置」打开串口"

#: crcmod 缺失的可读提示（design §4 硬要求 3 原文）
MISSING_CRCMOD = "协议8 需要 crcmod，请 pip install crcmod"


# ── 纯助手（无 Qt 依赖，可单独断言）────────────────────────────────────


def fmt_hex(data: bytes, limit: int = HEX_LOG_LIMIT) -> str:
    """字节 → 空格分隔大写 HEX；超过 ``limit`` 字节时**只显示头尾两段**，中间用 ``...`` 省略。

    - ``not limit`` 或 ``len(data) <= limit``：**整帧完整显示**（帧不长就没有截断的理由，
      现场定位首先要看的是完整形状，含尾部校验值/结束符 `16H`）；
    - 超过：头 ``limit//2`` 字节 + ``...`` + 尾 ``limit-limit//2`` 字节 + ``(共 N 字节)``
      —— 头段给帧头/APDU 头（含块序号），尾段给帧尾；被省略的正是大文件写块的**数据体本身**。

    例：62 字节的启动传输帧 → 62 字节原样打印；620 字节的写文件帧 →
    ``68 3C 00 ... 24 16  (共 620 字节)``（头尾各 100 字节）。
    """
    raw = data.hex().upper()
    total = len(data)
    if not limit or total <= limit:
        return " ".join(raw[i:i + 2] for i in range(0, len(raw), 2))
    head_len = limit // 2
    tail_len = limit - head_len
    head = " ".join(raw[i:i + 2] for i in range(0, head_len * 2, 2))
    tail = " ".join(raw[i:i + 2] for i in range((total - tail_len) * 2, total * 2, 2))
    return f"{head} ... {tail}  (共 {total} 字节)"


def parse_hex_text(text: str) -> Optional[bytes]:
    """HEX 文本 → 字节；非法返回 ``None``；空串返回 ``b""``（区分「没填」与「填错」）。"""
    cleaned = (text or "").replace(" ", "").replace("\t", "").replace("_", "").strip()
    if not cleaned:
        return b""
    try:
        return bytes.fromhex(cleaned)
    except ValueError:
        return None


def parse_exec_time(text: str) -> Optional[bytes]:
    """「YYYY-MM-DD HH:MM:SS」→ ``date_time_s`` 的 **7 字节数据**（年 2B 大端 + 月日时分秒）。

    规范口径：定长时间类型只有 tag + 定长数据、**没有长度域**（design §6.3；证据 =
    规范示例 ``1C 07 E0 01 14 00 00 00``，其中 ``07E0`` 是年 2016；「全 FF = 立即执行」
    也只在 7 字节数据口径下自洽 —— 长度域不可能是 FF）。长度域由本页调用方直接拼
    ``bytes([0x1C]) + 7B``，不经 ``AXDRCoder``（另一切片正在修它）。
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
        if not 1900 <= dt.year <= 9999:
            return None
        return dt.year.to_bytes(2, "big") + bytes([dt.month, dt.day, dt.hour, dt.minute, dt.second])
    return None


def normalize_hex_address(text: str, addr_len: int) -> bytes:
    """SA 地址字节：按**大端正序**输入，补齐/截断到 ``addr_len``（线上逆序由协议层做）。

    与 ``frame_gen_widget._get_dlt698_sa`` 同一口径（同一公式），只是不给「长度=自动」档
    —— 本页的 SA 必须与升级流程一一对应。非法 HEX 返回 ``b""``。
    """
    raw = parse_hex_text(text)
    if raw is None:
        return b""
    if len(raw) < addr_len:
        return raw + b"\x00" * (addr_len - len(raw))
    return raw[:addr_len]


def check_package_file(path: str) -> str:
    """升级包文件校验；**没问题返回空串**，有问题返回中文原因（design §10 第 2 行）。"""
    if not path:
        return "没有拿到文件路径"
    if not os.path.exists(path):
        return f"文件不存在：{path}"
    if os.path.isdir(path):
        return f"这是一个目录，请拖入具体的升级包文件：{path}"
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        return f"无法读取文件：{path}（{exc}）"
    if size <= 0:
        return f"文件为空（0 字节）：{path}"
    return ""


def _bounded_int(value, default: int, lo: int, hi: int) -> int:
    """宽松取整并夹在 ``[lo, hi]``；越界/非数回落默认值（配置被手改坏也不崩）。"""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return n if lo <= n <= hi else default


#: 日志/面板配色（浅色 / 暗色两套，`restyle_for_theme` 换这套）
LOG_PALETTES = {
    False: {"tx": "#1565C0", "rx": "#008000", "warn": "#B26A00",
            "fail": "#C00000", "info": "#444444",
            "bg": "#FFFFFF", "fg": "#202020", "border": "#C8CDD4", "hint": "#6B7280"},
    True: {"tx": "#64B5F6", "rx": "#81C784", "warn": "#FFB74D",
           "fail": "#EF5350", "info": "#B0BEC5",
           "bg": "#1E1E1E", "fg": "#E0E0E0", "border": "#4A4A4A", "hint": "#9AA0A6"},
}


# ── 拖放区 ───────────────────────────────────────────────────────────────


class _DropArea(QFrame):
    """升级包拖放区：把文件拖进来 → ``file_dropped(path)``；不合格 → ``drop_rejected(原因)``。

    为什么本页自建而不复用 ``main_gui.DragDropTextEdit``：后者按**文本编码**读文件
    （``data("text/plain")``），升级包是二进制；而且它在 ``main_gui`` 内，本页不得
    import main_gui（会成环）。最小实现 = ``setAcceptDrops(True)`` +
    ``dragEnterEvent``（**只有 ``hasUrls()`` 才 accept**，避免把页面里拖选的文本/
    内部控件也当成文件）+ ``dropEvent``（``urls()[0].toLocalFile()``，校验存在 /
    非目录 / 非空后发信号）。

    信号名不叫 ``rejected``：``QDialog.reject()`` 是既有方法名，别在 Qt 类里埋同名成员。
    """

    #: 校验通过的本机文件路径
    file_dropped = Signal(str)
    #: 校验失败（只发信号，由页面决定怎么外显：日志 + 弹框）
    drop_rejected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("UpgradeDropArea")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def dragEnterEvent(self, event) -> None:
        md = event.mimeData()
        if md is not None and md.hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        # 不接 move 的话，部分平台会在 enter 之后立刻取消拖放
        md = event.mimeData()
        if md is not None and md.hasUrls():
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        event.accept()

    def dropEvent(self, event) -> None:
        md = event.mimeData()
        urls = list(md.urls()) if md is not None else []
        if not urls:
            self.drop_rejected.emit("没有可读取的文件（只接受本机文件）")
            event.ignore()
            return
        path = urls[0].toLocalFile()
        err = check_package_file(path)
        if err:
            self.drop_rejected.emit(err)
            event.ignore()
            return
        event.acceptProposedAction()
        self.file_dropped.emit(path)


# ── 页面 ─────────────────────────────────────────────────────────────────


class Dlt698UpgradeWidget(QWidget):
    """协议8 文件传输升级页。

    主窗口需要的全部对外接口（冻结，签名不可改名/改序）：

    - :meth:`set_serial_worker` —— 注入主窗口共享的 ``SerialWorker``；**只订阅信号**，
      绝不开/关端口。
    - :meth:`cleanup` —— 停表 / 断信号 / 落盘配置；**不关闭串口**。
    - :meth:`restyle_for_theme` —— 主题切换后刷新本页动态配色。
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._dark = False

        # 用**属性访问**（不是 `from app_paths import data_path`）：测试可用
        # `_config_sandbox` patch `app_paths.data_path` 把落盘重定向到沙箱。
        self._config_path = str(app_paths.data_path(CONFIG_NAME))

        # ⚠ 落盘定时器必须**先于** `_build_ui()/_load_persisted()` 建好：载入持久化参数
        # 会触发控件 `toggled/valueChanged` → `_schedule_save()`，那时若还没有
        # `_save_timer`，槽里会抛 AttributeError（Qt 吞掉 → 配置保存从此静默失效）。
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_persisted)

        # 每包等待确认的单发定时器（design §4：不用 QThread）
        self._wait_timer = QTimer(self)
        self._wait_timer.setSingleShot(True)
        self._wait_timer.timeout.connect(self._on_timeout)

        self._serial_worker = None
        self._upg = None                 # 惰性 import 的 dl_t698_45_upgrade 模块缓存
        self._rx_buf = bytearray()       # 本页自有的 RX 累积缓冲

        # 传输上下文
        self._state = STATE_IDLE
        self._phase = PHASE_START
        self._path = ""
        self._data = b""
        self._blocks: List[bytes] = []
        self._plan = None                 # dl_t698_45_upgrade.UpgradePlan（分包算术单一来源）
        self._block_idx = 0
        self._confirmed_bytes = 0
        self._piid = 0
        self._attempt = 0                # 当前步骤**已经**重试的次数
        self._sent_frames = 0

        self._build_ui()
        self._load_persisted()
        self._apply_theme_style(self._dark)
        self._on_sa_type_changed()
        self._on_exec_mode_changed()
        self._refresh_summary()
        self._log("[信息] 升级页就绪：拖入升级包 → 开始升级"
                  "（只借用顶部「串口配置」的串口，本页不自开端口）")

    # ======================================================================
    # UI
    # ======================================================================

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # ── ① 拖放区（+「浏览…」兜底）──
        self.drop_area = _DropArea(self)
        drop_row = QHBoxLayout(self.drop_area)
        drop_row.setContentsMargins(10, 8, 10, 8)
        self.lbl_drop_hint = QLabel("拖入升级包文件（任意二进制）")
        self.lbl_file_name = QLabel("未选择文件")
        self.lbl_file_size = QLabel("大小 —")
        for lbl in (self.lbl_file_name, self.lbl_file_size):
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.btn_browse = QPushButton("浏览…")
        self.btn_browse.clicked.connect(self._on_browse)
        drop_row.addWidget(self.lbl_drop_hint)
        drop_row.addSpacing(8)
        drop_row.addWidget(self.lbl_file_name)
        drop_row.addSpacing(6)
        drop_row.addWidget(self.lbl_file_size)
        drop_row.addStretch(1)
        drop_row.addWidget(self.btn_browse)
        self.drop_area.file_dropped.connect(self._on_file_selected)
        self.drop_area.drop_rejected.connect(self._fail_soft)
        outer.addWidget(self.drop_area)

        # ── ② 升级参数（折叠区）──
        self.sec_params = CollapsibleSection("升级参数", key="upgrade_params", expanded=True)
        self.sec_params.toggled.connect(lambda _e: self._schedule_save())
        form = self.sec_params.content_layout()

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("每包字节数"))
        self.spin_block = QSpinBox()
        self.spin_block.setRange(BLOCK_SIZE_MIN, BLOCK_SIZE_MAX)
        self.spin_block.setValue(DEFAULTS["block_size"])
        self.spin_block.setToolTip(
            f"分包大小（{BLOCK_SIZE_MIN}~{BLOCK_SIZE_MAX}）；"
            "块大小 >65535 时协议层自动改用长帧 [6] u32")
        row1.addWidget(self.spin_block)
        row1.addSpacing(12)
        row1.addWidget(QLabel("每包超时(ms)"))
        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(TIMEOUT_MIN, TIMEOUT_MAX)
        self.spin_timeout.setValue(DEFAULTS["timeout_ms"])
        self.spin_timeout.setSingleStep(500)
        self.spin_timeout.setToolTip("等一帧确认的时间；波特率低/包大时调大")
        row1.addWidget(self.spin_timeout)
        row1.addSpacing(12)
        row1.addWidget(QLabel("重试次数"))
        self.spin_retries = QSpinBox()
        self.spin_retries.setRange(RETRY_MIN, RETRY_MAX)
        self.spin_retries.setValue(DEFAULTS["retries"])
        self.spin_retries.setToolTip("同一包最多重发几次；用尽则整轮失败并停止")
        row1.addWidget(self.spin_retries)
        row1.addStretch(1)
        form.addLayout(row1)

        # SA / CA
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("SA 类型"))
        self.combo_sa_type = QComboBox()
        for label, value in SA_TYPES:
            self.combo_sa_type.addItem(label, value)
        self.combo_sa_type.setCurrentIndex(1)          # 默认通配
        self.combo_sa_type.setToolTip(
            "默认通配地址（类型1/长度6/AA×6）；doc 示例用单地址，可切「单地址」复现")
        row2.addWidget(self.combo_sa_type)
        row2.addSpacing(8)
        row2.addWidget(QLabel("逻辑地址"))
        self.combo_sa_logic = QComboBox()
        for v in (0, 1, 2, 3):
            self.combo_sa_logic.addItem(str(v), v)
        row2.addWidget(self.combo_sa_logic)
        row2.addSpacing(8)
        row2.addWidget(QLabel("长度"))
        self.combo_sa_len = QComboBox()
        for v in (1, 2, 3, 4, 5, 6):
            self.combo_sa_len.addItem(str(v), v)
        self.combo_sa_len.setCurrentIndex(5)           # 默认 6
        row2.addWidget(self.combo_sa_len)
        row2.addSpacing(8)
        row2.addWidget(QLabel("地址(HEX)"))
        self.edit_sa = QLineEdit(DEFAULTS["sa_addr"])
        self.edit_sa.setToolTip("按大端正序书写（线上逆序由协议层处理）；广播类型忽略")
        self.edit_sa.setMinimumWidth(140)
        row2.addWidget(self.edit_sa)
        row2.addSpacing(8)
        row2.addWidget(QLabel("CA"))
        self.spin_ca = QSpinBox()
        self.spin_ca.setRange(0, 255)
        row2.addWidget(self.spin_ca)
        row2.addStretch(1)
        form.addLayout(row2)

        # 文件信息
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("源文件"))
        self.edit_source = QLineEdit()
        self.edit_source.setMinimumWidth(120)
        row3.addWidget(self.edit_source)
        row3.addWidget(QLabel("目标文件"))
        self.edit_target = QLineEdit()
        self.edit_target.setMinimumWidth(120)
        row3.addWidget(self.edit_target)
        row3.addWidget(QLabel("版本"))
        self.edit_version = QLineEdit(DEFAULTS["file_version"])
        self.edit_version.setMinimumWidth(70)
        row3.addWidget(self.edit_version)
        row3.addWidget(QLabel("属性(HEX)"))
        self.edit_attr = QLineEdit(DEFAULTS["attr"])
        self.edit_attr.setToolTip(
            "文件属性 = bit-string(SIZE(3))，编码固定 `04 03 <字节>`；"
            "默认 E0（读/写/执行全允许）")
        self.edit_attr.setMinimumWidth(56)
        row3.addWidget(self.edit_attr)
        row3.addWidget(QLabel("类别"))
        self.combo_category = QComboBox()
        for label, value in FILE_CATEGORIES:
            self.combo_category.addItem(label, value)
        row3.addWidget(self.combo_category)
        row3.addStretch(1)
        form.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(QLabel("文件大小(B)"))
        self.spin_size = QSpinBox()
        self.spin_size.setRange(0, 2 ** 31 - 1)
        self.spin_size.setGroupSeparatorShown(True)
        self.spin_size.setToolTip("默认取所选文件的真实字节数；可手工覆盖以复现文档实帧")
        self.spin_size.setMinimumWidth(130)
        row4.addWidget(self.spin_size)
        row4.addSpacing(12)
        row4.addWidget(QLabel("校验"))
        self.combo_check = QComboBox()
        for label, value, _kind in CHECK_TYPES:
            self.combo_check.addItem(label, value)
        row4.addWidget(self.combo_check)
        self.edit_check = QLineEdit()
        self.edit_check.setPlaceholderText("校验值 HEX，可空/可手工覆盖")
        self.edit_check.setMinimumWidth(150)
        row4.addWidget(self.edit_check)
        self.btn_calc = QPushButton("按文件计算")
        self.btn_calc.clicked.connect(self._on_calc_checksum)
        row4.addWidget(self.btn_calc)
        row4.addWidget(QLabel("字节序"))
        self.combo_endian = QComboBox()
        self.combo_endian.addItem("大端", "big")
        self.combo_endian.addItem("小端", "little")
        self.combo_endian.setToolTip("仅 CRC 生效（md5/SHA1 的摘要没有字节序之分）")
        row4.addWidget(self.combo_endian)
        row4.addStretch(1)
        form.addLayout(row4)

        # 执行升级
        row5 = QHBoxLayout()
        self.chk_auto_exec = QCheckBox("传完后自动执行升级")
        self.chk_auto_exec.setChecked(True)
        self.chk_auto_exec.setToolTip("不勾选则只传文件（写文件包全部确认完即结束）")
        row5.addWidget(self.chk_auto_exec)
        row5.addSpacing(12)
        row5.addWidget(QLabel("执行升级时间"))
        self.combo_exec_mode = QComboBox()
        self.combo_exec_mode.addItem("立即执行（全 FF）", "now")
        self.combo_exec_mode.addItem("指定时间", "sched")
        row5.addWidget(self.combo_exec_mode)
        self.edit_exec_time = QLineEdit()
        self.edit_exec_time.setPlaceholderText("YYYY-MM-DD HH:MM:SS")
        self.edit_exec_time.setMinimumWidth(150)
        self.edit_exec_time.setEnabled(False)
        row5.addWidget(self.edit_exec_time)
        row5.addWidget(QLabel("许可(HEX)"))
        self.edit_license = QLineEdit()
        self.edit_license.setPlaceholderText("空 = NULL")
        self.edit_license.setMinimumWidth(110)
        self.edit_license.setToolTip(
            "软件许可 CHOICE{NULL[00], License octet-string [09]}（规范 方法13）：\n"
            "留空 = 发 NULL(00)；填写时请**自带 `09 <长度>` 前缀**"
            "（例：许可 4 字节 `AA BB CC DD` → 填 `09 04 AA BB CC DD`），本页按原样写入、不做包装")
        row5.addWidget(self.edit_license)
        row5.addStretch(1)
        form.addLayout(row5)

        # 读版本信息（可选诊断步骤；默认不勾，勾选状态落盘）
        row6 = QHBoxLayout()
        self.chk_read_before = QCheckBox("升级前读版本信息")
        self.chk_read_before.setToolTip(
            "勾选：开始升级前先发一帧「读版本信息」（GET-Request Normal，OAD 43 00 03 00 ="
            "电气设备(设备管理类) 属性3 版本信息），把设备回的版本内容写进日志，便于升级前后比对。\n"
            "SA/CA 取本页上方配置（默认通配地址 AA AA AA AA AA AA）；"
            "读版本失败**不阻断**升级（重试用尽后记日志并继续）。")
        self.chk_read_after = QCheckBox("升级完成后读版本信息")
        self.chk_read_after.setToolTip(
            "勾选：执行升级被设备确认后再发一帧「读版本信息」，确认新版本已生效。\n"
            "读版本失败同样不阻断（此时升级本身已完成，只记日志）。")
        row6.addWidget(self.chk_read_before)
        row6.addSpacing(12)
        row6.addWidget(self.chk_read_after)
        row6.addSpacing(12)
        row6.addWidget(QLabel("读版本内容"))
        self.combo_read_target = QComboBox()
        for label, key, _short in READ_TARGETS:
            self.combo_read_target.addItem(label, key)
        self.combo_read_target.setToolTip(
            "「通用版本信息」= 标准 OAD 43 00 03 00（电气设备类 属性3）。\n"
            "「内部版本」= 厂家扩展 OAD FF 10 04 00（厂商自定义对象，内部/内部版本信息）。\n"
            "两者都是 GET-Request Normal（APDU 形如 05 01 <PIID> <OAD> 00），"
            "只差 OAD；升级前/升级后两步共用这个选择。")
        row6.addWidget(self.combo_read_target)
        row6.addStretch(1)
        form.addLayout(row6)

        outer.addWidget(self.sec_params)

        # ── 版本信息展示区（读版本信息的逐字段解析结果；本页唯一的「不滚动就能看清」位置）──
        # 升级前 / 升级完成后**并排两栏**：现场要的就是「前后对比」，竖排会互相挤到滚动条里
        self.grp_version = QGroupBox("版本信息")
        ver_box = QVBoxLayout(self.grp_version)
        ver_box.setContentsMargins(8, 6, 8, 6)
        ver_row = QHBoxLayout()
        self.txt_version_pre = QPlainTextEdit()
        self.txt_version_post = QPlainTextEdit()
        for box in (self.txt_version_pre, self.txt_version_post):
            box.setReadOnly(True)
            box.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
            box.setFont(QFont("Consolas", 9))
            box.setMinimumHeight(112)              # ≥7 行（标题 + 6 字段；9pt Consolas 行距 14px）
            box.setMaximumHeight(170)
            box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            ver_row.addWidget(box, 1)
        ver_box.addLayout(ver_row)
        outer.addWidget(self.grp_version)
        self._reset_version_info()

        # ── ③ 工具栏 + 进度 ──
        bar = QHBoxLayout()
        self.btn_start = QPushButton("开始升级")
        gui_utils.set_btn(self.btn_start, "success")
        self.btn_start.clicked.connect(self._on_start)
        self.btn_abort = QPushButton("中止")
        gui_utils.set_btn(self.btn_abort, "danger")
        self.btn_abort.clicked.connect(self._on_abort)
        self.btn_abort.setEnabled(False)
        self.btn_clear = QPushButton("清除")
        gui_utils.set_btn(self.btn_clear, "secondary")
        self.btn_clear.clicked.connect(self._on_clear)
        bar.addWidget(self.btn_start)
        bar.addWidget(self.btn_abort)
        bar.addWidget(self.btn_clear)
        bar.addSpacing(12)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setMinimumWidth(160)
        self.progress.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        bar.addWidget(self.progress, 1)
        self.lbl_progress = QLabel("未开始")
        bar.addWidget(self.lbl_progress)
        outer.addLayout(bar)

        # 按钮宽度只取**下限**（字号可配 ⇒ 写死宽度必裁字，AGENTS §8 陷阱 63）
        gui_utils.fit_btn_width_for_texts(self.btn_start,
                                          ("开始升级", "升级中…", "重新升级"))
        gui_utils.fit_btn_width(self.btn_abort, self.btn_clear, self.btn_browse,
                                self.btn_calc, extra=6)

        # ── ④ 状态行 + 日志（只读，2000 行封顶）──
        self.lbl_status = QLabel(f"状态：{STATE_IDLE}")
        outer.addWidget(self.lbl_status)

        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(2000)
        self.log_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log_text.setFont(QFont("Consolas", 9))
        outer.addWidget(self.log_text, 1)

        # 参数联动（改了才落盘；SA/执行时间切换会改控件可用性）
        for w in (self.spin_block, self.spin_timeout, self.spin_retries, self.spin_ca,
                  self.spin_size, self.edit_sa, self.edit_source, self.edit_target,
                  self.edit_version, self.edit_attr, self.edit_check,
                  self.edit_exec_time, self.edit_license):
            sig = getattr(w, "valueChanged", None) or getattr(w, "textChanged", None)
            if sig is not None:
                sig.connect(lambda *_a: self._schedule_save())
        for c in (self.combo_sa_type, self.combo_sa_logic, self.combo_sa_len,
                  self.combo_category, self.combo_check, self.combo_endian,
                  self.combo_exec_mode):
            c.currentIndexChanged.connect(lambda *_a: self._schedule_save())
        self.chk_auto_exec.toggled.connect(lambda _c: self._schedule_save())
        self.chk_read_before.toggled.connect(lambda _c: self._schedule_save())
        self.chk_read_after.toggled.connect(lambda _c: self._schedule_save())
        self.combo_read_target.currentIndexChanged.connect(lambda *_a: self._schedule_save())
        self.combo_exec_mode.currentIndexChanged.connect(lambda *_a: self._on_exec_mode_changed())
        self.combo_sa_type.currentIndexChanged.connect(lambda *_a: self._on_sa_type_changed())
        self.spin_block.valueChanged.connect(lambda _v: self._refresh_summary())

        self._on_connection_changed(False)

    # ── 主题 ──

    def restyle_for_theme(self, dark: bool) -> None:
        """主题切换：刷新本页**动态**配色（日志色卡、拖放区、提示文字）。

        只影响此后写入的日志行（历史行已按旧色写进文档，重刷成本高于收益）。
        """
        self._dark = bool(dark)
        self._apply_theme_style(self._dark)

    def _apply_theme_style(self, dark: bool) -> None:
        p = LOG_PALETTES[bool(dark)]
        self._palette = p
        self.log_text.setStyleSheet(
            f"QPlainTextEdit {{ background-color: {p['bg']}; color: {p['fg']};"
            f" border: 1px solid {p['border']}; }}")
        for box in (self.txt_version_pre, self.txt_version_post):
            box.setStyleSheet(
                f"QPlainTextEdit {{ background-color: {p['bg']}; color: {p['fg']};"
                f" border: 1px solid {p['border']}; }}")
        self.drop_area.setStyleSheet(
            f"QFrame#UpgradeDropArea {{ background-color: {p['bg']};"
            f" border: 1px dashed {p['border']}; border-radius: 4px; }}")
        self.lbl_drop_hint.setStyleSheet(f"color: {p['hint']};")

    # ======================================================================
    # 串口订阅（只订阅，绝不开/关端口）
    # ======================================================================

    def set_serial_worker(self, worker) -> None:
        """绑定主窗口共享的串口线程（与 `serial_tool_widget` / `frame_gen_widget` 同一约定）。

        只 connect ``raw_data_received`` / ``connection_changed`` / ``error_occurred``；
        不负责打开/关闭端口 —— 端口生命周期归顶部「串口配置」。
        **不订阅 ``frame_received``**：698.45 帧会被 ``SerialWorker`` 的 645/FT1.2
        容错分支截断（见模块 docstring）。
        """
        old = self._serial_worker
        if old is not None:
            self._detach(old)
        self._serial_worker = worker
        self._rx_buf.clear()
        if worker is None:
            self._on_connection_changed(False)
            return
        worker.raw_data_received.connect(self._on_raw_data)
        worker.connection_changed.connect(self._on_connection_changed)
        worker.error_occurred.connect(self._on_serial_error)
        self._on_connection_changed(bool(worker.is_open()))

    def _detach(self, worker) -> None:
        """断掉本页对 worker 的三条订阅（换 worker / cleanup 用；失败宽容）。"""
        for signal, slot in (
            (worker.raw_data_received, self._on_raw_data),
            (worker.connection_changed, self._on_connection_changed),
            (worker.error_occurred, self._on_serial_error),
        ):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

    def _on_connection_changed(self, connected: bool) -> None:
        """连接状态驱动「开始升级」可用性（design §10 第 1 行：未连接零字节发送）。"""
        if connected:
            self.btn_start.setEnabled(True)
            self.btn_start.setToolTip("")
        else:
            self.btn_start.setEnabled(False)
            self.btn_start.setToolTip(TIP_NOT_CONNECTED)

    def _on_serial_error(self, message: str) -> None:
        self._log(f"[失败] 串口错误：{message}", "fail")

    def _worker(self):
        """可用的 worker（未注入或未开串口 ⇒ ``None``）；发送前的唯一判据。"""
        w = self._serial_worker
        if w is None or not w.is_open():
            return None
        return w

    def _write(self, frame: bytes) -> bool:
        """唯一的发送出口：``write_raw``（静默）；成功计数 +1。"""
        w = self._worker()
        if w is None:
            self._stop_and_fail(f"串口未连接，已停止（这 {len(frame)} 字节未写入）")
            return False
        try:
            ok = bool(w.write_raw(frame))
        except Exception as exc:                      # 串口层任何异常都必须外显
            self._stop_and_fail(f"write_raw 异常：{type(exc).__name__}: {exc}")
            return False
        if not ok:
            self._stop_and_fail("write_raw 返回 False（串口写入失败），已停止")
            return False
        self._sent_frames += 1
        return True

    def _stop_and_fail(self, reason: str) -> None:
        self._wait_timer.stop()
        self._state = STATE_FAILED
        self._set_status()
        self._log(f"[失败] {reason}", "fail")
        self._finish_buttons()

    # ======================================================================
    # RX 组帧（design §5）
    # ======================================================================

    def _complete_frame_len(self, buf) -> int:
        """``buf`` 首部是否为一段**完整且末字节自证**的 698.45 帧；是则返回整帧长度，否则 0。

        判据全部来自分帧单一来源 :mod:`frame_deframe`（``L + 2`` + 前导 FEH 容忍），
        末字节 ``16H`` 自证在此补齐（分帧族只算长度、自证在调用方，与串口页同一约定）。
        """
        need = frame_deframe.frame_length_for(DEFRAME_STRATEGY, buf)
        if need and len(buf) >= need and buf[need - 1] == 0x16:
            return need
        return 0

    def _on_raw_data(self, data: bytes) -> None:
        """累积原始字节 → 用 ``frame_deframe`` 的 698.45 判据切出**完整**帧。

        判据（与串口页同一实现，单一来源）：``L + 2``、**末字节必须 ``0x16``** 才算收全、
        帧首连续前导 FEH 容忍。切不出完整帧时先尝试**重同步**（丢弃确定不是帧起点的
        字节，见 :meth:`_resync_junk`），丢不动才继续等下一批字节。
        """
        if not data:
            return
        self._rx_buf.extend(data)
        while True:
            need = self._complete_frame_len(self._rx_buf)
            if need:
                frame = bytes(self._rx_buf[:need])
                del self._rx_buf[:need]
                self._on_frame(frame)
                continue
            if self._resync_junk():
                continue          # 丢掉了垃圾/错位字节 ⇒ 重新判长度（同一交付里就能切出真帧）
            break                 # 既无完整帧、又无从重同步 ⇒ 等更多字节
        # 缓冲治理：只有「没有半截帧在等」时才丢噪声，正在等的必须留着续帧
        if len(self._rx_buf) > RX_BUF_MAX and not frame_deframe.frame_incomplete(
                DEFRAME_STRATEGY, self._rx_buf):
            dropped = len(self._rx_buf)
            self._rx_buf.clear()
            self._log(f"[信息] 丢弃 {dropped} 字节无法组帧的数据（缓冲上限 {RX_BUF_MAX}）",
                      "info")

    def _resync_junk(self) -> int:
        """丢弃**确定不可能是帧起点**的前导字节，返回丢弃数。

        698.45 帧的起点只有两种：``68``（起始符）与 ``FE``（唤醒前导）。判据保守：只要
        候选起点处**确有一段帧在等**（``frame_deframe.frame_incomplete``）或**已有整帧
        可取**（:meth:`_complete_frame_len`），就一个字节都不动；否则该字节不可能开启任何
        合法 698.45 帧，连同它之前的字节一起丢掉。

        这条路径要挡住的三种现场（都实测过：不挡就会把后续**所有**确认卡在缓冲头，
        整轮升级被一次线噪判成超时）：
          ① 前导 ``FE`` 之后不是 ``68``（线噪进了前导段）；
          ② 以 ``68`` 开头但长度域不可信（错帧/串扰，``frame_length_for`` 判 0）；
          ③ 按长度域已到齐而末字节不是 ``16H``（错位帧）。
        丢弃后同一次交付里的真确认即可被切出，不必等下一条报文。
        """
        buf = self._rx_buf
        k = 0
        while k < len(buf):
            if buf[k] not in (0x68, 0xFE):
                k += 1                    # 连 68H/FEH 都不是 ⇒ 必非帧起点
                continue
            rest = buf[k:]                # 首字节候选 ⇒ 交给分帧单一来源判定
            if self._complete_frame_len(rest) or frame_deframe.frame_incomplete(
                    DEFRAME_STRATEGY, rest):
                break
            k += 1
        if k:
            del buf[:k]
            self._log(f"[信息] 丢弃 {k} 字节非帧起点数据（错帧/噪声重同步：698.45 帧以 "
                      "68H 开头，FEH 前导后须紧跟 68H）", "info")
        return k

    def _on_frame(self, frame: bytes) -> None:
        """一帧完整 698.45 帧 → 判定是否为**本步**的确认（design §5 判定 + §10）。"""
        if self._state in TERMINAL_STATES:
            return                          # 不在传输中：不打扰（别的页也在看同一口）
        upg = self._upgrade_module()
        if upg is None:
            return
        try:
            if self._phase in VER_PHASES:
                res = upg.check_get_response(frame, self._read_oad(upg))
            else:
                res = upg.check_action_response(frame, self._expected_omd(upg))
        except Exception as exc:
            self._log(f"[RX] {fmt_hex(frame)}  → 确认判定异常："
                      f"{type(exc).__name__}: {exc}", "warn")
            return
        if not isinstance(res, dict):
            self._log(f"[RX] {fmt_hex(frame)}  → 确认判定返回值不是 dict（{res!r}）", "warn")
            return
        dar = res.get("dar")
        reason = str(res.get("reason") or "未知原因")
        if res.get("ok"):
            if self._phase in VER_PHASES:
                # 帧一行，解析明细写在**帧的下面**（用户反馈：贴在帧尾要横向拖到最后才看得见）
                self._log(f"[RX] {fmt_hex(frame)}", "rx")
                self._record_version_info(self._phase, res)
                self._log_version_detail(res)
            else:
                # DAR 可能因 PIID-ACD 位（bit7）带上标志位，判据只在协议层，这里照实显示
                self._log(f"[RX] {fmt_hex(frame)}  → DAR={self._dar_value(dar)} 成功", "rx")
            self._on_ack()
            return
        if isinstance(dar, int) and (dar & 0x7F) != 0:
            # §10：DAR≠0 → 日志给 DAR 值与含义，按重试处理
            self._log(f"[RX] {fmt_hex(frame)}  → 失败 DAR={self._dar_value(dar)}（{reason}）",
                      "fail")
            self._retry_or_fail(f"DAR={self._dar_value(dar)}（{reason}）")
            return
        # §10：非本步 OMD 的帧 / 解析失败帧 → WARN 并忽略，不计确认
        self._log(f"[RX] {fmt_hex(frame)}  → 忽略（{reason}）", "warn")

    @staticmethod
    def _dar_value(dar) -> object:
        """DAR 显示值：剥掉 PIID-ACD 之类可能混入的标志位（仅影响显示，判定在协议层）。"""
        if isinstance(dar, int):
            return dar & 0x7F
        return dar

    # ======================================================================
    # 版本信息展示区（逐字段明细；日志只放「帧一行 + 明细若干行」）
    # ======================================================================

    @staticmethod
    def _pad_cjk(text: str, width: int) -> str:
        """按**显示列宽**补空格（CJK 算 2 列）—— 纯 ``str.ljust`` 对中文名会错位。"""
        cols = sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)
        return text + " " * max(0, width - cols)

    @classmethod
    def _version_detail_lines(cls, rows: List[dict], indent: str = "  ") -> List[str]:
        """版本明细行：`名称 = 值   [原始字节]`（名称按显示宽度对齐）。"""
        if not rows:
            return []
        width = max(sum(2 if ord(ch) > 0x2E80 else 1 for ch in str(r.get("名称", "")))
                    for r in rows)
        lines = []
        for row in rows:
            name = cls._pad_cjk(str(row.get("名称", "")), width)
            raw = str(row.get("原始", "") or "")
            tail = f"   [{raw}]" if raw else ""
            lines.append(f"{indent}{name} = {row.get('值', '')}{tail}")
        return lines

    def _reset_version_info(self) -> None:
        """清空两个读版本结果（每次「开始升级」/「清除」都重置，避免上一轮的残留误导）。"""
        self._ver_info = {"pre": None, "post": None}
        self._render_version_panel()

    def _record_version_info(self, phase: str, res: Optional[dict] = None,
                            reason: str = "") -> None:
        """记下本步读版本结果（成功给逐字段明细；失败给原因）并刷新展示区。"""
        where = "pre" if phase == PHASE_VER_PRE else "post"
        self._ver_info[where] = {
            "target": self._read_target_short(),
            "time": datetime.now().strftime("%H:%M:%S"),
            "rows": list((res or {}).get("rows") or []),
            "note": str((res or {}).get("version") or ""),
            "reason": str(reason or ""),
        }
        self._render_version_panel()

    def _render_version_panel(self) -> None:
        """按本轮结果重画展示区（升级前 / 升级完成后 各一栏，便于前后对比）。"""
        for key, title, box in (("pre", "升级前", self.txt_version_pre),
                                ("post", "升级完成后", self.txt_version_post)):
            info = self._ver_info.get(key)
            if not info:
                box.setPlainText(f"{title}：（未读取）")
                continue
            head = f"{title} · {info['target']} · {info['time']}"
            if info["reason"]:
                box.setPlainText(f"{head} —— 未读到：{info['reason']}")
                continue
            lines = [head] + self._version_detail_lines(info["rows"])
            if len(lines) == 1:
                lines.append(f"（无明细）{info['note']}")
            box.setPlainText("\n".join(lines))

    def _log_version_detail(self, res: dict) -> None:
        """把读版本的解析结果**写在帧行的下面若干行**（而不是同一行尾部）。

        用户反馈：贴在帧尾时一行太长、日志是 NoWrap，要横向拖到最后才看得见内容。
        """
        rows = list(res.get("rows") or [])
        self._log(f"  → {self._version_line(res)}"
                  + (f"（{len(rows)} 项）" if rows else ""), "rx")
        for line in self._version_detail_lines(rows, indent="    "):
            self._log(line, "rx")

    def _version_line(self, res: dict) -> str:
        """读版本结果的**标签行**：`版本信息（升级前·内部）读取成功`（逐字段明细在下面几行）。"""
        where = "升级前" if self._phase == PHASE_VER_PRE else "升级完成后"
        head = f"版本信息（{where}·{self._read_target_short()}）"
        if res.get("rows"):
            return f"{head}读取成功"
        text = str(res.get("version") or "").strip()
        return f"{head}：{text}" if text else f"{head}：{res.get('reason') or '响应未带数据'}"

    # ======================================================================
    # 协议层惰性 import（design §4 硬要求 3）
    # ======================================================================

    def _upgrade_module(self):
        """**函数内**惰性 import ``dl_t698_45_upgrade``（它顶层 import crcmod 系模块）。

        失败时明确提示 ``MISSING_CRCMOD`` 并返回 None（不崩、不静默）。
        """
        if self._upg is not None:
            return self._upg
        try:
            import dl_t698_45_upgrade as upg
        except ImportError as exc:
            self._log(f"[失败] {MISSING_CRCMOD}（原始错误：{exc}）", "fail")
            QMessageBox.warning(self, "协议8 升级", MISSING_CRCMOD)
            return None
        self._upg = upg
        return upg

    def _expected_omd(self, upg) -> bytes:
        if self._phase == PHASE_START:
            return upg.OMD_START
        if self._phase == PHASE_BLOCKS:
            return upg.OMD_WRITE
        return upg.OMD_EXEC

    def _num_blocks(self) -> int:
        """总包数（一律取 `UpgradePlan.num_blocks`，本页不再自己算 ceil）。"""
        return self._plan.num_blocks if self._plan is not None else 0

    def _total_bytes(self) -> int:
        """进度分母（同上：`UpgradePlan.total_bytes`）。"""
        return self._plan.total_bytes if self._plan is not None else len(self._data)

    def _step_label(self) -> str:
        if self._phase == PHASE_VER_PRE:
            return "升级前读版本信息"
        if self._phase == PHASE_VER_POST:
            return "升级完成后读版本信息"
        if self._phase == PHASE_START:
            return "启动传输"
        if self._phase == PHASE_BLOCKS:
            return f"第 {self._block_idx + 1}/{self._num_blocks()} 包"
        return "执行升级"

    # ======================================================================
    # 状态机（design §4：单发 QTimer + 标志位）
    # ======================================================================

    def _send_current_step(self) -> None:
        """组**当前这一步**的帧并发送 + 起超时表；PIID 每帧自增（& 0x7F）。"""
        upg = self._upgrade_module()
        if upg is None:
            return
        sa, ca, err = self._sa_ca()
        if err:
            self._abort_with(err)
            return
        piid = self._piid
        self._piid = (self._piid + 1) & 0x7F
        try:
            if self._phase in VER_PHASES:
                # 读版本信息：SA/CA 取页面配置（默认通配 AAAAAA，与升级传输同一份）；
                # OAD 取「读版本内容」下拉（通用 43000300 / 厂家扩展内部版本 FF100400）
                frame = upg.build_read_version(sa, ca, piid, oad=self._read_oad(upg))
            elif self._phase == PHASE_START:
                frame = upg.build_start_transfer(
                    sa, ca, piid, self._file_info(upg), self.spin_block.value(),
                    self._check_type(), self._check_value(upg))
            elif self._phase == PHASE_BLOCKS:
                frame = upg.build_write_block(
                    sa, ca, piid, self._block_idx, self._blocks[self._block_idx])
            else:
                frame = upg.build_exec_upgrade(
                    sa, ca, piid, self._exec_time(), self._license())
        except ValueError as exc:
            self._abort_with(f"组帧失败：{exc}")
            return
        except Exception as exc:                      # 协议层任何异常都必须外显
            self._abort_with(f"组帧异常：{type(exc).__name__}: {exc}")
            return
        label = self._step_label()
        if not self._write(frame):
            return
        self._log(f"[TX] {fmt_hex(frame)}  ({label})", "tx")
        self._set_status()
        self._wait_timer.start(self.spin_timeout.value())

    def _on_ack(self) -> None:
        """收到本步确认：停表 → 只把**已确认**的包计入进度 → 推进下一步。"""
        self._wait_timer.stop()
        self._attempt = 0
        if self._phase == PHASE_VER_PRE:
            # 可选诊断步骤已确认 ⇒ 照常进入启动传输
            self._phase = PHASE_START
            self._send_current_step()
            return
        if self._phase == PHASE_START:
            self._phase = PHASE_BLOCKS
            self._block_idx = 0
            self._state = STATE_TRANSFERRING
            if not self._blocks:
                self._abort_with("分包列表为空，无法写文件")
                return
            self._send_current_step()
            return
        if self._phase == PHASE_BLOCKS:
            self._confirmed_bytes += len(self._blocks[self._block_idx])
            if self._block_idx + 1 < self._num_blocks():
                self._block_idx += 1
                self._refresh_progress()      # 先推进再刷：显示**在飞**的那一包
                self._send_current_step()
                return
            self._refresh_progress()
            if self.chk_auto_exec.isChecked():
                self._phase = PHASE_EXEC
                self._state = STATE_FINISHING
                self._send_current_step()
            else:
                # 未发执行升级 ⇒ 没有「升级完成」这回事，故不读升级后版本（勾了也要说明）
                if self.chk_read_after.isChecked():
                    self._log("[信息] 未勾「传完后自动执行升级」⇒ 不读升级后版本信息", "info")
                self._succeed("文件传输完成（未发送执行升级命令）")
            return
        if self._phase == PHASE_EXEC:
            if self.chk_read_after.isChecked():
                self._log("[信息] 执行升级已确认，继续读版本信息（升级完成后）", "info")
                self._phase = PHASE_VER_POST
                self._state = STATE_FINISHING
                self._send_current_step()
                return
            self._succeed("执行升级命令已确认，升级流程完成")
            return
        self._succeed("升级流程完成（已读升级后版本信息）")

    def _succeed(self, message: str) -> None:
        self._wait_timer.stop()
        self._state = STATE_DONE
        self.progress.setValue(100)
        self.lbl_progress.setText("升级完成 100%")
        self._set_status()
        self._log(f"[信息] {message}（进度 100%，"
                  f"已发送 {self._sent_frames} 帧）", "info")
        self._finish_buttons()

    def _on_timeout(self) -> None:
        """本步没等到确认 → 按重试处理（design §10「超时」行）。"""
        if self._state in TERMINAL_STATES:
            return
        self._retry_or_fail(f"{self.spin_timeout.value()}ms 内无确认响应"
                            f"（当前缓冲 {len(self._rx_buf)} 字节）")

    def _retry_or_fail(self, why: str) -> None:
        """同一包重发（PIID 自增）；重试用尽则整轮停止并说明还有多少包没发。"""
        self._wait_timer.stop()
        if self._state in (STATE_DONE, STATE_ABORTED, STATE_FAILED):
            return
        limit = self.spin_retries.value()
        step = self._step_label()
        if self._attempt < limit:
            self._attempt += 1
            prefix = "[超时]" if "无确认响应" in why else "[失败]"
            self._log(f"{prefix} {step} {why}，已重试 {self._attempt}/{limit}，重发", "warn")
            self._send_current_step()
            return
        if self._phase in VER_PHASES:
            # 读版本是**可选诊断步骤**：用尽重试也**不阻断**升级流程（用户需求）
            self._continue_after_version_failure(why)
            return
        remaining = self._pending_blocks()
        if self._phase == PHASE_BLOCKS:
            detail = (f"第 {self._block_idx + 1} 包失败，已停止，"
                      f"未发送后续 {remaining} 包（原因：{why}）")
        else:
            detail = f"{step} 失败，已停止（原因：{why}）"
        self._state = STATE_FAILED
        self._set_status()
        self._log(f"[失败] {detail}", "fail")
        self._finish_buttons()
        QMessageBox.warning(self, "升级已停止", detail)

    def _pending_blocks(self) -> int:
        """还没发送的写文件包数（重试用尽时的「未发送后续 N 包」文案）。"""
        if self._phase != PHASE_BLOCKS:
            return 0
        return max(0, self._num_blocks() - (self._block_idx + 1))

    def _continue_after_version_failure(self, why: str) -> None:
        """读版本信息用尽重试：**记日志后继续**（升级流程不因诊断步骤停下）。

        `ver_pre` → 照常发启动传输（状态机停在 starting）；`ver_post` → 升级本身已完成，
        直接按成功收尾（文案里说明读版本未成功，明细在日志）。
        """
        if self._phase == PHASE_VER_PRE:
            self._record_version_info(PHASE_VER_PRE, reason=why)
            self._log(f"[信息] 读版本信息未成功（{why}），继续升级流程", "warn")
            self._phase = PHASE_START
            self._attempt = 0
            self._send_current_step()
            return
        self._record_version_info(PHASE_VER_POST, reason=why)
        self._log(f"[信息] 读版本信息未成功（{why}），升级流程已结束", "warn")
        self._succeed("升级流程完成（读版本信息未成功，原因见日志）")

    def _abort_with(self, reason: str) -> None:
        self._wait_timer.stop()
        self._state = STATE_FAILED
        self._set_status()
        self._log(f"[失败] {reason}", "fail")
        self._finish_buttons()

    # ======================================================================
    # 参数装配（全部来自控件；非法输入即拒绝开始）
    # ======================================================================

    def _sa_ca(self):
        upg = self._upgrade_module()
        if upg is None:
            return b"", 0, "协议层未就绪"
        addr_type = int(self.combo_sa_type.currentData())
        logic = int(self.combo_sa_logic.currentData())
        addr_len = int(self.combo_sa_len.currentData())
        if parse_hex_text(self.edit_sa.text()) is None:
            return b"", 0, f"SA 地址不是合法 HEX：{self.edit_sa.text()!r}"
        # 广播地址固定 1 字节 AA，协议层忽略长度/地址体
        body = b"" if addr_type == 3 else normalize_hex_address(self.edit_sa.text(), addr_len)
        try:
            sa = upg.build_sa(addr_type=addr_type, logic_addr=logic,
                              addr_len=addr_len, addr_bytes=body)
        except ValueError as exc:
            return b"", 0, f"SA 地址非法：{exc}"
        return sa, int(self.spin_ca.value()), ""

    def _file_info(self, upg) -> bytes:
        return upg.build_file_info(
            size=self._effective_size(),
            source=self.edit_source.text(),
            target=self.edit_target.text(),
            attr_byte=self._attr_byte(),
            version=self.edit_version.text(),
            category=int(self.combo_category.currentData() or 0),
        )

    def _effective_size(self) -> int:
        """文件大小（协议字段）：手工覆盖优先，否则取分包计划的总字节数（design §3.2）。"""
        override = int(self.spin_size.value())
        return override if override > 0 else self._total_bytes()

    def _attr_byte(self) -> int:
        raw = parse_hex_text(self.edit_attr.text())
        if not raw:
            return 0xE0                     # 空输入 ⇒ 默认 E0（design §3.2）
        return raw[0]

    def _check_type(self) -> int:
        return int(self.combo_check.currentData() or 0)

    def _check_value(self, upg) -> bytes:
        """校验值：手工填写**优先且原样使用**；否则按文件内容计算（design §3.6）。"""
        manual = parse_hex_text(self.edit_check.text())
        if manual is None:
            raise ValueError(f"校验值不是合法 HEX：{self.edit_check.text()!r}")
        if manual:
            return manual
        if not self._data:
            return b""
        return upg.calc_checksum_value(self._data, kind=self._checksum_kind(),
                                       endian=self._endian())

    def _checksum_kind(self) -> str:
        for _label, value, kind in CHECK_TYPES:
            if value == self._check_type():
                return kind
        return "crc"

    def _endian(self) -> str:
        e = self.combo_endian.currentData()
        return e if e in ("big", "little") else "big"

    def _exec_time(self) -> Optional[bytes]:
        """``None`` ⇒ 由协议层用「立即执行」（全 FF）；指定时间则给 7 字节数据。"""
        if self.combo_exec_mode.currentData() != "sched":
            return None
        text = self.edit_exec_time.text().strip()
        parsed = parse_exec_time(text)
        if parsed is None:
            raise ValueError(f"执行升级时间格式不对：{text!r}（应为 YYYY-MM-DD HH:MM:SS）")
        return parsed

    def _license(self) -> bytes:
        raw = parse_hex_text(self.edit_license.text())
        if raw is None:
            raise ValueError(f"软件许可不是合法 HEX：{self.edit_license.text()!r}")
        return raw

    # ======================================================================
    # 交互
    # ======================================================================

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择升级包", "", "所有文件 (*.*)")
        if path:
            self._on_file_selected(path)

    def _on_file_selected(self, path: str) -> None:
        if self._state in (STATE_STARTING, STATE_TRANSFERRING, STATE_FINISHING):
            # 传输中途换文件会**换掉** `_blocks`/`_plan`，而 `_block_idx` 还指向旧计划：
            # 轻则把新文件的第 i 块当成旧包发出去，重则 `_blocks[_block_idx]` 越界抛
            # IndexError 把状态机打死（实测：换 30B 文件后确认帧直接 IndexError）。要换
            # 文件先「中止」——不做静默替换，也不半途改计划。
            self._fail_soft("升级进行中：已忽略这次选择的文件（请先「中止」再换文件）")
            return
        err = check_package_file(path)
        if err:
            self._fail_soft(err)
            return
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError as exc:
            self._fail_soft(f"文件读取失败：{path}（{exc}）")
            return
        self._path = path
        self._data = data
        # 「文件大小」跟着真实字节数走（用户仍可手工覆盖以复现文档实帧）
        self.spin_size.setValue(min(len(data), self.spin_size.maximum()))
        self._rebuild_blocks(announce=True)
        self._refresh_summary()

    def _rebuild_blocks(self, announce: bool = False) -> None:
        """按当前「每包字节数」重新分包（design §3.3）。

        块列表取 `split_blocks`；**总包数/末包字节数/进度分母一律取 `UpgradePlan`**
        （分包算术的单一来源，本页不再自己算一遍 ceil）。
        """
        upg = self._upgrade_module()
        if upg is None or not self._data:
            self._blocks = []
            self._plan = None
            return
        try:
            self._blocks = upg.split_blocks(self._data, self.spin_block.value())
            self._plan = upg.UpgradePlan.for_data(self._data, self.spin_block.value())
        except Exception as exc:
            self._blocks = []
            self._plan = None
            self._fail_soft(f"分包失败：{type(exc).__name__}: {exc}")
            return
        if announce and self._blocks:
            self._log(f"[信息] 分包完成：{self._plan.total_bytes:,} 字节 → "
                      f"{self._plan.num_blocks} 包（每包 ≤{self._plan.block_size} 字节，"
                      f"末包 {self._plan.last_block_bytes} 字节）", "info")

    def _refresh_summary(self, *_a) -> None:
        """拖放区的文件名/大小 + 空闲态的包数摘要。"""
        if not self._path:
            self.lbl_file_name.setText("未选择文件")
            self.lbl_file_size.setText("大小 —")
        else:
            self.lbl_file_name.setText(os.path.basename(self._path))
            self.lbl_file_size.setText(f"大小 {self._total_bytes():,} B")
        if self._state in TERMINAL_STATES:
            if self._state == STATE_DONE and self._confirmed_bytes >= self._total_bytes() > 0:
                self.lbl_progress.setText("升级完成 100%")
            elif self._num_blocks():
                self.lbl_progress.setText(f"共 {self._num_blocks()} 包，待开始")
            else:
                self.lbl_progress.setText("未开始")

    def _validate_inputs(self) -> str:
        """开始前的参数校验；返回中文原因（空串 = 可以开始）。"""
        if not self._data:
            return "请先拖入（或浏览选择）升级包文件"
        block_size = self.spin_block.value()
        if not (BLOCK_SIZE_MIN <= block_size <= BLOCK_SIZE_MAX):
            return f"每包字节数必须在 {BLOCK_SIZE_MIN}~{BLOCK_SIZE_MAX} 之间"
        if parse_hex_text(self.edit_sa.text()) is None:
            return f"SA 地址不是合法 HEX：{self.edit_sa.text()!r}"
        attr = parse_hex_text(self.edit_attr.text())
        if attr is None:
            return f"文件属性不是合法 HEX：{self.edit_attr.text()!r}"
        if parse_hex_text(self.edit_license.text()) is None:
            return f"软件许可不是合法 HEX：{self.edit_license.text()!r}"
        if parse_hex_text(self.edit_check.text()) is None:
            return f"校验值不是合法 HEX：{self.edit_check.text()!r}"
        if self.combo_exec_mode.currentData() == "sched" and \
                parse_exec_time(self.edit_exec_time.text()) is None:
            return "执行升级时间格式应为 YYYY-MM-DD HH:MM:SS"
        return ""

    def _on_start(self) -> None:
        if self._state in (STATE_STARTING, STATE_TRANSFERRING, STATE_FINISHING):
            return
        if self._worker() is None:
            self._fail_soft(TIP_NOT_CONNECTED)
            return
        err = self._validate_inputs()
        if err:
            self._fail_soft(err)
            return
        if self._upgrade_module() is None:
            return

        self._rebuild_blocks()
        if not self._blocks:
            self._fail_soft("分包结果为空（请检查文件内容与每包字节数）")
            return
        self._phase = PHASE_VER_PRE if self.chk_read_before.isChecked() else PHASE_START
        self._block_idx = 0
        self._confirmed_bytes = 0
        self._piid = 0                      # doc：启动传输 PIID=0、首块 PIID=1
        self._attempt = 0
        self._sent_frames = 0
        self._rx_buf.clear()
        self._reset_version_info()          # 展示区按本轮结果重画（不留上一轮的版本）
        self.progress.setValue(0)
        self.lbl_progress.setText("准备中")
        self._state = STATE_STARTING
        self.btn_start.setEnabled(False)
        self.btn_abort.setEnabled(True)
        self._freeze_plan_inputs(True)
        self._log(f"[信息] 开始升级：{os.path.basename(self._path)}"
                  f"（{self._total_bytes():,} B → {self._num_blocks()} 包，"
                  f"每包超时 {self.spin_timeout.value()}ms，"
                  f"重试用尽 {self.spin_retries.value()} 次；"
                  f"升级前读版本={'是' if self.chk_read_before.isChecked() else '否'}，"
                  f"升级后读版本={'是' if self.chk_read_after.isChecked() else '否'}；"
                  f"读版本内容={self._read_target_label()}）", "info")
        self._send_current_step()

    def _freeze_plan_inputs(self, frozen: bool) -> None:
        """传输进行中冻结会**改变计划**的输入（每包字节数 + 两个读版本开关 + 读版本内容）。

        改这些值会让在飞的帧与后续帧不同源（AGENTS §8 陷阱 77 / spec §7j 的既有契约）；
        按钮门控的复位统一走 :meth:`_finish_buttons`，不要在别处各写一份。
        """
        self.spin_block.setEnabled(not frozen)
        self.chk_read_before.setEnabled(not frozen)
        self.chk_read_after.setEnabled(not frozen)
        self.combo_read_target.setEnabled(not frozen)

    def _read_target_key(self) -> str:
        """当前「读版本内容」键（`common` / `internal`）；未知值回落默认。"""
        key = self.combo_read_target.currentData()
        for _label, k, _short in READ_TARGETS:
            if k == key:
                return k
        return DEFAULT_READ_TARGET

    def _read_oad(self, upg) -> bytes:
        """当前「读版本内容」对应的 OAD —— **协议常量只在 :mod:`dl_t698_45_upgrade` 一份**。"""
        if self._read_target_key() == "internal":
            return upg.OAD_INTERNAL_VERSION
        return upg.OAD_VERSION

    def _read_target_label(self) -> str:
        """下拉文案（开始日志用）。"""
        for label, key, _short in READ_TARGETS:
            if key == self._read_target_key():
                return label
        return READ_TARGETS[0][0]

    def _read_target_short(self) -> str:
        """日志短名（`通用` / `内部`）。"""
        for _label, key, short in READ_TARGETS:
            if key == self._read_target_key():
                return short
        return READ_TARGETS[0][2]

    def _on_abort(self) -> None:
        """中止：停表、置 aborted、不再发送（design §4）。"""
        if self._state in TERMINAL_STATES:
            self._wait_timer.stop()
            return
        self._wait_timer.stop()
        self._state = STATE_ABORTED
        self._set_status()
        self._log(f"[信息] 已中止（停在 {self._step_label()}，"
                  f"已确认 {self._confirmed_bytes:,}/{self._total_bytes():,} 字节）", "info")
        self._finish_buttons()

    def _on_clear(self) -> None:
        """清除：停表 + 清空日志/进度/收帧缓冲（**保留**文件与参数，便于原地重跑）。

        进行中点「清除」= 停掉本轮（不通知设备），所以按钮门控要一并复位
        （``_finish_buttons``）——否则「开始升级」会永久停在禁用态，页面只能靠重连恢复。
        """
        interrupted = self._state in (STATE_STARTING, STATE_TRANSFERRING, STATE_FINISHING)
        self._wait_timer.stop()
        self._rx_buf.clear()
        self.log_text.clear()
        self._reset_version_info()
        self.progress.setValue(0)
        self._confirmed_bytes = 0
        self._sent_frames = 0
        self._state = STATE_IDLE
        self._phase = PHASE_START
        self._block_idx = 0
        self._attempt = 0
        self._set_status()
        self._refresh_summary()
        self._finish_buttons()
        self._log("[信息] 已清除日志与进度"
                  + ("（本轮传输已停止，未通知设备）" if interrupted else ""), "info")

    def _on_calc_checksum(self) -> None:
        if not self._data:
            self._fail_soft("请先选择升级包文件（校验值按文件内容计算）")
            return
        upg = self._upgrade_module()
        if upg is None:
            return
        try:
            value = upg.calc_checksum_value(self._data, kind=self._checksum_kind(),
                                            endian=self._endian())
        except Exception as exc:
            self._fail_soft(f"计算校验值失败：{type(exc).__name__}: {exc}")
            return
        self.edit_check.setText(bytes(value).hex().upper())
        self._log(f"[信息] 校验值（{self._checksum_kind().upper()}/{self._endian()}）"
                  f"= {bytes(value).hex().upper()}", "info")

    def _on_exec_mode_changed(self) -> None:
        sched = self.combo_exec_mode.currentData() == "sched"
        self.edit_exec_time.setEnabled(bool(sched))
        if sched and not self.edit_exec_time.text().strip():
            self.edit_exec_time.setText(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def _on_sa_type_changed(self) -> None:
        broadcast = self.combo_sa_type.currentData() == 3
        self.edit_sa.setEnabled(not broadcast)
        self.edit_sa.setPlaceholderText("广播地址固定 1 字节 AA，忽略此输入" if broadcast else "")

    # ======================================================================
    # 进度 / 状态显示（进度只按**已确认**包累加）
    # ======================================================================

    def _refresh_progress(self) -> None:
        total = self._total_bytes()
        pct = 100 if total and self._confirmed_bytes >= total else int(
            self._confirmed_bytes * 100 / max(1, total))
        self.progress.setValue(pct)
        n = self._num_blocks() or 1
        self.lbl_progress.setText(
            f"{self._confirmed_bytes:,}/{total:,} B  {pct}%  "
            f"第 {min(self._block_idx + 1, n)}/{n} 包")

    def _set_status(self) -> None:
        text = f"状态：{self._state}"
        if self._state in (STATE_STARTING, STATE_TRANSFERRING, STATE_FINISHING):
            text += f"｜{self._step_label()}｜重试 {self._attempt}/{self.spin_retries.value()}"
        text += f"｜已发送 {self._sent_frames} 帧"
        self.lbl_status.setText(text)

    @property
    def state(self) -> str:
        """当前状态机状态名（测试/排障用；界面文案见 `lbl_status`）。"""
        return self._state

    # ======================================================================
    # 日志 / 弹框（design §10：弹框与日志**并存**，有弹框先写日志）
    # ======================================================================

    def _log(self, text: str, color: str = "info") -> None:
        """写一行日志（本页唯一日志出口）。前缀约定：``[TX]``/``[RX]``/``[超时]``/
        ``[失败]``/``[信息]``。"""
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        palette = getattr(self, "_palette", LOG_PALETTES[False])
        fmt.setForeground(QColor(palette.get(color, palette["info"])))
        cursor.insertText(text + "\n", fmt)
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)

    def _fail_soft(self, message: str) -> None:
        """不改状态机、只外显的错误路径（文件/参数类）：**先写日志、再弹框**。"""
        self._log(f"[失败] {message}", "fail")
        QMessageBox.warning(self, "协议8 升级", message)

    def _finish_buttons(self) -> None:
        self.btn_start.setEnabled(self._worker() is not None)
        self.btn_abort.setEnabled(False)
        self._freeze_plan_inputs(False)

    # ======================================================================
    # 配置持久化（原子写 + 坏文件宽容）
    # ======================================================================

    def _schedule_save(self) -> None:
        self._save_timer.start(400)

    def _collect_settings(self) -> dict:
        return {
            "version": CONFIG_VERSION,
            "block_size": self.spin_block.value(),
            "timeout_ms": self.spin_timeout.value(),
            "retries": self.spin_retries.value(),
            "auto_exec": self.chk_auto_exec.isChecked(),
            "read_before": self.chk_read_before.isChecked(),
            "read_after": self.chk_read_after.isChecked(),
            "read_target": self._read_target_key(),
            "sa_type": int(self.combo_sa_type.currentData()),
            "sa_logic": int(self.combo_sa_logic.currentData()),
            "sa_len": int(self.combo_sa_len.currentData()),
            "sa_addr": self.edit_sa.text(),
            "ca": self.spin_ca.value(),
            "source": self.edit_source.text(),
            "target": self.edit_target.text(),
            "file_version": self.edit_version.text(),
            "attr": self.edit_attr.text(),
            "category": int(self.combo_category.currentData()),
            "size_override": int(self.spin_size.value()),
            "check_kind": int(self.combo_check.currentData()),
            "check_value": self.edit_check.text(),
            "check_endian": self.combo_endian.currentData(),
            "exec_mode": self.combo_exec_mode.currentData(),
            "exec_time": self.edit_exec_time.text(),
            "license_hex": self.edit_license.text(),
            "params_expanded": self.sec_params.is_expanded(),
        }

    def _save_persisted(self) -> bool:
        """原子写（临时文件 + ``os.replace``）；失败返回 False 且不抛异常。"""
        try:
            payload = json.dumps(self._collect_settings(), ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return False
        tmp = f"{self._config_path}.tmp"
        try:
            parent = os.path.dirname(self._config_path) or "."
            os.makedirs(parent, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, self._config_path)
            return True
        except OSError:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            return False

    def _load_persisted(self) -> None:
        """读回配置；缺失/坏文件一律宽容回落默认值（design §7，绝不抛）。"""
        raw = None
        try:
            with open(self._config_path, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            raw = None
        if not isinstance(raw, dict):
            raw = {}
        s = dict(DEFAULTS)
        s.update({k: v for k, v in raw.items() if k in DEFAULTS})

        def _set_combo(combo: QComboBox, value) -> None:
            idx = combo.findData(value)
            if idx >= 0:
                combo.blockSignals(True)
                combo.setCurrentIndex(idx)
                combo.blockSignals(False)

        for spin, key, default, lo, hi in (
            (self.spin_block, "block_size", DEFAULTS["block_size"], BLOCK_SIZE_MIN, BLOCK_SIZE_MAX),
            (self.spin_timeout, "timeout_ms", DEFAULTS["timeout_ms"], TIMEOUT_MIN, TIMEOUT_MAX),
            (self.spin_retries, "retries", DEFAULTS["retries"], RETRY_MIN, RETRY_MAX),
            (self.spin_ca, "ca", 0, 0, 255),
        ):
            spin.blockSignals(True)
            spin.setValue(_bounded_int(s[key], default, lo, hi))
            spin.blockSignals(False)
        self.spin_size.blockSignals(True)
        self.spin_size.setValue(_bounded_int(s["size_override"], 0, 0, self.spin_size.maximum()))
        self.spin_size.blockSignals(False)

        _set_combo(self.combo_sa_type, _bounded_int(s["sa_type"], 1, 0, 3))
        _set_combo(self.combo_sa_logic, _bounded_int(s["sa_logic"], 0, 0, 3))
        _set_combo(self.combo_sa_len, _bounded_int(s["sa_len"], 6, 1, 6))
        _set_combo(self.combo_category, _bounded_int(s["category"], 0, 0, 1))
        _set_combo(self.combo_check, _bounded_int(s["check_kind"], 0, 0, 2))
        _set_combo(self.combo_endian,
                   s["check_endian"] if s["check_endian"] in ("big", "little") else "big")
        _set_combo(self.combo_exec_mode,
                   s["exec_mode"] if s["exec_mode"] in ("now", "sched") else "now")

        for edit, key in ((self.edit_sa, "sa_addr"), (self.edit_source, "source"),
                          (self.edit_target, "target"), (self.edit_version, "file_version"),
                          (self.edit_attr, "attr"), (self.edit_check, "check_value"),
                          (self.edit_exec_time, "exec_time"), (self.edit_license, "license_hex")):
            edit.blockSignals(True)
            edit.setText(str(s[key] if s[key] is not None else ""))
            edit.blockSignals(False)

        self.chk_auto_exec.blockSignals(True)
        self.chk_auto_exec.setChecked(bool(s["auto_exec"]))
        self.chk_auto_exec.blockSignals(False)
        for chk, key in ((self.chk_read_before, "read_before"),
                         (self.chk_read_after, "read_after")):
            chk.blockSignals(True)
            chk.setChecked(bool(s[key]))
            chk.blockSignals(False)
        target = s["read_target"] if s["read_target"] in \
            [k for _l, k, _s in READ_TARGETS] else DEFAULT_READ_TARGET
        _set_combo(self.combo_read_target, target)
        # 折叠状态直接读原始 JSON（缺 key 时保持 UI 默认展开）
        expanded = raw.get("params_expanded", True)
        self.sec_params.set_expanded(bool(expanded) if isinstance(expanded, bool) else True)
        # 以上 setter 都在 blockSignals 里：载入过程不会反过来触发 `_schedule_save`
        # 把刚读到的配置再写一遍（白 IO）。

    # ======================================================================
    # 收尾
    # ======================================================================

    def cleanup(self) -> None:
        """停表、断开串口信号、落盘配置（幂等）。**不关闭串口**：端口归主窗口。"""
        for timer in (self._wait_timer, self._save_timer):
            try:
                timer.stop()
            except RuntimeError:
                pass
        worker = self._serial_worker
        if worker is not None:
            self._detach(worker)
        self._serial_worker = None
        self._rx_buf.clear()
        self._save_persisted()


__all__ = ["Dlt698UpgradeWidget", "_DropArea", "CONFIG_NAME", "MISSING_CRCMOD",
           "fmt_hex", "parse_hex_text", "parse_exec_time", "normalize_hex_address",
           "check_package_file"]
