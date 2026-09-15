"""Web 版产品首页（落地页）的内容数据与纯展示组件。

**本模块不 import `reflex_web`**（与 `web_utils` / `theme_web` 同向依赖，避免循环导入）：
版本号、exe 体积、截图 data URL、下载事件、主题控件等随运行时而变的值一律由调用方
以参数注入。因此本模块可以脱离 `State` / 浏览器单独构建整页并断言，见
`test/test_web_landing.py`。

约定：
- 颜色一律引用 `theme_web.build_theme_css()` 提供的 `var(--token)`，不写裸 hex
  （品牌渐变上的白色文字是唯一例外）。
- 所有内部链接取自 `INTERNAL_LINKS`，测试据此做死链白名单校验。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import reflex as rx  # noqa: E402

# ══════════════════════════════════════════════════════════════
# 链接（单一来源）
# ══════════════════════════════════════════════════════════════

INTERNAL_LINKS = {
    "home": "/",
    "tool": "/app",
    "feedback": "/feedback",
    "share": "/share",
}
# 落地页内的锚点（section id → href）
SECTION_IDS = ("features", "protocols", "quickstart", "download")
ANCHORS = {key: f"#{key}" for key in SECTION_IDS}
# 落地页允许出现的全部站内 href（**字面量，不派生自 INTERNAL_LINKS**）。
# 若从 INTERNAL_LINKS 派生，则「渲染链接」与「白名单」同源，链接值被改错时白名单会
# 跟着一起变 → 守卫恒真（`test/test_web_landing.py` 的死链断言形同虚设）。
ALLOWED_HREFS = {
    "/",
    "/app",
    "/feedback",
    "/share",
    "#features",
    "#protocols",
    "#quickstart",
    "#download",
}

BLOG_URL = "https://blog.csdn.net/liruitao1993?type=blog"
PLATFORM_NOTE = "Windows 10 / 11 桌面客户端"

NAV_LINKS = [
    {"label": "功能特性", "href": ANCHORS["features"]},
    {"label": "支持协议", "href": ANCHORS["protocols"]},
    {"label": "快速上手", "href": ANCHORS["quickstart"]},
    {"label": "下载客户端", "href": ANCHORS["download"]},
]

# ══════════════════════════════════════════════════════════════
# 内容数据
# ══════════════════════════════════════════════════════════════

HERO_TITLE_LEAD = "电力通信协议"
HERO_TITLE_ACCENT = "一站式解析调试"
HERO_SUBTITLE = (
    "覆盖南网、国网、DLT645、698.45、新一代载波与双模互联互通等 12 种规约，"
    "从单帧解析、批量导入、协议校验到组帧下发、串口监控与 TCP 抓包，"
    "现场调试的常见动作都在同一个工具里完成。"
)

# 统计条：协议数取 len(PROTOCOLS)（`_key == "protocols"`），不写死数字
HERO_STATS = [
    {"value": "", "label": "种电力通信协议标准", "_key": "protocols"},
    {"value": "4", "label": "类数据入口：单帧 / 批量 / 串口 / TCP"},
    {"value": "100%", "label": "离线运行，免安装绿色版"},
    {"value": "MIT", "label": "许可协议 · 单文件 exe"},
]

FEATURES = [
    {
        "icon": "file_input",
        "title": "单帧解析",
        "desc": "粘贴十六进制报文按协议分层解析，点击解析行联动高亮输入框对应字节；"
        "支持帧内 CRC 回填与校验结果展示。",
    },
    {
        "icon": "list",
        "title": "批量解析",
        "desc": "从文件或剪贴板导入混杂文本，自动提取完整帧；支持监控日志前缀剥离与"
        "业务摘要，导出 JSON / CSV / Excel 报告。",
    },
    {
        "icon": "shield_check",
        "title": "协议校验",
        "desc": "起始符、长度域、校验和与 CRC 逐项给出通过 / 失败 / 警告；"
        "长度声明与实际不符时仍解析全部可见字段并显式告警。",
    },
    {
        "icon": "square_pen",
        "title": "协议组帧",
        "desc": "南网 / 国网 / 698.45 模板化组帧与预设命令一键填充，"
        "生成帧可直接经串口下发，字段改动实时回读解析预览。",
    },
    {
        "icon": "cable",
        "title": "串口通信",
        "desc": "串口参数配置、帧发送、实时接收解析与日志窗口，"
        "支持常用波特率与校验方式，发送记录可追溯。",
    },
    {
        "icon": "clipboard",
        "title": "测试方案与 Lua",
        "desc": "测试项增删改查、顺序发送、超时匹配与结果记录；可嵌入 Lua 脚本做条件分支与"
        "循环遍历，一键导出 Excel 测试报告。",
    },
    {
        "icon": "activity",
        "title": "实时监控器",
        "desc": "新一代载波与国网新一代串口原始字节流自动组帧（ED..EE / 96..16 包装），"
        "支持过滤、暂停、自动滚动与 CSV 记录。",
    },
    {
        "icon": "network",
        "title": "TCP 流量监控",
        "desc": "基于 scapy 抓包，按四元组汇总 TCP 流、双向流重组、自动识别协议并解析，"
        "支持历史 CSV 回放定位问题。",
    },
    {
        "icon": "git_compare",
        "title": "报文对比",
        "desc": "双报文按字节级与字段级对比，差异高亮并给出人话解读，"
        "可忽略校验和 / 序列号等字段，导出对比报告。",
    },
    {
        "icon": "wrench",
        "title": "报文工具",
        "desc": "ASCII / HEX 双向转换、DLT645 ±0x33 偏移、字节逆序、Pn/Fn 转换，"
        "以及 CRC-16 / 24 / 32 与校验和计算。",
    },
    {
        "icon": "chart_spline",
        "title": "频谱图",
        "desc": "频谱仪参数配合 trace 数值绘制仪器式网格频谱图，"
        "支持 MARK 标记、两点 Δ 测量、峰值搜索、积分带宽与 PNG 导出。",
    },
    {
        "icon": "search",
        "title": "查询与档案",
        "desc": "南网 DI、国网 AFN、DLT645 DI、OBIS 码、PLC RF 命令字、新一代业务标识与"
        "HDC 1.0 报文 ID 查询；档案导入导出与拓扑组网统计。",
    },
]

# 12 种协议：索引 / 协议 / 标准号 / 字节序 / 校验
# 数据来源：AGENTS.md §1 与 downloads/client_readme.md「支持协议」表（两处一致）
PROTOCOLS = [
    {
        "index": "0",
        "name": "南网协议",
        "standard": "Q/CSG1209021-2019",
        "endian": "小端",
        "check": "8 位位组算术和",
    },
    {
        "index": "1",
        "name": "PLC RF 协议（万胜海外）",
        "standard": "万胜 V1_04",
        "endian": "大端",
        "check": "累加和 & 0xFF",
    },
    {
        "index": "2",
        "name": "HDLC / 国网 DLMS",
        "standard": "IEC 62056-46",
        "endian": "大端（网络序）",
        "check": "CRC-16/FCS（CCITT）",
    },
    {
        "index": "3",
        "name": "DLMS-APDU（国网）",
        "standard": "IEC 62056-46",
        "endian": "大端",
        "check": "无",
    },
    {
        "index": "4",
        "name": "DLMS Wrapper 裸报文",
        "standard": "IEC 62056-46",
        "endian": "大端",
        "check": "无",
    },
    {
        "index": "5",
        "name": "DLMS-APDU 裸报文",
        "standard": "IEC 62056-46",
        "endian": "大端",
        "check": "无",
    },
    {
        "index": "6",
        "name": "DLT645-2007 电表协议",
        "standard": "DL/T 645-2007",
        "endian": "BCD，地址低字节在前",
        "check": "累加和 & 0xFF",
    },
    {
        "index": "7",
        "name": "国网协议",
        "standard": "Q/GDW 10376.2-2024（含福建增补 AFN 50H~56H）",
        "endian": "小端",
        "check": "8 位位组算术和",
    },
    {
        "index": "8",
        "name": "698.45 协议",
        "standard": "DL/T 698.45-2017",
        "endian": "小端",
        "check": "CRC-16（crcmod x-25）",
    },
    {
        "index": "9",
        "name": "新一代载波协议（通感一体化）",
        "standard": "通感一体化低压电力线宽带载波通信规约",
        "endian": "小端",
        "check": "CRC-32（MAC 帧）",
    },
    {
        "index": "10",
        "name": "国网新一代双模通信互联互通",
        "standard": "国网新一代双模通信互联互通技术规范",
        "endian": "小端",
        "check": "CRC-32（MAC 帧）",
    },
    {
        "index": "11",
        "name": "HDC 1.0 双模互联互通",
        "standard": "Q/GDW 12087.42-2020",
        "endian": "小端（MAC 地址大端）",
        "check": "CRC-24（FC/PB）+ CRC-32（MAC）",
    },
]

# 命令行：参数名与 main_gui.py `_handle_cli_args` 逐个一致
CLI_ACTIONS = [
    {
        "label": "按协议直接解析一条报文",
        "cmd": 'main_gui.py --parse "68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16" --protocol 0',
    },
    {
        "label": "解析日志文件中的报文",
        "cmd": "main_gui.py --file sample.log --protocol 国网新一代",
    },
    {
        "label": "读取剪贴板报文并弹出解析结果",
        "cmd": "main_gui.py --clipboard",
    },
    {
        "label": "启动后静默最小化到托盘",
        "cmd": "main_gui.py --minimized",
    },
]

SYSTEM_INTEGRATIONS = [
    {
        "icon": "monitor",
        "title": "系统托盘",
        "desc": "关闭主窗口默认最小化到托盘，左键单击显示 / 隐藏主窗口。",
    },
    {
        "icon": "zap",
        "title": "全局热键",
        "desc": "默认 Ctrl+Alt+X，复制十六进制报文后按热键即弹出解析结果。",
    },
    {
        "icon": "clipboard",
        "title": "剪贴板自动检测",
        "desc": "任意软件中复制 hex 报文自动弹提示框，自动识别协议后转入解析。",
    },
    {
        "icon": "box",
        "title": "资源管理器右键菜单",
        "desc": ".log / .txt / .hex / .bin 文件右键即可选协议直接解析。",
    },
    {
        "icon": "scroll_text",
        "title": "Notepad++ 集成",
        "desc": "在编辑器中选中报文复制后右键解析，无需切换窗口。",
    },
    {
        "icon": "terminal",
        "title": "单实例与开机自启",
        "desc": "重复启动会把命令行参数转发给已运行实例，可配置开机自启。",
    },
]

FOOTER_LINKS = [
    {"label": "作者博客", "href": BLOG_URL, "external": True},
    {"label": "问题反馈", "href": INTERNAL_LINKS["feedback"], "external": False},
    {"label": "报文分享", "href": INTERNAL_LINKS["share"], "external": False},
    {"label": "进入在线工具", "href": INTERNAL_LINKS["tool"], "external": False},
]


# ══════════════════════════════════════════════════════════════
# 样式（全部走 token；`.landing-*` 命名空间避免与工具页 GLOBAL_CSS 冲突）
# ══════════════════════════════════════════════════════════════

LANDING_CSS = """
html { scroll-behavior: smooth; }
.landing-root { background: var(--bg); min-height: 100vh; color: var(--text); }

/* ===== 顶栏 ===== */
.landing-nav {
  position: sticky; top: 0; z-index: 1000;
  background: var(--card);
  background: color-mix(in srgb, var(--card) 82%, transparent);
  backdrop-filter: saturate(180%) blur(14px);
  border-bottom: 1px solid var(--border);
}
.landing-nav-inner {
  max-width: 1200px; margin: 0 auto; padding: 10px 28px;
  display: flex; align-items: center; gap: 16px;
}
.landing-brand { display: flex; align-items: center; gap: 10px; text-decoration: none; }
.landing-brand-mark {
  width: 36px; height: 36px; border-radius: 11px; color: #fff; flex-shrink: 0;
  background: linear-gradient(135deg, var(--accent-ink), var(--accent));
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 2px 8px var(--shadow);
}
.landing-brand-name { font-weight: 700; font-size: 15px; color: var(--text); line-height: 1.2; }
.landing-brand-sub { font-size: 11px; color: var(--muted); margin-top: 2px; }
.landing-nav-links { display: flex; gap: 2px; margin-left: 10px; }
.landing-nav-link {
  padding: 7px 12px; border-radius: 9px; font-size: 14px; white-space: nowrap;
  color: var(--text-2); text-decoration: none; transition: background .16s ease, color .16s ease;
}
.landing-nav-link:hover { background: var(--accent-soft); color: var(--accent-ink); }
.landing-nav-actions { margin-left: auto; display: flex; align-items: center; gap: 10px; }
/* 顶栏主题控件复用工具页的 .app-header-btn/-select，但那套是「渐变底 + 白字」；
   本页顶栏是卡片底，需在作用域内改回 token 配色（含浅/深两套） */
.landing-nav .app-header-select {
  background: var(--field-bg); border: 1px solid var(--border-strong); color: var(--text-2);
}
.landing-nav .app-header-select:hover { background: var(--card-hover); }
.landing-nav .app-header-select option { color: var(--text); background: var(--card); }
.landing-nav .app-header-btn {
  background: var(--field-bg); color: var(--text-2); border: 1px solid var(--border-strong);
}
.landing-nav .app-header-btn:hover {
  background: var(--accent-soft); color: var(--accent-ink); border-color: var(--accent);
}

/* ===== 按钮 ===== */
.landing-btn {
  display: inline-flex; align-items: center; gap: 8px; cursor: pointer;
  padding: 11px 20px; border-radius: 11px; font-size: 14px; font-weight: 600;
  border: 1px solid transparent; text-decoration: none; white-space: nowrap;
  transition: transform .16s ease, box-shadow .16s ease, opacity .16s ease;
}
.landing-btn:hover { transform: translateY(-1px); }
.landing-btn-primary {
  color: #fff; border: none;
  background: linear-gradient(135deg, var(--accent-ink), var(--accent));
  box-shadow: 0 6px 18px var(--shadow);
}
.landing-btn-primary:hover { box-shadow: 0 10px 24px var(--shadow); }
.landing-btn-ghost {
  background: var(--card); color: var(--text-2); border: 1px solid var(--border-strong);
}
.landing-btn-ghost:hover { border-color: var(--accent); color: var(--accent-ink); }
.landing-btn[disabled] { opacity: .55; cursor: not-allowed; transform: none; }
.landing-nav-cta { padding: 9px 16px; font-size: 13.5px; }

/* ===== Hero ===== */
.landing-hero { position: relative; overflow: hidden; padding: 68px 28px 52px; }
.landing-hero::before {
  content: ""; position: absolute; left: -160px; right: -160px; top: -300px; height: 660px;
  background: radial-gradient(closest-side, var(--accent-soft), transparent 72%);
  pointer-events: none;
}
.landing-hero::after {
  content: ""; position: absolute; inset: 0; pointer-events: none; opacity: .5;
  background-image:
    linear-gradient(var(--grid) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid) 1px, transparent 1px);
  background-size: 28px 28px;
  -webkit-mask-image: radial-gradient(closest-side at 50% 26%, #000, transparent 76%);
  mask-image: radial-gradient(closest-side at 50% 26%, #000, transparent 76%);
}
.landing-hero-inner {
  position: relative; z-index: 1; max-width: 1200px; margin: 0 auto;
  display: grid; grid-template-columns: minmax(0, 1.02fr) minmax(0, 1.12fr);
  gap: 44px; align-items: center;
}
.landing-badge {
  display: inline-flex; align-items: center; gap: 8px; width: fit-content;
  padding: 5px 12px; border-radius: 999px; font-size: 12.5px; font-weight: 600;
  background: var(--accent-soft); color: var(--accent-ink);
  border: 1px solid var(--border);
}
.landing-title {
  margin: 16px 0 0; font-size: 40px; line-height: 1.2; font-weight: 800;
  letter-spacing: -0.8px; color: var(--text);
}
.landing-title em {
  font-style: normal;
  background: linear-gradient(100deg, var(--accent-ink), var(--accent));
  -webkit-background-clip: text; background-clip: text; color: transparent;
}
.landing-sub {
  margin: 16px 0 0; font-size: 15px; line-height: 1.8;
  color: var(--muted); max-width: 560px;
}
.landing-cta-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-top: 26px; }
.landing-meta {
  margin-top: 14px; display: flex; flex-direction: column; gap: 3px;
  font-size: 12.5px; color: var(--muted-2);
}

/* 截图（窗口拟态） */
.landing-shot {
  border: 1px solid var(--border-strong); border-radius: 14px; overflow: hidden;
  background: var(--card);
  box-shadow: 0 18px 48px var(--shadow), 0 2px 8px var(--shadow);
  transform: perspective(1500px) rotateY(-3.2deg) rotateX(1.4deg);
  transition: transform .38s ease;
}
.landing-shot:hover { transform: perspective(1500px) rotateY(0deg) rotateX(0deg); }
.landing-shot-bar {
  display: flex; align-items: center; gap: 6px; padding: 9px 12px;
  background: var(--card-hover); border-bottom: 1px solid var(--border);
}
.landing-shot-dot { width: 10px; height: 10px; border-radius: 50%; }
.landing-shot-title { margin-left: 8px; font-size: 11.5px; color: var(--muted-2); }
.landing-shot img { display: block; width: 100%; height: auto; }
.landing-shot-ph {
  min-height: 300px; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 8px;
  color: var(--muted-2); background: var(--plot-bg); text-align: center;
}

/* 统计条 */
.landing-stats {
  position: relative; z-index: 1; max-width: 1200px; margin: 40px auto 0;
  display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px;
}
.landing-stat {
  background: var(--card); border: 1px solid var(--border);
  border-radius: 12px; padding: 14px 16px;
}
.landing-stat-v { font-size: 23px; font-weight: 800; color: var(--accent-ink); line-height: 1.1; }
.landing-stat-l { margin-top: 5px; font-size: 12px; color: var(--muted); }

/* ===== 区块 ===== */
.landing-section { max-width: 1200px; margin: 0 auto; padding: 56px 28px; scroll-margin-top: 76px; }
.landing-sec-head { margin-bottom: 24px; }
.landing-sec-kicker {
  font-size: 12.5px; font-weight: 700; letter-spacing: .08em;
  text-transform: uppercase; color: var(--accent-ink);
}
.landing-sec-title {
  margin: 8px 0 0; font-size: 26px; font-weight: 750;
  letter-spacing: -0.4px; color: var(--text);
}
.landing-sec-desc {
  margin: 8px 0 0; font-size: 14px; line-height: 1.75;
  color: var(--muted); max-width: 760px;
}

/* 功能卡 */
.landing-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(272px, 1fr)); gap: 16px; }
.landing-card {
  background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 18px;
  transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
}
.landing-card:hover {
  transform: translateY(-3px); border-color: var(--accent); box-shadow: 0 12px 28px var(--shadow);
}
.landing-icon-box {
  width: 38px; height: 38px; border-radius: 11px; margin-bottom: 12px;
  background: var(--accent-soft); color: var(--accent-ink);
  display: flex; align-items: center; justify-content: center;
}
.landing-card-title { font-size: 15px; font-weight: 650; color: var(--text); }
.landing-card-desc { margin-top: 7px; font-size: 13px; line-height: 1.7; color: var(--muted); }

/* 协议表 */
.landing-table-wrap {
  overflow-x: auto; background: var(--card);
  border: 1px solid var(--border); border-radius: 14px;
}
.landing-table { width: 100%; min-width: 780px; border-collapse: collapse; font-size: 13.5px; }
.landing-table th {
  text-align: left; padding: 12px 14px; white-space: nowrap;
  background: var(--card-hover); color: var(--text-2); font-weight: 600;
  border-bottom: 1px solid var(--border);
}
.landing-table td {
  padding: 11px 14px; color: var(--text-2);
  border-bottom: 1px solid var(--border); vertical-align: top;
}
.landing-table tbody tr:last-child td { border-bottom: none; }
.landing-table tbody tr:hover td { background: var(--accent-soft); }
.landing-idx {
  display: inline-flex; min-width: 22px; justify-content: center;
  padding: 1px 6px; border-radius: 6px; font-size: 12px; font-weight: 700;
  background: var(--accent-soft); color: var(--accent-ink);
}
.landing-pname { font-weight: 650; color: var(--text); }

/* 快速上手 */
.landing-two { display: grid; grid-template-columns: minmax(0, 1.12fr) minmax(0, 1fr); gap: 20px; }
.landing-cli { display: flex; flex-direction: column; gap: 14px; }
.landing-cli-role { font-size: 13px; font-weight: 600; color: var(--text); }
.landing-code {
  margin: 6px 0 0; padding: 11px 13px; overflow-x: auto; white-space: pre;
  background: var(--code-bg); border: 1px solid var(--border); border-radius: 10px;
  font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12.5px; line-height: 1.6; color: var(--text-2);
}
.landing-mini-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(232px, 1fr)); gap: 12px; }
.landing-mini {
  background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 14px 16px;
  transition: border-color .18s ease, transform .18s ease;
}
.landing-mini:hover { border-color: var(--accent); transform: translateY(-2px); }
.landing-mini-head { display: flex; align-items: center; gap: 8px; color: var(--accent-ink); }
.landing-mini-title { font-size: 13.5px; font-weight: 650; color: var(--text); }
.landing-mini-desc { margin-top: 6px; font-size: 12.5px; line-height: 1.65; color: var(--muted); }

/* ===== 下载 CTA ===== */
.landing-cta-band { max-width: 1200px; margin: 0 auto; padding: 8px 28px 64px; scroll-margin-top: 76px; }
.landing-cta-inner {
  display: flex; align-items: center; justify-content: space-between;
  gap: 22px; flex-wrap: wrap; padding: 32px 34px; border-radius: 20px;
  color: #fff; box-shadow: 0 16px 40px var(--shadow);
  background: linear-gradient(135deg, var(--accent-ink) 0%, var(--accent) 58%, var(--accent-ink) 100%);
}
.landing-cta-title { font-size: 22px; font-weight: 780; letter-spacing: -0.3px; }
.landing-cta-sub {
  margin-top: 8px; font-size: 13.5px; line-height: 1.7;
  color: rgba(255, 255, 255, 0.86);
}
.landing-cta-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.landing-btn-on-accent {
  background: #fff; color: var(--accent-ink); border: none;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.18);
}
.landing-btn-on-accent-ghost {
  background: rgba(255, 255, 255, 0.16); color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.5);
}

/* 深色模式下 --accent/--accent-ink 本身是浅色（theme_web.ACCENT_OVERRIDES_DARK：
   深蓝 #60a5fa、浅青 #2dd4bf…），白字落在浅底上会糊 → 强调色表面上的文字改用页面底色
   （var(--bg) 在深色下就是最深的面色），并在浅色/深色下都保持足够对比。 */
html.dark .landing-btn-primary,
html.dark .landing-cta-inner,
html.dark .landing-btn-on-accent-ghost { color: var(--bg); }
html.dark .landing-cta-sub { color: color-mix(in srgb, var(--bg) 78%, transparent); }
html.dark .landing-btn-on-accent { background: var(--bg); color: var(--accent-ink); }
html.dark .landing-btn-on-accent-ghost {
  background: color-mix(in srgb, var(--bg) 12%, transparent);
  border-color: color-mix(in srgb, var(--bg) 50%, transparent);
}

/* ===== 页脚 ===== */
.landing-footer { border-top: 1px solid var(--border); background: var(--card); }
.landing-footer-inner {
  max-width: 1200px; margin: 0 auto; padding: 26px 28px;
  display: flex; align-items: center; gap: 18px; flex-wrap: wrap;
}
.landing-footer-brand {
  display: flex; align-items: center; gap: 8px;
  color: var(--text-2); font-size: 13.5px; font-weight: 600;
}
.landing-footer-links { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; margin-left: auto; }
.landing-footer-link { color: var(--muted); font-size: 13px; text-decoration: none; }
.landing-footer-link:hover { color: var(--accent-ink); }
.landing-footer-ver {
  width: 100%; margin-top: 4px; padding-top: 14px; border-top: 1px solid var(--border);
  font-size: 12px; color: var(--muted-2);
}

/* ===== 响应式 ===== */
@media (max-width: 900px) {
  /* 顶栏在窄屏必须能换行：品牌 + 主题控件 + CTA 横排会撑破视口
     （实测 420px 视口下 .landing-nav-actions 宽 389px、父级 overflow 可见 → 页面横向溢出） */
  .landing-nav-inner { padding: 10px 18px; flex-wrap: wrap; row-gap: 8px; }
  .landing-nav-actions { flex-wrap: wrap; row-gap: 8px; }
  .landing-nav-links { display: none; }
  .landing-hero { padding: 42px 18px 38px; }
  .landing-hero-inner, .landing-two { grid-template-columns: minmax(0, 1fr); }
  .landing-shot { transform: none; }
  .landing-title { font-size: 30px; }
  .landing-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .landing-section { padding: 38px 18px; }
  .landing-cta-band { padding: 4px 18px 48px; }
  .landing-cta-inner { padding: 24px 20px; }
  .landing-footer-inner { padding: 22px 18px; }
}
"""


# ══════════════════════════════════════════════════════════════
# 渲染小工具
# ══════════════════════════════════════════════════════════════


def _is_static(value: Any) -> bool:
    """是否为编译期常量（bool）而非 `rx.Var`。

    生产环境传的是 `State` 字段（Var）；纯逻辑测试传字面量。常量分支在 Python 侧
    直接取舍：少一层运行期 `rx.cond`，也让「缺图降级」这类分支能被字符串断言直接验证。
    """
    return isinstance(value, bool)


def _either(
    condition: Any, when_true: rx.Component, when_false: rx.Component
) -> rx.Component:
    """二选一渲染（常量条件走 Python 分支）。"""
    if _is_static(condition):
        return when_true if condition else when_false
    return rx.cond(condition, when_true, when_false)


def _text_or_dash(value: Any) -> Any:
    """空值给占位符，避免出现 "v" 这种半截文案。"""
    if isinstance(value, str):
        return value or "—"
    return rx.cond(value != "", value, "—")


def _size_text(value: Any) -> Any:
    """exe 体积文案（空值不说谎，也不留 "— MB"）。"""
    if isinstance(value, str):
        return f"{value} MB" if value else "体积待统计"
    return rx.cond(value != "", value + " MB", "体积待统计")


def _section_head(kicker: str, title: str, desc: str) -> rx.Component:
    return rx.el.div(
        rx.el.div(kicker, class_name="landing-sec-kicker"),
        rx.el.h2(title, class_name="landing-sec-title"),
        rx.el.p(desc, class_name="landing-sec-desc"),
        class_name="landing-sec-head",
    )


def _download_button(
    exe_available: Any,
    on_download: Any,
    *,
    testid: str,
    label: str,
    variant: str = "primary",
) -> rx.Component:
    """下载按钮：exe 未就绪时禁用并改文案（不隐藏，避免用户找不到入口）。"""
    style = {
        "primary": "landing-btn landing-btn-primary",
        "on_accent": "landing-btn landing-btn-on-accent",
    }.get(variant, "landing-btn landing-btn-ghost")

    def _btn(disabled: bool) -> rx.Component:
        return rx.el.button(
            rx.icon("download", size=16),
            rx.el.span("客户端 exe 未就绪" if disabled else label),
            on_click=None if disabled else on_download,
            disabled=disabled,
            class_name=style,
            data_testid=testid,
        )

    return _either(exe_available, _btn(False), _btn(True))


def _shot_window(image_src: Any, image_available: Any) -> rx.Component:
    """界面截图卡（窗口拟态）。缺图时降级为占位卡，绝不出现破图。"""
    return rx.el.div(
        rx.el.div(
            rx.el.span(
                class_name="landing-shot-dot", style={"background": "var(--danger)"}
            ),
            rx.el.span(
                class_name="landing-shot-dot", style={"background": "var(--warn)"}
            ),
            rx.el.span(
                class_name="landing-shot-dot", style={"background": "var(--ok)"}
            ),
            rx.el.span("协议解析工具 · 桌面客户端", class_name="landing-shot-title"),
            class_name="landing-shot-bar",
        ),
        _either(
            image_available,
            rx.el.img(
                src=image_src,
                alt="桌面客户端界面截图",
                data_testid="hero-shot",
            ),
            rx.el.div(
                rx.icon("image_off", size=32),
                rx.el.div("截图待更新", class_name="landing-mini-title"),
                rx.el.div(
                    "把界面截图放到 downloads/client_screenshot.png 即可自动显示",
                    class_name="landing-mini-desc",
                ),
                class_name="landing-shot-ph",
                data_testid="hero-shot-placeholder",
            ),
        ),
        class_name="landing-shot",
    )


# ══════════════════════════════════════════════════════════════
# 组件
# ══════════════════════════════════════════════════════════════


def landing_nav(theme_controls: rx.Component | None = None) -> rx.Component:
    """营销顶栏：品牌 + 锚点导航 + 主题控件 + 进入在线工具。

    Args:
        theme_controls: 由 `reflex_web` 注入的主题控件（预设下拉 + 模式按钮），
            与工具页顶栏共用同一实现（单一来源）。
    """
    return rx.el.div(
        rx.el.div(
            rx.el.a(
                rx.el.div(rx.icon("zap", size=18), class_name="landing-brand-mark"),
                rx.el.div(
                    rx.el.div("多协议解析平台", class_name="landing-brand-name"),
                    rx.el.div(
                        f"电力通信协议解析 · {len(PROTOCOLS)} 种协议",
                        class_name="landing-brand-sub",
                    ),
                ),
                href=INTERNAL_LINKS["home"],
                class_name="landing-brand",
                data_testid="nav-brand",
            ),
            rx.el.nav(
                *[
                    rx.el.a(
                        item["label"], href=item["href"], class_name="landing-nav-link"
                    )
                    for item in NAV_LINKS
                ],
                class_name="landing-nav-links",
            ),
            rx.el.div(
                theme_controls if theme_controls is not None else rx.fragment(),
                rx.el.a(
                    rx.icon("play", size=15),
                    rx.el.span("进入在线工具"),
                    href=INTERNAL_LINKS["tool"],
                    class_name="landing-btn landing-btn-primary landing-nav-cta",
                    data_testid="nav-online",
                ),
                class_name="landing-nav-actions",
            ),
            class_name="landing-nav-inner",
        ),
        class_name="landing-nav",
    )


def landing_hero(
    *,
    version: Any = "",
    version_date: Any = "",
    exe_name: Any = "",
    exe_size_mb: Any = "",
    exe_available: Any = False,
    image_src: Any = "",
    image_available: Any = False,
    on_download: Any = None,
) -> rx.Component:
    """Hero：版本徽章 + 主标题 + 双 CTA + 截图。"""
    if isinstance(version, str):
        badge_text: Any = f"v{version} · {PLATFORM_NOTE}" if version else PLATFORM_NOTE
    else:
        badge_text = rx.cond(
            version != "", f"v{version} · {PLATFORM_NOTE}", PLATFORM_NOTE
        )

    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.el.div(
                    rx.icon("shield_check", size=14),
                    badge_text,
                    class_name="landing-badge",
                ),
                rx.el.h1(
                    rx.el.span(HERO_TITLE_LEAD),
                    rx.el.em(HERO_TITLE_ACCENT),
                    class_name="landing-title",
                    data_testid="hero-title",
                ),
                rx.el.p(HERO_SUBTITLE, class_name="landing-sub"),
                rx.el.div(
                    _download_button(
                        exe_available,
                        on_download,
                        testid="hero-download",
                        label="下载客户端",
                    ),
                    rx.el.a(
                        rx.icon("play", size=16),
                        rx.el.span("进入在线工具"),
                        href=INTERNAL_LINKS["tool"],
                        class_name="landing-btn landing-btn-ghost",
                        data_testid="hero-online",
                    ),
                    class_name="landing-cta-row",
                ),
                rx.el.div(
                    rx.el.div(
                        "单文件绿色版 · 无需安装 · 更新日期 ",
                        _text_or_dash(version_date),
                    ),
                    rx.el.div(
                        _text_or_dash(exe_name), "  ·  ", _size_text(exe_size_mb)
                    ),
                    class_name="landing-meta",
                ),
            ),
            _shot_window(image_src, image_available),
            class_name="landing-hero-inner",
        ),
        class_name="landing-hero",
    )


def landing_stats() -> rx.Component:
    """关键数字条（协议数取 len(PROTOCOLS)，避免手写数字漂移）。"""
    items = []
    for item in HERO_STATS:
        value = (
            str(len(PROTOCOLS)) if item.get("_key") == "protocols" else item["value"]
        )
        items.append(
            rx.el.div(
                rx.el.div(value, class_name="landing-stat-v"),
                rx.el.div(item["label"], class_name="landing-stat-l"),
                class_name="landing-stat",
            )
        )
    return rx.el.div(*items, class_name="landing-stats")


def landing_features() -> rx.Component:
    """核心功能卡片网格。"""
    return rx.el.div(
        _section_head(
            "FEATURES",
            "从解析到下发，覆盖现场调试全流程",
            "每个模块都按电力通信现场调试的真实动作设计：拿到报文先解析，"
            "批量日志要能提帧统计，改参数要能组帧下发，问题定位要能对比与抓包。",
        ),
        rx.el.div(
            *[
                rx.el.div(
                    rx.el.div(
                        rx.icon(item["icon"], size=18), class_name="landing-icon-box"
                    ),
                    rx.el.div(item["title"], class_name="landing-card-title"),
                    rx.el.div(item["desc"], class_name="landing-card-desc"),
                    class_name="landing-card",
                )
                for item in FEATURES
            ],
            class_name="landing-grid",
            data_testid="feature-grid",
        ),
        id="features",
        class_name="landing-section",
    )


def landing_protocols() -> rx.Component:
    """协议支持表（索引 / 协议 / 标准号 / 字节序 / 校验）。"""
    return rx.el.div(
        _section_head(
            "PROTOCOLS",
            f"{len(PROTOCOLS)} 种协议，全部内置",
            "下拉框索引即协议编号，解析、校验、查询与组帧共用同一套协议定义；"
            "字节序与校验算法按各规约原文实现，不做跨协议类比。",
        ),
        rx.el.div(
            rx.el.table(
                rx.el.thead(
                    rx.el.tr(
                        rx.el.th("#", style={"width": "56px"}),
                        rx.el.th("协议", style={"width": "26%"}),
                        rx.el.th("标准号 / 规约"),
                        rx.el.th("字节序", style={"width": "16%"}),
                        rx.el.th("校验", style={"width": "20%"}),
                    )
                ),
                rx.el.tbody(
                    *[
                        rx.el.tr(
                            rx.el.td(
                                rx.el.span(item["index"], class_name="landing-idx")
                            ),
                            rx.el.td(
                                rx.el.span(item["name"], class_name="landing-pname")
                            ),
                            rx.el.td(item["standard"]),
                            rx.el.td(item["endian"]),
                            rx.el.td(item["check"]),
                        )
                        for item in PROTOCOLS
                    ]
                ),
                class_name="landing-table",
                data_testid="protocol-table",
            ),
            class_name="landing-table-wrap",
        ),
        id="protocols",
        class_name="landing-section",
    )


def landing_quickstart() -> rx.Component:
    """快速上手：命令行示例 + Windows 系统集成。"""
    return rx.el.div(
        _section_head(
            "QUICK START",
            "绿色版解压即用，命令行也能直接解析",
            "桌面版单文件 exe 无需安装；需要接进脚本或文件管理器时，"
            "命令行参数与系统集成能力可以直接串进既有工作流。",
        ),
        rx.el.div(
            rx.el.div(
                rx.el.div(
                    *[
                        rx.el.div(
                            rx.el.div(item["label"], class_name="landing-cli-role"),
                            rx.el.pre(
                                rx.el.code(f"python {item['cmd']}"),
                                class_name="landing-code",
                            ),
                            class_name="landing-cli-item",
                        )
                        for item in CLI_ACTIONS
                    ],
                    class_name="landing-cli",
                    data_testid="quickstart-cli",
                ),
                rx.el.div(
                    *[
                        rx.el.div(
                            rx.el.div(
                                rx.icon(item["icon"], size=15),
                                rx.el.span(
                                    item["title"], class_name="landing-mini-title"
                                ),
                                class_name="landing-mini-head",
                            ),
                            rx.el.div(item["desc"], class_name="landing-mini-desc"),
                            class_name="landing-mini",
                        )
                        for item in SYSTEM_INTEGRATIONS
                    ],
                    class_name="landing-mini-grid",
                ),
                class_name="landing-two",
            ),
        ),
        id="quickstart",
        class_name="landing-section",
    )


def landing_cta(
    *,
    version: Any = "",
    exe_name: Any = "",
    exe_size_mb: Any = "",
    exe_available: Any = False,
    on_download: Any = None,
) -> rx.Component:
    """下载收尾区（下载客户端 / 在线使用）。"""
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.el.div("准备好开始解析了吗？", class_name="landing-cta-title"),
                rx.el.div(
                    rx.el.span("桌面客户端 "),
                    rx.el.span(_text_or_dash(exe_name)),
                    rx.el.span(" · "),
                    rx.el.span(_size_text(exe_size_mb)),
                    rx.el.span(" · 版本 "),
                    rx.el.span(_text_or_dash(version)),
                    " — 也可以直接打开在线工具，无需下载。",
                    class_name="landing-cta-sub",
                ),
            ),
            rx.el.div(
                _download_button(
                    exe_available,
                    on_download,
                    testid="cta-download",
                    label="下载 Windows 客户端",
                    variant="on_accent",
                ),
                rx.el.a(
                    rx.icon("play", size=16),
                    rx.el.span("在线使用"),
                    href=INTERNAL_LINKS["tool"],
                    class_name="landing-btn landing-btn-on-accent-ghost",
                    data_testid="cta-online",
                ),
                class_name="landing-cta-actions",
            ),
            class_name="landing-cta-inner",
        ),
        id="download",
        class_name="landing-cta-band",
    )


def landing_footer(*, version: Any = "") -> rx.Component:
    """页脚：品牌 + 链接 + 版本行。"""
    return rx.el.footer(
        rx.el.div(
            rx.el.div(
                rx.icon("zap", size=15),
                rx.el.span("多协议解析平台"),
                class_name="landing-footer-brand",
            ),
            rx.el.div(
                *[
                    rx.el.a(
                        link["label"],
                        href=link["href"],
                        is_external=link["external"],
                        class_name="landing-footer-link",
                    )
                    for link in FOOTER_LINKS
                ],
                class_name="landing-footer-links",
            ),
            rx.el.div(
                rx.el.span("版本 "),
                rx.el.span(_text_or_dash(version)),
                rx.el.span(" · 支持 Windows 10 / 11 · MIT License"),
                class_name="landing-footer-ver",
            ),
            class_name="landing-footer-inner",
        ),
        class_name="landing-footer",
        data_testid="landing-footer",
    )


def landing_page(
    *,
    version: Any = "",
    version_date: Any = "",
    exe_name: Any = "",
    exe_size_mb: Any = "",
    exe_available: Any = False,
    image_src: Any = "",
    image_available: Any = False,
    on_download: Any = None,
    theme_controls: rx.Component | None = None,
) -> rx.Component:
    """组装整页。所有形参都有安全默认值 → 可无参构建（纯逻辑测试用）。

    调用方（`reflex_web.landing_page`）负责再套上 `theme_style()`（token + GLOBAL_CSS）
    与 `ThemeState.root_class` / `rx.theme(...)`（强调色作用域）。
    """
    return rx.el.div(
        rx.el.style(LANDING_CSS),
        landing_nav(theme_controls),
        landing_hero(
            version=version,
            version_date=version_date,
            exe_name=exe_name,
            exe_size_mb=exe_size_mb,
            exe_available=exe_available,
            image_src=image_src,
            image_available=image_available,
            on_download=on_download,
        ),
        landing_stats(),
        landing_features(),
        landing_protocols(),
        landing_quickstart(),
        landing_cta(
            version=version,
            exe_name=exe_name,
            exe_size_mb=exe_size_mb,
            exe_available=exe_available,
            on_download=on_download,
        ),
        landing_footer(version=version),
        class_name="landing-root",
        data_testid="landing-root",
    )
