import tkinter as tk
from tkinter import filedialog, messagebox
import threading
from pathlib import Path
import os
import sys
import subprocess

# 외부 라이브러리, 설치 필요: pip install tkinterdnd2
from tkinterdnd2 import DND_FILES, TkinterDnD 

# 우리가 만든 모듈 임포트
import logger_setup
import core_logic

def open_folder(path):
    """주어진 경로에 대해 크로스플랫폼을 지원하는 방식으로 파일 탐색기를 엽니다."""
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin": # macOS
            subprocess.run(["open", path])
        else: # Linux
            subprocess.run(["xdg-open", path])
    except Exception as e:
        messagebox.showerror("오류", f"폴더를 여는 데 실패했습니다: {e}")


class AssetExtractorApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()
        self.title("Risu Asset Extractor")
        self.geometry("500x250")

        # ... (UI 요소 생성 부분은 동일) ...
        self.info_label = tk.Label(
            self,
            text="여기에 .png 또는 .charx 파일을 드래그 앤 드롭하세요\n또는 버튼을 클릭하여 파일을 선택하세요.",
            font=("Helvetica", 12),
            padx=10, pady=40
        )
        self.info_label.pack(expand=True, fill=tk.BOTH)

        self.select_button = tk.Button(self, text="파일 선택", command=self.select_file)
        self.select_button.pack(pady=10)
        
        self.status_label = tk.Label(self, text="대기 중...", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.handle_drop)
    
    # ... (select_file, handle_drop, start_processing 함수는 동일) ...
    def select_file(self):
        file_path = filedialog.askopenfilename(
            title="캐릭터 카드 파일 선택",
            filetypes=(("RisuAI Cards", "*.png *.charx"), ("All files", "*.*"))
        )
        if file_path:
            self.start_processing(file_path)

    def handle_drop(self, event):
        file_path = self.tk.splitlist(event.data)[0]
        if Path(file_path).exists():
            self.start_processing(file_path)
        else:
            self.update_status(f"잘못된 경로: {file_path}")

    def start_processing(self, file_path):
        self.update_status(f"'{Path(file_path).name}' 처리 중...")
        thread = threading.Thread(
            target=self.run_extraction_thread,
            args=(file_path,),
            daemon=True
        )
        thread.start()

    def run_extraction_thread(self, file_path):
        """실제 추출 로직을 실행하고 완료 후 UI를 업데이트하는 스레드 함수"""
        try:
            # 이제 process_file은 성공 시 폴더 경로를, 실패 시 None을 반환합니다.
            output_folder_path = core_logic.process_file(file_path)
            
            if output_folder_path:
                self.update_status(f"'{Path(file_path).name}' 처리 완료! 자세한 내용은 로그를 확인하세요.")
                # 성공 메시지 박스를 메인 스레드에서 호출
                self.after(0, self.show_completion_dialog, output_folder_path)
            else:
                # process_file이 None을 반환하면 실패로 간주
                self.update_status(f"처리 중 오류 발생.")
                self.after(0, lambda: messagebox.showerror("오류", "파일 처리 중 오류가 발생했습니다.\n자세한 내용은 extraction.log 파일을 확인하세요."))

        except Exception as e:
            # 스레드 자체의 예외 처리
            self.update_status(f"오류 발생: {e}")
            self.after(0, lambda: messagebox.showerror("오류", f"알 수 없는 오류가 발생했습니다.\n자세한 내용은 extraction.log 파일을 확인하세요."))

    def show_completion_dialog(self, folder_path):
        """추출 완료 후 '폴더 열기' 버튼이 있는 새 창을 띄웁니다."""
        dialog = tk.Toplevel(self)
        dialog.title("추출 완료")
        
        # 창을 부모 창 중앙에 위치시키기
        self.update_idletasks()
        parent_x = self.winfo_x()
        parent_y = self.winfo_y()
        parent_width = self.winfo_width()
        parent_height = self.winfo_height()
        dialog_width = 350
        dialog_height = 150
        dialog.geometry(f"{dialog_width}x{dialog_height}+{parent_x + (parent_width - dialog_width) // 2}+{parent_y + (parent_height - dialog_height) // 2}")

        dialog.grab_set() # 이 창을 닫기 전까지 부모 창을 조작할 수 없게 함

        main_frame = tk.Frame(dialog, padx=20, pady=15)
        main_frame.pack(expand=True, fill=tk.BOTH)

        label = tk.Label(main_frame, text="에셋 추출이 성공적으로 완료되었습니다.", font=("Helvetica", 11))
        label.pack(pady=(0, 10))

        open_button = tk.Button(main_frame, text="결과 폴더 열기", command=lambda: open_folder(folder_path))
        open_button.pack(pady=5, ipadx=10)

        close_button = tk.Button(main_frame, text="닫기", command=dialog.destroy)
        close_button.pack(pady=5)

    def update_status(self, message):
        """하단 상태 표시줄의 텍스트를 업데이트합니다."""
        self.status_label.config(text=message)
        self.update_idletasks() # UI 즉시 업데이트

if __name__ == '__main__':
    logger_setup.setup_logger()
    app = AssetExtractorApp()
    app.mainloop()