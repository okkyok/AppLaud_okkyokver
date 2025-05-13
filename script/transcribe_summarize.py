import argparse
import datetime
import json
import os
import pathlib
import tempfile

import google.generativeai as genai
from pydub import AudioSegment
from pydub.utils import make_chunks

# Constants
CHUNK_MAX_DURATION_MS = 20 * 60 * 1000  # 20 minutes in milliseconds
OVERLAP_MS = 1 * 60 * 1000  # 1 minute in milliseconds


def transcribe_chunk(model, audio_chunk_path):
    """Uploads a single audio chunk and returns the transcription."""
    print(f"Uploading chunk: {audio_chunk_path}...")
    # audio_file_part = genai.upload_file(path=audio_chunk_path, mime_type="audio/wav") # Assuming WAV for chunks
    # Consider directly passing bytes if API supports it and pydub can provide them easily,
    # to avoid writing temporary chunk files if not strictly necessary.
    # For now, using file upload as it's more straightforward with current genai SDK.
    audio_file_part = genai.upload_file(
        path=audio_chunk_path
    )  # Let API infer mime type
    print(f"Completed upload: {audio_file_part.name}")

    print(f"Transcribing chunk {audio_file_part.name}...")
    response = model.generate_content(
        ["この音声ファイルを文字起こししてください。", audio_file_part]
    )
    print(f"Deleting uploaded chunk: {audio_file_part.name}")
    genai.delete_file(audio_file_part.name)

    if response.candidates and response.candidates[0].content.parts:
        return response.candidates[0].content.parts[0].text
    else:
        # It's possible a silent chunk returns no text.
        # Consider how to handle this - for now, return empty string.
        print(f"Warning: Transcription for chunk {audio_chunk_path} returned no text.")
        return ""


def transcribe_audio(model, audio_file_path):
    """
    Handles audio transcription, including splitting long files into chunks
    with overlap and transcribing each chunk.
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
        print(f"Deleting uploaded file: {audio_file_full.name}")
        genai.delete_file(audio_file_full.name)
        if response.candidates and response.candidates[0].content.parts:
            return response.candidates[0].content.parts[0].text
        else:
            raise ValueError(
                "Direct transcription failed or returned an empty response."
            )
    else:
        print("Audio is long, splitting into chunks with overlap...")
        # Calculate the number of chunks needed to ensure each is <= CHUNK_MAX_DURATION_MS
        # This is a simplified calculation; more robust logic might be needed for edge cases.
        # Effective chunk duration considering overlap for splitting calculation:
        # For chunking, we want segments of CHUNK_MAX_DURATION_MS, but each subsequent chunk starts OVERLAP_MS earlier.
        # So, a segment effectively covers CHUNK_MAX_DURATION_MS - OVERLAP_MS of new audio,
        # except for the first chunk which covers CHUNK_MAX_DURATION_MS.

        # Using pydub's make_chunks is simpler for fixed duration chunks.
        # However, we need custom logic for the overlap and ensuring similar length.

        chunks = []
        start_ms = 0
        chunk_id = 0
        temp_dir = tempfile.mkdtemp()
        all_transcriptions = []

        try:
            while start_ms < duration_ms:
                end_ms = min(start_ms + CHUNK_MAX_DURATION_MS, duration_ms)
                chunk = audio[start_ms:end_ms]
                chunk_id += 1
                # Use a temporary file for each chunk to pass to genai.upload_file
                # Chunks should ideally be in a format that genai.upload_file handles well without explicit mime_type,
                # or we specify it (e.g., audio.export with format="wav"). For simplicity, rely on API's inference.
                chunk_file_path = (
                    pathlib.Path(temp_dir) / f"chunk_{chunk_id}.wav"
                )  # Export as WAV for wider compatibility
                print(
                    f"Exporting chunk {chunk_id}: {start_ms}ms to {end_ms}ms to {chunk_file_path}"
                )
                chunk.export(chunk_file_path, format="wav")
                chunks.append(chunk_file_path)

                # Determine next start based on overlap, but don't go past duration_ms
                if end_ms == duration_ms:  # Last chunk
                    break
                start_ms = max(
                    0, end_ms - OVERLAP_MS
                )  # Ensure start_ms is not negative
                if (
                    start_ms >= duration_ms
                ):  # Avoid creating a zero-length or negative-length chunk
                    break

            print(f"Created {len(chunks)} chunks.")

            for i, chunk_path in enumerate(chunks):
                print(f"Processing chunk {i+1}/{len(chunks)}: {chunk_path}")
                try:
                    transcription_part = transcribe_chunk(model, chunk_path)
                    all_transcriptions.append(transcription_part)
                except Exception as e:
                    print(f"Error transcribing chunk {chunk_path}: {e}")
                    # Decide if one failed chunk should fail all, or try to continue
                    all_transcriptions.append(
                        f"[Error transcribing chunk {i+1}]"
                    )  # Placeholder for failed chunk

            # Simple concatenation for now. More sophisticated merging might be needed
            # if overlaps produce redundant text and need intelligent joining.
            # For now, this assumes the LLM summarizer can handle some redundancy
            # or that the transcription of overlapping parts is mostly consistent.
            print("Combining transcriptions...")
            full_transcription = "\n\n".join(
                filter(None, all_transcriptions)
            )  # Join non-empty parts
            return full_transcription

        finally:
            # Clean up temporary chunk files
            print(f"Cleaning up temporary directory: {temp_dir}")
            for chunk_path in chunks:
                try:
                    os.remove(chunk_path)
                except OSError as e:
                    print(f"Error removing temporary chunk file {chunk_path}: {e}")
            try:
                os.rmdir(temp_dir)
            except OSError as e:
                print(f"Error removing temporary directory {temp_dir}: {e}")


def summarize_text(model, text, prompt_template):
    """Summarizes the given text using the provided prompt template."""
    print("Summarizing text...")
    prompt = prompt_template.replace("{{TRANSCRIPTION}}", text)
    response = model.generate_content(prompt)
    if response.candidates and response.candidates[0].content.parts:
        return response.candidates[0].content.parts[0].text
    else:
        raise ValueError("Summarization failed or returned an empty response.")


def save_markdown(text, output_dir, original_audio_filename):
    """Saves the text as a Markdown file in the output directory."""
    date_prefix = datetime.datetime.now().strftime("%Y%m%d")
    base_filename = pathlib.Path(original_audio_filename).stem
    markdown_filename = f"{date_prefix}_{base_filename}.md"
    output_path = pathlib.Path(output_dir) / markdown_filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Markdown saved to: {output_path}")
    return markdown_filename


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
        # Log failure even if API key is missing, if log path is available
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

    original_audio_filename = pathlib.Path(args.audio_file_path).name
    output_markdown_filename = None

    try:
        # 1. Load summary prompt template
        with open(args.summary_prompt_file_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()

        # 2. Transcribe audio
        transcription = transcribe_audio(model, args.audio_file_path)

        # 3. Summarize text
        summary = summarize_text(model, transcription, prompt_template)

        # 4. Save Markdown
        output_markdown_filename = save_markdown(
            summary, args.markdown_output_dir, original_audio_filename
        )

        # 5. Log success
        log_processed_file(
            args.processed_log_file_path,
            original_audio_filename,
            output_markdown_filename,
            "success",
        )
        print("Processing successful.")

    except Exception as e:
        error_msg = f"Error processing {original_audio_filename}: {e}"
        print(error_msg)
        # Log failure
        log_processed_file(
            args.processed_log_file_path,
            original_audio_filename,
            output_markdown_filename,  # Could be None if saving failed
            "failure",
            str(e),
        )


if __name__ == "__main__":
    main()
