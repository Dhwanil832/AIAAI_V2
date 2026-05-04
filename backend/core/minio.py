from minio import Minio
from minio.error import S3Error
from config import settings
import io
import datetime

client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=False  # local on-premise, no TLS
)


def get_minio_client() -> Minio:
    return client


def ensure_bucket_exists():
    """
    Create the MinIO bucket if it doesn't exist.
    Called on startup.
    """
    try:
        if not client.bucket_exists(settings.MINIO_BUCKET):
            client.make_bucket(settings.MINIO_BUCKET)
            print(f"[minio] created bucket: {settings.MINIO_BUCKET}")
        else:
            print(f"[minio] bucket exists: {settings.MINIO_BUCKET}")
    except S3Error as e:
        print(f"[minio] error checking bucket: {e}")


def upload_image(file_bytes: bytes, filename: str, folder: str) -> str:
    """
    Upload an image to MinIO under vision/ prefix.

    folder   — logical grouping e.g. session_id or report_id
    filename — original filename or generated name with extension

    Returns the stored object path (not a URL) — used to retrieve later.
    e.g. "vision/report_42/scene_20260416_143022.jpg"
    """
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    # Sanitize filename — keep extension, replace spaces
    safe_name = filename.replace(" ", "_")
    object_path = f"vision/{folder}/{timestamp}_{safe_name}"

    file_stream = io.BytesIO(file_bytes)
    file_size = len(file_bytes)

    # Determine content type from extension
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    content_type_map = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
        "heic": "image/heic",
    }
    content_type = content_type_map.get(ext, "image/jpeg")

    try:
        client.put_object(
            settings.MINIO_BUCKET,
            object_path,
            file_stream,
            file_size,
            content_type=content_type
        )
        print(f"[minio] uploaded image: {object_path}")
        return object_path
    except S3Error as e:
        print(f"[minio] image upload failed: {e}")
        raise


def get_image_presigned_url(object_path: str, expires_hours: int = 2) -> str:
    """
    Generate a temporary presigned URL for an image stored in MinIO.

    Used by the frontend to render image thumbnails and full-size views
    without exposing MinIO credentials.

    expires_hours — how long the URL stays valid (default 2 hours)
    """
    try:
        url = client.presigned_get_object(
            settings.MINIO_BUCKET,
            object_path,
            expires=datetime.timedelta(hours=expires_hours)
        )
        return url
    except S3Error as e:
        print(f"[minio] presigned URL failed for {object_path}: {e}")
        raise