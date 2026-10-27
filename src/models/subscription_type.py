from typing import ClassVar

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class SubscriptionType(Base):
    """Catalog of who a subscription is for, managed by hand (there is no API for it, FR-001).

    The code recognises the two types with business meaning by their fixed identifier, never by
    their name: the name is catalog data and can be edited. A type added by hand (identifier 3 or
    more) is stored and read like any other, but no business rule (for instance the clinic limit
    of FR-006) recognises it until a future spec adds one.
    """

    __tablename__ = "subscription_types"

    INDIVIDUAL: ClassVar[int] = 1
    ENTERPRISE: ClassVar[int] = 2

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
