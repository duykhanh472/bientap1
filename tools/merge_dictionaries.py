#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/merge_dictionaries.py
---------------------------
Hợp nhất ĐA NGUỒN từ điển JSONL thành tệp master 'data/dictionary.jsonl':
1. Tự động phát hiện các tệp .jsonl trong data/ hoặc nhận danh sách tùy chỉnh qua CLI.
2. Tự động loại bỏ tệp thô (kaikki-vietnamese.jsonl) và tệp đầu ra (dictionary.jsonl).
3. Đặt mức ưu tiên cao nhất cho Wiktionary (dict_kaikki.jsonl).
4. Khử trùng lặp (Deduplicate), hợp nhất thẻ phân loại (tags) và từ loại (pos).
5. Tự động mở rộng từ ghép gạch nối (quốc gia <-> quốc-gia).
"""

import argparse
import json
import os
import sys
import unicodedata
from pathlib import Path
from typing import Dict, List, Set


def normalize_str(s: str) -> str:
    """Chuẩn hóa chuỗi về Unicode NFC."""
    if not s:
        return ""
    return unicodedata.normalize('NFC', s.strip())


def parse_to_set(data) -> Set[str]:
    """Chuyển đổi linh hoạt pos/tags (dù ở dạng list, str hay None) thành Set."""
    if not data:
        return set()
    if isinstance(data, list):
        return {normalize_str(str(x)) for x in data if x}
    if isinstance(data, str):
        return {normalize_str(data)}
    return set()


def load_jsonl_source(file_path: Path, priority_level: int, master_dict: dict) -> int:
    """
    Nạp dữ liệu từ 1 tệp JSONL và gộp vào master_dict theo thứ tự ưu tiên.
    priority_level: Số càng nhỏ thì mức độ ưu tiên càng cao (1 là cao nhất).
    """
    if not file_path.exists():
        print(f"   [!] Không tìm thấy tệp: {file_path.name}")
        return 0

    count = 0
    source_tag = file_path.stem.replace("dict_", "")  # vd: 'dict_kaikki' -> 'kaikki'

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            word = normalize_str(item.get("word", ""))
            if not word or word.startswith("-") or word.endswith("-"):
                continue

            # Chuẩn hóa key: Giữ nguyên hoa/thường nếu là tên riêng, còn lại đưa về lowercase
            norm_key = word if word.istitle() else word.lower()

            incoming_pos = parse_to_set(item.get("pos"))
            incoming_tags = parse_to_set(item.get("tags"))
            # Bổ sung tag nhận diện nguồn dữ liệu
            incoming_tags.add(f"src:{source_tag}")

            if norm_key not in master_dict:
                # Từ mới xuất hiện -> thêm mới vào từ điển
                master_dict[norm_key] = {
                    "word": norm_key,
                    "type": "compound" if (" " in norm_key or "-" in norm_key) else "single",
                    "pos": incoming_pos,
                    "tags": incoming_tags,
                    "priority": priority_level
                }
            else:
                current = master_dict[norm_key]
                # Nếu nguồn mới có độ ưu tiên cao hơn -> ghi đè POS chính
                if priority_level < current["priority"]:
                    if incoming_pos:
                        current["pos"] = incoming_pos
                    current["priority"] = priority_level
                else:
                    # Nếu nguồn phụ có thêm POS mà nguồn chính chưa có -> bổ sung
                    current["pos"].update(incoming_pos)

                # Thẻ tags luôn luôn được hợp nhất (union) từ tất cả các nguồn
                current["tags"].update(incoming_tags)

            count += 1

    return count


def expand_hyphenated_compounds(master_dict: dict) -> int:
    """Đảm bảo mọi từ ghép dấu cách đều có bản gạch nối đối ứng (quốc gia <-> quốc-gia)."""
    to_add = {}
    for key, data in master_dict.items():
        if " " in key:
            hyphen_key = key.replace(" ", "-")
            if hyphen_key not in master_dict and hyphen_key not in to_add:
                to_add[hyphen_key] = {
                    "word": hyphen_key,
                    "type": "compound",
                    "pos": set(data["pos"]),
                    "tags": set(data["tags"]) | {"hyphenated"},
                    "priority": data["priority"]
                }
    master_dict.update(to_add)
    return len(to_add)


def discover_input_files(data_dir: Path) -> List[Path]:
    """
    Tự động tìm kiếm các tệp từ điển JSONL hợp lệ trong thư mục data/.
    Tự động loại bỏ tệp raw kaikii và tệp dictionary.jsonl đích.
    """
    all_jsonls = list(data_dir.glob("*.jsonl"))

    # Các tệp cần bỏ qua không gộp trực tiếp
    ignored_names = {
        "dictionary.jsonl",           # Tệp master đầu ra
        "kaikki-vietnamese.jsonl",    # Tệp raw dump chưa qua bóc tách
        "raw_kaikki.jsonl"
    }

    candidates = [p for p in all_jsonls if p.name not in ignored_names]

    # Sắp xếp: Ưu tiên đưa tệp Wiktionary/Kaikki lên đầu (Priority 1)
    def sort_key(p: Path):
        name = p.name.lower()
        if "kaikki" in name or "wiktionary" in name:
            return (0, name)
        if "tdtvtd" in name:          # Từ điển tiếng Việt thông dụng
            return (1, name)
        if "ovdp" in name:            # Hồ Ngọc Đức
            return (2, name)
        if "babylon" in name:
            return (3, name)
        return (4, name)

    return sorted(candidates, key=sort_key)


def main():
    parser = argparse.ArgumentParser(
        description="Hợp nhất đa nguồn từ điển JSONL thành tệp master dictionary.jsonl"
    )
    parser.add_argument(
        "inputs", nargs="*", default=None,
        help="Danh sách các tệp .jsonl theo thứ tự ưu tiên giảm dần (tùy chọn)"
    )
    parser.add_argument(
        "--output", "-o", default="data/dictionary.jsonl",
        help="Đường dẫn file master đầu ra (mặc định: data/dictionary.jsonl)"
    )

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    data_dir = repo_root / "data"
    output_path = Path(args.output) if args.output else data_dir / "dictionary.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Xác định danh sách file đầu vào
    if args.inputs:
        input_paths = [Path(p) for p in args.inputs]
    else:
        input_paths = discover_input_files(data_dir)

    if not input_paths:
        print("[!] Không tìm thấy tệp từ điển .jsonl nào trong thư mục data/!")
        sys.exit(1)

    print("=" * 68)
    print(" VIETLIT-PROOFREADER: HỢP NHẤT ĐA NGUỒN TỪ ĐIỂN JSONL")
    print("=" * 68)
    print(f"-> Thư mục làm việc: {data_dir.resolve()}")
    print("-> Danh sách tệp được nạp theo thứ tự ưu tiên:")
    for prio, path in enumerate(input_paths, 1):
        note = " (ƯU TIÊN CAO NHẤT)" if prio == 1 else ""
        print(f"   [{prio}] {path.name:<28}{note}")

    # 2. Tiến hành nạp và gộp dữ liệu
    master_dict: Dict[str, dict] = {}

    print("\n-> Bắt đầu nạp và khử trùng lặp dữ liệu...")
    for prio, path in enumerate(input_paths, 1):
        count = load_jsonl_source(path, prio, master_dict)
        print(f"   ✓ [{prio}] Đã nạp {count:>7,} mục từ từ: {path.name}")

    print(f"\n-> Tổng số mục từ độc bản sau khi gộp: {len(master_dict):,}")

    # 3. Mở rộng từ ghép có gạch nối
    print("-> Đang tự động sinh các biến thể từ ghép gạch nối (quốc-gia)...")
    added_hyphen = expand_hyphenated_compounds(master_dict)
    print(f"   ✓ Đã bổ sung thêm {added_hyphen:,} biến thể có gạch nối.")

    # 4. Ghi ra tệp master data/dictionary.jsonl
    print(f"\n-> Đang ghi tổng cộng {len(master_dict):,} mục từ vào {output_path.name}...")
    with open(output_path, "w", encoding="utf-8") as f:
        for word in sorted(master_dict.keys()):
            item = master_dict[word]
            entry = {
                "word": word,
                "type": item["type"],
                "pos": sorted(list(item["pos"])),
                "tags": sorted(list(item["tags"]))
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print("\n" + "=" * 68)
    print(f"[THÀNH CÔNG] Tệp từ điển master đã hoàn thành!")
    print(f"-> Vị trí: {output_path.resolve()}")
    print(f"-> Dung lượng mục từ: {len(master_dict):,} từ.")
    print("=" * 68 + "\n")


if __name__ == "__main__":
    main()
