"""Module removed: SQLite storage is no longer used. All data is stored in PostgreSQL."""
raise ImportError(
    "sqlite_raw_store has been removed. "
    "The system now requires PostgreSQL. "
    "Ensure OCR_POSTGRES_ENABLED=true and PostgreSQL is running."
)
