#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run.py
------
Điểm khởi chạy một lệnh duy nhất (One-click start) cho VietLit-Proofreader.
"""

import sys
import uvicorn
from pathlib import Path

if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    print("=" * 68)
    print(" VIETLIT-PROOFREADER ĐANG KHỞI CHẠY...")
    print(" • Giao diện Web UI : http://127.0.0.1:8000")
    print(" • Tài liệu API      : http://127.0.0.1:8000/docs")
    print(" Nhấn Ctrl + C để dừng máy chủ.")
    print("=" * 68)

    uvicorn.run("server.app:app", host="127.0.0.1", port=8000, reload=True)
