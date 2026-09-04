import os
import struct
import sys


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
    magic = data[O : O + 8].decode("ascii", errors="replace")
    O += 8
    if magic != "VNDRBOOT":
        print(f"ERROR: Invalid magic '{magic}', expected 'VNDRBOOT'")
        sys.exit(1)

    hdr_ver = struct.unpack("<I", data[O : O + 4])[0]
    O += 4
    pg_sz = struct.unpack("<I", data[O : O + 4])[0]
    O += 4
    k_addr = struct.unpack("<I", data[O : O + 4])[0]
    O += 4
    r_addr = struct.unpack("<I", data[O : O + 4])[0]
    O += 4
    vrd_sz = struct.unpack("<I", data[O : O + 4])[0]
    O += 4
    cmdline = data[O : O + 2048].rstrip(b"\x00").decode("ascii", errors="replace")
    O += 2048
    tags_addr = struct.unpack("<I", data[O : O + 4])[0]
    O += 4
    name = data[O : O + 16].rstrip(b"\x00").decode("ascii", errors="replace")
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

    hdr_pages = (hdr_sz + bc_sz + pg_sz - 1) // pg_sz
    rd_pages = (vrd_sz + pg_sz - 1) // pg_sz
    dtb_pages = (dtb_sz + pg_sz - 1) // pg_sz
    tbl_off = (hdr_pages + rd_pages + dtb_pages) * pg_sz

    fragments = []
    for i in range(vrt_num):
        e_off = tbl_off + i * vrt_esz
        entry = data[e_off : e_off + vrt_esz]
        r_sz = struct.unpack("<I", entry[0:4])[0]
        r_of = struct.unpack("<I", entry[4:8])[0]
        r_ty = struct.unpack("<I", entry[8:12])[0]
        r_nm = entry[12:44].rstrip(b"\x00").decode("ascii", errors="replace")
        r_co = struct.unpack("<I", entry[44:48])[0] if len(entry) >= 48 else 0
        fragments.append(
            {
                "index": i,
                "name": r_nm,
                "type": r_ty,
                "type_s": TYPE_MAP.get(r_ty, f"?({r_ty})"),
                "size": r_sz,
                "offset": r_of,
                "comp": COMP_MAP.get(r_co, f"?({r_co})"),
            }
        )

    return {
        "file_size": len(data),
        "magic": magic,
        "hdr_ver": hdr_ver,
        "pg_sz": pg_sz,
        "k_addr": k_addr,
        "r_addr": r_addr,
        "vrd_sz": vrd_sz,
        "cmdline": cmdline,
        "tags_addr": tags_addr,
        "name": name,
        "hdr_sz": hdr_sz,
        "dtb_sz": dtb_sz,
        "dtb_addr": dtb_addr,
        "vrt_num": vrt_num,
        "fragments": fragments,
    }


def print_result(label, info):
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    print(f"  File size      : {fmt_size(info['file_size'])}")
    print(f"  Header version : {info['hdr_ver']}")
    print(f"  Page size      : {info['pg_sz']}")
    print(f"  Kernel addr    : 0x{info['k_addr']:08x}")
    print(f"  Ramdisk addr   : 0x{info['r_addr']:08x}")
    print(f"  Tags addr      : 0x{info['tags_addr']:08x}")
    print(f"  DTB addr       : 0x{info['dtb_addr']:016x}")
    print(f"  DTB size       : {fmt_size(info['dtb_sz'])}")
    print(f"  Vendor rd size : {fmt_size(info['vrd_sz'])}")
    print(f"  Fragment count : {info['vrt_num']}")
    print(f"  Cmdline        : {info['cmdline'][:80]}...")
    print()
    print(f"  {'#':<3} {'Name':<16} {'Type':<12} {'Size':<12} {'Compression':<12}")
    print(f"  {'-' * 3} {'-' * 16} {'-' * 12} {'-' * 12} {'-' * 12}")
    for frag in info["fragments"]:
        print(
            f"  {frag['index']:<3} {frag['name']:<16} {frag['type_s']:<12} {fmt_size(frag['size']):<12} {frag['comp']:<12}"
        )
    print()


def check_bootloop_risk(info, label):
    has_platform = False
    has_recovery = False
    platform_size = 0
    recovery_size = 0
    for frag in info["fragments"]:
        if frag["type_s"] == "PLATFORM":
            has_platform = True
            platform_size = frag["size"]
        elif frag["type_s"] == "RECOVERY":
            has_recovery = True
            recovery_size = frag["size"]

    print(f"  [{label}] Bootloop risk assessment:")
    if has_recovery:
        print(f"    WARNING: RECOVERY fragment exists ({fmt_size(recovery_size)})")
        print(
            "    → MediaTek bootloader may NOT load RECOVERY fragment on normal boot"
        )
        if platform_size < 1024:
            print(
                f"    CRITICAL: PLATFORM fragment is nearly empty ({fmt_size(platform_size)})"
            )
            print("    → Device will bootloop! Normal boot cannot find vendor init.")
        else:
            print(
                f"    CAUTION: PLATFORM fragment has content ({fmt_size(platform_size)})"
            )
            print("    → May work if bootloader loads both fragments")
    else:
        print("    OK: No RECOVERY fragment (matches stock behavior)")
        if has_platform and platform_size > 1024 * 1024:
            print(
                f"    OK: PLATFORM fragment has substantial content ({fmt_size(platform_size)})"
            )
            print("    → Device should boot normally")
        elif has_platform:
            print(
                f"    WARNING: PLATFORM fragment is small ({fmt_size(platform_size)})"
            )
    print()


def main():
    if len(sys.argv) < 2:
        print("Usage: verify_fragments.py <vendor_boot.img> [vendor_boot2.img ...]")
        print("  Parses vendor_boot v4 header and ramdisk fragment table")
        sys.exit(1)

    for path in sys.argv[1:]:
        if not os.path.exists(path):
            print(f"ERROR: {path} not found")
            continue

        label = os.path.basename(path)
        info = parse_vb_v4(path)
        print_result(label, info)
        check_bootloop_risk(info, label)

    if len(sys.argv) == 3:
        print(f"{'=' * 60}")
        print("  COMPARISON")
        print(f"{'=' * 60}")
        info1 = parse_vb_v4(sys.argv[1])
        info2 = parse_vb_v4(sys.argv[2])
        n1 = len(info1["fragments"])
        n2 = len(info2["fragments"])
        print(
            f"  {os.path.basename(sys.argv[1])}: {n1} fragment(s), total vendor_rd={fmt_size(info1['vrd_sz'])}"
        )
        print(
            f"  {os.path.basename(sys.argv[2])}: {n2} fragment(s), total vendor_rd={fmt_size(info2['vrd_sz'])}"
        )
        if n1 != n2:
            print(f"  DIFF: Fragment count differs ({n1} vs {n2})")
        else:
            print(f"  SAME: Fragment count matches ({n1})")
        print()


if __name__ == "__main__":
    main()
