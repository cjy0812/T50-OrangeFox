#!/usr/bin/env python3
"""Deep inspect repacked vendor_boot ramdisk to diagnose boot issues."""

import gzip
import os
import struct
import subprocess
import sys
import tempfile


def a4k(s):
    return ((s + 4095) // 4096) * 4096


def extract_ramdisk(img_path):
    with open(img_path, "rb") as f:
        data = f.read()
    O = 8 + 4
    pg = struct.unpack("<I", data[O : O + 4])[0]
    O += 4 + 4 + 4
    vrd = struct.unpack("<I", data[O : O + 4])[0]
    O += 4 + 2048 + 4 + 16
    hsz = struct.unpack("<I", data[O : O + 4])[0]
    O += 4 + 4 + 8 + 4 + 4 + 4 + 4
    hp = a4k(hsz) // pg
    rd = data[hp * pg : hp * pg + vrd]
    try:
        rd = gzip.decompress(rd)
        print(f"  Ramdisk: gzip decompressed {len(rd)} bytes")
    except Exception:
        print(f"  Ramdisk: raw {len(rd)} bytes")
    return rd


def main():
    img = (
        sys.argv[1] if len(sys.argv) > 1 else "ci_artifacts/vendor_boot_v4_repacked.img"
    )
    print(f"=== Inspecting {img} ===")

    ramdisk = extract_ramdisk(img)

    with tempfile.TemporaryDirectory() as td:
        cpio_path = os.path.join(td, "rd.cpio")
        rootfs = os.path.join(td, "rootfs")
        os.makedirs(rootfs)
        with open(cpio_path, "wb") as f:
            f.write(ramdisk)

        subprocess.run(
            ["bash", "-c", f"cd '{rootfs}' && cpio -id < '{cpio_path}' 2>/dev/null"],
            capture_output=True,
            text=True,
        )
        file_count = sum(
            1
            for _ in subprocess.run(
                ["find", rootfs, "-type", "f"], capture_output=True
            ).stdout.split()
        )
        print(f"  Extracted {file_count} files")

        def cat(path):
            full = os.path.join(rootfs, path)
            if os.path.exists(full):
                with open(full, errors="replace") as f:
                    return f.read()
            return None

        def grep_dir(pattern, ext=".rc"):
            results = []
            for root, dirs, files in os.walk(rootfs, followlinks=False):
                for fn in files:
                    if fn.endswith(ext):
                        fp = os.path.join(root, fn)
                        try:
                            with open(fp, errors="replace") as f:
                                for i, line in enumerate(f, 1):
                                    if pattern in line:
                                        rel = os.path.relpath(fp, rootfs)
                                        results.append(f"  {rel}:{i}: {line.rstrip()}")
                        except Exception:
                            pass
            return results

        def strings_bin(path, patterns):
            full = os.path.join(rootfs, path)
            if not os.path.exists(full):
                return []
            try:
                r = subprocess.run(["strings", full], capture_output=True, text=True)
                found = []
                for line in r.stdout.split("\n"):
                    for p in patterns:
                        if p.lower() in line.lower():
                            found.append(f"  {line.strip()}")
                            break
                return found
            except Exception:
                return []

        print("\n" + "=" * 60)
        print("  1. INIT IMPORT CHAIN")
        print("=" * 60)
        imports = grep_dir("import", ".rc")
        for line in imports[:30]:
            print(line)

        print("\n" + "=" * 60)
        print("  2. ADB DIAGNOSIS")
        print("=" * 60)
        print("--- default.prop: USB/ADB ---")
        dp = cat("default.prop") or ""
        for line in dp.split("\n"):
            if any(k in line for k in ["usb", "adb", "debuggable", "controller"]):
                print(f"  {line}")

        print("\n--- init.rc: adbd service ---")
        init_rc = cat("system/etc/init/hw/init.rc") or ""
        in_adbd = False
        for i, line in enumerate(init_rc.split("\n"), 1):
            if "adbd" in line or in_adbd:
                print(f"  {i}: {line}")
                in_adbd = "adbd" in line and "service" in line
                if in_adbd:
                    in_adbd = True

        print("\n--- init.recovery.mt8786.rc ---")
        mt = cat("init.recovery.mt8786.rc") or "(NOT FOUND)"
        print(mt[:500])

        print("\n" + "=" * 60)
        print("  3. ROTATION / DISPLAY")
        print("=" * 60)
        print("--- default.prop: rotation/pixel ---")
        for line in dp.split("\n"):
            if any(
                k in line
                for k in [
                    "rotation",
                    "pixel",
                    "minui",
                    "surface_flinger",
                    "orientation",
                ]
            ):
                print(f"  {line}")

        print("\n--- recovery binary: rotation strings ---")
        rot_strs = strings_bin(
            "system/bin/recovery",
            ["rotation", "tw_rotation", "ROTATION_", "minui", "hwrotation"],
        )
        for s in rot_strs[:20]:
            print(s)

        print("\n--- recovery binary: graphics backend ---")
        gfx_strs = strings_bin(
            "system/bin/recovery", ["fbdev", "drm", "gralloc", "minui", "graphics"]
        )
        for s in gfx_strs[:20]:
            print(s)

        print("\n" + "=" * 60)
        print("  4. TOUCH")
        print("=" * 60)
        touch_strs = strings_bin(
            "system/bin/recovery", ["goodix", "touch", "input", "evdev", "tw_input"]
        )
        for s in touch_strs[:15]:
            print(s)

        print("\n" + "=" * 60)
        print("  5. CRITICAL: Does init import our .rc?")
        print("=" * 60)
        init_imports = [
            l for l in imports if "init.recovery" in l or "mt8786" in l or "mt6768" in l
        ]
        if init_imports:
            print("  YES - found imports:")
            for l in init_imports:
                print(l)
        else:
            print("  ⚠️  NO direct import of init.recovery.mt8786.rc found!")
            print("  Checking if init.rc has 'import /init.recovery.*' ...")
            for line in init_rc.split("\n"):
                if "import" in line and "recovery" in line:
                    print(f"  Found: {line}")

        print("\n--- All .rc files in root ---")
        for fn in sorted(os.listdir(rootfs)):
            if fn.endswith(".rc"):
                print(f"  {fn}")


if __name__ == "__main__":
    main()
