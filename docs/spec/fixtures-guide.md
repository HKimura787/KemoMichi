# ゴールデンファイル（見本ファイル）作成手順

KemoMichi が Timelapse2 と損失なく往復できることを検証するため、**Timelapse2 実機で作った見本ファイル**
（`.tdb` / `.ddb`）をテストに使う。この文書はその作り方の手順書。

## 守ること

- **実データは使わない**。画像はダミー（下記「ダミー画像」）を使い、種名・項目名も架空のものにする。
  実プロジェクトのテンプレートやデータをリポジトリに入れてはならない。
- 作ったファイルは `tests/fixtures/<番号>-<名前>/` に置く（`.gitignore` はこのフォルダの `.tdb` / `.ddb` だけを許可している）。
- 各フォルダに `README.md` を置き、使った Timelapse2 のバージョンと、行った操作を書く。
- 1 つの見本では 1 つの観点だけを確認する（問題が起きたときに原因を特定しやすくするため）。

## ダミー画像

- 単色や文字だけの小さな JPEG（例: 640×480）を 10 枚程度。KemoMichi 側で生成スクリプトを用意する。
- EXIF の撮影日時を入れたものと入れないものを両方用意する。
- サブフォルダを 2 階層ほど作る（例: `CamA/2026-01/`, `CamB/2026-01/`）。
- 動画は短い（数秒）ダミー動画を MP4 と AVI で 1 本ずつ。

## 作成する見本ファイル

| # | 名前 | 内容 | 確認する観点 |
|---|---|---|---|
| 01 | minimal | 標準項目だけのテンプレートで画像を読み込む。入力はしない | 最小構成の `.tdb` / `.ddb` の構造 |
| 02 | all-control-types | 全コントロール型（Counter, FixedChoice, MultiChoice, Flag, Note, MultiLine, AlphaNumeric, IntegerAny, IntegerPositive, DecimalAny, DecimalPositive, DateTime_, Date_, Time_）を 1 つずつ作り、各型に値を入力 | 型ごとの列の型と値の表現 |
| 03 | empty-and-defaults | 02 と同じテンプレートで、既定値のまま・空欄・0 などを混在させる | 空値・既定値の表現 |
| 04 | species-flags | 架空の種 5 つを Flag で作り、種ごとの Counter も作る。1 枚に複数種を ON にした画像を含める | 種選択パレット・複数種・種ごとの個数 |
| 05 | markers | Counter でマーカー（点）を画像上に打つ（1 枚に複数点、複数の Counter） | `MarkersTable` の点の表現 |
| 06 | folder-levels | フォルダ階層メタデータ（Level）を 2 階層定義し、値を入力 | フォルダ階層データの表 |
| 07 | recognitions | KemoMichi が用意するダミーの認識結果 JSON を取り込む（画像・動画の両方） | 認識結果の表 |
| 08 | datetime-edits | 日時補正（一括オフセット、月日の入替）を実行 | 日時の保存形式と補正後の値 |
| 09 | delete-flag | 削除フラグを付け、一部を実際に削除 | `DeleteFlag` と `DeletedFiles/` |
| 10 | template-update | 01 の `.ddb` を作った後でテンプレートに項目を追加し、Timelapse2 で開き直して更新を受け入れる | テンプレート変更時の `.ddb` の変化 |
| 11 | saved-state | 並べ替え・検索条件・QuickPaste を設定して閉じる | `ImageSetTable` に保存される設定 |
| 12 | csv-export | 02 のデータを CSV 出力（ファイルも保存） | CSV の列順・書式・文字コード |
| 13 | video | ダミー動画を読み込み、値を入力 | 動画ファイルの行 |
| 14 | old-version | 可能なら Timelapse 2.3 系で作ったファイル | 旧版との互換 |

各見本では、**操作前と操作後の両方**のファイルを残す（例: `before/`, `after/`）。
差分から「その操作で何が変わるか」を正確に読み取るため。

## 手順の書き方（各フォルダの README.md）

```
Timelapse2 バージョン: 2.5.x.x
OS: Windows 11
手順:
1. テンプレートエディタで新規テンプレートを作成し、…を追加
2. フォルダ … を読み込み
3. 1 枚目の画像で … に … を入力
…
```

## KemoMichi 側の確認方法（P1 で実装）

- 見本を読み込み → 何も変えずに保存 → スキーマと全行が完全一致すること。
- 見本の `before` に KemoMichi で同じ操作をし、Timelapse2 が作った `after` と一致すること。
- KemoMichi が保存したファイルを Timelapse2 で開き、警告なく開けること（手動確認チェックリスト）。
