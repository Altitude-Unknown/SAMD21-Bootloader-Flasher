#!/usr/bin/env python3
"""Tests for the flasher, using a simulated Atmel-ICE and SAMD21 (tests/fake_target.py)."""

from __future__ import annotations

import hashlib
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fake_target import BOOTPROT_SIZES, FakeProbe, FakeSamd21  # noqa: E402
from samd_flasher import hid, jobs  # noqa: E402
from samd_flasher.hid._linux import output_report_size  # noqa: E402
from samd_flasher.images import ImageError, load_boards, parse_hex  # noqa: E402

PROBE = hid.HidInfo(0x03EB, 0x2141, "Atmel-ICE CMSIS-DAP", "J41800012345", 512, "test")
BOARDS = load_boards()


def image(size=8192, seed=1) -> bytes:
    out = bytearray()
    while len(out) < size:
        out += hashlib.sha256(bytes([seed]) + len(out).to_bytes(4, "little")).digest()
    return bytes(out[:size])


class Rig:
    """Patch the USB layer so jobs.* talk to a fake probe and chip."""

    def __init__(self, chip: FakeSamd21, report_size=512):
        self.chip = chip
        self.probe = FakeProbe(chip, report_size)
        self.log: list[str] = []
        self.progress: list[float] = []
        info = PROBE if report_size == 512 else PROBE.__class__(**{**PROBE.__dict__, "report_size": report_size})
        self.patches = [mock.patch.object(hid, "find_probes", lambda: [info]),
                        mock.patch.object(hid, "open_device", lambda _info: self.probe)]

    def __enter__(self):
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self.patches:
            p.stop()

    def flash(self, data, **kwargs):
        jobs.flash_bootloader(data, log=self.log.append, progress=self.progress.append, **kwargs)

    def check(self):
        return jobs.check_board(BOARDS, log=self.log.append)


class FlashTests(unittest.TestCase):
    def test_blank_chip_flash_verify_protect_run(self):
        chip = FakeSamd21()
        app = image(4096, seed=9)
        chip.flash[0x2000:0x2000 + len(app)] = app  # a program after the bootloader must survive
        data = BOARDS[0].image()
        with Rig(chip) as rig:
            rig.flash(data)
        self.assertEqual(bytes(chip.flash[:len(data)]), data)
        self.assertEqual(bytes(chip.flash[0x2000:0x2000 + len(app)]), app)
        self.assertEqual(chip.user_row[0] & 7, 2)  # BOOTPROT = 8 KB
        self.assertEqual(chip.user_row[1:8], FakeSamd21().user_row[1:8])  # other fuses untouched
        self.assertFalse(chip.halted)  # left running
        self.assertFalse(chip.debugen)
        self.assertEqual(rig.progress[-1], 1.0)
        self.assertTrue(rig.probe.closed)

    def test_replaces_protected_bootloader(self):
        chip = FakeSamd21(bootprot=2)
        chip.flash[:8192] = image(seed=3)
        data = image(seed=4)
        with Rig(chip) as rig:
            rig.flash(data)
        self.assertEqual(bytes(chip.flash[:8192]), data)
        self.assertEqual(chip.user_row[0] & 7, 2)
        self.assertTrue(any("Turning off bootloader protection (8 KB)" in line for line in rig.log))

    def test_no_protect_leaves_bootprot_off(self):
        chip = FakeSamd21(bootprot=2)
        with Rig(chip) as rig:
            rig.flash(image(), protect=False)
        self.assertEqual(chip.user_row[0] & 7, 7)

    def test_locked_region_is_unlocked(self):
        chip = FakeSamd21(region_locks=0xFFFE)  # region 0 (first 16 KB) locked by fuse
        with Rig(chip) as rig:
            rig.flash(image())
        self.assertEqual(bytes(chip.flash[:8192]), image())
        self.assertIn(0x41, chip.commands)  # unlock region

    def test_small_packets_and_1kb_wrap(self):
        chip = FakeSamd21()
        data = image(16384, seed=5)
        with Rig(chip, report_size=64) as rig:
            rig.flash(data, protect=True)
        self.assertEqual(bytes(chip.flash[:16384]), data)
        self.assertEqual(chip.user_row[0] & 7, 1)  # 16 KB protection for a 16 KB image

    def test_verify_failure_is_reported(self):
        chip = FakeSamd21(stuck=(0x123, 0x00))
        data = bytes([0xAA]) * 8192
        with Rig(chip) as rig, self.assertRaises(jobs.FlashError) as ctx:
            rig.flash(data)
        self.assertIn("0x00123", str(ctx.exception))
        self.assertEqual(chip.user_row[0] & 7, 7)  # never protected a bad write

    def test_locked_chip_needs_permission_to_erase(self):
        chip = FakeSamd21(protected=True)
        chip.flash[:4] = b"\x12\x34\x56\x78"
        with Rig(chip) as rig:
            with self.assertRaises(jobs.NeedsChipErase):
                rig.flash(image())
            self.assertEqual(bytes(chip.flash[:4]), b"\x12\x34\x56\x78")
            rig.flash(image(), allow_chip_erase=True)
        self.assertFalse(chip.protected)
        self.assertEqual(bytes(chip.flash[:8192]), image())

    def test_connects_under_reset_when_swd_is_disabled(self):
        chip = FakeSamd21(swd_disabled=True)
        with Rig(chip) as rig:
            rig.flash(image())
        self.assertEqual(bytes(chip.flash[:8192]), image())
        self.assertTrue(any("holding it in reset" in line for line in rig.log))

    def test_no_board_answering(self):
        chip = FakeSamd21(swd_disabled=True)
        with Rig(chip) as rig:
            with mock.patch("samd_flasher.jobs.connect_under_reset", side_effect=jobs.d.TransferError(7, 0)):
                with self.assertRaises(jobs.FlashError) as ctx:
                    rig.flash(image())
        self.assertIn("cannot reach the chip", str(ctx.exception))

    def test_no_programmer(self):
        with mock.patch.object(hid, "find_probes", lambda: []):
            with self.assertRaises(jobs.FlashError) as ctx:
                jobs.flash_bootloader(image())
        self.assertIn("No programmer found", str(ctx.exception))


class CheckTests(unittest.TestCase):
    def test_recognizes_installed_bootloader(self):
        chip = FakeSamd21(bootprot=2)
        board = BOARDS[2]
        chip.flash[:8192] = board.image()
        with Rig(chip) as rig:
            report = rig.check()
        self.assertIn(board.name, report.installed)
        self.assertEqual(report.protected_size, 8192)
        self.assertEqual(report.chip.name, "SAMD21G18A")
        self.assertEqual(report.chip.flash_size, 256 * 1024)
        self.assertFalse(chip.halted)

    def test_empty_and_unknown(self):
        with Rig(FakeSamd21()) as rig:
            self.assertEqual(rig.check().installed, "empty")
        chip = FakeSamd21()
        chip.flash[:8192] = image(seed=8)
        with Rig(chip) as rig:
            self.assertIn("unknown", rig.check().installed)

    def test_locked_chip(self):
        with Rig(FakeSamd21(protected=True)) as rig:
            report = rig.check()
        self.assertTrue(report.chip.protected)
        self.assertIn("security bit", report.summary())


class ImageTests(unittest.TestCase):
    def test_bundled_boards_match_checksums(self):
        self.assertEqual([b.id for b in BOARDS], ["rc_tx", "rc_rx", "yellowstone", "borealis"])
        for board in BOARDS:
            self.assertEqual(len(board.image()), 8192)

    def test_hex_round_trip(self):
        data = image(300, seed=2)
        lines = [":020000040000FA"]
        for addr in range(0, len(data), 16):
            chunk = data[addr:addr + 16]
            rec = bytes([len(chunk), addr >> 8, addr & 0xFF, 0]) + chunk
            lines.append(":" + (rec + bytes([(-sum(rec)) & 0xFF])).hex().upper())
        lines.append(":00000001FF")
        self.assertEqual(parse_hex("\n".join(lines)), data)

    def test_hex_errors(self):
        with self.assertRaises(ImageError):
            parse_hex(":0100000000FE\n")  # bad checksum
        with self.assertRaises(ImageError):
            parse_hex(":020000040001F9\n:0100000055AA\n:00000001FF")  # starts at 0x10000

    def test_bootprot_choice(self):
        from samd_flasher.samd21 import bootprot_for
        self.assertEqual(bootprot_for(8192), 2)
        self.assertEqual(bootprot_for(5000), 2)
        self.assertEqual(bootprot_for(512), 6)
        self.assertIsNone(bootprot_for(40000))
        self.assertEqual(BOOTPROT_SIZES[bootprot_for(8192)], 8192)


class HidTests(unittest.TestCase):
    def test_report_descriptor_size(self):
        # Vendor page, 64-byte input and output reports (a typical CMSIS-DAP v1 descriptor)
        desc = bytes.fromhex("0600FF0901A1011500260000750895400901810295400901910295010901B10200C0")
        self.assertEqual(output_report_size(desc), 64)
        big = desc.replace(bytes.fromhex("95400901910295"), bytes.fromhex("9600020901910295"))
        self.assertEqual(output_report_size(big), 512)

    def test_probe_filter(self):
        self.assertTrue(hid.is_probe(PROBE))
        self.assertTrue(hid.is_probe(hid.HidInfo(0x0D28, 0x0204, "DAPLink CMSIS-DAP", "", 64, "x")))
        self.assertFalse(hid.is_probe(hid.HidInfo(0x05AC, 0x0341, "Apple Internal Keyboard", "", 1, "x")))


if __name__ == "__main__":
    unittest.main()
