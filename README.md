# Altitude SAMD21 Bootloader Flasher

A desktop app that installs the bootloader on a new SAMD21 board through an
Atmel-ICE programmer, so the board can be programmed over USB from Arduino
from then on. It runs on macOS, Windows, and Raspberry Pi.

Built-in bootloaders:

- RC Airplane Transmitter
- RC Airplane Receiver
- YELLOWSTONE
- BOREALIS

**Check Board** reads the chip and says which bootloader (if any) is on it.
**Install Bootloader** writes, verifies, and protects it. Any `.bin` or `.hex`
bootloader file can also be flashed for testing.

## How it works

The app talks to the Atmel-ICE itself, with code written for this project and
only the Python standard library: USB HID access for each operating system,
the CMSIS-DAP commands the Atmel-ICE understands, Arm SWD memory access, and
the SAMD21's flash controller. There is no OpenOCD and nothing else to install.
See [USER_MANUAL.md](USER_MANUAL.md#notes-for-maintainers) for the layout.

## User Manual

See [USER_MANUAL.md](USER_MANUAL.md) for downloading, wiring, flashing,
troubleshooting, and the matching Arduino board package.

## Run From Source

Python 3.10 or newer with Tkinter (included with the python.org installers;
on Raspberry Pi OS, `sudo apt install python3-tk`):

```sh
python3 bootloader_flasher.py          # the window
python3 bootloader_flasher.py --help   # the command line
python3 -m unittest discover -s tests  # tests with a simulated Atmel-ICE and SAMD21
```

## Bootloader images

The images in `bootloaders/` are built from the MIT-licensed
[uf2-samdx1](https://github.com/adafruit/uf2-samdx1) UF2 bootloader with
Altitude Unknown board definitions. Their license and notices are in that
folder and must stay with them when they are shared. The app's own code does
not use any of it.
