"""
南网协议解析工具 - PySide6 GUI版
简洁界面，支持单帧解析和批量解析
"""

import os
import sys

# 在导入 PySide6 之前屏蔽 Qt DirectWrite 字体回退警告（无害噪音）
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts=false")
import base64
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QModelIndex,
    QObject,
    QPoint,
    QRect,
    QSize,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QGuiApplication,
    QIcon,
    QKeySequence,
    QShortcut,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import app_icons
import batch_source_view
import custom_di_store
import batch_core
from atomic_io import atomic_write_json
import proc_stats
import protocol_registry as protocol_registry
import thread_registry
from app_paths import app_data_dir, data_path, resource_path
from batch_parse_worker import (
    BatchParseWorker,
    apply_cross_frame_state,
    parse_one_frame,
    resolve_ed_wrapper,
)
from command_lookup import get_command_lookup
from diff_widget import DiffWidget
from dlt645_di_lookup import get_dlt645_di_lookup
from dlt645_meter_sim_widget import Dlt645VirtualMeterWidget
from enhanced_export import EnhancedBatchResultExporter
from gdw_afn_lookup import get_gdw_afn_lookup
from gui_utils import (
    ZoomableTableWidget,
    apply_chinese_context_menus,
    set_btn,
    set_btn_icon,
    setup_chinese_context_menu,
)
from llm_api_manager import LLMApiManagerDialog
from llm_preprocess_widget import LLMPreprocessWidget
from message_tool_widget import MessageToolWidget
from meter_sim_widget import VirtualMeterWidget
from monitor_widget import RealtimeMonitorWidget
from obis_lookup import get_obis_lookup
from parser_registry import get_parser, get_parser_class
from preset_buttons import PresetButtonWidget
from serial_worker import SerialWorker
from spectrum_widget import SpectrumWidget
from system_integration.clipboard_monitor import ClipboardMonitor
from system_integration.global_hotkey import GlobalHotkeyManager
from system_integration.parse_prompt_dialog import ParsePromptDialog
from system_integration.quick_parse_panel import QuickParsePanel
from system_integration.single_instance import SingleInstanceServer
from system_integration.sys_tray import SystemTrayManager
from system_integration.taskbar_buttons import BASE_BUTTON_ID as TASKBAR_BASE_ID
from system_integration.taskbar_buttons import TaskbarButtons
from test_plan_widget import TestPlanWidget
from theme_settings import ThemeManager, ThemeSettingsDialog

#: 支持「容错解析」（不校验帧完整性，按实收字节继续拆）的协议索引。
#: 目前只有 698.45（协议8）实现了 parse_to_table(..., verify=False)。
TOLERANT_PARSE_PROTOCOLS = {8}

APP_VERSION = "1.23.96"
BUILD_DATE = "2026-10-23"  # 编译日期，每次打包前更新

# 作者 GitHub 仓库地址 —— 「关于」对话框 Star 按钮的**唯一来源**。
# 改地址只改这一处（按钮文案/提示/跳转都读它，不要在别处再写死一份）。
AUTHOR_GITHUB_URL = "https://github.com/Liruitao1993/South_Network_Protocol_Analysis_Tool"


def _resolve_download_threads(update_settings: dict | None) -> int | None:
    """「更新设置 → 下载线程」的取值 → 下载器线程数。

    - 缺省 / 0 / 非法 ⇒ ``None`` = **自动**（按文件大小与 CPU 核数自适应，上限 32）；
    - 其余夹到 ``1..32``（上限来自 ``downloader.MAX_THREADS``，用户口径「最高 32 线程」）。
    """
    from downloader import MAX_THREADS

    try:
        value = int((update_settings or {}).get("download_threads", 0) or 0)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return max(1, min(MAX_THREADS, value))

# 窗口状态持久化（config.json 顶层 "window" 段）的表格清单：
# 只收「用户拖动列宽才有意义」的主表；弹窗/克隆表不做持久化（见任务 PRD 的
# Out of Scope）。恢复时按表名 + 当前列数匹配，列数不符即丢弃（协议切换会重建
# 查询页表格且列数不同）。
_WINDOW_STATE_TABLES = (
    "result_table_widget",
    "batch_summary_table",
    "batch_detail_table",
    "di_table",
    "obis_table",
    "dlt645_di_table",
    "cmd_table",
    "gdw_table",
    "eb_di_table",
    "oad_table",
)

CHANGELOG = [
    (
        "1.23.96",
        "2026-10-23",
        [
            "**多线程下载器四批次加固（1.23.95 上线后的评审整改）**：R1~R17 逐条落地，目标是一句话——**下载不会产出错文件、退出不会卡死、面板不再自相矛盾**",
            "**批次一 · 数据与退出安全（P0）**：① 分段请求收到 `HTTP 200`（服务端/代理忽略 Range）时**绝不再按段偏移写入**，判为「该源不可分段」⇒ 作废该段缓存并**自动回落单流**整份重下（此前会把整文件写进某一段的偏移，产出「大小对、内容错」的 exe）；② 主窗口退出（含托盘退出 / 自动更新重启）时**主动 cancel 并等待下载线程结束**，且取消时**保留**已下载分片（`on_cancel=\"keep\"`）——关一次程序不再白丢几百 MB；③ 同一时刻**只允许一个下载任务**：重复点「检查更新→下载」不再起第二个 worker 抢同一个 `.part`，而是把已有面板唤到前台",
            "**批次二 · 续传自证（P1）**：④ `progress.json` 的 `url` 参与校验，**url 变了整份进度作废**（换源后拿旧分片拼接＝必然坏文件）；⑤ 每段响应必须**自证** `Content-Range` 起始偏移 == 请求起点、总长 == 计划总长，不符即判该源不可分段（不静默错位写入）；⑥ 单流回落路径**也能续传**（`Range: bytes=off-` 追加写），不支持时在面板明示「该源不支持断点续传」，`resume=False` 时清理旧 `.part`；⑦ 磁盘满 / 写入失败等 `OSError` 一律翻成**中文可读提示**（含「磁盘空间不足：需要至少 X 可用空间」），不再把英文 `WinError 112` 抛给用户",
            "**批次三 · 交互可用性（P1）**：⑧ 面板点 X 关闭 = **转入后台继续下载**，并可从新菜单「配置 → 下载进度(&D)...」重新打开继续暂停/取消；⑨ 下载结束后**清空状态栏进度**（不再永久占住状态栏顶掉后续消息）；⑩ 面板按钮宽度走 `gui_utils.fit_btn_width` 且**字号变化时重算**（实测 14 号字下「后台运行」会被压回旧下限而裁字）；⑪ 进度快照的 `state` 驱动标题/状态列（暂停显示「⏸ 已暂停」、服务端不认 Range 重新开始时显示「↻ 重新开始」），不再靠百分比猜",
            "**批次四 · 一致性与清理（P2）**：⑫ `DEFAULT_MAX_THREADS`（16）真正成为「自动」的默认上限（此前用 `MAX_THREADS` 兜底，常量是死代码）；⑬ 停用/删除无人使用的 `http_probe` 死参数；⑭ 删掉 `_UpdateDownloadWorker.progress` 死信号（没人连接，留着会误导接线）；⑮ 取消**默认保留**已下载进度，另给「清理缓存」入口（两者行为可测地不同）；⑯ 取消后立即返回（不再顺序等所有分段 future）、去掉取消分支的空语句；⑰ 分段重试识别 `429` / `Retry-After`（有该头按其秒数退避，夹上限 10 s，无则沿用线性退避）",
            "**暂停等待改成真正的事件阻塞**：`DownloadControl.wait_resumed()`（`threading.Event`）取代 `sleep(0.1)` 轮询 —— 点「继续」立即生效，不再平均晚 50 ms，也不白唤醒 CPU",
            "测试：`test/test_downloader.py` **42 项**（新增 url 变更作废 / `Content-Range` 自证 / 单流续传与不支持时明示 / 磁盘提示中文 / 取消保留 vs 清理两条路径 / 取消及时返回 / `Retry-After` 夹上限 / 「自动」= 16 线程语义）+ `test/test_update_download_dialog.py` **26 项**（新增状态文案随 `state` / 大字号不裁字 / 关窗=后台 / 清理缓存可用性 / **真实宿主级**重入守卫、菜单重新打开、状态栏清理），**6 条变异反证**逐条实测变红后逐字节还原（段自证 / keep 保留 / 进度推进 / 共用句柄 / Retry-After 上限 / 面板模态）",
            "顺带修复两处既有测试自身的问题（与本次功能无关但会报假红）：`test/test_menu_wiring.py` 末尾打印 `✓` 在 GBK 控制台抛 `UnicodeEncodeError`（测试全绿却以 exit=1 结束）；`test/test_app_icon_path.py` 仍在 `.spec` 正文里 grep `app_icon.ico` 字面量，而 spec 早已改为 `datas=list(meta.DATAS)` ⇒ 改查 `pyinstaller_meta.DATAS`（真正的单一来源）",
            "配套：`APP_VERSION 1.23.95 → 1.23.96`、`BUILD_DATE 2026-10-23`、两个 `.iss` 同步；新增菜单项已登记 `test/test_menu_wiring.py` 的 EXPECTED",
        ],
    ),
    (
        "1.23.95",
        "2026-10-22",
        [
            "**自动升级改多线程分段下载（现场报「下载新版本太慢」）**：新增 `downloader.py`（纯逻辑无 Qt）—— 原自动升级走**单流** `urllib` 拉 100 MB 的 exe，慢到用户受不了；现改为 **HTTP Range 分段 + 线程池并发**：先探测总长并切成 N 段，每段一个 `Range: bytes=a-b` 请求并发拉取，**线程数上限 32**（用户口径「最高 32 线程」），跑满带宽。已实测 GitHub Release 资产直链支持 `Accept-Ranges: bytes`、Range 请求返回 `206 Partial Content` 且 `Content-Range` 正确（资产 URL 是 302 → S3，**跟随重定向**已处理）",
            "**断点续传**：已完成的分段记录在 `<exe>.progress.json` 边车文件里（记录每段 `(start, end)` 布局与已完成字节），**重跑只补没下完的段**；单段中途断掉也只重下那一段，不是整个文件重来。**段布局变了**（线程数变化/实现调整）或**资源变了**（etag/长度不同）⇒ 旧进度自动作废、从头下（否则拼出来的文件字节错位）",
            "**安全底线不变**：分段只写 `<exe>.part` 临时文件，**全部段完成并按段序合并、逐段核对长度后才改名为目标文件** ⇒ 中断/崩溃**绝不会**留下「看着像下载完了其实是半截」的 exe（自动升级会拿它覆盖正在运行的程序）。SHA-256 校验与 **PE 魔数兜底**（`MZ` + 最小体积，更新源给错时拦住）**一道都没动**",
            "**服务端不认 Range 就老实单流**：探测到服务端返回 200（而非 206）时**自动回落单流下载**，不因为「并发不了」就下载失败；拿不到总长时同样回落",
            "**「配置 → 更新设置」新增「下载线程」**（自动（推荐）/ 8 / 16 / 24 / 32）：默认「自动」= 按文件大小与 CPU 核数自适应（小文件自动收敛线程数，避免每段一个 HTTP 往返的开销）；存 `config.json` 的 `update.download_threads`（0 = 自动）",
            "**进度条按字节实时推进**：此前按「段完成」上报 ⇒ 大文件长时间「进度不动」；现每写满一个 64 KB 块即上报（节流 0.2 s），单调递增",
            "**修掉一个真实并发缺陷**（实测发现，非理论推演）：多线程**共用一个文件句柄**写不同区间时，`seek()` + `write()` 不是原子操作，线程之间会互相踩掉文件偏移 ⇒ **下载出来的文件字节错位**（实测错位点正好在 64 KB = READ_BLOCK 边界，且「第一次下载就与源文件不一致」）。修法：**每线程一个独立文件句柄**，各自 seek 到自己那一段（OS 按各自 fd 的文件偏移写，互不干扰）",
            "**下载界面重做（现场口径：面板挡操作、看不到线程和速率）**：新增 `update_download_dialog.py` —— ① **非模态**（`NonModal`）：下载期间**主程序照常可用**（原先是 `WindowModal` 的 `QProgressDialog`，弹出来整个程序不能动），还可以「后台运行」收起面板、进度留在状态栏；② **看得见线程**：顶部显示「N 线程并发 · 进行中 x / y」，表格**逐行显示每个分段的实时进度**（区间 / 进度条 / 已下载 / 状态）；③ **看得见速率**：当前 MB/s + 已下载/总量 + **剩余时间估算**；④ **暂停 / 继续**：暂停后各线程在 64 KB 块边界停下、已完成字节保留，点「继续」**从断点接着下**（复用续传机制，不重头再来）；⑤ **取消并清理**：立即停止并**删除 `.part` 与进度文件**，不留垃圾",
            "测试：新增 `test/test_downloader.py` **31 项**（分段规划与均分守恒 / 线程数上限 32 与小文件收敛 / **本地 HTTP 服务端端到端**：并发下载字节与源**逐字节一致**、不支持 Range 时回落单流、续传只补缺失段、进度单调递增且有中间态 / **暂停端到端**：暂停后线程能退出、`.part` 保留、继续后字节完全一致 / **取消端到端**：抛 `DownloadCancelled`、`.part` 与进度文件都被清理（分段与单流回落两条路径都测）/ **失败路径**：目标文件**不出现**、合并数据缺口必须失败 / 与 auto_updater 衔接与 PE 兜底仍在 / GUI 线程数配置贯通）+ `test/test_update_download_dialog.py` **14 项**（**非模态守卫** / 线程数与速率与逐线程表格 / 暂停按钮切换与信号 / 取消终态提示「已清理」/ 后台运行收起但不结束 / 完成态 / 主程序接线守卫**含「不得残留 QProgressDialog 实例化」**/ worker 支持 pause·resume·cancel），均已登记 `release_check.py:CORE_TESTS`",
            "配套：`APP_VERSION 1.23.94 → 1.23.95`、两个 `.iss` 同步；spec `hiddenimports` 增补 `downloader` / `update_download_dialog`",
        ],
    ),
    (
        "1.23.94",
        "2026-10-22",
        [
            "**新增「提交问题到 GitHub」：把问题自动提交到仓库的 Issue（需求：软件直接提问题到 GitHub 的 ISSUE）**：帮助菜单新增「提交问题到 GitHub(&G)」。新增 `github_issue.py`（纯逻辑无 Qt）+ `github_issue_dialog.py`（PySide6 对话框）。**两条通道**：① **API 直连**（首选，真正的自动）—— 填好 GitHub 令牌后点一次「直接提交到 GitHub」，走 REST API `POST /repos/{owner}/{repo}/issues` 建单，**issue 立刻出现在仓库里**并弹窗给出编号与链接，全程不碰浏览器；② **浏览器预填**（兜底，无需任何令牌）—— 按仓库现有 Issue Form 的**字段 id** 预填 `issues/new?template=bug.yml&...`，用户在网页上点一次提交即可",
            "**表单对齐仓库现有模板**：仓库已有 `.github/ISSUE_TEMPLATE/bug.yml` 与 `feature.yml`，对话框按「问题反馈（Bug）/ 功能建议（Feature）」两种形态分别对应这两张表单；`github_issue.FORM_PROTOCOL_OPTIONS` 抄的是 bug.yml 里 protocol 下拉的**逐字**选项文本（GitHub 下拉预填要求与选项完全一致才会选中），`test/test_github_issue.py` 直接拿仓库里的真实 yml 对拍，**模板改了这边没跟上会直接变红**。因 API 建单不经过 YAML 表单，正文段标题刻意写成与表单一致的 `### 工具版本` / `### 期望结果` 等，issue 页面看起来与网页表单提交的没差别",
            "**自动收集现场信息**：自动带入**当前协议**、**最近一次解析的报文 hex**、运行环境（版本 / 系统 / 是否 exe / Python）—— 带 hex 的 issue 最快定位；**运行环境不含**用户名、机器名等可识别个人的信息（与 `diagnostics` 脱敏口径一致）",
            "**崩溃一键提交**：程序崩溃的提示框新增「提交到 GitHub」按钮，点了就把**完整 traceback** 填进对话框直接发成 issue（崩溃时 MainWindow 可能还没建好，故走模块级 `_report_crash_to_github`，与菜单入口共用同一份仓库地址与令牌，不会出现「一个能提交一个不能」的分裂）；提交前会**抹掉崩溃日志里的本机路径行**（`可执行文件：C:\\Users\\<用户名>\\...`），避免把 Windows 用户名发到公开仓库",
            "**令牌不写进 exe**：只从「本对话框输入 → 存本机 config.json 的 `github_issue.token` 段」或「环境变量 `GITHUB_TOKEN` / `GH_TOKEN`」读取，优先级为 显式 > 环境变量 > config.json。别人拿到你的 exe 也拿不到你的令牌（也就不能替你在仓库里刷 issue）；令牌落 config.json 后会被 `diagnostics.redact` 自动脱敏（键名含 token），诊断包不会泄露",
            "**地址单一来源**：owner/repo 由 `github_issue.resolve_owner_repo(AUTHOR_GITHUB_URL)` 从「关于」按钮那个常量解析而来，与自动升级源同源，**改地址只改那一处**；「仓库地址不对」不会再出现两份地址打架",
            "**健壮性**：HTTP 401/403/404/422/429/5xx 一律翻译成中文人话（不暴露英文 urllib 栈）；**标签不存在导致 422 时自动去掉 labels 重试一次**（标签可有可无，issue 必须建出来）；浏览器兜底链接超长（>6000 字符）时明确提示改用 API 通道而不是被静默截断",
            "测试：新增 `test/test_github_issue.py` **32 项**（与仓库 yml 模板逐字对拍 ×3 / 标题正文拼装 ×4 / API 建单成功与 6 种错误码翻译 / 标签 422 自动去标签重试 / 预填 URL 编码与未知字段过滤 / 令牌优先级与 config 读写 / 令牌被诊断包脱敏 / 崩溃摘要路径脱敏 / offscreen 对话框冒烟与浏览器兜底 / 主程序接线守卫），已登记 `release_check.py:CORE_TESTS`",
            "配套：`APP_VERSION 1.23.93 → 1.23.94`、`BUILD_DATE 2026-10-22`、两个 `.iss` 同步；spec `hiddenimports` 增补 `github_issue` / `github_issue_dialog`；仓库 `bug.yml` 增补 `contact`（联系方式）字段，使浏览器兜底通道也能带上联系方式",
        ],
    ),
    (
        "1.23.93",
        "2026-10-21",
        [
            "**协议9：OFDMA（多站点）帧解析修复（现场报「解析不了 eFC」）**：帧 `D9 01 F0 FF DF 03 00 00 8E …` 实际是 **UL-OFDMA 的 SACK 帧（类型3）**，三处叠加导致无输出 —— ① `_detect_channel` 用「预测帧长==实际帧长」投票，OFDMA 的 FC 布局与单站点不同，ISAC 公式算出 968 字节、HRF 默认 16 字节 PB 恰好蒙中 32 字节 ⇒ 整帧被按 HRF（表45）解；现改为 **多站点标识 `var[3]&1` 为 1 时直接判 plc**。② `_parse_mpdu_sof_isac` 的 `if multi_site:` 只有 `pass`，ISAC 版 OFDMA 可变域从未解析；现抽出共享 `_parse_ofdma_variable`（表26，BPLC/ISAC 同构）供两分支调用（且只调用一处，避免行重复）。③ eFC 判定：文档只规定 **类型 1（DL-OFDMA 的 SACK / UL-OFDMA）不携带 eFC**，类型 0/2/3 各有 eFC 定义（表27/28/29）；**类型 3 的 eFC 必须按表29 解析**（每站点 3 字节：TEI + 接收状态 + 保留）。修复过程中一度误把类型 3 也排除，已纠正；并新增「eFC携带判定」行把四种类型依据写明。修复后该帧正确给出：多站点帧=1、OFDMA类型=3（UL-OFDMA SACK）、站点数=4、**携带 eFC**（站点0~3 TEI=2/3/4/5、接收状态 PB0:OK PB1:FAIL、CRC-24 通过）、通道=plc",
            "**「启动传输」兼容多设备 + 校验值改为 2 字节 CRC-16**（现场两帧实报）：① 现场设备用的是 **方法14**（`OMD=F0010E00`「启动传输（带块大小/版本/下载方标识）」），参数比方法7 多「软件版本数组 / 下载方标识数组 / 2 字节标识」三项，新增 `build_start_transfer_v14` 并**逐字节复现现场两帧**；② 这两帧只差 1 个类型标签（第 6 项 `09` octet-string vs `0A` visible-string），对应两类只认其一的新旧设备；③ 页面新增「启动格式」下拉：选 `自动兼容` 即按 方法14(octet) → 方法14(visible) → 方法7 逐个试，**哪条回 DAR=0 就用哪种继续下发文件块**，某格式重试用尽不算失败、换下一种，三种都不回才判失败（默认仍 `方法7`，老设备与既有轨迹零变化）；④ **校验值宽度错误修复**：此前 `kind=crc` 用 `zlib.crc32` 出 4 字节，设备要 **2 字节** —— 现场包 `DPU_APP_V1.0.3.4.bin`(469,200B) 的实帧校验是 `09 02 73 73`，经 CRC-16/**X-25** 计算恰好 `0x7373`（ARC/CCITT-FALSE/XMODEM/KERMIT/DNP/AUG 全部对不上，非随意选型），现 `calc_checksum_value('crc')` 出 2 字节，「按文件计算」对现场包直接给 `7373`；⑤ 判定用当前格式的 OMD（`_start_omd`），写死 07 会把方法14 的确认当杂帧忽略",
            "**修复「光伏升级」页读版本信息退化成原始 hex**（现场报障：升级前读版本只显示 `数据 = 0206...`）：设备把「厂商扩展信息」回成 A-XDR `null`（`00`）时，`version_like_members` 因「要求 6 个成员全部是 visible-string」把整条结构判成「非版本形状」，界面于是只给一行原始内容。现在判据放宽为「6 个成员，每个是 visible-string **或 null**」，NULL 成员显示 `NULL` 并追加一行「⚠ 字段缺失」点名（表191 声明为定长 visible-string，缺失要说清依据）；定长字段的 NUL 补齐（`CNC\\0`）在显示前剥掉、`原始` 列仍保留字节可追溯。回归：`test/test_dl698_upgrade.py` A12 ③b/③c（286 → 293 项）",
            "**协议8 新增「协议测试」页（按 OAD 分类的预置测试库，仅协议8 可见）**：与「协议组帧」页的分工 —— 组帧页临时/任意填，本页是**预先做好**的测试项，按协议的对象标识（OI）把 **777 个对象**分成「电能量 / 需量 / 变量 / 事件 / 参变量 / 冻结数据 / 采集 / 文件与应用 / 控制 / 厂家扩展」十类（子类按 OI 高字节 0H/1H… 排序，与协议分配表一致），勾选即下发，用于设备一致性/功能测试",
            "**叶子名写「这个 OAD 是什么」**：叶子括号里不再是类级属性名（`分相数值数组`），而是具体语义 —— `20000200（电压）`、`20000201（A相电压）`、`20000301（A相电压换算及单位）`、`43000300（版本信息）`、`43000200（设备描述符）`。规则：通用属性名补对象名（`逻辑名`→`电压逻辑名`）、**具体属性名原样保留**（早先把后缀无差别套用，`43000200` 被叫成「电气设备」）、兄弟数组加限定词（`（扩展精度）/（尾数）/（带品质）`）区分；**分相类（class 3）按 A/B/C 展开**为索引 01H/02H/03H 三条（§7.3.5「01H=第一个元素」+ 仓库内 `_decode_phase_array` 的 A/B/C 口径），选中时「元素索引」同步跟上；功率类（class 4）证据不足不拆。叶子总数 4526 → **4658 条**",
            "**分类树带简要信息，且叶子是「每个属性一条具体 OAD」**（共 **4658 条**，与现场同类工具同形）：顶层 `4H: 参变量`（OI 高字节高 4 位）、子层 `3H: 设备管理`（低 4 位）、叶子 `43000300_（版本信息）_(索引=0)_(优先级及序号=00)` —— 点 `43000300` 直接发读版本信息的帧，不必再挑属性；「设置方法」页的叶子是具体 OMD（`00100100_（复位）_(优先级及序号=00)`）。叶子里的 `优先级及序号` 表示「点这条会用什么 PIID 发」，**PIID/优先级一变全树同步改文案**（4500 余条 setText 约 30ms），不让标签对用户撒谎",
            "**四类功能分页**：读取属性（GET-Request Normal）｜设置属性（SET-Request Normal）｜读取记录（GET-Request Record，支持 RSD 不选择/方法1/方法2/方法9/方法10 + RCSD 列选择）｜设置方法（ACTION-Request Normal）。每页「筛选框 + 分类树 + 当前项参数 + 实时帧预览」；筛选支持名称/OI 十六进制前缀/接口类名",
            "**获取设备地址**：顶部「读地址」发 GET `40010200`（通信地址），响应里的 octet-string 直接回填「读地址 / 服务器地址」（「写地址」为空时也回填，**不覆盖**用户已填值）；「写地址」「读时间」「写时间」「建立应用连接」同理，后续每个 OAD 都用这份地址组帧",
            "**发送控制**：勾选项逐条下发；「Lst发送」把多个 OAD 合成**一帧** GET-Request Normal-List（`05 02`）；「循环发送」发完自动重来；超时按「等待响应/超时重发」重发，重发用尽记超时；「终止」立停；「清空」清日志与两张表。底部「信息表（时间/结果/信息）」+「报文表（时间/方向/长度/报文）」，右栏逐条日志（TX/RX + 字段行）",
            "**「编辑」= OAD/OMD 覆盖**：把当前项取值填进覆盖框就地改一两个字节再发（预置库覆盖不到厂家自定义对象）；留空仍按属性/索引生成，非法长度在预览与发送处都报 ⚠ 而不是静默退回",
            "**组帧口径全部逐字节对齐协议文档附录 H**（新增 `dlt698_test_core.py` 纯逻辑层 + `dlt698_test_widget.py` 页面）：H.3.1 读属性 `05 01 01 40 01 02 00 00`、H.3.2 读多属性 `05 02 02 02 20 00 02 00 20 01 02 00 00`、H.3.3 读记录（含 RSD/RCSD）、H.4.1 设置 `06 01 02 40 00 02 00 1C 07 E0 01 14 10 1B 0B 00`、H.5.1 操作 `07 01 05 00 10 01 00 0F 00 00`、H.2 建立连接 `02 00 …`（40 字节）；帧的 HCS/FCS 仍只由 `DLT69845FrameGenerator` 算（新增 `generate_apdu_frame` / `generate_connect_request`，既有调用零行为变化）",
            "**不冒充判定**：CONNECT-Response 与记录型二维数据体未做字段级解析（文档无自证布局）⇒ 结果给「已收到/未做字段级解析」而非「成功」；DAR 文案取自解析器 `_enrich_dar`（单一来源），失败时带 DAR 值与中文说明",
            "复用主窗口共享串口（`raw_data_received` + `write_raw`，不自建端口、不用 `send_frame`、不订阅 `frame_received`）；RX 按 `frame_deframe` 的 `L+2` 判据自组帧并按 68H/FEH 重同步丢噪声；参数落盘 `dlt698_testbench.json`，「远程升级」按钮跳「光伏升级」页",
            "**收发日志输出完整字段表**（用户口径「解析器已经很完备，要详细输出」）：勾「详细解析」（默认勾、落盘）后 **TX 与 RX 都**逐字段打印整帧结构 —— 起始字符/长度域/控制域各位/地址域/SA/CA/HCS/APDU 类型/PIID/OAD 语义/数据 A-XDR/FCS/结束符，数据源就是 `DLT69845Parser.parse_to_table`（**单帧解析页那张表**，不在页面里另写字段拆解）；四列按显示宽度对齐（CJK 算 2 列），长 hex 与结构化值压缩成「前 32 字符 …（共 N 字符）」，不让一行撑到屏幕外；未请求的帧（主动上报）也走同一套明细。双击底部「报文」表任意行 → 送「单帧解析」页看完整解析树",
            "测试：新增 `test/test_dlt698_testbench.py` **279 项**（6 条附录 H 黄金逐字节 + HCS/FCS 自解析 + L+2 自洽、OAD/OMD/PIID、date_time_s、SA、RSD/RCSD、分类库 777 项与记录型筛选、树三层文案与 4526 条 OAD 叶子、逐字段明细与长 hex 压缩、响应判定含 DAR/列表/记录/CONNECT 不冒充/坏帧、地址与时间提取、筛选、offscreen 页面构建与发送队列/超时重发/终止、读地址回填、OAD 覆盖、PIID 联动、详细解析开关与双击送解析、落盘与 cleanup、RX 半帧与噪声重同步、主题、源码护栏）+ `test/test_dlt698_test_tab_wiring.py` **22 项**（注册表 `has_test` 只属协议8、页签标题与位置、协议显隐、懒加载、串口注入、远程升级跳转、主题、收尾不关串口）；`test/test_yw645_gui.py` 页签矩阵补入本页",
            "配套：`APP_VERSION 1.23.92 → 1.23.93`、`protocol_registry` 新增 `has_test` 能力位（仅索引8 为真）+ `protocols_with_test()`",
        ],
    ),
    (
        "1.23.92",
        "2026-10-21",
        [
            "**单帧解析新增「校验该帧」勾选项（默认勾选）**：勾选 = 原有严格行为（帧结构/长度自洽/HCS/FCS 完整才解析，不完整直接报「❌ 解析失败」）；取消 = **容错解析**，不因半截帧整帧放弃，按实收字节一拆到底。目前仅 **698.45（协议8）** 支持，切到其它协议时该勾选框置灰并提示；勾选状态存 `config.json` 的 `single_parse.verify`，重开保持",
            "**698.45 容错解析（`parse_to_table(..., verify=False)`）**：长度域只作参考（明确提示「L=532，整帧应 534 字节，实收 256 字节」）；起始符/HCS/FCS/结束符**只记录不阻断**（校验不过标注「失败（容错模式：继续解析）」，结束符缺失标注「未找到 0x16」）；末尾按实收字节切 APDU（末尾是 0x16 才切 FCS+结束符，否则把尾部全部当用户数据）；结构化拆不动时输出「未解析字节」，表格末尾**永远给一行「原始报文」**（含总字节数）",
            "**APDU 解析失败不丢数据**：APDU 内部解析异常时输出「APDU解析错误」+「APDU原始字节」，不会因为 APDU 拆不开而整帧作废",
            "测试：新增 `test/test_dl698_tolerant_parse.py` **7 项**（严格模式仍报错 / 容错模式头部到末尾 / **全部 257 个截断前缀零异常** / 合法帧无告警且 HCS·FCS 通过 / 缺结束符 / 坏 FCS 继续 / 空与超短输入）+ `test/test_tolerant_parse_gui.py` **12 项**（勾选框存在与默认勾选 / 勾选时半截帧报失败 / 取消后出现头部与原始报文且不弹框 / 写盘 / 非协议8 置灰 / 切回保留状态）；均已登记 `release_check.py`",
            "配套：`APP_VERSION 1.23.91 → 1.23.92`、`BUILD_DATE 2026-10-21`、两个 `.iss` 同步；`parse` / `parse_to_table` 新增 `verify` 关键字参数（默认 `True`，对既有调用零行为变化）",
        ],
    ),
    (
        "1.23.91",
        "2026-10-20",
        [
            "**主界面新增「外观」按钮（太阳 / 月亮 / 显示器）**：菜单位置右上角、顶栏折叠按钮左侧，点击循环 `浅色 → 深色 → 跟随系统`；图标随**实际效果**变化（深色=月亮、浅色=太阳、跟随系统=显示器），提示写清三态与当前值。选择持久化到 `config.json` 的 `ui.appearance`，重开保持",
            "**主题与外观解耦，7 套主题都能深色**：新增 `resolve_appearance()`（主题 + 模式 + 系统深浅 → 实际主题与是否深色）。**经典（Fusion）/ Windows 原生 / Vista** 这类调色板型主题在深色下保留自身风格、改用深色 QPalette（`#202225` 底 + 浅色文字）并叠加暗色 QSS，切回浅色恢复出厂调色板；默认 / 毛玻璃 / 云母没有独立暗色版，深色时用「Fusion 暗色」渲染（主题对话框已写明这条规则）",
            "**跟随系统**：`QStyleHints.colorSchemeChanged` 实时跟随系统深浅（仅「跟随系统」模式生效；浅色/深色模式不受系统影响）；老 Qt 无该信号时安全降级",
            "**修复两处体验问题**：① 选中「Fusion 暗色」主题但模式是浅色时，点按钮原来「没反应」——现在自动回默认浅色主题；② 切页重绘的毛玻璃判断改用**实际生效主题**，避免深色模式下仍按 glass 走重绘分支",
            "测试：`test/test_appearance_mode.py` **10 项**（模式常量、7 主题 × 3 模式 × 系统深浅矩阵、旧配置回落、`ui.appearance` 落盘、深色调色板对比度）+ `test/test_appearance_gui.py` **16 项**（按钮存在/图标非空/三态循环/图标随状态变化/经典主题深色真变深且可恢复/跟随系统/持久化/暗色主题点击回浅色）；已登记 `release_check.py`",
            "配套：`APP_VERSION 1.23.90 → 1.23.91`；主题对话框新增外观说明；`ThemeManager.apply` 增加 `mode` / `system_dark` 参数（默认值向后兼容）",
        ],
    ),
    (
        "1.23.90",
        "2026-10-20",
        [
            "**性能（实测）**：`拓扑信息` 首开 **1586 ms → 13 ms**，全部 20 页走一遍的内存 **156 MB → 125 MB**。做法：`TopologyGraph` 改成 `@property` 按需创建，页面先出壳，`networkx`（导入约 1 s）延迟到第一次「加载/清除/导出拓扑」时才导入；`topology_widget` 不再顶层 `from topology_graph import TopologyGraph`",
            "**稳定性（崩溃兜底）**：新增 `crash_handler.py` —— 安装 `sys.excepthook` + `threading.excepthook`，把异常类型/消息/完整 traceback/版本/系统/线程名写进 `<数据目录>/logs/crash_*.log`（微秒级文件名，保留最近 20 份）；写日志自身失败、回调失败都被吞掉，主线程崩溃才弹提示，子线程崩溃只落盘不碰界面。诊断包已自动收集 `logs/crash_*.log`",
            "**性能（高吞吐日志）**：`生产测试架` 接收日志从「每行一次 `insertText`」改为**入队 + 100 ms 合并刷新**（相邻同色行合并成一次写入、自动滚动每次刷一次），超过 300 行立即刷；清空/退出时先刷队列，不丢尾包",
            "**全项目状态写入原子化**：除 `config.json` 6 处外，又把 `custom_di.json`（自定义 DI）、`dlt645_custom_di`、PLC RF 命令字、OBIS 自定义、预设命令、档案数据、LLM profiles/预处理配置、645 地址历史、虚拟表档案导出的写入全部换成 `atomic_write_json`（共 11 个模块），并加静态守卫测试禁止回退成 `open(w)+json.dump`",
            "**新增短时长稳测试** `test/test_soak_stability.py`（GUI_TESTS）：反复切页 600 次（20 个页面）RSS 158→185→189→189 MB（**最后 200 次 0 增长**，证明无泄漏）+ 高频灌 5000 帧（0.1 s，日志块达上限、队列清空），断言内存收敛与上限",
            "**解析健壮性（实测抓到并修复的真实缺陷）**：`gdw10376_parser` 在「长度域大于实收字节」的截断帧上会 `IndexError`（模糊测试 1200 次命中 277 次）。修复：把 `cs_pos` 夹回帧内（`min(4, frame_len-2)` 兜底）+ 取 AFN 前再判 `offset < frame_len`；修复后全协议随机/截断输入 **0 异常**",
            "新增 `test/test_crash_handler.py` **6 项**（格式化/落盘/清理旧文件/坏目录不抛/钩子落盘+回调/回调异常吞掉/幂等）、`test/test_frame_corpus.py` **3 项**（真实帧语料库 `test/frames/<key>/*.hex`：目录名必须是注册表 key、每帧解析非空、两次解析一致）、`test/test_parser_fuzz.py` **4 项**（固定 seed 随机/带头随机/语料全前缀截断/空与超短输入，12 个解析器共约 3000 例，断言不抛异常且总耗时 < 25 s；内含国网截断帧回归）；均已登记 `release_check.py` CORE_TESTS",
            "配套：`APP_VERSION` `1.23.89 → 1.23.90`；spec `hiddenimports` 增补 `crash_handler`；`docs/产品级优化评估-2026-10-20.md` 的 P1 性能/稳定性/协议准确性条目标记完成",
        ],
    ),
    (
        "1.23.89",
        "2026-10-20",
        [
            "**P0 加固（配置不再可能写坏）**：新增 `atomic_io.py`（纯标准库）——同目录临时文件 + flush/fsync + `os.replace` 原子替换，失败时旧文件保持原样、临时文件自动清理；Windows 文件被占用时带 4 次退避重试。`main_gui` 里 6 处 `open(config.json,'w') + json.dump`（更新设置 / 系统设置 / 预处理命令 / Python 脚本 / 窗口状态 / 通用保存）全部换成 `atomic_write_json`，写到一半崩溃/断电/强杀不再产生半截 JSON",
            "**P0 加固（自动升级失败可回滚）**：`auto_updater.UPDATE_BAT_TEMPLATE` 重写 —— 等旧进程退出 → **先把旧 exe 备份成 `.bak`** → 覆盖 → **比对新旧文件大小**（不等长即视为复制不完整）→ 启动新版 → **15 秒健康检查**（进程不在就回滚）→ 回滚时删可疑文件（重试 10 次，文件可能仍被占用）→ 还原 `.bak` 并重启旧版。备份移动失败（文件被占用）时**直接放弃升级，一个字节都不动**；成功升级后保留一份 `.bak` 作为人工回退点",
            "**P0 新增「生成诊断包」（帮助菜单）**：`diagnostics.py`（纯逻辑、无 Qt）把 环境信息（版本/编译日期/Python/PySide6/系统/是否打包）+ 各配置文件 + 最近 5 个日志尾部 打成一个 zip。配置里的 `api_key` / `token` / `password` / `secret` / `cookie` 等字段递归替换为「***已脱敏***」；单个日志最多 200 KB、总包上限 5 MB、缺文件只跳过不失败。用户反馈问题时只需发这一个 zip",
            "**修复启动日志里的图标告警**：`gui_utils._STANDARD_ICON_MAP` 缺 `search` / `settings` 两个键，导致归档页「初始化/查询」与拓扑页「查询/搜索」按钮**静默没有图标**（日志里只有一行告警）。已补映射（`SP_FileDialogContentsView` / `SP_FileDialogDetailedView`）",
            "测试：新增 `test/test_p0_hardening.py` **13 项** —— 原子写（创建/覆盖/失败保留旧文件且无残留/Unicode 往返/坏 JSON 回落）、升级脚本静态断言（备份/大小校验/15 秒健康检查/回滚还原/删除重试/占位符清零）、诊断包（脱敏保留非敏感字段/日志截断/总大小上限/缺文件跳过/嵌套结构脱敏）、主程序静态守卫（`atomic_write_json` 已接线、旧写法清零、诊断包入口存在、`diagnostics` 不依赖 Qt）；已登记 `release_check.py` CORE_TESTS",
            "配套：`APP_VERSION` `1.23.88 → 1.23.89`、`BUILD_DATE` 2026-10-20、两个 `.iss` 同步；`docs/产品级优化评估-2026-10-20.md` 的 P0-1/2/4 标记为已完成（P0-3 代码签名需证书，短期仍以 SHA-256 公示为主）",
        ],
    ),
    (
        "1.23.88",
        "2026-10-19",
        [
            "**新增「生产测试架」标签页**（常驻可见、与协议无关、懒加载；图标 flask-conical）：**三栏布局** —— 左「发送配置」（5 条发送框）、中「接收日志」、右「测试架参数」。串口只借用顶部「串口配置」的共享连接（`set_serial_worker`，本页不开/关端口），未连接时所有发送按钮禁用并给出提示",
            "**左右两栏可折叠、三栏宽度可拖**（用户反馈：参数面板与日志挤在一栏会吃掉日志空间）：两栏标题行的**外沿**各一个折叠按钮（左栏在左、右栏在右），折叠后只留 30 px 窄条（按钮 + 竖排栏名），**宽度全部让给中间日志**；再点一次展开并**还原折叠前的三栏宽度**；三栏之间的分隔条可直接拖动；折叠状态与三栏宽度一起落盘，重开程序保持",
            "**5 条发送配置框**：每条独立选 HEX / ASCII、独立勾选 **checksum8** 并选落位方式（`追加到末尾` / `覆盖末字节` / `插在 16H 前`），一键发送；名称与内容落盘，重开程序直接恢复；HEX 写错（奇数位 / 非法字符）**拒发并写明原因**，绝不静默改按文本发",
            "**接收日志**：HEX / ASCII 显示切换（ASCII 把不可打印字节显示为 `.`）、**时间戳开关**（`YYYY-MM-DD HH:MM:SS.mmm`，默认开）、自动滚动、清空、收发字节计数；单行超过 512 字节只显示头尾并标注总长（一条 4KB 回包不刷屏）",
            "**「发送参数帧」可选 HEX / ASCII 形态**：右栏底部与左侧发送框同一套语义 —— `HEX` 发 75 字节二进制帧（现场测试架默认）、`ASCII` 把报文按大写 HEX 文本字符发送（150 个字符，给接文本协议的工装）；选择会落盘，ASCII 形态在日志里额外记一行「按 ASCII 文本发送（150 字符）」，避免把 150 字符误当二进制帧",
            "**测试架参数帧**（现场样例 `68AAAAAAAAAAAA68143555AA55AA0100600E120818132F05FE…003916`，75 字节）：49 项参数（帧头 2 项测试开关 + 参数区 47 项 / 53 字节）+ 6 字节地址域（默认 `AA×6` 广播），**改动即时重算整帧并在预览行显示长度与 CS8**；参数按分组**单列排布**（右栏可拖窄也不出横向滚动条，标签不裁字）；`发送参数帧` / `复制报文` / `恢复现场示例` 三个动作；参数非法时只写日志与预览行、指出**具体字段名**，不弹框",
            "**逐字节复现现场样例**（`test/test_production_testbench.py` 断其相等）：帧结构 `68 + 地址6 + 68 + 14(控制域) + 35(参数区长度53) + 55AA55AA(命令标识) + 测试STA + 测试无线 + 参数区53 + 保留4×00 + CS8 + 16`，**CS8 = 首字节到保留位末字节的 8 位算术和**（不溢出），字段顺序/长度/校验范围任一改动即变红；反例断言：校验范围若不含 68H 帧头则对不上",
            "**参数表是唯一来源**：`production_testbench_core` 的 `FieldSpec` 字段表（`HEADER_FIELDS` 2 项 + `BODY_FIELDS` 47 项：key/标签/长度/默认值/下拉选项/提示）+ `FIELD_GROUPS` 同时驱动界面生成、组帧与落盘；参数区长度导入即断言 = 53 字节（防字段表被改坏）",
            "**纯逻辑 / Qt 分层**：`production_testbench_core.py` 无 Qt（组帧、checksum8、HEX/ASCII、时间戳、配置合并与原子写），`production_testbench_widget.py` 只做界面与信号接线；主窗口仅 5 处接线（import/占位 tab/懒加载/主题/退出清理），不改协议可见性逻辑",
            "**配置落盘** `production_testbench.json`（发送框 / 全部参数 / 地址域 / 显示偏好 / 三栏折叠状态与宽度）：脏值逐字段回落默认（非 HEX、长度不符、下拉越界都不采纳），`save` 走 `.tmp` + `os.replace` 原子写，坏 JSON 回落默认",
            "测试：`test/test_production_testbench.py` **120 项**（A 纯逻辑 55 项：golden/校验范围反例/三种 CS8 落位/文本编解码/字段偏移/非法输入/配置合并/布局配置/参数帧发送形态；B GUI 56 项：三栏布局/折叠展开还原/拖动宽度/窄条竖排标题/无横向滚动条/参数帧 HEX-ASCII 发送/5 框联动/CS8 三态/非法拒发/时间戳/恢复示例/落盘重开/主题/断开/cleanup 幂等；C main_gui 接线 9 项）；已登记 `release_check.py` GUI_TESTS",
            "配套：`APP_VERSION` `1.23.87 → 1.23.88`、spec `hiddenimports` 增补 `production_testbench_core` / `production_testbench_widget`（main_gui 内函数级惰性 import，静态分析扫不到）、README 功能表与本节、AGENTS §1/§3/§10",
        ],
    ),
    (
        "1.23.87",
        "2026-10-19",
        [
            "**修复协议9 测试帧「测试模式6（频段切换/载波切频）」被解析成无线信道号**（用户报障：`09 00 F0 FF … 81 61 20 00 …` 按协议9 解析，模式6 后面的字段显示成「Option值 / 无线信道号」，要求按**载波的值**解析）。依据 `南网新一代20260226校对/宽带双模通信模块（通感一体物联版）相关测试命令定义_260922.docx`「原有测试命令」第 6 条：**模式6 = 进行频段切换操作，配置值填「需要切换到的目标频段对应的值」**（值 0/1/2 → 通信频段 0/1/2 及 MHz 范围）；`Option值 + 信道号` 是**模式8（无线信道切换）**，两者语义不同",
            "**根因两处**（协议9 `csg_new_gen_cmd_payloads._parse_legacy_ext_cmd`）**：① 12bit 配置值按大端拼**（`(b2>>4)<<8 | b3`）——正确拼法是「**字节号小的端为低位**」（协议10 `gw_new_gen_cmd_payloads`、协议11 `hdc10_parser` 均如此），同一拼法还会把「30 分钟」的测试持续时间读成 3585；**② 模式6 与模式8 合并**按「Option+无线信道号」解析（一次错误改动引入「与模式8 一致」，协议10 同源一并改）",
            "**报文头长度同批修正**：该字段是 **6bit**（字节0 bit6-7 为**低**2位 + 字节1 bit0-3 为**高**4位，文档表61 跨两行），旧实现只取字节0 的 2bit ⇒ 用户帧 `81 61…` 显示「2」，正确值 **6 = 表61 整根 6 字节报文头**（与协议10/11 口径一致）",
            "**落地口径**：模式6 → 新增/改为「`频段值(目标频段)`」行（原始值 12bit 十六进制 + 解析值 0/1/2 + 通信频段名称与 MHz 范围，说明注明「表61 第6条」），**不再出现任何无线信道字段**；模式7（ToneMask）/模式8（无线信道 Option+信道号）语义保持不变；频段映射单源化在各 payload 模块的 `_BAND_MAP`（与 `csg_new_gen_frame_gen.BAND_MAP`、`hdc10_parser.EXT_BAND_RANGES` 同口径）",
            "测试：`test/test_csg_summary.py` 新增 `test_legacy_mode6_band_switch_is_carrier_semantics`（用户真实帧：模式6 → 频段值=2 / 通信频段2（0.781~2.930MHz）/ 报文头长度=6 / **模式6 无无线信道字段** + 模式8 仍为无线信道口径 的反例对拍）；`test/test_gw_ext_cmd.py` T3/T13/T14 的旧期望（「Option 2 / 信道 0」）改为频段值口径并加「模式6 不应出现无线信道字段」回归；相关联调全绿（`test_csg_summary`、`test_gw_ext_cmd` 48/48、`test_gw_monitor_summary` 18/18、`test_gw_app_summary_detail` 44/44、`test_hdc10_app_dispatch` 94/94、`test_web_gui_parity` 83/83、`test_csg_frame_reverse`、`test_csg_test_ext_0009`、`test_csg_batch_parse_level`、`test_gw_parse_levels`、`test_hdc10_bitfield_display` 47/47）",
            "**自动升级默认源改为作者 GitHub Release**（需求：默认查 GitHub 的 release 节点，并把更新说明加载出来，让自动升级功能完整）。`auto_updater.DEFAULT_UPDATE_CONFIG.source_type` 由 `gitee` 改为 **`github`**，配 `github_owner`/`github_repo`；仓库地址**仍是单一来源** —— 启动时用 `merge_update_config(..., repo_url=AUTHOR_GITHUB_URL)` 从「关于」的那个常量解析出 owner/repo（改地址只改一处，Star 按钮与更新源不会走偏），config.json 里显式填写的值优先、**清空输入框 = 回到默认**",
            "**GitHub 源直连接口**：最新版 `api.github.com/repos/{owner}/{repo}/releases/latest`、版本列表 `.../releases?per_page=30`（启动 3s + 每 30 分钟各查一次，未鉴权 60 次/小时的上限绰绰有余）。接口无需 token；**草稿版本一律略过**（作者还没打算放出去），预发布版本在列表里标 `[预发布]`",
            "**更新说明（Release body，markdown）加载并渲染**：手动「检查更新」的版本列表对话框改为**左列表 + 右更新说明**（`QTextBrowser.setMarkdown`，GitHub 的标题/列表/表格/链接都能看，链接可点）；「发现新版本」确认框也换成带滚动说明的对话框（顺带显示安装包名，并给「查看发布页」按钮打开 `html_url`），不再把原始 markdown 塞进 `QMessageBox` 纯文本；状态栏绿色⬆提示的 tooltip 用新 `summarize_notes()` 去掉 `#`/`**`/表格竖线等噪音。空说明给「（该版本未填写更新说明）」占位，**不静默留白**",
            "**校验与容错**：GitHub 资产的官方 `digest`（`sha256:…`）直接作为校验值 ⇒ 勾选「校验 SHA-256」时下载完真的能校验（此前 GitHub 源永远拿不到 sha256）；网络/接口失败一律翻译成中文人话（`describe_http_status`：404=「地址不存在或还没有 Release」、403/429=「频率限制」、5xx=「服务器错误」），不再把英文 urllib 栈抛给用户；下载阶段同样按状态码给原因",
            "**两个升级对话框拆到独立模块 `update_dialogs.py`**（主程序已 14000+ 行，且这两块可脱离 MainWindow 单独测试；已登记 spec `hiddenimports`）；「更新设置」对话框新增 GitHub owner/repo 输入框与当前更新源回显，GitHub / Gitee / 私有 HTTP 三源并存（老配置里的 `source_type: private` 行为不变）",
            "**修掉一条会毁掉客户端的升级缺陷（发布前独立验证发现）**：GitHub/Gitee 的 release 对象里，顶层 `url` 字段指向的是 **API 端点**（`api.github.com/repos/.../releases/<id>`），而旧逻辑在「资产没匹配到 exe」时会把顶层 `url` 当下载地址 —— 实测仓库里的旧版本 `1.8.2` 正是「有 Release 但没上传安装包资产」的形态，于是它会被列进版本列表，点下载拿到的是**接口返回的 JSON**，再被当成新 exe 覆盖正在运行的程序。两处收紧：① **发布对象（有 assets/tag_name/html_url）的下载地址只认资产直链**，顶层 `url`/`download_url` 仅在私有 version.json（非发布对象）里继续可用，且任何路径下命中 `api.github.com/repos/` 或 `gitee.com/api/v5/repos/` 一律拒绝；无安装包资产的版本**不进版本列表**（发布对象缺资产即报「没有可下载的安装包资产」）。② **替换 exe 前的最后一道闸**：新增 `is_pe_executable()`（`MZ` 魔数 + 最小体积），下载物不是 Windows 可执行程序就报错取消（哪怕 SHA-256 被跳过）—— 更新源写错、页面被劫持、拿到 HTML 错误页都不会把 exe 覆盖成垃圾。回归：`test_auto_updater.py::test_extract_release_never_uses_api_endpoint_as_download_url` / `test_extract_private_json_url_still_allowed` / `test_fetch_all_releases_skips_release_without_asset` / `test_is_pe_executable_guard`、`test_update_notes_gui.py::test_download_worker_rejects_non_pe`（JSON / HTML / 真 PE 三态）；真实接口复核：版本列表由 5 条（含异常 `1.8.2`）收敛为 4 条，每条均为资产直链",
            "**「校验 SHA-256」开关从此真的生效**：此前全仓库只有设置对话框读写 `sha256_verify`，实际是否校验只看「摘要有没拿到」，勾不勾一样（死开关）。现在下载线程按配置接：关掉即不带预期摘要、打开且摘要不匹配则拒绝并提示「SHA-256 校验失败，文件可能损坏」",
            "**「仓库地址唯一来源」在保存后依然成立**：原先打开一次「更新设置」点确定，就会把默认 owner/repo 显式写进 config.json，此后修改 `AUTHOR_GITHUB_URL` 不再生效。现改为**与默认值相同即存空串**（下次打开仍回显同一个默认值，用户无感），并加了「内置常量 vs AUTHOR_GITHUB_URL」一致性守卫测试把漂移风险钉成红灯",
            "**临时文件名清洗**：`_start_download` 的临时文件名按 `safe_file_stem()` 处理 tag（含 `/` 如 `release/1.24` 时原会把临时文件写成子目录、`:` 等 Windows 非法字符会让下载以 OSError 表现为「下载失败」）",
            "测试：新增 `test/test_update_notes_gui.py`（**54 项** offscreen：markdown 渲染与空说明占位、渲染异常退回纯文本、行文案 `[最新]/[预发布]/← 当前`、切行 → 说明联动、无资产禁用下载、双击=下载、拒绝/取消返回语义、`_UpdateCheckWorker` 带 repo_url、`_confirm_update_download` 真实方法体传参、接线源码守卫、下载线程 PE 三态、sha256 开关三态、仓库地址一致性、文件名清洗）+ `test/test_auto_updater.py` 扩至 **40 项**（默认源=github、`parse_github_repo_url` 各写法、repo_url 与用户配置优先级、空串回落、digest→sha256、源码压缩包不被当安装包、API 端点不被当下载地址、无资产版本剔除、PE 兜底、默认值收敛为可存空串、文件名清洗、版本列表降序/草稿剔除、私有源顶层 sha256 优先、错误文案）；两条测试均登记进 `release_check.py` 核心回归",
        ],
    ),
    (
        "1.23.86",
        "2026-10-18",
        [
            "**报文工具新增「地址替换」**（需求：报文工具里增加地址替换功能，输入原始报文后按协议类型替换地址并重新计算校验，覆盖 645 / 698 / 国网 1376.2 / 南网本地接口等，要做得比之前几处更通用）。粘贴**任意一帧**原始报文 + 选协议 → 只替换地址域并**按该协议重算校验**：地址位置 / 字节序 / 校验算法全部取自各协议自身实现，与蓝牙页、串口工具页是**同一引擎** `frame_addr_fix`（第 4 处复用，**没有第二份偏移或算法表**）",
            "**地址字段随协议动态生成**：南网 / 国网 = 源地址 + 目的地址，645 / 依瓦645 = 表地址，698.45 = SA + CA，南网上行 = 终端地址；**留空的字段保持原值**（只改其中一个也行）。输入框一改就在提示行实时回显「将写入 N 字节」与**替换后报文预览**，失败原因也只写在提示行、不弹框",
            "**支持协议 0 南网 / 6 DLT645-2007 / 7 国网 / 8 698.45 / 13 依瓦645 / 14 南网上行**；**先自证再改**（帧结构 + 原帧校验都要通过才替换，避免把别的协议的帧「洗」成看似合法的帧；地址在线长度必须与帧内一致）；645 / 698.45 的 `FE` 前导码剥离后**原样恢复**，其余协议带 `FE` 一律报错（不「救活」错帧）",
            "**失败不污染成功结果**：点「替换地址」失败时只把可读原因写进输出区 + 弹框，「替换后报文」结果行**保持原值**（避免误以为已经替换成功）；成功后可「复制结果」或「结果→输入」继续改另一个地址，输出区逐条给出「地址旧→新 / 校验旧→新」说明",
            "**光伏升级页：升级前 / 后版本信息自动比对判定**（现场口径：升级到底成没成，要有个明确结论）。「版本信息」展示区顶部新增**判定条**：升级前后读到的版本**有差异 ⇒ 判定升级成功（✅）**、**完全一致 ⇒ 判定升级失败（❌，设备没换新固件）**、缺升级前基线 / 有一侧没读到 / 前后读的不是同一项版本内容 ⇒ **无法判定（⚠）**、两侧都没读 ⇒ **尚未比对（⏳）**。判等**优先比原始字节**（展示用的「值」会补全日期、裁剪长值，拿它判等会把同一版本误判成变了），`⚠` 诊断行不参与；结论同时写进收尾状态行与日志，**判定不改状态机**（流程跑完 ≠ 固件升级成功），**任何展示都不得把「无法判定」说成成功或失败**",
            "**光伏升级页新增可选的「提升波特率」（仅串口通道，默认不勾、参数落盘、传输中冻结）**：开始升级前先发那条 31 字节的 FT1.2 现场实帧让**设备**切自己的 UART，静默「切换等待(ms)」（默认 300）之后**主机**才跟着切到 115200 —— 主机先切连命令都发不出去；命令**只发不等确认**（设备切速时主机还在旧速率，等确认只会白等一个超时）。收尾（执行升级被确认后 / 最后一包被确认后）、中止与清除都会切回 9600",
            "**「升级完成后读版本信息」在两种速率上各试一遍**（现场：升级**失败**时设备可能仍停在 115200）：9600 优先（命中率更高，也是共享串口的安全态），读不到再换 115200 重发一轮，**两种都读不到才算读不到**，原因文案同时给出两个速率；**没提升过就是单速率、一次切速都不做**（与旧版逐字相同）",
            "**升级包路径会记住**（现场：每次重开程序都要重新找那个几十 MB 的包）：只存路径不存字节，重开程序 / 重开本页**直接显示上次的文件**，**只有换新文件才更新**；文件已被删 / 变成目录 / 读不出来 ⇒ 不恢复（保持「未选择文件」）并写明原因 + 一条警告日志，但**落盘路径仍保留**（U 盘 / 网络盘可能回来，不替用户删记录）；恢复过程不弹框、不冲掉手工填的「文件大小」覆盖值",
            "**串口新增「运行中热切换波特率」**（`SerialWorker.set_baudrate`，端口开着也安全）：`with 写锁` 内**先 flush 排空发送缓冲、再改 DCB** —— 顺序反了前半截会按旧速率发成残帧；**绝不 close / 重开端口**（会丢设备侧会话，表现为掉线）。失败时**连内部 `_baudrate` 都不改**（否则 UI 说 115200、端口还跑 9600）；成功后发 `baudrate_changed`，由 `main_gui` 把顶部「串口配置」的速率与状态栏回显同步到**实际**速率（**刻意不落盘**：热切换是升级过程的临时状态，写进 config.json 会变成用户下次启动的新默认值）",
            "**仓库清场归档（阶段 0）**：根目录的一次性脚本 / 日志 / 导出件 / 截图收进本机 `archive/`（含 `MANIFEST.md` 清单，`.gitignore` 已忽略 `/archive/`，需要时用 `git show e45df52:<原路径>` 取回），可复用的维护脚本收进 `tools/`（DI 生成、PDF / docx 抽取、OI 表生成等），根目录只留生产模块、入口脚本与协议文档；`tools/` 下的生成物（`pdf_extract内容.txt`、`reports/`）不入库",
            "测试：新增 `test_message_tool_addr_fix.py`（**132 项**：六协议真帧 oracle = 替换后**该协议校验器 0 fail** + 只有地址与校验字节变化、前导 FE 门控、错误矩阵、输入写法容错、反例自检、offscreen GUI 接线与失败不污染）与 `test_serial_worker_set_baudrate.py`（**49 项**：先 flush 再改 DCB、非法值 / flush 失败 / 改速率失败都不改内部值、不关端口、共写锁）；`test_dl698_upgrade_gui.py` 扩至 **510 项**（+版本比对判定矩阵、提升波特率与双波特率重试、升级包路径持久化）；`release_check.py` 核心回归登记上述两条新测试",
        ],
    ),
    (
        "1.23.85",
        "2026-10-15",
        [
            "**新增「升级」标签页：协议8（DL/T 698.45）文件传输升级**（需求：把分布式产品的二进制升级包拖进来，按可设置的每包字节数分包，用 698.45 的文件传输功能逐包下发，每包等设备确认，全部传完再发执行升级命令）。流程 = 启动传输（`F0 01 07 00`，让设备进入接收升级包状态）→ 写文件（`F0 01 08 00`）×N，**每包一帧、收到确认帧才发下一包** → 执行升级（`F0 01 0D 00`，默认「立即执行」）",
            "**拖入升级包**：支持把二进制文件拖到页面上（也可「浏览…」）；显示文件名与字节数，空文件/目录/不可读一律明确报错且不进入传输状态。分包结果（总包数、每包字节、末包字节）与文件实际大小一致",
            "**参数可配**：每包字节数（默认 600）、确认超时（默认 3000ms）、重试次数（默认 3）、传输完成后是否自动执行升级；**SA 地址默认为通配地址**（类型=通配、长度 6、`AA AA AA AA AA AA`），可改为单地址/组地址/广播地址并支持一键回填文档示例地址；CA、文件信息（源文件/目标文件/文件大小/文件属性/文件版本/文件类别）、校验类型与校验值（可一键按文件计算 CRC32/MD5/SHA1）均可编辑",
            "**进度与日志**：进度条只按**已确认**的包累加（已传字节/总字节 + 第 x/N 包）；每帧 TX/RX 的 hex 与判定结果都进日志（含 DAR 值、超时第几次重试、中止原因）；失败/超时同时弹框提示（弹框与日志并存，不静默）",
            "**协议依据**：`协议文档/8.698.45协议/代理升级流程.docx`（参考流程 + 逐字节示例）+ `面向对象的用电信息数据交换协议(20210910).md` 附录 A.1/表188。组帧与解析**逐字节验证**：文档里 62 字节的「启动升级」实帧由本工具组帧后**完全相同**（含帧头校验/帧校验），响应帧也能正确解出 DAR=0",
            "**顺带修复三个既有协议栈缺陷**（不修则本功能无法自证）：① 解析器把位串（`bit-string`）的长度字段当成**字节数**，规范里是**位数** —— 直接后果是文档里那条实帧原先**根本解析不出来**（报「未知类型(0x76)」，0x76 就是「v1.0」的 v）；② 组帧侧的位串长度同错；③ 日期时间类（`date_time`/`date`/`time`/`date_time_s`）组帧时多写了一个长度字节，与解析器不一致（`time` 同时从 4 字节修回规范的 3 字节）。修复后 698 全套测试 + Web 组帧测试全绿",
            "**内部改进**：串口分帧判据（68 家族 `L+2`、末字节 16H 自证、前导 FEH 容忍、HDLC/645/Wrapper）从串口工具抽成独立模块 `frame_deframe.py` 作为**单一来源**（串口工具改为同名转发，行为逐字节不变，用 3010 组缓冲 × 7 种策略差分对拍验证）；「A-XDR 自定义」组帧模式改为直接调用共享编码器（此前两处各自手拼，位串/日期时间会写出非规范字节）",
            "测试：`test/test_dl698_upgrade.py` 286 项（纯逻辑，含文档实帧逐字节 golden、读版本信息 A10~A12、蓝牙每包上限反推 A13：MTU 512 ⇒ 475 且「整帧 ≤ 一次写上限」紧致成立/广播 SA 开销少 6 字节/小上限与非法输入、分包矩阵、SA 矩阵、确认判定、变异反证）+ `test/test_dl698_upgrade_gui.py` 355 项（离屏假串口 + 假蓝牙 worker：全通/重试/中止/进度/拖放/按钮不裁字/重同步/控件冻结/读版本信息 [17]~[21]/等设备复位 [22]/发送通道蓝牙 [23]：未连接与 MTU 未协商不设假上限、MTU 512 自动收敛到 475、整帧一次写、通道切换与掉线重连重算、落盘读回、切回串口）+ `test_bluetooth_worker.py` 123 项（新增 [8] 整帧一次写：物理上限不叠 _max_chunk、超限拒发零字节、恰好上限一次写出、特征码上限优先）+ `test_dl698_upgrade_tab_wiring.py` 37 项（真实主窗口接线，含 tab 标题与蓝牙取值回调）+ `test/test_tray_taskbar_entries.py` 27 项（托盘内嵌输入框 + 任务栏缩略图按钮：HICON 转换、降级、合成 `WM_COMMAND` 路由、文本→解析两条路径、4 个按钮分派）",
            "独立复核（trellis-check）发现并修掉 3 处阻塞级缺陷：① 接收缓冲重同步太保守（只跳「非 68/FE」），一次线噪就让缓冲头永久卡住、后续所有确认收不到 ⇒ 整轮升级失败（改为「没有半截帧在等且切不出整帧时才丢弃」，判据仍走 `frame_deframe` 单一来源）；② 传输途中换升级包会让 `_on_ack` 抛 `IndexError`（Qt 吞掉 → 状态机卡死），包数够时还会**静默改发另一个文件的数据**；③ 传输途中点「清除」⇒ 状态回 idle 但按钮门控没复位、页面永久不可用。现：传输中拒绝换文件/改参数（提示先「中止」），「清除」完整复位。同轮修掉一条恒真测试断言、删除两条不触产品代码的伪变异反证（A9 七条 → 五条）",
            "**修复 TX/RX 日志只显示半截帧**（用户反馈：启动传输那条 62 字节的帧只打到 48 字节就断了，尾部的校验值/结束符看不到）。现口径：**不超过 200 字节的一律整帧打印**；写文件这类大帧（每包几百字节起）才**只显示头尾各 100 字节、中间用 `...` 省略**并标注「(共 N 字节)」—— 头段给得到帧头/APDU 头与块序号、尾段给得到帧尾（`16H`），省略掉的正是升级包数据体本身",
            "**tab 改名为「光伏升级」+ 新增可选的「读版本信息」两步**（用户需求：升级前、升级完成后各读一次版本，便于比对确认）。两个勾选项**默认不勾**（勾选状态记住），「读版本内容」下拉二选一：**通用版本信息**（标准 OAD `43 00 03 00`，电气设备类属性 3）或**内部版本**（厂家扩展 OAD `FF 10 04 00`）—— 用户给的两条现场实帧，本工具组帧**逐字节一致**（含帧头校验/帧校验）；命令是通用的 698.45 读取（`05 01 <PIID> <OAD> 00`），SA/CA 与升级传输同一份配置（默认通配 `AA AA AA AA AA AA`）。收到的版本内容按对象定义解出来写进日志（如 `厂商代码=JCDZ，软件版本号=V1.5，…`），厂家扩展对象则直接给数据值",
            "**读版本失败不阻断升级**（刻意选择：设备可能根本不应答读版本。超时/否定/解析失败按既有重试次数重发，用尽后记一条日志继续跑；只有选中的那条命令的响应才认 —— 设备若回另一条的响应按「OAD 不符」忽略）。传输进行中这四个输入（两个开关 + 读版本内容 + 升级后等待时长）与每包字节数一起冻结",
            "**读版本信息的展示改版 + 版本内容逐字段解析**（现场反馈：解析结果贴在帧尾、日志不换行 ⇒ 得横向拖到底才看得见；内部版本只给出一串值，看不出哪项是软件版本、哪项是硬件日期）。① 日志改成「帧一行 + 明细在下」：`[RX] <整帧>` 单独一行，下一行是 `→ 版本信息（升级前·内部）读取成功（6 项）`，再往下每个字段一行（名称/值/原始字节，按显示宽度对齐）；② **升级参数栏之下新增「版本信息」展示区**，`升级前`/`升级完成后` **并排两栏**（现场要的就是前后对比），未读显示「（未读取）」、读失败显示原因，`开始升级`/`清除` 都会重置；③ **逐字段详细解析**：表191 的六个字段名与日期补全规则收口在 `dl_t698_45_data_decode`（`CLASS_ATTR_TEMPLATES` 引用同一份），标准版本信息与厂家扩展内部版本共用 —— 现场实帧解析为 `厂商代码=LHIN / 软件版本号=0039 / 软件版本日期=2026-08-03 / 硬件版本号=001A / 硬件版本日期=2025-10-13 / 厂商扩展信息=GWGSXXXX`（日期由 `260803` 补全为 `2026-08-03`）；**形状够但字节长度与表191 声明不符时，命名照给但会多一行 `⚠ 长度未自证`**（写明声明值与实发值），非结构数据则兜底一行「数据」",
            "**「升级完成后读版本信息」不再依赖是否发执行升级命令，且读之前先等设备复位**（用户纠错：有的设备收全升级包就会**自动复位升级**，所以不勾「传完后自动执行升级」同样要读版本；复位期间读不到，需要等一会儿）。现在两种情形都会读：勾了自动执行 ⇒ 执行升级被确认后读；没勾 ⇒ **最后一包写文件被确认后**读，两者都先经过「等设备复位」——新增参数**「升级后等待(s)」默认 10 秒、可改 0~600**（0 = 立即读），等待期间状态行实时显示「等待设备复位（剩余 N 秒）」，日志写明等多久/何时结束；等待中设备吐的帧按「忽略（等待设备复位中）」处理，`中止`/`清除` 都能随时打断等待（不会卡住）。等待期间**不会有任何帧发出去**（独立复核抓出并修掉一处边界：等待期若被误触发超时槽，原逻辑会按上一步的 OMD **凭空补发一条「执行升级」命令**，现已挡住并记日志）",
            "**新增「发送通道」：串口（默认）/ 蓝牙**（用户需求：蓝牙通道复用「蓝牙工具」页已建立的连接；并把 ATT 上限截过来当作每包数据的上限 —— 这是**算**出来的，不是拍脑袋）。蓝牙通道下：① 复用蓝牙工具页那条连接（本页不开连接、不断连接，蓝牙页没连时会禁用「开始升级」并说明去哪连）；② **每包字节数上限自动算好**：按「一次 ATT 写能承载的字节数」（协商 MTU − 3，或特征码自带的免响应写上限）**减去 698 帧真实开销**（帧头/地址/HCS/APDU 头/BER 长度域/FCS/结束符，用真实组帧反推，不是写死减 32）—— 例：MTU 512 ⇒ 一次写 509 字节 ⇒ **每包最大 475 字节**（你说的「不超过 480」成立），超出会**自动收敛**并把计算过程写在通道标签上；③ 发送时**一整帧一次 ATT 写**（绝不把 698 帧拆到多次写，超上限会拒发并报错）；④ MTU/连接变化、SA 改了都会自动重算；⑤ 通道选择会记住，传输中被冻结",
            "**桌面「粘性入口」：托盘菜单里直接输入报文 + 任务栏图标上的快捷按钮**（用户问「能不能像汽水音乐那样在 Win11 任务栏上放可交互控件」）。先说清能力边界：**Win11 的任务栏对第三方封闭**（Win10 的「任务栏自定义工具栏/deskband」已移除），任意控件（尤其输入框）**放不进任务栏那一行**；截图里那种「封面 + 标题 + 播放键」是 **SMTC 系统媒体卡片**、只有媒体会话能占。因此做了两条**系统支持**的入口：① **托盘菜单内嵌输入框** —— 右键托盘图标就能打字/粘贴报文，回车直接解析（判据与剪贴板检测同源；不是 HEX 也提不出报文时状态栏 + 气泡说明，不静默）；② **任务栏图标的快捷按钮** —— 鼠标悬停任务栏图标时，预览里出现 4 个可点按钮（解析剪贴板 / 快捷解析 / 批量解析 / 光伏升级），用的是官方 `ITaskbarList3/4` 缩略图工具栏接口（本机 Win11 实测可用）。注意：这类按钮只在窗口**有任务栏按钮**时可见（点 X 隐藏到托盘后没有）",
        ],
    ),
    (
        "1.23.84",
        "2026-10-14",
        [
            "**蓝牙工具：自定义按钮支持「按协议类别批量替换地址」**（用户：自定义按钮也需要支持批量替换地址的能力，通过按照协议类别统一进行替换）。底部工具栏新增「批量地址…」：选协议 → 对话框列出全部按钮（每行带当前绑定摘要）→ **默认勾选「已绑定该协议」的按钮**（另有「全选 / 全不选 / 只选本协议」）→ 填一次该协议的地址 → 一次写入这批按钮的 `protocol` + `addr`",
            "**逐按钮用「自己的报文」预检**（不是只按第一个按钮）：报文能否解析、地址长度（698.45 的 SA 由**该帧**的地址特征字节决定，逐按钮可不同）、写法是否合法、`frame_addr_fix.apply` 能否成功替换。预检失败的行标出可读原因并**默认不勾**（用户不动勾选 = 天然全或无）；若强行勾上 → 二次确认「将跳过这 N 个」后照改其余，被跳过项逐条写进日志（不静默）",
            "**顺带支持批量解绑**：协议下拉第一项「（清除协议与地址）」→ 一次移除这批按钮的 `protocol`/`addr` 两键，发送时恢复「按原样发送」",
            "**单一来源**：原先只活在「单按钮编辑」对话框里的「按帧定地址长度 + 逐字段解析」抽成 `frame_addr_fix.addr_lengths_for_frame()` / `check_values()`，单按钮对话框改调之（行为与文案**逐字符不变**，既有地址测试全绿）",
            "工具栏随新按钮调整为 6 个、并去掉行内提示标签（「右键可编辑 / 删除 / 移位」已在每个按钮 tooltip 末行）；实测 10 / 14 / 16 / 24 号字下**均不裁字**（判据 `width ≥ sizeHint`，AGENTS 陷阱 63）",
            "测试：`test_bluetooth_addr_fix.py` **111 项**（+15：共享校验入口边界 + 「与 apply 同源」抽样对拍）、`test_bluetooth_widget.py` **270 项**（+49：[16] 对话框直测 + 端到端写回 / tooltip / 日志 / 落盘 / 发送用新地址 / 清除还原 + 工具栏宽度）；**变异反证 4 条**（默认勾选改成全勾 → 9 项红；「只选本协议」改成全选 → 5 项红；跳过失败项时不弹二次确认 → 2 项红；清除只删 protocol 不删 addr → 1 项红）逐条实测变红后逐字节还原",
        ],
    ),
    (
        "1.23.83",
        "2026-10-14",
        [
            "**串口工具新增「替换地址」批量操作**（用户：串口工具页添加报文时也应该能批量替换通信地址，按对应协议替换并重新计算校验）。命令表工具行新增按钮：选协议 → 填地址 → 对**作用范围内（勾选的行；无勾选=全部）每条命令**按该协议替换地址域并**重算校验**（改地址后校验必然变，否则对端直接丢帧）",
            "**复用而非重写**：地址定位/字节序/校验算法全部走 `frame_addr_fix`（1.23.81 蓝牙页那套的同一实现，单一来源），串口页只做「命令表这层编排」——新增纯逻辑 `fix_frame_text` / `batch_fix_commands` / `AddrBatchItem` / `addr_batch_summary`（不修改入参，写回与撤销由 GUI 负责）",
            "**三个口径（用户已确认）**：① 可选**同时把协议写入这些命令的「协议」列**（「加载报文文件」导入的报文协议为空 → 写入后接收侧才能按该协议断帧解析）；② 可选**同时替换「预期响应」中的地址**——只处理纯 HEX 写法（包含/完全相等/开头/结尾匹配），且**能通过结构+校验自证才替换**，片段 / `XX` 通配 / 正则一律保持原样并在汇总里说明；③ 前导 `FEH` **只对协议 6/8 剥离并原样恢复**（依据 DL/T 645 §5.3.1、DL/T 698.45 §6.3.1 b)，其余协议带前导就该报错，不得「救活」错帧）",
            "**失败不洗白、可撤销**：结构不符 / 原帧校验不符 / 协议不支持（9~12）一律**原样保留** + 可读原因；汇总弹框分「已替换 / 未替换（自证失败）/ 跳过」三态计数并列出前 3 条原因，日志逐条给出「地址域 … → …；校验和 0xAA → 0xBB」（明细上限 20 行 + 汇总一行，不刷屏）；弹框内「撤销本次替换」一键回到替换前（逐字节），发送中禁止替换",
            "对话框按协议**动态生成地址输入行**（南网/国网=源/目的，645/依瓦=表地址，698=SA/CA，南网上行=终端地址），实时回显「将写入 N 字节：…」并给作用范围内样例命令的替换预览；「加载报文文件」导入的报文本身就是 `protocol=None`，因此协议由对话框指定，与命令表既有「协议」列互不干扰",
            "测试：新增 `test/test_serial_addr_fix.py`（**104 项**：六协议真帧 oracle = 替换后该协议校验器 0 fail / 非地址字节不变、前导 FE 门控、预期响应五类、作用范围与无效下标、不修改入参、兜底不中断整批、汇总文案）；`test/test_serial_tool_widget.py` 扩到 **536 项**（段 [35]：按钮不裁字 / 对话框字段联动与预览 / 端到端替换（含带前导 645 帧）与落盘读回 / 撤销 / 只处理勾选行 / 发送中禁止）；**变异反证 5 条**（前导不恢复 → 4+1 项红；前导门控失效 → 5 项红；未成功也改预期响应 → 1 项红；就地修改入参 → 2 项红；关闭协议列写入失效 → 1+1 项红）逐条实测变红后逐字节还原",
        ],
    ),
    (
        "1.23.82",
        "2026-10-13",
        [
            "**蓝牙工具：自定义报文区不再越加越多挤占界面**（用户：按钮一多就吃掉日志空间）。改前是 `QGroupBox` + 固定 3 列网格、**无高度上限、无滚动、不可折叠**，上限 64 个按钮 ≈ 22 行 ≈ 700px，直接把日志压没。现改为「**按钮区随可用空间自动 + 编辑工具栏常驻 + 整区可折叠**」",
            "**按钮区高度 = 内容驱动 + 分栏约束**（用户复核后修正的口径）：上限 = **按钮全部显示所需高度**、下限 = 1 行按钮高，因此**空间够就全显示、不白滚动**，空间不够才滚动。实测（offscreen，1200×800）：10 个按钮 + 把日志上拖腾出空间 → 按钮区 96px（=内容）、**滚动条 0**；64 个按钮 + 同样空间 → 按钮区用满 396px、滚动条 128（内容 528 装不下）；默认分栏下 64 个按钮 → 日志仍 496px 不被挤。对照旧实现（上限钉死 3 行）：同样腾出空间后 10 个按钮**仍只显示 3 行 + 滚动条** —— 用户报障即此",
            "关键实现：滚动容器用本页的 `ButtonScrollArea`（**最小高度由本页显式给定**）——直接用 `QScrollArea` 时它的 `minimumSizeHint()` 会跟着内层网格的最小尺寸走，64 个按钮会把「最小高度」透传给分栏器（实测下半区最小 559px、日志只剩 177px）；同时**不给下半区加尾部弹性空隙**，腾出的空间才会喂给按钮区",
            "**编辑工具栏常驻**：新增…/批量新增…/导出…/导入…/全部清除 + 提示移到**折叠区外面**（紧贴按钮区下方），折叠/展开都可见可点；折叠只收起按钮网格，收起时本区只剩标题行（并锁住 `Maximum` 尺寸策略，标题与工具栏之间不留大片空白）。展开态写进 `bluetooth_tool_config.json` 的 `custom_collapsed`，下次启动保持",
            "**竖向分栏**：右栏改为 `QSplitter(Vertical)` = 日志 ↔（发送区 + 自定义区），可拖拽分配；`childrenCollapsible=False` 防「拖成 0 找不回」；尺寸写进 `right_split` 并在载入时恢复（坏值/越界由 `bluetooth_core.normalize_right_split` 逐项夹紧或回落默认，绝不抛异常）",
            "测试：`test_bluetooth_widget.py` **221 项**（[14] 空间治理：10 个按钮腾出空间后**无滚动条** / 64 个按钮才滚动 / 默认分栏日志不被挤 / 按钮不被压扁 / 折叠后编辑按钮仍可见 / 分栏记忆与重启恢复）、`test_bluetooth_core.py` **161 项**（`normalize_right_split` 与两个新配置键的宽容处理）；**变异反证 4 条**（上限改回固定封顶 → 2 项红；工具栏放回折叠内容 → 3 项红；不设最小高度 → 1 项红；不采集分栏尺寸 → 2 项红）逐条实测变红后逐字节还原",
        ],
    ),
    (
        "1.23.81",
        "2026-10-13",
        [
            "**蓝牙自定义报文按钮支持「按协议替换地址 + 重算校验」**（用户：按钮里能填协议与地址，发送时按该协议替换地址域并重算校验，旁边有地址输入框）。新增纯逻辑模块 `frame_addr_fix.py`：按协议**定位地址域 → 替换 → 用该协议自身的实现重算校验**，界面只按协议声明动态生成 1~2 个地址输入框",
            "**v1 支持协议 0 南网 / 6 DLT645 / 7 国网 / 8 698.45 / 13 依瓦645 / 14 南网上行**（9/10/11/12 与 1~5 返回可读「暂不支持」）。地址位置与校验算法**全部复用既有实现**，不另写偏移/算法表：645 走 `DLT645FrameGenerator.build_frame`、698.45 走 `DLT69845FrameGenerator._assemble_frame`（HCS/FCS 自动）、依瓦走 `yw645_wire.encode_frame`、南网上行走 `csg_uplink_wire.encode_frame`（保留原长度域形态）、南网/国网 = 字节拼接 + `Frame.calculate_checksum` / `GDWFrame.calculate_checksum`",
            "**地址写法两种都认**：含分隔符/`0x`（如 `01 00 00 00 00 00`）→ 按帧内**在线顺序**原样写入；纯书写序（如 `000000000033`、依瓦 `450000000013`、南网上行终端地址十进制）→ 按该协议既有编码函数处理（自动字节序/BCD）。对话框实时回显「将写入 N 字节：…」，内容框能解析时还会给出**替换后预览**（含校验旧→新）",
            "**发送时生效、发送框保持原始模板**（用户口径）：点按钮 → 替换 + 重算 → 只把处理后的帧写出去，日志打「地址域 … → …；校验和 0xAA → 0xBB」；失败（地址非法 / 长度不符 / 帧不含地址域 / 原帧校验不符 / 协议不支持）一律**弹框 + 日志且一个字节都不发**。旧按钮（无这两个键）行为与 1.23.80 逐字节一致",
            "**先自证再改**：原帧必须通过「结构 + 校验」自证（`68…16`、长度域自洽、原校验正确）才允许替换——避免把别的协议的帧洗成看似合法的帧；南网 D5=0 / 国网「通信模块标识」=0 的帧明确报「不含地址域」；国网福建增补（AFN 0x50~0x56）明确不支持；地址长度必须与帧内一致（改长度会连带改 L/HCS/FCS，v1 不做）",
            "测试：新增 `test/test_bluetooth_addr_fix.py`（**96 项**：六协议真帧 oracle —— 替换后**该协议校验器 0 fail** + 地址字节/帧长/仅地址校验变化 + 错误矩阵 + 反例自检）；`test_bluetooth_core.py` **145 项**（+16：按钮新键保留/回落/坏值宽容/落盘往返）、`test_bluetooth_widget.py` **200 项**（+23：对话框联动/预览/发送替换/失败不发/发送框不被改写）；**变异反证 4 条**（645 不重算校验 → 2 项红；地址不反转 → 9 项红；698 不重算 HCS/FCS → 2 项红；不校验长度 → 2 项红）逐条实测变红后逐字节还原",
        ],
    ),
    (
        "1.23.80",
        "2026-10-13",
        [
            "**蓝牙工具：MTU / 写上限改为实时（修「同一台设备有时 20 字节、有时 512 字节」）**。ATT_MTU 由**操作系统异步协商**（Windows 上应用层只能读、不能请求），连接那一刻读到的常常还是 ATT 默认值 **23**（负载 `23-3=20`）；旧实现只在连接时读一次快照 ⇒ 一旦读到 20 就整条连接期都用 20 分包（用户截图：`0xFFE1` 显示「免响应写上上限：20 字节」）。bleak 官方文档也写明「可能先读到默认值 20、过一会儿再读才是高值」，Windows 侧由 `GattSession.MaxPduSizeChanged` 通知变化",
            "**连接后轮询等协商结果**：`BluetoothWorker._poll_mtu_if_needed()`（判据单一来源 `bluetooth_core.mtu_is_unnegotiated`：`≤ MTU_DEFAULT=23`，含 0/`None`/非法值；`MTU_POLL_INTERVAL=0.25` / `MTU_POLL_TIMEOUT=3.0` 与 `MIN_CHUNK` 同处）—— 位置在 `connected` 与订阅**之后**，界面与订阅不被白等 3 秒；值到了就更新并打一行 `MTU 协商更新：23 → 247（特征码免响应写上限 244 字节）`，**对端确实只支持默认值**时只提示一行「未收到 MTU 协商结果…不影响收发」（读数上两者不可区分，故不得报错）；断开/换设备/退出立即静默收尾",
            "**每次发送前重读实时上限**：`_write_coro` 在算分包尺寸前调 `_refresh_live_limits()`，分包按**发送那一刻**的真实值（`_char_objects` 持有 bleak 特征码活对象，**不进**投给界面的 dict，断开时清空）。实测证据：连接时上限 20 时 300 字节切 15 包，协商到 247 后同一连接改成 2 包（`test/test_bluetooth_worker.py` [7]）；**有变化才**更新 + 发信号 + 记日志，无变化完全静默",
            "**新信号 `mtu_updated(int, list)`（与 `characteristics_updated` 不可互相替代）**：后者语义是「特征码枚举完成」，界面收到会走「沿用/优选 → `set_characteristics`（**重新订阅**）」；拿它刷上限会产生多余重订阅、改写用户已选的通道。界面 `_on_limits_updated` 只更新 `_chars` 缓存 + MTU/特征码标签 + 刷新**打开中**的特征码对话框（`refresh_chars`，保勾选与当前行），MTU 文案抽在 `_mtu_text()`（连接时与实时更新共用，默认值时明示「ATT 默认值，协商结果未回」）",
            "测试：`test_bluetooth_core.py` **129 项**（+13，判据边界与常量关系）、`test_bluetooth_worker.py` **106 项**（+25：迟到协商 / 只支持默认值 / 发送前重读 MTU 与特征码两条路径 / 断开打断）、`test_bluetooth_widget.py` **177 项**（+8：标签、缓存、用 `worker.char_sets` 计数钉住「不重订阅」、对话框刷新）；**变异反证 4 条**（去掉轮询 → 5 项红；去掉发送前刷新 → 6 项红，分包退回 `[20]*15`；判据改 `<` → 2 项红；对话框刷新失效 → 1 项红）逐条实测变红后逐字节还原",
        ],
    ),
    (
        "1.23.79",
        "2026-10-13",
        [
            "**蓝牙工具：特征码自动优选 —— 连上就能收发，不用在几十个特征码里挑**。旧逻辑取设备枚举顺序里**第一个**可用写/通知码，实测常落到标准 GATT（`2A00` 设备名 / `2A19` 电量）、OTA/DFU 特征码上，用户仍得手动挑。现按「同码可写可通知（透传回环）> 厂商透传族谱（Nordic UART `6E400002/3`、`FFE1`、`FFE5/FFE9`、`FFF0~FFF2` …）> 名称/描述含 `tx/rx/uart/串口`」打分排序，并**降权**标准 GATT 与 OTA/DFU；打分表集中在 `bluetooth_core`（唯一来源），选择依据直接写进日志（例：`发送 0xFFE1（同时可写可通知 + 厂商透传族谱）；接收 0xFFE1（同一特征码，回环）`）",
            "**一键「自动探测」**（新增按钮，挨着「特征码…」）：按打分顺序逐个试「订阅 → 写一帧 → 等回包」，命中即锁定并报告「收到 N 字节回包」；失败逐条给出可读原因（订阅失败 / 写入失败 / 写入成功但 N ms 内无回包）；**全败恢复探测前的选择**并提示手工选。探测帧**优先用发送框内容**（HEX 写错直接拒绝、不写半截），为空时用配置的默认帧（`probe_frame`，默认 `41 54`=AT）—— tooltip 与日志都明说会真的写一帧",
            "**按设备地址记忆**（`char_map`，上限 20 条按时间淘汰）：同一台模块下次连接直接沿用（日志注明「沿用上次」）；换到**没记过**的设备会自动清掉上一台的选择并重新优选（否则上一台的通道会压住自动优选）",
            "**协议时序**：新增 `bluetooth_worker.subscribe_finished` —— 订阅是异步的，写完才等回包会丢掉首个响应，探测必须先等到它（候选无接收通道时也发一次）。纯逻辑状态机 `bluetooth_core.ProbeSession` + 界面 QTimer 分步驱动，**不阻塞 GUI**，可中途停止",
            "**界面提速**：状态行直接显示「发送 → 0xFFE1 ｜ 接收 → 0xFFE1」（未选显示「未选」）；「特征码…」对话框把优选结果**预选并置顶**、顶部给出推荐依据、不可用方向**文字标注**「（不可写）/（不可通知）」（置灰在 QSS 主题下看不见，见 §8 陷阱 71）",
            "测试：`test_bluetooth_core.py`（**116 项**：打分/优选/探测状态机/记忆/载荷解析）、`test_bluetooth_worker.py`（**81 项**：订阅完成信号成功与失败两条路径）、`test_bluetooth_widget.py`（**169 项**：含反例自检「旧逻辑会选 `2A19`」、探测命中/全败恢复、沿用与换设备、对话框预选与标注）；**变异反证 3 条**（打分排序失效 → 12 项红；订阅失败也照写 → 3 项红；记忆写同一全局键 → 3 项红）实测变红后逐字节还原",
        ],
    ),
    (
        "1.23.78",
        "2026-10-13",
        [
            "**串口工具：协议特征断帧不再被前导 FEH 破坏**（现场报障：协议 8 下 `FE FE FE FE 68 21 00 … 38 16`（39 字节）被切成两条 `[RX]`）。根因：分帧函数一律要求首字节 `0x68`，前导 FE 使其判不出长度 → `_frame_incomplete()` 也判 False → 退回 10ms 静默窗口把首片单独刷出。现 68 家族（`ft12_68` / `dlt645` / `dlt698_45` 三种策略**与未指定协议的启发式**）先按 `_wakeup_base`（= `wakeup_prefix.wakeup_prefix_len`，单一来源）跳过帧首连续 FE 再算长度，**返回值含前导字节数**（调用方仍按 `buf[need-1] == 0x16` 自证 ⇒ 三处调用点零改动）；`_frame_incomplete` 里「只有 FE、还没见到 68」也算已开始未收全；HDLC / DLMS Wrapper 不加前导容忍",
            "**新增「断帧设置」**（接收模式下方）：断帧方式 `auto`（有协议 → 按协议结构特征断帧拼帧；无协议 → 按字节超时 + 68 结构自证）/ `timeout_only`（忽略协议结构与自证）；4 个可调超时 `字节静默 10ms` / `聚合最长持有 200ms` / `协议帧等待静默 300ms` / `协议帧等待上限 5000ms`。默认值 = 原模块常量（`FRAME_TIMEOUT_DEFAULTS` 单一来源）⇒ 对老配置零行为变化，**只新增键、`CONFIG_VERSION` 不动**；`FRAME_TIMEOUT_RANGES` 是 UI spin range 与 `merge_params` 夹紧的唯一来源",
            "断帧依据可自查：`[断帧] 方式=…；依据=…（如「协议特征 dlt698_45（698.45 结构(68 L L C…)），前导 FE 自动跳过」/「未指定协议 → 按字节超时」）；超时 …` 只在**设置变更 / 协议变化 / 每轮开始**时输出一行（不逐帧打印，避免刷屏）",
            "测试：`test_serial_proto_frame.py`（**147 项**：前导 FE 矩阵 0/1/2/4 个 × 三种策略与启发式、纯 FE 与非 68 数据不误判、4 个新参数默认/夹紧/回落、RANGES 与 DEFAULTS 键对应）、`test_serial_tool_widget.py`（**501 项**：现场帧 14+25 两块交付、块间隔 50ms > 字节静默仍**只出 1 行**、`timeout_only` 对照、参数持久化往返、新控件不裁字）；**变异反证 3 条**（不跳前导 FE / 返回长度不含前导 / 断帧方式失效）实测变红后逐字节还原",
        ],
    ),
    (
        "1.23.77",
        "2026-10-13",
        [
            "**协议9 新增 2.0 测试扩展 `0x0009`「报文聚合传输测试模式」**（依据《宽带双模通信模块（通感一体物联版）相关测试命令定义_260922》1.4.9：`报文聚合数目 | 字节3 | 位0-7 | 8bit | 要求聚合发送的MAC帧个数`）。此前 `0x0001~0x0008` 已支持，`0x0009` 三处表全部缺失（解析映射表 / 解析分派表 / 组帧 `_EXT_BUILDERS`）——本次补齐，并让**解析 · 组帧 · 仿照报文回填 · 批量摘要**四处同构",
            "解析（`csg_new_gen_cmd_payloads`）：`_TEST_EXT_ID_MAP[0x0009]` + `_parse_test_ext_0009`（`报文聚合数目` 整字节：原始值 `0xNN` / 解析值十进制 / 说明「要求聚合发送的MAC帧个数」）+ 分派表登记；扩展数据缺失时按既有风格输出 `❌ 解析失败` 行（不返回空表、不抛异常）",
            "组帧（`csg_new_gen_frame_gen`）：`TEST_EXT_ID_MAP` / `build_ext_0009(agg_count=1)` / `_EXT_BUILDERS` / `test_modes()` 新增 `ext_agg`（组帧页模式下拉与仿照回填候选都读它，界面不硬编码）；取值越界（>255 / 负数 / 非整数）抛 `FrameBuildError`，不静默截断",
            "字节口径与既有扩展一致：`ext_data[x] = 文档字节 x+3`（`_parse_test_ext_0005` docstring 已固化）⇒ `报文聚合数目` = 扩展数据第 0 字节；`csg_frame_reverse._fill_ext` 补 `0x0009 → params[agg_count]`，粘贴现成 `0x0009` 帧可「回填 → 原样重建」（`unmapped` 为空）",
            "顺带修正 `csg_test_frame_gen_widget.py` 三处**互不一致且都已过期**的模式数量文案（docstring 写 26 / 载荷来源下拉写 24 / tooltip 写 26）→ 统一为模块级 `_MODE_COUNT = len(fg.test_modes())` 单一来源（现 25），不再随模式增减漂移",
            "测试：新增 `test/test_csg_test_ext_0009.py`（**76 项**：映射表与组帧模式清单 / 解析 `0x00·0x01·0x05·0xFF` golden 含偏移 20 / 扩展数据缺失容错 / 未登记扩展ID `0x000A` 护栏 / 组帧逐字节与越界 / 组帧→解析闭环（`app` 与 `auto` 两级）/ 应用层帧→仿照回填闭环（逐字节重建）/ 摘要片段与非测试帧无污染），登记 `release_check.py:CORE_TESTS`；**变异反证 3 条**（解析位宽取低 4bit → 3 项红；组帧数据域写 2 字节 → 5 项红；反解删 `0x0009` 分支 → 5 项红）实测变红后逐字节还原",
            "回归：`test_csg_new_gen` / `test_csg_summary` / `test_csg_frame_reverse` / `test_csg_frame_templates` / `test_csg_link_frame_gen` / `test_csg_batch_prefix` / `test_csg_batch_parse_level` / `test_csg_hrf_mac` 全绿；GUI `test_csg_frame_gen_gui`（139 项：25 个模式全部能组出带链路层、FCCS/CRC-32 校验通过的 SOF 帧）与 `test_collapsible_section`（51 项）全绿",
        ],
    ),
    (
        "1.23.76",
        "2026-10-13",
        [
            "**修复协议8/协议6「带 FEH 前导码的合法帧解析失败」**（用户报障：蓝牙工具收到 "
            "`FE FE FE FE 68 21 00 C3 …` 报「❌ 解析失败  起始字符错误: 0xFE, 期望 0x68」，39 字节全部可见却一字段都解不出）",
            "根因是**规范符合性缺口**，不是容错不足：DL/T 698.45-2017 §6.3.1 b)「在有效数据帧前加 4 个 FEH 作为前导码」；"
            "DL/T 645-2007 §5.3.1「在主站发送帧信息之前，建议先发送 4 个字节 FEH，以唤醒接收方」。"
            "旧实现把首字节当起始符判据 ⇒ 带前导的合法帧一律被判非法",
            "新增 `wakeup_prefix.py` 作为**全仓唯一**前导判定实现（零依赖、无 Qt）：`wakeup_prefix_len` / `strip_wakeup_prefix` / "
            "`wakeup_display` / `make_wakeup_row` / `shift_row_offsets`。口径：只跳过帧首**连续** `0xFE`（0~N 个，"
            "不假定恰好 4 个、不猜测其它字节、**不动帧中间的 FE**）；68 家族首字节恒 `68` ⇒ 剥离零误伤",
            "协议8：`DLT69845Parser.parse` 入口剥离并记录 `唤醒前导`（字节数 + 原始值），`原始数据` 保留用户原始输入（含 FE）；"
            "`parse_to_table` 首行插入「唤醒前导字节」并把**所有帧内行偏移整体 +skip**（报障帧实测：起始字符 4~4、HCS 16~17、"
            "FCS 36~37、结束符 38~38，与原始输入逐字节对齐）",
            "协议6：`check_structure` / `check_frame` / `calc_checksum` / `parse` 统一按**剥离后**的帧判定"
            "（对已剥离输入幂等），结果新增 `wakeup_len`、`raw_hex` 保留原始输入；"
            "`DLT645GuiParser.parse_to_table` 同款插行 + 偏移位移（帧起始符 1 = 4~4、校验和/帧结束符 = 末两字节）",
            "两个校验器（`DLT69845Validator` / `DLT645Validator`）先剥离再走全部检查，`skip > 0` 时追加「前导唤醒字节」PASS 说明项 —— "
            "消除「解析成功但校验报起始符错误」的不一致；坏 CS 帧仍 FAIL（前导**不放宽任何判据**）",
            "蓝牙工具：`_write_coro` 分包时输出说明性日志「数据 N 字节按单包上限 M 字节分为 K 包（来源；协商 MTU=…）"
            "※ ATT 层限制，应用层无法一次写出更多字节」（尺寸与来源同一实现 `_chunk_plan`，界面不另算一份）—— "
            "分包本身不可消除（ATT `MTU−3`），但用户从此可自查",
            "范围**严格限定**协议8/协议6：协议 0/7/9/10/11/12/13 行为一律不变（逐协议护栏断言 + 「白名单之外无引用」源码守卫）；"
            "批量/Web 帧提取本就从 `68H` 起同步、无需改动（新增「混合日志含 FE 仍提出正确帧」回归）",
            "新增 `test/test_wakeup_fe_prefix.py`（**73 项**，登记 `release_check.py:CORE_TESTS`）：报障帧 golden / 局部前缀 / "
            "全 FE 与「FE 后非 68」降级 / 无 FE 零回归锚点（协议6 冻结在 13 行基线）/ 协议6 解析 + 表格偏移 + 虚拟表从站 / "
            "两校验器 / 逐协议护栏 / 批量与 Web 提取 / offscreen GUI（单帧页 + 串口·蓝牙共用回调）/ 反例自检 + 单一来源源码守卫",
            "`test_bluetooth_worker.py` 补分包日志断言（含单包上限与 MTU 来源）；`test_dlt645_table_offsets.py` 适配前导行",
        ],
    ),
    (
        "1.23.75",
        "2026-10-12",
        [
            "**修复协议11（HDC 1.0）`报文头长度` 解析错误**（用户报障：报文头 `81 C1 …` 被解成 "
            "33 → 表格显示 `33×4B=132B`，正确应为 **6**）。根因是该 6bit **跨字节位域的拼装方向取反**："
            "它是全协议唯一一处「字节号小的段存高位」（`(b0>>6)<<4 | (b1&0x0F)`），而本协议其它跨字节位域"
            "（12bit「转发数据长度/配置值」、MAC 头 MSDU 长度、事件 0x008 功能码）与协议10 同名字段"
            "（`_parse_comm_test`）都是「**字节号小的段是低位段**」（口径同 `_bits_lsb`）。",
            "口径统一为 `hdr_len = ((b1 & 0x0F) << 2) | ((b0 >> 6) & 0x03)`，且**值即报文头的字节数**"
            "（不再是「4 字节字」）：协议11 全部 8 处 + 协议10 `gw_new_gen_cmd_payloads` 全部 14 处同步收口"
            "（协议10 的抄表/通用/注册/事件等旧值同样与自家说明「固定为8」自相矛盾）。",
            "**四处证据**（旧口径只在字节0 bit7-6 == 0 时与「值=字节数」数值相同——此时 "
            "`4×lowNibble == lowNibble<<2`，所以此前拿 `01 53`→12B / `01 61`→4B / `01 02`→8B 校准"
            "都看不出问题，用户帧的字节0 = `0x81`（bit7-6 = 0b10）才把它暴露出来）："
            "① 协议10 真实帧 `81 61 20 00 00 00` 的 `报文头长度` = 6，且该载荷**恰好 6 字节**即整根报文头"
            "（`test_gw_ext_cmd.py` T13）；② 本协议 0x0A1 真实帧 `01 53` → 12 字节头，与实测 DATA "
            "自字节 12 起自洽；③ 表2 扩展命令的报文头就是字节0~5 = 6 字节，用户报障帧 `81 C1` → 6；"
            "④ 各报文自家说明（「固定为8」/「通用报文头 4 字节」/「下行=20, 上行=36」）与新的值逐一对上。",
            "表格呈现同步：**原始值**给按值序的位段拼装式 `0b0001+0b10`（可直接读为数值）、**说明**给"
            "字节/比特归属 + 移位拼装式（`0b10 | 0b0001<<2 = 6`）+ 「单位 字节，报文头长度 = 6 字节」；"
            "解析值列由 `N×4B=MB` 改为 `N字节`。`_bit_span_note` 去掉已无调用方的 `lsb_first` 参数"
            "与「高位段在前」分支（全协议只有一种打包方向）。",
            "**不动被判定的槽位**：测试模式/配置操作的原始值仍为十进制 `12`、解析值仍为模式名"
            "（`batch_core.extract_test_mode_content` 靠「非数值者即名称」探测）；`转发数据规约类型` 的"
            "说明被测试逐字断言，故不加尾注。",
            "测试：`test/test_hdc10_bitfield_display.py` 重写并扩到 **47 项**（新增用户报障帧 "
            "`81 C1 → 6字节` 段、**与协议10 同字节同值对拍**、「值=字节数」偏移锚定、10 组取值三处反解恒等、"
            "旧口径 33 的反证）；`test_hdc10_meter_reading.py` / `test_hdc10_pb_structure_probe.py` / "
            "`test_hdc10_event_data.py`（builder 改按字节数编码）期望同步。**变异反证**：方向改回旧口径 → "
            "16 项变红；位域渲染段序/单位改回旧样 → 17 项变红（各自还原后逐字节一致、套件全绿）。",
            "配套：`APP_VERSION` `1.23.74 → 1.23.75`、README 版本徽章、两个 `.iss` 同步；"
            "AGENTS.md 陷阱 74 重写（原文声称「两类位域方向相反、别互相纠正」已被本次证据推翻）。",
        ],
    ),
    (
        "1.23.74",
        "2026-10-12",
        [
            "**协议11（HDC 1.0）跨字节位域在表格里的呈现**（用户追问：「报文头长度 = 4B 是怎么解析出来的、"
            "具体是怎样的多字节组合、如何体现 bit 组合关系」）：原先只给 `1×4B=4B`，"
            "看不出这个 1 来自哪两个字节的哪几位、也不体现同字节邻居的位归属。",
            "新增三个纯函数（`hdc10_parser.py`：`_bit_slice` / `_bit_span_note` / `_hdr_len_cells`）："
            "**原始值列**改为给位段拼装式 `0b00+0b0001`（`+` = 按位拼接），**说明列**给完整拼装式 "
            "`0b00_0001 = 1`（`_` 标出字节边界）+ 单位口径（4 字节字，类 IPv4 IHL）；"
            "相邻位域字段的说明列追加「位域归属」（如 `报文头字节1[bit7-4]=4bit=0b0110`）。"
            "偏移列本就高亮跨字节区间（报障帧为字节 37-38），两处合起来即可核对 bit 占用。",
            "覆盖 `报文头长度` 的**三处产出点**（抄表 0x001~0x003 / 通信测试 0x006 / 升级状态 0x034），"
            "并把 0x034 的解析值由裸数字补成 `N×4B=MB` 与另两处对齐；0x006「检测扩展命令」的 "
            "测试模式(byte1 bit7-4) / 12bit 配置值(byte2 bit7-4 + byte3) / 安全测试模式(byte4 bit3-0) / "
            "PHR_MCS / PSDU_MCS / PbSIZE 均补「位域归属」。",
            "**口径陷阱**：同一应用报文头里两类跨字节位域的拼装方向**相反** —— `报文头长度` 是"
            "「字节号小的存高位」（`(b0>>6)<<4 | (b1&0xF)`；实测 `01 53`→3→12B、`01 61`→1→4B），"
            "12bit「转发数据长度/配置值」是「字节号小的存低位」（`((b2>>4)&0xF) | (b3<<4)`，口径同 "
            "`_bits_lsb`）。故位域说明按各自方向渲染：前者 `0b高位段_低位段`，"
            "后者 `0b低位段 | 0b高位段<<4`（详见 AGENTS.md 陷阱 74）。",
            "**不动被判定的槽位**：测试模式/配置操作的原始值仍为十进制 `6`、解析值仍为模式名"
            "（`batch_core.extract_test_mode_content` 靠「非数值者即名称」探测，动了摘要就退化成"
            "「测试模式:6 (频段切换操作)」）；`转发数据规约类型` 的说明被测试逐字断言，故不加尾注。",
            "新增回归 `test/test_hdc10_bitfield_display.py`（38 项，已登记 `release_check.py:CORE_TESTS`）："
            "报障帧渲染逐字断言、**位序反证**（`0x81/0x63` 正解 35 ≠ 反解的 50）、"
            "`原始值/说明/解析值` 三处反解恒等（8 组取值 + 边界 0）、三类报文口径一致、"
            "相邻字段归属与摘要槽位不回归、60 条真实夹具逐条自洽、0-5 字节 × 7 级别不抛异常。",
            "配套：`APP_VERSION` `1.23.73 → 1.23.74`、README 版本徽章、两个 `.iss` 同步；"
            "全量 `release_check.py --with-gui` → PASS=131 / FAIL=0 / WARN=0。",
        ],
    ),
    (
        "1.23.73",
        "2026-10-12",
        [
            "**修复协议11（HDC 1.0）「台体日志帧解析不出内容」（用户现场报障：协议选 [11]、"
            "级别「FC+PB解析(完整MPDU)」，152 字节帧只解出 8 行错位内容）**：台体把报文内容组好后落日志，"
            "**FCCS / PBCS / ICV 由硬件发射机在发射时填充**，日志里留空为全 0 —— 这类「留空」帧同样要能解析。",
            "根因一（主）：`_detect_fc` 把 FCCS 当**唯一判据**。该帧 `crc24(字节0-12)=0xB3A813` 而日志里是 "
            "`00 00 00` → 判「无 FC」；而「判无 FC」分支里 **DT=0（信标）有启发式兜底、DT=1（SOF）没有** → "
            "整帧掉进「裸 MAC 帧」解析，吐一屏错位臆造（版本=1 单跳帧协议、MSDU长度=0、"
            "ICV 取到 `00 F0 FF FE` 校验失败、144 字节「多余数据」）。",
            "**修法：FCCS 留空（全 0）时改判帧体结构**（新增 `HDC10Parser._looks_like_fc_payload`）——"
            "帧长 ≥ 26、**只对 SOF 帧（`DT==1`）生效**，且要求「偏移16 是合法 PBH 且置了帧起始位」+ "
            "「`_probe_pb_form` 打分 ≥ 4」。**不做 DT 泛化**：开头为 PBH 的物理块帧（`0x40/0xC0`）其 byte0 "
            "低 3 位同样是 0，按 DT 统一放开会把 PB 级输入误判成信标帧。阈值 4 复用无-PBH 探测的同一把尺子，"
            "标定依据：真实单 PB 现场帧 44 条被误当 FC 解时打分分布 **{0: 28, 1: 16}（最高 1）**，"
            "而本帧 **6 分**（MSDU 长度/类型合理 + 端口/报文ID 命中 + ICV 自校验通过）→ 余量充足。"
            "**FCCS 有值但校验不过仍保持严格**（不判 MPDU），只对「全 0 留空」放开。",
            "**显式级别即契约**：`parse_to_table` 新增 `forced_fc` —— 用户选 `fc_pb` / `fc_mac` 时尊重声明，"
            "不再因 FCCS 不过就偷偷改走 MAC 帧路径；同时**必须**满足规范硬条件才不会劫持 PB 级输入："
            "帧长 ≥ 26、`DT==1`、标准版本号 0、**偏移16 是置了帧起始位的首块 PBH**（表37：首块不带帧起始标志"
            "即自相矛盾）。实测依据：60 条真实夹具里唯一低 3 位为 1 的 `0xC1` 开头的 PB 帧，其 "
            "`frame_bytes[16]=0x06` 无帧起始位 → 被挡在 FC 路径之外（不加这条时该帧结果由 8 行变 18 行的错位臆造）。",
            "根因二（连带，同帧同症状）：`_parse_pb_and_mac_header`（`fc_mac` 级别）对**首块也跑**「是否省略 "
            "PBH」的探测，帧尾 107 字节 0 填充让 `_probe_pb_form` 的「ICV 全 0」强证据**误命中** → 合法 PBH "
            "`0xC0` 被当 MAC 头解析（PB头=无、MSDU类型=0）。**首块已置帧起始位时直接采信 PBH**，"
            "与 `_parse_pb_block` 的 SOF 分支同条件（防两处漂移）。",
            "根因三（用「填充CRC-24」会静默改坏帧）：`main_gui._fill_crc24` 的 **eFC 分支没有协议门控** —— "
            "`byte0&7==1` 且 `byte19 bit0==1` 即命中，把 `crc24(字节16-28)` 写进**字节 29-31**；"
            "而协议11 的 FC 之后直接是物理块，字节 29-31 落在 MAC 帧头里 → 实测「组网序列号」由 `0x01` "
            "被改成 `0xE1`。**eFC 与逐物理块 PBCS 一并门控到协议9**（南网新一代专属布局），"
            "提示写明「协议N 的 FC 之后直接是物理块，无此布局」；**FCCS（字节13-15）保持对所有协议生效**。",
            "**留空 → 「未填充」而非「错误」**：FCCS 行留空时状态改为「⚠ 未填充(全 0)：…此处计算值应为 0x…」；"
            "物理块尾 3 字节全 0 新增「⚠ PBCS未填充」行（与「⚠ 无PBCS（截断）」区分，均不判为错误）；"
            "FCCS 未通过仍按 FC 解析时追加「⚠ FCCS 未通过」行写明依据，不让用户以为解析器在瞎猜。",
            "**端到端结果（用户原帧，auto 与 fc_pb 逐字符一致，54 行）**：DT=1 SOF、目的TEI=4095 广播、"
            "物理块个数=1、分集拷贝基本模式=4（136B，恰等于 FC 后剩余 136 字节）、PBH=`0xC0`、"
            "MAC 版本 0 标准头、MSDU类型=`0x30`(48 应用层)、MSDU长度=8、端口 `0x11`、"
            "报文ID `0x0006`（通信测试-频段切换，目标频段1）、**ICV `C5 0F 88 0D` 校验正确 ✓**、"
            "随后为「帧尾多余数据 107字节」与「⚠ PBCS未填充」。",
            "测试：新增 `test/test_hdc10_blank_checksum.py`（**55 项**，登记 `CORE_TESTS`：夹具自洽 / "
            "`_detect_fc` 留空放行与 6 组变异反证 / auto 与 fc_pb 端到端逐字段 / `fc_mac` 与 auto 的 "
            "PBH+MAC 头一致 / 级别尊重声明 / 8 档边界输入 × 7 级别不抛异常 / 60 条真实夹具零劫持）"
            "与 `test/test_hdc10_blank_checksum_gui.py`（**20 项**，登记 `GUI_TESTS`：协议11 下字节 29-31 "
            "不被改动且「组网序列号」仍为 `0x01`、FCCS 仍写入且两处 CRC-24 实现同源、协议9 的 4 个 PBCS "
            "位点回填不受影响、界面 `parse_single` 读出业务内容）；**变异反证**：逐条退回四处修复"
            "（`_detect_fc` 留空分支 / `fc_mac` 首块门控 / `forced_fc` 规范硬条件 / `_fill_crc24` 协议门控）"
            "→ 对应测试**全部变红**，还原后全绿。",
            "配套：`APP_VERSION`（`1.23.72 → 1.23.73`）、本 CHANGELOG 条目、`AGENTS.md`（§1 版本 / §8 陷阱 72 与 73、"
            "§10 摘要）、`CLAUDE.md`（版本 / 常见陷阱）、README 版本徽章与协议数口径（「13 种」→「15 种」，与协议表一致）、"
            "两个 `.iss` 同步；全量 `release_check.py --with-gui` → **PASS=130 / FAIL=0 / WARN=0**。"
            "约定沉淀为「**协议规定的校验位，凡现场存在『留空待硬件填充』"
            "的，解析器必须给出『未填充』结论而不是『校验失败』，且不得因此改走另一条帧结构路径**」。",
        ],
    ),
    (
        "1.23.72",
        "2026-10-12",
        [
            "**修复「特征码」选择对话框列表文字看不清（用户现场报障：浅色主题 + 深色系统下隔行黑字压深底）**："
            "根因在**主题层** —— 各主题的「表格 / 字段树」选择器组只列了 `QTableWidget, QTreeWidget`，"
            "**从未覆盖 `QListWidget`**。报障环境实测 `AppsUseLightTheme=0`（Windows 深色模式）、"
            "Qt 给出的 `QPalette::AlternateBase = #001a68`（深藏蓝），而 `LIGHT_QSS` 有 `* { color: #000000 }` "
            "强制黑字 —— 于是列表的**交替行**是「深色系统底 + 黑色主题字」，实测对比度仅 **1.35**"
            "（同环境下 glass 主题 1.06、mica 1.12），非交替行反而是白底黑字，视觉上就是「隔行看不清」。"
            "反向组合（浅色系统 + 暗色主题）同样是交替行 **1.23** —— 本质是**主题与系统调色板不一致时，"
            "未被 QSS 覆盖的交替行取了另一侧的底色**。",
            "**在主题层修，不给蓝牙页打补丁**：把 `QListWidget` 补进 5 套带 QSS 主题（default / dark / glass / "
            "mica / windowsvista）的「表格 / 字段树」**全部四条选择器**（基类组 + `::item:!alternate` / "
            "`::item:alternate` / `::item:selected`），配色一律沿用各主题既有表格值（如 dark 用 "
            "`#2b2b2b` / `#333333` / `#e0e0e0`、选中 `#42a5f5` + white，light 用 `#ffffff` / `#e8e8e8` / "
            "`#000000`），不留新口径；参数化生成的 `build_glass_qss` / `build_mica_qss` 自动继承。"
            "**受影响的不止蓝牙页**（`feedback_dialog` 的截图列表、`main_gui` 的列表同一根因），一并修好。",
            "`bluetooth_tool_widget.CharacteristicSelectDialog` 自身**一行样式都没改**（页面不写 light/dark "
            "硬编码、配色归主题 QSS 接管）—— 修的是主题口径，不是某张列表。",
            "**回归**：`test/test_theme_settings.py` 新增 1c 节「列表主题覆盖」（48 → **73 项**）。"
            "① 静态断言：凡主题给 `QTableWidget` 的选择器行必须同时出现 `QListWidget`（新主题漏写即变红）；"
            "② 渲染断言：把系统调色板**显式注入**成深色 / 浅色两种，真实 `grab()` 取像后只取**文字区**"
            "（跳过勾选框 —— 勾选框图元的高对比像素会掩盖文字问题）算 WCAG 对比度，交替行与普通行都必须 ≥ 4.5。"
            "**变异反证**：把 5 套 QSS 在内存里还原成修复前写法 → 新断言变红 **9 项**"
            "（default 深色系统 1.35 / glass 1.06 / mica 1.12 / dark 浅色系统 1.23，外加 5 条静态覆盖），"
            "还原后 73/73 全绿。",
            "配套：`APP_VERSION`（`1.23.71 → 1.23.72`）、本 CHANGELOG 条目、`AGENTS.md`（§1 版本 / §8 陷阱 70 新口径 / "
            "§10 摘要）、README 版本徽章、两个 `.iss` 同步；约定沉淀为「**新增主题或新增视图类控件时，"
            "表格与列表必须同款覆盖，且必须验交替行**」。全量 `release_check.py` → **PASS=117 / FAIL=0 / WARN=0**。",
        ],
    ),
    (
        "1.23.71",
        "2026-10-12",
        [
            "**新增「蓝牙工具」标签页：本项目首次具备 BLE 蓝牙通信能力**（集成自子工程"
            "「蓝牙转串口工具02」的 PySide6 版与 PyTauri 版传输核心）。始终可见、懒加载，"
            "与协议无关：**扫描 BLE 设备 → 连接 → 选特征码 → 收发报文 → 解析 → 虚拟串口透传**。",
            "**三个新独立模块**（`main_gui.py` 只做接线，不塞实现）：`bluetooth_core.py`"
            "（纯逻辑：配置持久化、MTU 分包、静默超时切帧重组，可脱 GUI/硬件单测）、"
            "`bluetooth_worker.py`（`QObject` + 私有 asyncio 循环线程：扫描/连接/特征码/订阅/写/重组）、"
            "`bluetooth_tool_widget.py`（UI 与三个对话框）。BLE 线程由页面自持 —— 蓝牙设备不存在"
            "「COM 口全局独占」约束，故不像串口那样由主窗口托管单例。",
            "**接线完全复用既有约定**：串口侧复用主窗口**共享** `SerialWorker`（虚拟模式透传，"
            "端口/波特率只在顶部「串口配置」设置）；解析走 `set_parse_provider(self._serial_parse_provider)`，"
            "与单帧页/串口工具页同一套 `_get_current_parser` + `build_gui_parser` 分派，逐字段结果一致；"
            "「送入单帧解析」复用 `_send_frame_to_single_parse`；widget 不 import `main_gui`（无循环依赖）。",
            "**相对原工具的实测改进**：① 写入分包按**协商 MTU / 特征码 `max_write_without_response_size`**"
            "计算（原工具硬编码 200 字节）；② 重组只保留「静默超时切帧」单一语义，不同特征码独立成帧；"
            "③ 断开/掉线前**交出未成帧残包**，不丢尾包；④ 发送格式三态（自动/HEX/ASCII）且"
            "**HEX 写错绝不静默按文本发**（`68 12 0G` 报错拒发，而不是把这 8 个字符的 UTF-8 字节发下去）；"
            "⑤ 连位数不成对（`68 12 0`）也拒发 —— 不让底层静默补 0 发出另一串字节；"
            "⑥ 未选特征码时自动取第一个可用收发通道并记日志；⑦ 未知 RSSI（bleak 报 0）不再误显示为满格。",
            "**弹框必留日志**：内容无效 / 未连接 / 回调缺失等原先只弹模态框的路径，现在同时写一条日志 —— "
            "弹框一点就没了，现场排查只能靠日志。",
            "**新增 4 份测试**（`test/`，均为独立脚本、结束 `os._exit`，已登记 `release_check.py:CORE_TESTS`）："
            "`test_bluetooth_core.py`（68 项纯逻辑）、`test_bluetooth_worker.py`（74 项，注入假 bleak）、"
            "`test_bluetooth_widget.py`（146 项，offscreen + 假 worker/假串口，不打桩不碰硬件）、"
            "`test_bluetooth_tab_wiring.py`（36 项，构造真实 `MainWindow` 验证懒加载/注入/主题/收尾接线 —— "
            "这些接线错了上面三份照样全绿）。",
            "配置持久化到 `app_paths.data_path(\"bluetooth_tool_config.json\")`（原子写 + 坏文件宽容回落默认），"
            "含自定义报文按钮、特征码选择、日志自动保存设置；打包 spec 补 `bleak` 相关 `hiddenimports`，"
            "缺库时功能降级并给出明确安装提示（不影响其余页面）。",
        ],
    ),
    (
        "1.23.70",
        "2026-10-10",
        [
            "**协议14 网络管理（深化应用）扩展解析**：新增《新一代计量自动化主站通信网络管理技术要求》"
            "第 4 章「终端上行规约（针对网络管理扩展）」的 15 个扩展 DI（AFN=0A/0C/04/13）与**结构化内容解码**"
            "——设备台账（65 字节 14 项）、从节点/入网被拒地址列表、周边节点信道信息（16B/节点）、"
            "网络拓扑（19B/节点：TEI + 代理 TEI + 入网时间 + 代理变更 + 离线次数 + 节点信息位域）、"
            "多网络信息、模块类型 + 离线时长、节点自检（过零/串口485/上次离网/复位原因枚举）、组网成功率、"
            "并发数、宽带载波频段、从节点重启、远程通信模块网管信息（21 项，报文字段高位在前）、"
            "设备掉电/上电告警（ARD2）；内容按字段展开为解析表子行（`↳ 字段`）",
            "**修正协议14 数据标识 DI 线上字节序：低字节在前**（表 `E1 00 60 12` → 线上 `12 60 00 E1`）。"
            "依据：新文档 13 条实帧（send/rec 成对、CS 全部自洽）+ 5.1.1「低字节在前」+ 协议0（`di_bytes[::-1]`）"
            "与 DL/T 645 同族约定；1.23.68/69 按表序上线，真实设备帧会显示「未收录 DI」。"
            "现解析与组帧统一走 `to_semantic_di()`/`to_wire_di()`，解析表以「原始值=线上顺序、解析值=表序」并列",
            "新增 `csg_uplink_nm.py`（网管扩展 DI / 枚举 / 结构化解码的唯一事实来源，含前缀规则 `E08004xx` 与"
            "`E1006014` 同表列 `E1006004` 并存）；`csg_uplink_di` 合并扩展条目并支持前缀解析；"
            "`content_length(di, data)` 支持变长列表按内容推算（多信息体可正确切分）；"
            "组帧模板 +5 条网管扩展，预设库 `CSG_UPLINK_command.json` 6 → **11 条**（全部 CS 自洽）",
            "回归：`test/test_csg_uplink.py` 90 → **126 项**全绿，含「文档 13 条实帧全部 valid」"
            "与「7 条 send 实帧逐字节复现（长度域 + DI 顺序 + CS）」",
            "文档：新增 `协议文档/14.南网上行通信规约/新一代计量自动化主站通信网络管理技术要求.md`"
            "（由同名 .docx 用 markitdown 转换），AGENTS §5.11 记录扩展 DI 清单与 DI 字节序口径",
        ],
    ),
    (
        "1.23.69",
        "2026-10-10",
        [
            "**修正协议14（南网上行通信规约）长度域：L 为 2 字节并重复一次 ⇒ 线上占 4 字节，整帧 = L + 8**"
            "（用户指正；1.23.68 按「单个 2 字节小端 L、整帧 L+6」实现，属误读）。"
            "证据链（PDF 版面按块坐标复核）：① 5.1.2 + 图3 规定 L 是 **2 字节** 16 位（网络传输上限 16383 亦需 16 位）；"
            "② 图2/图11/图12 的固定报文头逐行画出 `68H / L / L / 68H`，而图中**一行即一个字段**"
            "（同一张图里 A(7B)、信息点标识(2B)、数据标识编码(4B) 各占一行）⇒ 两个 L 是两个字段；"
            "③ 条文解释「长度L由两个字节组成，两个重复的长度L必需完全一致，否则，此帧为无效帧」+ 5.2.1「识别2个长度L」；"
            "④ 5.2.1「每帧接收的字符数为用户数据长度 L+8」= 68H(1) + L(4) + 68H(1) + CS(1) + 16H(1) "
            "—— 四条互证，不再需要「文档写错」来解释",
            "实现：`csg_uplink_wire` 引入 `Layout` + `candidates()/resolve_layout()/force_layout()` + `encode_frame()`，"
            "偏移全部由长度域形态推出（规范形态 APDU_OFFSET=14、MIN_FRAME_LEN=16）；"
            "切帧与解析**规范形态优先**，同时兼容历史异形形态（单个 2 字节小端 L、FT1.2 双同值单字节，整帧 L+6），"
            "`last_meta[\"len_form\"]` 给出实际形态，校验器对兼容形态给 WARN；"
            "解析新增「长度L重复段」行，两段不一致时标 ⚠ 且 valid=False（条文解释：此帧无效）",
            "组帧（`build_frame` / 组帧页）统一输出规范 4 字节形态；预设库 `CSG_UPLINK_command.json` 6 条按新形态重生成"
            "（CS 不变 —— CS 只覆盖控制域+地址域+应用层）；`test/test_csg_uplink.py` 63 → **90 项**全绿"
            "（新增三种长度域形态、混合流切帧、两段不一致等断言）",
            "文档同步：AGENTS §5.11（写入长度域证据链与容错口径）、`csg_uplink_wire`/`csg_uplink_parser`/"
            "`csg_uplink_validator` 头注释、协议14 输入示例帧、`reflex_web/web_utils` 注释",
        ],
    ),
    (
        "1.23.68",
        "2026-10-10",
        [
            "**新增协议14 南网上行通信规约（Q/CSG 11109004-2013，计量自动化终端上行通信规约）**："
            "帧格式 `68H + L(2B 小端) + 68H + C(1B) + A(7B) + 应用层 + CS + 16H`（5.1.1 图2），"
            "应用层 `AFN + SEQ + 信息体(DA2B+DI4B+内容)` 与可选 PW(16B)/Tp(5B)。"
            "新增 `csg_uplink_wire`（线格式单源，兼容 2 字节小端与 FT1.2 双同值两种长度形态）、"
            "`csg_uplink_di`（附 A/B/D/E 数据标识索引，由 PDF 经 pdfplumber 抽取 + 附 C 复用 DL/T645 DI）、"
            "`csg_uplink_parser`（链路层/控制域/地址域/AFN/SEQ/信息体全解）、"
            "`csg_uplink_frame_gen` + `csg_uplink_frame_gen_widget`（组帧页：地址域/控制域/AFN/信息体表格）、"
            "`validator/csg_uplink_validator`；注册表 index 14、extract=csg_uplink、查询页「DI 查询」、"
            "预设库 `CSG_UPLINK_command.json`（6 条种子）、Web（reflex）解析/查询/提取同源接入；"
            "`test/test_csg_uplink.py` 63 项全绿",
            "**协议14 文档缺陷显式兜底（不臆造）**：5.1.2 同时给出「L 为 2 字节（图3 D15..D0 / 网络上限 16383）」"
            "与 FT1.2 的「两个重复的长度 L 必需完全一致」两条互斥说法——实现以 2 字节小端为准，"
            "切帧同时兼容 FT1.2 形态；文档「每帧字符数 = L+8」与结构推出的 L+6 不符，按结构实现并在模块头注明",
            "**协议13（依瓦定制645）收尾**：补 `南网协议解析工具.spec` 的 `datas`（YW645_command.json）与 "
            "hiddenimports（yw645_parser/wire/di/frame_gen/frame_gen_widget/validator）；"
            "`release_check.CORE_TESTS` 纳入 6 个 yw645 测试",
            "文档同步：AGENTS §1/§3/§5、README 协议表、CLAUDE.md、`reflex_web/landing_web.PROTOCOLS` 追加协议14行",
        ],
    ),
    (
        "1.23.67",
        "2026-10-08",
        [
            "**修复协议9（南网新一代载波）信标帧 0x10 代理角色条目的代理站点 TEI 解析错误**（用户报障：现场信标帧的代理角色 TEI 解析不对）。表72 规定：代理角色条目长度字段之后是**连续 12 比特**的代理节点 TEI 位流 —— 节点1TEI = 字节3 bits0-7 + 字节4 bits0-3，节点2TEI = 字节4 bits4-7 + 字节5 bits0-7 ……；条目里**没有**独立计数字段，站点个数由条目长度推出（偶数个时 12N 比特恰好整字节，奇数个时末尾补 4 比特保留位）。旧实现按「每 2 字节一个 TEI」切、并把 `内容字节数//2` 当站点数 ⇒ 现场帧 `10 06 00 01 70 00`（条目长度 6 = 2 字节长度字段，内容 3 字节 = **2 个** 12 比特 TEI）只输出「代理站点数: 1 / 代理[0]TEI = 1」，第 2 个 TEI（字节4 高4位 0x7 + 字节5 0x00）被整段丢掉；实机其他 0x10 条目（如 `10 04 60 00` ⇒ 内容 2 字节 = 1 个 TEI + 4 比特保留）碰巧对，所以缺陷长期潜伏",
            "修复：`csg_new_gen_parser._parse_beacon_entry_detail` 的 0x10 分支改为按 12 比特连续位流解包（复用 `_extract_bits`，LSB 优先，与表61 站点TEI、0x0E 精简条目同一约定）——站点数 = `内容比特数 // 12`，每个 TEI 单独一行并给出**跨半字节**的字节范围（如 TEI2 落在内容字节 1~2）；末尾不足 12 比特时新增「条目尾保留位」行（表72 对奇数个代理站点的 4 比特保留位）。现场帧修复后为「代理站点数: 2 / 代理[0]TEI = 1 / 代理[1]TEI = 7」",
            "回归：`test/test_csg_new_gen.py` 新增用户实帧用例（114 字节，逐条目长度 22/34/4/10/6/31 与 6 条条目链不变、TEI = 1/7、字节高亮 96-97 与 97-98、偶数个站点时无尾保留位行），既有 1 个代理站点帧（`10 04 60 00` ⇒ TEI=96）断言保留并补「条目尾保留位 = 4bit」；变异反证：旧实现（`ln//2` + 步长 2）实测只输出 `['代理[0]TEI=1']`、站点数 1，新断言必红",
        ],
    ),
    (
        "1.23.66",
        "2026-09-30",
        [
            "**批量解析工具栏合并成两行**：「CLI 预处理」与「Python 脚本」原是上下两行，纵向白占一行；现合并进**同一个 `FlowLayout`**（两组之间加竖线），1366×768 与 1920 下都排成**一行**（工具栏区段 104px → 52px；实测窗口 ≥ 1264px 两行各自一行，1230~1263px 只有合并行折、更窄两行都折）。合并的关键不在 FlowLayout，而在**把占大头的导出按钮挪出这一行**：第一版把 4 个导出按钮留在合并行里，单行需 ~1700px，1366 下照样折成两行 —— 等于白合并。现导出按钮移到核心操作行右端（仍在工具栏右上角），解析进度条与「取消」移到状态栏（只在解析中出现，放状态栏既不挤按钮也不额外占行）",
            "两行都用 `FlowLayout` 而不是 `QHBoxLayout`：宽度够就一行，窄窗 / 高DPI 下**自动折行**退回原来多行的样子，既拿到合并收益，又不重演早期「单行流式布局把按钮挤到重叠」（那正是当年拆成三行的原因）；窄到 900px 仍逐项折行、零重叠",
            "`FlowLayout` 新增**可选的 stretch 权重**（`addWidget(w, stretch)` / `addStretch()`，默认关闭 ⇒ 顶部协议组行为不变）：宽屏把行内剩余宽度按权重分给两个下拉框（命令框 2 : 脚本框 1），弹性空隙把「共 N 帧」徽章顶到行右端。**拉伸只改宽度，必须把同行后续项的 x 一起右移** —— 否则变宽的下拉框会盖住后面的按钮（首版就踩了这个）",
            "**命令框占位符必须短**：可编辑 `QComboBox` 的 `sizeHint()` 会把 `placeholderText` 算进宽度（实测那条 40 字符长示例 → 481px，比最长的一条命令还宽），足以把合并行顶到折行；改成短示例后 371 → 250px，完整语法仍由 tooltip 与「帮助」承担。也不再给下拉框设 `maximumWidth` 上限 —— 那会把宽屏的剩余宽度全浪费掉，改用上面的权重分配",
            "`test/test_batch_toolbar_layout.py` 扩到 **59 项**（offscreen）：工具栏只剩两行、**1366 基准宽度下两行各自一行**（这才是「省下一行」的判据）、宽窗真一行且下拉框吃掉剩余宽度、帧计数徽章贴行右端、进度条/取消在状态栏、**2560→760 共 13 个宽度下两行零重叠**、命令框 `sizeHint` 不得失控。测试踩坑保留：跨 `QTabWidget` 页面**不能用 `mapTo(win)`** 判行（offscreen 下会给出 x=2563 这种离谱坐标），行数要用 `layout.itemAt(i).geometry()` 并按**容差聚类**（同行各项高度不同，`top()` 会差 55/57/61 几像素，直接 `set()` 会误判成 3 行）；`QLabel` 是 `QFrame` 子类，数分割线必须用精确类型",
        ],
    ),
    (
        "1.23.65",
        "2026-09-30",
        [
            "**协议9 组帧页新增「⓪ 仿照报文 / 模板」——照着别人的帧改，不用从零填表**：从官方测试系统拷一帧报文粘进来 → 自动反解并把**各层参数填成默认值** → 只改需要变的字段再生成；参数集可命名保存到本地，下次「加载模板 → 改关键字段 → 出新帧」",
            "**反解分层**：ED..EE 封装（PLC2.0 / 广西台体两种公共头）→ 整帧 MPDU → ①FC ②物理块 ③MAC 头 ④MSDU → 应用层帧 → 测试帧 BDU（表61 原有扩展 / 2.0 测试扩展）。**24 个测试模式全部可反解**：模式下拉与模式参数逐项还原（表61 的模式号取高 4 位，2.0 扩展按扩展 ID 分派，A 组取测试数据区频段）",
            "**回填后立刻用同一套参数重建一次，并与原帧逐字节对比**：一致才提示「与粘贴的报文完全一致，可放心微调」；表单表达不了的字段（如报文标识符非 0x0101、业务标识非 0xF0）会按「**手工 HEX 保真**」兜底并明确告知「此时改应用层/模式参数不影响载荷」。另给「对比当前输出」按钮，随时报告首个不一致的字节偏移",
            "**模板本地存储** `csg_frame_templates.json`（应用数据目录，已加 .gitignore）：存**完整参数集 + 原始参考报文 + 状态摘要**；下拉加载 / 保存为模板 / 删除，写入用「临时文件 + os.replace」原子替换，坏文件宽容（非 JSON 也不影响页面打开）",
            "**修复：32bit 字段装不进 QSpinBox** —— ED 时间戳是真实 Unix 秒量级（`0x68xxxxxx` > `0x7FFFFFFF`），此前上限被夹到 `0x7FFFFFFF` 既填不进真实时间戳、回填时 `setValue` 还直接抛 `OverflowError`；信标时间戳 / 信标周期同理。新增宽整数文本框 `_WideIntEdit`（接受十进制或 `0x` 十六进制），并把所有回填赋值统一收敛到「先夹到控件范围再 setValue」",
            "**右栏新增「显示响应解析」开关**：协议9 是纯组帧场景，响应帧解析默认收起，把高度让给「实时解析预览」；其它协议保持现状（仍默认显示），勾选状态记住用户偏好 —— 协议9 只是强制收起，随时可勾回来",
            "新增 `test/test_csg_frame_reverse.py`（**96 项**，纯逻辑：层次识别 / 24 模式全量反解 / 三型定界符 / 两种 ED 公共头 / 32bit 字段 / 错误路径 / **变异反证**）与 `test/test_csg_frame_templates.py`（**92 项**：存档往返 / 同名覆盖 / 名称校验 / 坏文件宽容 / 原子写 / 上限）；`test/test_csg_frame_gen_gui.py` 扩到 **139 项**（新增仿照回填、保真兜底、模板存取、响应解析开关等用例）",
        ],
    ),
    (
        "1.23.64",
        "2026-09-30",
        [
            "**协议9（南网新一代载波）接入「协议组帧」页**：此前该页只对 0/6/7/8/12 显示（注册表 `frame_gen_mode`），协议9 的组帧控件（`csg_test_frame_gen_widget.py` + `csg_new_gen_frame_gen.py` + `csg_link_frame_gen.py`）在仓库里存在却**没有接到 GUI**。现按 `frame_gen_mode=\"csg\"` 接线：组帧页左栏做成 `QStackedWidget`（第 0 页=常规动态表单 / 第 1 页=协议9 链路层组帧），协议9 下隐藏 DI/AFN/字段模式/EB 各区与「添加到预设」",
            "**五层折叠组帧表单**：①FC 帧控制（定界符/接入指示/SNID/源TEI·目的TEI/帧长/符号数/BPLC 或 ISAC 专属字段）｜②物理块 PBH+PBCS｜③MAC 帧头（发送序号/跳数/发送类型/MSDU 序号/CRC-32）｜④MSDU（VLAN/MSDU 头/手工载荷）｜⑤ED 封装（PLC2.0 与广西台体两种包装、CS、物理信道、时间戳、物理块个数/长度）。进页面默认勾选「组装链路层」，默认帧类型 **SOF 帧**",
            "**优先实现 SOF 帧与各类测试模式帧**：定界符三型 —— SOF（BPLC / ISAC-PLC 两版本、长/短 MAC 头、多物理块）、信标帧（FC 后直接载荷）、选择确认帧 SACK（仅 FC 16 字节）；**24 个测试模式全部**能组出带链路层、且 FCCS / PBCS / CRC-32 三处「校验通过」的 MPDU（用 `CSGNewGenParser` 的 `parse_level=\"auto\"` 回读反证，含接入指示=1 与 MAC 头原始 TEI = FC 源/目的 TEI 的语义不变量）",
            "**修复：切到信标帧组帧按钮直接崩** —— 信标时间戳/周期是 32bit 字段（`maximum=0xFFFFFFFF`），`QSpinBox.setRange` 抛 `OverflowError` 打断 `_rebuild_fc_fields`，表现为「FC 区还是 SOF 的样子、输出也仍是上一帧类型的 MPDU」。改为先夹到 C++ int 上限 `0x7FFFFFFF` 再设（32bit 字段自动切十六进制显示）",
            "**修复：信标帧无法组帧**（`载波映射表索引 超出 4bit 范围：16`）—— `build_link_frame` 里先按 `cfg.std_version` 反查了一次载波映射表索引（ISAC 下 136 字节 → TMI 16），使 `cmt_index` 不再是 `None`，`_ensure_cmt_index` 的「信标按 BPLC 语义反查（136→4 / 520→8）」特例被跳过，随后 `_fill_fc_beacon` 往 4bit 字段写 16。现统一只由 `build_fc → _ensure_cmt_index` 解析",
            "**修复：SACK / 信标的实时预览整块空掉** —— `FrameBuildResult.hex()` 里 `mac_frame` 写成 `mac_header + msdu`，而 SACK 两者皆 `None`、信标只有 `msdu` ⇒ `TypeError` 打断 `parse_rows`（该 dict 是**无条件求值**的，任何 `hex(层)` 调用都会踩到）。改为 None 安全拼接；确实没有 MAC 帧时抛可读的 `FrameBuildError` 而不是 `TypeError`",
            "**预设命令页可见性由 `frame_gen_mode` 改为按 `preset_mode` 判定**：协议9 有组帧页但没有预设库，按原判据会多出一个**空的**预设页，且组帧页的「添加到预设」会经 `preset_buttons._get_path` 的兜底分支把协议9 的帧写进 `GW_command.json`。协议9 下该按钮改为隐藏并带提示；0/6/7/8/12（有预设库）行为不变",
            "新增 `test/test_csg_frame_gen_gui.py`（**71 项**，offscreen）：走真实 GUI 路径（`main_gui` → `FrameGenWidget` → `CsgTestFrameGenWidget` → `csg_link_frame_gen` → 解析器回读），覆盖页签可见性、五层折叠结构、SOF/信标/SACK 三型闭环、24 模式全量、输出层次四档、折叠状态收集/恢复、配置快照往返、协议切换回退、按钮不裁字（`show()` 之后按 `sizeHint` 量，陷阱 63）。另把 `test/test_csg_link_frame_gen.py`（176 项）与 `test/test_collapsible_section.py`（51 项）一并登记进 `release_check.py`（前者进 `CORE_TESTS`，后两者进 `GUI_TESTS`）",
        ],
    ),
    (
        "1.23.63",
        "2026-09-29",
        [
            "**修复协议8（698.45）A-XDR 数据域字节序错误**：APDU 内的 A-XDR 数据域原按**小端**解码/编码，而标准规定 APDU 编码规则为 A-XDR（DL/T 790.6—2010）⇒ 多字节**大端**。现场实测帧 `… 05 FF FF 9E D0 …`（OAD `20 04 02 01` = 有功功率分相数值组）本工具原解析 `-794886145`（小端 `0xD09EFFFF`），现修正为 **-24880**（大端 `0xFFFF9ED0`），与官方工具一致。修正范围：整型（long / long-unsigned / double-long / double-long-unsigned / long64 / long64-unsigned）、浮点（float32 / float64）、`date_time` / `date` 的年与毫秒、OI/OAD/OMD 的 OI、TI 间隔值；**解码与编码两侧同步**（组帧↔解析自洽）",
            "**链路层保持小端不变**（长度域 `L`(2B)、HCS(2B)、FCS(2B)、地址域反转）—— 依据协议文档 L347（链路层「低字节在前，高字节在后」）与 §7.1（APDU 编码规则遵循 A-XDR）；两层字节序**不可互相套用**，不得「一刀切」",
            "**顺带修复 LINK 预连接不带 tag**：`_parse_link_request` / `_parse_link_response`（标准表38/39）原把请求类型 / 结果 / 心跳周期 / 时间标签当作**带 tag** 的 A-XDR 元素解，导致标准附录 H.1.1 示例直接解析失败；按 SEQUENCE 内定长字段不带 tag 规则改为定长切分（与协议12「陷阱 61」同一条规则）。修正后附录 H.1.1 登录请求解析出 请求类型=登录 / 心跳周期=180s / 时间=2016-05-19 08:05:00.164",
            "**组帧侧同步**：`dl_t698_45_frame_gen.py` / `dl_t698_45_frame_schema.py` 的心跳周期、客户机 APDU 最大长度、期望帧最大帧长、期望超时时间等 2 字节字段改大端（`>H`）；链路层长度域与 FCS 仍为小端",
            "**依据（oracle，可复查）**：协议文档 **附录 H.1.1「登录」**逐字节示例 —— `00 B4`=心跳周期 **180s**、`07 E0`=**2016** 年、`00 A4`=**164**ms、`02 5F`=607ms、`02 DA`=730ms。新增 `test/test_dl_t698_45_endian.py`（48 项：H.1.1 请求/响应双 oracle + 实测帧 -24880 + 8 整型 2 浮点编解码往返 + 链路层小端回归）；`test_dl_t698_45.py` / `test_dl_t698_45_data_decode.py` 中原按**错误小端**写死的期望值同步重写",
        ],
    ),
    (
        "1.23.62",
        "2026-09-29",
        [
            "**报文工具补齐「HEX → 数值」方向**（对称 1.23.60 的「数值 → HEX」）：同一分组框、同一类型下拉（698.45/A-XDR 12 种基础类型），输入 HEX 后**同时**给出大端解析值与小端解析值；浮点类型按 IEEE 754 直接给数值（`3F C0 00 00` → 1.5），有符号/无符号按类型位宽判定（`FF FF 9E D0` 作 double-long → 大端 **-24880**、小端 -794886145）",
            "与编码器**严格互逆**（同类型下『解码(编码(x)) == x』）：编码产出的大端 HEX 解出的大端列、小端 HEX 解出的小端列都回到原值；测试对 12 类型 × 边界值逐项断言，并保留两侧一致的文档锚点（`FF FF 9E D0` = -24880 即 `dl_t698_45_axdr` 文件头记录的 A-XDR 大端判据；`07 E0` = 2016 见附录 H.1.1）",
            "HEX 解析容忍空格/逗号/分号/冒号/顿号/斜杠/竖线/连字符与 `0x` 前缀（连续写法 `FFFF9ED0` 同样可解析）；**字节数必须与所选类型一致** —— 空输入/非 HEX 字符/奇数位/字节数不符一律给可读中文原因且不覆盖上次输出（不静默截断）",
            "`test/test_message_tool_numeric.py` 由 278 项扩到 **469 项**（新增 [6] 互逆与文档锚点 / [7] HEX 错误路径 / [8] GUI 对称方向：新按钮真实点击、回车接线、字节数不符提示、HEX 输入框 `visibleRegion` 与按钮不裁字）；**变异反证 3 条**（大小端互换 / 有符号位丢失 / 去掉字节数守卫）分别实测 **20 / 13 / 21** 项变红，还原后逐字节一致",
        ],
    ),
    (
        "1.23.61",
        "2026-09-28",
        [
            "**修复协议8（698.45）批量解析「一帧都提取不出」（P0）**：`_extract_69845_frames` 把整帧长当成 `L + 4`。DL/T 698.45-2017 §6.2.2 a) 定义长度域 L 为「传输帧中**不包含**起始字符和结束字符的数据长度」（L 本身含两个长度域字节）⇒ **整帧 = L + 2**。多算 2 字节后末字节自证（=16H）必然失败 ⇒ 提取器恒返回空，用户只看到「预处理后未保留有效报文内容！」。三处实现（桌面 `main_gui`、共享 `batch_core`、Web `reflex_web.web_utils`）同源修复",
            "**同一根因修复串口工具 698 分帧**：原判据要求「第 4 字节是第二个 68H」且用 `L + 3`。真实 698.45 链路帧是 `68 | L(2B 小端) | 控制域 | … | FCS | 16`，**没有第二个 68H**，两处错误叠加使协议8 的分帧策略**恒不命中** → 选「协议8」时退化为时间聚合（低波特率/拆包时一帧会被切成多行）。现按 `L + 2` 取整帧长，并把 698 / 645 / 南网·国网 的互斥判据从**头部签名**改为**末字节自证**（南网/国网 L = 整帧、末字节恒为 16H，故「按 L 到齐却不是 16H」即否定南网口径、改判 698 的 `L + 2`；反向：`dlt698_45` 遇末字节自证为南网的输入同样返回 0）",
            "**依据（三条独立实证）**：① 协议文档 6.2.2 a) 对 L 的定义；② 标准附录 H.1.1「登录」逐字节示例（**32 字节、L=0x001E=30**）；③ 现场实测 **33 字节**帧（L=31）经解析器 HCS/FCS **双通过**，证明字节布局就是 `L + 2`",
            "新增 `test/test_dl_t698_45_extract.py`（46 项：帧长公式的协议依据 / 桌面·共享·Web 三处提取器同源对拍（单帧·附录示例·多帧拼接·前置噪声·末字节不符·尾部缺 1 字节·长度域偏小）/ 桌面 `_extract_frames_for_protocol(…, 8)` 与共享三元组端到端 / 串口 `frame_length_for`·`declared_frame_len` 与「不误判南网·645」/ 串口接收端到端逐字节交付两帧 / 错误公式反例），已登记 `release_check.py` 门禁；**变异反证 3 条**（桌面 `+2→+4`、串口策略 `+2→+3`、`declared_frame_len` `+2→+3`）分别实测 **6 / 5 / 3** 项变红，还原后逐字节一致",
            "同批把既有测试里按错误公式构造的『698 帧』夹具（`68 L L 68` 的 20 字节假帧 —— 真实 698.45 无此形态，正是缺陷长期潜伏的原因）换成现场实测帧与附录 H.1.1 示例；`test_serial_proto_frame.py` / `test_serial_tool_widget.py` 同步更新",
        ],
    ),
    (
        "1.23.60",
        "2026-09-28",
        [
            "**报文工具新增「数值 → HEX（大端/小端）」转换**：先选基础数据类型，再输入十进制值，一次给出**大端**与**小端**两种字节序的 HEX 字节串。类型取自 DL/T 790.6-2010（698.45 APDU 的 A-XDR）中可用十进制表述的 12 种：bool / integer / unsigned / enum / long / long-unsigned / double-long / double-long-unsigned / long64 / long64-unsigned / float32 / float64 —— 沿用协议 8 既有词汇，不另造第二套类型名",
            "类型自带字节宽度与取值范围：超范围、非十进制、bool 非 0/1、float 的 NaN/inf/超出 float32 范围均给出**可读中文原因**（不静默出错），且不覆盖上一次输出；空白板一键「清空」沿用既有按钮",
            "编码器为**模块级纯逻辑**（`NUMERIC_TYPES` / `NUMERIC_TYPE_SPECS` / `encode_numeric_value`，零 Qt、可脱离 GUI 单测）；下拉项与规格表同源，测试断言无哑条目、无重名覆盖",
            "字节宽度/符号性与 `dl_t698_45_axdr.AXDRCoder` 的各 `_decode_*` **一一对应**，由「编码 → 698.45 A-XDR 解码」往返 oracle 验证（解析值、原始值、消耗字节数三查）；并钉住协议文档锚点：`2016`→`07 E0`、`180`→`00 B4`、`164`→`00 A4`（附录 H.1.1）与 `-24880`→`FF FF 9E D0`（A-XDR 大端判据，`dl_t698_45_axdr` 文件头记录的历史修复实例）",
            "新增 `test/test_message_tool_numeric.py`（278 项：类型表与解码器一致性 / 往返 oracle / 文档锚点 / 各类型 min·max 与 ±1 边界 / 错误路径中文原因 / offscreen GUI 真实点击与 returnPressed 接线 · 错误路径不覆盖输出 / 下拉与输入框 `visibleRegion` 非空 · 按钮 `width >= sizeHint` 不裁字），已登记 `release_check.py` 门禁；**变异反证 1 条**（把「小端 = 大端逆序」改成直通）实测 12 项变红",
        ],
    ),
    (
        "1.23.59",
        "2026-09-23",
        [
            "**TCP 监控新增「记录位置」能力**（现场：记录下来的 CSV 找不到、也不知道去哪找）：工具栏新增「打开位置」按钮——一键在资源管理器中**定位并选中当前记录文件**（无记录文件时打开记录目录）；新增「记录目录」菜单（选择记录目录… / 打开记录目录 / 恢复默认目录），目录可自选并**记住**（`tcp_monitor_config.json`，重启仍生效）；状态栏记录名悬停给出完整路径",
            "记录目录解析收敛到**单一来源**：`record_dir()` = 用户配置优先，否则 `<数据目录>/Output`（与串口工具日志目录同一约定）；`_start_csv_recording` 不再硬编码 `app_data_dir()/Output`，故测试沙箱能真正拦住（不再往开发机真实数据目录写文件）",
            "**顺带修复既有缺陷**：`monitor/tcp_monitor.py` 从未导入 `QFileDialog`，「加载记录」按钮一点即抛 `NameError`（自 TCP 监控 UI 引入以来潜伏——测试从未点过该按钮）；文件对话框起始目录同时改为当前记录目录",
            "新增纯逻辑层（可脱离 GUI 单测）：`default_record_dir` / `load_record_config`（缺失/损坏/非对象/BOM 均回落空配置）/ `save_record_config`（原子写 + 失败返回 False）/ `resolve_record_dir` / `open_in_file_manager`（Windows `explorer /select` 定位文件，非 Windows 回落 `xdg-open`）",
            "`gui_utils._STANDARD_ICON_MAP` 新增 `folder` 键（`SP_DirIcon`）——`set_btn_icon` 对未知键**静默跳过**（同「分享此帧」曾无图标的同类坑），故新按钮必须用合法键，并由测试断言图标非空",
            "新增 `test/test_tcp_monitor_record_dir.py`（61 项：纯函数矩阵 / 目录可配与持久化 / 记录落盘位置 / 定位文件 / 异常与保存失败不静默 / `QFileDialog` 回归 / 图标键与路径单一来源静态守卫），已登记 `release_check.py` 门禁；**变异反证 5 条**（退回硬编码目录、忽略用户配置、去掉 `QFileDialog` 导入、不再定位文件、图标键改非法）均实测变红",
            "**修复「应用层帧」工具栏 4 个按钮文字被裁**（现场截图：「记录目录」只显示成「记录目」）：根因是这 4 个按钮写死 `setFixedWidth(80)`，而 QSS 主题下它们的 `sizeHint().width()` 已是 **92px**（带菜单下拉箭头的「记录目录」**104px**）⇒ **默认字号就裁字**；字号可配置（7 套主题 × 任意字号），12 / 14 号时更需 104 / 116~128px。真正裁字的是**上限**（`setFixedWidth` 同时钉 min 与 max，而 QSS 的 `min-width` 又把 min 覆盖回去，只剩 max 生效）。现统一改走新增的 `gui_utils.fit_btn_width(...)`：取组内最宽者的 `sizeHint` 作为 `minimumWidth`（**只设下限不设上限**）——字号变大时 `sizeHint` 继续增长仍被布局满足，故切主题/改字号后**无需重算**，同时保持一行按钮等宽",
            "**同一根因的第二处（在线监控器筛选栏）**：`monitor_widget.py` 的「帧类型 / MSDU类型」按钮写死 100 / 120px，默认 10 号字下只要单选「选择确认帧(SACK)」就显示成「选择确认帧(」（需 103px）。这类按钮**文案会变**，单按当前文案取下限不够 ⇒ 新增 `gui_utils.fit_btn_width_for_texts(btn, 候选文案全集)`（按全集最宽值取下限，量完恢复原文案；`QAbstractButton.setText` 不发信号故无副作用）；候选文案与运行时文案**共用** `monitor_widget._short_label`（截断长度 `_BTN_TEXT_MAX` 单一来源，防两处漂移）；「浏览」按钮（文案固定）改走 `fit_btn_width`——它原先 `setFixedWidth(60)` 与 QSS 的 `min-width` 冲突成 `min 68 > max 60`",
            "新增 `test/test_btn_width_fit.py`（66 项：两个取宽函数的纯逻辑（含「未设上限 = 没写死」「不静默降掉既有更大下限」断言）/ 真机布局 10·12·14 号字下 4 个按钮不裁字且等宽 + 下限不依赖布局余量 / **反例自检**（改回 `setFixedWidth(80)` 后判据必红）/ 动态文案按钮走**真实勾选动作** / 运行中切字号·切主题（不重建控件）/ AST 静态守卫并自带正负样例），已登记 `release_check.py` 门禁",
            "**真机取证**：用真实窗口渲染工具栏后 OCR —— 修复前只读出「记录目」、修复后完整读出「记录目录」；主窗口全量扫描 170 个可见按钮**零裁字**（动态文案按钮不在静态扫描范围内，故另立用例）；主窗口在**最小尺寸 1000×700** 下切 TCP 监控页，10 / 14 / 16 / 24 号字实测按钮均不裁字（24 号字需 168px、实得 180px）⇒ **无需**改 FlowLayout 折行。约定沉淀为 §8 陷阱 63",
        ],
    ),
    (
        "1.23.58",
        "2026-09-23",
        [
            "**协议12 A-XDR 编码层重写（正确性修复）**：原实现把「小端 + BER 长度域」套到 A-XDR 上，导致 APDU 内所有多字节字段错位。协议12 文档通篇**没有示例帧**，故改用同族标准 DL/T 698.45 附录 H.1.1「登录」真实编码实例推导——`07 E0`=2016 年、`00 B4`=180s、`00 A4`=164ms 证明 **A-XDR 多字节为大端**；且**定长类型在 SEQUENCE 内不带 tag、不带长度域**（date_time 连自身标记 0x19 都没有）。链路层 L/C/FCS 仍为小端，两层不再互相套用",
            "新增 `modular_iface_axdr.py`（A-XDR 编解码**单源**：表4 全部类型、8 类 APDU、date_time/date/time/date_time_s/Scaler_Unit/bit-string/数组/结构、附录 A `fcstab` 与 `calc_fcs`、`frame_layout`、`verify_frame`）与 `modular_iface_data.py`（静态表**单源**：附录 B/C/D~L/M 与表1/2/3/5/11/13）",
            "编码假设集中到一处：`AXDR_TAG_IN_SEQUENCE=False` / `AXDR_LEN_FOR_FIXED_IN_CHOICE=False` / `AXDR_VAR_LENGTH_BYTES=1`，并新增 `verify_frame(frame)[\"axdr_tail\"]` 作为**判据**——拿到真实帧先跑它，非 0 就把 3 个开关的 8 种组合枚举一遍（实测依据写进注释）",
            "修正既有错表：`DAR_NAMES` 由 21 项（形似其它协议）收口到表11 的 **4 个值**（0 成功 / 1 拒绝读写 / 2 信息类未定义 / 255 其它）；DT 位段由 5+3+8 改为 **4+4+8**（与附录 G/J/K/L 的 4000/7100/8000/9000 及 §7.3~§7.11 自洽；表22 按 5 位会与附录冲突，已记录待真实帧定论）",
            "删除 `_take_axdr_uint` / `_take_axdr_string`（「探测式 + 取不到静默返回 0」会让真实帧字段无声消失），改为严格解码 + 失败时的 ⚠ 行；新增 Scaler_Unit（表12）解码，单位名取自附录 M",
            "`parse()` 收尾的 `self._rows(rows, {...} if False else None)` **死代码**修复：meta 现如实给出 `valid`/`fcs_ok`/`structure_ok`/`axdr_tail`/`errors` 等",
            "批量摘要/类型列补协议12 专属分支（此前落薜底分支）：`_get_summary_from_table_data` 输出「方向 | 控制码 | 信息类:… | APDU 名」（信息类名走解析器同一个 `dt_name`，ACK/NAK 给可读结果）；`_get_frame_type_name` 输出 APDU 名/控制码名（不改就会落薜底 `name.split(\" \")[0]` → 类型列显示 `[12]`）",
            "测试：`test/test_modular_iface.py` 46 → **430 项**；新增 `test/test_modular_iface_axdr.py` **185 项**（含 698 附录 H.1.1/H.3.2 独立 oracle、附录 A `fcstab` 全表对拍 + crcmod 交叉验证、表4 逐条、越界/截断、`verify_frame`）",
            "组帧页模板下拉恢复「读取·协议版本」（GUI 预设表引用它）→ **13 个模板**；spec `hiddenimports` 补齐 `modular_iface_axdr` / `modular_iface_data`",
            "**遗留**：Web 端（`reflex_web/`）尚未支持协议12 的解析/查询/组帧（仅首页协议表有条目）；协议12 未接入虚拟表与 TCP 监控协议识别",
            "**新增协议12 导致既有测试硬编码「12 个协议」变红**（`test_window_state` / `test_serial_tool_widget` / `test_serial_proto_frame` 共 6 项）：改为与 `protocol_registry.combo_labels()` 同源比对，以后再增协议不必逐个改数字",
            "**串口工具 `ft12_68` 签名排除恢复**（`test_serial_proto_frame` 2 项变红）：1.23.57 为修「首片过短把整帧切碎」把签名排除**整个去掉了**，连带丢掉了「指定南网/国网时不得把 698.45/645 帧按南网口径切」的契约。现改为**字节够判时才排除**（`len(buf) >= 8` 时排除第 4/第 8 字节为 68H 的 698.45 / 645 结构），两个契约同时成立",
            "**修复协议11 类型列潜伏红测试**（9e60ba6 / 1.23.17 起）：无 FC 的应用层业务帧曾把**「报文ID」行的说明列**（“安全模式: 明文传输, 业务ID: 0x030”）当成类型名。改为优先复用 `gw_app_biz_summary` 取业务名（如「开始升级」），取不到再退回 MSDU类型/报文ID 的解析值；`main_gui` 与 `batch_core` 两份 `get_frame_type_name` 同步同口径（TCP 监控走后者），测试断言由语义不明的「[11]」改为业务名精确相等",
            "**EXE 发版编译**：`dist/南网协议解析工具_v1.23.58_20260923154846.exe`（98.0 MB，FileVersion/ProductVersion=1.23.58.0）",
        ],
    ),
    (
        "1.23.57",
        "2026-09-22",
        [
            "串口工具 RX 按发送协议断帧修复（用户报障：国网 F112 响应被拆成 4 条 `[RX]`，未按协议组帧一帧一行输出）",
            "根因：首片只有 1 字节 `68` 时长度域未收齐，`frame_length_for` 返回 0，`_frame_incomplete` 误判「非协议帧」→ 走 10ms 静默窗口单独刷出首片；后续缓冲不再以 68 开头 → 整帧碎裂",
            "修：头标志已出现但长度域/签名特征未收够 → 一律按**未收全**等待（`FRAME_IDLE_MS`/`FRAME_HOLD_MAX_MS`）；协议已知时 `ft12_68` **3 字节即可算整帧长**（不再等满 8 字节做签名排除）",
            "回归：`test_serial_tool_widget.py` 新增复现用例（1+22+9+21 四块、块间隔>10ms → 只输出 1 行 53 字节整帧），全套 470 项通过",
            "国网 F112 芯片 ID 解析修复：24 字节线上为整块小端，**先原样显示原始 24 字节**，再整体倒序后按表104 解析（类别/厂商/型号/序列号）；现场帧倒序后前 6 字节恰为表104 固定头 `01 02 9C 01 C1 FB`，类别 0x03=HPLC+HRF 双模",
            "串口工具命令表新增「次数」列（发送次数）：每条命令可单独设置本轮连发 N 次（默认 1，范围 1~9999）；双击行 → 编辑对话框「发送次数」修改；发送时按 N 展开进 messages，`index_map` 仍指回原命令下标；与底部「循环次数」（原全局发送次数，已改名避免混淆）相乘。旧配置无 `send_count` 键 → 1；导出/归一化统一补齐",
            "测试：test_serial_tool_widget.py 扩至 471 项（命令表 7 列含「次数」、header 断言、export 带 send_count）",
            "顶栏折叠后启动时协议名仍贴左（用户截图报障）：`showEvent` 在窗口显示后（及 150ms 延迟）按**最终标题栏宽度**重算居中填充；`_update_window_title` 用 `frameGeometry` 宽度、控件+应用两套字体度量；padding 算成负时放宽 chrome 预留再算一次。构造结束时再刷一次标题",
            "**新增协议12 模组化终端功能模块接口**（anydoc 转 MD：`协议文档/12.模组化功能协议/…接口协议.md`）：链路层 68+L(数据域长)+C+FCS+16、FCS=CRC-16/PPP(x-25)；APDU 8 类 CHOICE、DT 信息类标识；`modular_iface_parser` / `modular_iface_frame_gen` / `ModularIfaceValidator`；注册表 index12、extract=modular、查询页「信息类查询」；组帧库含模板",
            "测试：`test/test_modular_iface.py` 46 项；registry / landing 101 项对拍通过",
            "**协议12 模块信息 Data 深解**（GetResponse/Set/Report 的 Data 不再只显示 hex）：按附录C DT=0000 手走 A-XDR structure，展开 模块设备型号/模块设备ID/软件版本/软件发布日期/硬件版本/硬件发布日期/厂商编码（日期约定 `1A 05 + year LE(2)+month+day+week`，避开 698 AXDR `_decode_date` 长度偏差）；协议版本/电源状态同路径；测试扩至 54 项",
            "**协议12 组帧 GUI 接线**（此前 `frame_gen_mode=None` 只有纯逻辑库）：注册表 `frame_gen_mode=preset_mode=modular`，组帧页模板下拉（12 模板）+ DIR/PRM/FID/DT/Data 配置 + 实时解析预览 + 串口回包解析；预设页独立 `MODULAR_command.json` 种子 8 条；配置快照含 `modular` 段；spec 补 datas/hiddenimports",
        ],
    ),
    (
        "1.23.56",
        "2026-09-22",
        [
            "串口工具：**命令状态可手动清理**（实测诉求）—— 勾选操作行新增「清除状态」按钮，一键把所有命令的名称列状态图标重置为「待测」。原先状态只在**每轮发送开始时**自动重置，跑过一轮后想清干净只能再发一次。只清运行态图标，**不动命令内容与勾选**；发送中禁止清除（与「清除统计」同一口径 —— 那时状态还在被实时改写，清了也会立刻被填回来，徒增困惑）；按钮带 tooltip 说明，空命令表下点击安全无副作用",
            "测试：test_serial_tool_widget.py 扩至 463 项（新增第 [33] 段 15 项：按钮存在且带图标、**走真实按钮信号**点击后三态全部回「待测」且图标逐态校验变灰、tooltip 同步、命令内容/勾选/名称不被影响、`_status` 键被移除且导出里不残留、重复清除幂等、发送中点击不生效、停止后可清、空表不抛异常）",
        ],
    ),
    (
        "1.23.55",
        "2026-09-22",
        [
            "串口工具：**命令列表「名称」列用状态图标表示本轮结果**（实测诉求）：○ 灰 待测 / ↻ 蓝 发送中（已发出、等待响应匹配）/ ✓ 绿 通过（发送成功；启用匹配时表示已匹配上）/ ✗ 红 失败（响应超时未匹配）/ ⚠ 橙 错误（写串口失败）。图标取 lucide（`circle` / `loader` / `check-circle` / `x-circle` / `alert-triangle`）并用 `CompositionMode_SourceIn` **按状态上色**（`app_icons` 只出单色，故对渲染好的 pixmap 整体染色并保留 alpha），名称文字同色系、tooltip 写明状态；表格下方加**图例**（悬停有详细说明）。状态迁移：每轮发送开始全部回到「待测」→ 发出后「通过」或「发送中」→ 匹配成功「通过」/ 超时「失败」；`_on_send_failed` 把仍在等待的记为「错误」；停止/收尾时剩余待匹配记为「失败」",
            "串口工具：状态存命令的**运行时键 `_status`**（不进 `normalize_command`、不落盘、不导出 —— `export_commands` 统一剔除下划线开头的键，避免下次打开显示上一次的旧状态）；状态变化只**重画那一行的名称单元格**（`_refresh_cmd_row`），不整表重建，因此不打断选中与滚动位置；命令上下移/删除时状态随命令字典自然跟随",
            "测试：test_serial_tool_widget.py 扩至 448 项（新增第 [32] 段 30 项：五态图标非空且**逐态校验渲染出的像素颜色**（容差 3，实测上色正确）、未知状态回落「待测」、图标缓存、五态形状两两不同、表格名称列的图标/配色/tooltip/文字、状态机读回、六条迁移路径（发出→发送中、无需匹配→通过、匹配成功→通过、超时→失败、发送失败→错误、每轮重置）、`_status` 不落盘不导出、图例文案）",
        ],
    ),
    (
        "1.23.54",
        "2026-09-22",
        [
            "串口工具：**日志新增「自动保存到文件」**（实测诉求）。勾选「自动保存日志」即把日志**实时写入文件**，取消勾选即停止并写入统计尾；文件是**日志窗口内容的完整镜像**（同样受「显示发送 / 显示接收 / 显示解析」控制，不存在第二套过滤规则），但**不截断** —— 窗口只保留最近 10000 行，文件一直追加，适合现场跑完再离线复盘。每行带**毫秒时间戳**前缀（可关）、**写一行 flush 一次**（断电/崩溃也尽量保住已写内容）；文件头记录标题/开始时间/串口上下文，文件尾记录停止时间与收发、匹配统计。目录可选（默认数据目录下的 `Output/`，与监控器 CSV 一级）、可一键在资源管理器打开；另有「保存当前日志…」把窗口现有内容另存一份",
            "串口工具：写入点挂在 `_log()`（日志窗口的**唯一出口**）上 → 面板显示什么、文件里就是什么，避免出现「窗口有、文件没有」这类漂移。文件名精确到秒且**同名不覆盖**（同一秒内停止再开始 → `_1`/`_2` 递增，宁可多一个文件也不丢数据）；`LogFileWriter` 纯逻辑无 Qt（`_write` 同时捕 `OSError` 与 `ValueError` —— 句柄被外部关掉时 Python 抛的是 `ValueError` 而非 `OSError`），任何写失败都**不抛给调用方**：GUI 依据返回值明确提示原因（含 `error` 文本）并自动关闭自动保存，绝不静默丢日志",
            "串口工具：`cleanup()` 现会先把**残留日志队列**刷进日志窗口/文件，再写统计尾并关闭文件（旧版队列里的最后几帧与解析行会在退出时直接丢失）。勾选状态作为偏好持久化（`log_auto_save` / `log_dir` / `log_timestamp` 三个新参数，旧配置缺键 → 默认关闭，行为与旧版完全一致，故 `CONFIG_VERSION` 不动）",
            "测试：test_serial_tool_widget.py 扩至 418 项（新增第 [31] 段 59 项：时间戳/文件名/默认目录/同名递增/手写文件等纯函数、`LogFileWriter` 的文件头无前缀 + 逐物理行加前缀 + 写一行即落盘 + 同名不覆盖 + 打开失败/写失败不抛、Widget 级「勾选即建文件（且在沙箱内）」、「面板新增的每一行都在文件里」的镜像断言、「显示发送」关闭时文件同步不写、时间戳开关立即生效、统计尾真实计数、写失败自动关闭并提示且不递归、目录不可用时勾选回弹 + 弹窗、偏好持久化与重启自动开始保存、手动保存与 cleanup 残留队列不丢)",
        ],
    ),
    (
        "1.23.53",
        "2026-09-22",
        [
            "串口工具：**新增匹配方式「HEX 通配（XX=任意字节）」**（实测诉求）。用正则匹配二进制帧要写 `\\xNN` 转义、还要绕开「忽略大小写把 `\\x68` 也当 `0x48`」「`.` 不匹配 `0x0A`」两个坑，现场太别扭 —— 现在可以直接写 **HEX + `XX`**：`68 D0 XX XX XX XX`。**沿用「测试方案」的既有约定**（`test_plan_widget._match_frame`：HEX 模式逐字符走、遇 `XX` 跳过一个字节），`XX` 可嵌在连续串里（`68D0XXXX16` 也认），`??` 是等价别名，分隔符复用 HEX 容错那一套。语义为**包含式**（在累积接收数据里任意位置查找，跨交付块），另支持可选锚点：开头写 `^`、结尾写 `$`（`^68D0XX` / `XX16$` / `^…$` 全长）。命中日志给出**命中偏移**；失败诊断区分「模式比数据长」与「未匹配到」",
            "串口工具：匹配方式下拉从 6 项扩到 7 项；对话框按所选方式**动态切换占位符与说明**（HEX 通配给出 `XX`/`^`/`$` 写法；正则给出 `\\xNN` 与两个坑的提醒，并建议二进制帧改用 HEX 通配）；新增 `parse_hex_wildcard()` / `hex_wildcard_match()` / `match_offset()` 三个纯函数（`match_offset` 统一匹配入口并返回偏移，`contains` 也能报出位置）；`normalize_command` 对 `hex_wildcard` 只校验通配模式合法性（非法才降级，不会像旧正则那样被静默降级）",
            "测试：test_serial_tool_widget.py 扩至 356 项（新增第 [30] 段 HEX 通配 34 项：模式解析 / 连续串内嵌 XX / `??` 别名 / 反例、包含式与 `^`/`$` 锚点、`XX` 真的跳过而非通配位必须逐字节相等、`match_offset` 偏移、normalize 与展示、通配专用诊断、以及**用实测国网帧四块交付的端到端命中**）",
        ],
    ),
    (
        "1.23.52",
        "2026-09-22",
        [
            "串口工具：**命令列表新增「选择」勾选列 + 全选 / 全不选 / 反选，发送只发勾选的命令（按表内顺序）**（实测诉求「多条命令时可以选择需要发送的，而不是默认全部执行」）。勾选状态存命令的 `enabled` 字段（随配置落盘读回；**旧配置无该键 → 全选**，与旧版本「只能全部发送」等价）；`SerialSendWorker` 新增 `index_map`，把「筛选后的下标」映射回 `commands` 的原下标 —— 名称 / 协议 / 匹配规则都按原下标取，否则会张冠李戴；一条都没勾时明确提示而不启动；发送日志标明「N/M 条命令（已勾选）」。实测用 `QTest` **真鼠标点击**验证了勾选框在 `NoEditTriggers` 下仍能切换（只断言 flags 不够）",
            "串口工具：**修复「明明是对的却提示不是有效的 HEX」**（实测报障）。根因：`hex_str_to_bytes` 按「空格 / 半角逗号」切分后把每个片段当**一个字节**，于是**连续无分隔的 hex**（如 `6812004116`）会被整串转成一个越界整数 → 判为非法。现在容错：连续串按字节切、半角/全角逗号/顿号/分号/斜杠/竖线/连字符/全角空格都当分隔符、容忍 `0x` 前缀；仍拒绝「连续串字符数为奇数」与「含非 hex 字符」。另外新增 `hex_input_error()`，把「不是有效 HEX」换成**可读原因**（`含非 HEX 字符 'G'（第 6 个字符）` / `片段 '681200411' 的字符数为奇数（9 个）`），对话框与「开始发送」校验都带上原因 —— 与匹配诊断同一思路，现场能自查",
            "串口工具：**修复「正则表达式」匹配方式完全不工作**。旧实现把「预期响应」一律按 HEX 校验，正则文本必然非法 → 被 `normalize_command` 静默降级成「不匹配」、待匹配项根本不会入队，现场只会看到「超时未匹配」。现在：正则方式下「预期响应」按**正则文本**处理（`normalize_command` 只校验正则语法是否合法、空正则也降级；`_on_sent` 用 `encode('latin-1')` 而非 `hex_str_to_bytes`），日志里预期按 `正则 <文本>` 展示（**不用 repr**，避免 `68\\s*D0` 显示成 `'68\\\\s*D0'`），且不参与「预期 = 发送值」误填提示",
            "测试：test_serial_tool_widget.py 扩至 322 项（新增第 [1] 段 HEX 容错 10 项、第 [1b] 段失败原因 5 项、第 [28] 段勾选与「只发勾选项」（含真鼠标点击、index_map 不错位、落盘读回、编辑不改勾选）、第 [29] 段正则匹配方式端到端 13 项）",
        ],
    ),
    (
        "1.23.51",
        "2026-09-22",
        [
            "串口工具：**命令列表双击直接进入编辑窗口**（等价于选中该行后点「编辑」），并给表格加了「双击某一行可直接编辑该命令」的提示。实现上单独加了 `_on_cmd_double_clicked(row, col)` 而**不给 `_edit_command` 加位置参数** —— 按钮的 `clicked` 会带一个 bool 参数，加位置参数会被那个 `False` 当成行号（`False` → 第 0 行），属于必须避开的坑；处理函数先 `selectRow(row)` 让视觉选中与编辑目标一致，越界行号（空表/程序化调用）直接忽略",
            "测试：test_serial_tool_widget.py 扩至 265 项（新增第 [27] 段：双击任意列都能打开对应行的编辑框、走**真实 `cellDoubleClicked` 信号**验证连线、双击后选中行一致、越界行号安全忽略、取消编辑不改动命令）",
        ],
    ),
    (
        "1.23.50",
        "2026-09-22",
        [
            "串口工具：**修复响应匹配漏配**（实测报障「设置了匹配规则仍超时未匹配」）。根因：匹配原来按**串口单次交付的块**比对，而驱动会把一帧拆成多次交付（实测 208 字节的国网帧被拆成 77+92+36+3 四块）—— 于是「预期响应 = 整帧」永远不可能匹配上（也不受接收模式影响：匹配吃的是原始交付块，不是切好的帧）。改为按**累积接收缓冲**比对（`MATCH_BUFFER_MAX = 8192` 防无界），跨交付块也能命中；累积缓冲在**每次发送**时清空（一问一答的窗口重新开始）、队列清空时也清空，避免用上一次响应的字节误判本次；**「队首连续匹配」语义不变**（同一批数据仍可连续命中多项）",
            "串口工具：**匹配判决全部输出可比对的日志**（实测诉求「需要把匹配规则也输出日志，才能分析为何判决失败」）。发送时输出 `[匹配] #n 等待响应：包含(contains)，预期 = …`；命中输出 `[匹配✓] #n 匹配成功（方式，预期 = …）`；超时输出 5 行诊断 —— `[匹配✗] … 超时未匹配` + `匹配方式 = 完全相等(equals)` + `预期响应 = …` + `期间收到 = …（共 N 字节）` + `诊断 = <为什么没匹配上>`。新增纯函数 `match_failure_reason()`：按 6 种匹配方式分别说明差在哪（预期串未出现 / 长度不一致 / 首个不同字节偏移 / 结尾不符 / 正则未匹配 / 期间未收到任何数据），并能识别最常见的误填 —— **预期响应与发送数据完全相同**时直接点名。新增 `hex_preview()`（超长 HEX 预览带总长）、`first_diff_offset()`、`match_type_label()`；匹配日志走 RX/TX 队列，享受 burst 保护（高速时不会刷屏）",
            "测试：test_serial_proto_frame.py 扩至 122 项（新增第 [10] 段匹配诊断纯函数：6 种方式的失败原因 + 误填识别 + HEX 预览截断 + 首个不同字节偏移）；test_serial_tool_widget.py 扩至 257 项（新增第 [26] 段：**用实测的 77+92+36+3 四块交付复现跨块匹配**、失败诊断 5 行内容、误填点名、以及「两次发送之间不得拿上一次响应的字节误判」）",
        ],
    ),
    (
        "1.23.49",
        "2026-09-22",
        [
            "修复（实测报障）：**改了默认值却对老用户不生效** —— 1.23.48 已把「解析行数上限」默认改为不限制，但日志里仍显示「已省略 83 行」。根因：参数一旦被保存过就会把**当时的默认值**写进 `serial_tool_config.json`（实测该文件是 `version: 1` + `parse_max_lines: 30`），而 `merge_params` 只在「键不存在」时才用新默认值。改为引入**配置版本迁移**：`CONFIG_VERSION` 升到 2，`load_config` 按 `version` 调 `migrate_params` —— v1 配置里 `parse_max_lines == 30`（= v1 的默认值，不是用户特意选的）迁移为新默认 `0`（不限制），用户显式设过的**其他**值一律保留；回写后版本升为 2，不会来回抖动。**通用教训**：以后改任何参数的默认值，都要同时考虑「旧配置里已存了旧默认值」并加迁移，否则改动等于没做",
            "测试：test_serial_proto_frame.py 扩至 102 项（新增第 [9] 段配置迁移：旧默认 30 → 0、用户特意设的 5 / 0 保留、v2 里的 30 保留、迁移不改原对象、`load_config` 走迁移、回写升版本 2、再读回不抖动），并把「反例自检」段顺延为 [10]",
        ],
    ),
    (
        "1.23.48",
        "2026-09-22",
        [
            "串口工具：**发送（TX）也按命令协议解析**，与接收对称 —— 之前只解析 RX，发送的命令在日志里只有一行 hex。`_tx_log_queue` 与 `_rx_log_queue` 统一为 `(kind, text)` 元素，`_queue_parse(frame, protocol, channel)` 按 `channel` 入对应队列；`_flush_log_queues` 用同一套规则处理两个队列（各自前缀 `[TX]`/`[RX]`、raw 用各自配色 tx/rx、解析行 sys、失败行 fail），**burst 只对各自队列的 raw 计数**",
            "串口工具：**解析行数默认不再截断**（`parse_max_lines` 默认 `0` = 不限制，可选 0~2000，0 显示为「不限制」）。起因：现场实测国网「查询从节点ID信息」一条应答帧就有 **113 行**解析（22 行帧级字段 + 1 行从节点总数量 + **15 个节点 × 6 行**），旧的默认上限 30 让现场只能看到前 30 行；实测已核对「113」是**解析行数**、与「从节点总数量 = 113」纯属数字巧合（解析器确实只输出 15 个节点 = 本次应答数量）",
            "测试：test_serial_proto_frame.py 扩至 88 项（`max_lines = 0 / 负数` 不限制、上限 2000、默认值语义）；test_serial_tool_widget.py 扩至 136 项（新增第 [24] 段：TX 按命令协议解析 / TX 原始行与字段行格式 / 关闭「显示解析」时 TX provider 零调用 / 命令协议为「不解析」时不解析 / TX 解析异常只进 TX 失败行 / 两个队列按各自前缀与配色刷出；第 [23] 段补「默认不限制 → 完整 113 行」与「节点地址行 = 15」两条实测断言）",
        ],
    ),
    (
        "1.23.47",
        "2026-09-22",
        [
            "串口工具：**命令表新增「协议」字段**（任务 09-22-serial-proto-parse）—— 命令表第 5 列显示协议短名（「不解析」= 不参与），添加/编辑命令时用下拉选择（`不解析` + 12 个协议，带 `[i]` 前缀）；字段随 `serial_tool_config.json` 落盘与读回，**旧配置无该键时回落「不解析」**，非法值（bool / 越界 / 非数字字符串）一律回落，导出裸列表时统一补齐该键（源工具忽略未知键，双向兼容不破）",
            "串口工具：**接收按「最近一次发送命令的协议」断帧**（串口是问答式，RX 就是这条 TX 的响应）。新增纯函数 `frame_length_for(strategy, buf)`：南网/国网 `68H + L(2B 小端)`（整帧 = L）、DLT645-2007 `68H + A(6) + 68H + 控制码 + L(1B@9)`（整帧 = L + 12）、698.45 `68H + L(2B 小端) + 68H`（整帧 = L + 3）、HDLC/DLMS-APDU(国网) `7EH…7EH` 定界（7D 转义，共享标志位不产空帧）、DLMS Wrapper `版本 0001 + … + 长度(2B 大端@6)`（整帧 = 8 + L）；**每种都要求自证**（末字节 16H / 第二起始符位置 / 版本 + 长度合理），任一不满足即返回 0 交回既有「启发式 + 时间聚合」路径 —— **错切帧比不切更糟**；无自证依据的协议（PLC RF / DLMS-APDU 裸 / 新一代 / 国网新一代 / HDC 1.0）行为与改动前完全一致",
            "串口工具：**按该协议解析并在日志直接输出文字**。解析能力由 `main_gui` 注入回调（`tab.set_parse_provider(self._serial_parse_provider)`，与 `set_serial_worker` 同一约定，widget 不 import main_gui），与单帧页/批量共用同一套分派（`_get_current_parser` + `build_gui_parser`），保证「串口工具看到的解析」与「复制到单帧页解析」逐字段一致。每个完整帧输出 `[解析·<协议短名>] <摘要>` + 缩进字段行（`字段名 = 解析值  说明`，解析值空则回落原始值）；行数上限可配（默认 30，超限提示「共 N 行，已省略 M 行」）；解析异常 / 返回空表时只输出 `[解析·…] 失败：<原因>`（fail 配色），**不伪造**半成品字段",
            "串口工具：新增「显示解析」开关（默认开，关闭时零解析开销 —— 实测 provider 零调用）与「解析行数上限」参数（1~500，随参数落盘）；RX 日志队列元素升级为 `(kind, text)`（raw/parse/fail 三色），**burst 策略只对原始行计数**：一批超 20 帧时只输出「摘要 + 首帧 + 末帧」，同批解析明细整批丢弃（防刷屏拖慢界面）",
            "串口工具：`export_commands` 统一补齐并归一化 `protocol` 键（程序内直接构造的命令可能缺它），保证落盘/导出格式一致；`_on_sent` 锁存该命令的协议供接收侧使用（同批命令协议不同时以最后发出的为准）",
            "测试：新增 test_serial_proto_frame.py（84 项：三种 68 结构 / 645 / 698.45 / HDLC / Wrapper 的策略分帧 + 越界与自证失败反例 + HDLC 共享标志位 + 文字格式化与截断 + 协议字段归一化与参数钳制 + 反例自检），登记 release_check.py:CORE_TESTS；test_serial_tool_widget.py 扩至 119 项（协议锁存与按协议断帧、假 provider 的解析格式/截断/异常/空表/开关、burst 不展开、协议字段对话框与落盘读回与导入导出、**真实解析器端到端冒烟**：国网 208 字节帧 / 645 / 698.45）",
        ],
    ),
    (
        "1.23.46",
        "2026-09-22",
        [
            "新增**「串口工具」标签页**（集成自 `E:\\python\\USB负载测试工具`，任务 09-22-serial-tool-integration）：命令表（名称 / 发送数据 HEX / 匹配方式 / 预期响应）增删改与上下移 + 保存·加载配置（JSON，与源工具**裸列表双向兼容**）+ 加载报文文件（txt 每行 hex，兼容 `前缀:` 形式，比源工具多一次「最后一个冒号」兜底）",
            "串口工具：**精确间隔**循环发送（间隔 1~10000ms、次数 0=无限；间隔 >5ms 先 sleep 再尾段忙等保精度）+ 发送完成后等一个响应超时收尾并打印成功率；接收两模式（原始数据按批聚合 / 按帧尾分割，帧尾可配默认 `FE 16`）",
            "串口工具：6 种响应匹配（包含 / 完全相等 / 开头 / 结尾 / 正则 / 不匹配）与源工具同名同义；接收数据从待匹配**队首连续**比对（一批数据可连续命中多项），超时 / 停止 / 收尾把剩余待匹配计为失败；成功率 = 成功 / 已发送待匹配数（仅计入「启用匹配且匹配方式非 none」的发送）",
            "串口工具：彩色日志（TX 红 / RX 绿 / 匹配 ✓✗ / 系统蓝）+ 1 万行上限 + 自动滚动 / 显示发送 / 显示接收开关；**高速发送日志按 100ms 批量刷出**，队列超过 20 条只输出「摘要 + 首帧 + 末帧」（实测 200 帧仅十余行日志，不刷屏）",
            "串口工具：命令与参数自动落盘到 `serial_tool_config.json`（临时文件 + `os.replace` 原子写，损坏回落默认值），该文件已加入 .gitignore；串口层**复用主窗口共享的 `serial_worker`**（与组帧页/监控器页同一约定，端口/波特率只在顶部「串口配置」设置），并为其新增静默写入 `write_raw()`（不逐帧发日志信号 + 写锁，供高速发送使用）；本页只读跟随连接状态、不再自带端口/波特率/连接控件（一个 COM 口只能打开一次，各页各持句柄会互相抢口）",
            "修复（实测报障，两轮）：**「原始数据」模式下一帧被打成多行**。① 串口驱动会把同一帧拆成多次 `read` 交付（低波特率甚至逐字节），原实现按每次交付输出一行 → 一帧多行、RX 帧数虚增；② 首轮改为 10ms **静默聚合**后仍报障：实测 208 字节的国网帧被拆成 77+92+36+3 共 4 行，说明**交付块间隔本身就大于 10ms**，纯时间聚合不可能可靠合并。最终改为**帧结构优先、时间聚合兜底**：按长度域收全再输出 —— 南网/国网 `68H + 长度域 L(2B 小端) + … + CS + 16H`（`L` 就是整帧字节数，实测 `68 D0 00 …` → 208 与 4 行合计 208 完全吻合）、698.45 `68H + L(2B 小端) + 68H + … + FCS + 16H`（整帧 = L + 3，见协议文档 6.2.2）、DLT645-2007 `68H + 地址(6B) + 68H + 控制码 + 数据长度 L(1B) + … + 16H`（整帧 = L + 12）；三者按**第二个起始符 68H 的位置**（第 4 / 第 8 字节）互斥判别，且末字节必须是 16H 才算自证 —— 帧体内出现 16H 不会被误切，两帧连在一次交付里也能切成两行，判别不出的（不足 8 字节等）一律退回时间聚合，**错切帧比不切更糟**。非上述结构与无结构裸数据仍走时间聚合，并保留 10ms 静默窗口、200ms 最长持有（防持续流无界增长）、已声明长度帧 300ms 容忍静默 + 5s 绝对上限；切换接收模式与 `cleanup()` 时立即刷出，不丢数据",
            "修复（测试暴露的既有缺陷）：构造期 `_load_persisted()` 触发控件 `toggled` → `_schedule_save()`，而 `_save_timer` 彼时尚未创建 → 信号槽内抛 `AttributeError`（Qt 静默吞掉，**配置保存随之失效**）。已把 `_save_timer` 提到 `_build_ui()`/`_load_persisted()` 之前创建，并加构造顺序回归断言",
            "修复（实现期由测试发现）：上一轮发送遗留的收尾定时器 / 迟到信号会掐断新一轮发送（实测 200 帧只发出 140）—— 改用「发送器身份 + 发送代次」双重守卫",
            "测试：新增 test_serial_tool_widget.py（纯逻辑 + 假串口驱动的发送/匹配/分帧/节流/持久化 + 主窗口懒加载集成）、test_serial_worker_write_raw.py，均登记 release_check.py:CORE_TESTS；既有 test_serial_worker_framing.py（28 项）全绿",
        ],
    ),
    (
        "1.23.45",
        "2026-09-22",
        [
            "TCP 监控：非 ED..EE 封装的**原始 TCP 载荷**不再被静默丢弃。`FlowBuffer` 新增切帧策略 `auto/ed/raw`（默认 auto）：某方向出现过 ED 帧则行为与改动前一致；判定为非 ED 方向时按 **TCP segment 逐包**产出「原始数据帧」（实测：27B 原始载荷原先切出 0 帧、`pending_bytes` 归零即字节全丢，现在 1 段 1 帧且长度相符）。含 0xED 的普通载荷不会被误判为 ED 帧（完整定界校验 + 等待上限 2 段），跨包 ED 帧仍正常切出，raw 方向遇完整 ED 帧可升级回 ED（应对抓包从 ED 连接中途开始）",
            "TCP 监控：协议识别扩展为「显式选择优先 + 自动识别（只认可自证形态）」。自动识别覆盖 DLMS Wrapper（版本 00 01 + 长度自洽）、DLMS-APDU 裸报文（首字节 ∈ `HDLCParser.APDU_TYPES`）、DLT645-2007（68+6+68 结构 + 校验器 0 fail）、698.45（HCS/FCS 双通过 CRC 自证）。**已声明边界**：南网/国网 同为 0x68 起头且链路层结构相近，校准实测两者校验器互判 0 fail（无法区分），故**不参与自动识别**，需显式选择 —— 错解析比不解析更糟；显式选择下解析器返回退化结果（行数 <2 或摘要为 '-'）也如实回落为原始数据，不拿退化结果冒充解析成功",
            "TCP 监控：识别不出的载荷按「原始数据」正常显示（协议列 = 原始数据、摘要含长度、解析行含 TCP 载荷/首字节/原始数据 三行），首字节命中 698.45 或 DLMS APDU 标签表时给出「疑似 … APDU: 名称」；路由不再只看首字节（原始载荷恰以 0xED 开头时不再被塞进 ED 路径得到「无法识别协议」+ 空表）",
            "TCP 监控 UI：新增 Wireshark 风格字节视图 `hex_dump_view.HexDumpView`（偏移 + 16 进制 + ASCII + 按字节范围高亮，高亮色与主窗口一致，保留旧属性名 `segment_hex`）；「解析结果」新增 表/字段树 切换（复用 `parse_result_view`，与主窗口同构，树选中同样高亮字节）；帧表新增「源 → 目的」列、未识别帧灰色弱化；新增「仅未识别」勾选与协议过滤（只影响显示、缓存保持全量）；协议下拉扩展为全协议并按 itemData 携带协议索引；切换协议下拉会**重解析已抓帧**（>200 帧分批让出事件循环，帧数量/顺序/字节不变）",
            "测试：新增 test_hex_dump_view.py（27 项）、test_tcp_monitor_raw_payload.py（27 项）、test_tcp_monitor_proto_detect.py（36 项）、test_tcp_monitor_ui_views.py（46 项），均登记 release_check.py:CORE_TESTS；既有 ED 相关 TCP 测试（test_tcp_monitor_ed_hdc 15 项 / test_tcp_monitor_proto11_frames 55 项 / hdc10_tcp_ed_frames）全绿",
        ],
    ),
    (
        "1.23.44",
        "2026-09-21",
        [
            "修复：启动后「协议选择」下拉框显示为空白、点一下才出现文字。根因是顶部协议组的自定义 `FlowLayout.sizeHint()` 返回了 `minimumSize()`（各子项最小尺寸的逐分量最大值 ≈ 最宽单项 276px），父布局据此只给这么宽 → 布局被迫换行成两行 → 分组框高 75px 而顶栏容器只有 49px → 第二行的协议下拉框被裁成一条缝（实测 geometry (5,44)、visibleRegion 仅 266x5）",
            "修复：`FlowLayout.sizeHint()` 改为**单行自然尺寸**（各子项 sizeHint 之和 + 间距 + 边距），语义对齐 QHBoxLayout；`minimumSize()` 保持不变，窗口真窄时仍照旧换行（换行能力未被削弱）",
            "修复：`_reflow_proto_group()` 增加「重排外层顶栏」步骤。原实现只 invalidate/updateGeometry/adjustSize 内层布局，分组框拿不到最终宽度、内层 FlowLayout 也不会被重新调用，子项就停在旧的换行位置；实测只重排外层后，下拉框同步从 (5,44)/266x5 恢复到 (76,20)/266x26，不再依赖点击等交互触发",
            "测试：新增 test/test_flow_layout_proto_group.py（11 项，offscreen：sizeHint 语义 / 窄窗仍换行 / 启动 reflow 后下拉框完整落在顶栏容器内 / 反例自检还原旧实现必须变红），登记 release_check.py:CORE_TESTS",
        ],
    ),
    (
        "1.23.43",
        "2026-09-21",
        [
            "「关于」对话框新增「去 GitHub 给作者点 Star」按钮（star 图标）与提示行「如果这个工具帮到了你，欢迎在 GitHub 上给作者点个 ⭐ Star」；点击用系统默认浏览器打开作者仓库",
            "作者仓库地址 `AUTHOR_GITHUB_URL` 为单一来源（按钮提示/跳转/测试都读它，改地址只改一处）；调起浏览器失败时弹窗给出可手动复制的地址，不静默无反应",
            "「关于」对话框拆出 `_build_about_dialog()`（构造与 `exec()` 分离）便于测试直接检查控件与接线，菜单接线不变（仍由 test_menu_wiring.py 守卫）",
            "测试：新增 test/test_about_github_star.py（offscreen：按钮存在/图标非空/文案/与「检查更新」「确定」同排/URL 单一来源/点击跳转/失败兜底/`_show_about_dialog` 仍 exec）",
        ],
    ),
    (
        "1.23.42",
        "2026-09-21",
        [
            "Web↔GUI 修复同步（任务 09-17-web-gui-parity-sync）：出「版本×Web 对应物」审计清单 docs/Web与GUI同步审计.md（1.23.0~1.23.22 共 167 条逐条判定：继承 88 / 缺失 21 / 同错 0 / N/A 58，含依据与文件:行号）",
            "645 转表收口为单一来源：`reflex_web._safe_parse_to_table` 删除逐字复制体，改 import `protocol_registry.DLT645GuiParser`；偏移公式改为按**实际帧长**（`frame_len`/`cs_pos`/`end_pos`）计算，修「声明长度与实际不符」帧的校验和/结束符偏移越界（合法帧输出逐行不变）；新增 test/test_dlt645_table_offsets.py（40 项，含单一来源守卫）",
            "测试模式摘要片段收口为单一来源：桌面 `_extract_test_mode_content` 改为一行转发 `batch_core.extract_test_mode_content`（`_TEST_MODE_SENTINELS` 同源），Web `web_utils` 接入同一函数并在 `get_csg_new_gen_summary`（`_append_test_mode_segment`，含去重守卫）与 `get_hdc10_summary` 补上该片段——修 Web 协议10/11 测试类报文摘要缺「测试模式」",
            "Web 查询页补齐自定义条目 CRUD：协议0 新增/覆盖/删除自定义 DI（`State.add_custom_di` / `delete_custom_di` / `delete_selected_custom`，查询表勾选列 + 「删除选中」批量按钮，内置 DI 忽略并计数）；协议7 新增自定义 AFN+Fn（`lookup_utils.add_gdw_custom_fn` / `remove_gdw_custom_fns`，复用 `GDW10376Parser` 既有 API，表单 + 批量删除）；查询表新增「自定义」★ 列；`custom_di_store` 读写支持可选 path 注入（默认行为不变）",
            "`gdw_afn_lookup` 新增 `refresh()`：自定义 AFN+Fn 增删后重建查询缓存（否则页面仍是旧表）",
            "测试：新增 test/test_web_gui_parity.py（83 项：R3 两端摘要片段对拍 + R4/R4b 增删与沙箱，均已登记 release_check.CORE_TESTS）；变异反证 3 条实测变红后还原（偏移公式回退 / 删 Web 片段 / 645 复制体回潮）",
            "顶栏折叠时标题栏协议短名**近似居中**：Windows 原生标题整段左对齐，按窗口宽度用空格把短名顶到中部，resize 时重算填充（用户反馈：字面插在字符串中间仍靠左）",
        ],
    ),
    (
        "1.23.41",
        "2026-09-21",
        [
            "GUI 顶部栏「协议选择 + 串口配置」支持整体显示/隐藏：菜单栏右上角小图标按钮（panel-top-open/close）一键切换，两组控件同时消失/恢复，不再各占一条折叠按钮栏",
            "顶栏折叠时：标题左侧保持「版本+日期 - 作者」不变，**仅协议短名**按窗口宽度空格近似居中（Windows 原生标题整段左对齐，resize 重算）；状态栏显示 `串口: 端口 · 波特率 · 校验 · 连接状态`",
            "折叠态持久化到 config.json 顶层 `top_bar.collapsed`（兼容初版 proto_collapsed/serial_collapsed，任一为真即整栏折叠）；不写入 ui 段",
            "测试：改写 test/test_top_bar_collapse.py（单开关一起显隐/标题短名/状态栏串口/配置往返）",
        ],
    ),
    (
        "1.23.40",
        "2026-09-21",
        [
            "协议6（DL/T645-2007）串口接收修复（用户报障：协议6 打开串口发送测试，只有发送没有接收）",
            "根因一：SerialWorker._process_buffer 只按 FT1.2 切帧（68H + 长度2B 小端 + … + 16H），而 DL/T645 是 68H + 地址(6B) + 68H + C + L + 数据(L) + CS + 16H —— 它把**地址低字节当长度域**，`68 01 00 …` 算出长度 1（<8）→ 整帧丢弃，frame_received 永不触发",
            "根因二：协议组帧页只连了 frame_received、未连 raw_data_received，故切帧失败时接收数据**完全静默**，日志里只剩 [发送]",
            "修：切帧按「首个 68H 之后偏移 +7 是否也是 68H」判别 DL/T645 双起始符（与 dlt645_parser 的 data[7] != 0x68 同口径），总长 = 12 + 数据长度；FT1.2 分支保持原样（含长度域对不上时靠 16H 兜底的容错路径）；支持 FEH 唤醒前导、粘包、半帧分次到达",
            "修：frame_gen_widget._on_serial_frame_received 补 dlt645 分支（原先落进 else 被 gdw_parser 解析，收到回包也只显示解析失败），新增 _dlt645_to_table 与 main_gui 深度解析同口径（fields 的 3/4 元组 → 6 元组表格行）",
            "测试：新增 test/test_serial_worker_framing.py（28 项）登记 CORE_TESTS——含用户截图那帧 68 01 00 00 00 00 00 68 11 04 33 33 34 33 B3 16",
        ],
    ),
    (
        "1.23.39",
        "2026-09-20",
        [
            "协议11 应用层扩展（用户提供 HPLC技术应用手册 与 2024年2批HDC模块即装即采增补协议要求(山东)，均已转 MD 归档）",
            "通信测试命令(0x006)：按 A-HS-11-03 表2 解析「检测扩展命令」——字节1 高4位为测试模式/配置操作（6 频段切换 / 7 ToneMask / 8 无线信道切换 / 12 MCS / 13 安全测试 / 3·4·5·9·10·11 模式持续时间），12bit 配置值按模式解释；普通通信测试（测试模式=0）仍按表32 原义",
            "事件上报(0x0008)：新增数据域字段级解析（原先只打印原始 hex）——位图方式（事件类型 1/2，起始TEI + 节点位图置位展开）/ 地址方式（3/4，电表个数 + N×(地址6B+带电状态1B)）/ 设备信息（51，即装即采附件3：设备地址·协议类型·描述符 + M 台下挂设备清单）",
            "修 报文头长度 位拼接：事件上报与通信测试原按「低位在字节0」拼装（事件帧显示 192 字节头），改为与本文件其余报文一致的 byte0[6:7]高2位 + byte1[0:3]低4位、单位4字节字（实测真实抄表帧 01 02 → 2×4B=8B 印证）",
            "TCP 监控协议11 自动解析：ED 包装布局改用 CRC-24 自证（原「HDC MAC 版本号」启发式对 DT∈{2,3} 的 SACK/网间协调帧会误判 plc2，业务帧整体错位 1 字节后被降级成「应用层报文」垃圾解析；穷举 NID 最低字节实测误判 32/256）",
            "TCP 监控自动识别排序：拿到帧控制证据时把 HDC 1.0 提到南网新一代之前（原先信标/SOF/SACK/网间协调四类帧全部被误判为南网新一代）；摘要兼容协议11「定界符类型(DT)」字段名",
            "测试：新增 test_tcp_monitor_proto11_frames.py(55) / test_hdc10_comm_test_ext.py(43) / test_hdc10_event_data.py(41) 并登记 CORE_TESTS；test_tcp_monitor_ed_hdc 与 test_tcp_monitor_proto11_frames 改用 os._exit 交出退出码，避免 Qt offscreen 收尾崩溃被 release_check 误判",
        ],
    ),
    (
        "1.23.38",
        "2026-09-20",
        [
            "协议11 TCP/ED 解析信标帧（用户提供现场帧：ED A4…FF EE，292 字节，帧长域=164 与末尾 EE 不一致）",
            "batch_core：帧长域与 EE 不一致且缓冲区以 EF..EE 结尾时，按末尾 EE 重算整包（`_ed_frame_parts` / `extract_business_from_ed_frame`）；extract 未指定 wrapper 时 resolve 带 protocol_index（10/11 优先 gx）",
            "HDC10 auto：FCCS 失败时若 DT=0 且 HDC1.0 版本位，按 FC+信标载荷继续解析（「⚠ 推测信标帧」）",
            "摘要：兼容协议11「定界符类型(DT)」字段名，并补「中央信标/发现信标」等信标类型",
            "该帧现解出：国网HDC包装头 + DT=0 信标 + FCCS✓ + 中央信标 + 时隙分配条目；摘要 `国网HDC监控包装帧 | NID:3 | 信标帧 | 中央信标 | 1→?`",
            "测试：新增 `test/test_beacon_ed_hdc10.py`（20 项）登记 CORE_TESTS",
        ],
    ),
    (
        "1.23.37",
        "2026-09-20",
        [
            "TCP 监控支持协议11 HDC 1.0：协议下拉新增「HDC 1.0」；选中后 ED..EE 封装按国网HDC 文案解析包装头字段，并对业务帧用 HDC10Parser 解析",
            "FlowBuffer 改为保留完整 ED 帧（原先写死剥 9 字节 PLC2 公共头，HDC/gx 8B 布局会错位）；解包与字段行走 batch_core.unwrap_ed_for_parse / build_ed_header_rows（与桌面同源）",
            "主窗口 TCP 监控 tab 注入 hdc10 解析器；自动识别顺序：南网 → 国网新一代 → HDC 1.0",
            "测试：新增 `test/test_tcp_monitor_ed_hdc.py`",
        ],
    ),
    (
        "1.23.36",
        "2026-09-20",
        [
            "ED 包装头字段文案按协议分语义（用户：广西 ED 与国网 HDC 封装定义相同，但协议10/11 解析结果不得显示「广西台体监控包装头」）",
            "单一来源 `batch_core.ed_wrapper_display(protocol_index, wrapper)`：协议9→PLC2.0/广西台体；协议10/11→国网HDC（gx 8B 布局同构，plc2 布局标题标注「(PLC2.0布局)」）",
            "接线：`_parse_ed_monitor_header`、`csg_new_gen_parser._parse_ed_wrapper`、桌面/批量/Web 摘要、ED 包装格式下拉文案（协议切换时刷新）",
            "测试：新增 `test/test_ed_wrapper_labels.py`（19 项）；ed_gx_wrapper / hdc10_ed_wrapper / ed_ui 回归全绿",
        ],
    ),
    (
        "1.23.35",
        "2026-09-20",
        [
            "协议10/11 单帧解析开放协议9 的 ED 工作流控件（用户：GUI 协议11 解析带 ED 封装报文时，需要 ED 勾选、4字节反转等操作）",
            "注册表 ProtocolSpec 新增 `has_ed_monitor` / `has_reverse_4byte`（协议9/10/11 为 True）；主窗口可见性与 parse_single 能力开关改为查表，不再写 `current_protocol==9` 硬门控",
            "协议10/11 工具栏可见：「ED监控协议」「ED包装格式」「4字节反转」「字节剔除头/尾」",
            "行为：勾选 ED → 与协议9 相同，解包失败明确报错；未勾选时 10/11 仍自动识别（业务帧 DT∈0~3 才剥离）；勾选 4字节反转/字节剔除对 9/10/11 生效",
            "解析弹窗「剥离ED监控头」同样适用于协议11，勾选后不完整 ED 帧报错",
            "测试：新增 `test/test_ed_ui_for_gw_hdc10.py`（25 项）；ed_fallback / ed_gx_wrapper / registry 回归全绿",
        ],
    ),
    (
        "1.23.34",
        "2026-09-20",
        [
            "修复协议11（HDC 1.0）FC 可变区域跨字节位域位序错误（用户报障：FC 源TEI 应为 002 却解析成 032，而 MAC 头 TEI 正确）",
            "根因：FC 可变区域的跨字节位域按「首字节=高位」组装（如 src_tei=(b4<<4)|(b5&0x0F)），而规范各表（表19/23/27/30/34）的「字节号/比特位」列是 LSB-first 位流——位号小的一端是低位；MAC 头一直按 LSB-first 解析（((b0>>4)&0x0F)|(b1<<4)）故正确，FC 错",
            "判定依据（两条独立实证）：① 广播标志位=比特1 → (b11>>1)&1=1，该帧目的TEI 确为广播地址 4095；② 分集拷贝基本模式=比特4-7 → 4，该帧物理块恰好 136 字节（模式4=136B）",
            "修复：新增 hdc10_parser._bits_lsb(data, byte_off, bit_off, nbits)（公式与规范比特位列一一对应，可防再犯）；6 个 FC 可变区域解析函数的 源TEI/目的TEI/帧长/符号数 全部改用它（共 13 处）；目的TEI 此前同样错（现场帧 256 应为 1）",
            "验证：现场 7 帧的 FC 源TEI/目的TEI 现与 MAC 头「原始源TEI」/「原始目的TEI」逐帧完全一致（帧0: 2/4095；帧1-6: 0/1）；新增 test/test_hdc10_fc_bits.py（22 项，含该语义不变量与「无旧位序写法」静态守卫）",
        ],
    ),

    (
        "1.23.33",
        "2026-09-20",
        [
            "修复协议11（HDC 1.0）单帧解析/快捷弹窗仍把 ED..EE 监控包装帧当应用层解析（用户报障：单帧框贴 ED 帧仍输出「应用层报文」）",
            "根因：ED 解包在单帧路径被硬门控在协议9——parse_single 的 ed_mode 要求 current_protocol==9 且勾选「ED监控协议」（复选框仅 9/10 可见），快捷弹窗 _preprocess 更是只认 idx in (9,10) → 协议11 下 ED 帧原样送解析器",
            "修复：两条单帧路径的 ED 识别扩到协议 9/10/11；协议10/11 无该复选框 → 自动识别，并新增 _ed_business_is_fc 防误剥离判据（解包后业务帧 DT=business[0]&0x07 必须 ∈0~3；0xED 低 3 位=5 恒非法，真 FC 恒满足），避免把首字节恰为 0xED 的物理块/MAC 帧误剥；协议9 勾选态「不完整帧必须报错」契约不变",
            "回归：test/test_hdc10_ed_wrapper.py 扩到 30 项（新增单帧解析与快捷弹窗端到端断言）",
        ],
    ),

    (
        "1.23.32",
        "2026-09-20",
        [
            "修复协议11（HDC 1.0）无法解析 ED..EE 监控包装帧（用户报障：现场日志帧贴入后被解析成「应用层报文」端口0xED/业务0x0A4）",
            "根因①：协议11 extract_strategy=\"line\" 的默认分支「每行一帧」完全不做 ED 解包（ED 解包只存在于协议9 的 csg_line 策略）→ 首字节 0xED 落到应用层解析",
            "根因②：既有解包路径硬编码 startswith(\"EDA5\") + 固定剥 15 字节；现场帧是 EDA4 且数据域公共头为 gx(8B) 而非 plc2(9B)，应剥 14 字节 → 双重不命中，即便泛化前缀也会多剥 1 字节致整帧错位",
            "修复：batch_core 新增通用 ED 解包三件套 ed_wrapper_prefix_len（按帧长+detect_ed_wrapper 判别 plc2/gx）/ split_ed_frames（按帧长切分一行内拼接的多帧，残帧丢弃）/ unwrap_ed_line；协议10/11 行提取改为 ED-aware（桌面 main_gui._extract_line_frames、Web web_utils 同源）；strip_gw_new_gen_prefix 的 app 扫描跳过 ED 行（避免被帧内偶然的 0x11/0x12/0x1A 截断）",
            "验证：现场 7 帧（每帧 168B）现解出 7 条 152B 业务帧（FC16+PB136），FCCS/PBCS/ICV 全部校验正确，MMTYPE 0x0008 发现列表完整展开；新增 test/test_hdc10_ed_wrapper.py（26 项，含桌面批量端到端与协议6 不受影响护栏）",
        ],
    ),

    (
        "1.23.31",
        "2026-09-19",
        [
            "协议11（HDC 1.0）网络管理消息 MME 全 20 个类型字段级深解析补齐（依据第4-2部分表59/60~137）：关联确认、关联汇总指示、代理变更请求/确认/位图确认、离线指示、通信成功率、网络冲突、过零NTB采集指示/告知、网络诊断、路由请求/回复/错误/应答、链路确认请求/回应、无线信道冲突，以及单跳帧无线发现列表 TLV（站点属性/路由/邻居信道非位图与位图）",
            "修复 0x000A 网络冲突上报分派调用不存在的 _parse_network_conflict 抛 NameError（被上层兜底成「管理消息解析失败」）；补全名称表缺失的 0x0050~0x0055（原显示「保留」）；0x0001 关联确认由猜测口径改为按表70逐字段解析；0x0006 离线指示由错误的 TEI 口径改为原因/总数/延迟/MAC 列表",
            "所有变长列表/位图/12比特紧凑差值流均做截断容错（声明长度超实际给 ⚠ 不崩）；Web 端复用同一解析器同步受益",
            "新增 test/test_hdc10_mme_full.py（81 项，全类型 golden 断言 + 截断容错 + 0x000A 回归）；真实帧 hdc10_real_frames.pkl 60 帧全量解析 0 崩溃",
        ],
    ),

    (
        "1.23.30",
        "2026-09-18",
        [
            "协议10/11 批量/监控摘要：网络层（含仅PB级别）MME 帧体现管理消息 MMTYPE（用户报障：协议11 仅PB 批量 68 帧，详情已是「关联请求」，摘要却只有 `0→1 | msduSeq:x | 单播`）",
            "根因：桌面 `_get_gw_new_gen_summary` 只精确匹配协议10 字段名 `管理消息类型(MMTYPE)`，协议11 为 `消息类型(MMTYPE)`（hdc10_mme_parser）→ 永不命中；且步骤7 故意跳过「网络管理」类 MSDU 类型",
            "桌面摘要现兼容两种字段名 + 区头 comment（`MMTYPE: 0x0000 (关联请求)`），输出 `MMTYPE:0x0000(关联请求)`；有 MMTYPE 时不重复「网络管理消息」",
            "Web `get_hdc10_summary` 同步：`MME:` 前缀改为与桌面一致的 `MMTYPE:`，并补 TEI/`msduSeq`/发送类型",
            "测试：新增 `test/test_gw_pb_mme_summary.py`（13 项）登记 CORE_TESTS；`test_gw_app_summary_detail` 网络层回归段扩 MMTYPE 断言",
        ],
    ),
    (
        "1.23.29",
        "2026-09-18",
        [
            "修复协议10/11「仅MAC帧(mac_only)」仍自动解析物理块头（用户报障：GUI 协议11 粘贴现场帧后要求“解析正确，而不是又自动的解析物理块头部”）",
            "契约与协议9对齐（AGENTS §8 陷阱19）：mac_only 输入即 MAC 帧，从字节0解析，不探测/剥离 PBH；需要 PBH 用 pb_only/auto",
            "协议10 `gw_new_gen_parser`：mac_only 原走 `_parse_pb_by_frame_type` 把首字节当 PBH → MAC 头整体错位（源TEI/目的TEI/MSDU类型全错），改为 `_parse_mac_and_msdu(data, 0)`",
            "协议11 `hdc10_parser._parse_mac_only`：去掉 data[0]&0x80 自动剥 1 字节逻辑",
            "协议11 MME 行偏移改为绝对帧偏移（原先相对 MSDU 切片，点击字节高亮错位）；`hdc10_mme_parser` 内容段偏移补 content_offset",
            "GUI 解析级别下拉切换后自动重解析（与通道切换同口径）",
            "现场帧关键字段（协议10/11 一致）：版本0 / 源TEI0 / 目的TEI1 / MSDU类型0 / MSDU长度92 / MMTYPE=0x0000 关联请求 / ICV 0xC4508168 校验通过",
            "测试：新增 `test/test_hdc10_mac_only_contract.py`（35 项，含 GUI 包装路径与 bit7 前缀变异反证），`test_gw_parse_levels` 按新契约改写；登记 `release_check.py:CORE_TESTS`",
        ],
    ),
    (
        "1.23.28",
        "2026-09-18",
        [
            "字段树增加「说明」列（字段 | 值 | 说明），中文含义直接可见；列宽 260/280，说明列伸展",
        ],
    ),
    (
        "1.23.27",
        "2026-09-18",
        [
            "字段树重做成 Wireshark 风格：两列「字段|值」而非表格四列；结构节点（有子级/位域/帧头等）可展开，叶子显示 解析值(+原始hex)；位段提取为 [D15]/[bit0-11]；说明进 tooltip；默认展开、点击仍高亮字节",
        ],
    ),
    (
        "1.23.26",
        "2026-09-18",
        [
            "字段树与表格视觉对齐：主题 QSS 中 QTreeWidget 与 QTableWidget 同配色/交替行/选中色/内边距；树默认 expandAll、列宽 130/100/100 与表一致、子级字段名灰色 #555、去掉与表不一致的父节点蓝字；主题切换时同步树字号行高",
        ],
    ),
    (
        "1.23.25",
        "2026-09-17",
        [
            "单帧解析结果新增「视图: 表格 / 字段树」切换（Wireshark 风格）：字段树按缩进还原父子层级，点击树节点高亮输入框对应报文字节；parse_result_view.py（纯逻辑 + QTreeWidget）；test/test_parse_result_tree.py",
        ],
    ),
    (
        "1.23.24",
        "2026-09-17",
        [
            "**协议11（HDC 1.0）修复「无物理块头」帧整体错位**（用户报障：同一帧协议10 能解析、协议11 只有 17 行且 MAC/MSDU 树全错）：`_parse_pb_block` 原先无条件剥离 1 字节物理块头(PBH)，而该帧 PB 体第 1 字节即 MAC 帧头起始 —— 依据 第4-2部分 表37（物理块头：bit7=帧结束标志，合法 PBH 恒为 1）与 表10（标准 MAC 帧头：版本 0 时 byte1/byte6 必为 0x00）判定其不含 PBH；**帧内 ICV 与 `crc32(MSDU)` 完全相等**（1/2^32 概率）为决定性证据",
            "新增 `HDC10Parser._probe_pb_form(data)` 逐字节打分探测 PB 形态（存在合规 MAC 头 → 无 PBH；合法 PBH + 其后合规 MAC 头 → 有 PBH；无任何合规信号 → 回落旧行为），`_parse_pb_block` 与 `_parse_pb_and_mac_header` 均改走该探测；现场帧 auto 级别 **17 行 → 57 行**，MAC 头 / ICV / 端口号 / 报文ID / 抄表头 / DATA 全部可读，与协议10 结果一致",
            "**同时修复既有缺陷**：`_parse_pb_and_mac_header` 把原帧**绝对**偏移当作 data 内**相对**索引（旧代码传 `base_offset + 1`）⇒ 解析级别「fc_mac」下 MAC 头整体错位（原始源TEI 读成 2、MSDU类型 读成 0、MSDU长度 读成 1280）",
            "补齐抄表报文头的**设备超时时间**（字节6 ×100ms，§5.3.1.8）与**选项字**（字节7：方向位；终端主动并发抄表下为「报文间间隔」×10ms，表8、表9；上行按表7 输出 16bit 应答状态）两行 —— 协议10 早已输出、协议11 缺失，属跨协议一致性",
            "新增 `test/test_hdc10_pb_structure_probe.py`（39 项，含**变异反证**：强制判定「有 PBH」后 MSDU 类型 ≠ 48、行数变少）；基线对拍：真实夹具 `test/hdc10_real_frames.pkl` 60 帧 × 7 个解析级别逐帧零差异（pb_only 逐帧指纹与强制旧行为完全相同），边界帧长 0/1/8/15/16/17 均不抛异常",
        ],
    ),
    (
        "1.23.23",
        "2026-09-17",
        [
            "**协议6（DL/T645-2007）新增「主动上报状态字 / 主动上报模式字」位表解析**（用户报障：读 `04001501` 只得到一串 96 位二进制，而提示写「状态字位定义见DL/T645-2007附录C」——**出处错误**，该位表定义在《国网计量中心电能表全性能试验检测公告-第4号补遗》，不在附录C）",
            "入库两张位表（逐位字面量，出处：第4号补遗「六、技术标准修改建议（一）」）：**主动上报状态字**（DI `04001501` / `04001503`，96 位 / 12 字节）与**主动上报模式字**（DI `04001104`，64 位 / 8 字节）；字节序**低字节在前**，由补遗自带三个报文示例自证（首字节 `01H`→Bit0=负荷开关误动或拒动、`02H`→Bit1=ESAM错误、字节[10] `01H`→Bit80=编程）",
            "**保留位置位不再静默**：输出「保留位（补遗未定义事件）: Bit76」这类明确标注（用户现场帧 `68 66 51 11 07 25 20 68 91 10 34 48 33 37 33 … 43 33 33 DF 16` 命中的正是 Bit76，补遗未定义该位，需向表厂确认），既不臆造事件名也不丢弃信息；**未置位的保留位不进列表**（96 位表若列未置位会输出近百项）",
            "**语义区分**：模式字 1 = 该事件允许主动上报（使能），状态字 1 = 该事件已发生；全 0 时分别输出「未开启任何事件主动上报」/「无事件」；长度与位表不符时仍尽力解析并前置「⚠ 长度不符」（遵循陷阱23：宁可解释也不空白）",
            "**修正「电表运行状态字 1~7」位号（原表 8 个字无一正确）**：`dlt645_data_codec.py:STATUS_WORD_BITS` 与 DL/T645-2007 附录C 逐位不符。例：状态字4 收到 `0x0002` 时原报「A相潮流方向异常」，附录C 该位是 Bit1=**欠压**。修正后与附录C 逐位一致，并与补遗 96 位表的 A 相组 Bit16–23 **双源互证**（两文档逐位相同，仅「潮流方向」/「功率反向」用词差异）",
            "**输出变化（有意变更，逐条列出）**：① 状态字1：Bit5 无功方向 / Bit4 有功方向 / Bit3 停电抄表电池 / Bit2 时钟电池 / Bit1 需量积算方式（原整体 +2 位错）；② 状态字2：Bit6~Bit4 无功方向(C/B/A) / Bit2~Bit0 有功方向(C/B/A)（原整体 +1 位错）；③ 状态字3：Bit4 继电器状态 / Bit3 编程允许 / **Bit2~Bit1 供电方式（两位域，输出 主电源/辅助电源/电池供电）** / Bit0 当前运行时段（原整体 +3 位错，且把两位域当两个单 bit）；④ 状态字7：Bit4 辅助电源失电 / Bit3 电流不平衡 / Bit2 电压不平衡（原三位错位）；⑤ 状态字4/5/6：Bit6=潮流方向、Bit1=欠压（原 Bit6 报「过载」、Bit1 报「潮流方向异常」），Bit8 断流保持",
            "补全附录C 明确声明的保留位占位（状态字 1/2/7 的 Bit8~Bit15、3 的 Bit8~Bit9、4/5/6 的 Bit9~Bit15）—— 置位时点名「保留位（未定义）: BitN」，未置位不进列表",
            "兜底文案纠错：未收录位域不再给单一错误出处，改为并列「电表运行状态字见 DL/T645-2007 附录C；主动上报状态字/模式字见国网第4号补遗」",
            "**单一来源**：位表与格式化器仅落在 `dlt645_data_codec.py`（新增 `REPORT_STATUS_BITS` / `REPORT_MODE_BITS` / `_format_bits` / `decode_report_status_word` / `decode_report_mode_word`），桌面 `protocol_registry.DLT645GuiParser`、Web `_safe_parse_to_table`、645 虚拟表调用同一份，无第二份清单；`dlt645_di.json`（生成物）未改",
            "新增 `test/test_dlt645_status_word_bits.py`（130 项，登记 CORE_TESTS）：补遗三示例 golden / 现场帧 Bit76 / 模式字 / **R2 不变量（状态字 Bit(32+n) ≡ 模式字 Bit(n)，n=32..63）** / 状态字 1~7 逐位独立清单对拍 / 位域三取值 / 保留位占位 / 位表完整性（每字覆盖 Bit0~Bit15）/ 边界降级 / **桌面↔Web 逐行对拍**",
            "**变异反证 3 条**全部实测变红后还原（状态字4 位号改回旧错位 9 红 / 去掉保留位标注 2 红 / 96 位当 64 位解 3 红）；`test_dlt645_lme.py` 的 12b/12c 用例原固化了错误位号（且 12c 在未置位列表里假绿）已同步改为附录C 口径",
            "**文档**：新增《第4号补遗》MD（由同名 PDF 转换）至 `协议文档/6.645协议/`，位表依据可追溯（注意该 MD 的位表有转换瑕疵：拆行/丢格/页码混入，位表以 PDF 单元格重取为准，见 AGENTS.md 陷阱 50）",
        ],
    ),
    (
        "1.23.22",
        "2026-09-17",
        [
            "**协议6（DLT645-2007）校验和错误时不再拒解析**（用户报障：提供的 645 帧 CS 不对时工具完全不解析、只弹「无效的DLT645帧格式」，看不到任何内容）",
            "根因：`dlt645_parser.check_frame()` 把「结构判据」（长度≥12 / 双 68H / 结束 16H）与「校验判据」（CS）混在一个返回值里，`parse()` 用它**提前 return** ⇒ 任何一项不符都得到空表（违反 AGENTS.md §8 陷阱 23「不得直接返回空白结果」）",
            "修复：判据拆为 `check_structure()` / `calc_checksum()`（`check_frame()` 保留、语义不变）；长度 ≥12 时无论结构与校验是否通过一律**继续完整解析**，并插入醒目提示行 —— **`⚠ 校验和错误`：帧内值 + 正确值 + 计算规则**（`CS = 起始符 68H 到数据域最后 1 字节的算术和 & 0xFF`）、`❌ 帧结构错误`（指明哪个字节不符）",
            "新增结果字段 `checksum_expected` / `structure_valid` / `structure_error`；`error` 文案与南网（`protocol_parser`）同口径「校验和错误，期望 0xXX，实际 0xYY」",
            "`valid` 语义**保持不变**（结构 OK + 校验 OK + 长度相符才为 True），虚拟表等既有消费方不受影响；合法帧输出**逐行不变**（实测 13 行一致）",
            "长度 <12 时给出「帧长不足」说明 + 原始 hex（可接受的降级，不崩溃不空白）",
            "新增 `test/test_dlt645_tolerant_parse.py`（135 项，登记 CORE_TESTS）；**变异反证 3 条**全部实测变红（恢复提前 return 7 红 / 去掉 checksum_expected 24 红 / valid 恒 True 14 红）",
            "**行为变化（有意接受）**：虚拟表从站对坏 CS 主站帧由「异常应答」变为「正常应答」—— `dlt645_sim/engine.py:114` 的 `if not parsed.get('valid')` 分支带注释「尽力：仍尝试取 control/data」属作者有意宽容，旧版回异常应答只是解析器返回空导致的偶然；现虚拟表日志会显示「⚠ 帧校验未通过: 校验和错误，期望 0xXX，实际 0xYY」，信息量更大（详见 AGENTS.md）",
            "附带：消除 `hdc10_parser.py` 两处静态分析误报（`bcsha_phases` 前置初始化、`extra_bytes` 判断补 `msdu_len is not None`），零行为变更（hdc10 全套 + `gw_new_gen` 逐行一致），该文件 lens 转 clean",
        ],
    ),
    (
        "1.23.21",
        "2026-09-17",
        [
            "**协议6（DL/T 645-2007）新增《光伏协议转换单元扩展协议》解析**（依据新增文档 `协议文档/6.645协议/附件1：协议转换单元【低压分布式光伏协议转换单元】-技术规范书0625.md`，已用 `convert_docx_to_md.py` 转出同名 .md）",
            "扩展数据标识三组共 **682 个 DI 键**（变量类 `02E6xxxx` 77 / 参数类 `04E6xxxx` 172 / 事件类 `03E6xxxx` 433）：电压·电流·有功·无功·功率因数块与全变量块（18 值），额定值/运行状态/输出类型/各调节值与时段调节/档案/触发限值，各类控制事件与电压越限·通信异常·清零·升级·校时记录。原先全部显示「未知数据标识」，现已逐字段展开",
            "新增扩展控制码 **`0FH` 主站请求 / `8FH` 从站应答**（无线转发透传帧：数据域 = 数据标识 + 透传数据，`L = 04H + 数据长度`，附录 I.3.3.1）；透传内容若命中扩展 DI 会二次展开",
            "解码规则按文档落实：数据切分以**「数据长度」列**为准（`数据格式`列仅作显示提示）；多字节 BCD 低字节在前；**功率块最高位为符号位**（0=发电为正 / 1=用电为负，范围 ±7999.9999，文档示例 0111=+7 / 1111=-7 已做 golden）；单相设备 B/C 相 `FF` 标注为「单相设备无该相」；事件块**每字节从左往右对应逆变器 12→1** 并逐项标注；调控结果枚举（00 成功/01 未调/02 失败/03 不支持/04 其他/FF 不存在）；`DI0` 双语义（变量/参数组=逆变器 1~12 或 `FF` 下挂全部；事件组=第 1~50 次，`0x32`=50）",
            "**单一来源**：扩展 DI 表只在新增模块 `dlt645_pv_ext.py`（纯逻辑无 Qt）定义一份，解析器 / 查询页 / Web 三处共用 `merge_pv_di_map` 合并；**未改动生成物 `dlt645_di.json`**（AGENTS.md §4.5 禁手改），合并冲突集实测为空",
            "**桌面与 Web 同步**：查询页两端均可检索扩展 DI（共 1781 条 = 1099 标准 + 682 扩展），解析呈现关键字段两端一致（对拍断言）",
            "**顺带修复组帧侧错配**（本次改动引入的副作用）：扩展 DI 进入组帧下拉后，`dlt645_frame_schema.build_di_fields` 把多值掩码当单值套模板——运行状态 `NN` 被当「通信地址」、时段调节块被当「日期」、事件块被当「时间」（682 键中 574 个推非裸模板，约 44 个形状明显不符）。现加最小守卫：多值掩码（`|` 分隔）一律走裸字节模板、`set=={\"N\"}` 需长度 ≥12；实测标准表 1099 条**零误伤**（无 `|` 掩码、无短全 N 掩码）；编码侧 `_encode_di_value` 同步加守卫保证模板与编码一致",
            "测试：新增 `test/test_dlt645_pv_ext.py`（**156 项**：DI 表合并/幂等/冲突集、682 键表驱动全覆盖、变量类 golden（含功率符号位边界）、全变量块 18 值、`DI0` 双语义、事件块逆变器字节序与调控结果枚举、参数类枚举与地址表、4 处歧义行存疑、`0F/8F` 透传含二次展开、兜底不回归、桌面 GUI 转表链、两端一致、文档一致性守卫、组帧守卫），登记 `release_check.py:CORE_TESTS`",
            "**变异反证 6 条**（全部实际观察到变红后再还原）：移除扩展 DI 分派（32 红）/ 去掉功率符号位（6 红）/ 删 `FUNC_NAMES[0x0F]`（4 红）/ Web 转表丢弃 4 元组解析值（5 红）/ 查询页不再合并扩展 DI（6 红）/ 组帧守卫回退（3 红）",
            "**存疑不臆造**（按 AGENTS.md「协议定义优先，禁止凭记忆推断」）：`04E60001` 尾部 3 字节、`04E62101` 接入端口 2 字节与末段 1 字节、`04E63002` 小数位、`03E61401` 电压数据小数位、`03E61403`（长度列与格式列互相矛盾）等均保留原始 hex 并标注存疑；`02E60FFF`（全变量块下挂所有值）文档未定义故未登记，命中时走既有兜底",
            "**范围外（另行立项）**：该扩展协议的**组帧**下发（写参数/调节命令）、645 虚拟表从站支持、附录 G 厂商逆变器协议（Modbus 等）、附录 I.3.3.2 的 698.45 透传（属协议8）",
        ],
    ),
    (
        "1.23.20",
        "2026-09-17",
        [
            "**协议11（HDC 1.0）应用层报文收口：不再有「看得到名字、看不到内容」的漏解析**（承接 1.23.19 的同类缺口排查）",
            "① `0x00A0 鉴权安全`（专属端口 `0x1A`）与 `0x00A4 配电信息上报` 原先落到「未识别的业务数据(0x0A0)」——现由 fallback 查 `MSG_ID_NAMES` 表统一命名（不再新增专用分支，从根上防「名字表与分派链两份手写清单漂移」复发）",
            "② `0x00A0`/`0x00A4` 的字段**不解析**并注明依据：这两个业务在 HDC 第4-3部分只有报文ID 表、无字段格式章节（已全文核实第1/4-1/4-2/4-3部分）→ 报业务名 + 原始数据，不臆造字段；新增常量 `MSG_ID_NO_FORMAT_DEFINED` 显式建模该规范事实",
            "③ 修正错误依据：有字段定义、仅「端口与已实现分支不匹配」的业务（共 44 种端口×业务ID 组合）原先也被说成「规范未给出字段格式」——事实错误；现分为 `⚠ 未按业务格式解析`（有定义但未命中分支，附当前端口）与 `⚠ 格式未定义`（规范确实无格式章节）两种措辞",
            "④ 端口白名单不再挡在通用头之前：`_parse_app_only` 与 `_parse_msdu_payload` 原先硬编码 `(0x11,0x12,0x1A)`，非白名单端口连端口号/报文ID/安全模式/控制字都不解析；现按「像不像通用头」判定，未知端口显示 `保留(0xNN)`（兼顾误粘完整 MPDU 仍走 FC 路径）",
            "⑤ 「是否应用层」改以 **MAC 头声明的类型字段**为准（表10 标准头 `48`、表13 单跳头 `128`；新增 `APP_MSDU_TYPES`/`IPV4_MSDU_TYPES` 单一来源），首字节启发式仅在无 MAC 头上下文时回退——修复双向误判（真实帧实测：声明 `48` 的帧被当「厂商扩展」、声明 `47` 的帧反被当应用层解析）",
            "⑥ `sec_mode != 0`（报文ID 高4位=信道安全机制，如 `0x2004` 完整性保护的校时）新增 `⚠ 安全保护` 提示行，说明数据域受保护、按明文解析的字段可能无效；该行已加入桌面与 Web 两端 `_GW_APP_META_FIELDS` 黑名单，不挤占批量摘要的业务名与关键字段位",
            "测试：新增 `test/test_hdc10_app_dispatch.py`（**94 项**：值域常量单一来源 / 命名与依据 / 非白名单端口通用头 / MAC 头声明驱动分派 / 回退路径不放宽 / 完整 MPDU 仍走 FC / 安全模式提示且校时字段零变化 / 真实帧 60 帧分派与声明类型逐帧一致 / fuzz 936+78 组合 / 44 种端口×业务组合措辞表驱动 / 两端摘要黑名单集合相等 / F821 守卫），登记 `release_check.py:CORE_TESTS`",
            "**基线对拍**：改动前后 60 帧全量快照，仅允许的 3 帧变化（2 帧由 MAC 头声明进应用层 + 其中 1 帧加安全提示；1 帧表外类型不再误进应用层），其余 57 帧逐行逐字节一致（sha256 指纹相同）",
            "**变异反证 5 条**（全部实际观察到变红后再还原）：移除 `APP_MSDU_TYPES` 分派 8 红 / 判据退回端口白名单 4 红 / 去掉 `MSG_ID_NAMES` 查表 11 红 / 移除安全提示行 6 红 / 去掉 `and not has_fc` 守卫 1 红",
            "**范围外（另行立项）**：抄表 DATA 域内嵌 645/698.45 报文展开；`hdc10_mme_parser` 未实现的 7 类 MMTYPE（代理变更 0x0003/0x0004/0x0005、过零NTB 0x000B/0x000C、网络诊断 0x004F、无线信道冲突 0x0080，真实帧已实测命中 0x000B）；IPv4 载荷深度解析；MME 分支 `except Exception` 静默吞异常",
        ],
    ),
    (
        "1.23.19",
        "2026-09-17",
        [
            "**修复 HDC 1.0（协议11）抄表报文解析崩溃**（用户报障：一条并发抄表报文选「应用层报文」级别解析时弹 `解析失败：name 'proto_ver' is not defined`）",
            "根因：`hdc10_parser._parse_meter_reading`（服务报文ID 0x001/0x002/0x003 三类抄表报文）在渲染「协议版本号」行时引用了**从未赋值**的局部名 `proto_ver`——同文件 `_parse_confirm`/`_parse_timesync` 等 6 个函数都写有 `proto_ver = b0 & 0x3F`，唯独本函数漏写；`ruff check --select F821` 全仓仅此一处",
            "**触发条件四条同时满足**（故自协议11 引入以来长期潜伏）：协议索引 11 + 解析级别「应用层报文(app)」+ 报文ID ∈ {0x001 终端主动抄表, 0x002 路由主动抄表, **0x003 终端主动并发抄表**} + 端口 0x11。默认「自动识别」级别先把数据当 MAC 帧解析、不经过该函数，所以一直没暴露",
            "修复：补 `proto_ver = b0 & 0x3F`（依据 HDC 1.0 第4-3部分 表3「下行抄表报文」字节0 bit0-5 = 协议版本号、§5.3.1.2「本版本取值固定为 1」；现场帧 b0=0x01 实测一致），该函数其余字段公式一字未动",
            "现场帧（88 字节，并发抄表）修复后逐字段验证：端口 0x11 / 报文ID 0x0003 / 协议版本号 1 / 报文头长度 2×4B=8B / 配置字 0 / 转发数据规约类型 3=DL/T698.45 / 转发数据长度 75 字节 / 报文序号 17543 / DATA 自偏移 12 起（内嵌 698.45 报文 `68 49 00 43 …`，帧尾 0x16 不计入 DATA）",
            "测试：新增 `test/test_hdc10_meter_reading.py`（13 项：现场帧 golden 逐字段 / 0x001·0x002·0x003 三类报文 / `auto` 级别 7 行基线回归（路径不同、零变化）/ DATA 偏移与帧尾自洽 / 短帧「过短」分支与 8 字节长度下限边界 / 全表行结构完整 / **F821 静态守卫**防同类复发），登记 `release_check.py:CORE_TESTS`；**变异反证**：删掉 `proto_ver` 赋值（内存变异，不动原文件）→ 精确复现 `NameError`",
            "注：lens/pyright 对同一批文件另报 4 处既有告警（`bcsha_phases` possibly unbound、`msdu_len` 类型收窄、`sys.stdout.reconfigure` 不在 `TextIO` 协议），经逐行核实均为**不可达路径/类型标注局限的误报**，按「最小修复」范围未改动",
        ],
    ),
    (
        "1.23.18",
        "2026-09-16",
        [
            "**应用层报文批量摘要显示业务功能与关键业务字段**（用户反馈：协议11 批量解析选「应用层报文」时摘要只有 `端口:18 | 报文:0x0030`，同一批 21 帧完全相同、无法扫读，而详情里其实有「开始升级/升级ID/升级时间窗/…」）",
            "新增统一提取规则 `_gw_app_biz_summary`（桌面 `main_gui` 与 Web `web_utils` 各一份、规则逐字一致）：**业务名**按两优先级取（① `── 业务数据 ──` 区头之后首个带缩进行的字段名——协议11 布局；② 「报文ID」解析值非 hex 时即业务名——协议10 布局）；**关键业务字段**取带缩进、非元数据、非分隔/业务名行、解析值非空且非「N字节」占位的前 2 个（`_GW_APP_SUMMARY_KEY_FIELDS` 常量可调）",
            "元数据黑名单 `_GW_APP_META_FIELDS` 收两协议字段名并集（端口号/报文ID/安全模式·安全机制/业务报文ID/报文控制字/协议版本号/报文头长度/控制·保留/数据长度/转发数据规约类型/转发数据长度/报文序号/规约类型/发送类型/MSDU类型），**不占**关键字段位；**关键字段扫描限定在「业务数据 / 应用层报文」段窗口内**（起点=区头行+1，终点=起点之后首个顶层行）——仅靠「有应用层才提取」的守门不够：真实 MPDU 在默认 auto/fc_pb 级别下 FC/MAC 字段（`版本`/`原始源TEI`/`定界符类型`/`网络类型`）排在应用层之前会占满关键字段位（复核用 `test/hdc10_real_frames.pkl` 实测：修复前 6/6 带应用层的表全部中招，修复后 0/6）",
            "摘要效果（现场帧）：协议11 `端口:18 | 报文:0x0030 | 开始升级 | 升级ID:2075013183 | 升级时间窗:120分钟`；协议10 `端口:升级业务 | 报文:开始升级(下行) | 升级ID:2075013183 | 升级时间窗:120分钟`（业务名已含于报文段时不重复追加）；物理层/网络层/测试模式摘要与失败帧摘要**逐字符不变**",
            "**Web 协议10 的分派按表类型分流**（原 `protocol_index in (9, 10)` 让协议10 整体走协议9 摘要函数——AGENTS §8 陷阱 31 记录的漂移）：**应用层报文**走与协议11 同一实现（本任务增强范围），**物理层/网络层帧保持原路径**（协议9 摘要函数对 TEI/发送类型等段覆盖更全，整包切换会让 104/120 张真实表摘要丢信息，实测后按表类型分流、不退化为准）→ 两端物理层段全量对齐属 `09-15-web-shared-parse-core`。该函数应用层段与桌面同口径（端口/报文ID 取解析值而非 comment 整句、补业务段与序号/规约/数据长度），**Web 应用层摘要文案因此变化**（如 `端口:升级业务`→`端口:18`、`报文ID:安全模式: …`→`报文:0x0030`）",
            "测试：新增 `test/test_gw_app_summary_detail.py`（42 项：纯函数两协议布局 / 协议11·10 端到端精确文案 / **用户 20 行样本真实批量解析**（每条带各自分钟数、摘要种类数==不同分钟数种类数）/ 元数据排除 / 网络层·空表·失败帧回归 / 两端对拍 / **真实夹具 auto·fc_pb·app 三级别**（关键字段不得混入 FC/MAC 头字段）/ Web 协议10 非应用层表不退化），登记 `release_check.py:CORE_TESTS`；**变异反证**：关键字段数置 0 / 提取短路 / 不排除元数据 三种变异均使断言变红（退出码 1；FAIL 分别 9 / 14 / 4，复核用等价旧版实现替换法测得 8 / 13 / 3），还原后 PASS=42",
        ],
    ),
    (
        "1.23.17",
        "2026-09-16",
        [
            "**修复协议11（HDC 1.0）批量解析解析不出前场日志行**（用户报障：粘贴 `Line NNNN: 时间戳: B1D[3] mrd:ar[24]:<hex>` 后弹「预处理后未保留有效报文内容！」，一帧都解析不出，而同样输入单帧解析正常）",
            "根因两个，都在批量解析的前缀剥离函数 `_strip_gw_new_gen_prefix` 里：① **解析级别来源读错**——它硬读协议10 的 `_gw_parse_level`，而协议11 的级别存在 `_hdc10_parse_level`（两个属性相互独立、界面共用同一个下拉框，见 `_on_gw_parse_level_changed`）；只要曾在协议10 下选过「应用层报文(app)」，切到协议11 后界面显示「自动识别」、批量剥离却按 app 规则过滤，而用户样本帧（`12` 开头）里没有偶字节 `11` → **整批被丢弃**。② **app 判据端口集过窄**——只认端口 `11`，而 HDC 1.0 应用层还有 `0x12`（升级业务，本批帧正是它）与 `0x1A`（鉴权安全），即便级别传对也会丢",
            "修复：`_strip_gw_new_gen_prefix(text, parse_level=None)` 新增级别形参，`None` 时取 `_current_parse_params()`（与**真正用于解析的级别同源**：协议10→`_gw_parse_level`、协议11→`_hdc10_parse_level`，单一分派点）；app 判据改为**端口集合**，集合按当前协议**取自解析器端口表**（`hdc10_parser.APP_PORTS` / `gw_new_gen_parser.GWNewGenParser.PORT_NAMES`）而非再写一份硬编码副本，import 失败才回落内置三元组——依据《双模通信互联互通技术规范 第4-3部分：应用层通信协议》§5.2.2「升级业务取值为 0x12，其他业务取值为 0x11」",
            "Web 端同步（`reflex_web/web_utils.py::strip_gw_new_gen_prefix` 增 `protocol_index` 形参 + 同一判据与同一来源；`reflex_web.py` 两处调用点传协议号）——Web 侧级别分派本来就是对的，只有 app 判据同病；新增**两端对拍断言**（同输入 × 协议10/11 × auto/app/pb_only/fc_only 输出逐字符相等）防再次漂移",
            "测试：新增 `test/test_hdc10_batch_strip_level.py`（29 项：纯函数矩阵 / 级别来源两向隔离 / 端口集合与解析器表对拍（含「必须含 0x12」防退回只认 11）/ 两端对拍 / **用户 20 行现场样本端到端**（协议11 + 协议10 残留 app → 20 帧全成功、不弹空内容警告）/ 协议10 回归 / 非 app 级别行为不变 / 真实 config.json 未被改写），登记 `release_check.py:CORE_TESTS`；已用**变异反证**自检：端口集合退回只认 `11` → 变红 9 项；级别来源退回 `_gw_parse_level` → 变红 1 项（核心回归断言）；两处同时退回时用户样本端到端精确复现现场缺陷（弹空内容警告、0 帧，FAIL=16），依次还原后全绿",
        ],
    ),
    (
        "1.23.16",
        "2026-09-16",
        [
            "**窗口 / 分栏 / 列宽状态持久化（任务 09-15-gui-window-state-persist）**：主窗口几何、`result_splitter` 比例、10 张关键表格的列宽在退出时存入 `config.json`、启动时恢复；配置菜单新增「恢复默认窗口布局」；带**屏外回落**（拔掉外接显示器后恢复的坐标不再可见 → 回落默认居中，不再出现“窗口跑到屏幕外”）与**非法值容错**（`config.json` 被手改成非法值时逐项跳过、不阻断启动）",
            "存储归属与写盘时机：状态存在**顶层 `window` 段**而不是 `ui` 段——`ui` 段每次都由 `ThemeManager.to_config()` **整体重建**，写进去会被下一次保存抹掉；只在 `closeEvent` 的**真实退出**路径写（最小化到托盘的分支提前 `return`，不写）。列宽按**列数校验**后套用（列数变了则丢弃旧值，避免按错位的宽度恢复），单列宽限 10~4000 整数",
            "**修掉本特性引入的“测试污染真实配置”副作用**（重要）：窗口退出时会写 `config.json`，而测试会构造并关闭主窗口 → 把 offscreen 合成出来的几何（实测 684×666 这类尺寸）写进**开发机的真实 `config.json`**，用户下次启动即被套用。两道防线：① `closeEvent` 增加 `_window_shown_once` 守卫——**从未真正显示过的窗口不写盘**（覆盖所有“构造即关闭”的测试路径与 `--parse/--file/--clipboard` 路径）；② 新增共享沙箱 `test/_config_sandbox.py`，接线到实测会写盘的 `test_app_exit.py` / `test_theme_settings.py`，并在 `test_pp_cli.py` 补上 `app_paths.data_path` 的 patch（`llm_preprocess_widget.save_config()` 走的是 `from app_paths import data_path` 那份绑定，只 patch `main_gui.data_path` 盖不住它）——该测试原有的「真实 config.json 未被改写」md5 断言因此恢复成立",
            "测试：新增 `test/test_window_state.py`（93 项：采集契约 / 内存往返 / 配置通道 / 12 组坏值容错 / 列数不匹配 / 屏外回落（打桩 `_is_rect_visible` 双向验证判据真的参与决策）/ 恢复默认 / 12 协议切换 / 退出→重启端到端），登记 `release_check.py:CORE_TESTS`；已用**变异反证**自检：把 `_apply_window_state` 改成空实现 → 测试变红 8 项，还原后全绿",
            "顺带：3 个测试文件的 `import _path_setup` 补上 `F401` 抑制（`# noqa: E402` 不压制 F401，任何 `ruff check --fix` 都会删掉这行 → `ModuleNotFoundError: No module named 'main_gui'`；约定已写入 `AGENTS.md §7`）；`test_theme_settings.py` 删除未使用的 `QDialog` 导入",
            "**GUI 死代码清理（任务 09-15-gui-dead-code-cleanup，纯删除 `main_gui.py` -301 行）**：删掉 5 组**重名方法**的死版本（Python 语义是后定义覆盖前定义，故删前面那批：`_refresh_serial_ports` / `_on_serial_open_clicked` / `_on_serial_connection_changed` / `_on_serial_error` / `_clear_layout`；逐组 diff 后确认前者或逐字相同、或为 `f58c863`「串口配置持久化」提交的有意重写且伴随占位项成对移除）；6 个零引用方法/函数（`_get_git_changelog` / `create_di_lookup_tab` / `load_example` / `export_single` / `_extract_direction_from_table` / `show_detail_dialog`）；10 个已跟踪根目录临时脚本（792 行）+ 3 个未跟踪临时脚本（`_generated_mapping*.py` 的数据已核对活在 `protocol_parser._get_f0_32_entry_name` 里，删除无损失）。删前逐项做了 `getattr` 动态派发扇扫（40+ 处全是读属性、无一取方法名）+ 注册表映射核对 + 全仓（含 spec/iss/json）零引用确认",
            "**修 `配置→模型API管理` 菜单失效**（清理时发现的真实功能回归）：该菜单项的 `.triggered.connect(self._show_llm_api_manager)` 被 `e1dd85e`（2026-08-21 协议11 提交）误删，菜单项从此点了没反应，而方法因「零引用」几乎被当死代码删掉。已恢复接线，并新增 `test/test_menu_wiring.py`（13 项行为式断言：类级打桩 + 真实 `action.trigger()`，断言每个菜单项都调用到对应方法；**变异反证**：拿掉 connect → 该用例变红）",
        ],
    ),
    (
        "1.23.15",
        "2026-09-16",
        [
            "**批量解析后台化（任务 09-15-gui-batch-parse-perf）**：原先点「批量解析」后剥离/提取/逐帧解析/逐行上表全在 UI 线程同步跑，33 MB 真实日志（49,532 帧）冻结窗口约 21 s 且无进度无取消。现拆为「主线程同步预处理（快照/行映射/前缀剥离/清洗/提取，~1.5 s）+ 后台线程逐帧解析」，新增 `batch_parse_worker.py`（`BatchParseWorker`，200 帧/片、背压回执、异常按帧隔离），工具栏加**进度条**与**取消**按钮（实测取消 10～15 ms 停止，远低于 1 s 验收线），取消后已完成结果保留且可看详情/导出",
            "批量解析 UX 修复（复核中实测）：取消落在**分片中途**时，已解析未满一片的结果原先被静默丢弃 → 状态栏「已解析 N」大于表格行数（N 不诚实）且这些帧白解析；新增 `_emit_cancelled()` 统一回传后再发取消",
            "**详情按需，常驻内存 229.4 MB → 20.6 MB**：`batch_results` 不再缓存每帧完整解析表（`_table_data`），改存 `_has_detail`/`_ed_type`（帧 hex 直接复用 `_input`，不额外存 `_frame_bytes`）；详情/导出/复制/时序图改走 `_get_frame_table_data(index)`（LRU 50 帧）按需重解析（实测 0.11 ms/帧，全量重建 5.55 s）",
            "**修详情重解析与批量解析不一致（实测 934/49,532 帧表格差 1 行）**：根因是解析器**跟帧可变状态**（`_efc_symbol_count`/`_ofdma_frame_type`/`_ofdma_station_count` 仅在特定分支被写，`parse_to_table` 未在入口重置）——同一帧在不同解析历史下结果不同。解法：worker 把「帧前状态」锁进记录 `_ctx`（仅非默认值时存，约 47% 帧），重解析前 `apply_cross_frame_state()` 复原（`None` = 写回默认值，清掉实例残留历史）。**未改解析器内部算法**（属 Out of Scope）",
            "**摘要过滤提速（0.87 s → 0.012 s / 次）**：`_on_batch_filter_changed` 整段用 `setUpdatesEnabled(False/True)` 包裹（`finally` 保证异常时也恢复重绘，代价几乎全在重绘而非循环）+ 行对象只取一次；关键词输入**250 ms 去抖**（`QTimer` restart 模式），状态下拉仍即时生效",
            "配套收口：`parse_batch` 拆为 `_prepare_batch_input()`（主线程同步，含快照与行号映射，语义不变）与 `_start_batch_parse()`；循环内 `_get_current_parser()` 提到循环外、worker 用**自有解析器实例**（`get_parser_class()()` + `build_gui_parser()`，不用共享单例，避免与单帧页/实时监控竞争）；单帧解析主体提为模块级 `parse_one_frame()` 供 worker 与详情路径**共用**；修异常行 `_type_name` 缺值导致「协议/类型」列读到上一帧残留的缺陷；`window.disconnect(worker)` 修正为 `disconnect(self)`（前者实为无效断连）",
            "测试：新增 `test/test_gui_batch_perf.py`（99 项：worker 分片/中途取消不丢结果/异常隔离/失败判定/记录形状/跨帧状态 helper/详情 LRU 与对拍/导出「包含表格数据」列/过滤 oracle 对拍+耗时+去抖+UI 心跳），登记 `release_check.py:CORE_TESTS`；`test_batch_snapshot_locate`、`test_batch_src_line_jump`、`test_ed_fallback_fix`、`test_ofdma_batch` 的同步假设改为 `test/_batch_wait.py::wait_batch()`（断言语义未变）",
        ],
    ),
    (
        "1.23.14",
        "2026-09-15",
        [
            "**Reflex Web 版新增独立产品首页（落地页）**：主页路由 `/` 改为介绍桌面客户端的首页，原 9 标签页工具页让位到 `/app`；`/share`、`/feedback`、`/feedback-admin` 路由不变。首页含 Hero（版本徽章 + 双 CTA + 窗口拟态截图）、关键数字条、12 张功能卡、12 协议支持表、命令行/系统集成快速上手、下载收尾区与页脚；全部颜色走 `theme_web` token（浅/深 + 5 强调色），≤900px 单列且顶栏换行",
            "新增 `reflex_web/reflex_web/landing_web.py`（约 1080 行）：**纯内容 + 纯展示组件，不 import `reflex_web`**（与 `web_utils`/`theme_web` 同向依赖，避免循环导入），版本号/exe 体积/截图/下载事件/主题控件一律参数注入 → 可脱离 State 与浏览器直接构建整页断言（`test/test_web_landing.py` 86 项）",
            "导航改造（4 处站内链接全部改指，无死链）：工具页顶栏品牌块改为指向首页的链接（不新增按钮，顶栏 `nowrap` 空间已紧张）；独立页「返回主页」→「在线工具」(/app)；独立页「管理员登录」与 `/share`「去解析并分享」、`/feedback-admin`「前往在线工具」均改指 `/app`（登录弹窗与反馈 Tab 只挂在工具页）",
            "主题控件抽为 `theme_controls_compact()`（工具页顶栏与首页顶栏**共用同一实现**，不再是两份）；首页顶栏作用域内把 `.app-header-select` / `.app-header-btn` 从「渐变底白字」改回 token 配色，并新增 `html.dark` 覆盖：深色模式下 `--accent`/`--accent-ink` 本身是浅色（`ACCENT_OVERRIDES_DARK`），强调色表面上的白字会糊 → 改用 `var(--bg)` 作字色",
            "State 新增 `download_exe_size_mb`（首页 CTA 显示 exe 体积，与历史版本行同算法）。**放弃**了「截图改走 `/api/download/...` 并删除 base64 字段」的原始设计：实测 dev 模式下 Reflex 前端跨源通信、**不代理任何后端路径**（`:3000/api/download/*`、`/download/*`、`/fbimg/*` 乃至 `/ping` 全部 200 + SPA HTML，只有直连 `:8000` 才是真资源，`.web/env.json` 的 `EVENT: ws://localhost:8000/_event` 佐证），相对路径图片在 dev 必然破图 → 沿用已验证的 base64 通道（`download_image_data_url` 保持不变）",
            "响应式修复：420px 视口下页面横向溢出 64px（根因 `.landing-nav-actions` 宽 389px 而父级 `overflow: visible`）→ 窄屏顶栏 `flex-wrap: wrap`；实测 360/420/768/1024/1440/1920 六档 `scrollWidth == innerWidth`",
            "顺带修掉顶栏一处写死的事实错误：版本徽章硬编码 `v1.13.0`（落后十几个版本，与首页/下载页显示的 `version.json` 版本自相矛盾）→ 抽 `version_badge()` 读 `downloads/version.json`（与客户端下载、首页徽章同一数据源），读不到就**不渲染**而不是显示假版本；`test/test_web_landing.py` 加守卫断言「徽章 == version.json 版本」且「顶栏不再出现 v1.13.0」",
            "`load_download_info` 复位块上提到「downloads/ 目录存在性判断之前」（复核发现）：原先 `downloads/` 不存在、或截图/version.json 被删除时，`download_image_data_url` / `download_version*` 等字段**不清空**，界面会显示上一次扫描到的陈旧版本号与截图；现在 11 个下载相关字段统一在函数开头复位（顺带删掉 `primary_exe is None` 分支里已冗余的三行复位）",
            "**Web 运行时数据外置（任务 09-16-web-data-externalization）**：反馈库/分享库/上传截图、发布管理上传的 exe（`downloads/`）、管理员口令（`admin_config.json`）原先都写在**代码目录内**（`<部署>/reflex_web/`），而升级多为「删掉旧部署目录 → 拷新包」⇒ 数据在**新程序启动前**就被删除；更糟的是两个构建脚本未排除运行时数据，会把**构建机的开发库**打进部署包（合并式拷贝时用开发数据顶掉服务器生产数据）。现新增 `reflex_web/reflex_web/app_data.py` 作为运行时路径**唯一来源**（`NW_WEB_DATA_DIR` → 冻结态 exe 同级 `nw_web_data/` → 回落代码目录=开发态现状），数据根默认位于**部署目录的上一级** `nw_web_data/`，由启动脚本注入变量（已设则不覆盖，可指到别的盘）；`feedback_model`/`share_model`/`reflex_web.py` 四处 getter/`run_app.py` 两个中间件全部改为消费它，删除 `FEEDBACK_DATA_DIR`/`FRAMESHARE_DATA_DIR` 两个测试专用变量（收敂为同一个）",
            "两个构建脚本（UV 离线 / 内嵌 Python）新增共用模块 `reflex_web/deploy_common.py`：忽略规则单一来源（排除 `data/`、`admin_config.json` 与 `downloads/` 里的运行时产物；`downloads/` 下的随包静态资源用**白名单**放行）、启动脚本片段（cmd/ps1/sh 三份都注入 `NW_WEB_DATA_DIR`）、`迁移数据.cmd/sh` 生成；删除失效的 `preserve_data_*`/`restore_data_*`——它搬的是 `<out_dir>/data`，而运行时真实路径是 `<out_dir>/reflex_web/data`，**该保护从未生效**（`离线部署.md` 里「重建时自动保留 data/」的承诺一并改写）",
            '顺带修掉单文件 exe 的数据清零问题（缺陷 C）：`reflex_web_exe.spec` 是 onefile，`sys._MEIPASS` 每次启动解包、退出即删，而 `run_app.py` 曾把它当作数据根 ⇒ 反馈库/分享库/downloads/口令**每次重启全部丢失**；冻结态现改为 `Path(sys.executable).parent / "nw_web_data"`（exe 同级，升级只换 exe）',
            "新增 `test/test_web_data_paths.py`（解析矩阵 env/冻结态/默认 + 消费方单一来源与源码级接线守卫 + 迁移幂等且绝不覆盖 + 构建产物排除运行时数据的 copytree 端到端 + 启动/迁移脚本模板注入与 `${VAR}` 无 `$` 回归守卫，登记 `release_check.py:CORE_TESTS`）；另附真实部署目录端到端验收：产物不含运行时数据 → 启动后反馈落在数据根 → **删除整个部署目录、重新生成一份、重启，反馈仍在**",
            "修复下载地址端口错乱（用户报障：部署在 8091 的实例点「下载客户端」跳到 `host:8000`）：根因是发布管理页/首页按钮用 `rx.config.get_config()` 的**构建期**端口（frontend 3000 / backend 8000）加 `socket` 猜本机 IP 拼绝对下载地址，单端口部署后端口被改错并写进 `version.json`（该 url 还被 GUI 自动更新读取，必须绝对地址）。修法：判定收口到 `web_utils.resolve_download_target` / `release_absolute_url` / `is_same_origin_serving`——**网页按钮走同源相对路径** `/download/<exe>`（任意 host/port 都对，且**自愈**历史 version.json 里写死的 `:8000`；仅当地址指向别的主机即外部托管时原样使用），**发布页默认地址/version.json 用当前请求的真实 host**（`self.router.headers.host`，不再猜 IP/端口）；删除两份重复实现与全仓无调用方的死代码 `set_release_url_from_host`；新增 `test/test_web_download_url.py`（35 项：纯函数矩阵 + 真实 State 的 `_download_target_url` + 源码守卫）",
            "部署易用性：两个部署构建脚本新增 `--port`（默认 8080），把端口固化进 cmd/ps1/sh 三份启动脚本与 `部署说明.txt`（目标服务器只对外开放某端口时双击即用，避免默认 8080 让人误判「部署失败」；命令行仍可 `--port` 覆盖）；新增 `docs/Web版局域网部署教程.md`（Windows 服务器·固定端口：防火墙放行、验证清单、首次配置、任务计划/NSSM 常驻、备份与升级、排错表），`reflex_web/离线部署.md`/README/AGENTS 同步指引",
            "自查修掉一处本次引入的 UX 回归：`downloads/` 若整目录排除，新部署站的**首页 Hero 截图与客户端说明会永久缺失**（这两样没有后台上传入口）→ 改为区分「随包静态资源」（`client_screenshot.png` / `client_readme.md` / `README.md` 进包）与「运行时发布产物」（`*.exe` / `version.json` / `archive/` 不进包），程序侧新增 `app_data.resolve_download_asset()`（数据根优先、缺失回落随包资源）并接入 `load_download_info` 的截图/README 两处",
            "测试与文档：新增 `test/test_web_landing.py`（100 项：内容不变式 / 与 `protocol_registry` 逐行对拍防漂移 / CLI 参数对 `main_gui` 真实解析分支 / 组件树与 testid 契约 / 缺图降级互斥 / 死链白名单 + **跨页面接线断言**（死链与 CLI 两条守卫均以**变异反证**确认能抓住回退——旧写法是「渲染由常量生成、白名单由同一常量派生」的自洽假绿，以及「`--parse` 子串存在性」被 `sys.argv` 元组判断满足的假绿）），登记 `release_check.py:CORE_TESTS`；`test_web_spectrum.py`、`test_web_theme.py` 的 `app.index()` → `app.tool_page()`；`reflex_web/tests/test_reflex_app.py` 的 7 处 goto 改 `/app` 并新增首页冒烟与「首页 → 在线工具」跳转用例；`reflex_web_exe.spec` hiddenimports 补 `reflex_web.landing_web`。**注**：`downloads/client_screenshot.png`（v1.12.0 空态）与 `downloads/version.json`（停在 1.14.13）建议随发布更新，首页直接读取",
        ],
    ),
    (
        "1.23.13",
        "2026-09-15",
        [
            '修复批量解析「预处理」命令链在中文输入法全角状态下不可用（现场现象：同为预处理的 `find "CSG"` 报「未知命令: find　＂CSG＂」，而无参数的 `hex_extract` 等能执行）。根因：全角空格（U+3000）与全角/弯引号（＂ “ ” ‘ ’）都不是 ASCII 字符，`shlex.split` 既不把它们当分隔符也不当引号 → 整串被当成一个命令名',
            '新增 `pp_cli.split_commands()`（GUI / Web 输入框共用）：先按原样拆分，**只有首个 token 不是已知命令时**才做全角→半角归一化重试（U+3000 / U+00A0 / U+2000–U+200A / U+202F / U+205F → 半角空格，U+200B 与 BOM 删除，＂“”‘’ → 半角引号），故「半角分隔符 + 参数里刻意保留全角字符」（如 `find "A　B"`）不会被改写；`main_gui._run_cli_preprocessor` 与 Web `parse_batch` / `run_preprocess` 三处调用点改走该函数（删除各自的 `shlex.split`）',
            "`pp_cli.parse_and_run` 未知命令报错增强：命令名含非 ASCII 字符时附转义形式与码位（如 `\\u67e5（含非 ASCII 字符 U+67E5）`），并补「半角空格分隔、半角双引号包裹」提示——全角/零宽字符肉眼不可见，旧文案无法定位；GUI 预处理命令框 tooltip、帮助对话框与 Web 预处理面板说明同步补半角书写规则",
            "新增 `test/test_pp_cli.py`（47 项：半角基准 / 全角·NBSP·零宽归一化 / 参数内容保护 / 错误提示码位 / 用户场景端到端 / offscreen `MainWindow._run_cli_preprocessor` 全角不弹错、非法命令仍报错、真实 config.json 未被改写），登记进 `release_check.py:CORE_TESTS`",
        ],
    ),
    (
        "1.23.12",
        "2026-09-15",
        [
            "Reflex Web 版解析 P0 缺陷修复（对齐桌面口径，10 条全部实测复现后修复）",
            "`_get_validator` 从未定义变量 `p` → 12 种协议「校验报文」全部报「校验出错: name 'p' is not defined」（异常被 verify_frame 兜底吞成文案）；改为复用桌面同一份 `protocol_registry.make_validator()`（该模块无 Qt 依赖，Web 可直接 import），删除 Web 侧 12 项硬编码校验器映射。**校验入参改用与 Web 解析一致的预处理**（清洗 + 头/尾剔除），避免「解析通过、校验失败」自相矛盾；注：桌面 `verify_single` 不做头/尾剔除，两端口径差异已记入 `AGENTS.md §8` 陷阱 31 与父任务子任务 `09-15-web-shared-parse-core`",
            "批量失败判定只看首行 `result[0][0]` → 解析器把 ❌ 行写在**表中途**的帧被标成「成功」（实测：协议9 `mac_only` 短 MAC 帧输入 `49 5C 2F AA BB CC DD EE` 时行0 是「解析模式」、行1 才是 `❌ 解析失败`，旧判定返回「成功」）；改为全表扫描「以 ❌ 开头的行」并取其说明作摘要，类型列固定「解析失败」（与桌面同列语义）；**顺带统一两侧空表语义**（空表 → 失败，桌面原 `any([])==False` 判成功属缺陷）与异常字面量（Web `错误/解析错误` → `异常`，带帧片段），桌面 `main_gui.parse_batch` 同步改为同一判据",
            "奇数长度 hex 被静默砍掉末位 nibble（截断/漏字符的报文被当作另一帧解析且无提示）→ 改为直接报错，文案与桌面一致（`输入长度为奇数，十六进制字符串必须是偶数长度！`）",
            "协议10/11「仅物理块PB」从不下发 `frame_type` → 协议10 实测落「⚠️ 未知帧类型 … 无对应解析逻辑」、协议11 恒按 SOF 解析；新增 `web_utils.parse_kwargs_for`（单帧与批量共用，消除两处重复的 3 段 if/elif）+ 协议10/11 的「PB帧类型」下拉（pb_only 时可见），协议9 补齐缺失的「仅MAC帧(mac_only)」级别与「PB帧类型」下拉（此前 `set_csg_pb_frame_type` 无任何 UI 入口，恒为 sof）",
            "ED..EE 监控包装「广西台体(gx, 8 字节公共头)」解析错位 1 字节：Web 无格式选择、只能走解析器内置的 PLC2.0 布局；现把桌面 `_detect_ed_wrapper` 的逐帧打分判别**下沉到解析器** `csg_new_gen_parser.detect_ed_wrapper`（+ `_parse_ed_wrapper` 支持双布局、`parse_to_table(ed_wrapper=None)` 可显式指定），桌面改为委托调用（删除重复打分与 `_ED_PB_SIZES` 常量）——**桌面在未勾选 ED 复选框时同样错位，本次两侧同时修好**；摘要侧（Web + 桌面）改按「含 `监控包装头`」判定并区分 `PLC2.0监控包装帧`/`广西台体监控包装帧`",
            "南网 DI 查询 AFN 列算错：`afn = di3 & 0x0F` 使所有 E8 前缀 DI 都显示 `08H`（实测「添加任务」应为 `02H`）→ 改为 AFN = DI1 并按 `AFN_MAP` 带出名称（与桌面 `main_gui.py:2234` 同口径）",
            "协议10 查询页数据源错误：此前直接复用协议9 的表（源码自述「后续可补充」）→ 改为读取 `GWNewGenParser` 自有 7 类表 49 条（报文ID/端口/定界符/MSDU/规约/发送类型/广播方向，含安全机制说明），查询列补「说明」列",
            "协议8 查询页「属性/方法」列恒为 `-` 占位 → 从 `OILookup` 的 `OI_TO_CLASS_ID`+`CLASS_ID_MAP` 填充（与桌面 `_load_oad_map_data` 同口径）",
            "报文工具 CRC-24 参数错误（`rev=False`，实测 `0xEAC98F`）→ 改为 `rev=True`，与协议9/10/11 三处解析器及桌面报文工具一致（实测 `0xFC4D81`）；CRC-32 经 200 组随机输入实测两端等价，未改动",
            "新增 `test/test_web_parse_fixes.py`（75 项：纯函数 / ED gx 双布局端到端 / pb_only frame_type 端到端 / 查询页 AFN·协议10·698 属性 / 校验器工厂 / CRC 同口径 / reflex `State(_reflex_internal_init=True)` 真实实例 / **驱动 `parse_batch` 的批量端到端**），登记进 `release_check.py` CORE_TESTS；桌面回归 `test_ed_gx_wrapper`(23)/`test_ed_fallback_fix`(15)/`test_csg_summary`/`test_csg_sequence_model`/`test_csg_batch_prefix`/`test_gw_monitor_summary`(18) 全过",
            "批量链路同口径化：`mac_only` 级别下 Web 前缀剥离此前走 FC 扫描分支 → 8 字节 MAC 帧整行被丢弃（实测 0 帧），改为与桌面直通（`main_gui.py:4942`）；批量逐帧不再静默裁剪奇数长度（交由 `bytes.fromhex` 报错并记「异常」，摘要带帧片段）；异常状态字面量 `错误/解析错误` → `异常`，完成文案分别统计成功/失败/异常",
            "审计勘误：原只读审计提出的「Web 剔除不幂等（连点两次 = 二次裁剪）」经实测**不成立**（Web 每次从原始 `frame_hex` 重算，本就幂等；按该结论加缓存反而会让第二次解析拿到未剔除字节，已在实施中撤销），改以纯函数 `strip_frame_bytes` + 「同输入重复调用结果一致」断言把该不变式钉住",
            '复核（trellis-check 子代理）修复：① **桌面快捷解析小窗的 ED 路径漏传 wrapper** → 广西台体(gx) 帧仍按 PLC2.0 9B 头错位 1 字节（复核实测业务偏移 15 而非 14）；调用点补 `wrapper=self._ed_wrapper_for_frame(...)`，并把 `main_gui._parse_ed_monitor_header` / `_extract_business_from_ed_frame` 的 `wrapper` 默认值由硬编码 `"plc2"` 改为「None = 按当前下拉/逐帧自动识别」，`test_ed_gx_wrapper.py` 增 3 条默认路径断言（26 项）。② **打包声明**：`validator/__init__.py` 补齐 `GWNewGenValidator`/`HDC10Validator` 的 re-export（`make_validator` 走 importlib，PyInstaller 静态分析看不到 → 此前桌面 spec 缺 `validator.gw_new_gen_validator`、Web spec 缺 `validator.hdc10_validator`/`hdc10_*`）；`reflex_web_exe.spec` 补 `protocol_registry`/`parser_registry`/`hdc10_parser`/`hdc10_mme_parser`/`validator.hdc10_validator`，`debug_web.spec` 与 `南网协议解析工具.spec` 补 `protocol_registry`/`parser_registry`（后者另补 `validator.gw_new_gen_validator`）。③ 文档：协议10 查询页关键词匹配含「说明」列（Web 为桌面超集，已知差异写入 `AGENTS §8.31`）；AGENTS §1 能力差异描述限定到协议范围、`MyAppVersion` 过期陈述改为随 `--sync-iss` 同步',
            "**Web 版新增「频谱图」常驻标签页**（任务 09-15-web-spectrum-plot，与协议无关）：桌面 `spectrum_widget.py` 的**纯逻辑层（前 ~950 行，零 Qt 依赖）被 Web 直接复用**（参数校验/trace 日志清洗/刻度/标记吸附/峰值搜索/积分带宽全部同一实现），新增 `reflex_web/reflex_web/spectrum_web.py` 只做 SVG 坐标换算（纯函数），Qt 的 QPainter 自绘换成 SVG（网格 10×N 格、顶格=参考电平、刻度/标签/参数注记/状态行）；功能对齐桌面：频率四字段双向联动与单位换算、RBW/VBW/检波/50Ω 换算/纵轴自动适配、trace 粘贴（含日志行清洗提示与报错语义）、点击加标记 M1~M6（每个标记固定配色、图上竖虚线/圆点/标签与标记表同色）、标记表 Δ 标注 `M?↔M?` 与 Δ 参考切换、峰值搜索/删除/清空、积分带宽（半透明带 + 两条点划线边沿 + `IBW Σ` 注记 + 带内积分功率含 RBW 归一化口径）、导出 PNG（前端 SVG→canvas，零新增依赖）；新增 `test/test_web_spectrum.py`（64 项：复用守卫 + SVG 几何 + State 端到端 + 组件树），登记进 `release_check.py:CORE_TESTS`",
            "Web 批量解析结果**搜索/筛选**（口径同桌面 `_on_batch_filter_changed`）：摘要卡片新增搜索框（匹配 **摘要 / 协议类型 / 帧 HEX / #序号**，大小写不敏感）与状态下拉（全部/成功/失败/异常），过滤作用于**全量**摘要（不限于当前页）并接上分页——过滤后回到第 1 页、页数与行号照旧；有关键词或筛选时显示 `显示 N / M`，选中帧被过滤掉时自动清空右侧详情；帧 HEX 只存后端私有摘要行（不下发前端，前端载荷与改造前一致）；新增 `web_utils.filter_batch_summaries` 纯函数与 `BATCH_STATUS_FILTERS`；`test/test_web_batch_paging.py` 扩至 57 项（含 249 行端到端：按 HEX/类型/#序号搜索、三种状态筛选、过滤后翻页、选中清理、清空复位）",
            "**Web 版主题系统**（任务 09-15-web-theme-system）：新增 `reflex_web/reflex_web/theme_web.py`（纯逻辑：6 个预设主题 + 5 个强调色 + 3 个模式 + CSS token 表 + 客户端脚本生成）；顶栏加「主题」下拉（预设 / 强调色 / 模式）与模式循环按钮（浅色→深色→跟随系统，图标随模式变化）；自研 token 层 `--bg/--card/--border/--text/--muted/--accent/--ok/--warn/--danger/--grid/--trace/--sp-m1..6`（浅色取改造前原值 → 与 1.23.11 观感等价，深色只覆盖 token），组件与 `GLOBAL_CSS` 里 **215 处硬编码色值全部 token 化**（组件区已无裸 hex）；Radix 组件通过 `rx.theme(accent_color/gray_color/radius=ThemeState.*)` 跟随，独立页面（/share、/feedback）也挂主题样式与启动脚本；选择写入 `localStorage['nw-theme']`（刷新保持，用 class 观察器兜住 Reflex ThemeProvider 挂载后的类覆盖竞态），并同步 provider 读取的 `theme` 键；频谱图 SVG（网格/坐标轴/迹线/积分带/标记）与标记表配色改为引用 `var(--sp-mN)`（由 `spectrum_widget.MARKER_COLORS_*` 生成，单一来源）→ 深色下画布一并跟随；新增 `test/test_web_theme.py`（89 项：预设/维度清单、token 契约与浅色等价、CSS 结构、标记配色单一来源、ThemeState 端到端、组件树与无裸 hex 守卫）",
            "修复主题控件引入的两处回归 + 一处既有缺陷：① 独立页面顶栏被新增的主题下拉挤没了「返回主页」等导航 → 主题控件只在主页渲染，且所有页面统一注入主题样式（此前 /share、/feedback 连 GLOBAL_CSS 都没有，改用 token 后顶栏背景一度变透明）；② 顶栏渐变与强调色作用域改挂到页面根容器（header 在 app-container 之外，原先切强调色时顶栏不变色）；③ 报文分享卡片把 `str(Var)` 当文本渲染出 `(isTrue (item_rx_state_?)…)` 垃圾串 → 改用 `item['id'].to_string()`",
            "Web 批量解析界面：摘要改为**分页**（全量摘要留后端、前端只同步当前页；首页/上页/下页/末页 + 每页 100/200/500/1000 条，行号跨页连续；单页 100 条约 25KB delta，替代原先「截断到 300 条 + 24MB 整批序列化」的做法）；摘要区与明细区高度改为随视口（`calc(100vh - …)`，不再写死 360/350px）；内容容器与顶栏放开为全宽（原 `max-width:1320px`）；选中行高亮改用 `class_name=rx.cond(...)`（`style=rx.cond({...})` 在本项目实测不落到 DOM，属既有缺陷）；新增 `web_utils.paginate/page_of` 与 `test/test_web_batch_paging.py`（25 项，含 250 帧端到端翻页/跨页选中/每页条数切换）",
        ],
    ),
    (
        "1.23.11",
        "2026-09-15",
        [
            "南网查询页「添加/删除自定义DI」收口为共用单源：新增 `custom_di_store.py`（纯逻辑无 Qt：JSON 读写/单字节 hex 校验/键解析/upsert/批量删除），`protocol_parser` 三处读写委托之（未知字段不丢），`main_gui` 与 `lookup_pages` 简化页共用同一份 `apply_custom_di_add` / `delete_selected_custom_di_interactive` 实现",
            "行为增强：重复 DI 由「直接拒绝」改为**覆盖确认**（提示区分「已添加/已覆盖」）；删除支持**多选批量**（DI 表开启 ExtendedSelection，提示带条数与被忽略的内置条数）；未选中/仅内置 DI 给出可读提示；新增行同步合并进解析器 `DI_COMBINATION_MAP`（单帧解析即时生效）",
            "`lookup_pages.py` 简化版查询页两枚死按钮（弹「功能待实现」）改为真实增删；DI 表格刷新改走 `state` 字典（刷新后重建列表，避免闭包引用陈旧 `di_data`）",
            "新增 `test/test_nanwang_custom_di.py`（92 项：store 纯逻辑 / 未知字段保留 / 非法 JSON 容错 / 沙箱隔离真身零改动 / MainWindow offscreen 增删·覆盖·内置拒绝·多选批量·重启保持 / 简化页 / 源码无「待实现」反例），登记进 `release_check.py` CORE_TESTS；附带修复 `test_plc_rf.py` 在 GBK 控制台 print ✓ 崩溃（补 UTF-8 重配置），`release_check.py` 子进程统一注入 `PYTHONIOENCODING=utf-8` 且报告输出容错",
        ],
    ),
    (
        "1.23.10",
        "2026-09-14",
        [
            "批量解析摘要体现测试帧的测试模式：协议9（新一代载波）业务标识 `0xF0` 测试帧、协议10/11（国网新一代/HDC 1.0）通信测试/检测扩展命令，摘要列现在会带上**测试模式**内容——`测试模式:PLC物理层透传测试模式(3)`（协议9 表61）、`测试模式:HPLC物理层透传测试模式(3)` / `测试模式:安全测试模式(13) | 安全测试模式:SM3算法测试`（协议10 检测扩展命令，含安全/新一代子模式）",
            "测试帧没有「测试模式/配置操作」字段时回退到可读信息：`测试ID:频段切换命令`（协议9 测试ID 0/1/2 类）、`扩展ID:Bitloading表下发`（2.0测试）、`通信频段:0x02`（测试数据区）、上行测试帧 → `测试帧上行（确认/否认，无数据单元）`；非测试帧摘要**逐字符不变**（helper 无痕迹时返回空串，不追加）",
            "新增 `MainWindow._extract_test_mode_content(table_data)`（staticmethod，纯逻辑）：按「名称/数值」双槽探测字段（协议9 表61 名称在 comment、协议10 名称在 parsed），过滤协议9 恒定输出的占位子模式行（「安全测试模式（仅测试模式13生效）」）；协议9 摘要走 `_extract_csg_core_content` 的**首个分支**（测试帧帧类型为「命令帧」，不提前返回会被通用命令分支淹没），协议10/11 在既有片段之后追加",
            "测试：`test/test_csg_summary.py` 去掉文件内复刻的摘要逻辑（原来那份已与产品实现漂移：新实现输出「网络管理消息」「业务标识:确认(0x00)」，复刻版是「网络层」「业务标识:确认」），改为复用 `MainWindow` 未绑定方法（Host 宿主，免 GUI 驱动），并新增**整帧→解析→摘要**用例覆盖 gate 与分支接线：真实抓包 0xF0 帧 / 1.0 测试帧 / 2.0 测试帧（扩展ID）/ 上行测试帧 / 非测试上行业务帧（sid 0x01/0x03/0x04/0x06）回归网；`test/test_gw_monitor_summary.py` 新增检测扩展命令模式 3、13、15 与模式 1（括号去重）、模式 0（无片段）五例",
            "复核（trellis-check 子代理）修复：① 模式15 的 `新一代测试模式` 取到 comment 描述文本（`转发数据规约类型字段扩展为新一代测试模式`）而非子模式名 → 去掉描述文本黑名单，改为「**parsed 非数值则名称在 parsed，否则在 comment**」的槽位探测（两个协议槽位相反），现输出 `新一代测试模式:CCO信标机制切换`；② 名称自带括号时重复括号（`保留(14)(14)`）→ 已带括号则省略模式号；③ `上行负载` 行名被 4 个非测试上行业务共用，helper 单独调用会误报「测试帧上行」→ 该分支要求表内 `业务标识` 自证为 0xF0，且协议10/11 只在三个哨兵行存在时才调用 helper；④ 新增用例改为整帧→摘要（原版本直调 helper，gate 写错也测不出）",
        ],
    ),
    (
        "1.23.9",
        "2026-09-14",
        [
            "新增「频谱图」标签页（常驻，与协议无关）：按频谱仪口径配置扫描参数——起始/终止/中心/扫宽四字段**双向联动**（改起始/终止重算中心与扫宽，改中心/扫宽重算起止；扫宽非正或推出非正起始频率时拒绝该次修改并提示）、四字段共用频率单位（kHz/MHz/GHz）、RBW/VBW（各自单位，留空则不标注）、参考电平、每格 dB（0.1~20）、纵向格数（4~12）、幅值单位（dBm/dBμV/dBmV，可选「输入按 dBm，50Ω 换算」：dBμV=dBm+107、dBmV=dBm+47）、检波方式（峰值/准峰值/平均值/RMS/采样）",
            "输入单条 trace 的全部扫频点数值（空格/制表/逗号/分号/换行/中文全角分隔符均可，支持正负号与科学计数），点数即频率轴点数、等间隔线性均分；非法 token 报「第 N 项 + 原文」且不静默丢弃、不破坏已有图形（AGENTS.md §8 陷阱 23 口径）；越界点裁剪到边缘并在状态行提示个数",
            "绘制：QPainter 自绘仪器式屏幕（横向固定 10 格 × 纵向可配格数，顶格=参考电平、每格 −dB/div；勾选「纵轴自动适配」后改按数据 min/max 留 5% 余量等分）；标题+参数注记（起止/扫宽/RBW/VBW/检波/参考电平/每格/点数/单位）随图渲染，可直接贴报告；「导出 PNG」默认 1600×1000；浅/暗双调色板并暴露 restyle_for_theme 接入主题切换",
            "实现：新建 spectrum_widget.py（前半纯逻辑层不依赖 Qt：SpectrumParams/SpectrumTrace/parse_levels/validate_params/freqs_for/y_range/y_ticks/x_tick_labels/format_*/resolve_freq_inputs + 测量层 Marker/markers_for/peak_indices/next_peak_index/delta_text；后半 Qt 层 SpectrumCanvas/SpectrumWidget，paintEvent 与导出 render_image 共用同一 _paint，绘图区几何由 plot_rect() 单一来源同时供绘制与鼠标换算）；main_gui 仅 3 处接线（import／常驻 tab 图标 chart-spline／_restyle_for_theme 钩子），不改协议可见性逻辑",
            "测量：鼠标悬停绘图区即出十字光标 + 读数框（最近数据点的频率/幅值，吸附不插值）；左键点击添加 MARK 标记 M1~M6（吸附最近数据点、超出上限给提示）——**每个标记一种固定颜色**（M1~M6 与序号绑定，浅/暗主题各一套；图上竖虚线/圆点/M? 标签与标记表行文字同色，便于图↔表对应，切主题同步重算）；标记以**频率为锚点**，重绘/改单位/切纵轴口径后自动重新吸附、超出扫描范围自动丢弃（丢弃提示追加在点数状态之后不覆盖）；「峰值搜索/下一个峰值」作用于标记表选中行（无选中即最后一个标记，无标记则在峰值处新建；唯一显著峰时明确提示不移动），「删除标记/清空标记」管理标记表（删除后连续重编号）；标记表列 `标记/频率/幅值(单位)/Δ频率(哪两点)/Δ幅值(哪两点)` 且**仅在存在标记时显示**（不压缩画布高度）",
            "两点测量与基础计算：Δ 一律**标注是哪两个点之间的差值**（单元格与测量栏都带 `M?↔M?` 前缀，如 `M1↔M3 560.348 MHz`、`Δf(M2↔M3) 159.652 MHz Δlevel -0.30 dB`）；新增「Δ 参考」下拉切换参考标记（默认 M1），切换后表格 Δ 列与测量栏同时重算；峰值/谷值（频率 + 幅值）常驻测量栏；「下一个峰值」按 3 dB 显著度（标准 key-col 定义）环形搜索局部峰，显著度用**单调栈 O(n) 预计算**（原逐点扫描实现最坏 O(n²)，16000 点实测 3.74 s 冻结界面 → 现 5.3 ms，9000 组数据逐例等价）",
            "积分带宽（IBW）：参数区新增分组——中心频率（与四字段共用频率单位）+ 积分带宽（kHz/MHz）+「显示积分带宽（两条竖线）」开关；勾选后图上出现两条**点划线竖线**（独立配色，与 6 个标记颜色都不撞色）+ 边沿间半透明填充带 + 带内顶部 `IBW 460–660 MHz` 标签，画布右上读数框追加一行积分功率",
            "积分功率计算：对落在 [低边沿, 高边沿] 内的点做线性功率求和后转回 dB，并按「频率步进 / RBW」归一化（RBW 未填则不做归一化并在读数注明）；单位偏移在求和前后抵消，故 dBμV/dBmV 口径直接可用（dBμV 结果 = dBm 结果 + 107）；读数同时给出带宽内点数；带宽超出扫宽按交集积分并标注「超出扫描范围」，与扫宽无交集则不填充并标注「无交集」",
            "trace 文本预处理（日志行清洗）：直接粘贴带日志前缀的行即可绘制——每行自动取**行尾真实数值**（`2026-09-14 12:25:43 015: 流程日志：2026-09-14 12:24:26:295 --USER--MTC@DESKTOP-417FFS5: -51.564613` → `-51.564613`），数值后可带电平单位后缀（`-51.5 dBm`）；规则顺序即优先级：空行忽略 / 该行全为数值则全部采纳（支持一行多值）/ 日志行行尾取电平值 / **日志行有数值却拿不到行尾数值 → 报错并指出行号**（静默丢行比报错危险）/ 日志行整行无数值（头部行、纯时间戳行）→ 跳过计数 / 非日志行含非法 token（`12a3`、`abc`）→ 报「第 N 项不是有效数值」",
            "两处防误提取：数值前必须是分隔边界（`12a3` 的尾部 `3` 不提取）；行尾形如 `HH:MM:SS[:.]mmm`（含 `12:24:26`、`2026/09/14 12:24:26`）按时间戳跳过——用户日志里每行都嵌 `12:24:26:295`，否则毫秒会变成 295 dBm 假点；单位白名单只含电平单位（`Hz/MHz/GHz` 刻意排除，避免「中心频率 600 MHz」被当电平）；行尾非有限值（`1e999`）与纯数值路径同口径拒绝",
            "清洗统计与提示：解析结果携带 `TraceInput`（有效行/采纳/跳过/日志行，不变式 `lines_total == lines_used + lines_skipped`），状态行显示「已清洗 N 行日志，跳过 K 行无数值」，切换「纵轴自动适配」不吞该提示；全无值输入报「请输入 trace 数值（已跳过 K 行无数值日志行）」；trace 输入框文案与占位符同步说明可直接粘贴日志；`parse_levels()` 对纯数值输入逐位等价于旧实现",
            "零新增依赖：不使用 matplotlib（已被 南网协议解析工具.spec 显式排除）与 QtCharts，PyInstaller spec 无需改动（无新增 datas/hiddenimports）；测试：新增 test/test_spectrum_model.py（225 项纯逻辑）与 test/test_spectrum_gui.py（135 项 offscreen）并纳入 release_check 清单",
        ],
    ),
    (
        "1.23.8",
        "2026-09-12",
        [
            "645虚拟表新增「模拟设置 · 随机产生事件」：勾选后每次读取事件状态字（DI 04001501 主动上报状态字 = 载波模块反复轮询的“电能表事件状态字”，`BS96` 12 字节）都返回一个新的随机值且与上一次不同；不勾选时读「档案数据」的值（新增默认项 12 字节全 0 = 无事件，读多少遍都一样）。离线与串口两条应答路径同时生效，生效时收发日志标注「◈ 随机事件状态字 04001501 = <24hex>」；勾选状态持久化到 dlt645_sim_data.json 的 random_event（旧文件无该字段按 false，导出/导入同步）",
            "修复事件状态字应答被截断（实测缺陷）：engine._data_type_for 依次探测 dlt645_di_lookup 的 get_info/get/lookup —— 该方法真实名为 get_di_info，导致 04001501(BS96/12B) 落到兜底掩码 XXXXXX.XX 被编成 4 字节（请求 04001501 应答 L=08、解析成 00000000）。改为优先 dlt645_frame_schema.get_di_info（与组帧路径同一权威源，读 dlt645_di.json）取 data_type+length 并传 encode_value(nbytes=length)：应答回到 L=0x10（4 字节 DI + 12 字节数据）",
            "新增 dlt645_sim/dynamic_data.py（纯逻辑无 Qt）：EVENT_WORD_DI=04001501 / EVENT_WORD_BYTES=12 + RandomEventWord（next_value() 返回 24 位 hex，保证与上一次不同、碰撞重抽；rng 可注入便于测试；reset() 清记忆）。引擎新增 event_word_source 注入参数与 last_note；产生器异常/返回非法值时回落档案值并记 last_error，不抛栈。**状态放 GUI 持有的实例**——引擎每帧重建（串口线程收帧循环内 _engine_factory()），放引擎里“每次变化”会失效",
            "修复 645虚拟表档案 JSON 读写全线失效：dlt645_sim_data.json 的保存/静默保存/加载/导出/导入全部引用 json.dumps/loads，但 `import json` 在此前的并行改动中被误删（替换成 import threading）——「保存」按钮抛 NameError、加载被 try/except 静默吞掉（用户档案与表地址重启后不生效）、静默保存只记「⚠ 新地址持久化失败」。已补回 import json",
            "测试：新增 test/test_dlt645_sim_event_word.py（66 项）——类型/长度修复（L=0x10、解析器读回 24 hex、常规 DI 类型不变）、默认不变化（连读 3 次逐字节相同且全 0、档案非 0 时按档案回）、随机模式（连读 20 次相邻互不相同且 20 个不同值、不影响其它 DI）、RandomEventWord 单测（含注入碰撞桩验证重抽）、异常容错（抛异常/非法值/空串/长度不符均回落档案且不崩）、offscreen GUI（小节与勾选框、勾选注入、离线两次响应不同、取消后恢复不变化）、持久化（写出/重载保持/旧 JSON 加载与导入均按 false 回落）、COM1↔COM2 真实回环（连读两次数据不同、取消后两次完全相同）。GUI 用例统一沙箱到临时目录，不碰用户 dlt645_sim_data.json",
        ],
    ),
    (
        "1.23.7",
        "2026-09-11",
        [
            "645虚拟表新增「模块版本查询（LME 自定义下发）」：虚拟表首次具备**主站方向**能力，按《LME产品相关信息生产运维接口手册_V2.4》向 HPLC 模块索取版本信息——三个一键按钮「读模块版本(4.2)」「读内部详细信息(4.6)」「设置(4.7)」：4.2 读单模 STA 详细版本（DI=04FFAAF9，C=11H，无数据单元，一条请求拿回外部厂商/芯片/MCU/APS/NWK/PHY/DSP 版本与编译时间）；4.6 读双模 STA 内部信息条目（DI=FF00DD01，按「分类/数据ID」指定条目，留空 = M=0 读模块全部支持条目，分类1 即程序信息/内部版本主体）；4.7 设置双模条目（C=14H，按「分类/数据ID:数据hex」构造，TLV 头编码格式/长度按 LME_INFO_ENTRIES 定义自动填，5bit 上限 31 字节超限即报错）",
            "新建 dlt645_sim/lme_query.py（纯逻辑无 Qt）：build_single_sta_query / build_dual_query / build_dual_set / build_query / decode_reply / reply_rows / describe_frame / describe_items；帧封装统一调 DLT645FrameGenerator（地址序/+0x33/CS/68…16 唯一权威），4.6 复用 pack_lme_query_request，解析复用 DLT645Parser 已内置的 LME 深度解析——不自造第二套 645 封装或 LME 解码",
            "645虚拟表运行页新增分组（串口从站与离线模拟之间）：目标地址（默认 AAAAAAAAAAAA = 手册 §5.1.1 虚拟电表上位机点对点口径）+ 三个读取/设置按钮 + 条目行（4.2 自动隐藏清空、4.6/4.7 切换语义与 tooltip）+ 只读帧框（等宽）+ 「下发到串口」/「复制hex」；点按钮即组帧→帧框→日志（控制码/长度/数据域），串口已监听则自动下发，未监听只记提示不弹窗打断；4.7 写类下发前弹确认框列出条目明细（可能改模块参数：本地接口默认信息=波特率/校验位、继电器控制等），取消则帧保留不下发；组帧失败弹中文提示且不覆盖已有帧框",
            "串口从站线程新增 slave_frame 信号：收帧按控制码 D7（idx8 & 0x80）分流——DIR=1 的帧（模块发来的回包）不再回「收到非主站帧，忽略」，而是上报 GUI；DIR=0 请求路径（引擎应答 + 回写）完全不变。回包经 DLT645Parser 解析后 LME 字段逐行填入「最近响应帧解析」表，日志给出一行摘要（接口名 + 厂商/芯片/版本/编译时间）",
            "645虚拟表「离线模拟」支持 DIR=1 回包直解：贴入模块回包点「生成响应」时直接解析展示（日志「检测到从站回包，直接解析」），无硬件也能核对 4.2/4.6/4.7 回包；DIR=0 请求路径保持原从站应答行为",
            "测试：新增 test/test_dlt645_sim_lme_query.py（95 项）——4.2 请求帧与手册 §5.1.1 发送示例逐字节一致（68 AA AA AA AA AA AA 68 11 04 2C DD 32 37 53 16）、4.6 M=0/M=1/M=2 数据域位域断言、4.7 TLV 头位域与 5bit 上限、手册接收帧（135B，CS=0x56）字段逐项回归（LH/60/V0102/2020-11-10/v0244/N0230/P2008/V4028/硬件信息长度0）、截断帧「⚠ 数据不完整」容错、offscreen GUI（三按钮/条目框显隐/失败不覆盖帧框/4.7 确认框/回包填表/离线 DIR=1 直解），并在本机 ELTIMA COM1↔COM2 虚拟串口对上完成**真实端到端**验证（下发 4.2 请求 → 对端逐字节比对 → 注入手册回包 → 自动解析进结果表）",
            "spec hiddenimports 补 dlt645_sim / dlt645_sim.engine / dlt645_sim.archive / dlt645_sim.lme_query（此前 dlt645_sim 未显式声明，exe 打包保险）",
        ],
    ),
    (
        "1.23.6",
        "2026-09-11",
        [
            "GUI 新增第 7 套主题「云母（Mica · Win11）」（theme_settings.py）：全不透明静态实现——底色取 Win11 云母在典型壁纸下的均值色 #f3f3f3，配色按 Fluent 浅色规范（#005fb8 主色/细扁平滚动条/下划线式输入焦点/药丸选项卡），Win11 另启用 DWM 圆角窗（DWMWA_WINDOW_CORNER_PREFERENCE=ROUND）。刻意不接 DWMWA_SYSTEMBACKDROP_TYPE 真底衬：那要求 WA_TranslucentBackground 透明窗口，而本 GUI 大量样式（GroupBox 标题等）直接绘于父容器表面，透明窗口下低 alpha 每帧混合擦不净旧像素，产生严重重影（毛玻璃靠亚克力模糊掩盖、云母平坦底色下原形毕露）——观感几乎一致、零重影；透明度滑杆对该主题走 setWindowOpacity 窗口级通道（build_mica_qss 不再缩放表面 alpha）；MICA 专属按钮调色板（secondary 深灰配白字，兼容统一 builder 的 p['text'] 键）",
            "test_theme_settings 修复过时断言并扩至 48 项：apply 早已在主题 QSS 末尾追加统一按钮 QSS（1.23.x），原 styleSheet()==裸qss 全等断言自那起 12 项恒失败（HEAD 对照证实 pre-existing）→ 改前缀匹配+按钮段存在断言；云母新增逐关键表面「不得含 rgba 背景」不透明断言（重影回归防线）+玻璃专属行显隐；透明度断言钉到主窗口表面层（基础 QWidget 极低 alpha 非契约）",
            "修复统一按钮 ghost 类白字隐形（08-26 按钮体系回归缺陷）：builder 的 ghost 文字色误用 p['text']（为 primary 深底设计的白色）→ default/mica/glass/vista 等浅色主题下「刷新/示例/复制响应/送单帧解析器回读/重载默认/导入导出JSON」等 ghost 按钮白字+透明底完全不可见；调色板新增 ghost_text 键（浅色主题 #334155、暗色 #d1d5db），builder 改 p.get('ghost_text', p['text']) 向后兼容；像素级验证 mica 下 ghost 文字真实渲染",
            "修复协议6 645虚拟表串口下拉永远为空：Dlt645VirtualMeterWidget.__init__ 从未调用 _refresh_ports()（698 版有、645 版抄漏），port_combo 零条目点开无内容，而唯一填充入口「刷新」按钮恰是隐形的 ghost——两 bug 咬合表现为「串口列表点不开」；构造即填充（offscreen 实测 8 端口）",
            "645虚拟表新增「表地址」预设定：串口从站组行首地址编辑框（12 位 hex，大写规范化，非法/非12位回退旧值并提示）；实时生效于离线与串口应答（引擎每帧经 _make_engine 工厂重建）、示例请求帧地址、档案保存/导出 JSON 与导入回填；tooltip 说明广播地址 999999999999/AAAAAAAAAAAA",
            "645虚拟表「离线模拟」新增「下发响应到串口」（success 绿按钮+发送图标）：把「生成响应」得到的虚拟表应答帧真实写入串口 TX，向主站/集中器注入任意指定报文；与从站自动应答共用同一串口故需先「开始监听」，未监听/无响应帧/写失败分别弹提示不崩，多帧全部下发并在收发日志记 ⇱ 行；Dlt645SerialSlaveThread 暴露 write_frame（_ser 运行期句柄+写锁，与读循环并发安全）；COM1↔COM2 虚拟串口对真实回环逐字节验证",
            "645虚拟表引擎补齐 DLT645-2007 §7 功能码（dlt645_sim/engine.py）：13H 读通信地址→93H（数据域=表地址线上序）、15H 写通信地址→95H（应答地址域=新地址；引擎改自身地址并经 address_written 信号跳回 GUI 同步编辑框+静默持久化，串口主站初始化不再回异常）、08H 广播校时静默接收无应答；此前这些帧一律回「暂不支持功能码」+D1H 异常（主站读/写地址流程直接被打断）；异常应答功能码同步修正为跟随请求（13H→D3H、15H→D5H，原恒 D1H 违反规约）；test_dlt645_sim 扩至 11 项（13H/15H 全链+坏长度 D5H+08H 无应答+D8H 异常码），用户真实帧 68 AA×6 68 13 00 DF 16 复验 93H 应答",
        ],
    ),
    (
        "1.23.5",
        "2026-09-11",
        [
            "协议6 新增「645虚拟表」tab（dlt645_meter_sim_widget.py）：离线粘贴主站读请求→生成响应→解析回读/复制；档案 DI 值可编辑保存（dlt645_sim_data.json）；可选串口从站监听自动回复；注册表 has_dlt645_sim 控制可见性（仅协议6）；关闭软件时回收串口线程",
        ],
    ),
    (
        "1.23.4",
        "2026-09-11",
        [
            "DLT645 从站模拟核心（dlt645_sim/，纯逻辑无 Qt）：handle_frame 支持主站读数据 11H→91H 闭环；未知 DI / 不支持功能码回异常 D1H（ERR 无请求数据）；档案 DI→可读值（复用 encode_value / DLT645FrameGenerator）；test/test_dlt645_sim.py",
            "GUI 虚拟表 tab 扩展与串口从站线程后续接入（本版本先落引擎与测试）",
        ],
    ),
    (
        "1.23.3",
        "2026-09-11",
        [
            "工程债：新增 release_check.py 发布前自检——APP_VERSION/CHANGELOG/README 徽章/Inno Setup MyAppVersion 对齐、spec datas 关键文件存在性、核心测试一键跑；--sync-iss 可自动回写两个 .iss 版本号",
            "新增 test/test_core_suite.py：与 release_check 共用核心测试清单（纯逻辑为主，--with-gui 追加 offscreen）；主题 offscreen 套件已知噪声仅 WARN",
        ],
    ),
    (
        "1.23.2",
        "2026-09-11",
        [
            "批量解析新增「导入 pcap」：离线读 pcap/pcapng，TCP 流重组后写入批量输入框并自动批量解析——现场路径「抓包文件 → 帧列表 → 按类型全选 → 时序图/导出」闭环；三种模式：PLC2 监控帧（完整 ED..EE，推荐协议9）/ PLC2 业务帧（剥包装）/ 原始 TCP 负载（每段一行）",
            "新增 pcap_import.py（纯逻辑无 Qt）：经典 .pcap 纯标准库解析零依赖；ED..EE 切帧与 FlowBuffer 同口径；format_batch_text 带时间戳/流方向注释；pcapng 走 scapy 兜底（Windows 会先补 ProgramFiles 再 import）；导入后建立批量原始日志快照，可右键回跳；test/test_pcap_import.py",
        ],
    ),
    (
        "1.23.1",
        "2026-09-11",
        [
            "架构：新增协议能力注册表 protocol_registry.py——12 种协议的展示名/别名/占位符/查询页/组帧模式/Tab 能力（档案/拓扑/虚拟表/监控/时序图）/解析级别族/批量提取策略/校验器类/GUI 解析器包装 统一声明；main_gui 查表分派，新增协议优先改注册表而非散落 8+ 处 if",
            "main_gui 接线：protocol_combo 下拉、_on_protocol_changed 占位符与 Tab/控件可见性、查询页 builder 分派、_get_current_parser 包装、校验器 map（单帧+快捷小窗）、_protocol_name_to_index、_extract_frames_for_protocol 策略选择 全部走 protocol_registry",
            '修复：协议6 预设命令页可见时未调用 preset_tab.set_protocol("dlt645")（此前 set_protocol 分支写在 virtual_meter 可见块内且漏 6）；预设 mode 由注册表 preset_mode 驱动',
        ],
    ),
    (
        "1.23.0",
        "2026-09-09",
        [
            "新增「通信时序图」标签页（仅协议9新一代载波）：批量解析结果一键生成 CCO⇄STA 通信序列图——节点按 TEI 自动判别（TEI=1 为 CCO 固定最左，其余 STA-XXXX 按首现排序），信标/SACK/应用层广播帧画为 CCO 发出的虚线广播箭头，单播为实线箭头；消息标签复用批量摘要（带 #帧号，超长截断+tooltip），纵轴按帧序排列；批量解析工具栏新增「时序图」按钮，摘要表有勾选行时仅用勾选帧（对齐「导出选中」惯例）否则全部帧",
            "时序图交互：滚轮/Ctrl+滚轮缩放、拖拽平移、「适应窗口」复位、「导出 PNG」整图导出；点击图上消息跳回批量解析页定位对应帧行并填充详情，反向选中摘要表行时图上对应消息高亮（_seq_sync_guard 防信号循环）；重新批量解析/清空时图模型同步重置",
            "时序图广播与未入网节点画法修正：真广播（信标/应用层广播）虚线箭头不再横穿全场景，改为只指向源节点相邻的已有节点（无右邻取左邻，单节点场景画固定长度短箭头）且标签加 [广播] 显式标识；TEI=0（关联请求等入网前帧，尚未分配具体TEI）节点标注「未入网站点」而非 STA-0000；test_csg_sequence_model 增 T10、test_csg_sequence_gui 增广播箭头落点断言",
            "时序图 SACK 方向与台体角色修正：选择确认帧不再当广播——帧内「目的TEI」即箭头所指节点（src 取源TEI，Bitloading 扩展帧携带，缺省 CCO；无目的TEI 才退化为广播画法），虚线橙色保持控制帧视觉区分；业务标识=0xF0 测试命令帧（台体初始化过程发送，非 CCO 报文）源节点新增角色「台体发射机」（独立节点，不复用帧内 spoof 源TEI）；test_csg_sequence_model T4 改有向断言+增 T11，test_csg_sequence_gui 样本扩至 5 帧覆盖 SACK/台体节点",
            "时序图直观性重构（物理实体视角）：存在 0xF0 测试帧时台体发射机与 CCO 合并为一条生命线「台体发射机(模拟CCO)」；未入网站点(TEI=0)按关联确认帧目的TEI 归并为同一 DUT 生命线「STA-XXXX (DUT)」并在关联确认行画「入网→STA-XXXX」状态标记；按关联请求/关联确认插入阶段分隔线（①初始化/②关联入网/③业务测试）；广播虚线改为覆盖全部已有节点（中央信标对所有STA有效，止于最右节点）；节点间距改为按最宽消息标签自适应加宽（下限360px，保证摘要文字在生命线间舒展不拥挤）、摘要截断40→60字；现场多STA日志（无测试帧且无关联确认）自动退化为按TEI分线不合并",
            "时序图覆盖扩展至协议9/10/11（南网新一代/国网新一代双模/HDC 1.0）：三协议解析器字段同构（定界符类型/源TEI/目的TEI/发送类型/MMTYPE，仅字段名与缩进差异），提取器统一为通用管道（去缩进索引+多字段名候选：定界符类型(DT)/消息类型(MMTYPE)/原始TEI兜底），信标源TEI有效时取信标源、缺省/为0归CCO；标签页与「时序图」按钮对三协议可见/可用；test_csg_sequence_model 增 T13(协议10缩进字段)/T14(协议11同构+入网归并)、T9 改三协议分派断言，test_csg_sequence_gui 增协议10/11可见性断言",
            "实现拆分：新文件 sequence_diagram_widget.py（纯逻辑层 SequenceNode/SequenceMessage/SequenceModel + build_sequence_model_csg/build_sequence_model 分派入口不依赖 Qt，UI 层 SequenceDiagramView/SequenceDiagramWidget 用 QGraphicsView 自绘，零新增依赖）；main_gui.py 仅增量接线（懒加载 tab/工具栏按钮/双向联动），tab 插入批量解析页之后不影响其他 tab 索引",
            "测试：新增 test_csg_sequence_model.py（T1~T9：TEI提取/CCO最左/信标与SACK广播/失败帧跳过/节点去重/应用层广播/ED包装帧/分派与原始索引保持）与 test_csg_sequence_gui.py（offscreen 19 项：tab注册与协议可见性/按钮启停/全量与勾选子集生成/图↔表双向联动/clear_batch重置）；csg 既有回归（summary/batch_parse_level/batch_prefix/new_gen/hrf_mac）全过",
            "批量解析脚本预处理 hex_clean 回退模式修复：此前脚本只识别监控日志 'ED ... 'O 标记，协议9批量输入为裸 hex 行时逐行跳过、输出为空，GUI 弹「脚本输出为空，未修改输入内容」看似运行无变化；现全文无 'ED 标记时回退为逐行通用清洗（剥离行首时间戳/日志标签、去非 hex 字符、保留长度≥16 且偶数的行），含标记输入保持原提取行为不变；新增 test/test_hex_clean_script.py（19 项）",
            "脚本列表去重：「加载」判重与启动回填 config.json py_scripts 时改用 realpath+normcase 规范化路径比较（Windows 正/反斜杠同一文件不再重复注册），历史重复条目启动加载时自动去重回填并自愈写回 config.json",
            "新增 ED 包装头格式选择「广西台体(14字节头)」：广西台体发射机报文与 PLC2.0 同为 ED..EE 包装但数据域公共头 8 字节（时间戳4+物理信道1+物理块个数1+物理块长度2，无 Payload CRC），业务帧自第 14 字节起（PLC2.0 为 15 字节）；协议9 工具栏新增下拉（PLC2.0 台体/广西台体），单帧/批量/校验剥离/批量提取四条链路统一按所选格式剥离；包装头表格按广西布局展示字段偏移；新增 test/test_ed_gx_wrapper.py（17 项）并以真实广西台体帧端到端验证（业务偏移14→SOF帧解析成功）",
            "ED 包装头格式新增「自动识别(推荐)」默认项：逐帧打分判别 gx/plc2——剥头后业务帧首字节符合 FC MPDU 特征(+2)、物理块长度字段与业务长度自洽((业务长-16)为pb_len正整数倍且pb_len属常用PB尺寸,+1)，平局优先 plc2，无正分回退手动选择；单帧/批量/校验剥离/批量提取四条链路统一逐帧自动识别，混合日志（广西台体+PLC2.0 帧混排）无需手动切换；test_ed_gx_wrapper 扩至 22 项（auto 双向识别/手动覆盖/auto 批量剥离）",
            "批量解析结果→输入日志行回跳：解析时逐帧记录显示行号 _src_line（行式协议 3/5/9/10/11 及通用：提取器返回行号三元组 + 前缀剥离行映射 _last_strip_line_map + 首部空白行偏移；流式扫描协议 0/1/2/4/7/8 不记录）；点击摘要行（含时序图联动选中）自动在批量输入框选中并滚动到对应报文行；修复协议9前缀剥离重复执行导致行映射被覆盖（_csg_strip_done 防重入）；新增 test/test_batch_src_line_jump.py（8 项：行号记录/点击回跳/ED包装行/监控前缀映射/lead偏移）",
            "批量解析摘要表右键「转到原始报文位置」：拖入/打开文件/粘贴时建立不可变**原始日志快照**（CLI/脚本回填式预处理只改输入框不动快照，解决原文被清洗覆盖后无处可回看的问题）；帧 hex 在快照归一化 hex 流中定位（逐行剥行首时间戳防数字混入、跨行帧连续、重发帧按出现次序消歧、命中按帧缓存二次定位零重算），弹 Notepad++ 式只读查看器（新文件 batch_source_view.py：行号边栏/等宽/黄底高亮+滚动居中/Ctrl+F 搜索条含上一个下一个与命中计数、非模态单实例复用）；**Ctrl+G 快捷键**直达当前行定位（菜单项同示快捷键），**弹窗保持**——弹窗打开期间摘要表切换行自动静默跟随刷新高亮（不抢焦点不弹提示），直到用户关闭弹窗才停止；右键菜单另含「复制本帧HEX」，保留原复制选中行/全部；手敲无快照时 parse_batch 兜底以框现文为快照，clear_batch 同步销毁快照与查看器；新增 test/test_batch_snapshot_locate.py（47 项：纯逻辑 12 + 快照链 6 + offscreen GUI 29）",
            "修复多物理块重组解析后点击行高亮错位：MAC 帧跨多 PB 时重组解析（MAC头/MSDU/应用层/级联块行）的偏移处于 concat 拼接缓冲区坐标，未翻译回原始帧导致点击行定位到错误字节；csg_new_gen_parser 新增 _concat_segments 分段映射（concat 区间→原始帧 PB 体起始）与 _concat_to_orig/_remap_concat_rows，在级联头/级联块/单MAC/填充/MSDU 应用层各行添加时翻译回原始偏移，单 PB 恒等、非 PB 帧每帧重置不受残留影响，MAC重组噪声标记行不再给错误高亮范围；新增 test/test_csg_multipb_highlight.py（5 项：2-PB 跨块行偏移自洽/跨块行存在/单PB恒等/非PB无残留）；另隔离 Qt offscreen 解释器退出期原生崩溃对测试退出码的污染（6 个 GUI 测试结尾 os._exit）",
        ],
    ),
    (
        "1.22.1",
        "2026-09-08",
        [
            "修复协议9（通感一体化）多物理块帧切片：CMT映射PB大小与帧长不符时（如真实抓包 CMT=1 实为 4×520 字节 PB），按帧长一致性等式 offset+物理块个数×PB大小==帧长 在候选集 520/264/136/72/40/16 中唯一推断 PB 大小并追加「PB大小推断」提示行；无解（截断日志等）回退 CMT 映射值保持原行为；HRF/Bitloading 显式 PB 大小不参与推断",
            "协议9 新增逐 PB 的 PBCS CRC-24 校验（计算范围=物理块头+物理块体+保留字节，存储值小端）：校验通过 / 置零(采集接口未提供) / 校验失败(计算值=…) 三态结论，尾部不足4字节显示「PBCS缺失(帧截断)」；另增 PB 尾保留字节行便于逐字节核对校验范围；经 4×520 置零 PBCS 真实帧与真实非零 PBCS 帧双重验算",
            "测试：新增 test_csg_pb_size_pbcs.py（4 项：真实 2096 字节帧切片与置零告警、合成 4×136 校验通过、篡改 PBCS 校验失败、截断帧 PBCS 缺失）；既有 csg 测试 69 项全过无回归",
            "协议9 多物理块帧表格改为逐块交错展示：物理块头[i]→物理块体[i]→保留(PB尾)/物理块检查序列[i]→下一个PBH，不再把多PB体合并成一行堆在表尾；重组体不符 MAC 帧特征（噪声/加密载荷）时逐块按原始报文展示并抑制其后 MAC/MSDU 伪解析行（加「MAC重组解析=无法解析」标记行），合法 MAC 帧不受误伤；test_csg_pb_size_pbcs 增 T5/T6 覆盖顺序与抑制",
            "修复单帧解析选中行高亮同步：输入框可视区自动滚动到高亮字节位置（长报文换行后靠后字节的高亮此前落在滚动区外不可见，多PB帧 PBCS 行尤甚）；增加 start>end 异常范围守卫；新增 offscreen 回归 test_csg_pb_highlight_gui.py（16 项：PBCS 四行高亮落点+滚动同步+FC 对照）",
            "「填充CRC-24」扩展支持逐物理块 PBCS 一键回填：解析器新增 calc_pbcs_fills（SOF MPDU 布局与 _parse_pb_block 同口径：FC 取物理块个数、帧长一致性判定 PB 起始{16,32}与大小，截断/信标/非SOF 不填），GUI 对每个完整 PB 重算 CRC-24(PBH+体+保留) 小端写回 PB 尾 3 字节并在提示框逐项列出；采集置零 00 00 00 的多 PB 帧填充后重解析即全部「校验通过」；新增 test_csg_pb_size_pbcs T7/T8 与 offscreen test_csg_pbcs_fill_gui.py（12 项）",
            "修复 exe 打包后窗口/托盘图标缺失：图标曾用 Path(__file__).parent 定位，frozen 下指向 _MEIPASS 而 spec datas 未打包 app_icon.ico 致 exists() 为假静默跳过（exe 文件图标是构建期 icon= 嵌入，与运行时窗口图标无关）；新增 _app_icon_path()（frozen 优先 _MEIPASS、回退 exe 目录）替换窗口与托盘两处引用，spec datas 补 ('app_icon.ico','.') 并补 dlt645_frame_gen/schema hiddenimports（1.22.0 组帧功能 exe 必需）；新增 offscreen test_app_icon_path.py（6 项）",
            "修复「分享此帧」按钮无图标与同排不一致：set_btn_icon 的 Qt 标准图标映射表无 share 键且未知键静默跳过；改用图标库 Lucide share-2（16×16 与同排一致，颜色随主题自适应）；set_btn_icon 未知键改为打印一次告警，顺带暴露并修复虚拟表 tab 三处同类错键（media-playback-start/stop→play/stop、dialog-ok→apply、document-save→save）；新增 offscreen test_button_icons.py（10 项：按钮行图标全非空+尺寸+未知键安全跳过）",
        ],
    ),
    (
        "1.22.0",
        "2026-09-08",
        [
            "协议6（DL/T645-2007）新增组帧能力：「协议组帧」「预设命令」tab 对协议6 开放；命令下拉分 主站请求/从站应答/异常应答 三组（12 功能码），DI 由 dlt645_di.json 1099 条驱动并按 17 种 data_type 掩码自动推导字段表单（真 BCD+小数点+低字节在前，填十进制而非 hex）；表地址/广播勾选/控制码只读展示；字段变化经 200ms 防抖实时刷新右侧解析预览，生成后「解析回读」标签当场闭环校验",
            "新建 dlt645_frame_gen.py（全仓库唯一 645 封装实现：地址序/控制码/+0x33/L/CS/68…16）与 dlt645_frame_schema.py（命令 schema + 掩码推导 + LME 查询模板）；dlt645_data_codec.py 新增 encode_* 系列与既有 decode_*/split_* 成对互逆",
            "LME 自定义接口查询请求 11H 结构化组帧：FF00DD01 按 分类/条目（含分类7）生成 条目信息+M+M×2B 请求头（数据ID 6bit|分类 3bit|保留 7bit），留空 M=0 读全量；04FFAAF9 无数据单元；lme_info_entry_parser.py 新增 pack_lme_query_request 等与解码互逆",
            "Reflex Web 组帧页支持协议6（命令/表地址/DI/动态字段），与 GUI 共用同一生成器保证同输入同输出；preset_buttons 支持 dlt645 预设库（DLT645_command.json 5 条种子预设）；spec datas 同步",
            "修正 EB 数据标识 645 帧口径：生成侧改为标准口径（数据域 +0x33、CS 覆盖帧头、DI 低字节在前——真实抓包 CCO-2-COM3 三帧逐字节验算证实），GUI/Web 两处手写封装统一改调 DLT645FrameGenerator；gdw10376_parser 内嵌 645 解析增加 -0x33 还原与 DI 双字节序兼容（标准低字节在前优先、旧高字节在前回退），新增 加扰/字节序/CS 三行标注（仅提示不阻断）",
            "修正 dlt645_parser 广播校时解析：数据域第 6 字节为「年 YY」而非「星期」（DL/T645-2007 §7.6 线序 ss mm hh DD MM YY），同步修正测试断言",
            "测试：新增 test_dlt645_frame_gen.py（161 项：真实抓包 golden sample 逐字节复现、掩码 encode→decode 往返、组帧→解析→校验闭环、LME 查询）与 test_dlt645_frame_gen_gui.py（66 项 offscreen 冒烟，实时预览走真实信号链路）；test_web_frame_gen_utils 增协议6 Web 同输出断言（74 项）；回归 test_gdw_fujian 19 项、test_dlt645_lme、test_quick_parse_panel 84 项全过",
            "修复协议9 批量解析将 SACK 帧误报「MAC帧长度不足(需要≥36字节)」：SACK/信标/NET 的 MPDU 判定从「SACK 必须恰好16字节」放宽为 ≥16 字节，FC 头之后的尾部字节（疑似 FCS/冗余）单独成行展示，不再回落到 MAC 解析路径；通道判别改为 MPDU 级输入一律按 FC 可变区域结构判别（批量解析每帧各自判别），下拉通道仅作提示，判别与下拉不一致时加「通道判别」提示行并以判别为准；test_csg_hrf_mac 增 T9（SACK 尾字节 + 通道提示）并按新契约更新 T8",
        ],
    ),
    (
        "1.21.1",
        "2026-09-02",
        [
            "Web 版「报文分享」新增管理员删除功能：/share 页复用反馈管理口令（AdminConfig，默认 admin123），管理员登录后每条分享记录卡片显示「删除」按钮——点击弹确认框，确认后删除该条（含 GUI 桌面端分享的记录）并刷新列表，防止分享区堆积杂乱内容",
            "share_model.py 新增 ShareStore.delete(item_id)（不存在返回 False 幂等安全）；ShareState 改为继承主 State（与 FeedbackState 同款模式）以访问 admin_logged_in，顺带修复主页「分享此帧」弹窗打开时访问 last_parsed_hex 的现存 bug；删除按钮用 rx.stop_propagation 防止误触卡片打开详情；删除确认弹窗受控三件套（on_open_change 同步 + 显式关闭按钮）",
            "测试：test_frame_share.py 新增 test_delete（存储层删除/幂等/删空页回退）与 test_delete_ui（删除按钮渲染/弹窗 open 绑定/stop_propagation），共 77 项全过；回归 test_web_feedback 49、test_feedback_api 31 全过；真机 e2e 验证提交→删除→幂等全链路",
            "GUI 修复：测试方案表格「超时(ms)」列原用内嵌 QSpinBox，上下调节箭头遮挡数字看不清，改为可编辑文本单元格直接填写（整数 100–600000，非法/越界输入自动还原旧值，持久监听行不可编辑）",
            "GUI 修复：懒加载标签页（TCP监控/协议组帧/档案管理/拓扑信息）首次点击替换占位页后图标永久丢失——_replace_lazy_tab 的 insertTab 未带回 tabIcon，现替换前保留图标",
        ],
    ),
    (
        "1.21.0",
        "2026-09-01",
        [
            "新增「报文分享」功能（Web /share 页面 + GUI 单帧解析「分享此帧」，共享 frameshare.db）：用户单帧解析后可把有价值的命令帧分享到服务端——记录 原始报文（服务端 normalize 规范存储）+ 协议 + 分享人（必填≤50）+ 说明（选填≤500）+ 来源（web/gui），所有人可在 /share 页浏览（时间倒序分页每页20条）与搜索（报文 hex 支持连续无空格输入自动匹配空格存储格式/协议/分享人/说明），点开详情可复制完整 hex",
            "Web 端：新增 ShareState + /share 独立页面（导航栏「报文分享」入口）+ 主页单帧解析「分享此帧」弹窗（State 缓存最近解析的报文与协议名，解析成功后可分享，sharer 必填、协议下拉预选当前协议）；详情弹窗受控三件套（关闭按钮/on_open_change 同步）；新 API POST /api/frameshare（JSON，dev Starlette Route + 生产 run_app.py 中间件双实现共用 share_model.submit_share）与 GET /api/frameshare/config（约束下发），频率限制 60s/10条/IP，CORS 反射 Origin",
            "GUI 端：新增 share_dialog.py（ShareDialog）——只读报文展示/协议下拉（自动映射当前协议索引到短名）/分享人（记住上次输入到 config.json share.last_sharer）/说明（预填 GUI 版本+OS+Python 环境）/服务器地址复用 feedback.server_url（同一服务器）；QtNetwork 异步 JSON POST（20s 超时，零新增依赖），成功后可一键在浏览器打开 /share；main_gui.py 单帧解析按钮行新增「分享此帧」（未解析时提示先解析）",
            "share_model.py（新）：ShareItem(rx.Model) + ShareStore 单例（独立 frameshare.db，FRAMESHARE_DATA_DIR 环境变量供测试重定向，部署脚本 data/ 整体保留策略天然覆盖）+ normalize_hex（hex 清洗规范存储）+ submit_share 纯函数（字段/协议白名单/hex 边界 2~2048B 全套校验）+ list_page 分页搜索；修复：share_model 移至 reflex_web.py 顶部 import（此前仅 API 请求时懒加载，rx.Model 元数据在请求线程注册导致 dev 后端事件循环假死——POST 一次成功后服务无响应，TestClient 无法复现、TestClient 隔离验证定位）",
            "测试：新增 test_frame_share.py（57 项：normalize_hex 边界/submit_share 校验分支/Store 分页搜索含无空格 hex 匹配/config 下发/GUI payload 构造与 validate_fields 分支/last_sharer config 往返/offscreen 对话框冒烟）；回归 test_web_feedback 49、test_feedback_api 31、test_feedback_dialog 30、test_web_frame_gen_utils 63、test_quick_parse_panel 84 项全过；真机 e2e POST 序列（合法 gui/web/非法 hex/空分享人/非法协议）全部按预期返回且服务保持存活",
        ],
    ),
    (
        "1.20.0",
        "2026-09-01",
        [
            "GUI 客户端新增『问题反馈』（帮助菜单）：新文件 feedback_dialog.py（QDialog），问题类型/涉及协议下拉、描述（≤2000 字实时计数）、联系方式、截图（≤3 张）；QNetworkAccessManager 异步 multipart 提交（零新依赖，20 秒超时），成功后可一键在浏览器打开反馈页；自动收集环境信息（版本/OS/Python/机器名/当前协议）随 sys_info 字段提交",
            "Reflex Web 服务端开放反馈提交 API：POST /api/feedback（multipart，dev Starlette Route + 生产 run_app.py ASGI 中间件双实现，共用 feedback_model.submit_from_api 纯函数）与 GET /api/feedback/config（GUI 拉取字段约束）；滑动窗口频率限制（60 秒 5 条/IP，进程内计数）；CORS 反射 Origin（无凭据接口，Qt 不校验）；GUI 与 Web 页面提交共用同一 feedback.db，反馈列表为桌面端来源记录显示『桌面端』徽章、详情弹窗展示客户端环境信息",
            "feedback_model 扩展：FeedbackItem 新增 source（web/gui 来源）与 sys_info（客户端环境信息）列，FeedbackStore 首次打开旧库自动 PRAGMA+ALTER TABLE 迁移（历史记录默认 source=web）；新增 submit_from_api（字段/截图全套校验+失败回滚已存文件）、parse_multipart（二进制安全手工解析，生产中间件用）、FeedbackRateLimiter（可注入窗口/上限）、api_config 纯函数",
            '反馈服务器地址可配置：config.json 新增 "feedback" 段（server_url，默认 http://127.0.0.1:8000），对话框内可修改并持久化；部署后把地址改为 Web 服务器实际地址即可',
            "测试：新增 test_feedback_api.py（31 项：提交/校验/截图回滚/multipart 解析/频率限制/旧库迁移/config）与 test_feedback_dialog.py（30 项：URL 规范化/config 读写/字段校验/sys_info/offscreen 对话框冒烟/截图增删/提交拦截）；回归 test_web_feedback 49 项、test_web_frame_gen_utils 63 项全过；真机端到端 curl 提交 → source=gui 落库验证",
            "同批修复（上轮 1.19.0 验收发现）：reflex_web.py 缺 datetime import 致 Web 端提交报错；顶栏在独立页改为『返回主页』+管理员按钮跳回主页（弹窗组件仅挂主页）；Tab 栏 overflow-y hidden 消除多余垂直滚动条；反馈列表 Tab 改双事件链触发（Reflex 跨 State delta 不随主 State 事件推送）；详情弹窗关闭按钮显式绑 State + on_open_change 同步（受控弹窗）；FeedbackState 改继承主 State 使 admin_logged_in 可访问（修复管理员删除报 AttributeError）",
        ],
    ),
    (
        "1.19.0",
        "2026-08-31",
        [
            "Reflex Web 版新增『问题反馈』页面（/feedback）：问题类型/涉及协议下拉、问题描述（必填 ≤2000 字）、联系方式（选填 ≤100 字）、截图上传（≤3 张 jpg/png/webp 单张 ≤5MB，魔数+扩展名+大小三重服务端校验，文件名服务端重生成防路径穿越）；导航栏新增『问题反馈』入口。新增 /feedback-admin 反馈管理页（复用发布管理 AdminConfig 口令）：时间倒序分页列表（每页 20 条）、详情弹窗（截图内联预览 /fbimg/ 路由）、状态流转（待处理/已确认/已修复/已忽略）、删除（记录与截图文件同步清理）",
            "反馈数据 SQLite 持久化：新增 reflex_web/reflex_web/feedback_model.py（FeedbackItem rx.Model + FeedbackStore 单例，check_same_thread=False 适配 Reflex 多线程）；数据落在 reflex_web/data/feedback.db + data/uploads/feedback/（与 downloads/ 同级策略，已加 .gitignore）。核心约束——重新部署不丢数据：build_embedded_deploy.py（增量 --skip-deps 与完整模式）与 build_offline_deploy.py 重建部署目录时把 data/ 移出再回填；备份/回填失败立即终止构建而非静默继续。新增 /fbimg/（+ /api/fbimg/）截图路由：生产 run_app.py ASGI 中间件 + 开发 Starlette 路由双实现，防穿越 + 仅服务 data/uploads/feedback/；依赖新增 sqlmodel（requirements.in + lock 已同步，Reflex 0.9.8 rx.Model 默认不装数据库依赖）",
            "新增 test/test_web_feedback.py（49 项断言）：截图保存校验（png/jpeg/webp 魔数、非法扩展、超大、空内容、穿越文件名拒绝）/ 防穿越清理（../、路径分隔符、非 fb_* 文件名拒绝）/ FeedbackStore CRUD（分页/待处理统计/状态流转/删除返回截图名）/ 部署脚本 data/ 保留往返（offline+embedded）/ 四文件编译验证；test_web_frame_gen_utils 回归 63 项通过",
        ],
    ),
    (
        "1.18.2",
        "2026-08-29",
        [
            "快捷小窗首次唤出『大高个』修复：空态窗口高约 200px、宽仅 520px——根因一是 QTextEdit 默认 sizeHint 高约 192px，空态解除限高后 _fit_height 直接采信把窗口撑高；二是 _DEFAULT_WIDTH=720 只用于居中计算从未真正 resize，构造期窗口停在最小宽 520。修复：空态 _fit_height 收口为单行输入条高度 66px（右下角拖拽拉高不受影响，清空/重新唤出时回落单行）；首次唤出（用户未调整过几何时）宽度取 _DEFAULT_WIDTH=720。四场景探针验证：空态唤出 720×66、剪贴板预填展开 720×390、清空收回 66px、拖高后收回仍收口",
            "快捷小窗空态『宽灰边』修复：用户反馈空态输入框四周有一圈很宽的灰色毛玻璃边——根因是外层 12px 投影边距 + 面板 16/14/16/12 内边距在空态依然生效，这些透明留白被亚克力染色后视觉上成了输入框的粗边框；改为边距随形态动态切换——空态收窄为 6px 外层光晕 + 2px 内边距（输入框距窗口边缘仅 8px，原 28px），展开态恢复原边距供毛玻璃卡片与投影使用；顺手清理 _restyle 中两个未使用的 fg 变量（ruff F841）。test_quick_parse_panel 新增 4 项边距断言（空态 6/2px、展开 12/16px 恢复、双向切换），共 66 项全过",
            "快捷小窗三项缺陷修复（代码评审发现）：① _ever_activated 属性误删初始化——changeEvent 失焦分支读取该属性，若首个 ActivationChange 事件到达时窗口未激活（唤出瞬间其他窗口持有焦点）会抛 AttributeError，已在 __init__ 恢复初始化；② 底部键位提示承诺『Enter 打开』但从未实现（焦点在输入框时 Enter 只插入换行）——给输入框装事件过滤器，Enter/Return 触发『在主窗口打开』，Shift+Enter 保留换行，提示文案同步改为『在主窗口打开 Enter』与按钮行为一致；③ 协议 9/10 ED 包装帧校验口径与解析不一致——_quick_panel_parse 剥离 ED 监控头后解析，但 _quick_panel_validate 仍拿带包装原帧校验导致『解析成功、徽章恒为校验失败』，现校验同样先剥离再校验（剥离失败回退原帧）。test_quick_parse_panel 扩至 81 项断言（_ever_activated 回归/Enter 三场景/ED 口径四场景），并修正 12 节热键断言逻辑（_open_full 已隐藏小窗后单次热键必然重新唤出）",
            "快捷小窗预填协议改为『自动识别优先』：此前唤出时把协议下拉同步到主窗体当前协议并用 _suppress_detect 屏蔽本轮 detect_protocol，导致主窗体停在国网(7)时粘贴新一代载波(9)/南网(0) 帧会被锁在 7 误解析。现移除 _suppress_detect：_prefill_clipboard 同步主窗协议仅作兜底，_do_parse 中只要用户未手动选过协议就跑 detect_protocol，识别得出即切换、识别不出（返回 None）才保持主窗协议；_on_text_changed/_on_proto_manually_changed 中对应清标志逻辑一并删除。test_quick_parse_panel 新增 12c 两项断言（南网帧识别为 0 不锁主窗 7 / 不可识别帧兜底保持 7），共 84 项全过",
        ],
    ),
    (
        "1.18.1",
        "2026-08-28",
        [
            "快捷解析小窗改为毛玻璃（亚克力/Acrylic）质感：Windows 10 1803+/11 启用系统级亚克力模糊，窗口背后的桌面与其他窗口内容被模糊并叠加浅色调，卡片改为约 50% 半透明，告别原本近乎不透明的死板色块；非 Windows 平台安全降级不影响使用。新增 system_integration/acrylic_effect.py（ctypes 调 SetWindowCompositionAttribute，失败静默），在 showEvent/热键唤出时随明/暗主题着色",
            "快捷小窗空态外观精简：无输入时只显示输入框本身——外层卡片变透明、去掉粗边框与投影，消除“输入框外套大卡片”的双层边框；右下角缩放现在可同时拉高输入框（原输入框被 62px 限高、卡片 Fixed 高度只能拉宽）。输入有效报文展开后卡片才呈现 1px 细毛玻璃边框，输入框限高、多余高度让给结果表格；卡片圆角统一 12px。test_quick_parse_panel 扩至 60 项断言（空态透明/投影禁用/输入框可拉高/展开恢复细边）",
            "小窗配色全面玻璃化：输入框、协议下拉、按钮、结果表格/表头/隔行底色均改为半透明，浅色主题用淡蓝白+蓝色描边、深色主题用深蓝灰+亮细边，选中色统一为淡蓝高亮；卡片圆角 12→14px。spec hiddenimports 补 acrylic_effect；test_quick_parse_panel 新增毛玻璃透明度/亚克力接口断言（53 项）",
            "修复小窗高度收回失效：清空输入回到空态时窗口高度滞留不回缩、手动调整窗口高度会被打回——根因是 _fit_height 只 invalidate 内层布局未 activate，外层 activate()/sizeHint() 读到陈旧缓存。修复为先激活内层布局再取 sizeHint；test_quick_parse_panel 现 62 项断言全过（含空态收回 390→244px、暗色/浅色毛玻璃透明度、缩放柄、MainWindow 集成）",
        ],
    ),
    (
        "1.18.0",
        "2026-08-28",
        [
            "状态栏增强：新增本软件自身的 CPU 占用与内存占用实时显示，方便用户判断软件是否影响电脑性能。CPU 为整机口径（进程 CPU 秒/墙钟/逻辑核数，与 Windows 任务管理器默认一致，0~100%），内存显示当前工作集、峰值在悬停提示；CPU <30% 灰色、30~60% 橙色提醒、≥60% 红色警示",
            "新增 proc_stats.py（纯标准库零依赖）：Windows 用 ctypes 调 GetProcessTimes/GetProcessMemoryInfo，Linux 读 /proc/self/stat 与 /proc/self/status，macOS 等不支持的平台安全降级显示 --；CPU% 需两次采样差值，首帧仅显示内存。采样为一次系统调用（微秒级），刷新定时器设为 4 秒慢刷新，避免高频轮询影响 GUI 流畅度",
            "线程数标签可点击：点击状态栏「线程: N」弹出轻量 QMenu 明细——Python 线程（名称/ident/守护/运行状态）+ QThread 工作线程（名称/类名/运行或已回收）分组列出，底部「📋 复制线程列表」一键复制到剪贴板；点菜单外部即关闭，不阻塞界面。原 tooltip 保留为简要提示",
            "新增 test/test_statusbar_stats.py（proc_stats 采样/三标签刷新/明细菜单结构+剪贴板/CPU 着色阈值）；test_app_exit 线程回收回归通过",
        ],
    ),
    (
        "1.17.2",
        "2026-08-28",
        [
            "修复关闭软件后进程仍残留的问题：Qt 仅在“最后一个可见顶层窗口”关闭时才发 lastWindowClosed 结束 app.exec()；点 X 最小化到托盘后窗口已隐藏，托盘「退出」/自动更新重启再调 self.close() 时无可见窗口关闭，事件循环永不退出（线程虽已全部回收）。修复：closeEvent 真正退出路径 event.accept() 后 QTimer.singleShot(0, QApplication.quit) 显式结束事件循环；新增 test/test_app_exit.py（offscreen 三场景：托盘退出/直接关闭/虚拟表线程登记）",
            "虚拟表串口从站线程 SerialSlaveThread 补登记 thread_registry（关闭兜底回收可覆盖）；剪贴板监听 stop() 的 disconnect 用 warnings.catch_warnings 屏蔽无害 RuntimeWarning",
            "修复协议9（通感一体化/ISAC-PLC）SOF 数据帧 Bitloading 标识与物理块大小解析错误：字节6(表23) bit0=Bitloading标识、bit1-2=物理块大小码(0:136 1:520 2:72 3:264)，原实现误用表13 ROBO/TMI 映射(0→520)且两字段合并显示；现拆分为“Bitloading标识”“物理块大小码”两个独立字段，TMI 模式仍走表13映射，Bitloading 模式显式 PB 大小(_pb_size)供 PB 解析使用；每帧重置 _pb_size/_cmt_index/_pb_count 防跨帧残留",
            "test/test_csg_new_gen.py 新增 2 项：ISAC SOF Bitloading 实帧(29012000045B0100F0000000206A8F56, PB=136) 与 TMI 模式构造帧",
        ],
    ),
    (
        "1.17.1",
        "2026-08-27",
        [
            "快捷解析小窗拆为两张独立卡片（用户反馈：输入框和结果应分开）：输入卡=徽章行（协议下拉+帧长+校验徽章）+输入框 常驻；结果卡=状态提示/⚠错误+结果表格+底部操作行 在下方实时浮出；两卡各自圆角边框、独立投影，间隙空白可按住拖动窗口",
            "缩放柄 QSizeGrip 从旧大卡移挂到最外层窗口右下角 margin 空白处——不遮挡任何控件，空态与展开态均可拖拽调整大小；明暗主题 _restyle 同步作用于双卡并刷新两卡投影颜色；_fit_height 对两张卡布局强制重算高度",
            "test/test_quick_parse_panel.py 扩至 45 项断言（新增：空态仅输入卡可见 / 解析后双卡并存且相互独立 / 错误态结果卡弹出 / 缩放柄挂外层窗口 / 暗色主题双卡配色同步）；offscreen 截图核验空态单卡、展开态上下双卡",
        ],
    ),
    (
        "1.17.0",
        "2026-08-27",
        [
            "新增 uTools 风格「快捷解析小窗」：全局热键（默认 Ctrl+Alt+X，可在系统集成设置改）唤出无边框圆角置顶悬浮面板，屏幕上方居中、带投影、无任务栏图标；粘贴/输入报文后输入框下方实时（300ms 防抖）弹出结果卡片——协议下拉自动识别可手动切换、帧长、校验✓/✗徽章、完整字段树（最高屏幕 55% 内部滚动）",
            "唤出时剪贴板含合法 hex 自动填入并解析（输入全选打字即覆盖）；Esc / 再按热键 / 点击面板外部自动隐藏；卡片「在主窗口打开完整视图」按钮转入原大解析弹窗（含解析级别/ED 剥离），「复制结果」复制 TSV；协议手动切换后不被自动识别覆盖，新输入才重新识别",
            "新增 system_integration/quick_parse_panel.py（QuickParsePanel 哑组件：不 import 解析器，clean/parse/validate/open_full/主题回调全部注入）；复用 detect_protocol 自动识别、parse_to_table 字段行、validator/*.verify 校验徽章；9/10 协议固定 auto 级别 + ED 监控头自动剥离；设置面板热键提示文案更新；spec hiddenimports 补 quick_parse_panel",
            "原大弹窗保留：命令行 --parse/--file/--clipboard、文件右键、Notepad++ 集成、卡片「完整视图」仍走 _parse_and_show_dialog；新增 test/test_quick_parse_panel.py 29 项断言（空态/真实帧/自动识别/错误态/徽章三态/异常容错/Esc/显隐/剪贴板预填/手动切协议/完整视图/复制/MainWindow 集成真实帧解析）",
        ],
    ),
    (
        "1.16.1",
        "2026-08-27",
        [
            "批量解析工具栏 5 个纯字形方块按钮（预处理行 ★保存/×删除/?帮助、脚本行 ×移除/?帮助）改为「标准图标+中文文字」：保存(save)/删除(delete)/移除(delete)/帮助(help)，与同行执行/加载/运行按钮风格一致；用户反馈纯图标无文字辨识困难",
            "移除 _make_toolbar_btn 已无调用方的 icon_btn 方块分支（全仓仅上述 5 处使用）；预处理命令下拉框 tooltip「点★/点×」说明同步改为「保存/删除」；按钮 min_width=80 紧凑布局，1366×768 下工具栏无几何重叠（offscreen 15 控件扫描验证）",
            "测试方案工具栏补齐图标：上移/下移（SP_ArrowUp/Down 绿色箭头）、编辑选中（文档图标）、导出（软盘）、导入（文件夹）、清空结果（圆叉）6 个原纯文字按钮补 Qt 标准图标，gui_utils._STANDARD_ICON_MAP 新增 up/down/edit 三个映射；12 个工具栏按钮全部图标+文字，表格行内发送/等待/后台/Lua 按钮维持配色纯文字",
        ],
    ),
    (
        "1.16.0",
        "2026-08-27",
        [
            "新增协议8（DL/T 698.45）『虚拟表』tab——698 从站模拟器（基于开源 Meter698-45Simulator 功能重写，非代码搬运，核心逻辑纯字节操作、无 Qt 依赖）：离线模式粘贴主站请求帧→自动生成响应帧并解析回读（可一键送单帧解析器）；串口从站模式独立选择串口（端口/波特率/校验/停止位）持续监听 68...16 请求帧自动组帧回复（建议配虚拟串口对）",
            "虚拟表引擎（meter_sim/ 包）：GET Normal/NormalList/Record（Selector 01/02/09）、链接请求、SET/ACTION 成功 DAR、安全明文(10 00)请求解封装与响应 MAC(0A0B0C0D) 封装；未知 OID 返回 DAR(对象不存在) 不回空；复用 DLT69845FrameGenerator 组链路帧（HCS/FCS 自动）、AXDRCoder 解码预览",
            "动态数据：当前日期时间(4000)实时生成、通信地址/表号(4001/4002/202a)按表序号回应、正向有功电能(00100200)随运行时间递增、日/月/曲线冻结时标按请求 Selector 时间自动回填、曲线冻结漏点时段返回0行、通配地址多表模拟（数量可配，表号递增）、黑/白名单 SA 过滤；设置持久化 meter_sim_settings.json",
            "档案数据 meter_sim_data.json：从开源 config.ini 迁移 194 个 OI 数据项（电能/需量/电压电流功率/冻结114条/参数/事件），档案页表格增删改、A-XDR 解码预览、JSON 导入导出、app_paths 定位 + 打包种子自愈；生成脚本 scripts/gen_meter_sim_data.py（离线一次性）",
            "tab 仅协议8可见；关闭软件时回收串口监听线程；spec datas 增加 meter_sim_data.json；测试 test/test_meter_sim.py 62 项（自组帧自解析闭环：典型 OID/ NormalList/Record/安全MAC/通配多表/黑名单/递增/漏点/粘包分片/畸形帧容错）全过，698 既有测试无回归",
        ],
    ),
    (
        "1.15.0",
        "2026-08-27",
        [
            "GUI 按钮全面添加图标（提升用户体验）：gui_utils.py 新增 set_btn_icon() + _STANDARD_ICON_MAP，采用 Qt 内置标准图标（QStyle.StandardPixmap）——零新增资源文件、跨平台随系统主题自动适配、自动高 DPI；未知 key 静默安全跳过不崩",
            "覆盖高频操作按钮：单帧解析（解析/清空/复制/导出/保存/校验/串口）、批量解析工具栏（批量解析/打开文件/选择类型/导出系列/★保存预设/×删除/?帮助）、全屏按钮、帧生成（生成/清空/发送/添加预设/清除预设/读取节点/清空输出）、报文对比（交换/对比/复制/导出）、测试计划（新建/添加/删除/保存/运行/停止/暂停/继续/单步/导出/清除）、TCP 监控（开始/停止/清除/导出/自动滚动/加载历史）、实时监控（暂停/清空/导出）、档案管理（初始化/启动/暂停/添加/删除/查询/导入/导出）、拓扑信息（查询/清除/导出/定位）",
            "保持图标+文字并存（默认不隐藏文字，仅视觉增强），与既有 set_btn/btnKind 蓝色系风格及 1.14.x 紧凑尺寸完全兼容；无贴切图标的转换类按钮（报文工具）与动态预设按钮保持原样",
            "设计/实现文档见 .trellis/tasks/08-27-gui-button-icons/（prd/design/implement）",
        ],
    ),
    (
        "1.14.9",
        "2026-08-26",
        [
            "协议0（南网）新增《计量自动化终端本地通信模块接口协议（试行）》文档核查与完善（protocol_parser.py / frame_generator_schema.py）：依据新文档（协议文档/0.南网协议/13 计量自动化终端本地通信模块接口协议，108 个数据标识）核查帧结构与 DI 定义，新增 15 个 DI 的名称注册与深度解析——批量查询/返回查询模块特征信息(E8 03/04 03 15)、查询/返回指定模块特征信息(E8 03/04 03 16)、查询/返回即插即用功能开关(E8 03/04 03 A0)、查询/返回黑名单节点信息(E8 03/04 03 A1)、查询任务建议超时时间(E8 00 03 0B)、查询/批量查询从节点相位信息(E8 03 03 0C/0D)、返回未完成任务列表(E8 04 02 05) 等",
            "修复 4 处新旧文档冲突的解析（均保留 PLUZ 旧格式兼容）：返回未完成任务列表双格式（新文档 计数2B+任务ID2B×n / PLUZ 旧格式）、添加组播任务模式字 D4=1 时含 2B 报文长度、启动/暂停任务空数据不再报错、添加任务模式字补 D4 组合多帧标志与 D6 PLUZ扩展位显示",
            "组帧新增 8 个下行命令 schema：设置即插即用功能开关/添加黑名单节点/删除黑名单节点/设置CCO时钟(E8 02 04 A0~A3)、批量查询模块特征信息/查询指定模块特征信息/查询即插即用功能开关/查询黑名单节点信息(E8 03 03 15/16/A0/A1)，组帧→解析回读全通过",
            "新增 test/test_nw_lcmi.py（64 项：32 解析 + 12 组帧回读 + 18 双格式兼容 + 2 预设回归）全过",
        ],
    ),
    (
        "1.14.8",
        "2026-08-26",
        [
            "修复 TCP 监控标签页首次点击卡顿（monitor/tcp_monitor.py）：模块级 from scapy.all import ...（首次导入耗时数秒）与 get_if_list()/get_if_addr() 网卡枚举均在 GUI 线程同步执行。改为 importlib.util.find_spec 轻量探测 + _load_scapy() 惰性加载；新增 IfaceListWorker 后台线程执行 scapy 导入与网卡枚举，完成后信号回填下拉框（期间显示「正在加载网卡列表…」并禁用开始抓包）；PacketSniffer 启动前确保加载完成；cleanup() 关闭时等待加载线程收尾",
            "修复 Fusion 暗色主题下报文对比页颜色不统一（diff_widget.py）：引入浅/暗双调色板 _PALETTES，新增 restyle_for_theme(dark) 统一重设输入面板/分组框/标题/复选框/图例等硬编码浅色样式；结果表格、字节高亮 HTML、差异标签、人话解读框构建时按当前调色板取色；main_gui 创建 diff 标签页后立即按当前主题 restyle，主题切换即时生效",
            "修复协议9「仅MAC帧」解析级别误剥 4 字节物理块头（csg_new_gen_parser.py）：mac_only 模式输入即 MAC 帧（不含 PBH），此前仍解析并去除前 4 字节 PBH（序列号/聚合标志/保留位）导致 MAC 头错位 4 字节。现从字节 0 直接解析 MAC 帧；GUI 下拉项「仅MAC帧(去除PBH)」更名「仅MAC帧」。回归 test_csg_hrf_mac(8)/test_csg_batch_parse_level(13)/test_csg_new_gen/test_csg_batch_prefix(8)/test_csg_summary(6) 全过",
            "协议9（新一代载波）支持测试装置通信控制协议V1.1解析：ED..EE 包装的数据域若为 CCO/STA 仓工装板控制帧（05/FE...05+地址+命令+6字节数据+校验）或功能驱动板帧（AA 0D 0A 结尾），自动识别并展开模块上下电、SET/RESET/EVENT 引脚、220V电源、8762A连接方式、衰减器A/B/C 等字段；Reflex Web 预处理保留 ED 包装帧并复用同一解析器。新增 test_csg_test_device_control.py，扩展 test_ed_fallback_fix.py 批量控制帧回归",
        ],
    ),
    (
        "1.14.7",
        "2026-08-24",
        [
            "修复 exe 打包后用户配置丢失：新增 app_paths.py 作为所有可写数据文件路径的唯一入口——frozen（PyInstaller 单文件 exe）下定位到 exe 所在目录，开发模式落项目根；此前 Path(__file__).parent 指向 _MEIPASS 临时解压目录（进程退出即删）、cwd 相对路径随启动位置漂移，导致每次更新 exe 后用户配置全部丢失",
            "接入文件：config.json（main_gui/llm_api_manager/llm_preprocess_widget/theme_settings/system_settings）、预设命令 NW/GW/DLT698_command.json、test_plan.json、custom_di.json、gdw_custom_afn.json、dlt645_di_custom.json、custom_commands.json、custom_obis.json、archive_data.json、监控 CSV Output/ 目录",
            "内置种子自愈：custom_di.json / gdw_custom_afn.json 在 exe 目录不存在时自动从 _MEIPASS 打包资源复制一份作为初始值（ensure_data_file），之后读写均落 exe 目录；已存在的用户文件不覆盖",
            "只读资源（icons/、dlt645_di.json、app_icon.ico 等）保持原定位不变；不做旧目录迁移；新增 test/test_app_paths.py（11 项：开发模式定位 + frozen monkeypatch 种子复制/不覆盖）",
            "修复低分屏/高DPI 下批量解析页按钮与输入框重叠 + 工具栏视觉凌乱：单行流式布局 → 三行独立 QHBoxLayout（核心操作+帧计数 / CLI 预处理 / Python 脚本+导出），行内下拉框吃掉剩余宽度，消除多行列宽竞争导致的负间隙重叠；全部文字按钮统一 min_width（普通 100/导出 120）等高等宽对齐；图标按钮（★保存 ×删除 ?帮助）弃用 setMaximumWidth 与空文本方案——QSS padding 使 sizeHint 变宽后与 maximumWidth 冲突致相邻重叠、空文本则让人无法辨识功能，改为内联收紧 padding + ensurePolished 后 setFixedWidth(sizeHint 宽度) 固定统一方块尺寸且保留字形；所有工具栏按钮补充 tooltip 说明",
            "修复关闭软件时周期性报 RuntimeError:Internal C++ object (_UpdateCheckWorker) already deleted：_run_update_check 连接 thread.finished→deleteLater 后 C++ 对象可能已被回收，closeEvent 旧代码 thread.disconnect() 直接触碰已删对象抛 RuntimeError。改为 try/except(RuntimeError) 包裹整个线程收尾块、disconnect 带参数并兜住 (RuntimeError, TypeError)；等待超时(500ms)时不再 quit()（阻塞网络 IO 无法中断、反而触发 Destroyed while running 警告），只断开信号放行；_UpdateCheckWorker 去掉 parent=self 避免窗口析构牵扯子线程。实测三场景（C++已删/运行中/已结束）closeEvent 均无异常",
            "批量解析新增「导出选中」：摘要表支持 Ctrl/Shift 多选行（原单选），工具栏新增「导出选中」按钮只导出高亮帧——用于从大批量结果中挑出信标帧等目标子集再导出；过滤栏新增「按类型全选」下拉+按钮（解析后动态提取类型列表，一键选中该类型全部帧，如全部信标帧）+「已选 N 帧」实时计数；导出对话框标题显示导出范围（仅选中帧 N/M 或全部）；清空/重新解析时自动重置选区与类型下拉",
            "窗口最小尺寸按屏幕自适应（min(1000, 可用宽度×0.85) / min(700, 可用高度×0.8)），1366×768 等低分屏下不再超出可视区压缩布局；主题 QSS 控件瘦身——按钮内边距 8px16px→4px12px、输入框 5px→2px6px、下拉框/选项卡同步收紧",
            "修复主题 QSS 字号与表格缩放基准脱节（gui_utils/theme_settings）：ThemeManager.apply 后重置全部 ZoomableTableWidget 缩放基准并按新字号重算行高，Ctrl+0 恢复不再把字号打回旧基准裁切文字",
        ],
    ),
    (
        "1.14.6",
        "2026-08-24",
        [
            "协议9（新一代载波）精简信标帧载荷深度解析（csg_new_gen_parser.py）：此前信标载荷只按标准信标表51 布局解析，精简信标（载荷头 bit4=1，表73）的 CCO MAC(6B)+信标周期计数(4B) 固定区被误读为 SNID/无线信道/信标机制字段、0x0E 精简条目头错位成「保留98」。现按表73 分支解析：标志+组网序列号+CCO MAC+周期计数+管理信息+BPCS；新增 0x0E 精简信标站点信息及时隙条目（表74）逐字段深度解析——TEI/代理TEI/角色(CCO/STA/PCO)/层级/MAC/RF跳数/载波频段/CSMA时隙开始NTB与长度。用户实测中央精简信标现正确解出 组网序列号70 / CCO MAC=00:00:90:98:01:63 / 周期计数20(=FC) / TEI=1(=FC源TEI) / 角色=CCO",
            "修复关闭软件后仍周期性弹更新提示：①点X最小化到托盘时暂停30分钟周期更新检查（closeEvent托盘分支停 _update_poll_timer），从托盘恢复显示时 showEvent 重启；启动3秒延迟单次检查加 isVisible 守卫——主窗口隐藏状态下自动检查直接跳过。②真正退出时收尾：停止周期定时器 + 断开并等待 _UpdateCheckWorker 线程结束（500ms 快速等待，超时 quit+2s 兜底），不再残留后台线程周期联网",
            "DAR 错误码表按文档表25 权威重写（dl_t698_45_apdu_parser.py DAR_MAP）：0成功~36比对失败+255其它 全量对齐；SET-Response/ACTION-Response Normal 的 DAR 改为裸 enum 单字节解析（此前走 A-XDR decode，非零错误码如 0x03 会撞 array 标签崩溃）",
            "测试：test_dl_t698_45.py GET-Response 用例改为文档语义（[1]=Data/[0]=DAR 双断言）；test_dl_t698_45_data_decode.py 全部合成帧 GetResult 标签 0x00→0x01；test_dl_t698_45_fujian.py 新增 用户版本信息真实帧全链路表格断言 + DAR 错误响应用例；四套件回归全过",
        ],
    ),
    (
        "1.14.5",
        "2026-08-21",
        [
            "协议11（HDC 1.0）查询站点升级状态上行报文解析（hdc10_parser.py 0x034）：此前只按下行表40 解析（块数/起始块号/升级ID），上行应答的 升级状态(字节1高4位)/有效块数/升级位图 全部丢失。现按文档第4-3部分 表45 补全：升级状态（0空闲/1接收进行/2接收完成/3升级进行/4试运行）、有效块数、起始块号、升级ID + 接收位图（每bit对应一个文件块，显示 N/M块已接收）；升级位图逐块编号明细按 起始块号+i 编号，每行32块多行展开，[✓n]=已接收 [✕n]=丢包；下行恰12字节仍按表40 解析并区分方向行",
            "协议11（HDC 1.0）台区户变关系识别(0x0A1)深度解析（hdc10_parser.py）：①修复报文头长度公式——6bit值(byte0[6:7]高2位+byte1[0:3]低4位)×4字节（类IPv4 IHL），此前错把「(b0低2位|b1高4位<<2)×4」致12字节头算成48字节、DATA从错误偏移切片只剩尾部16字节；校时/事件/通信测试/注册/升级等全部7处统一修正。②DATA域按采集类型深度解析：采集启动(表56 起始NTB/周期/数量/序列号)、特征信息告知(表57 TEI/采集方式/序列号/告知总数/起始NTB + 特征序列)、判别结果信息(表61 TEI/结束标志/识别结果/正确隶属CCO地址)。③特征序列按特征类型分派：工频电压(表58 BCD XXX.X 大端 220.5V)、工频频率(表59 BCD XX.XX 50.00Hz)、工频周期(表60 有符号偏差值+μs换算)，三相出线逐相展开，双沿采集解析 NTB2+第二组序列；test_hdc10 增至16项全过",
            "协议11（HDC 1.0）信标时隙分配条目/心跳检测/发现列表深度解析（hdc10_parser.py + hdc10_mme_parser.py）：①时隙分配条目(0xC0/F0)可变区按实机顺序解析——CSMA时隙信息(csha_phases×4B)先行 → 非中央信标信息(逐2B到边界，实测发现信标也携带、不做表50省略假设) → 绑定CSMA；实机声明total_len偏小(不含信标时隙数组)，内容延伸到管理区末尾(BPCS前)，真实帧17条时隙(2代理+15发现)+3条CSMA全解零剩余。②心跳检测(0x0007)按表94实现：原始源TEI(12b)/发现站点数最大站点TEI(12b)/最大发现站点数/位图大小 + 发现站点位图逐TEI编号明细([✓n])。③发现列表(0x0008)按表95实现：固定头32B逐字段(TEI/代理TEI跨字节12b/角色/层级/MAC/CCO MAC/相线评估/信道质量/成功率/站点总数/路由条目总数/位图大小等) + 三段变长区锚点切分——上行路由条目(下一跳TEI 12b+路由类型表98)、发现站点列表位图(锚点:位图大小, TEI明细展开)、接收发现列表信息与位图置位TEI一一配对显示[TEIn←计数]；test_hdc10 增至19项全过",
            "协议11（HDC 1.0）PB帧MSDU解析修复（hdc10_parser.py + hdc10_mme_parser.py）：①修复 MSDU长度 公式——表22 11bit=byte8全8b+byte9低2b(小端bit序)，此前错用 (b8<<3)|(b9&7) 致长度显示1031/1920等荒谬值。②MAC地址标志=1 时正确跳过 头后12字节地址域(源/目的MAC) 再定位 MSDU。③MSDU类型=0(网络管理消息) 显式传入 MME 解析链路；MME头按表58修正为4字节(MMTYPE 2B+保留2B)，此前3B致业务字段整体错位1字节。④PBH 剥离判据：MAC标准头 b0 bit7 恒为0(源TEI≤0x7FF)，b0 bit7=1 必为 PBH——auto/mac_only 模式自动识别并剥离。⑤未知/厂商扩展 MSDU类型 显示原始数据+可读ASCII标记提示(如 HL09)。⑥单PB对齐探测：以「声明MSDU长度 vs 实际+MME头合法性」综合评分选择 PBH 后起点。test_hdc10 增至20项全过",
        ],
    ),
    (
        "1.14.4",
        "2026-08-21",
        [
            "内嵌 Python 部署增量构建：build_embedded_deploy.py 新增 --skip-deps 模式——复用已有 python/（解释器+site-packages），仅刷新源码/数据/前端层，重复构建从 10+ 分钟降至约 1 分钟；requirements.lock 已最新时跳过 uv 重新编译。完整/增量构建原则写入 AGENTS.md/README（日常迭代用 --skip-deps，仅首次/改依赖/换 Python 版本时完整重建）",
            "协议8（DL/T 698.45）组帧 OI 增强（frame_gen_widget.py）：预定义字段模式 OI 改为「预设下拉 + 手动 hex 输入」双通道；A-XDR 模式 OI 同样支持预设/手动，并新增「描述符类型」下拉可自由选择 属性(OAD)/方法(OMD)（默认按命令类型：ACTION→OMD 其余→OAD），属性标识/索引 与 方法标识/操作模式 随选择切换显示；A-XDR 数据项编辑器中 OI/OAD/OMD 的下拉改为可编辑（NoInsert），支持手动输入任意 OI（hex 回退解析），自定义数据内容仍按 A-XDR TLV 模式填充；回归 test_web_frame_gen_utils(62)/test_dl_t698_45/test_dl_t698_45_fujian 全过",
            "修复协议8 A-XDR 复合类型（array/structure）编码语义：tag 后字节应为「元素个数」而非子项字节总长（文档附录 H.3.2：`01 — 类型=1，表示数组 / 03 — 数组元素个数=3`）。此前组帧 3 项 structure 误填 09（字节长），现正确填 03。修复点：frame_gen_widget.py / reflex_web/frame_gen_utils.py 编码器；dl_t698_45_axdr.py 解码器同步改为按个数循环（此前按字节长度截断，导致自组帧回读只显示 1 项）。回归 test_web_frame_gen_utils(62)/test_dl_t698_45/test_dl_t698_45_fujian/test_dl_t698_45_data_decode/test_oad_enrichment 全过",
            "修复协议8 组帧 SET-Request/ACTION-Request 缺尾部「没有时间标签」字节：此前仅 GET-Request 尾补 `00`，SET/ACTION 生成的 APDU 少 1 字节（文档 H.4/H.5：GET/SET/ACTION 请求均以 OPTIONAL TimeLabel 结尾，00=无）。修复 frame_gen_widget.py 两条生成路径（实时预览 + 生成按钮）与 reflex_web/frame_gen_utils.py::build_dlt698_axdr_apdu；新增 SET APDU 尾 00 测试断言",
            "协议8 解析表格 array/structure 成员逐项展开（dl_t698_45_parser.py）：此前复合类型仅显示「[N项]」，现对齐官方工具为每个成员生成子行（原始编码/值/类型说明，如 成员1 | 1101 | 1 | A-XDR:unsigned(0x11)），嵌套复合类型递归展开；新增 `_add_axdr_item_rows` 递归辅助",
            "协议8 请求 APDU 尾部 TimeTag 解析（dl_t698_45_apdu_parser.py）：GET/SET/ACTION 的 Normal/NormalList 分支统一解析 OPTIONAL TimeTag 尾字节（00=无时间标签），表格显示「时间标签 | 0x00 | 无时间标签」对齐官方工具；新增公共 `_parse_time_tag` 辅助（GET-Request Normal 原有内联逻辑改用该辅助）",
            "修复协议8 预设命令保存/显示：新增 DLT698_command.json 独立预设文件（此前 dlt698 预设被误存入 GW_command.json），PresetButtonWidget.set_protocol 支持 dlt698（此前静默忽略致预设页看不到 698 按钮），加载时按 protocol 过滤历史混入条目，AddPresetDialog 协议行显示「698.45 协议」",
        ],
    ),
    (
        "1.14.3",
        "2026-08-19",
        [
            "协议8（DL/T 698.45）EB030307 过零NTB值上行数据解析：ACTION-Response NormalList 兼容「数据个数」前缀（DAR 后 `01`=数据个数 + octet-string 数据，此前被误当 A-XDR array tag 解导致 0x81 报错），新增 `_parse_axdr_items_or_single` 双路径兜底（数据个数 N×A-XDR 失败回退单 A-XDR，兼容文档示例无前缀格式）",
            "EB030307 字段 schema（gdw_eb_di_fields.py）：数据开始时间(bcd_time 6B)/边沿类型(enum)/数据周期_分钟(uint8)/数据点数M(uint8)/NTB值数组(list，每项 相线1+相线2+相线3 NTB值 uint32)，真实上行帧 129B 解码为 10 组相线 NTB 值",
            "bcd_time 可读化：YYMMDDhhmmss（BCD）→ `2026-08-14 14:42:00` 格式（此前仅 hex 拼接）；EB030307 请求参数（1C 开头 date_time_s）优先走时间解码，响应数据走字段 schema",
            "数据不足防护：EB 数据内容长度不足固定头时回退 A-XDR 头 + 原始数据（避免截断错解）",
            "新增 test_dl_t698_45_fujian.py 2 项测试（用户真实上行帧解析 + 表格相线 NTB 展示）；全量回归 62+19+12 项通过；Web 实测显示 数据开始时间/边沿/点数/相线1/2/3 NTB 值",
        ],
    ),
    (
        "1.14.2",
        "2026-08-19",
        [
            "协议8（DL/T 698.45）福建简化698 解析（choice=0x02 List 结构）：新增 SET-Request/Response、ACTION-Request/Response 的 NormalList 分支（PIID + count + SEQUENCE OF {OAD/OMD, Data/DAR}），支持福建「本地通信模块扩展协议」V3.42 698 承载格式（EB030110 台区识别/EB030307 过零NTB 等）",
            "REPORT-Notification/Response 带 count 结构：PIID-ACD + count + OAD 列表 + 数据个数 + A-XDR 数据（对齐福建 698 上报示例 88 01 00 01 ... / 08 01 00 01 ...）",
            "EB 数据标识名称与字段解码：OAD/OMD 为 EB 数据标识（OI 高字节 0xEB）时按 4 字节原样查 gdw_eb_di_lookup 名称；数据内容按 gdw_eb_di_fields 字段 schema 解码（enum→名称、uint→值、bcd/bs8/list），无 schema 时保留原始 hex",
            "修复 EB 数据内容多字节 uint 字节序：按文档「645 减33逆序」规则为**大端**（此前编码器/解码器用 小端 导致识别时长 00 05 误读为 1280，现正确为 5 分钟），gdw_eb_di_fields.py 编码器同步修正",
            "新增 test/test_dl_t698_45_fujian.py：9 项测试（用户实测帧/文档示例 SET/ACTION/REPORT/多对象/大端编解码）全过；test_dl_t698_45.py、test_dl_t698_45_data_decode.py、test_gdw_fujian.py（19项）、test_web_frame_gen_utils.py（62项）回归全过",
        ],
    ),
    (
        "1.14.1",
        "2026-08-17",
        [
            "协议8（DL/T 698.45）APDU 数据内容业务解码（常用数据项全覆盖）：新建 dl_t698_45_data_decode.py——按对象属性格式解码 A-XDR 数据为业务值，覆盖电能量数组（kWh 换算+费率展开）、最大需量数组（值@发生时间）、分相电压/电流/功率/谐波（A/B/C 相+单位）、单值数据变量（数据/参数）；Scaler_Unit 换算按 10^scaler，单位码映射表；OI 未带属性3 时按 OI_UNIT_HINT 推断单位与默认缩放（762 个 OI 名称辅助）",
            "APDU 解析器接入（dl_t698_45_apdu_parser.py）：GET-Response Normal/NormalList/Next、SET-Request、REPORT-Notification Normal 在「数据」后新增「数据业务」键（不破坏原始 A-XDR 结果）；REPORT-Notification Normal 补齐缺失的 OAD 解析（此前 PIID-ACD 后直接当 Data）",
            "GUI 表格展示（dl_t698_45_parser.py parse_to_table）：「数据业务」按项展开显示（如 总: 1234.567 kWh / 费率1: 5 kWh / A相: 220.5 V），无模板 OI 不产生该行，原始解析不受影响",
            "修复 DLT69845Validator 长度域一致性公式：L = 不含起始符和结束符的数据长度（文档附录 H.1 帧例：帧长32 → L=30=帧长-2），此前 +4 误判为 +2 导致合法帧校验失败；生成器 _assemble_frame 原公式与文档一致，补充注释说明",
            "新增 test/test_dl_t698_45_data_decode.py：10 项测试（电能量/电压/电流/需量含时间/NormalList 逐项/SET/REPORT/未知OI/表格展示）全过；test_dl_t698_45.py、test_gdw_fujian.py（19项）、test_web_frame_gen_utils.py（62项）回归全过",
        ],
    ),
    (
        "1.14.0",
        "2026-08-17",
        [
            "国网协议(索引7)新增「福建增补规约」（1376.2集中器本地通信模块接口协议【福建增补】V1.4）解析与组帧：AFN=50H~56H 全功能覆盖——50H确认/否认、51H初始化、52H数据转发(透明转发/任务队列智能补采/本地定时/并发抄表福建/清空队列)、53H查询数据(参数配置/主节点地址/厂商版本/信道信息/串口参数/模式切换)、55H控制命令(设置地址/允许禁止上报/广播/注册/预告抄读/速率协商/模式切换等)、56H主动上报(主动注册/事件内容/抄读请求/响应报文/信道延时/广播完成/带任务信息上报)",
            "福建增补帧结构识别：信息域R按保留(5B)+序列号(1B)（上行加事件标志）、地址域A固定 A1+A3(12B 无中继)解析，与 2024 国网自动区分（AFN 探测）",
            "新增「本地通信模块扩展协议」EB 数据标识深度解析（附件1 V3.31）：新建 gdw_eb_di_lookup.py 映射表（事件/台区识别/设备基础/时钟/档案/任务队列等 40+ 数据项），645 帧内嵌 EB030002 停上电事件/EB030110 台区识别/EB030501 时钟/EB040302 停上电记录/EBEEEEEE 多数据项抄读等深度解析，透明转发(52H-F1)/事件上报(56H-F2)自动识别",
            "福建增补组帧：gdw_frame_generator_schema.py 新增 27 个 (AFN,Fn) 字段定义（含 list 字段自动数量、length_field 报文长度自动计算），gdw_send_frame_lib.py generate_frame 对增补 AFN 自动切换 R/A 结构",
            "校验器 GDWValidator 支持福建增补帧：AFN 值域检查按增补帧结构定位真实 AFN（探测 offset 22）",
            "GUI 集成：查询页自动含福建增补 AFN/Fn + 新增 EB 数据标识查询区块（搜索/浏览），组帧页自动可选福建增补命令",
            "修复 gdw_send_frame_lib.py _pack_fields 的 length_field 语义 bug（此前取长度字段自身值而非内容字段值，导致 05H-F20/13H-F2/福建增补 52H 等命令报文长度计算错误）",
            "新增 test/test_gdw_fujian.py：15 项测试（福建增补帧识别/各AFN Fn解析/EB深度解析/组帧回读/校验/2024回归）全部通过",
            "本地通信模块扩展协议升级至 V3.42-20260514：新增 EB030313/314 周边节点信号通信质量（本台区/非本台区）、EB030320/321 通信测距（启动/结果表）、EB030506 NTB校时_698方式专用（1C+BCD时间+NTB）、EB030520 自动NTB校时模式扩展（0~3：停用/645/698格式）；EBEEEEEE 多数据项抄读标记取消（V3.40 起采用698读取方式）。gdw_eb_di_lookup.py 增至 57 项，test_gdw_fujian.py 增至 16 项测试",
            "Reflex Web 版同步：协议7 解析/组帧/校验复用 GUI 模块自动获得福建增补支持；查询页新增 EB 数据标识查询（EB 前缀或台区/时钟等关键词）；test_web_frame_gen_utils.py 新增福建增补 + EB 查询用例（28 项全过）",
            "Web 组帧页新增「EB 数据标识 645 帧生成器」：选择 EB 数据标识（57 项）+ 645 控制码 + 地址域 + 数据内容，自动生成完整 645 帧（含校验和），一键填入 52H-F1 透明转发/56H-F2 事件上报的报文内容字段（test_web_frame_gen_utils.py 增至 35 项）",
            "EB 生成器新增 698.45 内容域填充：支持 6 种 698 服务（SET-Request/Response、ACTION-Request/Response、REPORT-Notification/Response），OAD=EB 数据标识原样，数据 A-XDR octet-string 编码，与附件1 文档 698 示例逐字节一致（test_web_frame_gen_utils.py 增至 44 项）",
            "698 内容域填充增强：①完整链路层帧（68 L C SA CA HCS APDU FCS 16，SA 地址类型/长度/hex、CA、DIR/PRM/功能码可配置，HCS/FCS 自动计算）；②新增 gdw_eb_di_fields.py 为 42 个 EB 数据项定义数据内容字段 schema（枚举/整型/BCD/ASCII/时间/list 等类型），选 OAD 后按字段表单配置数据内容自动编码（test_web_frame_gen_utils.py 增至 58 项）",
            "698 服务类型补齐 GET-Request/GET-Response（读取）+ 对象配置：服务类型 8 种（GET/SET/ACTION/REPORT 各请求/响应）；对象个数可选一个(01)/若干(02列表)；PIID、OI、属性编号/属性特征/元素索引（GET/SET）、方法标识/操作模式（ACTION）均可配置，默认=EB 数据标识对应字节（test_web_frame_gen_utils.py 增至 62 项）",
            "修复 main_gui.py 启动崩溃：test_plan_widget.py（GUI 组件，非测试脚本）此前被误移入 test/ 目录，根目录 /test_*.py 忽略规则导致 ModuleNotFoundError；已恢复至根目录并在 .gitignore 增加 !/test_plan_widget.py 例外，test/test_plan_widget.py 作为独立测试副本保留",
        ],
    ),
    (
        "1.13.0",
        "2026-08-14",
        [
            "新增「HDC 1.0 双模互联互通」协议（索引11，独立协议，Q/GDW 12087.42-2020）：主程序第 12 种协议。新增 hdc10_parser.py（HDC10Parser：FC/可变区域/信标载荷/时隙分配条目/MAC帧/应用层）、hdc10_mme_parser.py（MME 管理消息）、validator/hdc10_validator.py（HDC10Validator）、test_hdc10.py",
            "HDC 1.0 GUI 集成：协议下拉框 [11]；解析级别（auto/fc_pb/fc_only/mac_only/pb_only/fc_mac/app）与通道（PLC/HRF）下拉复用国网新一代控件；查询页新增报文ID/端口/定界符/MSDU类型映射；校验注册 11 → HDC10Validator；批量解析复用前缀剥离与摘要。仅 PySide6 主程序支持（Web 0-10 / TUI 0-9 未含）",
            "新一代载波协议(索引9)通道自动识别 PLC/HRF：parse_to_table 新增 channel='auto'（默认），按表45(HRF)/表20(BPLC)/表23(ISAC) 预测帧长比对判别通道，GUI 通道下拉默认自动识别",
            "新一代载波协议(索引9)无线信道单跳MAC帧解析（版本2，表12）：4字节帧头 + 无线发现列表消息（表139 TLV，站点属性按表142 展开）",
            "新一代载波协议(索引9)测试帧切频操作目标按 Option+信道号解析（模式6），与模式8 一致；同步修正国网新一代模式6",
            "新一代载波协议(索引9)批量解析管理消息摘要 int() 未处理 0x 前缀崩溃修复",
            "协议选择持久化：上次协议索引存入 config.json parse.protocol，启动自动恢复选中",
            "所有解析/查询/监控表格支持 Ctrl+滚轮缩放（gui_utils.py::ZoomableTableWidget，类 Excel）",
            "校验结果区新增展开/收缩 + 单帧/批量解析结果表新增全屏弹窗",
            "GUI 按钮风格统一（批量工具栏 / LLM API 对话框 / LLM 预处理面板）；修复 _py_run_btn 连接到不存在方法的 bug",
            "DLT645 数据域长度一致性校验增强：解析器与校验器均校验声明长度与实际帧长一致性，不一致时 FAIL + ⚠ 提示但尽力解析",
            "新增「TCP 流量监控」标签页（monitor/tcp_monitor.py）：基于 scapy 抓包，网卡选择、BPF 过滤、TCP 流列表、双向流重组、监控封装解帧、原始报文/解析结果分页、CSV 实时记录与历史加载，自动识别南网新一代 / 国网新一代",
            "新增 Windows 系统集成（system_integration/）：系统托盘、全局热键（Ctrl+Alt+X）、单实例、命令行参数（--parse/--protocol/--file/--minimized/--clipboard）、文件右键菜单、开机自启、剪贴板 hex 报文自动检测弹窗与 Notepad++ 集成",
            "新增表格右键复制与 Ctrl+C；解析弹窗增强：热键/命令行/文件右键共用，--parse/--file/--clipboard 不再弹出主窗口；监控器日志路径显示与浏览",
            "国网新一代 MME 管理消息解析持续完善（gw_new_gen_mme_parser.py）：关联/代理变更/发现列表/网络冲突/无线信道冲突/过零 NTB/网络诊断等，MMTYPE 2 字节小端",
        ],
    ),
    (
        "1.12.0",
        "2026-08-04",
        [
            "新增 LLM 智能预处理功能：批量解析标签页新增可折叠 LLM 预处理面板，支持通过 OpenAI 兼容 API 对原始日志进行多轮智能清洗后再解析",
            "内置 5 个 prompt 模板：提取 hex 帧、清理前缀、提取 TCP 报文、按协议分类、修复 hex 格式",
            "大文件自动分块（默认 200 行/块），异步调用不阻塞 GUI",
            "API 配置持久化到 config.json 的 llm 段，支持测试连接",
            "新增 llm_preprocess.py（API 客户端 + 分块器 + 异步 Worker）和 llm_preprocess_widget.py（预处理面板 UI）",
            "新增通用文本预处理工具 pp_cli.py：管道式命令链（find/excluding/replace/head/tail/skip/hex_extract/dedup），支持正则，可独立 CLI 或 GUI 内嵌使用",
            "批量解析标签页工具栏新增「预处理」命令输入框 +「执行」按钮 +「?」帮助按钮，输入命令链后对输入框内容执行预处理并回填结果",
        ],
    ),
    (
        "1.11.1",
        "2026-08-04",
        [
            "修复勾选「ED监控协议」后不完整/非法 ED..EE 帧被静默回退为 FC 起始解析的 bug：单帧解析、解析弹窗、批量解析三处路径在 ED 头剥离失败时均明确报错（报文不完整/缺 EF 或 EE），首字节 ED 不再被当作南网新一代 FC 起始符",
            "新增 test_ed_fallback_fix.py（14 用例，覆盖单帧/弹窗/批量三条路径的失败报错与完整 ED 帧回归）",
        ],
    ),
    (
        "1.11.0",
        "2026-08-01",
        [
            "新一代载波协议(通感一体化,索引9)网间协调帧(NET,定界符类型=3)可变区域解析：邻居网络比特图1~4 / 本网络无线信道编号 / 持续时间(40ms) / 带宽结束标志位 / 本网络无线option / 带宽结束偏移(4ms) / 带宽开始偏移(4ms)，字节12短网络标识高位组合完整SNID",
            "新一代载波协议聚合帧(物理块聚合标志=1)级联块应用层解析：抽取 _parse_msdu_payload 共享方法，级联块内 MAC 帧解析 MSDU 头(VLAN/MSDU类型)并按类型分派应用层报文(端口/控制域/业务标识/转发DLT645)，消除伪 MSDU 残留行",
            "新增 test_net_frame_real / test_net_frame_nonzero_fields / test_aggregated_frame_app_layer 回归用例",
        ],
    ),
    (
        "1.10.0",
        "2026-07-31",
        [
            "新增「主题与字体设置」（菜单 配置→主题与字体）：5 套主题（默认浅色 / Fusion 经典 / Fusion 暗色 / Windows 原生 / Windows Vista 原生），切换即时预览",
            "全局样式表升级为应用级：QMessageBox / 文件对话框等所有弹窗统一跟随主题",
            "字体设置：字体族（系统字体列表）+ 字号（8~24pt），与主题一起持久化到 config.json 的 ui 段",
            "暗色主题下自动适配统计标签 / 串口状态 / 批量状态等动态控件配色",
            "新增 theme_settings.py（主题注册表 + ThemeManager + ThemeSettingsDialog）与 test_theme_settings.py",
        ],
    ),
    (
        "1.9.5",
        "2026-06-27",
        [
            "国网新一代(索引10)自动区分 HDC 1.0(旧版双模) / HDC 2.0(新一代)：依据FC字节12 D[7:4]标准版本号",
            "FC解析后新增「协议版本判定」行，据此自动选择MAC帧头解析规则(0=HDC 1.0, 1=HDC 2.0)",
            "标准MAC帧头：HDC 1.0下 D5(聚合帧标志)/发送帧序号/链路标识符 三处新增字段回退标注为「保留」",
            "单跳MAC帧头：HDC 1.0用旧消息类型表(0=发现列表消息)、D7标注保留；HDC 2.0用新表(0=无线发现列表)、D7=聚合帧标志",
            "std_version 参数贯穿 parse_to_table→_parse_msdu_from_frame/_parse_pb_by_frame_type→_parse_mac_header→标准/单跳帧头",
            "参考旧版规范 Q/GDW 12087.41/42-2020(国网新一代协议/HDC-国网双模协议 PDF)；test_gw_new_gen.py 新增3组版本区分用例(共36断言)",
        ],
    ),
    (
        "1.9.4",
        "2026-06-27",
        [
            "国网新一代(索引10)解析级别新增「FC+PB解析(完整MPDU)」：FC(16B) + 完整物理块PB(PBH 1B + MAC帧头 + MSDU)",
            "修正「FC+MAC解析」未计算物理块头PBH(1B)的缺陷：原直接从偏移16解析MAC, 导致MAC头错位1字节",
            "fc_mac 现用 _locate_pbh_mac 定位 PBH+MAC, 正确先显示 PBH 行再解析 MAC 帧头",
        ],
    ),
    (
        "1.9.3",
        "2026-06-27",
        [
            "修复国网新一代(索引10)完整帧结构解析：正确的帧格式为 FC(16B) + PB(物理块)",
            "PB = PBH(物理块头,1B) + MAC帧头 + MSDU；FC末3字节为FCCS(FC自身CRC校验), 其后直接为PB, 无独立HCS",
            "原代码误设 FC 后有 HCS(3B)+PBH(1B) 跳4字节, 导致 MAC 头从错误偏移解析(版本无效、TEI错乱)",
            "新增 _locate_pbh_mac：用 FC 的源/目的TEI 强校验定位 PBH+MAC 起始, 正确跳过1字节PBH",
            "新增 _pbh_row 生成物理块头行(D[5:0]=序列号 D6=帧起始 D7=帧结束)",
        ],
    ),
    (
        "1.9.2",
        "2026-06-27",
        [
            "国网新一代(索引10)监控/批量摘要增强：对齐参考监控工具风格体现关键业务信息",
            "摘要字段：网络标识(NID)|帧类型(信标/SOF/选择确认/网间协调)|管理消息类型(MMTYPE)|源→目的TEI|msduSeq|单播/广播|报文ID+方向|报文序号|规约(698.45)|数据长度",
            "新增 _get_gw_new_gen_summary（按去缩进字段名索引，FC级优先），接入监控器与批量摘要两处",
            "新增 test_gw_monitor_summary.py（11个断言，复用 MainWindow 方法免 GUI 驱动）",
        ],
    ),
    (
        "1.9.1",
        "2026-06-27",
        [
            "监控器新增「监控解帧(96..16)」模式(默认开启)：按监控设备包装格式自动解帧，彻底解决串口连帧",
            "包装格式 96H+RSSI(1)+NTB(4,小端)+[LEN(12b)+协议类型(3b)+CHANNEL(1b)]+DATA(LEN)+CS(1)+16H",
            "按 LEN 定界逐包抽取，正确处理连帧与 DATA 内含 0x16 的情况；分片到达自动缓存补齐",
            "伪帧头(LEN超限/帧尾非0x16)自动跳过恢复；CS校验(帧头到CS前累加和&0xFF)错误时标红",
            "详情表前置监控包装头信息(RSSI/NTB/协议类型/CHANNEL/CS)，摘要加[RSSI/信道/CS]前缀",
            "开启解帧时禁用静默间隔/剔除设置(由LEN自动定界)；新增 test_monitor_deframe.py(7用例)",
        ],
    ),
    (
        "1.9.0",
        "2026-07-08",
        [
            "新增「监控器」标签页：南网新一代(9)/国网新一代(10)协议实时报文监控",
            "串口原始字节流按静默间隔(默认30ms，10-200ms可调)自动组帧并实时解析",
            "监控器支持解析前剔除报文头/尾字节(包装头+校验尾)，剔除后的帧用于解析/详情HEX/字节高亮",
            "左侧帧列表(序号/时间/方向/长度/摘要)环形缓冲1000帧，支持自动滚动/暂停/清空/导出CSV",
            "右侧详情：完整解析表格+原始HEX，点击解析行高亮对应字节；双击帧行送入单帧解析页",
            "新增 monitor_widget.py（RealtimeMonitorWidget 组件）与 test_monitor_widget.py",
        ],
    ),
    (
        "1.8.2",
        "2026-07-06",
        [
            "新增「报文对比」标签页：双报文字节级/字段级对比分析，支持字段感知对齐",
            "支持差异高亮（修改/新增/删除）、人话解读、忽略校验和/序列号、导出报告",
            "新增 frame_diff_engine.py（对比引擎）和 diff_widget.py（GUI 组件）",
            "新增 TUI 版本：tui_app.py + tui_app.tcss，基于 Textual 框架，支持单帧解析+字节高亮、批量多帧解析+摘要、协议一致性校验",
            "新增 NiceGUI Web 版本（web_app.py + web/）：基于 NiceGUI 框架的浏览器解析器，支持完整 10 种协议解析、单帧/批量/报文对比/组帧/预设/查询/测试计划/档案/拓扑等标签页，集成串口通信，暗色主题，健康检查端点 /health",
            "新增 enhanced_export.py：Excel 增强导出（协议元数据、字节高亮样式、分 Sheet 导出），CSV/TXT/JSON 多格式导出",
        ],
    ),
    (
        "1.8.1",
        "2026-06-27",
        [
            "测试方案新增 Lua 脚本支持：可在测试流程中嵌入可编程逻辑，支持条件分支、循环遍历、数据解析、变量共享",
            "新增 lua_script_engine.py（Lua 脚本引擎），提供 send/wait/log/hex_to_bytes 等 API 函数",
            "依赖：lupa（Python-Lua 桥接，pip install lupa）",
        ],
    ),
    (
        "1.8.0",
        "2026-07-04",
        [
            "新增 DLMS-APDU(国网) 协议选项（索引3），使用 HDLC 解析器的 APDU 深度解析功能",
            "HDLC/DLMS 协议重命名为 HDLC/国网DLMS，明确国网协议背景",
            "协议索引重新编号：原 3~8 顺延为 4~9，共 10 种协议",
        ],
    ),
    (
        "1.7.2",
        "2026-06-21",
        [
            "修复新一代载波协议（索引8）选择确认帧(SACK)解析：字节12正确解析为扩展帧类型+标准版本号",
            "SACK子解析器返回值修正，与其他帧类型子解析器保持一致",
        ],
    ),
    (
        "1.7.1",
        "2026-06-18",
        [
            "新一代载波协议（索引8）批量解析：新增监控日志前缀剥离，支持 '<时间> <序号> -> 接收机 Has Get <15字节监控头> <协议报文>' 格式",
            "新一代载波协议批量解析摘要：区分网络层/应用层报文，展示 MSDU 类型、MMTYPE、定界符类型、业务标识等关键业务内容",
            "修复：过滤掉非监控前缀且非纯 hex 的日志行（如时间戳、测试标记、中文说明），避免被误解析为伪帧",
        ],
    ),
    (
        "1.7.0",
        "2026-06-18",
        [
            "新增 DL/T 698.45-2017 协议（协议索引7）支持：链路层解析器、APDU 解析器、A-XDR 编解码、OI 查询、帧生成器、校验器",
            "新增 新一代载波协议（通感一体化，协议索引8）支持：MAC/MSDU 帧解析、应用层业务报文解析、命令载荷解析、校验器",
            "新一代载波协议支持 4 种解析级别切换：自动识别 / FC+PB 完整 MPDU / 仅 FC / 应用层报文",
            "新增新一代载波协议业务标识查询页面",
            "组帧/预设标签页扩展支持 698.45 协议（dlt698 模式）",
            "校验引擎统一接入 DLT69845Validator 与 CSGNewGenValidator",
            "新增 crcmod 依赖（698.45 CRC 使用 X-25 / CRC16）",
        ],
    ),
    (
        "1.6.8",
        "2026-05-09",
        [
            "档案管理：修复缺失 json 导入导致导出失败的问题",
            "档案管理：修复协议切换时错误清空档案数据的问题",
            "拓扑信息：新增组网完成时间统计功能（自动刷新模式）",
        ],
    ),
    (
        "1.6.7",
        "2026-04-30",
        [
            "修复南网协议DI字节序解析（恢复小端序，修复DI查找匹配）",
            "修复查询运行参数信息(E8 03 03 74)数据内容解析器IndexError",
            "修复国网验证器长度域校验逻辑（长度域值即帧总长度）",
            "南网/国网控制域位域显示二进制位值（D7~D0）",
            "国网信息域位域显示二进制位值（D0~D7）",
        ],
    ),
    (
        "1.6.6",
        "2026-04-30",
        [
            "修复DI解析字节序问题，恢复小端序正确匹配DI_COMBINATION_MAP",
        ],
    ),
    (
        "1.6.5",
        "2026-04-22",
        [
            "系统性修复字节序解析：所有多字节字段按小端序（低字节在前）解析",
            "修复ASCII字段反转：厂商代码/芯片代码等2字节ASCII正确反转显示",
            "修复BCD字段反转：版本时间/版本日期/版本号等按传输顺序反转后解析",
            "修复所有int.from_bytes大端序为小端序，符合协议低字节在前规范",
            "修复组帧引擎默认字节序为小端序，确保发送帧字节序正确",
            "修复_bcd_to_str支持非标准BCD十六进制（如0xC0显示为C0）",
        ],
    ),
    (
        "1.6.4",
        "2026-04-22",
        [
            "修复BCD日期解析：版本时间/版本日期/协议发布日期按BCD码原值显示",
            "修复BCD版本号解析：多字节BCD字段按小端序反转后显示",
            "修复批量查询厂商信息中的BCD日期和版本号解析",
        ],
    ),
    (
        "1.6.3",
        "2026-04-22",
        [
            "添加任务字段优化：任务模式字拆分为响应标识/转发标识/优先级下拉选择",
            "添加任务字段优化：报文内容拆分为业务代码（下拉）+报文有效内容（输入）",
            "添加任务支持条件字段：业务代码仅在转发标识=1时自动打包进报文",
            "引擎支持sub_fields位域合并和条件子字段打包",
            "添加多播任务同样支持任务模式字位域拆分",
        ],
    ),
    (
        "1.6.2",
        "2026-04-22",
        [
            "修正字段定义：移除多余字段（启动/暂停任务、查询白名单生效信息）",
            "修正字段定义：补充缺失字段（重启节点等待时长、台区识别保留字节等）",
            "修正字段定义：修复字段名与文档不匹配问题（无线参数、台区识别等）",
            "修正字段定义：为15个查询命令补充下行参数字段",
            "修正字段定义：统一多字节数值字段为小端序",
        ],
    ),
    (
        "1.6.1",
        "2026-04-22",
        [
            "协议组帧功能完善：支持88个下行DI命令",
            "命令说明弹窗支持非模态显示，可同时编辑主窗口",
            "字段模板表格和按钮布局优化，纵向空间更紧凑",
            "命令说明内容来源于PLUZ计量自动化系统技术规范文档",
            "串口通信支持配置、发送、日志和接收帧解析",
        ],
    ),
    (
        "1.6.0",
        "2026-04-21",
        [
            "新增国网协议(Q/GDW 10376.2-2024)解析支持",
            "支持国网协议AFN+Fn组合查询功能",
            "国网协议支持单帧解析、批量解析、字节高亮",
            "支持国网协议控制域、信息域、地址域、应用数据域完整解析",
        ],
    ),
    (
        "1.5.0",
        "2026-04-17",
        [
            "重构主界面代码，精简655行GUI代码，优化协议解析工具结构",
            "增强南网协议解析器，扩展控制域与用户数据区解析能力",
            "优化PyInstaller构建配置，提升打包稳定性与兼容性",
        ],
    ),
    (
        "1.4.0",
        "2026-04-16",
        [
            "修复表格交替行颜色失效的问题（stylesheet优化）",
            "新增AGENTS.md项目指南文件，便于AI辅助开发",
            "PyInstaller打包配置修复：添加custom_di.json和dlt645_di.json到datas",
        ],
    ),
    (
        "1.3.0",
        "2026-04-16",
        [
            "修复查询页面切换时按钮残留问题（递归清理layout）",
            "修复命令字查询页缺失的4个方法（_load_command_map_data等）",
            '修复命令字表格"十六进制"列显示十进制的bug，简化为2列',
            '新增菜单栏与"关于"对话框',
        ],
    ),
    (
        "1.2.0",
        "2026-04-16",
        [
            "优化HDLC解析器，修复APDU数据解析中的索引错误",
            "新增Wrapper帧提取功能",
        ],
    ),
    (
        "1.1.0",
        "2026-04-15",
        [
            "优化HDLC解析器，增强对返回数据和未知响应类型的处理",
            "更新主界面，改善协议选择和输入提示",
        ],
    ),
    (
        "1.0.1",
        "2026-04-15",
        [
            "新增README文档",
            "更新编译后的二进制文件",
        ],
    ),
    (
        "1.0.0",
        "2026-04-14",
        [
            "初始版本发布",
            "支持南网协议/PLC RF/HDLC/DLMS多协议解析",
            "单帧解析与批量解析功能",
            "DI/命令字/OBIS查询功能",
        ],
    ),
]


def _field_leading(name: str) -> int:
    """返回字段名的前导空格数"""
    return len(name) - len(name.lstrip(" "))


def _field_level_map(names) -> dict:
    """把一张表里出现的不同前导空格深度归一化为层级 1,2,3...。

    各解析器缩进单位不一（有的 2 空格一级、有的 4 空格一级），
    按"出现的不同深度排序"映射，保证层级浅且父子关系一致。
    """
    depths = sorted({_field_leading(n) for n in names if _field_leading(n) > 0})
    return {d: i + 1 for i, d in enumerate(depths)}


def _format_tree_field(name: str, level: int):
    """按层级生成树形标签，返回 (显示名, 层级)。

    层级>0 加 "└" 前缀，每深一级额外增加 4 空格横向间距。
    """
    stripped = name.lstrip(" ")
    if level <= 0:
        return stripped, 0
    indent = "    " * (level - 1)
    return f"{indent}  └ {stripped}", level


# ── 国网新一代(索引10) / HDC 1.0(索引11) 应用层端口号 ──────────────────────────
# 依据《双模通信互联互通技术规范 第4-3部分：应用层通信协议》§5.2.2「报文端口号」：
#   升级业务取值为 0x12，其他业务取值为 0x11；鉴权安全为 0x1A。
# 权威来源是**解析器端口表**（hdc10_parser.APP_PORTS / gw_new_gen_parser.PORT_NAMES），
# 这里只在 import 失败时回落，避免再出现第三份硬编码端口副本——早期 app 级别判据
# 只认 '11'，把 0x12 开头的升级业务帧整批丢掉（AGENTS §8 陷阱 43）。
_GW_APP_PORT_PREFIXES_FALLBACK = ("11", "12", "1A")


def _gw_app_port_prefixes(protocol_index: int) -> tuple:
    """按协议返回应用层端口号（大写 hex 字符串）集合，取自解析器端口表。

    Args:
        protocol_index: 10=国网新一代 / 11=HDC 1.0

    Returns:
        tuple[str, ...]：如 ("11", "12", "1A")
    """
    try:
        if protocol_index == 11:
            import hdc10_parser

            ports = hdc10_parser.APP_PORTS
        else:
            import gw_new_gen_parser

            ports = gw_new_gen_parser.GWNewGenParser.PORT_NAMES
        return tuple(f"{port:02X}" for port in ports)
    except Exception:
        # 解析器模块不可用（打包缺失等）时回落内置三元组，不让 GUI 抛异常
        return _GW_APP_PORT_PREFIXES_FALLBACK


# ── 应用层报文摘要：业务名 + 关键业务字段（协议10/11 共用同一规则）─────────────
# 应用层报文表的业务信息分布两种布局：协议11 的业务名在「── 业务数据 ──」区头行
# （字段名自带，如 `  开始升级`）、业务字段在其下（`    升级ID` 等）；协议10 无区头，
# 业务名已作为「报文ID」的解析值给出（`开始升级`），业务字段与元数据平铺（`  升级ID`）。
# 两条规则合并后即可用同一份代码覆盖两协议（详见 AGENTS §8 相关条目）。
#
# _GW_APP_META_FIELDS：元数据字段（非业务语义），**不占**关键字段位；收两协议字段名
# 的并集，避免漏排（如协议10 的「安全机制」vs 协议11 的「安全模式」）。
_GW_APP_META_FIELDS = (
    "报文端口号",
    "报文ID",
    "安全模式",
    "安全机制",
    "业务报文ID",
    "报文控制字",
    "协议版本号",
    "报文头长度",
    "控制/保留",
    "数据长度",
    "报文序号",
    "转发数据规约类型",
    "转发数据长度",
    "规约类型",
    "发送类型",
    "MSDU类型",
    "⚠ 安全保护",
)
# 关键业务字段个数（用户选定 2；调这里即可改变摘要长度）
_GW_APP_SUMMARY_KEY_FIELDS = 2


def _gw_app_biz_summary(table_data) -> tuple:
    """从应用层报文表中提取 (业务名, [关键业务字段…])。

    业务名（按优先级）：
      ① `── 业务数据` 区头之后的首个普通行字段名（协议11 布局，如 `开始升级`）；
      ② 「报文ID」解析值——**仅当它不是 hex 形式**时视为业务名（协议10 布局）；
      都不命中时返回空串（摘要退化为现状，不报错）。

    关键业务字段：在**应用层/业务数据段窗口内**（见下），字段名带前导空格（业务/子字段层）、
    非元数据、非分隔行/业务名行、解析值非空且不是「N字节」占位符，按顺序取前
    `_GW_APP_SUMMARY_KEY_FIELDS` 个，格式 `字段名:解析值`。

    扫描窗口：起点 = `── 业务数据` 行 +1（协议11 布局）；无该区头时 = 顶层
    「应用层报文」行 +1（协议10/auto 布局）；终点 = 起点之后首个**顶层行**（无缩进）
    或表尾。**不能全表扫描**：真实 MPDU 在 auto/fc_pb 级别下 FC/MAC 字段
    （`版本`/`原始源TEI`/`定界符类型`/`网络类型`）排在应用层之前，会被当成业务字段。
    """
    import re

    if not table_data:
        return "", []

    def _raw_name(item):
        return str(item[0]) if item and item[0] is not None else ""

    def _name(item):
        return _raw_name(item).strip()

    def _parsed(item):
        if not item or len(item) <= 2 or item[2] in (None, ""):
            return ""
        return str(item[2]).strip()

    def _is_meta(name):
        return any(
            name == meta or name.startswith(meta) for meta in _GW_APP_META_FIELDS
        )

    def _is_skippable(name):
        return (
            not name
            or name.startswith("──")
            or name.startswith("❌")
            or name.startswith("⚠")
        )

    # ── 扫描窗口：限定在「应用层报文 / 业务数据」段内 ──
    # 不能全表扫描：真实 MPDU 在 auto/fc_pb 级别下 FC/MAC 字段（`版本`/`原始源TEI`/
    # `定界符类型`/`网络类型`）排在应用层之前，会被当成业务字段（实测 6/6 真实帧中招）。
    window_start, window_end, from_biz_section = -1, -1, False
    # ① 优先：业务数据区（协议11 布局——业务名与业务字段都在区内，
    #    必须先于「应用层报文」区头检查：两个区头在同一表里按先后出现）
    for i, item in enumerate(table_data):
        if _name(item).startswith("── 业务数据"):
            window_start, from_biz_section = i + 1, True
            break
    # ② 回退：顶层「应用层报文」行（协议10/auto 布局，无业务数据区）
    if window_start < 0:
        for i, item in enumerate(table_data):
            name, raw_name = _name(item), _raw_name(item)
            if not raw_name.startswith(" ") and "应用层报文" in name:
                window_start = i + 1
                break
    if window_start < 0:
        return "", []
    for j in range(window_start, len(table_data)):
        if not _raw_name(table_data[j]).startswith(" "):  # 下一个顶层行 = 段结束
            window_end = j
            break
    window = table_data[
        window_start : window_end if window_end >= 0 else len(table_data)
    ]

    # ── 业务名 ──
    biz_name = ""
    biz_row_idx = -1
    if from_biz_section:
        # 协议11：`── 业务数据 ──` 之后首个带缩进的普通行，其字段名即业务名
        for k, item in enumerate(window):
            if not _raw_name(item).startswith(" ") or _is_skippable(_name(item)):
                continue
            biz_name, biz_row_idx = _name(item), window_start + k
            break
    if not biz_name:
        # 协议10：无业务数据区，业务名由「报文ID」解析值给出（非 hex 形式）
        for item in table_data:
            if _name(item) != "报文ID":
                continue
            parsed = _parsed(item)
            if parsed and not re.fullmatch(r"(0[xX])?[0-9A-Fa-f]+", parsed):
                biz_name = parsed
            break

    # ── 关键业务字段（只在窗口内扫描）──
    fields = []
    for i, item in enumerate(window):
        raw_name = _raw_name(item)
        name, parsed = _name(item), _parsed(item)
        if window_start + i == biz_row_idx or not parsed:
            continue
        # 只取带前导空格的字段行（顶层行不是业务字段）
        if not raw_name.startswith(" "):
            continue
        if _is_skippable(name) or _is_meta(name):
            continue
        if re.fullmatch(r"\d+字节", parsed):  # 字节数占位（区头/长度行）
            continue
        fields.append(f"{name}:{parsed}")
        if len(fields) >= _GW_APP_SUMMARY_KEY_FIELDS:
            break

    return biz_name, fields


# 配置文件路径标签映射
FILE_PATH_LABELS = {
    "nw_command": "南网预设命令",
    "gw_command": "国网预设命令",
    "test_plan": "测试方案",
    "custom_di": "南网自定义DI",
    "dlt645_di": "DLT645 DI映射",
    "gdw_custom_afn": "国网自定义AFN",
    "command": "PLC RF命令字",
}


class ConfigDialog(QDialog):
    """配置文件路径管理对话框"""

    def __init__(self, file_paths: dict[str, str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("配置管理")
        self.setMinimumWidth(650)
        self._file_paths = dict(file_paths)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        desc = QLabel(
            "管理各配置文件的存储路径。支持相对路径（相对于程序目录）或绝对路径。"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666;")
        layout.addWidget(desc)

        # 表格布局：每行 = 标签 + 路径输入 + 浏览按钮
        self._inputs: dict[str, QLineEdit] = {}
        for key, label in FILE_PATH_LABELS.items():
            row = QHBoxLayout()
            row.setSpacing(8)

            lbl = QLabel(f"{label}:")
            lbl.setFixedWidth(110)
            lbl.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            row.addWidget(lbl)

            edit = QLineEdit()
            edit.setText(self._file_paths.get(key, ""))
            edit.setPlaceholderText(f"默认: {key}.json")
            self._inputs[key] = edit
            row.addWidget(edit, 1)

            btn = QPushButton("浏览...")
            btn.setFixedWidth(70)
            btn.clicked.connect(
                lambda checked=False, k=key, e=edit: self._browse_file(k, e)
            )
            row.addWidget(btn)

            layout.addLayout(row)

        layout.addStretch()

        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        save_btn = QPushButton("保存")
        set_btn(save_btn, "success", "lg")
        save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(save_btn)

        cancel_btn = QPushButton("取消")
        set_btn(cancel_btn, "secondary", "lg")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _browse_file(self, key: str, edit: QLineEdit):
        """弹出文件选择对话框"""
        current = edit.text().strip()
        start_dir = str(app_data_dir())
        if current:
            p = Path(current)
            if not p.is_absolute():
                p = app_data_dir() / p
            if p.parent.exists():
                start_dir = str(p.parent)

        path, _ = QFileDialog.getOpenFileName(
            self,
            f"选择 {FILE_PATH_LABELS.get(key, key)}",
            start_dir,
            "JSON 文件 (*.json);;所有文件 (*.*)",
        )
        if path:
            # 尽量保存为相对路径
            try:
                rel = Path(path).relative_to(app_data_dir())
                edit.setText(str(rel))
            except ValueError:
                edit.setText(path)

    def _on_save(self):
        """保存按钮点击"""
        for key, edit in self._inputs.items():
            val = edit.text().strip()
            if val:
                self._file_paths[key] = val
            elif key in self._file_paths:
                del self._file_paths[key]
        self.accept()

    def get_file_paths(self) -> dict[str, str]:
        return self._file_paths


class DragDropTextEdit(QTextEdit):
    """支持拖拽文件加载的 QTextEdit"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if file_path and os.path.isfile(file_path):
                    try:
                        encodings = ["utf-8", "gbk", "gb2312", "latin-1"]
                        content = None
                        for enc in encodings:
                            try:
                                with open(file_path, encoding=enc) as f:
                                    content = f.read()
                                break
                            except (UnicodeDecodeError, UnicodeError):
                                continue
                        if content is None:
                            with open(
                                file_path, encoding="utf-8", errors="replace"
                            ) as f:
                                content = f.read()
                        self.setPlainText(content)
                        # 通知父窗口文件已加载
                        main_win = self.window()
                        if hasattr(main_win, "update_stats"):
                            import os as _os

                            fname = _os.path.basename(file_path)
                            lines = content.splitlines()
                            main_win.update_stats(
                                f"已拖入文件 {fname}（{len(lines)} 行）"
                            )
                        # 拖入即建立原始日志快照（预处理只改输入框，快照永不动）
                        mw = self.window()
                        if hasattr(mw, "_set_batch_snapshot"):
                            import os as _os

                            mw._set_batch_snapshot(
                                content, _os.path.basename(file_path)
                            )
                    except Exception as e:
                        from PySide6.QtWidgets import QMessageBox

                        QMessageBox.critical(self, "错误", f"读取文件失败：{e}")
            event.acceptProposedAction()


class FlowLayout(QLayout):
    """自动换行布局：空间不足时把控件排到下一行，永不重叠。

    用于顶部协议选择组——不同协议动态显示的解析级别/通道/剔除等控件数量不一，
    单行 QHBoxLayout 在窄窗/高DPI 下会把所有控件最小宽挤到重叠。
    基于 Qt 官方 FlowLayout 示例实现。

    默认按各自 sizeHint 靠左排（协议组口径）。``stretch=True`` 时把**行内剩余宽度**
    按权重分给 ``addWidget(w, stretch)`` 指定的子项与 ``addStretch()`` 弹性空隙，
    于是「宽屏吃满整行」和「窄屏自动折行、永不重叠」能同时成立（QHBoxLayout 只有
    前者，纯 FlowLayout 只有后者）。
    """

    def __init__(self, parent=None, margin=0, spacing=-1, stretch=False):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self._items = []
        self._stretch = stretch
        self._weights = {}

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self._items.append(item)

    def addWidget(self, widget, stretch=0):
        """加控件；``stretch>0`` 时在 ``stretch=True`` 的布局里按权重分剩余宽度。"""
        super().addWidget(widget)
        if stretch:
            self._weights[self._items[-1]] = stretch

    def addStretch(self, stretch=1):
        """弹性空隙：吃掉本行剩余宽度（用于把后面的控件顶到行右端）。"""
        item = QSpacerItem(
            0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        self.addItem(item)
        self._weights[item] = stretch

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        """单行自然尺寸（语义对齐 QHBoxLayout.sizeHint：各子项 sizeHint 之和）。

        不能直接返回 minimumSize()：它是「各子项最小尺寸的逐分量最大值」（≈最宽单项），
        父布局会照这个宽度只给这么宽 → 本布局被迫换行 → 高度翻倍并超出父容器高度，
        第二行（协议下拉框）被裁成一条缝，启动时看起来是空白，点一下才刷新。
        返回单行总宽后，父布局首轮即给足宽度，正常情况不会换行；窗口真窄时父布局仍可
        压到 minimumSize()，_do_layout 照旧换行（换行能力不受影响）。
        """
        total_w = 0
        max_h = 0
        visible = 0
        for item in self._items:
            wid = item.widget()
            if wid is not None and not wid.isVisible():
                continue
            hint = item.sizeHint()
            total_w += hint.width()
            max_h = max(max_h, hint.height())
            visible += 1
        if visible > 1:
            total_w += self.spacing() * (visible - 1)
        m = self.contentsMargins()
        return QSize(total_w + m.left() + m.right(), max_h + m.top() + m.bottom())

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            wid = item.widget()
            if wid is not None and not wid.isVisible():
                continue
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _row_widths(self, items, avail_width):
        """一行内各子项的最终宽度（默认就是各自 sizeHint，不做任何拉伸）。

        ``stretch=True`` 时把行内剩余宽度按 ``addWidget(w, stretch)`` /
        ``addStretch()`` 记下的**权重**分配下去：下拉框吃满整行、弹性空隙把后面的
        控件顶到行右端。权重为 0 的控件（按钮）永远保持 sizeHint 宽 —— 拉伸按钮会
        变成一排大宽块。
        """
        widths = [hint.width() for _, hint, _, _ in items]
        if not self._stretch or not widths:
            return widths
        used = sum(widths) + self.spacing() * (len(widths) - 1)
        leftover = avail_width - used
        if leftover <= 0:
            return widths
        weighted = []
        for i, entry in enumerate(items):
            weight = self._weights.get(entry[0])
            if weight:
                weighted.append((i, weight))
        if not weighted:
            return widths
        total = sum(w for _, w in weighted)
        given = 0
        for idx, weight in weighted[:-1]:
            add = leftover * weight // total
            widths[idx] += add
            given += add
        # 除不尽的余数给最后一个：免得行右端留下 1~2px 缝
        widths[weighted[-1][0]] += leftover - given
        return widths

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y = effective.x(), effective.y()
        line_height = 0
        row_items = []
        # 先按行收集，再统一垂直居中布局（标签比下拉框矮时不顶对齐）
        rows = []
        for item in self._items:
            wid = item.widget()
            if wid is not None and not wid.isVisible():
                continue
            hint = item.sizeHint()
            space_x = self.spacing()
            space_y = self.spacing()
            next_x = x + hint.width() + space_x
            # 弹性空隙不参与换行判定：否则窄屏下它会独占一行、凭空多 6px 高度
            is_gap = item.spacerItem() is not None
            if next_x - space_x > effective.right() and line_height > 0 and not is_gap:
                rows.append((row_items, line_height))
                x = effective.x()
                y = y + line_height + space_y
                next_x = x + hint.width() + space_x
                line_height = 0
                row_items = []
            row_items.append((item, hint, x, y))
            x = next_x
            line_height = max(line_height, hint.height())
        rows.append((row_items, line_height))

        if not test_only:
            for items, lh in rows:
                widths = self._row_widths(items, effective.width())
                # 拉伸只改宽度，x 是按原始 hint 排出来的：被拉宽的项必须把后面
                # 同一行的项一起往右推，否则宽的下拉框会盖住后面的按钮。
                shift = 0
                for (it, hint, ix, iy), w in zip(items, widths):
                    # 行内垂直居中
                    cy = iy + (lh - hint.height()) // 2
                    it.setGeometry(
                        QRect(QPoint(ix + shift, cy), QSize(w, hint.height()))
                    )
                    shift += w - hint.width()

        if rows:
            last_lh = rows[-1][1]
        else:
            last_lh = 0
        return y + last_lh - rect.y() + m.bottom()


def _app_icon_path() -> Path:
    """app_icon.ico 定位：frozen 优先 _MEIPASS 内置资源，缺失回退 exe 目录；开发模式项目根。

    spec 的 datas 必须含 ('app_icon.ico', '.')：否则 frozen 下 _MEIPASS 无此文件，
    窗口/托盘图标静默缺失（exe 在资源管理器里的文件图标是构建期 icon= 嵌入，
    与运行时窗口图标无关）。
    """
    p = resource_path("app_icon.ico")
    if not p.exists():
        p = app_data_dir() / "app_icon.ico"
    return p


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # 最小尺寸按屏幕自适应：低分屏（如 1366×768）下固定 1000×700 超出可视区，
        # 布局被压缩到小于控件最小尺寸时 Qt 会出现控件重叠
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            self.setMinimumSize(
                min(1000, int(avail.width() * 0.85)),
                min(700, int(avail.height() * 0.8)),
            )
        else:
            self.setMinimumSize(1000, 700)
        self.setWindowTitle(
            f"协议解析工具 v{APP_VERSION} ({BUILD_DATE}) - 作者: liruitao"
        )
        # 窗口/任务栏图标（托盘另用同文件，见 sys_tray）
        _app_icon = _app_icon_path()
        if _app_icon.exists():
            self.setWindowIcon(QIcon(str(_app_icon)))

        # 协议选择：0=南网协议，1=PLC RF协议，2=HDLC/国网DLMS，3=DLMS-APDU(国网)，4=Wrapper，5=APDU，6=DLT645，7=国网协议，8=698.45，9=新一代载波协议(通感一体化)
        self.current_protocol = 0

        # 新一代载波协议解析级别：auto=自动, fc_pb=FC+PB, fc_only=仅FC, app=应用层
        self._csg_parse_level = "auto"
        self._pending_frame_gen_mode = "south"
        self._pending_archive_mode = "south"
        self._pending_topology_mode = "south"
        self._lazy_tab_guard = False
        # 时序图⇄摘要表双向联动防循环标志（模式同 _lazy_tab_guard）
        self._seq_sync_guard = False
        # 字节剔除缓存：记录上次剔除后成功解析的hex，避免重复剔除
        self._csg_last_stripped_hex = ""

        # 国网新一代解析级别：auto=自动, fc_pb=FC+完整PB, fc_only=仅FC, fc_mac=FC+PB头+MAC, app=应用层
        self._gw_parse_level = "auto"
        # HDC 1.0解析级别
        self._hdc10_parse_level = "auto"
        self._hdc10_channel = "plc"

        # 批量解析结果缓存
        self.batch_results: list[dict[str, Any]] = []
        # 批量解析后台线程（任务 09-15-gui-batch-parse-perf 步骤 2）：
        # 逐帧解析在工作线程跑，UI 线程只做剥离/清洗/提取（同步）与攒批回填；
        # _batch_strip_map = 待交给 worker 的前缀剥离行映射快照
        self._batch_worker: BatchParseWorker | None = None
        self._batch_total: int = 0
        self._batch_strip_map: list[int] | None = None
        self._batch_cancelling: bool = False
        # 详情按需（步骤 3）：batch_results 不再常驻每帧完整解析表
        # （49,532 帧 = 229 MB → 约 4 MB），详情/导出/时序图按需重解析并走
        # LRU（上限 50 帧）；`_batch_parse_params` / `_batch_ed_wrapper` 是
        # 启动解析时的参数快照，重解析必须用同一套参数否则与批量结果不一致
        self._detail_cache: OrderedDict[int, list] = OrderedDict()
        self._detail_cache_max: int = 50
        self._batch_parse_params: dict | None = None
        self._batch_ed_wrapper: str = "auto"
        # 详情重解析专用解析器实例（不与共享单例混用；参数变化时重建）
        self._detail_parser_obj: Any = None
        self._detail_parser_key: tuple | None = None
        # 步骤 4：关键词过滤去抖（250 ms）——连续按键不再各跑一次全表 setRowHidden
        # （实测 49,532 行下 0.87 s/按键）；状态下拉不走去抖（点一下应立刻生效）
        self._batch_filter_timer = QTimer(self)
        self._batch_filter_timer.setSingleShot(True)
        self._batch_filter_timer.setInterval(250)
        self._batch_filter_timer.timeout.connect(self._on_batch_filter_changed)

        # 批量输入原始日志快照（拖入/打开/粘贴时建立；回填式预处理只改输入框
        # 不改快照；摘要表右键「转到原始报文位置」在快照中定位，09-10 任务）
        self._batch_snapshot_text: str = ""
        self._batch_snapshot_name: str = ""
        self._snapshot_hex_cache = None  # (snapshot_text, stream, line_of)
        self._snapshot_hits = {}  # frame_hex → 快照内全部命中 [(s,e),...]（随快照重建清空）
        self._src_viewer = None  # 原始日志查看器（非模态单实例）

        # 字节高亮映射
        self._byte_ranges: list = []

        # 上次单帧解析的 hex（供报文对比载入）
        self._last_parsed_hex: str | None = None

        # 应用配置（先加载，setup_ui 会用到）
        self._config_path = data_path("config.json")
        self._app_config: dict[str, Any] = {}
        self._file_paths: dict[str, Path] = {}
        self._load_app_config()

        # 主题与字体配置（应用级样式由 main() 在 QApplication 上应用，此处仅保存配置供动态控件适配）
        self._theme_id, self._font_family, self._font_size = (
            ThemeManager.load_from_config(self._app_config)
        )
        self._glass_settings = ThemeManager.load_glass_config(self._app_config)
        # 外观模式（浅色 / 深色 / 跟随系统）：与主题正交，右上角太阳/月亮图标切换
        self._appearance_mode = ThemeManager.load_mode(self._app_config)
        self._system_dark = ThemeManager.detect_system_dark()
        # 系统集成配置（config.json "system" 段）
        self._system_settings: dict[str, Any] = {}
        self._load_system_settings()
        self._stats_labels: list[tuple] = []  # (QLabel, 字号) 列表，主题切换时统一重设
        self._serial_status_color = "#999"  # 串口状态标签当前颜色（主题切换时重设）
        self._serial_status_bold = False  # 串口状态标签当前是否粗体（主题切换时重设）
        # 自动更新配置（config.json "update" 段）
        self._update_settings: dict[str, Any] = {}
        self._load_update_settings()
        from auto_updater import merge_update_config

        # 默认更新源 = 作者 GitHub 仓库的 Release（地址唯一来源仍是 AUTHOR_GITHUB_URL）
        self._update_settings = merge_update_config(
            self._update_settings, repo_url=AUTHOR_GITHUB_URL
        )

        self.setup_ui()
        self._setup_menu_bar()
        # 菜单栏图标按钮在 _setup_menu_bar 创建；套用顶栏折叠态须在其后
        self._apply_top_bar_collapse_state()
        self._update_window_title()

        # 跟随系统外观：系统深浅色变化时实时跟随（只有 mode == system 才真正应用）
        try:
            _app = QApplication.instance()
            if _app is not None:
                _app.styleHints().colorSchemeChanged.connect(
                    self._on_system_color_scheme_changed
                )
        except Exception:  # noqa: BLE001 - 老 Qt 没有 colorSchemeChanged
            pass

        # 发现新版本不再弹窗打扰：状态栏右下角常驻绿色⬆提示，点击可选择下载更新
        self._pending_update = None
        self._update_status_lbl = _UpdateStatusLink()
        self._update_status_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_status_lbl.clicked.connect(self._on_update_status_clicked)
        self._update_status_lbl.hide()
        self.statusBar().addPermanentWidget(self._update_status_lbl)

        # 系统集成管理器（托盘 / 全局热键 / 单实例）
        self._setup_system_integration()

        # 启动延迟自动检查更新 + 周期循环检查（网络失败静默；每 30 分钟重查一次，
        # 覆盖"程序长期运行、作者中途发布新版本"的场景）
        if self._update_settings.get(
            "check_on_start", True
        ) and self._update_settings.get("enabled", True):
            QTimer.singleShot(3000, self._auto_check_update)
            self._update_poll_timer = QTimer(self)
            self._update_poll_timer.setInterval(30 * 60 * 1000)  # 30 分钟
            self._update_poll_timer.timeout.connect(self._auto_check_update)
            self._update_poll_timer.start()
        # 状态栏：CPU/内存（慢刷新 4s，避免影响 GUI 性能）+ 线程数（1s，点击弹明细）
        self._proc_stats = proc_stats.ProcessStats()
        self._cpu_mem_lbl = QLabel("CPU: --  内存: --")
        self._cpu_mem_lbl.setStyleSheet("color: #607D8B; padding: 0 8px;")
        self._cpu_mem_lbl.setToolTip(
            "本软件自身的资源占用（CPU 为整机口径，与任务管理器一致；内存为工作集/峰值）\n"
            "每 4 秒刷新一次，采样开销微秒级，不影响界面流畅度"
        )
        self.statusBar().addPermanentWidget(self._cpu_mem_lbl)
        self._cpu_mem_timer = QTimer(self)
        self._cpu_mem_timer.setInterval(4000)  # 慢刷新：资源统计无需高频
        self._cpu_mem_timer.timeout.connect(self._refresh_cpu_mem)
        self._cpu_mem_timer.start()
        self._refresh_cpu_mem()  # 首次仅内存（CPU 需两次采样基线）

        self._thread_count_lbl = QLabel("线程: -")
        self._thread_count_lbl.setStyleSheet("color: #607D8B; padding: 0 8px;")
        self._thread_count_lbl.setToolTip("当前应用存活的工作线程数（点击查看明细）")
        self._thread_count_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._thread_count_lbl.mousePressEvent = self._on_thread_count_clicked
        self.statusBar().addPermanentWidget(self._thread_count_lbl)
        self._thread_count_timer = QTimer(self)
        self._thread_count_timer.setInterval(1000)
        self._thread_count_timer.timeout.connect(self._refresh_thread_count)
        self._thread_count_timer.start()
        self._refresh_thread_count()

        # 状态栏：串口配置折叠时的紧凑回显（端口 · 波特率 · 校验 · 连接状态）
        self._serial_statusbar_lbl = QLabel("")
        self._serial_statusbar_lbl.setStyleSheet("color: #607D8B; padding: 0 8px;")
        self._serial_statusbar_lbl.setToolTip(
            "串口配置面板折叠时，在此显示端口 / 波特率 / 校验位 / 连接状态"
        )
        self.statusBar().addPermanentWidget(self._serial_statusbar_lbl)
        self._serial_statusbar_lbl.hide()
        # 顶栏折叠态/标题在菜单栏图标就绪后套用（见 __init__ 中 _setup_menu_bar 之后）
        self._update_serial_statusbar()
        # 几何在 setup_ui 内已恢复；按最终宽度再算一次协议名居中（showEvent 还会再刷）
        self._update_window_title()

    @property
    def parser(self):
        return get_parser("south")

    @property
    def plc_rf_parser(self):
        return get_parser("plc_rf")

    @property
    def hdlc_parser(self):
        return get_parser("hdlc")

    @property
    def dlt645_parser(self):
        return get_parser("dlt645")

    @property
    def gdw_parser(self):
        return get_parser("gdw")

    @property
    def dl_t698_45_parser(self):
        return get_parser("dl_t698_45")

    @property
    def csg_new_gen_parser(self):
        return get_parser("csg_new_gen")

    @property
    def gw_new_gen_parser(self):
        return get_parser("gw_new_gen")

    @property
    def hdc10_parser(self):
        return get_parser("hdc10")

    def setup_ui(self):
        """设置UI布局"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # ========== 顶部栏：协议选择 + 串口配置（整体可隐藏，开关在菜单栏右上角） ==========
        # 折叠时整行一起消失（协议→窗口标题中间，串口→状态栏），不再占任何高度
        self.top_bar_widget = QWidget()
        top_bar = QHBoxLayout(self.top_bar_widget)
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(6)

        # ---- 协议选择分组 ----
        proto_group = QGroupBox("协议选择")
        self.proto_group = proto_group
        # FlowLayout：协议 9/10 动态显示的辅助控件多时自动换行，窄窗/高DPI 下不重叠
        proto_layout = FlowLayout(proto_group, margin=4, spacing=6)

        proto_label = QLabel("当前协议：")
        proto_label.setFont(self._ui_font(0, bold=True))
        proto_label.setFixedWidth(65)
        proto_layout.addWidget(proto_label)

        self.protocol_combo = QComboBox()
        for label in protocol_registry.combo_labels():
            self.protocol_combo.addItem(label)
        self.protocol_combo.setMinimumWidth(150)
        self.protocol_combo.setFont(self._ui_font(0))
        # 不使用 AdjustToContents：它把控件撑到列表中最长协议名宽度。
        # 改为按当前选中项文字自适应宽度，切换协议时实时收/放（见 _fit_combo_to_current）。
        self.protocol_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.protocol_combo.setMinimumContentsLength(10)
        self.protocol_combo.currentIndexChanged.connect(self._on_protocol_changed)
        proto_layout.addWidget(self.protocol_combo)
        # 初始按选中项拟合一次（控件已创建、未 show 时 fontMetrics 即可用）
        self._fit_combo_to_current(self.protocol_combo, min_w=120)

        # ---- 新一代载波协议解析级别选择（仅协议索引9时可见）----
        self.csg_parse_level_label = QLabel("解析级别：")
        self.csg_parse_level_label.setFont(self._ui_font(-1))
        proto_layout.addWidget(self.csg_parse_level_label)

        self.csg_parse_level_combo = QComboBox()
        self.csg_parse_level_combo.addItem("自动识别", "auto")
        self.csg_parse_level_combo.addItem("FC+PB解析(完整MPDU)", "fc_pb")
        self.csg_parse_level_combo.addItem("FC+eFC解析", "fc_efc")
        self.csg_parse_level_combo.addItem("仅FC解析", "fc_only")
        self.csg_parse_level_combo.addItem("应用层报文", "app")
        self.csg_parse_level_combo.addItem("仅MAC帧", "mac_only")
        self.csg_parse_level_combo.addItem("仅PB解析(完整物理块)", "pb_only")
        self.csg_parse_level_combo.setFont(self._ui_font(-1))
        self.csg_parse_level_combo.currentIndexChanged.connect(
            self._on_csg_parse_level_changed
        )
        self.csg_parse_level_combo.setVisible(False)
        proto_layout.addWidget(self.csg_parse_level_combo)
        self.csg_parse_level_label.setVisible(False)
        self._fit_combo_to_current(self.csg_parse_level_combo, min_w=90)

        # ---- 南网新一代通道选择（仅协议索引9时可见）----
        self.csg_channel_label = QLabel("通道：")
        self.csg_channel_label.setFont(self._ui_font(-1))
        self.csg_channel_label.setVisible(False)
        proto_layout.addWidget(self.csg_channel_label)

        self.csg_channel_combo = QComboBox()
        self.csg_channel_combo.addItem("自动识别", "auto")
        self.csg_channel_combo.addItem("PLC 载波", "plc")
        self.csg_channel_combo.addItem("HRF 无线", "hrf")
        self.csg_channel_combo.setFont(self._ui_font(-1))
        # 从配置恢复
        csg_ch = getattr(self, "_csg_channel", "auto")
        idx = self.csg_channel_combo.findData(csg_ch)
        if idx >= 0:
            self.csg_channel_combo.setCurrentIndex(idx)
        self.csg_channel_combo.currentIndexChanged.connect(self._on_csg_channel_changed)
        self.csg_channel_combo.setVisible(False)
        proto_layout.addWidget(self.csg_channel_combo)
        self._fit_combo_to_current(self.csg_channel_combo, min_w=96)

        # ---- 南网新一代PB帧类型选择（仅pb_only模式可见）----
        self.csg_pb_frame_type_label = QLabel("帧类型：")
        self.csg_pb_frame_type_label.setFont(self._ui_font(-1))
        self.csg_pb_frame_type_label.setVisible(False)
        proto_layout.addWidget(self.csg_pb_frame_type_label)

        self.csg_pb_frame_type_combo = QComboBox()
        self.csg_pb_frame_type_combo.addItem("SOF帧", "sof")
        self.csg_pb_frame_type_combo.addItem("信标帧", "beacon")
        self.csg_pb_frame_type_combo.addItem("ACK帧(SACK)", "sack")
        self.csg_pb_frame_type_combo.addItem("NET帧", "net")
        self.csg_pb_frame_type_combo.setFont(self._ui_font(-1))
        self.csg_pb_frame_type_combo.setMinimumWidth(120)
        self.csg_pb_frame_type_combo.setVisible(False)
        proto_layout.addWidget(self.csg_pb_frame_type_combo)

        # ---- 新一代载波协议字节剔除（仅协议索引9时可见）----
        self.csg_strip_head_label = QLabel("剔除前:")
        self.csg_strip_head_label.setFont(self._ui_font(-1))
        self.csg_strip_head_label.setVisible(False)
        proto_layout.addWidget(self.csg_strip_head_label)

        self.csg_strip_head_spin = QSpinBox()
        self.csg_strip_head_spin.setRange(0, 999)
        self.csg_strip_head_spin.setValue(0)
        self.csg_strip_head_spin.setSuffix(" 字节")
        self.csg_strip_head_spin.setFont(self._ui_font(-1))
        self.csg_strip_head_spin.setVisible(False)
        self.csg_strip_head_spin.setToolTip("解析前剔除报文头部指定字节数（0=不剔除）")
        proto_layout.addWidget(self.csg_strip_head_spin)

        self.csg_strip_tail_label = QLabel("尾部:")
        self.csg_strip_tail_label.setFont(self._ui_font(-1))
        self.csg_strip_tail_label.setVisible(False)
        proto_layout.addWidget(self.csg_strip_tail_label)

        self.csg_strip_tail_spin = QSpinBox()
        self.csg_strip_tail_spin.setRange(0, 999)
        self.csg_strip_tail_spin.setValue(0)
        self.csg_strip_tail_spin.setSuffix(" 字节")
        self.csg_strip_tail_spin.setFont(self._ui_font(-1))
        self.csg_strip_tail_spin.setVisible(False)
        self.csg_strip_tail_spin.setToolTip("解析前剔除报文尾部指定字节数（0=不剔除）")
        proto_layout.addWidget(self.csg_strip_tail_spin)

        # ---- 国网新一代解析级别选择（仅协议索引10时可见）----
        self.gw_parse_level_label = QLabel("解析级别：")
        self.gw_parse_level_label.setFont(self._ui_font(-1))
        self.gw_parse_level_label.setVisible(False)
        proto_layout.addWidget(self.gw_parse_level_label)

        self.gw_parse_level_combo = QComboBox()
        self.gw_parse_level_combo.addItem("自动识别", "auto")
        self.gw_parse_level_combo.addItem("FC+PB解析(完整MPDU)", "fc_pb")
        self.gw_parse_level_combo.addItem("仅FC解析", "fc_only")
        self.gw_parse_level_combo.addItem("仅MAC帧", "mac_only")
        self.gw_parse_level_combo.addItem("仅PB", "pb_only")
        self.gw_parse_level_combo.addItem("FC+MAC解析", "fc_mac")
        self.gw_parse_level_combo.addItem("应用层报文", "app")
        self.gw_parse_level_combo.setFont(self._ui_font(-1))
        self.gw_parse_level_combo.currentIndexChanged.connect(
            self._on_gw_parse_level_changed
        )
        self.gw_parse_level_combo.setVisible(False)
        proto_layout.addWidget(self.gw_parse_level_combo)
        self._fit_combo_to_current(self.gw_parse_level_combo, min_w=90)

        # ---- 国网新一代PB帧类型选择（仅pb_only模式可见）----
        self.gw_pb_frame_type_label = QLabel("帧类型：")
        self.gw_pb_frame_type_label.setFont(self._ui_font(-1))
        self.gw_pb_frame_type_label.setVisible(False)
        proto_layout.addWidget(self.gw_pb_frame_type_label)

        self.gw_pb_frame_type_combo = QComboBox()
        self.gw_pb_frame_type_combo.addItem("SOF帧", 1)
        self.gw_pb_frame_type_combo.addItem("信标帧", 0)
        self.gw_pb_frame_type_combo.addItem("ACK帧(SACK)", 2)
        self.gw_pb_frame_type_combo.addItem("NET帧", 3)
        self.gw_pb_frame_type_combo.setFont(self._ui_font(-1))
        self.gw_pb_frame_type_combo.setMinimumWidth(120)
        self.gw_pb_frame_type_combo.setVisible(False)
        proto_layout.addWidget(self.gw_pb_frame_type_combo)

        # ---- 国网新一代通道选择（仅协议索引10时可见）----
        self.gw_channel_label = QLabel("通道：")
        self.gw_channel_label.setFont(self._ui_font(-1))
        self.gw_channel_label.setVisible(False)
        proto_layout.addWidget(self.gw_channel_label)

        self.gw_channel_combo = QComboBox()
        self.gw_channel_combo.addItem("PLC 载波", "plc")
        self.gw_channel_combo.addItem("HRF 无线", "hrf")
        self.gw_channel_combo.setFont(self._ui_font(-1))
        self.gw_channel_combo.setMinimumWidth(100)
        # 从配置恢复
        gw_ch = getattr(self, "_gw_channel", "plc")
        idx = self.gw_channel_combo.findData(gw_ch)
        if idx >= 0:
            self.gw_channel_combo.setCurrentIndex(idx)
        self.gw_channel_combo.currentIndexChanged.connect(self._on_gw_channel_changed)
        self.gw_channel_combo.setVisible(False)
        proto_layout.addWidget(self.gw_channel_combo)

        top_bar.addWidget(proto_group, 1)

        # ---- 串口配置分组 ----
        serial_group = QGroupBox("串口配置")
        self.serial_group = serial_group
        serial_layout = QHBoxLayout(serial_group)
        serial_layout.setContentsMargins(8, 4, 8, 4)
        serial_layout.setSpacing(6)

        serial_layout.addWidget(QLabel("端口:"))
        self.serial_port_combo = QComboBox()
        self.serial_port_combo.setMinimumWidth(80)
        serial_layout.addWidget(self.serial_port_combo)

        self.serial_refresh_btn = QPushButton()
        self.serial_refresh_btn.setIcon(app_icons.load_icon("refresh-cw"))
        self.serial_refresh_btn.setToolTip("刷新串口列表")
        self.serial_refresh_btn.setMaximumWidth(30)
        self.serial_refresh_btn.setMinimumHeight(24)
        self.serial_refresh_btn.setFlat(True)
        self.serial_refresh_btn.setStyleSheet(self._serial_refresh_style())
        from PySide6.QtCore import QSize

        self.serial_refresh_btn.setIconSize(QSize(18, 18))
        self.serial_refresh_btn.clicked.connect(self._refresh_serial_ports)
        serial_layout.addWidget(self.serial_refresh_btn)

        serial_layout.addWidget(QLabel("波特率:"))
        self.serial_baud_combo = QComboBox()
        self.serial_baud_combo.setEditable(True)  # 允许手动输入自定义波特率
        self.serial_baud_combo.addItems(
            [
                "1200",
                "2400",
                "4800",
                "9600",
                "19200",
                "38400",
                "57600",
                "115200",
                "230400",
                "460800",
                "921600",
                "1000000",
                "2000000",
                "3000000",
            ]
        )
        self.serial_baud_combo.setCurrentText("9600")
        self.serial_baud_combo.setMinimumWidth(80)
        serial_layout.addWidget(self.serial_baud_combo)

        serial_layout.addWidget(QLabel("校验:"))
        self.serial_parity_combo = QComboBox()
        self.serial_parity_combo.addItems(["无", "偶", "奇"])
        self.serial_parity_combo.setMinimumWidth(60)
        serial_layout.addWidget(self.serial_parity_combo)

        self.serial_open_btn = QPushButton("打开串口")
        set_btn(self.serial_open_btn, "success")
        set_btn_icon(self.serial_open_btn, "open")
        self.serial_open_btn.setMinimumWidth(76)
        self.serial_open_btn.clicked.connect(self._on_serial_open_clicked)
        serial_layout.addWidget(self.serial_open_btn)

        self.serial_status_label = QLabel("未连接")
        self.serial_status_label.setStyleSheet(self._serial_status_style("#999"))
        serial_layout.addWidget(self.serial_status_label)

        serial_layout.addStretch()
        top_bar.addWidget(serial_group)

        # 串口参数变化时刷新状态栏紧凑回显（顶栏折叠时用户改不到，但连接状态仍可能变）
        self.serial_port_combo.currentTextChanged.connect(self._update_serial_statusbar)
        self.serial_baud_combo.currentTextChanged.connect(self._update_serial_statusbar)
        self.serial_parity_combo.currentTextChanged.connect(
            self._update_serial_statusbar
        )

        main_layout.addWidget(self.top_bar_widget)

        # ========== 串口工作线程 ==========
        self.serial_worker = SerialWorker()
        self.serial_worker.connection_changed.connect(
            self._on_serial_connection_changed
        )
        self.serial_worker.error_occurred.connect(self._on_serial_error)
        # 热切换波特率（协议8 升级页「提升波特率」）由持口方自行完成，这里只同步回显
        self.serial_worker.baudrate_changed.connect(self._on_serial_baudrate_changed)
        self._refresh_serial_ports()
        self._load_serial_config()

        # 选项卡（图标为 Lucide 线性图标，颜色随亮/暗主题自适应，见 app_icons.py）
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(
            self.create_single_parse_tab(),
            app_icons.load_icon("terminal"),
            "单帧解析",
        )
        # 查询页面根据协议动态创建
        self.protocol_lookup_tab = QWidget()
        self.protocol_lookup_tab_layout = QVBoxLayout(self.protocol_lookup_tab)
        self.tab_widget.addTab(
            self.protocol_lookup_tab, app_icons.load_icon("search"), "查询"
        )
        self._batch_tab_index = self.tab_widget.addTab(
            self.create_batch_parse_tab(), app_icons.load_icon("files"), "批量解析"
        )
        # 通信时序图页面（协议9批量解析结果可视化，懒加载，仅协议9可见）
        self._seq_diagram_placeholder = QWidget()
        self._seq_diagram_tab_index = self.tab_widget.addTab(
            self._seq_diagram_placeholder,
            app_icons.load_icon("waypoints"),
            "通信时序图",
        )
        self.tab_widget.setTabVisible(self._seq_diagram_tab_index, False)
        # 协议组帧页面（南网和国网协议支持）
        self._frame_gen_placeholder = QWidget()
        self._frame_gen_tab_index = self.tab_widget.addTab(
            self._frame_gen_placeholder, app_icons.load_icon("wrench"), "协议组帧"
        )
        # 预设命令页面（传入配置文件路径）
        self.preset_tab = PresetButtonWidget(
            nw_path=self._file_paths.get("nw_command"),
            gw_path=self._file_paths.get("gw_command"),
        )
        self.preset_tab.set_serial_worker(self.serial_worker)
        self._preset_tab_index = self.tab_widget.addTab(
            self.preset_tab, app_icons.load_icon("bookmark"), "预设命令"
        )
        self.preset_tab.button_clicked.connect(self._on_preset_button_clicked)
        # 测试方案页面（传入配置文件路径）
        self.test_plan_tab = TestPlanWidget(
            file_path=self._file_paths.get("test_plan"),
        )
        self.test_plan_tab.set_serial_worker(self.serial_worker)
        self._test_plan_tab_index = self.tab_widget.addTab(
            self.test_plan_tab, app_icons.load_icon("clipboard-list"), "测试方案"
        )
        # 档案管理页面（南网和国网协议支持）
        self._archive_placeholder = QWidget()
        self._archive_tab_index = self.tab_widget.addTab(
            self._archive_placeholder, app_icons.load_icon("archive"), "档案管理"
        )

        # 拓扑信息页面（南网和国网协议支持）
        self._topology_placeholder = QWidget()
        self._topology_tab_index = self.tab_widget.addTab(
            self._topology_placeholder, app_icons.load_icon("network"), "拓扑信息"
        )

        # 报文对比页面
        self.diff_tab = DiffWidget()
        self.diff_tab.restyle_for_theme(self._is_dark_theme())
        self._diff_tab_index = self.tab_widget.addTab(
            self.diff_tab, app_icons.load_icon("file-diff"), "报文对比"
        )

        # 报文工具页面（所有协议可见）
        self.message_tool_tab = MessageToolWidget()
        self.tab_widget.addTab(
            self.message_tool_tab, app_icons.load_icon("toolbox"), "报文工具"
        )

        # 频谱图页面（频谱仪参数 + trace 数值 → 仪器式网格频谱图，与协议无关常驻）
        self.spectrum_tab = SpectrumWidget()
        self.spectrum_tab.restyle_for_theme(self._is_dark_theme())
        self._spectrum_tab_index = self.tab_widget.addTab(
            self.spectrum_tab, app_icons.load_icon("chart-spline"), "频谱图"
        )

        # 虚拟表（协议8 从站模拟器）
        self.virtual_meter_tab = VirtualMeterWidget()
        self._virtual_meter_tab_index = self.tab_widget.addTab(
            self.virtual_meter_tab, app_icons.load_icon("gauge"), "虚拟表"
        )
        self.virtual_meter_tab.parse_requested.connect(
            self._on_virtual_meter_send_to_parser
        )
        self.tab_widget.setTabVisible(self._virtual_meter_tab_index, False)

        # DLT645 虚拟表（协议6 从站模拟器）
        self.dlt645_sim_tab = Dlt645VirtualMeterWidget()
        self._dlt645_sim_tab_index = self.tab_widget.addTab(
            self.dlt645_sim_tab, app_icons.load_icon("gauge"), "645虚拟表"
        )
        self.dlt645_sim_tab.parse_requested.connect(
            self._on_virtual_meter_send_to_parser
        )
        self.tab_widget.setTabVisible(self._dlt645_sim_tab_index, False)

        # TCP 流量监控器页面（始终可见）
        self._tcp_monitor_placeholder = QWidget()
        self._tcp_monitor_tab_index = self.tab_widget.addTab(
            self._tcp_monitor_placeholder, app_icons.load_icon("radar"), "TCP监控"
        )

        # 串口工具页面（始终可见；集成自 USB 负载测试工具）
        self._serial_tool_placeholder = QWidget()
        self._serial_tool_tab_index = self.tab_widget.addTab(
            self._serial_tool_placeholder, app_icons.load_icon("cable"), "串口工具"
        )

        # 蓝牙工具页面（始终可见；集成自蓝牙转串口工具）
        self._bluetooth_tool_placeholder = QWidget()
        self._bluetooth_tool_tab_index = self.tab_widget.addTab(
            self._bluetooth_tool_placeholder, app_icons.load_icon("bluetooth"), "蓝牙工具"
        )

        # 生产测试架页面（串口助手 + 测试架参数帧；始终可见，懒加载）
        self._testbench_placeholder = QWidget()
        self._testbench_tab_index = self.tab_widget.addTab(
            self._testbench_placeholder, app_icons.load_icon("flask-conical"), "生产测试架"
        )

        # 协议8 光伏升级页（698.45 文件传输升级；注册表 has_upgrade，仅协议8 可见；懒加载，
        # 创建即隐藏 —— 构造期 _on_protocol_changed 可能一次都不触发，协议专属 tab
        # 必须在创建处设隐藏）
        self._upgrade_placeholder = QWidget()
        self._upgrade_tab_index = self.tab_widget.addTab(
            self._upgrade_placeholder, app_icons.load_icon("hard-drive-upload"), "光伏升级"
        )
        self.tab_widget.setTabVisible(self._upgrade_tab_index, False)

        # 协议8「协议测试」页（按 OAD 分类的预置测试库；注册表 has_test，仅协议8 可见；
        # 懒加载、创建即隐藏 —— 理由同上：构造期 _on_protocol_changed 可能一次都不触发）
        self._test_placeholder = QWidget()
        self._test_tab_index = self.tab_widget.addTab(
            self._test_placeholder, app_icons.load_icon("flask-conical"), "协议测试"
        )
        self.tab_widget.setTabVisible(self._test_tab_index, False)

        # 实时监控器页面（南网新一代(9)/国网新一代(10) 专用，默认隐藏）
        self.monitor_tab = RealtimeMonitorWidget()
        self.monitor_tab.set_serial_worker(self.serial_worker)
        self.monitor_tab.set_send_to_single_handler(self._send_frame_to_single_parse)
        self._monitor_tab_index = self.tab_widget.addTab(
            self.monitor_tab, app_icons.load_icon("activity"), "监控器"
        )
        self.tab_widget.setTabVisible(self._monitor_tab_index, False)

        main_layout.addWidget(self.tab_widget, 1)

        # 毛玻璃主题下切 tab 可能残留上一页半透明像素（WA_TranslucentBackground
        # 不保证擦除 backing store）。切换时强制新旧页面重绘，消除 tab 重影。
        self.tab_widget.currentChanged.connect(self._on_tab_changed_repaint)
        self.tab_widget.currentChanged.connect(self._ensure_lazy_tab)

        # 初始化查询页面内容
        self._update_protocol_lookup_tab()

        # 统一设置中文右键菜单（在标签页创建完成后应用）
        self._apply_chinese_menus_to_all_tabs()

        # 恢复上次使用的协议（持久化：方便用户下次启动免选择）
        self._restore_saved_protocol()
        # 「窗口曾被真正显示过」标志：只有显示过的窗口才值得保存几何。
        # 否则每次构造即关闭的调用方（测试、单帧/命令行解析路径）都会把
        # 一个从未示人的合成几何写进用户 config.json，下次启动就套用上去。
        self._window_shown_once = False
        # 套用上次退出时保存的窗口几何 / 分栏 / 列宽（缺失/损坏/屏外均回落默认）
        self._apply_window_state()
        # 顶栏折叠态在 _setup_menu_bar 之后套用（开关在菜单栏角标）
        self._ui_ready = True  # UI 构造完成，此后协议切换才写盘

        # 分隔条拖动/尺寸变化后，子控件旧位置可能残留像素（Windows DWM 合成
        # 下半透明样式控件不保证擦除），强制父容器重绘消除分隔区域重影。
        for sp in self.findChildren(QSplitter):

            def _force_parent_rep(_a=None, _b=None, s=sp):
                p = s.parentWidget()
                if p is not None:
                    p.update()

            try:
                sp.splitterMoved.connect(_force_parent_rep)
            except Exception:
                pass

    def _restore_saved_protocol(self):
        """启动时恢复上次选择的协议索引（config parse.protocol）"""
        saved = getattr(self, "_saved_protocol", 0)
        if 0 <= saved < self.protocol_combo.count():
            self.protocol_combo.setCurrentIndex(saved)

    def create_single_parse_tab(self) -> QWidget:
        """创建单帧解析标签页 - 上下布局"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        # === 上方：输入区 ===
        input_group = QGroupBox("输入报文")
        input_layout = QVBoxLayout(input_group)

        self.single_input = QTextEdit()
        self.single_input.setPlaceholderText(
            "请输入十六进制报文，支持空格、逗号、换行等分隔符，例如：68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16"
        )
        self.single_input.setMaximumHeight(80)
        input_layout.addWidget(self.single_input)

        # 按钮行
        btn_layout = QHBoxLayout()
        self.parse_btn = QPushButton("解析报文")
        set_btn(self.parse_btn, "primary", "lg")
        set_btn_icon(self.parse_btn, "play")
        self.parse_btn.clicked.connect(self.parse_single)
        btn_layout.addWidget(self.parse_btn)

        self.verify_btn = QPushButton("校验报文")
        set_btn(self.verify_btn, "primary", "lg")
        set_btn_icon(self.verify_btn, "ok")
        self.verify_btn.clicked.connect(self.verify_single)
        btn_layout.addWidget(self.verify_btn)

        # 「校验该帧」：勾选=严格解析（默认，帧不完整/校验不过就报错）；
        # 取消=容错解析，按实收字节能拆多少拆多少，拆不动的原样输出。
        self.verify_frame_chk = QCheckBox("校验该帧")
        self.verify_frame_chk.setChecked(
            bool(self._app_config.get("single_parse", {}).get("verify", True))
        )
        self.verify_frame_chk.setToolTip(
            "勾选（默认）：要求帧结构、长度自洽、HCS/FCS 通过才解析，"
            "不完整时报「解析失败」。\n"
            "取消：按实收字节容错解析，能拆到哪算哪，剩余字节以「未解析字节 / 原始报文」原样输出。\n"
            "目前仅 698.45（协议8）支持容错解析。"
        )
        self.verify_frame_chk.setMinimumHeight(32)
        btn_layout.addWidget(self.verify_frame_chk)
        self._sync_verify_frame_chk()

        self.add_to_test_btn = QPushButton("添加到测试方案")
        set_btn(self.add_to_test_btn, "success", "lg")
        set_btn_icon(self.add_to_test_btn, "apply")
        self.add_to_test_btn.clicked.connect(self._add_parsed_to_test_plan)
        btn_layout.addWidget(self.add_to_test_btn)

        self.share_frame_btn = QPushButton("分享此帧")
        self.share_frame_btn.setToolTip(
            "把当前解析的报文分享到 Web 服务端（所有人可在「报文分享」页查看）"
        )
        set_btn(self.share_frame_btn, "warning", "lg")
        # Qt 标准图标无 share 字形（set_btn_icon 未知键静默跳过，致此前该按钮无图标
        # 与同排不一致）；改用图标库 Lucide share-2 线性图标，颜色随主题/按钮 palette 自适应
        from PySide6.QtCore import QSize as _QSize

        self.share_frame_btn.setIcon(app_icons.load_icon("share-2"))
        self.share_frame_btn.setIconSize(_QSize(16, 16))  # 与同排 set_btn_icon 尺寸一致
        self.share_frame_btn.clicked.connect(self._show_share_dialog)
        btn_layout.addWidget(self.share_frame_btn)

        clear_btn = QPushButton("清空")
        set_btn(clear_btn, "secondary", "lg")
        set_btn_icon(clear_btn, "clear")
        clear_btn.clicked.connect(self.clear_single)
        btn_layout.addWidget(clear_btn)

        # CRC 填充按钮
        self.fill_crc24_btn = QPushButton("填充CRC-24")
        set_btn(self.fill_crc24_btn, "warning", "lg")
        set_btn_icon(self.fill_crc24_btn, "apply")
        self.fill_crc24_btn.clicked.connect(self._fill_crc24)
        btn_layout.addWidget(self.fill_crc24_btn)

        self.fill_crc32_btn = QPushButton("填充CRC-32")
        set_btn(self.fill_crc32_btn, "accent", "lg")
        set_btn_icon(self.fill_crc32_btn, "apply")
        self.fill_crc32_btn.clicked.connect(self._fill_crc32)
        btn_layout.addWidget(self.fill_crc32_btn)

        # ED 监控协议勾选项（仅南网新一代协议显示）
        self.ed_monitor_chk = QCheckBox("ED监控协议")
        self.ed_monitor_chk.setToolTip(
            "勾选后解析 ED..EE 监控包装头（PLC2.0 / 广西台体），\n"
            "前置显示 RSSI/NTB/信道等信息，再解析业务帧。\n"
            "适用于协议9 / 10 / 11"
        )
        self.ed_monitor_chk.setVisible(False)
        btn_layout.addWidget(self.ed_monitor_chk)

        # ED 包装头格式选择（仅协议9显示）：自动识别 / PLC2.0 台体 15B 头 / 广西台体 14B 头
        self.ed_wrapper_combo = QComboBox()
        self.ed_wrapper_combo.addItem("自动识别(推荐)", "auto")
        self.ed_wrapper_combo.addItem("PLC2.0 台体(15字节头)", "plc2")
        self.ed_wrapper_combo.addItem("广西台体(14字节头)", "gx")
        self.ed_wrapper_combo.setToolTip(
            "ED..EE 监控包装头格式：\n"
            "自动识别：逐帧按业务帧 FC 特征 + 物理块长度自洽性打分判别\n"
            "PLC2.0 台体：数据域公共头 9 字节，业务帧自第 15 字节起\n"
            "广西台体/国网HDC：数据域公共头 8 字节（布局相同，文案随协议切换）"
        )
        self.ed_wrapper_combo.setVisible(False)
        btn_layout.addWidget(self.ed_wrapper_combo)

        # 4字节反转勾选项（仅南网新一代协议显示）
        self.csg_reverse_4byte_chk = QCheckBox("4字节反转")
        self.csg_reverse_4byte_chk.setToolTip(
            "勾选后对输入 hex 按 4 字节一组做端序翻转（大端↔小端），\n"
            "例如 C9D50438 → 3804D5C9，再进行解析。\n"
            "适用于协议9 / 10 / 11"
        )
        self.csg_reverse_4byte_chk.setVisible(False)
        btn_layout.addWidget(self.csg_reverse_4byte_chk)

        btn_layout.addStretch()
        input_layout.addLayout(btn_layout)

        layout.addWidget(input_group)

        # === 下方：解析结果表格 ===
        result_group = QGroupBox("解析结果")
        result_layout = QVBoxLayout(result_group)

        self.result_table_widget = ZoomableTableWidget()
        self.result_table_widget.setColumnCount(4)
        self.result_table_widget.setHorizontalHeaderLabels(
            ["字段", "原始值", "解析值", "说明"]
        )
        # 允许用户拖拽调整列宽
        header = self.result_table_widget.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        # 设置默认列宽
        self.result_table_widget.setColumnWidth(0, 130)
        self.result_table_widget.setColumnWidth(1, 100)
        self.result_table_widget.setColumnWidth(2, 100)
        self.result_table_widget.setEditTriggers(QTableWidget.NoEditTriggers)
        self.result_table_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.result_table_widget.setAlternatingRowColors(True)
        self.result_table_widget.verticalHeader().hide()
        self.result_table_widget.verticalHeader().setDefaultSectionSize(13)
        table_font = self._ui_font(-2)
        self.result_table_widget.setFont(table_font)
        # 行高更紧凑
        self.result_table_widget.verticalHeader().setDefaultSectionSize(10)
        self.result_table_widget.verticalHeader().hide()
        # 右键复制菜单 + Ctrl+C
        self._setup_table_copy_menu(self.result_table_widget)

        # 选中行时高亮报文字节
        self.result_table_widget.currentCellChanged.connect(self._highlight_bytes)
        # 双击行时，提取该区域字节作为DLMS-APDU重新解析
        self.result_table_widget.doubleClicked.connect(self._extract_apdu_reparse)
        # 存储每行对应的字节范围
        self._byte_ranges: list = []

        # 字段树（Wireshark 风格）+ 视图切换
        from PySide6.QtGui import QColor as _QColor
        from PySide6.QtWidgets import QTreeWidget as _QTreeWidget
        from PySide6.QtWidgets import QTreeWidgetItem as _QTreeWidgetItem

        from parse_result_view import build_ui_tree

        ParseResultTree = build_ui_tree(
            _QTreeWidget, _QTreeWidgetItem, QHeaderView, _QColor
        )
        self.result_tree_widget = ParseResultTree(self.result_table_widget.parent() or self)
        self.result_tree_widget.setFont(table_font)
        self.result_tree_widget.apply_table_style(table_font)
        self.result_tree_widget.byte_range_clicked = self._highlight_byte_range
        self._last_table_data: list = []

        self.result_stack = QStackedWidget()
        self.result_stack.addWidget(self.result_table_widget)  # 0 表格
        self.result_stack.addWidget(self.result_tree_widget)  # 1 树
        self.result_view_combo = QComboBox()
        self.result_view_combo.addItem("表格", "table")
        self.result_view_combo.addItem("字段树", "tree")
        self.result_view_combo.setToolTip(
            "解析结果展示方式：表格（默认）或 Wireshark 风格字段树。\n"
            "选中树节点可高亮输入框中对应报文字节。"
        )
        self.result_view_combo.setMinimumWidth(90)
        self.result_view_combo.currentIndexChanged.connect(self._on_result_view_changed)

        # 导出图片按钮行
        export_row = QHBoxLayout()
        export_row.addWidget(QLabel("视图:"))
        export_row.addWidget(self.result_view_combo)
        export_row.addStretch()
        self.export_result_btn = QPushButton("导出图片")
        self.export_result_btn.setToolTip("将解析结果表格导出为完整的PNG图片")
        set_btn(self.export_result_btn, "primary")
        set_btn_icon(self.export_result_btn, "save")
        self.export_result_btn.setMinimumWidth(76)
        self.export_result_btn.clicked.connect(self._export_result_image)
        export_row.addWidget(self.export_result_btn)
        result_layout.addLayout(export_row)

        result_layout.addWidget(self.result_stack)

        # === 校验结果区域 ===
        self.verify_group = QGroupBox("校验结果")
        verify_layout = QVBoxLayout(self.verify_group)
        verify_layout.setContentsMargins(8, 8, 8, 8)
        verify_layout.setSpacing(4)

        # 头部按钮行：展开 / 收缩（收缩后仅保留标题+按钮行，内容进入滚动区）
        verify_head = QHBoxLayout()
        verify_head.addStretch()
        self.verify_expand_btn = QPushButton("展开")
        self.verify_collapse_btn = QPushButton("收缩")
        for b in (self.verify_expand_btn, self.verify_collapse_btn):
            set_btn(b, "secondary", "sm")
        self.verify_expand_btn.setEnabled(True)  # 默认收缩态
        self.verify_collapse_btn.setEnabled(False)
        self.verify_expand_btn.setToolTip("展开校验结果全文")
        self.verify_collapse_btn.setToolTip("收缩校验结果，仅保留摘要入口")
        self.verify_expand_btn.clicked.connect(self._on_verify_expand)
        self.verify_collapse_btn.clicked.connect(self._on_verify_collapse)
        verify_head.addWidget(self.verify_expand_btn)
        verify_head.addWidget(self.verify_collapse_btn)
        verify_layout.addLayout(verify_head)

        # 校验结果内容（滚动区，收缩时隐藏）
        self.verify_scroll = QScrollArea()
        self.verify_scroll.setWidgetResizable(True)
        self.verify_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.verify_label = QLabel("点击「校验报文」按钮进行协议一致性校验")
        self.verify_label.setWordWrap(True)
        self.verify_label.setFont(self._ui_font(-1, family="Consolas"))
        self.verify_scroll.setWidget(self.verify_label)
        verify_layout.addWidget(self.verify_scroll, 1)
        result_layout.addWidget(self.verify_group)

        # 默认收缩：布局就绪后收起校验结果区（仅标题+按钮行）
        QTimer.singleShot(0, self._on_verify_collapse)

        # 导出图片 + 全屏并排（右对齐一组）
        export_row.addWidget(self.export_result_btn)
        export_row.addLayout(
            self._make_table_fullscreen_btn(
                "解析结果 - 全屏", self.result_table_widget, with_stretch=False
            )
        )

        layout.addWidget(result_group, 1)

        return tab

    # ------------------------------------------------------------- 视图辅助
    def _make_table_fullscreen_btn(
        self, title: str, table: QTableWidget, with_stretch: bool = True
    ) -> QHBoxLayout:
        """构建右对齐「全屏」按钮：点击在新窗口全屏展示解析结果表格。

        与报文对比「结果详情」交互一致：弹窗内克隆表格快照展示，
        点「关闭」或窗口 X 关闭后主界面原样恢复。
        with_stretch=False 时按钮紧跟调用方已有 stretch 之后（与其他按钮并排）。
        """
        row = QHBoxLayout()
        row.setSpacing(6)
        if with_stretch:
            row.addStretch()
        fs_btn = QPushButton("全屏")
        fs_btn.setToolTip("在新窗口全屏展示解析结果表格，关闭窗口即恢复")
        set_btn(fs_btn, "secondary")
        set_btn_icon(fs_btn, "open")
        fs_btn.clicked.connect(lambda: self._open_table_popup(title, table))
        row.addWidget(fs_btn)
        return row

    def _open_table_popup(self, title: str, source_table: QTableWidget):
        """以独立弹窗全屏展示解析结果表格（克隆快照，关闭后主界面原样恢复）"""
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(1200, 700)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 克隆源表格内容为快照（读取型展示，不共享原表格）
        clone = ZoomableTableWidget(source_table.rowCount(), source_table.columnCount())
        headers = []
        for c in range(source_table.columnCount()):
            h = source_table.horizontalHeaderItem(c)
            headers.append(h.text() if h else "")
        clone.setHorizontalHeaderLabels(headers)
        for r in range(source_table.rowCount()):
            for c in range(source_table.columnCount()):
                item = source_table.item(r, c)
                if item:
                    clone.setItem(r, c, QTableWidgetItem(item.text()))
        # 外观对齐源表格
        header = clone.horizontalHeader()
        header.setStretchLastSection(True)
        src_header = source_table.horizontalHeader()
        for c in range(source_table.columnCount()):
            if src_header.sectionSize(c) > 20:
                clone.setColumnWidth(c, src_header.sectionSize(c))
        clone.setEditTriggers(QTableWidget.NoEditTriggers)
        clone.setSelectionBehavior(QTableWidget.SelectRows)
        clone.setAlternatingRowColors(True)
        clone.verticalHeader().hide()
        clone.setFont(source_table.font())
        layout.addWidget(clone, 1)

        # 关闭按钮
        btn_close = QPushButton("关闭")
        btn_close.setMinimumWidth(80)
        set_btn(btn_close, "secondary")
        btn_close.clicked.connect(dialog.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        dialog.exec()

    def _on_verify_expand(self):
        """展开校验结果全文"""
        self.verify_scroll.show()
        self.verify_group.setMaximumHeight(16777215)
        self.verify_expand_btn.setEnabled(False)
        self.verify_collapse_btn.setEnabled(True)

    def _on_verify_collapse(self):
        """收缩校验结果：隐藏内容，仅保留组标题和按钮行"""
        self.verify_scroll.hide()
        head_h = self.verify_collapse_btn.sizeHint().height() + 8
        # 26 ≈ QGroupBox 标题区 + 布局边距（随主题可能有差异，预留余量）
        self.verify_group.setMaximumHeight(head_h + 28)
        self.verify_expand_btn.setEnabled(True)
        self.verify_collapse_btn.setEnabled(False)

    def _export_result_image(self):
        """将解析结果表格导出为完整的PNG图片"""
        table = self.result_table_widget
        if table.rowCount() == 0:
            QMessageBox.warning(self, "提示", "当前没有解析结果可以导出！")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "导出解析结果图片",
            f"解析结果_{self.current_protocol}.png",
            "PNG 图片 (*.png)",
        )
        if not file_path:
            return

        # 保存当前状态
        orig_h = table.height()
        orig_min_h = table.minimumHeight()
        orig_max_h = table.maximumHeight()
        orig_vscroll_policy = table.verticalScrollBarPolicy()

        # 计算完整高度：表头 + 所有行 + 边距
        header_h = table.horizontalHeader().height()
        total_row_h = sum(table.rowHeight(i) for i in range(table.rowCount()))
        full_h = header_h + total_row_h + 10
        full_w = table.viewport().width() + 2  # 略宽于可视区

        try:
            # 临时调整表格尺寸以显示全部行
            table.setMinimumHeight(full_h)
            table.setMaximumHeight(full_h)
            table.verticalScrollBar().setVisible(False)
            table.adjustSize()
            QApplication.processEvents()

            # 使用 grab() 截取完整表格
            pixmap = table.grab()

            pixmap.save(file_path, "PNG")
            QMessageBox.information(
                self, "导出成功", f"解析结果已导出为图片：\n{file_path}"
            )
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出图片时出错：{str(e)}")
        finally:
            # 恢复原始状态
            table.setMinimumHeight(orig_min_h)
            table.setMaximumHeight(orig_max_h)
            table.verticalScrollBar().setVisible(
                orig_vscroll_policy != Qt.ScrollBarAlwaysOff
            )
            table.resize(table.width(), orig_h)

    def _load_di_map_data(self):
        """从解析器加载DI组合MAP数据到表格（含自定义标记）"""
        self._di_data = []
        di_map = self.parser.DI_COMBINATION_MAP
        afn_map = self.parser.AFN_MAP
        custom_keys = custom_di_store.custom_key_set()

        for (di3, di2, di1, di0), desc in di_map.items():
            afn_val = di1
            afn_name = afn_map.get(afn_val, f"未知({afn_val:02X})")
            is_custom = (di3, di2, di1, di0) in custom_keys
            self._di_data.append(
                (di3, di2, di1, di0, afn_val, afn_name, desc, is_custom)
            )

        self.di_table.setRowCount(len(self._di_data))
        for row, (di3, di2, di1, di0, afn_val, afn_name, desc, is_custom) in enumerate(
            self._di_data
        ):
            self.di_table.setItem(row, 0, QTableWidgetItem(f"{di3:02X}"))
            self.di_table.setItem(row, 1, QTableWidgetItem(f"{di2:02X}"))
            self.di_table.setItem(row, 2, QTableWidgetItem(f"{di1:02X}"))
            self.di_table.setItem(row, 3, QTableWidgetItem(f"{di0:02X}"))
            self.di_table.setItem(
                row, 4, QTableWidgetItem(f"{afn_val:02X}H {afn_name}")
            )
            desc_item = QTableWidgetItem(("★ " if is_custom else "") + desc)
            if is_custom:
                desc_item.setForeground(QColor("#1976D2"))
            self.di_table.setItem(row, 5, desc_item)

        self.di_stats_label.setText(
            f"共 {len(self._di_data)} 条记录（其中自定义 {len(custom_keys)} 条）"
        )

    def _filter_di_table(self, text: str):
        """根据搜索文本过滤DI表格"""
        keyword = text.strip().upper()
        match_count = 0

        for row in range(self.di_table.rowCount()):
            if not keyword:
                self.di_table.setRowHidden(row, False)
                match_count += 1
                continue

            # 构建该行的搜索文本：DI拼接 + AFN + 中文含义
            di3 = self.di_table.item(row, 0).text()
            di2 = self.di_table.item(row, 1).text()
            di1 = self.di_table.item(row, 2).text()
            di0 = self.di_table.item(row, 3).text()
            afn_text = self.di_table.item(row, 4).text()
            desc_text = self.di_table.item(row, 5).text()

            di_str = f"{di3}{di2}{di1}{di0}"
            di_spaced = f"{di3} {di2} {di1} {di0}"
            search_text = f"{di_str} {di_spaced} {afn_text} {desc_text}".upper()

            if keyword in search_text:
                self.di_table.setRowHidden(row, False)
                match_count += 1
            else:
                self.di_table.setRowHidden(row, True)

        if keyword:
            self.di_stats_label.setText(
                f"匹配 {match_count} / {self.di_table.rowCount()} 条记录"
            )
        else:
            self.di_stats_label.setText(f"共 {self.di_table.rowCount()} 条记录")

    def _add_custom_di(self):
        """添加自定义DI对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("添加自定义DI")
        dialog.setMinimumWidth(360)
        layout = QVBoxLayout(dialog)

        # DI3
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("DI3:"))
        di3_input = QLineEdit()
        di3_input.setPlaceholderText("如 E8 或 EA")
        di3_input.setMaxLength(2)
        h1.addWidget(di3_input)
        layout.addLayout(h1)

        # DI2 DI1 DI0 同一行
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("DI2:"))
        di2_input = QLineEdit()
        di2_input.setMaxLength(2)
        h2.addWidget(di2_input)
        h2.addWidget(QLabel("DI1:"))
        di1_input = QLineEdit()
        di1_input.setMaxLength(2)
        h2.addWidget(di1_input)
        h2.addWidget(QLabel("DI0:"))
        di0_input = QLineEdit()
        di0_input.setMaxLength(2)
        h2.addWidget(di0_input)
        layout.addLayout(h2)

        # 中文含义
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("含义:"))
        desc_input = QLineEdit()
        desc_input.setPlaceholderText("如：查询XX信息")
        h3.addWidget(desc_input)
        layout.addLayout(h3)

        # 按钮
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("添加")
        cancel_btn = QPushButton("取消")
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        apply_chinese_context_menus(dialog)

        if dialog.exec() != QDialog.Accepted:
            return

        # 校验/去重/落盘/提示统一走 lookup_pages（与简化版查询页同一实现）
        import lookup_pages

        lookup_pages.apply_custom_di_add(
            self,
            di3_input.text(),
            di2_input.text(),
            di1_input.text(),
            di0_input.text(),
            desc_input.text(),
            on_changed=self._load_di_map_data,
        )

    def _del_custom_di(self):
        """删除选中的自定义DI（多选批量；实现见 lookup_pages，与简化版查询页同一份）"""
        import lookup_pages

        lookup_pages.delete_selected_custom_di_interactive(
            self,
            self.di_table,
            self._di_data,
            on_changed=self._load_di_map_data,
        )

    def create_batch_parse_tab(self) -> QWidget:
        """创建批量解析标签页（左右分栏布局：左侧摘要 + 右侧详情）"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)

        # ── 输入区 ──────────────────────────────────────────────
        input_group = QGroupBox("批量输入报文")
        input_layout = QVBoxLayout(input_group)
        input_layout.setSpacing(8)

        # 工具栏两行（核心操作+结果导出 / CLI 预处理+Python 脚本）。
        # 原为「核心操作 / 预处理 / 脚本+导出」三行，纵向白占一行；合并成两行后两行都用
        # FlowLayout —— 宽度够时排一行，窄窗 / 高DPI 空间不足时自动折行，既省高度又不会
        # 重演「单行流式布局把按钮挤到重叠」的老问题（每行内不再靠 QHBoxLayout 硬挤）。
        toolbar_box = QVBoxLayout()
        toolbar_box.setSpacing(4)

        # ── 第一行：核心操作 ─────────────────────────────────
        row0 = FlowLayout(spacing=6, stretch=True)
        self.load_file_btn = self._make_toolbar_btn("从文件加载", min_width=100)
        self.load_file_btn.setToolTip("从文本文件加载报文（支持每行一帧）")
        set_btn_icon(self.load_file_btn, "open_file")
        self.load_file_btn.clicked.connect(self.load_from_file)
        row0.addWidget(self.load_file_btn)

        self.load_pcap_btn = self._make_toolbar_btn("导入 pcap", min_width=100)
        self.load_pcap_btn.setToolTip(
            "离线导入 pcap：TCP 负载 → 批量输入框并自动解析\n"
            "经典 .pcap 零依赖；pcapng 需 scapy。\n"
            "PLC2 模式切 ED..EE 监控帧，可再按类型全选 / 时序图"
        )
        set_btn_icon(self.load_pcap_btn, "open_file")
        self.load_pcap_btn.clicked.connect(self.load_from_pcap)
        row0.addWidget(self.load_pcap_btn)

        self.paste_btn = self._make_toolbar_btn("从剪贴板粘贴", min_width=100)
        self.paste_btn.setToolTip("从剪贴板粘贴报文文本")
        set_btn_icon(self.paste_btn, "copy")
        self.paste_btn.clicked.connect(self.paste_from_clipboard)
        row0.addWidget(self.paste_btn)

        self.batch_parse_btn = self._make_toolbar_btn("开始批量解析", min_width=100)
        self.batch_parse_btn.setToolTip("逐帧解析输入框中的全部报文")
        set_btn_icon(self.batch_parse_btn, "play")
        self.batch_parse_btn.clicked.connect(self.parse_batch)
        row0.addWidget(self.batch_parse_btn)

        self.clear_batch_btn = self._make_toolbar_btn("清空", min_width=100)
        self.clear_batch_btn.setToolTip("清空输入框与解析结果")
        set_btn_icon(self.clear_batch_btn, "clear")
        self.clear_batch_btn.clicked.connect(self.clear_batch)
        row0.addWidget(self.clear_batch_btn)

        # ── 结果导出（原在「脚本」行右端）──────────────────────
        # 合并「预处理 / 脚本」两行后，导出按钮挪到核心操作行右端：仍在工具栏右上角，
        # 但下方合并行少了 ~470px —— 这正是它在 1366×768 下单行排得下的关键。
        # addStretch() 是 FlowLayout 的弹性空隙（等价 QHBoxLayout.addStretch），
        # 把导出与帧计数顶到行右端；窄屏折行时它们整组落到第二行，不会被压扁。
        row0.addStretch()
        row0.addWidget(self._make_toolbar_separator())

        self.batch_export_excel_btn = self._make_toolbar_btn(
            "导出 Excel", min_width=120
        )
        self.batch_export_excel_btn.setToolTip("解析结果导出为 Excel 文件")
        set_btn_icon(self.batch_export_excel_btn, "export")
        self.batch_export_excel_btn.clicked.connect(lambda: self.export_batch("excel"))
        row0.addWidget(self.batch_export_excel_btn)

        self.batch_export_json_btn = self._make_toolbar_btn("导出 JSON", min_width=120)
        self.batch_export_json_btn.setToolTip("解析结果导出为 JSON 文件")
        set_btn_icon(self.batch_export_json_btn, "export")
        self.batch_export_json_btn.clicked.connect(lambda: self.export_batch("json"))
        row0.addWidget(self.batch_export_json_btn)

        self.batch_export_selected_btn = self._make_toolbar_btn(
            "导出选中", min_width=100
        )
        self.batch_export_selected_btn.setToolTip(
            "只导出摘要表中高亮选中的帧（Ctrl/Shift 多选）；未选中任何行时导出全部"
        )
        set_btn_icon(self.batch_export_selected_btn, "export")
        self.batch_export_selected_btn.clicked.connect(
            lambda: self.export_batch("selected_dialog")
        )
        row0.addWidget(self.batch_export_selected_btn)

        # 「时序图」：协议9批量结果生成通信时序图（CCO⇄STA 消息交互图）；
        # 有勾选行时仅用勾选帧（对齐「导出选中」惯例），否则全部帧；仅协议9可用
        self.batch_seq_diagram_btn = self._make_toolbar_btn("时序图", min_width=100)
        self.batch_seq_diagram_btn.setToolTip(
            "将解析结果生成通信时序图（CCO⇄STA 消息交互）；\n"
            "摘要表有勾选行时仅用勾选帧，否则用全部帧"
        )
        self.batch_seq_diagram_btn.setIcon(app_icons.load_icon("waypoints"))
        self.batch_seq_diagram_btn.clicked.connect(self._generate_sequence_diagram)
        self.batch_seq_diagram_btn.setEnabled(self.current_protocol in (9, 10, 11))
        row0.addWidget(self.batch_seq_diagram_btn)

        # 帧计数徽章右对齐（弹性空隙把它顶到行右端；窄屏折行也不会被挤没）
        self.batch_frame_count_label = QLabel("共 0 帧")
        self.batch_frame_count_label.setStyleSheet(self._batch_count_style())
        row0.addWidget(self.batch_frame_count_label)
        toolbar_box.addLayout(row0)

        # ── 第二行（FlowLayout）：CLI 预处理 + Python 脚本 ───────────────
        # 「预处理」与「脚本」原是上下两行，合并成一行才真省纵向空间。用 FlowLayout
        # 而不是 QHBoxLayout 是关键：宽度够时排一行，窄窗 / 高DPI 下自动折行 —— 正好
        # 退回原来两行的样子，不会重演早期「单行流式布局把按钮挤到重叠」的老问题。
        # stretch=True：宽屏下把行内剩余宽度按权重分给两个下拉框（吃满整行），不靠左
        # 堆成一小撮；窄屏它们缩到最小宽，再窄就整行折行。分组间用竖线分隔。
        row1 = FlowLayout(spacing=6, stretch=True)
        pp_label = QLabel("预处理:")
        pp_label.setFont(self._ui_font(-1))
        row1.addWidget(pp_label)

        self._pp_cmd_combo = QComboBox()
        self._pp_cmd_combo.setEditable(True)
        self._pp_cmd_combo.setFont(self._ui_font(-1, family="Consolas"))
        self._pp_cmd_combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        # 占位符必须短：可编辑 QComboBox 的 sizeHint 把占位符算进宽度，原先那条长示例
        # 实测把下拉框撑到 481px（比最长的一条命令还宽）→ 合并行在 1366 下必折行，
        # 等于白合并。换成短示例后 371→250px，完整语法仍由 tooltip 与「帮助」承担。
        self._pp_cmd_combo.setPlaceholderText('如: hex_extract dedup')
        self._pp_cmd_combo.setToolTip(
            "通用文本预处理命令链（支持正则）\n"
            "可用命令: find <pat> | excluding <pat> | replace <pat> <repl>\n"
            "          head <n> | tail <n> | skip <n> | hex_extract | dedup\n"
            "          tcp_extract | merge_payloads\n"
            "分隔用半角空格，含空格的参数用半角双引号（全角空格/引号会自动归一化）\n"
            "点「保存」按钮保存当前命令到列表，点「删除」按钮删除选中命令"
        )
        # 加载预设命令
        self._pp_preset_commands = [
            'find "tcp data:" tcp_extract',
            'find "fc_payload_data" merge_payloads',
            'find "tcp data:"',
            'find "fc_payload_data"',
            'find "60F0" excluding "mrd:" dedup',
            'find "nwk:" replace ".*nwk:" "NWK:" head 20',
            "hex_extract dedup",
            'excluding "len:" head 50',
        ]
        self._load_pp_commands()
        # 下限保证窄窗下命令框仍可用；权重 2 让宽屏分到的剩余宽度更多（脚本名短，
        # 权重 1 够用）。放不下时整行折行，而不是把控件压到重叠。
        self._pp_cmd_combo.setMinimumWidth(220)
        row1.addWidget(self._pp_cmd_combo, 2)

        self._pp_save_btn = self._make_toolbar_btn("保存", min_width=80)
        self._pp_save_btn.setToolTip("保存当前输入的命令到常用列表")
        set_btn_icon(self._pp_save_btn, "save")
        self._pp_save_btn.clicked.connect(self._save_pp_command)
        row1.addWidget(self._pp_save_btn)

        self._pp_del_btn = self._make_toolbar_btn("删除", min_width=80)
        self._pp_del_btn.setToolTip("删除下拉列表中选中的命令")
        set_btn_icon(self._pp_del_btn, "delete")
        self._pp_del_btn.clicked.connect(self._delete_pp_command)
        row1.addWidget(self._pp_del_btn)

        self._pp_run_btn = self._make_toolbar_btn("执行", min_width=80)
        self._pp_run_btn.setToolTip("对输入框内容执行预处理命令链，结果回填到输入框")
        set_btn_icon(self._pp_run_btn, "play")
        self._pp_run_btn.clicked.connect(self._run_cli_preprocessor)
        row1.addWidget(self._pp_run_btn)

        self._pp_help_btn = self._make_toolbar_btn("帮助", min_width=80)
        self._pp_help_btn.setToolTip("显示预处理命令帮助")
        set_btn_icon(self._pp_help_btn, "help")
        self._pp_help_btn.clicked.connect(self._show_pp_help)
        row1.addWidget(self._pp_help_btn)
        row1.addWidget(self._make_toolbar_separator())

        # ── 同行：Python 脚本预处理 ───────────────────────────
        py_label = QLabel("脚本:")
        py_label.setFont(self._ui_font(-1))
        row1.addWidget(py_label)

        self._py_script_combo = QComboBox()
        self._py_script_combo.setFont(self._ui_font(-1, family="Consolas"))
        self._py_script_combo.setSizeAdjustPolicy(
            QComboBox.AdjustToMinimumContentsLengthWithIcon
        )
        self._py_script_combo.setToolTip(
            "Python 脚本预处理\n"
            "加载自定义 .py 脚本，对输入文本进行清洗/转换\n"
            "脚本需定义 process(text, context) -> str\n"
            "⚠ 直接运行本地脚本，仅加载可信脚本"
        )
        self._load_py_scripts()
        # 同上：下限保证脚本名可见，权重 1 吃少量剩余宽度
        self._py_script_combo.setMinimumWidth(150)
        row1.addWidget(self._py_script_combo, 1)

        self._py_load_btn = self._make_toolbar_btn("加载", min_width=80)
        self._py_load_btn.setToolTip("加载 .py 脚本文件到列表")
        set_btn_icon(self._py_load_btn, "open_file")
        self._py_load_btn.clicked.connect(self._load_py_script_file)
        row1.addWidget(self._py_load_btn)

        self._py_run_btn = self._make_toolbar_btn("运行", min_width=80)
        self._py_run_btn.setToolTip("对输入框内容运行当前脚本，结果回填")
        set_btn_icon(self._py_run_btn, "play")
        self._py_run_btn.clicked.connect(self._run_py_script)
        row1.addWidget(self._py_run_btn)

        self._py_del_btn = self._make_toolbar_btn("移除", min_width=80)
        self._py_del_btn.setToolTip("从列表中移除当前脚本（不删除磁盘文件）")
        set_btn_icon(self._py_del_btn, "delete")
        self._py_del_btn.clicked.connect(self._delete_py_script)
        row1.addWidget(self._py_del_btn)

        self._py_help_btn = self._make_toolbar_btn("帮助", min_width=80)
        self._py_help_btn.setToolTip("显示 Python 脚本预处理帮助")
        set_btn_icon(self._py_help_btn, "help")
        self._py_help_btn.clicked.connect(self._show_py_script_help)
        row1.addWidget(self._py_help_btn)

        toolbar_box.addLayout(row1)

        input_layout.addLayout(toolbar_box)

        # 输入文本框
        self.batch_input = DragDropTextEdit()
        # 禁止自动折行：一行即一帧，超长部分用水平滚动条查看，避免视觉换行干扰按行预处理
        self.batch_input.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.batch_input.setPlaceholderText(
            "粘贴或输入报文数据，支持多种协议：\n"
            "南网/国网协议：68开头，16结束\n"
            "HDLC协议：7E开头，7E结束\n"
            "其他协议：每行一帧直接解析"
        )
        self.batch_input.setMaximumHeight(140)
        input_layout.addWidget(self.batch_input)

        # 帧计数防抖定时器
        self._frame_count_timer = QTimer(self)
        self._frame_count_timer.setSingleShot(True)
        self._frame_count_timer.setInterval(200)
        self._frame_count_timer.timeout.connect(self._do_count_frames)
        self.batch_input.textChanged.connect(self._frame_count_timer.start)

        layout.addWidget(input_group)

        # ── LLM 预处理面板（可折叠） ──────────────────────────────
        self.llm_toggle_btn = QPushButton("▶ LLM 智能预处理")
        self.llm_toggle_btn.setCheckable(True)
        self.llm_toggle_btn.setStyleSheet(
            "QPushButton { text-align: left; padding: 4px 8px; font-weight: bold; }"
            "QPushButton:checked { background-color: #e8f4fd; }"
        )
        self.llm_toggle_btn.clicked.connect(self._toggle_llm_panel)
        layout.addWidget(self.llm_toggle_btn)

        self.llm_preprocess_widget = LLMPreprocessWidget()
        self.llm_preprocess_widget.hide()  # 默认折叠
        layout.addWidget(self.llm_preprocess_widget)

        # ── 结果区分栏（左侧摘要 + 右侧详情） ───────────────────
        self.result_splitter = QSplitter(Qt.Horizontal)

        # 左侧：摘要列表
        summary_group = QGroupBox("解析结果摘要")
        summary_layout = QVBoxLayout(summary_group)
        summary_layout.setContentsMargins(8, 10, 8, 8)
        summary_layout.setSpacing(6)

        # 搜索过滤栏
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(6)

        search_label = QLabel("搜索：")
        search_label.setFont(self._ui_font(-1))
        filter_bar.addWidget(search_label)

        self.batch_search_edit = QLineEdit()
        self.batch_search_edit.setPlaceholderText("输入关键词过滤（摘要/类型/TEI…）")
        self.batch_search_edit.setFont(self._ui_font(-1))
        self.batch_search_edit.setClearButtonEnabled(True)
        # 关键词去抖：250 ms 内连续输入只跑一次过滤（状态下拉仍即时生效）
        self.batch_search_edit.textChanged.connect(self._on_batch_search_text_changed)
        filter_bar.addWidget(self.batch_search_edit, 1)

        status_label = QLabel("状态：")
        status_label.setFont(self._ui_font(-1))
        filter_bar.addWidget(status_label)

        self.batch_status_filter = QComboBox()
        self.batch_status_filter.addItem("全部", "all")
        self.batch_status_filter.addItem("成功", "success")
        self.batch_status_filter.addItem("失败", "fail")
        self.batch_status_filter.addItem("异常", "error")
        self.batch_status_filter.setFont(self._ui_font(-1))
        self.batch_status_filter.currentIndexChanged.connect(
            self._on_batch_filter_changed
        )
        filter_bar.addWidget(self.batch_status_filter)

        # 按类型一键勾选（解析完成后动态填充类型列表，用于快速挑出信标帧等）
        self.batch_type_combo = QComboBox()
        self.batch_type_combo.setFont(self._ui_font(-1))
        self.batch_type_combo.setMinimumWidth(120)
        self.batch_type_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.batch_type_combo.setToolTip(
            "选择帧类型后点「全选」，自动勾选该类型的全部帧"
        )
        self.batch_type_combo.addItem("按类型全选…", None)
        filter_bar.addWidget(self.batch_type_combo)

        self.batch_select_type_btn = self._make_toolbar_btn(
            "全选", min_width=60, height=24
        )
        self.batch_select_type_btn.setToolTip(
            "勾选当前所选类型的全部帧；未选类型时清空全部勾选"
        )
        self.batch_select_type_btn.clicked.connect(self._on_batch_select_by_type)
        filter_bar.addWidget(self.batch_select_type_btn)

        self.batch_selected_count = QLabel("")
        self.batch_selected_count.setFont(self._ui_font(-1))
        self.batch_selected_count.setStyleSheet("color: #2196F3; font-weight: bold;")
        filter_bar.addWidget(self.batch_selected_count)

        # 过滤结果计数（显示 N / 总）；_on_batch_filter_changed 依赖此控件
        self.batch_filter_count = QLabel("")
        self.batch_filter_count.setFont(self._ui_font(-1))
        self.batch_filter_count.setStyleSheet("color: #757575;")
        filter_bar.addWidget(self.batch_filter_count)

        summary_layout.addLayout(filter_bar)

        self.batch_summary_table = ZoomableTableWidget()
        self.batch_summary_table.setColumnCount(5)
        self.batch_summary_table.setHorizontalHeaderLabels(
            ["#", "状态", "长度", "协议/类型", "摘要"]
        )
        header = self.batch_summary_table.horizontalHeader()
        # 列宽设置
        self.batch_summary_table.setColumnWidth(0, 40)
        self.batch_summary_table.setColumnWidth(1, 50)
        self.batch_summary_table.setColumnWidth(2, 60)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self.batch_summary_table.setSelectionBehavior(QTableWidget.SelectRows)
        # 扩展多选：Ctrl/Shift 选多行，配合「导出选中」挑选信标帧等子集
        self.batch_summary_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.batch_summary_table.setEditTriggers(QTableWidget.NoEditTriggers)
        # 选区变化联动「已选 N 帧」计数
        self.batch_summary_table.itemSelectionChanged.connect(
            self._update_batch_selected_count
        )
        # 选区变化联动通信时序图高亮（摘要表 → 图 方向）
        self.batch_summary_table.itemSelectionChanged.connect(
            self._on_batch_selection_highlight_seq
        )
        self.batch_summary_table.setAlternatingRowColors(True)
        self.batch_summary_table.verticalHeader().hide()
        table_font = self._ui_font(-2)
        self.batch_summary_table.setFont(table_font)
        self.batch_summary_table.verticalHeader().setDefaultSectionSize(22)
        # 右键菜单：定位原始报文 + 复制（专用菜单，含通用复制项）
        self._setup_batch_summary_menu()
        # 选中行/项变化时更新详情
        self.batch_summary_table.cellClicked.connect(self._on_batch_row_selected)
        self.batch_summary_table.itemSelectionChanged.connect(
            self._on_batch_row_selected
        )
        summary_layout.addWidget(self.batch_summary_table)

        # 全屏：弹窗展示摘要表（关闭即恢复）
        summary_layout.addLayout(
            self._make_table_fullscreen_btn(
                "解析结果摘要 - 全屏", self.batch_summary_table
            )
        )

        self.result_splitter.addWidget(summary_group)

        # 右侧：详情面板
        detail_group = QGroupBox("选中帧详细解析")
        detail_layout = QVBoxLayout(detail_group)
        detail_layout.setContentsMargins(8, 10, 8, 8)
        detail_layout.setSpacing(6)

        # 原始报文行
        hex_row = QHBoxLayout()
        hex_row.setSpacing(6)
        hex_label = self._make_stats_label("原始报文：", 12)
        hex_row.addWidget(hex_label)

        self.batch_detail_hex = QTextEdit()
        self.batch_detail_hex.setReadOnly(True)
        self.batch_detail_hex.setMaximumHeight(60)
        self.batch_detail_hex.setFont(self._ui_font(-1, family="Consolas"))
        self.batch_detail_hex.setPlaceholderText("选择左侧列表中的帧以查看详情…")
        hex_row.addWidget(self.batch_detail_hex, 1)

        self.batch_copy_hex_btn = QPushButton("复制")
        self.batch_copy_hex_btn.setMaximumWidth(60)
        self.batch_copy_hex_btn.clicked.connect(self._copy_batch_detail_hex)
        hex_row.addWidget(self.batch_copy_hex_btn)

        detail_layout.addLayout(hex_row)

        # 详情表格
        self.batch_detail_table = ZoomableTableWidget()
        self.batch_detail_table.setColumnCount(4)
        self.batch_detail_table.setHorizontalHeaderLabels(
            ["字段", "原始值", "解析值", "说明"]
        )
        detail_header = self.batch_detail_table.horizontalHeader()
        detail_header.setStretchLastSection(True)
        detail_header.setSectionResizeMode(QHeaderView.Interactive)
        self.batch_detail_table.setColumnWidth(0, 180)
        self.batch_detail_table.setColumnWidth(1, 120)
        self.batch_detail_table.setColumnWidth(2, 200)
        self.batch_detail_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.batch_detail_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.batch_detail_table.setAlternatingRowColors(True)
        self.batch_detail_table.verticalHeader().hide()
        detail_font = self._ui_font(-2)
        self.batch_detail_table.setFont(detail_font)
        self.batch_detail_table.verticalHeader().setDefaultSectionSize(20)
        # 右键复制菜单 + Ctrl+C
        self._setup_table_copy_menu(self.batch_detail_table)
        detail_layout.addWidget(self.batch_detail_table)

        # 全屏：弹窗展示详情表（关闭即恢复）
        detail_layout.addLayout(
            self._make_table_fullscreen_btn(
                "选中帧详细解析 - 全屏", self.batch_detail_table
            )
        )

        self.result_splitter.addWidget(detail_group)

        # 初始分割比例（约 45:55）
        self.result_splitter.setSizes([450, 550])

        layout.addWidget(self.result_splitter, 1)

        # ── 底部状态栏（状态文字 + 后台解析进度 / 取消）────────────
        # 进度条与「取消」原先挤在第一行行内：合并预处理/脚本后第一行右端要让给导出
        # 按钮，而这两个只在解析中出现（临时控件），放状态栏既不挤按钮也不额外占行。
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        self.batch_status_bar = QLabel("就绪")
        self.batch_status_bar.setStyleSheet(self._batch_status_style())
        status_row.addWidget(self.batch_status_bar, 1)

        # 后台批量解析进度 + 取消（仅解析中可见；任务 09-15-gui-batch-parse-perf）
        self.batch_progress_bar = QProgressBar()
        self.batch_progress_bar.setMinimumHeight(18)
        self.batch_progress_bar.setMinimumWidth(160)
        self.batch_progress_bar.setTextVisible(True)
        self.batch_progress_bar.setRange(0, 1)
        self.batch_progress_bar.setValue(0)
        self.batch_progress_bar.setToolTip("批量解析进度（后台执行，可取消）")
        self.batch_progress_bar.setVisible(False)
        status_row.addWidget(self.batch_progress_bar)

        self.batch_cancel_btn = self._make_toolbar_btn("取消", min_width=70)
        self.batch_cancel_btn.setToolTip(
            "停止批量解析（已解析完的结果保留，仍可看详情与导出）"
        )
        set_btn_icon(self.batch_cancel_btn, "stop")
        self.batch_cancel_btn.clicked.connect(self._cancel_batch_parse)
        self.batch_cancel_btn.setEnabled(False)
        self.batch_cancel_btn.setVisible(False)
        status_row.addWidget(self.batch_cancel_btn)
        layout.addLayout(status_row)

        # 兼容：保留 stats_label 引用（初始化为空，不显示到布局中）
        self.stats_label = QLabel("状态：待解析")
        self.stats_label.setVisible(False)

        return tab

    # ==================== 预设按钮功能 ====================

    def _on_preset_button_clicked(self, protocol: str, frame_hex: str, config: dict):
        """预设按钮点击：通过串口直接发送报文"""
        # 先切到对应协议（保持界面一致性）
        if protocol == "south" and self.current_protocol != 0:
            self.protocol_combo.setCurrentIndex(0)
        elif protocol == "gdw" and self.current_protocol != 7:
            self.protocol_combo.setCurrentIndex(7)
        elif protocol == "dlt698" and self.current_protocol != 8:
            self.protocol_combo.setCurrentIndex(8)
        elif protocol == "dlt645" and self.current_protocol != 6:
            self.protocol_combo.setCurrentIndex(6)
        elif protocol == "yw645" and self.current_protocol != 13:
            self.protocol_combo.setCurrentIndex(13)

        # 检查串口是否打开
        if not self.serial_worker or not self.serial_worker.is_open():
            QMessageBox.warning(self, "串口未打开", "请先打开串口后再发送预设命令。")
            return

        # 把报文同步到组帧页面（方便查看）
        frame_gen_tab = self._ensure_frame_gen_tab()
        frame_gen_tab.result_hex.setText(frame_hex)

        # 直接通过串口发送
        self.serial_worker.send_hex_string(frame_hex)

        # 在串口日志显示
        frame_gen_tab._on_serial_log(f"[预设发送] {frame_hex}")

    # ==================== 单帧解析功能 ====================

    def _debug_log(self, msg: str):
        """输出调试日志到终端（黑窗口），GUI 模式下从终端启动可见"""
        print(f"[DEBUG] {msg}", flush=True)

    def _refresh_cpu_mem(self):
        """状态栏慢刷新（4s）：本进程 CPU 占用 / 内存占用。

        CPU 为整机口径（与任务管理器一致），首次采样无基线显示 --；
        内存显示当前工作集，峰值放 tooltip。取不到的平台显示 --。
        采样是一次系统调用，微秒级开销，不占 GUI 线程时间。
        """
        try:
            s = self._proc_stats.sample()
        except Exception:
            self._cpu_mem_lbl.setText("CPU: --  内存: --")
            self.statusBar().update()
            return
        cpu_txt = "--" if s.cpu_pct is None else f"{s.cpu_pct:.1f}%"
        mem_txt = "--" if s.mem_mb is None else f"{s.mem_mb:.0f} MB"
        self._cpu_mem_lbl.setText(f"CPU: {cpu_txt}  内存: {mem_txt}")
        # CPU 着色：<30% 常规灰，30~60% 橙色提醒，>60% 红色警示
        color = "#607D8B"
        if s.cpu_pct is not None:
            if s.cpu_pct >= 60:
                color = "#E53935"
            elif s.cpu_pct >= 30:
                color = "#FB8C00"
        peak_txt = "--" if s.mem_peak_mb is None else f"{s.mem_peak_mb:.0f} MB"
        self._cpu_mem_lbl.setStyleSheet(f"color: {color}; padding: 0 8px;")
        self._cpu_mem_lbl.setToolTip(
            f"本软件资源占用（每 4 秒刷新）\n"
            f"CPU 占用：{cpu_txt}（整机口径，与任务管理器一致）\n"
            f"内存占用：{mem_txt}（当前工作集）\n"
            f"内存峰值：{peak_txt}"
        )
        # 文本长度变化触发状态栏布局重排，Windows 合成层下旧矩形可能残留（重影）
        self.statusBar().update()

    def _build_thread_detail_menu(self) -> tuple:
        """构建线程明细 QMenu（纯构建，不弹模态，便于测试）。

        返回 (menu, py_threads, qt_threads, copy_action)。
        """
        py_threads, qt_threads = thread_registry.snapshot()
        total = len(py_threads) + len(qt_threads)
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        menu.setWindowTitle(f"当前线程明细（共 {total} 个）")

        act = menu.addAction(f"当前线程明细（共 {total} 个，实时快照）")
        act.setEnabled(False)
        menu.addSeparator()

        sec_py = menu.addAction(f"Python 线程（{len(py_threads)}）")
        sec_py.setEnabled(False)
        for t in py_threads:
            name = getattr(t, "name", "?") or "?"
            tid = getattr(t, "ident", None)
            daemon = "守护" if getattr(t, "daemon", False) else "前台"
            alive = "运行中" if getattr(t, "is_alive", lambda: False)() else "已结束"
            label = (
                f"  • {name}  [{tid}, {daemon}, {alive}]"
                if tid
                else f"  • {name}  [{daemon}, {alive}]"
            )
            a = menu.addAction(label)
            a.setEnabled(False)

        menu.addSeparator()
        sec_qt = menu.addAction(f"QThread 工作线程（{len(qt_threads)}）")
        sec_qt.setEnabled(False)
        if qt_threads:
            for qt in qt_threads:
                try:
                    name = qt.objectName() or qt.__class__.__name__
                    running = "运行中" if qt.isRunning() else "已停止"
                except RuntimeError:
                    name = qt.__class__.__name__
                    running = "已回收"
                a = menu.addAction(f"  • {name}  [{running}]")
                a.setEnabled(False)
        else:
            a = menu.addAction("  （无）")
            a.setEnabled(False)

        menu.addSeparator()
        copy_act = menu.addAction("📋 复制线程列表")
        return menu, py_threads, qt_threads, copy_act

    def _copy_thread_list(self, py_threads, qt_threads):
        """把线程明细复制到剪贴板。"""
        lines = [f"Python 线程（{len(py_threads)}）："]
        for t in py_threads:
            lines.append(
                f"  • {getattr(t, 'name', '?')} (ident={getattr(t, 'ident', '?')}, "
                f"daemon={getattr(t, 'daemon', '?')})"
            )
        lines.append(f"QThread 工作线程（{len(qt_threads)}）：")
        for qt in qt_threads:
            try:
                lines.append(
                    f"  • {qt.objectName() or qt.__class__.__name__} "
                    f"(running={qt.isRunning()})"
                )
            except RuntimeError:
                lines.append(f"  • {qt.__class__.__name__} (deleted)")
        QApplication.clipboard().setText("\n".join(lines))

    def _on_thread_count_clicked(self, event):
        """点击状态栏「线程」标签：弹出当前线程明细 QMenu（轻量，点外部即关）。"""
        menu, py_threads, qt_threads, copy_act = self._build_thread_detail_menu()
        chosen = menu.exec(
            self._thread_count_lbl.mapToGlobal(
                self._thread_count_lbl.rect().bottomLeft()
            )
        )
        if chosen is copy_act:
            self._copy_thread_list(py_threads, qt_threads)

    def _refresh_thread_count(self):
        """状态栏刷新：统计当前存活线程数；明细改为点击标签弹出（见 _on_thread_count_clicked）。"""
        py_threads, qt_threads = thread_registry.snapshot()
        total = len(py_threads) + len(qt_threads)
        self._thread_count_lbl.setText(f"线程: {total}")
        self._thread_count_lbl.setToolTip(
            f"当前应用存活线程 {total} 个（Python {len(py_threads)} + QThread {len(qt_threads)}）\n"
            f"点击查看明细列表"
        )
        self.statusBar().update()

    def _on_tab_changed_repaint(self, index: int):
        """切 tab 时请求重绘当前页，消除毛玻璃半透明背景下的残留重影。

        用异步 update() + 防抖，而不是同步 repaint()：快速连续切 tab 时
        repaint() 会立即强制重绘整页（含大表格）导致卡顿不响应；update() 由
        Qt 合并多次请求，只在事件循环空闲时重绘一次。
        """
        effective_theme = ThemeManager.resolve_appearance(
            self._theme_id,
            getattr(self, "_appearance_mode", "light"),
            getattr(self, "_system_dark", False),
        )[0]
        if effective_theme != "glass":
            return
        self._pending_repaint_tab = index
        if not hasattr(self, "_tab_repaint_timer"):
            from PySide6.QtCore import QTimer

            self._tab_repaint_timer = QTimer(self)
            self._tab_repaint_timer.setSingleShot(True)
            self._tab_repaint_timer.setInterval(50)
            self._tab_repaint_timer.timeout.connect(self._do_tab_repaint)
        self._tab_repaint_timer.start()

    def _ensure_lazy_tab(self, index: int):
        """首次打开重标签页时再创建，避免启动时加载全部解析器和 schema。"""
        if getattr(self, "_lazy_tab_guard", False):
            return
        if index == getattr(self, "_frame_gen_tab_index", -1):
            self._ensure_frame_gen_tab()
        elif index == getattr(self, "_archive_tab_index", -1):
            self._ensure_archive_tab()
        elif index == getattr(self, "_topology_tab_index", -1):
            self._ensure_topology_tab()
        elif index == getattr(self, "_tcp_monitor_tab_index", -1):
            self._ensure_tcp_monitor_tab()
        elif index == getattr(self, "_serial_tool_tab_index", -1):
            self._ensure_serial_tool_tab()
        elif index == getattr(self, "_testbench_tab_index", -1):
            self._ensure_testbench_tab()
        elif index == getattr(self, "_bluetooth_tool_tab_index", -1):
            self._ensure_bluetooth_tool_tab()
        elif index == getattr(self, "_seq_diagram_tab_index", -1):
            self._ensure_seq_diagram_tab()
        elif index == getattr(self, "_upgrade_tab_index", -1):
            self._ensure_upgrade_tab()
        elif index == getattr(self, "_test_tab_index", -1):
            self._ensure_test_tab()

    def _ensure_frame_gen_tab(self):
        if hasattr(self, "frame_gen_tab"):
            return self.frame_gen_tab
        from frame_gen_widget import FrameGenWidget

        tab = FrameGenWidget()
        self.frame_gen_tab = tab
        tab.set_serial_worker(self.serial_worker)
        mode = getattr(self, "_pending_frame_gen_mode", "south")
        tab.set_protocol_mode(mode)
        tab.preset_added.connect(self.preset_tab.refresh)
        tab.test_plan_added.connect(self.test_plan_tab.add_item)
        self._replace_lazy_tab(
            self._frame_gen_placeholder, self._frame_gen_tab_index, tab
        )
        apply_chinese_context_menus(tab)
        return tab

    def _ensure_archive_tab(self):
        if hasattr(self, "archive_tab"):
            return self.archive_tab
        from archive_widget import ArchiveWidget

        tab = ArchiveWidget()
        self.archive_tab = tab
        tab.set_serial_worker(self.serial_worker)
        mode = getattr(self, "_pending_archive_mode", "south")
        tab.set_protocol_mode(mode)
        self._replace_lazy_tab(self._archive_placeholder, self._archive_tab_index, tab)
        apply_chinese_context_menus(tab)
        return tab

    def _ensure_topology_tab(self):
        if hasattr(self, "topology_tab"):
            return self.topology_tab
        from topology_widget import TopologyWidget

        tab = TopologyWidget()
        self.topology_tab = tab
        tab.set_serial_worker(self.serial_worker)
        mode = getattr(self, "_pending_topology_mode", "south")
        tab.set_protocol_mode(mode)
        self._replace_lazy_tab(
            self._topology_placeholder, self._topology_tab_index, tab
        )
        apply_chinese_context_menus(tab)
        return tab

    def _ensure_tcp_monitor_tab(self):
        if hasattr(self, "tcp_monitor_tab"):
            return self.tcp_monitor_tab
        from monitor.tcp_monitor import TCPMonitorWidget

        tab = TCPMonitorWidget()
        self.tcp_monitor_tab = tab
        tab.set_parsers(
            self.gw_new_gen_parser,
            self.csg_new_gen_parser,
            gw_summary_fn=self._get_gw_new_gen_summary,
            csg_summary_fn=self._get_csg_new_gen_summary,
            hdc10_parser=self.hdc10_parser,
            hdc10_summary_fn=self._get_gw_new_gen_summary,
        )
        self._replace_lazy_tab(
            self._tcp_monitor_placeholder, self._tcp_monitor_tab_index, tab
        )
        apply_chinese_context_menus(tab)
        return tab

    def _ensure_serial_tool_tab(self):
        """懒加载创建串口工具页（集成自 USB 负载测试工具，与协议无关、始终可见）。"""
        if hasattr(self, "serial_tool_tab"):
            return self.serial_tool_tab
        from serial_tool_widget import SerialToolWidget

        tab = SerialToolWidget()
        self.serial_tool_tab = tab
        # 复用主窗口共享的串口线程（与组帧页/监控器页同一约定）：
        # 端口/波特率只在顶部「串口配置」里设置，本页只订阅信号
        tab.set_serial_worker(self.serial_worker)
        # 解析能力同样走注入（本页不 import main_gui，避免循环依赖）：
        # 按命令协议解析 RX 帧并在日志输出文字
        tab.set_parse_provider(self._serial_parse_provider)
        self._replace_lazy_tab(
            self._serial_tool_placeholder, self._serial_tool_tab_index, tab
        )
        apply_chinese_context_menus(tab)
        return tab

    def _ensure_testbench_tab(self):
        """懒加载创建「生产测试架」页（串口助手 + 测试架参数帧，与协议无关、始终可见）。

        接线口径与串口工具页一致：复用主窗口**共享**的 `SerialWorker`（只订阅信号，
        绝不开/关端口 —— 一个 COM 口只能被打开一次）；组帧 / 校验 / 编解码全部在
        `production_testbench_core`（纯逻辑），本页不 import `main_gui`。
        """
        if hasattr(self, "testbench_tab"):
            return self.testbench_tab
        from production_testbench_widget import ProductionTestbenchWidget

        tab = ProductionTestbenchWidget()
        self.testbench_tab = tab
        tab.set_serial_worker(self.serial_worker)
        tab.restyle_for_theme(self._is_dark_theme())
        self._replace_lazy_tab(
            self._testbench_placeholder, self._testbench_tab_index, tab
        )
        apply_chinese_context_menus(tab)
        return tab

    def _serial_parse_provider(self, frame_bytes: bytes, protocol_index: int):
        """串口工具的解析回调：``(摘要, 解析表)``。

        与单帧页/批量共用同一套分派（`_get_current_parser` + `build_gui_parser`），
        保证「串口工具里看到的解析」与「复制到单帧页解析」逐字段一致。
        在 GUI 线程调用（串口接收信号投递到 GUI 线程），与响应匹配同一口径。
        """
        parser = self._get_current_parser(protocol_index)
        table_data = parser.parse_to_table(frame_bytes)
        summary = self._get_summary_from_table_data(table_data, protocol_index)
        return summary, table_data

    def _ensure_bluetooth_tool_tab(self):
        """懒加载创建蓝牙工具页（集成自蓝牙转串口工具，与协议无关、始终可见）。

        接线口径与串口工具页一致：能力全部注入，本页不 import `main_gui`。
        唯一的差别是 **BLE 通信线程由本页自持**（`BluetoothToolWidget` 内部惰性创建）：
        蓝牙设备不存在「COM 口全局独占」的约束，也就不需要像串口那样由主窗口托管单例。
        """
        if hasattr(self, "bluetooth_tool_tab"):
            return self.bluetooth_tool_tab
        from bluetooth_tool_widget import BluetoothToolWidget

        tab = BluetoothToolWidget()
        self.bluetooth_tool_tab = tab
        # 串口：复用主窗口**共享**的 SerialWorker（虚拟模式 BLE ⇄ 串口透传用），
        # 端口/波特率只在顶部「串口配置」设置，本页只订阅信号，不另开 COM 口
        tab.set_serial_worker(self.serial_worker)
        # 解析能力走注入：收到的 BLE 帧按选中协议解析，口径与单帧页/串口工具页一致
        tab.set_parse_provider(self._serial_parse_provider)
        # 协议下拉默认跟随主窗口当前协议（用户在本页手选后落盘，下次沿用）
        tab.set_protocol_provider(self._bluetooth_protocol_provider)
        tab.set_send_to_single_handler(self._send_frame_to_single_parse)
        self._replace_lazy_tab(
            self._bluetooth_tool_placeholder, self._bluetooth_tool_tab_index, tab
        )
        apply_chinese_context_menus(tab)
        return tab

    def _bluetooth_protocol_provider(self):
        """蓝牙页「协议」下拉的跟随值：主窗口当前协议索引。"""
        return int(self.current_protocol)

    def _ensure_seq_diagram_tab(self):
        """懒加载创建通信时序图标签页（协议9批量解析可视化）"""
        if hasattr(self, "seq_diagram_tab"):
            return self.seq_diagram_tab
        from sequence_diagram_widget import SequenceDiagramWidget

        tab = SequenceDiagramWidget()
        self.seq_diagram_tab = tab
        # 点击图上消息 → 跳回批量解析页定位对应帧
        tab.message_clicked.connect(self._on_seq_message_clicked)
        # 图内「刷新」→ 按当前 batch_results（含勾选子集规则）重建
        tab.refresh_requested.connect(self._generate_sequence_diagram)
        self._replace_lazy_tab(
            self._seq_diagram_placeholder, self._seq_diagram_tab_index, tab
        )
        apply_chinese_context_menus(tab)
        return tab

    def _ensure_upgrade_tab(self):
        """懒加载创建 698.45 文件传输升级页（仅协议8 可见；复用共享串口）。"""
        if hasattr(self, "upgrade_tab"):
            return self.upgrade_tab
        from dlt698_upgrade_widget import Dlt698UpgradeWidget

        tab = Dlt698UpgradeWidget()
        self.upgrade_tab = tab
        # 复用主窗口共享的串口线程（与组帧页/串口工具页同一约定）：端口/波特率只在
        # 顶部「串口配置」设置，本页只订阅 raw_data_received、经 write_raw 发送，不自建句柄。
        tab.set_serial_worker(self.serial_worker)
        # 蓝牙通道：复用「蓝牙工具」页那条连接（本页不自己建/断连接）——注入取值回调，
        # 因为蓝牙 worker 是蓝牙页**惰性创建**的，注入时可能还不存在。
        tab.set_bluetooth_provider(self._upgrade_bluetooth_source)
        self._replace_lazy_tab(
            self._upgrade_placeholder, self._upgrade_tab_index, tab
        )
        apply_chinese_context_menus(tab)
        return tab

    def _ensure_test_tab(self):
        """懒加载创建 698.45 协议测试页（仅协议8 可见；复用共享串口）。"""
        if hasattr(self, "test_tab"):
            return self.test_tab
        from dlt698_test_widget import Dlt698TestWidget

        tab = Dlt698TestWidget()
        self.test_tab = tab
        # 与升级页/组帧页同一约定：端口与波特率只在顶部「串口配置」设置，
        # 本页只订阅 raw_data_received、经 write_raw 发送，不自建句柄。
        tab.set_serial_worker(self.serial_worker)
        # 「远程升级」按钮切到光伏升级页（升级流程只实现一份）
        tab.open_upgrade.connect(
            lambda: self._goto_tab(getattr(self, "_upgrade_tab_index", -1)))
        # 双击报文表 → 送「单帧解析」页看完整解析树（与监控器同一注入点）
        tab.frame_to_single_parse.connect(self._send_frame_to_single_parse)
        self._replace_lazy_tab(self._test_placeholder, self._test_tab_index, tab)
        apply_chinese_context_menus(tab)
        return tab

    def _upgrade_bluetooth_source(self):
        """「光伏升级」页取蓝牙通信线程的唯一入口：蓝牙工具页当前的 worker（没有则 None）。

        蓝牙 worker 由蓝牙页**惰性创建**（用户在那页点扫描/连接时才有），所以这里只能按需取；
        升级页不缓存、不创建、不销毁它 —— 连接生命周期完全归蓝牙页。
        """
        tab = getattr(self, "bluetooth_tool_tab", None)
        if tab is None:
            return None
        try:
            return tab.bluetooth_worker()
        except Exception:
            return None

    def _replace_lazy_tab(self, old_widget, index, new_widget):
        title = self.tab_widget.tabText(index)
        icon = self.tab_widget.tabIcon(index)
        self.tab_widget.removeTab(index)
        self.tab_widget.insertTab(index, new_widget, icon, title)
        if self.tab_widget.currentIndex() != index:
            self._lazy_tab_guard = True
            try:
                self.tab_widget.setCurrentIndex(index)
            finally:
                self._lazy_tab_guard = False
        old_widget.deleteLater()

    def _do_tab_repaint(self):
        """防抖后实际执行：异步重绘当前 tab 页（update，非阻塞）。"""
        idx = getattr(self, "_pending_repaint_tab", -1)
        w = self.tab_widget.widget(idx) if idx >= 0 else None
        if w is not None:
            w.update()

    def _reflow_proto_group(self):
        """协议组内控件显隐变化后，触发 FlowLayout 重新计算换行与高度。"""
        group = getattr(self, "proto_group", None)
        if group is None:
            return
        lay = group.layout()
        if lay is not None:
            lay.invalidate()
        group.updateGeometry()
        group.adjustSize()
        # 关键：必须让**外层顶栏**这一层也重排一次。只动内层（invalidate / updateGeometry /
        # adjustSize）时，协议分组框拿不到最终宽度，内层 FlowLayout 也不会被重新调用，子项就
        # 停在旧的换行位置 —— 协议下拉框留在第二行、被顶栏裁成一条缝（实测 visibleRegion
        # 仅 266x5）→ 启动后显示为空白，点一下才刷新。重排外层后分组框立刻拿到最终宽度，
        # 内层随之重排，下拉框回到第一行（实测同步恢复到 (76,20) / 266x26，无需交互）。
        bar = getattr(self, "top_bar_widget", None)
        if bar is not None:
            bar_lay = bar.layout()
            if bar_lay is not None:
                bar_lay.invalidate()
                bar_lay.activate()

    # ==================== 顶部栏显隐（协议+串口一起，菜单栏图标开关） ====================

    # ==================== 外观模式（浅色 / 深色 / 跟随系统） ====================

    def _create_appearance_btn(self) -> QToolButton:
        """菜单栏右上角的「太阳/月亮/显示器」按钮：循环切换外观模式。"""
        btn = QToolButton()
        btn.setObjectName("appearance_btn")
        btn.setAutoRaise(True)
        btn.setFixedSize(28, 28)
        btn.setIconSize(QSize(16, 16))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._cycle_appearance)
        self._sync_appearance_btn(btn)
        return btn

    def _sync_appearance_btn(self, btn=None) -> None:
        """按「实际显示效果 + 模式」刷新图标与提示。"""
        btn = btn if btn is not None else getattr(self, "appearance_btn", None)
        if btn is None:
            return
        dark = self._is_dark_theme()
        mode = getattr(self, "_appearance_mode", "light")
        if dark:
            icon_key = "moon"
        elif mode == "system":
            icon_key = "monitor"
        else:
            icon_key = "sun"
        try:
            btn.setIcon(app_icons.load_icon(icon_key))
        except Exception:  # noqa: BLE001
            pass
        label = ThemeManager.APPEARANCE_LABELS.get(mode, "浅色")
        extra = "（当前主题为 Fusion 暗色）" if (dark and self._theme_id == "dark") else ""
        btn.setToolTip(f"外观：{label}{extra}\n点击切换：浅色 → 深色 → 跟随系统")

    def _cycle_appearance(self) -> None:
        """循环切换外观：浅色 → 深色 → 跟随系统 → 浅色。

        「Fusion 暗色」是显式主题，模式为浅色时点一下应回到浅色（换回默认主题），
        否则会出现「点了没反应」。
        """
        if self._is_dark_theme() and self._theme_id == "dark":
            self._theme_id = "default"
            self._appearance_mode = "light"
        elif getattr(self, "_appearance_mode", "light") == "light":
            self._appearance_mode = "dark"
        elif self._appearance_mode == "dark":
            self._appearance_mode = "system"
        else:
            self._appearance_mode = "light"
        self._apply_appearance()

    def _apply_appearance(self, persist: bool = True) -> None:
        """把当前「主题 + 外观模式」应用到全局，并同步动态控件与按钮图标。"""
        app = QApplication.instance()
        self._system_dark = ThemeManager.detect_system_dark()
        if app is not None:
            try:
                ThemeManager.apply(
                    app, self._theme_id, self._font_family, self._font_size,
                    glass=self._glass_settings,
                    mode=self._appearance_mode,
                )
            except Exception as e:  # noqa: BLE001 - 切主题失败不能带崩主程序
                print(f"[外观] 应用失败: {e}")
        self._restyle_for_theme()
        self._sync_appearance_btn()
        if persist:
            self._save_app_config()

    def _on_system_color_scheme_changed(self, *_args) -> None:
        """系统深浅色变化：仅「跟随系统」模式下实时跟随。"""
        self._system_dark = ThemeManager.detect_system_dark()
        if getattr(self, "_appearance_mode", "light") == "system":
            self._apply_appearance(persist=False)

    def _create_topbar_toggle_btn(self) -> QToolButton:
        """菜单栏右上角的小图标按钮：一键显示/隐藏整条「协议选择+串口配置」栏。"""
        btn = QToolButton()
        btn.setObjectName("topbar_toggle_btn")
        btn.setCheckable(True)
        btn.setChecked(True)  # 默认展开
        btn.setAutoRaise(True)
        btn.setFixedSize(28, 28)
        btn.setIconSize(QSize(16, 16))
        btn.clicked.connect(self._toggle_top_bar)
        self._sync_topbar_toggle_btn(btn)
        return btn

    def _sync_topbar_toggle_btn(self, btn=None):
        """按当前折叠态刷新图标与提示（展开=顶栏可见）。"""
        btn = btn if btn is not None else getattr(self, "topbar_toggle_btn", None)
        if btn is None:
            return
        shown = btn.isChecked()
        # panel-top-open：顶栏展开；panel-top-close：顶栏已收起
        btn.setIcon(
            app_icons.load_icon("panel-top-open" if shown else "panel-top-close")
        )
        btn.setToolTip(
            "隐藏协议选择与串口配置栏（折叠后协议在窗口标题、串口在状态栏）"
            if shown
            else "显示协议选择与串口配置栏"
        )

    def _apply_top_bar_collapse_state(self):
        """按 _saved_topbar_collapsed 套用顶栏显隐（构造末尾调用）。"""
        collapsed = bool(getattr(self, "_saved_topbar_collapsed", False))
        if hasattr(self, "topbar_toggle_btn"):
            self.topbar_toggle_btn.setChecked(not collapsed)
            self._sync_topbar_toggle_btn()
        if hasattr(self, "top_bar_widget"):
            self.top_bar_widget.setVisible(not collapsed)

    def _toggle_top_bar(self):
        """菜单栏图标点击：协议选择 + 串口配置整行一起显示/隐藏。"""
        shown = self.topbar_toggle_btn.isChecked()
        self.top_bar_widget.setVisible(shown)
        self._sync_topbar_toggle_btn()
        self._update_window_title()
        self._update_serial_statusbar()
        if getattr(self, "_ui_ready", False):
            self._save_app_config()

    @staticmethod
    def _title_chrome_reserve() -> int:
        """标题栏图标 + 最小化/最大化/关闭按钮的大致像素占用（Win10/11）。"""
        return 150

    def _update_window_title(self):
        """刷新主窗口标题。

        顶栏展开：`协议解析工具 v{ver} ({date}) - 作者: liruitao`（OS 左对齐）
        顶栏折叠：**版本+作者仍在左侧同一段**，仅协议短名近似居中——
        Windows 原生标题整段左对齐，用空格把短名顶到中部（缩放时 resizeEvent 重算）。
            `协议解析工具 v… (日期) - 作者: liruitao` + 填充空格 + `协议短名`
        """
        left = f"协议解析工具 v{APP_VERSION} ({BUILD_DATE}) - 作者: liruitao"
        collapsed = False
        proto_name = ""
        try:
            collapsed = not self.topbar_toggle_btn.isChecked()
            idx = self.protocol_combo.currentIndex()
            try:
                proto_name = protocol_registry.get_protocol(idx).short_name
            except Exception:
                proto_name = self.protocol_combo.currentText()
        except Exception:
            collapsed = False
        if not (collapsed and proto_name):
            self.setWindowTitle(left)
            return

        # 左段与协议之间至少一个间隔符；协议名再按窗口宽度居中
        sep = "  "
        pad = ""
        try:
            fm = self.fontMetrics()
            # 标题栏系统字体可能比控件字体更宽：两种都量，取偏大值 → pad 偏小更安全
            # （pad 过大会把协议名顶出中线右侧；用户反馈是偏左 → 先保证能顶开）
            try:
                app_fm = QGuiApplication.fontMetrics()
            except Exception:
                app_fm = fm
            left_px = fm.horizontalAdvance(left + sep)
            proto_px = max(
                fm.horizontalAdvance(proto_name),
                app_fm.horizontalAdvance(proto_name),
            )
            # 窗口已显示用 frame 宽（含边框更接近标题栏），否则 width()
            if self.isVisible():
                bar_w = int(self.frameGeometry().width() or self.width())
            else:
                bar_w = int(self.width())
            # Win10/11 标题栏左侧图标 + 右侧窗口按钮约 140~180px
            reserve = self._title_chrome_reserve()
            usable = max(240, bar_w - reserve)
            # 目标：left_px + pad + proto_px/2 ≈ usable/2
            pad_px = usable / 2.0 - proto_px / 2.0 - left_px
            if pad_px < 0 and bar_w > 700:
                # 左段偏长 / 预留偏保守时：放宽预留，至少把协议名往右顶
                usable = max(240, bar_w - 80)
                pad_px = usable / 2.0 - proto_px / 2.0 - left_px
            space_w = max(1, fm.horizontalAdvance(" "))
            n = int(max(0.0, pad_px) / space_w)
            n = min(n, 200)  # 上限防异常窗口宽度；允许 0（左段极长时紧挨其后）
            pad = " " * n
        except Exception:
            pass
        self.setWindowTitle(f"{left}{sep}{pad}{proto_name}")

    def resizeEvent(self, event):
        """窗口尺寸变化时：顶栏折叠态下重算标题中协议名的居中填充。"""
        super().resizeEvent(event)
        try:
            if (
                hasattr(self, "topbar_toggle_btn")
                and not self.topbar_toggle_btn.isChecked()
            ):
                self._update_window_title()
        except Exception:
            pass

    def _update_serial_statusbar(self):
        """顶栏折叠时，在状态栏显示端口/波特率/校验/连接状态；展开时隐藏。"""
        lbl = getattr(self, "_serial_statusbar_lbl", None)
        if lbl is None:
            return
        try:
            collapsed = not self.topbar_toggle_btn.isChecked()
        except Exception:
            collapsed = False
        if not collapsed:
            try:
                lbl.hide()
            except RuntimeError:
                pass
            return
        try:
            port = self.serial_port_combo.currentText() or "未选择"
            baud = self.serial_baud_combo.currentText() or "-"
            parity = self.serial_parity_combo.currentText() or "-"
            status = (
                self.serial_status_label.text()
                if hasattr(self, "serial_status_label")
                else "未连接"
            )
            color = getattr(self, "_serial_status_color", "#607D8B")
            if self._is_dark_theme() and color == "#999":
                color = "#bbb"
            lbl.setText(f"串口: {port} · {baud} · {parity} · {status}")
            lbl.setStyleSheet(f"color: {color}; padding: 0 8px;")
            lbl.show()
        except RuntimeError:
            pass

    def _fit_combo_to_current(self, combo, pad_extra=12, min_w=90):
        """让 QComboBox 宽度贴合当前选中项文字，而非撑到列表中最宽项。

        用当前 style 精确计算（含下拉箭头 + 内边距，自动适配高 DPI），
        再额外加 pad_extra 余量，避免不同字体渲染下尾字被截。
        弹出列表宽度按列表中最长项设置，长项不截断。
        """
        from PySide6.QtCore import QSize
        from PySide6.QtWidgets import QStyleOptionComboBox

        def combo_width_for_text(text):
            opt = QStyleOptionComboBox()
            combo.initStyleOption(opt)
            opt.currentText = text
            text_w = combo.fontMetrics().horizontalAdvance(text)
            content = QSize(text_w + pad_extra, 0)
            return (
                combo.style()
                .sizeFromContents(QStyle.ContentsType.CT_ComboBox, opt, content, combo)
                .width()
            )

        cur_w = max(combo_width_for_text(combo.currentText()), min_w)
        combo.setMinimumWidth(cur_w)
        combo.setMaximumWidth(cur_w)

        widest = 0
        for i in range(combo.count()):
            widest = max(
                widest, combo.fontMetrics().horizontalAdvance(combo.itemText(i))
            )
        if widest:
            # 弹出列表无下拉箭头，左右各留 pad_extra 余量
            combo.view().setMinimumWidth(widest + pad_extra * 2)

    def _sync_verify_frame_chk(self):
        """「校验该帧」只对支持容错解析的协议可用（当前 698.45）。"""
        chk = getattr(self, "verify_frame_chk", None)
        if chk is None:
            return
        try:
            supported = int(self.current_protocol) in TOLERANT_PARSE_PROTOCOLS
        except Exception:  # noqa: BLE001
            supported = False
        chk.setEnabled(supported)
        if supported:
            chk.setToolTip(
                "勾选（默认）：要求帧结构、长度自洽、HCS/FCS 通过才解析，不完整时报「解析失败」。\n"
                "取消：按实收字节容错解析，能拆到哪算哪，剩余字节以「未解析字节 / 原始报文」原样输出。"
            )
        else:
            chk.setToolTip("当前协议暂不支持容错解析（目前仅 698.45 / 协议8 支持）")

    def _on_protocol_changed(self, index: int):
        """协议选择改变时的回调"""
        self.current_protocol = index
        self._sync_verify_frame_chk()
        spec = protocol_registry.get_protocol(index)
        # 更新占位符提示
        self.single_input.setPlaceholderText(spec.placeholder)

        # 更新查询页面
        self._update_protocol_lookup_tab()

        # 协议组帧页面和预设命令页面：注册表 frame_gen_mode / preset_mode
        if hasattr(self, "_frame_gen_tab_index"):
            show_frame_gen = spec.frame_gen_mode is not None
            self.tab_widget.setTabVisible(self._frame_gen_tab_index, show_frame_gen)
            if show_frame_gen:
                mode = spec.frame_gen_mode
                self._pending_frame_gen_mode = mode
                if hasattr(self, "frame_gen_tab"):
                    self.frame_gen_tab.set_protocol_mode(mode)
            else:
                if hasattr(self, "frame_gen_tab"):
                    self.frame_gen_tab.reset()
        if hasattr(self, "_preset_tab_index"):
            # 预设命令页只在协议**有预设库**（spec.preset_mode）时显示。
            # 不能继续用 frame_gen_mode 判定：协议9 有组帧页但暂无预设库，
            # 按 frame_gen_mode 判定会把空预设页显示出来，且「添加到预设」会
            # 经 preset_buttons._get_path 的兜底分支误写 GW_command.json。
            self.tab_widget.setTabVisible(
                self._preset_tab_index, spec.preset_mode is not None
            )
            if spec.preset_mode is not None and hasattr(self, "preset_tab"):
                # 含协议6 dlt645：此前 set_protocol 挂在 virtual_meter 可见块内且漏 6
                self.preset_tab.set_protocol(spec.preset_mode)
        if hasattr(self, "_virtual_meter_tab_index"):
            self.tab_widget.setTabVisible(
                self._virtual_meter_tab_index, spec.has_virtual_meter
            )
        if hasattr(self, "_dlt645_sim_tab_index"):
            self.tab_widget.setTabVisible(
                self._dlt645_sim_tab_index, spec.has_dlt645_sim
            )
        # 协议8 698.45 文件传输升级：注册表 has_upgrade（仅协议8 可见）
        if hasattr(self, "_upgrade_tab_index"):
            self.tab_widget.setTabVisible(self._upgrade_tab_index, spec.has_upgrade)
        # 协议8 698.45 协议测试（按 OAD 分类的预置测试库）：注册表 has_test
        if hasattr(self, "_test_tab_index"):
            self.tab_widget.setTabVisible(self._test_tab_index, spec.has_test)
        # 档案管理 / 拓扑信息
        if hasattr(self, "_archive_tab_index"):
            self.tab_widget.setTabVisible(self._archive_tab_index, spec.has_archive)
            if spec.has_archive:
                mode = "south" if index == 0 else "gdw"
                self._pending_archive_mode = mode
                if hasattr(self, "archive_tab"):
                    self.archive_tab.set_protocol_mode(mode)
        if hasattr(self, "_topology_tab_index"):
            self.tab_widget.setTabVisible(self._topology_tab_index, spec.has_topology)
            if spec.has_topology:
                mode = "south" if index == 0 else "gdw"
                self._pending_topology_mode = mode
                if hasattr(self, "topology_tab"):
                    self.topology_tab.set_protocol_mode(mode)
            else:
                if hasattr(self, "topology_tab"):
                    self.topology_tab.clear_nodes()

        # 新一代载波协议解析级别：仅协议索引9时可见
        show_csg_level = spec.parse_level_family == "csg"
        self.csg_parse_level_label.setVisible(show_csg_level)
        self.csg_parse_level_combo.setVisible(show_csg_level)
        self.csg_pb_frame_type_label.setVisible(
            show_csg_level and self._csg_parse_level in ("pb_only", "mac_only")
        )
        self.csg_pb_frame_type_combo.setVisible(
            show_csg_level and self._csg_parse_level in ("pb_only", "mac_only")
        )
        # ED 监控 / 4字节反转 / 字节剔除：能力来自注册表（协议9/10/11）
        # 现场日志常带 ED..EE 封装与 4 字节端序，协议10/11 与协议9 同一套操作
        show_ed_ui = getattr(spec, "has_ed_monitor", False)
        show_rev = getattr(spec, "has_reverse_4byte", False)
        self.ed_monitor_chk.setVisible(show_ed_ui)
        if hasattr(self, "ed_wrapper_combo"):
            self.ed_wrapper_combo.setVisible(show_ed_ui)
            # 包装格式下拉文案按协议语境：9=广西台体/PLC2.0；10/11=国网HDC/PLC2.0布局
            self._sync_ed_wrapper_combo_labels(index)
        self.csg_reverse_4byte_chk.setVisible(show_rev)
        self.csg_strip_head_label.setVisible(show_ed_ui)
        self.csg_strip_head_spin.setVisible(show_ed_ui)
        self.csg_strip_tail_label.setVisible(show_ed_ui)
        self.csg_strip_tail_spin.setVisible(show_ed_ui)
        # 通道下拉框：仅协议索引9（南网新一代）时可见
        self.csg_channel_label.setVisible(show_csg_level)
        self.csg_channel_combo.setVisible(show_csg_level)

        # 国网新一代/HDC 1.0 解析级别选择：协议索引10和11时可见
        show_gw_level = spec.parse_level_family in ("gw", "hdc10")
        self.gw_parse_level_label.setVisible(show_gw_level)
        self.gw_parse_level_combo.setVisible(show_gw_level)
        # 通道下拉框：协议索引10和11时可见
        self.gw_channel_label.setVisible(show_gw_level)
        self.gw_channel_combo.setVisible(show_gw_level)

        # 同步解析级别combo到对应协议的当前值
        if index == 10:
            idx = self.gw_parse_level_combo.findData(self._gw_parse_level)
            if idx >= 0:
                self.gw_parse_level_combo.setCurrentIndex(idx)
        elif index == 11:
            idx = self.gw_parse_level_combo.findData(self._hdc10_parse_level)
            if idx >= 0:
                self.gw_parse_level_combo.setCurrentIndex(idx)

        # 清空当前结果
        self.clear_single()

        # 同步协议到报文对比标签页
        if hasattr(self, "diff_tab"):
            self.diff_tab.set_protocol(index)
            self.diff_tab.set_parser(self._get_current_parser())

        # 按当前选中项文字重新拟合各下拉框宽度，再让 FlowLayout 重算换行与高度
        self._fit_combo_to_current(self.protocol_combo, min_w=120)
        self._fit_combo_to_current(self.csg_parse_level_combo, min_w=90)
        self._fit_combo_to_current(self.csg_channel_combo, min_w=96)
        self._fit_combo_to_current(self.gw_parse_level_combo, min_w=90)
        self._fit_combo_to_current(self.gw_channel_combo, min_w=96)
        self._fit_combo_to_current(self.csg_pb_frame_type_combo, min_w=90)
        self._fit_combo_to_current(self.gw_pb_frame_type_combo, min_w=90)
        self._reflow_proto_group()
        # 协议折叠时窗口标题中间的协议名跟随切换
        self._update_window_title()

        # 通信时序图标签页：注册表 has_sequence_diagram；按钮同步启停
        if hasattr(self, "_seq_diagram_tab_index"):
            self.tab_widget.setTabVisible(
                self._seq_diagram_tab_index, spec.has_sequence_diagram
            )
        if hasattr(self, "batch_seq_diagram_btn"):
            self.batch_seq_diagram_btn.setEnabled(spec.has_sequence_diagram)

        # 监控器标签页：注册表 has_monitor / monitor_wrapper
        if hasattr(self, "_monitor_tab_index"):
            show_monitor = spec.has_monitor
            self.tab_widget.setTabVisible(self._monitor_tab_index, show_monitor)
            if show_monitor:
                parser = (
                    self.csg_new_gen_parser if index == 9 else self.gw_new_gen_parser
                )
                self.monitor_tab.set_protocol(
                    parser,
                    self._get_monitor_summary,
                    wrapper_format=spec.monitor_wrapper or "hplc",
                )

        # 协议切换时把当前协议同步到快捷解析小窗（小窗存在时）
        # set_protocol_index 静默切下拉；不重解析，由用户后续输入触发
        if getattr(self, "_quick_panel", None) is not None:
            self._quick_panel.set_protocol_index(index)

        # 持久化协议选择（UI 全部就绪后才写盘，避免构造期触发保存）
        if getattr(self, "_ui_ready", False):
            self._save_app_config()

    def _sync_ed_wrapper_combo_labels(self, protocol_index: int):
        """按协议语境刷新 ED 包装格式下拉文案（数据值 auto/plc2/gx 不变）。"""
        if not hasattr(self, "ed_wrapper_combo"):
            return
        from batch_core import ed_wrapper_display
        combo = self.ed_wrapper_combo
        combo.blockSignals(True)
        current = combo.currentData()
        labels = {
            "auto": "自动识别(推荐)",
            "plc2": ed_wrapper_display(protocol_index, "plc2")["combo_label"],
            "gx": ed_wrapper_display(protocol_index, "gx")["combo_label"],
        }
        for i in range(combo.count()):
            val = combo.itemData(i)
            if val in labels:
                combo.setItemText(i, labels[val])
        idx = combo.findData(current)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.blockSignals(False)
        self._fit_combo_to_current(combo, min_w=90)

    def _get_monitor_summary(self, table_data: list) -> str:
        """监控器摘要生成：按当前协议分派到对应摘要函数"""
        if self.current_protocol == 9:
            return self._get_csg_new_gen_summary(table_data)
        if self.current_protocol == 10:
            return self._get_gw_new_gen_summary(table_data)
        return self._get_summary_from_table_data(table_data)

    def _send_frame_to_single_parse(self, hex_str: str):
        """监控器双击帧：送入单帧解析页并触发解析"""
        self.single_input.setPlainText(hex_str)
        self.tab_widget.setCurrentIndex(0)
        self.parse_single()

    def _on_csg_parse_level_changed(self, index: int):
        """新一代载波协议解析级别改变时的回调"""
        level = self.csg_parse_level_combo.currentData()
        self._csg_parse_level = level or "auto"
        # pb_only / mac_only 模式显示帧类型选择
        show_frame_type = self._csg_parse_level in ("pb_only", "mac_only")
        self.csg_pb_frame_type_label.setVisible(show_frame_type)
        self.csg_pb_frame_type_combo.setVisible(show_frame_type)
        self._fit_combo_to_current(self.csg_parse_level_combo, min_w=90)
        self._fit_combo_to_current(self.csg_pb_frame_type_combo, min_w=90)
        self._reflow_proto_group()

    def _on_gw_parse_level_changed(self, index: int):
        """国网新一代/HDC 1.0 解析级别改变时的回调"""
        level = self.gw_parse_level_combo.currentData()
        if self.current_protocol == 11:
            self._hdc10_parse_level = level or "auto"
        else:
            self._gw_parse_level = level or "auto"

        # 根据解析级别显示/隐藏帧类型选择
        cur_level = (
            self._hdc10_parse_level
            if self.current_protocol == 11
            else self._gw_parse_level
        )
        show_frame_type = cur_level == "pb_only"
        self.gw_pb_frame_type_label.setVisible(
            show_frame_type and self.current_protocol in (10, 11)
        )
        self.gw_pb_frame_type_combo.setVisible(
            show_frame_type and self.current_protocol in (10, 11)
        )
        self._reflow_proto_group()
        # 级别切换后自动重解析（与通道切换同口径），避免界面显示新级别但仍是旧结果
        if self.single_input.toPlainText().strip():
            self.parse_single()

    def _on_csg_channel_changed(self, index: int):
        """南网新一代通道切换回调"""
        channel = self.csg_channel_combo.currentData()
        self._csg_channel = channel or "plc"
        self._fit_combo_to_current(self.csg_channel_combo, min_w=96)
        self._reflow_proto_group()
        # 自动重解析
        if self.single_input.toPlainText().strip():
            self.parse_single()

    def _on_gw_channel_changed(self, index: int):
        """国网新一代/HDC 1.0 通道切换回调"""
        channel = self.gw_channel_combo.currentData()
        if self.current_protocol == 11:
            self._hdc10_channel = channel or "plc"
        else:
            self._gw_channel = channel or "plc"
        self._fit_combo_to_current(self.gw_channel_combo, min_w=96)
        self._reflow_proto_group()
        # 自动重解析
        if self.single_input.toPlainText().strip():
            self.parse_single()

    def _toggle_llm_panel(self):
        """切换 LLM 预处理面板的显示/隐藏"""
        widget = self.llm_preprocess_widget
        btn = self.llm_toggle_btn
        if widget.isVisible():
            widget.hide()
            btn.setText("▶ LLM 智能预处理")
            btn.setChecked(False)
        else:
            widget.show()
            btn.setText("▼ LLM 智能预处理")
            btn.setChecked(True)
            # 刷新模型列表（可能刚在 API 管理中添加了新配置）
            widget._refresh_profiles()

    def _update_protocol_lookup_tab(self):
        """根据当前协议更新查询页面内容（builder 由 protocol_registry 映射）"""
        self._clear_layout(self.protocol_lookup_tab_layout)

        lookup_tab_index = self.tab_widget.indexOf(self.protocol_lookup_tab)
        spec = protocol_registry.get_protocol(self.current_protocol)
        builder_name = protocol_registry.lookup_builder_method(spec.lookup_kind)
        if spec.lookup_tab_title:
            self.tab_widget.setTabText(lookup_tab_index, spec.lookup_tab_title)
        if builder_name:
            getattr(self, builder_name)(self.protocol_lookup_tab_layout)
        # 查询页表格刚重建（持有代码默认列宽）：先快照默认值，再套用保存的列宽。
        # 否则切协议后用户调过的列宽会回到代码默认。
        self._snapshot_default_column_widths()
        self._apply_saved_column_widths()

    def _create_oad_lookup_content(self, layout):
        """创建698.45协议OAD查询页面内容"""
        # 搜索栏
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFixedWidth(45)
        self.oad_search_input = QLineEdit()
        self.oad_search_input.setPlaceholderText(
            "输入OI(如2000)或中文关键词(如通信地址)搜索..."
        )
        self.oad_search_input.setClearButtonEnabled(True)
        self.oad_search_input.textChanged.connect(self._filter_oad_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.oad_search_input)
        layout.addLayout(search_layout)

        # 统计标签
        self.oad_stats_label = self._make_stats_label()
        layout.addWidget(self.oad_stats_label)

        # 表格
        self.oad_table = ZoomableTableWidget()
        self.oad_table.setColumnCount(5)
        self.oad_table.setHorizontalHeaderLabels(
            ["OI", "对象名称", "属性", "方法", "说明"]
        )
        header = self.oad_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.oad_table.setColumnWidth(0, 80)
        self.oad_table.setColumnWidth(1, 120)
        self.oad_table.setColumnWidth(2, 200)
        self.oad_table.setColumnWidth(3, 120)
        self.oad_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.oad_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.oad_table.setAlternatingRowColors(True)
        self.oad_table.verticalHeader().hide()
        self.oad_table.verticalHeader().setDefaultSectionSize(20)
        table_font = self._ui_font(-2)
        self.oad_table.setFont(table_font)
        layout.addWidget(self.oad_table)

        # 加载数据
        self._load_oad_map_data()

    def _create_csg_new_gen_lookup_content(self, layout):
        """创建新一代载波协议(通感一体化)业务标识查询页面内容"""
        from csg_new_gen_parser import (
            CMD_COMM_SERVICE_MAP,
            CMD_FUNC_SERVICE_MAP,
            CONFIRM_SERVICE_MAP,
            DATA_SERVICE_MAP,
            DIRECTION_MAP,
            EXTENSION_MAP,
            FRAME_TYPE_MAP,
            MPDU_VERSION_MAP,
            MSG_ID_MAP,
            MSG_PORT_MAP,
            PRM_MAP,
            RESPONSE_MAP,
        )

        # 搜索栏
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFont(self._ui_font(0))
        search_layout.addWidget(search_label)

        self.csg_new_gen_search = QLineEdit()
        self.csg_new_gen_search.setPlaceholderText(
            "输入关键词搜索业务标识（如：确认、数据传输、命令...）"
        )
        self.csg_new_gen_search.setFont(self._ui_font(0))
        self.csg_new_gen_search.textChanged.connect(self._load_csg_new_gen_map_data)
        search_layout.addWidget(self.csg_new_gen_search)
        layout.addLayout(search_layout)

        # 统计标签
        self.csg_new_gen_stats_label = QLabel()
        self.csg_new_gen_stats_label.setFont(self._ui_font(-1))
        layout.addWidget(self.csg_new_gen_stats_label)

        # 查询表格
        self.csg_new_gen_table = ZoomableTableWidget()
        self.csg_new_gen_table.setColumnCount(4)
        self.csg_new_gen_table.setHorizontalHeaderLabels(
            ["分类", "代码", "名称", "说明"]
        )
        self.csg_new_gen_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.csg_new_gen_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.csg_new_gen_table.setAlternatingRowColors(True)
        self.csg_new_gen_table.verticalHeader().hide()
        self.csg_new_gen_table.verticalHeader().setDefaultSectionSize(20)
        table_font = self._ui_font(-2)
        self.csg_new_gen_table.setFont(table_font)
        # 表头自适应
        header = self.csg_new_gen_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.csg_new_gen_table)

        # 存储查找表
        self._csg_new_gen_entries = []
        # 构建条目列表
        for cat, map_dict in [
            ("报文端口号", MSG_PORT_MAP),
            ("报文标识符", MSG_ID_MAP),
            ("帧类型域", FRAME_TYPE_MAP),
            ("传输方向", DIRECTION_MAP),
            ("启动标志(PRM)", PRM_MAP),
            ("响应标识", RESPONSE_MAP),
            ("业务扩展域", EXTENSION_MAP),
            ("确认/否认业务", CONFIRM_SERVICE_MAP),
            ("数据传输业务", DATA_SERVICE_MAP),
            ("命令-功能业务", CMD_FUNC_SERVICE_MAP),
            ("命令-通信管理业务", CMD_COMM_SERVICE_MAP),
            ("MPDU标准版本", MPDU_VERSION_MAP),
        ]:
            for code, name in map_dict.items():
                self._csg_new_gen_entries.append(
                    (cat, f"0x{code:02X}" if isinstance(code, int) else code, name, "")
                )

        self._load_csg_new_gen_map_data()

    def _load_csg_new_gen_map_data(self):
        """加载/过滤新一代载波协议业务标识数据"""
        search = (
            self.csg_new_gen_search.text().strip().lower()
            if hasattr(self, "csg_new_gen_search")
            else ""
        )
        results = [
            e
            for e in self._csg_new_gen_entries
            if not search
            or search in e[0].lower()
            or search in e[1].lower()
            or search in e[2].lower()
        ]

        self.csg_new_gen_table.setRowCount(len(results))
        for row, (cat, code, name, note) in enumerate(results):
            self.csg_new_gen_table.setItem(row, 0, QTableWidgetItem(cat))
            self.csg_new_gen_table.setItem(row, 1, QTableWidgetItem(str(code)))
            self.csg_new_gen_table.setItem(row, 2, QTableWidgetItem(name))
            self.csg_new_gen_table.setItem(row, 3, QTableWidgetItem(note))

        self.csg_new_gen_stats_label.setText(
            f"匹配 {len(results)} / {len(self._csg_new_gen_entries)} 条记录"
        )

    def _create_gw_new_gen_lookup_content(self, layout):
        """创建国网新一代双模通信互联互通报文ID查询页面内容"""
        from gw_new_gen_parser import GWNewGenParser

        parser = GWNewGenParser()

        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFont(self._ui_font(0))
        search_layout.addWidget(search_label)
        self.gw_new_gen_search = QLineEdit()
        self.gw_new_gen_search.setPlaceholderText(
            "输入关键词搜索报文ID/端口号/消息类型..."
        )
        self.gw_new_gen_search.setFont(self._ui_font(0))
        self.gw_new_gen_search.textChanged.connect(self._load_gw_new_gen_map_data)
        search_layout.addWidget(self.gw_new_gen_search)
        layout.addLayout(search_layout)

        self.gw_new_gen_stats_label = QLabel()
        self.gw_new_gen_stats_label.setFont(self._ui_font(-1))
        layout.addWidget(self.gw_new_gen_stats_label)

        self.gw_new_gen_table = ZoomableTableWidget()
        self.gw_new_gen_table.setColumnCount(4)
        self.gw_new_gen_table.setHorizontalHeaderLabels(
            ["分类", "代码", "名称", "说明"]
        )
        self.gw_new_gen_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.gw_new_gen_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.gw_new_gen_table.setAlternatingRowColors(True)
        self.gw_new_gen_table.verticalHeader().hide()
        self.gw_new_gen_table.verticalHeader().setDefaultSectionSize(20)
        header = self.gw_new_gen_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.gw_new_gen_table)

        self._gw_new_gen_entries = []
        for code, name in parser.MSG_IDS.items():
            sec = (code >> 12) & 0x0F
            self._gw_new_gen_entries.append(
                ("报文ID", f"0x{code:04X}", name, f"安全机制={sec}")
            )
        for code, name in parser.PORT_NAMES.items():
            self._gw_new_gen_entries.append(("报文端口号", f"0x{code:02X}", name, ""))
        for code, name in parser.DELIMITER_TYPES.items():
            self._gw_new_gen_entries.append(("定界符类型", str(code), name, ""))
        for code, name in parser.MSDU_TYPES.items():
            self._gw_new_gen_entries.append(("MSDU类型", str(code), name, ""))
        for code, name in parser.PROTOCOL_TYPES.items():
            self._gw_new_gen_entries.append(("规约类型", str(code), name, ""))
        for code, name in parser.SEND_TYPES.items():
            self._gw_new_gen_entries.append(("发送类型", str(code), name, ""))
        for code, name in parser.BROADCAST_DIRS.items():
            self._gw_new_gen_entries.append(("广播方向", str(code), name, ""))
        self._load_gw_new_gen_map_data()

    def _load_gw_new_gen_map_data(self):
        """加载/过滤国网新一代报文ID数据"""
        search = (
            self.gw_new_gen_search.text().strip().lower()
            if hasattr(self, "gw_new_gen_search")
            else ""
        )
        results = [
            e
            for e in self._gw_new_gen_entries
            if not search
            or search in e[0].lower()
            or search in e[1].lower()
            or search in e[2].lower()
        ]
        self.gw_new_gen_table.setRowCount(len(results))
        for row, (cat, code, name, note) in enumerate(results):
            self.gw_new_gen_table.setItem(row, 0, QTableWidgetItem(cat))
            self.gw_new_gen_table.setItem(row, 1, QTableWidgetItem(str(code)))
            self.gw_new_gen_table.setItem(row, 2, QTableWidgetItem(name))
            self.gw_new_gen_table.setItem(row, 3, QTableWidgetItem(note))
        self.gw_new_gen_stats_label.setText(
            f"匹配 {len(results)} / {len(self._gw_new_gen_entries)} 条记录"
        )

    def _create_hdc10_lookup_content(self, layout):
        """创建HDC 1.0双模互联互通报文ID查询页面内容"""
        from hdc10_parser import (
            APP_PORTS,
            BROADCAST_DIRS,
            DELIMITER_TYPES,
            MSDU_TYPES,
            MSG_ID_NAMES,
            PROTOCOL_TYPES,
            SECURITY_MODES,
            TX_TYPES,
            HDC10Parser,
        )

        parser = HDC10Parser()

        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFont(self._ui_font(0))
        search_layout.addWidget(search_label)
        self.hdc10_search = QLineEdit()
        self.hdc10_search.setPlaceholderText("输入关键词搜索报文ID/端口号/消息类型...")
        self.hdc10_search.setFont(self._ui_font(0))
        self.hdc10_search.textChanged.connect(self._load_hdc10_map_data)
        search_layout.addWidget(self.hdc10_search)
        layout.addLayout(search_layout)

        self.hdc10_stats_label = QLabel()
        self.hdc10_stats_label.setFont(self._ui_font(-1))
        layout.addWidget(self.hdc10_stats_label)

        self.hdc10_table = ZoomableTableWidget()
        self.hdc10_table.setColumnCount(4)
        self.hdc10_table.setHorizontalHeaderLabels(["分类", "代码", "名称", "说明"])
        self.hdc10_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.hdc10_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.hdc10_table.setAlternatingRowColors(True)
        self.hdc10_table.verticalHeader().hide()
        self.hdc10_table.verticalHeader().setDefaultSectionSize(20)
        header = self.hdc10_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.hdc10_table)

        self._hdc10_entries = []
        for code, name in MSG_ID_NAMES.items():
            self._hdc10_entries.append(("报文ID(业务)", f"0x{code:03X}", name, ""))
        for code, name in APP_PORTS.items():
            self._hdc10_entries.append(("报文端口号", f"0x{code:02X}", name, ""))
        for code, name in DELIMITER_TYPES.items():
            self._hdc10_entries.append(("定界符类型", str(code), name, ""))
        for code, name in MSDU_TYPES.items():
            self._hdc10_entries.append(("MSDU类型", str(code), name, ""))
        for code, name in PROTOCOL_TYPES.items():
            self._hdc10_entries.append(("规约类型", str(code), name, ""))
        for code, name in TX_TYPES.items():
            self._hdc10_entries.append(("发送类型", str(code), name, ""))
        for code, name in BROADCAST_DIRS.items():
            self._hdc10_entries.append(("广播方向", str(code), name, ""))
        for code, name in SECURITY_MODES.items():
            self._hdc10_entries.append(("安全模式", str(code), name, ""))
        self._load_hdc10_map_data()

    def _load_hdc10_map_data(self):
        """加载/过滤HDC 1.0报文ID数据"""
        search = (
            self.hdc10_search.text().strip().lower()
            if hasattr(self, "hdc10_search")
            else ""
        )
        results = [
            e
            for e in self._hdc10_entries
            if not search
            or search in e[0].lower()
            or search in e[1].lower()
            or search in e[2].lower()
        ]
        self.hdc10_table.setRowCount(len(results))
        for row, (cat, code, name, note) in enumerate(results):
            self.hdc10_table.setItem(row, 0, QTableWidgetItem(cat))
            self.hdc10_table.setItem(row, 1, QTableWidgetItem(str(code)))
            self.hdc10_table.setItem(row, 2, QTableWidgetItem(name))
            self.hdc10_table.setItem(row, 3, QTableWidgetItem(note))
        self.hdc10_stats_label.setText(
            f"匹配 {len(results)} / {len(self._hdc10_entries)} 条记录"
        )

    def _create_modular_iface_lookup_content(self, layout):
        """模组化终端功能模块接口：信息类标识 / APDU / 控制码 查询页。"""
        from modular_iface_parser import (
            APDU_NAMES,
            CTRL_FUNC_NAMES,
            DTA1_MODULE_NAMES,
            DTA2_RW,
            GENERIC_DT_NAMES,
        )

        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFont(self._ui_font(0))
        search_layout.addWidget(search_label)
        self.modular_search = QLineEdit()
        self.modular_search.setPlaceholderText("输入关键词搜索 APDU/控制码/信息类...")
        self.modular_search.setFont(self._ui_font(0))
        self.modular_search.textChanged.connect(self._load_modular_map_data)
        search_layout.addWidget(self.modular_search)
        layout.addLayout(search_layout)

        self.modular_stats_label = QLabel()
        self.modular_stats_label.setFont(self._ui_font(-1))
        layout.addWidget(self.modular_stats_label)

        self.modular_table = ZoomableTableWidget()
        self.modular_table.setColumnCount(4)
        self.modular_table.setHorizontalHeaderLabels(["分类", "代码", "名称", "说明"])
        self.modular_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.modular_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.modular_table.setAlternatingRowColors(True)
        self.modular_table.verticalHeader().hide()
        header = self.modular_table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.modular_table)

        self._modular_entries = []
        for code, name in APDU_NAMES.items():
            self._modular_entries.append(
                ("APDU", f"0x{code:02X}", name, "A-XDR CHOICE")
            )
        for code, name in CTRL_FUNC_NAMES.items():
            self._modular_entries.append(
                ("控制码", f"{code:02X}H", name, "确认/否认/信息")
            )
        for dta1, mname in DTA1_MODULE_NAMES.items():
            self._modular_entries.append(
                ("DTA1模块", f"{dta1}H", mname, "信息类标识高5位")
            )
        for dta2, rw in DTA2_RW.items():
            self._modular_entries.append(
                ("DTA2读写", f"{dta2}H", rw, "信息类标识 bit10~8")
            )
        # GENERIC_DT_NAMES 键为 (dta2, dtb)，固定 DTA1=0
        for (dta2, dtb), gname in GENERIC_DT_NAMES.items():
            dt_val = ((dta2 & 0x07) << 8) | (dtb & 0xFF)
            self._modular_entries.append(
                (
                    "通用信息类",
                    f"DT=0x{dt_val:04X}",
                    gname,
                    f"DTA1=0 DTA2={dta2:X}H DTB={dtb:02X}H",
                )
            )
        self._load_modular_map_data()

    def _load_modular_map_data(self):
        search = (
            self.modular_search.text().strip().lower()
            if hasattr(self, "modular_search")
            else ""
        )
        results = [
            e
            for e in self._modular_entries
            if not search
            or search in e[0].lower()
            or search in e[1].lower()
            or search in e[2].lower()
            or search in str(e[3]).lower()
        ]
        self.modular_table.setRowCount(len(results))
        for row, (cat, code, name, note) in enumerate(results):
            self.modular_table.setItem(row, 0, QTableWidgetItem(cat))
            self.modular_table.setItem(row, 1, QTableWidgetItem(str(code)))
            self.modular_table.setItem(row, 2, QTableWidgetItem(name))
            self.modular_table.setItem(row, 3, QTableWidgetItem(note or ""))
        self.modular_stats_label.setText(
            f"匹配 {len(results)} / {len(self._modular_entries)} 条记录"
        )

    def _create_yw645_lookup_content(self, layout):
        """依瓦定制645（协议13）：附录A 通用参数类数据项查询页。

        数据源**单一来源** = ``yw645_di.DI_TABLE``（解析器 / 组帧下拉 / Web 查询页同源），
        **禁止**在本文件手写第二份 DI 清单（AGENTS.md 陷阱 48/55/61）。
        """
        from yw645_di import DI_TABLE

        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFont(self._ui_font(0))
        search_layout.addWidget(search_label)
        self.yw645_search = QLineEdit()
        self.yw645_search.setPlaceholderText(
            "输入 ID（0010 / 00 10）或中文关键词（设备类型 / 设备号）..."
        )
        self.yw645_search.setFont(self._ui_font(0))
        self.yw645_search.textChanged.connect(self._load_yw645_map_data)
        search_layout.addWidget(self.yw645_search)
        layout.addLayout(search_layout)

        self.yw645_stats_label = QLabel()
        self.yw645_stats_label.setFont(self._ui_font(-1))
        layout.addWidget(self.yw645_stats_label)

        self.yw645_table = ZoomableTableWidget()
        self.yw645_table.setColumnCount(6)
        self.yw645_table.setHorizontalHeaderLabels(
            ["ID", "数据项名称", "长度", "数据类型", "读/写", "说明"]
        )
        self.yw645_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.yw645_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.yw645_table.setAlternatingRowColors(True)
        self.yw645_table.verticalHeader().hide()
        header = self.yw645_table.horizontalHeader()
        header.setStretchLastSection(True)
        for _col in range(5):
            header.setSectionResizeMode(_col, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.yw645_table)

        self._yw645_entries = []
        for entry in DI_TABLE:
            did = str(entry.get("id", "")).upper()
            spaced = f"{did[:2]} {did[2:]}".strip()
            name = entry.get("name", "")
            length = entry.get("length", "")
            dtype = entry.get("dtype", "")
            rw = entry.get("rw", "")
            note = entry.get("note", "")
            self._yw645_entries.append(
                {
                    "cells": [spaced, name, length, dtype, rw, note],
                    # 过滤覆盖 ID 十六进制（0010 与 00 10 两种写法）+ 名称 + 说明
                    "search": f"{did} {spaced} {name} {length} {dtype} {rw} {note}".lower(),
                }
            )
        self._load_yw645_map_data()

    def _load_yw645_map_data(self):
        search = (
            self.yw645_search.text().strip().lower()
            if hasattr(self, "yw645_search")
            else ""
        )
        results = [
            item
            for item in self._yw645_entries
            if not search or search in item["search"]
        ]
        self.yw645_table.setRowCount(len(results))
        for row, item in enumerate(results):
            for col, cell in enumerate(item["cells"]):
                self.yw645_table.setItem(row, col, QTableWidgetItem(str(cell)))
        self.yw645_stats_label.setText(
            f"匹配 {len(results)} / {len(self._yw645_entries)} 条记录"
        )

    def _create_csg_uplink_lookup_content(self, layout):
        """南网上行通信规约（协议14）：附 A/B/D/E 数据标识（DI）查询页。

        数据源**单一来源** = ``csg_uplink_di.DI_INDEX``（解析器 / 组帧下拉 / Web 查询页同源），
        **禁止**在本文件手写第二份 DI 清单（AGENTS.md 陷阱 48/55/61）。
        """
        from csg_uplink_di import DI_ENTRIES

        info = QLabel(
            "数据标识来源：附 A 终端参数 / 附 B 测量点参数 / 附 D 告警数据 / 附 E 事件记录；"
            "附 C 测量点数据沿用 DL/T 645-2007 数据标识（请切协议6 查询）；"
            "「网管扩展」（第4章，深化应用）见归属表 4.x 条目。"
            "注：DI 线上低字节在前，本表按表序（DI3 DI2 DI1 DI0）列出。"
        )
        info.setFont(self._ui_font(-1))
        info.setWordWrap(True)
        layout.addWidget(info)

        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFont(self._ui_font(0))
        search_layout.addWidget(search_label)
        self.csg_uplink_search = QLineEdit()
        self.csg_uplink_search.setPlaceholderText(
            "输入 DI（E0000120 / E0 00 01 20）或中文关键词（终端地址 / 告警屏蔽）..."
        )
        self.csg_uplink_search.setFont(self._ui_font(0))
        self.csg_uplink_search.textChanged.connect(self._load_csg_uplink_map_data)
        search_layout.addWidget(self.csg_uplink_search)
        layout.addLayout(search_layout)

        self.csg_uplink_stats_label = QLabel()
        self.csg_uplink_stats_label.setFont(self._ui_font(-1))
        layout.addWidget(self.csg_uplink_stats_label)

        self.csg_uplink_table = ZoomableTableWidget()
        self.csg_uplink_table.setColumnCount(7)
        self.csg_uplink_table.setHorizontalHeaderLabels(
            ["DI", "数据标识名称", "数据格式", "字节数", "单位", "读/写", "归属表"]
        )
        self.csg_uplink_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.csg_uplink_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.csg_uplink_table.setAlternatingRowColors(True)
        self.csg_uplink_table.verticalHeader().hide()
        header = self.csg_uplink_table.horizontalHeader()
        header.setStretchLastSection(True)
        for _col in range(6):
            header.setSectionResizeMode(_col, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.csg_uplink_table)

        self._csg_uplink_entries = []
        for entry in DI_ENTRIES:
            di = str(entry.get("di", "")).upper()
            spaced = " ".join(di[i:i + 2] for i in range(0, len(di), 2))
            name = entry.get("name", "")
            fmt = entry.get("fmt", "")
            nbytes = entry.get("nbytes", "")
            unit = entry.get("unit", "")
            rw = ("读" if entry.get("read") else "") + ("写" if entry.get("write") else "")
            group = entry.get("group", "")
            self._csg_uplink_entries.append({
                "cells": [spaced, name, fmt, nbytes, unit, rw, group],
                "search": f"{di} {spaced} {name} {fmt} {nbytes} {unit} {group}".lower(),
            })
        self._load_csg_uplink_map_data()

    def _load_csg_uplink_map_data(self):
        search = (
            self.csg_uplink_search.text().strip().lower()
            if hasattr(self, "csg_uplink_search")
            else ""
        )
        results = [
            item for item in self._csg_uplink_entries
            if not search or search in item["search"]
        ]
        self.csg_uplink_table.setRowCount(len(results))
        for row, item in enumerate(results):
            for col, cell in enumerate(item["cells"]):
                self.csg_uplink_table.setItem(row, col, QTableWidgetItem(str(cell)))
        self.csg_uplink_stats_label.setText(
            f"匹配 {len(results)} / {len(self._csg_uplink_entries)} 条记录"
        )

    def _load_oad_map_data(self):
        """加载698.45 OI映射数据"""
        from dl_t698_45_oi_lookup import OILookup

        lookup = OILookup()
        self._oad_data = []
        for oi, name in lookup.OI_NAME_MAP.items():
            class_id = lookup.OI_TO_CLASS_ID.get(oi)
            if class_id is not None:
                info = lookup.CLASS_ID_MAP.get(class_id, {})
                attrs = ", ".join(
                    [f"{k}:{v}" for k, v in info.get("attributes", {}).items()]
                )
                methods = ", ".join(
                    [f"{k}:{v}" for k, v in info.get("methods", {}).items()]
                )
            else:
                attrs = ""
                methods = ""
            self._oad_data.append(
                (f"0x{oi:04X}", name, attrs, methods or "-", f"OI=0x{oi:04X}")
            )
        self._filter_oad_table()

    def _filter_oad_table(self):
        """过滤OAD查询表格"""
        keyword = (
            self.oad_search_input.text().strip().lower()
            if hasattr(self, "oad_search_input")
            else ""
        )
        filtered = []
        for row in self._oad_data:
            if not keyword or any(keyword in str(cell).lower() for cell in row):
                filtered.append(row)
        self.oad_table.setRowCount(len(filtered))
        for i, row in enumerate(filtered):
            for j, val in enumerate(row):
                self.oad_table.setItem(i, j, QTableWidgetItem(str(val)))
        self.oad_stats_label.setText(f"共 {len(filtered)} 条记录")

    def _create_gdw_lookup_content(self, layout):
        """创建国网协议AFN查询页面内容"""
        self.gdw_afn_lookup = get_gdw_afn_lookup()

        # 搜索栏 + 操作按钮
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFixedWidth(45)
        self.gdw_search_input = QLineEdit()
        self.gdw_search_input.setPlaceholderText(
            "输入AFN(如03H)或Fn(如F1)或中文关键词搜索..."
        )
        self.gdw_search_input.setClearButtonEnabled(True)
        self.gdw_search_input.textChanged.connect(self._filter_gdw_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.gdw_search_input)

        # 添加自定义按钮
        add_btn = QPushButton("添加自定义")
        add_btn.setToolTip("添加自定义AFN+Fn组合")
        add_btn.clicked.connect(self._add_custom_gdw_fn)
        search_layout.addWidget(add_btn)

        # 删除自定义按钮
        del_btn = QPushButton("删除自定义")
        del_btn.setToolTip("删除选中的自定义AFN+Fn组合")
        del_btn.clicked.connect(self._delete_custom_gdw_fn)
        search_layout.addWidget(del_btn)

        layout.addLayout(search_layout)

        # 统计标签
        self.gdw_stats_label = self._make_stats_label()
        layout.addWidget(self.gdw_stats_label)

        # 表格
        self.gdw_table = ZoomableTableWidget()
        self.gdw_table.setColumnCount(4)
        self.gdw_table.setHorizontalHeaderLabels(["AFN", "AFN名称", "Fn", "功能说明"])
        header = self.gdw_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.gdw_table.setColumnWidth(0, 60)
        self.gdw_table.setColumnWidth(1, 180)
        self.gdw_table.setColumnWidth(2, 60)
        self.gdw_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.gdw_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.gdw_table.setAlternatingRowColors(True)
        self.gdw_table.verticalHeader().hide()
        self.gdw_table.verticalHeader().setDefaultSectionSize(20)
        table_font = self._ui_font(-2)
        self.gdw_table.setFont(table_font)
        layout.addWidget(self.gdw_table)

        # ===== EB 数据标识查询区块（附件1 本地通信模块扩展协议）=====
        eb_group = QGroupBox("EB 数据标识（本地通信模块扩展协议 V3.31）")
        eb_layout = QVBoxLayout(eb_group)
        eb_layout.setContentsMargins(6, 4, 6, 4)
        eb_layout.setSpacing(4)

        eb_search_layout = QHBoxLayout()
        eb_search_label = QLabel("搜索:")
        eb_search_label.setFixedWidth(45)
        self.eb_di_search_input = QLineEdit()
        self.eb_di_search_input.setPlaceholderText(
            "输入EB数据标识(如EB030002)或中文关键词搜索..."
        )
        self.eb_di_search_input.setClearButtonEnabled(True)
        self.eb_di_search_input.textChanged.connect(self._filter_eb_di_table)
        eb_search_layout.addWidget(eb_search_label)
        eb_search_layout.addWidget(self.eb_di_search_input)
        eb_layout.addLayout(eb_search_layout)

        self.eb_di_table = ZoomableTableWidget()
        self.eb_di_table.setColumnCount(5)
        self.eb_di_table.setHorizontalHeaderLabels(
            ["数据标识", "名称", "数据格式", "长度", "功能"]
        )
        eheader = self.eb_di_table.horizontalHeader()
        eheader.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        eheader.setStretchLastSection(True)
        self.eb_di_table.setColumnWidth(0, 90)
        self.eb_di_table.setColumnWidth(1, 220)
        self.eb_di_table.setColumnWidth(2, 70)
        self.eb_di_table.setColumnWidth(3, 50)
        self.eb_di_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.eb_di_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.eb_di_table.setAlternatingRowColors(True)
        self.eb_di_table.verticalHeader().hide()
        self.eb_di_table.verticalHeader().setDefaultSectionSize(20)
        self.eb_di_table.setFont(table_font)
        eb_layout.addWidget(self.eb_di_table)
        layout.addWidget(eb_group)

        # 加载 EB 数据
        self._load_eb_di_data()

    def _load_eb_di_data(self):
        """加载 EB 数据标识到表格"""
        try:
            from gdw_eb_di_lookup import get_eb_di_lookup

            self._eb_di_lookup = get_eb_di_lookup()
            data = self._eb_di_lookup.get_all()
        except Exception:
            data = {}
        self._eb_di_data = data
        self.eb_di_table.setRowCount(len(data))
        for row, (code, info) in enumerate(sorted(data.items())):
            self.eb_di_table.setItem(row, 0, QTableWidgetItem(code))
            self.eb_di_table.setItem(row, 1, QTableWidgetItem(info.get("名称", "")))
            self.eb_di_table.setItem(
                row, 2, QTableWidgetItem(str(info.get("格式", "")))
            )
            self.eb_di_table.setItem(
                row, 3, QTableWidgetItem(str(info.get("长度", "")))
            )
            self.eb_di_table.setItem(row, 4, QTableWidgetItem(info.get("功能", "")))

    def _filter_eb_di_table(self, text: str):
        """过滤 EB 数据标识表格"""
        keyword = text.strip().upper()
        if not keyword:
            self._load_eb_di_data()
            return
        if hasattr(self, "_eb_di_lookup"):
            results = self._eb_di_lookup.search(keyword)
        else:
            results = {}
        self.eb_di_table.setRowCount(len(results))
        for row, (code, info) in enumerate(sorted(results.items())):
            self.eb_di_table.setItem(row, 0, QTableWidgetItem(code))
            self.eb_di_table.setItem(row, 1, QTableWidgetItem(info.get("名称", "")))
            self.eb_di_table.setItem(
                row, 2, QTableWidgetItem(str(info.get("格式", "")))
            )
            self.eb_di_table.setItem(
                row, 3, QTableWidgetItem(str(info.get("长度", "")))
            )
            self.eb_di_table.setItem(row, 4, QTableWidgetItem(info.get("功能", "")))

        # 加载数据
        self._load_gdw_map_data()

    def _load_gdw_map_data(self):
        """从国网解析器加载AFN+Fn数据到表格（包含自定义条目）"""
        data = self.gdw_parser.get_afn_fn_list()
        self._gdw_data = data
        self.gdw_table.setRowCount(len(data))
        for row, (afn, afn_name, fn, fn_name) in enumerate(data):
            item_afn = QTableWidgetItem(f"{afn:02X}H")
            item_afn_name = QTableWidgetItem(afn_name)
            item_fn = QTableWidgetItem(f"F{fn}")
            item_fn_name = QTableWidgetItem(fn_name)
            # 自定义条目用蓝色标记
            is_custom = (
                afn in self.gdw_parser._custom_fn_map
                and fn in self.gdw_parser._custom_fn_map.get(afn, {})
            )
            if is_custom:
                blue_brush = QColor("#E3F2FD")
                for item in (item_afn, item_afn_name, item_fn, item_fn_name):
                    item.setBackground(blue_brush)
            self.gdw_table.setItem(row, 0, item_afn)
            self.gdw_table.setItem(row, 1, item_afn_name)
            self.gdw_table.setItem(row, 2, item_fn)
            self.gdw_table.setItem(row, 3, item_fn_name)
        self.gdw_stats_label.setText(f"共 {len(data)} 条记录")

    def _filter_gdw_table(self, text: str):
        """根据搜索文本过滤国网AFN表格"""
        keyword = text.strip().upper()
        if not keyword:
            self._load_gdw_map_data()
            return
        results = self.gdw_parser.search_afn_fn(keyword)
        self.gdw_table.setRowCount(len(results))
        for row, (afn, afn_name, fn, fn_name) in enumerate(results):
            item_afn = QTableWidgetItem(f"{afn:02X}H")
            item_afn_name = QTableWidgetItem(afn_name)
            item_fn = QTableWidgetItem(f"F{fn}")
            item_fn_name = QTableWidgetItem(fn_name)
            is_custom = (
                afn in self.gdw_parser._custom_fn_map
                and fn in self.gdw_parser._custom_fn_map.get(afn, {})
            )
            if is_custom:
                blue_brush = QColor("#E3F2FD")
                for item in (item_afn, item_afn_name, item_fn, item_fn_name):
                    item.setBackground(blue_brush)
            self.gdw_table.setItem(row, 0, item_afn)
            self.gdw_table.setItem(row, 1, item_afn_name)
            self.gdw_table.setItem(row, 2, item_fn)
            self.gdw_table.setItem(row, 3, item_fn_name)
        self.gdw_stats_label.setText(
            f"匹配 {len(results)} / {len(self._gdw_data)} 条记录"
        )

    def _add_custom_gdw_fn(self):
        """弹出对话框添加自定义AFN+Fn"""
        from PySide6.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QFormLayout,
            QMessageBox,
            QSpinBox,
        )
        from PySide6.QtWidgets import QLineEdit as QLE

        dialog = QDialog(self)
        dialog.setWindowTitle("添加自定义AFN+Fn")
        dialog.setMinimumWidth(300)
        layout = QFormLayout(dialog)

        afn_input = QSpinBox()
        afn_input.setRange(0, 255)
        afn_input.setPrefix("0x")
        afn_input.setDisplayIntegerBase(16)
        layout.addRow("AFN (十六进制):", afn_input)

        fn_input = QSpinBox()
        fn_input.setRange(1, 248)
        layout.addRow("Fn:", fn_input)

        name_input = QLE()
        name_input.setPlaceholderText("输入功能名称")
        layout.addRow("功能名称:", name_input)

        afn_name_input = QLE()
        afn_name_input.setPlaceholderText("可选：自定义AFN类别名称")
        layout.addRow("AFN类别名称(可选):", afn_name_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            afn = afn_input.value()
            fn = fn_input.value()
            name = name_input.text().strip()
            afn_name = afn_name_input.text().strip()
            if not name:
                QMessageBox.warning(self, "警告", "功能名称不能为空")
                return
            # Check if already exists as standard
            if afn in self.gdw_parser.FN_MAP and fn in self.gdw_parser.FN_MAP.get(
                afn, {}
            ):
                QMessageBox.warning(
                    self, "警告", f"AFN={afn:02X}H Fn=F{fn} 已在标准定义中存在"
                )
                return
            # Add custom AFN name if provided
            if afn_name:
                self.gdw_parser.add_custom_afn(afn, afn_name)
            # Add custom Fn
            self.gdw_parser.add_custom_fn(afn, fn, name)
            self._load_gdw_map_data()
            self.gdw_search_input.clear()
            QMessageBox.information(
                self, "成功", f"已添加自定义组合: AFN={afn:02X}H Fn=F{fn}"
            )

    def _delete_custom_gdw_fn(self):
        """删除选中的自定义AFN+Fn"""
        row = self.gdw_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先选中要删除的自定义条目")
            return
        afn_text = self.gdw_table.item(row, 0).text().replace("H", "")
        fn_text = self.gdw_table.item(row, 2).text()
        try:
            afn = int(afn_text, 16)
            fn = int(fn_text.replace("F", ""))
        except ValueError:
            return
        # Check if it's custom
        is_custom = (
            afn in self.gdw_parser._custom_fn_map
            and fn in self.gdw_parser._custom_fn_map.get(afn, {})
        )
        if not is_custom:
            QMessageBox.information(self, "提示", "只能删除自定义添加的条目")
            return
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除自定义组合 AFN={afn:02X}H Fn=F{fn}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.gdw_parser.remove_custom_fn(afn, fn)
            self._load_gdw_map_data()
            QMessageBox.information(self, "成功", "已删除自定义组合")

    def _create_di_lookup_content(self, layout):
        """创建南网协议DI查询页面内容"""
        # 搜索栏
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFixedWidth(45)
        self.di_search_input = QLineEdit()
        self.di_search_input.setPlaceholderText(
            "输入DI编码(如E8020201)或中文关键词(如添加任务)搜索..."
        )
        self.di_search_input.setClearButtonEnabled(True)
        self.di_search_input.textChanged.connect(self._filter_di_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.di_search_input)
        layout.addLayout(search_layout)

        # 统计标签
        self.di_stats_label = self._make_stats_label()
        layout.addWidget(self.di_stats_label)

        # 表格
        self.di_table = ZoomableTableWidget()
        self.di_table.setColumnCount(6)
        self.di_table.setHorizontalHeaderLabels(
            ["DI3", "DI2", "DI1", "DI0", "AFN", "中文含义"]
        )
        header = self.di_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.di_table.setColumnWidth(0, 60)
        self.di_table.setColumnWidth(1, 60)
        self.di_table.setColumnWidth(2, 60)
        self.di_table.setColumnWidth(3, 60)
        self.di_table.setColumnWidth(4, 200)
        self.di_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.di_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.di_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.di_table.setAlternatingRowColors(True)
        self.di_table.verticalHeader().hide()
        self.di_table.verticalHeader().setDefaultSectionSize(20)
        table_font = self._ui_font(-2)
        self.di_table.setFont(table_font)
        layout.addWidget(self.di_table)

        # 按钮栏
        btn_layout = QHBoxLayout()
        add_di_btn = QPushButton("添加自定义DI")
        add_di_btn.clicked.connect(self._add_custom_di)
        btn_layout.addWidget(add_di_btn)

        del_di_btn = QPushButton("删除选中自定义DI")
        del_di_btn.clicked.connect(self._del_custom_di)
        btn_layout.addWidget(del_di_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 加载数据
        self._load_di_map_data()

    def _create_obis_lookup_content(self, layout):
        """创建OBIS查询页面（HDLC/Wrapper/APDU协议）"""
        self.obis_lookup = get_obis_lookup()

        # 搜索栏
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFixedWidth(30)
        self.obis_search_input = QLineEdit()
        self.obis_search_input.setPlaceholderText(
            "输入OBIS码(如0.0.96.1.0.255)或关键词搜索..."
        )
        self.obis_search_input.setClearButtonEnabled(True)
        self.obis_search_input.textChanged.connect(self._filter_obis_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.obis_search_input)
        layout.addLayout(search_layout)

        # 统计标签
        self.obis_stats_label = self._make_stats_label(size=11)
        layout.addWidget(self.obis_stats_label)

        # 表格
        self.obis_table = ZoomableTableWidget()
        self.obis_table.setColumnCount(4)
        self.obis_table.setHorizontalHeaderLabels(
            ["OBIS码", "对象名称", "对象类型", "访问属性"]
        )
        header = self.obis_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.obis_table.setColumnWidth(0, 100)
        self.obis_table.setColumnWidth(1, 130)
        self.obis_table.setColumnWidth(2, 90)
        self.obis_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.obis_table.setAlternatingRowColors(True)
        self.obis_table.verticalHeader().hide()
        self.obis_table.verticalHeader().setDefaultSectionSize(14)
        table_font = self._ui_font(-2)
        self.obis_table.setFont(table_font)

        layout.addWidget(self.obis_table)

        # 加载数据
        self._load_obis_map_data()

    def _create_dlt645_di_lookup_content(self, layout):
        """创建DLT645-2007 DI查询页面"""
        # 初始化DI查询器
        self.dlt645_di_lookup = get_dlt645_di_lookup()

        # 搜索栏
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFixedWidth(45)
        self.dlt645_di_search_input = QLineEdit()
        self.dlt645_di_search_input.setPlaceholderText(
            "输入DI编码(如04000101)或中文关键词搜索..."
        )
        self.dlt645_di_search_input.setClearButtonEnabled(True)
        self.dlt645_di_search_input.textChanged.connect(self._filter_dlt645_di_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.dlt645_di_search_input)
        layout.addLayout(search_layout)

        # 统计标签
        self.dlt645_di_stats_label = QLabel()
        self.dlt645_di_stats_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.dlt645_di_stats_label)

        # 表格
        self.dlt645_di_table = ZoomableTableWidget()
        self.dlt645_di_table.setColumnCount(5)
        self.dlt645_di_table.setHorizontalHeaderLabels(
            ["DI编码", "名称", "单位", "数据类型", "说明"]
        )
        header = self.dlt645_di_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.dlt645_di_table.setColumnWidth(0, 90)
        self.dlt645_di_table.setColumnWidth(1, 180)
        self.dlt645_di_table.setColumnWidth(2, 60)
        self.dlt645_di_table.setColumnWidth(3, 80)
        self.dlt645_di_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.dlt645_di_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.dlt645_di_table.setAlternatingRowColors(True)
        self.dlt645_di_table.verticalHeader().hide()
        self.dlt645_di_table.verticalHeader().setDefaultSectionSize(20)
        table_font = self._ui_font(-2)
        self.dlt645_di_table.setFont(table_font)

        layout.addWidget(self.dlt645_di_table)

        # 按钮栏
        btn_layout = QHBoxLayout()
        add_dlt645_di_btn = QPushButton("添加自定义DI")
        add_dlt645_di_btn.clicked.connect(self._add_dlt645_custom_di)
        btn_layout.addWidget(add_dlt645_di_btn)

        del_dlt645_di_btn = QPushButton("删除选中自定义DI")
        del_dlt645_di_btn.clicked.connect(self._del_dlt645_custom_di)
        btn_layout.addWidget(del_dlt645_di_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 加载数据
        self._load_dlt645_di_map_data()

    def _load_dlt645_di_map_data(self):
        """从DLT645 DI查询器加载数据到表格"""
        data = self.dlt645_di_lookup.data
        self._dlt645_di_data = data
        self.dlt645_di_table.setRowCount(len(data))
        for row, (di_code, di_name, unit, data_type, desc, is_custom) in enumerate(
            data
        ):
            self.dlt645_di_table.setItem(row, 0, QTableWidgetItem(di_code))
            name_item = QTableWidgetItem(("★ " if is_custom else "") + di_name)
            if is_custom:
                name_item.setForeground(QColor("#1976D2"))
            self.dlt645_di_table.setItem(row, 1, name_item)
            self.dlt645_di_table.setItem(row, 2, QTableWidgetItem(unit))
            self.dlt645_di_table.setItem(row, 3, QTableWidgetItem(data_type))
            self.dlt645_di_table.setItem(row, 4, QTableWidgetItem(desc))
        custom_count = sum(1 for item in data if item[5])
        self.dlt645_di_stats_label.setText(
            f"共 {len(data)} 条记录（其中自定义 {custom_count} 条）"
        )

    def _filter_dlt645_di_table(self, text: str):
        """根据搜索文本过滤DLT645 DI表格"""
        keyword = text.strip().upper()
        if not keyword:
            self._load_dlt645_di_map_data()
            return
        results = self.dlt645_di_lookup.search(keyword)
        self.dlt645_di_table.setRowCount(len(results))
        for row, (di_code, di_name, unit, data_type, desc, is_custom) in enumerate(
            results
        ):
            self.dlt645_di_table.setItem(row, 0, QTableWidgetItem(di_code))
            name_item = QTableWidgetItem(("★ " if is_custom else "") + di_name)
            if is_custom:
                name_item.setForeground(QColor("#1976D2"))
            self.dlt645_di_table.setItem(row, 1, name_item)
            self.dlt645_di_table.setItem(row, 2, QTableWidgetItem(unit))
            self.dlt645_di_table.setItem(row, 3, QTableWidgetItem(data_type))
            self.dlt645_di_table.setItem(row, 4, QTableWidgetItem(desc))
        custom_count = sum(1 for item in results if item[5])
        self.dlt645_di_stats_label.setText(
            f"匹配 {len(results)} / {len(self._dlt645_di_data)} 条记录（其中自定义 {custom_count} 条）"
        )

    def _add_dlt645_custom_di(self):
        """添加DLT645自定义DI对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle("添加自定义DI (DLT645)")
        dialog.setMinimumWidth(360)
        layout = QVBoxLayout(dialog)

        # DI编码
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("DI编码:"))
        di_code_input = QLineEdit()
        di_code_input.setPlaceholderText("如 04000101")
        di_code_input.setMaxLength(8)
        h1.addWidget(di_code_input)
        layout.addLayout(h1)

        # 名称
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("名称:"))
        name_input = QLineEdit()
        name_input.setPlaceholderText("如：当前正向有功总电能")
        h2.addWidget(name_input)
        layout.addLayout(h2)

        # 单位
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("单位:"))
        unit_input = QLineEdit()
        unit_input.setPlaceholderText("如：kWh（可留空）")
        h3.addWidget(unit_input)
        layout.addLayout(h3)

        # 数据类型
        h4 = QHBoxLayout()
        h4.addWidget(QLabel("数据类型:"))
        data_type_input = QLineEdit()
        data_type_input.setPlaceholderText("如：XX（可留空）")
        h4.addWidget(data_type_input)
        layout.addLayout(h4)

        # 按钮
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("添加")
        cancel_btn = QPushButton("取消")
        btn_layout.addStretch()
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec() != QDialog.Accepted:
            return

        di_code = di_code_input.text().strip().upper()
        name = name_input.text().strip()
        unit = unit_input.text().strip()
        data_type = data_type_input.text().strip()

        if not di_code or not name:
            QMessageBox.warning(self, "错误", "DI编码和名称不能为空！")
            return

        success = self.dlt645_di_lookup.add_custom_di(di_code, name, unit, data_type)
        if success:
            self._load_dlt645_di_map_data()
            QMessageBox.information(self, "成功", f"已添加自定义DI: {di_code} → {name}")
        else:
            QMessageBox.warning(
                self, "错误", "添加失败，请检查DI编码格式（8位十六进制）"
            )

    def _del_dlt645_custom_di(self):
        """删除选中的DLT645自定义DI"""
        row = self.dlt645_di_table.currentRow()
        if row < 0 or row >= len(self._dlt645_di_data):
            QMessageBox.warning(self, "提示", "请先选中一条记录！")
            return

        di_code, di_name, unit, data_type, desc, is_custom = self._dlt645_di_data[row]

        if not is_custom:
            QMessageBox.warning(self, "提示", "只能删除自定义DI（蓝色★标记的记录）！")
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除自定义DI：{di_code} ({di_name})？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        success = self.dlt645_di_lookup.delete_custom_di(di_code)
        if success:
            self._load_dlt645_di_map_data()
            QMessageBox.information(self, "成功", "已删除自定义DI")
        else:
            QMessageBox.warning(self, "错误", "删除失败")

    def _create_command_lookup_content(self, layout):
        """创建万胜PLC RF协议命令字查询页面"""
        self.command_lookup = get_command_lookup()

        # 搜索栏
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索：")
        search_label.setFixedWidth(30)
        self.cmd_search_input = QLineEdit()
        self.cmd_search_input.setPlaceholderText("输入命令字编码或中文关键词搜索...")
        self.cmd_search_input.setClearButtonEnabled(True)
        self.cmd_search_input.textChanged.connect(self._filter_command_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.cmd_search_input)
        layout.addLayout(search_layout)

        # 统计标签
        self.cmd_stats_label = self._make_stats_label(size=11)
        layout.addWidget(self.cmd_stats_label)

        # 表格
        self.cmd_table = ZoomableTableWidget()
        self.cmd_table.setColumnCount(2)
        self.cmd_table.setHorizontalHeaderLabels(["命令字", "名称"])
        header = self.cmd_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        self.cmd_table.setColumnWidth(0, 80)
        self.cmd_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cmd_table.setAlternatingRowColors(True)
        self.cmd_table.verticalHeader().hide()
        self.cmd_table.verticalHeader().setDefaultSectionSize(14)
        table_font = self._ui_font(-2)
        self.cmd_table.setFont(table_font)

        layout.addWidget(self.cmd_table)

        # 加载数据
        self._load_command_map_data()

    def _load_command_map_data(self):
        """从命令字查询器加载数据到表格"""
        data = self.command_lookup._data
        self.cmd_table.setRowCount(len(data))
        for row, (code, name, desc, is_custom) in enumerate(data):
            self.cmd_table.setItem(row, 0, QTableWidgetItem(f"{code:04X}"))
            name_item = QTableWidgetItem(("★ " if is_custom else "") + name)
            if is_custom:
                name_item.setForeground(QColor("#1976D2"))
            self.cmd_table.setItem(row, 1, name_item)
        self.cmd_stats_label.setText(f"共 {len(data)} 条记录")

    def _filter_command_table(self, text: str):
        """根据搜索文本过滤命令字表格"""
        keyword = text.strip().upper()
        if not keyword:
            self._load_command_map_data()
            return
        results = self.command_lookup.search(keyword)
        self.cmd_table.setRowCount(len(results))
        for row, (code, name, desc, is_custom) in enumerate(results):
            self.cmd_table.setItem(row, 0, QTableWidgetItem(f"{code:04X}"))
            name_item = QTableWidgetItem(("★ " if is_custom else "") + name)
            if is_custom:
                name_item.setForeground(QColor("#1976D2"))
            self.cmd_table.setItem(row, 1, name_item)
        self.cmd_stats_label.setText(
            f"匹配 {len(results)} / {len(self.command_lookup._data)} 条记录"
        )

    def _load_obis_map_data(self):
        """从OBIS查询器加载数据到表格"""
        data = self.obis_lookup._data
        self.obis_table.setRowCount(len(data))
        for row, (obis, name, desc, is_custom) in enumerate(data):
            obis_str = f"{obis[0]}.{obis[1]}.{obis[2]}.{obis[3]}.{obis[4]}.{obis[5]}"
            self.obis_table.setItem(row, 0, QTableWidgetItem(obis_str))
            name_item = QTableWidgetItem(("★ " if is_custom else "") + name)
            if is_custom:
                name_item.setForeground(QColor("#1976D2"))
            self.obis_table.setItem(row, 1, name_item)
            # 根据OBIS A值推断对象类型
            a = obis[0]
            type_map = {
                0: "General",
                1: "Register",
                2: "ExtendedRegister",
                3: "DemandRegister",
                5: "ProfileGeneric",
                7: "ScriptTable",
                10: "Association LN",
                17: "ActivityCalendar",
                20: "DisconnectControl",
            }
            self.obis_table.setItem(
                row, 2, QTableWidgetItem(type_map.get(a, f"Type_{a}"))
            )
            self.obis_table.setItem(
                row, 3, QTableWidgetItem("Read/Write" if is_custom else "Read")
            )
        self.obis_stats_label.setText(f"共 {len(data)} 条记录")

    def _filter_obis_table(self, text: str):
        """根据搜索文本过滤OBIS表格"""
        keyword = text.strip().upper()
        if not keyword:
            self._load_obis_map_data()
            return
        results = self.obis_lookup.search(keyword)
        self.obis_table.setRowCount(len(results))
        for row, (obis, name, desc, is_custom) in enumerate(results):
            obis_str = f"{obis[0]}.{obis[1]}.{obis[2]}.{obis[3]}.{obis[4]}.{obis[5]}"
            self.obis_table.setItem(row, 0, QTableWidgetItem(obis_str))
            name_item = QTableWidgetItem(("★ " if is_custom else "") + name)
            if is_custom:
                name_item.setForeground(QColor("#1976D2"))
            self.obis_table.setItem(row, 1, name_item)
            a = obis[0]
            type_map = {
                0: "General",
                1: "Register",
                2: "ExtendedRegister",
                3: "DemandRegister",
                5: "ProfileGeneric",
                7: "ScriptTable",
                10: "Association LN",
                17: "ActivityCalendar",
                20: "DisconnectControl",
            }
            self.obis_table.setItem(
                row, 2, QTableWidgetItem(type_map.get(a, f"Type_{a}"))
            )
            self.obis_table.setItem(
                row, 3, QTableWidgetItem("Read/Write" if is_custom else "Read")
            )
        self.obis_stats_label.setText(
            f"匹配 {len(results)} / {len(self.obis_lookup._data)} 条记录"
        )

    def _current_parse_params(
        self, protocol_index=None, parse_level=None, frame_type=None
    ) -> dict:
        """当前解析参数**快照**（纯读，不建 parser）：index / parse_level / frame_type / channel。

        从 `_get_current_parser` 中抽出，供后台线程在**不触碰 widget** 的前提下自行
        构造 parser：批量解析必须用独立实例（解析器带帧级可变状态），且不得跨线程
        读 `protocol_combo` / `csg_pb_frame_type_combo`（任务 09-15-gui-batch-parse-perf）。
        """
        protocol_index = (
            self.current_protocol if protocol_index is None else protocol_index
        )
        spec = protocol_registry.get_protocol(protocol_index)
        family = spec.parse_level_family
        if parse_level is None:
            if family == "csg":
                parse_level = getattr(self, "_csg_parse_level", "auto")
            elif family == "gw":
                parse_level = getattr(self, "_gw_parse_level", "auto")
            elif family == "hdc10":
                parse_level = getattr(self, "_hdc10_parse_level", "auto")
        if frame_type is None and parse_level is not None:
            if family == "csg" and parse_level in ("pb_only", "mac_only"):
                frame_type = self.csg_pb_frame_type_combo.currentData()
            elif family in ("gw", "hdc10") and parse_level == "pb_only":
                frame_type = self.gw_pb_frame_type_combo.currentData()
        channel = "plc"
        if family == "csg":
            channel = getattr(self, "_csg_channel", "auto")
        elif family == "gw":
            channel = getattr(self, "_gw_channel", "plc")
        elif family == "hdc10":
            channel = getattr(self, "_hdc10_channel", "plc")

        return {
            "index": protocol_index,
            "parse_level": parse_level,
            "frame_type": frame_type,
            "channel": channel,
        }

    def _get_current_parser(
        self, protocol_index=None, parse_level=None, frame_type=None
    ):
        """获取当前选中的解析器（包装逻辑由 protocol_registry.build_gui_parser 分派）。

        可指定协议索引（用于热键弹窗切换协议）与解析级别覆盖
        （用于弹窗内选择解析级别，None 用主窗口当前设置）。
        """
        params = self._current_parse_params(protocol_index, parse_level, frame_type)
        spec = protocol_registry.get_protocol(params["index"])
        base = get_parser(spec.parser_key)
        return protocol_registry.build_gui_parser(
            params["index"],
            base,
            parse_level=params["parse_level"],
            frame_type=params["frame_type"],
            channel=params["channel"],
        )

    @staticmethod
    def _clean_hex_input(text: str, keep_newlines: bool = False) -> str:
        """预处理报文输入：去除空格、逗号、换行等分隔符，支持0x前缀，仅保留十六进制字符

        支持的输入格式：
          - 纯 hex: 6811010101
          - 空格分隔: 68 11 01 01 01
          - 逗号分隔: 68,11,01,01,01
          - 混合分隔: 68, 11, 01 - 01. 01
          - 0x 前缀: 0x68 0x11 0x01 或 0x68,0x11,0x01
          - 换行分隔(多帧): 每行一帧
        """
        import re

        # 先处理 0x/0X 前缀：将 0x68 转为 68，避免 0x 被误清洗导致字节对齐错误
        text = re.sub(r"0[xX]([0-9A-Fa-f])", r"\1", text)
        pattern = r"[^0-9A-Fa-f\n]" if keep_newlines else r"[^0-9A-Fa-f]"
        return re.sub(pattern, "", text)

    @staticmethod
    def _reverse_4byte_groups(hex_str: str) -> str:
        """4字节一组做端序翻转（大端↔小端）。

        输入纯 hex 字符串，按每 8 个字符（4 字节）为一组，
        组内字节顺序反转。不足 4 字节的尾部保持原样。

        例：C9D50438 00000556 → 3804D5C9 56050000
        """
        result = []
        n = len(hex_str)
        i = 0
        while i < n:
            group = hex_str[i : i + 8]
            if len(group) == 8:
                # 字节序反转: 字节0字节1字节2字节3 → 字节3字节2字节1字节0
                result.append(group[6:8] + group[4:6] + group[2:4] + group[0:2])
            else:
                result.append(group)
            i += 8
        return "".join(result)

    # 新一代载波协议监控日志前缀标记与监控头长度
    # 监控日志格式: "<时间> <序号> -> 接收机 Has Get <N字节监控头> <协议报文>"
    # 实际报文从标记后的第 16 个字节（1-based）开始，即需要跳过 15 字节监控头
    CSG_MONITOR_PREFIX = "> 接收机 Has Get"
    CSG_MONITOR_HEADER_BYTES = 15  # 标记之后需跳过的监控头字节数

    def _strip_csg_monitor_prefix(self, text: str) -> str:
        """剥离新一代载波协议监控日志前缀（仅在协议8批量解析时调用）

        监控日志格式示例:
            15:49:51 254  -> 接收机 Has Get ED A5 00 00 02 EF 01 7E 4E 97 86 01 00 88 00 69 19 09 ...
                                                      ^^^^^^^^^^^^^^^ 15字节监控头 ^^^^^^^^^^^^^^^^
                                                                                      ^ 第16字节(69)开始为真实协议报文

        处理规则（逐行）:
          1. 仅保留含 "> 接收机 Has Get" 标记的行，其余行（时间戳、测试标记、
             纯文本日志、空行等）全部丢弃，避免被 _clean_hex_input 误清洗成伪帧
          2. 对保留的行：定位标记，取其后内容，跳过前 15 字节监控头，
             从第 16 字节开始保留作为协议报文

        注意：必须在 _clean_hex_input 之前调用，否则标记中的中文/箭头会被清洗掉，
        导致无法定位监控头边界。
        """
        import re

        prefix = self.CSG_MONITOR_PREFIX
        prefix_len = len(prefix)

        out_lines = []
        out_map = []
        for line_idx, line in enumerate(text.splitlines()):
            pos = line.find(prefix)
            if pos == -1:
                # 不含监控标记的行：直接丢弃（时间戳/测试标记/纯文本日志等）
                continue
            # 标记之后的内容
            after = line[pos + prefix_len :]
            # 提取连续 hex token（容忍空格/多空格/非hex分隔符）
            tokens = re.findall(r"[0-9A-Fa-f]{1,2}", after)
            # 跳过 15 字节监控头，从第 16 字节开始保留协议报文
            payload_tokens = tokens[self.CSG_MONITOR_HEADER_BYTES :]
            if payload_tokens:
                out_lines.append(" ".join(payload_tokens))
                out_map.append(line_idx)
        self._last_strip_line_map = out_map
        return "\n".join(out_lines)

    def _strip_gw_new_gen_prefix(
        self, text: str, parse_level: str | None = None
    ) -> str:
        """剥离国网新一代(索引10)/HDC 1.0(索引11)双模协议日志前缀

        日志格式示例:
            Line 339: 260718-111145-349: B1D[3] mrd:ar[75]:110300000132F303420D2305683D0043...

        处理规则:
          1. 以 fc_payload_data := ' 开头，' 后跟空白或 } 结尾为一个完整帧
          2. 帧可能跨多行，中间所有 hex 拼接为一个完整帧
          3. 无引号包裹的行：取最后一个冒号后的 hex
          4. 清理非 hex 字符，若解析级别为 app 则扫描应用层端口
             (0x11/0x12/0x1A，见 `_gw_app_port_prefixes`) 定位应用层起始
          5. 过短（<4 hex字符）的帧丢弃

        解析级别来源（**不要**改回硬编码 `_gw_parse_level`）:
          `parse_level=None`（默认）时取 `_current_parse_params()` 的级别——协议10 用
          `_gw_parse_level`、协议11 用 `_hdc10_parse_level`。这两个属性相互独立
          （见 `_on_gw_parse_level_changed`），但界面共用同一个下拉框：早期版本在这里
          硬读 `_gw_parse_level`，于是协议11 批量解析被**协议10 的残留级别**（如 app）
          过滤成空，弹「预处理后未保留有效报文内容！」（AGENTS §8 陷阱 43）。

        注意：必须在 _clean_hex_input 之前调用，否则前缀中的数字会被误当作 hex 数据。
        """
        import re

        if parse_level is None:
            parse_level = self._current_parse_params().get("parse_level") or "auto"
        # app 级别的帧起始判据：应用层端口集合（按当前协议取自解析器端口表）
        app_prefixes = _gw_app_port_prefixes(getattr(self, "current_protocol", 10))
        out_lines = []
        out_map = []

        # ── 状态机：提取所有完整 hex 帧 ──
        hex_frames = []
        in_payload = False  # 是否在引号包裹的 payload 内
        payload_hex = ""  # 当前 payload 累积的 hex
        payload_start_idx = -1  # 跨行 payload 的起始行号

        for line_idx, line in enumerate(text.splitlines()):
            line_s = line.strip()
            if not line_s:
                continue

            # ── 在 payload 引号内：收集 hex 直到闭合引号 ──
            if in_payload:
                # 查找闭合引号: ' 后跟空白或 } (如 '0 3", 'O }", 'O}")
                close_match = re.search(r"'\s*[}]?", line_s)
                if close_match:
                    before_close = line_s[: close_match.start()]
                    payload_hex += re.sub(r"[^0-9A-Fa-f]", "", before_close).upper()
                    in_payload = False
                    if len(payload_hex) >= 4:
                        hex_frames.append((payload_hex, payload_start_idx))
                    payload_hex = ""
                else:
                    # 无闭合引号：整行都是 hex 数据（可能还有下一行）
                    payload_hex += re.sub(r"[^0-9A-Fa-f]", "", line_s).upper()
                continue

            # ── 检测 payload 起始：fc_payload_data := ' 或类似的引号开启 ──
            payload_start = re.search(r"fc_payload_data\s*:=\s*['\"]", line_s)
            if payload_start:
                after_quote = line_s[payload_start.end() :]
                # 同行内是否有闭合引号？
                close_match = re.search(r"'\s*[}]?", after_quote)
                if close_match:
                    hex_clean = re.sub(
                        r"[^0-9A-Fa-f]", "", after_quote[: close_match.start()]
                    ).upper()
                    if len(hex_clean) >= 4:
                        hex_frames.append((hex_clean, line_idx))
                else:
                    # 引号跨行
                    payload_hex = re.sub(r"[^0-9A-Fa-f]", "", after_quote).upper()
                    in_payload = True
                    payload_start_idx = line_idx
                continue

            # ── 普通行：取最后一个冒号后的 hex ──
            last_colon = line_s.rfind(":")
            hex_part = line_s[last_colon + 1 :].strip() if last_colon >= 0 else line_s
            # 若行内含引号（闭合引号残留），只取引号前
            quote_pos = -1
            for q in ("'", '"'):
                p = hex_part.find(q)
                if p >= 0 and (quote_pos < 0 or p < quote_pos):
                    quote_pos = p
            if quote_pos >= 0:
                hex_clean = re.sub(r"[^0-9A-Fa-f]", "", hex_part[:quote_pos]).upper()
            else:
                hex_clean = re.sub(r"[^0-9A-Fa-f]", "", hex_part).upper()
            if len(hex_clean) >= 4:
                hex_frames.append((hex_clean, line_idx))

        # 处理尾部残留（引号未闭合的不完整帧）
        if payload_hex and len(payload_hex) >= 4:
            hex_frames.append((payload_hex, payload_start_idx))

        # ── 按解析级别定位帧起始 ──
        for hex_clean, src_idx in hex_frames:
            if parse_level == "app":
                found = False
                i = 0
                while i < len(hex_clean) - 1:
                    if hex_clean[i : i + 2] in app_prefixes and len(hex_clean) - i >= 8:
                        hex_clean = hex_clean[i:]
                        found = True
                        break
                    i += 2
                if not found:
                    continue
            out_lines.append(hex_clean)
            out_map.append(src_idx)

        self._last_strip_line_map = out_map
        return "\n".join(out_lines)

    def _strip_csg_new_gen_frame_prefix(
        self, text: str, parse_level: str = "auto"
    ) -> str:
        """南网新一代通感一体化批量解析预处理（在 _clean_hex_input 之前调用）

        主动定位帧起始并剔除非报文内容，逻辑对齐国网新一代 _strip_gw_new_gen_prefix，
        但依据南网帧结构与物理块头(4字节)特征：

        - 若文本含监控日志标记 ``> 接收机 Has Get``：沿用 _strip_csg_monitor_prefix，
          仅保留监控行并剥离 15 字节监控头（保留既有已测行为）。
        - 否则按行处理：取最后一个冒号后的 hex（兼容 "Line XXX: ...: hex" 日志），
          清洗为纯 hex，再按解析级别定位帧起始：
            * fc_pb / fc_only / fc_efc / auto  → 扫描 FC 起始特征字节
              (bit3=接入指示=1, bits0-2=定界符类型∈{0,1,2,3}，即低4位∈{0x8,0x9,0xA,0xB})
              如典型 SOF 起始 0x09 / 0x89 ...
            * pb_only  → 输入即物理块本身，直接保留整行（无FC签名）
            * app      → 扫描端口 0x11 定位应用层报文起始
          过短的行（<4 hex字符）直接丢弃。
        - TCP 包装报文：检测 ``EDA5`` 固定前缀，从 ``ED`` 偏移 15 字节（30 hex字符）定位 FC 起始，
          剥离 15 字节 TCP 包装头后即为 FC+PB 帧数据（适用于除 pb_only 外的所有级别）。
        """
        import re

        # 监控日志格式：沿用已有逻辑（仅保留监控行，剥离监控头）
        if self.CSG_MONITOR_PREFIX in text:
            return self._strip_csg_monitor_prefix(text)

        # 测试装置工装板/功能驱动板控制帧的判据来自解析器（单一来源，见 csg_new_gen_parser）
        from csg_new_gen_parser import is_test_device_control_frame

        out_lines = []
        out_map = []

        # ── 状态机：提取所有完整 hex 帧（支持跨行引号包裹） ──
        hex_frames = []
        in_payload = False  # 是否在引号包裹的 payload 内
        payload_hex = ""  # 当前 payload 累积的 hex
        payload_start_idx = -1  # 跨行 payload 的起始行号

        for line_idx, line in enumerate(text.splitlines()):
            line_s = line.strip()
            if not line_s:
                continue

            # ── 在 payload 引号内：收集 hex 直到闭合引号 ──
            if in_payload:
                close_match = re.search(r"'\s*[}]?", line_s)
                if close_match:
                    before_close = line_s[: close_match.start()]
                    payload_hex += re.sub(r"[^0-9A-Fa-f]", "", before_close).upper()
                    in_payload = False
                    if len(payload_hex) >= 4:
                        hex_frames.append((payload_hex, payload_start_idx))
                    payload_hex = ""
                else:
                    payload_hex += re.sub(r"[^0-9A-Fa-f]", "", line_s).upper()
                continue

            # ── 检测 payload 起始：fc_payload_data := ' ──
            payload_start = re.search(r"fc_payload_data\s*:=\s*['\"]", line_s)
            if payload_start:
                after_quote = line_s[payload_start.end() :]
                close_match = re.search(r"'\s*[}]?", after_quote)
                if close_match:
                    hex_clean = re.sub(
                        r"[^0-9A-Fa-f]", "", after_quote[: close_match.start()]
                    ).upper()
                    if len(hex_clean) >= 4:
                        hex_frames.append((hex_clean, line_idx))
                else:
                    payload_hex = re.sub(r"[^0-9A-Fa-f]", "", after_quote).upper()
                    in_payload = True
                    payload_start_idx = line_idx
                continue

            # ── 普通行：取最后一个冒号后的 hex ──
            last_colon = line_s.rfind(":")
            hex_part = line_s[last_colon + 1 :].strip() if last_colon >= 0 else line_s
            quote_pos = -1
            for q in ("'", '"'):
                p = hex_part.find(q)
                if p >= 0 and (quote_pos < 0 or p < quote_pos):
                    quote_pos = p
            if quote_pos >= 0:
                hex_clean = re.sub(r"[^0-9A-Fa-f]", "", hex_part[:quote_pos]).upper()
            else:
                hex_clean = re.sub(r"[^0-9A-Fa-f]", "", hex_part).upper()
            if len(hex_clean) >= 4:
                hex_frames.append((hex_clean, line_idx))

        if payload_hex and len(payload_hex) >= 4:
            hex_frames.append((payload_hex, payload_start_idx))

        # ── 按解析级别定位帧起始 ──
        for hex_clean, src_idx in hex_frames:
            # 检测 TCP 包装前缀 EDA5：从 ED 偏移 15 字节(30 hex)定位 FC 起始
            if parse_level != "pb_only" and hex_clean.startswith("EDA5"):
                if len(hex_clean) >= 62:
                    hex_clean = hex_clean[30:]
                    out_lines.append(hex_clean)
                    out_map.append(src_idx)
                continue

            if parse_level in ("pb_only", "mac_only"):
                pass  # 直接保留
            elif parse_level == "app":
                found = False
                i = 0
                while i + 32 <= len(hex_clean):
                    if hex_clean[i : i + 2] == "11" and len(hex_clean) - i >= 8:
                        hex_clean = hex_clean[i:]
                        found = True
                        break
                    i += 2
                if not found:
                    continue
            else:
                if hex_clean.startswith("ED"):
                    pass  # ED 包装帧直接保留
                elif is_test_device_control_frame(hex_clean):
                    # 台体工装板/功能驱动板控制帧（FE×n + 05 …，功能驱动板以 AA 0D 0A 结尾）：
                    # 不是载波 FC/PB 业务帧、没有 FC 起始签名，但它**是**能被解析器完整识别的帧
                    # （parse_to_table 优先判它）⇒ 必须原样保留。否则会被下面的 FC 扫描判定为
                    # 「无有效起始」整行丢弃 —— 现场表现是同一帧单帧解析正常、批量却报
                    # 「预处理后未保留有效报文内容！」（1.23.87 修）。
                    pass
                else:
                    found = False
                    i = 0
                    while i + 32 <= len(hex_clean):
                        byte_val = int(hex_clean[i : i + 2], 16)
                        low = byte_val & 0x0F
                        if low in (0x08, 0x09, 0x0A, 0x0B):
                            hex_clean = hex_clean[i:]
                            found = True
                            break
                        i += 2
                    if not found:
                        continue
            out_lines.append(hex_clean)
            out_map.append(src_idx)

        self._last_strip_line_map = out_map
        return "\n".join(out_lines)

    # ── PLC2.0 收发机监控包装头(ED..EE)解析 ──
    # 常量定义（与 monitor_widget 保持一致）
    _PLC2_CTRL1_NAMES = {0x00: "数据报文", 0x01: "控制报文"}
    _PLC2_CTRL2_DATA_NAMES = {
        0x01: "FC数据",
        0x02: "FC+Payload数据",
        0x03: "Payload数据",
        0x04: "发送完成",
        0x05: "选择确认帧发送完成",
        0x06: "RF和HPLC同时发送FC+Payload",
        0x07: "FC+Payload数据",
        0x08: "UL-OFDMA帧(DL-OFDMA的SACK帧)",
    }
    _PLC2_CHANNEL_NAMES = {
        0x01: "HPLC",
        0x02: "RF",
        0x03: "HPLC+RF",
        0x20: "PLC2.0 OFDMA",
    }

    def _plc2_channel_name(self, ch: int) -> str:
        if ch in self._PLC2_CHANNEL_NAMES:
            return self._PLC2_CHANNEL_NAMES[ch]
        if 0x10 <= ch <= 0x1C:
            return f"PLC2.0 MIMO(0x{ch:02X})"
        return f"保留(0x{ch:02X})"

    def _ed_wrapper_mode(self) -> str:
        """ED 包装头格式选择：auto=自动识别 / plc2=PLC2.0 台体 / gx=广西台体"""
        combo = getattr(self, "ed_wrapper_combo", None)
        if combo is not None:
            return combo.currentData() or "auto"
        return "auto"

    def _detect_ed_wrapper(self, frame_bytes: bytes) -> str:
        """自动识别 ED 包装头格式：gx(8B 公共头) / plc2(9B 公共头)

        打分算法与解析器共用（csg_new_gen_parser.detect_ed_wrapper）：
        逐候选格式打分（plc2 优先平局），无正分回退当前下拉手动值。
        单源化原因：Web 版无下拉，需要同一份判别逻辑；避免第三份实现。
        """
        from csg_new_gen_parser import detect_ed_wrapper

        mode = self._ed_wrapper_mode()
        fallback = "plc2" if mode == "auto" else mode
        return detect_ed_wrapper(frame_bytes, fallback=fallback)

    def _ed_wrapper_for_frame(self, frame_bytes: bytes) -> str:
        """单帧 ED 包装格式：下拉 auto 时逐帧自动识别，否则手动指定

        判别实现单源在 `batch_parse_worker.resolve_ed_wrapper`（后台批量解析线程
        必须用同一份口径，但不能读下拉控件）。
        """
        return resolve_ed_wrapper(frame_bytes, self._ed_wrapper_mode())

    @staticmethod
    def _ed_business_is_fc(business: bytes) -> bool:
        """ED 解包后的业务帧是否像合法 FC：定界符类型 DT = ``business[0] & 0x07`` ∈ 0~3。

        用于协议10/11「无 ED监控协议 复选框」时的**自动识别防误剥离**：首字节恰为
        0xED 的物理块/MAC 帧不应被当成监控包装帧。真 FC 的 DT 恒取 0~3（0xED 的
        低 3 位=5 非法），故本判据不会误拒合法业务帧。
        """
        return bool(business) and (business[0] & 0x07) <= 3

    def _parse_ed_monitor_header(
        self, frame_bytes: bytes, wrapper: str = None, protocol_index: int = None
    ):
        """解析 ED..EE 监控包装头（PLC2.0 / 广西台体两种公共头布局）

        包结构: ED(1)+帧长(2,LE)+控制域1(1)+控制域2(1)+EF(1)+数据域(变长)+CS(1)+EE(1)
        数据报文(ctrl1=0x00) ctrl2=0x01/0x02/0x03 的数据域公共头(9字节):
          物理信道(1)+时间戳(4,LE)+物理块个数(1)+保留/CRC(1)+单个物理块长度(2,LE)

        Args:
            wrapper: "plc2"/"gx"；None 或非法值 → 取当前下拉（auto 时逐帧打分识别）
                —— 默认不再是硬编码 plc2，避免漏传的调用点把 gx 帧按 9B 头错位解析
            protocol_index: 决定字段**解释语言**。协议9→PLC2.0/广西台体；
                协议10/11→国网HDC（gx 布局与 HDC 同构，不得再写广西台体）。
                None → 用 self.current_protocol

        Returns:
            (meta_rows, business_bytes, business_offset) 成功时返回前置行列表、业务字节、
                业务字节在原始帧中的偏移量
            (None, None, None) 帧不是有效的 ED 包装格式
        """
        if wrapper not in ("plc2", "gx"):
            wrapper = self._ed_wrapper_for_frame(frame_bytes)
        if protocol_index is None:
            protocol_index = getattr(self, "current_protocol", 9)
        from batch_core import ed_wrapper_display
        ed_lab = ed_wrapper_display(protocol_index, wrapper)
        n = len(frame_bytes)
        if n < 8 or frame_bytes[0] != 0xED:
            return None, None, None

        frame_len = frame_bytes[1] | (frame_bytes[2] << 8)  # = 数据域长度 + 4
        if frame_len < 4 or frame_len > 4096:
            return None, None, None
        total = frame_len + 4  # ED(1)+帧长(2)+[控制域1..CS=帧长]+EE(1)
        if total > n:
            return None, None, None
        # 强定界校验
        if frame_bytes[5] != 0xEF or frame_bytes[total - 1] != 0xEE:
            return None, None, None

        ctrl1 = frame_bytes[3]
        ctrl2 = frame_bytes[4]
        data_len = frame_len - 4
        data_start = 6
        data = frame_bytes[data_start : data_start + data_len]
        cs_offset = data_start + data_len
        cs = frame_bytes[cs_offset]
        ee_offset = total - 1
        calc_cs = sum(frame_bytes[:cs_offset]) & 0xFF

        ctrl1_name = self._PLC2_CTRL1_NAMES.get(ctrl1, f"保留(0x{ctrl1:02X})")
        ctrl2_name = (self._PLC2_CTRL2_DATA_NAMES if ctrl1 == 0x00 else {}).get(
            ctrl2, f"保留(0x{ctrl2:02X})"
        )
        cs_txt = (
            "✓ 正确" if cs == calc_cs else ("保留(0xFF)" if cs == 0xFF else "✗ 错误")
        )

        rows = [
            (
                ed_lab["title"],
                "",
                "",
                ed_lab["header_desc"],
                None,
                None,
            ),
            (
                "起始符(ED)",
                f"0x{frame_bytes[0]:02X}",
                "ED",
                ed_lab["start_comment"],
                0,
                0,
            ),
            (
                "帧长",
                f"{frame_bytes[1]:02X} {frame_bytes[2]:02X}",
                f"{frame_len} 字节",
                "控制域1+控制域2+EF+数据域+CS(小端)",
                1,
                2,
            ),
            (
                "控制域1",
                f"0x{ctrl1:02X}",
                ctrl1_name,
                "0x00-数据报文 0x01-控制报文",
                3,
                3,
            ),
            ("控制域2", f"0x{ctrl2:02X}", ctrl2_name, "报文子类型", 4, 4),
            (
                "数据域起始符(EF)",
                f"0x{frame_bytes[5]:02X}",
                "EF",
                "数据域起始标识",
                5,
                5,
            ),
            (
                "数据域长度",
                str(data_len),
                f"{data_len} 字节",
                f"字节 {data_start}~{cs_offset - 1}",
                data_start,
                cs_offset - 1,
            ),
        ]

        business = b""
        business_offset = data_start  # 默认偏移
        # 数据报文 0x01/0x02/0x03：解析公共头
        # PLC2.0=9字节: 物理信道(1)+时间戳(4)+物理块个数(1)+PayloadCRC(1)+物理块长度(2)
        # 广西台体=8字节: 时间戳(4)+物理信道(1)+物理块个数(1)+物理块长度(2)
        hdr_len = 8 if wrapper == "gx" else 9
        if ctrl1 == 0x00 and ctrl2 in (0x01, 0x02, 0x03) and data_len >= hdr_len:
            if wrapper == "gx":
                ts = int.from_bytes(data[0:4], "little")
                ch = data[4]
                pb_cnt = data[5]
                pb_len = int.from_bytes(data[6:8], "little")
                business = data[8:]
                business_offset = data_start + 8  # 业务帧从数据域第9字节开始
            else:
                ch = data[0]
                ts = int.from_bytes(data[1:5], "little")
                pb_cnt = data[5]
                flag6 = data[6]
                pb_len = int.from_bytes(data[7:9], "little")
                business = data[9:]
                business_offset = data_start + 9  # 业务帧从数据域第10字节开始
            crc_txt = (
                "错误"
                if (wrapper != "gx" and ctrl2 == 0x02 and flag6 == 1)
                else "正确/保留"
            )
            rows += [
                (
                    "物理信道",
                    f"0x{ch:02X}",
                    self._plc2_channel_name(ch),
                    "0x01-HPLC 0x02-RF 0x03-HPLC+RF 0x10~0x1C-MIMO 0x20-OFDMA",
                    data_start + (4 if wrapper == "gx" else 0),
                    data_start + (4 if wrapper == "gx" else 0),
                ),
                (
                    "时间戳",
                    f"0x{ts:08X}",
                    str(ts),
                    "HW→PC 接收开始时间(小端)",
                    data_start + (0 if wrapper == "gx" else 1),
                    data_start + (3 if wrapper == "gx" else 4),
                ),
                (
                    "物理块个数",
                    str(pb_cnt),
                    str(pb_cnt),
                    None,
                    data_start + 5,
                    data_start + 5,
                ),
            ]
            if wrapper != "gx":
                rows.append(
                    (
                        "Payload CRC",
                        f"0x{flag6:02X}",
                        crc_txt,
                        "ctrl2=0x02时: 0-正确 1-错误；其余保留",
                        data_start + 6,
                        data_start + 6,
                    )
                )
            rows.append(
                (
                    "单个物理块长度",
                    str(pb_len),
                    f"{pb_len} 字节(小端)",
                    None,
                    data_start + (6 if wrapper == "gx" else 7),
                    data_start + (7 if wrapper == "gx" else 8),
                )
            )
        else:
            business = data

        rows += [
            (
                "校验(CS)",
                f"0x{cs:02X}",
                cs_txt,
                "ED..数据域末所有字节求和取低8bit",
                cs_offset,
                cs_offset,
            ),
            (
                "结束符(EE)",
                f"0x{frame_bytes[ee_offset]:02X}",
                "EE",
                ed_lab["end_comment"],
                ee_offset,
                ee_offset,
            ),
            (
                "── 业务帧 ──",
                "",
                "",
                "以下为 ED 数据域解析结果",
                business_offset,
                cs_offset - 1,
            ),
        ]

        return rows, business, business_offset

    def _on_virtual_meter_send_to_parser(self, hex_text: str):
        """虚拟表 tab 请求：把响应帧 hex 填入单帧解析输入并解析回读"""
        self.single_input.setPlainText(hex_text)
        # 切到单帧解析页（第一个 tab）
        self.tab_widget.setCurrentIndex(0)
        self.parse_single()

    def parse_single(self):
        """解析单帧报文"""
        input_text = self.single_input.toPlainText().strip()
        if not input_text:
            QMessageBox.warning(self, "警告", "请输入报文内容！")
            return

        # 清理输入（支持空格、逗号、换行等分隔符）
        clean_input = self._clean_hex_input(input_text)
        clean_input = clean_input.strip()

        # 能力开关来自注册表：协议9/10/11 共用 ED 勾选、4字节反转、字节剔除
        proto_spec = protocol_registry.get_protocol(self.current_protocol)
        has_ed_cap = getattr(proto_spec, "has_ed_monitor", False)
        has_rev_cap = getattr(proto_spec, "has_reverse_4byte", False)

        # 4字节反转（注册表 has_reverse_4byte + 勾选时）
        if (
            has_rev_cap
            and hasattr(self, "csg_reverse_4byte_chk")
            and self.csg_reverse_4byte_chk.isChecked()
            and clean_input
        ):
            clean_input = self._reverse_4byte_groups(clean_input)

        # 验证输入
        if not all(c in "0123456789abcdefABCDEF" for c in clean_input):
            QMessageBox.critical(
                self, "错误", "输入包含非法字符，请只输入十六进制字符（0-9, A-F）！"
            )
            return

        if len(clean_input) % 2 != 0:
            QMessageBox.critical(
                self, "错误", "输入长度为奇数，十六进制字符串必须是偶数长度！"
            )
            return

        try:
            # 转换为字节
            frame_bytes = bytes.fromhex(clean_input)

            # 格式化为空格分隔的 hex，方便高亮
            hex_display = " ".join(f"{b:02X}" for b in frame_bytes)
            self.single_input.setPlainText(hex_display)

            # 字节剔除（协议9/10/11，解析前执行，支持缓存避免重复剔除）
            if has_ed_cap:
                strip_head = self.csg_strip_head_spin.value()
                strip_tail = self.csg_strip_tail_spin.value()
                current_hex = clean_input.lower()
                # 如果当前输入与上次剔除后的结果相同，说明已经剔除过，跳过
                if (
                    strip_head > 0 or strip_tail > 0
                ) and current_hex != self._csg_last_stripped_hex:
                    total = len(frame_bytes)
                    tail_end = total - strip_tail if strip_tail > 0 else total
                    if strip_head >= tail_end:
                        QMessageBox.critical(
                            self,
                            "错误",
                            f"剔除字节数过多（前{strip_head}+尾{strip_tail}={strip_head + strip_tail}），"
                            f"报文仅{total}字节！",
                        )
                        return
                    frame_bytes = frame_bytes[strip_head:tail_end]
                    hex_display = " ".join(f"{b:02X}" for b in frame_bytes)
                    self.single_input.setPlainText(hex_display)
                    # 缓存剔除后的hex（无空格小写），供下次比对
                    self._csg_last_stripped_hex = "".join(
                        f"{b:02x}" for b in frame_bytes
                    )

            # ED 监控协议头解析
            # 协议9：由「ED监控协议」勾选项显式启用
            # 协议10/11：勾选后同协议9；未勾选时仍自动识别（首字节 0xED 不可能是
            #   合法 HDC FC——定界符类型 DT 取 0~3，0xED 低 3 位=5）
            full_frame_bytes = (
                frame_bytes  # 保存完整帧（用于高亮定位和 current_result）
            )
            ed_meta_rows = None
            ed_business_offset = 0
            ed_checked = has_ed_cap and self.ed_monitor_chk.isChecked()
            ed_mode = (
                has_ed_cap
                and len(frame_bytes) >= 1
                and frame_bytes[0] == 0xED
                and (
                    ed_checked
                    or self.current_protocol in (10, 11)
                )
            )
            if ed_mode:
                ed_rows, business, ed_business_offset = self._parse_ed_monitor_header(
                    frame_bytes, wrapper=self._ed_wrapper_for_frame(frame_bytes)
                )
                if ed_rows is None or business is None:
                    if ed_checked:
                        declared = (
                            (frame_bytes[1] | (frame_bytes[2] << 8)) + 4
                            if len(frame_bytes) >= 3
                            else 0
                        )
                        msg = (
                            "ED 监控帧解析失败：报文不完整或格式错误。\n"
                            "已勾选「ED监控协议」，首字节 ED 不能作为业务帧起始符解析。\n"
                            "请检查报文是否被截断（帧长字段声明整包应为 %d 字节，实际 %d 字节），"
                            "或缺少 EF 数据域起始符 / EE 结束符。"
                            % (declared, len(frame_bytes))
                        )
                        QMessageBox.critical(self, "ED 监控帧错误", msg)
                        return
                    # 10/11 未勾选时的自动识别：结构不符 → 不剥离
                    # （可能是首字节恰为 0xED 的物理块/MAC 帧，交由解析器按原样处理）
                    ed_rows = None
                elif (
                    self.current_protocol in (10, 11)
                    and not ed_checked
                    and not self._ed_business_is_fc(business)
                ):
                    # 自动识别再要求业务帧确为合法 FC，防误剥离；
                    # 用户已勾选 ED 时按其意图解包，不再用 FC 判据否决
                    ed_rows = None
                if ed_rows is not None:
                    ed_meta_rows = ed_rows
                    frame_bytes = business  # 后续解析使用业务载荷
                    # 不替换 hex_display，保持输入框显示完整帧

            # 使用当前选中的解析器
            current_parser = self._get_current_parser()
            tolerant = (
                hasattr(self, "verify_frame_chk")
                and not self.verify_frame_chk.isChecked()
                and int(self.current_protocol) in TOLERANT_PARSE_PROTOCOLS
            )
            table_data = (
                current_parser.parse_to_table(frame_bytes, verify=False)
                if tolerant
                else current_parser.parse_to_table(frame_bytes)
            )
            # ED 监控头前置 + 业务行偏移修正
            if ed_meta_rows:
                # 业务行的 byte_start/byte_end 需要加上 ED 头偏移
                shifted_table = []
                for row in table_data:
                    if len(row) >= 6 and row[4] is not None and row[5] is not None:
                        shifted_row = (
                            row[0],
                            row[1],
                            row[2],
                            row[3],
                            row[4] + ed_business_offset,
                            row[5] + ed_business_offset,
                        )
                        # 处理可能的第 7 个元素 (is_child)
                        if len(row) > 6:
                            shifted_row = shifted_row + (row[6],)
                        shifted_table.append(shifted_row)
                    else:
                        shifted_table.append(row)
                table_data = ed_meta_rows + shifted_table
            self._populate_table_from_data(table_data)

            # 保存当前结果（使用完整帧，确保高亮和双击提取正确）
            self.current_result = full_frame_bytes
            self._last_parsed_hex = hex_display

        except Exception as e:
            QMessageBox.critical(self, "解析错误", f"解析失败：{str(e)}")

    def verify_single(self):
        """校验单帧报文的协议一致性"""
        input_text = self.single_input.toPlainText().strip()
        if not input_text:
            QMessageBox.warning(self, "警告", "请输入报文内容！")
            return

        # 清理输入（支持空格、逗号、换行等分隔符）
        clean_input = self._clean_hex_input(input_text)
        clean_input = clean_input.strip()

        # 验证输入
        if not all(c in "0123456789abcdefABCDEF" for c in clean_input):
            QMessageBox.critical(
                self, "错误", "输入包含非法字符，请只输入十六进制字符（0-9, A-F）！"
            )
            return

        if len(clean_input) % 2 != 0:
            QMessageBox.critical(
                self, "错误", "输入长度为奇数，十六进制字符串必须是偶数长度！"
            )
            return

        try:
            frame_bytes = bytes.fromhex(clean_input)

            # 校验器由 protocol_registry 按索引懒加载构造（与快捷小窗共用）
            validators = protocol_registry.build_validator_map()

            validator = validators.get(self.current_protocol)
            if validator:
                result = validator.verify(frame_bytes)
                self._display_verify_result(result)
            else:
                self.verify_label.setText("当前协议不支持校验")

        except Exception as e:
            QMessageBox.critical(self, "校验错误", f"校验失败：{str(e)}")

    def _display_verify_result(self, result):
        """显示校验结果"""
        from validator.base import CheckLevel

        lines = []
        lines.append(f"协议: {result.protocol}")
        lines.append(f"整体结果: {'✅ 通过' if result.valid else '❌ 失败'}")
        lines.append("")

        for check in result.checks:
            icon = (
                "✅"
                if check.level == CheckLevel.PASS
                else "❌"
                if check.level == CheckLevel.FAIL
                else "⚠️"
            )
            lines.append(f"{icon} {check.name}: {check.message}")

        if result.warnings:
            lines.append("")
            lines.append("⚠️ 警告:")
            for w in result.warnings:
                lines.append(f"  - {w}")

        if result.errors:
            lines.append("")
            lines.append("❌ 错误:")
            for e in result.errors:
                lines.append(f"  - {e}")

        self.verify_label.setText("\n".join(lines))

        # 设置颜色
        if result.valid:
            self.verify_group.setStyleSheet("QGroupBox { border: 2px solid #4CAF50; }")
        else:
            self.verify_group.setStyleSheet("QGroupBox { border: 2px solid #f44336; }")

    def _add_parsed_to_test_plan(self):
        """将当前解析的帧添加到测试方案"""
        input_text = self.single_input.toPlainText().strip()
        if not input_text:
            QMessageBox.warning(self, "警告", "请先解析报文！")
            return

        # 清理 HEX（支持空格、逗号、换行等分隔符）
        clean_hex = self._clean_hex_input(input_text)
        clean_hex = clean_hex.strip()

        if not clean_hex:
            QMessageBox.warning(self, "警告", "请输入报文内容！")
            return

        # 根据协议生成名称
        protocol_names = {
            0: "南网",
            1: "PLC RF",
            2: "HDLC",
            3: "Wrapper",
            4: "APDU",
            5: "DLT645",
            6: "国网",
            7: "698.45",
        }
        protocol_name = protocol_names.get(self.current_protocol, "未知")
        name = f"{protocol_name}帧-{len(self.test_plan_tab._items) + 1}"

        # 添加到测试方案
        self.test_plan_tab.add_item(name, clean_hex)
        QMessageBox.information(self, "成功", f"已添加到测试方案: {name}")

    def _get_frame_bytes_for_fill(self):
        """获取当前输入框的帧字节，返回 (frame_bytes, hex_str) 或 None"""
        input_text = self.single_input.toPlainText().strip()
        if not input_text:
            QMessageBox.warning(self, "警告", "请先输入报文内容！")
            return None
        clean_input = self._clean_hex_input(input_text).strip()
        if not all(c in "0123456789abcdefABCDEF" for c in clean_input):
            QMessageBox.critical(self, "错误", "输入包含非法字符！")
            return None
        if len(clean_input) % 2 != 0:
            QMessageBox.critical(self, "错误", "输入长度必须为偶数！")
            return None
        return bytes.fromhex(clean_input), clean_input.upper()

    def _update_input_hex(self, frame_bytes: bytes):
        """将更新后的帧字节写回输入框"""
        hex_display = " ".join(f"{b:02X}" for b in frame_bytes)
        self.single_input.setPlainText(hex_display)

    def _fill_crc24(self):
        """填充 CRC-24 校验位（FC FCS + eFC CRC + 逐物理块 PBCS）"""
        result = self._get_frame_bytes_for_fill()
        if result is None:
            return
        frame_bytes, hex_str = result
        frame_len = len(frame_bytes)

        if frame_len < 16:
            QMessageBox.warning(self, "警告", "帧长度不足 16 字节，无法填充 FC FCS！")
            return

        from csg_new_gen_parser import _crc24_func

        modified = bytearray(frame_bytes)
        filled = []

        # ── FC FCS: 字节0-12的CRC-24，写入字节13-15（小端序）──
        fc_crc = _crc24_func(bytes(modified[0:13]))
        modified[13] = fc_crc & 0xFF
        modified[14] = (fc_crc >> 8) & 0xFF
        modified[15] = (fc_crc >> 16) & 0xFF
        filled.append(f"FC FCS=0x{fc_crc:06X}(字节13-15)")

        # ── eFC CRC / 逐物理块 PBCS：**仅协议9（南网新一代）适用** ──
        # eFC(扩展帧控制) 与「逐物理块 PBCS」都定义在 南网新一代 的 SOF MPDU
        # 布局下。协议10（国网新一代）/协议11（HDC 1.0）的 FC(16B) 之后**直接
        # 就是物理块**，byte16 即 PBH——按协议9 的偏移回填会把 CRC 写进 MAC 帧头，
        # 静默改坏业务字段（实测：协议11 帧的「组网序列号」由 0x01 被改成 0xE1）。
        if self.current_protocol != 9:
            filled.append(
                f"eFC/PBCS: 未填充（协议{self.current_protocol} 的 FC 之后直接是物理块，"
                "无此布局；eFC 与逐物理块 PBCS 仅协议9 南网新一代适用）"
            )
        else:
            # ── eFC CRC: 字节16-28的CRC-24，写入字节29-31（小端序）──
            # 判断是否为 SOF 帧且 OFDMA 需要 eFC
            if frame_len >= 32:
                # 检查定界符类型（字节0 bit0-2）
                delimiter_type = modified[0] & 0x07
                if delimiter_type == 1:  # SOF帧
                    # 检查ISAC帧的multi_site位 (byte19 bit0)
                    if modified[19] & 0x01:  # multi_site=1
                        # OFDMA type (byte19 bit1-2): type1不携带eFC
                        ofdma_type = (modified[19] >> 1) & 0x03
                        if ofdma_type != 1:
                            efc_crc = _crc24_func(bytes(modified[16:29]))
                            modified[29] = efc_crc & 0xFF
                            modified[30] = (efc_crc >> 8) & 0xFF
                            modified[31] = (efc_crc >> 16) & 0xFF
                            filled.append(f"eFC CRC=0x{efc_crc:06X}(字节29-31)")

            # ── 物理块检查序列 PBCS：逐 PB 重算 CRC-24(PBH+体+保留) 小端写回 PB 尾 3 字节 ──
            # 支持多物理块一键填充（采集置零 00 00 00 的帧填充后校验即通过）
            from csg_new_gen_parser import CSGNewGenParser

            pbcs_fills = CSGNewGenParser().calc_pbcs_fills(bytes(modified))
            for pbcs_off, val, idx in pbcs_fills:
                modified[pbcs_off] = val & 0xFF
                modified[pbcs_off + 1] = (val >> 8) & 0xFF
                modified[pbcs_off + 2] = (val >> 16) & 0xFF
                filled.append(f"PBCS[{idx}]=0x{val:06X}(字节{pbcs_off}-{pbcs_off + 2})")
            if not pbcs_fills:
                filled.append("PBCS: 未填充（非SOF MPDU，或帧长与物理块布局不自洽）")

        self._update_input_hex(bytes(modified))
        QMessageBox.information(self, "成功", "已填充: " + "\n".join(filled))

    def _fill_crc32(self):
        """填充 CRC-32 校验位（MAC 帧完整性校验）"""
        result = self._get_frame_bytes_for_fill()
        if result is None:
            return
        frame_bytes, hex_str = result
        frame_len = len(frame_bytes)

        if frame_len < 20:
            QMessageBox.warning(self, "警告", "帧长度不足，无法填充 CRC-32！")
            return

        from csg_new_gen_parser import _crc32_func

        modified = bytearray(frame_bytes)

        # 确定 MAC 帧的起始位置
        # 检查是否为完整 MPDU（FC头 + PB + MAC帧）
        delimiter_type = modified[0] & 0x07
        if delimiter_type == 1 and frame_len >= 24:
            # SOF帧: FC=16字节, PB头=4字节, MAC帧从字节20开始
            mac_start = 20
            # MAC头大小: 短头12字节(byte20 bit0=1), 长头32字节(byte20 bit0=0)
            mac_header_size = 12 if (modified[20] & 0x01) else 32
            # MSDU 长度字段: MAC bytes 2-3 (全局偏移 mac_start+2)
            if mac_start + 4 <= frame_len:
                msdu_len = int.from_bytes(
                    modified[mac_start + 2 : mac_start + 4], "little"
                )
            else:
                msdu_len = frame_len - mac_start - mac_header_size - 4
            msdu_start = mac_start + mac_header_size
            msdu_end = msdu_start + msdu_len
            crc_pos = msdu_end  # CRC-32 写入位置
        else:
            # 非MPDU格式: 假设整个帧就是一个 MAC 帧，最后4字节是CRC-32
            mac_start = 0
            mac_header_size = 12 if (modified[0] & 0x01) else 32
            if mac_start + 4 <= frame_len:
                msdu_len = int.from_bytes(modified[2:4], "little")
            else:
                msdu_len = frame_len - mac_header_size - 4
            msdu_start = mac_start + mac_header_size
            msdu_end = msdu_start + msdu_len
            crc_pos = msdu_end

        # 确保 CRC 位置在帧内
        if crc_pos + 4 > frame_len:
            # 帧长度不够，将 CRC 放在帧末尾
            crc_pos = frame_len - 4
            msdu_end = crc_pos

        if msdu_end <= msdu_start:
            QMessageBox.warning(self, "警告", "MSDU 范围无效，无法计算 CRC-32！")
            return

        # 计算 CRC-32 (覆盖 MSDU 载荷，不包括 MAC 帧头)
        msdu_data = bytes(modified[msdu_start:msdu_end])
        crc_val = _crc32_func(msdu_data)

        # 写入 CRC-32 (小端序)
        modified[crc_pos] = crc_val & 0xFF
        modified[crc_pos + 1] = (crc_val >> 8) & 0xFF
        modified[crc_pos + 2] = (crc_val >> 16) & 0xFF
        modified[crc_pos + 3] = (crc_val >> 24) & 0xFF

        self._update_input_hex(bytes(modified))
        QMessageBox.information(
            self,
            "成功",
            f"已填充 CRC-32=0x{crc_val:08X}\n"
            f"计算范围: MSDU载荷(字节{msdu_start}-{msdu_end - 1}, {len(msdu_data)}字节)\n"
            f"写入位置: 字节{crc_pos}-{crc_pos + 3}",
        )

    def clear_single(self):
        """清空单帧解析输入和结果"""
        self.single_input.clear()
        self.result_table_widget.setRowCount(0)
        self.current_result = None
        self._byte_ranges = []
        self._last_table_data = []
        if hasattr(self, "result_tree_widget"):
            self.result_tree_widget.clear()
        # 清空校验结果
        if hasattr(self, "verify_label"):
            self.verify_label.setText("点击「校验报文」按钮进行协议一致性校验")
        if hasattr(self, "verify_group"):
            self.verify_group.setStyleSheet("")

    def _setup_table_copy_menu(self, table: QTableWidget):
        """为解析结果表格设置右键复制菜单和 Ctrl+C 快捷键"""
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(
            lambda pos, t=table: self._show_table_copy_menu(t, pos)
        )
        # Ctrl+C 快捷键
        shortcut = QShortcut(QKeySequence.Copy, table)
        shortcut.setContext(Qt.WidgetShortcut)
        shortcut.activated.connect(
            lambda t=table: self._copy_table_rows(t, all_rows=False)
        )

    def _show_table_copy_menu(self, table: QTableWidget, pos):
        """显示表格右键复制菜单"""
        menu = QMenu(table)
        has_selection = len(table.selectedItems()) > 0

        copy_sel = menu.addAction("复制选中行")
        copy_sel.setEnabled(has_selection)
        copy_sel.triggered.connect(lambda: self._copy_table_rows(table, all_rows=False))

        copy_all = menu.addAction("复制全部")
        copy_all.triggered.connect(lambda: self._copy_table_rows(table, all_rows=True))

        menu.exec(table.mapToGlobal(pos))

    def _copy_table_rows(self, table: QTableWidget, all_rows: bool = False):
        """将表格行复制到剪贴板（制表符分隔，含表头）"""
        col_count = table.columnCount()
        row_count = table.rowCount()

        # 收集需要复制的行号
        if all_rows:
            rows = list(range(row_count))
        else:
            selected = table.selectedIndexes()
            if not selected:
                # 无选中时退化为全部
                rows = list(range(row_count))
            else:
                row_set = sorted({idx.row() for idx in selected})
                rows = row_set

        if not rows:
            return

        # 表头
        headers = []
        for c in range(col_count):
            item = table.horizontalHeaderItem(c)
            headers.append(item.text() if item else "")
        lines = ["\t".join(headers)]

        # 数据行
        for r in rows:
            cells = []
            for c in range(col_count):
                item = table.item(r, c)
                cells.append(item.text() if item else "")
            lines.append("\t".join(cells))

        text = "\n".join(lines)
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(text)

    def _apply_chinese_menus_to_all_tabs(self):
        """为所有标签页中的文本输入控件设置中文右键菜单"""
        # 应用到主窗口及其所有子控件
        apply_chinese_context_menus(self)

        # 确保各个标签页中的控件也被处理
        if hasattr(self, "single_input"):
            setup_chinese_context_menu(self.single_input)
        if hasattr(self, "batch_input"):
            setup_chinese_context_menu(self.batch_input)
        if hasattr(self, "frame_gen_tab"):
            apply_chinese_context_menus(self.frame_gen_tab)
        if hasattr(self, "preset_tab"):
            apply_chinese_context_menus(self.preset_tab)

    def _setup_menu_bar(self):
        """创建菜单栏"""
        menubar = self.menuBar()

        # 右上角小图标：外观（太阳/月亮/跟随系统）+ 一键显示/隐藏「协议选择+串口配置」整栏
        self.appearance_btn = self._create_appearance_btn()
        self.topbar_toggle_btn = self._create_topbar_toggle_btn()
        corner = QWidget(menubar)
        corner_lay = QHBoxLayout(corner)
        corner_lay.setContentsMargins(0, 0, 6, 0)
        corner_lay.setSpacing(2)
        corner_lay.addWidget(self.appearance_btn)
        corner_lay.addWidget(self.topbar_toggle_btn)
        menubar.setCornerWidget(corner, Qt.Corner.TopRightCorner)

        # 配置菜单
        config_menu = menubar.addMenu("配置(&C)")
        config_action = config_menu.addAction("配置文件路径(&P)...")
        config_action.triggered.connect(self._show_config_dialog)
        theme_action = config_menu.addAction("主题与字体(&T)...")
        theme_action.triggered.connect(self._show_theme_settings_dialog)
        sys_action = config_menu.addAction("系统集成设置(&S)...")
        sys_action.triggered.connect(self._show_system_settings_dialog)
        llm_api_action = config_menu.addAction("模型API管理(&M)...")
        # 这行曾被 e1dd85e（协议11 功能提交）误删 → 菜单项点了没反应，且
        # `_show_llm_api_manager` 因此被误判为「零引用死代码」（任务
        # 09-15-gui-dead-code-cleanup 复核时发现）。已有守卫：test/test_menu_wiring.py
        llm_api_action.triggered.connect(self._show_llm_api_manager)
        update_act = config_menu.addAction("更新设置(&U)...")
        update_act.triggered.connect(self._show_update_settings_dialog)
        # 下载在后台进行时，面板被收起也能从这里叫回来（R8）
        dl_progress_act = config_menu.addAction("下载进度(&D)...")
        dl_progress_act.triggered.connect(self._show_download_panel)
        config_menu.addSeparator()
        reset_layout_act = config_menu.addAction("恢复默认窗口布局(&W)")
        reset_layout_act.triggered.connect(self._reset_window_layout)

        help_menu = menubar.addMenu("帮助(&H)")

        check_act = help_menu.addAction("检查更新(&C)")
        check_act.triggered.connect(self._check_update_manual)

        feedback_act = help_menu.addAction("问题反馈(&F)...")
        feedback_act.triggered.connect(self._show_feedback_dialog)

        github_issue_act = help_menu.addAction("提交问题到 GitHub(&G)...")
        github_issue_act.setToolTip(
            "把问题整理成 GitHub Issue：填好令牌可一键直连建单，"
            "没有令牌则在浏览器里按表单预填后提交"
        )
        github_issue_act.triggered.connect(self._show_github_issue_dialog)

        diag_act = help_menu.addAction("生成诊断包(&D)...")
        diag_act.setToolTip("把版本、脱敏后的配置与最近日志打成一个 zip，方便反馈问题时一次发全")
        diag_act.triggered.connect(self._export_diagnostics)

        about_action = help_menu.addAction("关于(&A)")
        about_action.triggered.connect(self._show_about_dialog)

    # ==================== 问题反馈 ====================
    def _show_feedback_dialog(self):
        """帮助菜单「问题反馈」：打开桌面端反馈对话框（提交到 Web 反馈服务器，
        与 Web 页面共用同一个 feedback.db）。懒 import 保持主程序启动轻量。"""
        try:
            from feedback_dialog import FeedbackDialog, set_config_path

            set_config_path(self._config_path)
            dlg = FeedbackDialog(
                parent=self,
                app_version=APP_VERSION,
                build_date=BUILD_DATE,
                protocol_name=self.protocol_combo.currentText(),
            )
            dlg.exec()
        except Exception as e:  # noqa: BLE001 - 反馈功能不应影响主程序
            QMessageBox.critical(self, "问题反馈", f"反馈功能打开失败：{e}")

    # ==================== 提交问题到 GitHub ====================
    def _show_github_issue_dialog(self):
        """帮助菜单「提交问题到 GitHub」：把现场整理成一条 issue。

        两条通道（见 `github_issue.py`）：
        - 填了令牌 → **直连 REST API 一键建单**，issue 立刻出现在仓库里；
        - 没填令牌 → 打开浏览器，按 Issue Form 的字段 id 预填，用户点一次提交。

        仓库地址与「关于」按钮、自动升级源同源（`AUTHOR_GITHUB_URL`）；
        令牌只存本机 config.json，不随程序分发。
        """
        try:
            from github_issue import protocol_option, resolve_owner_repo, resolve_token
            from github_issue_dialog import GitHubIssueDialog

            owner, repo = resolve_owner_repo(AUTHOR_GITHUB_URL)
            token = resolve_token(self._config_path)
            dlg = GitHubIssueDialog(
                parent=self,
                owner=owner,
                repo=repo,
                token=token,
                app_version=APP_VERSION,
                build_date=BUILD_DATE,
                protocol_option=protocol_option(self.current_protocol),
                frame_hex=(self._last_parsed_hex or ""),
                config_path=self._config_path,
            )
            dlg.exec()
            # 用户填了令牌就顺手记住（下次直接建单，不用再粘一遍）
            if dlg.token_edit.text().strip() and dlg.token_edit.text().strip() != token:
                dlg.persist_token()
        except Exception as e:  # noqa: BLE001 - 反馈功能不应影响主程序
            QMessageBox.critical(self, "提交问题到 GitHub", f"功能打开失败：{e}")

    # ==================== 诊断包 ====================
    def _export_diagnostics(self):
        """帮助菜单「生成诊断包」：版本 + 脱敏配置 + 最近日志 → 一个 zip。

        远程排障时用户只需发这一个文件。**不收集报文原文与个人身份信息**，
        配置里的 API Key / Token 等字段由 `diagnostics.redact` 统一替换。
        """
        from datetime import datetime

        try:
            from diagnostics import build_diagnostics
        except Exception as e:  # noqa: BLE001 - 诊断功能不应影响主程序
            QMessageBox.critical(self, "生成诊断包", f"诊断模块不可用：{e}")
            return

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_path = Path.home() / "Desktop" / f"南网解析诊断包_v{APP_VERSION}_{stamp}.zip"
        path, _ = QFileDialog.getSaveFileName(
            self, "保存诊断包", str(default_path), "ZIP 压缩包 (*.zip)")
        if not path:
            return
        if not path.lower().endswith(".zip"):
            path += ".zip"
        try:
            result = build_diagnostics(
                path, app_data_dir(), APP_VERSION, BUILD_DATE,
                extra={
                    "当前协议": self.protocol_combo.currentText(),
                    "当前页面": self.tab_widget.tabText(self.tab_widget.currentIndex()),
                    "已打开串口": bool(getattr(self.serial_worker, "is_open", lambda: False)()),
                },
            )
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "生成诊断包", f"生成失败：{e}")
            return

        size_kb = max(1, int(result.get("bytes", 0) / 1024))
        skipped = result.get("skipped") or []
        tip = f"\n\n跳过 {len(skipped)} 项（不存在或超出大小上限）" if skipped else ""
        QMessageBox.information(
            self, "生成诊断包",
            f"已生成（{size_kb} KB，{len(result.get('included', []))} 个文件）：\n"
            f"{result.get('path', path)}{tip}\n\n"
            "配置文件中的密钥类字段已脱敏，不含报文原文。\n请把这个 zip 发给开发者。")

    def _show_share_dialog(self):
        """单帧解析页「分享此帧」：把最近解析的报文分享到 Web 服务端
        （与 Web /share 页共享 frameshare.db）。懒 import 保持启动轻量。"""
        if not getattr(self, "current_result", None) or not self._last_parsed_hex:
            QMessageBox.information(self, "分享", "请先解析一个报文，再点击分享！")
            return
        try:
            from share_dialog import ShareDialog
            from share_dialog import fd as _fd

            _fd.set_config_path(self._config_path)
            # 主窗口协议名（如 "[0] 南网协议 (Q/CSG1209021-2019)"）→ 对话框内
            # 下拉为短名（"南网协议"），按索引映射
            short_names = {
                0: "南网协议",
                1: "PLC RF协议",
                2: "HDLC/国网DLMS",
                3: "DLMS-APDU(国网)",
                4: "DLMS Wrapper裸报文",
                5: "DLMS-APDU裸报文",
                6: "DLT645-2007 电表协议",
                7: "国网协议",
                8: "698.45协议",
                9: "新一代载波协议",
                10: "国网新一代双模",
                11: "HDC 1.0 双模",
            }
            proto = short_names.get(self.current_protocol, "不确定")
            dlg = ShareDialog(
                parent=self,
                frame_hex=self._last_parsed_hex,
                protocol_name=proto,
                app_version=APP_VERSION,
            )
            dlg.exec()
        except Exception as e:  # noqa: BLE001 - 分享功能不应影响主程序
            QMessageBox.critical(self, "分享", f"分享功能打开失败：{e}")

    # ==================== 自动更新 ====================
    def _load_update_settings(self):
        """加载 config.json "update" 段到 self._update_settings。"""
        cfg = self._app_config.get("update", {})
        self._update_settings = dict(cfg) if isinstance(cfg, dict) else {}

    def _save_update_settings(self):
        """把 self._update_settings 写回 config.json "update" 段。"""
        try:
            config = {}
            if self._config_path.exists():
                try:
                    with open(self._config_path, encoding="utf-8") as f:
                        config = json.load(f)
                except Exception:
                    config = {}
            config["update"] = self._update_settings
            atomic_write_json(self._config_path, config)
        except Exception as e:
            print(f"[更新] 保存配置失败: {e}")

    def _auto_check_update(self):
        """启动/周期静默自动检查更新（网络失败/无新版均不打扰）。

        主窗口隐藏（已关闭到托盘/最小化退出路径）时不检查——
        用户要求：只有软件打开时才检查更新，避免后台周期性弹更新提示。
        """
        if getattr(self, "_is_closing", False) or not self.isVisible():
            return
        try:
            self._run_update_check(silent=True)
        except Exception:
            pass

    def _check_update_manual(self):
        """帮助菜单/关于「检查更新」：拉取仓库全部版本并弹列表，用户可选择任意版本下载。"""
        self._run_update_check(silent=True, show_list=True)

    def _run_update_check(self, silent: bool, show_list: bool = False):
        """后台线程检查更新。

        - show_list=True：拉取仓库全部版本列表，弹选择对话框（手动「检查更新」）
        - 否则：检查最新版，有新版则询问（静默/周期自动检查）
        """
        cfg = dict(self._update_settings)

        if not cfg.get("enabled", True):
            if not silent:
                QMessageBox.information(
                    self, "检查更新", "已关闭自动更新（可在「配置→更新设置」开启）"
                )
            return

        # 用 QThread 子类做网络 IO，避免阻塞 GUI；信号直连 MainWindow 槽，AutoConnection 自动正确排队
        thread = getattr(self, "_update_check_thread", None)
        if thread is not None:
            try:
                if thread.isRunning():
                    return
            except RuntimeError:
                # C++ 对象已被 deleteLater 回收，Python wrapper 还在
                pass

        self._update_ctx = {"silent": silent, "show_list": show_list}

        thread = _UpdateCheckWorker(
            cfg, APP_VERSION, list_all=show_list, repo_url=AUTHOR_GITHUB_URL
        )
        self._update_check_thread = thread
        thread_registry.track(thread, "UpdateCheckWorker")
        if show_list:
            thread.release_list_ready.connect(self._on_version_list_result_cb)
        else:
            thread.result_ready.connect(self._on_update_check_result_cb)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_update_check_result_cb(self, result: dict):
        """检查更新完成回调（GUI 线程安全）。"""
        if getattr(self, "_is_closing", False):
            return
        ctx = getattr(self, "_update_ctx", {}) or {}
        self._on_update_check_result(result, ctx.get("silent", True))

    def _on_update_check_result(self, result: dict, silent: bool):
        """检查完成：自动检查发现新版仅在状态栏提示（不弹窗打扰），无新版则隐藏提示。"""
        if result.get("error"):
            if not silent:
                QMessageBox.warning(self, "检查更新", f"检查失败：{result['error']}")
            return
        latest = result.get("latest") or {}
        needed = result.get("needed", False)
        if not needed:
            self._set_update_status(None)
            if not silent:
                ver = latest.get("version", "未知")
                QMessageBox.information(self, "检查更新", f"已是最新版本（{ver}）。")
            return
        # 有新版
        if silent:
            # 自动/周期检查：不弹窗，仅状态栏右下角绿色⬆提示，用户点击后再确认下载
            self._set_update_status(latest)
            return
        if self._confirm_update_download(latest):
            self._start_download(latest)

    def _source_label(self) -> str:
        """当前更新源的一句话描述（对话框里给用户看）。"""
        from auto_updater import describe_source

        return describe_source(self._update_settings)

    def _release_page_url(self) -> str:
        """当前更新源的发布页地址（无则空串）。"""
        try:
            from auto_updater import VersionChecker

            return VersionChecker(self._update_settings).release_page_url()
        except Exception:
            return ""

    def _confirm_update_download(self, latest: dict) -> bool:
        """「发现新版本」确认：版本对比 + **更新说明**（可滚动）+ 发布页入口。

        返回 True 表示用户点了「下载并更新」。说明用 Markdown 渲染
        （GitHub Release body 就是 markdown），不再把原始 markdown 塞进
        QMessageBox 的纯文本里。
        """
        from update_dialogs import ask_update_available

        return ask_update_available(
            self, APP_VERSION, latest, release_page_url=self._release_page_url()
        )

    def _set_update_status(self, latest):
        """设置/清除状态栏「发现新版本」提示（latest=None 时隐藏，表示已是最新版）。"""
        lbl = getattr(self, "_update_status_lbl", None)
        if lbl is None:
            return
        if not latest:
            self._pending_update = None
            lbl.hide()
            self.statusBar().update()
            return
        self._pending_update = latest
        remote = latest.get("version", "?")
        from auto_updater import summarize_notes

        notes = summarize_notes(latest.get("notes") or "", 120)
        lbl.setText(f"⬆ 发现新版本 v{remote}，点击更新")
        lbl.setToolTip(
            f"发现新版本：{APP_VERSION} → {remote}\n{notes}\n点击查看更新说明并下载"
            if notes
            else f"发现新版本：{APP_VERSION} → {remote}\n点击查看更新说明并下载"
        )
        lbl.setStyleSheet(self._update_status_style())
        lbl.show()
        self.statusBar().update()

    def _update_status_style(self):
        """状态栏更新提示样式：绿色加粗醒目显示（暗色主题用亮绿）。"""
        from theme_settings import is_dark

        color = "#4ade80" if self._is_dark_theme() else "#0a8f2e"
        return f"color: {color}; font-weight: bold; font-size: {self._font_size + 1}pt; padding: 0 6px;"

    def _on_update_status_clicked(self):
        """点击状态栏更新提示：弹确认框（含更新说明），确认后下载更新。"""
        if getattr(self, "_is_closing", False):
            return
        latest = getattr(self, "_pending_update", None)
        if not latest:
            return
        if self._confirm_update_download(latest):
            self._start_download(latest)

    def _on_version_list_result_cb(self, releases: list, err: str):
        """版本列表回调（GUI 线程安全）。"""
        if getattr(self, "_is_closing", False):
            return
        self._on_version_list_result(releases, err)

    def _on_version_list_result(self, releases: list, err: str):
        """手动「检查更新」：显示仓库全部版本列表 + **更新说明**面板，可下载任意版本。"""
        if err:
            QMessageBox.warning(self, "检查更新", f"获取版本列表失败：{err}")
            return
        if not releases:
            QMessageBox.information(self, "检查更新", "仓库中没有可更新的版本。")
            return

        from update_dialogs import ask_version_list

        chosen = ask_version_list(
            self,
            releases,
            APP_VERSION,
            source_label=self._source_label(),
            release_page_url=self._release_page_url(),
        )
        if chosen:
            self._start_download(chosen)

    def _start_download(self, latest: dict):
        """后台下载新版 exe（**非模态**面板：可继续用主程序、可暂停、可取消）。"""
        from update_download_dialog import UpdateDownloadDialog

        url = latest.get("url", "")
        if not url:
            QMessageBox.warning(self, "更新", "未获取到下载地址。")
            return

        # 已有下载在跑就不再起第二个线程：两轮下载会抢同一个 `.part`（同一目的文件），
        # 实测会拼出字节错位的文件。改为把面板叫回前台即可。
        running = getattr(self, "_download_thread", None)
        if running is not None and running.isRunning():
            self._show_download_panel()
            self.statusBar().showMessage("已有下载任务在进行中，已显示下载面板", 5000)
            return

        exe_path = Path(sys.argv[0]) if getattr(sys, "frozen", False) else None
        # 打包运行：exe 自身路径；源码运行：定位 dist 下的 exe（便于测试）
        if exe_path is None or not exe_path.exists():
            exe_path = Path(__file__).parent / "dist" / "南网协议解析工具.exe"
            if not exe_path.exists():
                exe_path = Path(__file__).parent / "南网协议解析工具.exe"

        import tempfile

        from auto_updater import safe_file_stem

        tmp_dir = Path(tempfile.gettempdir()) / "jiexigongju_updater"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        # tag 含 `/`、`:` 等字符时直接拼会把临时文件写成子目录/非法路径 → 清洗
        new_exe = Path(tmp_dir) / (
            "南网解析工具_" + safe_file_stem(latest.get("version", "new")) + ".exe"
        )

        max_threads = _resolve_download_threads(self._update_settings)
        dlg = UpdateDownloadDialog(
            self,
            version=str(latest.get("version", "") or ""),
            total_size=0,
            threads=max_threads or 0,
        )
        thread = _UpdateDownloadWorker(
            url,
            new_exe,
            latest.get("sha256", ""),
            verify_sha=bool(self._update_settings.get("sha256_verify", True)),
            parent=self,
            max_threads=max_threads,
        )
        self._download_thread = thread
        self._download_dlg = dlg
        self._download_ctx = {
            "exe_path": str(exe_path),
            "dlg": dlg,
            "latest": latest,
            "dest": str(new_exe),
        }
        thread_registry.track(thread, "UpdateDownloadWorker")

        # 下载 → 界面
        thread.stats.connect(dlg.update_progress)
        thread.stats.connect(self._on_download_stats_statusbar)
        # 界面 → 下载（暂停 / 继续 / 取消）
        dlg.pause_requested.connect(thread.pause)
        dlg.resume_requested.connect(thread.resume)
        dlg.cancel_requested.connect(thread.cancel)

        thread.paused.connect(self._on_download_paused_cb)
        thread.cancelled.connect(self._on_download_cancelled_cb)
        thread.done.connect(self._on_download_done_cb)
        thread.finished.connect(thread.deleteLater)
        # 「后台运行」/ 关窗口：只收起面板，下载继续（状态栏保留进度）
        dlg.background_requested.connect(
            lambda d=dlg: self._hide_download_panel(d))
        # 「清理缓存」：删掉 .part 与进度文件（只剩「已取消」态可用）
        dlg.discard_requested.connect(
            lambda d=dlg: self._discard_download_cache(d))

        # **非模态**：show() 而不是 exec()，下载期间主程序照常可用
        dlg.show()
        thread.start()

    def _show_download_panel(self, *_args):
        """「配置→下载进度」：把下载面板叫回前台（后台运行时也能回来）。"""
        dlg = getattr(self, "_download_dlg", None)
        running = getattr(self, "_download_thread", None)
        if dlg is None or (running is not None and not running.isRunning()):
            self.statusBar().showMessage("当前没有正在进行的下载", 4000)
            return
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _hide_download_panel(self, dlg):
        """「后台运行」：只收起面板，下载线程继续跑。"""
        if dlg is not None:
            dlg.hide()
        self.statusBar().showMessage(
            "下载已在后台进行，可从「配置→下载进度」重新打开面板", 8000)

    def _discard_download_cache(self, dlg):
        """「清理缓存」：删掉 `.part` 与进度文件（仅在无下载进行时可用）。"""
        from downloader import cleanup_partial

        ctx = getattr(self, "_download_ctx", {}) or {}
        dest = ctx.get("dest", "")
        running = getattr(self, "_download_thread", None)
        if running is not None and running.isRunning():
            QMessageBox.information(self, "下载", "下载进行中，先暂停或取消再清理缓存。")
            return
        try:
            if dest:
                cleanup_partial(Path(dest))
        except Exception as exc:        # noqa: BLE001 - 清理失败不该弹异常栈
            self.statusBar().showMessage(f"清理缓存失败：{exc}", 8000)
            return
        if dlg is not None and hasattr(dlg, "mark_cancelled"):
            dlg.mark_cancelled()
        self.statusBar().showMessage("已清理下载缓存（临时文件与进度文件）", 6000)

    def _on_download_stats_statusbar(self, progress):
        """后台下载时在状态栏保留一行进度（面板收起后也能看到）。"""
        try:
            from downloader import format_speed

            text = (
                f"下载更新 {float(progress.percent):.0f}%"
                f" · {format_speed(progress.speed_bps)}"
                f" · {int(progress.threads)} 线程"
            )
            self.statusBar().showMessage(text)
        except Exception:                  # noqa: BLE001 - 状态栏不该影响下载
            pass

    def _on_download_paused_cb(self):
        self.statusBar().showMessage("下载已暂停（点「继续」从断点接着下）", 8000)

    def _on_download_cancelled_cb(self):
        ctx = getattr(self, "_download_ctx", {}) or {}
        dlg = ctx.get("dlg")
        if dlg is not None and hasattr(dlg, "mark_cancelled"):
            dlg.mark_cancelled()
        self.statusBar().showMessage("下载已取消，临时文件已清理", 8000)
    def _on_download_done_cb(self, ok: bool, err: str, new_path: str):
        """下载完成回调（GUI 线程安全）。"""
        ctx = getattr(self, "_download_ctx", {}) or {}
        self._on_download_done(
            ok,
            err,
            new_path,
            ctx.get("exe_path", ""),
            ctx.get("dlg"),
            ctx.get("latest", {}),
        )

    def _on_download_done(self, ok, err, new_path, exe_path, dlg, latest):
        """下载结束：成功则编排替换并退出，失败提示。"""
        # 状态栏那行「下载更新 x%」必须撤掉：否则下载完了还挂着 100% 的旧进度
        try:
            self.statusBar().clearMessage()
        except Exception:              # noqa: BLE001 - 状态栏不该影响收尾
            pass
        if dlg is not None:
            if ok and hasattr(dlg, "mark_completed"):
                dlg.mark_completed()
            elif not ok and hasattr(dlg, "mark_failed"):
                dlg.mark_failed(err)
            dlg.close()
        if not ok:
            QMessageBox.warning(self, "下载更新", f"下载失败：{err}")
            return
        # 下载校验成功，编排替换
        from auto_updater import Opdater

        updater = Opdater()
        updater.make_backup(Path(exe_path))  # 可选备份，失败忽略
        bat = updater.stage_and_replace(Path(new_path), Path(exe_path))
        if bat is None:
            QMessageBox.critical(self, "更新", "启动替换脚本失败，请手动覆盖 exe。")
            return
        QMessageBox.information(self, "更新", "更新下载完成，即将替换并重启应用。")
        self._schedule_quit()

    def _schedule_quit(self):
        """给 update.bat 留出启动时间后退出主程序。"""
        QTimer.singleShot(800, self.close)

    def _show_update_settings_dialog(self):
        """配置菜单「更新设置」：编辑 config.json update 段。"""
        from PySide6.QtWidgets import (
            QCheckBox,
            QComboBox,
            QDialog,
            QDialogButtonBox,
            QFormLayout,
            QLineEdit,
        )

        from auto_updater import describe_source, merge_update_config

        cfg = merge_update_config(self._update_settings, repo_url=AUTHOR_GITHUB_URL)

        dialog = QDialog(self)
        dialog.setWindowTitle("更新设置")
        dialog.setMinimumWidth(520)
        form = QFormLayout(dialog)

        enabled_cb = QCheckBox("启用自动更新")
        enabled_cb.setChecked(bool(cfg.get("enabled", True)))
        form.addRow("自动更新", enabled_cb)

        start_cb = QCheckBox("启动时自动检查")
        start_cb.setChecked(bool(cfg.get("check_on_start", True)))
        form.addRow("启动检查", start_cb)

        source_combo = QComboBox()
        source_combo.addItem("GitHub Releases（默认）", "github")
        source_combo.addItem("Gitee Releases（国内）", "gitee")
        source_combo.addItem("私有 HTTP 服务器", "private")
        idx = source_combo.findData(cfg.get("source_type", "github"))
        source_combo.setCurrentIndex(max(0, idx))
        form.addRow("更新源", source_combo)

        source_tip = QLabel(f"当前：{describe_source(cfg)}")
        source_tip.setStyleSheet("color: #888;")
        source_tip.setWordWrap(True)
        form.addRow("", source_tip)

        github_tip = (
            "留空即用内置默认（与「关于」里的作者仓库同源：\n"
            f"{AUTHOR_GITHUB_URL}）"
        )
        owner_edit = QLineEdit(str(cfg.get("github_owner", "")))
        owner_edit.setPlaceholderText("例如 Liruitao1993")
        owner_edit.setToolTip(github_tip)
        form.addRow("GitHub owner", owner_edit)
        repo_edit = QLineEdit(str(cfg.get("github_repo", "")))
        repo_edit.setPlaceholderText("例如 South_Network_Protocol_Analysis_Tool")
        repo_edit.setToolTip(github_tip)
        form.addRow("GitHub repo", repo_edit)

        gitee_owner_edit = QLineEdit(str(cfg.get("gitee_owner", "")))
        form.addRow("Gitee owner", gitee_owner_edit)
        gitee_repo_edit = QLineEdit(str(cfg.get("gitee_repo", "")))
        form.addRow("Gitee repo", gitee_repo_edit)
        private_edit = QLineEdit(str(cfg.get("private_url", "")))
        private_edit.setPlaceholderText("https://host/version.json")
        form.addRow("私有源 URL", private_edit)

        sha_cb = QCheckBox("校验 SHA-256（GitHub 源自动取官方摘要）")
        sha_cb.setChecked(bool(cfg.get("sha256_verify", True)))
        form.addRow("安全校验", sha_cb)

        # 下载线程数：多线程分段下载（跑满带宽）。0 = 自动（按文件大小/CPU 自适应）
        threads_combo = QComboBox()
        for label, value in (("自动（推荐）", 0), ("8 线程", 8), ("16 线程", 16),
                             ("24 线程", 24), ("32 线程（最快）", 32)):
            threads_combo.addItem(label, value)
        saved_threads = int(cfg.get("download_threads", 0) or 0)
        t_idx = threads_combo.findData(saved_threads)
        threads_combo.setCurrentIndex(t_idx if t_idx >= 0 else 0)
        threads_combo.setToolTip(
            "下载新版时用几个线程并发拉取分段（分段 + 断点续传）。\n"
            "线程越多，在带宽/延迟受限的网络上越快；默认 32 线程为上限。\n"
            "「自动」= 按文件大小与 CPU 核数自适应。"
        )
        form.addRow("下载线程", threads_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 与默认相同的 owner/repo 存空串 ⇒ 继续跟随 AUTHOR_GITHUB_URL（唯一来源）
            from auto_updater import github_fields_for_save

            gh = github_fields_for_save(
                owner_edit.text(), repo_edit.text(), repo_url=AUTHOR_GITHUB_URL
            )
            self._update_settings = {
                "enabled": enabled_cb.isChecked(),
                "check_on_start": start_cb.isChecked(),
                "source_type": source_combo.currentData(),
                "github_owner": gh["github_owner"],
                "github_repo": gh["github_repo"],
                "gitee_owner": gitee_owner_edit.text().strip(),
                "gitee_repo": gitee_repo_edit.text().strip(),
                "private_url": private_edit.text().strip(),
                "sha256_verify": sha_cb.isChecked(),
                # 0 = 自动（自适应）；其余为固定线程数（1~32）
                "download_threads": int(threads_combo.currentData() or 0),
            }
            self._save_update_settings()

    def _show_about_dialog(self):
        """显示"关于"对话框"""
        self._build_about_dialog().exec()

    def _build_about_dialog(self):
        """构造"关于"对话框并返回（不 exec，便于测试直接检查控件与接线）"""
        dialog = QDialog(self)
        dialog.setWindowTitle("关于")
        dialog.setMinimumSize(520, 480)
        dialog.setWindowFlags(
            dialog.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)

        title_label = QLabel("协议解析工具")
        title_label.setFont(self._ui_font(6, bold=True))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        version_label = QLabel("版本 2.0")
        version_label.setFont(self._ui_font(1))
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("color: #666;")
        layout.addWidget(version_label)

        desc_label = QLabel("支持南网协议 / PLC RF / HDLC/DLMS 多协议报文解析")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        author_label = QLabel("作者: liruitao")
        author_label.setFont(self._ui_font(0))
        author_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        author_label.setStyleSheet("color: #888;")
        layout.addWidget(author_label)

        # 提示用户去 GitHub 给作者点 Star（文案与跳转地址同源 AUTHOR_GITHUB_URL）
        star_tip_label = QLabel(
            "如果这个工具帮到了你，欢迎在 GitHub 上给作者点个 ⭐ Star"
        )
        star_tip_label.setFont(self._ui_font(0))
        star_tip_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        star_tip_label.setStyleSheet("color: #888;")
        star_tip_label.setWordWrap(True)
        layout.addWidget(star_tip_label)

        changelog_label = QLabel("版本更新记录")
        changelog_label.setFont(self._ui_font(0, bold=True))
        layout.addWidget(changelog_label)

        changelog_text = QTextEdit()
        changelog_text.setReadOnly(True)
        changelog_text.setFont(self._ui_font(-1))

        from datetime import date

        today = date.today().strftime("%Y-%m-%d")
        html_parts = []
        html_parts.append(f"<b>v2.0 ({today})</b><ul>")
        html_parts.append("<li>优化界面布局，提高信息密度</li>")
        html_parts.append("<li>统一表格字体为7pt，行高压缩至13px</li>")
        html_parts.append("</ul>")
        html_parts.append("<b>v1.0</b><ul>")
        html_parts.append("<li>初始版本发布</li>")
        html_parts.append("<li>支持南网、PLC RF、HDLC/DLMS、DLT645协议</li>")
        html_parts.append("</ul>")

        changelog_text.setHtml("".join(html_parts))
        layout.addWidget(changelog_text)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        star_btn = QPushButton("去 GitHub 给作者点 Star")
        star_btn.setObjectName("about_star_btn")
        star_btn.setIcon(app_icons.load_icon("star"))
        star_btn.setToolTip(f"在浏览器中打开作者仓库：{AUTHOR_GITHUB_URL}")
        star_btn.setMinimumWidth(170)
        star_btn.clicked.connect(self._open_author_github)
        btn_layout.addWidget(star_btn)
        check_update_btn = QPushButton("检查更新")
        check_update_btn.setFixedWidth(110)
        check_update_btn.clicked.connect(
            lambda: (dialog.accept(), self._check_update_manual())
        )
        btn_layout.addWidget(check_update_btn)
        ok_btn = QPushButton("确定")
        ok_btn.setFixedWidth(80)
        ok_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(ok_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        return dialog

    def _open_author_github(self):
        """用系统默认浏览器打开作者 GitHub 仓库（「关于」对话框的 Star 按钮）。

        打开失败时把地址显示出来供用户手动复制，而不是静默无反应
        （同 AGENTS §8 陷阱 23 的容错原则：宁可给出信息也不要什么都不发生）。
        """
        url = (AUTHOR_GITHUB_URL or "").strip()
        if not url:
            QMessageBox.information(
                self, "给作者点 Star", "未配置 GitHub 地址（AUTHOR_GITHUB_URL 为空）。"
            )
            return
        if not QDesktopServices.openUrl(QUrl(url)):
            QMessageBox.information(
                self,
                "给作者点 Star",
                f"未能调起浏览器，请手动访问：\n{url}",
            )

    # ==================== 系统集成（托盘 / 热键 / 单实例 / 命令行） ====================

    def _setup_system_integration(self):
        """初始化系统托盘、全局热键、单实例监听（在 setup_ui 之后调用）"""
        # 系统托盘
        self._tray_manager = None
        self._hotkey_manager = None
        self._single_instance = None
        self._tray_exit = False  # 托盘"退出"标志：true 时 closeEvent 真正退出
        self._is_closing = (
            False  # 关闭流程标志：拦截关闭途中后台线程排队投递的更新回调弹窗
        )

        icon_path = str(_app_icon_path())
        tray = SystemTrayManager(self)
        if tray.create(icon_path):
            self._tray_manager = tray
            tray.show_requested.connect(self._tray_show_window)
            tray.exit_requested.connect(self._tray_exit_app)
            tray.autostart_toggled.connect(self._on_tray_autostart_toggled)
            # 托盘菜单内嵌输入框：回车/点「解析」→ 走与剪贴板/文件右键同源的解析路径
            tray.parse_text_requested.connect(self._on_tray_parse_text)
            tray.update_autostart_state()

        # 全局热键
        self._hotkey_manager = GlobalHotkeyManager(
            self._system_settings.get("hotkey", "Ctrl+Alt+X")
        )
        self._hotkey_manager.set_callback(self._on_global_hotkey)
        self._restart_hotkey()

        # 单实例监听
        self._single_instance = SingleInstanceServer(self)
        self._single_instance.args_received.connect(self._on_second_instance_args)

        # 剪贴板监听（检测其他软件复制的 hex 报文 → 弹提示框）
        self._clipboard_monitor = ClipboardMonitor(self)
        self._clipboard_monitor.hex_ready.connect(self._on_clipboard_hex)
        self._clipboard_monitor.set_enabled(
            bool(self._system_settings.get("clipboard_monitor", True))
        )
        self._clipboard_monitor.start()

    def _on_clipboard_hex(self, frame_bytes: bytes, hex_str: str, detected_protocol):
        """剪贴板检测到 hex 报文 → 弹提示框（单实例复用，避免堆积）"""
        # 去重：主窗口自身解析填入剪贴板时不弹
        if hasattr(self, "_last_parsed_hex") and self._last_parsed_hex:
            own = self._last_parsed_hex.replace(" ", "").lower()
            if own == hex_str.lower():
                return

        # 复用已存在的提示框：更新内容而非新建（防止多次复制后窗口堆叠）
        if hasattr(self, "_prompt_dialog") and self._prompt_dialog is not None:
            try:
                if self._prompt_dialog.isVisible():
                    self._prompt_dialog.update_content(
                        frame_bytes, hex_str, detected_protocol
                    )
                    return
            except RuntimeError:
                pass  # C++ 对象已删除，重新创建

        dialog = ParsePromptDialog(frame_bytes, hex_str, detected_protocol, self)
        self._prompt_dialog = dialog
        # 关闭后清理引用，避免悬空
        dialog.destroyed.connect(lambda *_: self._clear_prompt_ref(dialog))
        # 填充协议下拉（11 协议）
        items = []
        for i in range(self.protocol_combo.count()):
            items.append((self.protocol_combo.itemText(i), i))
        dialog.add_protocols(items)
        # 显示（非模态 + 置顶，不阻塞主窗口）
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        # 解析确认后打开解析窗口
        dialog.accepted.connect(
            lambda d=dialog: self._open_prompt_parse(d.get_selection())
        )

    def _clear_prompt_ref(self, dialog):
        """提示框销毁时清引用"""
        if getattr(self, "_prompt_dialog", None) is dialog:
            self._prompt_dialog = None

    def _open_prompt_parse(self, selection):
        """提示框确认解析：按所选协议打开解析窗口（不弹主窗口）"""
        frame_bytes, proto_idx = selection
        if proto_idx is None:
            proto_idx = self.current_protocol
        # 不显示主窗口，直接弹解析结果窗口（避免窗口太多）
        self._parse_and_show_dialog(frame_bytes, initial_protocol=proto_idx)

    def _restart_hotkey(self):
        """按当前设置启动/停止全局热键监听"""
        if not hasattr(self, "_hotkey_manager") or self._hotkey_manager is None:
            return
        enabled = bool(self._system_settings.get("hotkey_enabled", True))
        if enabled:
            hotkey = self._system_settings.get("hotkey", "Ctrl+Alt+X")
            self._hotkey_manager.set_hotkey(hotkey)
            ok = self._hotkey_manager.start()
            if not ok:
                print(f"[全局热键] 注册失败，请检查热键格式或是否被占用: {hotkey}")
        else:
            self._hotkey_manager.stop()

    def _on_tray_autostart_toggled(self, enabled: bool):
        """托盘菜单中"开机自启"开关被切换"""
        self._system_settings["auto_start"] = bool(enabled)
        try:
            from system_integration.registry_menu import set_autostart

            set_autostart(bool(enabled))
            # 同步写回 config.json
            try:
                config = {}
                if self._config_path.exists():
                    with open(self._config_path, encoding="utf-8") as f:
                        config = json.load(f)
                config["system"] = self._system_settings
                atomic_write_json(self._config_path, config)
            except Exception as e:
                print(f"[系统设置保存失败] {e}")
        except Exception as e:
            print(f"[开机自启设置失败] {e}")

    # ── 粘性入口：托盘菜单内嵌输入框 / 任务栏缩略图按钮 ────────────────────

    #: 任务栏按钮（悬停图标预览里）——文案与图标名（`icons/lucide`）
    TASKBAR_BUTTONS = (("解析剪贴板", "clipboard"),
                       ("快捷解析", "zap"),
                       ("批量解析", "files"),
                       ("光伏升级", "hard-drive-upload"))

    def _parse_text_input(self, text: str) -> bool:
        """把一段用户文本当报文解析并弹结果（托盘输入框 / 任务栏按钮共用）。

        判据与剪贴板检测**同源**（`clipboard_monitor.strict_hex`）：
        - 整串是严格 HEX ⇒ `_parse_and_show_dialog(frame, 协议)`（协议先按特征识别，识别不出用当前下拉）；
        - 否则退回「按文本提取报文」路径（与文件右键 / `--file` 同一实现）。
        返回是否受理（False = 既不是 HEX 也提取不到报文，调用方负责提示，不静默）。
        """
        raw = (text or "").strip()
        if not raw:
            return False
        from system_integration import clipboard_monitor
        clean = clipboard_monitor.strict_hex(raw)
        if clean:
            try:
                frame = bytes.fromhex(clean)
            except ValueError:
                return False
            idx = clipboard_monitor.detect_protocol(frame)
            self._parse_and_show_dialog(frame, idx if idx is not None else self.current_protocol)
            self._raise_parse_windows()
            return True
        if not self._clean_hex_input(raw, keep_newlines=True).strip():
            return False
        self._parse_text_content(raw)
        return True

    def _raise_parse_windows(self):
        """把刚弹出的解析结果窗口提到最前（托盘/任务栏入口触发时主窗口可能被隐藏）。"""
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, QDialog) and widget.isVisible():
                widget.raise_()
                widget.activateWindow()

    def _on_tray_parse_text(self, text: str) -> None:
        """托盘菜单内嵌输入框提交 → 解析；不受理时气泡 + 状态栏说明（不静默）。"""
        if self._parse_text_input(text):
            return
        msg = "输入内容既不是合法 HEX 报文，也提取不到报文（示例：68 0E 00 … 16）"
        self.statusBar().showMessage(msg, 6000)
        if self._tray_manager is not None:
            self._tray_manager.show_message("无法解析", msg)

    def _taskbar_parse_clipboard(self) -> None:
        """任务栏按钮「解析剪贴板」：直接取剪贴板文本走同一条解析路径。"""
        try:
            text = QApplication.clipboard().text()
        except Exception:
            text = ""
        if not self._parse_text_input(text):
            self._on_tray_parse_text(text)          # 复用同一套「不受理」提示

    def _goto_tab(self, index: int) -> None:
        """切到指定标签页并把主窗口显示到前台（任务栏按钮用）。"""
        if self.isHidden():
            self.showNormal()
        self.raise_()
        self.activateWindow()
        if index is not None and index >= 0:
            self.tab_widget.setCurrentIndex(index)

    def _setup_taskbar_buttons(self, force: bool = False) -> bool:
        """给任务栏图标挂「悬停预览按钮」（Win11 支持；不可用则静默跳过）。

        只在**窗口句柄变化时**重挂（`ThumbBarAddButtons` 重复调用可能叠加按钮）；
        Qt 重建原生窗口后句柄会变，所以挂在 `showEvent` 里并比对句柄。
        """
        if getattr(self, "_taskbar_buttons", None) is None:
            self._taskbar_buttons = TaskbarButtons(self)
            self._taskbar_buttons.clicked.connect(self._on_taskbar_button)
        try:
            hwnd = int(self.windowHandle().winId()) if self.windowHandle() else 0
        except Exception:
            hwnd = 0
        if not hwnd:
            return False
        if not force and hwnd == getattr(self, "_taskbar_hwnd", 0):
            return bool(getattr(self, "_taskbar_ready", False))
        icons = []
        for _label, icon_name in self.TASKBAR_BUTTONS:
            try:
                icons.append(app_icons.load_icon(icon_name))
            except Exception:
                icons.append(None)
        ok = self._taskbar_buttons.set_buttons(
            self, list(zip([label for label, _i in self.TASKBAR_BUTTONS], icons)))
        self._taskbar_hwnd = hwnd
        self._taskbar_ready = bool(ok)
        if not ok and not getattr(self, "_taskbar_warned", False):
            self._taskbar_warned = True
            self.statusBar().showMessage(
                "任务栏快捷按钮不可用（当前系统/窗口状态不支持，其余功能不受影响）", 5000)
        return bool(ok)

    def _on_taskbar_button(self, btn_id: int) -> None:
        """任务栏缩略图按钮被点（外壳发 WM_COMMAND，经 `TaskbarButtons.clicked` 转来）。"""
        idx = int(btn_id) - int(TASKBAR_BASE_ID)
        labels = [label for label, _icon in self.TASKBAR_BUTTONS]
        if not 0 <= idx < len(labels):
            return
        label = labels[idx]
        if label == "解析剪贴板":
            self._taskbar_parse_clipboard()
        elif label == "快捷解析":
            self._on_global_hotkey()
        elif label == "批量解析":
            self._goto_tab(getattr(self, "_batch_tab_index", -1))
        else:                                        # 光伏升级：切协议8 + 切到该页
            if self.current_protocol != 8:
                self.protocol_combo.setCurrentIndex(8)
            self._goto_tab(getattr(self, "_upgrade_tab_index", -1))

    def _tray_show_window(self):
        """托盘"显示主窗口"：显示并置顶"""
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _tray_exit_app(self):
        """托盘"退出"：真正退出程序"""
        self._tray_exit = True
        self.close()

    def showEvent(self, event):
        """主窗口显示（含从托盘恢复）：恢复周期更新检查。"""
        super().showEvent(event)
        # 只有真正显示过的窗口才在退出时保存布局（见 closeEvent）
        self._window_shown_once = True
        if self._update_settings.get(
            "check_on_start", True
        ) and self._update_settings.get("enabled", True):
            timer = getattr(self, "_update_poll_timer", None)
            if timer is not None and not timer.isActive():
                timer.start()
        # 首次显示后让协议组 FlowLayout 按真实宽度重排一次，
        # 修正启动时宽度未确定导致的黑块/错位（最大化后才正常的问题）
        if not getattr(self, "_proto_first_reflowed", False):
            self._proto_first_reflowed = True
            QTimer.singleShot(0, self._reflow_proto_group)
        # 显示后按最终标题栏宽度重算协议名居中（构造期 width 可能还不是最终值；
        # Windows 可能在 show 时微调边框/按钮区，resizeEvent 未必触发）
        QTimer.singleShot(0, self._update_window_title)
        QTimer.singleShot(150, self._update_window_title)
        # 任务栏快捷按钮：挂一次（窗口句柄变化时 `_setup_taskbar_buttons` 自己会重挂）；
        # 延到事件循环里做，确保 show 之后原生窗口/任务栏按钮已经存在
        QTimer.singleShot(0, self._setup_taskbar_buttons)

    def closeEvent(self, event):
        """关闭窗口：若启用托盘且非主动退出，最小化到托盘"""
        if (
            self._tray_manager is not None
            and not self._tray_exit
            and self._system_settings.get("close_to_tray", True)
        ):
            event.ignore()
            self.hide()
            # 主窗口隐藏后不再周期性检查更新（避免后台静默弹更新提示占资源）；
            # 从托盘恢复显示时由 showEvent 重启周期检查
            timer = getattr(self, "_update_poll_timer", None)
            if timer is not None:
                timer.stop()
            self._tray_manager.show_hint_once()
            return
        # 真实退出（含托盘「退出」与自动更新重启）：先把窗口几何/分栏/列宽收进
        # config.json 再销毁 UI（最小化到托盘的分支已在上面 return，不写）。
        # 统一走 _save_app_config，不要在这里另写一份 JSON。
        # 仅在窗口**真正显示过**时保存：测试与 --parse/--file/--clipboard 路径
        # 构造的窗口从未示人，其几何是合成值，写进去会污染用户配置并在下次
        # 启动被套用（本特性的真实副作用，实测会写入 684×666 这类 offscreen 尺寸）。
        if getattr(self, "_window_shown_once", False):
            try:
                self._window_state = self._collect_window_state()
                self._save_app_config()
            except Exception as e:  # noqa: BLE001 - 保存失败不得阻断退出
                print(f"[窗口状态保存失败] {e}")
        # 关闭流程开始：拦截后台更新检查线程在退出途中排队投递的回调弹窗
        self._is_closing = True
        # 回收虚拟表串口监听线程
        try:
            self.virtual_meter_tab.shutdown()
        except Exception:
            pass
        try:
            self.dlt645_sim_tab.shutdown()
        except Exception:
            pass
        # 统一停止/回收所有后台线程与定时器
        self._shutdown_threads()

        # 清理托盘与热键
        if self._tray_manager is not None:
            self._tray_manager.hide_tray()
        if getattr(self, "_taskbar_buttons", None) is not None:
            try:
                self._taskbar_buttons.clear(self)
            except Exception:
                pass
        if self._hotkey_manager is not None:
            self._hotkey_manager.stop()
        event.accept()

        # 显式退出事件循环：Qt 仅在“最后一个可见窗口”关闭时才发 lastWindowClosed
        # 并退出 app.exec()。托盘退出（_tray_exit_app）与自动更新重启路径
        # （_schedule_quit）在窗口已隐藏时调用 close()，此时 lastWindowClosed 不触发，
        # 线程已全部回收但事件循环不退出、进程残留。故真正退出时必须主动 quit()。
        # 用 singleShot 延迟到当前事件处理结束后，避免在 closeEvent 中途终止事件循环。
        QTimer.singleShot(0, QApplication.quit)

    def _shutdown_threads(self):
        """真正退出时统一停止所有后台线程与定时器。

        每步独立 try/except，单点失败不阻断后续回收。阻塞型网络/抓包线程
        用各自的 stop 标志 + 有限 wait，超时断开信号放行；不调用 terminate()
        （可能在系统调用中死锁或损坏资源，进程退出后 OS 会回收）。
        """
        # 1) 状态栏自身的刷新定时器
        for tname in (
            "_thread_count_timer",
            "_update_poll_timer",
            "_frame_count_timer",
        ):
            t = getattr(self, tname, None)
            if t is not None:
                try:
                    t.stop()
                except Exception:
                    pass

        def _safe_wait(qthread, ms=1500):
            try:
                if qthread is not None and qthread.isRunning():
                    qthread.wait(ms)
            except RuntimeError:
                pass

        # 2) 更新检查/下载线程：断开信号后等待，避免关闭途中回调弹窗
        for tname in ("_update_check_thread", "_download_thread"):
            qt = getattr(self, tname, None)
            if qt is None:
                continue
            if tname == "_download_thread" and qt.isRunning():
                # 退出时取消下载但**保留**已下载的分段（on_cancel=keep）：
                # 默认 clean 会把几白 MB 的 .part 删掉，下次开机白重来
                try:
                    qt.on_cancel = "keep"
                    qt.cancel()
                except RuntimeError:
                    pass
            try:
                qt.disconnect(qt)
            except (RuntimeError, TypeError):
                pass
            _safe_wait(qt, 500)

        # 3) 串口工作线程
        sw = getattr(self, "serial_worker", None)
        if sw is not None:
            try:
                sw.close_port()
            except Exception:
                pass
            _safe_wait(sw, 1500)

        # 4) 全局热键线程（stop 内部已 wait）
        hm = getattr(self, "_hotkey_manager", None)
        if hm is not None:
            try:
                hm.stop()
            except Exception:
                pass

        # 5) 剪贴板监听（断开 dataChanged）
        cm = getattr(self, "_clipboard_monitor", None)
        if cm is not None:
            try:
                cm.stop()
            except Exception:
                pass

        # 6) TCP 抓包线程 + 其 UI 刷新定时器
        tcp = getattr(self, "tcp_monitor_tab", None)
        if tcp is not None:
            try:
                tcp.cleanup()
            except Exception:
                pass

        # 6b) 串口工具：发送线程 + 串口句柄 + 落盘
        serial_tool = getattr(self, "serial_tool_tab", None)
        if serial_tool is not None:
            try:
                serial_tool.cleanup()
            except Exception:
                pass

        # 6b-2) 生产测试架：停防抖定时器 + 断开共享串口信号 + 落盘（不关串口）
        testbench = getattr(self, "testbench_tab", None)
        if testbench is not None:
            try:
                testbench.cleanup()
            except Exception:
                pass

        # 6c) 蓝牙工具：BLE asyncio 循环线程 + 日志文件收尾
        bluetooth_tool = getattr(self, "bluetooth_tool_tab", None)
        if bluetooth_tool is not None:
            try:
                bluetooth_tool.cleanup()
            except Exception:
                pass

        # 6d) 698.45 升级页：停逐包确认定时器 + 断开串口信号 + 落盘（不得关闭串口）
        upgrade = getattr(self, "upgrade_tab", None)
        if upgrade is not None:
            try:
                upgrade.cleanup()
            except Exception:
                pass

        # 6e) 698.45 协议测试页：停等待/重发定时器 + 断开串口信号 + 落盘（不得关闭串口）
        test_tab = getattr(self, "test_tab", None)
        if test_tab is not None:
            try:
                test_tab.cleanup()
            except Exception:
                pass

        # 7) LLM 预处理线程（取消运行中的请求）
        llm = getattr(self, "llm_preprocess_widget", None)
        if llm is not None:
            try:
                if (
                    getattr(llm, "_worker", None) is not None
                    and llm._worker.isRunning()
                ):
                    llm._worker.cancel()
            except Exception:
                pass

        # 8) Python 脚本执行线程（可中断）
        ps = getattr(self, "_py_script_thread", None)
        if ps is not None:
            try:
                if ps.isRunning():
                    ps.requestInterruption()
                    ps.quit()
                    _safe_wait(ps, 1000)
            except RuntimeError:
                pass

        # 9) 批量解析后台线程：先断信号（避免关闭途中回投 UI 槽）+ 取消 + 有限等待
        bw = getattr(self, "_batch_worker", None)
        if bw is not None:
            try:
                bw.disconnect(self)
            except (RuntimeError, TypeError):
                pass
            try:
                bw.cancel()
            except Exception:
                pass
            _safe_wait(bw, 2000)
            # 先置空引用：队列里残留的 progress/cancelled 信号会变成陈旧信号
            # （否则 `_on_batch_progress` 会对已 deleteLater 的 C++ 对象调 ack()）。
            # 代价是 `_finish_batch_parse` 不再走收尾 → 此处自行复位控件状态，
            # 避免「批量解析」按钮/协议下拉停在禁用、进度条停在解析中
            # （步骤 2 复核遗留：仅真退出路径可达）
            self._batch_worker = None
            self._batch_cancelling = False
            try:
                self.batch_summary_table.setUpdatesEnabled(True)
                self._set_batch_parsing_state(False)
            except RuntimeError:
                pass

        # 10) 兜底：注册表中仍存活的 QThread 统一请求中断 + quit + 等待
        for qt in thread_registry.qthreads_alive():
            try:
                if qt.isRunning():
                    try:
                        qt.requestInterruption()
                    except Exception:
                        pass
                    try:
                        qt.quit()
                    except Exception:
                        pass
                    _safe_wait(qt, 800)
            except RuntimeError:
                pass

    def _on_global_hotkey(self):
        """全局热键触发：唤出 uTools 风格快捷解析小窗（首次懒创建）。

        小窗显示时自行读取剪贴板预填；剪贴板为空或非 hex 时空白等待输入。
        """
        if getattr(self, "_quick_panel", None) is None:
            items = [
                (self.protocol_combo.itemText(i), i)
                for i in range(self.protocol_combo.count())
            ]
            self._quick_panel = QuickParsePanel(
                self,
                protocol_items=items,
                clean_fn=lambda t: self._clean_hex_input(t),
                parse_fn=self._quick_panel_parse,
                validate_fn=self._quick_panel_validate,
                open_full_fn=self._quick_panel_open_full,
                is_dark_fn=self._is_dark_theme,
                main_protocol_fn=lambda: self.protocol_combo.currentIndex(),
            )
        self._quick_panel.toggle_panel()

    def _quick_panel_parse(self, frame_bytes: bytes, idx: int):
        """快捷小窗解析回调：返回 (rows|None, err|None, note|None)。

        9/10 协议固定 auto 级别并自动剥离 ED 监控头；其余直接解析。
        """
        parse_bytes = frame_bytes
        ed_rows = None
        try:
            if idx in (9, 10) and frame_bytes and frame_bytes[0] == 0xED:
                rows, business, _offset = self._parse_ed_monitor_header(
                    frame_bytes, wrapper=self._ed_wrapper_for_frame(frame_bytes)
                )
                if rows is None or business is None:
                    return (
                        None,
                        (
                            "ED 监控帧解析失败：报文不完整或格式错误（缺 EF/EE 或被截断），"
                            "首字节 ED 不能作为业务帧起始符解析。"
                        ),
                        None,
                    )
                parse_bytes = business
                ed_rows = rows
            kwargs = {}
            if idx in (9, 10):
                kwargs["parse_level"] = "auto"
            parser = self._get_current_parser(idx, **kwargs)
            data = parser.parse_to_table(parse_bytes)
        except Exception as e:
            return None, f"解析失败：{e}", None
        if ed_rows:
            data = list(ed_rows) + list(data)
        return data, None, None

    def _quick_panel_validate(self, frame_bytes: bytes, idx: int):
        """快捷小窗校验回调：返回 (valid|None, summary_str)。None=不支持校验。"""
        try:
            if not hasattr(self, "_quick_validators") or self._quick_validators is None:
                self._quick_validators = protocol_registry.build_validator_map()
            validator = self._quick_validators.get(idx)
            if validator is None:
                return None, ""
            verify_bytes = frame_bytes
            # 与 _quick_panel_parse 口径对齐：9/10 协议 ED 包装帧先剥离监控头再校验，
            # 否则 validator 不识别 ED 包装导致「解析成功但徽章恒为校验失败」
            if idx in (9, 10) and frame_bytes and frame_bytes[0] == 0xED:
                try:
                    _rows, business, _offset = self._parse_ed_monitor_header(
                        frame_bytes, wrapper=self._ed_wrapper_for_frame(frame_bytes)
                    )
                    if business:
                        verify_bytes = business
                except Exception:
                    pass
            result = validator.verify(verify_bytes)
            return bool(result.valid), result.summary()
        except Exception:
            return None, ""

    def _quick_panel_open_full(self, frame_bytes: bytes, idx: int):
        """快捷小窗「在主窗口打开」：把当前帧送入主程序单帧解析页。

        同步主窗体协议下拉到小窗选中协议、切到单帧解析 tab、触发解析，
        并隐藏小窗（避免遮挡主程序）。语义与 _send_frame_to_single_parse 一致。
        """
        hex_str = " ".join(f"{b:02X}" for b in frame_bytes)
        self.single_input.setPlainText(hex_str)
        if (
            0 <= idx < self.protocol_combo.count()
            and self.protocol_combo.currentIndex() != idx
        ):
            self.protocol_combo.setCurrentIndex(idx)
        self.tab_widget.setCurrentIndex(0)
        self.parse_single()
        if self._quick_panel is not None:
            self._quick_panel.hide()

    def _parse_and_show_dialog(self, frame_bytes: bytes, initial_protocol: int = None):
        """解析字节并弹出结果对话框（热键/命令行/文件右键共用）

        顶部提供协议选择下拉，切换时用所选协议重新解析。
        新一代载波(9)/国网新一代(10)额外提供解析级别下拉 + ED 监控头自动剥离。
        initial_protocol: 初始协议索引，None 用当前主窗口协议。
        """
        if initial_protocol is None:
            initial_protocol = self.current_protocol

        dialog = QDialog(self)
        dialog.setWindowTitle("解析结果")
        dialog.resize(960, 640)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QVBoxLayout(dialog)

        # 顶部：协议选择 + 解析级别 + hex 显示
        proto_row = QHBoxLayout()
        proto_row.addWidget(QLabel("协议:"))
        proto_combo = QComboBox()
        for i in range(self.protocol_combo.count()):
            proto_combo.addItem(self.protocol_combo.itemText(i), i)
        proto_combo.setCurrentIndex(
            proto_combo.findData(initial_protocol)
            if proto_combo.findData(initial_protocol) >= 0
            else 0
        )
        proto_combo.setMinimumWidth(280)
        proto_row.addWidget(proto_combo)

        # 解析级别下拉（仅 9/10 可见）：自动识别 + 各级别
        level_label = QLabel("解析级别:")
        proto_row.addWidget(level_label)
        level_combo = QComboBox()
        CSG_LEVELS = [
            ("自动识别", "auto"),
            ("FC+PB解析(完整MPDU)", "fc_pb"),
            ("FC+eFC解析", "fc_efc"),
            ("仅FC解析", "fc_only"),
            ("应用层报文", "app"),
            ("仅PB解析(完整物理块)", "pb_only"),
        ]
        GW_LEVELS = [
            ("自动识别", "auto"),
            ("仅FC解析", "fc_only"),
            ("仅MAC帧", "mac_only"),
            ("仅PB", "pb_only"),
            ("FC+MAC解析", "fc_mac"),
            ("应用层报文", "app"),
        ]
        level_combo.setVisible(False)
        level_label.setVisible(False)
        proto_row.addWidget(level_combo)

        # PB帧类型下拉（仅 pb_only 可见）
        frame_type_label = QLabel("帧类型:")
        frame_type_combo = QComboBox()
        frame_type_label.setVisible(False)
        frame_type_combo.setVisible(False)
        proto_row.addWidget(frame_type_label)
        proto_row.addWidget(frame_type_combo)
        proto_row.addStretch()
        layout.addLayout(proto_row)

        # ED 监控头剥离开关（协议9/10/11 可见，默认勾选）
        ed_chk = QCheckBox("剥离ED监控头")
        ed_chk.setChecked(True)
        ed_chk.setVisible(False)
        ed_chk.setToolTip(
            "勾选后自动识别并剥离 ED..EF..EE 监控包装头，前置显示监控信息再解析业务帧。\n"
            "适用于协议9 / 10 / 11；勾选后不完整 ED 帧会明确报错"
        )
        layout.addWidget(ed_chk)

        hex_text = QTextEdit()
        hex_text.setReadOnly(True)
        hex_text.setFont(self._ui_font(0, family="Consolas"))
        hex_text.setMaximumHeight(70)
        hex_str = " ".join(f"{b:02X}" for b in frame_bytes)
        hex_text.setText(f"报文: {hex_str}")
        layout.addWidget(hex_text)

        # 解析结果表格（紧凑排版，与主窗口解析表一致：小字号 + 贴合行高）
        table = ZoomableTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["字段", "原始值", "解析值", "说明"])
        header = table.horizontalHeader()
        header.setStretchLastSection(True)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(13)
        table_font = self._ui_font(-2)
        table.setFont(table_font)
        self._setup_table_copy_menu(table)
        layout.addWidget(table)

        error_label = QLabel()
        error_label.setWordWrap(True)
        error_label.setStyleSheet("color: #d32f2f;")
        error_label.hide()
        layout.addWidget(error_label)

        def _is_new_gen(idx):
            # 协议9/10/11：解析级别 + ED 监控头勾选（与主窗口注册表能力一致）
            return idx in (9, 10, 11)

        def _update_extras_visibility(idx):
            """按协议索引显示/隐藏解析级别、帧类型、ED监控头控件"""
            show = _is_new_gen(idx)
            level_label.setVisible(show)
            level_combo.setVisible(show)
            ed_chk.setVisible(show)
            if not show:
                frame_type_label.setVisible(False)
                frame_type_combo.setVisible(False)
                return
            # 填解析级别选项（9 用 CSG 族；10/11 用 GW 族）
            level_combo.blockSignals(True)
            level_combo.clear()
            levels = CSG_LEVELS if idx == 9 else GW_LEVELS
            for text, val in levels:
                level_combo.addItem(text, val)
            # 默认自动识别
            level_combo.setCurrentIndex(level_combo.findData("auto"))
            # 填帧类型选项
            frame_type_combo.blockSignals(True)
            frame_type_combo.clear()
            if idx == 9:
                for text, val in [
                    ("SOF帧", "sof"),
                    ("信标帧", "beacon"),
                    ("ACK帧(SACK)", "sack"),
                    ("NET帧", "net"),
                ]:
                    frame_type_combo.addItem(text, val)
            else:
                for text, val in [
                    ("SOF帧", 1),
                    ("信标帧", 0),
                    ("ACK帧(SACK)", 2),
                    ("NET帧", 3),
                ]:
                    frame_type_combo.addItem(text, val)
            level_combo.blockSignals(False)
            frame_type_combo.blockSignals(False)
            # pb_only 时显示帧类型
            is_pb = level_combo.currentData() == "pb_only"
            frame_type_label.setVisible(show and is_pb)
            frame_type_combo.setVisible(show and is_pb)

        def _preprocess(idx, raw):
            """协议预处理：ED 监控头剥离 + 前置行。返回 (bytes, extra_rows, err)

            协议9：由「ED监控协议/剥离ED监控头」勾选项启用（勾选后不完整帧必须报错）；
            协议10/11：勾选后同协议9（严格报错）；未勾选时自动识别，且要求解包后
            业务帧确为合法 FC（DT ∈ 0~3），否则按原样解析。
            """
            if not raw or raw[0] != 0xED:
                return raw, None, None
            if idx not in (9, 10, 11):
                return raw, None, None
            ed_on = ed_chk.isChecked()
            if idx == 9 and not ed_on:
                return raw, None, None
            declared = (raw[1] | (raw[2] << 8)) + 4 if len(raw) >= 3 else 0
            err = (
                "ED 监控帧解析失败：报文不完整或格式错误，"
                "首字节 ED 不能作为业务帧起始符解析。\n"
                "请检查报文是否被截断（帧长字段声明整包应为 %d 字节，实际 %d 字节），"
                "或缺少 EF 数据域起始符 / EE 结束符。" % (declared, len(raw))
            )
            try:
                rows, business, offset = self._parse_ed_monitor_header(
                    raw, wrapper=self._ed_wrapper_for_frame(raw)
                )
            except Exception:
                return (None, None, err) if (idx == 9 or ed_on) else (raw, None, None)
            if rows is None or business is None:
                return (None, None, err) if (idx == 9 or ed_on) else (raw, None, None)
            if idx in (10, 11) and not ed_on and not self._ed_business_is_fc(business):
                return raw, None, None
            return business, rows, None

        def do_parse(idx=None):
            """用当前所选协议重新解析并填充表格"""
            if idx is None:
                idx = proto_combo.currentData()
            dialog.setWindowTitle(f"解析结果 - {proto_combo.currentText()}")
            table.setRowCount(0)
            error_label.hide()
            # 预处理：ED 头剥离
            parse_bytes, ed_rows, ed_err = _preprocess(idx, frame_bytes)
            if ed_err is not None:
                error_label.setText(ed_err)
                error_label.show()
                return
            try:
                kwargs = {}
                if _is_new_gen(idx):
                    kwargs["parse_level"] = level_combo.currentData()
                    if level_combo.currentData() == "pb_only":
                        kwargs["frame_type"] = frame_type_combo.currentData()
                parser = self._get_current_parser(idx, **kwargs)
                data = parser.parse_to_table(parse_bytes)
            except Exception as e:
                error_label.setText(
                    f"解析失败（{proto_combo.currentText()}）：{str(e)}"
                )
                error_label.show()
                return
            # ED 监控头前置行
            if ed_rows:
                data = ed_rows + list(data)
            for r, item in enumerate(data):
                table.insertRow(r)
                table.setItem(r, 0, QTableWidgetItem(str(item[0])))
                table.setItem(r, 1, QTableWidgetItem(str(item[1])))
                table.setItem(r, 2, QTableWidgetItem(str(item[2])))
                table.setItem(r, 3, QTableWidgetItem(str(item[3])))
            # 行高自适应文字内容（紧凑贴合）
            table.resizeRowsToContents()

        def _on_level_changed(_idx):
            is_pb = level_combo.currentData() == "pb_only"
            frame_type_label.setVisible(is_pb)
            frame_type_combo.setVisible(is_pb)
            do_parse()

        level_combo.currentIndexChanged.connect(_on_level_changed)
        frame_type_combo.currentIndexChanged.connect(lambda _: do_parse())
        proto_combo.currentIndexChanged.connect(
            lambda _: (_update_extras_visibility(proto_combo.currentData()), do_parse())
        )
        _update_extras_visibility(initial_protocol)
        do_parse(proto_combo.currentData())

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        copy_btn = QPushButton("复制全部")
        copy_btn.clicked.connect(lambda: self._copy_table_rows(table, True))
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        btn_row.addWidget(copy_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        # 显示（非模态，不阻塞）
        dialog.show()

    def _on_second_instance_args(self, args: list):
        """第二个实例发来的命令行参数：执行 + 按需激活窗口"""
        # 无参数：仅激活已有主窗口
        if not args:
            self._tray_show_window()
            return
        # 有解析动作（--parse/--file/--clipboard）：直接弹解析结果，不弹主窗口
        has_action = any(a in ("--parse", "--file", "--clipboard") for a in args)
        if not has_action:
            self._tray_show_window()
        self._handle_cli_args(args)

    def _handle_cli_args(self, args: list):
        """处理命令行参数（--parse / --protocol / --file / --minimized / --clipboard）"""
        # 解析参数
        protocol_index = None
        parse_hex = None
        file_path = None
        minimized = False
        clipboard = False
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--parse" and i + 1 < len(args):
                parse_hex = args[i + 1]
                i += 2
            elif arg == "--protocol" and i + 1 < len(args):
                protocol_index = self._protocol_name_to_index(args[i + 1])
                i += 2
            elif arg == "--file" and i + 1 < len(args):
                file_path = args[i + 1]
                i += 2
            elif arg == "--clipboard":
                clipboard = True
                i += 1
            elif arg == "--minimized":
                minimized = True
                i += 1
            else:
                i += 1

        # 切换协议
        if (
            protocol_index is not None
            and 0 <= protocol_index < self.protocol_combo.count()
        ):
            self.protocol_combo.setCurrentIndex(protocol_index)

        # 最小化到托盘
        if minimized and self._tray_manager is not None:
            self.hide()
            return

        # 读剪贴板解析（NPP/UE 右键菜单、外部调用用）
        if clipboard:
            QTimer.singleShot(200, self._parse_clipboard_and_show)
            return

        # 文件解析
        if file_path:
            try:
                with open(file_path, encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception as e:
                QMessageBox.critical(self, "文件读取失败", f"无法读取文件：{str(e)}")
                return
            self._parse_text_content(content)
            return

        # 直接 hex 解析
        if parse_hex:
            clean = self._clean_hex_input(parse_hex)
            if len(clean) % 2 == 0 and all(
                c in "0123456789abcdefABCDEF" for c in clean
            ):
                try:
                    self._parse_and_show_dialog(bytes.fromhex(clean))
                except Exception as e:
                    QMessageBox.critical(self, "解析错误", f"解析失败：{str(e)}")

    def _parse_clipboard_and_show(self):
        """读取剪贴板 hex 并弹出解析对话框（--clipboard 参数用）"""
        clipboard = QGuiApplication.clipboard()
        text = clipboard.text() or ""
        if not text.strip():
            QMessageBox.information(
                self, "解析", "剪贴板为空，请先在编辑器中复制报文。"
            )
            return
        clean = self._clean_hex_input(text)
        clean = clean.strip()
        if len(clean) % 2 != 0 or not all(c in "0123456789abcdefABCDEF" for c in clean):
            QMessageBox.information(self, "解析", "剪贴板内容不是有效的十六进制报文。")
            return
        try:
            frame_bytes = bytes.fromhex(clean)
        except Exception:
            QMessageBox.information(self, "解析", "剪贴板内容不是有效的十六进制报文。")
            return
        # 不弹主窗口，直接显示解析结果（避免窗口太多）
        self._parse_and_show_dialog(frame_bytes)

    def _protocol_name_to_index(self, name: str) -> int:
        """协议名 → protocol_combo 索引（支持中文名 / 数字索引，查 protocol_registry）"""
        return protocol_registry.name_to_index(name)

    def _parse_text_content(self, content: str):
        """从文本内容提取帧并按当前协议解析，弹出结果（文件右键 / --file 共用）"""
        try:
            frames = self._extract_frames_for_protocol(content, self.current_protocol)
        except Exception:
            frames = [f.strip() for f in content.splitlines() if f.strip()]
        if not frames:
            QMessageBox.information(self, "提示", "文件中未找到可解析的报文。")
            return
        # 取第一帧解析
        first = frames[0]
        if isinstance(first, tuple):
            first = first[0]
        clean = self._clean_hex_input(first)
        if len(clean) % 2 != 0 or not all(c in "0123456789abcdefABCDEF" for c in clean):
            QMessageBox.information(self, "提示", "文件中未找到有效的十六进制报文。")
            return
        try:
            self._parse_and_show_dialog(bytes.fromhex(clean))
        except Exception as e:
            QMessageBox.critical(self, "解析错误", f"解析失败：{str(e)}")

    # ==================== 批量解析功能 ====================

    def load_from_file(self):
        """从文件加载报文列表"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择报文文件", "", "文本文件 (*.txt *.csv *.log);;所有文件 (*)"
        )

        if file_path:
            try:
                with open(file_path, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                self.batch_input.setPlainText(content)
                # 建立原始日志快照（此后 CLI/脚本回填只改输入框，不动快照）
                self._set_batch_snapshot(content, os.path.basename(file_path))
                frames = self._extract_frames(content)
                self.update_stats(
                    f'已从文件加载，识别到 {len(frames)} 帧报文（点击"开始批量解析"执行）'
                )
            except Exception as e:
                QMessageBox.critical(self, "错误", f"读取文件失败：{str(e)}")

    def load_from_pcap(self):
        """从 pcap/pcapng 离线导入 TCP 应用层帧到批量解析输入框。

        模式：
          - PLC2 监控帧（完整 ED..EE，适合协议9）
          - PLC2 业务帧（剥包装）
          - 原始 TCP 负载（每段一行，通用）
        """
        import pcap_import as pcap_import_mod

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 pcap 文件",
            "",
            "抓包文件 (*.pcap *.pcapng);;所有文件 (*)",
        )
        if not file_path:
            return

        box = QMessageBox(self)
        box.setWindowTitle("导入模式")
        box.setText(
            "选择 TCP 应用层提取方式：\n\n"
            "「PLC2 监控帧」— 按 ED..EE 切完整包装帧（推荐协议 9/时序图）\n"
            "「PLC2 业务帧」— 剥监控头只要业务帧\n"
            "「原始 TCP 负载」— 每个 TCP 段一行（通用兜底）"
        )
        btn_full = box.addButton("PLC2 监控帧", QMessageBox.AcceptRole)
        btn_biz = box.addButton("PLC2 业务帧", QMessageBox.AcceptRole)
        btn_raw = box.addButton("原始 TCP 负载", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec()
        clicked = box.clickedButton()
        if clicked in (None, box.button(QMessageBox.Cancel)):
            return
        if clicked is btn_full:
            mode = "plc2_full"
        elif clicked is btn_biz:
            mode = "plc2_business"
        else:
            mode = "tcp_payload"

        self.update_stats("正在导入 pcap…")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = pcap_import_mod.import_pcap(file_path, mode=mode)
            text = pcap_import_mod.format_batch_text(result.frames)
            self.batch_input.setPlainText(text)
            self._set_batch_snapshot(text, os.path.basename(file_path))
            summary = pcap_import_mod.summarize(result)
            if result.frame_count == 0:
                QMessageBox.warning(
                    self,
                    "导入结果",
                    f"未能提取到应用层帧。\n{summary}",
                )
                self.update_stats(f"pcap 导入完成，0 帧（{summary}）")
                return
            self.update_stats(
                f"已从 pcap 导入 {result.frame_count} 帧（{summary}）；"
                f"点击「开始批量解析」或自动继续"
            )
            # 直接批量解析，缩短现场路径：导入 → 解析 → 选类型 → 时序图
            self.parse_batch()
        except pcap_import_mod.PcapImportError as e:
            QMessageBox.critical(self, "导入失败", str(e))
            self.update_stats(f"pcap 导入失败：{e}")
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"意外错误：{e}")
            self.update_stats(f"pcap 导入失败：{e}")
        finally:
            QApplication.restoreOverrideCursor()

    def paste_from_clipboard(self):
        """从剪贴板粘贴"""
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if text:
            self.batch_input.setPlainText(text)
            # 粘贴即建立原始日志快照（内容来自剪贴板，无名）
            self._set_batch_snapshot(text, "剪贴板")
            frames = self._extract_frames(text)
            self.update_stats(
                f'已粘贴，识别到 {len(frames)} 帧报文（点击"开始批量解析"执行）'
            )

    @staticmethod
    def _clear_layout(layout):
        """递归清除layout中的所有子layout和widget"""
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                MainWindow._clear_layout(child.layout())

    @staticmethod
    def _extract_frames(text: str) -> list:
        """从混杂文本中提取完整的68起始帧（南网协议）

        预处理规则：
        1. 剔除时间戳、特殊符号前缀（[]、<>等非hex字符）
        2. 从hex字符串中按68H起始、利用长度域+校验和验证帧完整性
        """
        import re

        clean = re.sub(r"[^0-9A-Fa-f]", "", text).upper()

        frames = []
        i = 0
        while i < len(clean) - 7:
            pos = clean.find("68", i)
            if pos == -1:
                break

            if pos + 6 > len(clean):
                break

            try:
                low_byte = int(clean[pos + 2 : pos + 4], 16)
                high_byte = int(clean[pos + 4 : pos + 6], 16)
                length = low_byte | (high_byte << 8)
            except ValueError:
                i = pos + 2
                continue

            if length < 8 or length > 2048:
                i = pos + 2
                continue

            frame_hex_len = length * 2
            if pos + frame_hex_len > len(clean):
                i = pos + 2
                continue

            candidate = clean[pos : pos + frame_hex_len]
            if candidate[-2:] != "16":
                i = pos + 2
                continue

            try:
                frame_bytes = bytes.fromhex(candidate)
                cs_expected = sum(frame_bytes[3 : length - 1]) & 0xFF
                cs_actual = frame_bytes[length - 1]
                if cs_expected == cs_actual:
                    frames.append(candidate)
                    i = pos + frame_hex_len
                    continue
            except ValueError:
                pass

            i = pos + 2

        return frames

    def parse_batch(self):
        """批量解析入口（后台执行，立即返回，不阻塞界面）

        只做主线程同步的预处理（快照/行映射/剥离/清洗/提取，约 1.5 s）与后台
        任务启动；逐帧解析在 `BatchParseWorker` 线程执行，通过信号攒批回填摘要表。
        """
        prep = self._prepare_batch_input()
        if prep is None:
            return
        frames, params = prep
        self._start_batch_parse(frames, params)

    def _prepare_batch_input(self):
        """批量解析主线程预处理：快照 / 行映射 / 前缀剥离 / 清洗 / 帧提取。

        这些步骤**必须留在主线程同步完成**（设计 §7.2）：`_batch_lead_lines`、
        前缀剥离行映射与原始日志快照是摘要行号（`_src_line`）与「转到原始报文位置」
        的依据，解析开始前就要就绪；线程化会引入「快照未就绪但已开始解析」的竞态。

        Returns:
            (frames, params)：frames = 提取到的帧列表，params = 解析参数快照
            None：无有效输入或未提取到帧（已弹告警，行为与改动前一致）
        """
        full_text = self.batch_input.toPlainText()
        # 快照兜底：用户未走 拖入/打开/粘贴 入口（手敲/程序注入）且尚无快照时，
        # 以解析瞬间的输入框全文为原始日志快照（此后回填式预处理不覆盖它）
        if not self._batch_snapshot_text and full_text.strip():
            self._set_batch_snapshot(full_text, "输入框内容")
        input_text = full_text.strip()
        # 行号回跳：记录首部空白行剥离偏移与前缀剥离行映射（strip 函数填充）
        lead = len(full_text) - len(full_text.lstrip())
        self._batch_lead_lines = full_text[:lead].count("\n") if lead else 0
        self._last_strip_line_map = None
        self._csg_strip_done = False  # 协议9前缀剥离防重复（重复剥离会覆盖行映射）
        self._debug_log(f"parse_batch: 输入 {len(input_text)} 字符")
        self._debug_log(f"parse_batch: 前200字符:\n{input_text[:200]}")

        # 新一代载波协议(索引9)：先剥离监控日志前缀（在 hex 清洗前处理原始文本）
        # 监控日志格式: "<时间> <序号> -> 接收机 Has Get <15字节监控头> <协议报文>"
        # 需要先识别 "-> 接收机 Has Get" 标记，去除其后 15 字节监控头，再提取协议报文
        if self.current_protocol == 9:
            before = len(input_text)
            input_text = self._strip_csg_new_gen_frame_prefix(
                input_text, getattr(self, "_csg_parse_level", "auto")
            )
            self._csg_strip_done = True
            self._debug_log(
                f"_strip_csg_new_gen_frame_prefix: {before}→{len(input_text)} 字符"
            )
            self._debug_log(f"  前200字符:\n{input_text[:200]}")

        # 国网新一代(索引10)/HDC 1.0(索引11)：剥离日志前缀（在 hex 清洗前处理原始文本）
        # 日志格式: "Line XXX: timestamp: metadata:hex_data"
        # 取最后一个冒号后的 hex 数据；解析级别由函数内部按当前协议自取
        # （协议10 → _gw_parse_level，协议11 → _hdc10_parse_level，见 AGENTS §8 陷阱 43）
        if self.current_protocol in (10, 11):
            before = len(input_text)
            input_text = self._strip_gw_new_gen_prefix(input_text)
            self._debug_log(
                f"_strip_gw_new_gen_prefix: {before}→{len(input_text)} 字符"
            )

        # 预处理：去除空格、逗号等分隔符，保留换行以区分多帧
        before = len(input_text)
        input_text = self._clean_hex_input(input_text, keep_newlines=True)
        self._debug_log(f"_clean_hex_input: {before}→{len(input_text)} 字符")
        self._debug_log(f"  keep_newlines=True, 行数={len(input_text.splitlines())}")
        # 显示每行的前 40 字符
        for i, ln in enumerate(input_text.splitlines()[:5], 1):
            self._debug_log(f"  行{i}: [{len(ln) // 2:3d}B] {ln[:60]}")
        if len(input_text.splitlines()) > 5:
            self._debug_log(f"  ... 共 {len(input_text.splitlines())} 行")

        # 新一代载波协议(索引9)：先剥离监控日志前缀（在 hex 清洗前处理原始文本）
        # 监控日志格式: "<时间> <序号> -> 接收机 Has Get <15字节监控头> <协议报文>"
        # 需要先识别 "-> 接收机 Has Get" 标记，去除其后 15 字节监控头，再提取协议报文
        if self.current_protocol == 9 and not getattr(self, "_csg_strip_done", False):
            # 已在清洗前剥离过则跳过（重复剥离会把行映射覆盖为清洗后文本的行号）
            input_text = self._strip_csg_new_gen_frame_prefix(
                input_text, getattr(self, "_csg_parse_level", "auto")
            )

        # 国网新一代/HDC 1.0 (索引10/11)：剥离日志前缀
        if self.current_protocol in (10, 11):
            input_text = self._strip_gw_new_gen_prefix(input_text)

        # 预处理：去除空格、逗号等分隔符，保留换行以区分多帧
        input_text = self._clean_hex_input(input_text, keep_newlines=True)

        if not input_text:
            # 区分：原始输入为空 vs 预处理/清洗后为空
            raw = self.batch_input.toPlainText().strip()
            if raw:
                QMessageBox.warning(
                    self,
                    "警告",
                    "预处理后未保留有效报文内容！\n\n"
                    "可能原因：\n"
                    "• 预处理命令（如 find）过滤后，匹配行不含十六进制数据\n"
                    "• 日志行中的报文内容被文本描述覆盖\n\n"
                    "建议：检查预处理命令的过滤条件，或先不执行预处理查看原始内容。",
                )
            else:
                QMessageBox.warning(self, "警告", "请输入报文内容！")
            return

        # 根据当前协议选择帧提取方式
        frames = self._extract_frames_for_protocol(input_text, self.current_protocol)
        strip_map = getattr(self, "_last_strip_line_map", None)
        self._last_strip_line_map = None
        # 行映射快照交给后台 worker（下次解析会覆盖 _last_strip_line_map）
        self._batch_strip_map = strip_map
        self._debug_log(f"_extract_frames_for_protocol: 找到 {len(frames)} 帧")
        for i, f in enumerate(frames[:5], 1):
            fhex = f[0] if isinstance(f, tuple) else f
            self._debug_log(f"  帧{i}: [{len(fhex) // 2:3d}B] {fhex[:60]}")
        if len(frames) > 5:
            self._debug_log(f"  ... 共 {len(frames)} 帧")

        if not frames:
            # 给出更详细的诊断
            sample = input_text[:200].replace("\n", "\\n")
            QMessageBox.warning(
                self,
                "警告",
                f"未识别到有效帧！\n\n"
                f"清洗后内容（前200字符）：\n{sample}\n\n"
                f"可能原因：\n"
                f"• 当前协议（{self.protocol_combo.currentText()}）的帧起始符不匹配\n"
                f"• 内容为日志文本而非原始报文\n"
                f"• 报文被截断或格式异常",
            )
            return

        # 交给后台解析（本函数只负责同步预处理，不改结果集与控件状态）
        return frames, self._current_parse_params()

    # ==================== 批量解析后台执行（任务 09-15-gui-batch-parse-perf）====================

    def _batch_ed_parser(self, ed_wrapper_mode: str):
        """后台线程使用的 ED 包装头解析回调（widget-free）。

        `ed_wrapper_mode` 是启动解析时「ED 包装格式」下拉的快照（UI 线程读取）；
        闭包内只调用不读控件的 `_parse_ed_monitor_header`，且每帧只判一次格式。
        """

        def _parse(frame_bytes: bytes):
            # 归一化：本回调在工作线程内执行，绝不能回落到读控件
            # （`_parse_ed_monitor_header` 的 wrapper=None 分支会读下拉，跨线程不安全）
            mode = ed_wrapper_mode if ed_wrapper_mode in ("plc2", "gx") else "auto"
            wrapper = resolve_ed_wrapper(frame_bytes, mode)
            rows, business, offset = self._parse_ed_monitor_header(
                frame_bytes, wrapper=wrapper
            )
            return wrapper, rows, business, offset

        return _parse

    def _start_batch_parse(self, frames: list, params: dict):
        """启动后台批量解析：清空旧结果 → 建 worker → 进入「解析中」状态机。

        Args:
            frames: `_prepare_batch_input` 提取到的帧列表
            params: `_current_parse_params()` 的解析参数快照
        """
        # 防御：上一任务仍在跑（按钮已禁用，仅程序化重复调用能走到）→ 先断信号
        # （否则旧任务的 progress/cancelled 会投递到已清空的新结果集上）再取消
        worker = self._batch_worker
        if worker is not None:
            try:
                # 断开「worker → 本窗口」的全部连接（传 self 才是有效断连；
                # 曾误写 worker.disconnect(worker)，语义是「断开 worker→worker」
                # 实际返回 False、什么都没断，靠 _is_stale_batch_signal 兜底）
                worker.disconnect(self)
            except (RuntimeError, TypeError):
                pass
            self._batch_worker = None
            try:
                worker.cancel()
            except RuntimeError:
                pass
            try:
                worker.wait(2000)
            except RuntimeError:
                pass

        # 清空之前的结果
        self._batch_cancelling = False
        self.batch_summary_table.setUpdatesEnabled(True)
        self.batch_results = []
        # 详情 LRU 与新一批的解析参数快照（重解析必须与批量解析同参数）
        self._detail_cache.clear()
        self._batch_parse_params = dict(params)
        self._batch_ed_wrapper = self._ed_wrapper_mode()
        self.batch_summary_table.setRowCount(0)
        self.batch_detail_table.setRowCount(0)
        self.batch_detail_hex.clear()
        # 时序图随批量结果重建（若已创建）
        if getattr(self, "seq_diagram_tab", None) is not None:
            self.seq_diagram_tab.set_model(None)

        total = len(frames)
        self._batch_total = total
        worker = BatchParseWorker(
            frames,
            protocol_index=params["index"],
            parse_level=params["parse_level"],
            frame_type=params["frame_type"],
            channel=params["channel"],
            lead_lines=self._batch_lead_lines,
            strip_map=self._batch_strip_map,
            summary_fn=self._get_summary_from_table_data,
            type_name_fn=self._get_frame_type_name,
            ed_parse_fn=self._batch_ed_parser(self._batch_ed_wrapper),
            log_fn=self._debug_log,
        )
        self._batch_strip_map = None
        worker.progress.connect(self._on_batch_progress)
        worker.finished_ok.connect(self._on_batch_finished)
        worker.cancelled.connect(self._on_batch_cancelled)
        worker.failed.connect(self._on_batch_failed)
        # run() 返回（QThread::finished）后再删 C++ 对象，避免「线程仍在运行即析构」
        worker.finished.connect(worker.deleteLater)
        self._batch_worker = worker

        self._set_batch_parsing_state(True, total)
        worker.start()

    def _set_batch_parsing_state(self, parsing: bool, total: int = 0):
        """批量解析状态机：解析中禁用解析入口与协议下拉，空闲时隐藏进度控件。"""
        btn = getattr(self, "batch_parse_btn", None)
        if btn is not None:
            btn.setEnabled(not parsing)
        combo = getattr(self, "protocol_combo", None)
        if combo is not None:
            combo.setEnabled(not parsing)
        bar = getattr(self, "batch_progress_bar", None)
        if bar is not None:
            if parsing:
                bar.setRange(0, total)
                bar.setValue(0)
                bar.setFormat(f"解析中 0 / {total}")
                bar.setVisible(True)
            else:
                bar.setVisible(False)
        cancel = getattr(self, "batch_cancel_btn", None)
        if cancel is not None:
            cancel.setEnabled(parsing)
            cancel.setVisible(parsing)
        if parsing:
            self.batch_status_bar.setText(f"批量解析中… 0 / {total} 帧")

    def _is_stale_batch_signal(self) -> bool:
        """当前槽收到的信号是否来自**已被替换的旧任务**（跨任务残留交付）。

        旧 worker 的批量结果/收尾信号可能还在队列里，而新任务已启动（如解析中又
        拖入 pcap 触发 parse_batch）：此时旧信号若照常处理，会把新任务的
        `_batch_worker` 清空、控件状态改回「空闲」，新任务从此不可取消。
        用 sender 与当前 worker 比对到即丢弃（直接调用本方法时 sender 为 None）。
        """
        sender = self.sender()
        return sender is not None and sender is not self._batch_worker

    def _on_batch_progress(
        self, done: int, total: int, ok: int, fail: int, batch: list
    ):
        """工作线程攒批回填（按批而非逐帧，保证拖动/点击可响应）"""
        if self._is_stale_batch_signal():
            return
        table = self.batch_summary_table
        # 抑制逐行重绘：49k 行逐帧 insert+setItem 会明显卡顿
        table.setUpdatesEnabled(False)
        try:
            start = len(self.batch_results)
            self.batch_results.extend(batch)
            for offset, result in enumerate(batch):
                row = table.rowCount()
                table.insertRow(row)
                index = start + offset
                status = result.get("_status", "")

                # 序号（第 0 列 UserRole 存 batch_results 的全局原始索引，
                # 过滤/排序后行号≠索引，「转到原始报文位置」与详情都依赖它）
                num_item = QTableWidgetItem(str(index + 1))
                num_item.setTextAlignment(Qt.AlignCenter)
                num_item.setData(Qt.UserRole, index)
                table.setItem(row, 0, num_item)

                # 状态（emoji）
                status_item = QTableWidgetItem("✅" if status == "成功" else "❌")
                status_item.setTextAlignment(Qt.AlignCenter)
                if status == "成功":
                    status_item.setForeground(Qt.darkGreen)
                else:
                    status_item.setForeground(Qt.red)
                table.setItem(row, 1, status_item)

                # 长度
                frame_hex = result.get("_input", "")
                len_item = QTableWidgetItem(str(len(frame_hex) // 2))
                len_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(row, 2, len_item)

                # 协议/类型：_type_name 已对成功/失败/异常三种情况都写入，
                # 不再回落到可能残留上一帧的 table_data（原缺陷：异常行显示上帧类型）
                proto_item = QTableWidgetItem(result.get("_type_name") or "-")
                if status != "成功":
                    proto_item.setForeground(Qt.red)
                table.setItem(row, 3, proto_item)

                # 摘要
                table.setItem(row, 4, QTableWidgetItem(result.get("摘要", "")))
        finally:
            # 取消中保持抑制（由 _finish_batch_parse 统一恢复）：已解析批次还在信号
            # 队列里，逐批恢复重绘会把整表重绘 N 次，用户会感觉「取消没停下来」
            table.setUpdatesEnabled(not self._batch_cancelling)

        bar = getattr(self, "batch_progress_bar", None)
        if bar is not None:
            bar.setRange(0, total)
            bar.setValue(done)
            bar.setFormat(f"解析中 {done} / {total}")
        self.batch_status_bar.setText(
            f"批量解析中… {done} / {total} 帧（✅ {ok}，❌ {fail}）"
        )
        # 背压回执：告知 worker 可以继续下一片（避免信号队列积压大量回填任务，
        # 否则 processEvents() 会一次连续回填上百批，界面成段卡顿）
        worker = self._batch_worker
        if worker is not None:
            worker.ack()

    def _on_batch_finished(self, ok: int, fail: int):
        """工作线程全部完成"""
        self._finish_batch_parse(ok, fail, cancelled=False)

    def _on_batch_cancelled(self, ok: int, fail: int):
        """用户取消：已解析部分保留且可用（可看详情、可导出）"""
        self._finish_batch_parse(ok, fail, cancelled=True)

    def _on_batch_failed(self, message: str):
        """不可恢复错误（如构建解析器失败）"""
        if self._is_stale_batch_signal():
            return
        self._finish_batch_parse(0, 0, cancelled=True)
        self.batch_status_bar.setText(f"批量解析失败：{message}")

    def _finish_batch_parse(self, ok: int, fail: int, cancelled: bool = False):
        """收尾（完成/取消/失败共用）：状态栏 → 类型下拉 → 选中首行 → 恢复控件。"""
        if self._is_stale_batch_signal():
            return
        total = self._batch_total
        self._update_status_bar(ok, fail, total)
        if cancelled:
            self.batch_status_bar.setText(
                f"已取消 — 已解析 {ok + fail} / {total} 帧（✅ {ok} 成功，❌ {fail} 失败）"
            )
        bar = getattr(self, "batch_progress_bar", None)
        if bar is not None:
            bar.setValue(0 if cancelled else total)

        # 刷新「按类型全选」下拉（信标帧等类型一键勾选的来源）
        if hasattr(self, "batch_type_combo"):
            self._refresh_batch_type_combo()
            if hasattr(self, "batch_selected_count"):
                self.batch_selected_count.setText("")

        # 自动选中第一行并显示详情
        if self.batch_summary_table.rowCount() > 0:
            self.batch_summary_table.selectRow(0)
            self._on_batch_row_selected()

        self._set_batch_parsing_state(False)
        self._batch_cancelling = False
        self.batch_summary_table.setUpdatesEnabled(True)
        self._batch_worker = None

    def _cancel_batch_parse(self):
        """「取消」按钮：停止后台解析（分片边界返回，已完成结果保留）"""
        worker = self._batch_worker
        if worker is None:
            return
        worker.cancel()
        # 取消即停止解析（worker 在下一个分片边界返回，实测 <1ms）；已解析批次还在
        # 信号队列里，先抑制表格重绘直到收尾，避免「取消后表格还在刷」的观感
        self._batch_cancelling = True
        self.batch_summary_table.setUpdatesEnabled(False)
        self.batch_status_bar.setText("批量解析取消中…（已完成结果保留）")

    # ── 详情按需（步骤 3：去 `_table_data` 常驻缓存）────────────────

    def _detail_parser_for(self, params: dict):
        """详情重解析用的解析器实例（本窗口自建，参数变化时重建）。

        不用 ``parser_registry.get_parser`` 的共享单例：解析器带帧级可变状态
        （如 ``csg_new_gen_parser`` 的 ``_pb_size``/``_cmt_index``/``_pb_count``），
        与单帧解析页/实时监控共享会被相互污染。本实例只在 UI 线程的详情路径用。
        """
        key = (
            params["index"],
            params["parse_level"],
            repr(params["frame_type"]),
            params["channel"],
        )
        if self._detail_parser_obj is None or self._detail_parser_key != key:
            spec = protocol_registry.get_protocol(params["index"])
            base = get_parser_class(spec.parser_key)()
            self._detail_parser_obj = protocol_registry.build_gui_parser(
                params["index"],
                base,
                parse_level=params["parse_level"],
                frame_type=params["frame_type"],
                channel=params["channel"],
            )
            self._detail_parser_key = key
        return self._detail_parser_obj

    def _reparse_frame_detail(self, result: dict) -> list:
        """按锁存的参数快照重解析单帧，返回其完整表格数据（失败时返回 []）。

        与批量解析共用 ``batch_parse_worker.parse_one_frame``（单一实现），
        入参用记录里锁存的 ``_input``（即提取后的原始帧 hex）与 ``_ed_type``
        （决定协议9 ED 三分支的走向）→ 逐字段等于批量解析当时的 ``_table_data``。
        """
        params = self._batch_parse_params or self._current_parse_params()
        parser = self._detail_parser_for(params)
        # 帧前跨帧状态必须还原：解析器实例带「A 帧赋值、B 帧读取」的属性
        # （协议9 为 `_CROSS_FRAME_STATE` 登记的三个），不还原时详情重解析的
        # 分支判定会与批量解析不同（实测 934/49,532 帧差一行 `⚠️ eFC数据不足`）；
        # 记录里没有 `_ctx` 时显式写回默认值，清掉本实例的历史残留
        apply_cross_frame_state(parser, params["index"], result.get("_ctx"))
        record = parse_one_frame(
            (result.get("_input", ""), result.get("_ed_type") or "", 0),
            0,
            protocol_index=params["index"],
            parser=parser,
            summary_fn=self._get_summary_from_table_data,
            type_name_fn=self._get_frame_type_name,
            ed_parse_fn=self._batch_ed_parser(self._batch_ed_wrapper),
            lead_lines=0,
            strip_map=None,
            log_fn=None,
        )
        return list(record.get("_table_data") or [])

    def _get_frame_table_data(self, index: int) -> list:
        """取第 ``index`` 帧的详情表格数据（详情按需 + LRU，上限 50 帧）。

        顺序：LRU 命中 → 记录里仍带 ``_table_data``（兼容旧路径/测试）→
        按 ``_has_detail`` 判据重解析。失败/异常帧（无可展示表格）返回 []，
        与去缓存前 ``result.get("_table_data", [])`` 的取值一致。
        任何异常都兜住返回 []（详情面板不能因一帧崩掉）。
        """
        try:
            if index < 0 or index >= len(self.batch_results):
                return []
            cached = self._detail_cache.get(index)
            if cached is not None:
                self._detail_cache.move_to_end(index)
                return cached
            result = self.batch_results[index]
            if "_table_data" in result:
                table_data = list(result.get("_table_data") or [])
            elif result.get("_has_detail"):
                table_data = self._reparse_frame_detail(result)
            else:
                table_data = []
        except Exception:  # noqa: BLE001 —— 详情路径不得因单帧异常影响界面
            table_data = []
        self._detail_cache[index] = table_data
        self._detail_cache.move_to_end(index)
        while len(self._detail_cache) > self._detail_cache_max:
            self._detail_cache.popitem(last=False)
        return table_data

    def _batch_detail_resolver(self):
        """返回「结果 dict → 详情表格数据」的解析器闭包（供导出/时序图注入）。

        导出/时序图拿到的是 ``self.batch_results`` 里的**同一批 dict**（含选中子集），
        故用 ``id() → 全局下标`` 映射回 ``_get_frame_table_data``，避免 O(n) 的
        ``list.index`` 或修改记录键集；逐条取用、用完即弃，不把整批详情物化成
        一个大 list（49,532 帧会重新回到 229 MB）。映射外的 dict（如测试自造）
        回落到其自带的 ``_table_data``。
        """
        index_by_id = {id(r): i for i, r in enumerate(self.batch_results)}

        def _resolve(result) -> list:
            idx = index_by_id.get(id(result))
            if idx is None:
                return list(result.get("_table_data") or [])
            try:
                return self._get_frame_table_data(idx)
            except Exception:  # noqa: BLE001 —— 导出不得因一帧异常整批失败
                return []

        return _resolve

    def _get_summary_from_table_data(
        self, table_data: list, protocol_index: int = None
    ) -> str:
        """从表格数据中提取摘要信息，取重要的前几个字段拼接。

        `protocol_index` 供后台线程传入参数快照（None = 主窗口当前协议）；
        本函数及其下游（_get_csg_new_gen_summary / _get_gw_new_gen_summary）
        均不读 widget，可在工作线程调用。
        """
        if not table_data:
            return "-"

        proto = self.current_protocol if protocol_index is None else protocol_index
        summary_parts = []

        if proto == 0:
            # 南网协议：提取 AFN 名称（comment）、SEQ 值、DI 业务说明（comment）
            afn_val = None
            seq_val = None
            di_desc = None
            for item in table_data:
                field_name = item[0]
                parsed_val = item[2]
                comment = item[3]
                if field_name == "应用功能码 (AFN)":
                    # AFN 的 parsed_val 为空，说明在 comment 中
                    afn_val = comment if comment else parsed_val
                elif field_name == "帧序列号 (SEQ)":
                    seq_val = parsed_val
                elif field_name == "数据标识 (DI)":
                    # DI 的业务说明在 comment 中
                    if comment and not di_desc:
                        di_desc = comment
            if di_desc:
                summary_parts.insert(0, f"DI:{di_desc}")
            if afn_val is not None:
                summary_parts.append(f"AFN:{afn_val}")
            if seq_val is not None:
                summary_parts.append(f"SEQ:{seq_val}")
            return " | ".join(summary_parts) if summary_parts else "-"

        elif proto == 7:
            # 国网协议：提取 AFN 名称、Fn 说明、传输方向
            afn_name = None
            fn_desc = None
            dir_desc = None
            for item in table_data:
                field_name = item[0]
                parsed_val = item[2]
                comment = item[3]
                if field_name == "应用功能码(AFN)":
                    afn_name = comment if comment else parsed_val
                elif field_name == "数据单元标识(DT)":
                    fn_desc = comment if comment else parsed_val
                elif "传输方向" in field_name:
                    dir_desc = (
                        "下行"
                        if str(parsed_val).strip() == "0"
                        else "上行"
                        if str(parsed_val).strip() == "1"
                        else "-"
                    )
            if dir_desc:
                summary_parts.append(dir_desc)
            if afn_name:
                summary_parts.append(f"AFN:{afn_name}")
            if fn_desc:
                summary_parts.append(fn_desc)
            return " | ".join(summary_parts) if summary_parts else "-"

        elif proto == 8:
            # 698.45：提取 APDU 类型、DIR+PRM、功能码
            apdu_type = None
            dir_prm = None
            func_desc = None
            for item in table_data:
                field_name = item[0]
                parsed_val = item[2]
                comment = item[3]
                if field_name == "  APDU类型":
                    apdu_type = str(parsed_val) if parsed_val else comment
                elif field_name == "  DIR+PRM":
                    dir_prm = str(parsed_val) if parsed_val else comment
                elif field_name == "  功能码":
                    func_desc = str(parsed_val) if parsed_val else comment
            if dir_prm:
                summary_parts.append(dir_prm)
            if func_desc:
                summary_parts.append(func_desc)
            if apdu_type:
                summary_parts.append(apdu_type)
            return " | ".join(summary_parts) if summary_parts else "-"

        elif proto == 12:
            # 模组化终端功能模块接口：方向 + 控制码 + 信息类 + APDU
            # 行名与 `modular_iface_parser.parse()` 输出保持一致（AGENTS.md 陷阱 44：
            # 摘要只认表内已有字段，不另立第二份判据）。
            dir_val = ctrl_val = dt_raw = apdu_val = None
            for item in table_data:
                field_name = item[0]
                parsed_val = str(item[2] or "").strip()
                comment = str(item[3] or "").strip()
                if field_name == "  传输方向(DIR)":
                    dir_val = {"0": "终端→模块", "1": "模块→终端"}.get(parsed_val)
                elif field_name == "  控制码":
                    ctrl_val = parsed_val or comment
                elif field_name == "    信息类标识(DT)":
                    dt_raw = parsed_val  # 形如 0x0000
                elif field_name == "    APDU 类型":
                    apdu_val = parsed_val or comment
            if dir_val:
                summary_parts.append(dir_val)
            if ctrl_val:
                summary_parts.append(ctrl_val)
            if dt_raw:
                # 名称单一来源：与解析器同一个 dt_name（模块信息类也在内）
                try:
                    from modular_iface_data import dt_name as _dt_name

                    summary_parts.append(f"信息类:{_dt_name(int(dt_raw, 16))}")
                except (TypeError, ValueError):
                    summary_parts.append(f"信息类:{dt_raw}")
            if apdu_val:
                summary_parts.append(apdu_val)
            return " | ".join(summary_parts) if summary_parts else "-"

        elif proto == 9:
            # 新一代载波协议：区分网络层报文(MPDU/MAC/MMTYPE)与应用层报文(业务标识)
            return self._get_csg_new_gen_summary(table_data)

        elif proto in (10, 11):
            # 国网新一代/HDC 1.0：网络标识/帧类型/TEI/MSDU序列/发送类型/报文等关键信息
            return self._get_gw_new_gen_summary(table_data)

        else:
            # 其他协议：取前几个非冗余字段
            for i, item in enumerate(table_data):
                if i >= 4:
                    break
                field_name = item[0]
                parsed_val = item[2]
                if any(
                    k in field_name
                    for k in ["帧起始", "格式", "长度", "校验", "结束标志"]
                ):
                    continue
                summary_parts.append(f"{parsed_val}")
            return " | ".join(summary_parts) if summary_parts else "-"
    # 测试模式/子模式的解析行名（协议9 表61 与协议10 检测扩展命令共用）——
    # 单一来源在批量共享核心 batch_core（桌面/Web 共用，见 _extract_test_mode_content）
    _TEST_MODE_SENTINELS = batch_core.TEST_MODE_SENTINELS

    @staticmethod
    def _extract_test_mode_content(table_data: list) -> str:
        """转发到 batch_core.extract_test_mode_content（桌面/Web 共用单源）。"""
        return batch_core.extract_test_mode_content(table_data)

    def _get_csg_new_gen_summary(self, table_data: list) -> str:
        """新一代载波协议(索引9)批量解析摘要生成

        区分报文类型并优先使用 MSDU 类型作为顶层分类：
        - 含 "管理消息类型(MMTYPE)" → "<MSDU类型> | MMTYPE:..."
        - 含 "定界符类型" (MPDU/MAC 物理层帧) → "<MSDU类型> | <定界符> | 源/目的TEI"
        - 含 "业务标识" (应用层) → "<MSDU类型> | <帧类型> | 业务标识:... | 方向 | 核心内容"

        table_data 格式: (field_name, raw_value, parsed_value, comment, byte_start, byte_end)
        """
        if not table_data:
            return "-"

        # ── 单次遍历同时完成四件事（协议9 摘要逐帧调用；原实现扫 table_data 4 遍）──
        #   ① 解析失败：提取失败原因（命中即返回）
        #   ② 字段索引：快速定位关键字段
        #   ③ ED 监控包装帧标题探测（原为对 fields 的键再扫一遍）
        #   ④ 测试装置表标题探测（命中才调 test_device_summary ⇒ 普通帧省掉一次
        #      函数调用与整表扫描；判定口径与 `batch_core.is_test_device_table` 一致）
        fields = {}
        ed_hdr = None
        has_test_device = False
        for item in table_data:
            name = item[0]
            if name.startswith("❌"):
                return item[3] if item[3] else "解析失败"
            fields[name] = item
            if ed_hdr is None and "监控包装头" in name:
                ed_hdr = name
            if not has_test_device and name.startswith("──"):
                has_test_device = (
                    name.startswith("── 测试装置") and "控制协议" in name
                )

        # ── 测试装置工装板/功能驱动板控制协议（优先，避免落到兜底只显示说明文案）──
        # 摘要的核心是**命令专属解析值**（衰减器X衰减值 / 仓电源与引脚 / 220V 状态），
        # 走 batch_core 的共享实现（桌面/Web 同源，单一来源）。
        if has_test_device:
            test_dev_summary = batch_core.test_device_summary(table_data)
            if test_dev_summary:
                return test_dev_summary

        # ── ED 监控包装帧（标题含「监控包装头」；文案按协议/布局由 batch_core 单源给出）──
        from batch_core import ed_wrapper_summary_name

        if ed_hdr:
            parts = [ed_wrapper_summary_name(ed_hdr)]
            ctrl1 = fields.get("控制域1")
            ctrl2 = fields.get("控制域2")
            if ctrl1:
                parts.append(str(ctrl1[2]))
            if ctrl2:
                parts.append(str(ctrl2[2]))
            data_len = fields.get("数据域长度")
            if data_len:
                dlen_val = data_len[2]
                if isinstance(dlen_val, int):
                    parts.append(f"数据:{dlen_val}字节")
                else:
                    parts.append(f"数据:{dlen_val}")
            # 有业务帧时提取业务帧类型（在"── 业务帧 ──"之后）
            business_found = False
            for item in table_data:
                if item[0].startswith("── 业务帧"):
                    business_found = True
                    continue
                if (
                    business_found
                    and item[0]
                    and not item[0].startswith(" ")
                    and "校验" not in item[0]
                    and "结束符" not in item[0]
                ):
                    parts.append(str(item[3] or item[2] or item[0]))
                    break
            return " | ".join(parts)

        # ── 公共：MSDU 类型作为顶层分类（若存在）──
        msdu_type_prefix = ""
        if "MSDU类型" in fields:
            msdu_type_name = fields["MSDU类型"][3]  # 如 "应用层报文"/"网络管理消息"
            if msdu_type_name:
                msdu_type_prefix = msdu_type_name

        # ── 应用层报文：含业务标识字段（优先于定界符类型展示）──
        if "业务标识" in fields:
            summary_parts = [msdu_type_prefix if msdu_type_prefix else "应用层"]
            # 0. 附带上层定界符类型（如果有）
            if "定界符类型" in fields:
                delim_desc = fields["定界符类型"][3]
                summary_parts.append(delim_desc)
            # 1. 帧类型域（业务大类）
            frame_type_item = fields.get("  帧类型域(D3~D0)")
            if frame_type_item:
                ft_comment = frame_type_item[3]  # "0 - 确认/否认"
                ft_name = (
                    ft_comment.split(" - ", 1)[1] if " - " in ft_comment else ft_comment
                )
                summary_parts.append(ft_name)
            # 2. 业务标识（名称 + 编号）
            svc_item = fields["业务标识"]
            svc_val = svc_item[2]
            svc_comment = svc_item[3]  # "业务标识 0 - 确认"
            svc_desc = (
                svc_comment.split(" - ", 1)[1] if " - " in svc_comment else svc_comment
            )
            try:
                summary_parts.append(f"业务标识:{svc_desc}(0x{int(svc_val):02X})")
            except (ValueError, TypeError):
                summary_parts.append(f"业务标识:{svc_desc}")
            # 3. 传输方向
            dir_item = fields.get("  传输方向位(D15)")
            if dir_item:
                dir_comment = dir_item[3]  # "0 - 下行(CCO→STA)"
                dir_name = (
                    dir_comment.split(" - ", 1)[1]
                    if " - " in dir_comment
                    else dir_comment
                )
                summary_parts.append(dir_name)
            # 4. 源/目的TEI
            if "源TEI" in fields:
                summary_parts.append(f"源TEI:{fields['源TEI'][2]}")
            if "目的TEI" in fields:
                summary_parts.append(f"目的TEI:{fields['目的TEI'][2]}")
            # 5. 核心内容：从业务数据单元子字段提取关键信息
            core = self._extract_csg_core_content(table_data)
            if core:
                summary_parts.append(core)
            return " | ".join(summary_parts)

        # ── 网络层：含 MMTYPE 字段（管理消息）──
        if "管理消息类型(MMTYPE)" in fields:
            mmtype_item = fields["管理消息类型(MMTYPE)"]
            mmtype_comment = mmtype_item[3]  # "管理消息: 关联请求(MMeAssocReq)"
            mmtype_val = mmtype_item[2]
            # 提取冒号后的消息名称
            mmtype_name = (
                mmtype_comment.split(":", 1)[1].strip()
                if ":" in mmtype_comment
                else mmtype_comment
            )
            prefix = msdu_type_prefix if msdu_type_prefix else "网络管理消息"
            try:
                # MMTYPE 解析值为 '0x0030' 形式字符串，需先去 0x 前缀按 16 进制解析
                mm_val = (
                    int(mmtype_val, 16)
                    if str(mmtype_val).lower().startswith("0x")
                    else int(mmtype_val)
                )
            except (ValueError, TypeError):
                mm_val = 0
            summary_parts = [f"{prefix} | MMTYPE:{mmtype_name}(0x{mm_val:04X})"]
            # 附带管理消息版本
            if "管理消息版本" in fields:
                ver = fields["管理消息版本"][2]
                summary_parts.append(f"版本{ver}")
            # 附带源/目的TEI
            if "源TEI" in fields:
                summary_parts.append(f"源TEI:{fields['源TEI'][2]}")
            if "目的TEI" in fields:
                summary_parts.append(f"目的TEI:{fields['目的TEI'][2]}")
            return " | ".join(summary_parts)

        # ── 网络层：MPDU/MAC 物理层帧（定界符类型字段）──
        if "定界符类型" in fields:
            delim_item = fields["定界符类型"]
            delim_desc = delim_item[3]  # "SOF帧" / "信标帧" / "选择确认帧(SACK)"
            delim_val = delim_item[2]
            prefix = msdu_type_prefix if msdu_type_prefix else "网络层"
            summary_parts = [f"{prefix} | {delim_desc}"]
            # 信标帧：额外显示信标类型（发现/代理/中央）
            if delim_desc == "信标帧":
                beacon_type = ""
                if "信标载荷头" in fields:
                    beacon_head_item = fields["信标载荷头"]
                    beacon_parsed = beacon_head_item[2]
                    if isinstance(beacon_parsed, str) and "类型:" in beacon_parsed:
                        idx = beacon_parsed.index("类型:") + 3
                        beacon_type = beacon_parsed[idx:].split(",")[0].split(" ")[0]
                if not beacon_type and "信标类型" in fields:
                    beacon_type = str(fields["信标类型"][3] or fields["信标类型"][2])
                if beacon_type:
                    summary_parts.append(f"信标类型:{beacon_type}")
                # 信标帧附带网络标识
                if "网络标识(SNID)" in fields:
                    summary_parts.append(f"SNID:{fields['网络标识(SNID)'][2]}")
            # SOF/SACK 帧附带源/目的TEI和帧序号
            if delim_desc in ("SOF帧", "选择确认帧(SACK)"):
                if "源TEI" in fields:
                    summary_parts.append(f"源TEI:{fields['源TEI'][2]}")
                if "目的TEI" in fields:
                    summary_parts.append(f"目的TEI:{fields['目的TEI'][2]}")
                if "发送序号" in fields:
                    summary_parts.append(f"序号:{fields['发送序号'][2]}")
            return " | ".join(summary_parts)

        # ── 兜底：MSDU 负载等未分类报文，取前几个有效字段 ──
        parts = []
        for item in table_data[:4]:
            fn, pv, desc = item[0], item[2], item[3]
            if any(k in fn for k in ["帧起始", "格式", "长度", "校验", "结束"]):
                continue
            parts.append(str(desc) if desc else str(pv))
        return " | ".join(parts) if parts else "-"

    def _extract_csg_core_content(self, table_data: list) -> str:
        """从新一代载波协议应用层报文中提取核心业务内容（用于摘要）

        根据帧类型+业务标识组合，提取最有信息量的字段：
          - 确认/否认：否认原因码
          - 数据传输帧：源/目的地址 + 数据长度
          - 命令帧：目标设备地址 + 命令参数
          - 其他：取业务数据单元中首个有意义的字段
        """
        fields = {item[0]: item for item in table_data}

        # ── 获取帧类型和业务标识 ──
        ft_desc = fields.get("  帧类型域(D3~D0)", ("", "", "", ""))[3]
        svc_desc = fields.get("业务标识", ("", "", "", ""))[3]
        # 从 "业务标识 N - 名称" 中提取业务名
        svc_name = svc_desc.split(" - ", 1)[1] if " - " in svc_desc else svc_desc

        # ── 测试帧（业务标识 0xF0）：优先体现测试模式/测试ID ──
        # 必须放在确认/否认、命令帧分支之前：测试帧的帧类型域是「命令帧」，
        # 否则会落到通用命令帧列表，测试模式信息被淹没。
        svc_item = fields.get("业务标识")
        if svc_item is not None and (
            str(svc_item[2]).strip() == "240"
            or "F0" in str(svc_item[1]).upper()
            or "测试帧" in str(svc_item[3])
        ):
            mode_text = self._extract_test_mode_content(table_data)
            if mode_text:
                return mode_text

        # ── 否认帧：显示否认原因 ──
        if "否认" in svc_name:
            deny_item = fields.get("否认原因码")
            if deny_item:
                return f"原因:{deny_item[3]}"
            return "否认"

        # ── 确认帧：显示确认状态 ──
        if "确认" in svc_name and "否认" not in svc_name:
            confirm_item = fields.get("确认/否认负载")
            if confirm_item:
                return confirm_item[3]  # "确认报文，无业务数据"
            return "确认"

        # ── 数据传输帧：源/目的地址 + 数据长度 ──
        if "数据传输" in ft_desc:
            parts = []
            src = fields.get("源地址")
            dst = fields.get("目的地址")
            if src:
                # 提取冒号后的实际地址值
                addr = src[3].split(": ", 1)[1] if ": " in src[3] else src[2]
                parts.append(f"源:{addr}")
            if dst:
                addr = dst[3].split(": ", 1)[1] if ": " in dst[3] else dst[2]
                parts.append(f"目的:{addr}")
            data_len = fields.get("转发数据长度")
            if data_len:
                parts.append(f"{data_len[2]}字节")
            return " | ".join(parts) if parts else svc_name

        # ── 命令帧：命令名 + 关键参数 ──
        if "命令" in ft_desc:
            parts = [svc_name]
            # 提取设备地址（若有）
            dev_addr = fields.get("设备地址")
            if dev_addr:
                addr = (
                    dev_addr[3].split(": ", 1)[1]
                    if ": " in dev_addr[3]
                    else dev_addr[2]
                )
                parts.append(f"设备:{addr}")
            # 提取命令关键参数（非保留/非控制域的有意义字段）
            cmd_skip = {
                "帧类型域",
                "传输方向位",
                "启动标志",
                "响应标识",
                "业务扩展域",
                "任务优先级",
                "保留",
                "业务标识",
                "帧序号",
                "帧长",
                "报文端口号",
                "报文标识符",
                "应用版本号",
                "业务数据单元",
                "控制域",
            }
            for fn, item in fields.items():
                if fn.startswith("  "):
                    continue  # 跳过控制域位域子字段
                if any(k in fn for k in cmd_skip):
                    continue
                desc = item[3]
                val = item[2]
                if (
                    desc
                    and "保留" not in desc
                    and "默认" not in desc
                    and "未解析" not in desc
                ):
                    if val and str(val) != "0" and str(val) != "0字节":
                        # 避免与 svc_name 重复
                        if desc[: len(svc_name)] != svc_name:
                            parts.append(f"{desc[:30]}")
            return " | ".join(parts[:4])  # 最多4段

        # ── 兜底：取业务数据单元中首个有意义的字段 ──
        skip_keys = [
            "控制域",
            "传输方向",
            "启动标志",
            "响应标识",
            "业务扩展域标识",
            "任务优先级",
            "保留(D",
            "帧类型域",
            "报文端口号",
            "报文标识符",
            "应用版本号",
            "帧序号",
            "帧长",
            "业务标识",
            "保留",
            "MSDU",
            "VLAN",
            "级联",
            "物理块",
            "MPDU",
            "MAC",
        ]
        for fn, item in fields.items():
            if any(k in fn for k in skip_keys):
                continue
            desc = item[3]
            if not desc or desc in ("保留", "保留字段", "保留位默认填0"):
                continue
            if any(k in desc for k in ["未解析", "可能为填充", "尚未实现"]):
                continue
            if fn in ("业务数据单元", "确认/否认负载", "管理消息数据"):
                continue
            return f"{fn.strip()}:{desc[:30]}"
        return svc_name if svc_name else ""

    def _get_gw_new_gen_summary(self, table_data: list) -> str:
        """国网新一代(索引10)监控/批量摘要生成

        体现监控工具关注的关键业务信息：
          网络标识(NID) | 帧类型(信标/SOF/选择确认/网间协调) | 管理消息类型(MMTYPE) |
          源→目的TEI | MSDU序列号 | 发送类型(单播/广播) | MSDU类型 |
          应用层端口/报文ID(方向)/报文序号/规约类型/数据长度

        table_data 格式: (field, raw, parsed, comment, byte_start, byte_end, is_child)
        """
        if not table_data:
            return "-"

        # 解析失败：直接返回失败原因
        for item in table_data:
            if str(item[0]).startswith("❌"):
                return item[3] if item[3] else "解析失败"

        # 以去除缩进的字段名建立索引（首个出现优先：FC 在 MAC/应用层之前）
        fs = {}
        for item in table_data:
            key = str(item[0]).strip()
            if key:
                fs.setdefault(key, item)

        def val(name):
            it = fs.get(name)
            return str(it[2]).strip() if it and it[2] not in (None, "") else ""

        def cmt(name):
            it = fs.get(name)
            return str(it[3]).strip() if it and it[3] not in (None, "") else ""

        parts = []

        # 1. 网络标识(NID)
        nid = val("网络标识(NID)")
        if nid:
            parts.append(f"NID:{nid}")

        # 2. 帧类型（定界符类型）。协议10 comment 形如 "DT=1: SOF帧"；
        #    协议11 字段名为「定界符类型(DT)」，comment 即「信标帧/SOF帧」等。
        delim = cmt("定界符类型") or cmt("定界符类型(DT)")
        frame_type_name = ""
        if delim:
            frame_type_name = delim.split(":", 1)[1].strip() if ":" in delim else delim
            sof_sub = val("帧类型")  # SOF帧子类型: 数据帧/信道探测帧
            if "SOF" in frame_type_name and sof_sub:
                parts.append(f"{frame_type_name}({sof_sub})")
            else:
                parts.append(frame_type_name)

        # 信标帧：补「中央信标/发现信标/代理信标」等类型（协议11 现场扫读用）
        beacon_type = cmt("信标类型") or val("信标类型")
        if beacon_type and "保留" not in str(beacon_type):
            if frame_type_name and "信标" in frame_type_name:
                if beacon_type not in frame_type_name:
                    parts.append(str(beacon_type))
            elif not frame_type_name:
                parts.append(f"信标:{beacon_type}")

        # 3. 管理消息类型(MMTYPE)：如 关联确认(MMeAssocCnf)/发现列表
        #    字段名两协议不同构：协议10=`管理消息类型(MMTYPE)`，协议11=`消息类型(MMTYPE)`
        #    （hdc10_mme_parser）。pb_only 批量时网络层帧只有 MAC+MME，
        #    摘要若不带 MMTYPE 则整批「0→1 | msduSeq:x | 单播」无法扫读。
        mmtype = cmt("管理消息类型(MMTYPE)") or cmt("消息类型(MMTYPE)")
        mmtype_code = val("管理消息类型(MMTYPE)") or val("消息类型(MMTYPE)")
        if not mmtype:
            # 区头 comment 形如 "MMTYPE: 0x0000 (关联请求)"
            for item in table_data:
                key = str(item[0]).strip()
                if "网络管理消息" in key and len(item) >= 4 and item[3]:
                    c = str(item[3]).strip()
                    if "MMTYPE" in c:
                        mmtype = c
                        break
        if mmtype:
            text = mmtype[7:].strip() if mmtype.startswith("MMTYPE:") else mmtype
            if mmtype_code and mmtype_code not in text:
                parts.append(f"MMTYPE:{mmtype_code}({text})")
            else:
                parts.append(f"MMTYPE:{text}")

        # 4. 源→目的TEI：优先 FC 级，其次 MAC 级原始源/目的
        src = val("源TEI") or val("原始源TEI")
        dst = val("目的TEI") or val("原始目的TEI")
        if src or dst:
            parts.append(f"{src or '?'}→{dst or '?'}")

        # 5. MSDU序列号
        seq = val("MSDU序列号")
        if seq:
            parts.append(f"msduSeq:{seq}")

        # 6. 发送类型（单播/本地广播/...）
        send_type = cmt("发送类型")
        if send_type and "保留" not in send_type:
            parts.append(send_type)

        # 7. MSDU类型（非保留且未在别处体现）
        #    「网络管理消息」优先由 MMTYPE 段体现；无 MMTYPE 时仍要展示，
        #    否则 pb_only 网络层帧摘要只剩 TEI/序号。
        msdu_type = cmt("MSDU类型")
        has_mmtype = any(p.startswith("MMTYPE:") for p in parts)
        if msdu_type and "保留" not in msdu_type:
            if "网络管理" in msdu_type and has_mmtype:
                pass
            else:
                parts.append(msdu_type)

        # 8. 应用层：报文端口 + 报文ID(含方向) + 报文序号 + 规约类型 + 数据长度
        port = val("报文端口号")
        if port:
            parts.append(f"端口:{port}")
        msg_id = val("报文ID")
        if msg_id:
            # 方向(上行/下行)在"应用层报文"行 comment 中，如 "...报文ID=xxx 下行"
            app_cmt = cmt("应用层报文")
            direction = ""
            for d in ("下行", "上行"):
                if d in app_cmt:
                    direction = d
                    break
            parts.append(
                f"报文:{msg_id}({direction})" if direction else f"报文:{msg_id}"
            )
        # 业务名 + 关键业务字段：应用层报文的核心内容（协议11 的业务名在
        # 「── 业务数据 ──」区头行，协议10 已由「报文ID」解析值给出）——
        # 现场反馈：缺少这两段时同一批升级帧摘要完全相同，无法扫读。
        # 仅应用层报文（有端口号/报文ID）才提取：网络层/物理层帧没有业务语义，
        # 否则 `定界符类型`/`网络类型` 之类的帧字段会被当成业务字段混进摘要。
        if port or msg_id:
            biz_name, biz_fields = _gw_app_biz_summary(table_data)
            if biz_name and biz_name != msg_id and biz_name not in " | ".join(parts):
                parts.append(biz_name)
            parts.extend(biz_fields)
        # 报文序号（STA 应答时返回）
        msg_seq = val("报文序号")
        if msg_seq:
            parts.append(f"序号:{msg_seq}")
        # 规约类型（如 DL/T 698.45），精简展示
        proto = val("规约类型")
        if proto:
            parts.append(f"规约:{proto.replace('DL/T ', '')}")
        dlen = val("转发数据长度")
        if dlen:
            parts.append(f"数据:{dlen}")

        # 9. 测试类报文（通信测试/检测扩展命令）：体现测试模式/配置操作
        #    仅在三个哨兵行之一存在时才调用，避免 helper 对同名字段误提取（协议10 无 0xF0 概念）
        if any(
            str(item[0]).strip() in self._TEST_MODE_SENTINELS for item in table_data
        ):
            test_mode_text = self._extract_test_mode_content(table_data)
            if test_mode_text:
                parts.append(test_mode_text)

        return " | ".join(parts) if parts else "-"

    def _extract_frames_for_protocol(self, text: str, protocol_index: int) -> list:
        """根据协议提取对应格式的帧（策略选择由 protocol_registry 驱动）"""
        import re

        strategy = protocol_registry.get_protocol(protocol_index).extract_strategy
        if strategy == "ft12_68":
            # 南网/国网：68开头，16结束，FT1.2帧格式
            clean = re.sub(r"[^0-9A-Fa-f]", "", text).upper()
            return self._extract_68_frames(clean)
        if strategy == "modular":
            # 模组化接口：68 + L(数据域长度) + … + FCS + 16；整帧 = L+8
            clean = re.sub(r"[^0-9A-Fa-f]", "", text).upper()
            return self._extract_modular_frames(clean)
        if strategy == "yw645":
            # 依瓦定制645：68 + 6B 地址 + 68 + COMMAND + L + … + CS + 16；
            # 整帧 = 数据域长度 + 12（唯一实现在 yw645_wire.extract_yw645_frames，Web 端同源）。
            # ⚠ 数据域已 +0x33，0x16 可为合法数据字节 ⇒ 只能按长度域定位帧尾（prd F5）。
            clean = re.sub(r"[^0-9A-Fa-f]", "", text).upper()
            return self._extract_yw645_frames(clean)
        if strategy == "csg_uplink":
            # 南网上行通信规约：68 + L(2B 小端) + L(重复一次) + 68 + C + A + … + CS + 16，
            # 整帧 = L + 8（唯一实现在 csg_uplink_wire.extract_csg_uplink_frames，Web 端同源）。
            clean = re.sub(r"[^0-9A-Fa-f]", "", text).upper()
            return self._extract_csg_uplink_frames(clean)
        if strategy == "dlt698_45":
            # 698.45：68开头，16结束，但长度域定义不同
            clean = re.sub(r"[^0-9A-Fa-f]", "", text).upper()
            return self._extract_69845_frames(clean)
        if strategy == "generic":
            clean = re.sub(r"[^0-9A-Fa-f]", "", text).upper()
            return self._extract_generic_frames(clean, min_len=4, max_len=256)
        if strategy == "hdlc":
            clean = re.sub(r"[^0-9A-Fa-f]", "", text).upper()
            return self._extract_hdlc_frames(clean)
        if strategy == "wrapper":
            return self._extract_wrapper_frames(text)
        if strategy == "csg_line":
            # 监控前缀已在 parse_batch 中通过 _strip_csg_monitor_prefix 剥离
            return self._extract_csg_new_gen_frames(text)
        if strategy == "gw_line_min4":
            # 前缀已在 parse_batch 中通过 _strip_gw_new_gen_prefix 剥离
            return self._extract_line_frames(text, protocol_index, min_len=4)
        # line / 默认：每行一帧
        return self._extract_line_frames(text, protocol_index, min_len=1)

    def _extract_line_frames(
        self, text: str, protocol_index: int, min_len: int = 1
    ) -> list:
        """按行提取帧（每行一帧）；双模协议（10/11）的 ED..EE 包装行先解包。

        监控日志把 ED 包装帧（可能一行拼多帧）原样贴进来时，必须剥离
        ``ED(6B) + 数据域公共头``（plc2 9B / gx 8B）才是 FC+PB 业务帧；否则首字节
        0xED 会被当成应用层端口号解析（用户报障：协议11 下 ED 帧被解析成
        「应用层报文」）。解包实现与批量共享核心 ``batch_core`` 同源
        （协议9 走 csg_line 策略，其提取函数已含同等逻辑）。
        """
        from batch_core import unwrap_ed_line

        frames = []
        for i, raw_line in enumerate(text.splitlines()):
            line = raw_line.strip()
            if not line or len(line) < min_len:
                continue
            if protocol_index in (10, 11):
                unwrapped = unwrap_ed_line(line, protocol_index)
                if unwrapped is not None:
                    for frame_hex, ed_type in unwrapped:
                        frames.append((frame_hex, ed_type, i))
                    continue
            frames.append((line, "", i))
        return frames

    def _extract_wrapper_frames(self, text: str) -> list:
        """
        从文本中提取Wrapper帧
        Wrapper格式: 版本(2B) + 源端口(2B) + 目的端口(2B) + 长度(2B) = 8字节头部
        版本固定为 0x0001
        支持处理带日志前缀的格式，如 "WRAPPER[1] Sent 0001000000010000003B ..."
        """
        import re

        frames = []

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            # 提取连续的长串十六进制数据（至少16个字符）
            # 这样 WRAPPER 中的零散字母不会被误认为数据
            hex_matches = re.findall(r"[0-9A-Fa-f]{16,}", line)
            if not hex_matches:
                continue

            for hex_pattern in hex_matches:
                hex_pattern = hex_pattern.upper()

                # 扫描整个十六进制字符串，寻找Wrapper头部 (0001xxxx)
                i = 0
                while i <= len(hex_pattern) - 16:  # 至少需要8字节(16字符)头部
                    # 检查是否是Wrapper头部: 版本=0001
                    if hex_pattern[i : i + 4] == "0001":
                        # 解析Wrapper头部的长度字段
                        apdu_len = int(hex_pattern[i + 12 : i + 16], 16)

                        # 验证长度合理性（允许apdu_len=0，因为数据可能被截断）
                        if 0 <= apdu_len <= 8192:
                            # 计算完整帧长度: 8字节头部 + apdu_len
                            frame_len = 16 + apdu_len * 2

                            if i + frame_len <= len(hex_pattern):
                                # 提取完整帧
                                frame_hex = hex_pattern[i : i + frame_len]
                                frames.append(frame_hex)
                                i += frame_len
                                continue
                            else:
                                # 数据被截断，但仍提取可用的头部+部分数据
                                frame_hex = hex_pattern[i:]
                                frames.append(frame_hex)
                                break
                    i += 2

        return frames if frames else [re.sub(r"[^0-9A-Fa-f]", "", text).upper()]

    def _extract_hdlc_frames(self, clean: str) -> list:
        """提取HDLC帧（7E开头，7E结束）"""
        frames = []
        i = 0
        while i < len(clean) - 3:
            # 找下一个7E起始
            pos = clean.find("7E", i)
            if pos == -1:
                break
            # 找下一个7E结束
            end = clean.find("7E", pos + 2)
            if end == -1:
                # 如果没找到结束，直接取到结尾或者最大长度
                end = min(pos + 512, len(clean))
            candidate = clean[pos : end + 2]
            if len(candidate) >= 6:  # 至少3字节
                frames.append(candidate)
            i = end + 2
        return frames

    def _extract_68_frames(self, clean: str) -> list:
        """提取南网68格式帧（Q/CSG1209021-2019 FT1.2）

        帧格式: 68H | L(2B小端) | C(1B) | 用户数据(L-6字节) | CS(1B) | 16H
        L = 帧总字节数（含起始符、长度域、控制域、校验和、结束符）
        验证规则:
          1. 起始字符 = 68H
          2. L >= 8（最小帧长度）
          3. 帧末尾 = 16H
          4. 校验和：从控制域到用户数据末尾的所有字节累加和 mod 256
        """
        frames = []
        i = 0
        while i < len(clean) - 7:
            # 找下一个 68 起始
            pos = clean.find("68", i)
            if pos == -1:
                break

            # 尝试按长度域解析帧边界
            if pos + 6 > len(clean):
                i = pos + 2
                continue

            try:
                low_byte = int(clean[pos + 2 : pos + 4], 16)
                high_byte = int(clean[pos + 4 : pos + 6], 16)
                length = low_byte | (high_byte << 8)
            except ValueError:
                i = pos + 2
                continue

            # L 至少为 8（起始1 + 长度2 + 控制1 + 校验1 + 结束1 + 用户数据至少3）
            if length < 8 or length > 2048:
                i = pos + 2
                continue

            frame_hex_len = length * 2

            # 检查数据是否足够
            if pos + frame_hex_len > len(clean):
                i = pos + 2
                continue

            candidate = clean[pos : pos + frame_hex_len]

            # 验证结束符 = 16H
            if candidate[-2:] != "16":
                i = pos + 2
                continue

            # 通过长度域和结束符验证，接受此帧（不校验CS，由解析器负责校验）
            frames.append(candidate)
            i = pos + frame_hex_len
            continue

        return frames

    def _extract_69845_frames(self, clean: str) -> list:
        """提取698.45格式帧（DL/T 698.45-2017）

        帧格式: 68H | L(2B小端) | C(1B) | SA | CA | HCS(2B) | APDU | FCS(2B) | 16H
        **L 语义（协议文档 6.2.2 a）：帧数据长度值 = 传输帧中不包含起始字符和结束字符
        的数据长度 ⇒ 帧总长度 = L + 2**（L 本身含两个长度域字节）。标准附录 H.1.1
        「登录」示例自证：``68 1E 00 81 … FCS FCS 16`` 共 **32** 字节、L=0x001E=30。
        历史上的 ``L + 4`` 比真实值多 2 字节，末字节自证必然失败 ⇒ 协议8 批量提取
        恒返回空（1.23.60 修复）。
        验证规则:
          1. 起始字符 = 68H
          2. L >= 8（最小有效长度）
          3. 帧末尾 = 16H
          4. 长度域一致性: 实际帧长 = L + 2
        """
        frames = []
        i = 0
        while i < len(clean) - 7:
            pos = clean.find("68", i)
            if pos == -1:
                break

            if pos + 6 > len(clean):
                i = pos + 2
                continue

            try:
                low_byte = int(clean[pos + 2 : pos + 4], 16)
                high_byte = int(clean[pos + 4 : pos + 6], 16)
                length = low_byte | (high_byte << 8)
            except ValueError:
                i = pos + 2
                continue

            # L 至少为 8（控制1 + SA至少1 + CA1 + HCS2 + FCS2 + APDU至少1）
            if length < 8 or length > 2048:
                i = pos + 2
                continue

            # 698.45: 帧总长度 = L + 2（6.2.2 a：L 不含首尾定界符，且含两个长度字节）
            total_len = length + 2
            frame_hex_len = total_len * 2

            if pos + frame_hex_len > len(clean):
                i = pos + 2
                continue

            candidate = clean[pos : pos + frame_hex_len]

            # 验证结束符 = 16H
            if candidate[-2:] != "16":
                i = pos + 2
                continue

            frames.append(candidate)
            i = pos + frame_hex_len
            continue

        return frames

    def _extract_modular_frames(self, clean: str) -> list:
        """提取模组化终端功能模块接口帧。

        帧: 68H | L(2B LE, bit0~11=数据域长度) | C(2B) | Data | FCS(2B) | 16H
        整帧长度 = 数据域长度 + 8。
        """
        frames = []
        i = 0
        while i < len(clean) - 7:
            pos = clean.find("68", i)
            if pos == -1:
                break
            if pos + 6 > len(clean):
                i = pos + 2
                continue
            try:
                low = int(clean[pos + 2 : pos + 4], 16)
                high = int(clean[pos + 4 : pos + 6], 16)
                data_len = (low | (high << 8)) & 0x0FFF
            except ValueError:
                i = pos + 2
                continue
            if data_len > 4095:
                i = pos + 2
                continue
            total_len = data_len + 8
            frame_hex_len = total_len * 2
            if pos + frame_hex_len > len(clean):
                i = pos + 2
                continue
            candidate = clean[pos : pos + frame_hex_len]
            if candidate[-2:] != "16":
                i = pos + 2
                continue
            frames.append(candidate)
            i = pos + frame_hex_len
        return frames

    def _extract_yw645_frames(self, clean: str) -> list:
        """提取依瓦定制645（协议13）帧。

        唯一实现在 ``yw645_wire.extract_yw645_frames``（零 Qt 纯函数），桌面与 Web 端
        共用同一份，**不得在此再写第二份切帧逻辑**（AGENTS.md 陷阱 31 的漂移根因）。
        两道自证：``data[7] == 0x68`` + 按长度域落位后末字节 ``16H``。
        """
        from yw645_wire import extract_yw645_frames

        return extract_yw645_frames(clean)

    def _extract_csg_uplink_frames(self, clean: str) -> list:
        """提取南网上行通信规约（协议14）帧。

        唯一实现在 ``csg_uplink_wire.extract_csg_uplink_frames``（零 Qt 纯函数），
        桌面与 Web 端共用同一份。按帧首 68H + 长度域定长定位帧尾：规范形态
        （``68 L(2B) L(2B 重复) 68``，整帧 = L+8）优先，兼容历史异形形态
        （单个 2 字节小端 L / FT1.2 双同值单字节，整帧 = L+6）。
        """
        from csg_uplink_wire import extract_csg_uplink_frames

        return extract_csg_uplink_frames(bytes.fromhex(clean))

    def _extract_generic_frames(
        self, clean: str, min_len: int = 4, max_len: int = 512
    ) -> list:
        """通用帧提取：按行或直接提取完整有效hex字符串"""
        if len(clean) >= min_len * 2 and len(clean) <= max_len * 2:
            return [clean] if len(clean) % 2 == 0 else []
        return []

    def _extract_csg_new_gen_frames(self, text: str) -> list:
        """提取新一代载波协议帧

        输入 text 已经过 _clean_hex_input(keep_newlines=True) 清洗，
        且监控前缀已在 parse_batch 中剥离，此处为纯 hex 字符串（含换行）。

        处理规则:
          - 按行分割（每行一帧，兼容多帧批量输入）
          - 去除空白后只保留偶数长度的有效 hex 行
          - 过滤过短的行（< 4 字节，无法构成最小应用层报文）
          - **ED 监控帧处理**：若帧以 ED 开头，解析 ED..EE 包装头，提取业务帧

        Returns:
            list of tuple: [(frame_hex, ed_data_type, line_no), ...]
              - frame_hex: 提取后的帧 hex 字符串
              - ed_data_type: ED 数据类型描述（如 "FC数据"、"FC+Payload数据"），非 ED 帧为空字符串
              - line_no: 该帧在输入文本中的行号（供结果回跳日志定位）
        """
        frames = []
        for line_no, raw_line in enumerate(text.splitlines()):
            line = raw_line.strip()
            if not line:
                continue
            # 仅保留 hex 字符（清洗后应已是纯 hex，此处兜底）
            clean_line = "".join(
                c for c in line if c in "0123456789ABCDEFabcdef"
            ).upper()
            if len(clean_line) < 8:  # 至少 4 字节
                continue
            if len(clean_line) % 2 != 0:
                # 奇数长度：丢弃末尾字符以保证字节对齐
                clean_line = clean_line[:-1]

            ed_data_type = ""
            # ED 监控帧处理：解析 ED..EE 包装头，提取业务帧
            if clean_line.startswith("ED"):
                business_hex, data_type = self._extract_business_from_ed_frame(
                    clean_line,
                    wrapper=self._ed_wrapper_for_frame(bytes.fromhex(clean_line)),
                )
                if business_hex:
                    clean_line = business_hex
                    ed_data_type = data_type
                elif data_type.startswith("ED:"):
                    # 合法 ED 帧但无业务数据（控制报文、空数据报文等）
                    # 保留原始 ED hex，标记类型供后续解析识别
                    ed_data_type = data_type
                # 其余情况（ED 解析失败）保留原始帧，ed_data_type 为空

            frames.append((clean_line, ed_data_type, line_no))
        return frames

    def _extract_business_from_ed_frame(
        self, hex_str: str, wrapper: str = None
    ) -> tuple:
        """从 ED..EE 监控包装帧中提取业务数据（PLC2.0 9B / 广西台体 8B 公共头）

        包结构: ED(1)+帧长(2,LE)+控制域1(1)+控制域2(1)+EF(1)+数据域(变长)+CS(1)+EE(1)
        数据域公共头(9字节): 物理信道(1)+时间戳(4,LE)+物理块个数(1)+保留(1)+物理块长度(2,LE)

        注意：监控日志可能在 ED 帧后附加 FF EE 标记，需要正确处理
        Args:
            wrapper: "plc2"/"gx"；None/非法 → 按当前下拉（auto 时逐帧打分识别）

        Returns:
            (business_hex, data_type_desc) 成功时返回业务数据hex和类型描述
            ("", "") 解析失败
        """
        try:
            frame_bytes = bytes.fromhex(hex_str)
        except ValueError:
            return "", ""

        if wrapper not in ("plc2", "gx"):
            wrapper = self._ed_wrapper_for_frame(frame_bytes)
        n = len(frame_bytes)
        if n < 8 or frame_bytes[0] != 0xED:
            return "", ""

        # 解析帧长字段
        frame_len = frame_bytes[1] | (frame_bytes[2] << 8)
        if frame_len < 4 or frame_len > 4096:
            return "", ""

        # 计算预期的整包长度
        expected_total = frame_len + 4  # ED(1) + 帧长(2) + [内容:frame_len字节] + EE(1)

        # 查找实际的 EE 终止符位置
        # 优先使用帧长计算的位置，如果该位置不是 EE，则搜索
        ee_pos = -1
        if expected_total <= n and frame_bytes[expected_total - 1] == 0xEE:
            ee_pos = expected_total - 1
        else:
            # 帧长字段可能不准确，或者后面有多余数据(如 FF EE 标记)
            # 从位置6后搜索第一个 EE
            for i in range(6, min(n, expected_total + 10)):  # 允许一定偏差
                if frame_bytes[i] == 0xEE:
                    ee_pos = i
                    break

        if ee_pos < 0:
            return "", ""  # 找不到 EE 终止符

        # 验证 EF 起始符
        if frame_bytes[5] != 0xEF:
            return "", ""

        # 计算实际的数据范围
        # ED帧结构: ED(0) + 帧长(1-2) + ctrl1(3) + ctrl2(4) + EF(5) + 数据域 + CS + EE(ee_pos)
        data_start = 6
        data_end = ee_pos - 1  # 排除 CS(ee_pos-1) 和 EE(ee_pos)

        ctrl1 = frame_bytes[3]
        ctrl2 = frame_bytes[4]

        # 数据域为空：合法 ED 帧但没有业务数据（控制报文、空数据报文等）
        if data_end <= data_start:
            if ctrl1 == 0x01:
                return "", f"ED:控制报文(0x{ctrl2:02X})"
            elif ctrl1 == 0x00:
                return "", f"ED:数据报文(空,0x{ctrl2:02X})"
            else:
                return "", f"ED:空数据(0x{ctrl1:02X}/0x{ctrl2:02X})"

        data = frame_bytes[data_start:data_end]
        data_len = len(data)

        # 控制报文或非标准数据子类型中可能携带测试装置通信控制协议。
        # 该协议不是载波 FC/PB 业务帧，但属于 ED 数据域的有效内容，应交给协议9解析器展开。
        if self.current_protocol == 9:
            from csg_new_gen_parser import CSGNewGenParser

            if CSGNewGenParser()._parse_test_device_control(data) is not None:
                return frame_bytes[
                    : ee_pos + 1
                ].hex().upper(), f"测试装置控制(0x{ctrl2:02X})"

        # 非数据报文或数据域不足，返回空
        hdr_len = 8 if wrapper == "gx" else 9
        if ctrl1 != 0x00 or ctrl2 not in (0x01, 0x02, 0x03) or data_len < hdr_len:
            # 控制报文或非标准数据子类型但有数据域：仍然视为合法 ED 帧，无业务数据
            if ctrl1 == 0x01:
                return "", f"ED:控制报文(0x{ctrl2:02X})"
            else:
                return "", f"ED:非业务帧(0x{ctrl1:02X}/0x{ctrl2:02X})"

        # 跳过公共头（PLC2.0=9 字节 / 广西台体=8 字节），提取业务数据
        business = data[hdr_len:]
        if len(business) < 4:
            # 公共头完整但业务数据不足：仍按合法 ED 数据帧处理
            return "", f"ED:数据报文(业务不足,0x{ctrl2:02X})"

        # 根据 ctrl2 确定数据类型描述
        ctrl2_desc = {
            0x01: "FC数据",
            0x02: "FC+Payload数据",
            0x03: "Payload数据",
        }.get(ctrl2, f"未知(0x{ctrl2:02X})")

        return business.hex().upper(), ctrl2_desc

    def _run_cli_preprocessor(self):
        """执行通用预处理命令链：读取 batch_input → 解析命令 → 结果回填"""
        cmd_text = self._pp_cmd_combo.currentText().strip()
        if not cmd_text:
            QMessageBox.warning(
                self,
                "警告",
                "请输入预处理命令！\n"
                '示例: find "tcp data:" excluding "len:\\d+: "\n'
                "输入 ? 查看所有可用命令。",
            )
            return

        input_text = self.batch_input.toPlainText().strip()
        if not input_text:
            QMessageBox.warning(self, "警告", "输入框为空，请先粘贴或加载报文！")
            return

        try:
            # 用 split_commands 拆分（兼容中文输入法全角状态下打出的空格/引号）
            from pp_cli import parse_and_run, split_commands

            commands = split_commands(cmd_text)
        except ValueError as e:
            QMessageBox.warning(
                self,
                "命令解析错误",
                f"命令格式错误: {e}\n请检查引号是否匹配。\n"
                "提示: 命令与参数之间用半角空格分隔，含空格的参数用半角双引号包裹（中文输入法请切到半角）。",
            )
            return

        try:
            result = parse_and_run(input_text, commands)

            if not result.strip():
                QMessageBox.information(
                    self, "预处理结果", "预处理后无有效数据（所有行被过滤）"
                )
                return

            # 回填到输入框
            self.batch_input.setPlainText(result)
            frame_count = len([l for l in result.splitlines() if l.strip()])
            self.update_stats(f"预处理完成（{cmd_text}）：{frame_count} 行")

        except Exception as e:
            QMessageBox.critical(self, "预处理失败", f"执行预处理命令失败：\n{e}")

    def _load_pp_commands(self):
        """从 config.json 加载预处理命令列表"""
        commands = list(self._pp_preset_commands)
        if self._config_path.exists():
            try:
                with open(self._config_path, encoding="utf-8") as f:
                    config = json.load(f)
                saved = config.get("pp_commands", [])
                # 合并：预设命令在前，用户保存的在后，去重
                seen = set()
                merged = []
                for c in commands + saved:
                    if c not in seen:
                        seen.add(c)
                        merged.append(c)
                commands = merged
            except Exception:
                pass
        self._pp_cmd_combo.clear()
        self._pp_cmd_combo.addItems(commands)

    def _save_pp_command(self):
        """保存当前输入框中的命令到常用列表"""
        cmd = self._pp_cmd_combo.currentText().strip()
        if not cmd:
            QMessageBox.warning(self, "警告", "命令为空，无法保存")
            return
        # 检查是否已存在
        idx = self._pp_cmd_combo.findText(cmd)
        if idx >= 0:
            self._pp_cmd_combo.setCurrentIndex(idx)
            return  # 已存在，直接选中

        self._pp_cmd_combo.addItem(cmd)
        self._pp_cmd_combo.setEditText(cmd)
        self._persist_pp_commands()
        self.update_stats(f"已保存预处理命令: {cmd}")

    def _delete_pp_command(self):
        """删除下拉列表中选中的命令"""
        cmd = self._pp_cmd_combo.currentText().strip()
        if not cmd:
            return
        idx = self._pp_cmd_combo.findText(cmd)
        if idx < 0:
            return
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要从常用列表中删除以下命令吗？\n\n{cmd}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._pp_cmd_combo.removeItem(idx)
            self._persist_pp_commands()

    def _persist_pp_commands(self):
        """将当前命令列表持久化到 config.json 的 pp_commands 段"""
        config: dict[str, Any] = {}
        if self._config_path.exists():
            try:
                with open(self._config_path, encoding="utf-8") as f:
                    config = json.load(f)
            except Exception:
                config = {}
        commands = [
            self._pp_cmd_combo.itemText(i) for i in range(self._pp_cmd_combo.count())
        ]
        config["pp_commands"] = commands
        try:
            atomic_write_json(self._config_path, config)
        except Exception as e:
            print(f"[预处理命令保存失败] {e}")

    def _show_pp_help(self):
        """显示预处理命令帮助"""
        from pp_cli import COMMANDS

        lines = ["通用文本预处理命令（支持正则）:\n"]
        for name, info in COMMANDS.items():
            lines.append(f"  {name:15s} {info['help']}")
        lines.append("\n命令链示例:")
        lines.append('  find "tcp data:"')
        lines.append('  find "tcp data:" excluding "len:\\d+: "')
        lines.append('  find "60F0" excluding "mrd:" dedup')
        lines.append('  find "nwk:" replace ".*nwk:" "NWK:" head 10')
        lines.append("  hex_extract")
        lines.append("\n书写规则:")
        lines.append("  命令与参数之间用半角空格分隔，含空格的参数用半角双引号包裹")
        lines.append('  例: find "tcp data:"（全角空格/全角引号会自动归一化）')
        lines.append("\n常用命令管理:")
        lines.append("  ★  保存当前命令到下拉列表（持久化到 config.json）")
        lines.append("  ×  删除下拉列表中选中的命令")
        lines.append("  下拉列表可直接选择已保存的命令，也可手动输入新命令")
        QMessageBox.information(self, "预处理命令帮助", "\n".join(lines))

    # ==================== Python 脚本预处理 ====================

    def _resolve_script_path(self, path):
        """解析脚本路径：相对路径按项目根解析，返回绝对路径"""
        from pathlib import Path as _P

        p = _P(path)
        if p.is_absolute():
            return str(p)
        return str((_P(__file__).parent / p).resolve())

    @staticmethod
    def _script_key(path):
        """脚本路径判重键：realpath + normcase 规范化。

        QFileDialog 返回反斜杠绝对路径，内置注册经 resolve 后为正斜杠/大小写
        可能不同，逐字节比较会漏判导致同一文件重复注册（config.json 出现
        三条 "hex_clean" 的根因）。
        """
        import os

        try:
            return os.path.normcase(os.path.realpath(path))
        except OSError:
            return os.path.normcase(str(path))

    def _load_py_scripts(self):
        """从 config.json 加载 Python 脚本列表；首次启动注册示例脚本"""
        from pathlib import Path as _P

        scripts_dir = _P(__file__).parent / "scripts"
        # 内置示例脚本（首次启动自动注册，用相对路径）
        builtins = []
        if scripts_dir.is_dir():
            for name, fname in [
                ("Hex 清洗（示例）", "hex_clean.py"),
                ("TCP Payload 提取（示例）", "tcp_payload_extract.py"),
                ("按解析过滤（示例）", "filter_by_parse.py"),
            ]:
                fpath = scripts_dir / fname
                if fpath.is_file():
                    # 存相对路径，便于项目迁移
                    builtins.append({"name": name, "path": f"scripts/{fname}"})

        saved = []
        if self._config_path.exists():
            try:
                with open(self._config_path, encoding="utf-8") as f:
                    config = json.load(f)
                saved = config.get("py_scripts", [])
            except Exception:
                saved = []

        # 无任何记录 → 首次启动，填充内置示例
        if not saved and builtins:
            self._py_builtin_scripts = builtins
            for s in builtins:
                abs_path = self._resolve_script_path(s["path"])
                self._py_script_combo.addItem(s["name"], abs_path)
            # 持久化（用相对路径存内置示例）
            self._persist_py_scripts(builtins)
            return

        # 有保存记录 → 加载（同名同路径历史重复条目去重回填）
        self._py_builtin_scripts = builtins  # 保存引用供参考
        seen = set()
        for s in saved:
            if isinstance(s, dict) and "name" in s and "path" in s:
                abs_path = self._resolve_script_path(s["path"])
                key = (s["name"], self._script_key(abs_path))
                if key in seen:
                    continue
                seen.add(key)
                self._py_script_combo.addItem(s["name"], abs_path)
        # 存在历史重复条目 → 自愈：把去重后的列表写回 config.json
        if len(seen) < len(saved):
            self._persist_py_scripts()

    def _persist_py_scripts(self, scripts_list=None):
        """将脚本列表持久化到 config.json 的 py_scripts 段

        Args:
            scripts_list: 可选，指定要保存的列表（每项含 name/path）。
                         None 则从下拉框读取，路径尽量存相对形式。
        """
        from pathlib import Path as _P

        base = _P(__file__).parent
        config: dict[str, Any] = {}
        if self._config_path.exists():
            try:
                with open(self._config_path, encoding="utf-8") as f:
                    config = json.load(f)
            except Exception:
                config = {}

        if scripts_list is None:
            scripts = []
            for i in range(self._py_script_combo.count()):
                name = self._py_script_combo.itemText(i)
                path = self._py_script_combo.itemData(i)
                if not path:
                    continue
                # 项目内脚本存相对路径，外部脚本存绝对路径
                p = _P(path)
                try:
                    rel = p.relative_to(base)
                    path_str = str(rel).replace("\\", "/")
                except ValueError:
                    path_str = str(p)
                scripts.append({"name": name, "path": path_str})
        else:
            scripts = scripts_list

        config["py_scripts"] = scripts
        try:
            atomic_write_json(self._config_path, config)
        except Exception as e:
            print(f"[Python脚本保存失败] {e}")

    def _load_py_script_file(self):
        """通过文件对话框加载 .py 脚本到下拉列表"""
        from pathlib import Path as _P

        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self, "选择 Python 脚本", "", "Python 脚本 (*.py);;所有文件 (*.*)"
        )
        if not path:
            return

        # 检查文件是否已在列表中（规范化路径比较，防同一文件多种写法漏判）
        new_key = self._script_key(path)
        for i in range(self._py_script_combo.count()):
            item_path = self._py_script_combo.itemData(i)
            if item_path and self._script_key(item_path) == new_key:
                self._py_script_combo.setCurrentIndex(i)
                self.update_stats(
                    f"脚本已在列表中: {self._py_script_combo.itemText(i)}"
                )
                return

        # 用文件名（去扩展）作为显示名
        name = _P(path).stem
        self._py_script_combo.addItem(name, path)
        self._py_script_combo.setCurrentIndex(self._py_script_combo.count() - 1)
        self._persist_py_scripts()
        self.update_stats(f"已加载脚本: {name}")

    def _delete_py_script(self):
        """从下拉列表移除当前脚本（不删除磁盘文件）"""
        idx = self._py_script_combo.currentIndex()
        if idx < 0:
            return

        name = self._py_script_combo.itemText(idx)
        from PySide6.QtWidgets import QMessageBox

        ret = QMessageBox.question(
            self,
            "确认移除",
            f"确定从列表中移除脚本「{name}」吗？\n\n（不会删除磁盘上的 .py 文件）",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return

        self._py_script_combo.removeItem(idx)
        self._persist_py_scripts()
        self.update_stats(f"已移除脚本: {name}")

    def _run_py_script(self):
        """运行当前选中的 Python 脚本（后台线程，不阻塞 UI），结果回填到 batch_input"""
        import time

        t0 = time.time()

        idx = self._py_script_combo.currentIndex()
        if idx < 0:
            QMessageBox.warning(self, "警告", "请先加载或选择一个 Python 脚本！")
            return

        script_path = self._py_script_combo.itemData(idx)
        if not script_path:
            QMessageBox.warning(self, "警告", "脚本路径无效！")
            return

        # 读取输入文本（可能是大文本，计时）
        input_text = self.batch_input.toPlainText()
        t1 = time.time()
        print(f"[脚本] 读取输入: {len(input_text)} 字符, 耗时 {(t1 - t0) * 1000:.1f}ms")

        if not input_text.strip():
            QMessageBox.warning(self, "警告", "输入框为空，请先粘贴或加载报文！")
            return

        # 防止重复执行
        if getattr(self, "_py_script_running", False):
            QMessageBox.information(self, "提示", "脚本正在运行中，请稍候...")
            return

        script_name = self._py_script_combo.itemText(idx)
        self._py_script_running = True
        self._py_run_btn.setEnabled(False)
        self._py_run_btn.setText("运行中...")
        self.update_stats(f"正在运行脚本（{script_name}）...")

        # 构造 context（主线程中做，只包含轻量数据；parser 懒加载）
        from py_script_engine import build_context

        try:
            context = build_context(self)
        except Exception as e:
            self._py_script_running = False
            self._py_run_btn.setEnabled(True)
            self._py_run_btn.setText("运行")
            QMessageBox.critical(self, "脚本上下文构造失败", str(e))
            return

        t2 = time.time()
        print(f"[脚本] 准备阶段完成, 耗时 {(t2 - t0) * 1000:.1f}ms")

        # Worker + Thread
        self._py_script_thread = QThread(self)
        thread_registry.track(self._py_script_thread, "PyScriptThread")
        worker = _PyScriptWorker(script_path, input_text, context)
        worker.moveToThread(self._py_script_thread)
        self._py_script_worker = worker

        # 信号连接
        self._py_script_thread.started.connect(worker.run)
        worker.finished.connect(self._on_py_script_finished)
        worker.error.connect(self._on_py_script_error)
        worker.finished.connect(self._py_script_thread.quit)
        worker.error.connect(self._py_script_thread.quit)
        self._py_script_thread.finished.connect(worker.deleteLater)
        self._py_script_thread.finished.connect(self._py_script_thread.deleteLater)

        # 记录脚本名用于完成提示
        self._py_script_running_name = script_name

        self._py_script_thread.start()

    def _on_py_script_finished(self, result):
        """脚本执行成功回调"""
        import time

        t0 = time.time()
        self._py_script_running = False
        self._py_run_btn.setEnabled(True)
        self._py_run_btn.setText("运行")

        if not result.strip():
            QMessageBox.information(self, "脚本结果", "脚本输出为空，未修改输入内容。")
            return

        # 高效回填：用 QTextCursor 全选替换，减少重绘
        doc = self.batch_input.document()
        self.batch_input.setUpdatesEnabled(False)
        cursor = self.batch_input.textCursor()
        cursor.beginEditBlock()
        cursor.select(QTextCursor.Document)
        cursor.insertText(result)
        cursor.endEditBlock()
        # 光标移到开头
        cursor.setPosition(0)
        self.batch_input.setTextCursor(cursor)
        self.batch_input.setUpdatesEnabled(True)
        t1 = time.time()
        print(f"[脚本回调] 回填 {len(result)} 字符, 耗时 {(t1 - t0) * 1000:.1f}ms")

        line_count = len([l for l in result.splitlines() if l.strip()])
        script_name = getattr(self, "_py_script_running_name", "脚本")
        self.update_stats(f"脚本处理完成（{script_name}）：{line_count} 行")

    def _on_py_script_error(self, error_msg):
        """脚本执行失败回调"""
        self._py_script_running = False
        self._py_run_btn.setEnabled(True)
        self._py_run_btn.setText("运行")
        QMessageBox.critical(self, "脚本执行失败", error_msg)

    def _show_py_script_help(self):
        """显示 Python 脚本预处理帮助"""
        lines = [
            "Python 脚本预处理",
            "────────────────────────────────",
            "",
            "加载自定义 .py 脚本，对输入框文本进行清洗/提取/转换。",
            "脚本需定义入口函数：",
            "",
            "    def process(text, context):",
            '        """',
            "        Args:",
            "            text:    输入框原始文本（str）",
            "            context: 上下文字典",
            "        Returns:",
            "            处理后的文本（str）",
            '        """',
            "        return text",
            "",
            "context 包含字段：",
            "  protocol_index : int      当前协议索引（0-10）",
            "  protocol_name  : str      当前协议名称",
            "  config_dir     : str      项目根目录",
            "  parser         : object   当前协议解析器实例",
            "  main_window    : object   主窗口引用（慎用）",
            "",
            "脚本可自由 import 项目内模块（如 protocol_parser、hdlc_parser 等）。",
            "",
            "⚠ 安全提示：脚本直接运行，仅加载可信的 .py 文件。",
            "",
            "示例脚本位于项目 scripts/ 目录下。",
        ]
        QMessageBox.information(self, "Python 脚本预处理帮助", "\n".join(lines))

    # ==================== 原始日志快照与右键定位（09-10） ====================

    def _set_batch_snapshot(self, text, name=""):
        """建立/重建批量输入原始日志快照。

        仅在 拖入文件 / 打开文件 / 粘贴 / parse_batch 兜底 四处调用；
        CLI/脚本回填式预处理只改输入框，绝不触碰快照。
        行尾统一为 \n（QPlainTextEdit.setPlainText 行为一致），并使流缓存失效。
        """
        self._batch_snapshot_text = (
            (text or "").replace("\r\n", "\n").replace("\r", "\n")
        )
        self._batch_snapshot_name = name or ""
        self._snapshot_hex_cache = None
        self._snapshot_hits = {}

    def _snapshot_stream(self):
        """快照归一化 hex 流（懒建缓存：同一快照对象复用）。"""
        snap = self._batch_snapshot_text
        if not snap:
            return "", []
        cache = self._snapshot_hex_cache
        if cache is not None and cache[0] is snap:
            return cache[1], cache[2]
        stream, line_of = batch_source_view.hex_stream(snap)
        self._snapshot_hex_cache = (snap, stream, line_of)
        return stream, line_of

    def _ensure_source_viewer(self):
        """原始日志查看器（非模态单实例，重复右键复用）。"""
        v = self._src_viewer
        if v is None:
            v = batch_source_view.SourceViewerDialog(self)
            self._src_viewer = v
        return v

    def _snapshot_frame_hits(self, frame_hex: str):
        """帧 hex 在快照中的全部命中（按帧缓存：重复定位/连续切行零重算）。"""
        cached = self._snapshot_hits.get(frame_hex)
        if cached is not None:
            return cached
        stream, line_of = self._snapshot_stream()
        hits = batch_source_view.find_frame_in_stream(stream, line_of, frame_hex)
        self._snapshot_hits[frame_hex] = hits
        return hits

    def _locate_frame_in_snapshot(self, frame_idx: int, silent: bool = False):
        """在原始日志快照中定位该帧并在查看器高亮（Ctrl+G 快捷键同入口）。

        silent=True（弹窗已开时的行切换跟随）：跳过一切模态提示/告警——
        无快照/无 hex/零命中都静默返回，不打断连续浏览。
        """
        if frame_idx < 0 or frame_idx >= len(self.batch_results):
            return
        frame_hex = self.batch_results[frame_idx].get("_input", "")
        if not frame_hex:
            if not silent:
                self.update_stats("该帧无原始 hex，无法定位")
            return
        if not self._batch_snapshot_text:
            if not silent:
                QMessageBox.information(
                    self,
                    "无原始日志快照",
                    "当前没有原始日志快照。\n\n"
                    "拖入 / 打开文件 / 粘贴日志时会自动建立快照；\n"
                    "若输入框内容来自其他途径且未解析过，请先执行一次批量解析。",
                )
            return
        hits = self._snapshot_frame_hits(frame_hex)
        if hits:
            # 重发消歧：摘要中该帧是第 nth 次出现 → 取快照第 nth 个命中（超界取末个）
            nth = sum(
                1
                for j in range(frame_idx)
                if self.batch_results[j].get("_input") == frame_hex
            )
            hit = hits[min(nth, len(hits) - 1)]
        else:
            hit = None
        viewer = self._ensure_source_viewer()
        viewer.set_source(self._batch_snapshot_text, self._batch_snapshot_name)
        viewer.show_frame(hit, frame_idx + 1)
        if silent:
            # 弹窗已开：只更新高亮，不再抢焦点/置前（用户可能正在弹窗内搜索）
            return
        viewer.show()
        viewer.raise_()
        viewer.activateWindow()
        if hit is None:
            self.update_stats(
                f"帧 #{frame_idx + 1} 未在原始日志快照中命中（可能已被脚本改写）"
            )

    def _setup_batch_summary_menu(self):
        """批量摘要表专用右键菜单（定位原始报文 + 通用复制项）+ Ctrl+G 快捷键。"""
        self.batch_summary_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.batch_summary_table.customContextMenuRequested.connect(
            self._show_batch_summary_menu
        )
        # Ctrl+G：定位当前选中帧到原始日志（弹窗已开时静默跟随刷新高亮）
        sc = QShortcut(QKeySequence("Ctrl+G"), self.batch_summary_table)
        sc.setContext(Qt.WidgetShortcut)
        sc.activated.connect(self._locate_current_batch_frame)

    def _locate_current_batch_frame(self):
        """快捷键入口：对当前行执行快照定位。

        弹窗已开 → silent（只刷新高亮，不抢焦点）；未开 → 完整弹出流程。
        """
        table_row = self.batch_summary_table.currentRow()
        if table_row < 0:
            return
        item = self.batch_summary_table.item(table_row, 0)
        if item is None:
            return
        orig_idx = item.data(Qt.UserRole)
        if orig_idx is None or orig_idx >= len(self.batch_results):
            return
        v = self._src_viewer
        already_open = v is not None and v.isVisible()
        self._locate_frame_in_snapshot(orig_idx, silent=already_open)

    def _build_batch_summary_menu(self, table: QTableWidget, pos):
        """构建右键菜单（纯构建，不弹出——测试可直接调用）。

        右键落在当前选区之外时先选中该行（Qt 惯例），使「定位/复制本帧」
        作用于鼠标下的帧。
        """
        item = table.itemAt(pos)
        if item is not None:
            row = item.row()
            if not table.selectionModel().isRowSelected(row, QModelIndex()):
                table.selectRow(row)

        menu = QMenu(table)
        frame_idx = None
        if item is not None:
            num_item = table.item(item.row(), 0)
            if num_item is not None:
                frame_idx = num_item.data(Qt.UserRole)

        act_loc = menu.addAction("转到原始报文位置  Ctrl+G")
        act_loc.setShortcut("Ctrl+G")
        act_loc.setEnabled(
            frame_idx is not None and frame_idx < len(self.batch_results)
        )
        if frame_idx is not None:
            act_loc.triggered.connect(
                lambda _c=False, i=frame_idx: self._locate_frame_in_snapshot(i)
            )

        act_copy_hex = menu.addAction("复制本帧HEX")
        act_copy_hex.setEnabled(
            frame_idx is not None and frame_idx < len(self.batch_results)
        )
        if frame_idx is not None:
            act_copy_hex.triggered.connect(
                lambda _c=False, i=frame_idx: QApplication.clipboard().setText(
                    self.batch_results[i].get("_input", "")
                )
            )

        menu.addSeparator()
        has_selection = len(table.selectedItems()) > 0
        copy_sel = menu.addAction("复制选中行")
        copy_sel.setEnabled(has_selection)
        copy_sel.triggered.connect(lambda: self._copy_table_rows(table, all_rows=False))
        copy_all = menu.addAction("复制全部")
        copy_all.triggered.connect(lambda: self._copy_table_rows(table, all_rows=True))
        return menu

    def _show_batch_summary_menu(self, pos):
        """弹出批量摘要表右键菜单。"""
        menu = self._build_batch_summary_menu(self.batch_summary_table, pos)
        menu.exec(self.batch_summary_table.mapToGlobal(pos))

    def clear_batch(self):
        """清空批量解析内容"""
        self.batch_input.clear()
        self.batch_summary_table.setRowCount(0)
        self.batch_detail_table.setRowCount(0)
        self.batch_detail_hex.clear()
        self.batch_results = []
        # 原始日志快照与查看器随清空销毁（快照是用户刻意保留的原文，
        # 「清空」语义 = 全部重来，下次拖入/粘贴重新建立）
        self._batch_snapshot_text = ""
        self._batch_snapshot_name = ""
        self._snapshot_hex_cache = None
        self._snapshot_hits = {}
        if getattr(self, "_src_viewer", None) is not None:
            self._src_viewer.close()
            self._src_viewer.deleteLater()
            self._src_viewer = None
        # 时序图随批量结果清空（若已创建）
        if getattr(self, "seq_diagram_tab", None) is not None:
            self.seq_diagram_tab.set_model(None)
        self.batch_status_bar.setText("就绪")
        self.batch_frame_count_label.setText("共 0 帧")
        self.update_stats("待解析")
        # 重置搜索过滤
        if hasattr(self, "batch_search_edit"):
            self.batch_search_edit.clear()
        if hasattr(self, "batch_status_filter"):
            self.batch_status_filter.setCurrentIndex(0)
        if hasattr(self, "batch_filter_count"):
            self.batch_filter_count.setText("")
        # 重置类型全选下拉与选中计数
        if hasattr(self, "batch_type_combo"):
            self.batch_type_combo.blockSignals(True)
            while self.batch_type_combo.count() > 1:
                self.batch_type_combo.removeItem(1)
            self.batch_type_combo.setCurrentIndex(0)
            self.batch_type_combo.blockSignals(False)
        if hasattr(self, "batch_selected_count"):
            self.batch_selected_count.setText("")

    def _get_selected_batch_indices(self) -> list:
        """摘要表当前高亮行对应的 batch_results 原始索引（升序去重）"""
        idxs = set()
        for item in self.batch_summary_table.selectedItems():
            row = item.row()
            num_item = self.batch_summary_table.item(row, 0)
            if num_item is not None:
                orig = num_item.data(Qt.UserRole)
                if orig is not None and 0 <= orig < len(self.batch_results):
                    idxs.add(orig)
        return sorted(idxs)

    def _on_batch_select_by_type(self):
        """按类型一键勾选：把所选类型的全部可见行加入高亮选区；未选类型时清空选区"""
        type_data = self.batch_type_combo.currentData()
        self.batch_summary_table.clearSelection()
        if type_data is None:
            self._update_batch_selected_count()
            return
        from PySide6.QtCore import QItemSelection, QItemSelectionModel

        selection = QItemSelection()
        model = self.batch_summary_table.model()
        for row in range(self.batch_summary_table.rowCount()):
            if self.batch_summary_table.isRowHidden(row):
                continue
            proto_item = self.batch_summary_table.item(row, 3)
            if proto_item is None or proto_item.text() != type_data:
                continue
            left = model.index(row, 0)
            right = model.index(row, self.batch_summary_table.columnCount() - 1)
            selection.select(left, right)
        sel_model = self.batch_summary_table.selectionModel()
        if sel_model is not None:
            sel_model.select(
                selection, QItemSelectionModel.Select | QItemSelectionModel.Rows
            )
        self._update_batch_selected_count()

    def _update_batch_selected_count(self):
        """更新「已选 N 帧」标签"""
        n = len(self._get_selected_batch_indices())
        self.batch_selected_count.setText(f"已选 {n} 帧" if n else "")

    def _refresh_batch_type_combo(self):
        """解析完成后刷新类型下拉（从当前结果提取全部协议/类型）"""
        current = self.batch_type_combo.currentData()
        self.batch_type_combo.blockSignals(True)
        self.batch_type_combo.clear()
        self.batch_type_combo.addItem("按类型全选…", None)
        types = []
        for r in self.batch_results:
            t = r.get("_type_name")
            if t and t not in types:
                types.append(t)
        for t in sorted(types):
            self.batch_type_combo.addItem(t, t)
        if current is not None:
            pos = self.batch_type_combo.findData(current)
            if pos >= 0:
                self.batch_type_combo.setCurrentIndex(pos)
        self.batch_type_combo.blockSignals(False)

    def export_batch(self, fmt=None):
        """增强版批量解析结果导出 - 支持 JSON/Excel 多格式，Excel 含 Sheet2 详细解析

        Args:
            fmt: 导出格式，可选 "excel" / "json" / "selected_dialog" / None
                 - "excel" 或 "json": 直接弹出保存对话框，跳过格式选择
                 - "selected_dialog": 显示完整导出对话框，且默认只导出当前选中帧
                 - None: 显示完整的导出选项对话框（默认，向后兼容）
        """
        from PySide6.QtWidgets import QFileDialog

        if not self.batch_results:
            QMessageBox.warning(self, "警告", "没有可导出的解析结果！")
            return

        # 导出范围：选中帧（多选行模式，Ctrl/Shift 挑选信标帧等子集）
        selected_only = fmt == "selected_dialog"
        selected_idxs = self._get_selected_batch_indices() if selected_only else []
        if selected_only and not selected_idxs:
            QMessageBox.warning(
                self, "提示", "请先在摘要表中选中要导出的帧（Ctrl/Shift 可多选）！"
            )
            return
        export_pool = (
            [self.batch_results[i] for i in selected_idxs]
            if selected_only
            else self.batch_results
        )
        # 详情按需（步骤 3）：batch_results 不再常驻 _table_data，导出侧注入
        # 「结果 dict → 详情表格」解析器（逐条取用，不物化整批详情）
        detail_resolver = self._batch_detail_resolver()

        # 获取协议名称
        protocol_names = [
            "南网协议",
            "PLC_RF协议",
            "HDLC协议",
            "DLMS_APDU",
            "DLMS_Wrapper",
            "DLMS_APDU",
            "DLT645协议",
            "国网协议",
            "698.45协议",
            "新一代载波协议",
        ]
        protocol_name = (
            protocol_names[self.current_protocol]
            if self.current_protocol < len(protocol_names)
            else f"协议{self.current_protocol}"
        )

        # 快速路径：指定格式时直接弹出保存文件对话框
        if fmt in ("excel", "json"):
            if fmt == "excel":
                default_name = f"batch_parse_{protocol_name}.xlsx"
                filter_str = "Excel 文件 (*.xlsx);;所有文件 (*)"
            else:
                default_name = f"batch_parse_{protocol_name}.json"
                filter_str = "JSON 文件 (*.json);;所有文件 (*)"

            file_path, _ = QFileDialog.getSaveFileName(
                self, "选择导出位置", default_name, filter_str
            )
            if not file_path:
                return

            try:
                export_dir = str(Path(file_path).parent)
                exporter = EnhancedBatchResultExporter(export_dir)

                if fmt == "excel":
                    result_path = exporter.export_to_excel(
                        self.batch_results,
                        protocol_name,
                        output_file=file_path,
                        table_data_resolver=detail_resolver,
                    )
                else:
                    result_path = exporter.export_to_json(
                        self.batch_results,
                        protocol_name,
                        output_file=file_path,
                        table_data_resolver=detail_resolver,
                    )

                QMessageBox.information(
                    self, "导出成功", f"结果已保存到:\n{result_path}"
                )
            except Exception as e:
                QMessageBox.critical(self, "导出失败", str(e))
            return

        # 创建导出器
        exporter = EnhancedBatchResultExporter()

        # 显示导出选项对话框
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QDialog,
            QDialogButtonBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            QRadioButton,
            QVBoxLayout,
        )

        dialog = QDialog(self)
        dialog.setWindowTitle("批量解析导出")
        dialog.setMinimumWidth(500)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        scope_text = (
            f"仅选中帧 {len(export_pool)}/{len(self.batch_results)} 条"
            if selected_only
            else f"共 {len(self.batch_results)} 条结果"
        )
        title = QLabel(f"导出协议: {protocol_name}  |  {scope_text}")
        title.setStyleSheet("font-size: 13px; font-weight: bold; color: #2196F3;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 格式选择
        layout.addWidget(QLabel("选择导出格式:"))

        excel_radio = QRadioButton("Excel 格式（Sheet1 汇总 + Sheet2 每帧详细解析）")
        excel_radio.setChecked(True)
        layout.addWidget(excel_radio)

        json_radio = QRadioButton("JSON 格式（完整数据 + 元数据）")
        layout.addWidget(json_radio)

        # Excel 已打包进 exe，直接启用
        excel_radio.setEnabled(True)

        # 说明
        info_label = QLabel(
            "Excel 导出包含两个工作表：\n  Sheet1「汇总表」- 帧序号/状态/摘要\n  Sheet2「详细解析」- 每帧所有字段逐行展开"
        )
        info_label.setStyleSheet("color: #666; font-size: 11px;")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # 文件路径选择
        layout.addWidget(QLabel("输出路径:"))

        path_layout = QHBoxLayout()
        path_edit = QLineEdit()
        path_edit.setPlaceholderText("选择导出文件保存位置...")
        path_layout.addWidget(path_edit)

        browse_btn = QPushButton("浏览...")
        browse_btn.setMaximumWidth(80)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)

        # 浏览按钮点击事件
        def browse_path():
            if excel_radio.isChecked():
                default_name = f"batch_parse_{protocol_name}.xlsx"
                filter_str = "Excel 文件 (*.xlsx);;所有文件 (*)"
            else:
                default_name = f"batch_parse_{protocol_name}.json"
                filter_str = "JSON 文件 (*.json);;所有文件 (*)"

            file_path, _ = QFileDialog.getSaveFileName(
                self, "选择导出位置", default_name, filter_str
            )
            if file_path:
                path_edit.setText(file_path)

        browse_btn.clicked.connect(browse_path)

        # 格式切换时更新默认文件名
        def update_default_name():
            if excel_radio.isChecked():
                default_name = f"batch_parse_{protocol_name}.xlsx"
            else:
                default_name = f"batch_parse_{protocol_name}.json"
            path_edit.setText(default_name)

        excel_radio.toggled.connect(update_default_name)
        json_radio.toggled.connect(update_default_name)

        # 初始化默认路径
        update_default_name()

        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText("导出")
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")

        def do_export():
            try:
                file_path = path_edit.text().strip()
                if not file_path:
                    QMessageBox.warning(self, "警告", "请选择导出路径！")
                    return

                # 获取导出目录和文件名
                export_dir = str(Path(file_path).parent)
                file_name = Path(file_path).stem

                # 创建导出器，指定导出目录
                exporter = EnhancedBatchResultExporter(export_dir)

                if excel_radio.isChecked():
                    result_path = exporter.export_to_excel(
                        export_pool,
                        protocol_name,
                        output_file=file_path,
                        table_data_resolver=detail_resolver,
                    )
                else:
                    result_path = exporter.export_to_json(
                        export_pool,
                        protocol_name,
                        output_file=file_path,
                        table_data_resolver=detail_resolver,
                    )
                QMessageBox.information(
                    self, "导出成功", f"结果已保存到:\n{result_path}"
                )
                dialog.accept()
            except Exception as e:
                QMessageBox.critical(self, "导出失败", str(e))

        button_box.button(QDialogButtonBox.StandardButton.Ok).clicked.connect(do_export)
        button_box.button(QDialogButtonBox.StandardButton.Cancel).clicked.connect(
            dialog.reject
        )
        layout.addWidget(button_box)

        dialog.exec()

    def _get_frame_type_name(
        self, table_data: list, status: str, protocol_index: int = None
    ) -> str:
        """从解析表格数据中提取帧类型名称（用于摘要表的"协议/类型"列）。

        `protocol_index` 供后台线程传入参数快照（None = 主窗口当前协议）；
        兜底分支改读 protocol_registry（不再读 protocol_combo），可在工作线程调用。
        """
        proto = self.current_protocol if protocol_index is None else protocol_index
        if status != "成功" or not table_data:
            if status == "失败":
                return "解析失败"
            elif status == "异常":
                return "异常"
            else:
                return "-"

        if proto == 0:  # 南网协议
            for item in table_data:
                field = str(item[0])
                if "AFN" in field and not field.startswith(" "):
                    return str(item[3] or item[2] or "南网协议")
            return "南网协议"

        elif proto == 7:  # 国网协议
            for item in table_data:
                field = str(item[0])
                if "AFN" in field and not field.startswith(" "):
                    return str(item[3] or item[2] or "国网协议")
            return "国网协议"

        elif proto == 8:  # 698.45
            for item in table_data:
                field = str(item[0])
                if (
                    "APDU" in field or "功能码" in field or "服务" in field
                ) and not field.startswith(" "):
                    return str(item[3] or item[2] or "698.45协议")
            return "698.45协议"

        elif proto in (2, 3, 4, 5):  # DLMS 族
            for item in table_data:
                field = str(item[0])
                if (
                    "帧类型" in field or "服务" in field or "功能" in field
                ) and not field.startswith(" "):
                    val = str(item[3] or item[2] or "")
                    if val:
                        return val
            proto_names = {2: "HDLC", 3: "DLMS-APDU", 4: "DLMS-Wrapper", 5: "DLMS-APDU"}
            return proto_names[proto]

        elif proto == 9:  # 新一代载波
            for item in table_data:
                field = str(item[0])
                if (
                    "帧类型" in field or field.strip() == "FC"
                ) and not field.startswith(" "):
                    return str(item[3] or item[2] or "新一代载波")
            return "新一代载波"

        elif proto == 10:  # 国网新一代
            for item in table_data:
                field = str(item[0])
                if ("帧类型" in field or "MSDU类型" in field) and not field.startswith(
                    " "
                ):
                    return str(item[3] or item[2] or "国网新一代")
            return "国网新一代"

        elif proto == 11:  # HDC 1.0
            # 与协议10 字段名不同构：FC 定界符行叫「定界符类型(DT)」→ 两种都认，
            # 否则类型列恒为注册表名首段「HDC」而看不到
            # 信标帧/SOF帧/选择确认帧(SACK)/网间协调帧（口径与 batch_core 同名函数一致）。
            for item in table_data:
                field = str(item[0])
                if field.startswith(("定界符类型", "MSDU类型")):
                    val = str(item[3] or item[2] or "")
                    if val:
                        return val
            # 无 FC 裸 MAC/应用层帧：优先取业务名（如“开始升级”），复用
            # batch_core.gw_app_biz_summary 单一规则；取不到再退回 MSDU 类型/
            # 报文ID（item[2] 解析值优先，并排除“安全模式:…”说明）。曾误用
            # 「报文ID」行的**说明列**作为类型名（9e60ba6 潜伏红测试根因）
            biz_name, _ = batch_core.gw_app_biz_summary(table_data)
            if biz_name:
                return biz_name
            for item in table_data:
                field = str(item[0]).strip()
                if field in ("MSDU类型", "报文ID", "业务报文ID"):
                    val = str(item[2] or item[3] or "")
                    if val and not val.startswith("安全模式"):
                        return val
            return "HDC 1.0"

        elif proto == 12:  # 模组化终端功能模块接口
            # 信息帧取 APDU 名，确认/否认帧取控制码名（不能落到薜底分支：
            # 注册表展示名以“[12]”开头，split(" ")[0] 会得到“[12]”）
            ctrl_val = None
            for item in table_data:
                field = str(item[0])
                parsed_val = str(item[2] or "").strip()
                if field == "    APDU 类型" and parsed_val:
                    return parsed_val
                if field == "  控制码" and not ctrl_val:
                    ctrl_val = parsed_val or str(item[3] or "").strip()
            return ctrl_val or "模组化接口"

        elif proto == 6:  # DLT645
            for item in table_data:
                if "控制码" in str(item[0]) and not str(item[0]).startswith(" "):
                    return str(item[3] or item[2] or "DLT645")
            return "DLT645协议"

        elif proto == 1:  # PLC RF
            for item in table_data:
                field = str(item[0])
                if ("命令字" in field or "功能" in field) and not field.startswith(" "):
                    return str(item[3] or item[2] or "PLC RF")
            return "PLC RF协议"

        else:
            # 兜底：取注册表展示名首段（protocol_combo 文案与 combo_labels() 同源，
            # 取值完全一致）；不能读 protocol_combo —— 后台线程禁止触碰 widget。
            return protocol_registry.get_protocol(proto).name.split(" ")[0]

    def _on_batch_search_text_changed(self):
        """关键词输入去抖入口（250 ms）。

        连续按键只跑一次全表过滤；计时器 `timeout` 仍接 `_on_batch_filter_changed`，
        所以「最终态」与直接调用完全一致（仅延迟 250 ms）。
        """
        self._batch_filter_timer.start()

    def _on_batch_filter_changed(self):
        """批量解析结果搜索过滤（关键词 + 状态）

        性能：49,532 行逐行 `setRowHidden` 的代价几乎全在重绘（实测 0.87 s/按键），
        关掉重绘后同一循环 0.02 s。`finally` 保证异常时也恢复重绘。
        过滤字面量、匹配范围、计数文案、选中行回落行为均与改动前逐字一致。
        """
        if not hasattr(self, "batch_results") or not self.batch_results:
            return
        keyword = self.batch_search_edit.text().strip().lower()
        status_filter = self.batch_status_filter.currentData()
        visible_count = 0
        table = self.batch_summary_table
        total = table.rowCount()
        table.setUpdatesEnabled(False)
        try:
            for row in range(total):
                item = table.item(row, 0)
                if item is None:
                    continue
                orig_idx = item.data(Qt.UserRole)
                if orig_idx is None or orig_idx >= len(self.batch_results):
                    continue
                result = self.batch_results[orig_idx]
                status = result.get("_status", "")
                # 状态过滤
                if status_filter == "success" and status != "成功":
                    table.setRowHidden(row, True)
                    continue
                if status_filter == "fail" and status != "失败":
                    table.setRowHidden(row, True)
                    continue
                if status_filter == "error" and status != "异常":
                    table.setRowHidden(row, True)
                    continue
                # 关键词过滤（匹配摘要 + 协议类型 + 原始HEX）
                if keyword:
                    summary = str(result.get("摘要", "")).lower()
                    proto_item = table.item(row, 3)
                    proto = proto_item.text().lower() if proto_item else ""
                    raw_hex = str(result.get("_input", "")).lower()
                    if (
                        keyword not in summary
                        and keyword not in proto
                        and keyword not in raw_hex
                    ):
                        table.setRowHidden(row, True)
                        continue
                table.setRowHidden(row, False)
                visible_count += 1
        finally:
            table.setUpdatesEnabled(True)
        # 更新计数
        if keyword or status_filter != "all":
            self.batch_filter_count.setText(f"显示 {visible_count} / {total}")
        else:
            self.batch_filter_count.setText("")
        # 如果当前选中行被隐藏，选中第一条可见行
        current = table.currentRow()
        if current < 0 or table.isRowHidden(current):
            for r in range(total):
                if not table.isRowHidden(r):
                    table.selectRow(r)
                    break

    def _generate_sequence_diagram(self):
        """批量解析工具栏「时序图」/时序图页「刷新」：生成通信时序图并切到该页

        数据范围：摘要表有勾选行时仅用勾选帧（保持 batch_results 原始索引，
        图上 #N 与摘要表帧号一致），否则用全部帧。协议9/10/11可用。
        """
        if self.current_protocol not in (9, 10, 11):
            QMessageBox.information(
                self,
                "提示",
                "通信时序图当前仅支持协议9/10/11（南网新一代/国网新一代/HDC 1.0）。",
            )
            return
        if not self.batch_results:
            QMessageBox.information(self, "提示", "请先完成批量解析，再生成时序图。")
            return
        selected = self._get_selected_batch_indices()
        if selected:
            results = [self.batch_results[i] for i in selected]
            frame_indices = selected
        else:
            results = self.batch_results
            frame_indices = None
        from sequence_diagram_widget import build_sequence_model

        model = build_sequence_model(
            results,
            self.current_protocol,
            frame_indices=frame_indices,
            # 详情按需（步骤 3）：时序图提取需要每帧字段表，按需重解析
            table_data_resolver=self._batch_detail_resolver(),
        )
        if model is None:
            QMessageBox.information(self, "提示", "当前协议暂不支持时序图。")
            return
        tab = self._ensure_seq_diagram_tab()
        tab.set_model(model)
        self.tab_widget.setCurrentIndex(self._seq_diagram_tab_index)

    def _on_seq_message_clicked(self, frame_idx: int):
        """时序图消息点击 → 跳回批量解析页并定位对应帧行（图 → 摘要表方向）"""
        if getattr(self, "_seq_sync_guard", False):
            return
        self._seq_sync_guard = True
        try:
            # 按序号列 UserRole 反查摘要表行（过滤后行号≠原始索引）
            target_row = -1
            for row in range(self.batch_summary_table.rowCount()):
                item = self.batch_summary_table.item(row, 0)
                if item is not None and item.data(Qt.UserRole) == frame_idx:
                    target_row = row
                    break
            if target_row < 0:
                return
            self.tab_widget.setCurrentIndex(self._batch_tab_index)
            self.batch_summary_table.selectRow(target_row)
            item = self.batch_summary_table.item(target_row, 0)
            if item is not None:
                self.batch_summary_table.scrollToItem(item)
            # selectRow 不触发 cellClicked，直接按原始索引填充详情
            self._populate_batch_detail(frame_idx)
        finally:
            self._seq_sync_guard = False

    def _on_batch_selection_highlight_seq(self):
        """摘要表选区变化 → 时序图高亮对应消息（摘要表 → 图 方向）"""
        if getattr(self, "_seq_sync_guard", False):
            return
        tab = getattr(self, "seq_diagram_tab", None)
        if tab is None:
            return
        idxs = self._get_selected_batch_indices()
        if len(idxs) != 1:
            return
        self._seq_sync_guard = True
        try:
            tab.highlight_frame(idxs[0])
        finally:
            self._seq_sync_guard = False

    def _on_batch_row_selected(self, row=None, col=None):
        """批量解析摘要表行选中时的处理（填充右侧详情面板）"""
        # 获取当前选中行的原始 batch_results 索引
        if row is not None:
            table_row = row
        else:
            table_row = self.batch_summary_table.currentRow()
            if table_row < 0:
                return
        # 从序号列 item 中读取原始索引（过滤后行号≠原始索引）
        item = self.batch_summary_table.item(table_row, 0)
        if item is None:
            return
        orig_idx = item.data(Qt.UserRole)
        if orig_idx is None:
            # 兼容旧逻辑：直接用行号当索引
            orig_idx = table_row
        if orig_idx < 0 or orig_idx >= len(self.batch_results):
            return
        self._populate_batch_detail(orig_idx)
        # 回跳输入日志对应报文行（选中+居中）
        self._jump_batch_input_to_src_line(orig_idx)
        # 快照查看器已打开时：切行静默跟随（弹窗保持，只刷新高亮，直到用户关闭）
        _viewer = self._src_viewer
        if _viewer is not None and _viewer.isVisible():
            self._locate_frame_in_snapshot(orig_idx, silent=True)

    def _jump_batch_input_to_src_line(self, idx: int):
        """批量解析结果 → 输入日志对应报文行回跳（选中该行并居中）

        行号来源：批量解析时记录的 _src_line（显示文本行号）；
        输入框内容在解析后被编辑时行号可能偏移，属尽力回跳。
        """
        if idx < 0 or idx >= len(self.batch_results):
            return
        line_no = self.batch_results[idx].get("_src_line", -1)
        if line_no is None or line_no < 0:
            return
        block = self.batch_input.document().findBlockByNumber(line_no)
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        self.batch_input.setTextCursor(cursor)
        self.batch_input.ensureCursorVisible()  # QTextEdit 滚动到光标行可见

    def _populate_batch_detail(self, index: int):
        """填充批量解析详情面板（右侧表格 + 原始报文）"""
        if index < 0 or index >= len(self.batch_results):
            return

        result = self.batch_results[index]
        raw_hex = result.get("_input", "")

        # 填充原始报文
        if raw_hex:
            hex_display = " ".join(
                raw_hex[j : j + 2] for j in range(0, len(raw_hex), 2)
            )
            self.batch_detail_hex.setPlainText(hex_display)
        else:
            self.batch_detail_hex.clear()

        # 填充详情表格
        self.batch_detail_table.setRowCount(0)

        status = result.get("_status", "")
        if status == "异常":
            # 异常帧：显示错误信息
            error_text = result.get("错误", str(result))
            self.batch_detail_table.insertRow(0)
            err_item = QTableWidgetItem(f"❌ 解析异常：{error_text}")
            err_item.setForeground(Qt.red)
            self.batch_detail_table.setItem(0, 0, err_item)
            return

        # 详情按需（步骤 3）：不再依赖常驻的 _table_data；命中缓存时 0 开销，
        # 否则用批量解析锁存的帧字节与参数快照重解析一次
        table_data = self._get_frame_table_data(index)
        if not table_data:
            return

        level_map = _field_level_map(
            [str(it[0]) for it in table_data if it[0] is not None]
        )
        for r, item in enumerate(table_data):
            field_name = str(item[0]) if item[0] is not None else ""
            raw_val = str(item[1]) if item[1] is not None else ""
            parsed_val = str(item[2]) if item[2] is not None else ""
            comment = str(item[3]) if item[3] is not None else ""

            # 检测子字段：优先用 is_child 标志(index 6)，其次用归一化层级判断
            level = level_map.get(_field_leading(field_name), 0)
            display_name, level = _format_tree_field(field_name, level)
            if level == 0 and len(item) > 6 and bool(item[6]):
                display_name, level = f"  └ {field_name.strip()}", 1
            is_child = level > 0

            self.batch_detail_table.insertRow(r)

            field_item = QTableWidgetItem(display_name)
            if is_child:
                field_item.setForeground(QColor("#555555"))
            self.batch_detail_table.setItem(r, 0, field_item)
            self.batch_detail_table.setItem(r, 1, QTableWidgetItem(raw_val))
            self.batch_detail_table.setItem(r, 2, QTableWidgetItem(parsed_val))
            self.batch_detail_table.setItem(r, 3, QTableWidgetItem(comment))

    def _do_count_frames(self):
        """实时统计输入中的帧数量（防抖调用）"""
        text = self.batch_input.toPlainText().strip()
        if not text:
            self.batch_frame_count_label.setText("共 0 帧")
            return

        try:
            if self.current_protocol in (9, 10):
                # 新一代协议按行近似统计（精确统计需要完整前缀剥离，代价较高）
                count = sum(1 for line in text.splitlines() if line.strip())
            else:
                frames = self._extract_frames_for_protocol(text, self.current_protocol)
                count = len(frames)
        except Exception:
            count = 0

        self.batch_frame_count_label.setText(f"共 {count} 帧")

    def _copy_batch_detail_hex(self):
        """复制当前选中帧的原始报文到剪贴板"""
        text = self.batch_detail_hex.toPlainText().strip()
        if not text:
            return
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        # 临时更新状态栏提示
        old_text = self.batch_status_bar.text()
        self.batch_status_bar.setText("原始报文已复制到剪贴板")
        QTimer.singleShot(1500, lambda: self.batch_status_bar.setText(old_text))

    def _update_status_bar(self, success_count: int, fail_count: int, total: int):
        """更新批量解析底部状态栏"""
        self.batch_status_bar.setText(
            f"解析完成 — 共 {total} 帧（✅ {success_count} 成功，❌ {fail_count} 失败）"
        )

    def update_stats(self, text: str):
        """更新状态标签（兼容旧 stats_label，同时更新批量解析状态栏）"""
        if hasattr(self, "stats_label") and self.stats_label:
            self.stats_label.setText(f"状态：{text}")
        if hasattr(self, "batch_status_bar") and self.batch_status_bar:
            self.batch_status_bar.setText(text)

    # ==================== 表格结果填充与字节高亮 ====================

    def _populate_table_from_data(self, table_data: list):
        """从解析器生成的表格数据填充表格（6元组：含字节范围）"""
        self.result_table_widget.setRowCount(0)
        self._byte_ranges = []
        self._last_table_data = list(table_data) if table_data else []

        level_map = _field_level_map(
            [str(item[0]) for item in table_data if item[0] is not None]
        )
        for row, item in enumerate(table_data):
            field_name, raw_value, parsed_value, comment = (
                item[0],
                item[1],
                item[2],
                item[3],
            )
            byte_start = item[4] if len(item) > 4 else None
            byte_end = item[5] if len(item) > 5 else None

            level = level_map.get(_field_leading(str(field_name)), 0)
            display_name, level = _format_tree_field(str(field_name), level)
            self.result_table_widget.insertRow(row)
            field_item = QTableWidgetItem(display_name)
            if level > 0:
                field_item.setForeground(QColor("#555555"))
            self.result_table_widget.setItem(row, 0, field_item)
            self.result_table_widget.setItem(row, 1, QTableWidgetItem(str(raw_value)))
            self.result_table_widget.setItem(
                row, 2, QTableWidgetItem(str(parsed_value))
            )
            self.result_table_widget.setItem(row, 3, QTableWidgetItem(str(comment)))
            self._byte_ranges.append((byte_start, byte_end))

        # 同步字段树（切换视图时也可即时重建）
        if hasattr(self, "result_tree_widget"):
            self.result_tree_widget.populate(self._last_table_data)

    def _on_result_view_changed(self, _index: int = 0):
        """解析结果：表格 / 字段树 切换"""
        if not hasattr(self, "result_stack"):
            return
        data = self.result_view_combo.currentData()
        if data == "tree":
            if hasattr(self, "result_tree_widget") and self._last_table_data:
                self.result_tree_widget.populate(self._last_table_data)
            self.result_stack.setCurrentIndex(1)
        else:
            self.result_stack.setCurrentIndex(0)

    def _highlight_byte_range(self, byte_start, byte_end):
        """按字节范围高亮输入框（字段树点击 / 与表格共用）"""
        # 复用 _highlight_bytes 的范围逻辑：临时写入并调用
        self._apply_byte_highlight(byte_start, byte_end)

    def _apply_byte_highlight(self, byte_start, byte_end):
        if byte_start is None or byte_end is None:
            return
        doc = self.single_input.document()
        cursor = QTextCursor(doc)
        cursor.select(QTextCursor.SelectionType.Document)
        default_fmt = QTextCharFormat()
        default_fmt.setFontFamily("Consolas, Monaco, monospace")
        default_fmt.setForeground(QColor("#000000"))
        default_fmt.setBackground(QColor("#FFFFFF"))
        cursor.setCharFormat(default_fmt)

        char_start = byte_start * 3
        char_end = byte_end * 3 + 2
        text_len = len(self.single_input.toPlainText())
        if char_end > text_len:
            char_end = text_len
        if char_start > char_end:
            return
        highlight_cursor = QTextCursor(doc)
        highlight_cursor.setPosition(char_start)
        highlight_cursor.setPosition(char_end, QTextCursor.MoveMode.KeepAnchor)
        hl_fmt = QTextCharFormat()
        hl_fmt.setFontFamily("Consolas, Monaco, monospace")
        hl_fmt.setForeground(QColor("#000000"))
        hl_fmt.setBackground(QColor(255, 235, 59, 160))
        highlight_cursor.setCharFormat(hl_fmt)
        self.single_input.setTextCursor(highlight_cursor)

    def _highlight_bytes(self, row: int, col: int, prev_row: int, prev_col: int):
        """选中表格行时，高亮输入框中对应的报文字节"""
        if not self._byte_ranges:
            return

        doc = self.single_input.document()
        cursor = QTextCursor(doc)

        # 先清除所有高亮，恢复默认格式
        cursor.select(QTextCursor.SelectionType.Document)
        default_fmt = QTextCharFormat()
        default_fmt.setFontFamily("Consolas, Monaco, monospace")
        default_fmt.setForeground(QColor("#000000"))
        default_fmt.setBackground(QColor("#FFFFFF"))
        cursor.setCharFormat(default_fmt)

        # 检查行有效性
        if row < 0 or row >= len(self._byte_ranges):
            return

        byte_start, byte_end = self._byte_ranges[row]
        if byte_start is None or byte_end is None:
            return

        # 在 "XX XX XX ..." 格式中，第 i 个字节对应字符位置 i*3 ~ i*3+1
        char_start = byte_start * 3
        char_end = byte_end * 3 + 2

        # 边界保护
        text_len = len(self.single_input.toPlainText())
        if char_end > text_len:
            char_end = text_len
        if char_start > char_end:
            # 异常范围（如截断行 start>end）不高亮
            return

        # 选中对应字符，应用高亮
        highlight_cursor = QTextCursor(doc)
        highlight_cursor.setPosition(char_start)
        highlight_cursor.setPosition(char_end, QTextCursor.MoveMode.KeepAnchor)

        hl_fmt = QTextCharFormat()
        hl_fmt.setFontFamily("Consolas, Monaco, monospace")
        hl_fmt.setForeground(QColor("#000000"))
        hl_fmt.setBackground(QColor(255, 235, 59, 160))  # 黄色半透明高亮
        highlight_cursor.setCharFormat(hl_fmt)

        # 输入框可视区同步滚动到高亮位置：长报文换行后靠后的字节（如多PB帧的
        # PBCS）否则高亮落在滚动区外，用户看不到对应报文位置
        self.single_input.setTextCursor(highlight_cursor)

    def _extract_apdu_reparse(self, index):
        """双击表格行时，提取该行对应字节范围，弹窗深度解析DLMS-APDU"""
        row = index.row()
        if not self._byte_ranges or row < 0 or row >= len(self._byte_ranges):
            return

        byte_start, byte_end = self._byte_ranges[row]
        if byte_start is None or byte_end is None:
            return

        # 获取完整原始报文（从输入框解析得到）
        if not hasattr(self, "current_result"):
            QMessageBox.information(self, "提示", "无法获取原始报文数据，请先解析")
            return

        full_bytes = self.current_result
        # 提取对应范围字节（byte_end 包含在内）
        extracted_bytes = full_bytes[byte_start : byte_end + 1]

        if len(extracted_bytes) == 0:
            QMessageBox.information(self, "提示", "选中区域字节为空")
            return

        # 自动识别协议类型
        extracted_bytes = bytes(extracted_bytes)
        dialog_title = ""
        try:
            if self.current_protocol == 10:
                # 国网新一代双模通信互联互通
                parsed_data = self.gw_new_gen_parser.parse_to_table(extracted_bytes)
                dialog_title = f"深度解析国网新一代 (提取 {len(extracted_bytes)} 字节)"
            elif self.current_protocol == 11:
                # HDC 1.0 双模互联互通
                parsed_data = self.hdc10_parser.parse_to_table(extracted_bytes)
                dialog_title = f"深度解析HDC 1.0 (提取 {len(extracted_bytes)} 字节)"
            elif self.current_protocol in (8, 9):
                # 698.45 / 新一代载波
                parsed_data = self.gw_new_gen_parser.parse_to_table(extracted_bytes)
                dialog_title = f"深度解析新一代载波 (提取 {len(extracted_bytes)} 字节)"
            elif (
                len(extracted_bytes) >= 12
                and extracted_bytes[0] == 0x68
                and extracted_bytes[7] == 0x68
                and extracted_bytes[-1] == 0x16
            ):
                # DLT645协议
                result = self.dlt645_parser.parse(extracted_bytes)
                parsed_data = []
                for item in result["fields"]:
                    # LME自定义接口子字段为4元组(字段,原始hex,解析值,说明)，其余为3元组
                    if len(item) == 4:
                        field, raw, lme_parsed, desc = item
                    else:
                        field, raw, desc = item
                        lme_parsed = ""
                    parsed_data.append((field, raw, lme_parsed, desc, 0, 0))
                dialog_title = f"深度解析DLT645-2007 (提取 {len(extracted_bytes)} 字节)"
            else:
                # 默认DLMS APDU协议
                parsed_data = self.hdlc_parser.parse_apdu_to_table(extracted_bytes)
                dialog_title = f"深度解析DLMS-APDU (提取 {len(extracted_bytes)} 字节)"
        except Exception as e:
            QMessageBox.critical(self, "解析错误", f"解析失败:\n{str(e)}")
            return

        # 创建弹窗显示解析结果
        dialog = QDialog(self)
        dialog.setWindowTitle(dialog_title)
        dialog.resize(900, 600)

        layout = QVBoxLayout(dialog)

        # 显示提取的十六进制
        hex_text = QTextEdit()
        hex_text.setReadOnly(True)
        hex_text.setFont(self._ui_font(0, family="Consolas"))
        hex_text.setMaximumHeight(80)
        hex_str = " ".join(f"{b:02X}" for b in extracted_bytes)
        hex_text.setText(f"提取字节: {hex_str}")
        layout.addWidget(hex_text)

        # 解析结果表格
        table = ZoomableTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["字段", "十六进制", "解析值", "说明"])
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        table.setColumnWidth(0, 160)
        table.setColumnWidth(1, 120)
        table.setColumnWidth(2, 180)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().hide()
        table.verticalHeader().setDefaultSectionSize(20)
        table_font = self._ui_font(-2)
        table.setFont(table_font)
        # 右键复制菜单 + Ctrl+C
        self._setup_table_copy_menu(table)

        for r, item in enumerate(parsed_data):
            field_name = item[0]
            raw_hex = item[1]
            parsed_val = str(item[2])
            comment = item[3]
            table.insertRow(r)
            table.setItem(r, 0, QTableWidgetItem(field_name))
            table.setItem(r, 1, QTableWidgetItem(raw_hex))
            table.setItem(r, 2, QTableWidgetItem(parsed_val))
            table.setItem(r, 3, QTableWidgetItem(comment))

        layout.addWidget(table)
        dialog.setLayout(layout)
        dialog.exec()

    # ==================== 串口配置与持久化 ====================

    def _load_serial_config(self):
        """从 config.json 加载串口配置"""
        config_path = data_path("config.json")
        if not config_path.exists():
            return
        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
            serial_config = config.get("serial", {})
            port = serial_config.get("port", "")
            baud = serial_config.get("baudrate", "9600")
            parity = serial_config.get("parity", "无")

            # 应用配置（仅当值有效时）
            if port:
                idx = self.serial_port_combo.findText(port)
                if idx >= 0:
                    self.serial_port_combo.setCurrentIndex(idx)
            if baud:
                self.serial_baud_combo.setCurrentText(str(baud))
            if parity:
                self.serial_parity_combo.setCurrentText(parity)
        except Exception:
            pass

    def _get_baud_value(self) -> int | None:
        """获取并校验波特率输入（支持编辑框自定义值），无效返回 None 并提示"""
        baud_text = self.serial_baud_combo.currentText().strip()
        try:
            baud = int(baud_text)
            if baud <= 0:
                raise ValueError
            return baud
        except ValueError:
            QMessageBox.warning(self, "警告", f"波特率无效：{baud_text}，请输入正整数")
            return None

    def _resolve_config_path(self, raw: str) -> Path:
        """将配置文件路径字符串解析为绝对 Path"""
        p = Path(raw)
        if p.is_absolute():
            return p
        return app_data_dir() / p

    def _load_app_config(self):
        """加载应用配置（串口 + 文件路径）"""
        # 窗口几何/分栏/列宽状态（顶层 "window" 段）先置空：文件缺失/损坏时
        # 保持默认布局（见 _apply_window_state）
        self._window_state: dict[str, Any] = {}
        if not self._config_path.exists():
            self._app_config = {}
            self._file_paths = {}
            return
        try:
            with open(self._config_path, encoding="utf-8") as f:
                self._app_config = json.load(f)
        except Exception:
            self._app_config = {}

        paths = self._app_config.get("file_paths", {})
        self._file_paths = {}
        for key, val in paths.items():
            if val:
                self._file_paths[key] = self._resolve_config_path(val)

        # 加载南网/国网新一代通道配置
        parse_cfg = self._app_config.get("parse", {})
        self._csg_channel = parse_cfg.get("csg_channel", "auto")
        self._gw_channel = parse_cfg.get("gw_channel", "plc")
        # 上次使用的协议索引（启动时恢复选中，避免每次手动选择）
        try:
            self._saved_protocol = int(parse_cfg.get("protocol", 0))
        except (TypeError, ValueError):
            self._saved_protocol = 0
        # 同步到 combo（combo 在 create_single_parse_tab 中创建，稍后初始化时设置）

        # 顶部栏折叠状态（独立顶层 "top_bar" 段；**不要**写入 "ui"——该段由
        # ThemeManager.to_config 整体重建）。缺省 = 展开。
        # 兼容 1.23.41 初版的 proto_collapsed/serial_collapsed（任一为真即视为整栏折叠）。
        top_bar_cfg = self._app_config.get("top_bar", {})
        if not isinstance(top_bar_cfg, dict):
            top_bar_cfg = {}
        if "collapsed" in top_bar_cfg:
            self._saved_topbar_collapsed = bool(top_bar_cfg.get("collapsed", False))
        else:
            self._saved_topbar_collapsed = bool(
                top_bar_cfg.get("proto_collapsed", False)
                or top_bar_cfg.get("serial_collapsed", False)
            )

        # 窗口几何 / 分栏 / 列宽（顶层 "window" 段，由 closeEvent 真实退出路径写出）。
        # 只解析成数据，不碰 widget（此时 UI 还未建）；套用在 __init__ 末尾
        # 与 _update_protocol_lookup_tab 里。结构不合法则置空 → 回落默认布局。
        win_cfg = self._app_config.get("window", {})
        self._window_state = win_cfg if isinstance(win_cfg, dict) else {}

    # ==================== 窗口状态持久化：几何 / 分栏 / 列宽 ====================
    # 存储：config.json 顶层 "window" 段（**不要**塞进 "ui" 段——该段每次保存都由
    # ThemeManager.to_config 整体重建，塞进去会被下一次保存抹掉）。
    # 时机：载入（_load_app_config）只解析成 self._window_state；套用在 __init__ 末尾
    # （_apply_window_state）与查询页重建后（_update_protocol_lookup_tab）；写出只在
    # closeEvent 的真实退出路径（最小化到托盘不写）。
    # 容错：任何键缺失 / 类型错误 / base64 损坏 / 列数不匹配 → 静默回落默认布局。

    def _collect_window_state(self) -> dict:
        """收集当前窗口几何 / 分栏 / 关键表格列宽（退出时写入 config.json）。"""
        state: dict[str, Any] = {}
        try:
            state["geometry"] = base64.b64encode(bytes(self.saveGeometry())).decode(
                "ascii"
            )
        except Exception:
            pass

        splitter = getattr(self, "result_splitter", None)
        if splitter is not None:
            try:
                state["splitter"] = base64.b64encode(
                    bytes(splitter.saveState())
                ).decode("ascii")
            except Exception:
                pass
            try:
                state["splitter_sizes"] = [int(s) for s in splitter.sizes()]
            except Exception:
                pass

        columns: list[dict[str, Any]] = []
        for name in _WINDOW_STATE_TABLES:
            table = getattr(self, name, None)
            if table is None:
                continue
            try:
                header = table.horizontalHeader()
                count = int(header.count())
                if count <= 0:
                    continue
                columns.append(
                    {
                        "name": name,
                        "count": count,
                        "sizes": [int(header.sectionSize(i)) for i in range(count)],
                    }
                )
            except Exception:
                continue
        if columns:
            state["columns"] = columns
        return state

    @staticmethod
    def _is_rect_visible(rect) -> bool:
        """rect 是否与任一屏幕的可用区相交（防换显示器/降分辨率后窗口丢到屏外）。"""
        try:
            screens = QGuiApplication.screens()
        except Exception:
            return True
        if not screens:
            return True  # 拿不到屏幕信息时不做判断，宁可不丢保存值
        try:
            return any(
                screen.availableGeometry().intersects(rect) for screen in screens
            )
        except Exception:
            return True

    @staticmethod
    def _default_window_rect() -> QRect:
        """默认窗口矩形：主屏可用区内居中，尺寸不超出屏幕（低分屏不溢出）。"""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return QRect(0, 0, 1000, 700)
        avail = screen.availableGeometry()
        width = min(1000, int(avail.width()))
        height = min(700, int(avail.height()))
        x = avail.x() + max(0, (int(avail.width()) - width) // 2)
        y = avail.y() + max(0, (int(avail.height()) - height) // 2)
        return QRect(x, y, width, height)

    def _apply_default_geometry(self):
        """恢复默认尺寸并居中（保存值缺失/损坏/屏外时使用）。"""
        rect = self._default_window_rect()
        self.resize(rect.width(), rect.height())
        self.move(rect.x(), rect.y())

    def _snapshot_default_column_widths(self):
        """快照「代码默认列宽」，供 _reset_window_layout 回落。

        必须在**套用保存值之前**调用：查询页表格刚由 builder 重建、持有硬编码
        setColumnWidth 的结果时记录。已记录过的表不覆盖（setdefault 语义），
        避免把套用后的值当成默认值。
        """
        store = getattr(self, "_default_column_widths", None)
        if store is None:
            store = {}
            self._default_column_widths = store
        for name in _WINDOW_STATE_TABLES:
            if name in store:
                continue
            table = getattr(self, name, None)
            if table is None:
                continue
            try:
                header = table.horizontalHeader()
                count = int(header.count())
                if count <= 0:
                    continue
                store[name] = [int(header.sectionSize(i)) for i in range(count)]
            except Exception:
                continue

    @staticmethod
    def _column_sizes_valid(sizes, count: int) -> bool:
        """列宽数组必须与列数等长、且为 10~4000 的整数（坏值一律丢弃）。"""
        if not isinstance(sizes, list) or len(sizes) != count:
            return False
        for width in sizes:
            if isinstance(width, bool) or not isinstance(width, int):
                return False
            if not 10 <= width <= 4000:
                return False
        return True

    def _apply_saved_column_widths(self):
        """套用保存的列宽；表不存在 / 列数不匹配（协议切换重建）则跳过该表。"""
        state = getattr(self, "_window_state", None)
        block = state.get("columns") if isinstance(state, dict) else None
        if not isinstance(block, list):
            return
        for entry in block:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if name not in _WINDOW_STATE_TABLES:
                continue
            table = getattr(self, name, None)
            if table is None:
                continue
            try:
                header = table.horizontalHeader()
                count = int(header.count())
                if entry.get("count") != count:
                    continue
                sizes = entry.get("sizes")
                if not self._column_sizes_valid(sizes, count):
                    continue
                for i, width in enumerate(sizes):
                    table.setColumnWidth(i, int(width))
            except Exception:
                continue

    def _apply_window_state(self):
        """把 self._window_state 套到窗口上（全程容错，异常即保持默认布局）。"""
        # 列宽：先快照代码默认值，再套用保存值（顺序不可颠倒，否则「恢复默认
        # 布局」会把套用后的宽度当作默认值）
        self._snapshot_default_column_widths()
        self._apply_saved_column_widths()

        state = getattr(self, "_window_state", None)
        if not isinstance(state, dict):
            state = {}

        # 分栏比例：优先 saveState 的 base64，退回 sizes 列表
        splitter = getattr(self, "result_splitter", None)
        if splitter is not None:
            restored = False
            blob = state.get("splitter")
            if isinstance(blob, str) and blob:
                try:
                    raw = base64.b64decode(blob.encode("ascii"), validate=True)
                    restored = bool(raw) and bool(splitter.restoreState(raw))
                except Exception:
                    restored = False
            if not restored:
                sizes = state.get("splitter_sizes")
                try:
                    if (
                        isinstance(sizes, list)
                        and len(sizes) == splitter.count()
                        and all(
                            isinstance(s, int) and not isinstance(s, bool) and s >= 0
                            for s in sizes
                        )
                    ):
                        splitter.setSizes([int(s) for s in sizes])
                except Exception:
                    pass

        # 窗口几何：保存值缺失 / 损坏 / 落在所有屏幕之外 → 回退默认居中尺寸
        # （多屏拔掉外接显示器是常见场景，绝不能把窗口丢到屏幕外）
        geo = state.get("geometry")
        if isinstance(geo, str) and geo:
            applied = False
            try:
                raw = base64.b64decode(geo.encode("ascii"), validate=True)
                applied = bool(raw) and bool(self.restoreGeometry(raw))
            except Exception:
                applied = False
            if applied:
                try:
                    applied = self._is_rect_visible(self.geometry())
                except Exception:
                    applied = False
            if not applied:
                self._apply_default_geometry()

    def _reset_window_layout(self):
        """配置菜单「恢复默认窗口布局」：清掉保存状态并立即回落默认布局。"""
        self._window_state = {}
        self._app_config.pop("window", None)
        self._save_app_config()  # 立即写盘：清空顶层 "window" 段
        self._apply_default_geometry()
        splitter = getattr(self, "result_splitter", None)
        if splitter is not None:
            try:
                splitter.setSizes([450, 550])
            except Exception:
                pass
        for name, sizes in dict(getattr(self, "_default_column_widths", {})).items():
            table = getattr(self, name, None)
            if table is None:
                continue
            try:
                count = int(table.horizontalHeader().count())
                for i in range(min(count, len(sizes))):
                    table.setColumnWidth(i, int(sizes[i]))
            except Exception:
                continue
        try:
            self.statusBar().showMessage("已恢复默认窗口布局", 3000)
        except Exception:
            pass

    def _load_system_settings(self):
        """加载系统集成设置（config.json "system" 段）"""
        from system_integration.system_settings import DEFAULT_SYSTEM_SETTINGS

        settings = dict(DEFAULT_SYSTEM_SETTINGS)
        sys_cfg = self._app_config.get("system", {})
        if isinstance(sys_cfg, dict):
            for k in settings:
                if k in sys_cfg:
                    settings[k] = sys_cfg[k]
        self._system_settings = settings

    def _apply_system_settings(self, settings: dict):
        """应用系统集成设置（对话框确定 / 托盘自启开关时调用）"""
        self._system_settings = dict(settings)
        # 写入 config.json
        try:
            config = {}
            if self._config_path.exists():
                with open(self._config_path, encoding="utf-8") as f:
                    config = json.load(f)
            config["system"] = self._system_settings
            atomic_write_json(self._config_path, config)
        except Exception as e:
            print(f"[系统设置保存失败] {e}")

        # 开机自启
        from system_integration.registry_menu import set_autostart

        try:
            set_autostart(bool(self._system_settings.get("auto_start")))
        except Exception as e:
            print(f"[开机自启设置失败] {e}")

        # 托盘自启开关状态同步
        if hasattr(self, "_tray_manager") and self._tray_manager is not None:
            self._tray_manager.update_autostart_state()

        # 全局热键：设置变更后重启热键监听
        if hasattr(self, "_hotkey_manager") and self._hotkey_manager is not None:
            self._restart_hotkey()

        # 剪贴板监听开关
        if hasattr(self, "_clipboard_monitor") and self._clipboard_monitor is not None:
            self._clipboard_monitor.set_enabled(
                bool(self._system_settings.get("clipboard_monitor", True))
            )

    def _save_app_config(self):
        """保存应用配置到 config.json"""
        config: dict[str, Any] = {}
        if self._config_path.exists():
            try:
                with open(self._config_path, encoding="utf-8") as f:
                    config = json.load(f)
            except Exception:
                config = {}

        # 更新串口配置
        config["serial"] = {
            "port": self.serial_port_combo.currentText(),
            "baudrate": self.serial_baud_combo.currentText(),
            "parity": self.serial_parity_combo.currentText(),
        }

        # 更新文件路径配置
        file_paths: dict[str, str] = {}
        for key, path in self._file_paths.items():
            if path:
                try:
                    rel = path.relative_to(app_data_dir())
                    file_paths[key] = str(rel)
                except ValueError:
                    file_paths[key] = str(path)
        config["file_paths"] = file_paths

        # 单帧解析偏好：是否校验该帧（容错解析开关）
        if hasattr(self, "verify_frame_chk"):
            config["single_parse"] = {"verify": bool(self.verify_frame_chk.isChecked())}

        # 更新主题与字体配置（含毛玻璃参数）
        config["ui"] = ThemeManager.to_config(
            self._theme_id,
            self._font_family,
            self._font_size,
            glass=getattr(self, "_glass_settings", None),
            mode=getattr(self, "_appearance_mode", None),
        )

        # 更新 LLM 预处理配置
        if hasattr(self, "llm_preprocess_widget"):
            self.llm_preprocess_widget.save_config()

        # 保存通道配置
        parse_cfg = config.get("parse", {})
        parse_cfg["csg_channel"] = getattr(self, "_csg_channel", "plc")
        parse_cfg["gw_channel"] = getattr(self, "_gw_channel", "plc")
        parse_cfg["protocol"] = getattr(self, "current_protocol", 0)
        config["parse"] = parse_cfg

        # 顶部栏折叠状态（独立顶层 "top_bar" 段；勿写入 ui 段）。
        # 用菜单栏 toggle 的 checked 判定，不依赖 isVisible()——父窗口未 show 时后者恒 False。
        try:
            topbar_collapsed = not self.topbar_toggle_btn.isChecked()
        except Exception:
            topbar_collapsed = getattr(self, "_saved_topbar_collapsed", False)
        top_bar_state = config.get("top_bar", {})
        if not isinstance(top_bar_state, dict):
            top_bar_state = {}
        # 只保留单一 collapsed 键（清掉 1.23.41 初版的分键，避免双源漂移）
        config["top_bar"] = {"collapsed": topbar_collapsed}

        # 窗口几何/分栏/列宽（顶层 "window" 段）。只有 closeEvent 的真实退出路径
        # 会把 _window_state 填成最新值（_collect_window_state）；其余保存点沿用
        # 载入值，避免切协议/改串口配置时把中途布局当退出布局写盘。空则删键。
        win_state = getattr(self, "_window_state", None)
        if isinstance(win_state, dict) and win_state:
            config["window"] = win_state
        else:
            config.pop("window", None)

        try:
            atomic_write_json(self._config_path, config)
        except Exception as e:
            print(f"[配置保存失败] {e}")

    def _show_config_dialog(self):
        """显示配置路径管理对话框"""
        # 构建当前路径字典（字符串形式传给对话框）
        current_paths: dict[str, str] = {}
        for key, path in self._file_paths.items():
            if path:
                try:
                    rel = path.relative_to(app_data_dir())
                    current_paths[key] = str(rel)
                except ValueError:
                    current_paths[key] = str(path)

        dialog = ConfigDialog(current_paths, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_paths = dialog.get_file_paths()
        self._file_paths = {}
        for key, val in new_paths.items():
            if val:
                self._file_paths[key] = self._resolve_config_path(val)

        # 保存到 config.json
        self._save_app_config()

        # 动态刷新各页面
        self.preset_tab.set_file_paths(
            nw_path=self._file_paths.get("nw_command"),
            gw_path=self._file_paths.get("gw_command"),
        )
        self.test_plan_tab.set_file_path(self._file_paths.get("test_plan"))

        QMessageBox.information(self, "配置", "配置文件路径已更新并保存。")

    def _save_serial_config(self):
        """保存串口配置到 config.json（保留现有 file_paths）"""
        self._save_app_config()

    # ==================== 主题与字体 ====================

    def _is_dark_theme(self) -> bool:
        """当前**实际**是否深色（主题 + 外观模式 + 系统深浅共同决定）。"""
        try:
            return ThemeManager.resolve_appearance(
                self._theme_id,
                getattr(self, "_appearance_mode", "light"),
                getattr(self, "_system_dark", False),
            )[1]
        except Exception:  # noqa: BLE001
            return self._theme_id == "dark"

    def _make_stats_label(self, text: str = "", size: int = 12) -> QLabel:
        """创建随主题适配的统计/状态标签（注册到列表，主题切换时统一重设）"""
        lbl = QLabel(text)
        lbl.setStyleSheet(self._stats_style(size))
        self._stats_labels.append((lbl, size))
        return lbl

    def _stats_style(self, size: int = 12) -> str:
        """统计/状态标签样式（暗色主题下用浅灰文字）"""
        color = "#aaa" if self._is_dark_theme() else "#666"
        return f"color: {color}; font-size: {size}px;"

    def _make_toolbar_separator(self) -> QFrame:
        """工具栏分组竖线：同一行里靠它把「核心操作 | 导出」「预处理 | 脚本」分开。

        ``setFixedWidth(1)`` 而不是只设 frameShape：FlowLayout 按 sizeHint 排布，
        QFrame 默认 sizeHint 会带上边距，不固定就留出一条明显的空隙。
        """
        line = QFrame()
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setFixedWidth(1)
        line.setMinimumHeight(20)
        return line

    def _make_toolbar_btn(
        self, text: str = "", height: int = 24, min_width: int = 0
    ) -> QPushButton:
        """创建统一风格的工具栏按钮。

        统一设计原则：按钮不设置显式字体（继承应用字体，字体设置实时统一缩放）、
        不用 setFixedHeight（setMinimumHeight 仅为下限，内容随字体增长）。

        参数:
            text: 按钮文本
            height: 最小高度（默认 28，与工具栏其他控件对齐）
            min_width: 最小宽度，0 表示由内容决定
        """
        btn = QPushButton(text)
        btn.setMinimumHeight(height)
        if min_width:
            btn.setMinimumWidth(min_width)
        return btn

    def _batch_count_style(self) -> str:
        """批量解析帧计数标签样式"""
        if self._is_dark_theme():
            return "color: #bbb; font-size: 12px; padding: 2px 10px; background: #3a3a3a; border-radius: 10px;"
        return "color: #666; font-size: 12px; padding: 2px 10px; background: #f0f0f0; border-radius: 10px;"

    def _batch_status_style(self) -> str:
        """批量解析状态栏样式"""
        if self._is_dark_theme():
            return (
                "color: #bbb; font-size: 12px; padding: 4px 10px; "
                "background: #333333; border: 1px solid #555555; border-radius: 4px;"
            )
        return (
            "color: #666; font-size: 12px; padding: 4px 10px; "
            "background: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 4px;"
        )

    def _serial_status_style(self, color: str, bold: bool = False) -> str:
        """串口状态标签样式（灰色在暗色下提亮；同时记录当前颜色/粗体供主题切换重设）"""
        self._serial_status_color = color
        self._serial_status_bold = bold
        if self._is_dark_theme() and color == "#999":
            color = "#bbb"
        weight = " font-weight: bold;" if bold else ""
        return f"color: {color}; font-size: 12px;{weight}"

    def _serial_refresh_style(self) -> str:
        """串口刷新按钮样式（hover 色随主题明暗）"""
        if self._is_dark_theme():
            return (
                "QPushButton { background: transparent; border: none; padding: 2px; }"
                "QPushButton:hover { background: rgba(255,255,255,25); border-radius: 3px; }"
                "QPushButton:pressed { background: rgba(255,255,255,50); }"
            )
        return (
            "QPushButton { background: transparent; border: none; padding: 2px; }"
            "QPushButton:hover { background: rgba(0,0,0,20); border-radius: 3px; }"
            "QPushButton:pressed { background: rgba(0,0,0,40); }"
        )

    def _ui_font(self, delta: int = 0, bold: bool = False, family: str = None) -> QFont:
        """统一字体：字号跟随配置 _font_size，字体族跟随配置 _font_family（可覆盖）。

        层级约定（相对 _font_size，默认10）：
          delta=0  正文/搜索框/编辑区/主下拉
          delta=-1 普通标签/输入框/按钮/次要说明
          delta=-2 表格
          delta=+6 大标题
        """
        f = QFont(family or self._font_family, self._font_size + delta)
        f.setBold(bold)
        return f

    def _restyle_for_theme(self):
        """主题切换后重设动态控件样式（统计标签/串口状态/批量状态等）"""
        for lbl, size in self._stats_labels:
            try:
                lbl.setStyleSheet(self._stats_style(size))
            except RuntimeError:
                pass  # 退出时 C++ 对象已析构，忽略
        if hasattr(self, "serial_status_label"):
            try:
                self.serial_status_label.setStyleSheet(
                    self._serial_status_style(
                        self._serial_status_color, self._serial_status_bold
                    )
                )
            except RuntimeError:
                pass
        if hasattr(self, "serial_refresh_btn"):
            try:
                self.serial_refresh_btn.setStyleSheet(self._serial_refresh_style())
            except RuntimeError:
                pass
        if hasattr(self, "topbar_toggle_btn"):
            try:
                self._sync_topbar_toggle_btn()
            except RuntimeError:
                pass
        if hasattr(self, "appearance_btn"):
            try:
                self._sync_appearance_btn()
            except RuntimeError:
                pass
        if hasattr(self, "_serial_statusbar_lbl"):
            try:
                self._update_serial_statusbar()
            except RuntimeError:
                pass
        if hasattr(self, "batch_frame_count_label"):
            try:
                self.batch_frame_count_label.setStyleSheet(self._batch_count_style())
            except RuntimeError:
                pass
        if hasattr(self, "batch_status_bar"):
            try:
                self.batch_status_bar.setStyleSheet(self._batch_status_style())
            except RuntimeError:
                pass
        if getattr(self, "_update_status_lbl", None) is not None:
            try:
                self._update_status_lbl.setStyleSheet(self._update_status_style())
            except RuntimeError:
                pass
        if getattr(self, "diff_tab", None) is not None:
            try:
                self.diff_tab.restyle_for_theme(self._is_dark_theme())
            except RuntimeError:
                pass
        if getattr(self, "spectrum_tab", None) is not None:
            try:
                self.spectrum_tab.restyle_for_theme(self._is_dark_theme())
            except RuntimeError:
                pass
        if getattr(self, "bluetooth_tool_tab", None) is not None:
            try:
                self.bluetooth_tool_tab.restyle_for_theme(self._is_dark_theme())
            except RuntimeError:
                pass
        if getattr(self, "upgrade_tab", None) is not None:
            try:
                self.upgrade_tab.restyle_for_theme(self._is_dark_theme())
            except RuntimeError:
                pass
        if getattr(self, "test_tab", None) is not None:
            try:
                self.test_tab.restyle_for_theme(self._is_dark_theme())
            except RuntimeError:
                pass
        if getattr(self, "testbench_tab", None) is not None:
            try:
                self.testbench_tab.restyle_for_theme(self._is_dark_theme())
            except RuntimeError:
                pass
        # 字段树与解析结果表同字号（主题 QSS 已含 QTreeWidget）
        if getattr(self, "result_tree_widget", None) is not None:
            try:
                f = self.result_table_widget.font()
                self.result_tree_widget.apply_table_style(f)
            except RuntimeError:
                pass

    def _show_theme_settings_dialog(self):
        """显示主题与字体设置对话框（含系统集成设置）"""
        dialog = ThemeSettingsDialog(
            self._theme_id,
            self._font_family,
            self._font_size,
            glass=self._glass_settings,
            parent=self,
            mode=getattr(self, "_appearance_mode", "light"),
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._theme_id, self._font_family, self._font_size = dialog.get_settings()
            self._glass_settings = dialog.get_glass_settings()
            self._save_app_config()
            # 应用系统集成设置（自启 / 热键 / 关闭行为）
            sys_settings = dialog.get_system_settings()
            self._apply_system_settings(sys_settings)
        # 无论确定/取消（取消时对话框已还原主题），同步动态控件样式
        self._restyle_for_theme()

    def _show_system_settings_dialog(self):
        """显示系统集成设置对话框（配置菜单→系统集成设置）"""
        from system_integration.system_settings import SystemIntegrationSettings

        dialog = QDialog(self)
        dialog.setWindowTitle("系统集成设置")
        dialog.setMinimumWidth(560)
        dialog.setWindowFlags(
            dialog.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        layout = QVBoxLayout(dialog)
        panel = SystemIntegrationSettings(dialog)
        layout.addWidget(panel)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(dialog.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._apply_system_settings(panel.save_settings())

    def _show_llm_api_manager(self):
        """显示 LLM 模型 API 管理对话框"""
        dlg = LLMApiManagerDialog(self)
        dlg.exec()
        # 关闭后刷新 LLM 预处理面板的模型列表
        if hasattr(self, "llm_preprocess_widget"):
            self.llm_preprocess_widget._refresh_profiles()

    def _refresh_serial_ports(self):
        """刷新可用串口列表"""
        from serial_worker import SerialWorker

        current = self.serial_port_combo.currentText()
        self.serial_port_combo.clear()
        ports = SerialWorker.list_ports()
        for p in ports:
            self.serial_port_combo.addItem(p)
        # 恢复之前选中的端口（如果仍在列表中）
        if current:
            idx = self.serial_port_combo.findText(current)
            if idx >= 0:
                self.serial_port_combo.setCurrentIndex(idx)
        self._update_serial_statusbar()

    def _on_serial_open_clicked(self):
        """打开/关闭串口按钮点击"""
        if self.serial_worker.is_open():
            self.serial_worker.close_port()
            self.serial_open_btn.setText("打开串口")
            set_btn(self.serial_open_btn, "success")
            self.serial_port_combo.setEnabled(True)
            self.serial_baud_combo.setEnabled(True)
            self.serial_parity_combo.setEnabled(True)
            self.serial_status_label.setText("未连接")
            self.serial_status_label.setStyleSheet(self._serial_status_style("#999"))
            self._update_serial_statusbar()
            self._save_serial_config()
        else:
            port = self.serial_port_combo.currentText()
            if not port:
                QMessageBox.warning(self, "警告", "请先选择串口端口")
                return
            baud = self._get_baud_value()
            if baud is None:
                return
            parity = self.serial_parity_combo.currentText()
            self.serial_worker.configure(port, baudrate=baud, parity=parity)
            if self.serial_worker.open_port():
                self.serial_open_btn.setText("关闭串口")
                set_btn(self.serial_open_btn, "danger")
                self.serial_port_combo.setEnabled(False)
                self.serial_baud_combo.setEnabled(False)
                self.serial_parity_combo.setEnabled(False)
                self.serial_status_label.setText("已连接")
                self.serial_status_label.setStyleSheet(
                    "color: #4CAF50; font-size: 12px;"
                )
                self._update_serial_statusbar()
                self._save_serial_config()

    def _on_serial_connection_changed(self, connected: bool):
        """串口连接状态变化回调"""
        if not connected and self.serial_open_btn.text() == "关闭串口":
            # 被动断开（如设备拔出）
            self.serial_open_btn.setText("打开串口")
            set_btn(self.serial_open_btn, "success")
            self.serial_port_combo.setEnabled(True)
            self.serial_baud_combo.setEnabled(True)
            self.serial_parity_combo.setEnabled(True)
            self.serial_status_label.setText("未连接")
            self.serial_status_label.setStyleSheet(self._serial_status_style("#999"))
            self._update_serial_statusbar()

    def _on_serial_error(self, msg: str):
        """串口错误回调"""
        self.serial_status_label.setText(f"错误: {msg}")
        self.serial_status_label.setStyleSheet(self._serial_status_style("#f44336"))
        self._update_serial_statusbar()

    def _on_serial_baudrate_changed(self, baud: int):
        """串口线程**自行**改了波特率（协议8 升级页「提升波特率」）→ 顶部回显同步。

        端口/波特率名义上归这里，但「升级中途换速率」只能由**持口的那一方**做：本页重开
        端口会掉线（一个 COM 口只能开一次，见 ``_on_serial_open_clicked``）。故由
        ``SerialWorker.baudrate_changed`` 反向通知，把下拉框文字与状态栏回显对齐**实际**
        速率 —— 否则会出现「UI 说 9600、线上跑 115200」这种现场查不出来的假象。

        **刻意不落盘**：热切换是升级过程的临时状态（升级收尾会自动切回默认速率），
        写进 config.json 会把它变成用户下次启动的新默认值。
        """
        text = str(int(baud))
        if self.serial_baud_combo.currentText() != text:
            self.serial_baud_combo.blockSignals(True)
            self.serial_baud_combo.setCurrentText(text)
            self.serial_baud_combo.blockSignals(False)
        self._update_serial_statusbar()


def _report_crash_to_github(crash_path, crash_summary: str) -> None:
    """崩溃后把现场提交成 GitHub issue（模块级函数，崩溃时 MainWindow 可能还没建好）。

    崩溃发生在建窗阶段时没有主窗口可用，故这里自建对话框；仓库地址与令牌
    的取法与「帮助 → 提交问题到 GitHub」完全一致（同一份 AUTHOR_GITHUB_URL
    与 config.json），两条入口不会出现「一个能提交一个不能」的分裂。
    """
    try:
        from github_issue import resolve_owner_repo, resolve_token
        from github_issue_dialog import GitHubIssueDialog

        owner, repo = resolve_owner_repo(AUTHOR_GITHUB_URL)
        config_path = data_path("config.json")
        dlg = GitHubIssueDialog(
            parent=None,
            owner=owner,
            repo=repo,
            token=resolve_token(config_path),
            app_version=APP_VERSION,
            build_date=BUILD_DATE,
            config_path=config_path,
            crash_summary=str(crash_summary or ""),
        )
        dlg.setWindowTitle("提交崩溃报告到 GitHub")
        dlg.exec()
        if dlg.token_edit.text().strip():
            dlg.persist_token()
    except Exception:                      # noqa: BLE001 - 崩溃路径上不能再抛
        try:
            QMessageBox.warning(
                None, "提交崩溃报告",
                f"崩溃报告窗口打开失败，请手动反馈。\n崩溃日志：{crash_path}",
            )
        except Exception:                  # noqa: BLE001
            pass


def main():
    # 打包后自检：`exe --self-test` 不启动界面、不读配置、不写文件，返回码 0 才算合格。
    # 放在单实例检查之前 —— 自检不该被「已有实例在运行」拦掉。
    if "--self-test" in sys.argv[1:]:
        try:
            from self_test import run as _run_self_test

            sys.exit(_run_self_test())
        except SystemExit:
            raise
        except Exception:            # noqa: BLE001 - 自检自身失败也要给出非 0
            sys.exit(2)

    # 修复 Windows 终端中文乱码：将 stdout/stderr 切换为 UTF-8
    # PyInstaller GUI 模式（console=False）下 sys.stdout/stderr 为 None，需守卫
    if sys.platform == "win32":
        import io

        if sys.stdout is not None:
            sys.stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace"
            )
        if sys.stderr is not None:
            sys.stderr = io.TextIOWrapper(
                sys.stderr.buffer, encoding="utf-8", errors="replace"
            )

    # 单实例：已有实例在运行则传参并退出。
    # `NW_NO_SINGLE_INSTANCE=1` 仅供自动化冒烟（离屏启动验证）使用，正常用户不会设置。
    from system_integration.single_instance import try_connect_existing

    if os.environ.get("NW_NO_SINGLE_INSTANCE") != "1" and try_connect_existing(sys.argv[1:]):
        return 0

    app = QApplication(sys.argv)

    # 未捕获异常兜底：打包后 console=False，没有控制台，崩溃现场只能落文件。
    # 放在 MainWindow 之前安装 —— 建窗过程中的异常同样能记下来。
    try:
        import threading as _threading

        from crash_handler import install as _install_crash_handler

        def _on_crash(path, _summary):
            if _threading.current_thread() is not _threading.main_thread():
                return                     # 子线程里不要碰界面
            try:
                where = f"\n\n崩溃日志：{path}" if path else "\n\n（崩溃日志写入失败）"
                box = QMessageBox(None)
                box.setIcon(QMessageBox.Icon.Critical)
                box.setWindowTitle("程序遇到错误")
                box.setText(
                    "程序遇到未处理的错误，已记录现场。" + where
                    + "\n\n可点「提交到 GitHub」把崩溃现场自动发成一条 issue"
                    "（需填令牌），或用「帮助 → 生成诊断包」把日志发给我们。"
                )
                gh_btn = box.addButton("提交到 GitHub", QMessageBox.ButtonRole.AcceptRole)
                box.addButton("确定", QMessageBox.ButtonRole.RejectRole)
                box.exec()
                if box.clickedButton() is gh_btn:
                    _report_crash_to_github(path, _summary)
            except Exception:              # noqa: BLE001 - 提示失败不能再抛
                pass

        _install_crash_handler(APP_VERSION, BUILD_DATE, app_data_dir(), _on_crash)
    except Exception:                      # noqa: BLE001 - 兜底安装失败不影响启动
        pass

    # 提前设全局默认字体，避免 Qt 回退到 MS Sans Serif 触发 DirectWrite 警告
    app.setFont(QFont("Microsoft YaHei UI", 9))

    # 应用主题与字体设置（从 config.json 读取，未配置时使用默认浅色主题 + 微软雅黑 10pt）
    ThemeManager.apply_from_file(app)

    window = MainWindow()

    # 处理命令行参数（--parse / --protocol / --file / --minimized / --clipboard）
    cli_args = [a for a in sys.argv[1:] if a]
    has_parse_action = any(a in ("--parse", "--file", "--clipboard") for a in cli_args)

    if cli_args and not has_parse_action:
        window.show()
        window._handle_cli_args(cli_args)
    elif has_parse_action:
        # 解析动作：不显示主窗口，直接弹解析结果（避免窗口太多）
        window._handle_cli_args(cli_args)
    else:
        window.show()

    sys.exit(app.exec())


class _UpdateStatusLink(QLabel):
    """状态栏「发现新版本」提示标签（可点击，发出 clicked 信号）。"""

    clicked = Signal()

    def mousePressEvent(self, ev):
        self.clicked.emit()
        super().mousePressEvent(ev)


class _UpdateCheckWorker(QThread):
    """后台线程检查更新（QThread 子类化，避免 moveToThread + lambda 跨线程坑）。"""

    result_ready = Signal(dict)  # 最新版本检查结果
    release_list_ready = Signal(list, str)  # 全部版本列表 + 错误信息（list_all 模式）

    def __init__(
        self,
        cfg: dict,
        local_version: str,
        list_all: bool = False,
        repo_url: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.cfg = cfg
        self.local_version = local_version
        self.list_all = list_all
        self.repo_url = repo_url

    def run(self):
        if self.list_all:
            err = ""
            rels = []
            try:
                from auto_updater import VersionChecker

                rels = VersionChecker(self.cfg).fetch_all_releases()
            except Exception as e:
                err = str(e)
            self.release_list_ready.emit(rels, err)
            return
        from auto_updater import check_for_update

        res = check_for_update(
            self.local_version, self.cfg, repo_url=self.repo_url
        )
        self.result_ready.emit(res)


class _UpdateDownloadWorker(QThread):
    """后台线程下载新版 exe（多线程分段 + 可暂停 / 取消）。"""

    stats = Signal(object)                 # downloader.DownloadProgress（逐线程明细/速率）
    paused = Signal()                      # 已暂停（线程已停在块边界）
    cancelled = Signal()                   # 已取消（临时文件已清理）
    done = Signal(bool, str, str)          # (ok, error, new_path)

    def __init__(
        self, url: str, dest_file: Path, sha256: str, verify_sha: bool = True,
        parent=None, max_threads: int | None = None,
    ):
        super().__init__(parent)
        self.url = url
        self.dest_file = Path(dest_file)
        self.sha256 = sha256
        # 「配置→更新设置」的「校验 SHA-256」开关**真的生效**：
        # 关掉即不带预期摘要（此前是死开关，勾不勾都按「有摘要就校验」走）
        self.verify_sha = bool(verify_sha)
        # 下载线程数上限（None = 按文件大小/CPU 自适应，上限 32）
        self.max_threads = max_threads

        from downloader import DownloadControl

        #: 暂停 / 取消的控制句柄（GUI 通过 pause()/resume()/cancel() 操作）
        self.control = DownloadControl()
        #: 取消时临时文件去留：正常「取消」= clean（回收磁盘）；程序退出前置 keep
        #: （已下载的分段要留着，下次才能续传，否则关一次程序就白下几白 MB）
        self.on_cancel = "clean"

    # ── 外部控制 ────────────────────────────────────────────────────
    def pause(self) -> None:
        """暂停：各线程在下一个 64 KB 块边界停下，已完成字节保留（可续传）。"""
        self.control.pause()

    def resume(self) -> None:
        """继续：从断点接着下（复用续传机制，不重头再来）。"""
        self.control.resume()

    def cancel(self) -> None:
        """取消：立即停下，并清理已下载的临时文件。"""
        self.control.cancel()

    # ── 主流程 ──────────────────────────────────────────────────────
    def run(self):
        from auto_updater import Opdater, is_pe_executable
        from downloader import DownloadCancelled

        expected = self.sha256 if self.verify_sha else ""
        self.control.reset()
        op = Opdater(max_threads=self.max_threads)
        try:
            # 暂停 = 「本轮下载提前返回、目标文件还没生成」；继续 = 再来一轮（复用续传）
            while True:
                if self.control.cancelled:
                    self.cancelled.emit()
                    return
                try:
                    op.download(
                        self.url,
                        self.dest_file,
                        stats_cb=self.stats.emit,
                        control=self.control,
                        on_cancel=self.on_cancel,
                    )
                except DownloadCancelled:
                    self.cancelled.emit()
                    return
                except Exception as exc:      # noqa: BLE001
                    # 用户取消引发的网络/读取异常统一按「已取消」处理
                    if self.control.cancelled:
                        self.cancelled.emit()
                        return
                    self.done.emit(False, str(exc), str(self.dest_file))
                    return

                if self.control.cancelled:
                    self.cancelled.emit()
                    return
                # 暂停：dest 尚未生成（合并只在全部段完成后才做）
                if self.control.paused and not self.dest_file.exists():
                    self.paused.emit()
                    # **阻塞等** resume()/cancel()，不要 sleep(0.1) 轮询：
                    # 轮询会让暂停期间的「继续」平均晚 50ms 才生效，且浪费唤醒。
                    self.control.wait_resumed()
                    if self.control.cancelled:
                        if self.on_cancel == "clean":
                            from downloader import cleanup_partial

                            cleanup_partial(self.dest_file)
                        self.cancelled.emit()
                        return
                    continue                 # 继续下载（断点续传）
                break                        # 真正完成

            if expected and not op.verify(self.dest_file, expected):
                self.done.emit(
                    False, "SHA-256 校验失败，文件可能损坏", str(self.dest_file)
                )
                return
            # 替换 exe 前的最后一道闸：下载物必须是 Windows 可执行文件。
            # 更新源地址给错（接口 JSON / 登录页 HTML / 错误页）时魔数与体积都对不上，
            # 宁可报错也不能把正在运行的 exe 覆盖成垃圾。
            if not is_pe_executable(self.dest_file):
                self.done.emit(
                    False,
                    "下载到的文件不是 Windows 可执行程序（可能是错误页或接口数据），"
                    "已取消更新；请检查「配置→更新设置」里的更新源",
                    str(self.dest_file),
                )
                return
            self.done.emit(True, "", str(self.dest_file))
        except Exception as e:              # noqa: BLE001
            if self.control.cancelled:
                self.cancelled.emit()
                return
            self.done.emit(False, str(e), str(self.dest_file))


class _PyScriptWorker(QObject):
    """Python 脚本后台执行 Worker

    在独立线程中加载并运行脚本，通过信号返回结果或错误。
    """

    finished = Signal(str)  # 成功：返回处理后文本
    error = Signal(str)  # 失败：返回错误消息

    def __init__(self, script_path, input_text, context):
        super().__init__()
        self._script_path = script_path
        self._input_text = input_text
        self._context = context

    def run(self):
        import time

        t0 = time.time()
        try:
            from py_script_engine import load_script, run_script

            t1 = time.time()
            module = load_script(self._script_path)
            t2 = time.time()
            result = run_script(module, self._input_text, self._context)
            t3 = time.time()
            print(
                f"[脚本线程] import: {(t1 - t0) * 1000:.1f}ms, "
                f"load: {(t2 - t1) * 1000:.1f}ms, "
                f"run: {(t3 - t2) * 1000:.1f}ms, "
                f"total: {(t3 - t0) * 1000:.1f}ms"
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


if __name__ == "__main__":
    main()
