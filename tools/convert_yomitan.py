#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/convert_yomitan.py
------------------------
Chuyển đổi từ điển định dạng Yomitan/Yomichan (tệp .zip hoặc thư mục) sang .jsonl
Cấu trúc mảng của Yomitan:
[term, reading, definition_tags, rules, score, [definitions...], sequence, term_tags]
"""

import argparse
import json
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

VIET_WORD_RE = re.compile(r'^[A-Za-zÀ-ỹĐđ]+(?:[ -][A-Za-zÀ-ỹĐđ]+)*$')


def normalize_str(s: str) -> str:
    if not s:
        return ""
    return unicodedata.normalize('NFC', s.strip())


def process_term_entry(entry: list) -> dict:
    """Xử lý 1 bản ghi trong term_bank của Yomitan."""
    if not isinstance(entry, list) or len(entry) < 6:
        return None

    term = normalize_str(entry[0])
    if not VIET_WORD_RE.match(term) or term.startswith('-') or term.endswith('-'):
        return None

    pos_tag = normalize_str(entry[2]) if len(entry) > 2 else ""
    term_tags = normalize_str(entry[7]) if len(entry) > 7 else ""

    tags = set()
    if term_tags:
        for t in term_tags.split():
            tags.add(t.lower())

    # Thu thập text định nghĩa để kiểm tra
    definitions = entry[5]
    defs_text = []
    if isinstance(definitions, list):
        for d in definitions:
            if isinstance(d, str):
                defs_text.append(d)
            elif isinstance(d, dict) and 'content' in d:
                defs_text.append(str(d['content']))

    return {
        "word": term,
        "pos": [pos_tag] if pos_tag else [],
        "tags": list(tags),
        "source": "yomitan"
    }


def main():
    parser = argparse.ArgumentParser(description="Chuyển đổi từ điển Yomitan sang JSONL")
    parser.add_argument("--input", "-i", required=True, help="Đường dẫn file .zip hoặc thư mục Yomitan")
    parser.add_argument("--output", "-o", default="data/dict_yomitan.jsonl", help="Đường dẫn file đầu ra")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        print(f"[!] Không tìm thấy tệp đầu vào: {input_path}")
        sys.exit(1)

    entries = {}
    print(f"-> Đang xử lý từ điển Yomitan từ: {input_path.name}")

    if input_path.is_file() and input_path.suffix.lower() == '.zip':
        with zipfile.ZipFile(input_path, 'r') as zf:
            bank_files = [f for f in zf.namelist() if f.startswith('term_bank_') and f.endswith('.json')]
            for bf in bank_files:
                with zf.open(bf) as f:
                    data = json.load(f)
                    for row in data:
                        res = process_term_entry(row)
                        if res:
                            w = res['word']
                            if w not in entries:
                                entries[w] = res
                            else:
                                entries[w]['tags'] = list(set(entries[w]['tags'] + res['tags']))
                                entries[w]['pos'] = list(set(entries[w]['pos'] + res['pos']))
    elif input_path.is_dir():
        bank_files = list(input_path.glob("term_bank_*.json"))
        for bf in bank_files:
            with open(bf, "r", encoding="utf-8") as f:
                data = json.load(f)
                for row in data:
                    res = process_term_entry(row)
                    if res:
                        w = res['word']
                        if w not in entries:
                            entries[w] = res
                        else:
                            entries[w]['tags'] = list(set(entries[w]['tags'] + res['tags']))
                            entries[w]['pos'] = list(set(entries[w]['pos'] + res['pos']))

    print(f"-> Trích xuất được {len(entries):,} mục từ hợp lệ.")
    print(f"-> Đang ghi vào: {output_path}")
    with open(output_path, "w", encoding="utf-8") as f:
        for w in sorted(entries.keys()):
            f.write(json.dumps(entries[w], ensure_ascii=False) + "\n")

    print("[THÀNH CÔNG] Hoàn tất chuyển đổi Yomitan!\n")


if __name__ == "__main__":
    main()

