"""
tests/test_postgres_fallback.py
Kiểm tra rằng PostgresStore có thể bị tắt chủ động và báo lỗi rõ ràng.
"""
from ocr_so_do.infrastructure.persistence.postgres_store import PostgresStore


def test_postgres_disabled_reports_clearly():
    """Khi OCR_POSTGRES_ENABLED=false, store báo lỗi rõ ràng thay vì fallback sang SQLite."""
    store = PostgresStore(enabled=False)

    assert store.is_connected() is False
    assert store.unavailable_reason == "PostgreSQL đã được tắt bằng OCR_POSTGRES_ENABLED."
    assert store.save_batch("batch-test", "source", "C:/source", "C:/output") is False
    assert store.save_record(doc_id="test", file_name="test.pdf", raw_markdown="# test") is False
    records, count = store.list_records()
    assert records == []
    assert count == 0


def test_postgres_disabled_get_filter_options_returns_empty():
    """Filter options trả về rỗng khi PG tắt."""
    store = PostgresStore(enabled=False)
    options = store.get_filter_options()
    assert options == {"folders": [], "sources": [], "batches": []}


def test_postgres_disabled_get_stats_reports_disconnected():
    """Stats báo disconnected khi PG tắt."""
    store = PostgresStore(enabled=False)
    stats = store.get_stats()
    assert stats.get("connected") is False
