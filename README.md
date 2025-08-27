# AIボイスレコーダー化アプリ (AppLaud)

## 概要

AppLaudは、USBボイスレコーダーをMacに接続した際に、音声ファイルを自動的に取り込み、文字起こしと要約を行うアプリケーションです。生成されたテキストはMarkdownファイルとして保存され、日々の音声記録の管理と活用を効率化します。

## 主な機能

*   **自動ファイル取り込み:** 指定されたUSBボイスレコーダーの接続を検知し、音声ファイル（wav, mp3, m4a）を自動でローカルフォルダに移動します。
*   **AIによる文字起こしと要約:** Gemini APIを利用して、音声ファイルの文字起こしと要約を高精度で行います。
*   **Markdown形式での保存:** 要約結果をMarkdownファイルとして、整理された形式で保存します。ファイル名は日付と内容に基づき自動生成されます。
*   **長時間音声対応:** 20分を超える音声ファイルは自動的に分割処理され、APIの制限に対応しつつ、途切れることのない文字起こし結果を得られます。

## システム構成要素

*   **`file_mover.sh` (zshスクリプト):** USBデバイスの監視、音声ファイルの検出と移動、Pythonスクリプトの呼び出しを行います。全ての検出された音声ファイルを毎回必ず移動し、Pythonスクリプトを呼び出します。
*   **`transcribe_summarize.py` (Pythonスクリプト):** Gemini APIとの連携、音声ファイルの文字起こし、要約、Markdownファイル生成、処理記録を行います。
*   **`config.sh` (設定ファイル):** ボイスレコーダーの名称、各種フォルダパス、処理対象の拡張子などを設定します。
*   **`launchd` (macOS):** USBデバイス接続をトリガーとして `file_mover.sh` を実行します。 (ユーザーによる設定が必要です)

## セットアップ

1.  **リポジトリのクローン:**
    ```bash
    git clone https://github.com/your-username/AppLaud.git
    cd AppLaud
    ```

2.  **設定ファイルの作成:**
    ```bash
    # テンプレートから設定ファイルを作成
    cp script/config.sh.template script/config.sh
    
    # 個人情報プロンプトファイルの作成
    cp prompt/speaker_info.txt.template prompt/speaker_info.txt
    cp prompt/domain_context.txt.template prompt/domain_context.txt
    ```
    
3.  **設定ファイルの編集:**
    *   `script/config.sh` を開き、お使いの環境に合わせて以下の項目を設定してください：
        *   `GOOGLE_API_KEY`: Google Gemini APIキー（必須）
        *   `RECORDER_NAME`: 監視対象のボイスレコーダーのボリューム名
        *   `AUDIO_DEST_DIR`: 音声ファイルの移動先ローカルフォルダ
        *   `MARKDOWN_OUTPUT_DIR`: Markdown要約ファイルの出力先ローカルフォルダ
        *   `OBSIDIAN_DAILY_NOTES_DIR`: Obsidianデイリーノートのディレクトリ（使用する場合）
        *   その他、必要に応じてパスやフォーマットを調整してください

4.  **個人情報プロンプトファイルの編集:**
    *   `prompt/speaker_info.txt` を開き、あなたの情報に合わせて以下を設定してください：
        *   話者の基本情報（名前、性別など）
        *   よく登場する人物の名前や関係性
        *   音声認識精度向上のための情報
    *   `prompt/domain_context.txt` を開き、以下を設定してください：
        *   よく話題になる分野や専門用語
        *   組織名や地名などの固有名詞
        *   文脈理解に役立つ背景情報

5.  **依存ライブラリのインストール:**
    ```bash
    # 仮想環境の作成（推奨）
    python3 -m venv venv
    source venv/bin/activate
    
    # 必要なライブラリのインストール
    pip install -r requirements.txt
    ```

6.  **APIキーの設定:**
    *   Google CloudでGemini APIを有効にし、APIキーを取得してください
    *   取得したAPIキーを `script/config.sh` の `GOOGLE_API_KEY` に設定してください：
        ```bash
        export GOOGLE_API_KEY="your_actual_api_key_here"
        ```
    *   **重要**: `config.sh` は `.gitignore` に含まれているため、APIキーがGitHubにプッシュされることはありません
7.  **`launchd` エージェントの設定 (macOSユーザー向け):**
    *   USBデバイス接続時に `file_mover.sh` を自動実行するために、`launchd` のエージェントを設定する必要があります。
    *   本リポジトリの `script/com.example.applaud.filemover.plist.template` は、このための設定ファイルテンプレートです。
    *   **重要: 設定はすべて `script/config.sh` で一元管理してください。APIキーやパスは `.plist` には直接書かず、`config.sh` にまとめて記述します。**
    *   `.plist` の `ProgramArguments` で `--config /ABSOLUTE/PATH/TO/YOUR/AppLaud/script/config.sh` を渡すことで、設定ファイルの場所を明示的に指定できます。
    *   **file_mover.sh 側の設定ファイル読込例:**
        ```zsh
        #!/bin/zsh
        # 設定ファイルのパスを引数で受け取る
        if [[ "$1" == "--config" && -n "$2" ]]; then
          source "$2"
          shift 2
        else
          source "./config.sh"
        fi
        # ...以降、環境変数として設定値が利用可能...
        ```
    *   **手順:**
        1.  テンプレートファイルを `~/Library/LaunchAgents/` ディレクトリにコピーします。
            ```bash
            cp script/com.example.applaud.filemover.plist.template ~/Library/LaunchAgents/com.example.applaud.filemover.plist
            ```
        2.  コピーした `~/Library/LaunchAgents/com.example.applaud.filemover.plist` をテキストエディタで開きます。
        3.  ファイル内の以下のプレースホルダーを、ご自身の環境に合わせて修正してください。
            *   `/ABSOLUTE/PATH/TO/YOUR/AppLaud/script/file_mover.sh`: `file_mover.sh` スクリプトへの絶対パス。
            *   `/ABSOLUTE/PATH/TO/YOUR/AppLaud/script/config.sh`: `config.sh` への絶対パス。
            *   `/Volumes/YOUR_RECORDER_NAME`: `WatchPaths` 内。`config.sh` の `RECORDER_NAME` で設定したボイスレコーダーのボリューム名（例: `/Volumes/IC RECORDER`）。
            *   ログパス (`StandardOutPath`, `StandardErrorPath`) も必要に応じて変更してください（デフォルトは `/tmp/` 以下に出力されます）。
        4.  編集後、`launchd` エージェントを読み込みます。
            ```bash
            launchctl load ~/Library/LaunchAgents/com.example.applaud.filemover.plist
            ```
        5.  これで、指定したUSBデバイスがマウントされると自動的に `file_mover.sh` が実行されるようになります。
    *   **動作確認とログ:**
        *   ログは `.plist` ファイル内で指定したパス（デフォルトでは `/tmp/com.example.applaud.filemover.stdout.log` および `stderr.log`）に出力されます。問題が発生した場合はこれらのログファイルを確認してください。
        *   Console.app (`アプリケーション > ユーティリティ > コンソール`) でも `launchd` やスクリプトからのログを確認できる場合があります。
        *   **tailコマンドによるリアルタイム監視例:**
            ```bash
            tail -f /tmp/com.example.applaud.filemover.stdout.log
            tail -f /tmp/com.example.applaud.filemover.stderr.log
            ```
        *   ログファイルの内容をリアルタイムで確認したい場合に便利です。
    *   **アンロード (停止):**
        *   `launchd` エージェントの動作を停止（アンロード）するには、以下のコマンドを実行します。
            ```bash
            launchctl unload ~/Library/LaunchAgents/com.example.applaud.filemover.plist
            ```
        *   アンロード後、再度有効にするには `launchctl load` を実行します。`.plist` ファイルを修正した場合は、アンロードしてからロードし直すことで変更が反映されます。
6.  **動作確認用ディレクトリの作成 (任意):**
    *   `debug/dummy_usb/` にサンプル音声ファイルを置くことで、USB接続なしに動作をテストできます (別途 `file_mover.sh` の修正または手動実行が必要)。
    *   `debug/processed_audio/` と `debug/summaries/` は、処理された音声ファイルと生成されたMarkdownファイルが保存される場所のデフォルト例です。`.gitignore` にも含まれています。

## 使い方

1.  上記セットアップを完了します。
2.  設定したボイスレコーダーをMacにUSB接続します。
3.  自動的に処理が開始され、`config.sh` で指定した `MARKDOWN_OUTPUT_DIR` に要約Markdownファイルが生成されます。
4.  処理済みの音声ファイルは `AUDIO_DEST_DIR` に移動されます。
5.  処理のログは `PROCESSED_LOG_FILE` (デフォルト: `debug/processed_log.jsonl`) に記録されます。

## セキュリティに関する注意事項

*   **APIキーの管理**: `script/config.sh` にはAPIキーなどの機密情報が含まれます。このファイルは `.gitignore` で除外されており、GitHubにプッシュされません
*   **設定ファイルテンプレート**: `script/config.sh.template` が公開用テンプレートとして提供されています。実際の設定値は含まれていません
*   **初回セットアップ**: リポジトリをクローンした後は、必ず `config.sh.template` をコピーして `config.sh` を作成し、適切な設定値を入力してください

## その他の注意事項

*   本アプリケーションはmacOSでの使用を前提としています。特に `launchd` を利用した自動実行部分はmacOS特有の機能です
*   長時間音声の処理には時間がかかる場合があります

## ファイル名フォーマット設定

議事録ファイルの命名規則は `config.sh` で設定可能です：

```bash
# 利用可能なプレースホルダー:
#   {date} - 録音日付（YYYYMMDD形式）
#   {title} - AIが生成したタイトル
export MARKDOWN_FILENAME_FORMAT="{date}_{title}"
```

**フォーマット例:**
- `"{date}_{title}"` → `20250827_会議議事録.md`
- `"{title}_{date}"` → `会議議事録_20250827.md`
- `"{date}-{title}"` → `20250827-会議議事録.md`
- `"{title}"` → `会議議事録.md`

## 今後の改善点 (TODO)

*   Windows/Linuxへの対応
*   より詳細なエラーハンドリングと通知機能
*   Web UIによる設定や操作インターフェース
*   `launchd.plist` の設定を簡略化する補助スクリプト

詳細は `document/project.md` を参照してください。
