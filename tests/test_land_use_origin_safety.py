from extraction.gcn_merger import GCNMerger


def test_document_level_origin_is_not_copied_to_each_multi_parcel_row():
    page = {
        "_page_num": 3,
        "thua_dat": {
            "nguon_goc": "Công nhận QSDĐ như giao đất không thu tiền sử dụng đất",
            "danh_sach_thua": [
                {"so_thua": "1", "to_ban_do": "2", "dien_tich": 10},
                {"so_thua": "2", "to_ban_do": "2", "dien_tich": 20},
            ],
        },
        "ocr_results": [
            {"text": "Tổng số thửa đất: 2 thửa"},
            {"text": "Diện tích"},
            {"text": "Nguồn gốc"},
        ],
    }

    merged = GCNMerger.merge([page], bo_gcn_id="origin-safety")
    parcels = merged["thua_dat"]["danh_sach_thua"]

    assert [parcel["nguon_goc"] for parcel in parcels] == ["", ""]
    assert "nguon_goc" in merged["can_review"]
