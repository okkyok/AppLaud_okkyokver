#!/bin/zsh

# --- 設定（すべてexportで環境変数化）---

# Google Gemini APIキー
export GOOGLE_API_KEY="YOUR_GOOGLE_API_KEY"

# 監視するボイスレコーダーのボリューム名
export RECORDER_NAME="RECORDER"

# 音声ファイルが格納されているUSBデバイス内のサブディレクトリ名
export VOICE_FILES_SUBDIR="RECORD"

# 音声ファイルを移動する先のローカルディレクトリ
export AUDIO_DEST_DIR="/path/to/audio"

# Markdown要約ファイルを出力する先のローカルディレクトリ
export MARKDOWN_OUTPUT_DIR="/path/to/markdown_output"

# 実行するPythonスクリプトのパス
export PYTHON_SCRIPT_PATH="./transcribe_summarize.py"

# 要約時に使用するプロンプトファイルのパス
export SUMMARY_PROMPT_FILE_PATH="../prompt/summary_prompt.txt"

# 処理済みファイルを記録するJSONLファイルのパス
export PROCESSED_LOG_FILE="../debug/processed_log.jsonl"

# 処理対象の拡張子 (zsh配列形式で定義)
export TARGET_EXTENSIONS_ARRAY=(-iname '*.wav' -o -iname '*.mp3' -o -iname '*.m4a')

# ステータス管理ファイル
export STATUS_FILE_PATH="/path/to/processing_status.jsonl"

# プロンプトテンプレートファイル
export PROMPT_TEMPLATE_PATH="../prompt/template.txt"

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