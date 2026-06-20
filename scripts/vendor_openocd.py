#!/usr/bin/env python3
"""Copy OpenOCD into tools/openocd for PyInstaller packaging."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


SYSTEM_DYLIB_PREFIXES = (
    "/System/Library/",
    "/usr/lib/",
)


def run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True)


def copytree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def find_openocd(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if path.is_file():
            return path
        raise SystemExit(f"OpenOCD executable was not found: {path}")

    name = "openocd.exe" if sys.platform == "win32" else "openocd"
    found = shutil.which(name)
    if found:
        return Path(found)
    raise SystemExit("OpenOCD was not found on PATH.")


def find_scripts_dir(openocd: Path, explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit)
        if path.is_dir():
            return path
        raise SystemExit(f"OpenOCD scripts directory was not found: {path}")

    candidates = [
        openocd.parent.parent / "share" / "openocd" / "scripts",
        Path("/opt/homebrew/share/openocd/scripts"),
        Path("/usr/local/share/openocd/scripts"),
        Path("C:/Program Files/OpenOCD/share/openocd/scripts"),
        Path("C:/Program Files (x86)/OpenOCD/share/openocd/scripts"),
        Path("C:/tools/openocd/share/openocd/scripts"),
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise SystemExit("OpenOCD scripts directory was not found.")


def mac_dylibs(binary: Path) -> list[Path]:
    deps: list[Path] = []
    for line in run(["otool", "-L", str(binary)]).splitlines()[1:]:
        dep = line.strip().split(" ", 1)[0]
        if dep.startswith("@"):
            continue
        if dep.startswith(SYSTEM_DYLIB_PREFIXES):
            continue
        path = Path(dep)
        if path.is_file():
            deps.append(path)
    return deps


def vendor_macos_dylibs(openocd: Path, dst_root: Path) -> None:
    lib_dir = dst_root / "lib"
    lib_dir.mkdir(parents=True, exist_ok=True)

    copied: dict[Path, Path] = {}
    queue = mac_dylibs(openocd)
    while queue:
        source = queue.pop(0).resolve()
        if source in copied:
            continue

        dest = lib_dir / source.name
        shutil.copy2(source, dest)
        copied[source] = dest
        queue.extend(mac_dylibs(dest))

    for dest in copied.values():
        subprocess.run(["install_name_tool", "-id", f"@loader_path/../lib/{dest.name}", str(dest)], check=False)

    for binary in [openocd, *copied.values()]:
        for source, dest in copied.items():
            subprocess.run(
                ["install_name_tool", "-change", str(source), f"@loader_path/../lib/{dest.name}", str(binary)],
                check=False,
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--openocd", help="Path to the openocd executable.")
    parser.add_argument("--scripts", help="Path to OpenOCD's scripts directory.")
    parser.add_argument("--output", default="tools/openocd", help="Destination folder inside the project.")
    args = parser.parse_args()

    openocd = find_openocd(args.openocd).resolve()
    scripts = find_scripts_dir(openocd, args.scripts).resolve()
    output = Path(args.output).resolve()

    if output.exists():
        shutil.rmtree(output)
    bin_dir = output / "bin"
    bin_dir.mkdir(parents=True)

    openocd_dest = bin_dir / openocd.name
    shutil.copy2(openocd, openocd_dest)
    os.chmod(openocd_dest, 0o755)
    copytree(scripts, output / "share" / "openocd" / "scripts")

    if sys.platform == "darwin":
        vendor_macos_dylibs(openocd_dest, output)

    print(f"Vendored OpenOCD executable: {openocd_dest}")
    print(f"Vendored OpenOCD scripts: {output / 'share' / 'openocd' / 'scripts'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
