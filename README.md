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

## Requirements

- Atmel-ICE programmer connected by USB
- Target SAMD21 board connected over SWD
- OpenOCD installed or bundled beside the app

On macOS with Homebrew:

```sh
brew install open-ocd
```

The app also accepts an `OPENOCD_PATH` environment variable or lets you browse
to the `openocd` executable manually.

## Run From Source

```sh
python3 bootloader_flasher.py
```

## Flashing Notes

The first-time bootloader files are the plain `.bin` files. The app flashes
them at address `0x00000000`, verifies by default, and can set the SAMD21
bootloader protection fuse to 8 KB.

Use the built-in board choices for normal work. Use Browse only when testing a
new bootloader file.
