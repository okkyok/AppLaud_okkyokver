ロードマップの順番

1.  **`transcribe_summarize.py` (Python):**
    *   指定された音声ファイルパスを引数として受け取る。
    *   Gemini APIを使用して音声ファイルを文字起こしする。
    *   文字起こし結果と指定されたプロンプトに基づき、Gemini APIを使用して要約する。
    *   要約結果をMarkdown形式で指定されたフォルダに保存する (ファイル名には日付プレフィックスを付与)。
    *   処理結果 (元のファイル名、出力Markdown名、日時、ステータス) を指定されたJSONLファイルに追記する。
2.  **`file_mover.sh` (zsh):**
    *   設定ファイル (`config.sh`) を読み込む。
    *   マウントされたUSBデバイス内から、設定された拡張子の音声ファイルを検索する。
    *   処理済み記録ファイル (JSONL) を参照し、未処理の音声ファイルのみを対象とする。
    *   未処理の音声ファイルをローカルの指定ディレクトリに移動 (`mv`) する。
    *   移動が成功した各ファイルに対して `transcribe_summarize.py` を呼び出す (引数: 音声ファイルパス、Markdown出力先フォルダパス、要約プロンプトファイルパス、処理済み記録ファイルパス)。
3.  **`launchd` 設定 (macOS):**
    *   指定されたUSBボイスレコーダー (ボリューム名で識別) がMacにマウントされたことを検知する。
    *   マウント検知時に `file_mover.sh` スクリプトを、マウントされたデバイスのパスを引数として実行する。
4.  **設定ファイル (`config.sh`):**
    *   `RECORDER_NAME`: 監視対象のボイスレコーダーのボリューム名。
    *   `AUDIO_DEST_DIR`: 音声ファイルの移動先ローカルフォルダパス。
    *   `MARKDOWN_OUTPUT_DIR`: Markdownファイルの出力先フォルダパス。
    *   `PYTHON_SCRIPT_PATH`: `transcribe_summarize.py` のフルパス。
    *   `SUMMARY_PROMPT_FILE_PATH`: 要約プロンプトファイルのパス。
    *   `PROCESSED_LOG_FILE`: 処理済みファイル情報を記録するJSONLファイルのパス。
    *   `TARGET_EXTENSIONS`: 処理対象の拡張子。
5.  **要約プロンプトファイル (`prompt/summary_prompt.txt`):**
    *   Gemini APIに渡す要約指示のテンプレート。文字起こし結果を埋め込むプレースホルダーを含む。

**開発順序案:**

1.  `transcribe_summarize.py` の実装。
2.  `file_mover.sh` の実装。
3.  `config.sh` の作成と設定。
4.  `prompt/summary_prompt.txt` の作成。
5.  `launchd` の設定。
6.  全体テストとデバッグ。

## 開発タスクチェックリスト

### 1. Pythonスクリプト (`script/transcribe_summarize.py`)
- [x] 引数（音声ファイルパス、Markdown出力先フォルダパス、要約プロンプトファイルパス、処理済み記録ファイルパス）の受け取り処理を実装
- [x] Gemini API接続設定 (APIキーは環境変数 `GOOGLE_API_KEY` から読み込み)
- [x] 音声ファイルのGoogle Cloudへのアップロード処理 (Gemini API経由)
- [x] Gemini APIへの文字起こしリクエスト処理
- [x] 巨大ファイルの分割処理とチャンク毎の文字起こし、結果結合処理
- [x] 要約プロンプトファイルの読み込み処理
- [x] Gemini APIへの要約リクエスト処理（文字起こし結果とプロンプトを使用）
- [x] 要約結果のMarkdownファイル生成・保存処理
    - [x] ファイル名に日付プレフィックス (YYYYMMDD_) を付与
- [x] 処理記録 (JSONL形式) の追記処理 (`PROCESSED_LOG_FILE_PATH` で指定されたファイルへ)
    - [x] 記録項目: `source_audio`, `output_markdown`, `processed_at`, `status`

### 2. シェルスクリプト (`script/file_mover.sh`)
- [x] 設定ファイル (`script/config.sh`) 読み込み処理
- [x] マウントされたUSBデバイスパスを引数として受け取る処理
- [x] USBデバイス内の音声ファイル検索処理 (`TARGET_EXTENSIONS` で指定された拡張子)
- [x] 処理済み記録ファイル (`PROCESSED_LOG_FILE`) の読み込みと、処理済みファイルかどうかの判定ロジック
- [x] 未処理音声ファイルのローカル指定ディレクトリ (`AUDIO_DEST_DIR`) への移動 (`mv`) 処理
- [x] `transcribe_summarize.py` の呼び出し処理
    - [x] 必要な引数（音声ファイルパス、`MARKDOWN_OUTPUT_DIR`、`SUMMARY_PROMPT_FILE_PATH`、`PROCESSED_LOG_FILE`）を渡す

### 3. 設定ファイル (`script/config.sh`)
- [x] `RECORDER_NAME` の設定
- [x] `AUDIO_DEST_DIR` の設定 (例: `./debug/processed_audio`)
- [x] `MARKDOWN_OUTPUT_DIR` の設定 (例: `./debug/summaries`)
- [x] `PYTHON_SCRIPT_PATH` の設定 (例: `./script/transcribe_summarize.py`)
- [x] `SUMMARY_PROMPT_FILE_PATH` の設定 (例: `./prompt/summary_prompt.txt`)
- [x] `PROCESSED_LOG_FILE` の設定 (例: `./debug/processed_log.jsonl`)
- [x] `TARGET_EXTENSIONS` の設定 (例: `"-name '*.wav' -o -name '*.mp3' -o -name '*.m4a'"`)

### 4. 要約プロンプト (`prompt/summary_prompt.txt`)
- [x] Gemini APIに投入する要約指示テンプレートの作成
    - [x] 文字起こし結果を挿入するプレースホルダー (例: `{{TRANSCRIPTION}}`) を定義
    - [x] 出力形式 (Markdown)、要約のポイントなどを指示

### 5. `launchd` 設定 (macOS)
- [x] `launchd`エージェントのplistファイル作成
- [x] plistファイルに、指定ボリューム (`RECORDER_NAME`) マウント時に `file_mover.sh` を実行するよう設定
    - [x] `file_mover.sh` へマウントパスを引数として渡す設定 (plistに記述、動作確認と場合によりスクリプト修正が必要)

### 6. その他
- [x] `.gitignore` に `debug/processed_audio/`、`debug/summaries/`, `debug/processed_log.jsonl` などを追加 (必要に応じて)
- [ ] `README.md` の更新 (実行方法、設定方法など)
- [ ] 全体テストとデバッグ
    - [ ] ダミーUSBデバイス (`debug/dummy_usb`) を使用したテスト
    - [ ] 各種音声ファイル形式 (.wav, .mp3, .m4a) でのテスト
    - [ ] 処理済みファイルのスキップ機能テスト
    - [ ] エラーハンドリングテスト (APIエラー、ファイル移動エラー等)

- [x] zshのフルディスクアクセスの許可