# sd-photo-rescue

![license](https://img.shields.io/badge/license-MIT-blue) ![python](https://img.shields.io/badge/python-3-blue) ![platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-lightgrey) ![card](https://img.shields.io/badge/card-read--only-brightgreen)

**English** · [한국어](README.ko.md) · [日本語](README.ja.md)

**Accidentally formatted your SD card? Your photos are very likely still there.**

sd-photo-rescue is a free, **read-only** tool that scans the card and rebuilds your photos and videos — from the terminal, in one command. No installation, nothing to buy.

> When a camera or computer "formats" a card, it usually just clears the index, not the actual photo data. Until new files overwrite them, your shots are still on the card. This tool reads the card **without ever writing to it** and recovers files by their content.

---

## ⚠️ Do this first

**Stop using the card now.** Don't shoot more photos, don't let any app write to it, and don't re-format it — every write can overwrite what's still recoverable. Eject it and use a card reader.

---

## Get your photos back — 3 steps

On **macOS** or **Linux**:

**1. Download the tool** (one file, nothing to install):
```bash
curl -fsSLO https://raw.githubusercontent.com/psm9619/sd-photo-rescue/main/recover.py
```

**2. Run it** (needs `sudo` to read the card):
```bash
sudo python3 recover.py
```

**3. Answer a few questions** — pick your card from the list, choose what to recover (and optionally a date range or your camera's megapixels), and where to save.

That's it. Recovered files land in `~/recovered`, named by capture time (e.g. `20260612_143022.jpg`) so they stay in order.

### What a run looks like

```text
Detected disks:

  [1] /dev/disk4      127.9GB  SD Card Reader (usb)
  [a] show ALL disks    [q] quit

Which disk is your card? enter the number: 1
Selected: /dev/disk4  127.9GB  SD Card Reader
Is this correct? [y/N]: y

Reading: /dev/rdisk4  (127.9GB)  [READ-ONLY — the card is never written]
      ... 8.1GB scanned, 642 candidates
================================================================
 Done. Recovered 730 complete files (7.8GB)
 -> /Users/you/recovered
================================================================
```

---

## What it can recover

**Photos** — JPEG, HEIC  ·  **RAW** — Canon, Nikon, Sony, Fujifilm, Olympus, Panasonic, Pentax, Samsung, Leica/Adobe (DNG)  ·  **Video** — MP4, MOV

---

## Common questions

**Is this safe for my card?**
Yes. The card is opened **read-only** — the tool never writes to, formats, or changes it. Recovered files go to a separate folder.

**Why are the file names different (not `DSCF1234.JPG`)?**
Formatting erases the name table, so original names can't be brought back. Files are named by their capture time instead, which keeps them in shooting order.

**How long does it take?**
It reads the whole card once — roughly 20–60 minutes for a 128 GB card (longer on slow readers or with video). As long as the progress keeps updating, it's working, not stuck.

**It recovered little or nothing.**
First, make sure you ran it with `sudo`. If it's still empty, the card may have been **fully** erased (a secure/low-level format) or already overwritten by new files — those usually can't be recovered.

**Some files won't open.**
Files split into pieces across the card (large videos, heavily-used cards) can only be partially rebuilt; they're placed in a `_partial/` folder. This is a normal limit of this kind of recovery.

---

## Command-line options

Anything you leave out is asked interactively, so you can also just run `sudo python3 recover.py`.

```bash
sudo python3 recover.py \
    --disk /dev/disk4 \          # macOS; on Linux e.g. /dev/sdb
    --out ~/recovered \
    --types jpeg,raw,video \     # any of: jpeg, raw, video
    --date-from 2026-06-12 \     # omit both --date-* to recover ALL dates
    --date-to   2026-06-12 \     # or --date 2026-06-12 for a single day
    --megapixels 26              # optional: camera MP — sorts full-size from thumbnails

python3 recover.py --list                        # just list disks
python3 recover.py --image card.img --out ~/out  # work on a raw image file instead
```

Working from an image file (`--image`) doesn't need `sudo`. You can also make a read-only image first with `ddrescue` and recover from that.

### Output folders

- **main folder** — your recovered files (named by capture time when readable)
- `_unknown_date/` — files whose date couldn't be read (only when a date filter is set)
- `_other_size/` — files that don't match `--megapixels` (likely thumbnails/previews)
- `_partial/` — damaged or incomplete files (`.partial`); these may not open

### Camera RAW coverage

Recognised with the correct extension: **Canon** CR2/CR3, **Nikon** NEF, **Sony** ARW, **Fujifilm** RAF, **Olympus/OM** ORF, **Panasonic** RW2, **Adobe/Leica** DNG, **Pentax** PEF, **Samsung** SRW, **HEIC**.

Most RAW formats are TIFF-based, so even a brand not listed here is usually still recovered — just saved as `.tif`, which you can rename. A few non-TIFF formats (e.g. Sigma X3F, Phase One IIQ) aren't handled yet — please open an issue if you need one.

---

## How it works

1. Reads the card once and finds the start of every file by its **signature** (e.g. JPEG starts with `FF D8 FF`).
2. Finds each file's true **end** correctly:
   - **JPEG** — walks the marker segments, so an embedded thumbnail isn't mistaken for the end
   - **HEIC/CR3/MP4/MOV** — walks the ISO-BMFF box structure
   - **TIFF-based RAW** — parses the IFD chain for the real size, so the embedded preview doesn't truncate it
   - **RAF** — reads the size from its header
3. Optionally reads the **EXIF capture date** and keeps only your date range.
4. Writes each recovered file to the output folder. The card is only ever read.

It's a single, commented file using only the Python standard library — `recover.py`.

---

## Contributing & feedback

**Issues, ideas, and pull requests are all genuinely welcome — please don't hold back.**

- Did it **not** work on your card, or recover too little? That's exactly the kind of report that helps — [open an issue](https://github.com/psm9619/sd-photo-rescue/issues) and tell me the camera/card and what happened.
- Want a **RAW format or camera** that isn't supported yet (Sigma X3F, Phase One IIQ, …)? Ask for it — adding signatures is straightforward.
- Spotted a bug or have an improvement? PRs are very welcome, big or small.

It's a single, readable file, so changes are easy to make and review. Please run the tests before sending a PR:

```bash
python3 tests/test_recover.py
```

No question is too basic — if it didn't help you get your photos back, I want to know.

---

## Safety & license

The card is opened with `O_RDONLY` and only ever read — never written, formatted, or modified. On macOS the card is unmounted first so the OS can't touch it; on Linux the tool unmounts it and warns if it can't.

Released under the **MIT License** — see [LICENSE](LICENSE).
