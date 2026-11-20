# Altitude SAMD21 Bootloader Flasher User Manual

This app flashes Altitude Unknown SAMD21 bootloaders onto custom
ATSAMD21G18A-AU boards using an Atmel-ICE programmer over SWD.

The released macOS and Windows apps include OpenOCD, so normal users do not
need to install OpenOCD separately.

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

- `SAMD21BootloaderFlasher-macOS.zip` for macOS
- `SAMD21BootloaderFlasher-Windows.zip` for Windows

On macOS, unzip the app and move it to a normal folder such as Applications or
Documents before running it. Running directly from Downloads can sometimes make
macOS apply extra security restrictions.

## Flash A Bootloader

1. Connect the Atmel-ICE to the computer by USB.
2. Connect the Atmel-ICE SWD cable to the target board.
3. Power the target board.
4. Open the SAMD21 Bootloader Flasher app.
5. Choose the correct board from the Board menu.
6. Click `Use Built-In`.
7. Leave `Verify` checked.
8. Leave `Protect 8 KB bootloader` checked for normal use.
9. Click `Flash Bootloader`.
10. Confirm that the correct board is connected.
11. Wait for `Flash complete`.

The app writes the bootloader at flash address `0x00000000`, verifies it, then
sets the SAMD21 bootloader protection area to 8 KB.

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

### The flasher cannot connect to the target

Check:

- Target board is powered
- Atmel-ICE USB cable is connected
- SWDIO and SWCLK are not swapped
- RESET is connected
- GND is connected
- VTG / voltage reference is connected to the target's 3.3 V rail

### The app says flashing failed but verify passed

If programming and verify completed but reset failed, the bootloader may still
be written correctly. Disconnect and reconnect the board, then double-tap reset
to check for the bootloader drive.

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

The release workflow bundles OpenOCD into the packaged app before PyInstaller
runs. The app looks for OpenOCD at:

```text
tools/openocd/bin/openocd
```

or on Windows:

```text
tools/openocd/bin/openocd.exe
```

When bundled OpenOCD is present, the app also points OpenOCD at the bundled
config scripts so commands like `interface/cmsis-dap.cfg` and
`target/at91samdXX.cfg` work without a separate OpenOCD install.

The current USB VID/PID values in the Arduino board package are lab
placeholders. Replace them with assigned USB IDs before broad public
distribution.
