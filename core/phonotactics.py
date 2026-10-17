#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/phonotactics.py
--------------------
Bộ đối soát âm tiết tiếng Việt hợp lệ mặt chữ bằng cấu trúc set() O(1):
1. Nạp và lưu cache bộ ~20.000 âm tiết hợp lệ từ data/valid_syllables.txt.
2. Kiểm tra tính hợp lệ của từ đơn và từ ghép gạch nối (quốc-gia).
3. Nhận diện trường phái đặt dấu thanh: Kiểu cũ (hoà, thuỷ) vs Kiểu mới (hòa, thủy).
4. Cung cấp nguyên nhân vi phạm cấu trúc ngữ âm học phục vụ hiển thị trên UI.
"""

import os
import re
import unicodedata
from pathlib import Path
from typing import List, Optional, Set, Tuple, Union

try:
    from core.tokenizer import Token
except ImportError:
    # Hỗ trợ chạy độc lập khi test
    Token = None


# Các nguyên âm mang dấu thanh đặc thù cho việc phân biệt Cũ vs Mới
# Kiểu cũ: Dấu nằm trên âm đệm 'o', 'u' (hoà, toà, thuỷ, loè...)
OLD_STYLE_OA_OE = re.compile(r'^[a-zà-ỹđ]*[òóỏõọ][ae]$', re.IGNORECASE)
OLD_STYLE_UY = re.compile(r'^(?!qu)[a-zà-ỹđ]*[ùúủũụ]y$', re.IGNORECASE)

# Kiểu mới: Dấu nằm trên âm chính 'a', 'e', 'y' (hòa, tòa, thủy, lòe...)
NEW_STYLE_OA_OE = re.compile(r'^[a-zà-ỹđ]*o[àáảãạèéẻẽẹ]$', re.IGNORECASE)
NEW_STYLE_UY = re.compile(r'^[a-zà-ỹđ]*u[ỳýỷỹỵ]$', re.IGNORECASE)


class PhonotacticsValidator:
    """
    Bộ xác thực âm tiết tiếng Việt dựa trên bảng âm tiết chuẩn đã được tiền sinh.
    Sử dụng mô hình Singleton / Lazy-loading để nạp tệp valid_syllables.txt đúng 1 lần.
    """

    _instance: Optional['PhonotacticsValidator'] = None
    _valid_syllables: Set[str] = set()
    _is_loaded: bool = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(PhonotacticsValidator, cls).__new__(cls)
        return cls._instance

    def __init__(self, syllables_file: Optional[Union[str, Path]] = None):
        if not self._is_loaded:
            self.load_syllables(syllables_file)

    @classmethod
    def load_syllables(cls, file_path: Optional[Union[str, Path]] = None) -> int:
        """Nạp tập hợp âm tiết từ tệp văn bản vào set()."""
        if file_path:
            path = Path(file_path)
        else:
            # Đường dẫn mặc định: data/valid_syllables.txt
            repo_root = Path(__file__).resolve().parent.parent
            path = repo_root / "data" / "valid_syllables.txt"

        if not path.exists():
            raise FileNotFoundError(
                f"[!] Không tìm thấy tệp danh mục âm tiết: {path.resolve()}\n"
                "-> Vui lòng chạy lệnh: python tools/build_syllables.py trước!"
            )

        cls._valid_syllables.clear()
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                syl = unicodedata.normalize('NFC', line.strip().lower())
                if syl:
                    cls._valid_syllables.add(syl)

        cls._is_loaded = True
        return len(cls._valid_syllables)

    @property
    def total_syllables(self) -> int:
        return len(self._valid_syllables)

    def is_valid_syllable(self, syllable: str) -> bool:
        """
        Kiểm tra một âm tiết đơn lẻ có hợp lệ mặt chữ tiếng Việt hay không.
        Độ phức tạp: O(1).
        """
        if not syllable:
            return False
        norm = unicodedata.normalize('NFC', syllable.strip().lower())
        return norm in self._valid_syllables

    def is_valid_token(self, token_or_word: Union[str, any]) -> bool:
        """
        Kiểm tra một token từ vựng (từ đơn hoặc từ ghép có gạch nối).
        Nếu là từ ghép (quốc-gia), toàn bộ các tiếng con bắt buộc phải hợp lệ.
        """
        if not token_or_word:
            return False

        # Nếu truyền vào là đối tượng Token từ core.tokenizer
        if hasattr(token_or_word, "syllables"):
            return all(self.is_valid_syllable(s) for s in token_or_word.syllables)

        # Nếu truyền vào là chuỗi string
        word_str = str(token_or_word).strip()
        if '-' in word_str:
            parts = word_str.split('-')
            return all(self.is_valid_syllable(p) for p in parts if p)

        return self.is_valid_syllable(word_str)

    def get_invalid_syllables(self, token_or_word: Union[str, any]) -> List[str]:
        """Trả về danh sách các âm tiết con bị lỗi ngữ âm trong từ."""
        if not token_or_word:
            return []

        if hasattr(token_or_word, "syllables"):
            syllables = token_or_word.syllables
        else:
            syllables = str(token_or_word).strip().split('-')

        return [s for s in syllables if s and not self.is_valid_syllable(s)]

    def detect_tone_style(self, syllable: str) -> str:
        """
        Phân loại trường phái đặt dấu thanh của âm tiết:
        - 'old'     : Dấu kiểu cũ (hoà, toà, thuỷ, loè...)
        - 'new'     : Dấu kiểu mới (hòa, tòa, thủy, lòe...)
        - 'common'  : Cả cũ và mới đặt dấu giống hệt nhau (người, tiến, cuốn...)
        - 'invalid' : Không phải âm tiết tiếng Việt hợp lệ
        """
        if not self.is_valid_syllable(syllable):
            return "invalid"

        norm = unicodedata.normalize('NFC', syllable.strip().lower())

        if OLD_STYLE_OA_OE.match(norm) or OLD_STYLE_UY.match(norm):
            return "old"
        if NEW_STYLE_OA_OE.match(norm) or NEW_STYLE_UY.match(norm):
            return "new"

        return "common"

    def explain_invalidity(self, syllable: str) -> str:
        """Phân tích sơ bộ nguyên nhân âm tiết bị xem là bất khả thi trong tiếng Việt."""
        if self.is_valid_syllable(syllable):
            return "Âm tiết hợp lệ"

        norm = unicodedata.normalize('NFC', syllable.strip().lower())

        # 1. Chứa ký tự không thuộc chữ Quốc ngữ
        if re.search(r'[^a-zà-ỹđ]', norm):
            return "Chứa ký tự lạ hoặc rác scan OCR"

        # 2. Vần có âm tắc nhưng không mang thanh sắc hoặc nặng
        # c, ch, p, t chỉ đi với sắc / nặng
        if re.search(r'(c|ch|p|t)$', norm):
            # Kiểm tra nếu mang dấu huyền, hỏi, ngã, hoặc không dấu
            has_other_tones = re.search(r'[àằầèềìòồờùừỳảẳẩẻểỉỏổởủửỷãẵẫẽễĩõỗỡũữỹ]', norm)
            if has_other_tones:
                return "Âm cuối khép (c, ch, p, t) không thể mang thanh huyền/hỏi/ngã"

        # 3. Nguyên âm ngắn ă, â đứng mở (không có âm cuối)
        if re.search(r'[ăằắẳẵặâầấẩẫậ]$', norm):
            return "Nguyên âm ngắn (ă, â) không thể đứng ở cuối âm tiết mở"

        return "Tổ hợp phụ âm và nguyên âm không tồn tại trong tiếng Việt"


# Khởi tạo instance tiện ích toàn cục (Module-level API)
_global_validator: Optional[PhonotacticsValidator] = None


def get_validator() -> PhonotacticsValidator:
    """Lấy thể hiện duy nhất (Singleton) của PhonotacticsValidator."""
    global _global_validator
    if _global_validator is None:
        _global_validator = PhonotacticsValidator()
    return _global_validator


def is_valid_syllable(syllable: str) -> bool:
    """Hàm nhanh kiểm tra một âm tiết O(1)."""
    return get_validator().is_valid_syllable(syllable)


def is_valid_token(token_or_word: Union[str, any]) -> bool:
    """Hàm nhanh kiểm tra một token hoặc từ ghép O(1)."""
    return get_validator().is_valid_token(token_or_word)


# ==============================================================================
# BỘ KIỂM THỬ TRỰC TIẾP (Self-Test)
# ==============================================================================
if __name__ == "__main__":
    import time

    print("=" * 68)
    print(" CORE/PHONOTACTICS: KIỂM THỬ ĐỐI SOÁT ÂM TIẾT O(1)")
    print("=" * 68)

    val = PhonotacticsValidator()
    print(f"-> Đã nạp thành công: {val.total_syllables:,} âm tiết vào set() O(1).")

    # 1. Kiểm tra tính hợp lệ của các cặp dấu cũ/mới và từ lịch sử
    valid_samples = [
        "hoà", "hòa", "thuỷ", "thủy", "khoè", "khòe",
        "qui", "quy", "người", "nhơn", "đặng", "rượu",
        "quốc-gia", "văn-học", "tự-do", "anh-hùng"
    ]

    print("\n-> 1. Kiểm tra các từ hợp lệ (Cả cũ và mới):")
    for word in valid_samples:
        is_ok = val.is_valid_token(word)
        style = val.detect_tone_style(word.split('-')[0]) if '-' not in word else "compound"
        print(f"  • {word:<12} : {'✓ HỢP LỆ' if is_ok else '✗ LỖI'} (Trường phái: {style})")
        assert is_ok, f"Lỗi: {word} phải được xác nhận là hợp lệ!"

    # 2. Kiểm tra phát hiện lỗi OCR dị dạng
    invalid_samples = [
        "ngưòi",   # Sai dấu
        "bănh",    # ă đứng trước nh
        "hoặe",    # e ở cuối sau ă
        "lờinói",  # dính từ
        "nghi-thwjc", # rác OCR
        "văn-ngưòi"   # Từ ghép dính 1 tiếng lỗi
    ]

    print("\n-> 2. Kiểm tra phát hiện lỗi OCR vô nghĩa:")
    for bad_word in invalid_samples:
        is_ok = val.is_valid_token(bad_word)
        err_parts = val.get_invalid_syllables(bad_word)
        reason = val.explain_invalidity(err_parts[0]) if err_parts else "N/A"
        print(f"  • {bad_word:<12} : {'✗ PHÁT HIỆN LỖI OCR' if not is_ok else '✓ BỎ SÓT LỖI'}")
        print(f"    └─ Chi tiết: Tiếng sai {err_parts} -> {reason}")
        assert not is_ok, f"Lỗi: Không được bỏ lọt từ sai {bad_word}!"

    # 3. Benchmark tốc độ tra cứu O(1)
    print("\n-> 3. Đo lường tốc độ thực thi O(1) trên 100.000 lượt tra cứu...")
    test_word = "người"
    start_time = time.perf_counter()
    for _ in range(100_000):
        _ = val.is_valid_syllable(test_word)
    duration = time.perf_counter() - start_time

    print(f"  ✓ Thời gian thực hiện: {duration:.4f} giây")
    print(f"  ✓ Tốc độ đạt được    : {100_000 / duration:,.0f} lượt tra cứu / giây.")

    print("\n[THÀNH CÔNG] Module core/phonotactics.py hoàn thành xuất sắc toàn bộ bài test!")
