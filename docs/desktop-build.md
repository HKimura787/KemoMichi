# 補助アプリのビルド

補助アプリはPython・操作画面・FFmpeg / ffprobeを同梱し、起動するとローカルサーバーとブラウザを開きます。
Mac版はMac、Windows版はWindowsで作成します。

```sh
uv sync --group desktop
cd web
npm ci
cd ..
uv run --group desktop python tools/package_desktop.py
```

ビルド時はTkが使えるPython、Node.js、FFmpeg / ffprobeが必要です。
Windowsのインストーラー作成にはInno Setup 6も必要です。
`KEMOMICHI_FFMPEG_DIR` でFFmpeg / ffprobeの実行ファイルがあるフォルダを指定できます。

生成した `.app` またはアプリ実行フォルダは `dist/`、DMG・セットアップEXE・ポータブルZIPは `dist/installers/` に保存します。
`--bundle-only` はアプリのみを作成し、`--skip-web-build` は既存のWebビルドを使用します。

PyInstaller・Inno Setupの定義とランチャーは、ビルド時に `build/desktop-resources/` へ生成します。
削除した `desktop/`・`download/` フォルダには依存しません。

GitHub Actionsの **Desktop builds** でもOS別にビルドと自己テストを実行し、インストーラーを成果物へ保存します。
Windowsでは起動ウィンドウの起動・終了も、ビルドしたEXEで確認します。
補助アプリの終了時には動画処理を停止し、作成途中のddbはロールバックします。
通常の編集内容は操作ごとに保存されます。終了に失敗した場合は理由と「終了を再試行」を表示し、詳細は起動ウィンドウからログフォルダを開いて確認できます。
署名・公証、Windows実機での画面操作、公開配布に必要な対応ソース等の準備は別途必要です。
[依存ライブラリの確認](license-audit.md) も参照してください。
