# KemoMichi 補助アプリ

各利用者のPCで処理を動かし、既定のブラウザで操作します。データは各自のHDD上に保持します。
Python・必要なPythonライブラリ・Web画面・FFmpeg / ffprobe をアプリへ同梱します。

## 利用者の操作

1. Macは `.dmg` を開き、KemoMichi をアプリケーションフォルダへコピーします。
   Windowsは `KemoMichi-Windows-x86_64-setup.exe` の案内に沿ってインストールします。
2. KemoMichi のアイコンを開くと、ブラウザに作業画面が開きます。
3. 「既存のddbを開く・再開」または「tdbから新規作成」を選びます。
   ファイル・フォルダのパスを入力して移動し、一覧から対象を選択できます。
4. 終了時は補助アプリの「終了」を押すか、補助アプリのウィンドウを閉じます。
   実行中のプロジェクト作成・HTTP処理を待ち、データベースを閉じて終了します。

ブラウザのタブを閉じるだけでは処理は終了しません。「ブラウザで開く」で作業画面を再表示できます。
補助アプリ上では、Macの `Command+O`、Windowsの `Ctrl+O` でも再表示できます。
同じ補助アプリをもう一度起動すると、既存の処理を使ってブラウザを再表示します。
CLI版と同時に動かしても、空きポートを自動で選ぶため、既定ポート8765との衝突を避けます。

## プロジェクト・判読位置・CSV

- 既存の `.ddb`: フォルダから選択するか、ファイルのフルパスで開きます。
- 新規作成: 最初に画像・動画フォルダを選び、次の画面で `.tdb` を選びます。
  テンプレートが別のフォルダにある場合も、そのファイルやフォルダのパスで探せます。
- 新規の `.ddb` と出力 `.csv` は、元のファイルと同じ基本名になります。
- 書き込み可能なプロジェクトでは、選択中のファイル・動画のフレーム・絞り込み・表示モードを
  `.ddb.kemomichi` に保存します。再度そのddbを開くと、最後に保存した位置から再開します。
  動画再生中は約1秒ごとに保存し、一時停止時・ページを離れる際にも保存します。
  読み取り専用の場合は既存の保存位置を読み込みますが、新しい位置は書き込みません。
- HDDを別のPCへ移すときは、ddb・画像・動画に加えて `.ddb.kemomichi` も一緒に保持してください。

## 開発・ビルド

ビルドは対象OSごとに実行します。MacのAppleシリコン用とIntel用も別々に作ります。
ビルド環境にはTkが利用できるPython、Node.js、FFmpeg / ffprobe、MacではXcode Command Line Toolsが必要です。
Windowsでインストーラーを作る場合は Inno Setup 6 が必要です。利用者のPCではこれらの準備は不要です。

```sh
uv sync --group desktop
cd web
npm ci
cd ..
uv run --group desktop python tools/package_desktop.py
```

`KEMOMICHI_FFMPEG_DIR` でビルド時のFFmpeg / ffprobeの実体があるフォルダを指定できます。
WindowsのChocolatey等のラッパー・shimではなく、実体の `.exe` を指定します。
配布物は `dist/installers/` に作成されます。Macは `.dmg`、WindowsはインストーラーとポータブルZIPです。
ビルド後、そのOSの配布物を `download/mac/apple-silicon/`、`download/mac/intel/`、
または `download/windows/` へコピーし、照合用の `SHA256SUMS.txt` を作成します。
`download/` の案内文はGitで管理し、生成された配布ファイルはReleasesまたはActions成果物で共有します。
`--bundle-only` では `.app` / 実行フォルダのみ、`--skip-web-build` では既存のWebビルドを利用します。

```sh
uv run kemo-desktop
# ビルドしたMacアプリの自己テスト（PythonやHomebrewのPATHを使わない）
PATH=/usr/bin:/bin dist/KemoMichi.app/Contents/MacOS/KemoMichi \
  --smoke-test --state-dir /tmp/kemo-check --report /tmp/kemo-report.json
```

自己テストは一時フォルダに日本語・空白を含むパスのサンプルを作り、同梱ツール、Web画面、ddb、画像、動画を確認します。
`.github/workflows/desktop-build.yml` はMac arm64 / Mac x86_64 / Windows x86_64をビルドし、
自己テスト後に `download/` の構成をActions成果物へ保存します。実行しただけでは公開リリースを作成しません。

## ローカル接続とログ

補助アプリは `127.0.0.1` のみで待ち受け、起動ごとのセッションとブラウザのCookieで接続します。
操作画面も各利用者のPCから読み込みます。
ログと二重起動防止用の状態は、Macでは `~/Library/Application Support/KemoMichi`、
Windowsでは `%LOCALAPPDATA%\KemoMichi` に保存します。「ログフォルダを開く」で確認できます。

画像・動画のキャッシュは既定で2 GiBまで保持し、生成成功時に古いものから整理します。
`KEMOMICHI_CACHE_MAX_BYTES` で容量を変更できます。保存先と例外は [メディアキャッシュ](media-cache.md) を参照してください。

## Windows版をGitHub Actionsで作る

Windows用インストーラーはWindows環境で作成します。このMacから直接ビルドする方式ではありません。
GitHub Actionsを利用すると、手元にWindowsの開発環境を用意せずに作成できます。

1. `.github/workflows/desktop-build.yml` を含む現在のブランチをGitHubへpushします。
2. PRを作成します。対象ファイルの変更により **Desktop builds** が自動実行されます。
3. GitHubの **Actions → Desktop builds** で、Windowsのビルドと自己テストが成功したことを確認します。
4. その実行の **Artifacts → KemoMichi-Windows-x86_64** をダウンロードしてZIPを展開します。
5. `windows/` 内の `KemoMichi-Windows-x86_64-setup.exe` がインストーラーです。
   `KemoMichi-Windows-x86_64-portable.zip` は、展開して利用するポータブル版です。

このワークフローはインストーラーの作成・自己テストまで行います。
Windows実機での画面操作確認やコード署名は別途行います。GitHub Releasesへの公開は自動実行しません。

## 配布と公開前の作業

ダウンロード・インストール手順は [download/README.md](../download/README.md) にまとめます。
専用の公開ウェブサイトは使用しません。確認済みのインストーラーは直接渡すか、
GitHub Actionsの成果物またはGitHub Releasesの添付ファイルとして配布できます。

今回のMacビルドはAppleシリコン・macOS 26で確認する試用版です。
WindowsおよびIntel MacはCI・実機での確認が必要です。MacではDeveloper ID署名と公証、
Windowsではコード署名を整えてから一般公開します。Macの署名IDは `KEMOMICHI_CODESIGN_IDENTITY` で指定できます。
同梱する動画ツール等の配布条件は [ライセンス確認](license-audit.md) を参照してください。
