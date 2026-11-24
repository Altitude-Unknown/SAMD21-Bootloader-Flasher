"""Windows HID access through hid.dll, setupapi.dll and kernel32 (ctypes, no extra packages).

Windows numbers every HID report: writes start with the report ID (0 for
CMSIS-DAP) and reads return it as the first byte, which is removed here.
Reads use overlapped I/O so they can time out.
"""

from __future__ import annotations

import ctypes
from ctypes import POINTER, Structure, byref, c_ubyte, c_ulong, c_ushort, c_void_p, sizeof, wintypes

from . import HidDevice, HidError, HidInfo

_hid = ctypes.WinDLL("hid")
_setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ_WRITE = 0x3
OPEN_EXISTING = 3
FILE_FLAG_OVERLAPPED = 0x40000000
INVALID_HANDLE = c_void_p(-1).value
DIGCF_PRESENT = 0x2
DIGCF_DEVICEINTERFACE = 0x10
ERROR_IO_PENDING = 997
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 0x102


class GUID(Structure):
    _fields_ = [("Data1", c_ulong), ("Data2", c_ushort), ("Data3", c_ushort), ("Data4", c_ubyte * 8)]


class SP_DEVICE_INTERFACE_DATA(Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("InterfaceClassGuid", GUID), ("Flags", wintypes.DWORD),
                ("Reserved", ctypes.c_size_t)]


class HIDD_ATTRIBUTES(Structure):
    _fields_ = [("Size", c_ulong), ("VendorID", c_ushort), ("ProductID", c_ushort), ("VersionNumber", c_ushort)]


class HIDP_CAPS(Structure):
    _fields_ = [("Usage", c_ushort), ("UsagePage", c_ushort), ("InputReportByteLength", c_ushort),
                ("OutputReportByteLength", c_ushort), ("FeatureReportByteLength", c_ushort),
                ("Reserved", c_ushort * 17), ("NumberLinkCollectionNodes", c_ushort),
                ("NumberInputButtonCaps", c_ushort), ("NumberInputValueCaps", c_ushort),
                ("NumberInputDataIndices", c_ushort), ("NumberOutputButtonCaps", c_ushort),
                ("NumberOutputValueCaps", c_ushort), ("NumberOutputDataIndices", c_ushort),
                ("NumberFeatureButtonCaps", c_ushort), ("NumberFeatureValueCaps", c_ushort),
                ("NumberFeatureDataIndices", c_ushort)]


class OVERLAPPED(Structure):
    _fields_ = [("Internal", ctypes.c_size_t), ("InternalHigh", ctypes.c_size_t), ("Offset", wintypes.DWORD),
                ("OffsetHigh", wintypes.DWORD), ("hEvent", wintypes.HANDLE)]


def _fn(lib, name, restype, *argtypes):
    f = getattr(lib, name)
    f.restype = restype
    f.argtypes = list(argtypes)
    return f


HidD_GetHidGuid = _fn(_hid, "HidD_GetHidGuid", None, POINTER(GUID))
HidD_GetAttributes = _fn(_hid, "HidD_GetAttributes", wintypes.BOOLEAN, wintypes.HANDLE, POINTER(HIDD_ATTRIBUTES))
HidD_GetProductString = _fn(_hid, "HidD_GetProductString", wintypes.BOOLEAN, wintypes.HANDLE, c_void_p, c_ulong)
HidD_GetSerialNumberString = _fn(_hid, "HidD_GetSerialNumberString", wintypes.BOOLEAN, wintypes.HANDLE, c_void_p,
                                 c_ulong)
HidD_GetPreparsedData = _fn(_hid, "HidD_GetPreparsedData", wintypes.BOOLEAN, wintypes.HANDLE, POINTER(c_void_p))
HidD_FreePreparsedData = _fn(_hid, "HidD_FreePreparsedData", wintypes.BOOLEAN, c_void_p)
HidP_GetCaps = _fn(_hid, "HidP_GetCaps", ctypes.c_long, c_void_p, POINTER(HIDP_CAPS))
SetupDiGetClassDevsW = _fn(_setupapi, "SetupDiGetClassDevsW", wintypes.HANDLE, POINTER(GUID), wintypes.LPCWSTR,
                           wintypes.HWND, wintypes.DWORD)
SetupDiEnumDeviceInterfaces = _fn(_setupapi, "SetupDiEnumDeviceInterfaces", wintypes.BOOL, wintypes.HANDLE,
                                  c_void_p, POINTER(GUID), wintypes.DWORD, POINTER(SP_DEVICE_INTERFACE_DATA))
SetupDiGetDeviceInterfaceDetailW = _fn(_setupapi, "SetupDiGetDeviceInterfaceDetailW", wintypes.BOOL,
                                       wintypes.HANDLE, POINTER(SP_DEVICE_INTERFACE_DATA), c_void_p,
                                       wintypes.DWORD, POINTER(wintypes.DWORD), c_void_p)
SetupDiDestroyDeviceInfoList = _fn(_setupapi, "SetupDiDestroyDeviceInfoList", wintypes.BOOL, wintypes.HANDLE)
CreateFileW = _fn(_kernel32, "CreateFileW", wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                  c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
CloseHandle = _fn(_kernel32, "CloseHandle", wintypes.BOOL, wintypes.HANDLE)
CreateEventW = _fn(_kernel32, "CreateEventW", wintypes.HANDLE, c_void_p, wintypes.BOOL, wintypes.BOOL,
                   wintypes.LPCWSTR)
ResetEvent = _fn(_kernel32, "ResetEvent", wintypes.BOOL, wintypes.HANDLE)
WriteFile = _fn(_kernel32, "WriteFile", wintypes.BOOL, wintypes.HANDLE, c_void_p, wintypes.DWORD,
                POINTER(wintypes.DWORD), POINTER(OVERLAPPED))
ReadFile = _fn(_kernel32, "ReadFile", wintypes.BOOL, wintypes.HANDLE, c_void_p, wintypes.DWORD,
               POINTER(wintypes.DWORD), POINTER(OVERLAPPED))
GetOverlappedResult = _fn(_kernel32, "GetOverlappedResult", wintypes.BOOL, wintypes.HANDLE, POINTER(OVERLAPPED),
                          POINTER(wintypes.DWORD), wintypes.BOOL)
WaitForSingleObject = _fn(_kernel32, "WaitForSingleObject", wintypes.DWORD, wintypes.HANDLE, wintypes.DWORD)
CancelIo = _fn(_kernel32, "CancelIo", wintypes.BOOL, wintypes.HANDLE)


def _device_paths() -> list[str]:
    guid = GUID()
    HidD_GetHidGuid(byref(guid))
    info_set = SetupDiGetClassDevsW(byref(guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if info_set == INVALID_HANDLE:
        return []
    paths = []
    try:
        index = 0
        while True:
            iface = SP_DEVICE_INTERFACE_DATA()
            iface.cbSize = sizeof(SP_DEVICE_INTERFACE_DATA)
            if not SetupDiEnumDeviceInterfaces(info_set, None, byref(guid), index, byref(iface)):
                break
            index += 1
            required = wintypes.DWORD()
            SetupDiGetDeviceInterfaceDetailW(info_set, byref(iface), None, 0, byref(required), None)
            buf = ctypes.create_string_buffer(required.value)
            # SP_DEVICE_INTERFACE_DETAIL_DATA_W: a DWORD cbSize, then the path. cbSize is 8 on 64-bit Windows.
            ctypes.c_uint32.from_buffer(buf).value = 8 if sizeof(c_void_p) == 8 else 6
            if SetupDiGetDeviceInterfaceDetailW(info_set, byref(iface), buf, required, None, None):
                paths.append(ctypes.wstring_at(ctypes.addressof(buf) + 4))
    finally:
        SetupDiDestroyDeviceInfoList(info_set)
    return paths


def _open(path: str, access: int):
    return CreateFileW(path, access, FILE_SHARE_READ_WRITE, None, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)


def _string(getter, handle) -> str:
    buf = ctypes.create_unicode_buffer(256)
    return buf.value if getter(handle, buf, ctypes.sizeof(buf)) else ""


def _caps(handle) -> HIDP_CAPS:
    caps = HIDP_CAPS()
    data = c_void_p()
    if HidD_GetPreparsedData(handle, byref(data)):
        HidP_GetCaps(data, byref(caps))
        HidD_FreePreparsedData(data)
    return caps


def list_devices() -> list[HidInfo]:
    found = []
    for path in _device_paths():
        handle = _open(path, 0)  # no access needed to read attributes, so devices in use still show
        if handle == INVALID_HANDLE:
            continue
        try:
            attrs = HIDD_ATTRIBUTES()
            attrs.Size = sizeof(HIDD_ATTRIBUTES)
            if not HidD_GetAttributes(handle, byref(attrs)):
                continue
            caps = _caps(handle)
            found.append(HidInfo(vendor_id=attrs.VendorID, product_id=attrs.ProductID,
                                 product=_string(HidD_GetProductString, handle),
                                 serial=_string(HidD_GetSerialNumberString, handle),
                                 report_size=max(0, caps.OutputReportByteLength - 1), path=path))
        finally:
            CloseHandle(handle)
    return found


class WindowsHidDevice(HidDevice):
    def __init__(self, info: HidInfo):
        self._handle = _open(info.path, GENERIC_READ | GENERIC_WRITE)
        if self._handle == INVALID_HANDLE:
            raise HidError(f"Could not open {info.name}. Is another program using it?")
        caps = _caps(self._handle)
        self.report_size = max(1, caps.OutputReportByteLength - 1) or info.report_size
        self._in_size = max(caps.InputReportByteLength, self.report_size + 1)
        self._event = CreateEventW(None, True, False, None)

    def _wait(self, overlapped, timeout_ms: int) -> int:
        done = wintypes.DWORD()
        if WaitForSingleObject(self._event, timeout_ms) != WAIT_OBJECT_0:
            CancelIo(self._handle)
            GetOverlappedResult(self._handle, byref(overlapped), byref(done), True)
            raise HidError("The programmer did not answer. Unplug it, plug it back in, and try again.")
        if not GetOverlappedResult(self._handle, byref(overlapped), byref(done), False):
            raise HidError(f"USB error {ctypes.get_last_error()} talking to the programmer.")
        return done.value

    def _io(self, func, buf, length, timeout_ms):
        ResetEvent(self._event)
        overlapped = OVERLAPPED(hEvent=self._event)
        if not func(self._handle, buf, length, None, byref(overlapped)):
            error = ctypes.get_last_error()
            if error != ERROR_IO_PENDING:
                raise HidError(f"USB error {error} talking to the programmer. Was it unplugged?")
        return self._wait(overlapped, timeout_ms)

    def write(self, report: bytes) -> None:
        data = b"\0" + bytes(report).ljust(self.report_size, b"\0")
        buf = ctypes.create_string_buffer(data, len(data))
        self._io(WriteFile, buf, len(data), 2000)

    def read(self, timeout: float) -> bytes:
        buf = ctypes.create_string_buffer(self._in_size)
        count = self._io(ReadFile, buf, self._in_size, int(timeout * 1000))
        return buf.raw[1:count]  # drop the report ID

    def close(self) -> None:
        if self._handle and self._handle != INVALID_HANDLE:
            CloseHandle(self._handle)
            CloseHandle(self._event)
            self._handle = None


def open_device(info: HidInfo) -> HidDevice:
    return WindowsHidDevice(info)
