import uuid
from datetime import datetime

from sqlalchemy import String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    clerk_id: Mapped[str | None] = mapped_column(nullable=True, unique=True)
    email: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"),
        nullable=False,
    )
    # Billing / abuse control: limits enforced in app.services.evaluation_usage
    plan: Mapped[str] = mapped_column(String(32), default="free", server_default="free")
    evaluations_this_month: Mapped[int] = mapped_column(default=0, server_default="0")
    evaluation_usage_month: Mapped[str | None] = mapped_column(String(7), nullable=True)
