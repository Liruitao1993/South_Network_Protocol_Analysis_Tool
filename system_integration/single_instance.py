"""
单实例管理模块（系统集成）
==========================
使用 QLocalServer / QLocalSocket 确保同一时间只有一个实例。
重复启动时，新实例把命令行参数发给已有实例（激活主窗口 + 按参数执行），随后退出。
"""
import sys

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

SERVER_NAME = "协议解析工具_singleton"


def _send_args_to_existing(args) -> bool:
    """尝试连接已有实例，发送参数并等待 ACK，确认是活实例才返回 True

    关键：仅 connectToServer 成功不足以证明有活实例——僵尸进程残留的
    命名管道也能连接成功。必须等到服务器 ACK 才算真的连上主实例。
    """
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if not socket.waitForConnected(1000):
        return False
    payload = "||".join(args)
    socket.write(payload.encode("utf-8"))
    socket.flush()
    socket.waitForBytesWritten(1000)
    # 等待服务器 ACK（收到即确认主实例存活）
    if socket.waitForReadyRead(2000):
        bytes(socket.readAll())  # 读取 ACK
        socket.disconnectFromServer()
        return True
    # 无 ACK：可能是僵尸进程残留管道，非活实例，本进程应成为主实例
    socket.disconnectFromServer()
    return False


class SingleInstanceServer(QObject):
    """主实例：监听新实例发来的参数"""
    args_received = Signal(list)  # 新实例命令行参数

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server = QLocalServer()
        # 崩溃残留的 socket 文件：移除后重新监听
        self._server.removeServer(SERVER_NAME)
        self._server.listen(SERVER_NAME)
        self._server.newConnection.connect(self._on_new_connection)

    def _on_new_connection(self):
        conn = self._server.nextPendingConnection()
        if conn is None:
            return
        conn.readyRead.connect(lambda: self._on_data(conn))
        conn.disconnected.connect(lambda: self._on_disconnected(conn))
        # 客户端可能已写完全部数据（readyRead 可能已错过），主动尝试读取一次
        self._on_data(conn)

    def _on_data(self, conn: QLocalSocket):
        payload = bytes(conn.readAll()).decode("utf-8", errors="replace")
        if payload:
            args = [a for a in payload.split("||") if a]
            self.args_received.emit(args)
            # 发送 ACK，告知客户端数据已送达，客户端据此安全断开
            try:
                conn.write(b"ok")
                conn.flush()
            except Exception:
                pass

    def _on_disconnected(self, conn: QLocalSocket):
        # 客户端断开前可能还有未读数据，先读完再释放
        self._on_data(conn)
        conn.deleteLater()


def try_connect_existing(argv) -> bool:
    """启动时调用：若已有实例在运行，传参并返回 True（本进程应退出）"""
    if _send_args_to_existing(argv):
        return True
    return False
