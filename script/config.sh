#!/bin/zsh

# --- 設定 ---

# 監視するボイスレコーダーのボリューム名（Macでマウントされたときの名前）
# (launchdの設定で使用。file_mover.sh自体は直接この値を使用しないが、関連情報として記述)
RECORDER_NAME="RECORDER"

# 音声ファイルが格納されているUSBデバイス内のサブディレクトリ名 (例: "RECORD", "VOICE" など)
# 指定しない場合は空文字列 "" にするとマウントポイント直下を検索します。
VOICE_FILES_SUBDIR="RECORD"

# 音声ファイルを移動する先のローカルディレクトリ (./file_mover.shからの相対パス)
AUDIO_DEST_DIR="/Users/takahashinaoki/AudioRecording"

# Markdown要約ファイルを出力する先のローカルディレクトリ (./file_mover.shからの相対パス)
MARKDOWN_OUTPUT_DIR="/Users/takahashinaoki/Library/Mobile Documents/iCloud~md~obsidian/Documents/Notes/recordings"

# 実行するPythonスクリプトのパス (./file_mover.shからの相対パス)
# file_mover.sh と同じディレクトリにある想定
PYTHON_SCRIPT_PATH="./transcribe_summarize.py"

# 要約時に使用するプロンプトファイルのパス (./file_mover.shからの相対パス)
SUMMARY_PROMPT_FILE_PATH="../prompt/summary_prompt.txt"

# 処理済みファイルを記録するJSONLファイルのパス (./file_mover.shからの相対パス)
PROCESSED_LOG_FILE="../debug/processed_log.jsonl"

# 処理対象の拡張子 (zsh配列形式で定義)
# 各要素は find の -name や -o に対応する
TARGET_EXTENSIONS_ARRAY=(-iname '*.wav' -o -iname '*.mp3' -o -iname '*.m4a')

# ステータス管理ファイル
STATUS_FILE_PATH="/Users/takahashinaoki/Dev/projects/AppLaud/debug_outputs/processing_status.jsonl"

# プロンプトテンプレートファイル
# このリポジトリの prompt/template.txt を指定することを想定しています。
PROMPT_TEMPLATE_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../prompt/template.txt"

# --- ここまで設定 ---

# 設定値の確認 (デバッグ用)
echo "--- config.sh 設定値 (スクリプト基準での解決前) --- "
echo "RECORDER_NAME: ${RECORDER_NAME}"
echo "AUDIO_DEST_DIR: ${AUDIO_DEST_DIR}"
echo "MARKDOWN_OUTPUT_DIR: ${MARKDOWN_OUTPUT_DIR}"
echo "PYTHON_SCRIPT_PATH: ${PYTHON_SCRIPT_PATH}"
echo "SUMMARY_PROMPT_FILE_PATH: ${SUMMARY_PROMPT_FILE_PATH}"
echo "PROCESSED_LOG_FILE: ${PROCESSED_LOG_FILE}"
echo "TARGET_EXTENSIONS_ARRAY (各要素):"
for element in "${TARGET_EXTENSIONS_ARRAY[@]}"; do
  echo "  - '$element'"
done
echo "-------------------------"

# 設定内容の確認用 (デバッグ時にコメントを外してください)
# echo "RECORDER_NAME: $RECORDER_NAME"
# echo "AUDIO_DEST_DIR: $AUDIO_DEST_DIR"
# echo "MARKDOWN_OUTPUT_DIR: $MARKDOWN_OUTPUT_DIR"
# echo "PYTHON_SCRIPT_PATH: $PYTHON_SCRIPT_PATH"
# echo "SEARCH_PATTERNS: ${SEARCH_PATTERNS[@]}"
# echo "STATUS_FILE_PATH: $STATUS_FILE_PATH"
# echo "PROMPT_TEMPLATE_PATH: $PROMPT_TEMPLATE_PATH" 