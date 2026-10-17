# BẢN ĐẶC TẢ & KẾ HOẠCH TRIỂN KHAI: VIETLIT-PROOFREADER

Đại khái là mục tiêu: Chuẩn hóa sách điện tử để nó trở nên *universal* trên nhiều thiết bị nhất.

## I. TỔNG QUAN & NGUYÊN TẮC BẢO TỒN VĂN HỌC

1. **Phạm vi dữ liệu:** Tác phẩm văn học chữ Quốc ngữ từ thời sơ khai (thập niên 1880) đến trước năm 1975. Quy mô xử lý: **Từng chương sách (2.000 – 10.000 từ/phiên)**.
2. **Nguyên tắc bất khả xâm phạm (Preservation Rules):**
   - **Vị trí dấu thanh:** Chấp nhận song song cả hai chuẩn đặt dấu (Kiểu cũ: *hoà, thuỷ, khoẻ* và Kiểu mới: *hòa, thủy, khỏe*). Tuyệt đối **không tự ý hoán đổi** vị trí dấu của nguyên tác.
   - **Gạch nối từ ghép:** Bảo toàn 100% các từ ghép có gạch nối thời xưa (*quốc-gia, văn-học, xã-hội, tự-do*).
   - **Từ cổ & Phương ngữ:** Không tự ý hiện đại hóa từ vựng (giữ nguyên: *nhơn đức, đặng, dùm, bực, thuở/thoả*).
3. **Mục tiêu kỹ thuật:** Chạy offline, tốc độ phân tích $< 0.5$ giây/chương, không ảo giác (Zero Hallucination), bảo vệ an toàn cấu trúc Markdown.

---

## II. KIẾN TRÚC HỆ THỐNG (SYSTEM PIPELINE)

Hệ thống hoạt động theo luồng 4 tầng tuyến tính:

```
                  ┌──────────────────────────────────────────────┐
                  │            INPUT: Markdown Thô               │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ TẦNG 1: BẢO VỆ CÚ PHÁP & TIỀN XỬ LÝ (Syntax Guard & Normalizer)                 │
│  - Chuyển mã toàn bộ sang Unicode NFC.                                          │
│  - Masking: Đóng băng các phần tử Markdown (# Header, *italic*, > quote, [^1]). │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ TẦNG 2: QUY TẮC ĐỊNH DẠNG TẤT ĐỊNH (Deterministic Typography Rules)             │
│  - Xử lý khoảng trắng quanh dấu câu: dính liền ký tự trước, cách ký tự sau.     │
│  - Chuẩn hóa gạch đầu dòng thoại: Hyphen (-) -> Em-dash (—).                    │
│  - Tự động viết hoa sau dấu kết thúc câu (., !, ?, ...) và sau Em-dash (—).   │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ TẦNG 3: NLP THỐNG KÊ & TỪ ĐIỂN ĐA LỚP (Statistical NLP & Lexicon)               │
│  - Tokenizer bảo tồn gạch nối: Phân biệt `từ-ghép` với dấu trừ toán học.        │
│  - Bộ lọc âm tiết (Phonotactics): Phát hiện 99% lỗi OCR biến dạng (bănh, hoặe). │
│  - Thuật toán Viterbi (Word Segmentation): Sửa lỗi OCR dính chữ (tronglòng).    │
│  - Heuristic NER: Bảo vệ tên riêng, địa danh cổ khỏi bị báo lỗi sai.           │
│  - SymSpell Engine: Gợi ý từ thay thế dựa trên Edit Distance + Tần suất từ.     │
│  - N-gram Anomaly Detector: Cảnh báo lỗi Real-word (con gà -> con già).         │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ TẦNG 4: FASTAPI & GIAO DIỆN WEB DUYỆT LỖI (Human-in-the-Loop Web UI)            │
│  - Tính toán diff theo offset ký tự, gán nhãn mã lỗi (Error Badges).           │
│  - Giao diện 2 cột song song (Vanilla JS, CSS Grid).                            │
│  - Điều hướng và duyệt lỗi siêu tốc bằng bàn phím (Enter / X / W).              │
│  - Xuất ra file Markdown sạch 100%.                                             │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## III. CẤU TRÚC THƯ MỤC DỰ ÁN

```text
vietlit-proofreader/
├── data/
│   ├── valid_syllables.txt       # Danh sách ~20.000 âm tiết hợp lệ (cả dấu cũ & mới)
│   ├── dictionary.jsonl          # Từ ghép, từ cổ, từ điển từ Wiktionary/Kaikki
│   ├── unigram_freq.txt          # Bảng tần suất từ đơn (dùng cho Viterbi & SymSpell)
│   ├── bigram_freq.txt           # Bảng tần suất cụm 2 từ (dùng cho N-gram anomaly)
│   └── whitelist.txt             # Từ điển do người dùng tự bổ sung trong quá trình đọc
├── core/
│   ├── __init__.py
│   ├── normalizer.py             # Chuẩn hóa Unicode NFC, loại bỏ ký tự lạ
│   ├── markdown_guard.py         # Che chắn và hoàn trả cú pháp Markdown
│   ├── typography.py             # Bộ quy tắc Regex định dạng và viết hoa
│   ├── tokenizer.py              # Bộ tách token chuyên biệt cho từ có gạch nối
│   ├── phonotactics.py           # Bộ kiểm tra tính hợp lệ về mặt ngữ âm học
│   ├── nlp_segmenter.py          # Thuật toán Viterbi tách từ dính
│   ├── nlp_ner.py                # Nhận diện tên riêng / danh xưng cổ
│   ├── spell_checker.py          # Tích hợp SymSpell và đối soát từ điển
│   └── diff_engine.py            # Tổng hợp các lỗi thành danh sách Issue có vị trí
├── server/
│   ├── app.py                    # FastAPI Web Application & API endpoints
│   └── static/
│       ├── index.html            # Layout 2 cột duyệt bài
│       ├── style.css             # Giao diện Typography tối ưu cho đọc sách
│       └── app.js                # Xử lý tương tác Vanilla JS & Phím tắt
├── tools/
│   ├── build_syllables.py        # Script sinh tập âm tiết hợp lệ toán học
│   └── convert_kaikki.py         # Script convert dữ liệu Kaikki sang dictionary.jsonl
├── requirements.txt
└── run.py                        # File thực thi khởi chạy hệ thống
```

---

## IV. ĐẶC TẢ CHI TIẾT TỪNG MODULE

### 1. Module Dữ liệu & Ngữ âm (`phonotactics.py` & `data/`)
* **Tệp `valid_syllables.txt`:** Chứa toàn bộ các âm tiết tiếng Việt hợp lệ được sinh ra bằng tích Descartes của:
  $$\text{Âm đầu} \times \text{Âm đệm} \times \text{Âm chính} \times \text{Âm cuối} \times 6 \text{ Thanh điệu}$$
  *Ví dụ:* Cả `hoà` (dấu trên `o`) và `hòa` (dấu trên `a`) đều tồn tại độc lập trong tệp này.
* **Tệp `dictionary.jsonl`:** Định dạng JSON Lines, tối thiểu gồm trường:
  ```json
  {"word": "nhơn đức", "tags": ["archaic", "southern"]}
  {"word": "quốc-gia", "tags": ["compound", "hyphenated"]}
  ```
* **Tệp `whitelist.txt`:** Lưu trữ từ điển động. Tự động cập nhật mỗi khi người dùng bấm phím `W` trên Web UI.

### 2. Module Bảo vệ Markdown (`markdown_guard.py`)
* Sử dụng cơ chế **Masking (Đặt chỗ)** trước khi đưa văn bản vào xử lý chính tả:
  * Tiêu đề: `^#{1,6}\s+.*$` $\to$ `__MD_HEADER_0__`
  * Chữ in nghiêng/đậm: `(\*\*|__)(.*?)\1` $\to$ `__MD_BOLD_0__`
  * Khối trích dẫn / Thơ: `^>\s+.*$` $\to$ `__MD_QUOTE_0__`
  * Chú thích chân trang: `\[\^.+?\]` $\to$ `__MD_FN_0__`
* Sau khi toàn bộ pipeline xử lý xong, module sẽ unmask hoàn trả lại đúng vị trí ban đầu.

### 3. Module Typography & Viết hoa (`typography.py`)
Thực thi tuần tự qua các biểu thức Regex được tối ưu hóa:
1. **Khoảng trắng trước dấu:** Thay thế `\s+([.,;:!?»\)])` $\to$ `\1`.
2. **Khoảng trắng sau dấu:** Thay thế `([.,;:!?«\(])(?=[^\s\d\w\.,])` đảm bảo có đúng 1 space (loại trừ số thập phân `3.14` và chữ viết tắt `v.v.`).
3. **Gạch đầu dòng hội thoại:** Tìm các dòng bắt đầu bằng `^-\s+` hoặc `^–\s+` chuyển thành `— ` (Em-dash).
4. **Viết hoa sau dấu câu:**
   - Bắt các điểm kết câu: `(?<=[\.\!\?]\s)\b([a-zà-ỹ])` và sau gạch thoại `(?<=^—\s)\b([a-zà-ỹ])`.
   - Chuyển ký tự tìm được thành chữ hoa tương ứng.
   - *Ngoại lệ (Exception List):* Không viết hoa sau các từ viết tắt thông dụng: `v.v.`, `ông N.`, `th.s`, `tp.`, `q.`.

### 4. Module NLP Thống kê (`nlp_segmenter.py`, `spell_checker.py`, `nlp_ner.py`)

* **Tokenizer chuyên dụng:**
  Sử dụng biểu thức chính quy tách token có bảo tồn gạch nối:
  `TOKEN_PATTERN = r'\b[A-Za-zÀ-ỹ]+(?:-[A-Za-zÀ-ỹ]+)*\b'`
* **Thuật toán Viterbi (Tách chữ dính):**
  - Khi gặp một chuỗi chữ cái không tìm thấy trong từ điển nhưng có độ dài $> 7$ ký tự (ví dụ: `tronglòng`, `ôngấy`):
  - Áp dụng thuật toán Quy hoạch động Viterbi kết hợp với bảng tần suất `unigram_freq.txt` để tìm nhát cắt tối ưu nhất:
    $$\arg\max \prod_{i} P(w_i)$$
    Kết quả: `tronglòng` $\to$ `trong lòng`.
* **Heuristic NER (Bảo vệ tên riêng cổ):**
  - Bắt các chuỗi 2-4 từ viết hoa liên tiếp đi kèm các danh từ chỉ định phía trước:
    `(?i:\b(ông|bà|thầy|cô|quan|tổng đốc|làng|phủ|sông|núi)\s+)([A-ZÀ-Ỹ][a-zà-ỹ]+(?:\s+[A-ZÀ-Ỹ][a-zà-ỹ]+)*)`
  - Đưa cụm này vào danh sách "An toàn", không kích hoạt cảnh báo sai từ điển.
* **SymSpell Suggestion Engine:**
  - Nạp toàn bộ `valid_syllables.txt` và `dictionary.jsonl` vào cấu trúc Trie/Dictionary của SymSpell.
  - Khi một từ bị xác định là lỗi OCR (ví dụ: `ngưòi`), SymSpell tìm kiếm các ứng viên có khoảng cách Damerau-Levenshtein $\le 2$, ưu tiên các ứng viên có tần suất xuất hiện cao nhất trong `unigram_freq.txt` để đưa ra gợi ý (Gợi ý số 1: `người`).
* **N-gram Anomaly Detector (Phát hiện lỗi ngữ cảnh):**
  - Quét các cặp từ liền kề (Bigram). Nếu $P(w_2 \mid w_1) < \epsilon$ (ngưỡng xác suất cực thấp, ví dụ: `con già`), hệ thống sẽ đánh dấu cảnh báo màu vàng: *"Nghi ngờ lỗi ngữ cảnh (Contextual Anomaly)"*.

### 5. Module Diff Engine & FastAPI (`diff_engine.py`, `server/app.py`)
Mỗi lỗi phát hiện được đóng gói thành một cấu trúc dữ liệu JSON thống nhất:
```json
{
  "id": "iss_102",
  "category": "TYPO_OCR", 
  "start": 245,
  "end": 250,
  "original": "ngưòi",
  "replacement": "người",
  "reason": "Âm tiết không hợp lệ trong tiếng Việt",
  "candidates": ["người", "người", "ngòi"]
}
```
* **Danh mục lỗi (`category`):**
  - `TYPOGRAPHY`: Sửa khoảng trắng, dấu câu.
  - `CAPITALIZATION`: Sửa viết hoa sau dấu câu.
  - `OCR_SPLIT`: Sửa dính chữ qua Viterbi.
  - `TYPO_OCR`: Lỗi từ vô nghĩa, sửa qua SymSpell.
  - `CONTEXT_ANOMALY`: Lỗi từ có nghĩa nhưng sai ngữ cảnh (N-gram).

---

## V. ĐẶC TẢ GIAO DIỆN WEB UI (HTML / CSS / VANILLA JS)

Giao diện tập trung tối đa vào công thái học (Ergonomics), giúp người đọc rà soát hàng ngàn từ mà không bị mỏi mắt hay phân tâm.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  VIETLIT-PROOFREADER  │ Chương: 01.md │ [✓ Duyệt nhanh Typo] [💾 Xuất Markdown]   │
├────────────────────────────────────────┬─────────────────────────────────────────┤
│ CỘT TRÁI: NGUYÊN BẢN (ORIGINAL)        │ CỘT PHẢI: BẢN ĐỀ XUẤT (PROPOSED DIFF)   │
├────────────────────────────────────────┼─────────────────────────────────────────┤
│                                        │                                         │
│ — Thưa thầy ,con mới về .              │ — Thưa thầy, con mới về.                │
│                                        │           ^ [TYPOGRAPHY]                │
│ ngoài đồng hôm nay nhiều việc quá .    │ Ngoài đồng hôm nay nhiều việc quá.      │
│                                        │ ^ [CASE]                                │
│ tronglòng con thấy không đặng an.      │ trong lòng con thấy không đặng an.      │
│                                        │ ^^^^^^^^^^ [OCR_SPLIT]                  │
│ Chiếc lá thu rơi ngoài thềm .          │ Chiếc lá thu rơi ngoài thềm.            │
│                                        │          ^^^ [CONTEXT_ANOMALY]          │
│                                        │                                         │
└────────────────────────────────────────┴─────────────────────────────────────────┘
```

### Các tính năng tương tác chính của UI:
1. **Cuộn đồng bộ (Synchronized Scrolling):** Khi cuộn cột bên phải, cột bên trái tự động cuộn theo tương ứng để đối chiếu ngữ cảnh gốc.
2. **Hệ thống phím tắt (Keyboard Navigation):**
   - Phím `J` / `K`: Nhảy tới lỗi tiếp theo / lùi lại lỗi trước.
   - Phím `Enter` / Phím cách (`Space`): Chấp nhận sửa lỗi hiện tại $\to$ tự động nhảy sang lỗi kế tiếp.
   - Phím `X`: Bỏ qua lỗi hiện tại (giữ nguyên bản gốc).
   - Phím `W`: Thêm từ này vào `whitelist.txt` và bỏ gạch chân toàn bộ các từ tương tự trong toàn văn bản.
3. **Nút "Duyệt nhanh Typo & Viết hoa":** Một nút bấm cho phép tự động chấp nhận toàn bộ các lỗi hiển nhiên thuộc loại `TYPOGRAPHY` và `CAPITALIZATION`, giải phóng 80% khối lượng thao tác thủ công để người duyệt tập trung vào các lỗi từ vựng.
4. **Lưu vết LocalStorage:** Trạng thái duyệt của chương hiện tại được tự động lưu tạm trên trình duyệt, không lo mất tiến độ nếu vô tình F5 hoặc tắt tab.

---

## VI. LỘ TRÌNH THỰC HIỆN THEO TỪNG GIAI ĐOẠN (STEP-BY-STEP ROADMAP)

### Giai đoạn 1: Thiết lập Dữ liệu & Công cụ chuẩn bị

- [x] Viết `tools/build_syllables.py`: Sinh đầy đủ bảng âm tiết tiếng Việt với cả 2 cách đặt dấu $\to$ xuất ra `data/valid_syllables.txt`.
- [x] Viết `tools/convert_kaikki.py`: Đọc JSONL từ Kaikki/Wiktionary, lọc mục từ $\to$ tạo `data/dictionary.jsonl` và `data/unigram_freq.txt`.
- [x] Khởi tạo file trống `data/whitelist.txt`.

### Giai đoạn 2: Lập trình Core Engine - Tầng Rule-based

- [x] Xây dựng `core/normalizer.py`: Ép chuẩn Unicode NFC và dọn dẹp các ký tự điều khiển ẩn.
- [x] Xây dựng `core/markdown_guard.py`: Cơ chế Masking bảo vệ cú pháp Markdown (Headers, Quotes, Styling).
- [x] Xây dựng `core/typography.py`: Bộ Regex chuẩn hóa khoảng trắng quanh dấu câu, gạch thoại Em-dash, và viết hoa đầu câu/sau thoại.

### Giai đoạn 3: Lập trình Core Engine - Tầng NLP Thống kê

- [x] Xây dựng `core/tokenizer.py`: Nhận diện token chữ đơn và từ ghép nối bằng gạch ngang (`-`).
- [x] Xây dựng `core/phonotactics.py`: Đối soát nhanh âm tiết qua `set()` trong Python (độ phức tạp $O(1)$).
- [x] Xây dựng `core/nlp_segmenter.py`: Thuật toán Viterbi giải quyết bài toán dính chữ OCR.
- [x] Xây dựng `core/nlp_ner.py`: Bộ lọc Regex bắt cụm danh xưng + tên riêng.
- [x] Xây dựng `core/spell_checker.py`: Tích hợp `symspellpy` với từ điển tần suất để đề xuất từ thay thế.

### Giai đoạn 4: FastAPI Backend & Diff Engine

- [ ] Viết `core/diff_engine.py`: Gom các thay đổi từ Tầng 2 & Tầng 3 thành danh sách Issues có tọa độ ký tự chính xác.
- [ ] Viết `server/app.py`:
  - `POST /api/scan`: Nhận Markdown, trả về AST Issues và bản text đề xuất.
  - `POST /api/apply`: Nhận danh sách Issue IDs được duyệt, unmask và trả về file Markdown sạch.
  - `POST /api/whitelist`: Ghi từ mới vào file `data/whitelist.txt`.

### Giai đoạn 5: Dựng Giao diện Web UI (Vanilla JS)

- [ ] Viết `server/static/index.html` và `style.css`: Layout Split-view 2 cột với typography thân thiện với việc đọc sách dài.
- [ ] Viết `server/static/app.js`:
  - Fetch dữ liệu từ API `/api/scan`.
  - Render thẻ `<mark class="issue [category]" data-id="...">` trên cột phải.
  - Xây dựng hệ thống phím tắt (`J`, `K`, `Enter`, `X`, `W`).
  - Tích hợp tính năng Export file `.md` về máy tính.

### Giai đoạn 6: Thử nghiệm thực tế & Tinh chỉnh (Tuần 6)
- [ ] Tạo file mẫu `test_sample.md` chứa văn bản thực tế từ:
  - Một truyện ngắn của Hồ Biểu Chánh (đại diện Nam Bộ xưa).
  - Một tác phẩm của Nhất Linh / Khái Hưng (đại diện văn học tiền chiến có gạch nối).
  - Một tập tin OCR thực tế từ ABBYY chứa các lỗi dính chữ, sai dấu, rác ký tự.
- [ ] Kiểm thử độ an toàn của cú pháp Markdown sau khi xuất file.
- [ ] Đo lường hiệu năng và tinh chỉnh ngưỡng xác suất của Viterbi / N-gram để hạn chế tối đa cảnh báo giả.

---

## VII. TIÊU CHÍ NGHIỆM THU DỰ ÁN (ACCEPTANCE CRITERIA)

1. **Tính chính xác về mặt lịch sử:**
   - 100% các từ có gạch nối hợp lệ (như `quốc-gia`, `văn-nghệ`) **không bị cắt bỏ dấu gạch nối**.
   - 100% các từ đặt dấu kiểu cũ (như `hoà`, `thuỷ`) **không bị tự động chuyển đổi** sang kiểu mới (`hòa`, `thủy`) và ngược lại.
2. **Hiệu năng xử lý:**
   - Thời gian quét một chương sách 5.000 từ trên máy tính cá nhân thông thường đạt **dưới 0.5 giây**.
3. **An toàn cú pháp:**
   - File Markdown xuất ra từ công cụ khi chuyển đổi sang `.epub` (bằng Pandoc hoặc Calibre) không xuất hiện bất kỳ lỗi bể layout, mất tiêu đề hay mất trích dẫn.
4. **Vận hành độc lập:**
   - Công cụ chạy trực tiếp bằng lệnh `python run.py`, toàn bộ giao diện phục vụ cục bộ trên trình duyệt qua `http://localhost:8000`, hoạt động hoàn hảo khi ngắt toàn bộ kết nối Internet.

---

Bản kế hoạch trên đã khép kín toàn bộ yêu cầu, kiến trúc và lộ trình triển khai chi tiết. Khi bạn đã xem xét và đồng ý với bản kế hoạch này, chúng ta sẽ bắt đầu ngay vào **Giai đoạn 1**: Viết các đoạn mã chuẩn bị dữ liệu ngữ âm (`tools/build_syllables.py`) và chuyển đổi từ điển.