#!/usr/bin/env python3
"""
設定管理クラス - 環境変数の統一管理
"""

import os
import pathlib
from typing import Optional


class ConfigManager:
    """アプリケーション設定の統一管理クラス"""
    
    def __init__(self):
        """設定を初期化"""
        self._load_config()
    
    def _load_config(self):
        """環境変数から設定を読み込み"""
        # API設定
        self.google_api_key = os.getenv("GOOGLE_API_KEY")
        
        # ディレクトリ設定
        self.audio_dest_dir = os.getenv("AUDIO_DEST_DIR")
        self.markdown_output_dir = os.getenv("MARKDOWN_OUTPUT_DIR")
        self.processed_log_file = os.getenv("PROCESSED_LOG_FILE")
        
        # 一時ディレクトリ設定
        self.temp_chunk_base_dir = os.getenv("TEMP_CHUNK_BASE_DIR", ".tmp_chunks")
        
        # 処理済みファイル移動先
        self.processed_files_dir = os.getenv("PROCESSED_FILES_DIR")
        if not self.processed_files_dir and self.audio_dest_dir:
            self.processed_files_dir = os.path.join(self.audio_dest_dir, "done")
        
        # ログファイル設定
        self.log_file_path = os.getenv("LOG_FILE_PATH")
        if not self.log_file_path and self.processed_log_file:
            # processed_log_fileと同じディレクトリにログファイルを作成
            log_dir = os.path.dirname(self.processed_log_file)
            self.log_file_path = os.path.join(log_dir, "processing.log")
        
        # プロンプト設定
        self.summary_prompt_file_path = os.getenv("SUMMARY_PROMPT_FILE_PATH")
        self.prompt_template_path = os.getenv("PROMPT_TEMPLATE_PATH")
        
        # 録音ファイル設定
        self.recording_filename_pattern = os.getenv("RECORDING_FILENAME_PATTERN")
        self.audio_speed_multiplier = float(os.getenv("AUDIO_SPEED_MULTIPLIER", "2.0"))
        
        # 議事録ファイル名フォーマット設定
        self.markdown_filename_format = os.getenv("MARKDOWN_FILENAME_FORMAT", "{date}_{title}")
        
        # Obsidianデイリーノート設定
        self.obsidian_daily_notes_dir = os.getenv("OBSIDIAN_DAILY_NOTES_DIR")
        self.daily_note_filename_pattern = os.getenv("DAILY_NOTE_FILENAME_PATTERN", "%Y-%m-%d.md")
        self.daily_note_heading = os.getenv("DAILY_NOTE_HEADING", "## 🎙️ 音声記録")
        self.create_daily_note_if_not_exists = os.getenv("CREATE_DAILY_NOTE_IF_NOT_EXISTS", "true").lower() == "true"
        self.daily_note_template = os.getenv("DAILY_NOTE_TEMPLATE", "# %Y年%m月%d日\n\n## 🎙️ 音声記録\n\n")
    
    def validate_required_settings(self):
        """必須設定の検証"""
        missing = []
        
        if not self.google_api_key:
            missing.append("GOOGLE_API_KEY")
        if not self.markdown_output_dir:
            missing.append("MARKDOWN_OUTPUT_DIR")
            
        if missing:
            error_msg = f"Missing required environment variables: {', '.join(missing)}"
            print(f"Error: {error_msg}")
            raise ValueError(error_msg)
        
        print("All required settings validated successfully.")
    
    def get_prompt_dir(self) -> pathlib.Path:
        """プロンプトディレクトリのパスを取得"""
        script_dir = pathlib.Path(__file__).parent
        return script_dir.parent / "prompt"
    
    def load_context_file(self, filename: str) -> str:
        """コンテキストファイルを読み込み"""
        try:
            file_path = self.get_prompt_dir() / filename
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    return content if content else ""
            return ""
        except Exception as e:
            print(f"Warning: Could not read context file {filename}: {e}")
            return ""
    
    def get_context_files(self) -> dict[str, str]:
        """全コンテキストファイルを読み込み"""
        return {
            'speaker_info': self.load_context_file('speaker_info.txt'),
            'domain_context': self.load_context_file('domain_context.txt'),
            'custom_instructions': self.load_context_file('custom_instructions.txt')
        }
    
