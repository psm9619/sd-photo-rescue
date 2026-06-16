#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Self-tests for sd-photo-rescue. Run: python3 tests/test_recover.py"""
import os
import sys
import struct
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import recover as R


def seg(marker, payload):
    return bytes([0xFF, marker]) + struct.pack(">H", len(payload) + 2) + payload


def make_jpeg():
    thumb = b"\xff\xd8\xff\xdb\x00\x10" + b"\x00" * 14 + b"\xff\xd9"   # embedded thumbnail
    app1 = seg(0xE1, b"Exif\x00\x00" + b"MM\x00\x2a\x00\x00\x00\x08" + thumb)
    app0 = seg(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
    sof = seg(0xC0, b"\x08\x00\x10\x00\x10\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01")
    sos = seg(0xDA, b"\x01\x01\x00\x00\x3f\x00")
    return b"\xff\xd8" + app0 + app1 + sof + sos + b"\x12\xff\x00\xff\xd0\x34" + b"\xff\xd9"


def make_iso_heic():
    ftyp = struct.pack(">I", 24) + b"ftyp" + b"heic" + struct.pack(">I", 0) + b"mif1heic"
    mdat = struct.pack(">I", 16) + b"mdat" + b"ABCDEFGH"
    assert len(ftyp) == 24 and len(mdat) == 16
    return ftyp + mdat


def make_raf():
    hdr = bytearray(b"\x00" * 0x80)
    hdr[0:15] = b"FUJIFILMCCD-RAW"
    struct.pack_into(">I", hdr, 0x54, 0x80)     # jpg_offset
    struct.pack_into(">I", hdr, 0x58, 40)       # jpg_size
    struct.pack_into(">I", hdr, 0x64, 0x80)     # cfa_offset
    struct.pack_into(">I", hdr, 0x68, 100)      # cfa_size  -> end = 0x80 + 100 = 228
    return bytes(hdr) + b"\xab" * 100


def make_tiff_with_date(dstr="2026:06:12 10:00:00"):
    le = "<"
    s = dstr.encode() + b"\x00"
    ifd0, exif, data = 8, 26, 44
    buf = bytearray()
    buf += b"II" + struct.pack(le + "H", 0x2A) + struct.pack(le + "I", ifd0)
    buf += struct.pack(le + "H", 1)
    buf += struct.pack(le + "HHI", 0x8769, 4, 1) + struct.pack(le + "I", exif)
    buf += struct.pack(le + "I", 0)
    buf += struct.pack(le + "H", 1)
    buf += struct.pack(le + "HHI", 0x9003, 2, len(s)) + struct.pack(le + "I", data)
    buf += struct.pack(le + "I", 0)
    buf += s
    return bytes(buf)


def tmpfile(data):
    f = tempfile.NamedTemporaryFile(delete=False)
    f.write(data)
    f.close()
    return f.name


def test_jpeg_end():
    j = make_jpeg()
    buf = b"\x00" * 1000 + j + b"\xcd" * 500
    path = tmpfile(buf)
    r = R.Reader(path)
    try:
        soi = r.find(b"\xff\xd8\xff")
        assert soi == 1000, soi
        end = R.find_jpeg_end(r, soi, r.size)
        assert end == 1000 + len(j), (end, 1000 + len(j))   # not fooled by thumbnail
        assert r[soi:end][-2:] == b"\xff\xd9"
        print(f"  [OK] JPEG end (skips embedded thumbnail): {len(j)}B")
    finally:
        r.close(); os.unlink(path)


def test_iso():
    f = make_iso_heic()
    path = tmpfile(b"\x00" * 64 + f + b"\x00" * 64)
    r = R.Reader(path)
    try:
        ft = r.find(b"ftyp")
        start = ft - 4
        end = R.iso_bmff_length(r, start, r.size)
        assert end == start + len(f), (end, start + len(f))
        assert R.iso_ext(b"heic") == "heic" and R.iso_ext(b"crx ") == "cr3"
        assert R.iso_ext(b"qt  ") == "mov" and R.iso_ext(b"mp42") == "mp4"
        print(f"  [OK] ISO-BMFF box-walk length ({len(f)}B) + brand classify")
    finally:
        r.close(); os.unlink(path)


def test_raf():
    f = make_raf()
    path = tmpfile(f)
    r = R.Reader(path)
    try:
        end = R.raf_length(r, 0, r.size)
        assert end == 228, end
        print(f"  [OK] RAF header-driven length: {end}B")
    finally:
        r.close(); os.unlink(path)


def test_exif_date():
    from datetime import datetime
    tiff = make_tiff_with_date()
    assert R.exif_datetime(tiff) == datetime(2026, 6, 12, 10, 0, 0)
    j = make_jpeg()  # has MM exif but no DateTimeOriginal -> None is fine
    R.exif_datetime(j)
    print("  [OK] EXIF date from TIFF-based RAW header")


def test_carve_end_to_end():
    j = make_jpeg()
    iso = make_iso_heic()
    raf = make_raf()
    img = (b"\x00" * 2048 + j + b"\x11" * 777 + iso + b"\x22" * 333 + raf + b"\x33" * 999)
    path = tmpfile(img)
    out = tempfile.mkdtemp()
    r = R.Reader(path)
    saved_min = R.MIN_SIZE
    R.MIN_SIZE = 16          # synthetic files are tiny; real default (8KB) is fine
    try:
        stats = R.carve(r, r.size, out, ["jpeg", "iso", "raf", "tiff", "orf", "rw2"],
                        None, None, progress=False)
        files = sorted(os.listdir(out))
        exts = sorted(os.path.splitext(f)[1] for f in files if not f.startswith("_"))
        assert stats["saved"] >= 3, stats
        assert ".jpg" in exts and ".heic" in exts and ".raf" in exts, exts
        # byte-exactness of the JPEG
        jpgs = [f for f in files if f.endswith(".jpg")]
        with open(os.path.join(out, jpgs[0]), "rb") as fh:
            assert fh.read() == j
        print(f"  [OK] end-to-end carve: {stats['saved']} files, types={exts}")
    finally:
        R.MIN_SIZE = saved_min
        r.close(); os.unlink(path)
        for f in os.listdir(out):
            os.unlink(os.path.join(out, f))


def make_tiff_raw():
    # CR2-like TIFF: main strip data far out, plus an embedded JPEG preview signature
    # at offset 2000 (the trap that the old code truncated on).
    buf = bytearray(55000)
    le = "<"
    buf[0:4] = b"II\x2a\x00"
    struct.pack_into(le + "I", buf, 4, 8)          # IFD0 at offset 8
    struct.pack_into(le + "H", buf, 8, 4)          # 4 entries
    def entry(o, tag, val):
        struct.pack_into(le + "HHII", buf, o, tag, 4, 1, val)   # tag, LONG, count1, value
    entry(10, 0x0111, 5000)        # StripOffsets
    entry(22, 0x0117, 50000)       # StripByteCounts -> extent 55000
    entry(34, 0x0201, 2000)        # JPEGInterchangeFormat (preview at 2000)
    entry(46, 0x0202, 1000)        # JPEGInterchangeFormatLength
    struct.pack_into(le + "I", buf, 58, 0)         # next IFD = 0
    buf[2000:2003] = b"\xff\xd8\xff"               # embedded preview signature
    return bytes(buf)


def test_tiff_no_truncation():
    raw = make_tiff_raw()
    path = tmpfile(raw)
    r = R.Reader(path)
    try:
        end = R.tiff_length(r, 0, r.size)
        assert end == 55000, end       # full extent, NOT truncated to the preview at 2000
        print(f"  [OK] TIFF RAW true extent via IFD walk (not truncated at preview): {end}B")
    finally:
        r.close(); os.unlink(path)


def test_jpeg_dimensions():
    assert R.jpeg_dimensions(make_jpeg()) == (16, 16)
    print("  [OK] JPEG dimensions read from SOF (for megapixel check)")


def test_truthy():
    assert R._truthy("1") and R._truthy(1) and R._truthy(True) and R._truthy("true")
    assert not R._truthy("0") and not R._truthy(0) and not R._truthy(None) and not R._truthy("")
    print("  [OK] _truthy normalizes lsblk string/bool/int (Linux disk safety)")


def test_disk_parsers_smoke():
    # parsers must not crash even if the OS tools aren't present
    R.list_disks()
    assert R.human(1536) == "1.5KB"
    print("  [OK] disk listing + helpers smoke")


if __name__ == "__main__":
    print("sd-photo-rescue self-tests:")
    test_jpeg_end()
    test_iso()
    test_raf()
    test_exif_date()
    test_tiff_no_truncation()
    test_jpeg_dimensions()
    test_truthy()
    test_carve_end_to_end()
    test_disk_parsers_smoke()
    print("ALL PASSED ✅")
