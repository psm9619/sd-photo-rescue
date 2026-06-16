# sd-photo-rescue

![license](https://img.shields.io/badge/license-MIT-blue) ![python](https://img.shields.io/badge/python-3-blue) ![platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-lightgrey) ![card](https://img.shields.io/badge/card-read--only-brightgreen)

[English](README.md) · [한국어](README.ko.md) · **日本語**

**SDカードをうっかりフォーマットしてしまった? 写真はまだ残っている可能性が高いです。**

sd-photo-rescue は、カードをスキャンして写真・動画を復元する無料ツールです。**読み取り専用**なのでカードには触れず、ターミナルでコマンド1つで動きます。インストールも購入も不要です。

> カメラやパソコンがカードを「フォーマット」しても、消えるのは多くの場合インデックス（目次）だけで、写真データ本体は消えません。新しいファイルに上書きされるまで、写真はカードに残っています。このツールはカードに**一切書き込まず読み取るだけ**で、中身からファイルを復元します。

---

## ⚠️ まず最初に

**今すぐカードの使用をやめてください。** これ以上撮影しない、どのアプリにも書き込ませない、再フォーマットしない。たった1回の書き込みでも、復元できたはずの写真が失われることがあります。カードを取り出し、カードリーダーで作業してください。

---

## 写真を取り戻す — 3ステップ

**macOS** または **Linux** で:

**1. ツールを入手**（ファイル1つ、インストール不要）:
```bash
curl -fsSLO https://raw.githubusercontent.com/psm9619/sd-photo-rescue/main/recover.py
```

**2. 実行する**（カードの読み取りに `sudo` が必要）:
```bash
sudo python3 recover.py
```

**3. いくつかの質問に答える** — 一覧から自分のカードを選び、復元する種類（必要なら日付範囲やカメラの画素数も）を選んで、保存先を指定するだけ。

これで完了です。復元したファイルは `~/recovered` に保存され、`20260612_143022.jpg` のように撮影時刻で名前が付くため、順番どおりに並びます。

### 実行イメージ

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

## 復元できる形式

**写真** — JPEG、HEIC  ·  **RAW** — Canon、Nikon、Sony、Fujifilm、Olympus、Panasonic、Pentax、Samsung、Leica/Adobe（DNG）  ·  **動画** — MP4、MOV

---

## よくある質問

**自分のカードに対して安全ですか?**
はい。カードは**読み取り専用**でのみ開きます。書き込み・フォーマット・変更は一切しません。復元したファイルは別のフォルダに保存されます。

**ファイル名が元（`DSCF1234.JPG`）と違うのですが?**
フォーマットで名前テーブルが消えるため、元の名前は復元できません。代わりに撮影時刻で名前を付け、撮影順に並ぶようにしています。

**どのくらい時間がかかりますか?**
カードを一度すべて読み取ります。128GB で約20〜60分（遅いリーダーや動画が多いとさらに長く）。進捗表示が更新され続けている間は、止まっているのではなく処理中です。

**ほとんど／まったく復元できませんでした。**
まず `sudo` を付けて実行したか確認してください。それでも空の場合、クイックフォーマットではなく**完全消去**（セキュア／低レベルフォーマット）だったか、すでに新しいファイルで上書きされた可能性があります。その場合は通常、復元は困難です。

**一部のファイルが開けません。**
カード上で断片化して保存されたファイル（大きな動画、長く使ったカード）は一部しか復元できず、`_partial/` フォルダに入ります。この方式（カービング）の通常の限界です。

---

## コマンドラインオプション

省略した項目は対話形式で尋ねるので、単に `sudo python3 recover.py` だけでも使えます。

```bash
sudo python3 recover.py \
    --disk /dev/disk4 \          # macOS; Linux は例 /dev/sdb
    --out ~/recovered \
    --types jpeg,raw,video \     # jpeg, raw, video のいずれか
    --date-from 2026-06-12 \     # --date-* を両方省略すると全日付を復元
    --date-to   2026-06-12 \     # または1日だけ: --date 2026-06-12
    --megapixels 26              # 任意: カメラの画素数 — フルサイズとサムネを仕分け

python3 recover.py --list                        # ディスク一覧だけ表示
python3 recover.py --image card.img --out ~/out  # デバイスの代わりにイメージファイルから復元
```

イメージファイル（`--image`）での作業に `sudo` は不要です。先に `ddrescue` で読み取り専用イメージを作り、そこから復元してもかまいません。

### 出力フォルダの構成

- **メインフォルダ** — 復元したファイル（日付が読めれば撮影時刻の名前）
- `_unknown_date/` — 日付を読めなかったファイル（日付フィルタ指定時のみ）
- `_other_size/` — `--megapixels` に合わないファイル（多くはサムネ／プレビュー）
- `_partial/` — 破損・不完全なファイル（`.partial`）— 開けないことがあります

### カメラRAW対応

正しい拡張子で認識: **Canon** CR2/CR3、**Nikon** NEF、**Sony** ARW、**Fujifilm** RAF、**Olympus/OM** ORF、**Panasonic** RW2、**Adobe/Leica** DNG、**Pentax** PEF、**Samsung** SRW、**HEIC**。

多くのRAWは内部的にTIFFベースのため、ここに載っていないメーカーでも通常は復元できます — ただし `.tif` として保存されるので、名前を変えてください。一部の非TIFF形式（例: Sigma X3F、Phase One IIQ）は未対応です — 必要なら Issue でお知らせください。

---

## 仕組み

1. カードを一度読み取り、各ファイルの先頭を**シグネチャ**で見つけます（例: JPEG は `FF D8 FF` で始まる）。
2. 各ファイルの本当の**終端**を正しく特定します:
   - **JPEG** — マーカー構造をたどり、埋め込みサムネイルを終端と誤認しない
   - **HEIC/CR3/MP4/MOV** — ISO-BMFF のボックス構造をたどる
   - **TIFFベースのRAW** — IFDチェーンを解析して実サイズを算出（埋め込みプレビューで切れない）
   - **RAF** — ヘッダからサイズを読む
3. （任意）**EXIFの撮影日**を読み、指定した期間だけ残します。
4. 復元したファイルを保存先に書き出します。カードは読み取るだけです。

コメント付きの単一ファイルで、Python標準ライブラリのみを使用しています — `recover.py`。

---

## コントリビュート & フィードバック

**Issue・アイデア・プルリクエスト、どれも心から歓迎します — 遠慮しないでください。**

- 自分のカードで**うまくいかなかった**、復元が少なすぎた? そういう報告が一番の助けになります — [Issue を立てて](https://github.com/psm9619/sd-photo-rescue/issues)、カメラ／カードの種類と状況を教えてください。
- まだ対応していない **RAW形式・カメラ**（Sigma X3F、Phase One IIQ など）が必要ですか? リクエストしてください — シグネチャの追加は簡単です。
- バグを見つけた、改善案がある場合も PR を歓迎します。大小は問いません。

読みやすい単一ファイルなので、変更もレビューも容易です。PR の前にテストを実行してください:

```bash
python3 tests/test_recover.py
```

どんな初歩的な質問でも構いません — 写真を取り戻す役に立たなかったなら、ぜひ聞かせてください。

---

## 支援

このツールは無料で、これからもずっと無料です。写真を取り戻すお役に立てて、感謝の気持ちを伝えたい方は、よければコーヒーを一杯おごってください — もちろん任意です。☕

<a href="https://buymeacoffee.com/soominp0619" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="44"></a>

役に立ったら、リポジトリに ⭐（Star）を付けていただけると、他の方が見つけやすくなります。

---

## 安全性とライセンス

カードは `O_RDONLY`（読み取り専用）で開き、読み取るだけです — 書き込み・フォーマット・変更は行いません。macOS ではカードを先にアンマウントしてOSが触れないようにし、Linux ではアンマウントを試み、できない場合は警告します。

**MIT ライセンス**で配布しています — [LICENSE](LICENSE) を参照。
