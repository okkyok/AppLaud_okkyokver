#!/usr/bin/env python3
"""
メインスクリプト - 音声ファイルの文字起こし・要約・保存処理
"""

import argparse
import sys
import pathlib
import datetime

from config_manager import ConfigManager
from audio_processor import AudioProcessor
from file_manager import FileManager
from daily_note_utils import add_link_to_daily_note





























def main():
    """メイン処理関数"""
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

    try:
        # 設定管理の初期化
        config = ConfigManager()
        config.validate_required_settings()
        
        # クラスの初期化
        audio_processor = AudioProcessor(config)
        file_manager = FileManager(config)
        
        # 処理ディレクトリの設定
        processing_dir = pathlib.Path(args.audio_processing_dir)
        
        # 音声ファイルの取得
        audio_files = file_manager.get_audio_files(str(processing_dir))
        
        if not audio_files:
            print(f"No audio files found in {processing_dir}")
            return
        
        print(f"Found {len(audio_files)} audio files to process")
        
        # プロンプトテンプレートの読み込み
        with open(args.summary_prompt_file_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()
        
        # 各音声ファイルの処理
        for audio_file in audio_files:
            print(f"\n--- Processing file: {audio_file.name} ---")
            
            try:
                # 一時ディレクトリの作成
                temp_dir = file_manager.create_temp_chunk_directory(str(audio_file))
                
                # 録音日時の抽出
                recording_datetime = audio_processor.extract_recording_datetime_from_filename(
                    audio_file.name
                )
                
                # 文字起こし
                transcription = audio_processor.transcribe_audio(
                    str(audio_file), temp_dir
                )
                
                # 要約
                summary = audio_processor.summarize_text(
                    transcription, prompt_template, recording_datetime
                )
                
                # ファイル名生成
                filename_suggestion = audio_processor.generate_filename_from_summary(summary)
                if not filename_suggestion:
                    filename_suggestion = f"summary_{audio_file.stem}"
                
                # Markdownファイルの保存
                markdown_path = file_manager.save_markdown(
                    summary, filename_suggestion, recording_datetime
                )
                
                # デイリーノートへのリンク追加
                if config.obsidian_daily_notes_dir:
                    add_link_to_daily_note(markdown_path, recording_datetime)
                
                # 処理済みファイルの移動
                if config.processed_files_dir:
                    file_manager.move_processed_file(
                        str(audio_file), config.processed_files_dir
                    )
                
                # ログ記録
                file_manager.save_log(
                    f"Successfully processed {audio_file.name} -> {pathlib.Path(markdown_path).name}",
                    "info"
                )
                
                print(f"Successfully processed: {audio_file.name}")
                
            except Exception as e:
                error_msg = f"Error processing {audio_file.name}: {e}"
                print(error_msg)
                file_manager.save_log(error_msg, "error")
                continue
            
            finally:
                # 一時ディレクトリのクリーンアップ
                if 'temp_dir' in locals():
                    file_manager.cleanup_temp_directory(temp_dir)
        
        print("\nProcessing completed.")
        
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
