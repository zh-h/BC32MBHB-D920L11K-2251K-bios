#!/usr/bin/env python3
"""Build the current custom KP920 BIOS image (1.0-3).

Output filename::

    BC32MBHB-D920L11K-2251K_1.0-3_2020-07-22.bin

1.0 is the stock BIOS Version and 3 is the custom revision.  The revision is
bumped as the modifications evolve; it is not a menu of alternative images.

1.0-3 keeps the stock 1.68 pre-SoC15 Arm64Gop FFS (Radeon 520) byte-for-byte
and appends a post-SoC15 2.10 Arm64Gop FFS (Vega 20) to the inner DXE FV.
It also replaces the 300x95 boot logo with the generated Huawei logo.
The firmware's EC version (0.23) and BIOS Version (1.0) are left untouched;
the custom version is only a filename/build tag.

Only the compressed DXE FV's outer FFS file is rebuilt.  FFS header checksums
are left untouched for data-only changes; the EDK2 FFS file checksum field is
the fixed marker 0xAA (verified on all 39 top-level FFS files).
"""
import argparse
import hashlib
import lzma
import struct
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Current (single) custom version: stock BIOS Version 1.0 + custom build 3.
STOCK_BIOS_VERSION = "1.0"
CUSTOM_VERSION = 3
BUILD_DATE = "2020-07-22"
IMAGE_STEM = "BC32MBHB-D920L11K-2251K"
CUSTOM_VERSION_TAG = f"{STOCK_BIOS_VERSION}-{CUSTOM_VERSION}"
OUTPUT_NAME = f"{IMAGE_STEM}_{CUSTOM_VERSION_TAG}_{BUILD_DATE}.bin"
ORIGINAL_IMAGE_SHA = "e900c384175cf424b970163109cfe36829fa0d459fbd99d1af954257f63b3704"

# BIOS Version field in the version info block (0xBF0000 volume).
# 8-byte fixed slot: "1.0\0\0\0\0\0" -> "<CUSTOM_VERSION_TAG>\0...".
# The EC version field at 0xBF0058 ("0.23") is deliberately left untouched.
BIOS_VERSION_BLOCK_OFF = 0xBF0098
BIOS_VERSION_BLOCK_OLD = b"1.0\x00\x00\x00\x00\x00"
_block_tag = CUSTOM_VERSION_TAG.encode("ascii")
if len(_block_tag) >= len(BIOS_VERSION_BLOCK_OLD):
    raise SystemExit("CUSTOM_VERSION_TAG does not fit the 8-byte version block")
BIOS_VERSION_BLOCK_NEW = _block_tag.ljust(len(BIOS_VERSION_BLOCK_OLD), b"\x00")

# VersionInfoPeim carries a default BIOS version string "1.0" next to its
# build date/time.  It is adjacent to the "String != ..." assert text, so a
# longer version tag overwrites the leading characters of that debug-only
# string; the patch length grows only when the tag needs more room.
HOB_VERSION_OFF = 0x89B144
HOB_VERSION_OLD = b"1.0\x00St"
HOB_VERSION_NEW = _block_tag + b"\x00"
HOB_VERSION_PATCH_LEN = max(len(HOB_VERSION_OLD), len(HOB_VERSION_NEW))
HOB_VERSION_PATCH_NEW = HOB_VERSION_NEW.ljust(HOB_VERSION_PATCH_LEN, b"\x00")

# VersionInfoPeim copies the version string with "mov x2, #4"; use
# len(tag)+1 so the NUL-terminated tag is not truncated.
HOB_VERSION_COPY_OFF = 0x897D2C
HOB_VERSION_COPY_LEN = len(_block_tag) + 1
if HOB_VERSION_COPY_LEN > 0xFFFF:
    raise SystemExit("CUSTOM_VERSION_TAG too long for the version copy")
HOB_VERSION_COPY_OLD = struct.pack("<I", 0xD2800002 | (4 << 5))   # mov x2, #4
HOB_VERSION_COPY_NEW = struct.pack(
    "<I", 0xD2800002 | (HOB_VERSION_COPY_LEN << 5)
)

# Boot logo: the stock PowerLeader 300x95 24-bit BMP lives in file GUID
# 7BB28B99-61BB-11D5-9A5D-0090273FC14D.  BdsDxe draws the image at its native
# size (no scaling).  The current 840x260 24-bit Huawei BMP is pre-compensated
# for a 1024-wide 4:3 GOP being stretched to a 16:9 panel.  Replacing it grows
# the FFS, so the inner FV is rebuilt with every following file shifted.
BOOT_LOGO_GUID = uuid.UUID("7bb28b99-61bb-11d5-9a5d-0090273fc14d")
BOOT_LOGO_BMP = ROOT / "images" / "Huawei-Logo.bmp"
BOOT_LOGO_SHA = "8944e3ebd1b135d90af3e1b1dfeb7c7229b3f12e861f3727af548dfcc21393dd"
ORIG_BOOT_LOGO_SIZE = 85554  # stock 300x95 24-bit BMP
ORIG_BOOT_LOGO_SHA = "774a3dc6450d82c9723e772d5877419d3b6cf714bedb6369541e14ec3a631bce"

FV2_OFF = 0x860000
FV2_LEN = 0x320000
OUTER_FFS_OFF = 0x983770
OUTER_FFS_SIZE = 0x1EC5A1
OUTER_SEC_OFF = OUTER_FFS_OFF + 24
OUTER_SEC_SIZE = 0x1EC589
LZMA_GUID = uuid.UUID("ee4e5898-3914-4259-9d6e-dc7bd79403cf")
ARM_GOP_GUID = uuid.UUID("43b59c81-9c5f-4021-b0f2-947db2191781")
UNCOMP_SIZE = 0xDEA4C0
INNER_FV_OFF = 0x80
INNER_FV_LEN = 0xDEA440

# post-SoC15 GOP FFS appended by the current build
POST_GOP_FFS_GUID = uuid.UUID("92f10585-fb63-430f-8188-71feeb2dda5b")
POST_GOP_UI_NAME = "ARM64Gop 2.10"
DEFAULT_GOP210 = str(ROOT / "drivers" / "ARM64Gop_2_10.efi")
ARM64GOP_2_10_SHA = "c0b47fe3a16718666565e0a19a9d85d0eccbff2a8c71145cc082a5abc6bb4259"
ORIG_168_PE_SHA = "22021e0a5a47cff0d48dd86161eb540a786604898b81da41c8b06983f762372f"

FILTERS = [{
    "id": lzma.FILTER_LZMA1,
    "dict_size": 0x01000000,
    "lc": 3,
    "lp": 0,
    "pb": 2,
    "mode": lzma.MODE_NORMAL,
    "nice_len": 128,
    "mf": lzma.MF_BT4,
    "depth": 0,
}]


def u24(b, off=0):
    return int.from_bytes(b[off:off + 3], "little")


def p24(b, off, val):
    b[off:off + 3] = val.to_bytes(3, "little")


def checksum8(b):
    return (0x100 - (sum(b) & 0xFF)) & 0xFF


def build_logo_ffs(orig_ffs, bmp, max_alignment):
    """Build a freeform FFS containing the BMP raw section.

    The FFS is padded so the size delta versus the stock logo FFS is a
    multiple of max_alignment.  This keeps every following FFS file at its
    original alignment residue when the files are shifted.
    """
    first_sec_size = 4 + len(bmp)
    base_size = 24 + first_sec_size
    old_size = len(orig_ffs)
    extra = (-(base_size - old_size)) % max_alignment
    pad_align = (-first_sec_size) % 4
    if extra:
        if extra < pad_align + 4:
            extra += max_alignment
        pad_sec_size = extra - pad_align
    else:
        pad_align = 0
        pad_sec_size = 0
    size = base_size + extra
    if size >= 1 << 24 or first_sec_size >= 1 << 24 or pad_sec_size >= 1 << 24:
        raise SystemExit("boot logo FFS too large for 3-byte size")

    ffs = bytearray(size)
    ffs[0:24] = orig_ffs[0:24]
    p24(ffs, 0x14, size)
    ffs[0x10] = 0
    ffs[0x11] = 0
    ffs[0x10] = checksum8(ffs[:0x17])
    ffs[0x11] = 0xAA
    p24(ffs, 24, first_sec_size)
    ffs[27] = 0x19  # EFI_SECTION_RAW (BMP)
    ffs[28:28 + len(bmp)] = bmp
    pos = 24 + first_sec_size + pad_align
    if pad_sec_size:
        p24(ffs, pos, pad_sec_size)
        ffs[pos + 3] = 0x19  # EFI_SECTION_RAW (padding)
    return bytes(ffs)


def replace_ffs_and_resize(fv, guid, new_ffs):
    """Replace an FFS file, shift following files, and grow the FV."""
    files = list(iter_ffs(fv))
    target = None
    for i, (off, sz, g) in enumerate(files):
        if g == str(uuid.UUID(guid)):
            target = i
            break
    if target is None:
        raise SystemExit(f"FFS {guid} not found in inner FV")
    old_off, old_sz, _ = files[target]
    if new_ffs[:16] != fv[old_off:old_off + 16]:
        raise SystemExit("replacement FFS GUID does not match the target")

    pos = (old_off + len(new_ffs) + 7) & ~7
    layout = []
    for off, sz, _ in files[target + 1:]:
        pos = aligned_ffs_offset(pos, ffs_required_alignment(fv, off))
        layout.append((pos, off, sz))
        pos = (pos + sz + 7) & ~7
    end = pos
    block = fv_block_size(fv)
    new_len = ((end + block - 1) // block) * block
    if new_len >= 1 << 24:
        raise SystemExit("new inner FV too large for 3-byte FV image section")

    new_fv = bytearray(b"\xff" * new_len)
    new_fv[:old_off] = fv[:old_off]
    new_fv[old_off:old_off + len(new_ffs)] = new_ffs
    for new_off, src_off, sz in layout:
        new_fv[new_off:new_off + sz] = fv[src_off:src_off + sz]

    new_fv[0x20:0x28] = new_len.to_bytes(8, "little")
    struct.pack_into("<II", new_fv, 0x38, new_len // block, block)
    struct.pack_into("<II", new_fv, 0x40, 0, 0)
    new_fv[0x32:0x34] = b"\x00\x00"
    hdr_len = int.from_bytes(new_fv[0x30:0x32], "little")
    s16 = sum(int.from_bytes(new_fv[i:i + 2], "little")
              for i in range(0, hdr_len, 2)) & 0xFFFF
    new_fv[0x32:0x34] = ((0x10000 - s16) & 0xFFFF).to_bytes(2, "little")
    return new_fv


def patch_boot_logo(fv):
    """Replace the stock boot logo and grow/rebuild the inner FV."""
    off, sz = find_ffs_by_guid(fv, str(BOOT_LOGO_GUID))
    orig_ffs = bytes(fv[off:off + sz])
    body = None
    for _, sec_sz, typ, sec_body in parse_sections(orig_ffs[24:]):
        if typ == 0x19:
            if sec_sz - 4 != ORIG_BOOT_LOGO_SIZE:
                raise SystemExit(
                    f"unexpected stock boot logo size {sec_sz - 4:#x}"
                )
            body = sec_body
            break
    if body is None:
        raise SystemExit("stock boot logo raw section not found")
    if hashlib.sha256(body).hexdigest() != ORIG_BOOT_LOGO_SHA:
        raise SystemExit("source boot logo is not the expected stock BMP")

    new = BOOT_LOGO_BMP.read_bytes()
    if new[:2] != b"BM":
        raise SystemExit(f"{BOOT_LOGO_BMP} is not a BMP")
    if hashlib.sha256(new).hexdigest() != BOOT_LOGO_SHA:
        raise SystemExit(f"{BOOT_LOGO_BMP} SHA-256 mismatch")

    files = list(iter_ffs(fv))
    target = next(i for i, (o, _, _) in enumerate(files) if o == off)
    max_alignment = max(
        [8] + [ffs_required_alignment(fv, o) for o, _, _ in files[target + 1:]]
    )
    new_ffs = build_logo_ffs(orig_ffs, new, max_alignment)
    print(
        f"boot logo: FFS {len(orig_ffs):#x} -> {len(new_ffs):#x} "
        f"(BMP {len(new)} bytes, align {max_alignment:#x}, "
        f"{BOOT_LOGO_BMP.name})"
    )
    new_fv = replace_ffs_and_resize(fv, str(BOOT_LOGO_GUID), new_ffs)

    new_off, new_sz = find_ffs_by_guid(new_fv, str(BOOT_LOGO_GUID))
    for p, _, typ, sec_body in parse_sections(new_fv[new_off + 24:new_off + new_sz]):
        if typ == 0x19:
            body_off = new_off + 24 + p + 4
            if bytes(sec_body) != new:
                raise SystemExit("new boot logo raw section mismatch")
            print(f"boot logo: placed at inner {body_off:#x}")
            return new_fv, body_off, new
    raise SystemExit("new boot logo raw section not found")


def ffs_header_checksum_ok(fv, off):
    hdr = bytearray(fv[off:off + 0x17])
    stored = hdr[0x10]
    hdr[0x10] = 0
    hdr[0x11] = 0
    return checksum8(hdr) == stored


def comp_lzma(data):
    stream = lzma.compress(data, format=lzma.FORMAT_ALONE, filters=FILTERS)
    header = bytes([0x5D]) + (0x01000000).to_bytes(4, "little") + len(data).to_bytes(8, "little")
    if stream[:5] != header[:5]:
        raise RuntimeError(f"unexpected LZMA props: {stream[:5].hex()}")
    payload = header + stream[13:]
    if lzma.decompress(payload, format=lzma.FORMAT_ALONE) != data:
        raise RuntimeError("LZMA round-trip failed")
    return payload


def parse_sections(data):
    p = 0
    while p + 4 <= len(data):
        sz = u24(data, p)
        typ = data[p + 3]
        if sz < 4 or p + sz > len(data):
            return
        yield p, sz, typ, data[p + 4:p + sz]
        p = (p + sz + 3) & ~3


def iter_ffs(fv):
    ln = int.from_bytes(fv[0x20:0x28], "little")
    hdr = int.from_bytes(fv[0x30:0x32], "little")
    p = hdr
    while p + 24 <= ln:
        name = fv[p:p + 16]
        sz = u24(fv, p + 0x14)
        state = fv[p + 0x17]
        if state == 0xFF or sz < 24 or p + sz > ln:
            break
        yield p, sz, str(uuid.UUID(bytes_le=bytes(name)))
        p = (p + sz + 7) & ~7


def find_ffs_by_guid(fv, guid):
    want = str(uuid.UUID(guid))
    for off, sz, got in iter_ffs(fv):
        if got == want:
            return off, sz
    raise RuntimeError(f"FFS {want} not found in inner FV")


def build_gop_ffs(pe, guid, ui_name):
    """Build a DXE-driver FFS (PE32 + UI sections) for a GOP PE."""
    if pe[:2] != b"MZ":
        raise SystemExit("GOP PE is not an MZ image")
    ui = ui_name.encode("utf-16le") + b"\x00\x00"
    pe_sec = bytearray(4 + len(pe))
    p24(pe_sec, 0, len(pe_sec))
    pe_sec[3] = 0x10
    pe_sec[4:] = pe
    ui_sec = bytearray(4 + len(ui))
    p24(ui_sec, 0, len(ui_sec))
    ui_sec[3] = 0x15
    ui_sec[4:] = ui
    sections = bytes(pe_sec) + bytes(ui_sec)
    size = 24 + len(sections)
    if size >= 1 << 24:
        raise SystemExit("FFS too large for 3-byte size")
    ffs = bytearray(size)
    ffs[0:16] = uuid.UUID(guid).bytes_le
    ffs[0x12] = 0x07  # EFI_FV_FILETYPE_DRIVER
    ffs[0x13] = 0x00
    p24(ffs, 0x14, size)
    ffs[0x17] = 0xF8
    ffs[24:] = sections
    ffs[0x10] = 0
    ffs[0x11] = 0
    ffs[0x10] = checksum8(ffs[:0x17])
    ffs[0x11] = 0xAA
    return bytes(ffs)


def find_last_file_end(fv):
    """Aligned end of the last FFS file in the FV (insertion point)."""
    end = int.from_bytes(fv[0x30:0x32], "little")
    for off, sz, _ in iter_ffs(fv):
        end = off + sz
    return (end + 7) & ~7


# UEFITool/PI FFS alignment tables (see EFI_FFS_FILE_ATTRIBUTES).
FFS_ALIGNMENT_TABLE = (0, 4, 7, 9, 10, 12, 15, 16)
FFS_ALIGNMENT2_TABLE = (17, 18, 19, 20, 21, 22, 23, 24)


def ffs_required_alignment(fv, off):
    """Return the byte alignment required for the FFS file body."""
    attr = fv[off + 0x13]
    idx = (attr & 0x38) >> 3
    power = FFS_ALIGNMENT_TABLE[idx]
    if fv[0x37] > 1 and (attr & 0x02):
        power = FFS_ALIGNMENT2_TABLE[idx]
    return 1 << power


def aligned_ffs_offset(cursor, alignment):
    """Smallest offset >= cursor with (offset + 24) % alignment == 0."""
    a = max(alignment, 8)
    r = (-24) % a
    rem = cursor % a
    if rem <= r:
        return cursor - rem + r
    return cursor - rem + a + r


def fv_block_size(fv):
    num, length = struct.unpack_from("<II", fv, 0x38)
    if num == 0 or length == 0:
        raise SystemExit("FV block map has no usable first entry")
    if struct.unpack_from("<II", fv, 0x40) != (0, 0):
        raise SystemExit("multi-entry FV block map is not supported")
    return length


def append_ffs_to_fv(fv, new_ffs):
    """Append a new FFS to the FV, growing it on block-size boundaries."""
    if fv[0x28:0x2C] != b"_FVH":
        raise SystemExit("inner FV signature missing")
    insert = find_last_file_end(fv)
    block = fv_block_size(fv)
    if insert + len(new_ffs) >= 1 << 24:
        raise SystemExit("new FV too large for 3-byte FV image section size")
    new_len = ((insert + len(new_ffs) + block - 1) // block) * block
    new_fv = bytearray(b"\xff" * new_len)
    new_fv[:len(fv)] = fv
    new_fv[insert:insert + len(new_ffs)] = new_ffs
    new_fv[0x20:0x28] = new_len.to_bytes(8, "little")
    struct.pack_into("<II", new_fv, 0x38, new_len // block, block)
    struct.pack_into("<II", new_fv, 0x40, 0, 0)
    new_fv[0x32:0x34] = b"\x00\x00"
    hdr_len = int.from_bytes(new_fv[0x30:0x32], "little")
    s16 = sum(int.from_bytes(new_fv[i:i + 2], "little")
              for i in range(0, hdr_len, 2)) & 0xFFFF
    new_fv[0x32:0x34] = ((0x10000 - s16) & 0xFFFF).to_bytes(2, "little")
    return bytes(new_fv), insert


def replace_stream_fv(stream, new_fv):
    """Replace the FV image in the decompressed stream, growing the stream."""
    if stream[3] != 0x19 or stream[0x7F] != 0x17:
        raise SystemExit("unexpected inner stream section layout")
    out = bytearray(stream[:0x80])
    p24(out, 0x7C, 4 + len(new_fv))
    out += new_fv
    return bytes(out)


def verify_fv_block_map(fv, label):
    ln = int.from_bytes(fv[0x20:0x28], "little")
    hdr_len = int.from_bytes(fv[0x30:0x32], "little")
    off = 0x38
    total = 0
    entries = 0
    while off + 8 <= hdr_len:
        num, length = struct.unpack_from("<II", fv, off)
        if num == 0 and length == 0:
            break
        total += num * length
        entries += 1
        off += 8
    if entries == 0 or total != ln:
        raise RuntimeError(
            f"{label}: block map total {total:#x} != FvLength {ln:#x}"
        )
    print(f"  {label}: block map OK ({entries} entries, {total:#x})")


def pe_of_ffs(fv, guid):
    off, sz = find_ffs_by_guid(fv, guid)
    for _, _, typ, body in parse_sections(fv[off + 24:off + sz]):
        if typ == 0x10:
            return bytes(body)
    raise SystemExit(f"PE32 section not found in FFS {guid}")


def verify_fv_header(fv, label):
    hdr_len = int.from_bytes(fv[0x30:0x32], "little")
    stored = int.from_bytes(fv[0x32:0x34], "little")
    hdr = bytearray(fv[:hdr_len])
    hdr[0x32:0x34] = b"\x00\x00"
    s16 = sum(int.from_bytes(hdr[i:i + 2], "little") for i in range(0, len(hdr), 2)) & 0xFFFF
    calc = (0x10000 - s16) & 0xFFFF
    if calc != stored:
        raise RuntimeError(f"{label}: bad FV header checksum (stored {stored:#x}, calc {calc:#x})")


def verify_ffs(fv, label):
    verify_fv_header(fv, label)
    ln = int.from_bytes(fv[0x20:0x28], "little")
    hdr = int.from_bytes(fv[0x30:0x32], "little")
    p = hdr
    n = 0
    while p + 24 <= ln:
        sz = u24(fv, p + 0x14)
        state = fv[p + 0x17]
        if state == 0xFF or sz < 24 or p + sz > ln:
            break
        if not ffs_header_checksum_ok(fv, p):
            raise RuntimeError(f"{label}: bad FFS header checksum at {p:#x}")
        if fv[p + 0x11] != 0xAA:
            raise RuntimeError(f"{label}: unexpected FFS file checksum at {p:#x}")
        p = (p + sz + 7) & ~7
        n += 1
    print(f"  {label}: {n} FFS files, checksums OK")


def main():
    ap = argparse.ArgumentParser(
        description="Build the current custom KP920 BIOS image (1.0-3).",
        epilog=f"default output: firmware/modified/{OUTPUT_NAME}",
    )
    ap.add_argument(
        "--src",
        default=str(ROOT / "firmware" / "original" / "BC32MBHB-D920L11K-2251K_1.0_2020-07-22.bin"),
    )
    ap.add_argument(
        "--gop210",
        default=DEFAULT_GOP210,
        help="post-SoC15 2.10 GOP PE (default: drivers/ARM64Gop_2_10.efi)",
    )
    ap.add_argument(
        "--out",
        default=str(ROOT / "firmware" / "modified" / OUTPUT_NAME),
        help=f"output image (default: firmware/modified/{OUTPUT_NAME})",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing output file even if its content differs",
    )
    args = ap.parse_args()

    img = bytearray(open(args.src, "rb").read())
    if len(img) != 16 * 1024 * 1024:
        raise SystemExit("source is not 16 MiB")
    source_sha = hashlib.sha256(img).hexdigest()
    print("source sha256", source_sha)
    if source_sha != ORIGINAL_IMAGE_SHA:
        raise SystemExit(
            "unexpected source image; this builder patches fixed offsets in "
            "the stock BIOS image"
        )
    orig_img = bytes(img)

    # --- update the displayed/reported BIOS Version field ---
    off = BIOS_VERSION_BLOCK_OFF
    old_len = len(BIOS_VERSION_BLOCK_OLD)
    if img[off:off + old_len] != BIOS_VERSION_BLOCK_OLD:
        raise SystemExit("unexpected BIOS version field in version info block")
    img[off:off + len(BIOS_VERSION_BLOCK_NEW)] = BIOS_VERSION_BLOCK_NEW
    print(f"BIOS version block: 1.0 -> {CUSTOM_VERSION_TAG}")

    off = HOB_VERSION_OFF
    if img[off:off + len(HOB_VERSION_OLD)] != HOB_VERSION_OLD:
        raise SystemExit("unexpected VersionInfoPeim default version string")
    img[off:off + HOB_VERSION_PATCH_LEN] = HOB_VERSION_PATCH_NEW
    print(f"VersionInfoPeim default version: 1.0 -> {CUSTOM_VERSION_TAG}")

    off = HOB_VERSION_COPY_OFF
    if img[off:off + len(HOB_VERSION_COPY_OLD)] != HOB_VERSION_COPY_OLD:
        raise SystemExit("unexpected VersionInfoPeim version copy instruction")
    img[off:off + len(HOB_VERSION_COPY_NEW)] = HOB_VERSION_COPY_NEW
    print(f"VersionInfoPeim version copy length: 4 -> {HOB_VERSION_COPY_LEN}")

    # --- check outer structures ---
    if img[FV2_OFF + 0x28:FV2_OFF + 0x2C] != b"_FVH":
        raise SystemExit("FV2 signature missing")
    if int.from_bytes(img[FV2_OFF + 0x20:FV2_OFF + 0x28], "little") != FV2_LEN:
        raise SystemExit("unexpected FV2 length")
    ffs = img[OUTER_FFS_OFF:OUTER_FFS_OFF + OUTER_FFS_SIZE]
    if str(uuid.UUID(bytes_le=bytes(ffs[:16]))) != "9e21fd93-9c72-4c15-8c4b-e77f1db2d792":
        raise SystemExit("outer FFS GUID mismatch")
    if u24(ffs, 0x14) != OUTER_FFS_SIZE or ffs[0x17] != 0xF8:
        raise SystemExit("outer FFS size/state mismatch")
    sec = ffs[24:24 + OUTER_SEC_SIZE]
    if u24(sec) != OUTER_SEC_SIZE or sec[3] != 0x02:
        raise SystemExit("outer section header mismatch")
    if uuid.UUID(bytes_le=bytes(sec[4:20])) != LZMA_GUID:
        raise SystemExit("outer section is not LZMA")
    if int.from_bytes(sec[20:22], "little") != 0x18:
        raise SystemExit("unexpected LZMA data offset")

    # --- decompress inner stream ---
    payload = bytes(sec[24:])
    inner_stream = bytearray(lzma.decompress(payload, format=lzma.FORMAT_ALONE))
    if len(inner_stream) != UNCOMP_SIZE:
        raise SystemExit(f"unexpected inner size {len(inner_stream):#x}")
    inner_fv = bytearray(inner_stream[INNER_FV_OFF:INNER_FV_OFF + INNER_FV_LEN])
    if inner_fv[0x28:0x2C] != b"_FVH":
        raise SystemExit("inner FV signature missing")
    verify_ffs(inner_fv, "inner FV (original)")

    # --- replace the boot logo first (it grows the inner FV) ---
    inner_fv, boot_logo_off, boot_logo_bytes = patch_boot_logo(inner_fv)
    verify_ffs(inner_fv, "inner FV (logo)")
    verify_fv_block_map(inner_fv, "inner FV (logo)")

    # --- keep the stock 1.68 FFS and append the 2.10 FFS ---
    old_off, old_sz = find_ffs_by_guid(inner_fv, str(ARM_GOP_GUID))
    old_pe = pe_of_ffs(inner_fv, str(ARM_GOP_GUID))
    if hashlib.sha256(old_pe).hexdigest() != ORIG_168_PE_SHA:
        raise SystemExit("source Arm64Gop is not the pristine 1.68 PE")

    new_pe = open(args.gop210, "rb").read()
    if new_pe[:2] != b"MZ":
        raise SystemExit("--gop210 is not an MZ image")
    new_sha = hashlib.sha256(new_pe).hexdigest()
    if len(new_pe) != 0x18E30:
        raise SystemExit(f"unexpected --gop210 size {len(new_pe):#x}")
    if new_sha != ARM64GOP_2_10_SHA:
        raise SystemExit(f"--gop210 SHA mismatch: {new_sha}")

    post_guid_str = str(POST_GOP_FFS_GUID)
    if any(g == post_guid_str for _, _, g in iter_ffs(inner_fv)):
        raise SystemExit("source already contains the post-SoC15 GOP FFS")

    new_ffs = build_gop_ffs(new_pe, post_guid_str, POST_GOP_UI_NAME)
    new_fv, insert = append_ffs_to_fv(inner_fv, new_ffs)
    verify_ffs(new_fv, "inner FV (dual)")
    verify_fv_block_map(new_fv, "inner FV (dual)")
    final_stream = replace_stream_fv(inner_stream, new_fv)
    print(
        f"dual GOP: old 1.68 FFS @ inner {old_off:#x} (PE "
        f"{hashlib.sha256(old_pe).hexdigest()[:16]}...); "
        f"new FFS @ inner {insert:#x}, size {len(new_ffs):#x}, "
        f"GUID {post_guid_str}, name {POST_GOP_UI_NAME!r}; "
        f"inner FV {len(new_fv):#x}"
    )

    # --- recompress and rebuild outer section/FFS ---
    new_payload = comp_lzma(bytes(final_stream))
    new_sec_size = 24 + len(new_payload)
    new_ffs_size = 24 + new_sec_size
    if OUTER_FFS_OFF + new_ffs_size > FV2_OFF + FV2_LEN:
        raise SystemExit("new FFS does not fit in FV2")
    print(f"new section {new_sec_size:#x}; new FFS size {new_ffs_size:#x} (old {OUTER_FFS_SIZE:#x})")

    new_file = bytearray(b"\xff" * new_ffs_size)
    new_file[0:24] = img[OUTER_FFS_OFF:OUTER_FFS_OFF + 24]
    p24(new_file, 0x14, new_ffs_size)
    new_file[0x10] = 0
    new_file[0x11] = 0
    new_file[0x10] = checksum8(new_file[:0x17])
    new_file[0x11] = 0xAA
    sec_bytes = bytearray(new_sec_size)
    p24(sec_bytes, 0, new_sec_size)
    sec_bytes[3] = 0x02
    sec_bytes[4:20] = LZMA_GUID.bytes_le
    struct.pack_into("<HH", sec_bytes, 20, 0x18, 0x01)
    sec_bytes[24:] = new_payload
    new_file[24:24 + new_sec_size] = sec_bytes

    out = bytearray(img)
    out[OUTER_FFS_OFF:OUTER_FFS_OFF + new_ffs_size] = new_file
    if new_ffs_size < OUTER_FFS_SIZE:
        # The freed tail of the old file region must become FV free space.
        out[OUTER_FFS_OFF + new_ffs_size:OUTER_FFS_OFF + OUTER_FFS_SIZE] = (
            b"\xff" * (OUTER_FFS_SIZE - new_ffs_size)
        )

    # --- verify output ---
    check_fv = bytes(out[FV2_OFF:FV2_OFF + FV2_LEN])
    hdr = bytearray(check_fv[:0x48])
    stored = int.from_bytes(hdr[0x32:0x34], "little")
    hdr[0x32:0x34] = b"\x00\x00"
    s16 = sum(int.from_bytes(hdr[i:i + 2], "little") for i in range(0, len(hdr), 2)) & 0xFFFF
    if (0x10000 - s16) & 0xFFFF != stored:
        raise SystemExit("FV2 header checksum invalid after rebuild")
    verify_ffs(check_fv, "FV2 (output)")

    out_ffs = bytes(out[OUTER_FFS_OFF:OUTER_FFS_OFF + new_ffs_size])
    if str(uuid.UUID(bytes_le=bytes(out_ffs[:16]))) != "9e21fd93-9c72-4c15-8c4b-e77f1db2d792":
        raise SystemExit("output FFS GUID mismatch")
    out_sec_size = u24(out_ffs, 24)
    out_sec = out_ffs[24:24 + out_sec_size]
    out_payload = bytes(out_sec[24:])
    out_inner = lzma.decompress(out_payload, format=lzma.FORMAT_ALONE)
    out_fv_len = u24(out_inner, 0x7C) - 4
    if out_fv_len <= 0 or len(out_inner) != 0x80 + out_fv_len:
        raise SystemExit("output dual inner length mismatch")
    out_inner_fv = out_inner[0x80:0x80 + out_fv_len]
    verify_ffs(out_inner_fv, "inner FV (dual output)")
    verify_fv_block_map(out_inner_fv, "inner FV (dual output)")
    if out_inner_fv[boot_logo_off:boot_logo_off + len(boot_logo_bytes)] != boot_logo_bytes:
        raise SystemExit("output is missing the boot logo replacement")
    print("output boot logo matches the generated BMP")
    off = BIOS_VERSION_BLOCK_OFF
    if out[off:off + len(BIOS_VERSION_BLOCK_NEW)] != BIOS_VERSION_BLOCK_NEW:
        raise SystemExit("output BIOS version field was not updated")
    off = HOB_VERSION_OFF
    if out[off:off + HOB_VERSION_PATCH_LEN] != HOB_VERSION_PATCH_NEW:
        raise SystemExit("output VersionInfoPeim default version was not updated")
    off = HOB_VERSION_COPY_OFF
    if out[off:off + len(HOB_VERSION_COPY_NEW)] != HOB_VERSION_COPY_NEW:
        raise SystemExit("output VersionInfoPeim copy length was not updated")
    print(f"output BIOS version fields are {CUSTOM_VERSION_TAG}")
    old_pe2 = pe_of_ffs(out_inner_fv, str(ARM_GOP_GUID))
    new_pe2 = pe_of_ffs(out_inner_fv, post_guid_str)
    if old_pe2 != old_pe:
        raise SystemExit("dual output: old 1.68 PE changed")
    if new_pe2 != new_pe:
        raise SystemExit("dual output: new 2.10 PE mismatch")
    print("dual output: old 1.68 PE unchanged; new post-SoC15 PE matches")

    # difference bounds
    diffs = [i for i in range(len(orig_img)) if orig_img[i] != out[i]]
    first = diffs[0] if diffs else None
    last = diffs[-1] if diffs else None
    print(
        f"diff range: {first:#x}..{last:#x} ({len(diffs)} bytes)"
        if diffs else "no diffs"
    )
    allowed = [
        (BIOS_VERSION_BLOCK_OFF, BIOS_VERSION_BLOCK_OFF + len(BIOS_VERSION_BLOCK_NEW)),
        (HOB_VERSION_OFF, HOB_VERSION_OFF + HOB_VERSION_PATCH_LEN),
        (HOB_VERSION_COPY_OFF, HOB_VERSION_COPY_OFF + len(HOB_VERSION_COPY_NEW)),
        (OUTER_FFS_OFF, OUTER_FFS_OFF + max(OUTER_FFS_SIZE, new_ffs_size)),
    ]
    for i in diffs:
        if not any(a <= i < b for a, b in allowed):
            raise SystemExit(f"unexpected diff at {i:#x}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_sha = hashlib.sha256(out).hexdigest()
    if out_path.exists() and not args.force:
        existing_sha = hashlib.sha256(out_path.read_bytes()).hexdigest()
        if existing_sha != out_sha:
            raise SystemExit(
                f"{out_path} already exists with SHA-256 {existing_sha} "
                f"(new build is {out_sha}); use --force to overwrite"
            )
    out_path.write_bytes(out)
    print("custom version", CUSTOM_VERSION_TAG)
    print("output sha256", out_sha)
    print("wrote", out_path)


if __name__ == "__main__":
    main()
