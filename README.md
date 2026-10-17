# Số hóa văn học

## Giai đoạn 0 - Xây dựng môi trường

Bạn mở Terminal tại thư mục gốc của dự án và chạy các lệnh sau:

1. **Khởi tạo và kích hoạt môi trường ảo (Khuyến nghị để tránh xung đột thư viện):**
   ```bash
   # Tạo môi trường ảo venv
   python -m venv venv

   # Kích hoạt trên Linux/macOS:
   source venv/bin/activate

   # Hoặc kích hoạt trên Windows (Command Prompt / PowerShell):
   # venv\Scripts\activate
   ```

2. **Cài đặt toàn bộ dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

Tất cả các module còn lại của dự án (như regex, Unicode normalization, thuật toán quy hoạch động Viterbi, bộ lọc ngữ âm...) đều được viết dựa trên thư viện chuẩn có sẵn của Python (`unicodedata`, `re`, `json`, `collections`, `pathlib`) nên không cần tải thêm bất kỳ gói cồng kềnh nào khác.

## Giai đoạn 1

### Hướng dẫn chạy và kết quả dự kiến

1. **Cách thực thi:**
   Bạn lưu đoạn mã trên vào đường dẫn `tools/build_syllables.py` trong thư mục dự án, sau đó mở Terminal chạy lệnh:
   ```bash
   python tools/build_syllables.py
   ```

2. **Kết quả tạo ra:**
   - Script sẽ tự động tạo thư mục `data/` (nếu chưa có) và ghi ra file `data/valid_syllables.txt`.
   - Dung lượng: Chứa khoảng **~18.000 – 21.000 âm tiết** hợp lệ (tất cả đều đã ép mã Unicode NFC chuẩn tuyệt đối).
   - Màn hình Console sẽ in bảng kiểm chứng xác nhận các cặp từ đặt dấu cũ như `hoà, thuỷ, khoè, toạ, thuỵ` và các từ đặt dấu kiểu mới `hòa, thủy, khòe, tọa, thụy` đều có mặt song song với đánh dấu `[✓]`.

Tệp này sẽ đóng vai trò là "chân vạc thứ nhất" phục vụ việc tra cứu $O(1)$ siêu tốc cho Core Engine ở các bước tiếp theo. Bạn chạy thử nghiệm tệp này xong hãy cho mình biết kết quả nhé!

### Hướng dẫn sử dụng & Tải dữ liệu Kaikki

1. **Tải tệp dữ liệu Kaikki:**
   Bạn mở Terminal, di chuyển vào thư mục dự án và tải tệp JSONL của tiếng Việt bằng `curl` (hoặc tải trực tiếp bằng trình duyệt):
   ```bash
   # Tải bản trích xuất tiếng Việt từ Kaikki (khoảng 50MB - 120MB)
   curl -L -o data/kaikki-vietnamese.jsonl "https://kaikki.org/dictionary/Vietnamese/kaikki.org-dictionary-Vietnamese.jsonl"
   ```

2. **Chạy script chuyển đổi:**
   ```bash
   python tools/convert_kaikki.py
   ```
   *(Script sẽ tự động tìm tệp `.jsonl` trong thư mục `data/` mà không cần bạn gõ thêm tham số).*

3. **Kết quả đạt được:**
   - Tạo ra `data/dictionary.jsonl`: Lưu hàng chục ngàn từ ghép, thành ngữ, từ cổ kèm tag phân loại; tự động liên kết các cặp từ gạch nối như `quốc-gia` và `quốc gia`.
   - Tạo ra `data/unigram_freq.txt`: Bảng tần suất phân phối thực tế của từ vựng tiếng Việt, sẵn sàng cho thuật toán Viterbi và SymSpell ở các bước tiếp theo.

Sau khi chạy xong Giai đoạn 1 này, thư mục `data/` của bạn đã có đủ bộ 3 dữ liệu cốt lõi (`valid_syllables.txt`, `dictionary.jsonl`, `unigram_freq.txt`). Chúng ta đã sẵn sàng chuyển sang **Giai đoạn 2: Xây dựng Core Rule-Engine (Markdown Guard & Typography)**!

## Giai đoạn 2

### Normalizer

1. Đảm bảo bạn đã tạo file trống `core/__init__.py` để thư mục `core` trở thành một Python package:
   ```bash
   touch core/__init__.py
   ```
2. Chạy thử nghiệm trực tiếp module này:
   ```bash
   python core/normalizer.py
   ```
   Bạn sẽ thấy terminal in ra kết quả tự động phát hiện, triệt tiêu mã BOM `\uFEFF`, khử sạch rác `\u200B`, `\u00AD`, chuyển đổi `\u00A0` về dấu cách chuẩn và kiểm định toàn bộ văn bản đầu ra đạt **Unicode NFC 100%**.

### Guardrail

1. **Kiểm tra chính tả xuyên thấu (Transparent Formatting):** Các cụm `**in đậm**` được che `**` thành `⟦MG_0⟧in đậm⟦MG_1⟧`, do đó từ `in đậm` nằm ở giữa vẫn hoàn toàn chịu sự kiểm soát của bộ chính tả/OCR mà định dạng `**` không hề bị vỡ.
2. **Khôi phục $O(N)$ bằng Regex:** Hàm `unmask` dùng biểu thức `PLACEHOLDER_PATTERN.sub` một lần duy nhất, giải mã hàng chục ngàn từ chỉ mất vài phần triệu giây.

Sau khi đã có `normalizer.py` và `markdown_guard.py`, chúng ta đã sẵn sàng chuyển sang mắt xích quan trọng nhất của Giai đoạn 2: **`core/typography.py`** (Chuẩn hoá khoảng trắng quanh dấu câu, gạch thoại Em-dash `— `, và viết hoa tự động sau dấu câu). Bạn hãy cho mình biết khi sẵn sàng nhé!


### Kiểm tra typography:

```
python core/typography.py
```

