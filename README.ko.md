# sd-photo-rescue

![license](https://img.shields.io/badge/license-MIT-blue) ![python](https://img.shields.io/badge/python-3-blue) ![platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-lightgrey) ![card](https://img.shields.io/badge/card-read--only-brightgreen)

[English](README.md) · **한국어** · [日本語](README.ja.md)

**SD카드를 실수로 포맷하셨나요? 사진은 아직 거의 그대로 남아 있을 가능성이 높습니다.**

sd-photo-rescue는 카드를 훑어서 사진·영상을 되살려 주는 무료 도구입니다. **읽기 전용**이라 카드를 건드리지 않고, 터미널에서 명령어 한 줄로 동작합니다. 설치할 것도, 결제할 것도 없습니다.

> 카메라나 컴퓨터가 카드를 "포맷"할 때는 보통 목록(색인)만 지울 뿐, 사진 데이터 자체는 지우지 않습니다. 새 파일이 덮어쓰기 전까지 사진은 카드에 그대로 남아 있습니다. 이 도구는 카드에 **전혀 쓰지 않고 읽기만** 하면서, 내용을 보고 파일을 복원합니다.

---

## ⚠️ 가장 먼저 하실 일

**지금 그 카드 사용을 멈추세요.** 사진을 더 찍지 말고, 어떤 앱도 카드에 쓰지 못하게 하고, 다시 포맷하지 마세요. 한 번의 쓰기만으로도 되살릴 수 있던 사진이 사라질 수 있습니다. 카드를 빼서 카드 리더기로 작업하세요.

---

## 사진 되찾기 — 3단계

**macOS** 또는 **Linux**에서:

**1. 도구 받기** (파일 하나, 설치 불필요):
```bash
curl -fsSLO https://raw.githubusercontent.com/psm9619/sd-photo-rescue/main/recover.py
```

**2. 실행하기** (카드를 읽으려면 `sudo` 필요):
```bash
sudo python3 recover.py
```

**3. 질문에 답하기** — 목록에서 내 카드를 고르고, 무엇을 복구할지(원하면 날짜 범위나 카메라 화소도) 선택한 뒤 저장 위치를 정하면 됩니다.

끝입니다. 복구된 파일은 `~/recovered`에 저장되며, `20260612_143022.jpg`처럼 촬영 시각으로 이름이 붙어 순서대로 정렬됩니다.

### 실행 화면 예시

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

## 복구 가능한 형식

**사진** — JPEG, HEIC  ·  **RAW** — Canon, Nikon, Sony, Fujifilm, Olympus, Panasonic, Pentax, Samsung, Leica/Adobe(DNG)  ·  **영상** — MP4, MOV

---

## 자주 묻는 질문

**제 카드에 안전한가요?**
네. 카드는 **읽기 전용**으로만 열립니다. 쓰거나 포맷하거나 바꾸지 않습니다. 복구한 파일은 별도 폴더에 저장됩니다.

**파일 이름이 원래(`DSCF1234.JPG`)와 다른데요?**
포맷이 이름표를 지워서 원래 이름은 되살릴 수 없습니다. 대신 촬영 시각으로 이름을 붙여, 찍은 순서대로 정렬되게 했습니다.

**시간이 얼마나 걸리나요?**
카드를 한 번 통째로 읽습니다. 128GB 기준 대략 20~60분(느린 리더기나 영상이 많으면 더 오래). 진행 표시가 계속 갱신되는 동안은 멈춘 게 아니라 작업 중입니다.

**거의/전혀 복구되지 않았어요.**
먼저 `sudo`로 실행했는지 확인하세요. 그래도 비어 있다면, 빠른 포맷이 아니라 **완전 삭제**(보안/저수준 포맷)였거나 이미 새 파일로 덮어써졌을 수 있습니다. 이런 경우는 보통 복구가 어렵습니다.

**일부 파일이 안 열려요.**
카드 곳곳에 조각나 저장된 파일(큰 영상, 오래 쓴 카드)은 일부만 복원될 수 있고, `_partial/` 폴더에 따로 담깁니다. 이 방식(카빙)의 자연스러운 한계입니다.

---

## 명령행 옵션

지정하지 않은 항목은 대화형으로 물어보므로, 그냥 `sudo python3 recover.py`만 실행해도 됩니다.

```bash
sudo python3 recover.py \
    --disk /dev/disk4 \          # macOS; Linux는 예: /dev/sdb
    --out ~/recovered \
    --types jpeg,raw,video \     # jpeg, raw, video 중 선택
    --date-from 2026-06-12 \     # --date-* 둘 다 생략하면 전체 날짜 복구
    --date-to   2026-06-12 \     # 또는 하루만: --date 2026-06-12
    --megapixels 26              # (선택) 카메라 화소 — 풀사이즈와 썸네일 분리

python3 recover.py --list                        # 디스크 목록만 표시
python3 recover.py --image card.img --out ~/out  # 디바이스 대신 이미지 파일에서 복구
```

이미지 파일(`--image`)로 작업하면 `sudo`가 필요 없습니다. 먼저 `ddrescue`로 읽기 전용 이미지를 떠서 거기서 복구해도 됩니다.

### 결과 폴더 구성

- **메인 폴더** — 복구된 파일 (날짜를 읽을 수 있으면 촬영 시각 이름)
- `_unknown_date/` — 날짜를 못 읽은 파일 (날짜 필터를 켰을 때만)
- `_other_size/` — `--megapixels`와 안 맞는 파일 (대개 썸네일/미리보기)
- `_partial/` — 손상되거나 불완전한 파일(`.partial`) — 안 열릴 수 있음

### 카메라 RAW 지원

정확한 확장자로 인식: **Canon** CR2/CR3, **Nikon** NEF, **Sony** ARW, **Fujifilm** RAF, **Olympus/OM** ORF, **Panasonic** RW2, **Adobe/Leica** DNG, **Pentax** PEF, **Samsung** SRW, **HEIC**.

대부분의 RAW는 내부적으로 TIFF 기반이라, 이 목록에 없는 브랜드도 보통은 복구됩니다 — 다만 `.tif`로 저장되니 이름만 바꾸면 됩니다. 일부 비(非)TIFF 형식(예: Sigma X3F, Phase One IIQ)은 아직 지원하지 않습니다 — 필요하면 이슈로 알려주세요.

---

## 동작 원리

1. 카드를 한 번 읽으며 각 파일의 시작을 **시그니처**로 찾습니다 (예: JPEG는 `FF D8 FF`로 시작).
2. 각 파일의 진짜 **끝**을 정확히 찾습니다:
   - **JPEG** — 마커 구조를 따라가 내장 썸네일을 끝으로 착각하지 않음
   - **HEIC/CR3/MP4/MOV** — ISO-BMFF 박스 구조를 따라감
   - **TIFF 기반 RAW** — IFD 체인을 분석해 실제 크기를 계산(내장 미리보기에서 잘리지 않음)
   - **RAF** — 헤더에서 크기를 읽음
3. (선택) **EXIF 촬영일**을 읽어 지정한 기간만 남깁니다.
4. 복구한 파일을 저장 폴더에 씁니다. 카드는 오직 읽기만 합니다.

주석이 달린 단일 파일이며 Python 표준 라이브러리만 사용합니다 — `recover.py`.

---

## 기여 & 피드백

**이슈, 아이디어, PR 모두 진심으로 환영합니다 — 부담 갖지 마세요.**

- 내 카드에서 **안 됐거나** 너무 적게 복구됐나요? 그런 제보가 가장 큰 도움이 됩니다 — [이슈를 남겨주세요](https://github.com/psm9619/sd-photo-rescue/issues). 카메라/카드 종류와 상황을 알려주시면 됩니다.
- 아직 지원 안 되는 **RAW 포맷·카메라**(Sigma X3F, Phase One IIQ 등)가 필요하세요? 요청 주세요 — 시그니처 추가는 어렵지 않습니다.
- 버그를 발견했거나 개선 아이디어가 있으면 PR 대환영입니다. 크든 작든 좋아요.

읽기 쉬운 단일 파일이라 수정·검토가 쉽습니다. PR 전에 테스트를 한 번 돌려주세요:

```bash
python3 tests/test_recover.py
```

사소한 질문이라도 괜찮습니다 — 사진을 되찾는 데 도움이 안 됐다면, 그 얘기를 꼭 듣고 싶습니다.

---

## 후원

이 도구는 무료이고 앞으로도 그렇습니다. 사진을 되찾는 데 도움이 됐고 고마움을 표하고 싶으시다면 커피 한 잔 사주셔도 좋아요 — 전혀 부담 갖지 마세요. ☕

<a href="https://buymeacoffee.com/soominp0619" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="44"></a>

도움이 되셨다면 저장소에 ⭐(Star)를 눌러주시면 다른 분들이 찾는 데도 도움이 됩니다.

---

## 안전성 & 라이선스

카드는 `O_RDONLY`(읽기 전용)로 열려 읽기만 합니다 — 쓰기·포맷·수정을 하지 않습니다. macOS에서는 먼저 카드를 마운트 해제해 OS가 건드리지 못하게 하고, Linux에서는 마운트 해제를 시도한 뒤 실패하면 알려줍니다.

**MIT 라이선스**로 배포됩니다 — [LICENSE](LICENSE) 참고.
