import httpx
from app.core.config import settings


async def upload_to_supabase(
    file_bytes: bytes,
    file_path: str,
    content_type: str = "application/octet-stream",
) -> str:
    """Upload a file to Supabase Storage and return the public URL."""
    url = (
        f"{settings.SUPABASE_URL}/storage/v1/object/"
        f"{settings.SUPABASE_STORAGE_BUCKET}/{file_path}"
    )
    headers = {
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
        "apikey": settings.SUPABASE_SERVICE_KEY,
        "Content-Type": content_type,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, content=file_bytes, headers=headers)

        # 409 means file exists — upsert instead
        if resp.status_code == 409:
            resp = await client.put(url, content=file_bytes, headers=headers)

        if resp.status_code not in (200, 201):
            raise Exception(f"Supabase upload failed: {resp.status_code} {resp.text}")

    public_url = (
        f"{settings.SUPABASE_URL}/storage/v1/object/public/"
        f"{settings.SUPABASE_STORAGE_BUCKET}/{file_path}"
    )
    return public_url