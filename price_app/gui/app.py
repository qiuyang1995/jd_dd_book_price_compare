from __future__ import annotations

import queue
import re
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from price_app.config import APP_TITLE
from price_app.services.dangdang import DangDangPriceService
from price_app.services.jd_playwright import JDPlaywrightService
from price_app.services.workflow import PriceWorkflow


PALETTE = {
    "bg": "#EEF3F8",
    "card": "#F9FBFD",
    "card_alt": "#FFFFFF",
    "line": "#D9E3EE",
    "text": "#17324D",
    "muted": "#62758A",
    "primary": "#1D4ED8",
    "primary_hover": "#1E40AF",
    "accent": "#0F766E",
    "accent_hover": "#115E59",
    "warning": "#C2410C",
    "warning_hover": "#9A3412",
    "pill": "#DCEAFE",
    "pill_text": "#1E3A8A",
    "log_bg": "#F4F8FC",
}


class TkCallBridge:
    """让后台线程把同步 UI 调用切回 Tk 主线程执行。"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self._tasks: "queue.Queue[tuple[object, tuple[object, ...], dict[str, object], threading.Event | None, dict[str, object] | None]]" = queue.Queue()
        self.root.after(20, self._drain_tasks)

    def run_sync(self, func, *args, **kwargs):
        result: dict[str, object] = {}
        event = threading.Event()
        self._tasks.put((func, args, kwargs, event, result))
        event.wait()
        if "error" in result:
            raise result["error"]  # type: ignore[misc]
        return result.get("value")

    def run_async(self, func, *args, **kwargs) -> None:
        self._tasks.put((func, args, kwargs, None, None))

    def _drain_tasks(self) -> None:
        while True:
            try:
                func, args, kwargs, event, result = self._tasks.get_nowait()
            except queue.Empty:
                break

            try:
                value = func(*args, **kwargs)
                if result is not None:
                    result["value"] = value
            except BaseException as exc:  # noqa: BLE001 - 需要把异常透传回工作线程
                if result is not None:
                    result["error"] = exc
            finally:
                if event is not None:
                    event.set()

        self.root.after(20, self._drain_tasks)


class JDPriceFetcherApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1040x860")
        self.root.minsize(960, 760)
        self.root.resizable(True, True)
        self.root.configure(bg=PALETTE["bg"])

        self.file_path = ""
        self.bridge = TkCallBridge(root)
        self.file_path_var = tk.StringVar(value="未选择 Excel 文件")
        self.status_var = tk.StringVar(value="就绪")
        self.progress_text_var = tk.StringVar(value="等待开始")
        self.helper_var = tk.StringVar(value="首次使用请先测试京东访问并完成扫码登录。")

        self._configure_styles()
        self._build_ui()
        self.log("📝 日志系统已启动，等待操作。")

    def _configure_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Modern.Horizontal.TProgressbar",
            troughcolor="#DCE5EF",
            borderwidth=0,
            background=PALETTE["primary"],
            lightcolor=PALETTE["primary"],
            darkcolor=PALETTE["primary"],
            thickness=12,
        )

    def _build_ui(self) -> None:
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        shell = tk.Frame(self.root, bg=PALETTE["bg"], padx=18, pady=18)
        shell.grid(sticky="nsew")
        shell.grid_rowconfigure(3, weight=1)
        shell.grid_columnconfigure(0, weight=1)

        self._build_header(shell)
        self._build_control_panel(shell)
        self._build_progress_panel(shell)
        self._build_log_panel(shell)
        self._build_footer(shell)

    def _build_header(self, parent: tk.Frame) -> None:
        header = self._card(parent, bg=PALETTE["card_alt"], pady=18, padx=22)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        title = tk.Label(
            header,
            text="图书价格抓取工作台",
            font=("微软雅黑", 22, "bold"),
            fg=PALETTE["text"],
            bg=PALETTE["card_alt"],
        )
        title.grid(row=0, column=0, sticky="w")

        subtitle = tk.Label(
            header,
            text="京东 / 当当 图书价格对比、登录态复用与 Excel 自动回写",
            font=("微软雅黑", 10),
            fg=PALETTE["muted"],
            bg=PALETTE["card_alt"],
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(6, 0))

        self.status_badge = tk.Label(
            header,
            textvariable=self.status_var,
            font=("微软雅黑", 10, "bold"),
            fg=PALETTE["pill_text"],
            bg=PALETTE["pill"],
            padx=14,
            pady=8,
        )
        self.status_badge.grid(row=0, column=1, rowspan=2, sticky="e")

    def _build_control_panel(self, parent: tk.Frame) -> None:
        controls = self._card(parent, bg=PALETTE["card"], pady=14, padx=16)
        controls.grid(row=1, column=0, sticky="ew", pady=(18, 0))
        controls.grid_columnconfigure(0, weight=1)
        controls.grid_columnconfigure(1, weight=1)
        controls.grid_columnconfigure(2, weight=1)
        controls.grid_columnconfigure(3, weight=1)

        section_title = tk.Label(
            controls,
            text="操作面板",
            font=("微软雅黑", 11, "bold"),
            fg=PALETTE["text"],
            bg=PALETTE["card"],
        )
        section_title.grid(row=0, column=0, sticky="w", columnspan=4)

        section_hint = tk.Label(
            controls,
            textvariable=self.helper_var,
            font=("微软雅黑", 9),
            fg=PALETTE["muted"],
            bg=PALETTE["card"],
        )
        section_hint.grid(row=1, column=0, sticky="w", columnspan=4, pady=(4, 10))

        self.select_btn = self._action_button(
            controls,
            text="选择 Excel 文件",
            command=self.select_file,
            bg=PALETTE["primary"],
            hover_bg=PALETTE["primary_hover"],
        )
        self.select_btn.grid(row=2, column=0, sticky="ew", padx=(0, 8))

        self.test_jd_btn = self._action_button(
            controls,
            text="测试京东访问",
            command=self.test_jd_access,
            bg=PALETTE["accent"],
            hover_bg=PALETTE["accent_hover"],
        )
        self.test_jd_btn.grid(row=2, column=1, sticky="ew", padx=8)

        self.test_dd_btn = self._action_button(
            controls,
            text="测试当当访问",
            command=self.test_dd_access,
            bg="#0F766E",
            hover_bg="#0B5E58",
        )
        self.test_dd_btn.grid(row=2, column=2, sticky="ew", padx=8)

        self.start_btn = self._action_button(
            controls,
            text="开始批量执行",
            command=self.start,
            bg=PALETTE["warning"],
            hover_bg=PALETTE["warning_hover"],
        )
        self.start_btn.grid(row=2, column=3, sticky="ew", padx=(8, 0))

        file_card = tk.Frame(
            controls,
            bg=PALETTE["card_alt"],
            highlightbackground=PALETTE["line"],
            highlightthickness=1,
            bd=0,
            padx=16,
            pady=10,
        )
        file_card.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        file_card.grid_columnconfigure(1, weight=1)

        file_label = tk.Label(
            file_card,
            text="当前文件",
            font=("微软雅黑", 9, "bold"),
            fg=PALETTE["muted"],
            bg=PALETTE["card_alt"],
        )
        file_label.grid(row=0, column=0, sticky="w")

        self.file_value_label = tk.Label(
            file_card,
            textvariable=self.file_path_var,
            font=("Consolas", 10),
            fg=PALETTE["text"],
            bg=PALETTE["card_alt"],
            justify="left",
            anchor="w",
            wraplength=760,
        )
        self.file_value_label.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))

    def _build_progress_panel(self, parent: tk.Frame) -> None:
        progress_card = self._card(parent, bg=PALETTE["card_alt"], pady=14, padx=16)
        progress_card.grid(row=2, column=0, sticky="ew", pady=(18, 0))
        progress_card.grid_columnconfigure(0, weight=1)

        top_row = tk.Frame(progress_card, bg=PALETTE["card_alt"])
        top_row.grid(row=0, column=0, sticky="ew")
        top_row.grid_columnconfigure(0, weight=1)

        progress_title = tk.Label(
            top_row,
            text="任务进度",
            font=("微软雅黑", 11, "bold"),
            fg=PALETTE["text"],
            bg=PALETTE["card_alt"],
        )
        progress_title.grid(row=0, column=0, sticky="w")

        self.progress_label = tk.Label(
            top_row,
            textvariable=self.progress_text_var,
            font=("Consolas", 10, "bold"),
            fg=PALETTE["primary"],
            bg=PALETTE["card_alt"],
        )
        self.progress_label.grid(row=0, column=1, sticky="e")

        self.progress = ttk.Progressbar(
            progress_card,
            length=100,
            mode="determinate",
            style="Modern.Horizontal.TProgressbar",
        )
        self.progress.grid(row=1, column=0, sticky="ew", pady=(12, 10))

        progress_hint = tk.Label(
            progress_card,
            text="默认请求间隔 15-25 秒，异常时会自动提高，尽量避开京东风控。",
            font=("微软雅黑", 9),
            fg=PALETTE["muted"],
            bg=PALETTE["card_alt"],
        )
        progress_hint.grid(row=2, column=0, sticky="w")

    def _build_log_panel(self, parent: tk.Frame) -> None:
        log_card = self._card(parent, bg=PALETTE["card"], pady=14, padx=16)
        log_card.grid(row=3, column=0, sticky="nsew", pady=(18, 0))
        log_card.grid_rowconfigure(1, weight=1)
        log_card.grid_columnconfigure(0, weight=1)

        header = tk.Frame(log_card, bg=PALETTE["card"])
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.grid_columnconfigure(0, weight=1)

        log_title = tk.Label(
            header,
            text="运行日志",
            font=("微软雅黑", 11, "bold"),
            fg=PALETTE["text"],
            bg=PALETTE["card"],
        )
        log_title.grid(row=0, column=0, sticky="w")

        log_hint = tk.Label(
            header,
            text="日志会自动滚动到最新位置",
            font=("微软雅黑", 9),
            fg=PALETTE["muted"],
            bg=PALETTE["card"],
        )
        log_hint.grid(row=0, column=1, sticky="e")

        log_frame = tk.Frame(
            log_card,
            bg=PALETTE["log_bg"],
            highlightbackground=PALETTE["line"],
            highlightthickness=1,
            bd=0,
        )
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        self.log_box = tk.Text(
            log_frame,
            height=16,
            wrap="word",
            state="disabled",
            bg=PALETTE["log_bg"],
            fg=PALETTE["text"],
            bd=0,
            relief="flat",
            padx=16,
            pady=16,
            insertbackground=PALETTE["text"],
            selectbackground="#C7DAF7",
            font=("Consolas", 10),
        )
        self.log_box.grid(row=0, column=0, sticky="nsew")
        self.log_box.tag_configure("timestamp", foreground="#7C8EA1")
        self.log_box.tag_configure("level_info", foreground=PALETTE["primary"])
        self.log_box.tag_configure("level_success", foreground="#0F766E")
        self.log_box.tag_configure("level_warn", foreground="#B45309")
        self.log_box.tag_configure("level_error", foreground="#B91C1C")
        self.log_box.tag_configure("message_info", foreground=PALETTE["text"])
        self.log_box.tag_configure("message_success", foreground="#0B5E58")
        self.log_box.tag_configure("message_warn", foreground="#92400E")
        self.log_box.tag_configure("message_error", foreground="#991B1B")

        scrollbar = tk.Scrollbar(
            log_frame,
            orient="vertical",
            command=self.log_box.yview,
            activebackground=PALETTE["primary"],
            troughcolor="#E5EDF5",
            bg="#CCD8E5",
            bd=0,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_box.configure(yscrollcommand=scrollbar.set)

    def _build_footer(self, parent: tk.Frame) -> None:
        footer = tk.Frame(parent, bg=PALETTE["bg"], pady=10)
        footer.grid(row=4, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)

        footer_label = tk.Label(
            footer,
            text="Playwright 持久化登录态 · Excel 自动回写 · GUI 线程安全调度",
            font=("微软雅黑", 9),
            fg=PALETTE["muted"],
            bg=PALETTE["bg"],
        )
        footer_label.grid(row=0, column=0, sticky="w")

    def log(self, message: str) -> None:
        self.bridge.run_async(self._append_log, message)

    def _append_log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        level, clean_message = self._normalize_log_message(message)
        self.log_box.config(state="normal")
        self.log_box.insert(tk.END, f"[{timestamp}] ", ("timestamp",))
        self.log_box.insert(tk.END, f"[{level}] ", (f"level_{level.lower()}",))
        self.log_box.insert(tk.END, f"{clean_message}\n", (f"message_{level.lower()}",))
        self.log_box.see(tk.END)
        self.log_box.config(state="disabled")

    def select_file(self) -> None:
        file_path = filedialog.askopenfilename(filetypes=[("Excel 文件", "*.xlsx")])
        if file_path:
            self.file_path = file_path
            self.file_path_var.set(file_path)
            self.status_var.set("文件已就绪")
            self.helper_var.set("文件已选择，可以直接开始批量执行。")
            self.log(f"📂 已选择文件：{file_path}")

    def start(self) -> None:
        if not self.file_path:
            messagebox.showwarning("提示", "请先选择 Excel 文件。")
            return

        self._set_running(True, status_text="批量处理中")
        self.helper_var.set("正在批量抓取价格，期间会自动保存 Excel 进度。")
        threading.Thread(target=self._run_process, daemon=True).start()

    def test_jd_access(self) -> None:
        self._set_running(True, status_text="京东测试中")
        self.helper_var.set("正在校验京东登录态与搜索能力。")
        threading.Thread(target=self._run_jd_test, daemon=True).start()

    def test_dd_access(self) -> None:
        self._set_running(True, status_text="当当测试中")
        self.helper_var.set("正在校验当当搜索与价格解析能力。")
        threading.Thread(target=self._run_dd_test, daemon=True).start()

    def _run_process(self) -> None:
        try:
            self.log("🚀 开始处理 Excel 文件。")
            with JDPlaywrightService(log_callback=self.log) as jd_service:
                workflow = PriceWorkflow(
                    jd_service=jd_service,
                    dd_service=DangDangPriceService(),
                    log_callback=self.log,
                    progress_callback=self._update_progress,
                    confirm_login=self._confirm_jd_login,
                )
                summary = workflow.process(self.file_path)

            elapsed = self._format_duration(summary.elapsed_seconds)
            self.log(f"🎉 全部完成，共处理 {summary.processed_rows}/{summary.total_rows} 条，耗时 {elapsed}。")
            self.bridge.run_sync(messagebox.showinfo, "完成", f"价格抓取完成。\n总耗时：{elapsed}")
        except Exception as exc:  # noqa: BLE001 - 需要把失败直接反馈给用户
            self.log(f"❌ 执行失败：{exc}")
            self.bridge.run_sync(messagebox.showerror, "执行失败", str(exc))
        finally:
            self._set_running(False)

    def _run_jd_test(self) -> None:
        test_isbns = ["9787575307130", "9787308262453"]
        start_time = time.time()
        success_count = 0

        try:
            self.log("🧪 开始测试京东访问。")
            with JDPlaywrightService(log_callback=self.log) as jd_service:
                if not jd_service.ensure_login(self._confirm_jd_login):
                    raise RuntimeError("京东登录失败，请确认扫码已完成。")

                for index, isbn in enumerate(test_isbns, start=1):
                    result = jd_service.fetch_price(isbn)
                    if result.is_success:
                        success_count += 1
                        self.log(f"✅ {index}/{len(test_isbns)} {isbn} -> ¥{result.price}")
                    else:
                        self.log(f"⚠️ {index}/{len(test_isbns)} {isbn} -> {result.display_value or result.status.value}")

            elapsed = self._format_duration(time.time() - start_time)
            self.bridge.run_sync(
                messagebox.showinfo,
                "测试结果",
                f"京东测试完成。\n成功 {success_count}/{len(test_isbns)} 条\n耗时：{elapsed}",
            )
        except Exception as exc:  # noqa: BLE001
            self.log(f"❌ 京东测试失败：{exc}")
            self.bridge.run_sync(messagebox.showerror, "测试失败", str(exc))
        finally:
            self._set_running(False)

    def _run_dd_test(self) -> None:
        test_isbns = ["9787513948128", "9787229192914"]
        start_time = time.time()
        success_count = 0

        try:
            self.log("🧪 开始测试当当访问。")
            service = DangDangPriceService()
            for index, isbn in enumerate(test_isbns, start=1):
                result = service.fetch_price(isbn)
                if result.price:
                    success_count += 1
                    self.log(f"✅ {index}/{len(test_isbns)} {isbn} -> ¥{result.price} {result.discount}".rstrip())
                else:
                    self.log(f"⚠️ {index}/{len(test_isbns)} {isbn} 未获取到有效价格。")

            elapsed = self._format_duration(time.time() - start_time)
            self.bridge.run_sync(
                messagebox.showinfo,
                "测试结果",
                f"当当测试完成。\n成功 {success_count}/{len(test_isbns)} 条\n耗时：{elapsed}",
            )
        except Exception as exc:  # noqa: BLE001
            self.log(f"❌ 当当测试失败：{exc}")
            self.bridge.run_sync(messagebox.showerror, "测试失败", str(exc))
        finally:
            self._set_running(False)

    def _confirm_jd_login(self) -> bool:
        return bool(
            self.bridge.run_sync(
                messagebox.askyesno,
                "京东登录确认",
                "请在打开的浏览器中完成京东扫码登录。\n完成后点击“是”，未完成点击“否”重新打开登录页。",
            )
        )

    def _update_progress(self, current: int, total: int) -> None:
        self.bridge.run_async(self._set_progress_value, current, total)

    def _set_progress_value(self, current: int, total: int) -> None:
        safe_total = max(total, 1)
        percent = int((current / safe_total) * 100)
        self.progress["maximum"] = safe_total
        self.progress["value"] = current
        self.progress_text_var.set(f"{current}/{total} · {percent}%")

    def _set_running(self, running: bool, status_text: str | None = None) -> None:
        self.bridge.run_async(self._set_controls_state, running, status_text)

    def _set_controls_state(self, running: bool, status_text: str | None = None) -> None:
        state = "disabled" if running else "normal"
        self.select_btn.config(state=state)
        self.test_jd_btn.config(state=state)
        self.test_dd_btn.config(state=state)
        self.start_btn.config(state=state)

        if running:
            self.status_var.set(status_text or "处理中")
            self.status_badge.config(bg="#FEF3C7", fg="#92400E")
            return

        self.status_var.set("就绪")
        self.helper_var.set("首次使用请先测试京东访问并完成扫码登录。")
        self.status_badge.config(bg=PALETTE["pill"], fg=PALETTE["pill_text"])

    @staticmethod
    def _format_duration(seconds: float) -> str:
        hours, remainder = divmod(int(seconds), 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}时{minutes:02d}分{secs:02d}秒"

    @staticmethod
    def _card(parent: tk.Widget, bg: str, padx: int, pady: int) -> tk.Frame:
        return tk.Frame(
            parent,
            bg=bg,
            highlightbackground=PALETTE["line"],
            highlightthickness=1,
            bd=0,
            padx=padx,
            pady=pady,
        )

    def _action_button(
        self,
        parent: tk.Widget,
        text: str,
        command,
        bg: str,
        hover_bg: str,
    ) -> tk.Button:
        button = tk.Button(
            parent,
            text=text,
            command=command,
            font=("微软雅黑", 10, "bold"),
            bg=bg,
            fg="white",
            activebackground=hover_bg,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=18,
            pady=12,
            cursor="hand2",
            disabledforeground="#DDE7F2",
        )
        button.bind("<Enter>", lambda _event: button.config(bg=hover_bg))
        button.bind("<Leave>", lambda _event: button.config(bg=bg))
        return button

    @staticmethod
    def _normalize_log_message(message: str) -> tuple[str, str]:
        level = "INFO"
        if "❌" in message or "失败" in message or "错误" in message:
            level = "ERROR"
        elif "⚠" in message or "警告" in message or "访问受限" in message:
            level = "WARN"
        elif "✅" in message or "🎉" in message or "成功" in message or "完成" in message:
            level = "SUCCESS"

        clean_message = re.sub(r"^[^\w\u4e00-\u9fff]+", "", message).strip()
        return level, clean_message or message


def run() -> None:
    root = tk.Tk()
    JDPriceFetcherApp(root)
    root.mainloop()
