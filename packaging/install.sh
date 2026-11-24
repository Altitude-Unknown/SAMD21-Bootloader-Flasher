#!/bin/sh
# Install the Altitude SAMD21 Bootloader Flasher on a Raspberry Pi (64-bit Raspberry Pi OS):
# copies the app to ~/.local/bin, adds it to the Programming menu, and installs a
# udev rule so the Atmel-ICE can be used without sudo.
set -e
cd "$(dirname "$0")"
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/.local/share/icons"
cp "SAMD21BootloaderFlasher" "$HOME/.local/bin/samd21-bootloader-flasher"
chmod +x "$HOME/.local/bin/samd21-bootloader-flasher"
cp samd21-bootloader-flasher.png "$HOME/.local/share/icons/samd21-bootloader-flasher.png"
cat > "$HOME/.local/share/applications/samd21-bootloader-flasher.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=SAMD21 Bootloader Flasher
Comment=Install bootloaders on SAMD21 boards with an Atmel-ICE
Exec=$HOME/.local/bin/samd21-bootloader-flasher
Icon=$HOME/.local/share/icons/samd21-bootloader-flasher.png
Categories=Development;Education;
Terminal=false
DESKTOP
echo "Installing the USB rule for the Atmel-ICE (asks for your password)..."
sudo cp 99-altitude-samd-flasher.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
echo "Installed. Unplug and replug the Atmel-ICE, then open the app from the menu (Programming),"
echo "or run: ~/.local/bin/samd21-bootloader-flasher"
