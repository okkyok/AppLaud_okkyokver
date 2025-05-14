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
        f"以下の要約内容に最も適した、簡潔で分かりやすいファイル名を提案してください。"
        f"ファイル名は英語のアルファベット(小文字)、数字、アンダースコア、ハイフンのみを使用し、"
        f"最大{MAX_FILENAME_LENGTH}文字程度で、拡張子は含めないでください。"
        f"例: ○○株式会社商談, 幾何学講義, お問い合わせ電話対応\n\n"
        f"要約内容:\n{summary_text[:1000]}"
        f"\n\n提案ファイル名:"
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
    """Sanitizes a filename suggestion to be filesystem-friendly."""
    if not filename_suggestion:
        return "untitled_summary"

    # Convert to lowercase
    text = filename_suggestion.lower()
    # Replace spaces and common problematic characters with underscore
    text = re.sub(r'[\s\\/:*?"<>|]+', "_", text)
    # Keep only alphanumeric, underscore, hyphen
    text = re.sub(r"[^a-z0-9_\-]", "", text)
    # Replace multiple underscores/hyphens with a single one
    text = re.sub(r"[_\-]{2,}", "_", text)
    # Remove leading/trailing underscores/hyphens
    text = text.strip("_-")
    # Truncate to max_length
    text = text[:max_length]
    # If somehow empty after sanitization, return default
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

    if duration_ms <= CHUNK_MAX_DURATION_MS:
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
            return response.candidates[0].content.parts[0].text
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


def save_markdown(text, output_dir, generated_filename_base):
    """Saves the text as a Markdown file in the output directory using a generated filename base.
    If a file with the same name exists, appends a count (_1, _2, ...) to avoid overwriting.
    """
    date_prefix = datetime.datetime.now().strftime("%Y%m%d")
    base_name = f"{date_prefix}_{generated_filename_base}"
    markdown_filename = f"{base_name}.md"
    output_path = pathlib.Path(output_dir) / markdown_filename
    count = 1
    # Check for existing files and increment count if needed
    while output_path.exists():
        markdown_filename = f"{base_name}_{count}.md"
        output_path = pathlib.Path(output_dir) / markdown_filename
        count += 1
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Markdown saved to: {output_path}")
    return markdown_filename  # Return the actual filename used


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
        description="Transcribe and summarize an audio file."
    )
    parser.add_argument(
        "--audio_file_path", required=True, help="Path to the audio file."
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
        if args.processed_log_file_path and args.audio_file_path:
            log_processed_file(
                args.processed_log_file_path,
                pathlib.Path(args.audio_file_path).name,
                None,
                "failure",
                "GOOGLE_API_KEY not set",
            )
        return

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")  # Using recommended model

    original_audio_path = pathlib.Path(args.audio_file_path)
    original_audio_filename = original_audio_path.name
    original_audio_filename_stem = original_audio_path.stem
    output_markdown_filename = None

    # Define a specific temporary directory for this audio file's chunks
    # This directory will only be cleaned up on full success
    # temp_base_dir = pathlib.Path(tempfile.gettempdir()) # System's temp dir
    # For more predictable location within project, can use: (ensure .gitignore includes './.tmp_chunks/')
    temp_base_dir = pathlib.Path(".").resolve() / ".tmp_chunks"
    temp_chunk_processing_dir = temp_base_dir / f"{original_audio_filename_stem}_chunks"

    cleanup_temp_dir_on_success = False  # Flag to control cleanup

    try:
        # Check duration to decide if temp_chunk_processing_dir is needed
        # This is a bit redundant as transcribe_audio also checks, but helps manage dir creation
        audio_for_duration_check = AudioSegment.from_file(args.audio_file_path)
        if len(audio_for_duration_check) > CHUNK_MAX_DURATION_MS:
            temp_chunk_processing_dir.mkdir(parents=True, exist_ok=True)
            cleanup_temp_dir_on_success = True  # Mark for cleanup only if it was used
            print(f"Using temporary directory for chunks: {temp_chunk_processing_dir}")

        with open(args.summary_prompt_file_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()

        # Pass the specific temp dir to transcribe_audio if it's a long file
        transcription = transcribe_audio(
            model,
            args.audio_file_path,
            temp_chunk_processing_dir if cleanup_temp_dir_on_success else None,
        )

        summary = summarize_text(model, transcription, prompt_template)

        # Generate filename from summary
        suggested_filename_base = generate_filename_from_summary(model, summary)
        sanitized_filename_base = sanitize_filename(suggested_filename_base)

        output_markdown_filename = save_markdown(
            summary, args.markdown_output_dir, sanitized_filename_base
        )

        log_processed_file(
            args.processed_log_file_path,
            original_audio_filename,
            output_markdown_filename,
            "success",
        )
        print("Processing successful.")

        # If all successful, and temp dir was used, clean it up
        # if cleanup_temp_dir_on_success and temp_chunk_processing_dir.exists():
        #     print(f"Cleaning up temporary directory: {temp_chunk_processing_dir}")
        #     shutil.rmtree(temp_chunk_processing_dir)

    except Exception as e:
        error_msg = f"Error processing {original_audio_filename}: {e}"
        print(error_msg)
        log_processed_file(
            args.processed_log_file_path,
            original_audio_filename,
            output_markdown_filename,
            "failure",
            str(e),
        )
        print("Temporary chunk files (if any) will be kept for next run due to error.")


if __name__ == "__main__":
    main()
