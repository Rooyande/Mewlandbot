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


class CatRarity(StrEnum):
    COMMON = "common"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"
    MYTHIC = "mythic"


class Cat(Base):
    """
    تعریف گربه‌ها (کاتالوگ)
    هر گربه یک template است: اسم، rarity، قیمت، نرخ تولید، تصویر پایه و ...
    """
    __tablename__ = "cats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # نمایش
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    rarity: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CatRarity.COMMON.value
    )

    # قیمت خرید با meow points
    price_meow: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

    # تولید آفلاین پایه (مثلاً هر X دقیقه Y امتیاز)
    base_meow_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    base_meow_interval_sec: Mapped[int] = mapped_column(
        Integer, nullable=False, default=600
    )  # 10 min

    # مسیر فایل تصویر پایه گربه (برای رندر لایه‌ای)
    # مثال: assets/cats/siamese.png
    base_image_path: Mapped[str] = mapped_column(String(256), nullable=False)

    # آیا فعال است؟
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    owners: Mapped[list["UserCat"]] = relationship(back_populates="cat")


class UserCat(Base):
    """
    مالکیت گربه‌ها توسط کاربر
    هر رکورد یعنی کاربر این گربه را دارد + سطح + اسم اختصاصی + وضعیت
    """
    __tablename__ = "user_cats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    user_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    cat_id: Mapped[int] = mapped_column(ForeignKey("cats.id"), nullable=False)

    # اسم دلخواه کاربر برای گربه
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # سطح
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # وضعیت نیازها (برای آینده: hunger/sad)
    happiness: Mapped[int] = mapped_column(Integer, nullable=False, default=100)  # 0..100
    hunger: Mapped[int] = mapped_column(Integer, nullable=False, default=0)      # 0..100

    last_fed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_played_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # اگر گربه مرده یا ترک کرده:
    is_alive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_left: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    cat: Mapped["Cat"] = relationship(back_populates="owners")
