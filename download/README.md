# KemoMichi ダウンロード

自分のPCに合うフォルダを開き、配布ファイルを選んでください。
Python・FFmpegの追加インストールやサーバー起動の操作は不要です。

| 使うPC | 開くフォルダ | ファイル |
| --- | --- | --- |
| Mac（M1・M2・M3などのApple Silicon） | [mac/apple-silicon](mac/apple-silicon/) | `KemoMichi-macOS-arm64.dmg` |
| Mac（Intel） | [mac/intel](mac/intel/) | `KemoMichi-macOS-x86_64.dmg` |
| Windows（x64） | [windows](windows/) | `KemoMichi-Windows-x86_64-setup.exe` |

この開発用PCではApple Silicon用DMGを配置済みです。
Intel Mac版・Windows版はビルドと動作確認待ちです。
各フォルダに案内だけがあり、上記のファイルがない場合は、まだその版を入手できません。

## 入手方法

- このフォルダをPCで開いている場合：対象のDMGまたはEXEをダブルクリックします。
- 配布者からフォルダやZIPを受け取った場合：PCに保存し、ZIPなら全体を展開してから対象ファイルを開きます。
- GitHubで閲覧している場合：ここには案内を保存しています。インストーラーはGitへ登録せず、
  ビルド後にGitHub ReleasesまたはActions成果物で共有します。公開前は配布者から受け取ってください。
  「Code → Download ZIP」にはインストーラーは含まれません。

試用版はMacのDeveloper ID署名・公証、Windowsのコード署名が未完了です。
起動を拒否された場合は、表示されたメッセージを開発者へ知らせてください。

インストール後はKemoMichiを開くとブラウザに作業画面が表示されます。
インストール手順は、上の表から開ける各OSフォルダのREADMEにまとめています。

`SHA256SUMS.txt` は配布ファイルの照合用です。起動する必要はありません。
