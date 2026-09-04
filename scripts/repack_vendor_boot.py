import gzip
import os
import shutil
import struct
import subprocess
import sys
import tempfile


def align4k(size):
    return ((size + 4095) // 4096) * 4096


TYPE_MAP = {0: "NONE", 1: "PLATFORM", 2: "RECOVERY", 3: "DLKM"}
COMP_MAP = {0: "none", 1: "gzip", 2: "lz4", 3: "lz4_legacy", 4: "lz4_hp"}


def fmt_size(size):
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / (1024 * 1024):.1f} MB"


def parse_vb_v4(path):
    with open(path, "rb") as f:
        data = f.read()
    O = 0
    magic = data[O : O + 8]
    O += 8
    if magic != b"VNDRBOOT":
        print(f"ERROR: Invalid magic {magic}, expected VNDRBOOT")
        sys.exit(1)
    struct.unpack("<I", data[O : O + 4])[0]
    O += 4
    pg_sz = struct.unpack("<I", data[O : O + 4])[0]
    O += 4
    k_addr = struct.unpack("<I", data[O : O + 4])[0]
    O += 4
    r_addr = struct.unpack("<I", data[O : O + 4])[0]
    O += 4
    vrd_sz = struct.unpack("<I", data[O : O + 4])[0]
    O += 4
    cmdline_off = O
    cmdline = data[O : O + 2048]
    O += 2048
    tags_addr = struct.unpack("<I", data[O : O + 4])[0]
    O += 4
    name_off = O
    name = data[O : O + 16]
    O += 16
    hdr_sz = struct.unpack("<I", data[O : O + 4])[0]
    O += 4
    dtb_sz = struct.unpack("<I", data[O : O + 4])[0]
    O += 4
    dtb_addr = struct.unpack("<Q", data[O : O + 8])[0]
    O += 8
    struct.unpack("<I", data[O : O + 4])[0]
    O += 4
    vrt_num = struct.unpack("<I", data[O : O + 4])[0]
    O += 4
    vrt_esz = struct.unpack("<I", data[O : O + 4])[0]
    O += 4
    bc_sz = struct.unpack("<I", data[O : O + 4])[0]
    O += 4

    hdr_pages = align4k(hdr_sz + bc_sz) // pg_sz
    rd_pages = align4k(vrd_sz) // pg_sz
    dtb_pages = align4k(dtb_sz) // pg_sz
    tbl_off = (hdr_pages + rd_pages + dtb_pages) * pg_sz

    fragments = []
    for i in range(vrt_num):
        e_off = tbl_off + i * vrt_esz
        entry = data[e_off : e_off + vrt_esz]
        r_sz = struct.unpack("<I", entry[0:4])[0]
        r_of = struct.unpack("<I", entry[4:8])[0]
        r_ty = struct.unpack("<I", entry[8:12])[0]
        r_nm = entry[12:44]
        r_co = struct.unpack("<I", entry[44:48])[0] if len(entry) >= 48 else 0
        fragments.append(
            {
                "size": r_sz,
                "offset": r_of,
                "type": r_ty,
                "name": r_nm,
                "comp": r_co,
                "type_s": TYPE_MAP.get(r_ty, "?"),
                "comp_s": COMP_MAP.get(r_co, "?"),
            }
        )

    rd_start = hdr_pages * pg_sz
    dtb_start = (hdr_pages + rd_pages) * pg_sz

    return {
        "data": data,
        "pg_sz": pg_sz,
        "hdr_sz": hdr_sz,
        "bc_sz": bc_sz,
        "vrd_sz": vrd_sz,
        "dtb_sz": dtb_sz,
        "hdr_pages": hdr_pages,
        "rd_pages": rd_pages,
        "dtb_pages": dtb_pages,
        "rd_start": rd_start,
        "dtb_start": dtb_start,
        "tbl_off": tbl_off,
        "vrt_num": vrt_num,
        "vrt_esz": vrt_esz,
        "fragments": fragments,
        "k_addr": k_addr,
        "r_addr": r_addr,
        "tags_addr": tags_addr,
        "dtb_addr": dtb_addr,
        "cmdline": cmdline,
        "cmdline_off": cmdline_off,
        "name": name,
        "name_off": name_off,
    }


def extract_fragment_data(vb, idx):
    frag = vb["fragments"][idx]
    start = vb["rd_start"] + frag["offset"]
    end = start + frag["size"]
    return vb["data"][start:end]


def extract_cpio_gz(data, out_dir, label):
    if len(data) < 2:
        print(f"  [{label}] Fragment too small ({len(data)} bytes), skipping")
        return False
    try:
        decompressed = gzip.decompress(data)
    except Exception:
        decompressed = data
    cpio_path = os.path.join(out_dir, f"{label}.cpio")
    with open(cpio_path, "wb") as f:
        f.write(decompressed)
    extract_dir = os.path.join(out_dir, label)
    os.makedirs(extract_dir, exist_ok=True)
    result = subprocess.run(
        ["bash", "-c", f"cd '{extract_dir}' && cpio -id < '{cpio_path}' 2>&1"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and "not permitted" not in result.stderr:
        print(f"  [{label}] cpio extract warning: {result.stderr[:200]}")
    file_count = sum(1 for _ in os.walk(extract_dir))
    print(f"  [{label}] Extracted to {extract_dir} ({file_count} dirs)")
    return True


def create_cpio_gz(src_dir, out_path):
    result = subprocess.run(
        [
            "bash",
            "-c",
            f"cd '{src_dir}' && find . | cpio -o -H newc 2>/dev/null | gzip -9 > '{out_path}'",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  cpio create failed: {result.stderr}")
        return False
    size = os.path.getsize(out_path)
    print(f"  Created cpio.gz: {fmt_size(size)}")
    return True


def parse_boot_img_ramdisk(path):
    with open(path, "rb") as f:
        data = f.read()
    magic = data[0:8]
    if magic == b"ANDROID!":
        O = 8
        kernel_sz = struct.unpack("<I", data[O : O + 4])[0]
        O += 4
        struct.unpack("<I", data[O : O + 4])[0]
        O += 4
        ramdisk_sz = struct.unpack("<I", data[O : O + 4])[0]
        O += 4
        struct.unpack("<I", data[O : O + 4])[0]
        O += 4
        struct.unpack("<I", data[O : O + 4])[0]
        O += 4
        struct.unpack("<I", data[O : O + 4])[0]
        O += 4
        struct.unpack("<I", data[O : O + 4])[0]
        O += 4
        page_sz = struct.unpack("<I", data[O : O + 4])[0]
        O += 4
        O += 8
        data[O : O + 16]
        O += 16
        data[O : O + 512]
        O += 512
        O += 32
        hdr_ver = struct.unpack("<I", data[O : O + 4])[0]
        O += 4

        kernel_pages = (kernel_sz + page_sz - 1) // page_sz
        ramdisk_start = (1 + kernel_pages) * page_sz
        ramdisk_data = data[ramdisk_start : ramdisk_start + ramdisk_sz]
        print(
            f"  Boot img: hdr_ver={hdr_ver}, ramdisk_sz={fmt_size(ramdisk_sz)}, page_sz={page_sz}"
        )
        return ramdisk_data
    elif data[0:2] == b"\x1f\x8b":
        print("  File is gzip compressed (likely raw ramdisk)")
        return data
    else:
        print(f"  Unknown format: magic={magic[:8].hex()}")
        return data


def build_vendor_boot_v4(
    stock_vb, merged_ramdisk_data, dtb_data, out_path, partition_size
):
    pg_sz = stock_vb["pg_sz"]
    cmdline = stock_vb["cmdline"]
    name = stock_vb["name"]

    vrd_sz = len(merged_ramdisk_data)
    dtb_sz = len(dtb_data)

    hdr = bytearray()
    hdr += b"VNDRBOOT"
    hdr += struct.pack("<I", 4)
    hdr += struct.pack("<I", pg_sz)
    hdr += struct.pack("<I", stock_vb["k_addr"])
    hdr += struct.pack("<I", stock_vb["r_addr"])
    hdr += struct.pack("<I", vrd_sz)
    hdr += cmdline
    hdr += struct.pack("<I", stock_vb["tags_addr"])
    hdr += name

    bc = bytearray()
    hdr + bc
    hdr_sz_val = len(hdr)
    total_hdr_bc = hdr_sz_val + len(bc)

    hdr += struct.pack("<I", total_hdr_bc)
    hdr += struct.pack("<I", dtb_sz)
    hdr += struct.pack("<Q", stock_vb["dtb_addr"])

    vrt_num = 1
    vrt_esz = 48
    vrt_sz_val = vrt_num * vrt_esz

    hdr += struct.pack("<I", vrt_sz_val)
    hdr += struct.pack("<I", vrt_num)
    hdr += struct.pack("<I", vrt_esz)
    hdr += struct.pack("<I", len(bc))

    actual_hdr_sz = len(hdr)
    hdr_sz_off = len(b"VNDRBOOT") + 4 + 4 + 4 + 4 + 4 + 2048 + 4 + 16
    struct.pack_into("<I", hdr, hdr_sz_off, actual_hdr_sz)

    hdr_pages = align4k(actual_hdr_sz) // pg_sz
    rd_pages = align4k(vrd_sz) // pg_sz
    dtb_pages = align4k(dtb_sz) // pg_sz

    frag_entry = bytearray(vrt_esz)
    struct.pack_into("<I", frag_entry, 0, vrd_sz)
    struct.pack_into("<I", frag_entry, 4, 0)
    struct.pack_into("<I", frag_entry, 8, 1)
    frag_entry[12:44] = b"\x00" * 32
    struct.pack_into("<I", frag_entry, 44, 1)

    out = bytearray(partition_size)

    hdr_padded = bytes(hdr) + b"\x00" * (hdr_pages * pg_sz - len(hdr))
    out[0 : hdr_pages * pg_sz] = hdr_padded

    rd_off = hdr_pages * pg_sz
    rd_padded = merged_ramdisk_data + b"\x00" * (
        rd_pages * pg_sz - len(merged_ramdisk_data)
    )
    out[rd_off : rd_off + rd_pages * pg_sz] = rd_padded

    dtb_off = (hdr_pages + rd_pages) * pg_sz
    dtb_padded = dtb_data + b"\x00" * (dtb_pages * pg_sz - len(dtb_data))
    out[dtb_off : dtb_off + dtb_pages * pg_sz] = dtb_padded

    tbl_off = (hdr_pages + rd_pages + dtb_pages) * pg_sz
    out[tbl_off : tbl_off + vrt_esz] = frag_entry

    with open(out_path, "wb") as f:
        f.write(out)
    print(f"  Written {out_path}: {fmt_size(len(out))}")
    return True


def main():
    if len(sys.argv) < 4:
        print("Usage: repack_vendor_boot.py <stock_vb> <fox_vb> <output>")
        print("  stock_vb:  stock vendor_boot.img (with valid PLATFORM fragment)")
        print(
            "  fox_vb:    OrangeFox vendor_boot.img (with PLATFORM + RECOVERY fragments)"
        )
        print("  output:    output vendor_boot.img path")
        print("")
        print(
            "  Merges stock PLATFORM + OrangeFox RECOVERY into single PLATFORM fragment"
        )
        print("  -> MediaTek bootloader compatible (no RECOVERY fragment)")
        sys.exit(1)

    stock_path = sys.argv[1]
    fox_vb_path = sys.argv[2]
    out_path = sys.argv[3]
    partition_size = 67108864

    print(f"{'=' * 60}")
    print("  Step 1: Parse stock vendor_boot")
    print(f"{'=' * 60}")
    stock = parse_vb_v4(stock_path)
    for i, f in enumerate(stock["fragments"]):
        print(
            f"  [{i}] type={f['type_s']:10s} size={fmt_size(f['size']):>10s} comp={f['comp_s']}"
        )

    stock_plat_data = None
    for i, f in enumerate(stock["fragments"]):
        if f["type"] == 1:
            stock_plat_data = extract_fragment_data(stock, i)
            print(f"  Stock PLATFORM: {fmt_size(len(stock_plat_data))}")
            break
    if stock_plat_data is None:
        print("  ERROR: No PLATFORM fragment in stock!")
        sys.exit(1)

    dtb_data = stock["data"][stock["dtb_start"] : stock["dtb_start"] + stock["dtb_sz"]]
    print(f"  DTB: {fmt_size(len(dtb_data))}")

    print(f"\n{'=' * 60}")
    print("  Step 2: Parse OrangeFox vendor_boot")
    print(f"{'=' * 60}")
    fox = parse_vb_v4(fox_vb_path)
    for i, f in enumerate(fox["fragments"]):
        print(
            f"  [{i}] type={f['type_s']:10s} size={fmt_size(f['size']):>10s} comp={f['comp_s']}"
        )

    fox_plat_data = None
    fox_rec_data = None
    for i, f in enumerate(fox["fragments"]):
        if f["type"] == 1:
            fox_plat_data = extract_fragment_data(fox, i)
            print(f"  OrangeFox PLATFORM: {fmt_size(len(fox_plat_data))}")
        elif f["type"] == 2:
            fox_rec_data = extract_fragment_data(fox, i)
            print(f"  OrangeFox RECOVERY: {fmt_size(len(fox_rec_data))}")

    if fox_rec_data is None and (fox_plat_data is None or len(fox_plat_data) < 100):
        print("  ERROR: No RECOVERY fragment and no useful PLATFORM in OrangeFox!")
        sys.exit(1)

    print(f"\n{'=' * 60}")
    print("  Step 3: Merge ramdisks")
    print(f"{'=' * 60}")

    with tempfile.TemporaryDirectory() as tmpdir:
        stock_dir = os.path.join(tmpdir, "stock")
        rec_dir = os.path.join(tmpdir, "recovery")
        merged_dir = os.path.join(tmpdir, "merged")

        print("  Extracting stock PLATFORM fragment...")
        extract_cpio_gz(stock_plat_data, tmpdir, "stock")

        if fox_rec_data is not None and len(fox_rec_data) > 100:
            print("  Extracting OrangeFox RECOVERY fragment...")
            extract_cpio_gz(fox_rec_data, tmpdir, "recovery")
        else:
            print("  No RECOVERY fragment to extract, using stock only")
            rec_dir = None

        print("  Merging: stock vendor + OrangeFox recovery overlay...")
        shutil.copytree(stock_dir, merged_dir, symlinks=True)

        if rec_dir and os.path.isdir(rec_dir):
            overlay_count = 0
            for root, dirs, files in os.walk(rec_dir, followlinks=False):
                rel_root = os.path.relpath(root, rec_dir)
                if rel_root == ".":
                    dst_root = merged_dir
                else:
                    dst_root = os.path.join(merged_dir, rel_root)
                os.makedirs(dst_root, exist_ok=True)
                for dname in dirs:
                    dstdir = os.path.join(dst_root, dname)
                    src_dir = os.path.join(root, dname)
                    if os.path.islink(src_dir):
                        if os.path.islink(dstdir) or os.path.exists(dstdir):
                            if os.path.isdir(dstdir) and not os.path.islink(dstdir):
                                shutil.rmtree(dstdir)
                            else:
                                os.remove(dstdir)
                        os.symlink(os.readlink(src_dir), dstdir)
                        overlay_count += 1
                    else:
                        os.makedirs(dstdir, exist_ok=True)
                for fname in files:
                    src = os.path.join(root, fname)
                    dst = os.path.join(dst_root, fname)
                    if os.path.islink(dst) or os.path.exists(dst):
                        if os.path.isdir(dst) and not os.path.islink(dst):
                            shutil.rmtree(dst)
                        else:
                            os.remove(dst)
                    if os.path.islink(src):
                        os.symlink(os.readlink(src), dst)
                    else:
                        os.makedirs(os.path.dirname(dst), exist_ok=True)
                        shutil.copy2(src, dst)
                    overlay_count += 1
            print(f"  Overlaid {overlay_count} files from OrangeFox RECOVERY")
        else:
            print("  No overlay applied (stock vendor only)")

        print("  Post-processing default.prop for MTK recovery...")
        dp_path = os.path.join(merged_dir, "default.prop")
        stock_dp_path = os.path.join(stock_dir, "default.prop")

        stock_props = {}
        if os.path.exists(stock_dp_path):
            with open(stock_dp_path, errors="replace") as f:
                for line in f:
                    s = line.strip()
                    if "=" in s and not s.startswith("#"):
                        key = s.split("=", 1)[0]
                        stock_props[key] = line.rstrip()

        mtk_required_keys = [
            "ro.hardware.egl",
            "ro.hardware.hwcomposer",
            "ro.sf.lcd_density",
            "debug.renderengine.backend",
            "vendor.sf.hwc_repaint_fmt",
            "ro.surface_flinger.has_HDR_display",
            "ro.surface_flinger.force_hwc_copy_for_virtual_displays",
            "ro.surface_flinger.max_frame_buffer_acquired_buffers",
        ]

        if os.path.exists(dp_path):
            with open(dp_path, errors="replace") as f:
                dp_lines = f.readlines()

            new_lines = []
            usb_config_set = False
            sf_orientation_set = False
            merged_keys = set()
            for line in dp_lines:
                stripped = line.strip()
                if stripped.startswith("persist.sys.usb.config=none"):
                    continue
                if stripped.startswith("persist.sys.usb.config=adb"):
                    if not usb_config_set:
                        new_lines.append(line)
                        usb_config_set = True
                    continue
                if stripped.startswith(
                    "ro.surface_flinger.primary_display_orientation="
                ):
                    if not sf_orientation_set:
                        new_lines.append(
                            "ro.surface_flinger.primary_display_orientation=ORIENTATION_270\n"
                        )
                        sf_orientation_set = True
                    continue
                if "=" in stripped and not stripped.startswith("#"):
                    merged_keys.add(stripped.split("=", 1)[0])
                new_lines.append(line)

            if not usb_config_set:
                new_lines.append("persist.sys.usb.config=adb\n")
            if not sf_orientation_set:
                new_lines.append(
                    "ro.surface_flinger.primary_display_orientation=ORIENTATION_270\n"
                )

            missing_props = []
            for key in mtk_required_keys:
                if key not in merged_keys and key in stock_props:
                    new_lines.append(stock_props[key] + "\n")
                    missing_props.append(key)

            with open(dp_path, "w") as f:
                f.writelines(new_lines)

            len(dp_lines) - len(new_lines) + len(missing_props)
            print("    Removed persist.sys.usb.config=none lines")
            print(
                "    Set ro.surface_flinger.primary_display_orientation=ORIENTATION_270"
            )
            if missing_props:
                print(
                    f"    Injected {len(missing_props)} stock props: {', '.join(missing_props)}"
                )
        else:
            print("    WARNING: default.prop not found in merged ramdisk")

        merged_cpio_path = os.path.join(tmpdir, "merged.cpio.gz")
        print("  Creating merged cpio.gz...")
        if not create_cpio_gz(merged_dir, merged_cpio_path):
            print("  ERROR: Failed to create merged cpio")
            sys.exit(1)

        with open(merged_cpio_path, "rb") as f:
            merged_ramdisk_data = f.read()

    print(f"\n{'=' * 60}")
    print("  Step 4: Build new vendor_boot.img")
    print(f"{'=' * 60}")
    print(f"  Merged PLATFORM: {fmt_size(len(merged_ramdisk_data))}")
    print(f"  DTB: {fmt_size(len(dtb_data))}")
    print(f"  Partition size: {fmt_size(partition_size)}")

    if len(merged_ramdisk_data) + len(dtb_data) + 4096 * 10 > partition_size:
        print("  ERROR: Merged ramdisk too large for partition!")
        sys.exit(1)

    build_vendor_boot_v4(stock, merged_ramdisk_data, dtb_data, out_path, partition_size)

    print(f"\n{'=' * 60}")
    print("  Step 5: Verify output")
    print(f"{'=' * 60}")
    result = parse_vb_v4(out_path)
    for i, f in enumerate(result["fragments"]):
        print(
            f"  [{i}] type={f['type_s']:10s} size={fmt_size(f['size']):>10s} comp={f['comp_s']}"
        )

    plat_ok = any(
        f["type_s"] == "PLATFORM" and f["size"] > 1024 * 1024
        for f in result["fragments"]
    )
    no_rec = not any(f["type_s"] == "RECOVERY" for f in result["fragments"])

    if plat_ok and no_rec:
        print("\n  ✅ SUCCESS: PLATFORM fragment has content, no RECOVERY fragment")
        print("  → MediaTek bootloader can load PLATFORM normally")
        print("  → Recovery resources available via merged ramdisk")
    elif plat_ok:
        print("\n  ⚠️  PLATFORM OK but RECOVERY fragment exists (may cause issues)")
    else:
        print("\n  ❌ FAILED: PLATFORM fragment too small")


if __name__ == "__main__":
    main()
