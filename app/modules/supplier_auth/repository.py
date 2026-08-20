import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.supplier_auth.models import SupplierRefreshToken


class SupplierRefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        supplier_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        session_started_at: datetime,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> SupplierRefreshToken:
        token = SupplierRefreshToken(
            supplier_id=supplier_id,
            token_hash=token_hash,
            expires_at=expires_at,
            session_started_at=session_started_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.session.add(token)
        await self.session.flush()
        return token

    async def get_valid_by_hash(self, token_hash: str) -> SupplierRefreshToken | None:
        stmt = select(SupplierRefreshToken).where(
            SupplierRefreshToken.token_hash == token_hash,
            SupplierRefreshToken.revoked_at.is_(None),
            SupplierRefreshToken.expires_at > datetime.now(timezone.utc),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_unexpired_by_hash(self, token_hash: str) -> SupplierRefreshToken | None:
        """Like get_valid_by_hash but also returns already-revoked rows (still
        unexpired) — used by the refresh-reuse grace period, which needs to see
        *when* a token was revoked, not just whether it's still usable."""
        stmt = select(SupplierRefreshToken).where(
            SupplierRefreshToken.token_hash == token_hash,
            SupplierRefreshToken.expires_at > datetime.now(timezone.utc),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke(self, token: SupplierRefreshToken) -> None:
        token.revoked_at = datetime.now(timezone.utc)
        await self.session.flush()

    async def revoke_all_for_supplier(self, supplier_id: uuid.UUID) -> None:
        stmt = (
            update(SupplierRefreshToken)
            .where(
                SupplierRefreshToken.supplier_id == supplier_id,
                SupplierRefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await self.session.execute(stmt)
