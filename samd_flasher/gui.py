"""The window: pick a board, check it, install its bootloader.

All USB work runs on one background thread at a time (the macOS HID code
needs a device to stay on the thread that opened it); messages come back to
the window through a queue.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import APP_NAME, VERSION, hid, jobs
from .images import Board, ImageError, load_boards, load_file, resource_dir

BG = "#f3f6f8"
PANEL = "#ffffff"
TEXT = "#17212b"
MUTED = "#60707d"
ACCENT = "#0f7f8f"
GOOD = "#15803d"
BAD = "#b91c1c"
OTHER_FILE = "Other file…"


class FlasherApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.configure(bg=BG)
        self.minsize(640, 600)
        self.boards: list[Board] = load_boards()
        self.events: queue.Queue = queue.Queue()
        self.busy = False
        self.custom_file: Path | None = None
        self.board_var = tk.StringVar(value=self.boards[0].name)
        self.protect_var = tk.BooleanVar(value=True)
        self.probe_var = tk.StringVar(value="Looking for a programmer…")
        self.board_info_var = tk.StringVar()
        self.check_var = tk.StringVar(value="Connect the board, then press Check Board to see what is on it.")
        self._icon = None
        self._style()
        self._build()
        self._set_icon()
        self._board_changed()
        self.refresh_probes()
        self.after(100, self._poll)

    # -- layout --------------------------------------------------------------------

    def _style(self):
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
        style.configure("Muted.TLabel", background=PANEL, foreground=MUTED)
        style.configure("Step.TLabel", background=PANEL, foreground=ACCENT, font=("TkDefaultFont", 13, "bold"))
        style.configure("Panel.TCheckbutton", background=PANEL, foreground=TEXT)
        style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff", padding=(14, 6))
        style.map("Accent.TButton", background=[("disabled", "#9bb8bd"), ("active", "#0c6a78")])
        style.configure("Horizontal.TProgressbar", background=ACCENT)

    def _panel(self, parent, step: str, title: str) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Panel.TFrame", padding=14)
        frame.pack(fill="x", pady=(0, 10))
        head = ttk.Frame(frame, style="Panel.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text=step, style="Step.TLabel").pack(side="left")
        ttk.Label(head, text=title, style="Panel.TLabel", font=("TkDefaultFont", 13, "bold")).pack(side="left",
                                                                                                     padx=(8, 0))
        return frame

    def _build(self):
        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)
        tk.Label(root, text="SAMD21 Bootloader Flasher", bg=BG, fg=TEXT,
                 font=("TkDefaultFont", 17, "bold")).pack(anchor="w")
        tk.Label(root, text="Installs the bootloader on a new board through an Atmel-ICE, so it can be "
                            "programmed over USB from then on.", bg=BG, fg=MUTED, wraplength=600,
                 justify="left").pack(anchor="w", pady=(2, 12))

        p1 = self._panel(root, "1", "Programmer")
        row = ttk.Frame(p1, style="Panel.TFrame")
        row.pack(fill="x", pady=(6, 0))
        self.probe_label = tk.Label(row, textvariable=self.probe_var, bg=PANEL, fg=MUTED, anchor="w",
                                    justify="left", wraplength=480)
        self.probe_label.pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Refresh", command=self.refresh_probes).pack(side="right")

        p2 = self._panel(root, "2", "Board")
        row = ttk.Frame(p2, style="Panel.TFrame")
        row.pack(fill="x", pady=(6, 0))
        self.board_combo = ttk.Combobox(row, textvariable=self.board_var, state="readonly", width=34,
                                        values=[b.name for b in self.boards] + [OTHER_FILE])
        self.board_combo.pack(side="left")
        self.board_combo.bind("<<ComboboxSelected>>", lambda _e: self._board_changed(pick_file=True))
        self.check_button = ttk.Button(row, text="Check Board", command=self.check)
        self.check_button.pack(side="right")
        ttk.Label(p2, textvariable=self.board_info_var, style="Muted.TLabel", wraplength=600,
                  justify="left").pack(anchor="w", pady=(6, 0))
        self.check_label = tk.Label(p2, textvariable=self.check_var, bg=PANEL, fg=TEXT, wraplength=600,
                                    justify="left", anchor="w")
        self.check_label.pack(fill="x", pady=(6, 0))

        p3 = self._panel(root, "3", "Install")
        ttk.Checkbutton(p3, text="Protect the bootloader so a program can't overwrite it (recommended)",
                        variable=self.protect_var, style="Panel.TCheckbutton").pack(anchor="w", pady=(6, 0))
        row = ttk.Frame(p3, style="Panel.TFrame")
        row.pack(fill="x", pady=(10, 0))
        self.progress = ttk.Progressbar(row, maximum=1.0)
        self.progress.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self.flash_button = ttk.Button(row, text="Install Bootloader", style="Accent.TButton", command=self.flash)
        self.flash_button.pack(side="right")

        logs = ttk.Frame(root)
        logs.pack(fill="both", expand=True)
        head = ttk.Frame(logs)
        head.pack(fill="x")
        tk.Label(head, text="Details", bg=BG, fg=MUTED).pack(side="left")
        ttk.Button(head, text="Save Details…", command=self.save_log).pack(side="right")
        self.log_text = tk.Text(logs, height=8, wrap="word", state="disabled", relief="flat", bg=PANEL, fg=TEXT,
                                highlightthickness=1, highlightbackground="#dde3e8", padx=8, pady=6)
        self.log_text.pack(fill="both", expand=True, pady=(4, 0))
        tk.Label(root, text=f"Version {VERSION}", bg=BG, fg=MUTED).pack(anchor="e", pady=(6, 0))

    def _set_icon(self):
        path = resource_dir() / "assets" / "icons" / "app_icon.png"
        if path.is_file():
            try:
                self._icon = tk.PhotoImage(file=str(path))
                self.iconphoto(True, self._icon)
            except tk.TclError:
                pass

    # -- board choice -----------------------------------------------------------------

    def selected_board(self) -> Board | None:
        return next((b for b in self.boards if b.name == self.board_var.get()), None)

    def _board_changed(self, pick_file: bool = False):
        board = self.selected_board()
        if board:
            self.custom_file = None
            self.board_info_var.set(f"{board.version}. After installing, double-tap the board's reset button "
                                    f"and a USB drive named {board.drive} appears.")
            return
        if pick_file:
            path = filedialog.askopenfilename(title="Choose a bootloader file",
                                              filetypes=[("Bootloader files", "*.bin *.hex"), ("All files", "*.*")])
            if not path:
                self.board_var.set(self.boards[0].name)
                self._board_changed()
                return
            self.custom_file = Path(path)
        name = self.custom_file.name if self.custom_file else "no file chosen"
        self.board_info_var.set(f"File: {name}. Only use files you trust: the wrong bootloader can stop "
                                "the board from working over USB.")

    def image(self) -> tuple[bytes, str]:
        board = self.selected_board()
        if board:
            return board.image(), f"the {board.name} bootloader"
        if not self.custom_file:
            raise ImageError("Choose a file first.")
        return load_file(self.custom_file), self.custom_file.name

    # -- programmer ---------------------------------------------------------------------

    def refresh_probes(self):
        if self.busy:
            return
        try:
            probes = hid.find_probes()
        except hid.HidError as exc:
            self.probe_var.set(str(exc))
            self.probe_label.configure(fg=BAD)
            return
        if probes:
            extra = f" (and {len(probes) - 1} more; the first is used)" if len(probes) > 1 else ""
            self.probe_var.set(f"{probes[0].name} is connected.{extra}")
            self.probe_label.configure(fg=GOOD)
        else:
            self.probe_var.set("No programmer found. Plug the Atmel-ICE into this computer, then press Refresh.")
            self.probe_label.configure(fg=BAD)

    # -- jobs --------------------------------------------------------------------------

    def _start(self, work, title: str):
        self.busy = True
        for button in (self.flash_button, self.check_button):
            button.configure(state="disabled")
        self.progress.configure(value=0)
        self._log_clear()
        self._log(title)

        def run():
            log = lambda text: self.events.put(("log", text))
            progress = lambda value: self.events.put(("progress", value))
            try:
                self.events.put(("done", work(log, progress)))
            except jobs.NeedsChipErase as exc:
                self.events.put(("erase?", str(exc)))
            except (jobs.FlashError, ImageError, hid.HidError, OSError) as exc:
                self.events.put(("error", str(exc)))
            except Exception as exc:  # an unexpected bug: show it rather than leave the window stuck
                self.events.put(("error", f"Unexpected problem: {exc!r}"))

        threading.Thread(target=run, daemon=True).start()

    def check(self):
        self.check_var.set("Checking…")
        self.check_label.configure(fg=MUTED)
        self._start(lambda log, _p: ("check", jobs.check_board(self.boards, log=log)), "Checking the board…")

    def flash(self, allow_chip_erase: bool = False):
        try:
            image, label = self.image()
        except (ImageError, OSError) as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        if not allow_chip_erase and not messagebox.askyesno(
                APP_NAME, f"Install {label} on the connected board?\n\nThis replaces the bootloader on the board. "
                          "Check that the Atmel-ICE is plugged into the right board."):
            return
        protect = self.protect_var.get()
        self._start(lambda log, progress: ("flash", jobs.flash_bootloader(
            image, protect=protect, allow_chip_erase=allow_chip_erase, log=log, progress=progress)),
            f"Installing {label}…")

    def _poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self._log(value)
                elif kind == "progress":
                    self.progress.configure(value=value)
                else:
                    self._finish(kind, value)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _finish(self, kind, value):
        self.busy = False
        for button in (self.flash_button, self.check_button):
            button.configure(state="normal")
        if kind == "done" and value[0] == "check":
            self.check_var.set(value[1].summary())
            self.check_label.configure(fg=TEXT)
        elif kind == "done":
            board = self.selected_board()
            hint = (f"\n\nTo check it, double-tap the board's reset button: a USB drive named {board.drive} "
                    "should appear." if board else "")
            messagebox.showinfo(APP_NAME, "The bootloader is installed and verified." + hint)
        elif kind == "erase?":
            self._log(value)
            if messagebox.askyesno(APP_NAME, value + "\n\nErase the whole chip and install the bootloader?",
                                   icon="warning"):
                self.flash(allow_chip_erase=True)
        else:
            self._log("Error: " + value)
            if self.check_var.get() == "Checking…":
                self.check_var.set("Could not check the board.")
                self.check_label.configure(fg=BAD)
            messagebox.showerror(APP_NAME, value)
        self.refresh_probes()

    # -- details log --------------------------------------------------------------------

    def _log(self, text: str):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _log_clear(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def save_log(self):
        path = filedialog.asksaveasfilename(title="Save details", defaultextension=".txt",
                                            initialfile="bootloader-flasher-details.txt")
        if path:
            Path(path).write_text(self.log_text.get("1.0", "end"), encoding="utf-8")


def main() -> int:
    app = FlasherApp()
    app.mainloop()
    return 0
