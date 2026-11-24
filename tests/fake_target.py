"""A simulated Atmel-ICE and SAMD21G18A, for testing without hardware.

The fake answers real CMSIS-DAP packets, runs SWD DP/AP transfers, and models
the parts of the SAMD21 the app touches: flash rows and the page buffer, the
NVM controller commands, BOOTPROT and region locks (latched at reset), the
security bit, chip erase, and the CPU reset extension.
"""

from __future__ import annotations

import struct

FLASH_SIZE = 256 * 1024
PAGE = 64
ROW = 256
USER_ROW = 0x00804000
DID = 0x10010305  # SAMD21G18A revision D
DPIDR = 0x0BC11477
AP_IDR = 0x04770031
BOOTPROT_SIZES = {7: 0, 6: 512, 5: 1024, 4: 2048, 3: 4096, 2: 8192, 1: 16384, 0: 32768}

ACK_OK, ACK_FAULT, ACK_NONE = 1, 4, 7


class Fault(Exception):
    pass


class FakeSamd21:
    def __init__(self, bootprot=7, region_locks=0xFFFF, protected=False, swd_disabled=False, stuck=None):
        self.flash = bytearray(b"\xff" * FLASH_SIZE)
        self.user_row = bytearray(b"\xff" * ROW)
        # A typical factory user row; BOOTPROT in bits 2:0, region locks in bits 63:48.
        self.user_row[0:8] = struct.pack("<II", 0xD8E0C7F8 | bootprot, 0x0000FC5D | (region_locks << 16))
        self.page_buffer = bytearray(b"\xff" * PAGE)
        self.protected = protected
        self.swd_disabled = swd_disabled  # the running program turned the SWD pins into GPIO
        self.stuck = stuck  # (address, value): a flash byte that always reads `value`
        self.ctrlb = 0
        self.addr = 0
        self.status = 0
        self.intflag = 1
        self.dsu_statusa = 0
        self.crstext = False
        self.debugen = False
        self.halted = False
        self.demcr = 0
        self.resets = 0
        self.commands: list[int] = []
        self.latch()

    # -- fuses latched at reset ---------------------------------------------------------

    def latch(self):
        word0, word1 = struct.unpack_from("<II", self.user_row)
        self.bootprot = word0 & 0x7
        self.lock = word1 >> 16

    def reset(self):
        self.resets += 1
        self.latch()
        self.halted = bool(self.debugen and self.demcr & 1)

    # -- bus -------------------------------------------------------------------------

    def read(self, address: int) -> int:
        """32-bit read."""
        if self.protected and not 0x41002000 <= address < 0x41003000:
            raise Fault
        if address < FLASH_SIZE:
            word = bytearray(self.flash[address:address + 4])
            if self.stuck and address <= self.stuck[0] < address + 4:
                word[self.stuck[0] - address] = self.stuck[1]
            return struct.unpack("<I", word)[0]
        if USER_ROW <= address < USER_ROW + ROW:
            return struct.unpack_from("<I", self.user_row, address - USER_ROW)[0]
        regs = {
            0x41002000: lambda: (self.dsu_statusa | (self.crstext << 1)) << 8 | (int(self.protected) << 16),
            0x41002018: lambda: DID,
            0x41004004: lambda: self.ctrlb,
            0x41004008: lambda: (FLASH_SIZE // PAGE) | (3 << 16),
            0x41004014: lambda: self.intflag,
            0x41004018: lambda: self.status,
            0x4100401C: lambda: self.addr,
            0x41004020: lambda: self.lock,
            0xE000EDF0: lambda: int(self.debugen) | (int(self.halted) << 1) | (int(self.halted) << 17),
            0xE000EDFC: lambda: self.demcr,
        }
        if address in regs:
            return regs[address]() & 0xFFFFFFFF
        if 0x41004000 <= address < 0x41004100:
            return 0
        raise Fault

    def write(self, address: int, value: int, size: int):
        if self.protected and not 0x41002000 <= address < 0x41003000:
            raise Fault
        shift = (address & 3) * 8
        data = (value >> shift) & ((1 << (8 * size)) - 1)
        if address < FLASH_SIZE or USER_ROW <= address < USER_ROW + ROW:
            if size != 4:
                raise Fault  # the page buffer needs 32-bit writes here
            struct.pack_into("<I", self.page_buffer, address % PAGE, data)
            return
        if address == 0x41002000 and size == 1:  # DSU.CTRL
            if data & 0x10:
                self.flash[:] = b"\xff" * FLASH_SIZE
                self.protected = False
                self.dsu_statusa |= 0x01
            return
        if address == 0x41002001 and size == 1:  # DSU.STATUSA, write 1 to clear
            if data & 0x02 and self.crstext:
                self.crstext = False
                self.halted = bool(self.debugen and (self.demcr & 1 or self.halted))
            self.dsu_statusa &= ~data
            return
        if address == 0x41004000 and size == 2:
            if data >> 8 != 0xA5:
                self.status |= 0x04
                self.intflag |= 0x02
                return
            self.command(data & 0x7F)
            return
        if address == 0x41004004:
            self.ctrlb = data
            return
        if address == 0x41004014:
            self.intflag &= ~data
            self.intflag |= 1
            return
        if address == 0x41004018 and size == 2:
            self.status &= ~data
            return
        if address == 0x4100401C:
            self.addr = data
            return
        if address == 0xE000EDF0:
            if data >> 16 == 0xA05F:
                self.debugen = bool(data & 1)
                self.halted = bool(data & 2) and self.debugen
            return
        if address == 0xE000EDFC:
            self.demcr = data
            return
        if address == 0xE000ED0C:
            if data == 0x05FA0004:
                self.reset()
            return
        raise Fault

    def command(self, cmd: int):
        self.commands.append(cmd)
        address = self.addr * 2
        if cmd in (0x02, 0x04):  # erase row, write page
            if address < BOOTPROT_SIZES[self.bootprot] or not self.lock >> (address // (FLASH_SIZE // 16)) & 1:
                self.status |= 0x08  # LOCKE
                self.intflag |= 0x02
                return
            if cmd == 0x02:
                row = address - address % ROW
                self.flash[row:row + ROW] = b"\xff" * ROW
            else:
                page = address - address % PAGE
                for i in range(PAGE):
                    self.flash[page + i] &= self.page_buffer[i]  # flash bits only go from 1 to 0
                self.page_buffer[:] = b"\xff" * PAGE
        elif cmd == 0x05 and address == USER_ROW:
            self.user_row[:] = b"\xff" * ROW
        elif cmd == 0x06 and address == USER_ROW:
            for i in range(PAGE):
                self.user_row[i] &= self.page_buffer[i]
            self.page_buffer[:] = b"\xff" * PAGE
        elif cmd == 0x41:
            self.lock |= 1 << (address // (FLASH_SIZE // 16))
        elif cmd == 0x44:
            self.page_buffer[:] = b"\xff" * PAGE
        else:
            self.status |= 0x04
            self.intflag |= 0x02


class FakeProbe:
    """Stands in for hid.HidDevice: an Atmel-ICE speaking CMSIS-DAP, wired to a FakeSamd21."""

    def __init__(self, chip: FakeSamd21, report_size: int = 512):
        self.chip = chip
        self.report_size = report_size
        self.replies: list[bytes] = []
        self.awake = False
        self.select = 0
        self.csw = 0x03000040
        self.tar = 0
        self.sticky = False
        self.ctrl_stat = 0
        self.pins = 0xFF
        self.closed = False

    # HidDevice interface
    def write(self, report: bytes) -> None:
        assert len(report) <= self.report_size
        self.replies.append(self.handle(bytes(report)).ljust(self.report_size, b"\0"))

    def read(self, timeout: float) -> bytes:
        return self.replies.pop(0)

    def close(self) -> None:
        self.closed = True

    # CMSIS-DAP
    def handle(self, p: bytes) -> bytes:
        cmd = p[0]
        if cmd == 0x00:
            item = p[1]
            data = {0xFF: struct.pack("<H", self.report_size), 0xF0: b"\x01", 0x04: b"1.0\0",
                    0x02: b"Atmel-ICE CMSIS-DAP\0"}.get(item, b"")
            return bytes([0, len(data)]) + data
        if cmd == 0x02:
            return bytes([2, 1 if p[1] in (0, 1) else 0])
        if cmd in (0x01, 0x03, 0x04, 0x11):
            return bytes([cmd, 0])
        if cmd == 0x08:
            self.sticky = False
            return b"\x08\x00"
        if cmd == 0x12:
            bits = p[1] or 256
            if p[2:4] == b"\x9e\xe7" and bits == 16:
                self.awake = not self.chip.swd_disabled
            return b"\x12\x00"
        if cmd == 0x10:
            output, select = p[1], p[2]
            new = (self.pins & ~select) | (output & select)
            if self.pins & 0x80 == 0 and new & 0x80 and not new & 0x01:
                # RESET released while SWCLK is low: CPU reset extension, and no program has run yet
                self.chip.crstext = True
                self.chip.swd_disabled = False
                self.chip.latch()
            self.pins = new
            return bytes([0x10, self.pins])
        if cmd == 0x05:
            return self.transfer(p)
        if cmd == 0x06:
            return self.transfer_block(p)
        return bytes([cmd, 0xFF])

    def transfer(self, p: bytes) -> bytes:
        count = p[2]
        i = 3
        out = bytearray()
        done = 0
        ack = ACK_OK
        for _ in range(count):
            req = p[i]
            i += 1
            value = None
            if not req & 2:
                value = struct.unpack_from("<I", p, i)[0]
                i += 4
            ack, data = self.one(req, value)
            if ack != ACK_OK:
                break
            done += 1
            if data is not None:
                out += struct.pack("<I", data)
        return bytes([5, done, ack]) + bytes(out)

    def transfer_block(self, p: bytes) -> bytes:
        count, req = struct.unpack_from("<HB", p, 2)
        out = bytearray()
        done = 0
        ack = ACK_OK
        for n in range(count):
            value = None if req & 2 else struct.unpack_from("<I", p, 5 + 4 * n)[0]
            ack, data = self.one(req, value)
            if ack != ACK_OK:
                break
            done += 1
            if data is not None:
                out += struct.pack("<I", data)
        return bytes([6]) + struct.pack("<HB", done, ack) + bytes(out)

    def one(self, req: int, value: int | None):
        if not self.awake:
            return ACK_NONE, None
        if self.sticky:
            return ACK_FAULT, None
        ap, read, a = req & 1, req & 2, req & 0x0C
        if not ap:
            if read:
                return ACK_OK, {0x0: DPIDR, 0x4: self.ctrl_stat | ((self.ctrl_stat & (5 << 28)) << 1),
                                0x8: self.select, 0xC: 0}[a]
            if a == 0x4:
                self.ctrl_stat = value
            elif a == 0x8:
                self.select = value
            return ACK_OK, None
        register = (self.select & 0xF0) | a
        if register == 0x00:
            if read:
                return ACK_OK, self.csw
            self.csw = value
            return ACK_OK, None
        if register == 0x04:
            if read:
                return ACK_OK, self.tar
            self.tar = value
            return ACK_OK, None
        if register == 0xFC:
            return ACK_OK, AP_IDR
        if register != 0x0C:
            return ACK_OK, 0
        size = 1 << (self.csw & 7)
        try:
            if read:
                data = self.chip.read(self.tar & ~3)
            else:
                self.chip.write(self.tar, value, size)
                data = None
        except Fault:
            self.sticky = True
            return ACK_FAULT, None
        if self.csw & 0x30 == 0x10:  # auto-increment wraps inside a 1 KB block, as real MEM-APs may
            self.tar = (self.tar & ~0x3FF) | ((self.tar + size) & 0x3FF)
        return ACK_OK, data
