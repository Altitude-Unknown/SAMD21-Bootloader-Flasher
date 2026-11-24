**Altitude SAMD21 Bootloader Flasher 1.0.0** is a rewrite: the app now talks
to the Atmel-ICE directly instead of running OpenOCD, so the download is much
smaller and there is nothing else to install.

## New

- **New bootloaders.** The built-in bootloaders are the Altitude SAMD21
  Bootloader 1.0.0, written from scratch for these boards. They work the same way
  (Arduino uploads, double-tap reset, the UF2 drive), and the RC transmitter,
  receiver and YELLOWSTONE now have their own USB IDs (1209:A5C0, A5C1, A5C2)
  instead of lab placeholders. Update the Altitude Arduino board package at the
  same time.
- **Raspberry Pi** version (64-bit Raspberry Pi OS), with an installer that
  sets up USB access for the Atmel-ICE.
- **Check Board** tells you which chip is connected, which bootloader is on it
  (or that it is empty), and whether the bootloader is protected.
- Boards whose program has turned off the debug pins or put the chip to sleep
  can still be flashed: the app holds the chip in reset while it connects.
- Chips with the security bit set are detected; the app asks before erasing
  them.
- Every install is verified byte by byte, and the bootloader files are checked
  against their checksums before flashing.
- Clearer messages for wiring, power, and USB problems, and **Save Details…**
  to share them.

## Download

| Computer | File |
| --- | --- |
| Mac (Apple silicon: M1 or newer) | `SAMD21BootloaderFlasher-macOS.zip` |
| Windows 10 or 11 | `SAMD21BootloaderFlasher-Windows.zip` |
| Raspberry Pi 4 or 5 (64-bit Raspberry Pi OS) | `SAMD21BootloaderFlasher-Raspberry-Pi-ARM64.zip` |

See the [user manual](USER_MANUAL.md) for wiring and step-by-step use.
