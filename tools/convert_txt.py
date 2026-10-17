#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/convert_txt.py
--------------------
Chuyển đổi danh sách từ vựng dạng .txt (1 từ/dòng hoặc 'từ [tần suất]') sang .jsonl
Hỗ trợ cả file đơn lẻ hoặc cả một thư mục chứa nhiều file .txt.
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

VIET_WORD_RE = re.compile(r'^[A-Za-zÀ-ỹĐđ]+(?:[ -][A-Za-zÀ-ỹĐđ]+)*$')


def normalize_str(s: str) -> str:
    if not s:
        return ""
    return unicodedata.normalize('NFC', s.strip())


def process_txt_file(file_path: Path, entries_dict: dict, tag_name: str):
    count = 0
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            # Bỏ qua dòng trống hoặc dòng chú thích
            if not line or line.startswith("#"):
                continue

            # Xử lý trường hợp dòng có kèm tần số (vd: "nhà cửa 1234")
            parts = line.split("\t") if "\t" in line else line.split()
            # Nếu phần tử cuối cùng là số nguyên, ta lấy phần trước nó làm từ
            if len(parts) > 1 and parts[-1].isdigit():
                word_raw = " ".join(parts[:-1])
            else:
                word_raw = line

            word = normalize_str(word_raw)
            if VIET_WORD_RE.match(word) and not word.startswith("-") and not word.endswith("-"):
                norm_key = word if word.istitle() else word.lower()
                if norm_key not in entries_dict:
                    entries_dict[norm_key] = {
                        "word": norm_key,
                        "type": "compound" if (" " in norm_key or "-" in norm_key) else "single",
                        "pos": [],
                        "tags": [tag_name] if tag_name else ["wordlist"],
                        "source": "txt"
                    }
                count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description="Chuyển đổi danh sách từ TXT sang JSONL")
    parser.add_argument("--input", "-i", required=True, help="Đường dẫn file .txt hoặc thư mục chứa file .txt")
    parser.add_argument("--output", "-o", default="data/dict_txt.jsonl", help="Đường dẫn file đầu ra")
    parser.add_argument("--tag", "-t", default="wordlist", help="Gán tag cho nguồn này (vd: vntk, hongocduc)")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        print(f"[!] Không tìm thấy: {input_path}")
        sys.exit(1)

    entries = {}
    print(f"-> Đang đọc dữ liệu TXT từ: {input_path}")

    if input_path.is_file():
        added = process_txt_file(input_path, entries, args.tag)
        print(f"   Đã đọc {added:,} từ từ {input_path.name}")
    elif input_path.is_dir():
        for tf in input_path.glob("*.txt"):
            added = process_txt_file(tf, entries, tf.stem)
            print(f"   Đã đọc {added:,} từ từ {tf.name}")

    print(f"-> Tổng số từ hợp lệ: {len(entries):,}")
    print(f"-> Đang ghi vào: {output_path}")
    with open(output_path, "w", encoding="utf-8") as f:
        for w in sorted(entries.keys()):
            f.write(json.dumps(entries[w], ensure_ascii=False) + "\n")

    print("[THÀNH CÔNG] Hoàn tất chuyển đổi danh sách TXT!\n")


if __name__ == "__main__":
    main()

