"""SAMD21 operations over SWD: identify the chip, halt it, and program its flash.

Register addresses and bit positions come from Microchip's SAMD21 device
headers (CMSIS-Atmel, samd21/include: component/nvmctrl.h, component/dsu.h,
instance/nvmctrl.h) and the Armv6-M Architecture Reference Manual (debug
registers DHCSR, DEMCR, AIRCR).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from . import dap as d
from .swd import Swd

# Cortex-M0+ debug registers (Armv6-M)
DHCSR = 0xE000EDF0
DEMCR = 0xE000EDFC
AIRCR = 0xE000ED0C
DBGKEY = 0xA05F0000
C_DEBUGEN = 1 << 0
C_HALT = 1 << 1
S_HALT = 1 << 17
VC_CORERESET = 1 << 0
AIRCR_RESET = 0x05FA0004  # VECTKEY | SYSRESETREQ

# Device Service Unit
DSU = 0x41002000
DSU_CTRL = DSU + 0x00  # 8-bit, write only
DSU_STATUSA = DSU + 0x01  # 8-bit
DSU_STATUSB = DSU + 0x02  # 8-bit, read only
DSU_DID = DSU + 0x18
DSU_CTRL_CE = 1 << 4
STATUSA_DONE = 1 << 0
STATUSA_CRSTEXT = 1 << 1
STATUSA_FAIL = 1 << 3
STATUSB_PROT = 1 << 0

# NVM controller
NVMCTRL = 0x41004000
NVM_CTRLA = NVMCTRL + 0x00  # 16-bit
NVM_CTRLB = NVMCTRL + 0x04
NVM_PARAM = NVMCTRL + 0x08
NVM_INTFLAG = NVMCTRL + 0x14  # 8-bit
NVM_STATUS = NVMCTRL + 0x18  # 16-bit
NVM_ADDR = NVMCTRL + 0x1C
NVM_LOCK = NVMCTRL + 0x20  # 16-bit
CMDEX_KEY = 0xA5 << 8
CMD_ER, CMD_WP, CMD_EAR, CMD_WAP, CMD_UR, CMD_PBC = 0x02, 0x04, 0x05, 0x06, 0x41, 0x44
CTRLB_MANW = 1 << 7
INTFLAG_READY = 1 << 0
INTFLAG_ERROR = 1 << 1
STATUS_PROGE = 1 << 2
STATUS_LOCKE = 1 << 3
STATUS_NVME = 1 << 4
STATUS_ERRORS = STATUS_PROGE | STATUS_LOCKE | STATUS_NVME

USER_ROW = 0x00804000  # NVMCTRL_USER: BOOTPROT in bits 2:0, region locks in bits 63:48
PAGES_PER_ROW = 4
# BOOTPROT fuse value -> protected bootloader size in bytes (SAMD21 datasheet, "Boot Loader Size")
BOOTPROT_SIZES = {7: 0, 6: 512, 5: 1024, 4: 2048, 3: 4096, 2: 8192, 1: 16384, 0: 32768}

SAMD21_SERIES = 0x01
SAMD21_DEVICES = {  # DSU.DID.DEVSEL -> part name
    0x00: "SAMD21J18A", 0x01: "SAMD21J17A", 0x02: "SAMD21J16A", 0x03: "SAMD21J15A",
    0x05: "SAMD21G18A", 0x06: "SAMD21G17A", 0x07: "SAMD21G16A", 0x08: "SAMD21G15A",
    0x0A: "SAMD21E18A", 0x0B: "SAMD21E17A", 0x0C: "SAMD21E16A", 0x0D: "SAMD21E15A",
}


class ChipError(Exception):
    pass


@dataclass
class ChipInfo:
    did: int
    name: str
    revision: str
    flash_size: int
    page_size: int
    protected: bool

    @property
    def row_size(self) -> int:
        return self.page_size * PAGES_PER_ROW

    @property
    def region_size(self) -> int:
        return self.flash_size // 16  # the NVM has 16 lock regions


def bootprot_for(size: int) -> int | None:
    """Smallest BOOTPROT setting that protects `size` bytes, or None if it is too big."""
    for value, protected in sorted(BOOTPROT_SIZES.items(), key=lambda kv: kv[1]):
        if protected >= size:
            return value
    return None


class Samd21:
    def __init__(self, swd: Swd):
        self.swd = swd
        self.info: ChipInfo | None = None

    # -- identify -----------------------------------------------------------------

    def identify(self) -> ChipInfo:
        did = self.swd.read32(DSU_DID)
        processor, family = did >> 28, (did >> 23) & 0x1F
        series, devsel, revision = (did >> 16) & 0x3F, did & 0xFF, (did >> 8) & 0xF
        if processor != 1 or family != 0:
            raise ChipError(f"This is not a SAMD chip (device ID 0x{did:08X}).")
        if series != SAMD21_SERIES:
            raise ChipError(f"This is a SAM D/R chip, but not a SAMD21 (device ID 0x{did:08X}).")
        protected = bool(self.swd.read8(DSU_STATUSB) & STATUSB_PROT)
        page_size, flash_size = 64, 0
        if not protected:
            param = self.swd.read32(NVM_PARAM)
            page_size = 8 << ((param >> 16) & 0x7)
            flash_size = (param & 0xFFFF) * page_size
        name = SAMD21_DEVICES.get(devsel, f"SAMD21 (device 0x{devsel:02X})")
        self.info = ChipInfo(did, name, chr(ord("A") + revision), flash_size, page_size, protected)
        return self.info

    # -- run control ----------------------------------------------------------------

    def halt(self) -> None:
        self.swd.write32(DHCSR, DBGKEY | C_DEBUGEN | C_HALT)
        self._wait(lambda: self.swd.read32(DHCSR) & S_HALT, "halt the processor")

    def reset_and_halt(self) -> None:
        """Reset the chip and stop it at its first instruction, before any code runs."""
        self.swd.write32(DHCSR, DBGKEY | C_DEBUGEN)
        self.swd.write32(DEMCR, VC_CORERESET)
        self.swd.write32_ignore_ack(AIRCR, AIRCR_RESET)
        self._wait(lambda: self.swd.read32(DHCSR) & S_HALT, "stop the processor after reset")
        self.swd.write32(DEMCR, 0)
        self.release_reset_extension()

    def release_reset_extension(self) -> None:
        """After connecting under reset, the DSU holds the CPU in reset until this flag is cleared."""
        if self.swd.read8(DSU_STATUSA) & STATUSA_CRSTEXT:
            self.swd.write32(DHCSR, DBGKEY | C_DEBUGEN | C_HALT)
            self.swd.write32(DEMCR, VC_CORERESET)  # stop at the first instruction once the reset ends
            self.swd.write8(DSU_STATUSA, STATUSA_CRSTEXT)  # write 1 to clear
            self._wait(lambda: self.swd.read32(DHCSR) & S_HALT, "stop the processor")
            self.swd.write32(DEMCR, 0)

    def reset_and_run(self) -> None:
        self.swd.write32(DEMCR, 0)
        self.swd.write32(DHCSR, DBGKEY)  # debug off, so the processor runs freely
        self.swd.write32_ignore_ack(AIRCR, AIRCR_RESET)

    def _wait(self, condition, what: str, timeout: float = 1.0) -> None:
        deadline = time.monotonic() + timeout
        while not condition():
            if time.monotonic() > deadline:
                raise ChipError(f"Timed out waiting for the chip to {what}.")

    # -- NVM controller ---------------------------------------------------------------

    def _nvm_ready(self) -> None:
        self._wait(lambda: self.swd.read8(NVM_INTFLAG) & INTFLAG_READY, "finish a flash operation", 2.0)

    def nvm_command(self, command: int, address: int | None = None) -> None:
        self._nvm_ready()
        if address is not None:
            self.swd.write32(NVM_ADDR, address >> 1)  # ADDR takes the 16-bit word address
        self.swd.write16(NVM_CTRLA, CMDEX_KEY | command)
        self._nvm_ready()
        status = self.swd.read16(NVM_STATUS)
        if status & STATUS_ERRORS:
            self.swd.write16(NVM_STATUS, status & STATUS_ERRORS)  # write 1 to clear
            self.swd.write8(NVM_INTFLAG, INTFLAG_ERROR)
            if status & STATUS_LOCKE:
                raise ChipError(f"The flash at 0x{(address or 0):05X} is locked.")
            raise ChipError(f"The flash controller reported an error (status 0x{status:04X}).")

    def set_manual_write(self) -> None:
        ctrlb = self.swd.read32(NVM_CTRLB)
        if not ctrlb & CTRLB_MANW:
            self.swd.write32(NVM_CTRLB, ctrlb | CTRLB_MANW)

    def _write_page(self, address: int, page: bytes, command: int) -> None:
        self.nvm_command(CMD_PBC)
        words = [int.from_bytes(page[i:i + 4], "little") for i in range(0, len(page), 4)]
        self.swd.write_words(address, words)  # writes to flash addresses fill the page buffer
        self.nvm_command(command, address)

    # -- user row: BOOTPROT and lock fuses ----------------------------------------------------

    def read_user_row(self) -> bytes:
        return self.swd.read_bytes(USER_ROW, self.info.page_size)

    def bootprot(self) -> int:
        return self.read_user_row()[0] & 0x7

    def write_bootprot(self, value: int) -> None:
        """Change BOOTPROT, keeping every other bit of the user row. Takes effect at the next reset."""
        page = bytearray(self.read_user_row())
        if page[0] & 0x7 == value:
            return
        page[0] = (page[0] & ~0x7) | value
        self.set_manual_write()
        self.nvm_command(CMD_EAR, USER_ROW)
        self._write_page(USER_ROW, bytes(page), CMD_WAP)
        if self.read_user_row() != bytes(page):
            raise ChipError("The fuse settings did not read back as written.")

    def unlock_region(self, address: int) -> None:
        region = address // self.info.region_size
        if not self.swd.read16(NVM_LOCK) & (1 << region):  # LOCK bit 0 means locked
            self.nvm_command(CMD_UR, address)

    # -- flash -----------------------------------------------------------------------

    def read_flash(self, address: int, length: int) -> bytes:
        return self.swd.read_bytes(address, length)

    def write_flash(self, address: int, data: bytes, progress=lambda done, total: None) -> None:
        """Erase and write whole rows starting at `address` (row aligned). Unused bytes stay erased (0xFF)."""
        info = self.info
        if address % info.row_size:
            raise ChipError("Flash writes must start on a row boundary.")
        length = -(-len(data) // info.row_size) * info.row_size
        data = data.ljust(length, b"\xff")
        if address + length > info.flash_size:
            raise ChipError("The file is larger than the chip's flash.")
        self.set_manual_write()
        for offset in range(0, length, info.row_size):
            row = address + offset
            self.unlock_region(row)
            self.nvm_command(CMD_ER, row)
            for page_offset in range(0, info.row_size, info.page_size):
                page = data[offset + page_offset:offset + page_offset + info.page_size]
                if page != b"\xff" * info.page_size:  # an erased page is already all 0xFF
                    self._write_page(row + page_offset, page, CMD_WP)
            progress(offset + info.row_size, length)

    # -- protected chips -----------------------------------------------------------------

    def chip_erase(self) -> None:
        """Erase the whole chip, including the security bit. Everything on the chip is lost."""
        self.swd.write8(DSU_STATUSA, STATUSA_DONE | STATUSA_FAIL)  # clear old results
        self.swd.write8(DSU_CTRL, DSU_CTRL_CE)
        self._wait(lambda: self.swd.read8(DSU_STATUSA) & (STATUSA_DONE | STATUSA_FAIL), "erase", 10.0)
        if self.swd.read8(DSU_STATUSA) & STATUSA_FAIL:
            raise ChipError("The chip erase failed.")


def connect_under_reset(swd: Swd) -> int:
    """Connect to a chip whose program has turned off its debug pins or put it to sleep.

    Holding SWCLK low while releasing RESET makes the SAMD21 keep its processor in
    reset (CPU reset extension), so no program runs before the debugger attaches.
    """
    probe = swd.probe
    probe.connect_swd()
    probe.swj_clock(swd.clock_hz)
    probe.transfer_configure(idle_cycles=0, wait_retry=128)
    probe.swj_pins(0, d.PIN_NRESET | d.PIN_SWCLK)  # RESET low, SWCLK low
    time.sleep(0.02)
    probe.swj_pins(d.PIN_NRESET, d.PIN_NRESET)  # release RESET, keep SWCLK low
    time.sleep(0.02)
    dpidr = swd.wake()
    swd.power_up()
    return dpidr
