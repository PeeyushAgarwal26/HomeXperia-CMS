import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.customer_auth.models import CustomerRefreshToken


class CustomerRefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        customer_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
        session_started_at: datetime,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> CustomerRefreshToken:
        token = CustomerRefreshToken(
            customer_id=customer_id,
            token_hash=token_hash,
            expires_at=expires_at,
            session_started_at=session_started_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.session.add(token)
        await self.session.flush()
        return token

    async def get_valid_by_hash(self, token_hash: str) -> CustomerRefreshToken | None:
        stmt = select(CustomerRefreshToken).where(
            CustomerRefreshToken.token_hash == token_hash,
            CustomerRefreshToken.revoked_at.is_(None),
            CustomerRefreshToken.expires_at > datetime.now(timezone.utc),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_unexpired_by_hash(self, token_hash: str) -> CustomerRefreshToken | None:
        """Like get_valid_by_hash but also returns already-revoked rows (still
        unexpired) — used by the refresh-reuse grace period, which needs to see
        *when* a token was revoked, not just whether it's still usable."""
        stmt = select(CustomerRefreshToken).where(
            CustomerRefreshToken.token_hash == token_hash,
            CustomerRefreshToken.expires_at > datetime.now(timezone.utc),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke(self, token: CustomerRefreshToken) -> None:
        token.revoked_at = datetime.now(timezone.utc)
        await self.session.flush()

    async def revoke_all_for_customer(self, customer_id: uuid.UUID) -> None:
        stmt = (
            update(CustomerRefreshToken)
            .where(
                CustomerRefreshToken.customer_id == customer_id,
                CustomerRefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await self.session.execute(stmt)
