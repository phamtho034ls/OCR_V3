import io
import json
import zipfile
from unittest.mock import MagicMock, patch

from ocr_so_do.interfaces.api.security import Permission, Principal


def _admin_principal():
    return Principal(
        subject="admin",
        username="admin",
        display_name="Admin",
        email=None,
        roles=frozenset({"ocr-admin"}),
        permissions=Permission.ALL,
    )
import pytest


def test_export_pg_raw_markdown_zip():
    from ocr_so_do.interfaces.api.routers import pg_storage
    from ocr_so_do.interfaces.api.routers.pg_storage import export_pg_raw_markdown

    mock_records = [
        {
            "id": "doc-uuid-1",
            "file_name": "GCN_NguyenVanA.pdf",
            "template": "mau_B",
            "so_phat_hanh": "BR 123456",
            "ten_chu": "Nguyễn Văn A",
            "source_path": "D:/data/GCN_NguyenVanA.pdf",
            "raw_markdown": "# GCN Nguyen Van A\n\nThửa đất số 10\nTờ bản đồ số 5\n",
        },
        {
            "id": "doc-uuid-2",
            "file_name": "GCN_TranThiB.pdf",
            "template": "mau_B",
            "so_phat_hanh": "BR 654321",
            "ten_chu": "Trần Thị B",
            "source_path": "D:/data/GCN_TranThiB.pdf",
            "raw_markdown": "# GCN Tran Thi B\n\nThửa đất số 22\nTờ bản đồ số 8\n",
        }
    ]

    mock_store = MagicMock()
    mock_store.get_raw_records_dump.return_value = mock_records

    with patch.object(pg_storage, "get_postgres_store", return_value=mock_store):
        import asyncio
        resp = asyncio.run(
            export_pg_raw_markdown(
                folder_result="Batch_01",
                ids="doc-uuid-1,doc-uuid-2",
                principal=_admin_principal(),
            )
        )

    assert resp.status_code == 200
    assert resp.media_type == "application/zip"
    assert "attachment; filename=\"GoiMarkdown_DuLieuTho_Batch_01_" in resp.headers["Content-Disposition"]

    # Verify ZIP contents
    zip_bytes = io.BytesIO(resp.body)
    with zipfile.ZipFile(zip_bytes, "r") as zf:
        file_list = zf.namelist()
        assert len(file_list) == 3
        assert "00_TONG_HOP_TOAN_BO.md" in file_list
        assert any("GCN_NguyenVanA" in f for f in file_list)
        assert any("GCN_TranThiB" in f for f in file_list)

        # Check content of one file
        md_content = zf.read([f for f in file_list if "GCN_NguyenVanA" in f][0]).decode("utf-8")
        assert "Thửa đất số 10" in md_content

        # Check combined file
        combined_content = zf.read("00_TONG_HOP_TOAN_BO.md").decode("utf-8")
        assert "Hồ sơ 1: GCN_NguyenVanA.pdf" in combined_content
        assert "Hồ sơ 2: GCN_TranThiB.pdf" in combined_content


def test_export_pg_raw_db_json():
    from ocr_so_do.interfaces.api.routers import pg_storage
    from ocr_so_do.interfaces.api.routers.pg_storage import export_pg_raw_db

    mock_records = [
        {
            "id": "doc-uuid-1",
            "file_name": "GCN_Test.pdf",
            "template": "mau_B",
            "raw_markdown": "# Markdown",
            "structured_data": {"so_phat_hanh": "BR 111111"}
        }
    ]

    mock_store = MagicMock()
    mock_store.get_raw_records_dump.return_value = mock_records

    with patch.object(pg_storage, "get_postgres_store", return_value=mock_store):
        import asyncio
        resp = asyncio.run(export_pg_raw_db(folder_result="TestFolder", principal=_admin_principal()))

    assert resp.status_code == 200
    assert resp.media_type == "application/json; charset=utf-8"
    assert "CSDL_DuLieuTho_TestFolder_" in resp.headers["Content-Disposition"]

    data = json.loads(resp.body.decode("utf-8"))
    assert data["total_records"] == 1
    assert data["records"][0]["id"] == "doc-uuid-1"
