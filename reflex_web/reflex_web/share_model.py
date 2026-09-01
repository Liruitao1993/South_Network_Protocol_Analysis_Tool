"""报文分享存储层（frameshare.db）。

用户在单帧解析后可将有价值的命令帧分享到共享库：原始报文 hex + 协议 +
分享人 + 说明 + 来源（web/gui）。Web /share 页面浏览与搜索；GUI 通过
POST /api/frameshare（JSON）提交，两端共享同一数据库。

测试可通过环境变量 FRAMESHARE_DATA_DIR 重定向数据目录。

运行表自动建库（sqlmodel create_all 幂等）；本表 1.21.0 首次引入，
无历史迁移需求。
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

import reflex as rx
import sqlmodel

# ── 常量（与 GUI 侧 share_dialog 保持一致的约束） ──────────────

MAX_SHARER_LEN = 50
MAX_NOTE_LEN = 500
MAX_FRAME_BYTES = 2048  # 报文字节数上限（单帧足够）
MIN_FRAME_BYTES = 2
PER_PAGE = 20

# 协议白名单（与 GUI feedback_dialog.PROTOCOL_OPTIONS 同源语义；独立声明
# 避免 web 存储层 import GUI 模块）
SHARE_PROTOCOLS = [
    "不确定",
    "南网协议",
    "PLC RF协议",
    "HDLC/国网DLMS",
    "DLMS-APDU(国网)",
    "DLMS Wrapper裸报文",
    "DLMS-APDU裸报文",
    "DLT645-2007 电表协议",
    "国网协议",
    "698.45协议",
    "新一代载波协议",
    "国网新一代双模",
    "HDC 1.0 双模",
]

_SOURCES = ("web", "gui")

_HEX_CLEAN_RE = re.compile(r"[^0-9A-Fa-f]")


def data_dir() -> Path:
    """分享数据根目录 reflex_web/data/（环境变量 FRAMESHARE_DATA_DIR 可覆盖）。

    __file__ 位于 reflex_web/reflex_web/share_model.py（内层包），
    parent.parent 即外层 reflex_web/ 包目录，data/ 与 downloads/ 同级。
    """
    override = os.environ.get("FRAMESHARE_DATA_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "data"


def db_path() -> Path:
    """SQLite 数据库文件路径。"""
    return data_dir() / "frameshare.db"


def uploads_dir() -> Path:
    """兼容接口：分享无截图上传，返回 data 目录（保持与 feedback_model 同构）。"""
    return data_dir()


class ShareItem(rx.Model, table=True):
    """报文分享记录。"""

    created_at: str = ""
    frame_hex: str = ""  # 空格分隔大写 hex（服务端 normalize 后存储）
    protocol: str = ""
    sharer: str = ""
    note: str = ""
    source: str = "web"  # web=网页提交 / gui=桌面客户端 API 提交


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── 纯函数：hex 规范化与提交校验 ──────────────────────────────


def normalize_hex(hex_str: str) -> str | None:
    """清洗并校验报文 hex，返回「空格分隔大写」规范形式；非法返回 None。

    接受 0x 前缀、空格/逗号/换行分隔。字节数须在 [MIN, MAX]。
    """
    if not hex_str or not isinstance(hex_str, str):
        return None
    # 去 0x/0X 前缀（逐 token 处理，避免误吞合法 hex 中的字符）
    text = hex_str.strip()
    text = re.sub(r"0[xX](?=[0-9A-Fa-f])", "", text)
    clean = _HEX_CLEAN_RE.sub("", text)
    if not clean or len(clean) % 2 != 0:
        return None
    if not all(c in "0123456789abcdefABCDEF" for c in clean):
        return None  # _HEX_CLEAN_RE 已过滤，此行防御性兜底
    byte_len = len(clean) // 2
    if byte_len < MIN_FRAME_BYTES or byte_len > MAX_FRAME_BYTES:
        return None
    raw = bytes.fromhex(clean)
    return " ".join(f"{b:02X}" for b in raw)


def submit_share(fields: dict) -> tuple[bool, object, int]:
    """HTTP API 提交入口（dev/prod 路由共用，纯逻辑可单测）。

    fields: frame_hex / protocol / sharer / note / source（str）。
    返回 (ok, id_or_error_msg, http_status)。
    """
    fields = fields or {}

    def _s(key: str) -> str:
        v = fields.get(key, "")
        return v.strip() if isinstance(v, str) else ""

    frame_hex = normalize_hex(fields.get("frame_hex", "") or "")
    if frame_hex is None:
        return (
            False,
            f"报文格式无效（需 2~{MAX_FRAME_BYTES} 字节偶长 hex）",
            400,
        )
    protocol = _s("protocol")
    if protocol not in SHARE_PROTOCOLS:
        return False, f"协议无效（可选：{'/'.join(SHARE_PROTOCOLS)}）", 400
    sharer = _s("sharer")
    if not sharer:
        return False, "请填写分享人", 400
    if len(sharer) > MAX_SHARER_LEN:
        return False, f"分享人不能超过 {MAX_SHARER_LEN} 字", 400
    note = fields.get("note", "") or ""
    if not isinstance(note, str):
        note = str(note)
    note = note.strip()
    if len(note) > MAX_NOTE_LEN:
        return False, f"说明不能超过 {MAX_NOTE_LEN} 字", 400
    source = _s("source") or "web"
    if source not in _SOURCES:
        source = "gui" if source == "gui" else "web"
    if source not in _SOURCES:
        source = "web"

    item = ShareItem(
        created_at=_now(),
        frame_hex=frame_hex,
        protocol=protocol,
        sharer=sharer,
        note=note,
        source=source,
    )
    try:
        new_id = ShareStore.instance().add(item)
    except Exception as e:  # noqa: BLE001 - 存储失败返回 500
        return False, f"保存失败: {e}", 500
    return True, new_id, 200


def share_config() -> dict:
    """字段约束下发（GUI 拉取）。"""
    return {
        "ok": True,
        "protocols": SHARE_PROTOCOLS,
        "max_sharer_len": MAX_SHARER_LEN,
        "max_note_len": MAX_NOTE_LEN,
        "max_frame_bytes": MAX_FRAME_BYTES,
        "per_page": PER_PAGE,
    }


def share_page_url(
    host: str,
    scheme: str = "http",
    frontend_port: int | None = None,
    mounted: bool = False,
) -> str:
    """根据请求 Host 拼浏览器可访问的 /share 页 URL。

    GUI 提交到后端 API 地址，但页面在前端服务上：
    - mounted=True（prod，run_app.py 单端口挂载前后端）：前后端同源，
      直接用请求 Host。
    - mounted=False（dev，``reflex run`` 前后端分端口）：GUI 直连后端，
      Host 带的是后端端口（如 8000），页面在前端端口（如 3000），
      把 Host 末尾端口替换为 frontend_port；Host 无端口时补上。
    Host 缺失时返回相对路径 "/share"（同源兜底）。
    """
    if not host:
        return "/share"
    if not mounted and frontend_port:
        m = re.search(r":(\d+)$", host)
        if m:
            # 已是前端端口（如经 Vite 代理提交）则保持不变
            if int(m.group(1)) != frontend_port:
                host = host[: m.start()] + f":{frontend_port}"
        else:
            host = f"{host}:{frontend_port}"
    return f"{scheme or 'http'}://{host}/share"


def _item_dict(item: ShareItem) -> dict:
    """ORM → 前端 dict（Reflex State 列表用）。"""
    return {
        "id": item.id,
        "created_at": item.created_at,
        "frame_hex": item.frame_hex,
        "protocol": item.protocol,
        "sharer": item.sharer,
        "note": item.note,
        "source": item.source,
    }


# ── 存储层单例 ────────────────────────────────────────────────


class ShareStore:
    """frameshare.db 访问单例（check_same_thread=False 适配 Reflex 多线程）。"""

    _instance: ShareStore | None = None
    _engine = None

    def __init__(self):
        db = db_path()
        db.parent.mkdir(parents=True, exist_ok=True)
        self._engine = sqlmodel.create_engine(
            f"sqlite:///{db}", connect_args={"check_same_thread": False}
        )
        sqlmodel.SQLModel.metadata.create_all(self._engine)

    @classmethod
    def instance(cls) -> ShareStore:
        if cls._instance is None:
            cls._instance = ShareStore()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """测试用：关闭并重置单例（下一 instance() 重建连接）。"""
        if cls._engine is not None:
            try:
                cls._engine.dispose()
            except Exception:  # noqa: BLE001
                pass
        cls._engine = None
        cls._instance = None

    # ── CRUD ──

    def add(self, item: ShareItem) -> int:
        with sqlmodel.Session(self._engine) as session:
            session.add(item)
            session.commit()
            session.refresh(item)
            return int(item.id or 0)

    def get(self, item_id: int) -> ShareItem | None:
        with sqlmodel.Session(self._engine) as session:
            return session.get(ShareItem, int(item_id))

    def list_page(
        self, page: int, per_page: int, keyword: str = ""
    ) -> tuple[list[dict], int, int]:
        """分页 + 关键字搜索（hex/协议/分享人/说明）。

        hex 搜索兼容两种输入：含空格（直接 contains）与连续无空格
        （把关键字按两字符切开重新插空格后 contains——与库内规范存储
        格式对齐）。返回 (items_dicts, total, pages)。
        """
        page = max(1, int(page))
        per_page = max(1, int(per_page))
        kw = (keyword or "").strip()
        conds = None
        if kw:
            hex_variants = [kw]
            compact = _HEX_CLEAN_RE.sub("", kw)
            if compact and len(compact) >= 4 and len(compact) % 2 == 0:
                spaced = " ".join(
                    compact[i : i + 2] for i in range(0, len(compact), 2)
                )
                if spaced != kw:
                    hex_variants.append(spaced)
            like_conds = [
                ShareItem.frame_hex.contains(v) for v in hex_variants
            ]
            like_conds += [
                ShareItem.protocol.contains(kw),
                ShareItem.sharer.contains(kw),
                ShareItem.note.contains(kw),
            ]
            conds = sqlmodel.or_(*like_conds)
        with sqlmodel.Session(self._engine) as session:
            total_q = session.exec(
                sqlmodel.select(sqlmodel.func.count()).select_from(ShareItem)
                if conds is None
                else sqlmodel.select(sqlmodel.func.count()).select_from(
                    ShareItem
                ).where(conds)
            )
            total = int(total_q.one() or 0)
            pages = max(1, (total + per_page - 1) // per_page)
            page = min(page, pages)
            stmt = sqlmodel.select(ShareItem)
            if conds is not None:
                stmt = stmt.where(conds)
            stmt = (
                stmt.order_by(ShareItem.id.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
            )
            items = list(session.exec(stmt).all())
        return [_item_dict(i) for i in items], total, pages
