from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from core.dependencies import get_current_user
from core.whisper import transcribe_audio
from models.user import User

router = APIRouter()

ALLOWED_EXTENSIONS = {
    "webm", "mp4", "wav", "ogg", "mp3", "m4a"
}


@router.post("/")
async def transcribe(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    Transcribe an audio file to text.
    Accepts webm, mp4, wav, ogg, mp3, m4a.
    Returns { "text": "transcribed text here" }
    """
    # Get file extension
    filename = file.filename or "audio.webm"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "webm"

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format: {ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    audio_bytes = await file.read()

    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="Audio file is empty")

    if len(audio_bytes) > 25 * 1024 * 1024:  # 25MB limit
        raise HTTPException(status_code=400, detail="Audio file too large. Maximum size is 25MB")

    text = transcribe_audio(audio_bytes, file_extension=ext)

    print(f"[transcribe] user={current_user.username} ext={ext} size={len(audio_bytes)} result_len={len(text)}")

    return {"text": text}