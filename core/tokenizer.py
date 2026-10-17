#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/tokenizer.py
-----------------
Bộ phân tích từ vựng (Tokenizer) chuyên biệt cho văn học chữ Quốc ngữ (1880–1975):
1. Nhận diện token chữ đơn (người, nhà) và từ ghép có gạch nối (quốc-gia, văn-học).
2. Lưu vết tọa độ ký tự chính xác (start, end offset) phục vụ Diff Engine & Web UI.
3. Bóc tách thuộc tính: chữ hoa/thường, danh sách âm tiết con cấu thành.
4. Tách câu thông minh (Sentence Splitting) có bảo vệ từ viết tắt (v.v., ông N.).
"""

import re
from dataclasses import dataclass
from typing import Generator, List, Optional

# Ký tự chữ cái tiếng Việt (bao gồm cả Đ/đ và toàn bộ nguyên âm có dấu)
VIET_CHARS = r'[A-Za-zÀ-ỹĐđ]'

# Pattern nhận diện từ đơn hoặc từ ghép nối bằng gạch ngang:
# Ví dụ: 'quốc-gia', 'văn-học', 'xã-hội', 'người', 'nhà'
# Không khớp với: dấu gạch rời ( - ), số (10-5), hoặc mã đặt chỗ Markdown (⟦MG_0⟧)
WORD_TOKEN_PATTERN = re.compile(
    rf'\b{VIET_CHARS}+(?:-{VIET_CHARS}+)*\b'
)

# Danh sách viết tắt để tránh ngắt câu sai
ABBREVIATIONS = r'v\.v|th\.s|ts|gs|pgs|tr|sđd|tp|tt|bt|q|đ\/c'
ABBREV_WITH_DOT = rf'\b(?:{ABBREVIATIONS}|[A-ZÀ-ỸĐ])\.'

# Group 1: Từ viết tắt (bỏ qua không ngắt) | Group 2: Dấu kết câu thực sự
SENTENCE_SPLIT_PATTERN = re.compile(
    rf'({ABBREV_WITH_DOT})|(\.{{3}}|[\.!\?])(?:\s+|\n+|$)'
)

@dataclass
class Token:
    """Đối tượng lưu trữ thông tin của một từ / từ ghép trong văn bản."""
    text: str              # Chuỗi gốc trong văn bản (vd: "Quốc-gia")
    start: int             # Tọa độ ký tự bắt đầu trong văn bản
    end: int               # Tọa độ ký tự kết thúc trong văn bản
    is_hyphenated: bool    # True nếu là từ ghép có gạch nối (quốc-gia)
    syllables: List[str]   # Danh sách các âm tiết con (vd: ['quốc', 'gia'])
    is_capitalized: bool   # Viết hoa chữ cái đầu (Quốc-gia)
    is_all_caps: bool      # Viết hoa toàn bộ (QUỐC-GIA)

    @property
    def lower(self) -> str:
        """Trả về dạng chữ thường của token (vd: 'quốc-gia')."""
        return self.text.lower()

    def __len__(self) -> int:
        return len(self.text)

    def __repr__(self) -> str:
        return f"Token({self.text!r}, [{self.start}:{self.end}])"


@dataclass
class Sentence:
    """Đối tượng lưu trữ một câu hoàn chỉnh kèm danh sách tokens bên trong."""
    text: str              # Nội dung nguyên văn của câu
    start: int             # Tọa độ bắt đầu của câu trong văn bản
    end: int               # Tọa độ kết thúc của câu trong văn bản
    tokens: List[Token]    # Danh sách các Token từ vựng có trong câu

    def __repr__(self) -> str:
        snippet = self.text if len(self.text) <= 30 else self.text[:27] + "..."
        return f"Sentence({snippet!r}, tokens={len(self.tokens)})"


def tokenize_words(text: str) -> List[Token]:
    """
    Bóc tách toàn bộ các từ đơn và từ ghép có gạch nối trong văn bản.
    Bỏ qua dấu câu, khoảng trắng và các thẻ bảo vệ Markdown (⟦MG_ID⟧).
    """
    if not text:
        return []

    tokens: List[Token] = []

    for match in WORD_TOKEN_PATTERN.finditer(text):
        raw_word = match.group(0)
        start_idx = match.start()
        end_idx = match.end()

        is_hyphen = '-' in raw_word
        # Tách các âm tiết con (nếu có gạch nối)
        syllables = [s.lower() for s in raw_word.split('-')] if is_hyphen else [raw_word.lower()]

        # Kiểm tra trạng thái viết hoa
        first_char = raw_word[0]
        is_cap = first_char.isupper()
        is_upper = raw_word.isupper()

        token = Token(
            text=raw_word,
            start=start_idx,
            end=end_idx,
            is_hyphenated=is_hyphen,
            syllables=syllables,
            is_capitalized=is_cap,
            is_all_caps=is_upper
        )
        tokens.append(token)

    return tokens


def tokenize_sentences(text: str) -> List[Sentence]:
    """
    Phân tách văn bản thành danh sách các câu độc lập.
    Đảm bảo:
    - Không ngắt câu tại số thập phân (3.14).
    - Không ngắt câu tại từ viết tắt (v.v., ông N.).
    - Gắn kèm danh sách Token từ vựng tương ứng cho từng câu.
    """
    if not text:
        return []

    sentences: List[Sentence] = []
    current_start = 0

    for match in SENTENCE_SPLIT_PATTERN.finditer(text):
        # Nếu khớp từ viết tắt -> bỏ qua không ngắt câu
        if match.group(1):
            continue

        # Điểm kết thúc của câu tại Group 2 (bao gồm cả dấu kết câu)
        punct_end = match.end(2)
        sent_text = text[current_start:punct_end].strip()

        if sent_text:
            # Tìm vị trí thực tế của chuỗi sau khi strip
            actual_start = text.find(sent_text, current_start)
            actual_end = actual_start + len(sent_text)

            # Lấy các token từ vựng thuộc phạm vi câu này
            sent_tokens = tokenize_words(sent_text)
            # Điều chỉnh tọa độ token theo offset tuyệt đối của toàn văn bản
            adjusted_tokens = [
                Token(
                    text=t.text,
                    start=actual_start + t.start,
                    end=actual_start + t.end,
                    is_hyphenated=t.is_hyphenated,
                    syllables=t.syllables,
                    is_capitalized=t.is_capitalized,
                    is_all_caps=t.is_all_caps
                )
                for t in sent_tokens
            ]

            sentences.append(Sentence(
                text=sent_text,
                start=actual_start,
                end=actual_end,
                tokens=adjusted_tokens
            ))

        current_start = match.end()

    # Xử lý đoạn văn bản còn lại ở cuối (nếu không có dấu kết câu ở cuối cùng)
    if current_start < len(text):
        tail_text = text[current_start:].strip()
        if tail_text:
            actual_start = text.find(tail_text, current_start)
            actual_end = actual_start + len(tail_text)
            tail_tokens = tokenize_words(tail_text)
            adjusted_tokens = [
                Token(
                    text=t.text,
                    start=actual_start + t.start,
                    end=actual_start + t.end,
                    is_hyphenated=t.is_hyphenated,
                    syllables=t.syllables,
                    is_capitalized=t.is_capitalized,
                    is_all_caps=t.is_all_caps
                )
                for t in tail_tokens
            ]
            sentences.append(Sentence(
                text=tail_text,
                start=actual_start,
                end=actual_end,
                tokens=adjusted_tokens
            ))

    return sentences


# ==============================================================================
# BỘ KIỂM THỬ TRỰC TIẾP (Self-Test)
# ==============================================================================
if __name__ == "__main__":
    print("=" * 65)
    print(" CORE/TOKENIZER: KIỂM THỬ BỘ TÁCH TỪ VÀ TÁCH CÂU LỊCH SỬ")
    print("=" * 65)

    sample_doc = (
        "— Nước-nhà đang buổi canh-tân, thanh-niên cần hiểu rõ quốc-gia.\n"
        "Ông N. bảo rằng tỉ lệ đạt 3.14 là rất hiếm, v.v. và khó thành.\n"
        "⟦MG_0⟧Đây là câu có mã Markdown⟦MG_1⟧, từ này là tự-do."
    )

    print("-> 1. Kiểm thử tách từ (Tokenize Words):")
    tokens = tokenize_words(sample_doc)
    print(f"Tổng số token từ vựng tìm thấy: {len(tokens)}")

    hyphen_tokens = [t for t in tokens if t.is_hyphenated]
    print(f"\nCác từ ghép có gạch nối phát hiện được ({len(hyphen_tokens)} từ):")
    for ht in hyphen_tokens:
        print(f"  • {ht.text:<15} [Offset: {ht.start:>2}:{ht.end:<2}] -> Âm tiết con: {ht.syllables}")

    # Kiểm tra tính chính xác của tọa độ (Slicing verification)
    print("\n-> 2. Kiểm chứng độ chính xác của tọa độ ký tự:")
    for t in tokens[:5]:
        extracted = sample_doc[t.start:t.end]
        assert extracted == t.text, f"Lệch tọa độ: {extracted} != {t.text}"
        print(f"  ✓ text[{t.start}:{t.end}] == {t.text!r}")

    # Kiểm tra tách câu
    print("\n-> 3. Kiểm thử phân tách câu (Tokenize Sentences):")
    sentences = tokenize_sentences(sample_doc)
    print(f"Tổng số câu phân tách được: {len(sentences)}")
    for idx, s in enumerate(sentences, 1):
        print(f"  [Câu {idx}] [{s.start}:{s.end}] ({len(s.tokens)} tokens):")
        print(f"    \"{s.text}\"")

    # Xác thực các yêu cầu quan trọng
    token_texts = [t.text for t in tokens]
    assert "Nước-nhà" in token_texts, "Lỗi: Không nhận diện được 'Nước-nhà'"
    assert "canh-tân" in token_texts, "Lỗi: Không nhận diện được 'canh-tân'"
    assert "quốc-gia" in token_texts, "Lỗi: Không nhận diện được 'quốc-gia'"
    assert "tự-do" in token_texts, "Lỗi: Không nhận diện được 'tự-do'"
    assert "⟦MG_0⟧" not in token_texts, "Lỗi: Tokenizer bị dính mã Markdown!"
    assert len(sentences) == 3, f"Lỗi: Số lượng câu không đúng (Kỳ vọng 3, thực tế {len(sentences)})"

    print("\n[THÀNH CÔNG] Module core/tokenizer.py đã vượt qua toàn bộ các bài test!")

