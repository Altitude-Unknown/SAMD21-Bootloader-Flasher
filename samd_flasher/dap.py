"""CMSIS-DAP, the command set an Atmel-ICE (and other ARM debug probes) understands.

Each command is one USB HID report; the probe answers with one report that
starts with the same command byte. Only the commands this app needs are here.
Reference: Arm CMSIS-DAP specification, "Commands".
"""

from __future__ import annotations

import struct

from .hid import HidDevice

DAP_INFO = 0x00
DAP_HOST_STATUS = 0x01
DAP_CONNECT = 0x02
DAP_DISCONNECT = 0x03
DAP_TRANSFER_CONFIGURE = 0x04
DAP_TRANSFER = 0x05
DAP_TRANSFER_BLOCK = 0x06
DAP_WRITE_ABORT = 0x08
DAP_SWJ_PINS = 0x10
DAP_SWJ_CLOCK = 0x11
DAP_SWJ_SEQUENCE = 0x12

INFO_VENDOR = 0x01
INFO_PRODUCT = 0x02
INFO_SERIAL = 0x03
INFO_FIRMWARE = 0x04
INFO_CAPABILITIES = 0xF0
INFO_PACKET_SIZE = 0xFF

DAP_OK = 0x00
PORT_SWD = 1

# DAP_SWJ_Pins bits
PIN_SWCLK = 1 << 0
PIN_SWDIO = 1 << 1
PIN_NRESET = 1 << 7

# DAP_Transfer request bits
AP = 1 << 0
READ = 1 << 1

# Transfer acknowledges
ACK_OK, ACK_WAIT, ACK_FAULT = 1, 2, 4


class DapError(Exception):
    pass


class TransferError(DapError):
    """An SWD transfer was not acknowledged with OK."""

    def __init__(self, ack: int, done: int):
        self.ack = ack
        self.done = done
        if ack & 0x7 == ACK_FAULT:
            text = "the chip refused the access (FAULT)"
        elif ack & 0x7 == ACK_WAIT:
            text = "the chip stayed busy (WAIT)"
        elif ack & 0x8:
            text = "an SWD protocol error (check the wiring)"
        else:
            text = "no answer from the chip (check the wiring and that the board is powered)"
        super().__init__(f"SWD transfer failed: {text}.")


class CmsisDap:
    def __init__(self, device: HidDevice, timeout: float = 2.0):
        self.device = device
        self.timeout = timeout
        self.packet_size = device.report_size

    # -- framing ---------------------------------------------------------------

    def command(self, payload: bytes) -> bytes:
        if len(payload) > self.packet_size:
            raise DapError(f"Command of {len(payload)} bytes does not fit a {self.packet_size}-byte packet.")
        self.device.write(payload)
        reply = self.device.read(self.timeout)
        if not reply or reply[0] != payload[0]:
            raise DapError(f"Unexpected answer from the programmer to command 0x{payload[0]:02X}.")
        return reply

    def _status(self, payload: bytes, what: str) -> None:
        if self.command(payload)[1] != DAP_OK:
            raise DapError(f"The programmer could not {what}.")

    # -- information -------------------------------------------------------------

    def info(self, item: int) -> bytes:
        reply = self.command(bytes([DAP_INFO, item]))
        return reply[2:2 + reply[1]]

    def info_string(self, item: int) -> str:
        return self.info(item).split(b"\0")[0].decode("ascii", "replace")

    def setup(self) -> None:
        """Match the packet size the probe reports (some probes use smaller packets than their USB reports)."""
        size = self.info(INFO_PACKET_SIZE)
        if len(size) == 2:
            reported = struct.unpack("<H", size)[0]
            if 0 < reported <= self.packet_size:
                self.packet_size = reported
        caps = self.info(INFO_CAPABILITIES)
        if caps and not caps[0] & 0x01:
            raise DapError("This programmer does not support SWD, which SAMD21 chips need.")

    # -- connection ------------------------------------------------------------------

    def connect_swd(self) -> None:
        if self.command(bytes([DAP_CONNECT, PORT_SWD]))[1] != PORT_SWD:
            raise DapError("The programmer could not switch to SWD mode.")

    def disconnect(self) -> None:
        self.command(bytes([DAP_DISCONNECT]))

    def host_status(self, running: bool) -> None:
        """The programmer's activity LED."""
        self.command(bytes([DAP_HOST_STATUS, 1, 1 if running else 0]))

    def swj_clock(self, hz: int) -> None:
        self._status(struct.pack("<BI", DAP_SWJ_CLOCK, hz), f"set the SWD clock to {hz} Hz")

    def swj_sequence(self, bit_count: int, data: bytes) -> None:
        self._status(bytes([DAP_SWJ_SEQUENCE, bit_count & 0xFF]) + data, "send the SWD wake-up sequence")

    def swj_pins(self, output: int, select: int, wait_us: int = 0) -> int:
        """Drive the selected pins (SWCLK, SWDIO, nRESET...) and return the pin states read back."""
        return self.command(struct.pack("<BBBI", DAP_SWJ_PINS, output, select, wait_us))[1]

    def transfer_configure(self, idle_cycles: int = 0, wait_retry: int = 128, match_retry: int = 0) -> None:
        self._status(struct.pack("<BBHH", DAP_TRANSFER_CONFIGURE, idle_cycles, wait_retry, match_retry),
                     "configure SWD transfers")

    def write_abort(self, value: int) -> None:
        self._status(struct.pack("<BBI", DAP_WRITE_ABORT, 0, value), "clear SWD errors")

    # -- transfers -------------------------------------------------------------------

    def transfer(self, requests: list[tuple[int, int | None]]) -> list[int]:
        """Run (request, value) pairs; value is None for reads. Returns the values read, in order."""
        payload = bytearray([DAP_TRANSFER, 0, len(requests)])
        for request, value in requests:
            payload.append(request)
            if not request & READ:
                payload += struct.pack("<I", value)
        reply = self.command(bytes(payload))
        done, ack = reply[1], reply[2]
        if done != len(requests) or ack != ACK_OK:
            raise TransferError(ack, done)
        reads = sum(1 for request, _ in requests if request & READ)
        return list(struct.unpack_from(f"<{reads}I", reply, 3))

    def max_block_words(self) -> int:
        return (self.packet_size - 5) // 4

    def transfer_block_read(self, request: int, count: int) -> list[int]:
        reply = self.command(struct.pack("<BBHB", DAP_TRANSFER_BLOCK, 0, count, request | READ))
        done, ack = struct.unpack_from("<HB", reply, 1)
        if done != count or ack != ACK_OK:
            raise TransferError(ack, done)
        return list(struct.unpack_from(f"<{count}I", reply, 4))

    def transfer_block_write(self, request: int, words: list[int]) -> None:
        payload = struct.pack("<BBHB", DAP_TRANSFER_BLOCK, 0, len(words), request) + struct.pack(
            f"<{len(words)}I", *words)
        reply = self.command(payload)
        done, ack = struct.unpack_from("<HB", reply, 1)
        if done != len(words) or ack != ACK_OK:
            raise TransferError(ack, done)
