import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, declarative_base

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE_PATH = (BACKEND_DIR / "pharmacy.db").resolve()
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"

# Prefer an explicit DATABASE_URL (Postgres in prod, SQLite for quick local dev).
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def _is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite:")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite_url(DATABASE_URL) else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def ensure_sqlite_schema(db_engine: Engine) -> None:
    if db_engine.dialect.name != "sqlite":
        return

    with db_engine.begin() as conn:
        tables = {
            row[0]
            for row in conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        def existing_columns(table: str) -> set[str]:
            return {
                row[1]
                for row in conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
            }

        def add_column_if_missing(table: str, column_name: str, column_sql: str) -> None:
            cols = existing_columns(table)
            if column_name in cols:
                return
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column_sql}")

        if "users" in tables:
            add_column_if_missing("users", "username", "username VARCHAR")
            add_column_if_missing("users", "password_hash", "password_hash VARCHAR")
            add_column_if_missing("users", "contact_info", "contact_info TEXT")
            add_column_if_missing("users", "full_name", "full_name VARCHAR")
            add_column_if_missing("users", "is_admin", "is_admin INTEGER NOT NULL DEFAULT 0")
            add_column_if_missing("users", "pharmacy_id", "pharmacy_id INTEGER")

            user_cols = existing_columns("users")
            if "name" in user_cols:
                conn.exec_driver_sql(
                    "UPDATE users SET full_name = name WHERE full_name IS NULL AND name IS NOT NULL"
                )
            conn.exec_driver_sql(
                "UPDATE users SET role = 'OWNER' WHERE role IS NULL"
            )

        if "pharmacies" in tables:
            add_column_if_missing("pharmacies", "status", "status VARCHAR NOT NULL DEFAULT 'APPROVED'")
            add_column_if_missing("pharmacies", "branding_details", "branding_details TEXT")
            add_column_if_missing("pharmacies", "operating_hours", "operating_hours VARCHAR")
            add_column_if_missing("pharmacies", "support_cod", "support_cod INTEGER NOT NULL DEFAULT 1")
            add_column_if_missing("pharmacies", "domain", "domain VARCHAR")
            add_column_if_missing("pharmacies", "is_active", "is_active INTEGER NOT NULL DEFAULT 1")

            conn.exec_driver_sql(
                "UPDATE pharmacies SET status = 'APPROVED' WHERE status IS NULL"
            )
            conn.exec_driver_sql(
                "UPDATE pharmacies SET is_active = 1 WHERE is_active IS NULL"
            )

        if "medicines" in tables:
            add_column_if_missing("medicines", "category", "category VARCHAR")
            add_column_if_missing("medicines", "stock_level", "stock_level INTEGER NOT NULL DEFAULT 0")
            add_column_if_missing(
                "medicines",
                "prescription_required",
                "prescription_required INTEGER NOT NULL DEFAULT 0",
            )
            add_column_if_missing("medicines", "dosage", "dosage VARCHAR")
            add_column_if_missing("medicines", "side_effects", "side_effects TEXT")

            med_cols = existing_columns("medicines")
            if "quantity" in med_cols:
                conn.exec_driver_sql(
                    "UPDATE medicines SET stock_level = quantity WHERE stock_level IS NULL AND quantity IS NOT NULL"
                )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
