Dưới đây là câu trả lời chi tiết cho thắc mắc kiến trúc của bạn, cùng với kế hoạch và toàn bộ mã nguồn của **3 script công cụ** để chuyển đổi và gộp từ điển.

---

### 1. Chương trình nên đọc MỘT tệp hay NHIỀU tệp `.jsonl`?

**Khuyến nghị kỹ thuật: Chương trình chính (Core Engine) chỉ nên đọc MỘT tệp duy nhất (`data/dictionary.jsonl`).**

Lý do:
1. **Tốc độ khởi động và tra cứu:** Nạp một tệp phẳng đã được gộp sẵn vào bộ nhớ RAM (`dict` hoặc `set` trong Python) chỉ mất khoảng **0.05 – 0.1 giây**. Nếu để Core Engine đọc cùng lúc nhiều tệp rồi phân xử xung đột mỗi lần chạy, chương trình sẽ bị trễ và tốn RAM vô ích.
2. **Nguyên lý Unix (Modular Pipeline):** Chúng ta tách biệt hoàn toàn giữa **Tầng chuẩn bị dữ liệu (Data Pipeline)** và **Tầng vận hành (Core Engine)**:
   - Từng nguồn từ điển (Kaikki, Yomitan, danh sách TXT) có một script converter riêng để xuất ra file `.jsonl` tạm thời.
   - Một script trung tâm (`merge_dictionaries.py`) sẽ gộp, khử trùng (deduplicate), giải quyết xung đột (ưu tiên Wiktionary), hợp nhất thẻ tag và xuất ra tệp master `data/dictionary.jsonl`.

```
[Kaikki JSONL]   ──► convert_kaikki.py  ──► data/dict_kaikki.jsonl  ──┐
[Yomitan .zip]   ──► convert_yomitan.py ──► data/dict_yomitan.jsonl ──┼─► merge_dictionaries.py ─► data/dictionary.jsonl
[TXT Wordlists]  ──► convert_txt.py     ──► data/dict_txt.jsonl     ──┘   (Master duy nhất)
```

---

### 2. Mã nguồn: `tools/convert_yomitan.py`
*Tác dụng:* Đọc trực tiếp từ tệp `.zip` (hoặc thư mục giải nén) của từ điển Yomitan/Yomichan, phân tích cấu trúc `term_bank_*.json` và chuyển đổi sang `.jsonl`.

```python

```

---

### 3. Mã nguồn: `tools/convert_txt.py`
*Tác dụng:* Chuyển đổi các danh sách từ vựng dạng plain text (như VNTK, Hồ Ngọc Đức, mỗi dòng một từ) sang `.jsonl`.

```python

```

---

### 4. Mã nguồn: `tools/merge_dictionaries.py`
*Tác dụng:* **Gộp nhiều tệp `.jsonl` thành tệp `data/dictionary.jsonl` duy nhất.**
- **Khử trùng lặp (Deduplicate).**
- **Ưu tiên Wiktionary (Kaikki):** Nếu mục từ đã có trong Wiktionary, nó sẽ giữ định nghĩa gốc của Wiktionary nhưng **hợp nhất (union) các tag mới** từ Yomitan/TXT vào.
- **Tự động mở rộng từ ghép gạch nối:** Tạo cặp đối ứng (`quốc gia` $\leftrightarrow$ `quốc-gia`).

```python

```

---

### 5. Hướng dẫn Luồng chạy Tổng thể (End-to-End Workflow)

Bây giờ bạn có một quy trình cực kỳ linh hoạt để nạp bất kỳ nguồn từ điển nào:

```bash
# Bước 1: Sinh bộ âm tiết hợp lệ (đã làm ở lượt trước)
python tools/build_syllables.py

# Bước 2: Chuyển đổi các nguồn từ điển bạn có về .jsonl
# 2.1 Convert Kaikki -> data/dict_kaikki.jsonl
python tools/convert_kaikki.py --input data/kaikki-vietnamese.jsonl --output-dict data/dict_kaikki.jsonl

# 2.2 Convert Yomitan -> data/dict_yomitan.jsonl
python tools/convert_yomitan.py --input data/viet-yomitan.zip --output data/dict_yomitan.jsonl

# 2.3 Convert file hoặc thư mục txt -> data/dict_txt.jsonl
python tools/convert_txt.py --input data/vntk_words.txt --output data/dict_txt.jsonl

# Bước 3: Gộp tất cả thành 1 tệp duy nhất với thứ tự ưu tiên
python tools/merge_dictionaries.py
```

Sau khi chạy lệnh ở Bước 3, chương trình chính sẽ chỉ làm việc với đúng một tệp `data/dictionary.jsonl` hoàn chỉnh, chứa toàn bộ vốn từ của tất cả các nguồn bạn đã thu thập được mà không bao giờ bị trùng lặp.