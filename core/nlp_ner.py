#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/nlp_ner.py
---------------
Bộ nhận diện Thực thể Tên riêng cổ và Danh xưng lịch sử (Token-based Window Scanning):
1. Duyệt trên luồng Token đã được bóc tách từ core.tokenizer.
2. Bắt cụm Danh xưng/Chức sắc + Tên riêng: thầy Thông Chánh, Cụ Phan Bội Châu.
3. Bắt cụm Tiền tố Địa lý/Hành chính + Địa danh: dinh Gia Định, sông Bến Nghé.
4. Bắt chức sắc phong kiến/thuộc địa độc lập: quan Tổng đốc, Đức Thầy.
5. Bắt tên riêng có gạch nối và chuỗi từ viết hoa liên tiếp: Nam-Kỳ, Nguyễn Tri Phương.
"""

import os
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set

# Đảm bảo đường dẫn gốc của dự án luôn có trong sys.path khi chạy trực tiếp
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.tokenizer import Token, tokenize_words

# 1. Danh mục danh xưng thân tộc & chức sắc phong kiến, thuộc địa, tôn giáo
PERSON_TITLES_MULTI = {
    'quan lớn', 'quan phủ', 'quan huyện', 'quan tuần', 'quan tổng đốc',
    'tổng đốc', 'tuần phủ', 'tri phủ', 'tri huyện', 'bố chính', 'án sát',
    'lãnh binh', 'đề đốc', 'cai tổng', 'lý trưởng', 'hương cả', 'hương sư',
    'hương trưởng', 'hương hào', 'xã trưởng', 'chánh tổng',
    'thông ngôn', 'thầy thông', 'thầy phán', 'thầy ký', 'thầy giáo',
    'đốc học', 'khâm sai', 'thượng thư', 'trạng nguyên', 'bảng nhãn', 'thám hoa',
    'công tử', 'hoàng đế', 'hoàng hậu', 'hoàng tử', 'công chúa', 'thái tử',
    'đức thầy', 'đức cha', 'đức mẹ', 'đức ông', 'hòa thượng', 'thượng tọa',
    'linh mục', 'mục sư', 'ni sư'
}

PERSON_TITLES_SINGLE = {
    'ông', 'bà', 'cụ', 'bác', 'chú', 'thím', 'cô', 'dì', 'cậu', 'mợ',
    'dượng', 'anh', 'chị', 'em', 'chàng', 'nàng', 'thị', 'cháu',
    'quan', 'vua', 'chúa', 'đức', 'thầy'
}

# 2. Danh mục tiền tố địa lý & hành chính
LOCATION_PREFIXES_MULTI = {
    'thành phố', 'cù lao', 'ngã ba', 'ngã tư', 'xứ đàng trong', 'xứ đàng ngoài'
}

LOCATION_PREFIXES_SINGLE = {
    'tỉnh', 'thành', 'hạt', 'phủ', 'huyện', 'tổng', 'làng', 'thôn',
    'ấp', 'xóm', 'phường', 'xứ', 'quận', 'dinh', 'trấn', 'đồn',
    'sông', 'ngòi', 'kênh', 'rạch', 'suối', 'hồ', 'đầm', 'núi',
    'đèo', 'đồi', 'cồn', 'đảo', 'vịnh', 'biển', 'bãi', 'mũi',
    'rừng', 'động', 'hang', 'thác', 'chợ', 'bến', 'cầu', 'phố',
    'cửa', 'chùa', 'đền', 'lăng', 'miếu', 'đình'
}

# Các cụm từ viết hoa ở đầu câu thông thường cần bỏ qua
COMMON_SENTENCE_STARTERS = {
    'hôm nay', 'ngày mai', 'sau đó', 'thế rồi', 'nhưng mà', 'chúng tôi', 'người ta'
}


@dataclass
class Entity:
    """Đối tượng lưu trữ thực thể tên riêng phát hiện được."""
    text: str          # Chuỗi thực thể gốc (vd: "quan Tổng đốc", "Gia Định")
    start: int         # Tọa độ bắt đầu trong văn bản
    end: int           # Tọa độ kết thúc trong văn bản
    category: str      # Phân loại: "PERSON", "LOCATION", "PROPER_NAME"

    @property
    def normalized(self) -> str:
        return unicodedata.normalize('NFC', self.text.strip())

    def __repr__(self) -> str:
        return f"Entity({self.text!r}, {self.category}, [{self.start}:{self.end}])"


class HeuristicNER:
    """
    Bộ bóc tách thực thể dựa trên quét cửa sổ Token (Token-based Window Scanner).
    """

    @classmethod
    def _is_connected_by_spaces_only(cls, text: str, t1: Token, t2: Token) -> bool:
        """Kiểm tra giữa 2 token có phải chỉ cách nhau bằng khoảng trắng (không có dấu câu hay ngắt dòng)."""
        gap = text[t1.end:t2.start]
        return gap.strip(' ') == '' and '\n' not in gap

    @classmethod
    def extract_entities(cls, text: str) -> List[Entity]:
        """Quét luồng token và trích xuất thực thể theo quy tắc ngữ cảnh."""
        if not text:
            return []

        tokens = tokenize_words(text)
        n = len(tokens)
        entities: List[Entity] = []

        i = 0
        while i < n:
            tok = tokens[i]

            # -------------------------------------------------------------
            # TRƯỜNG HỢP 1: Chức sắc ghép nhiều từ (vd: "quan Tổng đốc", "Đức Thầy")
            # -------------------------------------------------------------
            matched_multi_person = False
            for span_len in (3, 2):
                if i + span_len <= n:
                    # Kiểm tra các token có nối liền nhau bằng space không
                    if all(cls._is_connected_by_spaces_only(text, tokens[i + k], tokens[i + k + 1]) for k in range(span_len - 1)):
                        phrase = " ".join(tokens[i + k].lower for k in range(span_len))
                        if phrase in PERSON_TITLES_MULTI:
                            end_tok_idx = i + span_len - 1

                            # Nhìn về phía trước: Có tên riêng viết hoa nào nối tiếp không?
                            curr_look = i + span_len
                            while curr_look < n:
                                next_tok = tokens[curr_look]
                                if next_tok.is_capitalized and cls._is_connected_by_spaces_only(text, tokens[curr_look - 1], next_tok):
                                    end_tok_idx = curr_look
                                    curr_look += 1
                                else:
                                    break

                            start_pos = tokens[i].start
                            end_pos = tokens[end_tok_idx].end
                            entities.append(Entity(
                                text=text[start_pos:end_pos],
                                start=start_pos,
                                end=end_pos,
                                category="PERSON"
                            ))
                            i = end_tok_idx + 1
                            matched_multi_person = True
                            break
            if matched_multi_person:
                continue

            # -------------------------------------------------------------
            # TRƯỜNG HỢP 2: Tiền tố địa danh ghép (vd: "cù lao", "ngã ba")
            # -------------------------------------------------------------
            matched_multi_loc = False
            for span_len in (2,):
                if i + span_len <= n:
                    if all(cls._is_connected_by_spaces_only(text, tokens[i + k], tokens[i + k + 1]) for k in range(span_len - 1)):
                        phrase = " ".join(tokens[i + k].lower for k in range(span_len))
                        if phrase in LOCATION_PREFIXES_MULTI:
                            # Phải có ít nhất 1 từ viết hoa theo sau
                            curr_look = i + span_len
                            end_tok_idx = -1
                            while curr_look < n:
                                next_tok = tokens[curr_look]
                                if next_tok.is_capitalized and cls._is_connected_by_spaces_only(text, tokens[curr_look - 1], next_tok):
                                    end_tok_idx = curr_look
                                    curr_look += 1
                                else:
                                    break

                            if end_tok_idx != -1:
                                start_pos = tokens[i].start
                                end_pos = tokens[end_tok_idx].end
                                entities.append(Entity(
                                    text=text[start_pos:end_pos],
                                    start=start_pos,
                                    end=end_pos,
                                    category="LOCATION"
                                ))
                                i = end_tok_idx + 1
                                matched_multi_loc = True
                                break
            if matched_multi_loc:
                continue

            # -------------------------------------------------------------
            # TRƯỜNG HỢP 3: Danh xưng đơn (ông, bà, thầy, cụ...) + Tên viết hoa
            # -------------------------------------------------------------
            if tok.lower in PERSON_TITLES_SINGLE:
                curr_look = i + 1
                end_tok_idx = -1
                while curr_look < n:
                    next_tok = tokens[curr_look]
                    if next_tok.is_capitalized and cls._is_connected_by_spaces_only(text, tokens[curr_look - 1], next_tok):
                        end_tok_idx = curr_look
                        curr_look += 1
                    else:
                        break

                if end_tok_idx != -1:
                    start_pos = tok.start
                    end_pos = tokens[end_tok_idx].end
                    entities.append(Entity(
                        text=text[start_pos:end_pos],
                        start=start_pos,
                        end=end_pos,
                        category="PERSON"
                    ))
                    i = end_tok_idx + 1
                    continue

            # -------------------------------------------------------------
            # TRƯỜNG HỢP 4: Tiền tố địa lý đơn (tỉnh, sông, chợ, dinh...) + Tên viết hoa
            # -------------------------------------------------------------
            if tok.lower in LOCATION_PREFIXES_SINGLE:
                curr_look = i + 1
                end_tok_idx = -1
                while curr_look < n:
                    next_tok = tokens[curr_look]
                    if next_tok.is_capitalized and cls._is_connected_by_spaces_only(text, tokens[curr_look - 1], next_tok):
                        end_tok_idx = curr_look
                        curr_look += 1
                    else:
                        break

                if end_tok_idx != -1:
                    start_pos = tok.start
                    end_pos = tokens[end_tok_idx].end
                    entities.append(Entity(
                        text=text[start_pos:end_pos],
                        start=start_pos,
                        end=end_pos,
                        category="LOCATION"
                    ))
                    i = end_tok_idx + 1
                    continue

            # -------------------------------------------------------------
            # TRƯỜNG HỢP 5: Tên riêng có gạch nối thời xưa (Nam-Kỳ, Đông-Kinh)
            # -------------------------------------------------------------
            if tok.is_hyphenated and tok.is_capitalized:
                # Toàn bộ các vế trong từ gạch nối đều viết hoa chữ đầu
                sub_parts = tok.text.split('-')
                if all(p and p[0].isupper() for p in sub_parts):
                    entities.append(Entity(
                        text=tok.text,
                        start=tok.start,
                        end=tok.end,
                        category="PROPER_NAME"
                    ))
                    i += 1
                    continue

            # -------------------------------------------------------------
            # TRƯỜNG HỢP 6: Chuỗi từ viết hoa liên tiếp (>= 2 từ: Nguyễn Tri Phương)
            # -------------------------------------------------------------
            if tok.is_capitalized:
                curr_look = i + 1
                while curr_look < n:
                    next_tok = tokens[curr_look]
                    if next_tok.is_capitalized and cls._is_connected_by_spaces_only(text, tokens[curr_look - 1], next_tok):
                        curr_look += 1
                    else:
                        break

                # Có từ 2 từ viết hoa liên tiếp trở lên
                if (curr_look - i) >= 2:
                    end_tok_idx = curr_look - 1
                    full_phrase = text[tok.start:tokens[end_tok_idx].end]
                    # Loại trừ các cụm từ đầu câu thông dụng (Hôm nay, Ngày mai...)
                    if full_phrase.lower() not in COMMON_SENTENCE_STARTERS:
                        entities.append(Entity(
                            text=full_phrase,
                            start=tok.start,
                            end=tokens[end_tok_idx].end,
                            category="PROPER_NAME"
                        ))
                        i = curr_look
                        continue

            i += 1

        return entities

    @classmethod
    def is_token_in_entity(cls, token_start: int, token_end: int, entities: List[Entity]) -> bool:
        """Kiểm tra token có thuộc phạm vi của thực thể tên riêng nào không."""
        for ent in entities:
            if ent.start <= token_start and token_end <= ent.end:
                return True
            if ent.start > token_end:
                break
        return False


# Module-level API tiện ích
def extract_entities(text: str) -> List[Entity]:
    return HeuristicNER.extract_entities(text)


def is_token_in_entities(token_start: int, token_end: int, entities: List[Entity]) -> bool:
    return HeuristicNER.is_token_in_entity(token_start, token_end, entities)


# ==============================================================================
# BỘ KIỂM THỬ TRỰC TIẾP (Self-Test)
# ==============================================================================
if __name__ == "__main__":
    print("=" * 68)
    print(" CORE/NLP_NER: KIỂM THỬ THỰC THỂ BẰNG QUÉT CỬA SỔ TOKEN")
    print("=" * 68)

    sample_text = (
        "— Thưa quan Tổng đốc, thầy Thông Chánh đã tới dinh Gia Định hôm qua.\n"
        "Cụ Phan Bội Châu cùng các đồng chí ở Nam-Kỳ đang chuẩn bị qua Đông-Kinh.\n"
        "Họ hẹn gặp nhau tại chợ Bến Thành, gần sông Bến Nghé.\n"
        "Hôm nay trời nhiều mây, Nguyễn Tri Phương chỉ huy quân dân chống giặc."
    )

    print("-> Văn bản mẫu:")
    print("-" * 50)
    print(sample_text)
    print("-" * 50)

    entities = extract_entities(sample_text)
    print(f"\n-> Tìm thấy {len(entities)} thực thể tên riêng / danh xưng:")

    for ent in entities:
        print(f"  • [{ent.category:<11}] {ent.text:<25} (Tọa độ: {ent.start:>2}:{ent.end:<2})")

    found_texts = [e.text for e in entities]

    # Kiểm tra tính toàn vẹn (Không nuốt từ, không đứt đoạn)
    assert "quan Tổng đốc" in found_texts, "Lỗi: Không nhận diện đúng 'quan Tổng đốc'"
    assert "thầy Thông Chánh" in found_texts, "Lỗi: Nuốt nhầm chữ thành 'thầy Thông Chánh đã'"
    assert "dinh Gia Định" in found_texts
    assert "Cụ Phan Bội Châu" in found_texts
    assert "Nam-Kỳ" in found_texts, "Lỗi: Nuốt nhầm chữ thành 'ở Nam-Kỳ đang'"
    assert "Đông-Kinh" in found_texts
    assert "chợ Bến Thành" in found_texts
    assert "sông Bến Nghé" in found_texts
    assert "Nguyễn Tri Phương" in found_texts
    assert "Hôm nay" not in found_texts, "Lỗi: Bắt nhầm 'Hôm nay' ở đầu câu"

    print("\n[THÀNH CÔNG] Module core/nlp_ner.py chuẩn hóa Token-based đã ĐẠT 100%!")
