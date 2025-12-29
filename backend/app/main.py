import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect

from app.db import Base, engine, ensure_sqlite_schema, SessionLocal
from app import models
from app.ai.provider_factory import get_ai_provider
from app.auth.routes import router as auth_router
from app.auth.bootstrap import ensure_admin_user
from app.routes.pharmacy_routes import router as pharmacy_router
from app.routes.medicine_routes import router as medicine_router
from app.routes.product_routes import router as product_router
from app.routes.order_routes import router as order_router
from app.routes.prescription_routes import router as prescription_router
from app.routes.appointment_routes import router as appointment_router
from app.routes.ai_routes import router as ai_router
from app.routes.cart_routes import router as cart_router
from app.appointments.reminders import process_due_reminders, process_no_shows

def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]

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
        "products",
        "orders",
        "order_items",
        "prescriptions",
        "prescription_medicines",
        "appointments",
        "appointment_settings",
        "appointment_audits",
        "appointment_reminders",
        "ai_interactions",
        "ai_logs",
        "documents",
        "document_chunks",
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
    scheduler = None
    if _env_flag("ENABLE_APPOINTMENT_REMINDERS", default=False):
        from apscheduler.schedulers.background import BackgroundScheduler

        poll_seconds = int(os.getenv("REMINDER_POLL_SECONDS", "300"))

        def _run_due_reminders() -> None:
            db = SessionLocal()
            try:
                process_due_reminders(db)
                process_no_shows(db)
            finally:
                db.close()

        scheduler = BackgroundScheduler()
        scheduler.add_job(_run_due_reminders, "interval", seconds=poll_seconds, max_instances=1)
        scheduler.start()
    try:
        yield
    finally:
        if scheduler:
            scheduler.shutdown(wait=False)
        # Avoid creating a provider just to close it.
        if get_ai_provider.cache_info().currsize > 0:
            provider = get_ai_provider()
            close = getattr(provider, "aclose", None)
            if callable(close):
                await close()

app = FastAPI(title="AI-Powered Pharmacy Assistant Backend", lifespan=lifespan)

cors_origins = _split_csv(os.getenv("CORS_ORIGINS")) or [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
cors_origin_regex = os.getenv("CORS_ALLOW_ORIGIN_REGEX") or r"^https?://([a-z0-9-]+\.)*localhost(:\d+)?$"
# `.env` files often double-escape backslashes (e.g. `\\d` instead of `\d`); normalize so CORS preflight works.
cors_origin_regex = cors_origin_regex.replace("\\\\", "\\")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth", tags=["Auth"])
app.include_router(pharmacy_router)
app.include_router(medicine_router)
app.include_router(product_router)
app.include_router(order_router)
app.include_router(prescription_router)
app.include_router(appointment_router)
app.include_router(ai_router)
app.include_router(cart_router)


@app.get("/")
def read_root():
    return {"message": "Backend is running"}
