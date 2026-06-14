# -*- coding: utf-8 -*-
import os
import sys
import re
import csv
import json
import ast
import threading
import configparser
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from PIL import Image, ImageTk
from google import genai
from google.genai import types
import webbrowser
import time

# ---------------------------------------------------------
# 1. 系統設定與 INI 檔讀寫邏輯 (config.ini)
# ---------------------------------------------------------
CONFIG_FILE = "config.ini"

# 預設多行、易讀排版的提示詞範本
DEFAULT_PROMPT = (
    "辨識此物品。請只回傳 JSON 格式：\n"
    "{\n"
    "  'name': '物品名稱',\n"
    "  'category': '分類',\n"
    "  'expiry': '日期',\n"
    "  'model': '{model_id}',\n"
    "  'confidence': '信心度(0-100%)'\n"
    "}。\n\n"
    "分類僅限：食品、電子產品、生活用品、藥品、文具、化妝品、工具、其他。\n"
    "同種物品請用1號2號編碼。"
)

def load_config():
    """載入設定檔，若不存在則提供預設值"""
    config = configparser.ConfigParser(interpolation=None)
    defaults = {
        "model_id": "gemini-3.5-flash",
        "api_key": "",
        "prompt_template": DEFAULT_PROMPT,
        "folder_path": "",
        "request_interval": "4.0"
    }
    
    if not os.path.exists(CONFIG_FILE):
        config["Settings"] = defaults
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                config.write(f)
        except Exception as e:
            print(f"無法寫入預設設定檔: {e}")
        return defaults

    try:
        config.read(CONFIG_FILE, encoding="utf-8")
        settings = config["Settings"]
        api_key = settings.get("api_key", "").strip()
        if not api_key:
            api_key = defaults["api_key"]
            
        return {
            "model_id": settings.get("model_id", defaults["model_id"]),
            "api_key": api_key,
            "prompt_template": settings.get("prompt_template", defaults["prompt_template"]),
            "folder_path": settings.get("folder_path", defaults["folder_path"]),
            "request_interval": settings.get("request_interval", defaults["request_interval"])
        }
    except Exception as e:
        print(f"讀取設定檔失敗，將使用預設值: {e}")
        return defaults

def save_config(model_id, api_key, prompt_template, folder_path, request_interval):
    """保存當前設定至 config.ini"""
    config = configparser.ConfigParser(interpolation=None)
    config["Settings"] = {
        "model_id": model_id,
        "api_key": api_key,
        "prompt_template": prompt_template,
        "folder_path": folder_path,
        "request_interval": request_interval
    }
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            config.write(f)
    except Exception as e:
        print(f"儲存設定檔失敗: {e}")

# ---------------------------------------------------------
# 2. 核心檔案解析與 CSV 寫入輔助函數
# ---------------------------------------------------------
def parse_filename(filename):
    """
    依據「物品名稱_分類_敘述_編號.ext」規則解析檔名
    例如：蘋果_食品_可口_01.jpg -> (蘋果, 食品, 可口, 01)
    """
    name_without_ext, _ = os.path.splitext(filename)
    parts = name_without_ext.split('_')
    
    if len(parts) >= 4:
        target_name = parts[0]
        target_category = parts[1]
        target_desc = parts[2]
        # 若編號中含有底線，將剩餘部分重組
        target_id = "_".join(parts[3:])
        return target_name, target_category, target_desc, target_id
    elif len(parts) == 3:
        return parts[0], parts[1], "無", parts[2]
    elif len(parts) == 2:
        return parts[0], parts[1], "無", "未知"
    elif len(parts) == 1:
        return parts[0], "未知", "無", "未知"
    return "未知", "未知", "無", "未知"

def append_to_csv(csv_path, row_data):
    """安全地將單筆辨識結果追加寫入 CSV，使用 utf-8-sig 讓 Excel 開啟不亂碼"""
    file_exists = os.path.exists(csv_path)
    with open(csv_path, mode='a', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "原物品名稱", "原分類", "原敘述", "原編號", "模型 ID",
                "辨識物品名稱", "辨識分類", "辨識信心度", "辨識有效日期",
                "辨識狀態", "錯誤訊息", "名稱比對", "類別比對", "過期日期比對"
            ])
        writer.writerow(row_data)

# ---------------------------------------------------------
# 3. 視窗應用程式主類別 (CustomTkinter)
# ---------------------------------------------------------
class GeminiBatchTesterApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # 讀取持久化設定
        self.config_data = load_config()

        # 初始化控制狀態
        self.is_running = False
        self.worker_thread = None
        self.api_key_visible = False

        # 視窗基本設定
        self.title("Gemini 影像辨識批次測試工具")
        self.geometry("1100x600")
        self.minsize(980, 500)
        
        # 設置深色主題與青藍色強調色
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # 建立 UI 版面
        self.create_widgets()
        
        # 載入上次儲存的參數至 UI 中
        self.apply_config_to_ui()

    def create_widgets(self):
        # 設置格柵排版 (Grid Weights)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1) # 讓 Tabview 隨視窗縮放拉伸

        # --- 標題區 ---
        self.title_label = ctk.CTkLabel(
            self, 
            text="Gemini 影像辨識批次測試工具", 
            font=ctk.CTkFont(family="Microsoft JhengHei", size=22, weight="bold")
        )
        self.title_label.grid(row=0, column=0, padx=20, pady=(15, 2), sticky="ew")

        # --- Tabview 分頁控制 ---
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=1, column=0, padx=20, pady=(2, 15), sticky="nsew")
        
        self.tab_tester = self.tabview.add("批次測試")
        self.tab_info = self.tabview.add("金鑰與模型資訊")
        
        # 設置分頁的 grid 權重 (左欄配置區，右欄執行日誌區)
        self.tab_tester.grid_columnconfigure(0, weight=0, minsize=430) # 左欄固定最小寬度
        self.tab_tester.grid_columnconfigure(1, weight=1)              # 右欄自適應延展
        self.tab_tester.grid_rowconfigure(0, weight=1)                 # 整體高度自適應
        
        self.tab_info.grid_columnconfigure(0, weight=1)
        self.tab_info.grid_rowconfigure(1, weight=1) # 讓模型資訊文字框延展

        # =========================================================
        # 分頁一：批次測試 (tab_tester) - 左右橫版佈局
        # =========================================================

        # ---- 左側欄容器 (配置區) ----
        self.left_col_frame = ctk.CTkFrame(self.tab_tester, fg_color="transparent")
        self.left_col_frame.grid(row=0, column=0, padx=(5, 5), pady=5, sticky="nsew")
        self.left_col_frame.grid_columnconfigure(0, weight=1)

        # --- 區域一：模型與金鑰設定 (垂直堆疊) ---
        self.settings_frame = ctk.CTkFrame(self.left_col_frame)
        self.settings_frame.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        self.settings_frame.grid_columnconfigure(1, weight=1)

        # Model 選擇
        self.model_label = ctk.CTkLabel(self.settings_frame, text="模型選擇:", font=ctk.CTkFont(family="Microsoft JhengHei", size=13, weight="bold"))
        self.model_label.grid(row=0, column=0, padx=(15, 5), pady=(12, 6), sticky="w")
        
        models_list = [
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
            "gemini-3.1-flash-lite-preview",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
            "gemma-4-26b-a4b-it",
            "gemma-4-31b-it"
        ]
        self.model_combo = ctk.CTkComboBox(self.settings_frame, values=models_list, font=ctk.CTkFont(size=12))
        self.model_combo.grid(row=0, column=1, padx=(5, 15), pady=(12, 6), sticky="ew")

        # API KEY 填入
        self.key_label = ctk.CTkLabel(self.settings_frame, text="Gemini Key:", font=ctk.CTkFont(family="Microsoft JhengHei", size=13, weight="bold"))
        self.key_label.grid(row=1, column=0, padx=(15, 5), pady=(6, 12), sticky="w")

        # 金鑰輸入容器 (放置 Entry 與 眼睛切換按鈕)
        self.key_container = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.key_container.grid(row=1, column=1, padx=(5, 15), pady=(6, 12), sticky="ew")
        self.key_container.grid_columnconfigure(0, weight=1)

        self.key_entry = ctk.CTkEntry(self.key_container, placeholder_text="請填入 Gemini API 金鑰...", show="*")
        self.key_entry.grid(row=0, column=0, sticky="ew")

        self.toggle_key_btn = ctk.CTkButton(
            self.key_container, 
            text="👁", 
            width=30, 
            fg_color="gray30", 
            hover_color="gray40", 
            command=self.toggle_api_key_visibility
        )
        self.toggle_key_btn.grid(row=0, column=1, padx=(5, 0))

        # 獲取 API 金鑰超連結
        self.get_key_link = ctk.CTkLabel(
            self.settings_frame, 
            text="👉 點此獲取 Gemini API 金鑰 (https://aistudio.google.com/app/api-keys)", 
            font=ctk.CTkFont(family="Microsoft JhengHei", size=11, underline=True),
            text_color="#63a5ff",
            cursor="hand2"
        )
        self.get_key_link.grid(row=2, column=0, columnspan=2, padx=(15, 15), pady=(0, 10), sticky="w")
        self.get_key_link.bind("<Button-1>", lambda e: webbrowser.open("https://aistudio.google.com/app/api-keys"))

        # 請求間隔設定
        self.interval_label = ctk.CTkLabel(self.settings_frame, text="請求間隔 (秒):", font=ctk.CTkFont(family="Microsoft JhengHei", size=13, weight="bold"))
        self.interval_label.grid(row=3, column=0, padx=(15, 5), pady=(6, 12), sticky="w")
        
        self.interval_entry = ctk.CTkEntry(self.settings_frame, placeholder_text="預設 4.0 秒...")
        self.interval_entry.grid(row=3, column=1, padx=(5, 15), pady=(6, 12), sticky="ew")

        # --- 區域二：提示詞範本設定 ---
        self.prompt_frame = ctk.CTkFrame(self.left_col_frame)
        self.prompt_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        self.prompt_frame.grid_columnconfigure(0, weight=1)
        self.prompt_frame.grid_columnconfigure(1, weight=0)

        self.prompt_label = ctk.CTkLabel(self.prompt_frame, text="影像辨識提示詞 (Prompt):", font=ctk.CTkFont(family="Microsoft JhengHei", size=13, weight="bold"))
        self.prompt_label.grid(row=0, column=0, padx=15, pady=(8, 4), sticky="w")

        self.restore_prompt_btn = ctk.CTkButton(
            self.prompt_frame, 
            text="回復預設", 
            width=80,
            height=22,
            fg_color="gray30",
            hover_color="gray40",
            font=ctk.CTkFont(family="Microsoft JhengHei", size=11),
            command=self.restore_default_prompt
        )
        self.restore_prompt_btn.grid(row=0, column=1, padx=15, pady=(8, 4), sticky="e")

        self.prompt_text = ctk.CTkTextbox(self.prompt_frame, height=110, font=ctk.CTkFont(size=12))
        self.prompt_text.grid(row=1, column=0, columnspan=2, padx=15, pady=(4, 12), sticky="ew")

        # --- 區域三：資料夾與實驗名稱設定 ---
        self.folder_frame = ctk.CTkFrame(self.left_col_frame)
        self.folder_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        self.folder_frame.grid_columnconfigure(1, weight=1)

        self.folder_label = ctk.CTkLabel(self.folder_frame, text="圖檔資料夾:", font=ctk.CTkFont(family="Microsoft JhengHei", size=13, weight="bold"))
        self.folder_label.grid(row=0, column=0, padx=(15, 5), pady=10, sticky="w")

        self.folder_entry = ctk.CTkEntry(self.folder_frame, placeholder_text="請選擇圖檔所在的資料夾路徑...")
        self.folder_entry.grid(row=0, column=1, padx=(5, 5), pady=10, sticky="ew")
        self.folder_entry.bind("<KeyRelease>", lambda event: self.update_experiment_info())

        self.browse_btn = ctk.CTkButton(
            self.folder_frame, 
            text="瀏覽...", 
            width=60, 
            command=self.browse_folder
        )
        self.browse_btn.grid(row=0, column=2, padx=(5, 15), pady=10)

        # 實驗詳情即時顯示
        self.info_label = ctk.CTkLabel(
            self.folder_frame, 
            text="實驗名稱: - | 偵測圖檔: 0 張", 
            font=ctk.CTkFont(family="Microsoft JhengHei", size=11, slant="italic"),
            text_color="gray60"
        )
        self.info_label.grid(row=1, column=0, columnspan=3, padx=15, pady=(0, 8), sticky="w")


        # ---- 右側欄容器 (執行與日誌區) ----
        self.right_col_frame = ctk.CTkFrame(self.tab_tester, fg_color="transparent")
        self.right_col_frame.grid(row=0, column=1, padx=(5, 5), pady=5, sticky="nsew")
        self.right_col_frame.grid_columnconfigure(0, weight=1)
        self.right_col_frame.grid_rowconfigure(2, weight=1) # 讓日誌框隨高度自適應延展

        # --- 區域四：控制按鈕與進度條 ---
        self.control_frame = ctk.CTkFrame(self.right_col_frame)
        self.control_frame.grid(row=0, column=0, padx=10, pady=(5, 5), sticky="ew")
        self.control_frame.grid_columnconfigure(0, weight=1)

        # 控制列 (按鈕與進度資訊並排)
        self.action_container = ctk.CTkFrame(self.control_frame, fg_color="transparent")
        self.action_container.grid(row=0, column=0, padx=15, pady=(10, 4), sticky="ew")
        self.action_container.grid_columnconfigure(1, weight=1)

        self.run_btn = ctk.CTkButton(
            self.action_container, 
            text="開始批次辨識", 
            font=ctk.CTkFont(family="Microsoft JhengHei", size=13, weight="bold"),
            fg_color="#1f538d",
            hover_color="#153c66",
            height=30,
            command=self.toggle_execution
        )
        self.run_btn.grid(row=0, column=0, padx=(0, 15), sticky="w")

        self.status_text_label = ctk.CTkLabel(
            self.action_container, 
            text="等待執行...", 
            font=ctk.CTkFont(family="Microsoft JhengHei", size=13),
            anchor="w"
        )
        self.status_text_label.grid(row=0, column=1, sticky="ew")

        # 進度條
        self.progress_bar = ctk.CTkProgressBar(self.control_frame)
        self.progress_bar.grid(row=1, column=0, padx=15, pady=(4, 10), sticky="ew")
        self.progress_bar.set(0)

        # 輸出終端日誌標籤
        self.log_label = ctk.CTkLabel(self.right_col_frame, text="執行日誌回報 (Log Console):", font=ctk.CTkFont(family="Microsoft JhengHei", size=12, weight="bold"))
        self.log_label.grid(row=1, column=0, padx=15, pady=(5, 2), sticky="w")

        # 輸出終端日誌 (滾動文字框)
        self.log_console = ctk.CTkTextbox(self.right_col_frame, font=ctk.CTkFont(family="Consolas", size=11))
        self.log_console.grid(row=2, column=0, padx=15, pady=(2, 10), sticky="nsew")
        self.log_console.configure(state="disabled") # 預設唯讀

        # =========================================================
        # 分頁二：金鑰與模型資訊 (tab_info)
        # =========================================================
        
        # 頂部控制列
        self.info_top_frame = ctk.CTkFrame(self.tab_info)
        self.info_top_frame.grid(row=0, column=0, padx=15, pady=10, sticky="ew")
        self.info_top_frame.grid_columnconfigure(1, weight=1)
        
        self.verify_key_btn = ctk.CTkButton(
            self.info_top_frame, 
            text="查詢 API 金鑰與可用模型", 
            font=ctk.CTkFont(family="Microsoft JhengHei", size=13, weight="bold"),
            command=self.start_api_check
        )
        self.verify_key_btn.grid(row=0, column=0, padx=15, pady=15, sticky="w")
        
        self.conn_status_label = ctk.CTkLabel(
            self.info_top_frame, 
            text="連線狀態: 未連線", 
            font=ctk.CTkFont(family="Microsoft JhengHei", size=13),
            text_color="gray60"
        )
        self.conn_status_label.grid(row=0, column=1, padx=15, pady=15, sticky="w")
        
        # 底部大文字框顯示模型與 token 資訊
        self.models_textbox = ctk.CTkTextbox(self.tab_info, font=ctk.CTkFont(family="Consolas", size=11))
        self.models_textbox.grid(row=1, column=0, padx=15, pady=(5, 15), sticky="nsew")
        
        # 初始化提示文字
        self.models_textbox.insert("0.0", "請點擊上方按鈕測試您的 Gemini API 金鑰連線並獲取可用模型清單及 Token 限制資訊。")
        self.models_textbox.configure(state="disabled")

    # ---------------------------------------------------------
    # 4. UI 邏輯與事件響應
    # ---------------------------------------------------------
    def apply_config_to_ui(self):
        """將 config 數據載入到 UI 視窗元件中"""
        self.model_combo.set(self.config_data["model_id"])
        self.key_entry.insert(0, self.config_data["api_key"])
        self.prompt_text.insert("0.0", self.config_data["prompt_template"])
        self.folder_entry.insert(0, self.config_data["folder_path"])
        self.interval_entry.insert(0, self.config_data.get("request_interval", "4.0"))
        self.update_experiment_info()

    def save_current_config(self):
        """從 UI 元件中提取當前設定並寫入 INI 檔"""
        model_id = self.model_combo.get()
        api_key = self.key_entry.get().strip()
        # 獲取 prompt_template，使用 strip() 避免尾端換行累積
        prompt_template = self.prompt_text.get("0.0", tk.END).strip()
        folder_path = self.folder_entry.get().strip()
        request_interval = self.interval_entry.get().strip()
        save_config(model_id, api_key, prompt_template, folder_path, request_interval)

    def restore_default_prompt(self):
        """還原提示詞文字框為系統預設排版樣式"""
        if messagebox.askyesno("確認還原", "確定要將影像辨識提示詞還原為系統預設的排版格式嗎？\n這將會覆蓋您當前修改過的提示詞。"):
            self.prompt_text.delete("0.0", tk.END)
            self.prompt_text.insert("0.0", DEFAULT_PROMPT)
            self.log("[系統通知] 已將影像辨識提示詞還原為預設多行排版樣式。")

    def start_api_check(self):
        """啟動背景執行緒查詢 API 金鑰與可用模型清單"""
        api_key = self.key_entry.get().strip()
        if not api_key:
            messagebox.showerror(
                "驗證錯誤", 
                "請先在【批次測試】分頁中填入您的 Gemini API Key！\n\n若您尚未擁有 API 金鑰，請至以下網址獲取：\nhttps://aistudio.google.com/app/api-keys"
            )
            return
            
        self.verify_key_btn.configure(state="disabled", text="正在查詢中...")
        self.conn_status_label.configure(text="連線狀態: 正在驗證與載入模型...", text_color="orange")
        
        # 清空模型資訊框
        self.models_textbox.configure(state="normal")
        self.models_textbox.delete("0.0", tk.END)
        self.models_textbox.insert("0.0", "正在向 Gemini 伺服器發送連線請求...\n")
        self.models_textbox.configure(state="disabled")
        
        threading.Thread(target=self.check_api_info_process, args=(api_key,), daemon=True).start()

    def check_api_info_process(self, api_key):
        """背景工作執行緒，負責向 Gemini 查詢模型清單"""
        try:
            client = genai.Client(api_key=api_key)
            # 獲取模型清單
            models = client.models.list()
            
            model_entries = []
            for m in models:
                model_id = m.name.replace("models/", "")
                display_name = getattr(m, "display_name", "未知")
                description = getattr(m, "description", "無")
                input_limit = getattr(m, "input_token_limit", "未提供")
                output_limit = getattr(m, "output_token_limit", "未提供")
                
                model_entries.append((model_id, display_name, input_limit, output_limit, description))
            
            if not model_entries:
                raise ValueError("無法獲取任何模型清單，請確認您的 API 金鑰權限。")
                
            # 將資料送回主執行緒更新 UI
            self.after(0, self.update_api_info_success, model_entries)
            
        except Exception as e:
            # 將錯誤送回主執行緒更新 UI
            self.after(0, self.update_api_info_fail, str(e))

    def update_api_info_success(self, model_entries):
        """成功取得可用模型資訊，更新至 UI"""
        self.verify_key_btn.configure(state="normal", text="查詢 API 金鑰與可用模型")
        self.conn_status_label.configure(text="連線狀態: 連線成功 (API Key 有效)", text_color="#47d147")
        
        self.models_textbox.configure(state="normal")
        self.models_textbox.delete("0.0", tk.END)
        self.models_textbox.insert(tk.END, "連線成功！已成功載入當前帳戶的可用模型清單。\n\n")
        
        # 表格格式輸出
        header = f"{'模型 ID (Model ID)':<40} | {'輸入 Token 限制 (Input Limit)':<30} | {'輸出 Token 限制 (Output Limit)'}\n"
        divider = "=" * 110 + "\n"
        self.models_textbox.insert(tk.END, header)
        self.models_textbox.insert(tk.END, divider)
        
        for model_id, display_name, input_limit, output_limit, desc in model_entries:
            def format_token(val):
                if isinstance(val, int):
                    return f"{val:,} tokens"
                return str(val)
                
            input_str = format_token(input_limit)
            output_str = format_token(output_limit)
            
            # 模型基本資訊
            line = f"{model_id:<40} | {input_str:<30} | {output_str}\n"
            self.models_textbox.insert(tk.END, line)
            
            # 模型名稱與描述
            self.models_textbox.insert(tk.END, f"   顯示名稱: {display_name}\n")
            if desc and desc != "無":
                self.models_textbox.insert(tk.END, f"   說明描述: {desc}\n")
            self.models_textbox.insert(tk.END, "-" * 110 + "\n")
            
        self.models_textbox.configure(state="disabled")

    def update_api_info_fail(self, err_msg):
        """連線或查詢失敗，更新錯誤訊息至 UI"""
        self.verify_key_btn.configure(state="normal", text="查詢 API 金鑰與可用模型")
        self.conn_status_label.configure(text="連線狀態: 連線失敗 (驗證錯誤)", text_color="#ff4d4d")
        
        self.models_textbox.configure(state="normal")
        self.models_textbox.delete("0.0", tk.END)
        self.models_textbox.insert(tk.END, "連線失敗！請檢查您的 Gemini API Key 是否正確以及您的網路連線。\n\n")
        self.models_textbox.insert(tk.END, f"【錯誤詳細資訊】\n{err_msg}\n")
        self.models_textbox.configure(state="disabled")

    def toggle_api_key_visibility(self):
        """切換 API Key 輸入框的遮罩狀態"""
        if self.api_key_visible:
            self.key_entry.configure(show="*")
            self.toggle_key_btn.configure(text="👁")
            self.api_key_visible = False
        else:
            self.key_entry.configure(show="")
            self.toggle_key_btn.configure(text="🔒")
            self.api_key_visible = True

    def browse_folder(self):
        """彈出資料夾選擇視窗"""
        selected = filedialog.askdirectory(title="選擇圖檔資料夾", initialdir=self.folder_entry.get())
        if selected:
            # 正規化路徑分隔符為本機作業系統標準
            normalized_path = os.path.normpath(selected)
            self.folder_entry.delete(0, tk.END)
            self.folder_entry.insert(0, normalized_path)
            self.update_experiment_info()
            # 立即保存路徑變更
            self.save_current_config()

    def update_experiment_info(self):
        """依據當前路徑即時更新實驗名稱與偵測到的圖檔數量"""
        path = self.folder_entry.get().strip()
        if not path or not os.path.exists(path) or not os.path.isdir(path):
            self.info_label.configure(text="實驗名稱: - | 偵測圖檔: 0 張", text_color="gray60")
            return

        # 實驗名稱就是資料夾名稱
        exp_name = os.path.basename(path)
        if not exp_name: # 若路徑為根目錄如 C:\，basename 會為空
            exp_name = path

        # 掃描圖檔數量
        valid_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')
        try:
            files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f)) and f.lower().endswith(valid_extensions)]
            self.info_label.configure(
                text=f"實驗名稱: {exp_name} | 偵測圖檔: {len(files)} 張",
                text_color="cyan"
            )
        except Exception:
            self.info_label.configure(text="實驗名稱: - | 無法存取該資料夾路徑", text_color="red")

    def log(self, message):
        """安全地向日誌文字框追加輸出"""
        self.log_console.configure(state="normal")
        self.log_console.insert(tk.END, f"{message}\n")
        self.log_console.see(tk.END) # 自動滾動到底部
        self.log_console.configure(state="disabled")

    def clear_log(self):
        """清空日誌文字框"""
        self.log_console.configure(state="normal")
        self.log_console.delete("0.0", tk.END)
        self.log_console.configure(state="disabled")

    # ---------------------------------------------------------
    # 5. 批次處理控制流程與多執行緒
    # ---------------------------------------------------------
    def toggle_execution(self):
        """處理開始/停止按鈕點擊事件"""
        if self.is_running:
            # 執行停止流程
            self.is_running = False
            self.log("\n[系統通知] 正在送出終止請求，請稍候當前辨識任務結束...")
            self.status_text_label.configure(text="正在終止程序...", text_color="orange")
            self.run_btn.configure(state="disabled") # 避免重複點擊
        else:
            # 執行開始流程
            self.start_batch_processing()

    def start_batch_processing(self):
        # 1. 驗證 API 金鑰與資料夾
        api_key = self.key_entry.get().strip()
        folder_path = self.folder_entry.get().strip()
        model_id = self.model_combo.get().strip()
        prompt_template = self.prompt_text.get("0.0", tk.END).strip()

        if not api_key:
            messagebox.showerror(
                "設定錯誤", 
                "請先輸入您的 Gemini API Key！\n\n若您尚未擁有 API 金鑰，請至以下網址獲取：\nhttps://aistudio.google.com/app/api-keys"
            )
            return
        if not folder_path or not os.path.exists(folder_path) or not os.path.isdir(folder_path):
            messagebox.showerror("設定錯誤", "請選擇一個有效的本機圖檔資料夾！")
            return
        if not prompt_template:
            messagebox.showerror("設定錯誤", "辨識提示詞 (Prompt) 不能為空！")
            return

        # 2. 自動保存當前狀態至 config.ini
        self.save_current_config()

        # 3. 初始化 UI 狀態為運行中
        self.is_running = True
        self.clear_log()
        self.run_btn.configure(
            text="停止批次執行", 
            fg_color="#a83232", # 紅色警告色
            hover_color="#852828"
        )
        self.status_text_label.configure(text="正在準備批次任務...", text_color="cyan")
        self.progress_bar.set(0)

        # 4. 啟動背景工作執行緒，避免阻礙主 GUI 渲染
        request_interval = self.interval_entry.get().strip()
        self.worker_thread = threading.Thread(
            target=self.batch_worker_process, 
            args=(folder_path, api_key, model_id, prompt_template, request_interval),
            daemon=True
        )
        self.worker_thread.start()

    def batch_worker_process(self, folder_path, api_key, model_id, prompt_template, request_interval_str):
        """背景工作執行緒核心辨識處理邏輯"""
        try:
            # 解析間隔時間
            try:
                request_interval = float(request_interval_str)
                if request_interval < 0:
                    request_interval = 0.0
            except ValueError:
                request_interval = 4.0
            # 掃描圖檔
            valid_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.bmp')
            all_files = os.listdir(folder_path)
            image_files = [f for f in all_files if os.path.isfile(os.path.join(folder_path, f)) and f.lower().endswith(valid_extensions)]
            
            total_images = len(image_files)
            if total_images == 0:
                self.after(0, self.finish_processing, "錯誤: 資料夾中沒有偵測到任何圖檔 (*.jpg, *.png 等)！", "red")
                return

            exp_name = os.path.basename(folder_path)
            if not exp_name:
                exp_name = folder_path

            self.after(0, self.log, f"==== 開始批次測試 ====")
            self.after(0, self.log, f"實驗名稱: {exp_name}")
            self.after(0, self.log, f"圖檔數量: {total_images} 張")
            self.after(0, self.log, f"測試模型: {model_id}\n")

            # 建立 Gemini Client 實例
            client = genai.Client(api_key=api_key)

            # --- Pre-flight API 連線與模型可用性測試 ---
            self.after(0, self.log, "正在執行 pre-flight API 連線與模型測試...")
            self.after(0, self.status_text_label.configure, {
                "text": "正在測試 API 連線...",
                "text_color": "orange"
            })
            
            try:
                # 測試 API 是否能正常呼叫選定之模型
                test_prompt = f"這是連線測試。請回覆當前模型名稱為：{model_id}。勿回傳其他內容。"
                test_response = client.models.generate_content(
                    model=model_id,
                    contents=test_prompt
                )
                test_text = test_response.text.strip()
                self.after(0, self.log, f"   -> API 測試成功！模型回覆: {test_text}\n")
            except Exception as e:
                # 測試失敗，拋出日誌並終止批次任務
                error_info = f"Gemini API 測試連線失敗 (無法工作): {e}\n批次辨識任務已終止，請檢查您的 API Key 與網路狀態。"
                self.after(0, self.log, f"\n[連線錯誤] {error_info}")
                self.after(0, self.finish_processing, f"錯誤: {error_info}", "red")
                return

            from datetime import datetime
            date_str = datetime.now().strftime("%Y%m%d")
            csv_filename = f"{exp_name}_{date_str}.csv"
            csv_path = os.path.join(folder_path, csv_filename)
            
            # 啟動時先將既有的 CSV 刪除，確保寫入全新資料，避免重複並更新表頭
            if os.path.exists(csv_path):
                try:
                    os.remove(csv_path)
                    self.after(0, self.log, "   [系統通知] 偵測到既有同名 CSV 檔案，已自動清除以重新寫入，避免資料重複與欄位錯位。\n")
                except Exception as del_err:
                    self.after(0, self.log, f"   [警告] 無法刪除舊有 CSV 檔案 (可能檔案正被 Excel 開啟): {del_err}\n")

            success_count = 0
            fail_count = 0

            # 初始化 Token 累積計數器
            total_input_tokens = 0
            total_output_tokens = 0
            total_tokens = 0

            for index, filename in enumerate(image_files):
                # 檢查使用者是否已手動終止程序
                if not self.is_running:
                    self.after(0, self.log, "\n[使用者終止] 批次執行已被手動終止。")
                    break

                # 頻率控制延遲 (第一張不延遲，後續張數在處理前延遲)
                if index > 0 and request_interval > 0:
                    time.sleep(request_interval)

                self.after(0, self.log, f"[{index + 1}/{total_images}] 正在處理: {filename}")
                self.after(0, self.status_text_label.configure, {
                    "text": f"處理中 ({index + 1}/{total_images}): {filename}",
                    "text_color": "#4287f5"
                })
                
                # 更新進度條
                progress_val = (index) / total_images
                self.after(0, self.progress_bar.set, progress_val)

                # 1. 讀取本機影像與 MIME
                file_full_path = os.path.join(folder_path, filename)
                _, ext = os.path.splitext(filename)
                ext_lower = ext.lower()
                mime_type = "image/jpeg"
                if ext_lower == ".png":
                    mime_type = "image/png"
                elif ext_lower == ".webp":
                    mime_type = "image/webp"
                elif ext_lower == ".bmp":
                    mime_type = "image/bmp"

                # 2. 解析檔名標籤 (Ground Truth)
                target_name, target_category, target_desc, target_id = parse_filename(filename)
                self.after(0, self.log, f"   -> 解析真實標籤: 名稱='{target_name}', 分類='{target_category}', 敘述='{target_desc}', 編號='{target_id}'")

                # 3. 呼叫 Gemini 進行物品識別
                analysis = {}
                status_str = "成功"
                error_msg = ""
                
                try:
                    with open(file_full_path, "rb") as img_file:
                        image_bytes = img_file.read()

                    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                    
                    # 替換 prompt 中的 {model_id} 變數
                    formatted_prompt = prompt_template.replace("{model_id}", model_id)

                    # 執行 API 呼叫與 429 自動重試邏輯 (重試 1 次)
                    response = None
                    max_attempts = 2  # 原始嘗試 1 次 + 重試 1 次
                    retry_delay = 8.0
                    for attempt in range(max_attempts):
                        try:
                            response = client.models.generate_content(
                                model=model_id,
                                contents=[image_part, formatted_prompt]
                            )
                            break  # 成功，跳出重試迴圈
                        except Exception as req_err:
                            err_str = str(req_err)
                            if ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str) and attempt < max_attempts - 1:
                                self.after(0, self.log, f"   [警告] 遭遇 429 頻率限制，將於 {retry_delay} 秒後自動重試 (重試第 {attempt+1} 次)...")
                                time.sleep(retry_delay)
                                continue
                            raise req_err

                    # 提取 JSON 結構
                    response_text = response.text
                    self.after(0, self.log, f"   -> 模型回覆原文: {response_text.strip()}")

                    match = re.search(r'\{.*\}', response_text.replace("\n", ""), re.DOTALL)
                    if match:
                        json_str = match.group()
                        
                        # 使用進階的 ast.literal_eval 來解析單引號 JSON，並備用 json.loads
                        try:
                            analysis = ast.literal_eval(json_str)
                        except Exception:
                            try:
                                analysis = json.loads(json_str.replace("'", '"'))
                            except Exception:
                                analysis = json.loads(json_str)
                                
                        success_count += 1
                        self.after(0, self.log, f"   -> 解析成功: {analysis}")

                        # 讀取並累加當前呼叫的 Token 使用量
                        usage = getattr(response, "usage_metadata", None)
                        if usage:
                            input_tokens = getattr(usage, "prompt_token_count", 0)
                            output_tokens = getattr(usage, "candidates_token_count", 0)
                            total_tokens_call = getattr(usage, "total_token_count", 0)
                            
                            total_input_tokens += input_tokens
                            total_output_tokens += output_tokens
                            total_tokens += total_tokens_call
                            self.after(0, self.log, f"   -> Token 消耗: 輸入 {input_tokens:,} / 輸出 {output_tokens:,} / 總計 {total_tokens_call:,} tokens")
                    else:
                        raise ValueError("模型回應中找不到 JSON 區塊。請確認提示詞是否正確要求 JSON 回傳。")

                except Exception as e:
                    status_str = "失敗"
                    error_msg = str(e)
                    fail_count += 1
                    self.after(0, self.log, f"   -> 辨識失敗: {error_msg}")
                    analysis = {
                        "name": "辨識失敗",
                        "category": "未知",
                        "expiry": "無",
                        "confidence": "0%"
                    }

                # 4. 進行數據比對與驗證
                pred_name = analysis.get("name", "未知")
                pred_category = analysis.get("category", "未知")
                pred_expiry = analysis.get("expiry", "無")
                
                # 名稱比對：原名稱有在辨識結果字串中任一位置出現即 OK
                if status_str == "成功" and target_name != "未知" and pred_name != "辨識失敗":
                    name_match_status = "OK" if target_name.lower().strip() in pred_name.lower().strip() else "FAIL"
                else:
                    name_match_status = "FAIL"
                    
                # 類別比對：類別全文相同即 OK
                if status_str == "成功" and target_category != "未知" and pred_category != "未知":
                    cat_match_status = "OK" if target_category.lower().strip() == pred_category.lower().strip() else "FAIL"
                else:
                    cat_match_status = "FAIL"

                # 過期日期比對邏輯：若敘述以 EX 開頭，則進行日期提取與智慧比對
                expiry_match_status = "NA"
                if status_str == "成功" and target_desc.upper().startswith("EX"):
                    gt_expiry_raw = target_desc[2:].strip()
                    
                    def parse_date_digits(s):
                        if not s:
                            return ""
                        # 去除非數字字元
                        digits = re.sub(r'\D', '', s)
                        if len(digits) == 8:
                            return digits
                        # 支援 YYYY-M-D 或 YYYY/M/D 等格式
                        match = re.search(r'(\d{4})[-/年]?(\d{1,2})[-/月]?(\d{1,2})', s)
                        if match:
                            y, m, d = match.groups()
                            return f"{int(y):04d}{int(m):02d}{int(d):02d}"
                        return digits
                    
                    gt_expiry_norm = parse_date_digits(gt_expiry_raw)
                    pred_expiry_norm = parse_date_digits(pred_expiry)
                    
                    if gt_expiry_norm and pred_expiry_norm and gt_expiry_norm == pred_expiry_norm:
                        expiry_match_status = "OK"
                    else:
                        expiry_match_status = "FAIL"

                # 5. 組裝數據並即時寫入 CSV 檔案中
                row = [
                    target_name,                      # 原物品名稱 (Ground Truth)
                    target_category,                  # 原分類 (Ground Truth)
                    target_desc,                      # 原敘述 (Ground Truth)
                    target_id,                        # 原編號 (Ground Truth)
                    model_id,                         # 模型 ID
                    pred_name,                        # 辨識物品名稱 (Predicted)
                    pred_category,                    # 辨識分類 (Predicted)
                    analysis.get("confidence", "0%"), # 辨識信心度 (Predicted)
                    pred_expiry,                      # 辨識有效日期 (Predicted)
                    status_str,                       # 辨識狀態
                    error_msg,                        # 錯誤訊息
                    name_match_status,                # 名稱比對 (OK/FAIL)
                    cat_match_status,                 # 類別比對 (OK/FAIL)
                    expiry_match_status               # 過期日期比對 (OK/FAIL/NA)
                ]
                
                # 即時追加寫入 CSV
                try:
                    append_to_csv(csv_path, row)
                except Exception as csv_err:
                    self.after(0, self.log, f"   [警告] 無法寫入 CSV 檔案: {csv_err}")

                self.after(0, self.log, "-" * 50)

            # 迴圈結束後，更新進度條至 100%
            self.after(0, self.progress_bar.set, 1.0)
            
            # 組裝最終統計結果 (含總計 Token 消耗量統計)
            summary_msg = (
                f"==== 批次執行結束 ====\n"
                f"成功: {success_count} 筆, 失敗: {fail_count} 筆。\n\n"
                f"本次測試總 Token 消耗量統計:\n"
                f"  - 輸入 Token 總量: {total_input_tokens:,} tokens\n"
                f"  - 輸出 Token 總量: {total_output_tokens:,} tokens\n"
                f"  - 總計 Token 消耗: {total_tokens:,} tokens\n\n"
                f"辨識 CSV 結果已保存在：\n{csv_path}"
            )
            self.after(0, self.finish_processing, summary_msg, "green" if fail_count == 0 else "yellow")

        except Exception as thread_err:
            self.after(0, self.finish_processing, f"執行緒異常中斷: {thread_err}", "red")

    def finish_processing(self, summary_message, status_color):
        """重置 UI 狀態，顯示最終執行結果日誌"""
        self.is_running = False
        self.run_btn.configure(
            text="開始批次辨識", 
            fg_color="#1f538d", 
            hover_color="#153c66",
            state="normal"
        )
        
        color_map = {
            "red": "#ff4d4d",
            "orange": "orange",
            "yellow": "#ffd214",
            "green": "#47d147"
        }
        
        self.status_text_label.configure(
            text="處理結束！" if "錯誤" not in summary_message else "執行中止！", 
            text_color=color_map.get(status_color, "white")
        )
        
        self.log(f"\n{summary_message}\n")
        messagebox.showinfo("批次辨識完成", "影像批次辨識測試已執行完畢！\n詳細結果已存入資料夾的 CSV 中。")

# ---------------------------------------------------------
# 6. 應用程式進入點
# ---------------------------------------------------------
if __name__ == "__main__":
    # Windows 環境下的視窗解析度 DPI 自適應縮放
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = GeminiBatchTesterApp()
    
    # 關閉視窗時自動保存當前設定
    def on_closing():
        app.save_current_config()
        app.destroy()
        
    app.protocol("WM_DELETE_WINDOW", on_closing)
    app.mainloop()
