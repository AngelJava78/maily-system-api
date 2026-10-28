from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class SubscriptionModule(Base):
    """One clinic module included in a subscription (spec 008).

    The module key is owned by the users API (Principle IX); this table only records which keys a
    subscription chose. Composite primary key, no own `id`: it already rejects a repeated module
    for the same subscription and, with the foreign key, a row without its subscription (FR-002).
    """

    __tablename__ = "subscription_modules"

    subscription_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subscriptions.id"), primary_key=True
    )
    module_key: Mapped[str] = mapped_column(Text, primary_key=True)
