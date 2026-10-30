#!/usr/bin/env python3
"""Minimal Vega 20 patch for AMD Arm64Gop_1_68.efi.

Only the first name-table entry (PE 0x1DD90) is changed to 0x66A1.  The
device range entry at 0x1D320 and its family byte 0x0107 stay untouched.
The driver's lookup scans the name array before the range check, so 0x66A1
binds; Start is VBIOS/ATOMBIOS-driven, so the family byte is not a handler
selector.

Also builds an unsigned variant by zeroing the PE Security data directory.
"""
import hashlib
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "drivers" / "Arm64Gop_1_68.efi"
OUT = ROOT / "drivers" / "Arm64Gop_vega20_min.efi"
OUT_UNSIGNED = ROOT / "drivers" / "Arm64Gop_vega20_min_unsigned.efi"
NAME_OFF = 0x1DD90
NAME_ID = 0x66A1
NAME_STR = 0x191D0  # "AMD Radeon VegaM Graphics" (cosmetic)


def pe_checksum(data: bytes) -> int:
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    ckoff = pe + 0x58
    b = bytearray(data)
    b[ckoff:ckoff + 4] = b"\0\0\0\0"
    if len(b) % 2:
        b += b"\0"
    s = 0
    for i in range(0, len(b), 2):
        s += b[i] | (b[i + 1] << 8)
        s = (s & 0xFFFF) + (s >> 16)
    s = (s & 0xFFFF) + (s >> 16)
    return (s + len(data)) & 0xFFFFFFFF


def fix_checksum(data: bytearray) -> None:
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    struct.pack_into("<I", data, pe + 0x58, pe_checksum(data))


def main() -> int:
    src = open(SRC, "rb").read()
    if len(src) != 0x216C0:
        raise SystemExit("unexpected source size")

    b = bytearray(src)
    struct.pack_into("<IIQ", b, NAME_OFF, NAME_ID, 0, NAME_STR)
    fix_checksum(b)
    open(OUT, "wb").write(b)
    print(OUT, len(b), hashlib.sha256(b).hexdigest())

    pe = struct.unpack_from("<I", b, 0x3C)[0]
    sec_off, sec_size = struct.unpack_from("<II", b, pe + 0xA8)
    print(f"Security directory: file offset {sec_off:#x}, size {sec_size:#x}")
    ub = bytearray(b)
    struct.pack_into("<II", ub, pe + 0xA8, 0, 0)
    fix_checksum(ub)
    open(OUT_UNSIGNED, "wb").write(ub)
    print(OUT_UNSIGNED, len(ub), hashlib.sha256(ub).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
