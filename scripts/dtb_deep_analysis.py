#!/usr/bin/env python3
"""Deep DTB analysis: find panel, touch, rotation, framebuffer, pixel format."""

import os
import struct
import subprocess
import sys
import tempfile


def find_dtbs(data):
    dtbs = []
    for i in range(0, len(data) - 4, 4):
        if struct.unpack(">I", data[i : i + 4])[0] == 0xD00DFEED:
            sz = struct.unpack(">I", data[i + 4 : i + 8])[0]
            if sz > 0 and i + sz <= len(data):
                dtbs.append((i, sz, data[i : i + sz]))
    return dtbs


def decompile(blob):
    with tempfile.NamedTemporaryFile(suffix=".dtb", delete=False) as f:
        f.write(blob)
        f.flush()
        r = subprocess.run(
            ["dtc", "-I", "dtb", "-O", "dts", f.name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        os.unlink(f.name)
    return r.stdout


KEYWORDS = [
    "panel",
    "lcm_driver",
    "lcm",
    "touch",
    "rotation",
    "rotate",
    "fb0",
    "framebuffer",
    "pixel",
    "bpp",
    "format",
    "resolution",
    "xres",
    "yres",
    "goodix",
    "gt9",
    "ft5",
    "focaltech",
    "sw_rotation",
    "orientation",
    "primary_display",
]


def main():
    path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "/mnt/g/GitHub/T50/T50-OrangeFox/Device_Tree/prebuilt/dtb.img"
    )
    data = open(path, "rb").read()
    dtbs = find_dtbs(data)
    print(f"Found {len(dtbs)} DTB(s) in {path}")

    for idx, (offset, size, blob) in enumerate(dtbs):
        dts = decompile(blob)
        lines = dts.split("\n")
        print(f"\n{'=' * 60}")
        print(
            f"DTB #{idx} @ offset=0x{offset:x}, size={size} bytes, {len(lines)} lines"
        )
        print(f"{'=' * 60}")

        for i, line in enumerate(lines):
            low = line.lower().strip()
            if any(k in low for k in KEYWORDS):
                s = max(0, i - 3)
                e = min(len(lines), i + 4)
                print(f"\n  >>> Match at line {i}: {line.strip()}")
                for j in range(s, e):
                    marker = ">>>" if j == i else "   "
                    print(f"  {marker} L{j}: {lines[j]}")


if __name__ == "__main__":
    main()
