# Altitude SAMD21 Bootloader Flasher

Small desktop app for flashing custom SAMD21 bootloaders with an Atmel-ICE
programmer over SWD.

The app is a simple GUI wrapper around OpenOCD. It includes built-in bootloader
choices for:

- RC Airplane Transmitter
- RC Airplane Receiver
- YELLOWSTONE
- BOREALIS

It can also browse for any `.bin` or `.hex` file.

## User Manual

See [USER_MANUAL.md](USER_MANUAL.md) for step-by-step flashing instructions,
Atmel-ICE wiring notes, troubleshooting, and the matching Arduino board package
install instructions.

## Requirements For Released Apps

- Atmel-ICE programmer connected by USB
- Target SAMD21 board connected over SWD

The macOS and Windows release builds bundle OpenOCD inside the app package, so
normal users should not need to install OpenOCD separately.

## Run From Source

Running from source still needs OpenOCD installed on the computer.

On macOS with Homebrew:

```sh
brew install open-ocd
```

The app also accepts an `OPENOCD_PATH` environment variable or lets you browse
to the `openocd` executable manually.

```sh
python3 bootloader_flasher.py
```

## Build Notes

The release workflow runs `scripts/vendor_openocd.py` before PyInstaller. That
copies OpenOCD into `tools/openocd`, including the OpenOCD script/config files
used by `interface/cmsis-dap.cfg` and `target/at91samdXX.cfg`.

## Flashing Notes

The first-time bootloader files are the plain `.bin` files. The app flashes
them at address `0x00000000`, verifies by default, and can set the SAMD21
bootloader protection fuse to 8 KB.

Use the built-in board choices for normal work. Use Browse only when testing a
new bootloader file.
