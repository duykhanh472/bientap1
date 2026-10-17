#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/normalizer.py
------------------
Tầng tiền xử lý kỹ thuật cơ sở:
1. Chuẩn hóa toàn bộ văn bản về Unicode NFC (dựng sẵn).
2. Dọn sạch các ký tự điều khiển ẩn, mã BOM, ký tự zero-width, soft-hyphen từ OCR.
3. Chuẩn hóa các biến thể khoảng trắng Unicode về khoảng trắng tiêu chuẩn (ASCII space).
4. Chuẩn hóa ngắt dòng Unix (\\n) và bảo vệ quy ước 2 dấu cách ngắt dòng của Markdown.
"""

import re
import unicodedata

# 1. Các ký tự vô hình cần loại bỏ hoàn toàn
# \uFEFF: Byte Order Mark (BOM) / Zero-width no-break space
# \u200B: Zero-width space
# \u200C: Zero-width non-joiner (ZWNJ)
# \u200D: Zero-width joiner (ZWJ)
# \u2060: Word joiner
# \u00AD: Soft hyphen (gạch nối mềm do ABBYY tự chèn để ngắt dòng)
# \u200E, \u200F: LTR/RTL directional marks
INVISIBLE_CHARS_RE = re.compile(
    r'[\uFEFF\u200B\u200C\u200D\u2060\u00AD\u200E\u200F]'
)

# 2. Các ký tự điều khiển ASCII rác (ngoại trừ \t và \n)
CONTROL_CHARS_RE = re.compile(
    r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]'
)

# 3. Các biến thể khoảng trắng Unicode lạ -> chuyển về khoảng trắng thường '\x20'
# \u00A0: No-break space (NBSP)
# \u1680: Ogham space
# \u2000-\u200A: En quad, Em quad, Thin space, Hair space, v.v.
# \u202F: Narrow no-break space
# \u205F: Medium mathematical space
# \u3000: Ideographic space
UNICODE_SPACES_RE = re.compile(
    r'[\u00A0\u1680\u2000-\u200A\u202F\u205F\u3000]'
)

# 4. Ký tự ngắt dòng đặc thù
LINE_SEPARATORS_RE = re.compile(r'[\r\u2028\u2029]')


def normalize_unicode_nfc(text: str) -> str:
    """Ép toàn bộ chuỗi về dạng chuẩn Unicode NFC (Dựng sẵn)."""
    if not text:
        return ""
    return unicodedata.normalize('NFC', text)


def remove_invisible_junk(text: str) -> str:
    """Xóa bỏ các ký tự vô hình, mã BOM và rác điều khiển OCR."""
    if not text:
        return ""
    # Xóa ký tự vô hình (Zero-width, Soft hyphen...)
    text = INVISIBLE_CHARS_RE.sub('', text)
    # Xóa ký tự điều khiển ASCII
    text = CONTROL_CHARS_RE.sub('', text)
    return text


def normalize_spaces(text: str) -> str:
    """Chuyển đổi toàn bộ các loại khoảng trắng Unicode về khoảng trắng chuẩn (ASCII 0x20)."""
    if not text:
        return ""
    # Đổi các loại khoảng trắng lạ về dấu cách thường
    text = UNICODE_SPACES_RE.sub(' ', text)
    # Đổi Tab (\t) thành 4 dấu cách để đồng nhất thụt lề
    text = text.replace('\t', '    ')
    return text


def normalize_newlines(text: str) -> str:
    """
    Chuẩn hóa dấu ngắt dòng về chuẩn Unix (\\n).
    Đồng thời dọn dẹp khoảng trắng thừa ở cuối mỗi dòng nhưng BẢO VỆ
    quy chuẩn ngắt dòng mềm của Markdown (dòng kết thúc bằng đúng 2 dấu cách '  \\n').
    """
    if not text:
        return ""

    # Chuyển \r\n (Windows) hoặc \r (Mac cũ) thành \n
    text = text.replace('\r\n', '\n')
    text = LINE_SEPARATORS_RE.sub('\n', text)

    cleaned_lines = []
    for line in text.split('\n'):
        # Kiểm tra nếu dòng có chủ đích kết thúc bằng đúng 2 khoảng trắng (Markdown break)
        if line.endswith('  ') and not line.endswith('   '):
            # Giữ lại đúng 2 khoảng trắng
            cleaned_line = line.rstrip() + '  '
        else:
            # Xóa sạch khoảng trắng rác ở cuối dòng
            cleaned_line = line.rstrip()

        cleaned_lines.append(cleaned_line)

    result = '\n'.join(cleaned_lines)

    # Thu gọn các đoạn xuống dòng quá nhiều (tối đa 2 dòng trống liên tiếp)
    result = re.sub(r'\n{4,}', '\n\n\n', result)
    return result


def normalize_text(text: str) -> str:
    """
    HÀM TỔNG HỢP (Master Pipeline):
    Thực thi toàn bộ các bước chuẩn hoá kỹ thuật theo đúng thứ tự an toàn:
    1. Ép Unicode NFC
    2. Loại bỏ rác điều khiển & ký tự ẩn
    3. Chuẩn hóa khoảng trắng
    4. Chuẩn hóa ngắt dòng & bảo vệ Markdown
    """
    if not text:
        return ""

    text = normalize_unicode_nfc(text)
    text = remove_invisible_junk(text)
    text = normalize_spaces(text)
    text = normalize_newlines(text)
    # Ép NFC lần cuối sau khi đã ghép chuỗi
    text = normalize_unicode_nfc(text)

    return text


# ==============================================================================
# BỘ KIỂM THỬ TRỰC TIẾP (Self-Test)
# ==============================================================================
if __name__ == "__main__":
    print("=" * 65)
    print(" CORE/NORMALIZER: TỰ ĐỘNG KIỂM THỬ CHUẨN HOÁ KỸ THUẬT")
    print("=" * 65)

    # 1. Tạo mẫu test hỗn hợp NFD + Ký tự ẩn + NBSP + Windows CRLF
    # "hoà" viết ở dạng NFD (o + dấu huyền \u0300)
    word_nfd = "ho" + "\u0300" + "a\u0300"
    # Giả lập rác OCR: Zero-width space (\u200B), Soft hyphen (\u00AD), NBSP (\u00A0)
    raw_sample = (
        "\uFEFF## Chương I: Mở Đầu\r\n"
        "Đoạn văn này có\u00A0khoảng\u200Btrắng\u00ADlạ và dấu ngắt Windows.\r\n"
        "Từ này là tổ hợp NFD: " + word_nfd + " .\r\n"
        "Dòng này kết thúc bằng thơ:  \r\n"
        "Trăng vương đầu ngọn trúc.\n\n\n\n\n"
        "Dòng sau quá nhiều khoảng trống."
    )

    print("\n-> VĂN BẢN ĐẦU VÀO THÔ (Có chứa mã ẩn & NFD):")
    print(repr(raw_sample))

    cleaned = normalize_text(raw_sample)

    print("\n-> VĂN BẢN SAU KHI QUA NORMALIZER:")
    print("-" * 40)
    print(cleaned)
    print("-" * 40)

    # Xác thực kiểm tra
    assert "\uFEFF" not in cleaned, "Lỗi: Chưa xóa mã BOM!"
    assert "\u200B" not in cleaned, "Lỗi: Chưa xóa Zero-width space!"
    assert "\u00AD" not in cleaned, "Lỗi: Chưa xóa Soft-hyphen!"
    assert "\u00A0" not in cleaned, "Lỗi: Chưa chuẩn hóa Non-breaking space!"
    assert "\r" not in cleaned, "Lỗi: Vẫn còn dấu ngắt dòng Windows!"
    assert unicodedata.is_normalized('NFC', cleaned), "Lỗi: Văn bản chưa đạt chuẩn NFC!"

    print("\n[THÀNH CÔNG] Toàn bộ các bài test của normalizer.py đều ĐẠT chuẩn!")

