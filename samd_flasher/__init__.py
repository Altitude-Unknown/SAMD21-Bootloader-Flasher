"""Altitude SAMD21 Bootloader Flasher: installs bootloaders on SAMD21 boards through an Atmel-ICE.

Everything between this app and the chip is written here: USB HID access
(samd_flasher.hid), CMSIS-DAP (dap), SWD (swd), and the SAMD21 flash
controller (samd21). It needs only the Python standard library.
"""

APP_NAME = "Altitude SAMD21 Bootloader Flasher"
VERSION = "1.0.0"
