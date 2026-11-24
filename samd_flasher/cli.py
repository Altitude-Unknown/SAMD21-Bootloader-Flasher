"""Command line: the same jobs as the window, for scripts, labs, and hardware testing.

    bootloader_flasher.py list
    bootloader_flasher.py check
    bootloader_flasher.py flash rc_tx            (a board from the list)
    bootloader_flasher.py flash --file my.bin    (any .bin or .hex)
    bootloader_flasher.py read out.bin           (save the first 8 KB of the chip)
"""

from __future__ import annotations

import argparse
import sys

from . import APP_NAME, VERSION, hid, jobs
from .images import ImageError, load_boards, load_file


def _progress(fraction: float) -> None:
    sys.stdout.write(f"\r  {int(fraction * 100):3d}%")
    sys.stdout.flush()
    if fraction >= 1.0:
        sys.stdout.write("\n")


def _log(text: str) -> None:
    sys.stdout.write("\r" + text + "\n")
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bootloader_flasher", description=f"{APP_NAME} {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list programmers and built-in boards")
    sub.add_parser("check", help="identify the connected chip and its bootloader")
    flash = sub.add_parser("flash", help="install a bootloader")
    flash.add_argument("board", nargs="?", help="board id from 'list'")
    flash.add_argument("--file", help="a .bin or .hex file instead of a built-in board")
    flash.add_argument("--no-protect", action="store_true", help="leave bootloader protection (BOOTPROT) off")
    flash.add_argument("--erase-locked-chip", action="store_true",
                       help="if the chip's security bit is set, erase the whole chip first")
    flash.add_argument("--yes", action="store_true", help="don't ask before flashing")
    read = sub.add_parser("read", help="save the start of the chip's flash to a file")
    read.add_argument("output")
    read.add_argument("--size", type=int, default=jobs.BOOTLOADER_SIZE)
    args = parser.parse_args(argv)
    boards = load_boards()

    try:
        if args.command == "list":
            probes = hid.find_probes()
            print("Programmers:" if probes else "Programmers: none found (plug in the Atmel-ICE)")
            for p in probes:
                print(f"  {p.name}")
            print("Boards:")
            for b in boards:
                print(f"  {b.id:12s} {b.name} ({b.version}, drive {b.drive})")
            return 0
        if args.command == "check":
            jobs.check_board(boards, log=_log)
            return 0
        if args.command == "read":
            with jobs.session(log=_log) as chip:
                if chip.info.protected:
                    raise jobs.FlashError("The chip's security bit is set, so its flash can't be read.")
                chip.halt()
                data = chip.read_flash(0, args.size)
                chip.reset_and_run()
            with open(args.output, "wb") as f:
                f.write(data)
            print(f"Saved {len(data)} bytes to {args.output}.")
            return 0
        # flash
        if args.file:
            image, label = load_file(args.file), args.file
        else:
            board = next((b for b in boards if b.id == args.board), None)
            if board is None:
                parser.error("choose a board id (see 'list') or --file")
            image, label = board.image(), f"the {board.name} bootloader"
        if not args.yes:
            answer = input(f"Flash {label} ({len(image)} bytes) to the connected board? [y/N] ")
            if answer.strip().lower() not in ("y", "yes"):
                print("Cancelled.")
                return 1
        jobs.flash_bootloader(image, protect=not args.no_protect, allow_chip_erase=args.erase_locked_chip,
                              log=_log, progress=_progress)
        return 0
    except (jobs.FlashError, ImageError, hid.HidError, OSError) as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1
