#!/usr/bin/env python3
"""
デイリーノート関連のユーティリティ関数
"""

import os
import datetime
import pathlib
import re


def generate_daily_note_filename(target_date, filename_pattern):
    """
    日本語曜日対応のデイリーノートファイル名を生成する
    
    Args:
        target_date (datetime): 対象日時
        filename_pattern (str): ファイル名パターン（%J = 日本語曜日）
    
    Returns:
        str: 生成されたファイル名
    """
    # 日本語曜日のマッピング
    japanese_weekdays = {
        0: '月',  # Monday
        1: '火',  # Tuesday
        2: '水',  # Wednesday
        3: '木',  # Thursday
        4: '金',  # Friday
        5: '土',  # Saturday
        6: '日'   # Sunday
    }
    
    # %J（日本語曜日）を実際の曜日に置換
    if '%J' in filename_pattern:
        weekday_jp = japanese_weekdays[target_date.weekday()]
        filename_pattern = filename_pattern.replace('%J', weekday_jp)
    
    # 通常のstrftimeで残りの部分を処理
    return target_date.strftime(filename_pattern)


def add_link_to_daily_note(markdown_filename, recording_datetime=None):
    """
    Obsidianのデイリーノートに議事録へのリンクを時刻順で追加する
    
    Args:
        markdown_filename (str): 生成されたMarkdownファイル名
        recording_datetime (datetime): 録音日時（デイリーノートの日付決定に使用）
    
    Returns:
        bool: 成功した場合True、失敗した場合False
    """
    # 環境変数から設定を読み込み
    daily_notes_dir = os.environ.get('OBSIDIAN_DAILY_NOTES_DIR')
    filename_pattern = os.environ.get('DAILY_NOTE_FILENAME_PATTERN', '%Y-%m-%d.md')
    heading = os.environ.get('DAILY_NOTE_HEADING', '## 🎙️ 音声記録')
    create_if_not_exists = os.environ.get('CREATE_DAILY_NOTE_IF_NOT_EXISTS', 'true').lower() == 'true'
    template = os.environ.get('DAILY_NOTE_TEMPLATE', '# %Y年%m月%d日\n\n## 🎙️ 音声記録\n\n')
    
    if not daily_notes_dir:
        print("Warning: OBSIDIAN_DAILY_NOTES_DIR not set. Skipping daily note update.")
        return False
    
    # 日付を決定（録音日時があればそれを使用、なければ現在日時）
    target_date = recording_datetime if recording_datetime else datetime.datetime.now()
    
    # デイリーノートのファイルパスを生成（日本語曜日対応）
    daily_note_filename = generate_daily_note_filename(target_date, filename_pattern)
    daily_note_path = pathlib.Path(daily_notes_dir) / daily_note_filename
    
    # ディレクトリが存在しない場合は作成
    daily_note_path.parent.mkdir(parents=True, exist_ok=True)
    
    # デイリーノートが存在しない場合の処理
    if not daily_note_path.exists():
        if create_if_not_exists:
            # テンプレートから新しいデイリーノートを作成（日本語曜日対応）
            template_content = generate_daily_note_filename(target_date, template)
            with open(daily_note_path, 'w', encoding='utf-8') as f:
                f.write(template_content)
            print(f"Created new daily note: {daily_note_path}")
        else:
            print(f"Daily note does not exist and creation is disabled: {daily_note_path}")
            return False
    
    # デイリーノートの内容を読み込み
    with open(daily_note_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 議事録へのリンクを作成（Obsidianの内部リンク形式）
    # ファイル名から拡張子を除去してリンクを作成
    link_name = pathlib.Path(markdown_filename).stem
    link_text = f"- [[{link_name}]]"
    
    # 録音時刻があれば追加
    if recording_datetime:
        time_str = recording_datetime.strftime('%H:%M')
        link_text += f" ({time_str})"
    
    link_text += "\n"
    
    # 既に同じリンクが存在するかチェック
    if link_name in content:
        print(f"Link already exists in daily note: {link_name}")
        return False
    
    # 指定された見出しの下にリンクを時系列順で追加
    lines = content.split('\n')
    heading_found = False
    heading_index = -1
    
    for i, line in enumerate(lines):
        if line.strip() == heading.strip():
            heading_found = True
            heading_index = i
            break
    
    if not heading_found:
        # 見出しが見つからない場合は末尾に追加
        if content and not content.endswith('\n'):
            content += '\n'
        content += f"\n{heading}\n{link_text}\n"
    else:
        # 既存のリンクを抽出して時刻順にソート
        existing_links = []
        link_start_index = heading_index + 1
        link_end_index = len(lines)
        
        # 次の見出しまでの範囲を特定
        for j in range(heading_index + 1, len(lines)):
            if lines[j].strip().startswith('##'):
                link_end_index = j
                break
        
        # 既存のリンクを抽出
        for j in range(link_start_index, link_end_index):
            line = lines[j].strip()
            if line.startswith('- [[') and ']]' in line:
                # 時刻情報を抽出
                time_match = re.search(r'\((\d{2}:\d{2})\)', line)
                if time_match:
                    time_str = time_match.group(1)
                    hour, minute = map(int, time_str.split(':'))
                    time_minutes = hour * 60 + minute
                else:
                    time_minutes = 9999  # 時刻がない場合は最後に配置
                
                existing_links.append((time_minutes, line))
        
        # 新しいリンクの時刻を計算
        if recording_datetime:
            new_time_minutes = recording_datetime.hour * 60 + recording_datetime.minute
        else:
            new_time_minutes = 9999
        
        # 新しいリンクを追加してソート
        existing_links.append((new_time_minutes, link_text.rstrip()))
        existing_links.sort(key=lambda x: x[0])
        
        # 見出し以降のリンク部分を置き換え
        # まず既存のリンクを削除
        del lines[link_start_index:link_end_index]
        
        # ソートされたリンクを挿入
        for i, (_, link_line) in enumerate(existing_links):
            lines.insert(link_start_index + i, link_line)
        
        # 最後のリンクの後に空行を確保
        last_link_index = link_start_index + len(existing_links) - 1
        next_heading_index = None
        
        for j in range(last_link_index + 1, len(lines)):
            if lines[j].strip().startswith('##'):
                next_heading_index = j
                break
        
        if next_heading_index is not None:
            # 次の見出しがある場合、その前に空行があるかチェック
            if next_heading_index > last_link_index + 1 and lines[next_heading_index - 1].strip() != '':
                lines.insert(next_heading_index, "")
        else:
            # ファイル末尾の場合、最後に空行を追加
            if last_link_index + 1 >= len(lines) or (last_link_index + 1 < len(lines) and lines[-1].strip() != ''):
                lines.append("")
        
        content = '\n'.join(lines)
    
    # デイリーノートを更新
    with open(daily_note_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Added link to daily note: {daily_note_path}")
    print(f"Link: {link_text.strip()}")
    return True
