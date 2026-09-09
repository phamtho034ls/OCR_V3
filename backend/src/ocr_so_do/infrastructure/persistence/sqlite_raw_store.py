"""
infrastructure/persistence/sqlite_raw_store.py
Quản lý lưu trữ bền vững dữ liệu thô dạng Markdown vào bảng SQLite cục bộ (Zero-Config).
Tệp cơ sở dữ liệu mặc định: output/raw_ocr.db
"""
import sqlite3
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional


class SqliteRawStore:
    """
    Quản lý bảng raw_ocr_records lưu trữ dữ liệu thô dạng Markdown.
    Thread-safe thông qua kết nối cục bộ theo thread.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self.db_path = Path(db_path).resolve()
        else:
            # Tìm thư mục output
            _curr = Path(__file__).resolve()
            _root = _curr.parents[5] if len(_curr.parents) >= 6 else Path(".")
            out_dir = _root / "output"
            out_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = out_dir / "raw_ocr.db"

        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS raw_ocr_records (
                        id TEXT PRIMARY KEY,
                        file_name TEXT NOT NULL,
                        template TEXT,
                        total_pages INTEGER DEFAULT 1,
                        raw_markdown TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_raw_ocr_created 
                    ON raw_ocr_records(created_at DESC);
                """)
                conn.commit()

    def save_record(
        self,
        doc_id: str,
        file_name: str,
        template: str,
        total_pages: int,
        raw_markdown: str
    ) -> bool:
        """Lưu hoặc cập nhật bản ghi dữ liệu thô Markdown."""
        with self._lock:
            try:
                with self._get_connection() as conn:
                    conn.execute("""
                        INSERT INTO raw_ocr_records (id, file_name, template, total_pages, raw_markdown, created_at)
                        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(id) DO UPDATE SET
                            file_name=excluded.file_name,
                            template=excluded.template,
                            total_pages=excluded.total_pages,
                            raw_markdown=excluded.raw_markdown,
                            created_at=CURRENT_TIMESTAMP;
                    """, (doc_id, file_name, template, total_pages, raw_markdown))
                    conn.commit()
                return True
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Lỗi lưu SQLite raw_ocr_records: {e}")
                return False

    def list_records(self, limit: int = 200, offset: int = 0, search: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lấy danh sách các bản ghi tóm tắt (không kèm nội dung Markdown đầy đủ để tối ưu RAM)."""
        with self._lock:
            with self._get_connection() as conn:
                if search and search.strip():
                    pattern = f"%{search.strip()}%"
                    cursor = conn.execute("""
                        SELECT id, file_name, template, total_pages, created_at,
                               LENGTH(raw_markdown) as content_length
                        FROM raw_ocr_records
                        WHERE file_name LIKE ? OR template LIKE ? OR id LIKE ?
                        ORDER BY created_at DESC
                        LIMIT ? OFFSET ?;
                    """, (pattern, pattern, pattern, limit, offset))
                else:
                    cursor = conn.execute("""
                        SELECT id, file_name, template, total_pages, created_at,
                               LENGTH(raw_markdown) as content_length
                        FROM raw_ocr_records
                        ORDER BY created_at DESC
                        LIMIT ? OFFSET ?;
                    """, (limit, offset))
                rows = cursor.fetchall()
                return [
                    {
                        "id": r["id"],
                        "file_name": r["file_name"],
                        "template": r["template"] or "N/A",
                        "total_pages": r["total_pages"],
                        "created_at": str(r["created_at"]),
                        "content_length": r["content_length"]
                    }
                    for r in rows
                ]

    def get_record(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Lấy chi tiết một bản ghi kèm toàn bộ nội dung Markdown thô."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT id, file_name, template, total_pages, raw_markdown, created_at
                    FROM raw_ocr_records
                    WHERE id = ?;
                """, (doc_id,))
                r = cursor.fetchone()
                if not r:
                    return None
                return {
                    "id": r["id"],
                    "file_name": r["file_name"],
                    "template": r["template"] or "N/A",
                    "total_pages": r["total_pages"],
                    "raw_markdown": r["raw_markdown"],
                    "created_at": str(r["created_at"])
                }

    def delete_record(self, doc_id: str) -> bool:
        """Xóa một bản ghi theo ID."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM raw_ocr_records WHERE id = ?;", (doc_id,))
                conn.commit()
                return True

    def clear_all_records(self) -> int:
        """Xóa toàn bộ các bản ghi trong bảng raw_ocr_records và dọn dẹp dung lượng SQLite."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM raw_ocr_records;")
                row = cursor.fetchone()
                total = row[0] if row else 0
                conn.execute("DELETE FROM raw_ocr_records;")
                conn.commit()
                try:
                    conn.execute("VACUUM;")
                except Exception:
                    pass
                return total

    def count_records(self, search: Optional[str] = None) -> int:
        """Đếm tổng số bản ghi trong bảng raw_ocr_records."""
        with self._lock:
            with self._get_connection() as conn:
                if search and search.strip():
                    pattern = f"%{search.strip()}%"
                    cursor = conn.execute("""
                        SELECT COUNT(*) FROM raw_ocr_records
                        WHERE file_name LIKE ? OR template LIKE ? OR id LIKE ?;
                    """, (pattern, pattern, pattern))
                else:
                    cursor = conn.execute("SELECT COUNT(*) FROM raw_ocr_records;")
                row = cursor.fetchone()
                return row[0] if row else 0


# Singleton instance
_sqlite_store = None


def get_sqlite_raw_store() -> SqliteRawStore:
    global _sqlite_store
    if _sqlite_store is None:
        _sqlite_store = SqliteRawStore()
    return _sqlite_store
