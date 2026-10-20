"""version.json 生成工具（tkinter GUI，纯标准库，零依赖）

用 PyInstaller 打包成单 exe，放服务器上直接用。

用法：
    python gen_version_gui.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


def find_default_exe() -> str:
    """启动时自动找同目录下的 exe。"""
    # 打包后：exe 所在目录；源码运行：脚本所在目录
    if getattr(sys, "frozen", False):
        here = Path(sys.executable).parent
    else:
        here = Path(__file__).resolve().parent
    for p in here.glob("*.exe"):
        if p.is_file() and p.name != Path(sys.executable).name:
            return str(p)
    return ""


def sha256_of_file(path: Path, progress_cb=None) -> str:
    """计算 SHA-256，可选进度回调 percent(float)。"""
    total = path.stat().st_size
    h = hashlib.sha256()
    done = 0
    chunk_size = 1 << 20  # 1 MB
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
            done += len(chunk)
            if progress_cb and total:
                progress_cb(done * 100.0 / total)
    if progress_cb:
        progress_cb(100.0)
    return h.hexdigest()


class VersionGenApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("version.json 生成工具")
        root.geometry("560x380")
        root.resizable(False, False)

        # 变量
        self.exe_path_var = tk.StringVar(value=find_default_exe())
        self.version_var = tk.StringVar(value="")
        self.url_var = tk.StringVar(value="")
        self.notes_var = tk.StringVar(value="")
        self.output_var = tk.StringVar(value="")

        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}
        frm = ttk.Frame(self.root)
        frm.pack(fill="both", expand=True, padx=12, pady=12)

        # exe 路径
        ttk.Label(frm, text="exe 文件:").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.exe_path_var, width=48).grid(row=0, column=1, **pad)
        ttk.Button(frm, text="浏览...", command=self._browse_exe, width=8).grid(row=0, column=2, **pad)

        # 版本号
        ttk.Label(frm, text="版本号:").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.version_var, width=48).grid(row=1, column=1, columnspan=2, sticky="w", **pad)

        # 下载地址
        ttk.Label(frm, text="下载地址:").grid(row=2, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.url_var, width=48).grid(row=2, column=1, columnspan=2, sticky="w", **pad)
        tip = ttk.Label(frm, text="留空则自动填 /下载/文件名", foreground="gray")
        tip.grid(row=3, column=1, sticky="w", padx=10)

        # 更新说明
        ttk.Label(frm, text="更新说明:").grid(row=4, column=0, sticky="nw", **pad)
        self.notes_text = tk.Text(frm, width=48, height=4)
        self.notes_text.grid(row=4, column=1, columnspan=2, **pad)

        # 输出路径
        ttk.Label(frm, text="输出路径:").grid(row=5, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.output_var, width=48).grid(row=5, column=1, **pad)
        ttk.Button(frm, text="浏览...", command=self._browse_output, width=8).grid(row=5, column=2, **pad)

        # 进度条
        self.progress = ttk.Progressbar(frm, mode="determinate", length=420)
        self.progress.grid(row=6, column=0, columnspan=3, **pad)

        # 按钮
        btn_frm = ttk.Frame(frm)
        btn_frm.grid(row=7, column=0, columnspan=3, pady=10)
        self.gen_btn = ttk.Button(btn_frm, text="生成 version.json", command=self._generate, width=20)
        self.gen_btn.pack(side="left", padx=8)
        ttk.Button(btn_frm, text="退出", command=self.root.destroy, width=10).pack(side="left", padx=8)

        # 状态
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(frm, textvariable=self.status_var, foreground="blue").grid(
            row=8, column=0, columnspan=3, sticky="w", padx=10)

    def _browse_exe(self):
        path = filedialog.askopenfilename(
            title="选择 exe 文件",
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")],
        )
        if path:
            self.exe_path_var.set(path)
            # 自动填输出路径
            if not self.output_var.get():
                self.output_var.set(str(Path(path).parent / "version.json"))
            # 自动填下载地址
            if not self.url_var.get():
                from urllib.parse import quote
                self.url_var.set(f"/download/{quote(Path(path).name)}")

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            title="保存 version.json",
            defaultextension=".json",
            filetypes=[("JSON 文件", "*.json")],
            initialfile="version.json",
        )
        if path:
            self.output_var.set(path)

    def _generate(self):
        exe = self.exe_path_var.get().strip()
        version = self.version_var.get().strip()

        if not exe:
            messagebox.showerror("错误", "请选择 exe 文件")
            return
        if not Path(exe).exists():
            messagebox.showerror("错误", f"exe 不存在:\n{exe}")
            return
        if not version:
            messagebox.showerror("错误", "请输入版本号")
            return

        self.gen_btn.config(state="disabled")
        self.progress["value"] = 0
        self.status_var.set("计算 SHA-256...")

        # 后台线程计算，避免 GUI 卡住
        t = threading.Thread(target=self._do_generate, daemon=True)
        t.start()

    def _do_generate(self):
        try:
            exe_path = Path(self.exe_path_var.get().strip())
            version = self.version_var.get().strip()
            notes = self.notes_text.get("1.0", "end").strip()
            url = self.url_var.get().strip()

            if not url:
                from urllib.parse import quote
                url = f"/download/{quote(exe_path.name)}"

            def set_progress(v):
                self.root.after(0, lambda: self.progress.configure(value=v))

            sha = sha256_of_file(exe_path, progress_cb=set_progress)

            data = {
                "version": version,
                "url": url,
                "notes": notes,
                "sha256": sha,
            }

            out = self.output_var.get().strip()
            if out:
                out_path = Path(out)
            else:
                out_path = exe_path.parent / "version.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

            self.root.after(0, lambda: self._on_success(out_path, sha))
        except Exception as e:
            # 先把消息取出再进闭包：except 块结束后 `e` 会被解绑，
            # 而 after(0, ...) 是延迟执行，届时 str(e) 会抛 NameError 吞掉真实错误
            err_msg = str(e)
            self.root.after(0, lambda: self._on_error(err_msg))

    def _on_success(self, out_path: Path, sha: str):
        self.gen_btn.config(state="normal")
        self.status_var.set(f"完成 → {out_path.name}")
        messagebox.showinfo(
            "成功",
            f"version.json 已生成:\n{out_path}\n\nSHA-256:\n{sha}"
        )

    def _on_error(self, msg: str):
        self.gen_btn.config(state="normal")
        self.status_var.set("失败")
        messagebox.showerror("错误", msg)


def main():
    root = tk.Tk()
    # 尝试设置默认字体，改善中文显示
    try:
        from tkinter import font
        default_font = font.nametofont("TkDefaultFont")
        default_font.configure(size=10)
        root.option_add("*Font", default_font)
    except Exception:
        pass
    VersionGenApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
