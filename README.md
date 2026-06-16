# sd-photo-rescue

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
    --date-from 2026-06-12 \
    --date-to   2026-06-12       # or --date 2026-06-12 for a single day

python3 recover.py --list                       # just list disks
python3 recover.py --image card.img --out ~/out # work on a raw image file instead
```

Working from an image file (`--image`) does **not** need sudo. If you prefer, make a read-only image first with `ddrescue` and recover from that.

---

## How it works (short version)

1. Reads the device in one pass and finds the start of every file by its **signature** (e.g. JPEG starts with `FF D8 FF`).
2. Finds each file's true **end** correctly:
   - JPEG: walks the marker segments (so an embedded thumbnail isn't mistaken for the end)
   - HEIC/CR3/MP4/MOV: walks the ISO-BMFF box structure
   - RAF: reads the size from its header
3. Optionally reads the **EXIF capture date** and keeps only your date range.
4. Writes each recovered file to the output folder. The card is only ever read.

See `recover.py` — it's commented and uses only the standard library.

---

## Troubleshooting

- **No disks listed / permission error** → run with `sudo`.
- **Very few or no files recovered** → the card may have been *fully* erased (secure-erase/low-level format) or already overwritten by new photos. Quick formats are recoverable; full erases usually are not.
- **Original file names (e.g. `DSCF1234.JPG`) aren't restored** → expected. Formatting wipes the name table, so files are named by capture time instead.
- **It's slow** → it reads the whole card at least once; a 128 GB card can take 15–40 minutes. Progress is printed as it goes.
- **Linux**: needs `lsblk` (util-linux, present by default) and `sudo`.

---

## Safety

This tool opens the card with `O_RDONLY` and only ever reads from it. It never writes, formats, or modifies the card. Recovered files are written to a **separate** output folder. Before reading, it unmounts the card so the operating system can't write to it either.

---

## 한국어 안내

카메라/컴퓨터에서 **실수로 포맷한 SD카드**의 사진·영상을 터미널에서 복구하는 도구입니다. 파이썬 파일 하나, 설치 불필요, **읽기 전용이라 안전**합니다.

> 포맷은 보통 "목차(파일 테이블)"만 지울 뿐, 사진 데이터는 덮어쓰기 전까지 카드에 남아 있습니다. 이 도구는 카드에 **쓰지 않고 읽기만** 하면서 내용으로 파일을 복원합니다(파일 카빙).

**제일 먼저:** 그 카드 사용을 즉시 멈추세요. 추가 촬영·재포맷 금지(덮어쓰면 복구 불가).

**사용법 (macOS / Linux):**
```bash
curl -fsSLO https://raw.githubusercontent.com/psm9619/sd-photo-rescue/main/recover.py
sudo python3 recover.py
```
→ 디스크 목록이 뜨면 **카드 번호만 입력** → 복구할 종류/날짜/저장폴더를 고르면 끝.

- JPEG + RAW(CR2/CR3/NEF/ARW/RAF/ORF/RW2/DNG/HEIC) + 영상(MP4/MOV) 복구
- EXIF 촬영일로 **기간 필터** 가능 (`--date-from`/`--date-to`)
- 카드에 **절대 쓰지 않음**(읽기 전용). 결과는 별도 폴더(`~/recovered`)에 저장
- 결과 파일명은 촬영시각(`20260612_143022_*.jpg`)이라 시간순 정렬됨
- 원본 파일명(DSCF####)은 포맷이 지워서 복원되지 않습니다(촬영시각 이름으로 저장)

복구가 거의 안 되면 빠른 포맷이 아니라 **완전 포맷/보안 삭제**였을 수 있습니다(이 경우 복구 어려움).

---

## License

MIT — see [LICENSE](LICENSE).
