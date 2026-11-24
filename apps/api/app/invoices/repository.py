"""Database operations for invoice intake drafts.

Uses the service-role key (server-side only). RLS is enabled on all tables
and is NOT disabled. No permissive RLS policies are created here.
"""

from app.config import settings
from supabase import create_client, Client


class RepositoryError(Exception):
    pass


def _client() -> Client:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RepositoryError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be configured "
            "for backend database operations."
        )
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def find_draft_by_sha256(client: Client, sha256: str) -> dict | None:
    """Return an existing intake draft matching the SHA-256, if any."""
    result = client.table("invoice_intake_drafts").select("*").eq("sha256", sha256).execute()
    data = result.data or []
    if not data:
        return None
    return data[0]


def insert_intake_draft(client: Client, draft: dict) -> dict:
    """Insert a new intake draft and return the inserted row."""
    result = client.table("invoice_intake_drafts").insert(draft).execute()
    if getattr(result, "error", None):
        raise RepositoryError(f"Insert failed: {result.error}")
    data = result.data or []
    if not data:
        raise RepositoryError("Insert returned no data")
    return data[0]


def update_draft_status(client: Client, draft_id: str, status: str) -> dict:
    """Update the processing_status of an intake draft."""
    result = (
        client.table("invoice_intake_drafts")
        .update({"processing_status": status, "updated_at": "now()"})
        .eq("id", draft_id)
        .execute()
    )
    if getattr(result, "error", None):
        raise RepositoryError(f"Update failed: {result.error}")
    data = result.data or []
    if not data:
        raise RepositoryError("Update returned no data")
    return data[0]