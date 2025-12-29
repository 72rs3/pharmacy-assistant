import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect

from app.db import Base, engine, ensure_sqlite_schema
from app import models
from app.auth.routes import router as auth_router
from app.auth.bootstrap import ensure_admin_user
from app.routes.pharmacy_routes import router as pharmacy_router
from app.routes.medicine_routes import router as medicine_router

def _env_flag(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _required_tables() -> set[str]:
    return {
        "pharmacies",
        "users",
        "medicines",
        "orders",
        "order_items",
        "prescriptions",
        "prescription_medicines",
        "appointments",
        "ai_interactions",
        "ai_logs",
    }


def _assert_schema_ready() -> None:
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    missing = sorted(_required_tables() - existing)
    if not missing:
        return
    raise RuntimeError(
        "Database schema is not initialized. "
        "Run `alembic upgrade head` (from the `backend/` folder), "
        f"or set DB_AUTO_CREATE=1 for a quick dev bootstrap. Missing tables: {', '.join(missing)}"
    )


def init_database() -> None:
    auto_create = _env_flag("DB_AUTO_CREATE", default=(engine.dialect.name == "sqlite"))
    if auto_create:
        Base.metadata.create_all(bind=engine)
        ensure_sqlite_schema(engine)
    else:
        _assert_schema_ready()

    ensure_admin_user()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    yield

app = FastAPI(title="AI-Powered Pharmacy Assistant Backend", lifespan=lifespan)

# Allow local frontend to access the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(pharmacy_router)
app.include_router(medicine_router)


@app.get("/")
def read_root():
    return {"message": "Backend is running"}
