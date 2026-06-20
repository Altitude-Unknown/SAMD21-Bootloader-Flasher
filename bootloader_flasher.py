#!/usr/bin/env python3
"""Small GUI for flashing SAMD21 bootloaders with an Atmel-ICE programmer."""

from __future__ import annotations

import os
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


APP_NAME = "Altitude SAMD21 Bootloader Flasher"


@dataclass(frozen=True)
class BoardProfile:
    label: str
    asset_path: str
    description: str


BOARD_PROFILES = {
    "RC Airplane Transmitter": BoardProfile(
        label="RC Airplane Transmitter",
        asset_path="assets/bootloaders/rc_tx/bootloader-altitude_rc_tx_m0-v4.0.0.bin",
        description="ATSAMD21G18A, external 32.768 kHz crystal, D13 boot LED",
    ),
    "RC Airplane Receiver": BoardProfile(
        label="RC Airplane Receiver",
        asset_path="assets/bootloaders/rc_rx/bootloader-altitude_rc_rx_m0-v4.0.0.bin",
        description="ATSAMD21G18A, external 32.768 kHz crystal, D13 boot LED",
    ),
    "YELLOWSTONE": BoardProfile(
        label="YELLOWSTONE",
        asset_path="assets/bootloaders/yellowstone/bootloader-altitude_yellowstone_m0-v4.0.0.bin",
        description="ATSAMD21G18A, external 32.768 kHz crystal, D13 boot LED",
    ),
    "BOREALIS": BoardProfile(
        label="BOREALIS",
        asset_path="assets/bootloaders/borealis/bootloader-altitude_borealis_m0-v4.0.0.bin",
        description="ATSAMD21G18A, external 32.768 kHz crystal, D13 boot LED",
    ),
}


INTERFACE_CONFIGS = {
    "Atmel-ICE CMSIS-DAP": "interface/cmsis-dap.cfg",
}

TARGET_CONFIGS = {
    "SAMD21/SAMD11/SAMD51 auto": "target/at91samdXX.cfg",
}


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def bundled_asset(relative_path: str) -> Path:
    return app_root() / relative_path


def find_openocd() -> str | None:
    env_path = os.environ.get("OPENOCD_PATH")
    if env_path and Path(env_path).is_file():
        return env_path

    candidates = [
        app_root() / "tools" / "openocd" / "bin" / ("openocd.exe" if sys.platform == "win32" else "openocd"),
        Path("/opt/homebrew/bin/openocd"),
        Path("/usr/local/bin/openocd"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    return shutil.which("openocd")


def build_openocd_command(
    openocd_path: str,
    interface_cfg: str,
    target_cfg: str,
    bootloader_file: Path,
    verify: bool,
    reset_after: bool,
    protect_bootloader: bool,
) -> list[str]:
    flash_command = f"program {{{bootloader_file}}} 0x00000000"
    if verify:
        flash_command += " verify"
    if reset_after:
        flash_command += " reset"

    commands = [
        "init",
        "reset halt",
        "at91samd bootloader 0",
        flash_command,
    ]
    if protect_bootloader:
        commands.append("at91samd bootloader 8192")
    if reset_after:
        commands.append("reset run")
    commands.append("shutdown")

    cmd = [
        openocd_path,
        "-f",
        interface_cfg,
        "-f",
        target_cfg,
    ]
    for command in commands:
        cmd.extend(["-c", command])
    return cmd


class BootloaderFlasherApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("900x620")
        self.minsize(760, 520)

        self.log_queue: queue.Queue[str | tuple[str, int]] = queue.Queue()
        self.process: subprocess.Popen[str] | None = None

        self.board_var = tk.StringVar(value=next(iter(BOARD_PROFILES)))
        self.bootloader_var = tk.StringVar()
        self.openocd_var = tk.StringVar(value=find_openocd() or "")
        self.interface_var = tk.StringVar(value="Atmel-ICE CMSIS-DAP")
        self.target_var = tk.StringVar(value="SAMD21/SAMD11/SAMD51 auto")
        self.verify_var = tk.BooleanVar(value=True)
        self.reset_var = tk.BooleanVar(value=True)
        self.protect_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Choose a board and connect Atmel-ICE over SWD.")

        self._build_ui()
        self._use_board_bootloader()
        self.after(100, self._poll_log_queue)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(9, weight=1)

        ttk.Label(root, text="Board").grid(row=0, column=0, sticky="w", pady=5)
        board_combo = ttk.Combobox(root, textvariable=self.board_var, values=list(BOARD_PROFILES), state="readonly")
        board_combo.grid(row=0, column=1, sticky="ew", padx=(12, 8), pady=5)
        board_combo.bind("<<ComboboxSelected>>", lambda _event: self._use_board_bootloader())
        ttk.Button(root, text="Use Built-In", command=self._use_board_bootloader).grid(row=0, column=2, sticky="e", pady=5)

        ttk.Label(root, text="Bootloader File").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(root, textvariable=self.bootloader_var).grid(row=1, column=1, sticky="ew", padx=(12, 8), pady=5)
        ttk.Button(root, text="Browse", command=self._browse_bootloader).grid(row=1, column=2, sticky="e", pady=5)

        ttk.Label(root, text="OpenOCD").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Entry(root, textvariable=self.openocd_var).grid(row=2, column=1, sticky="ew", padx=(12, 8), pady=5)
        ttk.Button(root, text="Find", command=self._browse_openocd).grid(row=2, column=2, sticky="e", pady=5)

        ttk.Label(root, text="Programmer").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Combobox(root, textvariable=self.interface_var, values=list(INTERFACE_CONFIGS), state="readonly").grid(
            row=3, column=1, sticky="ew", padx=(12, 8), pady=5
        )

        ttk.Label(root, text="Target").grid(row=4, column=0, sticky="w", pady=5)
        ttk.Combobox(root, textvariable=self.target_var, values=list(TARGET_CONFIGS), state="readonly").grid(
            row=4, column=1, sticky="ew", padx=(12, 8), pady=5
        )

        options = ttk.Frame(root)
        options.grid(row=5, column=1, columnspan=2, sticky="w", padx=(12, 0), pady=(8, 2))
        ttk.Checkbutton(options, text="Verify", variable=self.verify_var).pack(side="left", padx=(0, 18))
        ttk.Checkbutton(options, text="Reset after flashing", variable=self.reset_var).pack(side="left", padx=(0, 18))
        ttk.Checkbutton(options, text="Protect 8 KB bootloader", variable=self.protect_var).pack(side="left")

        buttons = ttk.Frame(root)
        buttons.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(14, 6))
        ttk.Button(buttons, text="Show Command", command=self._show_command).pack(side="left")
        self.flash_button = ttk.Button(buttons, text="Flash Bootloader", command=self._flash)
        self.flash_button.pack(side="right")

        ttk.Label(root, textvariable=self.status_var).grid(row=7, column=0, columnspan=3, sticky="w", pady=(8, 6))

        self.log_text = tk.Text(root, height=18, wrap="word", state="disabled")
        self.log_text.grid(row=9, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        scrollbar = ttk.Scrollbar(root, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=9, column=3, sticky="ns", pady=(8, 0))
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _use_board_bootloader(self) -> None:
        profile = BOARD_PROFILES[self.board_var.get()]
        path = bundled_asset(profile.asset_path)
        self.bootloader_var.set(str(path))
        self.status_var.set(profile.description)

    def _browse_bootloader(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose bootloader file",
            filetypes=[("Bootloader files", "*.bin *.hex"), ("All files", "*.*")],
        )
        if path:
            self.bootloader_var.set(path)

    def _browse_openocd(self) -> None:
        path = filedialog.askopenfilename(title="Choose openocd executable")
        if path:
            self.openocd_var.set(path)

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _command_or_error(self) -> list[str] | None:
        openocd_path = self.openocd_var.get().strip()
        bootloader_text = self.bootloader_var.get().strip()

        if not openocd_path:
            messagebox.showerror(
                "OpenOCD not found",
                "OpenOCD is not installed or was not found. Install OpenOCD, or use Find to select the openocd executable.",
            )
            return None
        if not Path(openocd_path).is_file() and not shutil.which(openocd_path):
            messagebox.showerror("OpenOCD not found", f"OpenOCD executable not found:\n{openocd_path}")
            return None
        if not bootloader_text:
            messagebox.showerror("Missing bootloader", "Choose a bootloader .bin or .hex file.")
            return None

        bootloader_file = Path(bootloader_text)
        if not bootloader_file.is_file():
            messagebox.showerror("Missing bootloader", f"Bootloader file not found:\n{bootloader_file}")
            return None

        return build_openocd_command(
            openocd_path=openocd_path,
            interface_cfg=INTERFACE_CONFIGS[self.interface_var.get()],
            target_cfg=TARGET_CONFIGS[self.target_var.get()],
            bootloader_file=bootloader_file,
            verify=self.verify_var.get(),
            reset_after=self.reset_var.get(),
            protect_bootloader=self.protect_var.get(),
        )

    def _show_command(self) -> None:
        cmd = self._command_or_error()
        if not cmd:
            return
        self._clear_log()
        self._append_log("OpenOCD command:\n\n")
        self._append_log(" ".join(f'"{part}"' if " " in part else part for part in cmd))
        self._append_log("\n")

    def _flash(self) -> None:
        if self.process is not None:
            messagebox.showinfo("Flash in progress", "A flashing operation is already running.")
            return

        cmd = self._command_or_error()
        if not cmd:
            return

        if not messagebox.askyesno(
            "Flash bootloader",
            "This will erase/program the bootloader area through SWD. Make sure the correct board is connected to Atmel-ICE.\n\nContinue?",
        ):
            return

        self._clear_log()
        self.status_var.set("Flashing bootloader...")
        self.flash_button.configure(state="disabled")
        worker = threading.Thread(target=self._flash_worker, args=(cmd,), daemon=True)
        worker.start()

    def _flash_worker(self, cmd: list[str]) -> None:
        try:
            self.log_queue.put("Running:\n" + " ".join(f'"{part}"' if " " in part else part for part in cmd) + "\n\n")
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            assert self.process.stdout is not None
            for line in self.process.stdout:
                self.log_queue.put(line)
            return_code = self.process.wait()
            self.log_queue.put(("done", return_code))
        except Exception as exc:
            self.log_queue.put(f"\nERROR: {exc}\n")
            self.log_queue.put(("done", 1))
        finally:
            self.process = None

    def _poll_log_queue(self) -> None:
        try:
            while True:
                item = self.log_queue.get_nowait()
                if isinstance(item, tuple) and item[0] == "done":
                    return_code = item[1]
                    if return_code == 0:
                        self.status_var.set("Flash complete.")
                        self._append_log("\nFlash complete.\n")
                    else:
                        self.status_var.set(f"Flash failed with exit code {return_code}.")
                        self._append_log(f"\nFlash failed with exit code {return_code}.\n")
                    self.flash_button.configure(state="normal")
                else:
                    self._append_log(str(item))
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)


if __name__ == "__main__":
    app = BootloaderFlasherApp()
    app.mainloop()
