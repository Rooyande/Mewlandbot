import asyncio

from sqlalchemy import text

from app.infra.db.session import engine


async def migrate() -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name='users'
                          AND column_name='last_claim_at'
                    ) THEN
                        ALTER TABLE users ADD COLUMN last_claim_at TIMESTAMPTZ;
                    END IF;
                END$$;
                """
            )
        )

    print("Migration OK: users.last_claim_at ensured.")


if __name__ == "__main__":
    asyncio.run(migrate())
