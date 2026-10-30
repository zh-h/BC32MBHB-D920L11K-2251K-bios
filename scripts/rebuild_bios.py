#!/usr/bin/env python3
"""Rebuild KP920 BIOS image with a patched Arm64Gop PE (or a harmless canary).

Only the compressed DXE FV's outer FFS file is modified. FFS header checksums
are left untouched for data-only changes; the EDK2 FFS file checksum field is
the fixed marker 0xAA (verified on all 39 top-level FFS files).
"""
import argparse
import hashlib
import lzma
import struct
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

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


def find_inner_gop(inner_fv):
    ln = int.from_bytes(inner_fv[0x20:0x28], "little")
    hdr = int.from_bytes(inner_fv[0x30:0x32], "little")
    p = hdr
    while p + 24 <= ln:
        name = inner_fv[p:p + 16]
        sz = u24(inner_fv, p + 0x14)
        state = inner_fv[p + 0x17]
        if state == 0xFF or sz < 24 or p + sz > ln:
            break
        if str(uuid.UUID(bytes_le=bytes(name))) == str(ARM_GOP_GUID):
            return p, sz
        p = (p + sz + 7) & ~7
    raise RuntimeError("Arm64Gop FFS not found")


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
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--src",
        default=str(ROOT / "firmware" / "original" / "BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22).bin"),
    )
    ap.add_argument("--patched", default=str(ROOT / "drivers" / "Arm64Gop_vega20_min.efi"))
    ap.add_argument(
        "--out",
        default=str(ROOT / "firmware" / "modified" / "BC32MBHB-D920L11K-2251K-0.23 (1.0 - 2020.07.22)-modified.bin"),
    )
    ap.add_argument("--canary", action="store_true", help="only change the Arm64Gop UI name")
    args = ap.parse_args()

    img = bytearray(open(args.src, "rb").read())
    if len(img) != 16 * 1024 * 1024:
        raise SystemExit("source is not 16 MiB")
    print("source sha256", hashlib.sha256(img).hexdigest())

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

    # --- locate and modify Arm64Gop ---
    gop_off, gop_size = find_inner_gop(inner_fv)
    print(f"Arm64Gop FFS @ inner {gop_off:#x}, size {gop_size:#x}")
    pe_sec = None
    for p, sz, typ, body in parse_sections(inner_fv[gop_off + 24:gop_off + gop_size]):
        if typ == 0x10:
            pe_sec = (p, sz, body)
            break
    if pe_sec is None:
        raise SystemExit("PE32 section not found")
    p, pe_sec_size, pe = pe_sec
    if len(pe) != 0x216C0 or pe[:2] != b"MZ":
        raise SystemExit("unexpected Arm64Gop PE")

    if args.canary:
        # UI section is right after the PE section; change one UTF-16 character.
        ui_start = p + pe_sec_size
        ui_sz = u24(inner_fv, gop_off + 24 + ui_start)
        ui_body_off = gop_off + 24 + ui_start + 4
        if ui_sz < 6 or ui_body_off + (ui_sz - 4) > gop_off + gop_size:
            raise SystemExit("UI section not found")
        ui_body_len = ui_sz - 4
        old = inner_fv[ui_body_off:ui_body_off + ui_body_len]
        # "Arm64Gop" -> "Arm64GoX" (harmless display-name change)
        new = bytearray(old)
        if new[-2:] == b"p\x00":
            new[-2:] = b"X\x00"
        else:
            new[-1] ^= 0x01
        inner_fv[ui_body_off:ui_body_off + ui_body_len] = new
        print("canary: changed Arm64Gop UI name", old.hex(), "->", bytes(new).hex())
    else:
        patched = open(args.patched, "rb").read()
        if len(patched) != len(pe):
            raise SystemExit(f"patched PE size {len(patched):#x} != {len(pe):#x}")
        pe_abs = gop_off + 24 + p + 4
        inner_fv[pe_abs:pe_abs + len(pe)] = patched
        print(f"replaced PE at inner {pe_abs:#x} with {args.patched}")

    verify_ffs(inner_fv, "inner FV (modified)")

    # --- recompress and rebuild outer section/FFS ---
    inner_stream[INNER_FV_OFF:INNER_FV_OFF + INNER_FV_LEN] = inner_fv
    new_payload = comp_lzma(bytes(inner_stream))
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
    if len(out_inner) != UNCOMP_SIZE:
        raise SystemExit("output inner size mismatch")
    out_inner_fv = out_inner[INNER_FV_OFF:INNER_FV_OFF + INNER_FV_LEN]
    verify_ffs(out_inner_fv, "inner FV (output)")
    if args.canary:
        print("output inner FV differs at expected UI bytes")
    else:
        gop2, gop2_size = find_inner_gop(out_inner_fv)
        pe2 = None
        for p2, sz2, typ2, body2 in parse_sections(out_inner_fv[gop2 + 24:gop2 + gop2_size]):
            if typ2 == 0x10:
                pe2 = body2
                break
        if pe2 != open(args.patched, "rb").read():
            raise SystemExit("output PE does not match patched driver")
        print("output PE matches patched driver")

    # difference bounds
    first = next((i for i in range(len(img)) if img[i] != out[i]), None)
    last = next((i for i in range(len(img) - 1, -1, -1) if img[i] != out[i]), None)
    print(f"diff range: {first:#x}..{last:#x}" if first is not None else "no diffs")
    if first is not None and first < OUTER_FFS_OFF:
        raise SystemExit("unexpected diff before outer FFS")
    if last is not None and last >= OUTER_FFS_OFF + max(OUTER_FFS_SIZE, new_ffs_size):
        raise SystemExit("unexpected diff after outer FFS")

    open(args.out, "wb").write(out)
    print("output sha256", hashlib.sha256(out).hexdigest())
    print("wrote", args.out)


if __name__ == "__main__":
    main()
