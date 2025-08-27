#!/usr/bin/env python3
"""
デイリーノートの時刻順ソート機能をテストするスクリプト
"""

import os
import sys
import datetime
import tempfile
import pathlib

# スクリプトディレクトリをパスに追加
sys.path.append('/Users/okky_1_2/dev/AppLaud/script')

from daily_note_utils import add_link_to_daily_note

def test_time_sorting():
    """時刻順ソート機能のテスト"""
    print("=== デイリーノート時刻順ソート機能テスト ===")
    
    # テスト用の一時ディレクトリを作成
    with tempfile.TemporaryDirectory() as temp_dir:
        # 環境変数を設定
        os.environ['OBSIDIAN_DAILY_NOTES_DIR'] = temp_dir
        os.environ['DAILY_NOTE_FILENAME_PATTERN'] = 'test-%Y-%m-%d.md'
        os.environ['DAILY_NOTE_HEADING'] = '## 🎙️ テスト記録'
        os.environ['CREATE_DAILY_NOTE_IF_NOT_EXISTS'] = 'true'
        os.environ['DAILY_NOTE_TEMPLATE'] = '# テスト日記\n\n## 🎙️ テスト記録\n\n'
        
        # テスト日時
        test_date = datetime.datetime(2025, 8, 25, 0, 0, 0)
        
        # 異なる時刻の議事録を追加（意図的に時系列順ではない順序で追加）
        test_recordings = [
            ("会議3_午後", datetime.datetime(2025, 8, 25, 15, 30, 0)),  # 15:30
            ("会議1_朝", datetime.datetime(2025, 8, 25, 9, 15, 0)),     # 09:15
            ("会議4_夕方", datetime.datetime(2025, 8, 25, 18, 45, 0)),  # 18:45
            ("会議2_昼", datetime.datetime(2025, 8, 25, 12, 0, 0)),     # 12:00
            ("会議5_時刻なし", None),  # 時刻情報なし
        ]
        
        print("テスト議事録を時系列順ではない順序で追加中...")
        for filename, recording_time in test_recordings:
            print(f"  追加中: {filename}.md ({recording_time.strftime('%H:%M') if recording_time else '時刻なし'})")
            success = add_link_to_daily_note(f"{filename}.md", recording_time)
            if not success:
                print(f"    ⚠️ 追加失敗: {filename}")
        
        # 結果を確認
        daily_note_path = pathlib.Path(temp_dir) / 'test-2025-08-25.md'
        if daily_note_path.exists():
            print(f"\n生成されたデイリーノート: {daily_note_path}")
            with open(daily_note_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            print("\n=== デイリーノート内容 ===")
            print(content)
            print("=== 内容終了 ===")
            
            # 時刻順になっているかチェック
            lines = content.split('\n')
            links = []
            for line in lines:
                if line.strip().startswith('- [[') and ']]' in line:
                    links.append(line.strip())
            
            print(f"\n抽出されたリンク（{len(links)}個）:")
            for i, link in enumerate(links, 1):
                print(f"  {i}. {link}")
            
            # 期待される順序をチェック
            expected_order = [
                "- [[会議1_朝]] (09:15)",
                "- [[会議2_昼]] (12:00)", 
                "- [[会議3_午後]] (15:30)",
                "- [[会議4_夕方]] (18:45)",
                "- [[会議5_時刻なし]]"
            ]
            
            print(f"\n期待される順序:")
            for i, expected in enumerate(expected_order, 1):
                print(f"  {i}. {expected}")
            
            # 結果判定
            if links == expected_order:
                print("\n✅ テスト成功: リンクが正しく時刻順にソートされています")
                return True
            else:
                print("\n❌ テスト失敗: リンクの順序が期待と異なります")
                return False
        else:
            print(f"\n❌ テスト失敗: デイリーノートが作成されませんでした")
            return False

if __name__ == "__main__":
    success = test_time_sorting()
    sys.exit(0 if success else 1)
