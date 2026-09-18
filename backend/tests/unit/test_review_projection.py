from ocr_so_do.application.projections.review_projection import build_document_review


def test_review_projection_links_field_to_page_box_and_crop():
    bbox = [[100, 200], [260, 200], [260, 235], [100, 235]]
    record = {
        "id": "doc_1",
        "file_name": "BH 405667.pdf",
        "template": "mau_B",
        "status": "success",
        "structured_data": {
            "so_phat_hanh": "BH 405667",
            "nguoi_su_dung": {"ho_ten_chu_1": "Đặng Văn Nghiệp"},
            "thua_dat": {"so_thua": "21", "to_ban_do": "97"},
            "pages": [{
                "page_index": 0,
                "preview_url": "/output/doc_1/page_1/preview_p1.png",
                "raw_fields": {
                    "so_phat_hanh": {
                        "value": "BH 405667",
                        "confidence": 0.98,
                        "bbox": bbox,
                        "source_line": "Số phát hành BH 405667",
                    },
                },
                "crops": [{
                    "url": "/output/doc_1/page_1/crops/crop_0001.png",
                    "bbox": bbox,
                    "final_text": "BH 405667",
                    "final_conf": 0.98,
                }],
                "ocr_results": [],
            }],
        },
    }

    payload = build_document_review(
        record,
        field_reviews={
            "so_phat_hanh": {
                "review_status": "confirmed",
                "reviewed_at": "2026-09-17 10:00:00",
            },
        },
    )

    serial = next(field for field in payload["fields"] if field["key"] == "so_phat_hanh")
    assert payload["pages"] == [{
        "page_index": 0,
        "label": "Trang 1",
        "image_url": "/output/doc_1/page_1/preview_p1.png",
        "has_image": True,
    }]
    assert serial["page_index"] == 0
    assert serial["bbox"] == bbox
    assert serial["crop_url"].endswith("crop_0001.png")
    assert serial["review"]["review_status"] == "confirmed"


def test_review_projection_omits_empty_optional_second_owner():
    payload = build_document_review({
        "id": "doc_2",
        "file_name": "one-owner.pdf",
        "structured_data": {
            "nguoi_su_dung": {"ho_ten_chu_1": "Nguyễn Văn A"},
            "pages": [],
        },
    })

    keys = {field["key"] for field in payload["fields"]}
    assert "ho_ten_chu_2" not in keys
    assert "cmnd_chu_2" not in keys


def test_review_projection_prefers_verified_token_over_wrong_parser_bbox():
    header_bbox = [[700, 220], [880, 220], [880, 250], [700, 250]]
    value_bbox = [[520, 310], [620, 310], [620, 336], [520, 336]]
    payload = build_document_review({
        "id": "doc_3",
        "file_name": "table.pdf",
        "structured_data": {
            "thua_dat": {"thoi_han": "Đến 11/2019"},
            "pages": [{
                "page_index": 2,
                "preview_url": "/output/doc_3/page_3/preview_p3.png",
                "raw_fields": {
                    # Đây là dạng dữ liệu lỗi đang có: parser cho value đúng
                    # nhưng vẫn giữ bbox header "Nguồn gốc sử dụng".
                    "thoi_han": {
                        "value": "Đến 11/2019",
                        "confidence": 0.95,
                        "bbox": header_bbox,
                        "source_line": "Thời hạn",
                    },
                },
                "ocr_results": [{
                    "text": "11/11/2019",
                    "confidence": 0.93,
                    "bbox": value_bbox,
                }],
                "crops": [
                    {"bbox": header_bbox, "final_text": "Nguồn gốc sử dụng", "url": "/output/header.png"},
                    {"bbox": value_bbox, "final_text": "11/11/2019", "url": "/output/value.png"},
                ],
            }],
        },
    })

    duration = next(field for field in payload["fields"] if field["key"] == "thoi_han")
    assert duration["bbox"] == value_bbox
    assert duration["crop_url"] == "/output/value.png"
    assert duration["source_text"] == "11/11/2019"


def test_review_projection_does_not_attach_unrelated_one_character_crop():
    date_bbox = [[505, 992], [903, 982], [904, 1010], [505, 1019]]
    # Chạm mép với box ngày cấp, nhưng thực tế là crop phần ký tên bên dưới.
    unrelated_bbox = [[482, 1024], [974, 1011], [975, 1037], [482, 1050]]
    payload = build_document_review({
        "id": "doc_4",
        "file_name": "certificate.pdf",
        "structured_data": {
            "cap_gcn": {"ngay_cap": "09/12/2013"},
            "pages": [{
                "page_index": 2,
                "preview_url": "/output/doc_4/page_3/preview_p3.png",
                "ocr_results": [{
                    "text": "Cao Lộc, ngày 09 tháng 12 năm 2013",
                    "confidence": 0.93,
                    "bbox": date_bbox,
                }],
                "crops": [{
                    "bbox": unrelated_bbox,
                    "final_text": "TM. ỦY BAN NHÂN DÂN HUYỆN CAO LỘC",
                    "url": "/output/unrelated.png",
                }],
            }],
        },
    })

    issue_date = next(field for field in payload["fields"] if field["key"] == "ngay_cap")
    assert issue_date["bbox"] == date_bbox
    assert issue_date["crop_url"] == ""


def test_review_projection_omits_coarse_crop_that_does_not_prove_field_value():
    footer_bbox = [[86, 1344], [390, 1341], [390, 1371], [86, 1375]]
    payload = build_document_review({
        "id": "doc_5",
        "file_name": "certificate.pdf",
        "structured_data": {
            "so_vao_so": "CH00043",
            "pages": [{
                "page_index": 2,
                "preview_url": "/output/doc_5/page_3/preview_p3.png",
                "ocr_results": [{
                    "text": "Số vào sổ cấp GCN: CH00043",
                    "confidence": 0.81,
                    "bbox": footer_bbox,
                }],
                # Crop pipeline cũ đọc thành barcode dù bbox OCR phía trên đã
                # đúng. Không được trả nó như bằng chứng của Số vào sổ.
                "crops": [{
                    "bbox": footer_bbox,
                    "final_text": "03610000000000035",
                    "url": "/output/coarse-footer.png",
                }],
            }],
        },
    })

    registry = next(field for field in payload["fields"] if field["key"] == "so_vao_so")
    assert registry["bbox"] == footer_bbox
    assert registry["crop_url"] == ""
