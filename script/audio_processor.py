#!/usr/bin/env python3
"""
音声処理クラス - 文字起こし・要約・ファイル名生成
"""

import datetime
import pathlib
import tempfile
import re
from typing import Optional, Tuple

import google.generativeai as genai
from pydub import AudioSegment

from config_manager import ConfigManager


class AudioProcessor:
    """音声ファイルの処理を担当するクラス"""
    
    # 定数
    CHUNK_MAX_DURATION_MS = 20 * 60 * 1000  # 20分
    OVERLAP_MS = 1 * 60 * 1000  # 1分
    MAX_FILENAME_LENGTH = 50
    
    def __init__(self, config: ConfigManager):
        """初期化"""
        self.config = config
        self.model = genai.GenerativeModel("gemini-1.5-flash")
        genai.configure(api_key=config.google_api_key)
    
    def extract_recording_datetime_from_filename(self, filename: str) -> Optional[datetime.datetime]:
        """録音ファイル名から日時を抽出"""
        pattern = self.config.recording_filename_pattern
        if not pattern:
            return None
        
        try:
            filename_without_ext = pathlib.Path(filename).stem
            
            # パターンから正規表現を生成
            regex_pattern = pattern
            regex_pattern = regex_pattern.replace('%Y', r'(?P<Y>\d{4})')
            regex_pattern = regex_pattern.replace('%m', r'(?P<m>\d{2})')
            regex_pattern = regex_pattern.replace('%d', r'(?P<d>\d{2})')
            regex_pattern = regex_pattern.replace('%H', r'(?P<H>\d{2})')
            regex_pattern = regex_pattern.replace('%M', r'(?P<M>\d{2})')
            regex_pattern = regex_pattern.replace('%S', r'(?P<S>\d{2})')
            
            match = re.match(regex_pattern, filename_without_ext)
            if not match:
                print(f"Warning: Filename '{filename}' does not match pattern '{pattern}'")
                return None
            
            groups = match.groupdict()
            year = int(groups.get('Y', 1900))
            month = int(groups.get('m', 1))
            day = int(groups.get('d', 1))
            hour = int(groups.get('H', 0))
            minute = int(groups.get('M', 0))
            second = int(groups.get('S', 0))
            
            recording_datetime = datetime.datetime(year, month, day, hour, minute, second)
            print(f"Extracted recording datetime: {recording_datetime} from filename: {filename}")
            return recording_datetime
            
        except Exception as e:
            print(f"Error extracting datetime from filename '{filename}' with pattern '{pattern}': {e}")
            return None
    
    def create_fast_audio(self, audio_file_path: str, temp_dir: pathlib.Path) -> pathlib.Path:
        """音声ファイルを指定倍速に変換"""
        audio = AudioSegment.from_file(audio_file_path)
        
        # 指定倍速に変換
        fast_audio = audio._spawn(
            audio.raw_data, 
            overrides={"frame_rate": int(audio.frame_rate * self.config.audio_speed_multiplier)}
        )
        
        # 一時ファイル名を生成
        original_name = pathlib.Path(audio_file_path).stem
        fast_audio_path = temp_dir / f"{original_name}_fast.wav"
        
        temp_dir.mkdir(parents=True, exist_ok=True)
        fast_audio.export(fast_audio_path, format="wav")
        print(f"Created {self.config.audio_speed_multiplier}x speed audio: {fast_audio_path}")
        
        return fast_audio_path
    
    def transcribe_chunk(self, audio_chunk_path: pathlib.Path, transcription_output_path: pathlib.Path) -> str:
        """単一音声チャンクの文字起こし"""
        print(f"Uploading chunk: {audio_chunk_path}...")
        audio_file_part = genai.upload_file(path=audio_chunk_path)
        print(f"Completed upload: {audio_file_part.name}")

        print(f"Transcribing chunk {audio_file_part.name}...")
        response = self.model.generate_content(
            ["この音声ファイルを文字起こししてください。", audio_file_part]
        )
        print(f"Deleting uploaded chunk from API: {audio_file_part.name}")
        genai.delete_file(audio_file_part.name)

        transcription_text = ""
        if response.candidates and response.candidates[0].content.parts:
            transcription_text = response.candidates[0].content.parts[0].text
        else:
            print(f"Warning: Transcription for chunk {audio_chunk_path} returned no text.")

        # 文字起こし結果を保存
        try:
            with open(transcription_output_path, "w", encoding="utf-8") as f:
                f.write(transcription_text)
            print(f"Transcription for chunk saved to: {transcription_output_path}")
        except IOError as e:
            print(f"Error saving transcription for chunk {audio_chunk_path} to {transcription_output_path}: {e}")

        return transcription_text
    
    def transcribe_audio(self, audio_file_path: str, temp_chunk_dir_path: Optional[pathlib.Path]) -> str:
        """音声ファイルの文字起こし（チャンク分割対応）"""
        print(f"Loading audio file: {audio_file_path}...")
        try:
            audio = AudioSegment.from_file(audio_file_path)
        except Exception as e:
            raise ValueError(f"Could not read audio file {audio_file_path}. Ensure ffmpeg is installed if using non-wav/mp3. Error: {e}")

        duration_ms = len(audio)
        print(f"Audio duration: {duration_ms / 1000 / 60:.2f} minutes")

        # 高速音声用の一時ディレクトリを作成
        if temp_chunk_dir_path is not None:
            fast_audio_temp_dir = temp_chunk_dir_path / "fast_audio"
        else:
            fast_audio_temp_dir = pathlib.Path(audio_file_path).parent / "fast_audio_temp"

        # 短い音声用キャッシュファイルパス
        short_transcription_cache = None
        if temp_chunk_dir_path is not None:
            short_transcription_cache = temp_chunk_dir_path / "full_transcription.txt"
        else:
            short_transcription_cache = pathlib.Path(audio_file_path).parent / (
                pathlib.Path(audio_file_path).stem + "_transcription.txt"
            )

        fast_audio_path = None
        try:
            if duration_ms <= self.CHUNK_MAX_DURATION_MS:
                # キャッシュがあれば再利用
                if short_transcription_cache.exists():
                    print(f"Found cached transcription: {short_transcription_cache}")
                    with open(short_transcription_cache, "r", encoding="utf-8") as f:
                        return f.read()
                
                print(f"Audio is short enough, creating {self.config.audio_speed_multiplier}x speed version and transcribing directly.")
                
                # 高速音声を作成
                fast_audio_path = self.create_fast_audio(audio_file_path, fast_audio_temp_dir)
                
                print(f"Uploading {self.config.audio_speed_multiplier}x speed file: {fast_audio_path}...")
                audio_file_full = genai.upload_file(path=fast_audio_path)
                print(f"Completed upload: {audio_file_full.name}")

                print(f"Transcribing {self.config.audio_speed_multiplier}x speed audio...")
                response = self.model.generate_content(
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
                    raise ValueError("Direct transcription failed or returned an empty response.")
        finally:
            # 高速音声の一時ファイルをクリーンアップ
            if fast_audio_path and fast_audio_path.exists():
                try:
                    fast_audio_path.unlink()
                    print(f"Deleted {self.config.audio_speed_multiplier}x speed temporary file: {fast_audio_path}")
                except Exception as e:
                    print(f"Warning: Failed to delete {self.config.audio_speed_multiplier}x speed temporary file {fast_audio_path}: {e}")
            
            # 高速音声用一時ディレクトリをクリーンアップ（空の場合のみ）
            if fast_audio_temp_dir.exists():
                try:
                    fast_audio_temp_dir.rmdir()
                    print(f"Deleted {self.config.audio_speed_multiplier}x speed temporary directory: {fast_audio_temp_dir}")
                except OSError:
                    pass

        # 長い音声ファイルの処理
        return self._transcribe_long_audio(audio, audio_file_path, temp_chunk_dir_path)
    
    def _transcribe_long_audio(self, audio: AudioSegment, audio_file_path: str, temp_chunk_dir_path: pathlib.Path) -> str:
        """長い音声ファイルのチャンク分割処理"""
        print(f"Audio is long, creating {self.config.audio_speed_multiplier}x speed version and splitting into chunks with overlap into {temp_chunk_dir_path}...")
        temp_chunk_dir_path.mkdir(parents=True, exist_ok=True)

        chunk_audio_files = []
        chunk_transcription_files = []
        all_transcriptions = []

        start_ms = 0
        chunk_id = 0
        duration_ms = len(audio)
        
        while start_ms < duration_ms:
            end_ms = min(start_ms + self.CHUNK_MAX_DURATION_MS, duration_ms)
            chunk_id += 1

            chunk_audio_file_path = temp_chunk_dir_path / f"chunk_{chunk_id}_fast.wav"
            chunk_transcription_file_path = temp_chunk_dir_path / f"chunk_{chunk_id}_transcription.txt"
            chunk_audio_files.append(chunk_audio_file_path)
            chunk_transcription_files.append(chunk_transcription_file_path)

            # Export audio chunk if it doesn't exist
            if not chunk_audio_file_path.exists():
                print(f"Exporting {self.config.audio_speed_multiplier}x speed audio chunk {chunk_id}: {start_ms}ms to {end_ms}ms to {chunk_audio_file_path}")
                current_chunk_segment = audio[start_ms:end_ms]
                # 指定倍速に変換
                current_chunk_segment = current_chunk_segment._spawn(
                    current_chunk_segment.raw_data, 
                    overrides={"frame_rate": int(current_chunk_segment.frame_rate * self.config.audio_speed_multiplier)}
                )
                current_chunk_segment.export(chunk_audio_file_path, format="wav")
            else:
                print(f"{self.config.audio_speed_multiplier}x speed audio chunk {chunk_audio_file_path} already exists.")

            # Check for existing transcription or transcribe
            if chunk_transcription_file_path.exists():
                print(f"Found existing transcription for chunk {chunk_id}: {chunk_transcription_file_path}")
                try:
                    with open(chunk_transcription_file_path, "r", encoding="utf-8") as f:
                        transcription_part = f.read()
                except IOError as e:
                    print(f"Error reading existing transcription {chunk_transcription_file_path}: {e}. Retranscribing.")
                    transcription_part = self.transcribe_chunk(chunk_audio_file_path, chunk_transcription_file_path)
            else:
                print(f"Transcribing {self.config.audio_speed_multiplier}x speed chunk {chunk_id}: {chunk_audio_file_path}")
                transcription_part = self.transcribe_chunk(chunk_audio_file_path, chunk_transcription_file_path)

            all_transcriptions.append(transcription_part)

            if end_ms == duration_ms:
                break
            start_ms = max(0, end_ms - self.OVERLAP_MS)
            if start_ms >= duration_ms:
                break

        expected_cost_reduction = int((1 - (1 / self.config.audio_speed_multiplier)) * 100)
        print(f"Processed {len(all_transcriptions)} {self.config.audio_speed_multiplier}x speed chunks. Expected ~{expected_cost_reduction}% API cost reduction.")
        full_transcription = "\n\n".join(filter(None, all_transcriptions))
        return full_transcription
    
    def build_enhanced_prompt(self, base_template: str, transcription_text: str, recording_datetime: Optional[datetime.datetime] = None) -> str:
        """コンテキスト情報を含む拡張プロンプトを構築"""
        context_files = self.config.get_context_files()
        
        # 日時情報を設定
        event_date = ""
        event_time = ""
        event_location = "[音声内容から推測してください]"
        
        if recording_datetime:
            event_date = recording_datetime.strftime("%Y年%m月%d日")
            event_time = recording_datetime.strftime("%H:%M")
        
        # プレースホルダーを置換
        enhanced_prompt = base_template
        enhanced_prompt = enhanced_prompt.replace("{{SPEAKER_INFO}}", context_files['speaker_info'])
        enhanced_prompt = enhanced_prompt.replace("{{DOMAIN_CONTEXT}}", context_files['domain_context'])
        enhanced_prompt = enhanced_prompt.replace("{{CUSTOM_INSTRUCTIONS}}", context_files['custom_instructions'])
        enhanced_prompt = enhanced_prompt.replace("{{EVENT_DATE}}", event_date)
        enhanced_prompt = enhanced_prompt.replace("{{EVENT_TIME}}", event_time)
        enhanced_prompt = enhanced_prompt.replace("{{EVENT_LOCATION}}", event_location)
        enhanced_prompt = enhanced_prompt.replace("{{TRANSCRIPTION}}", transcription_text)
        
        return enhanced_prompt
    
    def summarize_text(self, text: str, prompt_template: str, recording_datetime: Optional[datetime.datetime] = None) -> str:
        """文字起こしテキストの要約"""
        print("Building enhanced prompt with context information...")
        
        enhanced_prompt = self.build_enhanced_prompt(prompt_template, text, recording_datetime)
        
        print("Summarizing text...")
        response = self.model.generate_content(enhanced_prompt)
        if response.candidates and response.candidates[0].content.parts:
            return response.candidates[0].content.parts[0].text
        else:
            raise ValueError("Summarization failed or returned an empty response.")
    
    def generate_filename_from_summary(self, summary_text: str) -> Optional[str]:
        """要約からファイル名を生成"""
        print("Generating filename from summary...")
        prompt = (
            f"以下の要約内容の最も重要なトピックを反映した、具体的で短い日本語のファイル名を**一つだけ作成**してください。"
            f"ファイル名は、{self.MAX_FILENAME_LENGTH}文字以内の**一つの連続した文字列**とし、日本語、英数字、アンダースコア、ハイフンのみを使用してください。"
            f"拡張子は含めないでください。\n\n"
            f"例: AI戦略会議議事録\n\n"
            f"要約内容:\n{summary_text[:1000]}"
            f"\n\n作成ファイル名:"
        )
        try:
            response = self.model.generate_content(prompt)
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
    
    def sanitize_filename(self, filename_suggestion: str) -> str:
        """ファイル名のサニタイズ"""
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
        text = text[:self.MAX_FILENAME_LENGTH]
        if not text:
            return "untitled_summary"
        return text
