#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/spell_checker.py
---------------------
Bộ soát lỗi chính tả và đề xuất từ thay thế 4 tầng cho văn học chữ Quốc ngữ:
1. Tầng 0: Nhận diện chữ số La Mã (I, II, IV, XIX...) và từ viết tắt.
2. Tầng 1: Đối soát Whitelist và Thực thể Tên riêng (NER).
3. Tầng 2: Đối soát Từ điển Master (dictionary.jsonl).
4. Tầng 3: Đối soát Ngữ âm học Phonotactics O(1) (bảo tồn dấu cũ/mới và gạch nối).
5. Tầng 4: Kích hoạt Viterbi (tách dính chữ) hoặc SymSpell (sửa lỗi ký tự OCR).
"""

import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Đảm bảo đường dẫn gốc của dự án luôn có trong sys.path khi chạy trực tiếp
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from symspellpy import SymSpell, Verbosity

from core.nlp_ner import Entity, extract_entities, is_token_in_entities
from core.nlp_segmenter import get_segmenter
from core.phonotactics import get_validator, is_valid_syllable
from core.tokenizer import Token, tokenize_words

# Pattern nhận diện chữ số La Mã (dùng trong đánh số chương/tập sách cổ)
ROMAN_NUMERAL_RE = re.compile(
    r'^(?=[MDCLXVI])M*(C[MD]|D?C*)(X[CL]|L?X*)(I[XV]|V?I*)$',
    re.IGNORECASE
)


@dataclass
class SpellingIssue:
    """Đối tượng lưu trữ thông tin về một lỗi chính tả phát hiện được."""
    token: Token
    issue_type: str        # 'TYPO_OCR' (sai từ), 'OCR_SPLIT' (dính chữ)
    original: str          # Từ gốc trong văn bản
    start: int             # Tọa độ ký tự bắt đầu
    end: int               # Tọa độ ký tự kết thúc
    suggestions: List[str] # Danh sách các từ gợi ý thay thế
    reason: str            # Giải thích nguyên nhân lỗi
    confidence: float      # Độ tự tin của gợi ý (0.0 đến 1.0)

    def __repr__(self) -> str:
        sug_str = ", ".join(self.suggestions[:3])
        return f"Issue({self.issue_type}, '{self.original}' -> [{sug_str}], pos={self.start}:{self.end})"


class SpellChecker:
    """
    Hệ thống kiểm tra lỗi chính tả và gợi ý sửa lỗi OCR tích hợp SymSpell.
    """

    _instance: Optional['SpellChecker'] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SpellChecker, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, data_dir: Optional[Path] = None):
        if self._initialized:
            return

        repo_root = Path(__file__).resolve().parent.parent
        self.data_dir = data_dir or (repo_root / "data")

        # 1. Khởi tạo các bộ lọc phụ trợ
        self.validator = get_validator()
        self.segmenter = get_segmenter()

        # 2. Nạp Whitelist và Master Dictionary
        self.whitelist: Set[str] = set()
        self.master_dict: Set[str] = set()
        self.whitelist_path = self.data_dir / "whitelist.txt"
        self.dict_path = self.data_dir / "dictionary.jsonl"
        self.freq_path = self.data_dir / "unigram_freq.txt"

        self.load_whitelist()
        self.load_master_dictionary()

        # 3. Khởi tạo SymSpell
        self.sym_spell = SymSpell(max_dictionary_edit_distance=2, prefix_length=7)
        self.load_symspell_dictionary()

        self._initialized = True

    def load_whitelist(self):
        """Nạp danh sách từ whitelist do người dùng chỉ định."""
        self.whitelist.clear()
        if self.whitelist_path.exists():
            with open(self.whitelist_path, "r", encoding="utf-8") as f:
                for line in f:
                    w = unicodedata.normalize('NFC', line.strip().lower())
                    if w:
                        self.whitelist.add(w)

    def add_to_whitelist(self, word: str) -> bool:
        """Thêm một từ vào whitelist và lưu ngay vào tệp."""
        norm_w = unicodedata.normalize('NFC', word.strip().lower())
        if not norm_w or norm_w in self.whitelist:
            return False

        self.whitelist.add(norm_w)
        with open(self.whitelist_path, "a", encoding="utf-8") as f:
            f.write(norm_w + "\n")
        return True

    def load_master_dictionary(self):
        """Nạp danh mục từ vựng từ data/dictionary.jsonl."""
        self.master_dict.clear()
        if self.dict_path.exists():
            with open(self.dict_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                        w = unicodedata.normalize('NFC', item.get("word", "").lower())
                        if w:
                            self.master_dict.add(w)
                    except json.JSONDecodeError:
                        continue

    def load_symspell_dictionary(self):
        """Nạp tần suất từ vào SymSpell."""
        if self.freq_path.exists():
            self.sym_spell.load_dictionary(
                str(self.freq_path),
                term_index=0,
                count_index=1,
                separator=" ",
                encoding="utf-8"
            )
        else:
            # Dự phòng: Nạp các âm tiết hợp lệ với tần suất cơ sở
            for syl in self.validator._valid_syllables:
                self.sym_spell.create_dictionary_entry(syl, 10)

    def _restore_casing(self, target_word: str, suggestion: str) -> str:
        """Khôi phục trạng thái viết hoa của từ gốc cho gợi ý."""
        if target_word.isupper():
            return suggestion.upper()
        if target_word[0].isupper():
            return suggestion[0].upper() + suggestion[1:]
        return suggestion.lower()

    def check_token(self, token: Token, is_in_entity: bool = False) -> Optional[SpellingIssue]:
        """
        Kiểm tra 1 Token từ vựng qua 4 tầng kiểm định.
        Trả về: SpellingIssue nếu phát hiện lỗi, ngược lại trả về None.
        """
        raw_text = token.text
        norm_lower = token.lower

        # --- TẦNG 0: CHỮ SỐ LA MÃ & NGOẠI LỆ ---
        if ROMAN_NUMERAL_RE.match(raw_text):
            return None

        # --- TẦNG 1: THỰC THỂ TÊN RIÊNG & WHITELIST ---
        if is_in_entity:
            return None
        if norm_lower in self.whitelist:
            return None

        # --- TẦNG 2: TỪ ĐIỂN MASTER (DICTIONARY.JSONL) ---
        if norm_lower in self.master_dict:
            return None

        # --- TẦNG 3: BỘ LỌC NGỮ ÂM HỌC PHONOTACTICS O(1) ---
        # 3.1 Nếu là từ ghép có gạch nối (quốc-gia)
        if token.is_hyphenated:
            invalid_syllables = [s for s in token.syllables if not self.validator.is_valid_syllable(s)]
            # Nếu toàn bộ các tiếng đều hợp lệ -> PASS (Bảo tồn từ ghép gạch nối!)
            if not invalid_syllables:
                return None

            # Nếu có tiếng bị lỗi OCR (ví dụ: quốc-giia)
            # Dùng SymSpell sửa riêng tiếng bị lỗi và ghép lại
            repaired_suggestions = []
            err_syl = invalid_syllables[0]
            sym_results = self.sym_spell.lookup(err_syl, Verbosity.CLOSEST, max_edit_distance=2)

            for item in sym_results[:5]:
                if self.validator.is_valid_syllable(item.term):
                    # Thay thế tiếng lỗi bằng tiếng đúng
                    fixed_parts = [item.term if s == err_syl else s for s in token.syllables]
                    sug_compound = "-".join(fixed_parts)
                    repaired_suggestions.append(self._restore_casing(raw_text, sug_compound))

            return SpellingIssue(
                token=token,
                issue_type="TYPO_OCR",
                original=raw_text,
                start=token.start,
                end=token.end,
                suggestions=repaired_suggestions or [raw_text.replace(err_syl, "...")],
                reason=f"Tiếng '{err_syl}' trong từ ghép bị lỗi chính tả",
                confidence=0.85
            )

        # 3.2 Nếu là từ đơn
        if self.validator.is_valid_syllable(norm_lower):
            # Từ đơn hợp lệ mặt chữ (bao gồm cả hoà và hòa) -> PASS
            return None

        # --- TẦNG 4: PHÂN ĐOÀN LỖI & ĐỀ XUẤT THAY THẾ ---

        # 4.1 Kiểm tra xem có phải là lỗi DÍNH CHỮ (OCR_SPLIT) không
        split_result = self.segmenter.split_merged_word(raw_text)
        if split_result:
            return SpellingIssue(
                token=token,
                issue_type="OCR_SPLIT",
                original=raw_text,
                start=token.start,
                end=token.end,
                suggestions=[split_result],
                reason="Dính chữ do lỗi quét OCR",
                confidence=0.95
            )

        # 4.2 Lỗi SAI CHÍNH TẢ / RÁC KÝ TỰ (TYPO_OCR) -> Gọi SymSpell
        suggestions = []
        sym_results = self.sym_spell.lookup(norm_lower, Verbosity.CLOSEST, max_edit_distance=2)

        for item in sym_results:
            # Chỉ lấy các gợi ý là âm tiết tiếng Việt hợp lệ hoặc có trong từ điển
            if self.validator.is_valid_syllable(item.term) or item.term in self.master_dict:
                cased_sug = self._restore_casing(raw_text, item.term)
                if cased_sug not in suggestions:
                    suggestions.append(cased_sug)
            if len(suggestions) >= 5:
                break

        explanation = self.validator.explain_invalidity(norm_lower)

        return SpellingIssue(
            token=token,
            issue_type="TYPO_OCR",
            original=raw_text,
            start=token.start,
            end=token.end,
            suggestions=suggestions,
            reason=explanation,
            confidence=0.90 if suggestions else 0.50
        )

    def check_document(self, text: str) -> List[SpellingIssue]:
        """
        Quét toàn bộ đoạn văn bản và trả về danh sách các lỗi chính tả phát hiện được.
        """
        if not text:
            return []

        # 1. Trích xuất thực thể tên riêng để bảo vệ
        entities = extract_entities(text)

        # 2. Tách từ vựng
        tokens = tokenize_words(text)

        issues: List[SpellingIssue] = []

        # 3. Duyệt và kiểm tra từng token
        for tok in tokens:
            in_entity = is_token_in_entities(tok.start, tok.end, entities)
            issue = self.check_token(tok, is_in_entity=in_entity)
            if issue:
                issues.append(issue)

        return issues


# Module-level API tiện ích
_global_checker: Optional[SpellChecker] = None


def get_spell_checker() -> SpellChecker:
    """Lấy thể hiện Singleton của SpellChecker."""
    global _global_checker
    if _global_checker is None:
        _global_checker = SpellChecker()
    return _global_checker


def check_text(text: str) -> List[SpellingIssue]:
    """Hàm nhanh soát lỗi chính tả cho một đoạn văn bản."""
    return get_spell_checker().check_document(text)


# ==============================================================================
# BỘ KIỂM THỬ TRỰC TIẾP (Self-Test)
# ==============================================================================
if __name__ == "__main__":
    print("=" * 68)
    print(" CORE/SPELL_CHECKER: KIỂM THỬ HỆ THỐNG SOÁT LỖI 4 TẦNG & SYMSPELL")
    print("=" * 68)

    checker = SpellChecker()
    print("-> Đã khởi tạo SpellChecker thành công.")

    sample_paragraph = (
        "— Thưa quan Tổng đốc, thầy Thông Chánh đã tới dinh Gia Định trong Chương I.\n"
        "Người-ta thường nói hoà với thuận, nhưng tronglòng hắn lại có ý khác.\n"
        "Bức tranh này thật đep, nhưng ngưòi vẽ đã đi xa.\n"
        "Họ bàn về việc quốc-giia và những điều canh-tân."
    )

    print("\n-> Văn bản kiểm thử:")
    print("-" * 50)
    print(sample_paragraph)
    print("-" * 50)

    issues = checker.check_document(sample_paragraph)
    print(f"\n-> Phát hiện tổng cộng {len(issues)} vấn đề cần xử lý:")

    for iss in issues:
        print(f"  • [{iss.issue_type:<9}] '{iss.original}' (Tọa độ {iss.start}:{iss.end})")
        print(f"    └─ Gợi ý : {iss.suggestions}")
        print(f"    └─ Lý do : {iss.reason}")

    # Danh sách các từ bị lỗi kỳ vọng
    flagged_words = [i.original for i in issues]

    # 1. Bắt buộc phải phát hiện các lỗi này:
    assert "tronglòng" in flagged_words, "Lỗi: Bỏ sót từ dính chữ 'tronglòng'"
    assert "đep" in flagged_words, "Lỗi: Bỏ sót lỗi chính tả 'đep'"
    assert "ngưòi" in flagged_words, "Lỗi: Bỏ sót lỗi dấu OCR 'ngưòi'"
    assert "quốc-giia" in flagged_words, "Lỗi: Bỏ sót lỗi từ ghép 'quốc-giia'"

    # 2. Bắt buộc KHÔNG ĐƯỢC báo lỗi các từ này (Pass):
    assert "quan Tổng đốc" not in flagged_words, "Lỗi: Báo lỗi oan tên riêng 'quan Tổng đốc'"
    assert "thầy Thông Chánh" not in flagged_words, "Lỗi: Báo lỗi oan tên riêng 'thầy Thông Chánh'"
    assert "Gia Định" not in flagged_words, "Lỗi: Báo lỗi oan địa danh 'Gia Định'"
    assert "Chương" not in flagged_words
    assert "I" not in flagged_words, "Lỗi: Báo lỗi oan chữ số La Mã 'I'"
    assert "hoà" not in flagged_words, "Lỗi: Báo lỗi oan từ dấu kiểu cũ 'hoà'"
    assert "canh-tân" not in flagged_words, "Lỗi: Báo lỗi oan từ ghép gạch nối 'canh-tân'"

    # 3. Kiểm tra chất lượng gợi ý:
    for iss in issues:
        if iss.original == "tronglòng":
            assert "trong lòng" in iss.suggestions
        elif iss.original == "ngưòi":
            assert "người" in iss.suggestions
        elif iss.original == "quốc-giia":
            assert "quốc-gia" in iss.suggestions

    print("\n[THÀNH CÔNG] Module core/spell_checker.py đã hoàn thành xuất sắc toàn bộ bài test!")
