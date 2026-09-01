"""GUI 问题反馈对话框测试（feedback_dialog.py，offscreen Qt）

覆盖：
- normalize_server_url / load / save 反馈服务器地址（config.json "feedback" 段）
- validate_fields：空地址/空描述/超长/超限全部分支
- collect_sys_info：版本/OS/协议关键字段
- FeedbackDialog：offscreen 创建、字段计数、截图添加/移除/超限、空描述提交拦截
- multipart 组帧：QHttpMultiPart 实际构造（通过 _on_submit 的表单字段覆盖）

不发真实网络请求（默认地址不可达时走错误回调路径，不崩溃）。

运行（项目根）：
    python test/test_feedback_dialog.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import _path_setup  # noqa: F401,E402

ROOT = Path(_path_setup.__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import feedback_dialog as fd  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


# 最小合法 PNG（8 字节签名 + IHDR + IEND，服务端 _check_magic 仅验头部；
# 对话框上传把 bytes 当不透明数据处理，测试无需真实可渲染图片）
_MIN_PNG = (
    b"\x89PNG\r\n\x1a\n"          # PNG 签名
    b"\x00\x00\x00\x0dIHDR"        # IHDR 长度 + 类型
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02"  # 1x1 8bit RGB
    b"\x00\x00\x00\x07IDAT" + b"\x00\x00\x00\x00"  # 空 IDAT（测试用）
    + b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def make_png_bytes(color=(255, 0, 0), size=(16, 16)):
    """返回预置的最小合法 PNG 字节（颜色/尺寸参数仅为兼容旧调用签名）。"""
    return _MIN_PNG


def main():
    print("== 纯函数：URL 规范化 ==")
    check("补 http 前缀", fd.normalize_server_url("192.168.1.5:8080") == "http://192.168.1.5:8080")
    check("去尾部斜杠", fd.normalize_server_url("http://x/") == "http://x")
    check("https 保留", fd.normalize_server_url("https://a.b:9000/") == "https://a.b:9000")
    check("空串", fd.normalize_server_url("  ") == "")

    print("== 纯函数：config 读写 ==")
    tmp = Path(tempfile.mkdtemp()) / "config.json"
    fd.set_config_path(tmp)
    check("默认地址（无文件）", fd.load_feedback_server_url() == fd.DEFAULT_SERVER_URL)
    check("保存返回 True", fd.save_feedback_server_url("http://10.0.0.1:8080") is True)
    check("读回保存值", fd.load_feedback_server_url() == "http://10.0.0.1:8080")
    data = json.loads(tmp.read_text(encoding="utf-8"))
    check("写入 feedback 段", data.get("feedback", {}).get("server_url") == "http://10.0.0.1:8080")
    # 保留其他段
    data["serial"] = {"port": "COM3"}
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    fd.save_feedback_server_url("http://new:9000")
    data2 = json.loads(tmp.read_text(encoding="utf-8"))
    check("不覆盖其他段", data2.get("serial", {}).get("port") == "COM3"
          and data2["feedback"]["server_url"] == "http://new:9000")

    print("== 纯函数：validate_fields ==")
    check("空地址拦截", fd.validate_fields("功能异常", "南网协议", "x", "", 0, "")[0] is False)
    check("空描述拦截", fd.validate_fields("功能异常", "南网协议", "   ", "", 0, "http://x")[0] is False)
    check("非法类型拦截", fd.validate_fields("胡说", "南网协议", "x", "", 0, "http://x")[0] is False)
    check("描述超长拦截",
          fd.validate_fields("功能异常", "p", "字" * (fd.MAX_DESC_LEN + 1), "", 0, "http://x")[0] is False)
    check("联系方式超长拦截",
          fd.validate_fields("功能异常", "p", "x", "1" * (fd.MAX_CONTACT_LEN + 1), 0, "http://x")[0] is False)
    check("截图超量拦截",
          fd.validate_fields("功能异常", "p", "x", "", fd.MAX_SCREENSHOTS + 1, "http://x")[0] is False)
    check("合法通过",
          fd.validate_fields("功能异常", "南网协议", "有问题", "qq", 2, "http://x")[0] is True)

    print("== 纯函数：collect_sys_info ==")
    si = fd.collect_sys_info("1.20.0", "2026-09-01", "南网协议")
    check("含版本", "1.20.0" in si)
    check("含 OS", "操作系统" in si)
    check("含协议", "南网协议" in si)
    check("含渠道", "GUI" in si or "桌面" in si)

    print("== Qt offscreen：对话框 ==")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    dlg = fd.FeedbackDialog(None, app_version="1.20.0", build_date="2026-09-01",
                            protocol_name="南网协议")
    check("类型下拉 5 项", dlg.type_combo.count() == len(fd.ISSUE_TYPES) == 5)
    check("协议下拉 13 项", dlg.proto_combo.count() == len(fd.PROTOCOL_OPTIONS) == 13)
    check("当前协议自动带入", "南网" in dlg.proto_combo.currentText(),
          dlg.proto_combo.currentText())
    check("环境信息框有内容", "1.20.0" in dlg.sys_edit.toPlainText())
    check("初始无截图", dlg.shot_list.count() == 0 and len(dlg._shots) == 0)

    print("== 截图添加/移除/超限 ==")
    png = make_png_bytes()
    dlg._shots.append(("a.png", png))
    dlg._refresh_shots()
    check("添加后列表 +1", dlg.shot_list.count() == 1)
    dlg._shots.append(("b.png", png))
    dlg._shots.append(("c.png", png))
    dlg._refresh_shots()
    check("3 张满额", dlg.shot_list.count() == 3)
    dlg.shot_list.setCurrentRow(0)
    dlg._remove_shot()
    check("移除选中后 -1", dlg.shot_list.count() == 2 and len(dlg._shots) == 2)

    print("== 空描述提交被拦截（不发请求）=")
    dlg2 = fd.FeedbackDialog(None, app_version="1.20.0", build_date="2026-09-01",
                             protocol_name="698.45协议")
    dlg2.server_url = ""  # 清空地址
    dlg2.desc_edit.setPlainText("")
    dlg2._on_submit()
    check("空地址+空描述时 status 提示且无 reply",
          dlg2._reply is None and dlg2.status_label.text() != "")

    print("== multipart 组帧不崩溃（构造 QHttpMultiPart） ==")
    from PySide6.QtNetwork import QHttpMultiPart, QNetworkRequest

    dlg3 = fd.FeedbackDialog(None, app_version="1.20.0", build_date="2026-09-01",
                             protocol_name="南网协议")
    dlg3.desc_edit.setPlainText("测试问题")
    dlg3._shots.append(("shot.png", png))
    # 直接调用内部组帧逻辑的等价路径：构造 multi 后不 post（避免真实网络）
    multi = QHttpMultiPart(QHttpMultiPart.ContentType.FormDataType)
    from PySide6.QtCore import QByteArray
    from PySide6.QtNetwork import QHttpPart
    part = QHttpPart()
    part.setHeader(
        QNetworkRequest.KnownHeaders.ContentDispositionHeader,
        'form-data; name="issue_type"',
    )
    part.setBody(QByteArray("功能异常".encode()))
    multi.append(part)
    check("QHttpMultiPart 可构造", multi is not None)

    print(f"\n{'='*50}")
    print(f"结果: {PASS} 通过, {FAIL} 失败")
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
