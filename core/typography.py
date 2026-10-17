#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/typography.py
------------------
Bộ quy tắc Regex chuẩn hóa Typography & Viết hoa chuyên dụng cho văn học:
1. Chuẩn hóa dấu ba chấm (...) và các tổ hợp dấu câu.
2. Xóa khoảng trắng thừa trước dấu câu (, . ; : ! ? ) ] } » ”).
3. Đảm bảo đúng 1 khoảng trắng sau dấu câu (trừ số thập phân, từ viết tắt).
4. Xóa khoảng trắng sát mép trong của ngoặc và dấu trích dẫn.
5. Chuẩn hóa gạch đầu dòng hội thoại thành Em-dash (— ) theo quy chuẩn sắp chữ văn học.
6. Tự động viết hoa đầu đoạn, sau dấu kết câu (., !, ?), sau gạch thoại (— ),
   sau dấu hai chấm mở ngoặc kép (: "), đồng thời bảo vệ các từ viết tắt và lời dẫn thoại.
"""

import re

# Bảng các từ viết tắt tiếng Việt thông dụng có dấu chấm (không viết hoa từ kế tiếp)
ABBREVIATIONS = (
    r'v\.v|th\.s|ts|gs|pgs|tr|sđd|tp|tt|bt|q|đ\/c'
)

# Pattern khớp từ viết tắt kèm dấu chấm (để bảo vệ, tránh look-behind biến thiên)
ABBREV_WITH_DOT = rf'\b(?:{ABBREVIATIONS}|[A-ZÀ-ỸĐ])\.'

# Các đại từ / danh từ đi kèm động từ dẫn thoại (Dialogue speech tags)
# Ví dụ: "— Đi đâu đấy? tôi hỏi." -> 'tôi hỏi' giữ nguyên chữ thường
SPEECH_TAG_PRONOUNS = r'(?:tôi|hắn|nó|ông|bà|thị|chàng|nàng|người|chúng tôi)'
SPEECH_TAG_VERBS = r'(?:hỏi|đáp|bảo|nói|thưa|cười|nghĩ|kêu|la|than|thốt|rằng|tiếp)'
SPEECH_TAG_PATTERN = re.compile(
    rf'^{SPEECH_TAG_PRONOUNS}\s+{SPEECH_TAG_VERBS}\b',
    re.IGNORECASE
)


def normalize_ellipsis(text: str) -> str:
    """Chuẩn hóa dấu ba chấm: 4 chấm trở lên hoặc chấm cách nhau -> đúng 3 chấm (...)"""
    if not text:
        return ""
    # Đổi ký tự Unicode ellipsis '…' thành 3 dấu chấm chuẩn ASCII '...'
    text = text.replace('…', '...')
    # Thu gọn 4 chấm trở lên thành 3 chấm
    text = re.sub(r'\.{4,}', '...', text)
    # Gộp các dấu chấm có khoảng trắng ở giữa (vd: . . .) thành ...
    text = re.sub(r'\.\s+\.\s+\.', '...', text)
    return text


def normalize_punctuation_spacing(text: str) -> str:
    """
    Chuẩn hóa khoảng trắng quanh các dấu câu đơn lẻ (, . ; : ! ?):
    - Xóa khoảng trắng TRƯỚC dấu.
    - Đảm bảo đúng 1 khoảng trắng SAU dấu (trừ số thập phân, giờ giấc, từ viết tắt).
    """
    if not text:
        return ""

    # 1. Xóa khoảng trắng TRƯỚC các dấu câu: , . ; : ! ?
    # Loại trừ trường hợp dấu ba chấm (...)
    text = re.sub(r'[ \t]+([,;:!?])', r'\1', text)
    text = re.sub(r'[ \t]+(?<!\.)\.(?!\.)', '.', text)

    # 2. Đảm bảo đúng 1 khoảng trắng SAU các dấu phẩy, chấm phẩy, hai chấm, chấm than, hỏi
    # Bỏ qua nếu phía sau là: khoảng trắng, số (1,5 hoặc 12:30), dấu đóng ngoặc/trích dẫn, xuống dòng, hoặc token mask ⟦
    text = re.sub(r'([,;:!?])(?=[^\s\d\)\],;:!?\"\'”»\n⟦])', r'\1 ', text)

    # 3. Đảm bảo đúng 1 khoảng trắng SAU dấu chấm câu (.)
    # Sử dụng kỹ thuật Group 1 (Từ viết tắt -> giữ nguyên) | Group 2 (Dấu chấm thực sự -> thêm space)
    dot_spacing_regex = re.compile(
        rf'({ABBREV_WITH_DOT})|(\.)(?=[^\s\d\)\],;:!?\"\'”»\n⟦\.])'
    )

    def dot_spacing_repl(match):
        if match.group(1):
            # Khớp từ viết tắt kèm dấu chấm (vd: v.v., N.) -> giữ nguyên
            return match.group(1)
        # Dấu chấm câu thông thường cần thêm khoảng trắng
        return '. '

    text = dot_spacing_regex.sub(dot_spacing_repl, text)

    return text


def normalize_bracket_and_quote_spacing(text: str) -> str:
    """
    Xóa khoảng trắng sát mép trong của các cặp ngoặc và dấu trích dẫn:
    ( nội dung ) -> (nội dung), « nội dung » -> «nội dung», " nội dung " -> "nội dung"
    """
    if not text:
        return ""

    # Xóa khoảng trắng sau dấu mở ngoặc / mở trích dẫn (gồm cả " mở)
    text = re.sub(r'([\(\[\{«“])\s+', r'\1', text)
    text = re.sub(r'(?:^|[\s\(\[\{—:])"\s+', r'"', text)

    # Xóa khoảng trắng trước dấu đóng ngoặc / đóng trích dẫn (gồm cả " đóng)
    text = re.sub(r'\s+([\)\]\}»”])', r'\1', text)
    text = re.sub(r'(?<=[\wà-ỹĐđ.,!?…])\s+"', '"', text)

    # Xóa khoảng trắng thừa trước dấu đóng ngoặc
    text = re.sub(r'[ \t]+([\)\]\}»”])', r'\1', text)

    return text


def normalize_dialogue_dashes(text: str) -> str:
    """
    Chuẩn hóa dấu gạch đầu dòng hội thoại:
    Chuyển đổi các dấu gạch ngắn (- ), en-dash (– ), hai gạch (-- ) ở đầu dòng
    thành Em-dash (— ) chuẩn xuất bản văn học.
    """
    if not text:
        return ""

    # Tìm các dòng bắt đầu bằng 1 hoặc 2 dấu gạch kèm khoảng trắng tùy ý
    # ^[ \t]*[-–—]{1,2}[ \t]* -> '— '
    text = re.sub(
        r'^[ \t]*[-–—]{1,2}[ \t]*',
        '— ',
        text,
        flags=re.MULTILINE
    )

    return text


def capitalize_after_sentence_boundaries(text: str) -> str:
    """
    Tự động viết hoa chữ cái đầu tiên:
    1. Đầu mỗi đoạn văn.
    2. Sau dấu gạch đầu dòng thoại (— ).
    3. Sau dấu kết câu (., !, ?) và ba chấm (...).
    4. Sau dấu hai chấm mở ngoặc kép (: ").
    * Bảo tồn chữ thường cho các từ viết tắt và lời dẫn thoại (— Đi đâu đấy? tôi hỏi).*
    """
    if not text:
        return ""

    # 1. Viết hoa chữ cái đầu đoạn văn (dòng mới bắt đầu bằng chữ thường)
    text = re.sub(
        r'(?m)^([a-zà-ỹđ])',
        lambda m: m.group(1).upper(),
        text
    )

    # 2. Viết hoa sau dấu gạch đầu dòng thoại: ^— chữ -> ^— Chữ
    text = re.sub(
        r'(?m)^(—\s+)([a-zà-ỹđ])',
        lambda m: f"{m.group(1)}{m.group(2).upper()}",
        text
    )

    # 3. Viết hoa sau dấu hai chấm mở ngoặc trích dẫn: : "chữ -> : "Chữ
    text = re.sub(
        r'(:\s*["“«])([a-zà-ỹđ])',
        lambda m: f"{m.group(1)}{m.group(2).upper()}",
        text
    )

    # 4. Viết hoa sau dấu kết thúc câu: ., !, ?, ...
    # Sử dụng kỹ thuật Group 1 (Từ viết tắt) | Group 2 (Dấu kết câu thực thụ)
    sentence_end_pattern = re.compile(
        rf'({ABBREV_WITH_DOT})|(\.{{3}}|[\.!\?])(["”»\)]*)(\s+)([a-zà-ỹđ][^\s\d\(\[\{{«“"”».,;:!?]*)'
    )

    def cap_sentence_repl(match):
        # Nếu khớp từ viết tắt -> giữ nguyên không viết hoa
        if match.group(1):
            return match.group(1)

        punct = match.group(2)          # Dấu câu (., !, ?, ...)
        closing = match.group(3)        # Dấu đóng ngoặc nếu có
        spacing = match.group(4)        # Khoảng trắng
        following_word = match.group(5) # Từ đầu tiên của câu sau

        # Trường hợp ngoại lệ: Nếu dấu câu là ! hoặc ? nhưng phía sau là lời dẫn thoại (vd: "tôi hỏi")
        # Kiểm tra đoạn text phía sau tính từ vị trí từ tiếp theo
        tail_text = text[match.start(5):]
        if punct in ('!', '?') and SPEECH_TAG_PATTERN.match(tail_text):
            return match.group(0)

        # Viết hoa chữ cái đầu tiên của từ
        capitalized_word = following_word[0].upper() + following_word[1:]
        return f"{punct}{closing}{spacing}{capitalized_word}"

    text = sentence_end_pattern.sub(cap_sentence_repl, text)

    return text


def standardize_typography(text: str) -> str:
    """
    HÀM TỔNG HỢP (Master Typography Pipeline):
    Thực thi toàn bộ các bước định dạng văn bản theo trình tự logic chặt chẽ:
    1. Chuẩn hóa dấu ba chấm (...)
    2. Chuẩn hóa khoảng trắng quanh dấu câu đơn lẻ (, . ; : ! ?)
    3. Chuẩn hóa mép trong dấu ngoặc và trích dẫn
    4. Chuẩn hóa dấu gạch đầu dòng thoại (— )
    5. Tự động viết hoa đầu câu, sau dấu chấm và sau thoại
    """
    if not text:
        return ""

    text = normalize_ellipsis(text)
    text = normalize_punctuation_spacing(text)
    text = normalize_bracket_and_quote_spacing(text)
    text = normalize_dialogue_dashes(text)
    text = capitalize_after_sentence_boundaries(text)

    return text


# ==============================================================================
# BỘ KIỂM THỬ TRỰC TIẾP (Self-Test)
# ==============================================================================
if __name__ == "__main__":
    print("=" * 65)
    print(" CORE/TYPOGRAPHY: KIỂM THỬ ĐỊNH DẠNG VÀ VIẾT HOA VĂN HỌC")
    print("=" * 65)

    test_cases = [
        # 1. Lỗi khoảng trắng quanh dấu câu
        ("Tôi ,bạn và anh ấy .ngày mai đi .",
         "Tôi, bạn và anh ấy. Ngày mai đi."),

        # 2. Số thập phân và giờ giấc (Tuyệt đối không chèn khoảng trắng)
        ("Tỉ lệ là 3.14 hoặc 1,5 vào lúc 12:30 hôm nay.",
         "Tỉ lệ là 3.14 hoặc 1,5 vào lúc 12:30 hôm nay."),

        # 3. Từ viết tắt và tên tắt (Không viết hoa từ kế tiếp)
        ("Các loại quả như cam, quýt, v.v. và nhiều thứ khác của ông N. mang lại.",
         "Các loại quả như cam, quýt, v.v. và nhiều thứ khác của ông N. mang lại."),

        # 4. Gạch đầu dòng hội thoại và viết hoa sau gạch thoại
        ("- chào bác ,bác đi đâu đấy ?\n-- cháu đi chợ .",
         "— Chào bác, bác đi đâu đấy?\n— Cháu đi chợ."),

        # 5. Dấu ngoặc và trích dẫn thừa khoảng trắng
        ("Hắn nói ( một mình ) trong căn phòng « bí mật » : \"ngày mai bắt đầu \" .",
         "Hắn nói (một mình) trong căn phòng «bí mật»: \"Ngày mai bắt đầu\"."),

        # 6. Dấu ba chấm và lời dẫn thoại ngoại lệ
        ("— Đi đâu đấy? tôi hỏi .\n— Trời mưa rồi....chúng ta về thôi .",
         "— Đi đâu đấy? tôi hỏi.\n— Trời mưa rồi... Chúng ta về thôi.")
    ]

    passed = 0
    for idx, (raw, expected) in enumerate(test_cases, 1):
        result = standardize_typography(raw)
        if result == expected:
            passed += 1
            print(f"✓ Test {idx}: ĐẠT")
        else:
            print(f"✗ Test {idx}: THẤT BẠI")
            print(f"  • Đầu vào   : {repr(raw)}")
            print(f"  • Kết quả   : {repr(result)}")
            print(f"  • Mong muốn : {repr(expected)}")

    print("-" * 65)
    print(f"Kết quả kiểm thử: {passed}/{len(test_cases)} tests hoàn thành xuất sắc!")
    assert passed == len(test_cases), "Một số bài test chưa đạt!"
    