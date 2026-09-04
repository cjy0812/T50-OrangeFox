#!/usr/bin/env python3
"""Analyze OrangeFox CI vendor_boot ramdisk."""

import sys, os, subprocess

sys.path.insert(0, "/mnt/g/GitHub/T50/T50-OrangeFox")
from repack_vendor_boot import parse_vb_v4, extract_fragment_data, extract_cpio_gz

FOX = "/mnt/g/GitHub/T50/T50-OrangeFox/ci_artifacts/vendor_boot.img"
OUT = "/tmp/t50_fox"


def main():
    vb = parse_vb_v4(FOX)
    frags = vb["fragments"]
    print(f"Fragments: {len(frags)}")
    for i, f in enumerate(frags):
        print(f"  [{i}] name={f.get('name', '?')} size={f.get('ramdisk_size', 0)}")

    # Extract RECOVERY fragment (OrangeFox recovery content)
    subprocess.run(["rm", "-rf", OUT], capture_output=True)
    os.makedirs(OUT, exist_ok=True)

    # Try RECOVERY fragment first (index 1), fall back to PLATFORM (index 0)
    for idx in [1, 0]:
        if idx < len(frags):
            try:
                extract_cpio_gz(extract_fragment_data(vb, idx), OUT, f"FRAG{idx}")
                break
            except:
                continue

    # Search for adbd service definition
    print(f"\n=== Searching for adbd service ===")
    for root, dirs, files in os.walk(OUT):
        for fn in files:
            if fn.endswith(".rc"):
                fp = os.path.join(root, fn)
                with open(fp, "r", errors="ignore") as f:
                    content = f.read()
                if "adbd" in content:
                    rel = fp.replace(OUT, "")
                    print(f"\n--- {rel} ---")
                    for line in content.split("\n"):
                        if "adbd" in line.lower() or "service" in line.lower()[:10]:
                            print(f"  {line}")

    # Check default.prop
    print(f"\n=== Key properties ===")
    for root, dirs, files in os.walk(OUT):
        for fn in files:
            if fn.endswith(".prop"):
                fp = os.path.join(root, fn)
                with open(fp, "r", errors="ignore") as f:
                    for line in f:
                        low = line.lower()
                        if any(
                            k in low
                            for k in [
                                "ro.sf.",
                                "rotation",
                                "pixel",
                                "minui",
                                "display",
                                "hwrotation",
                                "density",
                            ]
                        ):
                            rel = fp.replace(OUT, "")
                            print(f"  {rel}: {line.strip()}")

    # Check init.recovery RC
    print(f"\n=== init.recovery RC files ===")
    for root, dirs, files in os.walk(OUT):
        for fn in files:
            if "init.recovery" in fn or "init.usb" in fn:
                fp = os.path.join(root, fn)
                rel = fp.replace(OUT, "")
                print(f"\n--- {rel} ---")
                with open(fp, "r", errors="ignore") as f:
                    print(f.read()[:2000])


if __name__ == "__main__":
    main()
