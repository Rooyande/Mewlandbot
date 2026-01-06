import asyncio

from sqlalchemy import text

from app.infra.db.session import engine


async def migrate() -> None:
    async with engine.begin() as conn:
        # اگر ستون وجود نداشت اضافه کن
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name='cats'
                          AND column_name='image_file_id'
                    ) THEN
                        ALTER TABLE cats ADD COLUMN image_file_id VARCHAR(256);
                    END IF;
                END$$;
                """
            )
        )

    print("Migration OK: cats.image_file_id ensured.")


if __name__ == "__main__":
    asyncio.run(migrate())
