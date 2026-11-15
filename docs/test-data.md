# テストデータ整備方針

KemoMichi のテストで使う画像・動画・Timelapse2 ファイル（.tdb/.ddb）を、3 つの層に分けて整備します。
利用者から提供される実データ（.tdb/.ddb）をリポジトリに入れないという既存方針（`.gitignore` の
`*.tdb`/`*.ddb` 禁止、`!tests/fixtures/**/*.tdb`・`!tests/fixtures/**/*.ddb` のみ例外）はそのままです。

## 結論

- **層 0（合成データ）**：リポジトリにコミットし、CI では層 0 のみを常に実行します。実在のデータは
  含みません。
- **層 1（公開実画像）**：CDLA-Permissive のデータセットを必要時にのみ取得します。画像自体はコミットせず、
  PR の CI ではスキップし、別のジョブで実行します。
- **層 2（手元専用）**：利用者提供データや、再配布不可（非商用限定・未取得など）のデータを使います。
  コミットせず、環境変数が無ければスキップします。

以下、現状のコードで既にある部分と、これから追加する部分を分けて書きます。実装順は
[進める順番](#進める順番) の通りです。

## 層 0：合成データ（リポジトリ管理・CI 常時実行）

`src/kemocore/demo.py` の `create_demo_project`（`tests/conftest.py` の `demo` フィクスチャが使う）を
拡張します。現状、`make_demo_media` は 2 台のカメラ分の連番画像、EXIF なし画像 1 枚、動画 2 本を
作ります。動画 2 本はいずれも `ffmpeg` を呼び出して作るため、`ffmpeg` が無い環境では作られません
（該当テストは `tests/conftest.py` の `needs_ffmpeg` でスキップします）。追加するケースは次の通りです。

| 分類 | 内容 | 状態 |
|---|---|---|
| EXIF 境界 | `DateTimeOriginal` なし | 既存（`NOEXIF_0001.JPG`） |
| EXIF 境界 | EXIF が壊れている（不正なバイト列など） | 追加予定 |
| EXIF 境界 | 年またぎ（例：12/31 23:59 → 1/1 0:00） | 追加予定 |
| EXIF 境界 | 同一秒に複数枚が連続する | 追加予定 |
| 連写の区切り | 連写判定の閾値ちょうど・前後の秒差 | 追加予定（現状は `minutes=37 * i` に 0〜2 秒を加えるだけの間隔で、連写判定の閾値付近は作っていません） |
| 画質 | IR モノクロ画像 | 追加予定（現状の夜間画像はグレー一色 `(50,50,50)` の塗り分けで、実際の IR 画質は再現していません） |
| 画質 | 色かぶり（例：赤被り・緑被り） | 追加予定 |
| 壊れたファイル | 0 バイト | 追加予定 |
| 壊れたファイル | ヘッダのみで本体が無い | 追加予定 |
| 壊れたファイル | 拡張子と内容が不一致（例：`.jpg` だが中身は PNG） | 追加予定 |
| パス | 日本語を含むパス | 追加予定 |
| パス | 空白を含むパス | 追加予定 |
| パス | 長いファイル名・パス | 追加予定 |
| パス | Windows 予約名（`CON`、`NUL`、`COM1` など） | 追加予定 |
| REST 用動画 | フレーム番号を焼き込んだ既知 fps の動画 | 追加予定（現状の `make_video` は `testsrc2` を使い、フレーム番号を焼き込んでいるかは未確認。`rate="30000/1001"`、3 秒間のみで、REST 計測の対象フレーム数には対応していません） |

REST 用動画は、整数 fps（例：30fps）が既知で、ffmpeg でフレーム番号を焼き込み、ある範囲
（例：42〜171 フレーム目）を滞在イベントの対象とする想定です。この動画を使うテストでは、
期待値（滞在時間）を「フレーム数 ÷ fps」として**テストコードに数値で直書き**し、
KemoMichi 側の計算コードから値を再取得しないようにします（独立検算とするため）。
具体的な対象フレーム数・区間の秒数はテスト実装時に確定するため、本書では計算しません。

## 層 1：公開実画像（必要時取得・PR の CI ではスキップ、週次ジョブで実行）

**ライセンスが CDLA-Permissive のデータセットのみ**を使います。CI のスケジュール実行（`schedule:`
トリガー）は現時点の `.github/workflows/ci.yml` には無く、これから追加する予定です。

| データセット | 使う分量 | 内容 | ライセンス |
|---|---|---|---|
| ENA24-detection | 約 20 枚 | 種ラベル・bbox 付き | CDLA-Permissive |
| CCT20 | 約 20 枚 | 空撮影を含む | CDLA-Permissive |
| Desert Lion Conservation | 動画 2〜3 本・静止画 | カメラトラップ映像 | CDLA-Permissive |

取得方法として、`tests/fixtures/realdata/manifest.json`（これから作成）に URL・SHA-256・ライセンス・
出典を記録し、画像・動画自体はコミットせず取得する想定です。取得先は `KEMOMICHI_CACHE` ではなく、
新しい環境変数 `KEMOMICHI_TESTDATA_DIR`（予定）で指定し、未設定時はユーザーのキャッシュ配下の固定
フォルダ（例：`~/.cache/kemomichi/testdata`、Windows は `%LOCALAPPDATA%\KemoMichi\testdata`）を
使います。`tests/conftest.py` の autouse フィクスチャ `_isolated_cache` が `KEMOMICHI_CACHE` をテストごとの
一時ディレクトリに差し替えるため、その配下だと毎回再ダウンロードになってしまうためです。SHA-256 が
一致しない場合は取得失敗として扱います。取得・検証を行うスクリプト `tools/fetch_testdata.py` と、
`pytest` 側の `@pytest.mark.realdata` マーカー・`--realdata` オプションは、いずれもこれから作る予定で、
現時点ではまだ存在しません。

この層で確認したい内容：

- カメラ機種ごとの EXIF の違い。
- 実解像度での表示・キャッシュ性能。
- MegaDetector の検出結果 JSON の読み込み。

**未確認点**：

- ENA24-detection（画像 zip 3.6 GB）・CCT20（6 GB）は、LILA BC 上でのサイズは確認済みですが、
  1 枚ずつ個別に約 20 枚を取得できるかどうかは未確認です。
- Desert Lion Conservation は画像ごとの HTTP URL がページ上にありますが、動画の形式や取得方法（URL の
  組み立て方など）はページに記載がなく未確認です。
- EXIF の撮影日時がこれらのデータセットの配布形式で保持されているかは、LILA BC の各データセットページに
  記載が無く未確認です。取得スクリプト（`tools/fetch_testdata.py`、予定）でダウンロード後に確認し、
  EXIF 日時が残っていない画像は manifest に入れない方針とします。

## 層 2：手元専用（コミットしない）

| データ | 内容 | ライセンス／状態 |
|---|---|---|
| 利用者提供の .tdb/.ddb | Timelapse2 との互換確認 | 利用者提供データのため非公開 |
| SatoyamaCT | 日本の種の見た目・IR 色味の確認 | CC BY-NC 4.0（非商用限定） |
| Snapshot Japan 2023 の画像 | 現時点では取得不可。取得できた場合に追加予定 | 未確認（下記参照） |

`KEMOMICHI_LOCAL_DATA`（これから用意する環境変数、予定）が未設定の場合、この層のテストはスキップします。
テスト結果には画像そのものやファイルパスを出力せず、件数と合否のみを出す方針とします。

## Timelapse2 基準データ

KemoMichi 自身が書き出した `.ddb` を期待値にはしません。本物の Timelapse2（Windows 専用）で
作成・保存した小さな `.tdb`/`.ddb` を `tests/fixtures/` 配下に置き、これを基準データとします。
中の画像は層 0 の合成画像を使い、利用者から提供された実データは含めません。

テストでは、この基準データを KemoMichi で「開く → 編集 → 保存 → 再度開く」という往復を行い、
Timelapse2 が保存した形式のまま壊れていないかを確認します。Timelapse2 自体が Windows 専用のため、
この基準データの作成・更新作業は Windows 環境で行う必要があります。

## 例外：Snapshot Japan 2023 の Camtrap DP メタデータ

Snapshot Japan 2023 の GBIF 登録データ（出現記録、CC BY 4.0）は、画像付きレコードが 0 件であることを
確認済みです。一方、Camtrap DP パッケージ（v7）の `media.csv` には 150,624 件の画像メタデータの記載が
あり（画像本体は Wildlife Insights 側の GCS バケットにあり、`exifData` 欄は全件空、`storage.googleapis.com`
への直接アクセスは 403、バケット一覧は 401 で取得できないことを確認済みです）、これはメタデータのみの
例外としてコミットしてよい候補と考えます。CC BY 4.0 かつメタデータのみ（画像本体を含まない）という条件で、
数地点分のサブセットを出典明記の上でコミットし、将来の Camtrap DP 入出力（KemoMichi がこの形式を
読み書きする場合の基準データ）に使う想定です。Wildlife Insights 経由で画像本体を取得する手続きは
未確認です。

## 進める順番

1. 層 0 の拡張（EXIF 境界・連写境界・画質・壊れたファイル・パスの境界・REST 用動画）
2. Timelapse2 基準データの作成（Windows 環境で Timelapse2 を使用）
3. 層 1 の manifest（`tests/fixtures/realdata/manifest.json`、予定）と取得スクリプト
   （`tools/fetch_testdata.py`、予定）
4. 層 2 は、データの場所を指定する仕組み（`KEMOMICHI_LOCAL_DATA`、予定、とスキップ処理）のみを用意する
   （データ自体の配置は利用者側の作業とします）

## 付録：データセット調査結果（2026-11-15 確認）

LILA BC（出典参照）は GCS／AWS（Source Cooperative）／Azure で配布しています。
確認した範囲では、どのデータセットのページにも EXIF が保持されているかどうかの記載はありません。

| データセット | 規模 | ライセンス | 備考 |
|---|---|---|---|
| ENA24-detection | 約 1 万枚、23 クラス、全画像に bbox | CDLA-Permissive | 画像 zip 3.6 GB |
| Caltech Camera Traps | 24.3 万枚、約 70% が空撮影 | CDLA-Permissive | 縮小版 CCT20 は 6 GB（長辺 1024px） |
| Desert Lion Conservation | 65,959 枚＋動画 199 本 | CDLA-Permissive | 画像ごとの HTTP URL あり。動画の形式・取得パスは記載なし |
| Trail Camera Images of NZ Animals | 約 250 万枚 | CDLA-Permissive | EXIF の ImageDescription に場所 ID |
| NACTI | 370 万枚 | CDLA-Permissive | zip 1 本が数百 GB |

- **Snapshot Japan 2023**（出典参照）：GBIF 登録（出現記録 7,620 件、CC BY 4.0、画像付きレコード
  0 件）。Camtrap DP パッケージ v7（`https://gbif.jp/ipt/archive.do?r=snapshot_japan_2023` から取得）を
  確認したところ、`media.csv` には 150,624 件の記載があり、全件 `filePublic=true`、画像は Wildlife
  Insights の GCS バケット（`gs://…snapshot_japan_2023__main/…`）参照、`exifData` 欄は全件空です。
  画像を `storage.googleapis.com` で直接取得すると 403、バケット一覧は 401 で取得できないことを
  確認済みです。人が写った画像は論文の記載によれば削除済みです。画像本体の取得手続き
  （Wildlife Insights 経由）は未確認です。
- **SatoyamaCT**（出典参照）：関西大学ほかによるデータセットで、Release v1.0.0 の `images.zip` は
  223,040,207 バイト、`embeddings.zip` は 60,020,867 バイトで、ログインなしで取得可能（HTTP 200 を
  確認。中身は未確認）。CC BY-NC 4.0（非商用限定）。切り出し画像 12,642 枚（IR 約 76%）で、元画像・
  動画は含みません。
- **動画データ（LILA 外、詳細未確認）**：PanAf20K（約 2 万本、42.2 GiB、非商用）、SA-FARI
  （1.1 万本以上、ライセンス未確認）。
- Camtrap DP の解説が国立環境研究所から出されています（出典参照）。

## 出典

- LILA BC：<https://lila.science/datasets>
- ENA24-detection：<https://lila.science/datasets/ena24detection>
- Caltech Camera Traps：<https://lila.science/datasets/caltech-camera-traps>
- Desert Lion Conservation：<https://lila.science/datasets/desert-lion-conservation-camera-traps/>
- Trail Camera Images of NZ Animals：<https://lila.science/datasets/nz-trailcams>
- NACTI：<https://lila.science/datasets/nacti>
- Snapshot Japan 2023（論文）：<https://pmc.ncbi.nlm.nih.gov/articles/PMC11926606/>
- Snapshot Japan 2023（GBIF）：<https://www.gbif.org/dataset/f0a42d7d-1eda-4ec8-ac66-c1343acea3bc>
- Snapshot Japan 2023（Camtrap DP パッケージ）：<https://gbif.jp/ipt/archive.do?r=snapshot_japan_2023>
- Wildlife Insights 利用規約：<https://wildlifeinsights.org/summary-terms-use>
- SatoyamaCT（GitHub）：<https://github.com/keito-git/satoyama-ct>
- SatoyamaCT（論文）：<https://arxiv.org/abs/2609.30278>
- PanAf20K：<https://data.bris.ac.uk/data/dataset/1h73erszj3ckn2qjwm4sqmr2wt>
- SA-FARI：<https://www.conservationxlabs.com/sa-fari>
- Camtrap DP 解説（国立環境研究所）：<https://jxiv.jst.go.jp/index.php/jxiv/preprint/view/1357>
