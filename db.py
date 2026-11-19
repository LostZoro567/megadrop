"""Tiny async Supabase (PostgREST) client. Pure httpx = fast, no heavy SDK."""
import logging
from datetime import datetime, timezone

import httpx

from config import SUPABASE_KEY, SUPABASE_URL

log = logging.getLogger("db")


class DB:
    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url=f"{SUPABASE_URL}/rest/v1",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {SUPABASE_KEY}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(15.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
        )

    async def close(self):
        await self.client.aclose()

    async def upsert_user(self, user) -> None:
        """Save/refresh a user. Never raises (runs in background)."""
        try:
            r = await self.client.post(
                "/users?on_conflict=user_id",
                json={
                    "user_id": user.id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "language_code": user.language_code,
                    "is_blocked": False,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            )
            r.raise_for_status()
        except Exception as e:
            log.error("upsert_user failed for %s: %s", user.id, e)

    async def set_blocked(self, ids: list[int], blocked: bool) -> None:
        try:
            for i in range(0, len(ids), 200):
                chunk = ids[i : i + 200]
                r = await self.client.patch(
                    f"/users?user_id=in.({','.join(map(str, chunk))})",
                    json={"is_blocked": blocked},
                    headers={"Prefer": "return=minimal"},
                )
                r.raise_for_status()
        except Exception as e:
            log.error("set_blocked failed: %s", e)

    async def count_users(self, blocked: bool | None = None) -> int:
        params = {"select": "user_id"}
        if blocked is not None:
            params["is_blocked"] = f"eq.{str(blocked).lower()}"
        r = await self.client.get(
            "/users", params=params, headers={"Prefer": "count=exact", "Range": "0-0"}
        )
        r.raise_for_status()
        return int(r.headers["content-range"].split("/")[1])

    async def iter_active_pages(self, page_size: int = 1000):
        """Yield lists of active user IDs using keyset pagination (fast at any size)."""
        last = 0
        while True:
            r = await self.client.get(
                "/users",
                params={
                    "select": "user_id",
                    "is_blocked": "eq.false",
                    "user_id": f"gt.{last}",
                    "order": "user_id.asc",
                    "limit": page_size,
                },
            )
            r.raise_for_status()
            rows = r.json()
            if not rows:
                return
            ids = [row["user_id"] for row in rows]
            yield ids
            last = ids[-1]
