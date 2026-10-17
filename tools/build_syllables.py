#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tools/build_syllables.py
------------------------
Sinh tập hợp âm tiết tiếng Việt hợp lệ mặt chữ (chữ Quốc ngữ) phục vụ việc
soát lỗi OCR cho văn học giai đoạn 1880–1975.

Đặc tính cốt lõi:
1. Hỗ trợ song song cả 2 cách đặt dấu thanh:
   - Kiểu cũ (truyền thống / trước 1975): hoà, thuỷ, khoè, toạ, thuỵ...
   - Kiểu mới (sau 1980): hòa, thủy, khòe, tọa, thụy...
2. Bảo toàn tính chuẩn xác ngữ âm học:
   - Luật chính tả: c/k/qu, g/gh, ng/ngh.
   - Vần kết thúc bằng âm tắc (c, ch, p, t) chỉ mang thanh Sắc hoặc Nặng.
3. Xuất file UTF-8 chuẩn NFC ra thư mục data/valid_syllables.txt.
"""

import os
import sys
import unicodedata
from pathlib import Path

# Bảng hoán đổi ký tự mang dấu thanh (NFC)
# Thứ tự: [0: Ngang, 1: Huyền, 2: Hỏi, 3: Ngã, 4: Sắc, 5: Nặng]
VOWEL_TONE_TABLE = {
    'a': ('a', 'à', 'ả', 'ã', 'á', 'ạ'),
    'ă': ('ă', 'ằ', 'ẳ', 'ẵ', 'ắ', 'ặ'),
    'â': ('â', 'ầ', 'ẩ', 'ẫ', 'ấ', 'ậ'),
    'e': ('e', 'è', 'ẻ', 'ẽ', 'é', 'ẹ'),
    'ê': ('ê', 'ề', 'ể', 'ễ', 'ế', 'ệ'),
    'i': ('i', 'ì', 'ỉ', 'ĩ', 'í', 'ị'),
    'o': ('o', 'ò', 'ỏ', 'õ', 'ó', 'ọ'),
    'ô': ('ô', 'ồ', 'ổ', 'ỗ', 'ố', 'ộ'),
    'ơ': ('ơ', 'ờ', 'ở', 'ỡ', 'ớ', 'ợ'),
    'u': ('u', 'ù', 'ủ', 'ũ', 'ú', 'ụ'),
    'ư': ('ư', 'ừ', 'ử', 'ữ', 'ứ', 'ự'),
    'y': ('y', 'ỳ', 'ỷ', 'ỹ', 'ý', 'ỵ'),
}

# Danh sách phụ âm đầu chuẩn của chữ Quốc ngữ
ONSETS = [
    '', 'b', 'c', 'ch', 'd', 'đ', 'g', 'gh', 'gi', 'h',
    'k', 'kh', 'l', 'm', 'n', 'ng', 'ngh', 'nh', 'p', 'ph',
    'qu', 'r', 's', 't', 'th', 'tr', 'v', 'x'
]

# Định nghĩa vần: (vần_gốc, vị_trí_dấu_mới, vị_trí_dấu_cũ, là_âm_tắc_c_ch_p_t)
# Nếu vị_trí_dấu_cũ là None nghĩa là kiểu cũ và mới đặt dấu ở cùng 1 vị trí.
RHYMES = [
    # 1. Nguyên âm đơn mở (không âm cuối)
    ('a', 0, None, False),
    ('e', 0, None, False),
    ('ê', 0, None, False),
    ('i', 0, None, False),
    ('o', 0, None, False),
    ('ô', 0, None, False),
    ('ơ', 0, None, False),
    ('u', 0, None, False),
    ('ư', 0, None, False),
    ('y', 0, None, False),

    # 2. Nguyên âm đôi mở & Âm đệm mở (Nơi kiểu cũ và mới phân tách)
    # oa: mới đặt ở 'a' (idx 1: hòa), cũ đặt ở 'o' (idx 0: hoà)
    ('oa', 1, 0, False),
    # oe: mới đặt ở 'e' (idx 1: hòe), cũ đặt ở 'o' (idx 0: hoè)
    ('oe', 1, 0, False),
    # uy: mới đặt ở 'y' (idx 1: thủy), cũ đặt ở 'u' (idx 0: thuỷ)
    ('uy', 1, 0, False),
    # Các nguyên âm đôi mở khác (Cũ và mới đều cùng vị trí)
    ('ia', 0, None, False),
    ('ya', 0, None, False),
    ('ua', 0, None, False),
    ('ưa', 0, None, False),
    ('uơ', 1, None, False),
    ('uê', 1, None, False),

    # 3. Vần có bán âm cuối (-i, -y, -o, -u)
    ('ai', 0, None, False),
    ('oi', 0, None, False),
    ('ơi', 0, None, False),
    ('ui', 0, None, False),
    ('ưi', 0, None, False),
    ('uôi', 1, None, False),
    ('ươi', 1, None, False),
    ('ay', 0, None, False),
    ('ây', 0, None, False),
    ('oay', 1, None, False),
    ('uây', 1, None, False),
    ('ao', 0, None, False),
    ('eo', 0, None, False),
    ('oao', 1, None, False),
    ('au', 0, None, False),
    ('âu', 0, None, False),
    ('êu', 0, None, False),
    ('iu', 0, None, False),
    ('ưu', 0, None, False),
    ('iêu', 1, None, False),
    ('yêu', 1, None, False),
    ('ươu', 1, None, False),
    ('uyu', 1, None, False),

    # 4. Vần có âm cuối mũi (-m, -n, -ng, -nh)
    ('am', 0, None, False),
    ('ăm', 0, None, False),
    ('âm', 0, None, False),
    ('em', 0, None, False),
    ('êm', 0, None, False),
    ('im', 0, None, False),
    ('om', 0, None, False),
    ('ôm', 0, None, False),
    ('ơm', 0, None, False),
    ('um', 0, None, False),
    ('ưm', 0, None, False),
    ('iêm', 1, None, False),
    ('yêm', 1, None, False),
    ('uôm', 1, None, False),
    ('ươm', 1, None, False),
    ('oam', 1, None, False),
    ('oăm', 1, None, False),

    ('an', 0, None, False),
    ('ăn', 0, None, False),
    ('ân', 0, None, False),
    ('en', 0, None, False),
    ('ên', 0, None, False),
    ('in', 0, None, False),
    ('on', 0, None, False),
    ('ôn', 0, None, False),
    ('ơn', 0, None, False),
    ('un', 0, None, False),
    ('ưn', 0, None, False),
    ('iên', 1, None, False),
    ('yên', 1, None, False),
    ('uôn', 1, None, False),
    ('ươn', 1, None, False),
    ('oan', 1, None, False),
    ('oăn', 1, None, False),
    ('uân', 1, None, False),
    ('uyên', 2, None, False),

    ('ang', 0, None, False),
    ('ăng', 0, None, False),
    ('âng', 0, None, False),
    ('eng', 0, None, False),
    ('ong', 0, None, False),
    ('ông', 0, None, False),
    ('ung', 0, None, False),
    ('ưng', 0, None, False),
    ('iêng', 1, None, False),
    ('yêng', 1, None, False),
    ('uông', 1, None, False),
    ('ương', 1, None, False),
    ('oang', 1, None, False),
    ('oăng', 1, None, False),
    ('uâng', 1, None, False),
    ('oong', 1, None, False),

    ('anh', 0, None, False),
    ('ênh', 0, None, False),
    ('inh', 0, None, False),
    ('oanh', 1, None, False),
    ('uynh', 1, None, False),

    # 5. Vần có âm cuối tắc (-p, -t, -c, -ch) -> CHỈ mang dấu Sắc (4) hoặc Nặng (5)
    ('ap', 0, None, True),
    ('ăp', 0, None, True),
    ('âp', 0, None, True),
    ('ep', 0, None, True),
    ('êp', 0, None, True),
    ('ip', 0, None, True),
    ('op', 0, None, True),
    ('ôp', 0, None, True),
    ('ơp', 0, None, True),
    ('up', 0, None, True),
    ('ưp', 0, None, True),
    ('iêp', 1, None, True),
    ('yêp', 1, None, True),
    ('uôp', 1, None, True),
    ('ươp', 1, None, True),
    ('oap', 1, None, True),
    ('oăp', 1, None, True),

    ('at', 0, None, True),
    ('ăt', 0, None, True),
    ('ât', 0, None, True),
    ('et', 0, None, True),
    ('êt', 0, None, True),
    ('it', 0, None, True),
    ('ot', 0, None, True),
    ('ôt', 0, None, True),
    ('ơt', 0, None, True),
    ('ut', 0, None, True),
    ('ưt', 0, None, True),
    ('iêt', 1, None, True),
    ('yêt', 1, None, True),
    ('uôt', 1, None, True),
    ('ươt', 1, None, True),
    ('oat', 1, None, True),
    ('oăt', 1, None, True),
    ('uât', 1, None, True),
    ('uyêt', 2, None, True),

    ('ac', 0, None, True),
    ('ăc', 0, None, True),
    ('âc', 0, None, True),
    ('oc', 0, None, True),
    ('ôc', 0, None, True),
    ('uc', 0, None, True),
    ('ưc', 0, None, True),
    ('iêc', 1, None, True),
    ('uôc', 1, None, True),
    ('ươc', 1, None, True),
    ('oac', 1, None, True),
    ('oăc', 1, None, True),
    ('ooc', 1, None, True),

    ('ach', 0, None, True),
    ('êch', 0, None, True),
    ('ich', 0, None, True),
    ('oach', 1, None, True),
    ('uych', 1, None, True),
]


def apply_tone_to_rhyme(rhyme: str, vowel_idx: int, tone_idx: int) -> str:
    """Gắn thanh điệu vào nguyên âm tại vị trí vowel_idx trong vần."""
    if tone_idx == 0:
        return rhyme
    target_char = rhyme[vowel_idx]
    if target_char in VOWEL_TONE_TABLE:
        accented_char = VOWEL_TONE_TABLE[target_char][tone_idx]
        return rhyme[:vowel_idx] + accented_char + rhyme[vowel_idx + 1:]
    return rhyme


def is_valid_combination(onset: str, rhyme: str) -> bool:
    """
    Kiểm tra tính tương thích ngữ âm giữa phụ âm đầu và phần vần
    theo quy chuẩn chữ Quốc ngữ.
    """
    first_vowel = rhyme[0]

    # 1. Quy tắc c / k / qu:
    # 'k' chỉ đi với i, y, e, ê, ia, iê, yê
    if onset == 'k':
        return first_vowel in ('i', 'y', 'e', 'ê')

    # 'c' KHÔNG đi với i, y, e, ê (trừ trường hợp vần bắt đầu bằng bán âm o/u)
    if onset == 'c':
        if first_vowel in ('i', 'y', 'e', 'ê'):
            return False

    # 'qu' là âm đệm /w/, không ghép với các vần bắt đầu bằng o hoặc u
    if onset == 'qu':
        if first_vowel in ('o', 'u'):
            return False
        # qu không đi với ia, ưa, ua (chỉ đi với quyên, quyết, qua, que, quê, qui, quy...)
        if rhyme in ('ia', 'ua', 'ưa'):
            return False

    # 2. Quy tắc g / gh và ng / ngh:
    # 'gh' và 'ngh' BẮT BUỘC đi với i, e, ê, y
    if onset in ('gh', 'ngh'):
        return first_vowel in ('i', 'e', 'ê', 'y')

    # 'g' và 'ng' KHÔNG đi với i, e, ê, y (trừ khi có âm đệm o/u như: ngoại, ngoan, nguýt)
    if onset in ('g', 'ng'):
        if first_vowel in ('i', 'e', 'ê', 'y'):
            return False

    return True


def assemble_syllable(onset: str, accented_rhyme: str) -> str:
    """
    Ghép phụ âm đầu và phần vần có xử lý các trường hợp đặc biệt của chính tả:
    - 'gi' + 'i...' -> rút gọn thành 'gi...' (ví dụ: gi + in -> gìn, gi + i -> gì)
    """
    if onset == 'gi' and accented_rhyme.startswith(('i', 'ì', 'ỉ', 'ĩ', 'í', 'ị')):
        # Rút bớt một chữ 'i'
        return 'g' + accented_rhyme
    return onset + accented_rhyme


def generate_all_syllables() -> set:
    """Sinh toàn bộ tập hợp âm tiết tiếng Việt hợp lệ (cả dấu cũ và dấu mới)."""
    valid_set = set()

    for onset in ONSETS:
        for rhyme, new_idx, old_idx, is_stop in RHYMES:
            if not is_valid_combination(onset, rhyme):
                continue

            # Xác định các thanh điệu được phép
            # Âm tắc c/ch/p/t chỉ mang thanh Sắc (4) và Nặng (5)
            allowed_tones = (4, 5) if is_stop else (0, 1, 2, 3, 4, 5)

            for tone in allowed_tones:
                # 1. Sinh theo Kiểu Mới
                rhyme_new = apply_tone_to_rhyme(rhyme, new_idx, tone)
                syllable_new = assemble_syllable(onset, rhyme_new)
                valid_set.add(unicodedata.normalize('NFC', syllable_new.lower()))

                # 2. Sinh theo Kiểu Cũ (nếu có khác biệt)
                # Lưu ý: Với 'qu', dù là 'uy' thì kiểu cũ vẫn đặt dấu ở 'y' (quý, quỷ), không ai viết 'qúy'
                actual_old_idx = old_idx
                if onset == 'qu' and rhyme == 'uy':
                    actual_old_idx = new_idx

                if actual_old_idx is not None and actual_old_idx != new_idx:
                    rhyme_old = apply_tone_to_rhyme(rhyme, actual_old_idx, tone)
                    syllable_old = assemble_syllable(onset, rhyme_old)
                    valid_set.add(unicodedata.normalize('NFC', syllable_old.lower()))

    # Bổ sung các biến thể chữ Quốc ngữ cổ và từ phiên âm lịch sử thường gặp
    historical_additions = [
        # Dạng chính tả cũ 'qui' thay vì 'quy'
        'qui', 'quì', 'quí', 'quỉ', 'quĩ', 'quị',
        # Từ mượn hoặc từ tượng thanh quen thuộc trong văn học tiền chiến/miền Nam
        'ga', 'gà', 'gá', 'ra', 'rà', 'rá', 'bơ', 'bờ', 'bớ',
        'pin', 'pô', 'phanh', 'tanh', 'xích', 'kíp', 'mít',
        'sa', 'sà', 'sá', 'sả', 'sã', 'sạ',
        'va', 'và', 'vá', 'vả', 'vã', 'vạ',
        'giùm', 'dùm', 'đặng', 'bực', 'thoắt', 'thoăn', 'ngoẵng',
        'xoong', 'coóng', 'soóc', 'bót', 'mẹt', 'rượu', 'rượm'
    ]
    for word in historical_additions:
        valid_set.add(unicodedata.normalize('NFC', word.lower()))

    return valid_set


def vietnamese_sort_key(word: str) -> list:
    """
    Tạo khóa sắp xếp thứ tự bảng chữ cái tiếng Việt tự nhiên:
    a, ă, â, b, c, d, đ, e, ê, g, h, i, k, l, m, n, o, ô, ơ, p, q, r, s, t, u, ư, v, x, y
    """
    order = "aàảãáạăằẳẵắặâầẩẫấậbcdđeèẻẽéẹêềểễếệghiklmn" \
            "oòỏõóọôồổỗốộơờởỡớợpqrstuùủũúụưừửữứựvxyỳỷỹýỵ"
    char_map = {c: i for i, c in enumerate(order)}
    return [char_map.get(c, 999) for c in unicodedata.normalize('NFC', word)]


def main():
    print("=" * 60)
    print(" VIETLIT-PROOFREADER: BỘ SINH ÂM TIẾT TIẾNG VIỆT HỢP LỆ")
    print("=" * 60)

    # Xác định đường dẫn file đầu ra data/valid_syllables.txt
    repo_root = Path(__file__).resolve().parent.parent
    data_dir = repo_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    output_path = data_dir / "valid_syllables.txt"

    print("-> Đang khởi tạo và tính toán tổ hợp âm tiết...")
    syllables = generate_all_syllables()

    print(f"-> Tổng số âm tiết sinh được: {len(syllables):,} âm tiết.")
    print("-> Đang chuẩn hóa Unicode NFC và sắp xếp từ điển...")
    sorted_syllables = sorted(list(syllables), key=vietnamese_sort_key)

    print(f"-> Đang ghi dữ liệu ra tệp: {output_path}")
    with open(output_path, "w", encoding="utf-8") as f:
        for syl in sorted_syllables:
            f.write(syl + "\n")

    # Thống kê kiểm chứng các cặp dấu cũ/mới tiêu biểu
    sample_pairs = [
        ("hoà", "hòa"),
        ("thuỷ", "thủy"),
        ("khoè", "khòe"),
        ("toạ", "tọa"),
        ("thuỵ", "thụy"),
        ("qui", "quy"),
        ("giùm", "dùm"),
    ]

    print("\n--- KIỂM CHỨNG CÁC CẶP CHÍNH TẢ LỊCH SỬ TIÊU BIỂU ---")
    for old_s, new_s in sample_pairs:
        has_old = "✓" if old_s in syllables else "✗"
        has_new = "✓" if new_s in syllables else "✗"
        print(f"  • Cũ: {old_s:<6} [{has_old}]   |   Mới: {new_s:<6} [{has_new}]")

    print("\n[THÀNH CÔNG] Tệp valid_syllables.txt đã sẵn sàng!")
    print(f"Vị trí: {output_path.resolve()}\n")


if __name__ == "__main__":
    main()
