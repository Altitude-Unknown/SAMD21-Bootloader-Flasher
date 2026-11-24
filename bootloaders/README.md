# Bootloaders

The bootloader images this app installs, one per board, listed in
`boards.json` with their SHA-256 checksums (the app refuses an image whose
checksum does not match).

They are built from Altitude Unknown board definitions in the
[uf2-samdx1](https://github.com/adafruit/uf2-samdx1) UF2 bootloader source
(`Bootloaders/uf2-samdx1` in the BOREALIS workspace). That source is MIT
licensed: its license and third-party notices are in this folder and must be
kept with the images when they are shared.

The flasher app itself does not use any of that code.
