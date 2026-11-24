"""Supabase Storage operations for invoice intake.

Uses the service-role key (server-side only). The anon key is never used
for privileged backend storage operations.
"""

from app.config import settings
from supabase import create_client, Client


class StorageError(Exception):
    pass


def _client() -> Client:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise StorageError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured "
            "for backend storage operations."
        )
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def upload_pdf(bucket: str, storage_path: str, data: bytes, content_type: str = "application/pdf") -> str:
    """Upload a PDF to Supabase Storage and return the storage path.

    Raises StorageError if the bucket is not configured or the upload fails.
    """
    client = _client()
    try:
        result = client.storage.from_(bucket).upload(
            storage_path,
            data,
            {"content-type": content_type, "upsert": "false"},
        )
    except Exception as exc:
        raise StorageError(f"Supabase Storage upload failed: {exc}") from exc
    # The v2 client returns different shapes depending on version; normalize.
    if isinstance(result, dict) and result.get("error"):
        raise StorageError(f"Supabase Storage upload failed: {result['error']}")
    return storage_path


def storage_public_url(bucket: str, storage_path: str) -> str:
    """Return a public URL for a stored object (bucket must be public)."""
    client = _client()
    try:
        result = client.storage.from_(bucket).get_public_url(storage_path)
    except Exception as exc:
        raise StorageError(f"Could not resolve public URL: {exc}") from exc
    if isinstance(result, dict):
        return result.get("publicURL", "")
    return str(result)