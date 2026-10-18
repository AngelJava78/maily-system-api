from typing import ClassVar

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class SubscriptionStatus(Base):
    """Status catalog of the subscriptions, managed by hand (there is no API for it, FR-022).

    The code recognises the system statuses by their fixed identifier, never by their name: the
    name is catalog data and can be edited. Statuses 1 to 4 must not be deleted or renumbered; a
    status added by hand (identifier 5 or more) is treated as a current subscription.
    """

    __tablename__ = "subscription_statuses"

    ACTIVE: ClassVar[int] = 1
    INACTIVE: ClassVar[int] = 2
    BLOCKED: ClassVar[int] = 3
    DELETED: ClassVar[int] = 4

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
