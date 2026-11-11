from typing import ClassVar

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class ClinicSubscriptionStatus(Base):
    """Status catalog of a clinic's subscription, managed by hand (no API for it, research R6).

    The code recognises the system statuses by their fixed identifier, never by their name. 1 to 3
    must not be deleted or renumbered; a status added by hand (4 or more) is treated as current.
    """

    __tablename__ = "clinic_subscription_statuses"

    ACTIVE: ClassVar[int] = 1
    PENDING_RESOLUTION: ClassVar[int] = 2
    CANCELLED: ClassVar[int] = 3

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
