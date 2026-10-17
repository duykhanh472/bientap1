#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/convert_kaikki.py
-----------------------
Chuyển đổi dữ liệu JSONL từ Kaikki.org (Wiktionary) thành:
1. data/dictionary.jsonl : Từ điển từ ghép, từ cổ, thành ngữ có phân loại tags.
2. data/unigram_freq.txt : Bảng tần suất unigram phục vụ SymSpell và Viterbi.

Tự động hỗ trợ cả 2 nguồn:
- Kaikki Vietnamese (English Wiktionary extract)
- Kaikki Tiếng Việt (Vietnamese Wiktionary extract)
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

# Biểu thức chính quy nhận diện từ tiếng Việt hợp lệ (chấp nhận dấu cách và gạch nối)
VIET_WORD_RE = re.compile(r'^[A-Za-zÀ-ỹĐđ]+(?:[ -][A-Za-zÀ-ỹĐđ]+)*$')
# Regex bóc tách từng tiếng/âm tiết đơn để tính tần suất
TOKEN_RE = re.compile(r'\b[A-Za-zÀ-ỹĐđ]+(?:-[A-Za-zÀ-ỹĐđ]+)*\b')

# Các thẻ (tags) lịch sử / phương ngữ quan trọng cần bảo tồn
HISTORICAL_TAGS = {
    'archaic', 'dated', 'historical', 'obsolete', 'rare', 'dialectal',
    'southern vietnam', 'central vietnam', 'northern vietnam', 'literary',
    'cổ', 'cũ', 'lịch sử', 'phương ngữ', 'nam bộ', 'trung bộ', 'bắc bộ',
    'văn chương', 'ít dùng'
}


def normalize_str(s: str) -> str:
    """Chuẩn hóa chuỗi về Unicode NFC và loại bỏ khoảng trắng thừa."""
    if not s:
        return ""
    return unicodedata.normalize('NFC', s.strip())


def is_valid_viet_word(word: str) -> bool:
    """Kiểm tra từ có cấu tạo hợp lệ (chỉ gồm chữ cái tiếng Việt, dấu cách, gạch nối)."""
    if not word or len(word) > 60:
        return False
    # Loại trừ các mục có dấu gạch ngang ở đầu hoặc cuối (tiền tố/hậu tố: -hóa, tiền-)
    if word.startswith('-') or word.endswith('-'):
        return False
    return bool(VIET_WORD_RE.match(word))


def extract_tags_and_texts(item: dict) -> tuple:
    """Trích xuất tags liên quan và các đoạn văn bản (định nghĩa/ví dụ) để đếm tần suất."""
    collected_tags = set()
    text_corpus = []

    # Thu thập top-level tags
    for tag in item.get('tags', []):
        tag_norm = normalize_str(tag).lower()
        if tag_norm in HISTORICAL_TAGS:
            collected_tags.add(tag_norm)

    # Thu thập từ các senses (định nghĩa, ví dụ)
    for sense in item.get('senses', []):
        for tag in sense.get('tags', []):
            tag_norm = normalize_str(tag).lower()
            if tag_norm in HISTORICAL_TAGS:
                collected_tags.add(tag_norm)

        # Lấy văn bản định nghĩa (glosses) để tính tần suất ngôn ngữ
        for gloss in sense.get('glosses', []):
            text_corpus.append(gloss)

        # Lấy các câu ví dụ (examples)
        for ex in sense.get('examples', []):
            if isinstance(ex, dict):
                text_corpus.append(ex.get('text', ''))
            elif isinstance(ex, str):
                text_corpus.append(ex)

    return list(collected_tags), text_corpus


def find_default_input_file(data_dir: Path) -> Path:
    """Tìm tệp .jsonl có sẵn trong thư mục data nếu người dùng không chỉ định."""
    candidates = list(data_dir.glob("*.jsonl"))
    if candidates:
        return candidates[0]
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Chuyển đổi Kaikki JSONL sang dictionary.jsonl và unigram_freq.txt"
    )
    parser.add_argument(
        "--input", "-i", type=str, default=None,
        help="Đường dẫn tới file Kaikki JSONL (vd: data/kaikki-vietnamese.jsonl)"
    )
    parser.add_argument(
        "--output-dict", "-d", type=str, default=None,
        help="Đường dẫn file đầu ra dictionary.jsonl (mặc định: data/dictionary.jsonl)"
    )
    parser.add_argument(
        "--output-freq", "-f", type=str, default=None,
        help="Đường dẫn file đầu ra unigram_freq.txt (mặc định: data/unigram_freq.txt)"
    )
    parser.add_argument(
        "--syllables", "-s", type=str, default=None,
        help="Đường dẫn file valid_syllables.txt để hiệp đồng tần suất"
    )

    args = parser.parse_args()

    # Thiết lập đường dẫn thư mục
    repo_root = Path(__file__).resolve().parent.parent
    data_dir = repo_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Xác định file đầu vào
    input_path = Path(args.input) if args.input else find_default_input_file(data_dir)
    if not input_path or not input_path.exists():
        print("=" * 65)
        print(" [!] KHÔNG TÌM THẤY TỆP DỮ LIỆU KAIKKI JSONL ĐẦU VÀO")
        print("=" * 65)
        print("Bạn hãy tải một trong 2 tệp sau và đặt vào thư mục 'data/':")
        print(" 1. Kaikki Vietnamese (English Wiktionary extract):")
        print("    https://kaikki.org/dictionary/Vietnamese/kaikki.org-dictionary-Vietnamese.jsonl")
        print(" 2. Kaikki Tiếng Việt (Vietnamese Wiktionary extract):")
        print("    https://kaikki.org/viwiktionary/Ti%E1%BA%BFng%20Vi%E1%BB%87t/index.html")
        print("\nHoặc chỉ định đường dẫn qua lệnh:")
        print(" python tools/convert_kaikki.py --input /duong/dan/file.jsonl\n")
        sys.exit(1)

    out_dict_path = Path(args.output_dict) if args.output_dict else data_dir / "dictionary.jsonl"
    out_freq_path = Path(args.output_freq) if args.output_freq else data_dir / "unigram_freq.txt"
    syllables_path = Path(args.syllables) if args.syllables else data_dir / "valid_syllables.txt"

    print("=" * 65)
    print(" VIETLIT-PROOFREADER: CHUYỂN ĐỔI TỪ ĐIỂN KAIKKI")
    print("=" * 65)
    print(f"-> Tệp đầu vào : {input_path}")
    print(f"-> Đầu ra Dict : {out_dict_path}")
    print(f"-> Đầu ra Freq : {out_freq_path}")

    dict_entries = {}          # word -> {"pos": set(), "tags": set()}
    unigram_counts = Counter() # word/syllable -> count

    line_count = 0
    valid_entries_count = 0

    print("\n-> Đang đọc và phân tích tệp JSONL (Streaming)...")
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line_count += 1
            if line_count % 25000 == 0:
                print(f"   ...đã xử lý {line_count:,} dòng")

            line = line.strip()
            if not line:
                continue

            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Lọc ngôn ngữ: tiếng Việt
            lang_code = item.get("lang_code", "")
            lang = item.get("lang", "")
            if lang_code != "vi" and lang not in ("Vietnamese", "Tiếng Việt"):
                continue

            raw_word = item.get("word", "")
            word = normalize_str(raw_word)

            if not is_valid_viet_word(word):
                continue

            valid_entries_count += 1
            pos = normalize_str(item.get("pos", ""))
            tags, text_corpus = extract_tags_and_texts(item)

            # 1. Lưu trữ vào từ điển
            # Nếu từ viết hoa (tên riêng), giữ nguyên; từ thông thường đưa về lowercase
            norm_key = word if word.istitle() else word.lower()

            if norm_key not in dict_entries:
                dict_entries[norm_key] = {"pos": set(), "tags": set()}
            if pos:
                dict_entries[norm_key]["pos"].add(pos)
            if tags:
                dict_entries[norm_key]["tags"].update(tags)

            # 2. Hỗ trợ từ ghép gạch nối (quốc gia <-> quốc-gia)
            # Nếu từ ghép có khoảng trắng, tự sinh thêm biến thể có gạch nối
            if " " in norm_key:
                hyphen_word = norm_key.replace(" ", "-")
                if hyphen_word not in dict_entries:
                    dict_entries[hyphen_word] = {"pos": set(), "tags": set()}
                dict_entries[hyphen_word]["tags"].add("hyphenated")
                if pos:
                    dict_entries[hyphen_word]["pos"].add(pos)

            # 3. Tính tần suất unigram
            # Headword được cộng điểm ưu tiên ban đầu
            words_in_headword = TOKEN_RE.findall(norm_key.lower())
            for w in words_in_headword:
                # Nếu là từ ghép gạch nối, tính tần suất cho cả từ ghép lẫn từng tiếng đơn
                if "-" in w:
                    unigram_counts[w] += 15
                    for part in w.split("-"):
                        unigram_counts[part] += 20
                else:
                    unigram_counts[w] += 25

            # Tính tần suất từ các văn bản giải nghĩa và ví dụ
            for txt in text_corpus:
                txt_norm = normalize_str(txt).lower()
                tokens = TOKEN_RE.findall(txt_norm)
                for tok in tokens:
                    if "-" in tok:
                        for part in tok.split("-"):
                            unigram_counts[part] += 1
                    else:
                        unigram_counts[tok] += 1

    print(f"\n-> Tổng số dòng đã quét: {line_count:,}")
    print(f"-> Số mục từ hợp lệ trích xuất được: {len(dict_entries):,}")

    # 4. Hiệp đồng với valid_syllables.txt
    # Đảm bảo mọi âm tiết hợp lệ đều có mặt trong bảng unigram với tần suất tối thiểu
    if syllables_path.exists():
        print(f"-> Đang đồng bộ với bảng âm tiết: {syllables_path.name}...")
        syllables_added = 0
        with open(syllables_path, "r", encoding="utf-8") as f:
            for s_line in f:
                syl = normalize_str(s_line)
                if syl and syl not in unigram_counts:
                    unigram_counts[syl] = 2  # Gán tần suất cơ sở
                    syllables_added += 1
        print(f"   ...đã bổ sung {syllables_added:,} âm tiết cơ sở vào bảng tần suất.")

    # 5. Ghi tệp data/dictionary.jsonl
    print(f"-> Đang ghi {len(dict_entries):,} mục từ vào {out_dict_path.name}...")
    with open(out_dict_path, "w", encoding="utf-8") as f:
        for word in sorted(dict_entries.keys()):
            entry = {
                "word": word,
                "type": "compound" if (" " in word or "-" in word) else "single",
                "pos": sorted(list(dict_entries[word]["pos"])),
                "tags": sorted(list(dict_entries[word]["tags"]))
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # 6. Ghi tệp data/unigram_freq.txt (định dạng chuẩn: word count, xếp giảm dần)
    print(f"-> Đang ghi {len(unigram_counts):,} unigram vào {out_freq_path.name}...")
    with open(out_freq_path, "w", encoding="utf-8") as f:
        # Sắp xếp theo tần suất giảm dần
        for word, count in unigram_counts.most_common():
            # Loại bỏ các từ chứa khoảng trắng trong file unigram
            if " " not in word:
                f.write(f"{word} {count}\n")

    # In kết quả kiểm tra mẫu
    print("\n--- KIỂM TRA MẪU DỮ LIỆU ĐÃ TẠO ---")
    test_words = ["quốc-gia", "quốc gia", "nhơn đức", "hoà", "hòa", "văn-học"]
    for tw in test_words:
        status_dict = "✓ (Dict)" if tw in dict_entries else "✗"
        freq = unigram_counts.get(tw.lower(), 0)
        print(f"  • {tw:<12} : {status_dict:<8} | Tần suất unigram: {freq:,}")

    print("\n[THÀNH CÔNG] Hoàn tất Giai đoạn 1: Chuẩn bị Dữ liệu & Ngữ âm!")
    print(f"1. {out_dict_path.resolve()}")
    print(f"2. {out_freq_path.resolve()}\n")


if __name__ == "__main__":
    main()


