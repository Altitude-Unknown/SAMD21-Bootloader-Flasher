"""Linux (including Raspberry Pi OS) HID access through /dev/hidraw (plain files, no extra packages).

Device details come from /sys/class/hidraw. The output report size is read from
the device's report descriptor. Opening /dev/hidrawN needs permission: the
Raspberry Pi package installs a udev rule for Microchip programmers.
"""

from __future__ import annotations

import errno
import glob
import os
import select

from . import HidDevice, HidError, HidInfo


def _read(path: str, binary: bool = False):
    try:
        with open(path, "rb" if binary else "r") as f:
            return f.read()
    except OSError:
        return b"" if binary else ""


def output_report_size(descriptor: bytes) -> int:
    """Bytes in output report 0 (or the first numbered one), from a HID report descriptor."""
    size = count = 0
    report_id = 0
    totals: dict[int, int] = {}
    i = 0
    while i < len(descriptor):
        prefix = descriptor[i]
        if prefix == 0xFE:  # long item: skip it
            i += 3 + (descriptor[i + 1] if i + 1 < len(descriptor) else 0)
            continue
        length = (0, 1, 2, 4)[prefix & 0x3]
        value = int.from_bytes(descriptor[i + 1:i + 1 + length], "little")
        kind, tag = (prefix >> 2) & 0x3, prefix >> 4
        if kind == 1:  # global item
            if tag == 7:
                size = value
            elif tag == 9:
                count = value
            elif tag == 8:
                report_id = value
        elif kind == 0 and tag == 9:  # main item: Output
            totals[report_id] = totals.get(report_id, 0) + size * count
        i += 1 + length
    if not totals:
        return 0
    bits = totals.get(0, next(iter(totals.values())))
    return (bits + 7) // 8


def list_devices() -> list[HidInfo]:
    found = []
    for sys_dir in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        fields = dict(line.split("=", 1) for line in _read(os.path.join(sys_dir, "device/uevent")).splitlines()
                      if "=" in line)
        try:
            _bus, vid, pid = fields.get("HID_ID", "").split(":")
            vendor_id, product_id = int(vid, 16), int(pid, 16)
        except ValueError:
            continue
        descriptor = _read(os.path.join(sys_dir, "device/report_descriptor"), binary=True)
        found.append(HidInfo(vendor_id=vendor_id, product_id=product_id, product=fields.get("HID_NAME", ""),
                             serial=fields.get("HID_UNIQ", ""), report_size=output_report_size(descriptor),
                             path="/dev/" + os.path.basename(sys_dir)))
    return found


class LinuxHidDevice(HidDevice):
    def __init__(self, info: HidInfo):
        try:
            self._fd = os.open(info.path, os.O_RDWR)
        except PermissionError:
            raise HidError(f"No permission to use {info.name} ({info.path}). Install the udev rule from the "
                           "Raspberry Pi package (install.sh), then unplug and replug the programmer.") from None
        except OSError as exc:
            raise HidError(f"Could not open {info.name}: {exc.strerror}") from None
        self.report_size = info.report_size or 64

    def write(self, report: bytes) -> None:
        data = b"\0" + bytes(report).ljust(self.report_size, b"\0")  # first byte: report number 0
        try:
            os.write(self._fd, data)
        except OSError as exc:
            raise HidError(f"Sending to the programmer failed: {exc.strerror}. Was it unplugged?") from None

    def read(self, timeout: float) -> bytes:
        ready, _, _ = select.select([self._fd], [], [], timeout)
        if not ready:
            raise HidError("The programmer did not answer. Unplug it, plug it back in, and try again.")
        try:
            return os.read(self._fd, max(self.report_size, 64) + 1)
        except OSError as exc:
            if exc.errno == errno.ENODEV:
                raise HidError("The programmer was unplugged.") from None
            raise HidError(f"Reading from the programmer failed: {exc.strerror}") from None

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None


def open_device(info: HidInfo) -> HidDevice:
    return LinuxHidDevice(info)
