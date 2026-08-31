"""问题反馈数据模型与存储层（Reflex Web 版）

职责：
- FeedbackItem: SQLite 表模型（Reflex rx.Model / sqlmodel）
- FeedbackStore: 存取单例（懒加载 engine，create_all 幂等建表）
- save_screenshot / delete_screenshots: 截图文件保存与清理（服务端校验 + 防穿越）

数据落盘位置（与 downloads/、admin_config.json 同级策略）：
    reflex_web/data/feedback.db           # SQLite
    reflex_web/data/uploads/feedback/     # 截图

部署后位于 <部署目录>/reflex_web/data/，两个部署脚本重建时保留 data/。
测试可通过环境变量 FEEDBACK_DATA_DIR 重定向数据目录。
"""
from __future__ import annotations

import os
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

import reflex as rx
import sqlmodel
from sqlalchemy import desc as sa_desc

# ── 业务常量 ──────────────────────────────────────────────

ISSUE_TYPES = ["功能异常", "解析错误", "界面体验", "新功能建议", "其他"]
FEEDBACK_STATUSES = ["待处理", "已确认", "已修复", "已忽略"]

MAX_DESC_LEN = 2000
MAX_CONTACT_LEN = 100
MAX_SCREENSHOTS = 3
MAX_SCREENSHOT_SIZE = 5 * 1024 * 1024  # 5MB

ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

# 魔数（文件头）签名
_MAGIC_SIGNATURES = (
    b"\x89PNG\r\n\x1a\n",     # png
    b"\xff\xd8\xff",          # jpeg
    b"RIFF",                  # webp 以 RIFF 开头，另验中段 WEBP
)

_FILENAME_PATTERN = re.compile(r"^fb_\d{8}_\d{6}_[0-9a-f]{8}\.(?:png|jpe?g|webp)$")


# ── 数据目录 ──────────────────────────────────────────────

def data_dir() -> Path:
    """反馈数据根目录 reflex_web/data/（环境变量 FEEDBACK_DATA_DIR 可覆盖，供测试）。

    本文件位于 reflex_web/reflex_web/（内层包），数据目录在其上级：
    与 downloads/、admin_config.json 同级，部署脚本重建时保留。
    """
    override = os.environ.get("FEEDBACK_DATA_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "data"


def uploads_dir() -> Path:
    """截图目录 reflex_web/data/uploads/feedback/。"""
    return data_dir() / "uploads" / "feedback"


def db_path() -> Path:
    return data_dir() / "feedback.db"


# ── 模型 ──────────────────────────────────────────────────

class FeedbackItem(rx.Model, table=True):
    """问题反馈记录。"""

    created_at: str = ""
    issue_type: str = ""
    protocol: str = ""
    description: str = ""
    contact: str = ""
    screenshots: str = ""       # 分号分隔的文件名
    status: str = "待处理"


def _split_screenshots(field: str) -> list[str]:
    if not field:
        return []
    return [s for s in field.split(";") if s]


def _join_screenshots(names: list[str]) -> str:
    return ";".join(names)


# ── 存储层 ────────────────────────────────────────────────

class FeedbackStore:
    """SQLite 存取（同步实现；Reflex 事件处理器内直接调用）。

    engine 懒加载 + create_all 幂等；check_same_thread=False 适配
    Reflex 后端多线程事件处理。
    """

    _instance: FeedbackStore | None = None

    def __init__(self, engine=None):
        # engine 参数供测试注入（内存库等）
        if engine is None:
            import sqlmodel as _sm
            uploads_dir().mkdir(parents=True, exist_ok=True)
            engine = _sm.create_engine(
                f"sqlite:///{db_path()}",
                connect_args={"check_same_thread": False},
            )
            _sm.SQLModel.metadata.create_all(engine)
        self.engine = engine

    @classmethod
    def instance(cls) -> FeedbackStore:
        """单例访问（get 与实例 get(item_id) 重名冲突，故用 instance）。"""
        if cls._instance is None:
            cls._instance = FeedbackStore()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """测试用：重置单例（并允许环境变量重定向后重建）。"""
        cls._instance = None

    # ── CRUD ──

    def add(self, item: FeedbackItem) -> int:
        try:
            with sqlmodel.Session(self.engine) as session:
                session.add(item)
                session.commit()
                session.refresh(item)
                if item.id is None:
                    raise RuntimeError("反馈记录写入失败（未获得 id）")
                return int(item.id)
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"反馈写入数据库失败: {exc}") from exc

    def list_all(self, offset: int = 0, limit: int = 20) -> tuple[list[FeedbackItem], int]:
        """时间倒序分页，返回 (items, total)。"""
        try:
            count_stmt = sqlmodel.select(sqlmodel.func.count()).select_from(FeedbackItem)
            items_stmt = (
                sqlmodel.select(FeedbackItem)
                .order_by(
                    sa_desc(sqlmodel.col(FeedbackItem.created_at)),
                    sa_desc(sqlmodel.col(FeedbackItem.id)),
                )
                .offset(offset)
                .limit(limit)
            )
            with sqlmodel.Session(self.engine) as session:
                total = int(session.exec(count_stmt).one() or 0)
                items = list(session.exec(items_stmt).all())
            return items, total
        except Exception as exc:
            raise RuntimeError(f"反馈查询失败: {exc}") from exc

    def count_pending(self) -> int:
        try:
            stmt = (
                sqlmodel.select(sqlmodel.func.count())
                .select_from(FeedbackItem)
                .where(sqlmodel.col(FeedbackItem.status) == "待处理")
            )
            with sqlmodel.Session(self.engine) as session:
                return int(session.exec(stmt).one() or 0)
        except Exception as exc:
            raise RuntimeError(f"反馈统计失败: {exc}") from exc

    def get(self, item_id: int) -> FeedbackItem | None:
        with sqlmodel.Session(self.engine) as session:
            item = session.get(FeedbackItem, item_id)
            if item is not None:
                session.expunge(item)
            return item

    def update_status(self, item_id: int, status: str) -> bool:
        if status not in FEEDBACK_STATUSES:
            return False
        with sqlmodel.Session(self.engine) as session:
            item = session.get(FeedbackItem, item_id)
            if item is None:
                return False
            item.status = status
            session.add(item)
            session.commit()
            return True

    def delete(self, item_id: int) -> list[str]:
        """删除记录，返回其关联截图文件名（供 UI 层删文件）。"""
        with sqlmodel.Session(self.engine) as session:
            item = session.get(FeedbackItem, item_id)
            if item is None:
                return []
            names = _split_screenshots(item.screenshots)
            session.delete(item)
            session.commit()
            return names


# ── 截图文件工具 ──────────────────────────────────────────

def _check_magic(data: bytes) -> bool:
    if len(data) < 12:
        return False
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if data.startswith(b"\xff\xd8\xff"):
        return True
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return True
    return False


def generate_filename(ext: str) -> str:
    """生成服务端文件名 fb_YYYYmmdd_HHMMSS_<rand8>.<ext>（不含用户原始名）。"""
    now = datetime.now()
    rand = secrets.token_hex(4)
    return f"fb_{now.strftime('%Y%m%d_%H%M%S')}_{rand}.{ext}"


def save_screenshot(data: bytes, orig_name: str) -> str:
    """保存一张截图，返回生成的文件名。

    校验：扩展名白名单 + 魔数 + 大小上限。任何不合法抛 ValueError。
    """
    if not data:
        raise ValueError("文件内容为空")
    if len(data) > MAX_SCREENSHOT_SIZE:
        raise ValueError(f"文件超过大小上限（{MAX_SCREENSHOT_SIZE // (1024*1024)}MB）")
    ext = Path(orig_name or "").suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise ValueError(f"不支持的文件类型: {ext or '(无扩展名)'}，仅支持 jpg/png/webp")
    if not _check_magic(data):
        raise ValueError("文件内容不是有效的图片格式")
    uploads_dir().mkdir(parents=True, exist_ok=True)
    name = generate_filename(ext.lstrip("."))
    (uploads_dir() / name).write_bytes(data)
    return name


def delete_screenshots(names: list[str]) -> int:
    """删除截图文件，返回实际删除数。

    防穿越：只接受匹配 fb_* 生成模式的纯文件名，拒绝路径分隔符。
    单个文件删除失败（被占用等）不中断整体清理，与 Reflex 删除记录解耦。
    """
    removed = 0
    base = uploads_dir().resolve()
    for name in names or []:
        if not name or "/" in name or "\\" in name or ".." in name:
            continue
        if not _FILENAME_PATTERN.match(name):
            continue
        path = (base / name).resolve()
        try:
            if path.is_relative_to(base) and path.is_file():
                path.unlink()
                removed += 1
        except OSError:
            # 文件可能已被手动清理或被其他进程占用：跳过，不阻塞记录删除
            pass
    return removed


def screenshot_url(name: str) -> str:
    """生成截图访问 URL（生产 run_app.py / dev reflex_web.py 均注册 /fbimg/）。"""
    if not name or "/" in name or "\\" in name or ".." in name:
        return ""
    return f"/fbimg/{name}"
