#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/markdown_guard.py
----------------------
Cơ chế Masking bảo vệ an toàn 100% cú pháp Markdown:
1. Đóng băng các khối mã (Code blocks, inline code).
2. Đóng băng các thẻ HTML, liên kết hình ảnh, chú thích chân trang ([^1]).
3. Đóng băng cú pháp tiêu đề (#), trích dẫn (>), số thứ tự (1.), đường kẻ (---).
4. Đóng băng các dấu định dạng in đậm (**), in nghiêng (*), gạch ngang (~~)
   nhưng VẪN ĐỂ HỞ phần chữ bên trong để bộ soát chính tả làm việc.
5. Hoàn trả (Unmask) nguyên vẹn cấu trúc ban đầu.
"""

import re
from typing import Dict, Tuple


class MarkdownGuard:
    """
    Bộ bảo vệ cú pháp Markdown thông qua cơ chế Masking (Đặt chỗ tạm thời).
    Sử dụng cặp ký tự ⟦MG_ID⟧ (Unicode U+27E6 / U+27E7) không xung đột với chữ Quốc ngữ.
    """

    PLACEHOLDER_PATTERN = re.compile(r'⟦MG_(\d+)⟧')

    def __init__(self):
        self._reset()

    def _reset(self):
        self.mask_map: Dict[str, str] = {}
        self.counter = 0

    def _generate_token(self, original_content: str) -> str:
        """Tạo một token đặt chỗ duy nhất và lưu vết nội dung gốc."""
        token = f"⟦MG_{self.counter}⟧"
        self.mask_map[token] = original_content
        self.counter += 1
        return token

    def mask(self, text: str) -> Tuple[str, Dict[str, str]]:
        """
        Quét và đóng băng toàn bộ cú pháp Markdown theo thứ tự ưu tiên từ lớn đến bé:
        Trả về: (văn bản đã che chắn, từ điển giải mã mask_map)
        """
        if not text:
            return "", {}

        self._reset()
        masked = text

        # 1. Khối mã nhiều dòng (Fenced Code Blocks: ```code``` hoặc ~~~code~~~)
        def repl_code_block(m):
            return self._generate_token(m.group(0))

        masked = re.sub(r'(```[\s\S]*?```|~~~[\s\S]*?~~~)', repl_code_block, masked)

        # 2. Khối mã nội dòng (Inline Code: `code`)
        masked = re.sub(r'(`[^`\n]+`)', repl_code_block, masked)

        # 3. Chú thích HTML (<!-- comment -->) và thẻ HTML (<span ...>, <br/>)
        masked = re.sub(r'(<!--[\s\S]*?-->|<[A-Za-z/][^>\n]*>)', repl_code_block, masked)

        # 4. Chú thích chân trang (Footnotes - Rất phổ biến trong sách cổ)
        # 4.1 Định nghĩa chú thích ở cuối trang: [^1]: hoặc [^ghi_chu]:
        masked = re.sub(r'(^\[\^[^\]\n]+\]:)', lambda m: self._generate_token(m.group(1)), masked, flags=re.MULTILINE)
        # 4.2 Thẻ gọi chú thích trong đoạn văn: [^1]
        masked = re.sub(r'(\[\^[^\]\n]+\])', lambda m: self._generate_token(m.group(1)), masked)

        # 5. Hình ảnh và Liên kết (Images & Links)
        # 5.1 Toàn bộ cú pháp ảnh: ![alt](url "title")
        masked = re.sub(r'(!\[[^\]]*\]\([^\)\n]+\))', lambda m: self._generate_token(m.group(1)), masked)
        # 5.2 Phần đích đến của link: [văn bản hiển thị](url) -> Chỉ mask [ và ](url)
        # để 'văn bản hiển thị' vẫn được soát lỗi chính tả bình thường!
        def repl_link(m):
            anchor = m.group(1)
            url_part = m.group(2)
            open_bracket = self._generate_token("[")
            close_and_url = self._generate_token(f"]({url_part})")
            return f"{open_bracket}{anchor}{close_and_url}"

        masked = re.sub(r'\[([^\]\n]+)\]\(([^\)\n]+)\)', repl_link, masked)

        # 6. Các thành phần cấu trúc dòng (Line Structural Prefixes)
        # 6.1 Tiêu đề Markdown: ^# ... ^######
        masked = re.sub(r'^(#{1,6}\s+)', lambda m: self._generate_token(m.group(1)), masked, flags=re.MULTILINE)
        # 6.2 Khối trích dẫn: ^> hoặc ^>>
        masked = re.sub(r'^(>+\s*)', lambda m: self._generate_token(m.group(1)), masked, flags=re.MULTILINE)
        # 6.3 Danh sách có thứ tự: ^1.  ^2.  (để dấu chấm không bị coi là ngắt câu)
        masked = re.sub(r'^(\d+\.\s+)', lambda m: self._generate_token(m.group(1)), masked, flags=re.MULTILINE)
        # 6.4 Đường kẻ ngang phân cách: --- hoặc *** hoặc ___
        masked = re.sub(r'^([-*_]\s*){3,}$', lambda m: self._generate_token(m.group(0)), masked, flags=re.MULTILINE)

        # 7. Định dạng chữ (In đậm, In nghiêng, Gạch bỏ)
        # Che chắn các dấu đánh dấu (**, *, ~~) để hở từ bên trong cho spell-check
        # 7.1 In đậm nghiêng kết hợp: *** hoặc ___
        masked = re.sub(r'(\*\*\*|___)', lambda m: self._generate_token(m.group(1)), masked)
        # 7.2 In đậm: ** hoặc __
        masked = re.sub(r'(\*\*|__)', lambda m: self._generate_token(m.group(1)), masked)
        # 7.3 Gạch bỏ: ~~
        masked = re.sub(r'(~~)', lambda m: self._generate_token(m.group(1)), masked)
        # 7.4 In nghiêng: * (hoặc _ đứng độc lập không nằm trong từ)
        masked = re.sub(r'(\*|(?<!\w)_(?!\w))', lambda m: self._generate_token(m.group(1)), masked)

        return masked, dict(self.mask_map)

    @classmethod
    def unmask(cls, text: str, mask_map: Dict[str, str]) -> str:
        """
        Hoàn trả toàn bộ các token ⟦MG_ID⟧ về đúng nội dung Markdown ban đầu.
        Độ phức tạp O(N), an toàn tuyệt đối không gây xung đột chuỗi.
        """
        if not text or not mask_map:
            return text

        def repl(match):
            token = match.group(0)
            return mask_map.get(token, token)

        return cls.PLACEHOLDER_PATTERN.sub(repl, text)


# ==============================================================================
# BỘ KIỂM THỬ TỰ ĐỘNG (Self-Test)
# ==============================================================================
if __name__ == "__main__":
    print("=" * 65)
    print(" CORE/MARKDOWN_GUARD: KIỂM THỬ BẢO VỆ CÚ PHÁP MARKDOWN")
    print("=" * 65)

    sample_markdown = """# Chương I: Lời Nói Đầu

Đây là đoạn văn có chữ **in đậm**, chữ *in nghiêng* và chú thích[^1].
Bác Ba nói:
> "Sự đời không ai học đặng chữ ngờ..."

Một danh sách kiểm tra:
1. Mục thứ nhất có link [Trang chủ](https://vietlit.org/index.html).
2. Mục thứ nhì có `inline code` và ảnh ![Minh họa](img/bia_sach.jpg).

---

```python
# Đoạn mã không được đụng vào:
print("Xin chào . thế giới !")
```

[^1]: Trích dẫn sách xưa xuất bản năm 1932.
"""

    guard = MarkdownGuard()
    print("-> 1. Văn bản Markdown gốc:")
    print("-" * 45)
    print(sample_markdown)
    print("-" * 45)

    masked_text, mask_map = guard.mask(sample_markdown)

    print(f"\n-> 2. Văn bản sau khi MASKING ({len(mask_map)} phần tử được bảo vệ):")
    print("-" * 45)
    print(masked_text)
    print("-" * 45)

    # Giả lập can thiệp của tầng Typography / Spell-check vào phần chữ lộ ra:
    # Ví dụ sửa từ 'nghiêng' thành 'rất nghiêng'
    simulated_fixed_text = masked_text.replace("in nghiêng", "rất nghiêng")

    restored_text = guard.unmask(simulated_fixed_text, mask_map)

    print("\n-> 3. Văn bản sau khi UNMASK (Khôi phục Markdown hoàn hảo):")
    print("-" * 45)
    print(restored_text)
    print("-" * 45)

    # Kiểm tra tính toàn vẹn cú pháp
    assert "# Chương I:" in restored_text
    assert "**in đậm**" in restored_text
    assert "*rất nghiêng*" in restored_text
    assert "[^1]" in restored_text
    assert "[^1]:" in restored_text
    assert "[Trang chủ](https://vietlit.org/index.html)" in restored_text
    assert 'print("Xin chào . thế giới !")' in restored_text
    assert "---" in restored_text

    print("\n[THÀNH CÔNG] Toàn bộ cú pháp Markdown được bảo toàn 100%!")

