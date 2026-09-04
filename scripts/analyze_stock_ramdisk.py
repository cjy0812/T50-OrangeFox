#!/usr/bin/env python3
"""Analyze stock vendor_boot ramdisk for display/touch/rotation/ADB clues."""

import os
import subprocess
import sys

sys.path.insert(0, "/mnt/g/GitHub/T50/T50-OrangeFox")
from repack_vendor_boot import extract_cpio_gz, extract_fragment_data, parse_vb_v4

STOCK = "/mnt/g/GitHub/T50/T50-OrangeFox/Device_Tree/Raw_img/vendor_boot_a.bin"
OUT = "/tmp/t50_stock"


def main():
    vb = parse_vb_v4(STOCK)
    frags = vb["fragments"]
    print(f"Fragments: {len(frags)}")
    for i, f in enumerate(frags):
        print(f"  [{i}] name={f.get('name', '?')} size={f.get('ramdisk_size', 0)}")

    # Extract PLATFORM
    subprocess.run(["rm", "-rf", OUT], capture_output=True)
    os.makedirs(OUT, exist_ok=True)
    extract_cpio_gz(extract_fragment_data(vb, 0), OUT, "PLATFORM")

    # List top-level
    print("\n=== Top-level dirs ===")
    for d in sorted(os.listdir(OUT)):
        print(f"  {d}")

    # Search properties
    print("\n=== Key properties ===")
    for root, dirs, files in os.walk(OUT):
        for fn in files:
            fp = os.path.join(root, fn)
            if not fn.endswith(".prop") and not fn.endswith(".rc"):
                continue
            try:
                with open(fp, errors="ignore") as f:
                    for line in f:
                        low = line.lower()
                        if any(
                            k in low
                            for k in [
                                "ro.sf.",
                                "rotation",
                                "hwrotation",
                                "display",
                                "pixel",
                                "fb",
                                "touch",
                                "goodix",
                                "musb",
                                "usb.controller",
                                "adbd",
                                "lcm",
                                "panel",
                            ]
                        ):
                            rel = fp.replace(OUT, "")
                            print(f"  {rel}: {line.strip()}")
            except Exception:
                pass

    # Show init.recovery RC files
    print("\n=== init.recovery RC files ===")
    for root, dirs, files in os.walk(OUT):
        for fn in files:
            if "init.recovery" in fn or "init.usb" in fn:
                fp = os.path.join(root, fn)
                rel = fp.replace(OUT, "")
                print(f"\n--- {rel} ---")
                with open(fp, errors="ignore") as f:
                    print(f.read()[:2000])

    # Show any hw-*.rc files
    print("\n=== hw init RC files ===")
    for root, dirs, files in os.walk(OUT):
        for fn in files:
            if fn.startswith("hw-") and fn.endswith(".rc"):
                fp = os.path.join(root, fn)
                rel = fp.replace(OUT, "")
                print(f"\n--- {rel} ---")
                with open(fp, errors="ignore") as f:
                    print(f.read()[:1000])


if __name__ == "__main__":
    main()
