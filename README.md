# KemoMichi（獣道）

Timelapse2 互換の、クロスプラットフォーム対応カメラトラップ画像解析アプリ。

- Windows / macOS / Linux で動作
- サーバに置いてブラウザから利用可能
- Timelapse2 のプロジェクトファイル（`.tdb` / `.ddb`）をそのまま開いて編集・保存
- 種選択パレット、色味調整、REST 法の補助線とフレーム単位の滞在時間計測

## ダウンロード・インストール（Mac / Windows）

補助アプリを起動すると、ブラウザにKemoMichiの操作画面が開きます。
Python・FFmpegの個別インストールや、ターミナルでのサーバー起動は不要です。
画像・動画・ddbは、自分のPCや接続した外付けHDDに置いたまま利用できます。
ダウンロード案内はこのREADMEで行います。専用の公開ウェブサイトは不要です。

**配布ファイルとOS別の案内は [download フォルダ](download/README.md) にまとめています。**

### 現在入手できる試用版

| 対象 | ファイル名 | 準備状況 |
| --- | --- | --- |
| Mac（Apple Silicon / Mシリーズ） | `KemoMichi-macOS-arm64.dmg` | この開発用PCの `download/mac/apple-silicon/` に配置済み。macOS 26で動作確認済み |
| Mac（Intel） | `KemoMichi-macOS-x86_64.dmg` | ビルド・動作確認待ち |
| Windows（x64） | `KemoMichi-Windows-x86_64-setup.exe` | ビルド・動作確認待ち |
| Windows（x64、ポータブル版） | `KemoMichi-Windows-x86_64-portable.zip` | ビルド・動作確認待ち |

現時点では、この変更に対応したインストーラーをGitHubへ公開していません。
この開発用PC以外で試す場合は、作成済みの配布ファイルを受け取ってください。
GitHubの「Code → Download ZIP」はソースコードの取得用で、アプリのインストーラーではありません。

### Mac：このPCにある試用版を使う

1. Finderを開き、`Command + Shift + G`（フォルダへ移動）を押します。
2. この開発用PCでは、次のパスを入力します。

   ```text
   /Users/ke-katowmo.co.jp/Desktop/program/KemoMichi/download/mac/apple-silicon
   ```

3. `KemoMichi-macOS-arm64.dmg` をダブルクリックします。
4. 開いた画面で **KemoMichi** を **Applications（アプリケーション）** へドラッグします。
5. Finderの「アプリケーション」から **KemoMichi** を開きます。ブラウザに作業画面が表示されます。
6. コピーが終わったら、FinderのサイドバーにあるKemoMichiのディスクイメージを取り出せます。

別のMacで配布ファイルを受け取った場合は、保存したDMGを開き、手順4以降を行います。
Appleメニューの「このMacについて」に表示されるチップがApple Mシリーズなら `arm64`、
Intelプロセッサなら `x86_64` 用を選んでください（[Appleの確認手順](https://support.apple.com/en-us/116943)）。
現在作成済みのDMGはApple Silicon用です。

試用版はDeveloper ID署名・公証が未完了です。macOSに起動を拒否された場合は、
表示されたメッセージを開発者へ知らせてください。

### Windows：配布ファイルを入手したら

Windows版は作成・確認後に利用できます。Mac用DMGはWindowsでは使えません。

1. `KemoMichi-Windows-x86_64-setup.exe` をダウンロードして開きます。
2. インストーラーの案内に従ってインストールします。
3. スタートメニューの **KemoMichi** を開きます。ブラウザに作業画面が表示されます。

ポータブル版を使う場合は、`KemoMichi-Windows-x86_64-portable.zip` を右クリックして
「すべて展開」し、展開先の `KemoMichi` フォルダ内にある `KemoMichi.exe` を開きます。
ZIPの中から直接起動せず、同梱フォルダ・ファイルをまとめて保持してください。
Windows版のコード署名も未完了です。起動を拒否された場合は、表示されたメッセージを開発者へ知らせてください。

### GitHub Actionsから試用版を取得する場合

以下は、開発者が今回のビルド設定をGitHubへ反映し、ビルドが成功した後の手順です。
ビルド設定をGitHubへ反映するまでは、この変更に対応した成果物を取得できません。

1. GitHubへログインし、[KemoMichiのActions](https://github.com/HKimura787/KemoMichi/actions) を開きます。
2. **Desktop builds** の成功した実行を開きます。
3. **Artifacts** から、自分のPCに合う `KemoMichi-macOS-arm64`、`KemoMichi-macOS-x86_64`、
   または `KemoMichi-Windows-x86_64` を選び、ZIPをダウンロードします。
4. ダウンロードしたZIPを展開し、OS別フォルダの案内を開きます。
   Macは `mac/apple-silicon/` または `mac/intel/` のDMG、Windowsは `windows/` のセットアップEXEを使います。

Actions成果物のダウンロードには、GitHubへのログインとリポジトリの読み取り権限が必要です。
成果物には保存期限があります（[GitHubの案内](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts)）。
通常の配布時は、確認済みのインストーラーをGitHub Releasesへ添付する方法も使えます。

### 起動後の使い方・終了

1. 作業画面で **既存のddbを開く・再開** または **tdbから新規作成** を選びます。
2. ファイルまたはフォルダのパスを入力し、一覧からddb・tdbを選びます。
   外付けHDDを使う場合は、HDDを接続してから選んでください。
3. 作業を終えたら、補助アプリの **終了** を押すか、補助アプリのウィンドウを閉じます。

ブラウザのタブを閉じるだけでは補助アプリは終了しません。
画面を閉じた場合は、補助アプリの **ブラウザで開く** で再表示できます。
再開位置も持ち運ぶ場合は、ddb・画像・動画と一緒に、ddbの隣にある
`<ddbのファイル名>.kemomichi` ファイル（例：`調査.ddb.kemomichi`）も保持してください。

補助アプリの詳細・配布用ビルドは [docs/desktop.md](docs/desktop.md)、
依存ライブラリの確認は [docs/license-audit.md](docs/license-audit.md) を参照してください。

## 開発環境ですぐ試す

```bash
uv sync
uv run kemo demo ~/kemomichi-demo
uv run kemo serve ~/kemomichi-demo/TimelapseTemplate.ddb
```

pip でも使えます（`pip install -e .` の後、`kemo ...`）。

詳しくは [docs/mvp.md](docs/mvp.md)。

## 文書

- 変更記録: [CHANGELOG.md](CHANGELOG.md)
- 設計計画: [docs/design-plan.md](docs/design-plan.md)
- デザインシステム: [docs/design-system.md](docs/design-system.md)
- Timelapse2 ファイル形式仕様: [docs/spec/timelapse-format.md](docs/spec/timelapse-format.md)
- MVP の使い方: [docs/mvp.md](docs/mvp.md)

ライセンス: MIT（[LICENSE](LICENSE)）。UI の色・書体はデジタル庁デザインシステムのデザイントークン
（`@digital-go-jp/design-tokens`、MIT ライセンス、© デジタル庁）を使用しています。

※ Timelapse は Saul Greenberg / University of Calgary のソフトウェアです。本プロジェクトは
Timelapse のコードを使用しない独立した実装で、本家とは関係ありません。
