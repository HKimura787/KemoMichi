# KemoMichi（獣道）

Timelapse2 互換の、クロスプラットフォーム対応カメラトラップ画像解析アプリ。

- Windows / macOS / Linux で動作
- サーバに置いてブラウザから利用可能
- Timelapse2 のプロジェクトファイル（`.tdb` / `.ddb`）をそのまま開いて編集・保存
- 種選択パレット、色味調整、REST 法の補助線とフレーム単位の滞在時間計測

## すぐ試す

```bash
pip install -e .
kemo demo ~/kemomichi-demo
kemo serve ~/kemomichi-demo/TimelapseData.ddb
```

詳しくは [docs/mvp.md](docs/mvp.md)。

## 文書

- 設計計画: [docs/design-plan.md](docs/design-plan.md)
- デザインシステム: [docs/design-system.md](docs/design-system.md)
- Timelapse2 ファイル形式仕様: [docs/spec/timelapse-format.md](docs/spec/timelapse-format.md)
- MVP の使い方: [docs/mvp.md](docs/mvp.md)

ライセンス: MIT（[LICENSE](LICENSE)）。UI の色・書体はデジタル庁デザインシステムのデザイントークン
（`@digital-go-jp/design-tokens`、MIT ライセンス、© デジタル庁）を使用しています。

※ Timelapse は Saul Greenberg / University of Calgary のソフトウェアです。本プロジェクトは
Timelapse のコードを使用しない独立した実装で、本家とは関係ありません。
