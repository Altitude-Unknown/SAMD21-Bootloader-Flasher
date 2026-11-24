#!/usr/bin/env python3
"""Altitude SAMD21 Bootloader Flasher.

    python3 bootloader_flasher.py              open the window
    python3 bootloader_flasher.py list|check|flash|read ...   command line (see --help)
    python3 bootloader_flasher.py --self-test  check a packaged build, then exit
"""

from __future__ import annotations

import os
import sys


def self_test() -> int:
    """Used by the release builds: everything loads, the bootloaders match their checksums, USB works."""
    from samd_flasher import APP_NAME, VERSION, hid
    from samd_flasher.gui import FlasherApp
    from samd_flasher.images import load_boards

    problems = []
    try:
        boards = load_boards()
        for board in boards:
            board.image()
    except Exception as exc:
        problems.append(f"bootloaders: {exc}")
    try:
        devices = hid.list_devices()
        note = f"{len(devices)} USB HID devices, {len(hid.find_probes())} programmers"
    except Exception as exc:
        problems.append(f"USB HID: {exc!r}")
        note = "USB HID failed"
    try:
        app = FlasherApp()
        app.update()
        app.destroy()
    except Exception as exc:
        problems.append(f"window: {exc!r}")
    lines = [f"{APP_NAME} {VERSION} self-test: {note}"] + [f"FAIL: {p}" for p in problems]
    lines.append("PASS" if not problems else "FAILED")
    print("\n".join(lines))
    log = os.environ.get("FLASHER_SELFTEST_LOG")  # a windowed Windows .exe has no console
    if log:
        with open(log, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return 1 if problems else 0


def main() -> int:
    args = sys.argv[1:]
    if args == ["--self-test"]:
        return self_test()
    if args:
        from samd_flasher.cli import main as cli_main
        return cli_main(args)
    from samd_flasher.gui import main as gui_main
    return gui_main()


if __name__ == "__main__":
    sys.exit(main())
