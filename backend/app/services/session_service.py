import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import AppSession
from app.models.utils import NotFound
from app.schemas.session import SessionCreate


class SessionService:
    async def create(
        self, db: AsyncSession, data: SessionCreate | None = None
    ) -> AppSession:
        payload = data or SessionCreate()
        now = datetime.now(timezone.utc)
        row = AppSession(
            session_id=secrets.token_urlsafe(32),
            meta=payload.metadata,
            created_at=now,
            last_accessed=now,
            expires_at=now + timedelta(hours=payload.ttl_hours),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    async def get(self, db: AsyncSession, session_pk: uuid.UUID) -> AppSession:
        row = await db.get(AppSession, session_pk)
        if not row:
            raise NotFound(f"Session {session_pk} not found")
        return row

    async def touch(self, db: AsyncSession, session_pk: uuid.UUID) -> AppSession:
        row = await self.get(db, session_pk)
        row.last_accessed = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(row)
        return row

    async def ensure(self, db: AsyncSession, session_pk: uuid.UUID) -> AppSession:
        return await self.get(db, session_pk)


session_service = SessionService()
