from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from fastapi.security import HTTPBearer
from core.ollama import check_ollama_connection
from core.qdrant import ensure_collection_exists
from core.minio import ensure_bucket_exists
from routers import auth, chat, reports, unfinished, uploads, dashboard, historical, users, notifications, transcribe, vision

security = HTTPBearer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up...")

    # Check Ollama
    ollama_ok = await check_ollama_connection()
    if ollama_ok:
        print("Ollama connection OK")
    else:
        print("WARNING: Cannot reach Ollama. Make sure it is running.")

    # Check Qdrant
    try:
        ensure_collection_exists()
        print("Qdrant connection OK")
    except Exception as e:
        print(f"WARNING: Cannot reach Qdrant: {e}")

    # Check MinIO
    try:
        ensure_bucket_exists()
        print("MinIO connection OK")
    except Exception as e:
        print(f"WARNING: Cannot reach MinIO: {e}")

    yield
    print("Shutting down...")

app = FastAPI(title="Safety Chatbot API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(reports.router, prefix="/reports", tags=["reports"])
app.include_router(unfinished.router, prefix="/unfinished", tags=["unfinished"])
app.include_router(uploads.router, prefix="/uploads", tags=["uploads"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(historical.router, prefix="/historical", tags=["historical"])
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
app.include_router(transcribe.router, prefix="/transcribe", tags=["transcribe"])
app.include_router(vision.router, prefix="/vision", tags=["vision"])

@app.get("/")
async def root():
    return {"message": "Safety Chatbot API is running"}