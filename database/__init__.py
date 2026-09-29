"""Thread-safe local SQLite persistence shared by desktop and mobile state."""
from database.sqlite import SQLiteStore

__all__ = ["SQLiteStore"]
