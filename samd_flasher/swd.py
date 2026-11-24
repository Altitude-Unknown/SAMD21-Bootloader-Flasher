"""SWD memory access to an Arm Cortex-M chip through a CMSIS-DAP probe.

Arm's Debug Interface (ADIv5) has a Debug Port (DP) and an Access Port (AP).
The AP used here is a MEM-AP: write an address to TAR, then read or write DRW
to access memory at that address. Reference: Arm Debug Interface Architecture
Specification ADIv5, chapters on the SW-DP and MEM-AP.
"""

from __future__ import annotations

import time

from . import dap as d

# Debug Port registers (address bits [3:2])
DP_DPIDR = 0x0  # read
DP_ABORT = 0x0  # write
DP_CTRL_STAT = 0x4
DP_SELECT = 0x8
DP_RDBUFF = 0xC

# MEM-AP registers (bank in SELECT[7:4], register in address bits [3:2])
AP_CSW = 0x00
AP_TAR = 0x04
AP_DRW = 0x0C
AP_IDR = 0xFC

CDBGPWRUPREQ = 1 << 28
CDBGPWRUPACK = 1 << 29
CSYSPWRUPREQ = 1 << 30
CSYSPWRUPACK = 1 << 31
ABORT_CLEAR_ALL = 0x1E  # ORUNERRCLR | WDERRCLR | STKERRCLR | STKCMPCLR

CSW_SIZE_MASK = 0x07
CSW_INC_MASK = 0x30
CSW_INC_SINGLE = 0x10
SIZE_BYTE, SIZE_HALF, SIZE_WORD = 0, 1, 2

TAR_WRAP = 1024  # the TAR auto-increment is only guaranteed within a 1 KB block

# The SWD wake-up: at least 50 clocks with SWDIO high (line reset), the
# 16-bit JTAG-to-SWD code 0xE79E (sent LSB first), another line reset, then idle.
LINE_RESET = (56, b"\xff" * 7)
JTAG_TO_SWD = (16, b"\x9e\xe7")
IDLE = (8, b"\x00")


def _req(ap: bool, read: bool, address: int) -> int:
    return (d.AP if ap else 0) | (d.READ if read else 0) | (address & 0x0C)


class Swd:
    def __init__(self, probe: d.CmsisDap, clock_hz: int = 1_000_000):
        self.probe = probe
        self.clock_hz = clock_hz
        self.dpidr = 0
        self._select = None
        self._csw_base = 0
        self._csw = None

    # -- connecting --------------------------------------------------------------

    def wake(self) -> int:
        """Switch the chip's debug pins to SWD and read the Debug Port ID."""
        for bits, data in (LINE_RESET, JTAG_TO_SWD, LINE_RESET, IDLE):
            self.probe.swj_sequence(bits, data)
        self.dpidr = self.read_dp(DP_DPIDR)
        return self.dpidr

    def connect(self) -> int:
        self.probe.connect_swd()
        self.probe.swj_clock(self.clock_hz)
        self.probe.transfer_configure(idle_cycles=0, wait_retry=128)
        dpidr = self.wake()
        self.power_up()
        return dpidr

    def power_up(self) -> None:
        self.probe.write_abort(ABORT_CLEAR_ALL)
        self._select = None
        self.write_dp(DP_SELECT, 0)
        self._select = 0
        self.write_dp(DP_CTRL_STAT, CSYSPWRUPREQ | CDBGPWRUPREQ)
        deadline = time.monotonic() + 1.0
        while True:
            status = self.read_dp(DP_CTRL_STAT)
            if status & (CSYSPWRUPACK | CDBGPWRUPACK) == CSYSPWRUPACK | CDBGPWRUPACK:
                break
            if time.monotonic() > deadline:
                raise d.DapError("The chip's debug logic did not power up.")
        self._csw_base = self.read_ap(AP_CSW) & ~(CSW_SIZE_MASK | CSW_INC_MASK)
        self._csw = None

    def clear_errors(self) -> None:
        self.probe.write_abort(ABORT_CLEAR_ALL)

    # -- DP / AP registers -----------------------------------------------------------

    def read_dp(self, address: int) -> int:
        return self.probe.transfer([(_req(False, True, address), None)])[0]

    def write_dp(self, address: int, value: int) -> None:
        self.probe.transfer([(_req(False, False, address), value)])

    def _select_bank(self, address: int) -> list:
        bank = address & 0xF0
        if bank == self._select:
            return []
        self._select = bank
        return [(_req(False, False, DP_SELECT), bank)]  # AP 0, bank from the address

    def read_ap(self, address: int) -> int:
        requests = self._select_bank(address) + [(_req(True, True, address), None)]
        return self.probe.transfer(requests)[0]

    def write_ap(self, address: int, value: int) -> None:
        self.probe.transfer(self._select_bank(address) + [(_req(True, False, address), value)])

    def _csw_requests(self, size: int, increment: bool) -> list:
        csw = self._csw_base | size | (CSW_INC_SINGLE if increment else 0)
        if csw == self._csw:
            return []
        self._csw = csw
        return self._select_bank(AP_CSW) + [(_req(True, False, AP_CSW), csw)]

    # -- memory ----------------------------------------------------------------------

    def read32(self, address: int) -> int:
        requests = self._csw_requests(SIZE_WORD, False) + self._select_bank(AP_TAR)
        requests += [(_req(True, False, AP_TAR), address), (_req(True, True, AP_DRW), None)]
        return self.probe.transfer(requests)[0]

    def write32(self, address: int, value: int) -> None:
        self._write_sized(address, value & 0xFFFFFFFF, SIZE_WORD)

    def read16(self, address: int) -> int:
        return (self.read32(address & ~3) >> ((address & 2) * 8)) & 0xFFFF

    def read8(self, address: int) -> int:
        return (self.read32(address & ~3) >> ((address & 3) * 8)) & 0xFF

    def write16(self, address: int, value: int) -> None:
        self._write_sized(address, (value & 0xFFFF) << ((address & 2) * 8), SIZE_HALF)

    def write8(self, address: int, value: int) -> None:
        self._write_sized(address, (value & 0xFF) << ((address & 3) * 8), SIZE_BYTE)

    def _write_sized(self, address: int, lane_value: int, size: int) -> None:
        """Write 1, 2 or 4 bytes. Narrow writes put the data in its byte lane, as the bus expects."""
        requests = self._csw_requests(size, False) + self._select_bank(AP_TAR)
        requests += [(_req(True, False, AP_TAR), address), (_req(True, False, AP_DRW), lane_value)]
        self.probe.transfer(requests)

    def write32_ignore_ack(self, address: int, value: int) -> None:
        """For writes that reset the chip: the acknowledge may never arrive."""
        try:
            self.write32(address, value)
        except d.TransferError:
            pass
        self.clear_errors()

    def _chunks(self, address: int, words: int):
        """Split a word run into pieces that fit one packet and stay inside a 1 KB TAR block."""
        while words:
            room = (TAR_WRAP - (address % TAR_WRAP)) // 4
            n = min(words, room, self.probe.max_block_words())
            yield address, n
            address += n * 4
            words -= n

    def read_words(self, address: int, count: int) -> list[int]:
        out: list[int] = []
        for start, n in self._chunks(address, count):
            self.probe.transfer(self._csw_requests(SIZE_WORD, True) + self._select_bank(AP_TAR) +
                                [(_req(True, False, AP_TAR), start)])
            out += self.probe.transfer_block_read(_req(True, True, AP_DRW), n)
        return out

    def write_words(self, address: int, words: list[int]) -> None:
        index = 0
        for start, n in self._chunks(address, len(words)):
            self.probe.transfer(self._csw_requests(SIZE_WORD, True) + self._select_bank(AP_TAR) +
                                [(_req(True, False, AP_TAR), start)])
            self.probe.transfer_block_write(_req(True, False, AP_DRW), words[index:index + n])
            index += n

    def read_bytes(self, address: int, length: int) -> bytes:
        words = self.read_words(address, (length + 3) // 4)
        return b"".join(w.to_bytes(4, "little") for w in words)[:length]
