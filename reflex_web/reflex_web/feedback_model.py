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
MAX_SYSINFO_LEN = 2000  # GUI 客户端自动收集的环境信息上限

ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

# 魔数（文件头）签名
_MAGIC_SIGNATURES = (
    b"\x89PNG\r\n\x1a\n",  # png
    b"\xff\xd8\xff",  # jpeg
    b"RIFF",  # webp 以 RIFF 开头，另验中段 WEBP
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
    screenshots: str = ""  # 分号分隔的文件名
    status: str = "待处理"
    # 提交来源：web（网页表单）/ gui（桌面客户端 API，1.20.0 起）
    source: str = "web"
    # GUI 客户端自动收集的环境信息（版本/OS 等，选填 ≤2000 字）
    sys_info: str = ""


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
            self._migrate_source_column(engine)
        self.engine = engine

    @staticmethod
    def _migrate_source_column(engine):
        """旧库轻量迁移：缺列则 ALTER TABLE 补列（create_all 不会给已存在表加列）。

        1.20.0 起 FeedbackItem 增加 source（web/gui 来源）与 sys_info（GUI
        客户端环境信息）两列；已部署环境的老 feedback.db 首次打开时自动
        补列，历史记录 source 默认 'web'、sys_info 默认空串。幂等。
        """
        # (列名, 列定义) —— SQLite ADD COLUMN 必须带默认值（本表无 NOT NULL 强约束）
        wanted = {
            "source": "VARCHAR DEFAULT 'web'",
            "sys_info": "VARCHAR DEFAULT ''",
        }
        with engine.connect() as conn:
            rows = conn.exec_driver_sql("PRAGMA table_info(feedbackitem)").fetchall()
            cols = {r[1] for r in rows}
            for name, decl in wanted.items():
                if name not in cols:
                    conn.exec_driver_sql(
                        f"ALTER TABLE feedbackitem ADD COLUMN {name} {decl}"
                    )
            conn.commit()

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

    def list_all(
        self, offset: int = 0, limit: int = 20
    ) -> tuple[list[FeedbackItem], int]:
        """时间倒序分页，返回 (items, total)。"""
        try:
            count_stmt = sqlmodel.select(sqlmodel.func.count()).select_from(
                FeedbackItem
            )
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
        raise ValueError(
            f"文件超过大小上限（{MAX_SCREENSHOT_SIZE // (1024 * 1024)}MB）"
        )
    ext = Path(orig_name or "").suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise ValueError(
            f"不支持的文件类型: {ext or '(无扩展名)'}，仅支持 jpg/png/webp"
        )
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


# ── HTTP API 提交（GUI 客户端等外部调用，复用同一数据库） ─────────────


def submit_from_api(
    fields: dict, files: list | None = None
) -> tuple[bool, object, int]:
    """供 HTTP API 调用的提交入口（dev/prod 两条路由共用，纯逻辑可单测）。

    参数：
        fields: 表单字段 dict，键 issue_type/protocol/description/contact/
                sys_info/source（均为 str）。
        files:  截图列表 [(orig_filename, data_bytes), ...]，可空。

    返回：(ok, id_or_error_msg, http_status)
        成功：(True, 新记录 id:int, 200)
        失败：(False, 中文错误:str, 400/413/500)
    """
    files = files or []
    fields = fields or {}

    def _s(key: str) -> str:
        v = fields.get(key, "")
        return v.strip() if isinstance(v, str) else ""

    issue_type = _s("issue_type")
    protocol = _s("protocol")
    description = _s("description")
    contact = _s("contact")
    sys_info = fields.get("sys_info", "") or ""
    if not isinstance(sys_info, str):
        sys_info = str(sys_info)
    source = _s("source") or "gui"
    if source not in ("web", "gui"):
        source = "gui"

    # ── 字段校验 ──
    if issue_type not in ISSUE_TYPES:
        return False, f"问题类型无效（可选：{'/'.join(ISSUE_TYPES)}）", 400
    if not protocol:
        return False, "请选择涉及协议", 400
    if not description:
        return False, "请填写问题描述", 400
    if len(description) > MAX_DESC_LEN:
        return False, f"问题描述不能超过 {MAX_DESC_LEN} 字", 400
    if len(contact) > MAX_CONTACT_LEN:
        return False, f"联系方式不能超过 {MAX_CONTACT_LEN} 字", 400
    if len(sys_info) > MAX_SYSINFO_LEN:
        return False, f"环境信息超长（>{MAX_SYSINFO_LEN}）", 400
    if len(files) > MAX_SCREENSHOTS:
        return (
            False,
            f"截图最多 {MAX_SCREENSHOTS} 张（当前 {len(files)} 张）",
            400,
        )

    # ── 截图保存（逐张校验，任一失败回滚已存文件）──
    saved_names: list[str] = []
    for item in files:
        try:
            orig_name, data = item[0], item[1]
        except (IndexError, TypeError, ValueError):
            delete_screenshots(saved_names)
            return False, "截图数据格式错误", 400
        if not isinstance(data, (bytes, bytearray)):
            delete_screenshots(saved_names)
            return False, "截图内容不是有效的文件数据", 400
        if len(data) > MAX_SCREENSHOT_SIZE:
            delete_screenshots(saved_names)
            return (
                False,
                f"单张截图不能超过 {MAX_SCREENSHOT_SIZE // (1024 * 1024)}MB",
                413,
            )
        try:
            saved_names.append(save_screenshot(bytes(data), orig_name or "shot.png"))
        except ValueError as exc:
            delete_screenshots(saved_names)
            return False, f"截图保存失败：{exc}", 400
        except Exception as exc:  # noqa: BLE001 - 落盘异常统一为服务端错误
            delete_screenshots(saved_names)
            return False, f"截图保存异常：{exc}", 500

    # ── 写库 ──
    try:
        item = FeedbackItem(
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            issue_type=issue_type,
            protocol=protocol,
            description=description,
            contact=contact,
            screenshots=_join_screenshots(saved_names),
            status="待处理",
            source=source,
            sys_info=sys_info,
        )
        new_id = FeedbackStore.instance().add(item)
    except Exception as exc:  # noqa: BLE001
        delete_screenshots(saved_names)
        return False, f"反馈写入失败：{exc}", 500

    return True, new_id, 200


def parse_multipart(body: bytes, boundary: bytes) -> tuple[dict, list]:
    """二进制安全解析 multipart/form-data 请求体（生产 ASGI 中间件用）。

    开发模式用 Starlette request.form()；生产 run_app.py 无 Starlette 请求
    对象，手工按 boundary 切分。仅支持本 API 需要的简单结构：文本字段 +
    文件字段（Content-Disposition 带 filename）。

    返回：(fields: {name: str}, files: [(filename, data_bytes), ...])
    """
    import re as _re

    fields: dict[str, str] = {}
    files: list[tuple[str, bytes]] = []

    delim = b"--" + boundary.strip(b'"')
    # 按 boundary 切分（CRLF--boundary 为前导）
    parts = body.split(delim)
    for part in parts:
        # 去掉首尾 CRLF；忽略前导/结束标记段
        if not part or part in (b"--\r\n", b"--", b"\r\n"):
            continue
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.rstrip(b"\r\n").endswith(b"--"):
            part = part.rstrip(b"\r\n")[:-2]
        # 头部/正文以空行分隔
        sep = part.find(b"\r\n\r\n")
        if sep == -1:
            continue
        header_block = part[:sep].decode("utf-8", errors="replace")
        data = part[sep + 4 :]
        if data.endswith(b"\r\n"):
            data = data[:-2]

        disp = ""
        for line in header_block.split("\r\n"):
            if line.lower().startswith("content-disposition:"):
                disp = line
                break
        if not disp:
            continue

        name_m = _re.search(r'name="([^"]*)"', disp)
        if not name_m:
            continue
        name = name_m.group(1)
        fn_m = _re.search(r'filename="([^"]*)"', disp)

        if fn_m:
            filename = fn_m.group(1)
            if filename and data:
                files.append((filename, bytes(data)))
        else:
            fields[name] = data.decode("utf-8", errors="replace")

    return fields, files


# ── 频率限制（进程内内存计数，单进程部署足够；重启清零） ──────────────

RATE_WINDOW_SEC = 60.0
RATE_MAX_PER_WINDOW = 5


class FeedbackRateLimiter:
    """滑动窗口限流：同一 key（客户端 IP）每窗口内最多 max_calls 次。"""

    def __init__(
        self,
        max_calls: int = RATE_MAX_PER_WINDOW,
        window: float = RATE_WINDOW_SEC,
    ):
        self.max_calls = max_calls
        self.window = window
        self._hits: dict[str, list[float]] = {}

    def check(self, key: str, now: float | None = None) -> bool:
        """记录一次请求；未超限返回 True，超限返回 False。"""
        import time

        now = time.monotonic() if now is None else now
        cuts = [t for t in self._hits.get(key, []) if now - t < self.window]
        cuts.append(now)
        self._hits[key] = cuts
        return len(cuts) <= self.max_calls


# dev 与 prod 路由各持单例（进程内生效）
_rate_limiter: FeedbackRateLimiter | None = None


def rate_limiter() -> FeedbackRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = FeedbackRateLimiter()
    return _rate_limiter


def api_config() -> dict:
    """GET /api/feedback/config 返回的客户端限制参数（GUI 填充下拉/限制用）。"""
    return {
        "ok": True,
        "issue_types": list(ISSUE_TYPES),
        "max_desc_len": MAX_DESC_LEN,
        "max_contact_len": MAX_CONTACT_LEN,
        "max_screenshots": MAX_SCREENSHOTS,
        "max_size_mb": MAX_SCREENSHOT_SIZE // (1024 * 1024),
    }
