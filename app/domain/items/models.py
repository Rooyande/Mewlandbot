from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.users.models import Base


class ItemEffectType(StrEnum):
    # تولید را ضرب می‌کند (مثلاً 1.2 یعنی 20% بیشتر)
    MEOW_MULTIPLIER = "meow_multiplier"

    # تولید را به صورت عددی زیاد می‌کند (مثلاً +5 در هر tick)
    FLAT_BONUS = "flat_bonus"

    # فاصله تولید را کم می‌کند (مثلاً -60 یعنی 60 ثانیه کمتر)
    INTERVAL_REDUCE_SEC = "interval_reduce_sec"


class Item(Base):
    """
    آیتم‌های Shop (کاتالوگ)
    """
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    name: Mapped[str] = mapped_column(String(64), nullable=False)

    price_meow: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

    effect_type: Mapped[str] = mapped_column(String(32), nullable=False, default=ItemEffectType.FLAT_BONUS.value)

    # مقدار تاثیر: مثلا 1.2 یا 5 یا 60
    effect_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # اگر خواستی بعداً عکس اضافه کنی:
    image_file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    owners: Mapped[list["UserItem"]] = relationship(back_populates="item")


class UserItem(Base):
    """
    آیتم‌های خریداری‌شده توسط کاربر
    """
    __tablename__ = "user_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)

    # تعداد (اگر آیتم قابل stack بود)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    item: Mapped["Item"] = relationship(back_populates="owners")
