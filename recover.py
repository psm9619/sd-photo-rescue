#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sd-photo-rescue — recover photos/videos from a formatted or corrupted SD card.

What it does
------------
When a camera/computer "formats" a card it usually only erases the file table,
not the photo data. This tool reads the card *read-only* and rebuilds files by
scanning their raw bytes for known signatures ("file carving"): JPEG, the common
camera RAW formats (CR2, CR3, NEF, ARW, RAF, ORF, RW2, DNG, HEIC) and video
(MP4/MOV). It can optionally keep only files shot in a date range (from EXIF).

It NEVER writes to the card. The card is opened O_RDONLY; recovered files are
written to a separate output folder.

Usage
-----
Easiest (interactive wizard — just answer the questions):

    sudo python3 recover.py

Advanced (flags; anything you omit is asked interactively):

    sudo python3 recover.py --disk /dev/disk4 --out ~/recovered \\
        --types jpeg,raw,video --date-from 2026-06-12 --date-to 2026-06-12

Other:
    python3 recover.py --list                 # just list disks and exit
    python3 recover.py --image card.img --out ~/recovered   # work on an image file

Requirements: Python 3 (standard library only). macOS or Linux.
Root/sudo is needed to read a raw device (not needed for --image).
"""

import sys
import os
import struct
import argparse
import subprocess
import json
import platform
from datetime import datetime

try:
    import plistlib  # macOS disk listing
except Exception:  # pragma: no cover
    plistlib = None

# --------------------------------------------------------------------------- #
#  Tunables
# --------------------------------------------------------------------------- #
MIN_SIZE = 8 * 1024                  # ignore carved fragments smaller than this
JPEG_MAX = 64 * 1024 * 1024          # max size of one JPEG
TIFF_MAX = 200 * 1024 * 1024         # max size of one TIFF-based RAW
RAF_MAX = 300 * 1024 * 1024          # max size of one Fujifilm RAF
ISO_MAX = 16 * 1024 * 1024 * 1024    # max size of one ISO-BMFF file (HEIC/CR3/MP4/MOV)
SCAN_CHUNK = 64 * 1024 * 1024        # bytes read per scan window
IS_WINDOWS = os.name == "nt"


# --------------------------------------------------------------------------- #
#  Read-only reader for a device OR an image file (mmap-like interface)
# --------------------------------------------------------------------------- #
class Reader:
    """Read-only access to a raw device or image file with a cached window.

    Supports the small subset we need: r[i], r[a:b], r.find(sub, start, end).
    Works on both macOS (/dev/rdiskN) and Linux (/dev/sdX) and on plain files.
    """

    CACHE = 96 * 1024 * 1024
    DIRECT = 8 * 1024 * 1024

    def __init__(self, path):
        self.path = path
        self.fd = os.open(path, os.O_RDONLY)
        self.block = self._detect_block()
        self.size = self._detect_size(path)
        self._buf = b""
        self._bs = 0
        self._be = 0
        self.progress = False
        self._last = 0

    def _detect_block(self):
        for b in (512, 4096):
            try:
                os.lseek(self.fd, 0, os.SEEK_SET)
                if os.read(self.fd, b):
                    return b
            except OSError:
                continue
        return 512

    def _detect_size(self, path):
        try:
            n = os.lseek(self.fd, 0, os.SEEK_END)
            if n and n > 0:
                return n
        except OSError:
            pass
        # Fallbacks for raw devices that don't report size via lseek
        try:
            if sys.platform == "darwin":
                out = subprocess.check_output(["diskutil", "info", path],
                                              stderr=subprocess.DEVNULL).decode("utf-8", "ignore")
                for line in out.splitlines():
                    if "Disk Size" in line or "Total Size" in line:
                        i, j = line.find("("), line.find(" Bytes")
                        if 0 <= i < j:
                            return int(line[i + 1:j].strip())
            else:
                out = subprocess.check_output(["blockdev", "--getsize64", path],
                                              stderr=subprocess.DEVNULL).decode().strip()
                return int(out)
        except Exception:
            pass
        return 0

    def _raw_read(self, start, length):
        if start < 0:
            start = 0
        a = (start // self.block) * self.block
        e = ((start + length + self.block - 1) // self.block) * self.block
        if self.size:
            e = min(e, ((self.size + self.block - 1) // self.block) * self.block)
        out = bytearray()
        need = e - a
        while len(out) < need:
            os.lseek(self.fd, a + len(out), os.SEEK_SET)
            chunk = os.read(self.fd, need - len(out))
            if not chunk:
                break
            out += chunk
        return bytes(out), a

    def _ensure(self, start, length):
        if self._buf and self._bs <= start and start + length <= self._be:
            return
        self._buf, self._bs = self._raw_read(start, max(length, self.CACHE))
        self._be = self._bs + len(self._buf)
        if self.progress and self._be - self._last >= 4 * 1024 * 1024 * 1024:
            print(f"      ... {human(self._be)} read", flush=True)
            self._last = self._be

    def __getitem__(self, key):
        if isinstance(key, slice):
            a = key.start or 0
            b = key.stop if key.stop is not None else self.size
            n = b - a
            if n <= 0:
                return b""
            if n > self.DIRECT:
                data, st = self._raw_read(a, n)
                return data[a - st:a - st + n]
            self._ensure(a, n)
            o = a - self._bs
            return self._buf[o:o + n]
        self._ensure(key, 1)
        return self._buf[key - self._bs]

    def find(self, sub, start=0, end=None):
        hard = self.size or None
        if end is None:
            end = hard or (1 << 62)
        elif hard:
            end = min(end, hard)
        ov = len(sub) - 1
        pos = start
        while pos < end:
            self._ensure(pos, min(self.CACHE, end - pos))
            if self._be <= pos:
                break
            win_end = min(self._be, end)
            idx = self._buf.find(sub, pos - self._bs, win_end - self._bs)
            if idx != -1:
                return self._bs + idx
            if win_end >= end or (hard and self._be >= hard):
                break
            pos = win_end - ov
        return -1

    def close(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None


# --------------------------------------------------------------------------- #
#  JPEG: walk marker segments to find the true EOI (ignores embedded thumbnail)
# --------------------------------------------------------------------------- #
def find_jpeg_end(r, start, size):
    end_limit = min(start + JPEG_MAX, size)
    p = start + 2
    while p < end_limit - 1:
        if r[p] != 0xFF:
            return None
        while p < end_limit and r[p] == 0xFF:
            p += 1
        if p >= end_limit:
            return None
        marker = r[p]
        p += 1
        if marker == 0xD9:                       # EOI = real end
            return p
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if marker == 0xDA:                       # SOS: scan entropy data
            if p + 1 >= end_limit:
                return None
            seglen = (r[p] << 8) | r[p + 1]
            p += seglen
            while p < end_limit:
                nf = r.find(b"\xff", p, end_limit)
                if nf == -1 or nf >= end_limit - 1:
                    return None
                b = r[nf + 1]
                if b == 0x00 or 0xD0 <= b <= 0xD7:
                    p = nf + 2
                    continue
                if b == 0xFF:
                    p = nf + 1
                    continue
                p = nf
                break
            else:
                return None
            continue
        if p + 1 >= end_limit:
            return None
        seglen = (r[p] << 8) | r[p + 1]
        if seglen < 2:
            return None
        p += seglen
    return None


# --------------------------------------------------------------------------- #
#  ISO Base Media File Format (HEIC / CR3 / MP4 / MOV): walk top-level boxes
# --------------------------------------------------------------------------- #
# Recognised ISO-BMFF top-level box types. An unknown 4CC marks end-of-file
# (prevents the box-walk from swallowing trailing padding/garbage).
KNOWN_BOX = {
    b"ftyp", b"moov", b"mdat", b"free", b"skip", b"wide", b"pnot", b"uuid",
    b"meta", b"moof", b"mfra", b"styp", b"sidx", b"ssix", b"prft", b"emsg",
    b"meco", b"idat", b"mere", b"pdin", b"bloc", b"cslg",
}


def iso_bmff_length(r, start, size):
    end_limit = min(start + ISO_MAX, size)
    pos = start
    boxes = 0
    while pos + 8 <= end_limit:
        sz = struct.unpack(">I", r[pos:pos + 4])[0]
        typ = r[pos + 4:pos + 8]
        if typ not in KNOWN_BOX:
            break
        if sz == 1:                              # 64-bit largesize
            if pos + 16 > end_limit:
                break
            sz = struct.unpack(">Q", r[pos + 8:pos + 16])[0]
        elif sz == 0:                            # extends to end of medium
            pos = end_limit
            boxes += 1
            break
        if sz < 8 or sz > size - pos:        # box can't be tiny or overrun the medium
            break
        pos += sz
        boxes += 1
    if boxes >= 2 and pos > start:
        return min(pos, size)
    return None


def iso_ext(brand):
    b = brand.rstrip(b" ").lower()
    if b == b"crx":
        return "cr3"
    if b in (b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx", b"mif1", b"msf1"):
        return "heic"
    if b in (b"avif", b"avis"):
        return "avif"
    if b in (b"qt",):
        return "mov"
    if b in (b"mp41", b"mp42", b"isom", b"m4v", b"mp4v", b"msnv", b"dash"):
        return "mp4"
    if b.startswith(b"3g"):
        return "3gp"
    return "mp4"  # default container


# --------------------------------------------------------------------------- #
#  Fujifilm RAF: fixed header carries the data offsets/sizes
# --------------------------------------------------------------------------- #
def raf_length(r, start, size):
    end_limit = min(start + RAF_MAX, size)
    try:
        hdr = r[start:start + 0x80]
        if not hdr.startswith(b"FUJIFILMCCD-RAW"):
            return None
        end = 0
        for off in (0x54, 0x58, 0x5C, 0x60, 0x64, 0x68):
            val = struct.unpack(">I", hdr[off:off + 4])[0]
            end = max(end, val)
        # last pair is cfa_offset(0x64)+cfa_size(0x68)
        cfa = struct.unpack(">I", hdr[0x64:0x68])[0] + struct.unpack(">I", hdr[0x68:0x6C])[0]
        total = start + max(end, cfa)
        if start + 0x80 < total <= end_limit:
            return total
    except Exception:
        return None
    return None


# --------------------------------------------------------------------------- #
#  TIFF-based RAW classification (CR2 / NEF / ARW / DNG / ORF / RW2)
# --------------------------------------------------------------------------- #
def tiff_ext(r, start, family):
    if family == "orf":
        return "orf"
    if family == "rw2":
        return "rw2"
    head = bytes(r[start:start + 65536])
    h8 = head[:8192]
    # Canon CR2 has 'CR' at byte offset 8
    if head[8:10] == b"CR":
        return "cr2"
    if b"NIKON" in head[:4096]:
        return "nef"
    if b"SONY" in h8:
        return "arw"
    if b"PENTAX" in h8 or b"RICOH" in h8:
        return "pef"
    if b"SAMSUNG" in h8:
        return "srw"
    if b"Hasselblad" in head[:16384]:
        return "3fr"
    if b"LEICA" in h8 or b"Leica" in h8:
        return "dng"            # Leica typically uses DNG
    if b"Minolta" in h8 or b"MINOLTA" in h8:
        return "mrw"
    # DNG carries a DNGVersion tag; ASCII 'Adobe' / 'DNG' often present
    if b"DNG" in h8 or b"Adobe" in h8:
        return "dng"
    return "tif"               # unknown TIFF-based RAW: data is intact, just rename


# Compute a TIFF-based RAW's true byte length by walking its IFD chain.
# RAW files (CR2/NEF/ARW/DNG/ORF/RW2) embed full-size JPEG previews and extra
# IFDs, so we must NOT end the file at the next foreign signature (that would
# truncate it). Instead we follow IFD0 -> next-IFD -> SubIFDs -> ExifIFD and take
# the furthest byte referenced by any strip/tile/preview/value array.
_TIFF_TSZ = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8,
             11: 4, 12: 8, 13: 4, 16: 8, 17: 8, 18: 8}
TIFF_FALLBACK = 64 * 1024 * 1024     # used only if the IFD parse is inconclusive


def tiff_length(r, start, size):
    end_limit = min(start + TIFF_MAX, size)
    h = bytes(r[start:start + 2])
    if h == b"MM":
        en = ">"
    elif h[:1] == b"I":                  # II*, IIRO/IIRS (ORF), IIU (RW2)
        en = "<"
    else:
        return None

    def U16(o):
        return struct.unpack(en + "H", r[start + o:start + o + 2])[0]

    def U32(o):
        return struct.unpack(en + "I", r[start + o:start + o + 4])[0]

    def values(typ, cnt, e):
        sz = _TIFF_TSZ.get(typ, 0)
        if sz == 0 or cnt == 0 or cnt > 1000000:
            return []
        base = (e + 8) if sz * cnt <= 4 else U32(e + 8)
        out = []
        for k in range(min(cnt, 8192)):
            o = base + k * sz
            out.append(U16(o) if sz == 2 else U32(o))
        return out

    try:
        ifd0 = U32(4)
        if ifd0 < 8 or start + ifd0 + 2 > end_limit:
            return None
    except Exception:
        return None

    maxend = 0
    found_data = False
    seen = set()
    queue = [ifd0]
    guard = 0
    while queue and guard < 128:
        guard += 1
        ifd = queue.pop()
        if ifd in seen or ifd < 8 or start + ifd + 6 > end_limit:
            continue
        seen.add(ifd)
        try:
            n = U16(ifd)
        except Exception:
            continue
        if n == 0 or n > 512:
            continue
        maxend = max(maxend, ifd + 2 + n * 12 + 4)       # the IFD table itself
        strip_off = strip_cnt = tile_off = tile_cnt = None
        jpg_off = jpg_len = None
        for i in range(n):
            e = ifd + 2 + i * 12
            try:
                tag = U16(e); typ = U16(e + 2); cnt = U32(e + 4)
            except Exception:
                break
            total = _TIFF_TSZ.get(typ, 0) * cnt
            if total > 4:
                try:
                    maxend = max(maxend, U32(e + 8) + total)   # out-of-line value array
                except Exception:
                    pass
            if tag in (0x0111, 0x0117, 0x0144, 0x0145, 0x0201, 0x0202, 0x014A, 0x8769):
                v = values(typ, cnt, e)
                if tag == 0x0111:
                    strip_off = v
                elif tag == 0x0117:
                    strip_cnt = v
                elif tag == 0x0144:
                    tile_off = v
                elif tag == 0x0145:
                    tile_cnt = v
                elif tag == 0x0201:
                    jpg_off = v[0] if v else None
                elif tag == 0x0202:
                    jpg_len = v[0] if v else None
                elif tag == 0x014A:
                    queue.extend(v)
                elif tag == 0x8769 and v:
                    queue.append(v[0])
        if strip_off and strip_cnt:
            for o, c in zip(strip_off, strip_cnt):
                maxend = max(maxend, o + c); found_data = True
        if tile_off and tile_cnt:
            for o, c in zip(tile_off, tile_cnt):
                maxend = max(maxend, o + c); found_data = True
        if jpg_off and jpg_len:
            maxend = max(maxend, jpg_off + jpg_len); found_data = True
        try:
            nxt = U32(ifd + 2 + n * 12)
            if nxt:
                queue.append(nxt)
        except Exception:
            pass

    if maxend <= 0:
        return None
    end = start + maxend
    if not found_data:
        # Structure looked like TIFF but no image data tags -> over-carve a bit
        # rather than drop it (some vendor RAWs use non-standard tags).
        end = min(start + TIFF_FALLBACK, size)
    if end > end_limit or end - start < MIN_SIZE:
        return None
    return end


# --------------------------------------------------------------------------- #
#  EXIF capture date (works for JPEG and TIFF-based RAW; best effort otherwise)
# --------------------------------------------------------------------------- #
def _ifd_datetime(buf, tiff):
    try:
        bo = buf[tiff:tiff + 2]
        en = "<" if bo == b"II" else ">" if bo == b"MM" else None
        if en is None:
            return None

        def u16(o):
            return struct.unpack(en + "H", buf[o:o + 2])[0]

        def u32(o):
            return struct.unpack(en + "I", buf[o:o + 4])[0]

        def read_ifd(off):
            d = {}
            n = u16(tiff + off)
            base = tiff + off + 2
            for i in range(n):
                e = base + i * 12
                d[u16(e)] = (u16(e + 2), u32(e + 4), buf[e + 8:e + 12])
            return d

        ifd0 = read_ifd(u32(tiff + 4))
        entry = None
        if 0x8769 in ifd0:
            exif = read_ifd(struct.unpack(en + "I", ifd0[0x8769][2])[0])
            entry = exif.get(0x9003) or exif.get(0x9004)
        entry = entry or ifd0.get(0x0132)
        if not entry:
            return None
        typ, cnt, vo = entry
        if cnt <= 4:
            data = vo[:cnt]
        else:
            o = struct.unpack(en + "I", vo)[0]
            data = buf[tiff + o:tiff + o + cnt]
        s = data.split(b"\x00")[0].decode("ascii", "ignore").strip()
        return datetime.strptime(s, "%Y:%m:%d %H:%M:%S")
    except Exception:
        return None


def exif_datetime(buf):
    idx = buf.find(b"Exif\x00\x00", 0, 400000)
    if idx != -1:
        dt = _ifd_datetime(buf, idx + 6)
        if dt:
            return dt
    if buf[:2] in (b"II", b"MM"):                # raw TIFF (CR2/NEF/ARW/DNG/ORF/RW2)
        dt = _ifd_datetime(buf, 0)
        if dt:
            return dt
    j = buf.find(b"\xff\xd8\xff", 0, 600000)     # RAF etc. embed a JPEG with EXIF
    if j != -1:
        k = buf.find(b"Exif\x00\x00", j, j + 300000)
        if k != -1:
            return _ifd_datetime(buf, k + 6)
    return None


# --------------------------------------------------------------------------- #
#  Signature scan + carve
# --------------------------------------------------------------------------- #
# family -> (signature bytes, offset of signature within the file)
SIGS = {
    "jpeg": [(b"\xff\xd8\xff", 0)],
    "iso":  [(b"ftyp", 4)],
    "raf":  [(b"FUJIFILMCCD-RAW", 0)],
    "tiff": [(b"II\x2a\x00", 0), (b"MM\x00\x2a", 0)],
    "orf":  [(b"IIRO", 0), (b"IIRS", 0), (b"MMOR", 0)],
    "rw2":  [(b"IIU\x00", 0)],
}
TYPE_GROUPS = {
    "jpeg": ["jpeg"],
    "raw":  ["raf", "tiff", "orf", "rw2", "iso"],   # iso also covers CR3/HEIC
    "video": ["iso"],
}


def build_patterns(enabled_families):
    pats = []
    for fam in enabled_families:
        for sig, delta in SIGS.get(fam, []):
            pats.append((fam, sig, delta))
    return pats


def collect_signatures(r, size, families, progress=False):
    pats = build_patterns(families)
    if not pats:
        return []
    maxlen = max(len(p[1]) + p[2] for p in pats)
    overlap = maxlen + 8
    hits = set()
    pos = 0
    nextrep = 0
    while pos < size:
        chunk = r[pos:min(pos + SCAN_CHUNK, size)]
        if not chunk:
            break
        for fam, pat, delta in pats:
            i = 0
            while True:
                j = chunk.find(pat, i)
                if j == -1:
                    break
                off = pos + j - delta
                if off >= 0:
                    hits.add((off, fam))
                i = j + 1
        if progress and pos >= nextrep:
            print(f"      ... {human(pos)} scanned, {len(hits)} candidates", flush=True)
            nextrep = pos + 4 * 1024 * 1024 * 1024
        if pos + SCAN_CHUNK >= size:
            break
        pos += SCAN_CHUNK - overlap
    return sorted(hits)


def date_ok(dt, dfrom, dto):
    if dfrom is None and dto is None:
        return True
    if dt is None:
        return None            # unknown -> caller decides (keep, but mark)
    d = dt.date()
    if dfrom and d < dfrom:
        return False
    if dto and d > dto:
        return False
    return True


def human(n):
    n = float(n)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f}{u}"
        n /= 1024
    return f"{n:.1f}PB"


def jpeg_dimensions(buf):
    """Return (width, height) of a JPEG's MAIN image by reading its SOF marker.
    Segment-walking skips APP1 (so an embedded thumbnail's SOF is ignored)."""
    i, L = 2, len(buf)
    SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while i + 9 < L:
        if buf[i] != 0xFF:
            i += 1
            continue
        while i < L and buf[i] == 0xFF:
            i += 1
        if i >= L:
            break
        m = buf[i]
        i += 1
        if m == 0xD9 or m == 0x01 or 0xD0 <= m <= 0xD7:
            continue
        if i + 1 >= L:
            break
        seg = (buf[i] << 8) | buf[i + 1]
        if m in SOF:
            if i + 6 <= L:
                h = (buf[i + 3] << 8) | buf[i + 4]
                w = (buf[i + 5] << 8) | buf[i + 6]
                return (w, h)
            break
        if seg < 2:
            break
        i += seg
    return None


def carve(r, size, out_dir, families, dfrom, dto, megapixels=0, progress=False):
    print("Scanning the whole medium for file signatures (this can take a while)...")
    if progress and hasattr(r, "progress"):
        r.progress = False     # we use the scan's own progress line
    hits = collect_signatures(r, size, families, progress=progress)
    print(f"Found {len(hits)} candidate signatures. Carving...")

    os.makedirs(out_dir, exist_ok=True)
    unknown_dir = os.path.join(out_dir, "_unknown_date")
    other_dir = os.path.join(out_dir, "_other_size")
    partial_dir = os.path.join(out_dir, "_partial")
    st = {"saved": 0, "bytes": 0, "skipped_date": 0, "unknown_date": 0,
          "other_size": 0, "partial": 0, "candidates": len(hits)}
    cursor = 0
    n = len(hits)
    for idx in range(n):
        off, fam = hits[idx]
        if off < cursor:
            continue
        end = None
        ext = None
        partial = False
        if fam == "jpeg":
            ext = "jpg"
            end = find_jpeg_end(r, off, size)
            if end is None and 0xC0 <= r[off + 3] <= 0xFE:
                # damaged/truncated but looks like a real JPEG: best-effort partial
                bound = size
                for k in range(idx + 1, n):
                    if hits[k][0] > off:
                        bound = hits[k][0]
                        break
                end = min(bound, off + JPEG_MAX, size)
                partial = True
        elif fam == "iso":
            ext = iso_ext(bytes(r[off + 8:off + 12]))
            end = iso_bmff_length(r, off, size)
        elif fam == "raf":
            ext = "raf"
            end = raf_length(r, off, size)
        elif fam in ("tiff", "orf", "rw2"):
            ext = tiff_ext(r, off, fam)
            end = tiff_length(r, off, size)     # true IFD extent (no truncation)
        if not end or end - off < MIN_SIZE:
            continue

        flen = end - off
        head = bytes(r[off:off + min(flen, 512 * 1024)])
        dt = exif_datetime(head)
        if date_ok(dt, dfrom, dto) is False:
            cursor = end
            st["skipped_date"] += 1
            continue

        mp_ok = True
        if megapixels and ext in ("jpg", "raf"):
            dims = jpeg_dimensions(head)
            if dims:
                mp = dims[0] * dims[1] / 1_000_000.0
                mp_ok = (megapixels * 0.5 <= mp <= megapixels * 1.3)

        stamp = dt.strftime("%Y%m%d_%H%M%S") if dt else None
        base = f"{stamp}_off{off:012d}" if stamp else f"off{off:012d}"
        if partial:
            dest, route = partial_dir, "partial"
        elif megapixels and not mp_ok:
            dest, route = other_dir, "other"
        elif dt is None and (dfrom or dto):
            dest, route = unknown_dir, "unknown"
        else:
            dest, route = out_dir, "ok"
        os.makedirs(dest, exist_ok=True)
        fname = base + "." + ext + (".partial" if partial else "")
        path = os.path.join(dest, fname)

        wrote = 0
        p = off
        incomplete = False
        try:
            with open(path, "wb") as f:
                while p < end:
                    blk = r[p:min(p + 16 * 1024 * 1024, end)]
                    if not blk:                 # short read on damaged media
                        incomplete = True
                        break
                    f.write(blk)
                    p += len(blk)
                    wrote += len(blk)
        except OSError as e:
            import errno
            if e.errno == errno.ENOSPC:
                print(f"\n[!] Output disk is FULL after {st['saved']} files "
                      f"({human(st['bytes'])}). Free space or pick another --out folder, "
                      f"then re-run. Recovered files so far are kept.")
                try:
                    os.remove(path)
                except OSError:
                    pass
                break
            raise

        if incomplete and not partial:          # truncated by a bad read -> flag it
            os.makedirs(partial_dir, exist_ok=True)
            newp = os.path.join(partial_dir, base + "." + ext + ".partial")
            try:
                os.replace(path, newp)
            except OSError:
                pass
            st["partial"] += 1
        elif partial:
            st["partial"] += 1
        else:
            st["saved"] += 1
            if route == "other":
                st["other_size"] += 1
            elif route == "unknown":
                st["unknown_date"] += 1
        st["bytes"] += wrote
        cursor = end
        if progress and (st["saved"] + st["partial"]) % 200 == 0:
            print(f"      ... {st['saved'] + st['partial']} files carved", flush=True)

    return st


# --------------------------------------------------------------------------- #
#  Disk discovery (macOS + Linux)
# --------------------------------------------------------------------------- #
def list_disks():
    if sys.platform == "darwin":
        return _list_disks_macos()
    if sys.platform.startswith("linux"):
        return _list_disks_linux()
    return []


def _list_disks_macos():
    disks = []
    try:
        pl = plistlib.loads(subprocess.check_output(
            ["diskutil", "list", "-plist", "physical"], stderr=subprocess.DEVNULL))
    except Exception:
        return disks
    for ident in pl.get("WholeDisks", []):
        try:
            info = plistlib.loads(subprocess.check_output(
                ["diskutil", "info", "-plist", "/dev/" + ident], stderr=subprocess.DEVNULL))
        except Exception:
            continue
        disks.append({
            "id": ident,
            "node": info.get("DeviceNode", "/dev/" + ident),
            "raw": "/dev/r" + ident,
            "size": info.get("TotalSize") or info.get("Size") or 0,
            "name": info.get("MediaName", "?"),
            "internal": bool(info.get("Internal", False)),
            "removable": bool(info.get("RemovableMedia", False)
                              or info.get("RemovableMediaOrExternalDevice", False)
                              or not info.get("Internal", False)),
            "proto": info.get("BusProtocol", ""),
        })
    return disks


def _truthy(v):
    # lsblk emits booleans as real bools (new util-linux) OR "0"/"1" strings (old).
    # bool("0") is True, so normalise explicitly.
    return str(v).strip().lower() in ("1", "true", "yes")


def _list_disks_linux():
    disks = []
    try:
        data = json.loads(subprocess.check_output(
            ["lsblk", "-J", "-b", "-o",
             "NAME,SIZE,TYPE,RM,HOTPLUG,MODEL,TRAN,MOUNTPOINT"],
            stderr=subprocess.DEVNULL))
    except Exception:
        return disks
    for d in data.get("blockdevices", []):
        if d.get("type") != "disk":
            continue
        rm = _truthy(d.get("rm")) or _truthy(d.get("hotplug")) or d.get("tran") == "usb"
        disks.append({
            "id": d["name"],
            "node": "/dev/" + d["name"],
            "raw": "/dev/" + d["name"],
            "size": int(d.get("size") or 0),
            "name": d.get("model") or "?",
            "internal": not rm,
            "removable": rm,
            "proto": d.get("tran") or "",
            "children": d.get("children", []),
        })
    return disks


def unmount_disk(disk):
    """Unmount (NOT erase/eject) so the OS can't write to the card while we read."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["diskutil", "unmountDisk", disk["node"]], check=False)
        else:
            # walk the tree deepest-first; unmount anything that has a mountpoint
            def walk(nodes):
                for nd in nodes or []:
                    yield from walk(nd.get("children"))
                    yield nd
            failed = []
            for nd in walk(disk.get("children")):
                mps = nd.get("mountpoints") or ([nd.get("mountpoint")] if nd.get("mountpoint") else [])
                if any(mps):
                    rc = subprocess.run(["umount", "/dev/" + nd["name"]], check=False)
                    if rc.returncode != 0:
                        failed.append(nd["name"])
            if failed:
                print(f"[!] Could not unmount: {', '.join(failed)}. If your file manager "
                      f"re-mounts the card, unmount it manually before continuing.")
    except Exception:
        pass


def is_root():
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


# --------------------------------------------------------------------------- #
#  Interactive wizard
# --------------------------------------------------------------------------- #
def ask(prompt, default=None):
    s = input(prompt).strip()
    return s if s else (default if default is not None else "")


def parse_date(s):
    s = s.strip()
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d").date()


def choose_disk_interactive(show_all=False):
    disks = list_disks()
    if not disks:
        if sys.platform == "darwin":
            print("No disk found. Make sure the card is fully inserted, try another USB port,")
            print("and check it shows in Disk Utility. On recent macOS you may need to give")
            print("Terminal 'Full Disk Access' (System Settings > Privacy & Security).")
            print("You can also work from an image file with:  --image <file>")
        else:
            print("No disk found. Run with sudo, make sure the card is connected, and that")
            print("'lsblk' is installed. You can also work from an image file: --image <file>")
        return None
    external = [d for d in disks if d["removable"] and not d["internal"]]
    if show_all or not external:
        if not external and not show_all:
            print("No external/removable card detected — showing ALL disks.")
            print("Pick your CARD (usually the small external one), NOT an internal disk.\n")
        ordered = [d for d in disks if not d["internal"]] + [d for d in disks if d["internal"]]
    else:
        ordered = external
    print("\nDetected disks:\n")
    for i, d in enumerate(ordered, 1):
        flag = "   <-- INTERNAL/SYSTEM (avoid)" if d["internal"] else ""
        print(f"  [{i}] {d['node']:<14} {human(d['size']):>9}  {d['name']} ({d['proto']}){flag}")
    print("  [a] show ALL disks    [q] quit")
    print("(Reading is harmless even if you pick wrong — it never writes — but pick your card.)")
    while True:
        sel = ask("\nWhich disk is your card? enter the number: ").lower()
        if sel == "q":
            return None
        if sel == "a":
            return choose_disk_interactive(show_all=True)
        if sel.isdigit() and 1 <= int(sel) <= len(ordered):
            d = ordered[int(sel) - 1]
            if d["internal"]:
                c = ask(f"!! {d['node']} looks like an INTERNAL/SYSTEM disk. "
                        f"Type 'yes' to use it anyway: ")
                if c.lower() != "yes":
                    continue
            print(f"\nSelected: {d['node']}  {human(d['size'])}  {d['name']}")
            if ask("Is this correct? [y/N]: ").lower() == "y":
                return d
    return None


def wizard():
    print("=" * 64)
    print(" sd-photo-rescue — read-only photo/video recovery")
    print("=" * 64)
    print("This tool only READS the card. It never writes to it.")
    if not is_root():
        print("\nNOTE: reading a raw device needs admin rights. If disks don't show")
        print("up or you get a permission error, re-run with:  sudo python3 recover.py")

    disk = choose_disk_interactive()
    if not disk:
        return 1

    print("\nWhat do you want to recover?")
    print("  [1] Photos only (JPEG)")
    print("  [2] Photos + RAW (CR2/CR3/NEF/ARW/RAF/ORF/RW2/DNG/HEIC)")
    print("  [3] Photos + RAW + Video (MP4/MOV)   [default]")
    t = ask("choose [1/2/3]: ", "3")
    families = {"1": ["jpeg"],
                "2": ["jpeg", "raf", "tiff", "orf", "rw2", "iso"],
                "3": ["jpeg", "raf", "tiff", "orf", "rw2", "iso"]}.get(t,
                ["jpeg", "raf", "tiff", "orf", "rw2", "iso"])
    # (RAW and Video both rely on the iso family for CR3/HEIC vs MP4/MOV)

    print("\nOnly recover photos from a certain date range? (uses the photo's EXIF date)")
    print("  Don't know the date? Just press Enter twice to recover EVERYTHING on the card.")
    dfrom = parse_date(ask("  from date (YYYY-MM-DD, Enter = all): "))
    dto = parse_date(ask("  to   date (YYYY-MM-DD, Enter = all): "))

    print("\nKnow your camera's megapixels? (optional) Helps separate full-size photos")
    print("  from small thumbnails/previews. e.g. 26 for a 26MP camera. Enter to skip.")
    mp_s = ask("  megapixels (Enter = skip): ")
    try:
        megapixels = float(mp_s) if mp_s else 0
    except ValueError:
        megapixels = 0

    default_out = os.path.join(os.path.expanduser("~"), "recovered")
    out = os.path.expanduser(ask(f"\nSave recovered files to [{default_out}]: ", default_out))

    print("\n" + "-" * 64)
    print(f" Card        : {disk['node']}  ({human(disk['size'])})  {disk['name']}")
    print(f" Recover     : option {t} -> {','.join(sorted(set(families)))}")
    print(f" Date range  : {dfrom or 'all'} .. {dto or 'all'}")
    print(f" Megapixels  : {megapixels or 'not set'}")
    print(f" Output      : {out}")
    print("-" * 64)
    print("The card will be unmounted (not ejected) so the OS can't write to it,")
    print("then read end-to-end. Nothing is written to the card.")
    if ask("Start recovery? [y/N]: ").lower() != "y":
        print("Cancelled.")
        return 1

    print("\nUnmounting the card...")
    unmount_disk(disk)
    src = disk["raw"] if sys.platform == "darwin" else disk["node"]
    return run_recovery(src, out, families, dfrom, dto, megapixels)


# --------------------------------------------------------------------------- #
#  Recovery driver + reporting
# --------------------------------------------------------------------------- #
def run_recovery(src, out, families, dfrom, dto, megapixels=0):
    import errno
    import shutil
    try:
        r = Reader(src)
    except PermissionError:
        print(f"\n[error] Permission denied opening {src}. Re-run with sudo:")
        print("        sudo python3 recover.py ...")
        return 1
    except FileNotFoundError:
        print(f"\n[error] Not found: {src}")
        return 1
    except OSError as e:
        if e.errno == errno.EBUSY:
            print(f"\n[error] {src} is in use by another program.")
            print("Close Photos / Image Capture / Finder windows for the card, then retry.")
            print("(You may eject it in Finder first — eject is fine; do NOT erase/format.)")
        else:
            print(f"\n[error] Could not open {src}: {e}")
        return 1
    if not r.size or r.size < 1024 * 1024:
        print(f"\n[error] Could not read the size of {src} (size={r.size}).")
        print("Try: unplug/re-plug the card, run 'python3 recover.py --list' to confirm it")
        print("appears, then re-run with sudo.")
        r.close()
        return 1

    try:                       # output free-space warning (carved data can be many GB)
        os.makedirs(out, exist_ok=True)
        free = shutil.disk_usage(out).free
        if free < r.size:
            print(f"\n[!] The card is {human(r.size)}; recovered files can be large, but the")
            print(f"    output folder has only {human(free)} free. If it fills up, recovery")
            print(f"    stops (files so far are kept). Consider a different --out folder.")
    except Exception:
        pass

    r.progress = True
    print(f"\nReading: {src}  ({human(r.size)})  [READ-ONLY — the card is never written]\n")
    try:
        stats = carve(r, r.size, out, sorted(set(families)), dfrom, dto,
                      megapixels=megapixels, progress=True)
    finally:
        r.close()

    print("\n" + "=" * 64)
    print(f" Done. Recovered {stats['saved']} complete files ({human(stats['bytes'])})")
    if dfrom or dto:
        print(f"   - skipped (outside date range)        : {stats['skipped_date']}")
        if stats["unknown_date"]:
            print(f"   - date unreadable (_unknown_date/)    : {stats['unknown_date']}")
    if megapixels and stats["other_size"]:
        print(f"   - different resolution (_other_size/) : {stats['other_size']}")
    if stats["partial"]:
        print(f"   - damaged/incomplete (_partial/)      : {stats['partial']}  (may not open)")
    print(f" -> {out}")
    print("=" * 64)
    print("Tip: files named YYYYMMDD_HHMMSS_* carry a recovered EXIF capture time.")
    if not is_root() and stats["saved"] == 0:
        print("Recovered nothing? If you didn't use sudo, re-run: sudo python3 recover.py")
    return 0


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Recover photos/videos from a formatted SD card (read-only).")
    ap.add_argument("--disk", help="device node, e.g. /dev/disk4 (macOS) or /dev/sdb (Linux)")
    ap.add_argument("--image", help="work on an image file instead of a device")
    ap.add_argument("--out", help="output folder (default: ~/recovered)")
    ap.add_argument("--types", default="jpeg,raw,video",
                    help="comma list of jpeg,raw,video (default: all)")
    ap.add_argument("--date-from", help="keep files on/after this date (YYYY-MM-DD)")
    ap.add_argument("--date-to", help="keep files on/before this date (YYYY-MM-DD)")
    ap.add_argument("--date", help="shortcut for a single day (sets from=to)")
    ap.add_argument("--megapixels", type=float, default=0,
                    help="camera megapixels (e.g. 26): sorts full-size photos from thumbnails")
    ap.add_argument("--list", action="store_true", help="list disks and exit")
    ap.add_argument("--allow-internal", action="store_true",
                    help="allow selecting an internal/system disk with --disk")
    ap.add_argument("--yes", action="store_true", help="skip confirmation prompts")
    args = ap.parse_args(argv)
    try:
        return _dispatch(args)
    except (KeyboardInterrupt, EOFError):
        print("\n\nStopped. Nothing was written to the card. Files recovered so far are kept")
        print("in the output folder. On macOS the card was unmounted — re-insert it to use it.")
        return 1


def _dispatch(args):
    if IS_WINDOWS:
        print("Windows isn't supported yet (macOS and Linux only). You can still use")
        print("--image on Windows if you already have a raw image of the card.")

    if args.list:
        for d in list_disks():
            tag = "internal" if d["internal"] else "external"
            print(f"{d['node']:<16} {human(d['size']):>9}  {tag:<8} {d['name']} ({d['proto']})")
        return 0

    if not args.disk and not args.image:        # interactive wizard
        return wizard()

    families = []
    for t in args.types.split(","):
        families += TYPE_GROUPS.get(t.strip(), [])
    families = sorted(set(families)) or ["jpeg"]
    dfrom = parse_date(args.date_from or args.date or "")
    dto = parse_date(args.date_to or args.date or "")
    out = os.path.expanduser(args.out or os.path.join("~", "recovered"))

    if args.image:
        src = os.path.expanduser(args.image)
        if not os.path.isfile(src):
            print(f"[error] image not found: {src}")
            return 1
        return run_recovery(src, out, families, dfrom, dto, args.megapixels)

    # device
    src = args.disk
    ident = os.path.basename(src).replace("rdisk", "disk")
    info = next((d for d in list_disks()
                 if d.get("id") == ident or d.get("node") == "/dev/" + ident), None)
    if info and info["internal"] and not args.allow_internal:
        print(f"[refused] {src} looks like an INTERNAL/SYSTEM disk. If you are SURE, re-run")
        print("with --allow-internal. (Access is read-only, but this is a safety guard.)")
        return 1
    if sys.platform == "darwin" and "/rdisk" not in src:
        src = src.replace("/dev/disk", "/dev/rdisk")    # prefer raw device on macOS
    if not args.yes:
        print(f"About to READ {src} (read-only) and write results to {out}.")
        if input("Continue? [y/N]: ").strip().lower() != "y":
            return 1
    if sys.platform == "darwin":
        subprocess.run(["diskutil", "unmountDisk", "/dev/" + ident], check=False)
    elif info:
        unmount_disk(info)
    return run_recovery(src, out, families, dfrom, dto, args.megapixels)


if __name__ == "__main__":
    sys.exit(main())
