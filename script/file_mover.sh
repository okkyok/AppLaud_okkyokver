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

# --- 検索対象パスの決定 ---
SEARCH_PATH="$MOUNTED_DEVICE_PATH"
if [ -n "$VOICE_FILES_SUBDIR" ]; then
    SEARCH_PATH="${MOUNTED_DEVICE_PATH}/${VOICE_FILES_SUBDIR}"
fi
echo "検索対象パス: $SEARCH_PATH"

# --- マウントポイントの準備待機 ---
echo "マウントポイント準備待機中: $SEARCH_PATH"
RETRY_COUNT=0
MAX_RETRIES=30 # 最大30秒待機
while [ ! -d "$SEARCH_PATH" ]; do
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "エラー: $SEARCH_PATH が $MAX_RETRIES 秒以内に利用可能になりませんでした。"
        exit 1
    fi
    sleep 1
    RETRY_COUNT=$((RETRY_COUNT + 1))
done
echo "$SEARCH_PATH 準備完了。"

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
    # ファイルが空でないことを確認してからループを実行
    if [ -s "$PROCESSED_LOG_FILE" ]; then
        while IFS= read -r line;
        do
            processed_file_name=$(echo "$line" | jq -r 'try .source_audio catch ""')
            if [ $? -ne 0 ]; then
                echo "警告: jqの処理中にエラーが発生しました。対象行: $line" >&2
                # jqエラーの場合はその行をスキップ
                continue
            fi
            if [ -n "$processed_file_name" ] && [ "$processed_file_name" != "null" ]; then
                PROCESSED_FILES+=("$processed_file_name")
            fi
        done < "$PROCESSED_LOG_FILE"
    else
        echo "処理済み記録ファイルは空です。"
    fi
fi
echo "処理済みファイルリストを読み込みました。件数: ${#PROCESSED_FILES[@]}"


# --- 音声ファイルの検索 ---
echo "指定されたパスから音声ファイルを検索します: $SEARCH_PATH"
echo "検索拡張子 (配列): ${TARGET_EXTENSIONS_ARRAY[@]}"

echo "findコマンド実行前に5秒待機します..."
sleep 5

find_args=("$SEARCH_PATH")

echo "実行するfindコマンドのパス部分: $find_args[1]"
print -lr -- "実行するfindコマンドの述語部分 (TARGET_EXTENSIONS_ARRAY):" "${TARGET_EXTENSIONS_ARRAY[@]}"

AUDIO_FILES=()
find_stderr_output="" # findの標準エラー出力を格納する変数
# findの標準エラー出力をキャプチャする
# zshでのプロセス置換と変数代入の確実な方法として一時ファイルを使うことも考えられるが、まずは直接試みる
# findの標準出力を取得し、標準エラーはキャプチャして別途表示
find_output_stdout=$(find "$find_args[1]" -type f \
    \( "${TARGET_EXTENSIONS_ARRAY[@]}" \) \
    -not -name '._*' \
    -print0 2> >(find_stderr_output=$(cat); echo "$find_stderr_output" >&2) ) # stderrをキャプチャしつつ、ターミナルのログにも出す
find_exit_code=$?

echo "Find command exit code: $find_exit_code"

if [ $find_exit_code -ne 0 ]; then # find_stderr_output のチェックは削除。終了コードのみで判断。
    echo "エラー: findコマンドの実行に失敗しました。終了コード: $find_exit_code。パス: $find_args[1]" >&2
    if [ -n "$find_stderr_output" ] && [[ "$find_stderr_output" != *"Permission denied"* ]] && [[ "$find_stderr_output" != *"Operation not permitted"* ]]; then
        # Permission denied 以外のエラーメッセージがあれば表示 (Permission deniedはよく出るので抑制)
        echo "Find command stderr: $find_stderr_output" >&2
    fi
    if [ ! -d "$find_args[1]" ]; then # find失敗の原因がディレクトリ不在か確認
        echo "エラー: 検索対象ディレクトリが存在しません: $find_args[1]" >&2
    fi
    exit 1 # findが失敗したら終了
fi

# findの標準出力からファイルリストを読み込む
if [ -n "$find_output_stdout" ]; then
  while IFS= read -r -d $'\0' file; do
      if [ -n "$file" ]; then # 空のファイル名が紛れ込まないように
          AUDIO_FILES+=("$file")
      fi
  done <<< "$find_output_stdout"
else
  echo "findコマンドの標準出力は空でした（対象ファイルなし、またはエラー）。"
  # find_exit_codeが0でもファイルが見つからない場合は正常終了
fi

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