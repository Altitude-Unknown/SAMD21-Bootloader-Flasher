"""What the app does, in steps a person can follow: find the programmer, check a board, flash it.

Every step reports through `log(text)` and `progress(fraction)`, so the window
and the command line show the same messages.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

from . import dap as d
from . import hid
from .images import Board, identify
from .samd21 import BOOTPROT_SIZES, ChipError, ChipInfo, Samd21, bootprot_for, connect_under_reset
from .swd import Swd

BOOTLOADER_SIZE = 8192  # how much of the chip "Check Board" reads to recognize a bootloader


class FlashError(Exception):
    """A problem explained in plain English, ready to show."""


class NeedsChipErase(FlashError):
    pass


def _quiet(*_args):
    pass


def size_text(size: int) -> str:
    return f"{size // 1024} KB" if size >= 1024 and size % 1024 == 0 else f"{size} bytes"


@contextmanager
def session(probe: hid.HidInfo | None = None, log=_quiet, clock_hz: int = 1_000_000):
    """Open the programmer, connect to the SAMD21 and identify it. Closes everything afterwards."""
    if probe is None:
        probes = hid.find_probes()
        if not probes:
            raise FlashError("No programmer found. Plug the Atmel-ICE into this computer with its USB cable.")
        probe = probes[0]
    device = hid.open_device(probe)
    dap = d.CmsisDap(device)
    try:
        dap.setup()
        log(f"Programmer: {probe.name}, firmware {dap.info_string(d.INFO_FIRMWARE) or 'unknown'}.")
        dap.host_status(True)
        swd = Swd(dap, clock_hz)
        try:
            swd.connect()
        except d.DapError:
            log("The chip did not answer. Trying again while holding it in reset...")
            try:
                connect_under_reset(swd)
            except d.DapError:
                raise FlashError("The programmer cannot reach the chip. Check that the board is powered, the "
                                 "SWD cable is on the right header the right way round, and RESET is wired.") from None
        chip = Samd21(swd)
        try:
            info = chip.identify()
        except d.TransferError:
            raise FlashError("The chip answered but its ID could not be read. Check the wiring.") from None
        except ChipError as exc:
            raise FlashError(str(exc)) from None
        log(f"Chip: {info.name}, revision {info.revision}" +
            (", security bit set (locked)." if info.protected else f", {size_text(info.flash_size)} flash."))
        if not info.protected:
            chip.release_reset_extension()
        yield chip
    except (d.DapError, ChipError, hid.HidError) as exc:
        raise FlashError(str(exc)) from None
    finally:
        try:
            dap.host_status(False)
            dap.disconnect()
        except (d.DapError, hid.HidError):
            pass
        device.close()


@dataclass
class BoardReport:
    chip: ChipInfo
    protected_size: int | None  # bootloader protection in bytes; None if unknown (chip locked)
    installed: str  # what is in the bootloader area, in words

    def summary(self) -> str:
        if self.chip.protected:
            return (f"{self.chip.name}: the security bit is set, so its contents can't be read. "
                    "Flashing will erase the whole chip first.")
        protection = (f"protected ({size_text(self.protected_size)})" if self.protected_size
                      else "not protected")
        return f"{self.chip.name}, rev {self.chip.revision}. Bootloader area: {self.installed}; {protection}."


def check_board(boards: list[Board], probe=None, log=_quiet) -> BoardReport:
    with session(probe, log) as chip:
        info = chip.info
        if info.protected:
            report = BoardReport(info, None, "unknown (chip locked)")
        else:
            chip.halt()
            contents = chip.read_flash(0, BOOTLOADER_SIZE)
            match = identify(contents, boards)
            if match:
                installed = f"{match.name} bootloader ({match.version})"
            elif contents == b"\xff" * len(contents):
                installed = "empty"
            else:
                installed = "an unknown bootloader or program"
            report = BoardReport(info, BOOTPROT_SIZES[chip.bootprot()], installed)
            chip.reset_and_run()
        log(report.summary())
        return report


def flash_bootloader(image: bytes, protect: bool = True, allow_chip_erase: bool = False, probe=None,
                     log=_quiet, progress=_quiet) -> None:
    """Write `image` at address 0, verify it, optionally protect it, and restart the board."""
    with session(probe, log) as chip:
        if chip.info.protected:
            if not allow_chip_erase:
                raise NeedsChipErase("This chip's security bit is set. It can only be flashed after erasing the "
                                     "whole chip, which also deletes the program on it.")
            log("Erasing the whole chip to clear the security bit...")
            chip.chip_erase()
            chip.swd.power_up()
            chip.identify()
        info = chip.info
        if len(image) > info.flash_size:
            raise FlashError(f"The file ({size_text(len(image))}) is bigger than the chip's flash.")
        chip.reset_and_halt()
        progress(0.02)

        current = BOOTPROT_SIZES[chip.bootprot()]
        if current:
            log(f"Turning off bootloader protection ({size_text(current)}) so the bootloader can be replaced...")
            chip.write_bootprot(7)
            chip.reset_and_halt()
        progress(0.05)

        log(f"Erasing and writing {size_text(len(image))}...")
        chip.write_flash(0, image, lambda done, total: progress(0.05 + 0.75 * done / total))

        log("Verifying...")
        written = chip.read_flash(0, len(image))
        if written != image:
            address = next(i for i, (a, b) in enumerate(zip(written, image)) if a != b)
            raise FlashError(f"Verify failed: the byte at 0x{address:05X} reads 0x{written[address]:02X}, "
                             f"expected 0x{image[address]:02X}. Try flashing again; if it keeps failing, "
                             "check the board's power.")
        progress(0.95)

        if protect:
            value = bootprot_for(len(image))
            if value is None:
                log("The image is too big to protect (more than 32 KB); leaving protection off.")
            else:
                log(f"Protecting the first {size_text(BOOTPROT_SIZES[value])} (the bootloader)...")
                chip.write_bootprot(value)
        log("Restarting the board...")
        chip.reset_and_run()
        progress(1.0)
        log("Done. The bootloader is installed and verified.")
