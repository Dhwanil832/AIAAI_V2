"""
whisper.py
──────────
On-premise speech-to-text using faster-whisper.
Model is loaded once on first use and reused across requests.

Uses the "base" model by default — small enough to run on CPU,
accurate enough for workplace incident descriptions in English.
Swap to "small" or "medium" if accuracy needs improvement.
"""

from faster_whisper import WhisperModel
import tempfile
import os

# Model is loaded lazily on first transcription request
_model = None
MODEL_SIZE = "base"


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        print(f"[whisper] loading model: {MODEL_SIZE}")
        _model = WhisperModel(
            MODEL_SIZE,
            device="cpu",
            compute_type="int8"   # int8 is fastest on CPU with minimal accuracy loss
        )
        print(f"[whisper] model loaded")
    return _model


def transcribe_audio(audio_bytes: bytes, file_extension: str = "webm") -> str:
    """
    Transcribe raw audio bytes to text.

    Writes audio to a temp file, runs faster-whisper, returns the full
    transcription as a single string. Temp file is deleted after transcription.

    Supports any format faster-whisper/ffmpeg can read:
    webm, mp4, wav, ogg, mp3, m4a.

    Returns empty string if transcription fails or produces no speech.
    """
    model = _get_model()

    # Write to temp file — faster-whisper needs a file path, not bytes
    suffix = f".{file_extension.lstrip('.')}"
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        segments, info = model.transcribe(
            tmp_path,
            language="en",          # Force English — steel plant context
            beam_size=5,
            vad_filter=True,        # Skip silent sections
            vad_parameters={
                "min_silence_duration_ms": 500
            }
        )

        # Collect all segments into one string
        text = " ".join(seg.text.strip() for seg in segments).strip()
        print(f"[whisper] transcribed {len(text)} chars | lang={info.language} prob={info.language_probability:.2f}")
        return text

    except Exception as e:
        print(f"[whisper] transcription failed: {e}")
        return ""

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)