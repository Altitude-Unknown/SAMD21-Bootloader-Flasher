# Bootloaders

The bootloader images this app installs, one per board, listed in
`boards.json` with their SHA-256 checksums (the app refuses an image whose
checksum does not match).

They are the [Altitude SAMD21 Bootloader](https://github.com/Altitude-Unknown/Altitude-SAMD21-Bootloader)
1.0.0, written from scratch for these boards (MIT license): Arduino uploads
over USB serial and a UF2 drag-and-drop drive. Each image is padded to the full
8 KB bootloader area so installing it also clears any older bootloader.

| Board | USB ID | Drive |
| --- | --- | --- |
| RC Airplane Transmitter | 1209:A5C0 | RCTXBOOT |
| RC Airplane Receiver | 1209:A5C1 | RCRXBOOT |
| YELLOWSTONE | 1209:A5C2 | YSTONEBOOT |
| BOREALIS | 03EB:2402 (lab placeholder) | BOREALBOOT |
