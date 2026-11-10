# Timelapse2 ファイル形式仕様（P0 第1版）

- 作成日: 2026-10-18
- 対象: Timelapse 2.5.x（ソースのバージョン表記 2.5.2.0）の `.tdb` / `.ddb` と関連ファイル
- 作り方: 公開されているソースの動作を読み、**事実（テーブル名・列名・型・値の表現・規則）だけ**を
  自分の言葉で書き起こした。Timelapse のコード（CC BY-NC-SA 4.0）は一切写していない。
- 状態: ソースを読んで得た内容で、実ファイルでの検証はこれから（`fixtures-guide.md` の見本ファイルで行う）。
  **未検証** と書いた項目は推定を含む。
- 各節の「KemoMichi の方針」は、互換を保つために本アプリがどう振る舞うかを定めたもの。

---

## 0. 全体の約束事

- `.tdb` も `.ddb` も SQLite 3 のファイル（UTF-8、ページサイズ 4096 を確認）。
- テーブルの主キーは基本的に `Id INTEGER PRIMARY KEY AUTOINCREMENT`（そのため `sqlite_sequence` が存在する）。
- 列の既定値はすべて**引用符付きの文字列**で定義される（数値列でも `'0'` のような文字列）。
- 真偽値の表現が 2 通りある:
  - データとして書く値は小文字の `true` / `false`。
  - スキーマの既定値として書かれたものは先頭大文字の `True` になっている箇所がある（`ExportToCSV` の既定値）。
  - 読むときは大文字小文字を区別せず「true かどうか」で判定し、それ以外は false。
- 空の値は NULL ではなく空文字列 `''`。
- Timelapse は接続時に外部キーを有効にし、`journal_mode` は既定（`delete`）のまま使う。
  WAL になっているファイルを開くと `delete` に戻す処理がある。
- テーブルを作り直すときは既存テーブルを削除してから作成する。
- **実ファイルでは、作られた時期や更新の履歴によって列の順序や既定値が違うことを確認した**
  （例: 後から追加された列が末尾にある、既定値の有無が違う）。列の位置や既定値を前提にしてはいけない。

**KemoMichi の方針**
- 列は常に**名前で**参照し、位置に依存しない。
- 読むときは真偽値を大文字小文字を区別せずに解釈し、書くときは小文字 `true` / `false`。
- 空は `''` で書く（NULL を書かない）。
- `journal_mode` は変更しない（WAL にしない）。
- 知らないテーブル・列・行は読み飛ばし、書き込み時もそのまま残す。

---

## 1. `.tdb`（テンプレート）

### 1.1 テーブル

| テーブル | 内容 |
|---|---|
| `TemplateTable` | データ入力項目（コントロール）の定義。1 行 = 1 項目 |
| `FolderDataTemplateTable` | フォルダ階層ごとのデータ項目の定義（§4） |
| `FolderDataInfo` | フォルダ階層（レベル）の定義（§4） |
| `TemplateInfo` | テンプレートのバージョン情報。**`.tdb` にだけ存在**し、`.ddb` には作られない |

### 1.2 `TemplateTable` の列

| 列 | 型 | 意味 |
|---|---|---|
| `Id` | INTEGER 主キー | 行番号 |
| `ControlOrder` | INTEGER | 入力パネルでの並び順 |
| `SpreadsheetOrder` | INTEGER | CSV での列順 |
| `Type` | TEXT | コントロール型（§1.4） |
| `DefaultValue` | TEXT | 既定値 |
| `Label` | TEXT | 画面に出す名前 |
| `DataLabel` | TEXT | 列名（DataTable の列名、CSV の見出し） |
| `Tooltip` | TEXT | 説明文 |
| `Visible` | TEXT | 表示するか（`true` / `false`） |
| `List` | TEXT | 選択肢（FixedChoice / MultiChoice のみ。§1.5） |
| `ExportToCSV` | TEXT（既定 `'True'`） | CSV に出力するか |
| `TXTBOXWIDTH` | TEXT | 入力欄の幅（ピクセル） |
| `Copyable` | TEXT | 「前の値をコピー」の対象か |

- 古いテンプレートを更新したときに `ExportToCSV` が後から追加された場合、型名が `Flag`、既定値が `'true'` になる。
- Timelapse は常に `ControlOrder` の順で読む。順序の値は**連続しているとは限らず、0 から始まることもある**。

### 1.3 標準項目（すべてのテンプレートにある 4 行）

| Type（= DataLabel） | Label | 既定値 | 幅 | CSV 出力 | 備考 |
|---|---|---|---|---|---|
| `File` | File | `''` | 100 | true | ファイル名 |
| `RelativePath` | RelativePath | `''` | 100 | true | ルートフォルダからの相対パス |
| `DateTime` | DateTime | `<作成年>-01-01 12:00:00` | 160 | true | 撮影日時 |
| `DeleteFlag` | Delete? | `false` | 20 | **false** | 削除フラグ |

- 4 行とも `Visible` は true、`Copyable` は false、`List` は空。
- 新規作成時の `ControlOrder` は File が 0、以降 1, 2, 3。`SpreadsheetOrder` は 1〜4。
- 標準項目は削除できない。古いファイルの `MarkForDeletion` という DataLabel は DeleteFlag として扱う。

### 1.4 コントロール型

標準 4 型に加え、利用者が追加できる 14 型。**一覧にない型があると Timelapse はファイルを開けない。**

| Type | 新規作成時の DataLabel | 既定値 | 幅 | Copyable |
|---|---|---|---|---|
| `Counter` | `Counter0`, `Counter1`, … | `0` | 30 | **false** |
| `IntegerAny` | `Integer0`, … | `0` | 60 | true |
| `IntegerPositive` | `IntegerPositive0`, … | `0` | 60 | true |
| `DecimalAny` | `Decimal0`, … | `0` | 60 | true |
| `DecimalPositive` | `DecimalPositive0`, … | `0` | 60 | true |
| `Note` | `Note0`, … | `''` | 100 | true |
| `MultiLine` | `MultiLine0`, … | `''` | 100 | true |
| `AlphaNumeric` | `AlphaNumeric0`, … | `''` | 100 | true |
| `FixedChoice` | `Choice0`, … | `''` | 100 | true |
| `MultiChoice` | `MultiChoice0`, … | `''` | 100 | true |
| `Flag` | `Flag0`, … | `false` | 20 | true |
| `DateTime_` | `DateTime_0`, … | `<作成年>-01-01 12:00:00` | 160 | true |
| `Date_` | `Date_0`, … | `<作成年>-01-01` | 120 | true |
| `Time_` | `Time_0`, … | `12:00:00` | 95 | true |

- 自動で付く DataLabel は「接頭辞 + まだ使われていない最小の番号（0 から）」。
- 新規追加した項目の `ControlOrder` は「既存の行数 + 1」、`SpreadsheetOrder` も同じ値。
- 項目を削除すると、それより後ろの `ControlOrder` / `SpreadsheetOrder` が 1 つずつ詰められる。

### 1.5 選択肢（`List`）の表現

- JSON オブジェクト: `IncludeEmptyChoice`（空の選択肢を含めるか、真偽値）と
  `ChoiceListNonEmpty`（選択肢の文字列の配列）の 2 つのキーをこの順に持つ。
- 選択肢が 1 つもない場合は JSON ではなく空文字列 `''`。
- 選択肢は前後の空白を除き、空や重複は取り除かれる。読めない JSON は「選択肢なし・空を含む」とみなされる。

### 1.6 DataLabel の規則（テンプレートエディタが強制する）

- 英字で始まり、英数字と `_` だけ。
- 空は不可。大文字小文字を区別して重複不可。
- `Date` / `Time` と SQLite の予約語（`id`, `date`, `time`, `datetime`, `query`, `plan` など。大文字小文字を区別しない）は、
  末尾に `_` を付けて避ける。

### 1.7 `TemplateInfo`

- 列: `VersionCompatabily`（**この綴りのまま**）、`BackwardsCompatibility`、`Standard`。`Id` 列はない。1 行だけ。
- `VersionCompatabily` = 最後に保存した Timelapse のバージョン、`BackwardsCompatibility` = このファイルを開ける最も古いバージョン。
- `Standard` = 準拠する規格。`''`、`AlbertaMetadataStandard`、`CamtrapDP` のいずれか。
- 古いファイルの修復: 綴り違いの `VersionCompatability` 列は改名され、欠けた列・行は追加される。

**KemoMichi の方針（§1 全体）**
- 型・既定値・幅・Copyable は上表に合わせて新規項目を作る（Timelapse で作った場合と同じ結果にする）。
- 種ごとの Counter の一括追加（計画書 §6.1）は、上の採番規則と順序の規則に従う。
- 選択肢の JSON はキーの順序まで同じ形で書く。
- DataLabel の検証規則は同じものを実装する。
- `TemplateInfo` の値は変更しない（§5）。

---

## 2. `.ddb`（データ）

### 2.1 テーブル

| テーブル | 内容 |
|---|---|
| `TemplateTable`, `FolderDataTemplateTable`, `FolderDataInfo` | テンプレートの写し。行は作り直されるため `Id` は `.tdb` と一致しない |
| `DataTable` | 1 行 = 1 ファイル（画像・動画） |
| `ImageSetTable` | イメージセット全体の情報（1 行） |
| `MarkersTable` | Counter のマーカー（点）（§2.4） |
| `Level1`, `Level2`, … | フォルダ階層ごとのデータ（§4） |
| `Info`, `DetectionCategories`, `ClassificationCategories`, `Detections`, `DetectionsVideo` | 認識結果（§3。取り込み後にだけ存在） |
| `Classifications` | 古い形式の認識結果（読み込み時に `Detections` へ統合される） |

既定のファイル名は `TimelapseData.ddb` と `TimelapseTemplate.tdb`。
KemoMichi での新規作成時は、テンプレートと同じ名前の `.ddb` にする（例: `調査.tdb` → `調査.ddb`）。

### 2.2 `DataTable`

- `Id INTEGER PRIMARY KEY AUTOINCREMENT` の後に、`TemplateTable` の項目ごとに 1 列（列名 = DataLabel）。
  列の順序は作成時は `ControlOrder` 順と推定（**未検証**）。後から追加された列は末尾。
- 列の型と既定値:

| 項目 | 型 | 列の既定値 |
|---|---|---|
| `DateTime` | `DATETIME` | 項目の既定値（`yyyy-MM-dd HH:mm:ss` として読めない場合は `<年>-01-01 12:00:00`） |
| `IntegerAny` / `IntegerPositive` / `DecimalAny` / `DecimalPositive` | TEXT | 常に `''`（行の追加時には項目の既定値が明示的に書き込まれる） |
| その他すべて | TEXT | 項目の既定値（空なら `''`）。例: DeleteFlag は `'false'`、Counter は `'0'` |

- 行を追加するときは `Id` 以外の全列に値を明示して書く。
- 索引（開くたびに無ければ作成）: `IndexRelativePath`(RelativePath)、`IndexFile`(File)、
  `IndexRelativePathFile`(RelativePath, File)、`IndexRelativePathDateTimeFile`(RelativePath, DateTime, File)、
  `IndexDeleteFlag`(DeleteFlag、大文字小文字を区別しない比較)。
- 任意の索引: エピソード番号を書き込んだ列の `IndexEpisodeField`、認識結果用の 3 つ（§3）。

### 2.3 `ImageSetTable`

| 列 | 型 | 作成時の値 |
|---|---|---|
| `Id` | INTEGER 主キー | 1（1 行だけ） |
| `RootFolder` | TEXT | `.ddb` があるフォルダの**名前だけ**（フルパスではない） |
| `Log` | TEXT | `''`（利用者のメモ） |
| `Row` | TEXT | `-1`（最後に表示したファイルの Id。列名は歴史的経緯で `Row`） |
| `VersionCompatabily` | TEXT | 作成した Timelapse のバージョン |
| `BackwardsCompatibility` | TEXT | `2.3.3.0` |
| `SortTerms` | TEXT | 既定の並べ替え（§2.6） |
| `SearchTerms` | TEXT | `{}` |
| `QuickPasteTerms` | TEXT | `[]` |
| `BBDisplayThreshold` | REAL（既定 `-1`） | BBox を表示する信頼度の閾値。-1 は既定値を使う意味 |
| `Standard` | TEXT | テンプレートの `Standard` |

Timelapse はこの表を `Id = 1` の行として読む。

### 2.4 `MarkersTable`（マーカー）

- `Id` の後に、**Counter 型の項目ごとに 1 列**（列名 = DataLabel、TEXT）。
  新規作成時の列は既定値 `''`、後から追加された列は既定値 `'[]'`。
- 行の `Id` は対応する `DataTable` の `Id` と同じ値（外部キーはない）。
  その画像で初めてカウンタをクリックしたときに作られ、作られた時点で全列が `'[]'`。
- 値は点の JSON 配列。座標は**画像の幅・高さで割った 0〜1 の相対座標**（左上が原点）、小数第 4 位で丸め。
  各要素は `"x,y"` という文字列と推定（**未検証**。見本ファイル 05 で確認する）。
- 古い形式として `x,y|x,y` の記述が残っているが、現行の読み込みは JSON だけを解釈し、読めないところで打ち切る。
- `DataTable` の Counter の値（個数）は点の数とは**独立に**保存される（点から計算されない）。
- ファイルの記録を削除すると、`DataTable` と `MarkersTable` の行が一緒に消える。

### 2.5 値の表現

| 種類 | 表現 |
|---|---|
| `DateTime` | `yyyy-MM-dd HH:mm:ss`。**時差・タイムゾーン情報なし**（カメラの時計の現地時刻そのまま） |
| `DateTime_` | `yyyy-MM-dd HH:mm:ss` |
| `Date_` | `yyyy-MM-dd` |
| `Time_` | `HH:mm:ss`（24 時間制） |
| Flag / DeleteFlag | `true` / `false`（小文字） |
| Counter / 整数 | 整数の文字列。空 `''` もありうる |
| 小数 | `.` 区切りの文字列（地域設定に依存しない）。空もありうる |
| MultiChoice | 選んだ項目をカンマ区切り（空白なし、前後のカンマなし）。項目の並び順は**未検証** |
| AlphaNumeric | 英数字・`_`・`-` のみ |
| `RelativePath` | 区切りは `\`（Windows 形式）。先頭・末尾に区切りなし。ルート直下のファイルは `''` |
| `File` | ファイル名のみ |

- 撮影日時の取得順: EXIF の DateTimeOriginal → Reconyx 独自の日時 → ファイルの作成日時と更新日時の早い方。
- 年が 1900〜2100 の範囲外、または読めない日時は `1900-01-01 00:00:00` に書き換えられる。
- 古い形式 `yyyy-MM-ddTHH:mm:ss.fffZ` も読める扱いになっている（**未検証**）。

**KemoMichi の方針（§2 全体）**
- `RelativePath` は内部では OS に合わせて扱い、`.ddb` に書くときは必ず `\` 区切りにする（macOS / Linux でも）。
- 日時はタイムゾーンを付けない現地時刻として扱う。表示・計算でタイムゾーンを補正しない。
- 新しいファイルの行を追加するときは、Timelapse と同じく全列に値を明示する。
- マーカーは `MarkersTable` に同じ形式で書く（ポイント機能、計画書 §6.6）。Counter の値は点の数と連動させるが、
  Timelapse で付けた「点の数と一致しない個数」は勝手に直さない（不一致を表示するだけ）。
- 索引は Timelapse と同じものを作る（無ければ）。

### 2.6 `ImageSetTable` に保存される JSON

いずれも JSON のキーは先頭大文字（例: `DataLabel`）、列挙値は整数で書かれる。

- **SortTerms**: 2 要素の配列（第 1・第 2 の並べ替え条件）。各要素は `DataLabel`、`DisplayLabel`、`ControlType`、
  `IsAscending`（**文字列**の `"true"` / `"false"`）を持つ。既定は RelativePath 昇順 → DateTime 昇順。
- **QuickPasteTerms**: 配列。各要素は `Title` と `Items`。`Items` の各要素は `DataLabel`、`Label`、
  `Use`（JSON の真偽値）、`Value`（文字列）、`ControlType`。
  テンプレートに無くなった項目は読み込み時に除かれ、新しい Flag 項目の値は `"False"`（先頭大文字）で補われる。
- **SearchTerms**: 検索条件のオブジェクト。主なキー:
  - `SearchTerms`: 条件の配列（各要素に `ControlType`、`DatabaseValue`、`DataLabel`、`Label`、`List`、`Operator`、`UseForSearching`）
  - `Operator` の値は `=`、` GLOB `、` ^GLOB `、` Includes `、` Excludes `、`>`、`≥`、`<`、`≤`、`≠`
    （**語の演算子は前後に空白を含む**。不等号は Unicode の記号）
  - `TermCombiningOperator`（0 = AND、1 = OR）、`RandomSample`、`UseTimeInsteadOfDate`、
    `ShowMissingDetections`、`EpisodeShowAllIfAnyMatch`、`EpisodeNoteField`
  - `RecognitionSelections`: 認識結果による絞り込み条件（検出カテゴリ番号、分類カテゴリ番号の配列、信頼度の上下限など）
  - 項目の型を変えると SearchTerms は `''` にリセットされる。

**KemoMichi の方針**: 3 つとも**読み書きはするが、理解できないキーは保持したまま**書き戻す。
KemoMichi のフィルタ（計画書 §6 の方針 3）と SearchTerms は相互変換し、変換できない条件は元の JSON を残す。

---

## 3. 認識結果（AI の検出結果）

### 3.1 テーブル

| テーブル | 列 |
|---|---|
| `Info` | `infoID`（1 行だけ）、`detector`、`megadetector_version`（既定 `vUnknown`）、`detection_completion_time`、`classifier`、`classification_completion_time`、`typical_detection_threshold`（既定 0.2）、`conservative_detection_threshold`（既定 0.05）、`typical_classification_threshold`（既定 0.5） |
| `DetectionCategories` | `category`（主キー、番号の文字列）、`label`。番号 `0` = `Empty` が必ず入る |
| `ClassificationCategories` | `classification`（主キー。列名は category ではない）、`label`、`description`（既定 `''`） |
| `Detections` | `detectionID`（主キー、連番。欠番あり）、`category`、`conf`、`bbox`、`classification`、`classification_conf`、`Id`（= DataTable の Id。削除時に連動して消える） |
| `DetectionsVideo` | `frame_number`、`frame_rate`、`detectionID`（= Detections。削除時に連動）。主キーなし |

- 型名に SQLite の正式な型でない `STRING` が使われているため、列は数値寄りの扱い（NUMERIC 親和性）になり、
  `"1"` のような番号は**整数として保存される**（KemoMichi で同じ定義のテーブルを作って確認）。読むときは文字列に直して扱う。
- 索引: `IndexDetectionID`(Detections.Id)、`IndexDetectionVideoID`(DetectionsVideo.detectionID)、
  `IndexDetectionsClassificationConfidence`(classification, conf, classification_conf, Id)。
- 認識結果のテーブルが空なら、開くときに削除される。

### 3.2 値

- `bbox`: 4 つの数値を「カンマ + 空白」で区切った文字列（例 `0.123, 0.4, 0.05, 0.1`）。
  意味は画像に対する相対の **左上 x, 左上 y, 幅, 高さ**。空文字列は「枠なし」。
- **取り込み時に枠が少し広げられる**: x と y から 0.002 を引き、幅と高さに 0.004 を足し、負の値は 0 にして小数第 3 位で丸める。
- `conf` / `classification_conf` は小数第 3 位で丸め。
- 分類は検出ごとに**最も信頼度の高い 1 つだけ**を保存する。
- 処理済みで検出がない画像には「カテゴリ 0、conf 0、bbox 空」の 1 行が入る（処理済みの印）。
  検出リスト自体が null の画像には行が入らない。

### 3.3 認識結果 JSON の取り込み

- 読むキー: `info`（`detector`、`detection_completion_time`、`classifier`、`classification_completion_time`、
  `format_version`（**読むだけで確認しない**）、`summary_report`、`detector_metadata`、`classifier_metadata`）、
  `detection_categories`、`classification_categories`、`classification_category_descriptions`、`images`。
- `images[]`: `file`、`frame_rate`、`detections`。`detections[]`: `category`、`conf`、`bbox`（4 要素以外は枠なし扱い）、
  `frame_number`、`classifications`（`[番号, 信頼度]` の配列）。
- 取り込み直後の間引き:
  - 検出: 信頼度が `max(0.03, conservative_detection_threshold / 2.5)` 未満は捨てる。
  - 分類: `max(0.03, typical_classification_threshold / 2.5)` 未満は捨て、残りの最上位 1 つだけ残す。
  - 名前が空の分類は `unknownClassification`、`unknownClassification2`… に改名。
- 画像と動画の判定: `file` が `.jpg` / `.jpeg` で終われば画像、それ以外は動画。
  動画は `frame_number >= 0` かつ画像単位の `frame_rate > 0` のときだけ保存される。
  **PNG などの画像や `frame_rate` のない動画の検出は黙って捨てられる。**
- パスの照合: `/` を `\` に置き換えてから、ファイル名と相対パスで `DataTable` の `File` / `RelativePath` と照合。
  一致しないファイルは黙って飛ばす。フォルダが 1 つも一致しなければ取り込み失敗。
  JSON がサブフォルダにある場合はサブフォルダ名を補って照合を試みる。
- 既存の認識結果がある場合は**統合**: カテゴリは**名前（label）で**突き合わせて番号を振り直し、
  JSON に含まれる画像の古い検出は削除して入れ替え、含まれない画像の検出は残す。
  カテゴリの番号と名前が矛盾すると、全削除して入れ替えるかを利用者に尋ねる。
- AddaxAI の単体版で作られたと推定されるファイル（分類クラスが検出カテゴリにも入っている、
  または名前が `image_recognition_file.json`）には警告を出す。

**KemoMichi の方針**
- 取り込み結果が Timelapse と**同じ行になる**よう、間引き・丸め・枠の拡大・処理済みの印・番号の振り直しを同じ規則で行う
  （Timelapse で取り込んだ見本 07 と比較して検証）。
- ただし「黙って捨てる」ケース（PNG、frame_rate なし、一致しないファイル）は、KemoMichi では**件数と理由を表示**する。
  互換性のため保存はしない（Timelapse と同じ結果）が、利用者が気付けるようにする。
- 表示時は枠の拡大を戻さない（Timelapse と同じ見え方にする）。

---

## 4. フォルダ階層データ（レベル）

- `FolderDataInfo`: レベルごとに 1 行（`Id` = `Level`）。`Level`、`Guid`（小文字・ハイフン付きの GUID）、`Alias`（表示名）。
  レベル 1 = ルートフォルダ。
- `FolderDataTemplateTable`: `TemplateTable` と同じ列に `Level` を加え、`TXTBOXWIDTH` と `Copyable` を除いたもの。
- データは `.ddb` の `Level1`、`Level2`、… テーブルに入る。列は `Id`、`FolderDataPath`、項目ごとの列（型と既定値の規則は §2.2 と同じ）。
  項目が 1 つもないレベルのテーブルは作られない。
- `FolderDataPath`: レベル 1 は `''`、レベル N は相対パスの先頭 N-1 階層を `\` で連結したもの
  （例: レベル 2 = `SiteA`、レベル 3 = `SiteA\Cam1`）。この値で行を特定する。
- `.ddb` と `.tdb` のレベルは、まず Guid、次に Alias で対応付けられる。

**KemoMichi の方針**: 同じ構造で読み書きする。カメラ（フォルダ）単位の KemoMichi 独自設定
（ガイド図形、色味プリセットなど）は `FolderDataPath` と同じ表記のパスをキーにしてサイドカーに保存する。

---

## 5. バージョンと互換性

- 定数: 最低対応 2.3.0.0、後方互換の基準 2.3.3.0（テンプレートは 2.3.0.0）。バージョンは 4 つの数字の大小で比較する。
- `.tdb` を開く前の確認:
  - `TemplateTable` がない → 不正なファイル。
  - `TemplateInfo` がない、または型 `UtcOffset` の項目がある → 2.3 より前の形式（専用の変換ツールが必要）。
  - `VersionCompatabily` が実行中の版より新しい → 警告するが開く。
- `.ddb` を開く前の確認:
  - `DataTable` がない → 不正なファイル。
  - `ImageSetTable.VersionCompatabily` がない・2.3.0.0 未満・`DataTable` に `UtcOffset` 列がある → 2.3 より前の形式。
  - 実行中の版が `BackwardsCompatibility` より古い → **開けない**。
  - `VersionCompatabily` が実行中の版より新しい → 警告するが開く。
  - SQLite の簡易整合性検査（`quick_check`）が通ること。
- 開いた後: Timelapse は `VersionCompatabily` を自分の版まで引き上げ、`BackwardsCompatibility` が 2.3.3.0 未満なら引き上げる。
  **下げることはない。**
- 開くたびに行われる補修: 欠けた列・行・テーブルの追加、WAL の解除など。

**KemoMichi の方針**
- `VersionCompatabily` と `BackwardsCompatibility` は**書き換えない**（KemoMichi のバージョンを書かない。
  Timelapse の旧版で開けなくなるのを防ぐため）。KemoMichi が書いたことはサイドカーに記録する。
- 新規作成する `.tdb` / `.ddb` には、対応を確認した Timelapse のバージョン（例: 2.5.2.0）と 2.3.3.0 を書く。
- `BackwardsCompatibility` が KemoMichi の対応範囲より新しいファイルは読み取り専用で開く。
- 2.3 より前の形式は開かず、Timelapse の変換ツールの使用を案内する。
- Timelapse が開くたびに行う補修（欠けた列の追加など）は、KemoMichi では**行わない**（読み取り時に補って扱うだけ）。
  ファイルを変更するのは利用者がデータを編集したときだけにする。

---

## 6. テンプレートの変更（`.ddb` と `.tdb` の同期）

Timelapse は `.ddb` を開くとき、その中のテンプレートと `.tdb` を比べ、違えば利用者に尋ねて同期する。

- 利用者は `.ddb` 内のテンプレートを使い続けることも選べる（その場合は何も変わらない）。
- DataLabel の集合が違う場合、`.ddb` の `TemplateTable` を削除して `.tdb` から写し直す。
- **追加された項目**: `DataTable` の末尾に列を追加（型と既定値は §2.2 の規則。既存の行は既定値になる）。
  Counter なら `MarkersTable` にも既定値 `'[]'` の列を追加。
- **削除された項目**: テーブルを作り直して列を削除。`MarkersTable` の同名列も削除し、全列が `'[]'` の行は消す。
- **改名**（利用者が追加と削除の組を改名として確認したもの）: 各テーブルの列名を変更。
- 順序・既定値・ラベル・説明・幅・Copyable・Visible・ExportToCSV・選択肢の変更: `.ddb` のテンプレート行に反映。
  列の既定値が変わった場合は `DataTable` を作り直す。
- 型の変更は一部だけ許される（Flag / AlphaNumeric / FixedChoice / MultiChoice / Counter → 文字列型、
  FixedChoice → MultiChoice、Counter → 整数・小数型 など）。それ以外は同期エラー。
- 同期の前にバックアップが作られる。

**KemoMichi の方針**
- 種ごとの Counter の一括追加など、KemoMichi でテンプレートを変えるときは、**`.tdb` と `.ddb` の両方**を、
  Timelapse が同期したときと同じ結果になるように変更する。そうすれば Timelapse で開いたときに同期の確認が出ない。
- 項目の削除・型の変更は第 1 版では行わない（Timelapse のテンプレートエディタに任せる）。
- 変更前に必ずバックアップ（§7）。

---

## 7. バックアップと削除ファイル

- バックアップ: 元ファイルと同じ場所の `Backups/` に `<名前>.yyyy-MM-dd.HH-mm-ss<拡張子>`（現地時刻）。
  新しい 8 個は残し、それ以外で 14 日より古いものは削除。書き込み前に最大 30 分に 1 回、
  テンプレート同期の前、CSV 取り込みの前などに作られる。
- 削除: 「削除したファイルを保存する」設定なら画像を `<画像のルート>/DeletedFiles/<相対パス>/<ファイル名>` に移す。
  ファイルだけ削除した場合は記録が残り DeleteFlag が false に戻る。記録も削除した場合は `DataTable` と `MarkersTable` の行を消し、
  データベースを最適化（VACUUM）する。
- フォルダの走査では `Backups`、`DeletedFiles`、`.vthumb` を除外する。

**KemoMichi の方針**: 同じ場所・同じ命名規則・同じ保持規則でバックアップを作る（Timelapse と KemoMichi の
どちらで作ったバックアップも同じ一覧に並ぶ）。走査で除外するフォルダも同じにする。

---

## 8. CSV

### 8.1 出力

- 既定のファイル名 `ImageData.csv`。**UTF-8（BOM 付き）**、改行は CRLF、区切りはカンマ。
  KemoMichi では、既定の出力名をデータファイルと同じ基本名にする（例: `調査.ddb` → `調査.csv`）。
- 値にダブルクォート・カンマ・改行が含まれるときだけダブルクォートで囲み、中のダブルクォートは 2 つ重ねる。
- 列の順序:
  1. フォルダ階層ごとの列（見出しは Alias、空なら `Level-N`）。レベル 1 は常に空、レベル N は相対パスの先頭 N-1 階層。
     パスが浅い行ではセルが書かれず列数が足りなくなる（Timelapse の不具合と思われる）。
  2. `RootFolder`（設定で出力する場合。既定で出力）。
  3. 各項目の DataLabel を `SpreadsheetOrder` の順に（`ExportToCSV` が false の項目を除く）。標準項目も含む。
- 日時: 既定は `yyyy-MM-dd HH:mm:ss`。設定で `T` 区切り、または `Date`（`dd-MMM-yyyy`、英語の月名）と
  `Time`（`HH:mm:ss`）の 2 列に分けられる。**既定で日時の前に空白を 1 つ入れる**（Excel が日時を勝手に変換しないため）。
- その他の値は保存されている文字列のまま。認識結果は CSV に出ない。
- フォルダ階層データはレベルごとに別ファイル `<Alias または Level-N>.csv`。

### 8.2 取り込み

- 見出し行 + 1 行以上。各値は前後の空白を除いて読む（日時の前の空白も除かれる）。
- `File` と `RelativePath` の列が必須。その他の見出しはテンプレートの DataLabel か `RootFolder` / `Date` / `Time` /
  `Folder` / `ImageQuality` でなければならず、**知らない見出しがあると取り込み全体を中止**。
- 型ごとに値を検証し、1 つでも不正なら全体を中止（最初の 5 件を報告）。
- `File` と `RelativePath` が完全一致する行を更新。`File` / `RelativePath` / `RootFolder` などは更新しない。
  一致しない行は黙って無視。全体を 1 つのトランザクションで書く。
- `RelativePath` が空（ルート直下）の行は `File` だけで照合されるため、**別フォルダの同名ファイルまで更新される**（不具合と思われる）。

**KemoMichi の方針**
- 出力は同じ書式（BOM、CRLF、引用規則、日時の前の空白、列順）を既定にする。
  フォルダ階層の列が欠ける不具合は**再現せず**、空のセルを書く（列数をそろえる）。
- 取り込みは同じ検証規則にするが、ルート直下の同名ファイルの問題は再現せず、`RelativePath` が空でも正しく照合する。
  一致しない行は件数を表示する。

---

## 9. エピソード

- **保存されず、その都度計算される**。現在の並び順・絞り込みの中で、連続するファイルの撮影日時の差が閾値以下なら同じエピソード。
  フォルダの境界は見ない（既定の並び順 RelativePath → DateTime に依存）。
- 閾値は既定 2 分（1 秒〜30 分）。**利用者ごとに Windows のレジストリに保存**され、`.ddb` には入らない。
- 前後最大 1000 ファイル（設定で 10000）までしか調べない。
- 「エピソード情報を項目に書き込む」機能で Note 項目に `<番号>:<位置>|<総数>`（例 `23:1|7`）、`<番号>`、`<位置>|<総数>` のいずれかの形で保存できる。

**KemoMichi の方針**: 同じ規則で計算する。閾値はサイドカーに保存（プロジェクトごと）。
フォルダをまたいでエピソードがつながらないようにする設定を追加する（既定は Timelapse と同じ）。
Note 項目への書き込みは同じ 3 形式。

---

## 10. CamtrapDP 出力（概要）

- テンプレートの `Standard` が `CamtrapDP` のときだけ使える。出力先 `CamtrapDPExportedFiles/`。
- `datapackage.json`（レベル 1 のフォルダデータから）、`deployments.csv`（レベル 2 の各行。`deploymentID` はフォルダのパス）、
  `media.csv`、`observations.csv`（DataTable から。空の ID には GUID を補う）。
- 日時は現地時刻の末尾に `Z` を付けた形（UTC に変換していない）。動画の MIME 型の表記に誤りがある。
- 認識結果は使われない（BBox などは利用者が入力した項目の値）。

**KemoMichi の方針**: P4 で実装。CamtrapDP の規格に正しく従う（日時は時差付きで出力、MIME 型を正しく）。
Timelapse と結果が違う点は文書に明記する。

---

## 11. 見本ファイルで確認すること（未検証項目）

| 項目 | 確認する見本 |
|---|---|
| マーカーの点の JSON の正確な形 | 05 markers |
| `DataTable` の列順 | 01 minimal、10 template-update |
| MultiChoice の項目の並び順 | 02 all-control-types |
| SearchTerms / QuickPasteTerms の実際の JSON | 11 saved-state |
| `STRING` 型の列に入った値の実際の型（同じ定義で整数になることは確認済み。Timelapse 実機での確認） | 07 recognitions |
| 古い日時形式（末尾 `Z`）の扱い | 14 old-version |
| テンプレート同期で `.ddb` がどう変わるか | 10 template-update |
| CSV のバイト列（BOM、CRLF、空白） | 12 csv-export |
