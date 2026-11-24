# Altitude SAMD21 Bootloader Flasher User Manual

This app flashes Altitude Unknown SAMD21 bootloaders onto custom
ATSAMD21G18A-AU boards using an Atmel-ICE programmer over SWD.

The app talks to the Atmel-ICE directly: there is nothing else to install. It
runs on macOS, Windows, and Raspberry Pi (64-bit Raspberry Pi OS).

## What This App Is For

Use this app when a blank or custom SAMD21 board needs one of the Altitude
Unknown bootloaders installed.

Built-in bootloader choices:

- RC Airplane Transmitter
- RC Airplane Receiver
- YELLOWSTONE
- BOREALIS

After the bootloader is installed, Arduino IDE can upload normal sketches over
USB, as long as the matching Altitude Unknown Arduino board package is also
installed.

## Required Hardware

- Atmel-ICE programmer
- Target board with ATSAMD21G18A-AU microcontroller
- SWD connection from Atmel-ICE to the target board
- USB cable for the Atmel-ICE
- USB cable or external power for the target board

## SWD Wiring

Connect the Atmel-ICE SWD pins to the matching pads or header on the target
board:

- SWDIO
- SWCLK
- RESET
- GND
- VTG / target voltage reference, usually 3.3 V

The target board must be powered while flashing. The Atmel-ICE uses VTG to
sense the target voltage; VTG is not normally the main power source for the
board.

## Download The Flasher App

Download the latest release here:

https://github.com/Altitude-Unknown/SAMD21-Bootloader-Flasher/releases/latest

Use:

- `SAMD21BootloaderFlasher-macOS.zip` for macOS (Apple silicon: M1 or newer)
- `SAMD21BootloaderFlasher-Windows.zip` for Windows 10 or 11
- `SAMD21BootloaderFlasher-Raspberry-Pi-ARM64.zip` for a Raspberry Pi 4 or 5

**macOS:** unzip the app and move it to Applications before opening it.

**Windows:** unzip and run `SAMD21BootloaderFlasher.exe`. No driver is needed:
Windows recognizes the Atmel-ICE on its own.

**Raspberry Pi:** unzip, then in a terminal in that folder run `./install.sh`.
It installs the app in the Programming menu and a USB rule so the Atmel-ICE
can be used without `sudo` (it asks for your password once). Unplug and replug
the Atmel-ICE afterwards.

## Flash A Bootloader

1. Connect the Atmel-ICE to the computer by USB.
2. Connect the Atmel-ICE SWD cable to the target board.
3. Power the target board.
4. Open the SAMD21 Bootloader Flasher app. Step 1, **Programmer**, should say
   the Atmel-ICE is connected. If not, press **Refresh**.
5. In step 2, **Board**, choose the board.
6. Optional: press **Check Board**. The app reads the chip and tells you what
   it is (for example `SAMD21G18A, rev D`), which bootloader is already on it
   (or that it is empty), and whether the bootloader is protected.
7. In step 3, **Install**, leave **Protect the bootloader** checked for normal
   use, and press **Install Bootloader**.
8. Confirm that the correct board is connected.
9. Wait for the message that the bootloader is installed and verified.

The app writes the bootloader at flash address `0x00000000`, reads it back to
verify every byte, protects the bootloader area (8 KB) so a sketch can't
overwrite it, and restarts the board. If the board already had a protected
bootloader, the app turns the protection off first, then back on. The rest of
the flash (any sketch after the bootloader) is not touched.

**Other file…** at the bottom of the Board list flashes any `.bin` or `.hex`
bootloader file. Use it only for testing new bootloaders.

**Save Details…** saves the messages from the last check or install, which
helps when asking for help.

## Check That The Bootloader Worked

After flashing:

1. Disconnect the Atmel-ICE if desired.
2. Connect the target board to the computer over USB.
3. Double-tap reset on the target board.
4. A bootloader USB drive should appear.

Expected bootloader drive names:

- RC Transmitter: `RCTXBOOT`
- RC Receiver: `RCRXBOOT`
- YELLOWSTONE: `YSTONEBOOT`
- BOREALIS: `BOREALBOOT`

The bootloader drive name only appears while the board is in bootloader mode.
When a normal Arduino sketch is running, the USB serial name comes from the
Arduino board package and the sketch firmware.

## Install The Arduino Board Package

The bootloader only handles low-level USB upload mode. To compile and upload
sketches like the lab computer does, Arduino IDE also needs the Altitude
Unknown SAMD board package.

Board package repo:

https://github.com/Altitude-Unknown/Arduino-Altitude-SAMD

This package provides these Arduino boards:

- `Altitude Unknown RC TX M0`
- `Altitude Unknown RC RX M0`
- `Altitude Unknown YELLOWSTONE M0`
- `Altitude Unknown BOREALIS M0`

And these Arduino CLI FQBNs:

- `AltitudeUnknown:samd:altitude_rc_tx_m0`
- `AltitudeUnknown:samd:altitude_rc_rx_m0`
- `AltitudeUnknown:samd:altitude_yellowstone_m0`
- `AltitudeUnknown:samd:altitude_borealis_m0`

### Before You Install: The SAMD Cores

The Altitude Unknown package uses the compiler and upload tools from two
standard board packages. Install them first. In Arduino IDE:

1. Open `File > Preferences` (`Arduino IDE > Settings` on macOS) and add this
   to `Additional boards manager URLs`:

```text
https://adafruit.github.io/arduino-board-index/package_adafruit_index.json
```

2. Open `Tools > Board > Boards Manager` and install:
   - `Arduino SAMD Boards (32-bits ARM Cortex-M0+)` (tested with 1.8.13)
   - `Adafruit SAMD Boards` version `1.7.10`

### macOS Install

1. Download the board package from GitHub:
   https://github.com/Altitude-Unknown/Arduino-Altitude-SAMD
2. Click `Code`.
3. Click `Download ZIP`.
4. Unzip the folder.
5. Open Terminal in the unzipped `Arduino-Altitude-SAMD` folder.
6. Run:

```sh
./install_local.sh
```

7. Restart Arduino IDE.
8. In Arduino IDE, choose:

`Tools > Board > Altitude Unknown SAMD Boards`

### Windows Install

1. Download the board package from GitHub:
   https://github.com/Altitude-Unknown/Arduino-Altitude-SAMD
2. Click `Code`.
3. Click `Download ZIP`.
4. Unzip the folder.
5. Double-click `install_windows.bat` in the unzipped
   `Arduino-Altitude-SAMD` folder. It copies the boards into:

   ```text
   Documents\Arduino\hardware\AltitudeUnknown\samd
   ```

   or into the sketchbook folder set in Arduino IDE, if you changed it. If it
   lists a missing SAMD core, install it as described above.
6. Restart Arduino IDE.
7. In Arduino IDE, choose:

`Tools > Board > Altitude Unknown SAMD Boards`

To update the package later, download the ZIP again and rerun
`install_windows.bat`; it replaces the old copy.

## Upload A Sketch In Arduino IDE

1. Install the bootloader with the flasher app.
2. Install the Altitude Unknown Arduino board package.
3. Connect the target board over USB.
4. Open Arduino IDE.
5. Select the matching board:
   - RC transmitter: `Altitude Unknown RC TX M0`
   - RC receiver: `Altitude Unknown RC RX M0`
   - YELLOWSTONE: `Altitude Unknown YELLOWSTONE M0`
   - BOREALIS: `Altitude Unknown BOREALIS M0`
6. Select the serial port for the board.
7. Upload the sketch normally.

If the board does not show up for upload, double-tap reset to force bootloader
mode, then try uploading again.

## Troubleshooting

### No programmer found

- Check the Atmel-ICE's USB cable (try another port or cable).
- Close any other program that uses the Atmel-ICE (Microchip Studio, MPLAB X,
  OpenOCD), then press **Refresh**.
- Raspberry Pi: if the app says it has no permission, run `./install.sh` from
  the download again, then unplug and replug the Atmel-ICE.

### The programmer cannot reach the chip

Check:

- Target board is powered
- The SWD cable is on the right header, the right way round
- SWDIO and SWCLK are not swapped
- RESET is connected
- GND is connected
- VTG / voltage reference is connected to the target's 3.3 V rail

If a sketch on the board has turned off the debug pins or put the chip to
sleep, the app holds the chip in reset while it connects. That needs the RESET
wire.

### The chip's security bit is set

A chip with its security bit set can't be read or programmed until it is
completely erased. The app asks before it does that, because the erase also
deletes the sketch on the board.

### Verify failed

The bytes read back from the chip don't match the bootloader. Flash again. If
it keeps failing, check the board's power supply and the SWD wiring, which
should be short.

### Arduino IDE still shows an Adafruit board name

The bootloader name and Arduino sketch USB name are separate.

Install the Altitude Unknown Arduino board package and compile/upload using the
matching Altitude Unknown board entry. Once a sketch compiled for that board is
running, the USB serial device should use the Altitude Unknown product name.

### Compiling fails with a missing compiler, CMSIS, or bossac

The SAMD cores are not installed. Install `Arduino SAMD Boards` and
`Adafruit SAMD Boards` 1.7.10 as described in
[Before You Install: The SAMD Cores](#before-you-install-the-samd-cores),
then restart Arduino IDE.

### The board package does not appear in Arduino IDE

Restart Arduino IDE after installing the board package. If it still does not
appear, check that the folder path is exactly:

macOS:

```text
~/Documents/Arduino/hardware/AltitudeUnknown/samd
```

Windows:

```text
Documents\Arduino\hardware\AltitudeUnknown\samd
```

The `samd` folder should contain files such as `boards.txt`, `platform.txt`,
and `programmers.txt`.

## Notes For Maintainers

The app does not use OpenOCD or any other programming tool. Everything
between the app and the chip is in `samd_flasher/`, written for this project
with only the Python standard library:

- `hid/`: USB HID access for macOS (IOKit), Windows (hid.dll), and Linux
  (`/dev/hidraw`)
- `dap.py`: the CMSIS-DAP commands the Atmel-ICE understands
- `swd.py`: Arm SWD debug port and memory access
- `samd21.py`: the SAMD21 chip: identify it, halt it, and program its flash
  through the NVM controller, including the BOOTPROT fuse
- `jobs.py`: the steps the window and the command line run

The same steps run from a terminal, which helps with lab setup and testing:

```sh
python3 bootloader_flasher.py list
python3 bootloader_flasher.py check
python3 bootloader_flasher.py flash rc_tx
python3 bootloader_flasher.py read backup.bin
```

`tests/` runs the whole flashing process against a simulated Atmel-ICE and
SAMD21: `python3 -m unittest discover -s tests`.

The bootloader images are in `bootloaders/`, listed in `bootloaders/boards.json`
with SHA-256 checksums. They are built from the MIT-licensed uf2-samdx1 source;
keep its license and notices (in `bootloaders/`) with them when sharing.

The current USB VID/PID values in the bootloaders and the Arduino board package
are lab placeholders. Replace them with assigned USB IDs before broad public
distribution.

To release, set `VERSION` in `samd_flasher/__init__.py`, update
`RELEASE_NOTES.md`, and push a tag `v<VERSION>`. The workflow tests, builds,
self-tests, signs, and publishes the three apps.
