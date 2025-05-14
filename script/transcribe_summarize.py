import argparse
import datetime
import json
import os
import pathlib
import tempfile
import shutil
import re  # For filename sanitization

import google.generativeai as genai
from pydub import AudioSegment

# Constants
CHUNK_MAX_DURATION_MS = 20 * 60 * 1000  # 20 minutes in milliseconds
OVERLAP_MS = 1 * 60 * 1000  # 1 minute in milliseconds
MAX_FILENAME_LENGTH = 50  # Max length for the AI generated part of the filename


def generate_filename_from_summary(model, summary_text):
    """Generates a filename suggestion from the summary text using Gemini API."""
    print("Generating filename from summary...")
    prompt = (
        f"以下の要約内容の最も重要なトピックを反映した、具体的で短い日本語のファイル名を**一つだけ作成**してください。"
        f"ファイル名は、{MAX_FILENAME_LENGTH}文字以内の**一つの連続した文字列**とし、日本語、英数字、アンダースコア、ハイフンのみを使用してください。"
        f"拡張子は含めないでください。\n\n"
        f"例: AI戦略会議議事録\n\n"
        f"要約内容:\n{summary_text[:1000]}"
        f"\n\n作成ファイル名:"
    )
    try:
        response = model.generate_content(prompt)
        if response.candidates and response.candidates[0].content.parts:
            suggested_name = response.candidates[0].content.parts[0].text.strip()
            print(f"API suggested filename: {suggested_name}")
            return suggested_name
        else:
            print("Warning: Filename generation returned no suggestion.")
            return None
    except Exception as e:
        print(f"Error during filename generation: {e}")
        return None


def sanitize_filename(filename_suggestion, max_length=MAX_FILENAME_LENGTH):
    """日本語（全角文字）も許容しつつ、ファイル名として不適切な記号のみ除去する。"""
    if not filename_suggestion:
        return "untitled_summary"

    # 先頭・末尾の空白除去
    text = filename_suggestion.strip()
    # 許可する文字: 日本語（全角）、英数字、アンダースコア、ハイフン
    # 除去する: \\/:*?"<>| などファイル名に使えない記号
    text = re.sub(r'[\\/:*?"<>|]', "", text)
    # 空白はアンダースコアに
    text = re.sub(r"[\s]+", "_", text)
    # 連続アンダースコア・ハイフンを1つに
    text = re.sub(r"[_\-]{2,}", "_", text)
    # 先頭・末尾のアンダースコア・ハイフン除去
    text = text.strip("_- ")
    # 長さ制限
    text = text[:max_length]
    if not text:
        return "untitled_summary"
    return text


def transcribe_chunk(model, audio_chunk_path, transcription_output_path):
    """Uploads a single audio chunk, transcribes it, and saves the transcription."""
    print(f"Uploading chunk: {audio_chunk_path}...")
    audio_file_part = genai.upload_file(path=audio_chunk_path)
    print(f"Completed upload: {audio_file_part.name}")

    print(f"Transcribing chunk {audio_file_part.name}...")
    response = model.generate_content(
        ["この音声ファイルを文字起こししてください。", audio_file_part]
    )
    print(f"Deleting uploaded chunk from API: {audio_file_part.name}")
    genai.delete_file(audio_file_part.name)  # Delete from GenAI service

    transcription_text = ""
    if response.candidates and response.candidates[0].content.parts:
        transcription_text = response.candidates[0].content.parts[0].text
    else:
        print(f"Warning: Transcription for chunk {audio_chunk_path} returned no text.")

    # Save transcription to file
    try:
        with open(transcription_output_path, "w", encoding="utf-8") as f:
            f.write(transcription_text)
        print(f"Transcription for chunk saved to: {transcription_output_path}")
    except IOError as e:
        print(
            f"Error saving transcription for chunk {audio_chunk_path} to {transcription_output_path}: {e}"
        )
        # Decide if this error should be propagated or handled
        # For now, we'll return the text, but it won't be persisted for next run if saving failed.

    return transcription_text


def transcribe_audio(model, audio_file_path, temp_chunk_dir_path):
    """
    Handles audio transcription, including splitting long files into chunks
    with overlap, transcribing each chunk, and managing temporary files for reuse.
    Returns the full transcription text and a list of temporary chunk audio files created.
    """
    print(f"Loading audio file: {audio_file_path}...")
    try:
        audio = AudioSegment.from_file(audio_file_path)
    except Exception as e:
        raise ValueError(
            f"Could not read audio file {audio_file_path}. Ensure ffmpeg is installed if using non-wav/mp3. Error: {e}"
        )

    duration_ms = len(audio)
    print(f"Audio duration: {duration_ms / 1000 / 60:.2f} minutes")

    # --- 短い音声用キャッシュファイルパス ---
    short_transcription_cache = None
    if temp_chunk_dir_path is not None:
        short_transcription_cache = temp_chunk_dir_path / "full_transcription.txt"
    else:
        # fallback: use audio file dir
        short_transcription_cache = pathlib.Path(audio_file_path).parent / (
            pathlib.Path(audio_file_path).stem + "_transcription.txt"
        )

    if duration_ms <= CHUNK_MAX_DURATION_MS:
        # キャッシュがあれば再利用
        if short_transcription_cache.exists():
            print(f"Found cached transcription: {short_transcription_cache}")
            with open(short_transcription_cache, "r", encoding="utf-8") as f:
                return f.read()
        print("Audio is short enough, transcribing directly.")
        print(f"Uploading file: {audio_file_path}...")
        audio_file_full = genai.upload_file(path=audio_file_path)
        print(f"Completed upload: {audio_file_full.name}")

        print("Transcribing audio...")
        response = model.generate_content(
            ["この音声ファイルを文字起こししてください。", audio_file_full]
        )
        print(f"Deleting uploaded file from API: {audio_file_full.name}")
        genai.delete_file(audio_file_full.name)
        if response.candidates and response.candidates[0].content.parts:
            transcription = response.candidates[0].content.parts[0].text
            # キャッシュとして保存
            try:
                with open(short_transcription_cache, "w", encoding="utf-8") as f:
                    f.write(transcription)
                print(f"Transcription cached to: {short_transcription_cache}")
            except Exception as e:
                print(f"Warning: Failed to cache transcription: {e}")
            return transcription
        else:
            raise ValueError(
                "Direct transcription failed or returned an empty response."
            )
    else:
        print(
            f"Audio is long, splitting into chunks with overlap into {temp_chunk_dir_path}..."
        )
        temp_chunk_dir_path.mkdir(parents=True, exist_ok=True)  # Ensure temp dir exists

        chunk_audio_files = []
        chunk_transcription_files = []
        all_transcriptions = []

        start_ms = 0
        chunk_id = 0
        while start_ms < duration_ms:
            end_ms = min(start_ms + CHUNK_MAX_DURATION_MS, duration_ms)
            chunk_id += 1

            chunk_audio_file_path = temp_chunk_dir_path / f"chunk_{chunk_id}.wav"
            chunk_transcription_file_path = (
                temp_chunk_dir_path / f"chunk_{chunk_id}_transcription.txt"
            )
            chunk_audio_files.append(chunk_audio_file_path)
            chunk_transcription_files.append(chunk_transcription_file_path)

            # Export audio chunk if it doesn't exist
            if not chunk_audio_file_path.exists():
                print(
                    f"Exporting audio chunk {chunk_id}: {start_ms}ms to {end_ms}ms to {chunk_audio_file_path}"
                )
                current_chunk_segment = audio[start_ms:end_ms]
                current_chunk_segment.export(chunk_audio_file_path, format="wav")
            else:
                print(f"Audio chunk {chunk_audio_file_path} already exists.")

            # Check for existing transcription or transcribe
            if chunk_transcription_file_path.exists():
                print(
                    f"Found existing transcription for chunk {chunk_id}: {chunk_transcription_file_path}"
                )
                try:
                    with open(
                        chunk_transcription_file_path, "r", encoding="utf-8"
                    ) as f:
                        transcription_part = f.read()
                except IOError as e:
                    print(
                        f"Error reading existing transcription {chunk_transcription_file_path}: {e}. Retranscribing."
                    )
                    # Fall through to transcribe if reading fails
                    transcription_part = transcribe_chunk(
                        model, chunk_audio_file_path, chunk_transcription_file_path
                    )
            else:
                print(f"Transcribing chunk {chunk_id}: {chunk_audio_file_path}")
                transcription_part = transcribe_chunk(
                    model, chunk_audio_file_path, chunk_transcription_file_path
                )

            all_transcriptions.append(transcription_part)

            if end_ms == duration_ms:
                break
            start_ms = max(0, end_ms - OVERLAP_MS)
            if start_ms >= duration_ms:
                break

        print(f"Processed {len(all_transcriptions)} chunks.")
        full_transcription = "\n\n".join(filter(None, all_transcriptions))
        return full_transcription  # Temporary chunk files are cleaned up by main


def summarize_text(model, text, prompt_template):
    """Summarizes the given text using the provided prompt template."""
    print("Summarizing text...")
    prompt = prompt_template.replace("{{TRANSCRIPTION}}", text)
    response = model.generate_content(prompt)
    if response.candidates and response.candidates[0].content.parts:
        return response.candidates[0].content.parts[0].text
    else:
        raise ValueError("Summarization failed or returned an empty response.")


def save_markdown(text, output_dir, generated_filename_base, file_date):
    """日本語タイトルも許容し、YYYYMMDD_タイトル.md 形式でMarkdownを保存する。既存ファイルがあれば連番を付与。"""
    # 日付+タイトルのファイル名例: 20240601_幾何学講義.md
    date_prefix = file_date.strftime("%Y%m%d")
    base_name = f"{date_prefix}_{generated_filename_base}"
    markdown_filename = f"{base_name}.md"
    output_path = pathlib.Path(output_dir) / markdown_filename
    count = 1
    # 既存ファイルがあれば連番を付与
    while output_path.exists():
        markdown_filename = f"{base_name}_{count}.md"
        output_path = pathlib.Path(output_dir) / markdown_filename
        count += 1
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Markdown saved to: {output_path}")
    return markdown_filename  # 実際に使われたファイル名を返す


def log_processed_file(
    log_file_path, source_audio, output_markdown, status, error_message=None
):
    """Logs the processing information to a JSONL file."""
    log_entry = {
        "source_audio": source_audio,
        "output_markdown": output_markdown,
        "processed_at": datetime.datetime.now().isoformat(),
        "status": status,
    }
    if error_message:
        log_entry["error_message"] = error_message

    with open(log_file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    print(f"Logged to: {log_file_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe and summarize audio files in a directory."
    )
    parser.add_argument(
        "--audio_processing_dir",
        required=True,
        help="Directory containing audio files to process.",
    )
    parser.add_argument(
        "--markdown_output_dir",
        required=True,
        help="Directory to save the Markdown summary.",
    )
    parser.add_argument(
        "--summary_prompt_file_path",
        required=True,
        help="Path to the summary prompt template file.",
    )
    parser.add_argument(
        "--processed_log_file_path", required=True, help="Path to the JSONL log file."
    )
    args = parser.parse_args()

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("Error: GOOGLE_API_KEY environment variable not set.")
        if args.processed_log_file_path and args.audio_processing_dir:
            log_processed_file(
                args.processed_log_file_path,
                pathlib.Path(args.audio_processing_dir).name,
                None,
                "failure",
                "GOOGLE_API_KEY not set",
            )
        return

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")  # Using recommended model

    processing_dir = pathlib.Path(args.audio_processing_dir)
    markdown_output_dir = pathlib.Path(args.markdown_output_dir)
    summary_prompt_file_path = pathlib.Path(args.summary_prompt_file_path)
    processed_log_file_path = pathlib.Path(args.processed_log_file_path)

    done_dir = processing_dir / "done"
    done_dir.mkdir(parents=True, exist_ok=True)

    # Process each audio file in the directory
    audio_extensions = [".wav", ".mp3", ".m4a"]
    audio_files_to_process = [
        f
        for f in processing_dir.iterdir()
        if f.is_file() and f.suffix.lower() in audio_extensions
    ]

    if not audio_files_to_process:
        print(
            f"No audio files found in {processing_dir} with extensions {audio_extensions}"
        )
        return

    print(
        f"Found {len(audio_files_to_process)} audio files to process in {processing_dir}"
    )

    for audio_file_path in audio_files_to_process:
        original_audio_path = audio_file_path
        original_audio_filename = original_audio_path.name
        original_audio_filename_stem = original_audio_path.stem
        output_markdown_filename = None
        print(f"\n--- Processing file: {original_audio_filename} ---")

        # Define a specific temporary directory for this audio file's chunks
        temp_base_dir = pathlib.Path(".").resolve() / ".tmp_chunks"
        # Ensure unique temp dir name, even if filenames are similar across different original dirs
        # (though in this script, all files come from the same processing_dir)
        temp_chunk_processing_dir = (
            temp_base_dir / f"{original_audio_filename_stem}_chunks"
        )

        cleanup_temp_dir_on_success = False  # Flag to control cleanup

        try:
            # Check duration to decide if temp_chunk_processing_dir is needed
            audio_for_duration_check = AudioSegment.from_file(original_audio_path)
            if len(audio_for_duration_check) > CHUNK_MAX_DURATION_MS:
                temp_chunk_processing_dir.mkdir(parents=True, exist_ok=True)
                cleanup_temp_dir_on_success = (
                    True  # Mark for cleanup only if it was used
                )
                print(
                    f"Using temporary directory for chunks: {temp_chunk_processing_dir}"
                )

            with open(summary_prompt_file_path, "r", encoding="utf-8") as f:
                prompt_template = f.read()

            transcription = None
            try:
                transcription = transcribe_audio(
                    model,
                    original_audio_path,
                    temp_chunk_processing_dir if cleanup_temp_dir_on_success else None,
                )
            except Exception as e:
                print(f"Error during transcription for {original_audio_filename}: {e}")
                log_processed_file(
                    processed_log_file_path,
                    original_audio_filename,
                    None,
                    "transcribe_failure",
                    str(e),
                )
                # Continue to the next file if transcription fails
                continue

            try:
                summary = summarize_text(model, transcription, prompt_template)
                suggested_filename_base = generate_filename_from_summary(model, summary)
                sanitized_filename_base = sanitize_filename(suggested_filename_base)

                # Get audio file creation date
                file_creation_timestamp = original_audio_path.stat().st_ctime
                file_creation_date = datetime.datetime.fromtimestamp(
                    file_creation_timestamp
                )

                output_markdown_filename = save_markdown(
                    summary,
                    markdown_output_dir,
                    sanitized_filename_base,
                    file_creation_date,
                )
                log_processed_file(
                    processed_log_file_path,
                    original_audio_filename,
                    output_markdown_filename,
                    "summary_success",
                )
                print(f"Processing successful for {original_audio_filename}.")

                # Move processed file to done directory
                try:
                    shutil.move(
                        str(original_audio_path),
                        str(done_dir / original_audio_filename),
                    )
                    print(f"Moved {original_audio_filename} to {done_dir}")
                except Exception as e:
                    print(f"Error moving {original_audio_filename} to {done_dir}: {e}")
                    # Log this failure separately if needed, or add to existing log
                    log_processed_file(
                        processed_log_file_path,
                        original_audio_filename,
                        output_markdown_filename,  # Markdown might have been created
                        "move_to_done_failure",
                        f"Failed to move to {done_dir}: {str(e)}",
                    )

                # Clean up temp chunk dir if it was used and successful
                if cleanup_temp_dir_on_success and temp_chunk_processing_dir.exists():
                    try:
                        shutil.rmtree(temp_chunk_processing_dir)
                        print(
                            f"Successfully removed temporary chunk directory: {temp_chunk_processing_dir}"
                        )
                    except Exception as e:
                        print(
                            f"Warning: Failed to remove temporary chunk directory {temp_chunk_processing_dir}: {e}"
                        )

            except Exception as e:
                error_msg = f"Error summarizing {original_audio_filename}: {e}"
                print(error_msg)
                log_processed_file(
                    processed_log_file_path,
                    original_audio_filename,
                    output_markdown_filename,  # Markdown might have been created or not
                    "summary_failure",
                    str(e),
                )
                print(
                    f"Temporary chunk files (if any) for {original_audio_filename} will be kept for next run due to error."
                )
                # Continue to the next file
                continue

        except Exception as e:
            error_msg = f"Unhandled error processing {original_audio_filename}: {e}"
            print(error_msg)
            log_processed_file(
                processed_log_file_path,
                original_audio_filename,
                output_markdown_filename,  # Markdown might have been created or not
                "failure",
                str(e),
            )
            print(
                f"Temporary chunk files (if any) for {original_audio_filename} will be kept for next run due to error."
            )
            # Continue to the next file
            continue

    print("\nAll files processed.")


if __name__ == "__main__":
    main()
