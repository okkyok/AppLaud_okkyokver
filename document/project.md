## AIボイスレコーダー化アプリ 仕様書

### 1. 概要

本システムは、指定されたUSBボイスレコーダーがMacに接続された際に、自動的に音声ファイル（wav, mp3, m4a）をローカルの指定フォルダに移動し、Gemini APIを利用して文字起こしと要約を行い、結果をMarkdownファイルとして指定されたフォルダに出力するアプリケーションです。実装はzshスクリプト（file_mover.sh）とPythonスクリプト（transcribe_summarize.py）で構成され、エラー耐性や冪等性、キャッシュ・一時ファイル管理など実用的な工夫が施されています。

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

#### 実装上のポイント
- **zshスクリプト（file_mover.sh）**
  - 柔軟な引数パース（--configとマウントパスの順不同対応）。
  - 設定ファイル（config.sh）から各種パス・拡張子・サブディレクトリ名などを読み込み。
  - マウントポイントやサブディレクトリの存在を最大30秒リトライで待機。
  - findコマンドで拡張子指定（TARGET_EXTENSIONS_ARRAY）をグループ化し、-inameで大文字小文字を区別せず検索。
  - 検索結果を配列に格納し、各ファイルごとに処理。
  - ログファイルや出力ディレクトリの存在確認・作成。
  - ファイル移動後、Pythonスクリプトを絶対パスで呼び出し、必要な引数を渡す。
  - エラー時は詳細なメッセージを出力し、findやmv、Python実行の失敗を検知。

- **Pythonスクリプト（transcribe_summarize.py）**
  - 20分超の音声は1分オーバーラップでチャンク分割し、各チャンクごとにAPIで文字起こし。
  - チャンクごとにキャッシュ（transcription.txt）を利用し、再実行時はAPI呼び出しを省略。
  - 20分以下の音声はそのままAPIにアップロードし、キャッシュも利用。
  - 文字起こし後、要約プロンプト（ファイルから読み込み）を使いGemini APIで要約。
  - 要約内容からAPIでファイル名案を生成し、サニタイズ（英小文字・数字・_・-のみ、最大50文字、空ならuntitled_summary）。
  - Markdownファイルは日付プレフィックス＋生成名で保存。重複時は_1, _2...を付与。
  - 全処理の成否・エラー内容をJSONLでログ記録。
  - 一時ディレクトリは成功時のみ削除、エラー時は残して再利用。

### 3. 主要機能

#### 3.1. デバイス接続トリガーとファイル移動 (zsh: file_mover.sh)

- **トリガー:** 指定USBボイスレコーダー（ボリューム名で識別）がMacにマウントされた時（launchd等で設定）。
- **入力:**
    - マウントパス
    - 設定ファイル（config.sh）
- **処理:**
    1. 設定ファイルから各種パス・拡張子・サブディレクトリ名を読み込み。
    2. 検索パス（例: /Volumes/RECORDER/RECORD）が利用可能になるまで最大30秒リトライ。
    3. マウント直後の安定化のため5秒待機。
    4. findコマンドで拡張子指定（TARGET_EXTENSIONS_ARRAY）をグループ化し、-inameで大文字小文字を区別せず検索。findの標準出力を配列に格納。
    5. 検出ファイルごとに、ローカル移動先ディレクトリにmvで移動。
    6. 各ファイルごとにPythonスクリプトを絶対パスで呼び出し、必要な引数（音声ファイルパス、Markdown出力先、要約プロンプトファイル、処理済み記録ファイル）を渡す。
    7. ログファイルや出力ディレクトリの存在確認・作成。
    8. エラー時は詳細なメッセージを出力し、findやmv、Python実行の失敗を検知。

- **設定項目:**
    - RECORDER_NAME: 監視対象ボリューム名
    - VOICE_FILES_SUBDIR: サブディレクトリ名
    - AUDIO_DEST_DIR: ローカル移動先
    - MARKDOWN_OUTPUT_DIR: Markdown出力先
    - PYTHON_SCRIPT_PATH: Pythonスクリプトパス
    - SUMMARY_PROMPT_FILE_PATH: 要約プロンプトファイル
    - PROCESSED_LOG_FILE: JSONLログファイル
    - TARGET_EXTENSIONS_ARRAY: 拡張子配列（find用）

#### 3.2. 文字起こしと要約 (Python: transcribe_summarize.py)

- **入力:**
    - 音声ファイルパス
    - MARKDOWN_OUTPUT_DIR
    - SUMMARY_PROMPT_FILE_PATH
    - PROCESSED_LOG_FILE_PATH
    - 環境変数GOOGLE_API_KEY
- **処理:**
    1. GOOGLE_API_KEYが未設定なら即エラー・ログ記録。
    2. 20分超の音声は1分オーバーラップでチャンク分割し、各チャンクごとにAPIで文字起こし。チャンクごとにキャッシュ（transcription.txt）を利用。
    3. 20分以下の音声はそのままAPIにアップロードし、キャッシュも利用。
    4. 文字起こし後、要約プロンプト（ファイルから読み込み）を使いGemini APIで要約。
    5. 要約内容からAPIでファイル名案を生成し、サニタイズ（英小文字・数字・_・-のみ、最大50文字、空ならuntitled_summary）。
    6. Markdownファイルは日付プレフィックス＋生成名で保存。重複時は_1, _2...を付与。
    7. 全処理の成否・エラー内容をJSONLでログ記録。
    8. 一時ディレクトリは成功時のみ削除、エラー時は残して再利用。

- **依存ライブラリ:**
    - google-generativeai
    - pydub

### 4. 設定ファイル例（config.sh）

```zsh
#!/bin/zsh
# --- 設定 ---
RECORDER_NAME="IC RECORDER"
VOICE_FILES_SUBDIR="RECORD"
AUDIO_DEST_DIR="./audio"
MARKDOWN_OUTPUT_DIR="./debug_outputs/summaries"
PYTHON_SCRIPT_PATH="./script/transcribe_summarize.py"
SUMMARY_PROMPT_FILE_PATH="./prompt/summary_prompt.txt"
PROCESSED_LOG_FILE="./debug_outputs/processed_log.jsonl"
TARGET_EXTENSIONS_ARRAY=(-iname '*.wav' -o -iname '*.mp3' -o -iname '*.m4a')
# --- ここまで設定 ---
```

### 5. 実装上の注意点

- **APIキー管理:** GOOGLE_API_KEYは環境変数で設定。未設定時は即エラー・ログ記録。
- **エラーハンドリング:** 各ステップで詳細なエラー出力・ログ記録。find/mv/Python/API/ファイル書き込み等の失敗を検知。
- **キャッシュ・一時ファイル:** チャンクごと・全体ごとにtranscription.txtをキャッシュ。エラー時は一時ディレクトリを残し、再利用可能。
- **ファイル名生成:** 要約内容からAPIでファイル名案を生成し、サニタイズ（英小文字・数字・_・-のみ、最大50文字、空ならuntitled_summary）。
- **冪等性:** file_mover.shは処理済み記録ファイルを参照し、同じファイルの重複処理を防止（※現状の実装では未処理判定は未実装。今後の拡張余地あり）。
- **パスの扱い:** すべてのパスはクォーテーションで囲み、スペース等に対応。
- **ディレクトリ作成:** ログ・出力・一時ディレクトリは必要に応じてmkdir -pで作成。

### 6. ワークフロー

1. ユーザーがUSBボイスレコーダーをMacに接続。
2. macOSがデバイスを検出し、ボリュームをマウント。
3. launchdがマウントを検知し、file_mover.shをマウントパスを引数に実行。
4. file_mover.shが設定ファイルから各種パス・拡張子・サブディレクトリ名を読み込み。
5. file_mover.shがレコーダー内の音声ファイル（wav, mp3, m4a）を探索。
6. 各音声ファイルをローカルAUDIO_DEST_DIRに移動。
7. 移動した各ファイルについて、file_mover.shがtranscribe_summarize.pyを呼び出し（引数: 音声ファイルパス、出力先、要約プロンプト、処理済み記録ファイル）。
8. transcribe_summarize.pyが要約プロンプトを読み込み、Gemini APIで文字起こし・要約・ファイル名生成。
9. MarkdownファイルをMARKDOWN_OUTPUT_DIRに保存。
10. 処理結果（元ファイル名、出力Markdown名、日時、ステータス）をJSONLでPROCESSED_LOG_FILEに追記。
11. 一時ディレクトリは成功時のみ削除、エラー時は残して再利用。