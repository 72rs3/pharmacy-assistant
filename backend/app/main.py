from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import Base, engine
from app import models
from app.auth.routes import router as auth_router

# Create tables
Base.metadata.create_all(bind=engine)

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


@app.get("/")
def read_root():
    return {"message": "Backend is running"}
