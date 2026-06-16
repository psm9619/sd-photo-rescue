# sd-photo-rescue

**English** · [한국어](README.ko.md) · [日本語](README.ja.md)

Recover photos and videos from an SD card that was **formatted by mistake** (or won't mount), straight from your terminal. One Python file, no installation, **read-only and safe**.

> Formatting a card usually erases only the file table — your photos are still physically there until something overwrites them. This tool reads the card **without writing to it** and rebuilds the files by their content ("file carving").

- ✅ Recovers **JPEG**, **RAW** (Canon CR2/CR3, Nikon NEF, Sony ARW, Fujifilm RAF, Olympus ORF, Panasonic RW2, Adobe DNG, HEIC) and **video** (MP4/MOV)
- ✅ Can keep only the photos shot in a **date range** (from EXIF)
- ✅ **Never writes to your card** — opens it read-only
- ✅ Interactive: it finds your disks, you just pick a number
- ✅ Pure Python 3 standard library — nothing to install
- 💻 macOS and Linux (Windows: use `--image` on a raw image for now)

---

## ⚠️ First, before anything else

**Stop using the card immediately.** Do not take more photos, do not let the camera or any app write to it, do not re-format it. Every write can permanently overwrite recoverable photos. Take the card out and use a reader.

---

## Quick start

### macOS / Linux

1. Download the one file `recover.py` (or `git clone` this repo).
   ```bash
   curl -fsSLO https://raw.githubusercontent.com/psm9619/sd-photo-rescue/main/recover.py
   ```
2. Plug in the card and run (it needs `sudo` to read the raw device):
   ```bash
   sudo python3 recover.py
   ```
3. Answer the questions:
   - it lists your disks → **type the number** of your card
   - pick what to recover (photos / +RAW / +video)
   - optional date range
   - choose an output folder

That's it. Recovered files land in the output folder (default `~/recovered`), named by capture time like `20260612_143022_*.jpg` so they sort chronologically.

> **Make sure you pick the right disk.** The tool shows size and "internal/external" and warns on system disks. Your card is the small **external/removable** one (e.g. 64 GB / 128 GB).

---

## Options (for repeat runs / automation)

Anything you don't pass is asked interactively.

```bash
sudo python3 recover.py \
    --disk /dev/disk4 \          # macOS; on Linux e.g. /dev/sdb
    --out ~/recovered \
    --types jpeg,raw,video \     # any of: jpeg, raw, video
    --date-from 2026-06-12 \     # omit both --date-* to recover ALL dates
    --date-to   2026-06-12 \     # or --date 2026-06-12 for a single day
    --megapixels 26              # optional: your camera's MP (sorts full-size vs thumbnails)

python3 recover.py --list                       # just list disks
python3 recover.py --image card.img --out ~/out # work on a raw image file instead
```

Working from an image file (`--image`) does **not** need sudo. If you prefer, make a read-only image first with `ddrescue` and recover from that.

### Output folders

- main folder — your recovered files (named by capture time when readable)
- `_unknown_date/` — files whose date couldn't be read (only when a date filter is set)
- `_other_size/` — files that don't match `--megapixels` (likely thumbnails/previews)
- `_partial/` — damaged or incomplete carves (`.partial`); these may not open

### Camera RAW coverage

Fully recognised (correct extension): **Canon** CR2/CR3, **Nikon** NEF, **Sony** ARW, **Fujifilm** RAF, **Olympus/OM** ORF, **Panasonic** RW2, **Adobe/Leica** DNG, **Pentax** PEF, **Samsung** SRW, **HEIC**. Most RAW formats are TIFF-based, so even a brand not in this list is usually still recovered — just saved as `.tif`, which you can rename. A few non-TIFF formats (e.g. Sigma X3F, Phase One IIQ) aren't handled yet.

---

## How it works (short version)

1. Reads the device in one pass and finds the start of every file by its **signature** (e.g. JPEG starts with `FF D8 FF`).
2. Finds each file's true **end** correctly:
   - JPEG: walks the marker segments (so an embedded thumbnail isn't mistaken for the end)
   - HEIC/CR3/MP4/MOV: walks the ISO-BMFF box structure
   - TIFF-based RAW: parses the IFD chain for the real extent (so the embedded preview doesn't truncate it)
   - RAF: reads the size from its header
3. Optionally reads the **EXIF capture date** and keeps only your date range.
4. Writes each recovered file to the output folder. The card is only ever read.

See `recover.py` — it's commented and uses only the standard library.

---

## Troubleshooting

- **No disks listed / permission error** → run with `sudo`.
- **Very few or no files recovered** → the card may have been *fully* erased (secure-erase/low-level format) or already overwritten by new photos. Quick formats are recoverable; full erases usually are not.
- **Original file names (e.g. `DSCF1234.JPG`) aren't restored** → expected. Formatting wipes the name table, so files are named by capture time instead.
- **It's slow** → it reads the whole card once; a 128 GB card typically takes 20–60 minutes, longer on slow/USB-2 readers or with video. It is **not** stuck as long as the progress lines keep updating. Speed is limited by how fast the card/reader can be read — there's no way around reading the card once.
- **Some files won't open** → carving can't rebuild *fragmented* files (large videos / heavily-used cards). Those land in `_partial/` or may be slightly corrupt. This is a normal limit of carving.
- **Linux**: needs `lsblk` (util-linux, present by default) and `sudo`.

---

## Safety

This tool opens the card with `O_RDONLY` and only ever reads from it. It never writes, formats, or modifies the card. Recovered files are written to a **separate** output folder. Before reading, on macOS it unmounts the card so the OS can't write to it; on Linux it attempts to unmount and warns if it can't. Either way the card is opened strictly read-only.

---

## License

MIT — see [LICENSE](LICENSE).
