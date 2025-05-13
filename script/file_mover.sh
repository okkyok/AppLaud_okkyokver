#!/bin/zsh

# file_mover.sh
#
# USBデバイスがマウントされた際に呼び出され、音声ファイルを処理するスクリプト。
#
# 処理内容:
# 1. 設定ファイルを読み込む。
# 2. マウントされたUSBデバイスのパスを引数として受け取る。
# 3. デバイス内の音声ファイルを検索する。
# 4. 処理済みでないファイルを指定ディレクトリに移動する。
# 5. Pythonスクリプトを呼び出して文字起こしと要約を行う。

# --- 設定ファイルの読み込み ---
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
CONFIG_FILE="${SCRIPT_DIR}/config.sh"

if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
    echo "設定ファイルを読み込みました: $CONFIG_FILE"
else
    echo "エラー: 設定ファイルが見つかりません: $CONFIG_FILE" >&2
    exit 1
fi

# --- 引数のチェック ---
if [ -z "$1" ]; then
    echo "エラー: マウントされたUSBデバイスのパスが指定されていません。" >&2
    echo "使用法: $0 <マウントパス>" >&2
    exit 1
fi

MOUNTED_DEVICE_PATH="$1"
echo "マウントパス: $MOUNTED_DEVICE_PATH"

# --- ディレクトリ作成 ---
# AUDIO_DEST_DIR と MARKDOWN_OUTPUT_DIR が存在しない場合は作成
# PROCESSED_LOG_FILE の親ディレクトリも作成
mkdir -p "${AUDIO_DEST_DIR}"
echo "音声ファイル保存先ディレクトリを確認/作成しました: ${AUDIO_DEST_DIR}"
mkdir -p "${MARKDOWN_OUTPUT_DIR}"
echo "Markdown出力先ディレクトリを確認/作成しました: ${MARKDOWN_OUTPUT_DIR}"
LOG_FILE_DIR=$(dirname "${PROCESSED_LOG_FILE}")
if [ ! -d "$LOG_FILE_DIR" ]; then
    mkdir -p "$LOG_FILE_DIR"
    echo "ログファイル用ディレクトリを作成しました: $LOG_FILE_DIR"
fi
# ログファイル自体が存在しない場合は空ファイルを作成
touch "${PROCESSED_LOG_FILE}"
echo "処理済み記録ファイルを確認/作成しました: ${PROCESSED_LOG_FILE}"


# --- 処理済みファイルリストの読み込み ---
PROCESSED_FILES=()
if [ -f "$PROCESSED_LOG_FILE" ]; then
    while IFS= read -r line;
    do
        processed_file_name=$(echo "$line" | jq -r 'try .source_audio catch ""')
        if [ -n "$processed_file_name" ] && [ "$processed_file_name" != "null" ]; then
            PROCESSED_FILES+=("$processed_file_name")
        fi
    done < "$PROCESSED_LOG_FILE"
fi
echo "処理済みファイルリストを読み込みました。件数: ${#PROCESSED_FILES[@]}"


# --- 音声ファイルの検索 ---
echo "指定されたパスから音声ファイルを検索します: $MOUNTED_DEVICE_PATH"
echo "検索拡張子 (配列): ${TARGET_EXTENSIONS_ARRAY[@]}"

find_args=("$MOUNTED_DEVICE_PATH")
# config.shで定義された配列を直接展開してfind_argsに追加
# find_args+=(${TARGET_EXTENSIONS_ARRAY[@]}) # この行は不要になる

echo "実行するfindコマンドのパス部分: $find_args[1]"
print -lr -- "実行するfindコマンドの述語部分 (TARGET_EXTENSIONS_ARRAY):" "${TARGET_EXTENSIONS_ARRAY[@]}"

AUDIO_FILES=()
# findコマンドの標準エラー出力を確認するために一時的にリダイレクトを外すか、エラーも表示するようにする
# MOUNTED_DEVICE_PATH と TARGET_EXTENSIONS_ARRAY を直接findコマンドに渡す
find_output_and_error=$(find "$find_args[1]" "${TARGET_EXTENSIONS_ARRAY[@]}" -type f -print0 2>&1)
find_exit_code=$?
echo "Find command exit code: $find_exit_code" # デバッグ出力追加

if [ $find_exit_code -ne 0 ]; then
    echo "Find command error: $find_output_and_error" >&2
fi

while IFS= read -r -d $'\0' file; do
    AUDIO_FILES+=("$file")
done <<< "$find_output_and_error" # findの標準出力のみを読み込む


echo "検出された音声ファイル (AUDIO_FILES配列):"
for f in "${AUDIO_FILES[@]}"; do echo "  - $f"; done

if [ ${#AUDIO_FILES[@]} -eq 0 ]; then
    echo "対象の音声ファイルが見つかりませんでした。"
    exit 0
fi
echo "検出された音声ファイル数: ${#AUDIO_FILES[@]}"


# --- ファイルごとの処理ループ ---
echo "\n処理を開始します..."

for audio_file_full_path in "${AUDIO_FILES[@]}"; do
    audio_file_name=$(basename "$audio_file_full_path")
    echo "\n--------------------------------------------------"
    echo "処理対象ファイル: $audio_file_full_path ($audio_file_name)"

    # --- 処理済みか確認 ---
    is_processed=false
    for processed_name in "${PROCESSED_FILES[@]}"; do
        if [[ "$audio_file_name" == "$processed_name" ]]; then
            is_processed=true
            break
        fi
    done

    if $is_processed; then
        echo "ファイル [$audio_file_name] は既に処理済みです。スキップします。"
        continue
    fi

    echo "ファイル [$audio_file_name] は未処理です。"

    # --- ファイルの移動 ---
    destination_path="${AUDIO_DEST_DIR}/${audio_file_name}"
    echo "ファイルを移動します: $audio_file_full_path -> $destination_path"
    mv -f "$audio_file_full_path" "$destination_path"
    if [ $? -eq 0 ]; then
        echo "ファイルの移動に成功しました。"

        # --- Pythonスクリプトの呼び出し ---
        # Pythonスクリプトのパスを絶対パスに変換しておく方が安全
        # SCRIPT_DIR は file_mover.sh があるディレクトリ
        abs_python_script_path="$(cd "${SCRIPT_DIR}" && realpath "${PYTHON_SCRIPT_PATH}")"
        abs_summary_prompt_file_path="$(cd "${SCRIPT_DIR}" && realpath "${SUMMARY_PROMPT_FILE_PATH}")"
        abs_processed_log_file_path="$(cd "${SCRIPT_DIR}" && realpath "${PROCESSED_LOG_FILE}")"
        abs_markdown_output_dir="$(cd "${SCRIPT_DIR}" && realpath "${MARKDOWN_OUTPUT_DIR}")"
        abs_audio_dest_dir_for_python="$(cd "${SCRIPT_DIR}" && realpath "${AUDIO_DEST_DIR}")"
        moved_audio_file_path_for_python="${abs_audio_dest_dir_for_python}/${audio_file_name}"

        echo "Pythonスクリプトを呼び出します: $abs_python_script_path"
        python3 "$abs_python_script_path" \
            --audio_file_path "$moved_audio_file_path_for_python" \
            --markdown_output_dir "$abs_markdown_output_dir" \
            --summary_prompt_file_path "$abs_summary_prompt_file_path" \
            --processed_log_file_path "$abs_processed_log_file_path"
        
        python_exit_code=$?
        if [ $python_exit_code -eq 0 ]; then
            echo "Pythonスクリプトの実行に成功しました。"
        else
            echo "エラー: Pythonスクリプトの実行に失敗しました。(終了コード: $python_exit_code)" >&2
            # ここでエラー処理を追加可能 (例: ログに詳細を記録、ファイルを元に戻すなど)
            # 今回はログ出力のみ
        fi
    else
        echo "エラー: ファイルの移動に失敗しました: $audio_file_full_path" >&2
    fi
done

echo "\n全ての処理が完了しました。"
exit 0 