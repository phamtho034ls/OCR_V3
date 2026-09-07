# OCR Sổ đỏ / Sổ hồng

Pipeline trích xuất dữ liệu có cấu trúc từ ảnh/scan/PDF Giấy chứng nhận quyền sử dụng đất (GCNQSDĐ) tại Việt Nam.

---

## Tổng quan kiến trúc

```
ocr-so-do/
├── configs/
│   ├── template_labels.json   # Nhãn field theo từng mẫu (A/B)
│   └── color_profiles.json    # Profile màu xử lý nền theo mẫu
├── preprocessing/
│   ├── ingestion.py           # Đọc ảnh/PDF, kiểm tra chất lượng
│   ├── deskew.py              # Chỉnh nghiêng, crop biên
│   ├── color_profile.py       # CLAHE, tách kênh màu theo mẫu
│   └── seal_mask.py           # Che dấu mộc đỏ/xanh (HSV threshold)
├── detection/
│   └── paddleocr_detect.py    # PaddleOCR PP-OCRv4, trả bbox + text
├── recognition/
│   ├── vietocr_recognize.py   # VietOCR VGG/ResNet-Transformer
│   └── fine_tune_scaffold.py  # Scaffold fine-tune (chạy khi có dữ liệu)
├── extraction/
│   ├── template_classifier.py   # Phân loại mẫu A/B (keyword-based)
│   ├── page_grouper.py          # Gom trang theo mã số phát hành
│   ├── label_anchor_extractor.py # Trích field theo nhãn (fuzzy match)
│   ├── cross_validate.py        # Đối chiếu số ↔ chữ diện tích
│   ├── diagram_extractor.py     # Tách vùng sơ đồ thửa đất
│   └── address_normalizer.py    # Chuẩn hóa địa chỉ + ngày tháng
├── api/
│   └── main.py                # FastAPI: /ocr, /ocr/batch, /review
├── tests/
│   ├── fixtures/              # Ảnh mẫu test (không commit dữ liệu thật)
│   ├── test_extraction.py
│   ├── test_preprocessing.py
│   ├── test_ingestion.py
│   └── test_api.py
├── requirements.txt
├── run.py                     # CLI runner
└── README.md
```

**Pipeline 13 bước:**

```
Ingestion → Preprocessing → Template Classification → Page Grouping →
Seal Masking → Text Detection → Text Recognition → Field Extraction →
Cross-Validation → Diagram Extraction → Post-Processing →
Confidence Scoring → Output JSON
```

---

## Yêu cầu hệ thống

| Thành phần | Yêu cầu tối thiểu |
|---|---|
| GPU VRAM | 4 GB (model load ~2.5–3 GB) |
| RAM | 16 GB |
| Python | 3.10+ |
| CUDA | 12.x (optional, có fallback CPU) |
| OS | Windows / Linux |

---

## Cài đặt

### 1. Tạo môi trường ảo

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate
```

### 2. Cài PyTorch (CUDA 12.1)

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

> Nếu không có GPU: `pip install torch torchvision`

### 3. Cài PaddlePaddle GPU (Windows + CUDA 12.x)

```bash
pip install paddlepaddle-gpu==2.6.2.post120 \
  -f https://www.paddlepaddle.org.cn/whl/windows/mkl/avx/stable.html
```

> CPU-only: `pip install paddlepaddle`

### 4. Cài các dependency còn lại

```bash
pip install -r requirements.txt
```

---

## Chạy

### Chạy API server

```bash
python run.py serve
# Mặc định: http://0.0.0.0:8000
# Swagger docs: http://localhost:8000/docs

# Tuỳ chọn:
python run.py serve --host 127.0.0.1 --port 8080 --reload
```

### OCR một file

```bash
python run.py ocr path/to/scan.jpg
# Hoặc PDF:
python run.py ocr path/to/gcn.pdf

# Lưu kết quả ra file JSON:
python run.py ocr scan.jpg --output result.json

# OCR nhiều file, lưu vào thư mục:
python run.py ocr img1.jpg img2.jpg --output-dir results/

# Chạy CPU-only (không dùng GPU):
python run.py ocr scan.jpg --cpu
```

### Chạy tests

```bash
python run.py test
# Hoặc trực tiếp:
pytest tests/ -v --tb=short
```

---

## Sử dụng API

### OCR đơn lẻ

```bash
curl -X POST http://localhost:8000/ocr \
  -F "file=@/path/to/gcn.jpg"
```

**Response mẫu:**

```json
{
  "job_id": "a1b2c3d4",
  "mau": "mau_B",
  "so_phat_hanh": "CĐ754219",
  "so_vao_so": "CT00.484",
  "nguoi_su_dung": {
    "ten": "Nguyễn Văn A",
    "cmnd": "123456789",
    "ngay_sinh": "",
    "dia_chi_thuong_tru": "Xã An Phú, Huyện Thuận An, Bình Dương"
  },
  "thua_dat": {
    "so_thua": "456",
    "to_ban_do": "78",
    "dia_chi": "Xã An Phú, Huyện Thuận An, Tỉnh Bình Dương",
    "dien_tich_so": "500 m²",
    "dien_tich_chu": "",
    "dien_tich_validated": false,
    "hinh_thuc_su_dung": "",
    "muc_dich_su_dung": "Đất ở tại đô thị",
    "thoi_han": "Lâu dài",
    "nguon_goc": "Nhà nước công nhận"
  },
  "confidence": {
    "so_thua": 0.97,
    "to_ban_do": 0.96,
    "dien_tich": 0.95
  },
  "can_review": ["nguon_goc"],
  "quality_check": {"warnings": []},
  "attachments": {
    "so_do_thua_dat": "output/a1b2c3d4/a1b2c3d4_diagram.png"
  },
  "processing_time_ms": 1240.5
}
```

### OCR batch (nhiều file)

```bash
curl -X POST http://localhost:8000/ocr/batch \
  -F "files=@img1.jpg" \
  -F "files=@img2.jpg"

# Poll kết quả:
curl http://localhost:8000/batch/{batch_id}
```

### Lấy danh sách cần review thủ công

```bash
curl http://localhost:8000/review
```

---

## Cấu hình `template_labels.json`

File `configs/template_labels.json` định nghĩa nhãn field cho từng mẫu tài liệu.

### Cấu trúc

```json
{
  "mau_A": {
    "_meta": {
      "description": "Mô tả mẫu",
      "diagram_region": "top_right",
      "pages": 1
    },
    "ten_truong": "Nhãn trên giấy:"
  },
  "mau_B": { ... }
}
```

### Thêm mẫu mới (mẫu C, D, ...)

1. Mở `configs/template_labels.json`
2. Thêm key mới ở cấp cao nhất, ví dụ `"mau_C"`:

```json
{
  "mau_A": { ... },
  "mau_B": { ... },
  "mau_C": {
    "_meta": {
      "description": "Giấy chứng nhận mẫu 2014 - Thông tư 23",
      "diagram_region": "bottom_right",
      "pages": 2
    },
    "so_thua": "Thửa đất số:",
    "to_ban_do": "Tờ bản đồ số:",
    "dien_tich": "Diện tích:",
    "muc_dich_su_dung": "Mục đích sử dụng:",
    "ten_truong_moi": "Nhãn mới trên giấy mẫu C:"
  }
}
```

3. **Thêm từ khóa phân loại** vào `extraction/template_classifier.py`:

```python
# Trong class TemplateClassifier:
KEYWORDS_MAU_C: List[str] = [
    "THONG TU 23",
    "2014",
    # ... thêm keyword nhận diện mẫu C
]
```

4. Cập nhật phương thức `classify()` để nhận diện mẫu C.

> **Các trường bắt buộc theo `_extension_guide`:** `_meta`, `so_thua`, `to_ban_do`, `dien_tich`, `muc_dich_su_dung`

---

## Cấu hình `color_profiles.json`

Định nghĩa cách xử lý màu nền cho từng mẫu:

- **Mẫu A** (nền vàng): Ưu tiên kênh Green/Grayscale
- **Mẫu B** (nền hồng): Ưu tiên kênh Blue để tách chữ khỏi nền hồng

---

## Giải thích output JSON

| Trường | Mô tả |
|---|---|
| `mau` | Mẫu phân loại: `mau_A`, `mau_B`, `unknown` |
| `so_phat_hanh` | Mã định danh duy nhất (chỉ mẫu B), dạng `[A-ZĐ]{2}\d{6}` |
| `confidence` | Điểm tin cậy 0–1 từng field (OCR confidence + validation) |
| `can_review` | Danh sách tên field cần review thủ công |
| `attachments.so_do_thua_dat` | Đường dẫn ảnh sơ đồ thửa đất đã crop |
| `raw_fields` | Toàn bộ field raw từ OCR (debug) |

**Ngưỡng review:** Field có `confidence < 0.6` hoặc không có giá trị sẽ vào `can_review`.

---

## Fine-tuning VietOCR (scaffold)

Script scaffold đã có tại `recognition/fine_tune_scaffold.py`.

**Chạy khi đã có dữ liệu gán nhãn:**

```bash
python recognition/fine_tune_scaffold.py \
  --data-dir path/to/labeled_data/ \
  --output-dir models/vietocr_finetuned/
```

Dữ liệu cần theo format: mỗi ảnh crop text + file `.txt` chứa ground truth.

---

## Lưu ý bảo mật

- **Không commit ảnh giấy tờ thật** vào thư mục `tests/fixtures/`
- Dùng ảnh mẫu synthetic/ẩn danh để test
- Output JSON chứa thông tin nhạy cảm (CMND, địa chỉ) — bảo vệ thư mục `output/`

---

## Troubleshooting

| Lỗi | Giải pháp |
|---|---|
| `CUDA out of memory` | Chạy `python run.py ocr ... --cpu` hoặc giảm batch size |
| `paddleocr not found` | Cài đúng phiên bản theo CUDA (xem hướng dẫn cài đặt) |
| `vietocr model not found` | VietOCR tự tải model khi chạy lần đầu (cần internet) |
| Field trả về rỗng | Kiểm tra `can_review` và `confidence` — ảnh có thể mờ hoặc nghiêng |
| Template `unknown` | Thêm keyword nhận diện vào `TemplateClassifier` |
