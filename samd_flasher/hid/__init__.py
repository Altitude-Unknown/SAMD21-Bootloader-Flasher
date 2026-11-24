"""USB HID access for CMSIS-DAP programmers, written for this app.

Each operating system has its own HID interface, so there is one small module
per platform, all using only the Python standard library (ctypes or plain
files). They share one shape:

    list_devices() -> list[HidInfo]
    open_device(info) -> HidDevice   (write(report), read(timeout), close())

`find_probes()` keeps only CMSIS-DAP programmers: the Atmel-ICE and other
Microchip debuggers by USB ID, and any device whose product name says
"CMSIS-DAP".
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

# USB vendor/product IDs of Microchip (Atmel) debuggers that speak CMSIS-DAP.
KNOWN_PROBES = {
    (0x03EB, 0x2141): "Atmel-ICE",
}


@dataclass(frozen=True)
class HidInfo:
    vendor_id: int
    product_id: int
    product: str
    serial: str
    report_size: int  # bytes in one output report, without a report ID
    path: str  # platform-specific way to reopen this exact device

    @property
    def name(self) -> str:
        known = KNOWN_PROBES.get((self.vendor_id, self.product_id))
        base = known or self.product or f"USB device {self.vendor_id:04X}:{self.product_id:04X}"
        return f"{base} ({self.serial})" if self.serial else base


class HidError(Exception):
    pass


class HidDevice:
    """Interface every platform module implements."""

    report_size: int

    def write(self, report: bytes) -> None:
        raise NotImplementedError

    def read(self, timeout: float) -> bytes:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()


def _backend():
    if sys.platform == "darwin":
        from . import _mac as backend
    elif sys.platform == "win32":
        from . import _windows as backend
    elif sys.platform.startswith("linux"):
        from . import _linux as backend
    else:
        raise HidError(f"USB programmers are not supported on {sys.platform}.")
    return backend


def is_probe(info: HidInfo) -> bool:
    return (info.vendor_id, info.product_id) in KNOWN_PROBES or "CMSIS-DAP" in info.product.upper()


def list_devices() -> list[HidInfo]:
    return _backend().list_devices()


def find_probes() -> list[HidInfo]:
    return [info for info in list_devices() if is_probe(info)]


def open_device(info: HidInfo) -> HidDevice:
    return _backend().open_device(info)
