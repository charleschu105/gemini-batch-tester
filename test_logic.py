# -*- coding: utf-8 -*-
import os
import shutil
import csv
import ast
import configparser
from main import parse_filename, append_to_csv, load_config, save_config

def test_parse_filename():
    print("Executing parse_filename tests...")
    
    # Test case 1: Standard 4 parts
    n, c, d, i = parse_filename("蘋果_食品_可口_01.jpg")
    assert n == "蘋果", f"Expected 蘋果, got {n}"
    assert c == "食品", f"Expected 食品, got {c}"
    assert d == "可口", f"Expected 可口, got {d}"
    assert i == "01", f"Expected 01, got {i}"
    
    # Test case 2: Expiry date description
    n, c, d, i = parse_filename("牛奶_食品_EX20260811_02.png")
    assert n == "牛奶", f"Expected 牛奶, got {n}"
    assert c == "食品", f"Expected 食品, got {c}"
    assert d == "EX20260811", f"Expected EX20260811, got {d}"
    assert i == "02", f"Expected 02, got {i}"

    # Test case 3: Multiple underscores in ID
    n, c, d, i = parse_filename("藍牙耳機_電子產品_全新_A_02_B.png")
    assert n == "藍牙耳機", f"Expected 藍牙耳機, got {n}"
    assert c == "電子產品", f"Expected 電子產品, got {c}"
    assert d == "全新", f"Expected 全新, got {d}"
    assert i == "A_02_B", f"Expected A_02_B, got {i}"

    # Test case 4: 3 parts (backfall)
    n, c, d, i = parse_filename("可樂_食品_03.png")
    assert n == "可樂", f"Expected 可樂, got {n}"
    assert c == "食品", f"Expected 食品, got {c}"
    assert d == "無", f"Expected 無, got {d}"
    assert i == "03", f"Expected 03, got {i}"

    # Test case 5: 2 parts (backfall)
    n, c, d, i = parse_filename("水_飲料.bmp")
    assert n == "水", f"Expected 水, got {n}"
    assert c == "飲料", f"Expected 飲料, got {c}"
    assert d == "無", f"Expected 無, got {d}"
    assert i == "未知", f"Expected 未知, got {i}"

    # Test case 6: 1 part (backfall)
    n, c, d, i = parse_filename("筆記本.bmp")
    assert n == "筆記本", f"Expected 筆記本, got {n}"
    assert c == "未知", f"Expected 未知, got {c}"
    assert d == "無", f"Expected 無, got {d}"
    assert i == "未知", f"Expected 未知, got {i}"

    print(" -> parse_filename tests: PASSED")

def test_config_logic():
    print("Executing config persistence tests...")
    
    # Backup existing config if exists
    config_backup_path = "config.ini.bak"
    has_backup = os.path.exists("config.ini")
    if has_backup:
        shutil.copy("config.ini", config_backup_path)
        os.remove("config.ini")

    try:
        # Load when no config exists (should load defaults)
        defaults = load_config()
        assert defaults["model_id"] == "gemini-3.5-flash", "Default model ID failed"
        assert defaults["api_key"] == "", "Default API key failed"
        assert "物品名稱" in defaults["prompt_template"], "Default prompt template failed"
        assert defaults["request_interval"] == "4.0", "Default request interval failed"
        
        # Save custom config
        save_config("custom-model-99", "AIzaSyTestKey123", "測試提示詞 {model_id}", "C:\\test\\path", "2.5")
        
        # Reload custom config
        custom_settings = load_config()
        assert custom_settings["model_id"] == "custom-model-99", "Saving model ID failed"
        assert custom_settings["api_key"] == "AIzaSyTestKey123", "Saving API key failed"
        assert custom_settings["prompt_template"] == "測試提示詞 {model_id}", "Saving prompt failed"
        assert custom_settings["folder_path"] == "C:\\test\\path", "Saving path failed"
        assert custom_settings["request_interval"] == "2.5", "Saving interval failed"
        
        print(" -> config persistence tests: PASSED")
    finally:
        # Restore backup
        if os.path.exists("config.ini"):
            os.remove("config.ini")
        if has_backup:
            shutil.copy(config_backup_path, "config.ini")
            os.remove(config_backup_path)

def test_csv_logic():
    print("Executing CSV writing tests...")
    temp_csv = "test_run_results.csv"
    if os.path.exists(temp_csv):
        os.remove(temp_csv)
        
    try:
        # 14 columns row:
        # [原物品名稱, 原分類, 原敘述, 原編號, 模型 ID, 辨識物品名稱, 辨識分類, 辨識信心度, 辨識有效日期, 辨識狀態, 錯誤訊息, 名稱比對, 類別比對, 過期日期比對]
        row_data_1 = ["蘋果", "食品", "EX2026-08-11", "01", "gemini-3.5-flash", "蘋果", "食品", "95%", "2026-08-11", "成功", "", "OK", "OK", "OK"]
        row_data_2 = ["未知", "未知", "無", "未知", "gemini-3.5-flash", "滑鼠", "電子產品", "80%", "無", "成功", "", "FAIL", "FAIL", "NA"]
        
        append_to_csv(temp_csv, row_data_1)
        append_to_csv(temp_csv, row_data_2)
        
        # Verify file contents
        assert os.path.exists(temp_csv), "CSV file was not created"
        
        with open(temp_csv, mode="r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)
            
        assert len(rows) == 3, f"Expected 3 rows (header + 2 data), got {len(rows)}"
        assert rows[0][0] == "原物品名稱", "Header check failed"
        assert rows[0][2] == "原敘述", f"Expected '原敘述' at index 2, got {rows[0][2]}"
        assert rows[1][0] == "蘋果", "Data row 1 Chinese encoding failed"
        assert rows[2][5] == "滑鼠", f"Expected '滑鼠' at index 5, got {rows[2][5]}"
        
        # Assert Match columns are at the end of the header
        assert rows[0][-3] == "名稱比對", f"Expected '名稱比對' at third to last, got {rows[0][-3]}"
        assert rows[0][-2] == "類別比對", f"Expected '類別比對' at second to last, got {rows[0][-2]}"
        assert rows[0][-1] == "過期日期比對", f"Expected '過期日期比對' at last column, got {rows[0][-1]}"
        
        # Assert values
        assert rows[1][-3] == "OK", f"Expected 'OK' for name match, got {rows[1][-3]}"
        assert rows[1][-2] == "OK", f"Expected 'OK' for category match, got {rows[1][-2]}"
        assert rows[1][-1] == "OK", f"Expected 'OK' for expiry match, got {rows[1][-1]}"
        
        assert rows[2][-3] == "FAIL", f"Expected 'FAIL' for name match, got {rows[2][-3]}"
        assert rows[2][-2] == "FAIL", f"Expected 'FAIL' for category match, got {rows[2][-2]}"
        assert rows[2][-1] == "NA", f"Expected 'NA' for expiry match, got {rows[2][-1]}"
        
        print(" -> CSV writing tests: PASSED")
    finally:
        if os.path.exists(temp_csv):
            os.remove(temp_csv)

if __name__ == "__main__":
    test_parse_filename()
    test_config_logic()
    test_csv_logic()
    print("\nALL LOGIC UNIT TESTS PASSED!")
