#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/nlp_segmenter.py
---------------------
Bộ xử lý lỗi dính chữ OCR theo kiến trúc 2 tầng chuẩn sản xuất:
- Tầng 1: Đối soát chéo O(1) với từ điển từ ghép master (data/dictionary.jsonl).
- Tầng 2: Quy hoạch động Viterbi có ràng buộc tần suất từ thực tế (unigram_freq.txt).
- Bảo vệ tuyệt đối các âm tiết đơn dài (nghiêng, hoàng) và từ sai chính tả (ngưòi).
"""

import json
import math
import os
import sys
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Đảm bảo đường dẫn gốc dự án luôn có trong sys.path khi chạy trực tiếp
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.phonotactics import get_validator, is_valid_syllable

# Độ dài tối thiểu của chuỗi nghi ngờ dính chữ (ít nhất 2 tiếng, mỗi tiếng >= 2 ký tự)
MIN_MERGED_LENGTH = 4
# Độ dài tối đa của một âm tiết tiếng Việt (nghiêng, nghiêng = 7 ký tự)
MAX_SYLLABLE_LENGTH = 8
# Tần suất tối thiểu của một từ độc lập trong văn bản để được tham gia bóc tách Viterbi
MIN_WORD_FREQUENCY = 10
# Điểm phạt cho mỗi nhát cắt từ để ưu tiên các từ hoàn chỉnh
WORD_PENALTY = 2.5
# 8 nguyên âm duy nhất trong toàn bộ tiếng Việt có thể đứng độc lập làm từ vựng có nghĩa
VALID_SINGLE_CHAR_WORDS = {'ý', 'ở', 'ổ', 'ả', 'a', 'ô', 'ơ', 'ê'}

class ViterbiSegmenter:
    """
    Bộ phân đoạn từ dính chữ kết hợp tra cứu Từ điển Master và Thuật toán Viterbi.
    """

    _instance: Optional['ViterbiSegmenter'] = None
    _compound_map: Dict[str, str] = {}         # "tronglòng" -> "trong lòng"
    _unigram_counts: Dict[str, int] = {}
    _unigram_log_probs: Dict[str, float] = {}
    _total_words: int = 0
    _is_loaded: bool = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(ViterbiSegmenter, cls).__new__(cls)
        return cls._instance

    def __init__(self, data_dir: Optional[Path] = None):
        if not self._is_loaded:
            repo_root = Path(__file__).resolve().parent.parent
            base_dir = data_dir or (repo_root / "data")
            self.load_master_compounds(base_dir / "dictionary.jsonl")
            self.load_unigram_frequencies(base_dir / "unigram_freq.txt")
            self.__class__._is_loaded = True

    @classmethod
    def load_master_compounds(cls, dict_path: Path):
        """
        Nạp toàn bộ từ ghép từ dictionary.jsonl và tạo chỉ mục chuỗi nén (Compact Index):
        'trong lòng' -> {'tronglòng': 'trong lòng'}
        'mặt trời'   -> {'mặttrời': 'mặt trời'}
        """
        cls._compound_map.clear()
        if not dict_path.exists():
            return

        with open(dict_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    w = unicodedata.normalize('NFC', item.get("word", "").strip())
                    # Chỉ lấy các từ ghép có khoảng trắng hoặc gạch nối
                    if " " in w or "-" in w:
                        spaced_phrase = w.replace("-", " ")
                        compact_key = spaced_phrase.replace(" ", "").lower()
                        # Lưu dạng chuẩn cách rời bằng 1 khoảng trắng
                        cls._compound_map[compact_key] = spaced_phrase
                except json.JSONDecodeError:
                    continue

    @classmethod
    def load_unigram_frequencies(cls, freq_path: Path):
        """Nạp bảng tần suất unigram thực tế phục vụ thuật toán Viterbi."""
        cls._unigram_counts.clear()
        cls._unigram_log_probs.clear()

        counts: Dict[str, int] = {}
        total_count = 0

        if freq_path.exists():
            with open(freq_path, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 2 and parts[-1].isdigit():
                        w = unicodedata.normalize('NFC', parts[0].lower())
                        cnt = int(parts[-1])
                        counts[w] = cnt
                        total_count += cnt
        else:
            # Dự phòng: Nạp các âm tiết hợp lệ với tần suất cơ bản
            validator = get_validator()
            for syl in validator._valid_syllables:
                counts[syl] = 20
                total_count += 20

        cls._total_words = max(total_count, 1)
        cls._unigram_counts = counts

        # Tính toán log-probabilities
        log_total = math.log(cls._total_words)
        for w, cnt in counts.items():
            cls._unigram_log_probs[w] = math.log(cnt) - log_total

    def get_word_log_prob(self, word: str) -> float:
        """Lấy điểm log-prob của một từ vựng có tần suất thực tế."""
        norm_w = unicodedata.normalize('NFC', word.lower())
        if norm_w in self._unigram_log_probs:
            return self._unigram_log_probs[norm_w]
        return -999.0

    def is_candidate_for_split(self, word: str) -> bool:
        """
        Kiểm tra điều kiện tiên quyết trước khi xem xét tách chữ:
        - Không chứa dấu gạch nối (vì quốc-gia đã là gạch nối của tác giả).
        - Độ dài tối thiểu 4 ký tự.
        - TUYỆT ĐỐI KHÔNG ĐƯỢC là một âm tiết đơn hợp lệ (nghiêng, hoàng không bao giờ là dính chữ).
        """
        if not word or '-' in word:
            return False

        norm = unicodedata.normalize('NFC', word.strip())
        if len(norm) < MIN_MERGED_LENGTH:
            return False

        # Nếu bản thân chuỗi đã là âm tiết tiếng Việt hợp lệ -> GIỮ NGUYÊN
        if is_valid_syllable(norm):
            return False

        return True

    def _restore_casing(self, original: str, spaced_result: str) -> str:
        """Khôi phục trạng thái viết hoa của từ gốc cho chuỗi sau khi tách."""
        segments = spaced_result.split()
        if not segments:
            return spaced_result

        # 1. Viết hoa toàn bộ: ĐÃĐẾN -> ĐÃ ĐẾN
        if original.isupper():
            return " ".join(s.upper() for s in segments)

        # 2. Viết hoa chữ cái đầu: Tronglòng -> Trong lòng
        if original[0].isupper():
            first = segments[0]
            first_cased = first[0].upper() + first[1:]
            return " ".join([first_cased] + segments[1:])

        # 3. Viết thường: tronglòng -> trong lòng
        return " ".join(segments)

    def segment(self, text: str) -> Optional[List[str]]:
        """
        Tách chuỗi ký tự dính chữ thành danh sách các từ có nghĩa.
        Trả về: [w1, w2, ...] hoặc None nếu chuỗi không phải là dính chữ hợp lệ.
        """
        if not self.is_candidate_for_split(text):
            return None

        norm_text = unicodedata.normalize('NFC', text.strip())
        lower_key = norm_text.lower()

        # =====================================================================
        # TẦNG 1: ĐỐI SOÁT TỪ ĐIỂN TỪ GHÉP MASTER O(1) (Chính xác tuyệt đối)
        # =====================================================================
        if lower_key in self._compound_map:
            matched_phrase = self._compound_map[lower_key]
            # Tách thành danh sách từ
            return matched_phrase.split()

        # =====================================================================
        # TẦNG 2: THUẬT TOÁN VITERBI QUY HOẠCH ĐỘNG CÓ RÀNG BUỘC TỪ VỰNG THỰC TẾ
        # (Dành cho các cụm cú pháp tự do như: 'đãđến', 'nóicùngnhau')
        # =====================================================================
        n = len(lower_key)
        dp: List[float] = [-math.inf] * (n + 1)
        parent: List[int] = [-1] * (n + 1)
        dp[0] = 0.0

        for i in range(1, n + 1):
            min_j = max(0, i - MAX_SYLLABLE_LENGTH)
            for j in range(min_j, i):
                sub = lower_key[j:i]

                # RÀNG BUỘC 0 (Ngôn ngữ học): Từ độc lập phải có >= 2 ký tự (trừ 8 từ đơn đặc thù).
                # Ngăn chặn tuyệt đối việc coi các ký tự chữ cái như 'ò', 'i' là một từ trong câu.
                if len(sub) == 1 and sub not in VALID_SINGLE_CHAR_WORDS:
                    continue

                # Ràng buộc 1: Mỗi mảnh cắt bắt buộc phải là âm tiết tiếng Việt hợp lệ
                if not is_valid_syllable(sub):
                    continue

                # Ràng buộc 2: Mảnh cắt bắt buộc phải là từ có tần suất sử dụng thực tế trong từ điển
                # (Loại bỏ triệt để việc bẻ các từ lỗi thành các âm tiết lý thuyết hiếm như 'ngưòi' -> 'ngư' + 'òi')
                if self._unigram_counts.get(sub, 0) < MIN_WORD_FREQUENCY:
                    continue

                score = dp[j] + self.get_word_log_prob(sub) - WORD_PENALTY
                if score > dp[i]:
                    dp[i] = score
                    parent[i] = j

        # Nếu không có đường đi nào tới cuối chuỗi -> không thể tách hợp lệ
        if dp[n] == -math.inf:
            return None

        # Truy vết kết quả
        segments: List[str] = []
        curr = n
        while curr > 0:
            prev = parent[curr]
            if prev == -1:
                return None
            segments.append(lower_key[prev:curr])
            curr = prev

        segments.reverse()

        # Chỉ chấp nhận nếu tách thành từ 2 từ trở lên
        if len(segments) <= 1:
            return None

        return segments

    def split_merged_word(self, word: str) -> Optional[str]:
        """
        Hàm giao tiếp chính:
        Nhận vào chuỗi nghi vấn 'tronglòng' -> Trả về 'trong lòng' (hoặc None nếu không phải dính chữ).
        """
        segs = self.segment(word)
        if segs and len(segs) > 1:
            raw_spaced = " ".join(segs)
            return self._restore_casing(word, raw_spaced)
        return None


# Module-level API tiện ích
_global_segmenter: Optional[ViterbiSegmenter] = None


def get_segmenter() -> ViterbiSegmenter:
    global _global_segmenter
    if _global_segmenter is None:
        _global_segmenter = ViterbiSegmenter()
    return _global_segmenter


def split_ocr_merged_word(word: str) -> Optional[str]:
    return get_segmenter().split_merged_word(word)


# ==============================================================================
# BỘ KIỂM THỬ TRỰC TIẾP (Self-Test)
# ==============================================================================
if __name__ == "__main__":
    print("=" * 68)
    print(" CORE/NLP_SEGMENTER: KIỂM THỬ BÓC TÁCH DÍNH CHỮ CHUẨN SẢN XUẤT")
    print("=" * 68)

    segmenter = ViterbiSegmenter()
    print(f"-> Nạp từ điển từ ghép master: {len(segmenter._compound_map):,} cụm từ.")
    print(f"-> Nạp bảng tần suất unigram : {len(segmenter._unigram_counts):,} từ vựng thực tế.")

    # 1. Các trường hợp dính chữ thực tế bắt buộc phải tách đúng
    test_merged_cases = [
        ("tronglòng", "trong lòng"),
        ("ôngấy", "ông ấy"),
        ("mặttrời", "mặt trời"),
        ("đãđến", "đã đến"),
        ("ngườita", "người ta"),
        ("khôngthể", "không thể"),
        ("nóicùngnhau", "nói cùng nhau"),
        ("Tronglòng", "Trong lòng"),
        ("ĐÃĐẾN", "ĐÃ ĐẾN"),
        ("Ngườiấy", "Người ấy"),
    ]

    print("\n-> 1. Kiểm thử tách các chuỗi dính chữ thực tế:")
    for raw, expected in test_merged_cases:
        actual = segmenter.split_merged_word(raw)
        status = "✓ ĐẠT" if actual == expected else "✗ SAI"
        print(f"  • {raw:<14} -> {str(actual):<18} | Kỳ vọng: {expected} [{status}]")
        assert actual == expected, f"Lỗi tách chữ: {raw} -> {actual} != {expected}"

    # 2. Các trường hợp BẮT BUỘC KHÔNG ĐƯỢC TÁCH (Âm tiết đơn dài, từ ghép gạch nối, lỗi chính tả)
    negative_cases = [
        "nghiêng",     # Âm tiết đơn dài 7 chữ cái
        "hoàng",       # Âm tiết đơn dài 5 chữ cái
        "thương",      # Âm tiết đơn dài 6 chữ cái
        "quốc-gia",    # Từ ghép có gạch nối
        "ngưòi",       # Lỗi chính tả (OCR sai dấu của 'người') -> Phải giữ nguyên để SymSpell sửa!
        "nhà",         # Từ đơn thông thường
    ]

    print("\n-> 2. Kiểm thử bảo vệ nguyên vẹn (Tuyệt đối không xé bậy):")
    for word in negative_cases:
        res = segmenter.split_merged_word(word)
        status = "✓ BẢO VỆ TỐT" if res is None else f"✗ LỖI XÉ BẬY ({res})"
        print(f"  • {word:<14} -> {str(res):<18} [{status}]")
        assert res is None, f"Lỗi: Không được xé từ nguyên bản/sai chính tả: {word}!"

    print("\n[THÀNH CÔNG] Module core/nlp_segmenter.py đạt chuẩn sản xuất 100%!")
