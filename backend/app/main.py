from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import Base, engine, ensure_sqlite_schema
from app import models
from app.auth.routes import router as auth_router
from app.routes.pharmacy_routes import router as pharmacy_router
from app.routes.medicine_routes import router as medicine_router

# Create tables
Base.metadata.create_all(bind=engine)
ensure_sqlite_schema(engine)

app = FastAPI(title="AI-Powered Pharmacy Assistant Backend")

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
