"""macOS HID access through Apple's IOKit framework (ctypes, no extra packages).

Output reports are sent with IOHIDDeviceSetReport. Input reports arrive through
a callback on a run loop, so each device is scheduled on the run loop of the
thread that opened it, and read() runs that loop until a report arrives. Open,
use, and close a device on the same thread (the app does all USB work on one
worker thread).
"""

from __future__ import annotations

import ctypes
import threading
from ctypes import (CFUNCTYPE, POINTER, byref, c_bool, c_char_p, c_double, c_int32, c_long, c_uint8, c_uint32,
                    c_uint64, c_void_p)

from . import HidDevice, HidError, HidInfo

_cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
_iokit = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/IOKit.framework/IOKit")

CFIndex = c_long
UTF8 = 0x08000100  # kCFStringEncodingUTF8
SINT32 = 3  # kCFNumberSInt32Type
REPORT_OUTPUT = 1  # kIOHIDReportTypeOutput
IO_RETURN_SUCCESS = 0
IO_RETURN_EXCLUSIVE = -536870203  # 0xE00002C5 kIOReturnExclusiveAccess
RUN_FINISHED, RUN_STOPPED, RUN_TIMED_OUT, RUN_HANDLED = 1, 2, 3, 4


def _fn(lib, name, restype, *argtypes):
    f = getattr(lib, name)
    f.restype = restype
    f.argtypes = list(argtypes)
    return f


CFStringCreateWithCString = _fn(_cf, "CFStringCreateWithCString", c_void_p, c_void_p, c_char_p, c_uint32)
CFStringGetCString = _fn(_cf, "CFStringGetCString", c_bool, c_void_p, c_char_p, CFIndex, c_uint32)
CFGetTypeID = _fn(_cf, "CFGetTypeID", c_long, c_void_p)
CFStringGetTypeID = _fn(_cf, "CFStringGetTypeID", c_long)
CFNumberGetTypeID = _fn(_cf, "CFNumberGetTypeID", c_long)
CFNumberGetValue = _fn(_cf, "CFNumberGetValue", c_bool, c_void_p, CFIndex, c_void_p)
CFSetGetCount = _fn(_cf, "CFSetGetCount", CFIndex, c_void_p)
CFSetGetValues = _fn(_cf, "CFSetGetValues", None, c_void_p, POINTER(c_void_p))
CFRetain = _fn(_cf, "CFRetain", c_void_p, c_void_p)
CFRelease = _fn(_cf, "CFRelease", None, c_void_p)
CFRunLoopGetCurrent = _fn(_cf, "CFRunLoopGetCurrent", c_void_p)
CFRunLoopRunInMode = _fn(_cf, "CFRunLoopRunInMode", c_int32, c_void_p, c_double, c_bool)
DEFAULT_MODE = c_void_p.in_dll(_cf, "kCFRunLoopDefaultMode")

IOHIDManagerCreate = _fn(_iokit, "IOHIDManagerCreate", c_void_p, c_void_p, c_uint32)
IOHIDManagerSetDeviceMatching = _fn(_iokit, "IOHIDManagerSetDeviceMatching", None, c_void_p, c_void_p)
IOHIDManagerCopyDevices = _fn(_iokit, "IOHIDManagerCopyDevices", c_void_p, c_void_p)
IOHIDDeviceGetProperty = _fn(_iokit, "IOHIDDeviceGetProperty", c_void_p, c_void_p, c_void_p)
IOHIDDeviceGetService = _fn(_iokit, "IOHIDDeviceGetService", c_uint32, c_void_p)
IORegistryEntryGetRegistryEntryID = _fn(_iokit, "IORegistryEntryGetRegistryEntryID", c_int32, c_uint32,
                                        POINTER(c_uint64))
IOHIDDeviceOpen = _fn(_iokit, "IOHIDDeviceOpen", c_int32, c_void_p, c_uint32)
IOHIDDeviceClose = _fn(_iokit, "IOHIDDeviceClose", c_int32, c_void_p, c_uint32)
IOHIDDeviceSetReport = _fn(_iokit, "IOHIDDeviceSetReport", c_int32, c_void_p, c_int32, CFIndex, c_void_p, CFIndex)
ReportCallback = CFUNCTYPE(None, c_void_p, c_int32, c_void_p, c_int32, c_uint32, POINTER(c_uint8), CFIndex)
IOHIDDeviceRegisterInputReportCallback = _fn(_iokit, "IOHIDDeviceRegisterInputReportCallback", None, c_void_p,
                                             POINTER(c_uint8), CFIndex, ReportCallback, c_void_p)
IOHIDDeviceScheduleWithRunLoop = _fn(_iokit, "IOHIDDeviceScheduleWithRunLoop", None, c_void_p, c_void_p, c_void_p)
IOHIDDeviceUnscheduleFromRunLoop = _fn(_iokit, "IOHIDDeviceUnscheduleFromRunLoop", None, c_void_p, c_void_p,
                                       c_void_p)

_keys: dict[str, int] = {}


def _key(text: str) -> int:
    """A CFString for a property name, made once and kept for the life of the app."""
    if text not in _keys:
        _keys[text] = CFStringCreateWithCString(None, text.encode(), UTF8)
    return _keys[text]


def _int_property(device, name: str) -> int:
    ref = IOHIDDeviceGetProperty(device, _key(name))
    if not ref or CFGetTypeID(ref) != CFNumberGetTypeID():
        return 0
    value = c_int32()
    CFNumberGetValue(ref, SINT32, byref(value))
    return value.value


def _str_property(device, name: str) -> str:
    ref = IOHIDDeviceGetProperty(device, _key(name))
    if not ref or CFGetTypeID(ref) != CFStringGetTypeID():
        return ""
    buf = ctypes.create_string_buffer(512)
    return buf.value.decode("utf-8", "replace") if CFStringGetCString(ref, buf, len(buf), UTF8) else ""


def _registry_id(device) -> str:
    entry = c_uint64()
    service = IOHIDDeviceGetService(device)
    if service and IORegistryEntryGetRegistryEntryID(service, byref(entry)) == 0:
        return str(entry.value)
    return ""


class _Snapshot:
    """The HID devices present right now. Device references stay valid while this is alive."""

    def __init__(self):
        self.manager = IOHIDManagerCreate(None, 0)
        if not self.manager:
            raise HidError("macOS did not allow access to USB devices.")
        IOHIDManagerSetDeviceMatching(self.manager, None)  # every HID device; we filter ourselves
        self.set = IOHIDManagerCopyDevices(self.manager)
        count = CFSetGetCount(self.set) if self.set else 0
        refs = (c_void_p * count)()
        if count:
            CFSetGetValues(self.set, refs)
        self.devices = [ref for ref in refs if ref]

    def release(self):
        if self.set:
            CFRelease(self.set)
            self.set = None
        if self.manager:
            CFRelease(self.manager)
            self.manager = None


def _info(device) -> HidInfo:
    return HidInfo(
        vendor_id=_int_property(device, "VendorID"),
        product_id=_int_property(device, "ProductID"),
        product=_str_property(device, "Product"),
        serial=_str_property(device, "SerialNumber"),
        report_size=_int_property(device, "MaxOutputReportSize"),
        path=_registry_id(device),
    )


def list_devices() -> list[HidInfo]:
    snapshot = _Snapshot()
    try:
        return [_info(device) for device in snapshot.devices]
    finally:
        snapshot.release()


class MacHidDevice(HidDevice):
    def __init__(self, info: HidInfo):
        snapshot = _Snapshot()
        try:
            match = next((d for d in snapshot.devices if _registry_id(d) == info.path), None)
            if match is None:
                raise HidError(f"{info.name} is no longer connected.")
            self._device = CFRetain(match)
        finally:
            snapshot.release()
        result = IOHIDDeviceOpen(self._device, 0)
        if result != IO_RETURN_SUCCESS:
            CFRelease(self._device)
            self._device = None
            if result == IO_RETURN_EXCLUSIVE:
                raise HidError(f"{info.name} is in use by another program. Close it and try again.")
            raise HidError(f"Could not open {info.name} (IOKit error 0x{result & 0xFFFFFFFF:08X}).")
        self.report_size = info.report_size or 64
        self._thread = threading.get_ident()
        self._reports: list[bytes] = []
        in_size = max(_int_property(self._device, "MaxInputReportSize"), self.report_size)
        self._buffer = (c_uint8 * in_size)()
        self._callback = ReportCallback(self._on_report)  # keep a reference: IOKit calls it later
        self._run_loop = CFRunLoopGetCurrent()
        IOHIDDeviceRegisterInputReportCallback(self._device, self._buffer, in_size, self._callback, None)
        IOHIDDeviceScheduleWithRunLoop(self._device, self._run_loop, DEFAULT_MODE)

    def _on_report(self, _context, result, _sender, _type, _report_id, report, length):
        if result == IO_RETURN_SUCCESS and length > 0:
            self._reports.append(ctypes.string_at(report, length))

    def _check_thread(self):
        if threading.get_ident() != self._thread:
            raise HidError("Programmer used from a different thread than the one that opened it.")

    def write(self, report: bytes) -> None:
        self._check_thread()
        data = bytes(report).ljust(self.report_size, b"\0")
        buf = (c_uint8 * len(data)).from_buffer_copy(data)
        result = IOHIDDeviceSetReport(self._device, REPORT_OUTPUT, 0, buf, len(data))
        if result != IO_RETURN_SUCCESS:
            raise HidError(f"Sending to the programmer failed (IOKit error 0x{result & 0xFFFFFFFF:08X}). "
                           "Was it unplugged?")

    def read(self, timeout: float) -> bytes:
        self._check_thread()
        remaining = timeout
        while not self._reports and remaining > 0:
            step = min(remaining, 0.05)
            CFRunLoopRunInMode(DEFAULT_MODE, step, True)
            remaining -= step
        if not self._reports:
            raise HidError("The programmer did not answer. Unplug it, plug it back in, and try again.")
        return self._reports.pop(0)

    def close(self) -> None:
        if self._device:
            IOHIDDeviceUnscheduleFromRunLoop(self._device, self._run_loop, DEFAULT_MODE)
            IOHIDDeviceClose(self._device, 0)
            CFRelease(self._device)
            self._device = None


def open_device(info: HidInfo) -> HidDevice:
    return MacHidDevice(info)
