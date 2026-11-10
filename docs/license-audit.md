# 依存ライブラリの確認（2026-11-10）

NReco.VideoConverter と SixLabors.ImageSharp は、KemoMichi では使用していません。
現在の Python / npm の依存関係、実装中のソース、Macアプリのファイル一覧を確認しました。
Timelapse2 のファイル形式への対応と、本家で使用しているライブラリの利用は別の話です。

| 処理 | KemoMichi の実装 | 確認事項 |
|---|---|---|
| 画像の読み込み・プレビュー | Pillow | MIT-CMU。配布物へライセンス文を収録 |
| 動画解析・変換 | FFmpeg / ffprobe を直接実行 | ビルド構成に応じた LGPL / GPL の条件を確認 |
| ddb / tdb | Python標準の sqlite3 | NReco / ImageSharp は使用しない |
| Web画面 | React、TanStack Virtual、デジタル庁デザイントークン | 各依存のライセンス表記を保持 |
| 補助アプリ | Python、Tk、PyInstaller | 配布物に必要なライセンス文を収録 |

## 確認方法

```sh
uv run python tools/license_audit.py --bundle dist/KemoMichi.app --output build/dependency-audit.json
```

Python / npm のロックファイル、ソース中の完全なライブラリ名と、同梱ファイル名を照合します。
指定された2ライブラリへの参照を検出した場合は失敗します。
`tools/package_desktop.py` もこの検査を実行し、依存一覧と FFmpeg のバージョン・ビルド構成を同梱します。
この検査は名前・依存関係の技術的な照合であり、全ライブラリの法的適合性を保証するものではありません。

## 指定されたライブラリの条件

- [NReco公式FAQ](https://www.nrecosite.com/video_converter_net.aspx): 利用条件は単純な「非商用限定」とは異なり、再配布・SaaS・複数配置等の条件で商用ライセンスが必要とされています。KemoMichi はこのライブラリを使用していません。
- [Six Labors公式](https://sixlabors.com/pricing/): 商用ライセンスとCommunityライセンスの対象条件があります。本家Timelapse向けの許諾をKemoMichiへ引き継げるとは扱いません。KemoMichi はこのライブラリを使用していません。
- [Pillow公式ライセンス](https://pillow.readthedocs.io/en/stable/about.html#license): MIT-CMU。

## FFmpeg同梱版の公開配布

今回このMacで使用した FFmpeg 9.0.2 のビルド構成には `--enable-gpl`、libx264、libx265 が含まれ、
`--enable-nonfree` は含まれません。**「FFmpegなら常にLGPL」として配布しません。**
また、GPLと「非商用限定」は同じ意味ではありません。

[FFmpeg公式のライセンス説明](https://ffmpeg.org/legal.html)に従い、公開配布するバイナリに対応した
ライセンス文、対応ソース、依存する外部ライブラリ、ビルド手順を確認・用意する必要があります。
ビルドスクリプトが収録するバージョン・構成情報とライセンス一覧だけで、この作業が完了したとは扱いません。
現在作成するアプリは署名・公証と配布条件の確認前の試用ビルドです。
