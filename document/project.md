## AIボイスレコーダー化アプリ 仕様書

### 1. 概要

本システムは、指定されたUSBボイスレコーダーがMacに接続された際に、自動的に音声ファイル（wav, mp3, m4a）をローカルの指定フォルダに移動し、Gemini APIを利用して文字起こしと要約を行い、結果をMarkdownファイルとして指定されたフォルダに出力するシンプルなアプリケーションです。

### 2. システム構成

```mermaid
graph TD
    A[USBボイスレコーダー接続] --> B{macOS: デバイス検出};
    B -- マウント情報 --> C[zshスクリプト: file_mover.sh];
    C -- 音声ファイルパス --> D[Pythonスクリプト: transcribe_summarize.py];
    C -- 検出 & 移動 --> E[ローカル音声ファイル保存フォルダ];
    D -- Gemini API --> F[Google Cloud];
    F -- 文字起こし/要約結果 --> D;
    D -- Markdown生成 --> G[ローカルMarkdown出力フォルダ];
    C --> H{処理済み記録 (JSONL)};
    D --> H;
```

1.  **デバイス検出 (macOS):** `launchd`などを利用し、指定されたボリューム名を持つUSBデバイスのマウントを監視します。
2.  **ファイル移動 (zsh):** `file_mover.sh`がトリガーされ、マウントされたデバイスから指定された音声ファイル（wav, mp3, m4a）をローカルの指定フォルダに移動します。
3.  **文字起こし・要約 (Python):** `file_mover.sh`が移動した各音声ファイルに対して、`transcribe_summarize.py`を呼び出します。このPythonスクリプトはGemini APIと通信し、文字起こしと要約を実行します。
4.  **出力 (Python):** `transcribe_summarize.py`は、要約結果をMarkdown形式でローカルの指定フォルダに保存します。

### 3. 主要機能

#### 3.1. デバイス接続トリガーとファイル移動 (zsh: `file_mover.sh`)

* **トリガー:** 指定されたUSBボイスレコーダー（ボリューム名で識別）がMacにマウントされた時。(`launchd`等で設定)
* **入力:**
    * マウントされたデバイスのパス。
    * 設定ファイル（監視対象のレコーダー名、移動先フォルダパス、処理対象拡張子、処理済み記録ファイルパス）。
* **処理:**
    1.  設定ファイルから処理済み記録ファイルパス (`PROCESSED_LOG_FILE`) を読み込みます。
    2.  マウントされたデバイス内を探索し、指定された拡張子（`.wav`, `.mp3`, `.m4a`）を持つ音声ファイルを検出します。
    3.  検出された各音声ファイルについて、処理済み記録ファイル（JSONL）を参照し、既に処理済み（同じファイル名が記録されている）か確認します。
        * 処理済みの場合はスキップし、次のファイルに進みます。
    4.  未処理の場合、検出された音声ファイルを、設定ファイルで指定されたローカルの移動先フォルダに`mv`コマンドで移動します。
    5.  移動が成功した各ファイルに対して、`transcribe_summarize.py`スクリプトを呼び出し、ファイルパス、Markdown出力先フォルダパス、要約プロンプトファイルパス、処理済み記録ファイルパスを引数として渡します。
    * 例: `python3 /path/to/transcribe_summarize.py "/path/to/moved/audio/file.m4a" "/path/to/markdown_output/" "/path/to/prompt.txt" "/path/to/processed_log.jsonl"`
* **設定項目:**
    * `RECORDER_NAME`: 監視対象のボイスレコーダーのボリューム名 (例: "IC RECORDER")
    * `AUDIO_DEST_DIR`: 音声ファイルの移動先ローカルフォルダパス (例: "audio/")
    * `PYTHON_SCRIPT_PATH`: `transcribe_summarize.py`のフルパス (例: "script/transcribe_summarize.py")
    * `OUTPUT_DIR`: Markdownファイルの出力先フォルダパス (例: "debug_outputs/summaries/")
    * `SUMMARY_PROMPT_FILE`: 要約プロンプトが記述されたテキストファイルのパス (例: `prompt/summary_prompt.txt`)
    * `PROCESSED_LOG_FILE`: 処理済みファイル情報を記録するJSONLファイルのパス (例: `debug_outputs/processed_log.jsonl`)

#### 3.2. 文字起こしと要約 (Python: `transcribe_summarize.py`)

* **入力:**
    * zshスクリプトから渡される音声ファイルのフルパス。
    * 環境変数または設定ファイルから読み込むGemini APIキー。
    * zshスクリプトから渡されるMarkdownファイルの出力先フォルダパス (例: `debug_outputs/summaries/`)。
    * 要約プロンプトを記述したテキストファイルのパス（設定ファイル経由で渡される）。
    * zshスクリプトから渡される処理済み記録ファイル(JSONL)のパス。
* **使用モデル:** Gemini (`gemini-2.0-flash`を推奨。Audio API対応のため)
* **処理:**
    1.  Google Generative AI Python SDK (`google-generativeai`) を使用してGemini APIに接続します。(環境変数設定済み 'GOOGLE_API_KEY')
    2.  **音声ファイルの長さ確認と分割:**
        *   まず、受け取った音声ファイルの長さを確認します（`pydub`などのライブラリを使用）。
        *   **20分を超える場合:**
            *   元の音声ファイル名に基づいて一意な名前を持つ一時ディレクトリを作成します (例: `temp/original_audio_filenamestem_chunks/`)。
            *   `pydub` ライブラリを使用し、音声ファイルを20分以下のできるだけ均等な長さのチャンクに分割します。
            *   分割時、隣接するチャンク間で1分間のオーバーラップ部分を作成します。例えば、最初のチャンクが0分から15分の場合、次のチャンクは14分から開始するようにします。
            *   分割された各音声チャンクを、作成した一時ディレクトリ内にファイルとして保存します (例: `chunk_1.wav`)。
        *   **20分以下の場合:** 分割処理は行いません。一時ディレクトリの作成も不要です。
    3.  **ファイルアップロードと文字起こし:**
        *   **分割した場合:**
            *   一時ディレクトリ内の各音声チャンクファイル (例: `chunk_1.wav`) について順に処理します。
            *   まず、対応する文字起こし済みテキストファイル (例: `chunk_1_transcription.txt`) が一時ディレクトリ内に既に存在するか確認します。
                *   **存在する場合:** API呼び出しをスキップし、このファイルから文字起こし結果を読み込みます。
                *   **存在しない場合:** 当該音声チャンクファイルをGoogle Cloud (Gemini API経由) にアップロードします。アップロード後、Gemini APIに文字起こしをリクエストします。成功した場合、得られた文字起こしテキストを一時ディレクトリ内に対応する名前のテキストファイル (例: `chunk_1_transcription.txt`) として保存します。APIにアップロードしたファイルは処理後にAPI側で削除されます。
        *   **分割しない場合:** 受け取った単一の音声ファイルをGoogle Cloud (Gemini API経由) にアップロードし、文字起こしをリクエストします。処理完了後、アップロードしたファイルはAPI側で削除されます。
        *   文字起こしプロンプト例: 「この音声ファイルを文字起こししてください。」
    4.  **結合（分割した場合）:** 一時ディレクトリ内の各チャンクの文字起こしテキストファイル (例: `chunk_1_transcription.txt`, `chunk_2_transcription.txt`, ...) から内容を読み込み、オーバーラップ部分を適切に処理しながら結合し、一つの連続したテキストにします。
    5.  **要約:**
        1.  設定されたパスから要約プロンプトファイルを読み込みます。
        2.  読み込んだプロンプトと全体の文字起こしテキストを元に、Gemini APIに要約をリクエストします。
        * プロンプト例（ファイル内容）: 「以下のテキストをMarkdown形式で要約してください:

{{ここに文字起こしテキスト全体が挿入される}}

要約は以下の点に注意してください:
- 重要なポイントを箇条書きにする
- 各ポイントは簡潔に」
    6.  **Markdown出力:**
        1. 生成された要約テキストと、ファイル名生成用のプロンプト（例：「以下の要約内容に最も適した、簡潔で分かりやすいファイル名を提案してください。ファイル名はアルファベット、数字、アンダースコア、ハイフンのみを使用し、最大50文字程度で、拡張子は含めないでください。」）を元に、Gemini APIに再度リクエストを送信し、ファイル名の候補を取得します。
        2. APIから取得したファイル名候補に対してサニタイズ処理（ファイル名として不適切な文字の除去や置換、長さ制限の適用など）を行います。
        3. 最終的なファイル名を `YYYYMMDD_<サニタイズされたAPI提案ファイル名>.md` という形式で決定します。
        4. このファイル名で、指定された出力先フォルダに要約内容をMarkdown形式で保存します。
    7.  **処理記録:** Markdownファイルの保存に成功した場合、処理した元の音声ファイル名、生成されたMarkdownファイル名、処理日時（例: ISO 8601形式）、および処理ステータス（例: "success"）をJSONL形式で指定された処理済み記録ファイルに追記します。
        * 例: `{"source_audio": "original_audio.m4a", "output_markdown": "original_audio.md", "processed_at": "2023-10-27T10:30:00Z", "status": "success"}`
    8.  **クリーンアップ (分割した場合のみ):** スクリプト全体の処理が全て成功した場合に限り、手順2で作成した一時ディレクトリと、その中に含まれるすべてのファイル（音声チャンクファイル、文字起こしテキストファイル）を削除します。処理中にエラーが発生した場合は、これらの一時ファイルは保持され、次回の実行時に再利用されます。
* **設定項目:**
    * `GOOGLE_API_KEY`: Gemini APIキー (環境変数 `GOOGLE_API_KEY` から読み込むことを推奨)
    * `MARKDOWN_OUTPUT_DIR`: Markdownファイルの出力先フォルダパス (引数で受け取る、例: `debug_outputs/summaries/`)
    * `SUMMARY_PROMPT_FILE`: 要約プロンプトが記述されたテキストファイルのパス (引数で受け取る、例: `prompt/summary_prompt.txt`)
    * `PROCESSED_LOG_FILE_PATH`: 処理済み記録を追記するJSONLファイルのパス (引数で受け取る)
* **依存ライブラリ:**
    * `google-generativeai`
    * `pydub`

### 4. 設定ファイル例 (`config.sh`)

zshスクリプト (`file_mover.sh`) が読み込む設定ファイルの例です。

```zsh
#!/bin/zsh

# --- 設定 ---

# 監視するボイスレコーダーのボリューム名（Macでマウントされたときの名前）
RECORDER_NAME="IC RECORDER"

# 音声ファイルを移動する先のローカルディレクトリ
AUDIO_DEST_DIR="./audio"

# Markdown要約ファイルを出力する先のローカルディレクトリ
MARKDOWN_OUTPUT_DIR="./debug_outputs/summaries"

# 実行するPythonスクリプトのフルパス
PYTHON_SCRIPT_PATH="./script/transcribe_summarize.py"

# 要約時に使用するプロンプトファイルのパス
SUMMARY_PROMPT_FILE_PATH="./prompt/summary_prompt.txt"

# 処理済みファイルを記録するJSONLファイルのパス
PROCESSED_LOG_FILE="./debug_outputs/processed_log.jsonl"

# 処理対象の拡張子 (スペース区切り) - findコマンドで使用
TARGET_EXTENSIONS="-name '*.wav' -o -name '*.mp3' -o -name '*.m4a'"

# --- ここまで設定 ---
```

### 5. 実装上の注意点

* **APIキー管理:** `GOOGLE_API_KEY` は環境変数として設定するか、安全な方法で管理してください。スクリプト内に直接書き込まないでください。
* **エラーハンドリング:** 各ステップ（ファイル移動、API呼び出し、ファイル書き込み）で基本的なエラーハンドリング（失敗時のログ出力など）を追加することが望ましいです。
* **依存関係:** Pythonスクリプト実行環境には、必要なライブラリ (`google-generativeai` 等) がインストールされている必要があります。
* `launchd`設定:** macOSの`launchd`エージェントを設定し、指定したボリューム名がマウントされたときに`file_mover.sh`が実行されるように構成する必要があります。
* **ファイルパス:** スクリプト内でファイルパスを扱う際は、スペース等を含む可能性を考慮し、適切にクォーテーション(`"`)で囲んでください。
* **冪等性:** `file_mover.sh`は、処理済み記録ファイル（JSONL形式）を参照し、各音声ファイルが既に処理されていないかを確認します。記録されている場合は処理をスキップすることで、同じファイルが誤って複数回処理されることを防ぎます。`transcribe_summarize.py`は処理完了後、このJSONLファイルにエントリを追加します。
    * JSONLエントリ例: `{"source_audio": "filename.m4a", "output_markdown": "filename.md", "processed_at": "YYYY-MM-DDTHH:MM:SSZ", "status": "success"}`
* **JSONLファイル:** 処理済み記録ファイルは、1行に1つのJSONオブジェクトが記録されるJSON Lines形式で保存されます。これにより、追記が容易になります。

### 6. ワークフロー

1.  ユーザーが指定されたボイスレコーダーをMacにUSB接続します。
2.  macOSがデバイスを検出し、ボリュームをマウントします。
3.  `launchd`がマウントを検知し、`file_mover.sh`をマウントパスを引数に実行します。
4.  `file_mover.sh`が設定ファイルから処理済み記録ファイルパスを読み込みます。
5.  `file_mover.sh`がレコーダー内の音声ファイル（wav, mp3, m4a）を探索します。
6.  各音声ファイルについて、`file_mover.sh`は処理済み記録ファイルを参照し、未処理の場合のみファイルをローカルの`AUDIO_DEST_DIR`に移動します。処理済みの場合はスキップします。
7.  移動した各未処理ファイルについて、`file_mover.sh`が`transcribe_summarize.py`を呼び出します（引数: 音声ファイルパス、出力先フォルダパス、要約プロンプトファイルパス、処理済み記録ファイルパス）。
8.  `transcribe_summarize.py`が、指定されたプロンプトファイルを読み込みます。
9.  `transcribe_summarize.py`がGemini APIを使用して音声ファイルを文字起こしします。
10. `transcribe_summarize.py`が文字起こし結果と読み込んだプロンプトをGemini APIを使用してMarkdown形式で要約します。この際にファイル名も作成します．ファイル名には元の音声ファイルの生成された日付をYYYYMMDD_としてprefixに入れます．
11. `transcribe_summarize.py`が要約Markdownを指定された`MARKDOWN_OUTPUT_DIR`に保存します。
12. `transcribe_summarize.py`が処理結果（元のファイル名、出力Markdown名、日時、ステータス）を指定された処理済み記録ファイル（JSONL）に追記します。
13. （オプション）`file_mover.sh`は処理完了後、レコーダー上の元ファイルを削除するか、そのまま残すかを選択できます。（現在の仕様では`mv`なので移動元からは消えます）