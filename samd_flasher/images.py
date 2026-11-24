"""Firmware images: the bundled board bootloaders, and .bin / Intel .hex files."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path


class ImageError(Exception):
    pass


def resource_dir() -> Path:
    """Folder holding bootloaders/ and assets/ (inside the packaged app, or the source checkout)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Board:
    id: str
    name: str
    file: str
    sha256: str
    version: str
    board_id: str
    usb_name: str
    drive: str

    @property
    def path(self) -> Path:
        return resource_dir() / "bootloaders" / self.file

    def image(self) -> bytes:
        data = self.path.read_bytes()
        if hashlib.sha256(data).hexdigest() != self.sha256:
            raise ImageError(f"The {self.name} bootloader file is damaged (checksum mismatch). "
                             "Download the app again.")
        return data


def load_boards() -> list[Board]:
    manifest = json.loads((resource_dir() / "bootloaders" / "boards.json").read_text(encoding="utf-8"))
    return [Board(**entry) for entry in manifest["boards"]]


def load_file(path: str | Path) -> bytes:
    """A firmware image that starts at address 0, from a .bin or Intel .hex file."""
    path = Path(path)
    if path.suffix.lower() in (".hex", ".ihex"):
        return parse_hex(path.read_text(encoding="ascii", errors="replace"))
    data = path.read_bytes()
    if not data:
        raise ImageError(f"{path.name} is empty.")
    return data


def parse_hex(text: str) -> bytes:
    """Intel HEX to a flat image starting at address 0; gaps are filled with 0xFF (erased flash)."""
    chunks: dict[int, bytes] = {}
    base = 0
    for number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        if not line.startswith(":"):
            raise ImageError(f"Line {number} of the .hex file is not a hex record.")
        try:
            record = bytes.fromhex(line[1:])
        except ValueError:
            raise ImageError(f"Line {number} of the .hex file has characters that are not hex digits.") from None
        if len(record) < 5 or len(record) != record[0] + 5:
            raise ImageError(f"Line {number} of the .hex file has the wrong length.")
        if sum(record) & 0xFF:
            raise ImageError(f"Line {number} of the .hex file fails its checksum.")
        length, address, kind, payload = record[0], int.from_bytes(record[1:3], "big"), record[3], record[4:-1]
        if kind == 0x00:
            chunks[base + address] = payload
        elif kind == 0x01:
            break
        elif kind == 0x02:
            base = int.from_bytes(payload, "big") << 4
        elif kind == 0x04:
            base = int.from_bytes(payload, "big") << 16
        # 0x03 and 0x05 are start addresses, which flashing does not need.
    if not chunks:
        raise ImageError("The .hex file has no data.")
    end = max(addr + len(data) for addr, data in chunks.items())
    if min(chunks) != 0:
        raise ImageError(f"The .hex file starts at 0x{min(chunks):X}; a bootloader must start at address 0.")
    image = bytearray(b"\xff" * end)
    for addr, data in chunks.items():
        image[addr:addr + len(data)] = data
    return bytes(image)


def identify(installed: bytes, boards: list[Board]) -> Board | None:
    """Which bundled bootloader a chip's first bytes match exactly, if any."""
    for board in boards:
        try:
            image = board.image()
        except (OSError, ImageError):
            continue
        if installed[:len(image)] == image:
            return board
    return None
