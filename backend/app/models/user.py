from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    __table_args__ = (
        CheckConstraint(
            "CHAR_LENGTH(username) >= 3",
            name="ck_users_username_min_length",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    username: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True
    )
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False
    )

    display_name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    bio: Mapped[str | None] = mapped_column(
        String(300), nullable=True
    )
    avatar_key: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("1")
    )
    email_verified_at: Mapped[DateTime | None] = mapped_column(
        DateTime, nullable=True
    )

    created_at: Mapped[DateTime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
