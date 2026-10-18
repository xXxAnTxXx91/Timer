import ctypes
import json
import os
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

try:
    import pystray
    from PIL import Image
except ImportError:
    pystray = None
    Image = None


class ShutdownTimerApp:
    BG = "#101820"
    CARD = "#192630"
    MUTED = "#9aabb7"
    TEXT = "#f3f6f8"
    ACCENT = "#58d6a5"
    RED = "#ff6b70"
    ACTIONS = {
        "Выключение": "/s",
        "Перезагрузка": "/r",
        "Сон": "/sleep",
    }

    def __init__(self, root):
        self.root = root
        self.root.title("Таймер выключения")
        self.root.geometry("480x530")
        self.root.resizable(False, False)
        self.root.configure(bg=self.BG)
        icon_path = Path(__file__).resolve().with_name("ico.ico")
        if icon_path.exists():
            try:
                self.root.iconbitmap(str(icon_path))
            except tk.TclError:
                pass
        self.config_path = self._config_path()
        self.settings = self._load_settings()
        self.remaining = 0
        self.total_seconds = 0
        self.deadline = None
        self.after_id = None
        self.timer_running = False
        self.shutdown_pending = False
        self.tray_icon = None
        self.warning_window = None
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    @staticmethod
    def _config_path():
        base = Path.home()
        appdata = Path(os.environ.get("APPDATA", base))
        return appdata / "Таймер выключения" / "settings.json"

    def _load_settings(self):
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_settings(self):
        data = {
            "time": self.time_var.get().strip(),
            "action": self.action_var.get(),
            "warning_delay": self.delay_var.get(),
        }
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Timer.Horizontal.TProgressbar",
            troughcolor="#293943",
            background=self.ACCENT,
            bordercolor="#293943",
            lightcolor=self.ACCENT,
            darkcolor=self.ACCENT,
        )

        content = tk.Frame(self.root, bg=self.BG, width=440)
        content.pack(fill="x", padx=20, pady=12)

        card = tk.Frame(
            content, bg=self.CARD, highlightthickness=1, highlightbackground="#2a3b46"
        )
        card.pack(fill="x")
        tk.Label(
            card,
            text="Время до действия",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Segoe UI", 10),
        ).pack(pady=(9, 4))
        self.time_var = tk.StringVar(value=self.settings.get("time", "30"))
        self.entry = tk.Entry(
            card,
            textvariable=self.time_var,
            font=("Segoe UI", 19),
            width=13,
            justify="center",
            bg="#23343f",
            fg=self.TEXT,
            insertbackground=self.TEXT,
            relief="flat",
            highlightthickness=1,
            highlightbackground="#40535f",
            highlightcolor=self.ACCENT,
        )
        self.entry.pack(ipady=3)
        tk.Label(
            card,
            text="Минуты (например, 90) или ЧЧ:ММ:СС",
            bg=self.CARD,
            fg=self.MUTED,
            font=("Segoe UI", 8),
        ).pack(pady=(2, 6))

        presets = tk.Frame(card, bg=self.CARD)
        presets.pack(fill="x", padx=12, pady=(0, 8))
        for col in range(5):
            presets.grid_columnconfigure(col, weight=1, uniform="preset")
        for col, value in enumerate((15, 30, 60, 90, 120)):
            tk.Button(
                presets,
                text=f"{value} мин",
                command=lambda v=value: self.set_preset(v),
                bg="#293b46",
                fg=self.TEXT,
                activebackground="#344b58",
                activeforeground=self.TEXT,
                font=("Segoe UI", 9),
                relief="flat",
                pady=6,
                cursor="hand2",
            ).grid(row=0, column=col, sticky="ew", padx=4)

        options = tk.Frame(card, bg=self.CARD)
        options.pack(fill="x", padx=16, pady=(0, 8))
        options.grid_columnconfigure(1, weight=1)
        tk.Label(
            options, text="Действие", bg=self.CARD, fg=self.TEXT, font=("Segoe UI", 10)
        ).grid(row=0, column=0, sticky="w", pady=4)
        self.action_var = tk.StringVar(value=self.settings.get("action", "Выключение"))
        if self.action_var.get() not in self.ACTIONS:
            self.action_var.set("Выключение")
        self.action_box = DarkDropdown(
            options, self.action_var, list(self.ACTIONS), self.TEXT, self.ACCENT
        )
        self.action_box.grid(row=0, column=1, sticky="ew", padx=(12, 0), pady=4)
        tk.Label(
            options,
            text="Предупредить заранее",
            bg=self.CARD,
            fg=self.TEXT,
            font=("Segoe UI", 10),
        ).grid(row=1, column=0, sticky="w", pady=4)
        self.delay_var = tk.StringVar(
            value=str(self.settings.get("warning_delay", "20 секунд"))
        )
        if self.delay_var.get() not in ("0 секунд", "20 секунд", "60 секунд"):
            self.delay_var.set("20 секунд")
        self.delay_box = DarkDropdown(
            options,
            self.delay_var,
            ("0 секунд", "20 секунд", "60 секунд"),
            self.TEXT,
            self.ACCENT,
        )
        self.delay_box.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=4)

        self.time_label = tk.Label(
            content,
            text="00:00:00",
            bg=self.BG,
            fg=self.TEXT,
            font=("Segoe UI", 31, "bold"),
        )
        self.time_label.pack(pady=(9, 0))
        self.status_label = tk.Label(
            content,
            text="Таймер не запущен",
            bg=self.BG,
            fg=self.MUTED,
            font=("Segoe UI", 9),
            height=2,
            wraplength=420,
        )
        self.status_label.pack(fill="x")
        self.progress = ttk.Progressbar(
            content,
            style="Timer.Horizontal.TProgressbar",
            mode="determinate",
            maximum=100,
        )
        self.progress.pack(fill="x", pady=(1, 9))

        actions = tk.Frame(content, bg=self.BG)
        actions.pack(fill="x", padx=28)
        self.start_button = tk.Button(
            actions,
            text="Запустить таймер",
            command=self.start_timer,
            bg=self.ACCENT,
            fg="#10251d",
            activebackground="#71e5b9",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            pady=7,
            cursor="hand2",
        )
        self.start_button.pack(fill="x")
        self.cancel_button = tk.Button(
            actions,
            text="Остановить таймер",
            command=self.cancel_timer,
            bg="#293943",
            fg=self.TEXT,
            activebackground="#3a4e59",
            font=("Segoe UI", 9),
            relief="flat",
            pady=7,
            cursor="hand2",
            state="disabled",
        )
        self.cancel_button.pack(fill="x", pady=(6, 0))
        self.tray_button = tk.Button(
            actions,
            text="Свернуть в трей",
            command=self.minimize_to_tray,
            bg="#293943",
            fg=self.TEXT,
            activebackground="#3a4e59",
            font=("Segoe UI", 9),
            relief="flat",
            pady=7,
            cursor="hand2",
        )
        self.tray_button.pack(fill="x", pady=(6, 0))

    def set_preset(self, value):
        self.time_var.set(str(value))
        self._save_settings()

    @staticmethod
    def _parse_duration(value):
        value = value.strip()
        if ":" not in value:
            minutes = int(value)
            seconds = minutes * 60
        else:
            parts = value.split(":")
            if len(parts) != 3 or any(not part.isdigit() for part in parts):
                raise ValueError
            hours, minutes, secs = map(int, parts)
            if minutes > 59 or secs > 59:
                raise ValueError
            seconds = hours * 3600 + minutes * 60 + secs
        if seconds <= 0:
            raise ValueError
        return seconds

    def start_timer(self):
        if self.timer_running or self.shutdown_pending:
            return
        try:
            self.total_seconds = self._parse_duration(self.time_var.get())
        except ValueError:
            messagebox.showerror(
                "Некорректное время",
                "Введите число минут или время в формате ЧЧ:ММ:СС.",
                parent=self.root,
            )
            return
        self._save_settings()
        self.remaining = self.total_seconds
        self.deadline = time.monotonic() + self.total_seconds
        self.timer_running = True
        self.entry.configure(state="disabled")
        self.action_box.configure(state="disabled")
        self.delay_box.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.cancel_button.configure(state="normal", text="Остановить таймер")
        self.status_label.configure(
            text=f"Будет выполнено: {self.action_var.get().lower()}", fg=self.ACCENT
        )
        self._tick()

    def _format_time(self, seconds):
        hours, remainder = divmod(max(0, seconds), 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _tick(self):
        if not self.timer_running:
            return
        self.remaining = max(0, int(self.deadline - time.monotonic() + 0.999))
        self.time_label.configure(text=self._format_time(self.remaining))
        elapsed = self.total_seconds - self.remaining
        self.progress.configure(value=(elapsed / self.total_seconds) * 100)
        if self.remaining <= 20 and self.remaining > 0:
            self.status_label.configure(
                text="Внимание: действие скоро начнётся", fg="#ffbe62"
            )
        if self.remaining <= 0:
            self.timer_running = False
            self._begin_action()
            return
        self.after_id = self.root.after(200, self._tick)

    def _begin_action(self):
        delay = int(self.delay_var.get().split()[0])
        action = self.ACTIONS[self.action_var.get()]
        self.shutdown_pending = True
        self.time_label.configure(text=self._format_time(delay))
        self.status_label.configure(
            text=f"{self.action_var.get()} через {delay} сек. Нажмите отмену, чтобы остановить.",
            fg="#ffbe62",
        )
        self.cancel_button.configure(state="normal", text="Отменить действие")
        self.deadline = time.monotonic() + delay
        if action in ("/s", "/r"):
            succeeded, error = self._run_shutdown(
                [action, "/t", str(delay), "/c", "Выполняется действие по таймеру"]
            )
            if not succeeded:
                self.shutdown_pending = False
                self._dismiss_warning()
                self.status_label.configure(
                    text=f"Не удалось запланировать действие: {error}", fg=self.RED
                )
                self._reset_controls()
                return
            if delay == 0:
                self.status_label.configure(
                    text=f"Выполняется: {self.action_var.get().lower()}", fg=self.RED
                )
                self._reset_controls()
                return
        self._pending_tick()
        if delay > 0:
            self.root.after(0, lambda: self._show_warning(delay))

    def _show_warning(self, delay):
        if not self.shutdown_pending or delay <= 0:
            return
        if self.warning_window is not None and self.warning_window.winfo_exists():
            return
        window = tk.Toplevel(self.root)
        self.warning_window = window
        window.title("Действие скоро начнётся")
        window.resizable(False, False)
        if self.root.state() == "normal":
            window.transient(self.root)
        window.configure(bg=self.BG)
        tk.Label(
            window,
            text=f"{self.action_var.get()} начнётся через {delay} секунд.",
            bg=self.BG,
            fg=self.TEXT,
            font=("Segoe UI", 10),
            padx=20,
            pady=16,
        ).pack(fill="x")
        buttons = tk.Frame(window, bg=self.BG)
        buttons.pack(fill="x", padx=16, pady=(0, 14))
        tk.Button(
            buttons,
            text="Отменить действие",
            command=self._cancel_from_warning,
            bg=self.RED,
            fg="#281315",
            activebackground="#ff8589",
            relief="flat",
            padx=10,
            pady=6,
        ).pack(side="left", expand=True, fill="x", padx=(0, 5))
        tk.Button(
            buttons,
            text="Оставить",
            command=self._dismiss_warning,
            bg="#293943",
            fg=self.TEXT,
            activebackground="#3a4e59",
            relief="flat",
            padx=10,
            pady=6,
        ).pack(side="left", expand=True, fill="x", padx=(5, 0))
        window.protocol("WM_DELETE_WINDOW", self._dismiss_warning)
        window.update_idletasks()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - window.winfo_width()) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - window.winfo_height()) // 2)
        window.geometry(f"+{x}+{y}")

    def _dismiss_warning(self):
        window = self.warning_window
        self.warning_window = None
        if window is not None:
            try:
                if window.winfo_exists():
                    window.destroy()
            except tk.TclError:
                pass

    def _cancel_from_warning(self):
        if self.cancel_timer():
            self._dismiss_warning()

    @staticmethod
    def _run_shutdown(arguments):
        try:
            result = subprocess.run(
                ["shutdown", *arguments],
                check=False,
                capture_output=True,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            return False, str(exc)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            return False, detail or f"Команда завершилась с кодом {result.returncode}."
        return True, ""

    def _pending_tick(self):
        if not self.shutdown_pending:
            return
        remaining = max(0, int(self.deadline - time.monotonic() + 0.999))
        self.time_label.configure(text=self._format_time(remaining))
        if remaining <= 0:
            self.after_id = None
            self._dismiss_warning()
            action = self.ACTIONS[self.action_var.get()]
            if action == "/sleep":
                self._perform_sleep()
            else:
                self.shutdown_pending = False
                self.status_label.configure(
                    text=f"Выполняется: {self.action_var.get().lower()}", fg=self.RED
                )
                self._reset_controls()
        else:
            self.after_id = self.root.after(200, self._pending_tick)

    def _perform_sleep(self):
        try:
            power = ctypes.WinDLL("powrprof", use_last_error=True)
            set_suspend_state = power.SetSuspendState
            set_suspend_state.argtypes = (
                ctypes.c_ubyte,
                ctypes.c_ubyte,
                ctypes.c_ubyte,
            )
            set_suspend_state.restype = ctypes.c_ubyte
            succeeded = set_suspend_state(0, 0, 0)
            if not succeeded:
                error = ctypes.get_last_error()
                raise OSError(error, "Windows не смогла перевести компьютер в сон")
        except (AttributeError, OSError) as exc:
            self.status_label.configure(
                text=f"Не удалось включить режим сна: {exc}", fg=self.RED
            )
            messagebox.showerror("Не удалось перейти в сон", str(exc), parent=self.root)
        else:
            self.status_label.configure(
                text="Компьютер переходит в сон…", fg=self.ACCENT
            )
        self.shutdown_pending = False
        self._reset_controls()

    def cancel_timer(self):
        if self.shutdown_pending:
            action = self.ACTIONS.get(self.action_var.get(), "/s")
            if action in ("/s", "/r"):
                succeeded, error = self._run_shutdown(["/a"])
                if not succeeded:
                    messagebox.showerror(
                        "Не удалось отменить",
                        f"Windows не смогла отменить действие: {error}",
                        parent=self.root,
                    )
                    return False
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self._dismiss_warning()
        if self.shutdown_pending:
            self.shutdown_pending = False
            self.timer_running = False
            self.time_label.configure(text="00:00:00")
            self.progress.configure(value=0)
            self.status_label.configure(
                text="Запланированное действие отменено", fg=self.MUTED
            )
        elif self.timer_running:
            self.timer_running = False
            self.time_label.configure(text="00:00:00")
            self.progress.configure(value=0)
            self.status_label.configure(text="Таймер отменён", fg=self.MUTED)
        self._reset_controls()
        return True

    def _reset_controls(self):
        self.entry.configure(state="normal")
        self.action_box.configure(state="readonly")
        self.delay_box.configure(state="readonly")
        self.start_button.configure(state="normal")
        self.cancel_button.configure(state="disabled", text="Остановить таймер")

    def minimize_to_tray(self):
        if pystray is None or Image is None:
            self.root.iconify()
            self.status_label.configure(
                text="Трей недоступен: установите зависимости из requirements.txt",
                fg="#ffbe62",
            )
            return
        if self.tray_icon is None:
            icon_path = Path(__file__).resolve().with_name("ico.ico")
            try:
                image = Image.open(icon_path)
            except OSError:
                image = Image.new("RGB", (64, 64), self.ACCENT)
            menu = pystray.Menu(
                pystray.MenuItem(
                    "Открыть таймер",
                    lambda icon, item: self.root.after(0, self.restore_from_tray),
                    default=True,
                ),
                pystray.MenuItem(
                    "Выход", lambda icon, item: self.root.after(0, self.exit_app)
                ),
            )
            self.tray_icon = pystray.Icon(
                "shutdown_timer", image, "Таймер выключения", menu
            )
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        self.root.withdraw()

    def restore_from_tray(self):
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()

    def exit_app(self):
        if self.timer_running or self.shutdown_pending:
            if not messagebox.askyesno(
                "Завершить таймер?",
                "Таймер остановится. Завершить приложение?",
                parent=self.root,
            ):
                return
            if not self.cancel_timer():
                return
        else:
            self._dismiss_warning()
        self._save_settings()
        if self.tray_icon is not None:
            self.tray_icon.stop()
        self.root.destroy()

    def close(self):
        self.exit_app()


class DarkDropdown(tk.Frame):
    """Small dark dropdown styled to match the app instead of the Windows theme."""

    BG = "#23343f"
    HOVER = "#344b58"
    BORDER = "#40535f"

    def __init__(self, parent, variable, values, foreground, accent):
        super().__init__(
            parent,
            bg=self.BG,
            highlightthickness=1,
            highlightbackground=self.BORDER,
            highlightcolor=accent,
        )
        self.variable = variable
        self.values = tuple(values)
        self.foreground = foreground
        self.enabled = True
        self.display = tk.Label(
            self,
            textvariable=variable,
            anchor="w",
            padx=9,
            pady=5,
            bg=self.BG,
            fg=foreground,
            font=("Segoe UI", 10),
            cursor="hand2",
        )
        self.display.pack(side="left", fill="both", expand=True)
        self.arrow = tk.Label(
            self,
            text="▾",
            width=3,
            bg=self.BG,
            fg="#b7c6cf",
            font=("Segoe UI", 10),
            cursor="hand2",
        )
        self.arrow.pack(side="right", fill="y")
        self.menu = tk.Menu(
            self,
            tearoff=False,
            bg=self.BG,
            fg=foreground,
            activebackground=self.HOVER,
            activeforeground=foreground,
            relief="flat",
            borderwidth=1,
            font=("Segoe UI", 10),
        )
        for value in self.values:
            self.menu.add_command(
                label=value, command=lambda choice=value: self.variable.set(choice)
            )
        for widget in (self, self.display, self.arrow):
            widget.bind("<Button-1>", self._open_menu)
            widget.bind("<Enter>", self._hover_on)
            widget.bind("<Leave>", self._hover_off)

    def _open_menu(self, _event=None):
        if self.enabled:
            self.menu.tk_popup(
                self.winfo_rootx(), self.winfo_rooty() + self.winfo_height()
            )
            self.menu.grab_release()

    def _hover_on(self, _event=None):
        if self.enabled:
            self.display.configure(bg=self.HOVER)
            self.arrow.configure(bg=self.HOVER, fg=self.foreground)

    def _hover_off(self, _event=None):
        self.display.configure(bg=self.BG)
        self.arrow.configure(bg=self.BG, fg="#b7c6cf")

    def configure(self, cnf=None, **kwargs):
        state = kwargs.pop("state", None)
        result = super().configure(cnf, **kwargs)
        if state is not None:
            self.enabled = state != "disabled"
            color = self.foreground if self.enabled else "#71818b"
            self.display.configure(
                fg=color, cursor="hand2" if self.enabled else "arrow"
            )
            self.arrow.configure(
                fg="#b7c6cf" if self.enabled else "#71818b",
                cursor="hand2" if self.enabled else "arrow",
            )
        return result

    config = configure


if __name__ == "__main__":
    root = tk.Tk()
    app = ShutdownTimerApp(root)
    root.mainloop()
