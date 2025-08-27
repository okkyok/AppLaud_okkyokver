#!/usr/bin/env python3
"""
ファイル管理クラス - Markdownファイルの保存とディレクトリ管理
"""

import datetime
import pathlib
import shutil
import tempfile
from typing import Optional

import yaml

from config_manager import ConfigManager


class FileManager:
    """ファイル操作を担当するクラス"""
    
    def __init__(self, config: ConfigManager):
        """初期化"""
        self.config = config
    
    def create_temp_chunk_directory(self, audio_file_path: str) -> pathlib.Path:
        """音声チャンク用の一時ディレクトリを作成"""
        audio_file_stem = pathlib.Path(audio_file_path).stem
        temp_chunk_dir = pathlib.Path(self.config.temp_chunk_base_dir) / audio_file_stem
        temp_chunk_dir.mkdir(parents=True, exist_ok=True)
        print(f"Created temp chunk directory: {temp_chunk_dir}")
        return temp_chunk_dir
    
    def cleanup_temp_directory(self, temp_dir: pathlib.Path):
        """一時ディレクトリのクリーンアップ"""
        if temp_dir.exists():
            try:
                shutil.rmtree(temp_dir)
                print(f"Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                print(f"Warning: Failed to clean up temp directory {temp_dir}: {e}")
    
    def save_markdown(self, summary_text: str, filename_suggestion: str, 
                     recording_datetime: Optional[datetime.datetime] = None) -> str:
        """Markdownファイルの保存"""
        # ファイル名のサニタイズ
        sanitized_title = self._sanitize_filename(filename_suggestion)
        
        # 録音日時から日付を生成
        if recording_datetime:
            date_str = recording_datetime.strftime("%Y%m%d")
        else:
            # 録音日時がない場合は現在日時を使用
            date_str = datetime.datetime.now().strftime("%Y%m%d")
        
        # 設定からファイル名フォーマットを取得して適用
        filename_format = self.config.markdown_filename_format
        final_filename = filename_format.format(date=date_str, title=sanitized_title)
        
        # 出力パスの決定
        output_dir = pathlib.Path(self.config.markdown_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        markdown_file_path = output_dir / f"{final_filename}.md"
        
        # 重複ファイル名の処理
        counter = 1
        original_path = markdown_file_path
        while markdown_file_path.exists():
            # 重複時は元のフォーマットに_番号を追加
            duplicate_filename = filename_format.format(date=date_str, title=f"{sanitized_title}_{counter}")
            markdown_file_path = original_path.parent / f"{duplicate_filename}.md"
            counter += 1
        
        # YAMLフロントマターの作成（元のタイトルを使用）
        yaml_frontmatter = self._create_yaml_frontmatter(
            filename_suggestion, recording_datetime
        )
        
        # Markdownコンテンツの作成
        markdown_content = f"---\n{yaml.dump(yaml_frontmatter, allow_unicode=True, default_flow_style=False)}---\n\n{summary_text}"
        
        # ファイルの保存
        try:
            with open(markdown_file_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            print(f"Markdown saved to: {markdown_file_path}")
            return str(markdown_file_path)
        except IOError as e:
            raise IOError(f"Failed to save markdown to {markdown_file_path}: {e}")
    
    def _create_yaml_frontmatter(self, title: str, 
                                recording_datetime: Optional[datetime.datetime]) -> dict:
        """YAMLフロントマターの作成"""
        now = datetime.datetime.now()
        frontmatter = {
            "title": title,
            "created": now.strftime("%Y-%m-%d %H:%M:%S"),
            "tags": ["音声記録", "議事録"]
        }
        
        # 録音日時情報の追加
        if recording_datetime:
            frontmatter.update({
                "recording_date": recording_datetime.strftime("%Y-%m-%d"),
                "recording_time": recording_datetime.strftime("%H:%M:%S"),
                "recording_datetime": recording_datetime.strftime("%Y-%m-%d %H:%M:%S")
            })
        
        return frontmatter
    
    def _sanitize_filename(self, filename_suggestion: str) -> str:
        """ファイル名のサニタイズ"""
        import re
        
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
        max_length = 50
        text = text[:max_length]
        if not text:
            return "untitled_summary"
        return text
    
    def save_log(self, message: str, log_type: str = "info"):
        """ログメッセージの保存"""
        if not self.config.log_file_path:
            return
        
        log_dir = pathlib.Path(self.config.log_file_path).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{log_type.upper()}] {message}\n"
        
        try:
            with open(self.config.log_file_path, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except IOError as e:
            print(f"Warning: Failed to write to log file: {e}")
    
    def ensure_directory_exists(self, directory_path: str):
        """ディレクトリの存在確認・作成"""
        path = pathlib.Path(directory_path)
        path.mkdir(parents=True, exist_ok=True)
    
    def get_audio_files(self, directory: str, extensions: list = None) -> list:
        """指定ディレクトリから音声ファイルを取得"""
        if extensions is None:
            extensions = ['.wav', '.mp3', '.m4a', '.flac', '.aac']
        
        directory_path = pathlib.Path(directory)
        if not directory_path.exists():
            return []
        
        audio_files = []
        for ext in extensions:
            audio_files.extend(directory_path.glob(f"*{ext}"))
            audio_files.extend(directory_path.glob(f"*{ext.upper()}"))
        
        return sorted(audio_files)
    
    def move_processed_file(self, source_path: str, processed_dir: str):
        """処理済みファイルの移動"""
        source = pathlib.Path(source_path)
        if not source.exists():
            print(f"Warning: Source file does not exist: {source_path}")
            return
        
        processed_path = pathlib.Path(processed_dir)
        processed_path.mkdir(parents=True, exist_ok=True)
        
        destination = processed_path / source.name
        
        # 重複ファイル名の処理
        counter = 1
        original_destination = destination
        while destination.exists():
            stem = original_destination.stem
            suffix = original_destination.suffix
            destination = original_destination.parent / f"{stem}_{counter}{suffix}"
            counter += 1
        
        try:
            shutil.move(str(source), str(destination))
            print(f"Moved processed file: {source} -> {destination}")
        except Exception as e:
            print(f"Warning: Failed to move processed file {source} to {destination}: {e}")
