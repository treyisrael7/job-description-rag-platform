"""Deployment-friendly file storage abstraction. S3 in production, local for dev only."""

from abc import ABC, abstractmethod


class StorageBackend(ABC):
    @abstractmethod
    def generate_presigned_put(
        self,
        key: str,
        content_type: str,
        expires_in: int = 3600,
    ) -> tuple[str, str]:
        """Return (upload_url, method)."""
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Verify object exists."""
        ...

    @abstractmethod
    def download(self, key: str) -> bytes:
        """Download object content as bytes."""
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete object if it exists. No-op if not found."""
        ...


class S3Storage(StorageBackend):
    def __init__(self, bucket: str, region: str, access_key: str, secret_key: str):
        import boto3
        from botocore.config import Config
        self._client = boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4"),
        )
        self._bucket = bucket

    def generate_presigned_put(
        self,
        key: str,
        content_type: str,
        expires_in: int = 3600,
    ) -> tuple[str, str]:
        url = self._client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )
        return url, "PUT"

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception:
            return False

    def download(self, key: str) -> bytes:
        resp = self._client.get_object(Bucket=self._bucket, Key=key)
        return resp["Body"].read()

    def delete(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=key)
        except Exception:
            pass


class LocalStorage(StorageBackend):
    """Dev only. Stores in local dir. Upload via API endpoint, not presigned URL."""

    def __init__(self, base_path: str = "uploads"):
        import os
        self._base = base_path
        os.makedirs(base_path, exist_ok=True)

    def generate_presigned_put(
        self,
        key: str,
        content_type: str,
        expires_in: int = 3600,
    ) -> tuple[str, str]:
        # Returns path-relative URL; client PUTs to our /documents/upload-local endpoint
        from urllib.parse import quote
        encoded = quote(key, safe="")
        return f"/documents/upload-local?key={encoded}", "PUT"

    def exists(self, key: str) -> bool:
        from pathlib import Path
        path = Path(self._base) / key
        return path.is_file()

    def get_path(self, key: str) -> str:
        from pathlib import Path
        return str(Path(self._base) / key)

    def download(self, key: str) -> bytes:
        from pathlib import Path
        path = Path(self._base) / key
        return path.read_bytes()

    def delete(self, key: str) -> None:
        from pathlib import Path
        path = Path(self._base) / key
        if path.is_file():
            path.unlink()


def get_storage():
    """Return storage backend: S3 if configured, else local (dev only)."""
    from app.core.config import settings
    if (
        settings.s3_bucket
        and settings.aws_access_key_id
        and settings.aws_secret_access_key
    ):
        return S3Storage(
            bucket=settings.s3_bucket,
            region=settings.aws_region,
            access_key=settings.aws_access_key_id,
            secret_key=settings.aws_secret_access_key,
        )
    return LocalStorage()
