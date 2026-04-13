from minio import Minio
from minio.error import S3Error
from config import settings

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