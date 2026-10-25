from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base

# Name of the unique index on the code; the Service recognises it in `UniqueViolationError`.
MONITORED_COMPONENT_CODE_INDEX = "monitored_components_code_not_deleted_key"


class MonitoredComponent(Base):
    """A service or frontend whose health the aggregation reports (spec 005, FR-023 to FR-029).

    The two integrated components (`maily-system-api` and `database`) are not stored here: their
    codes are reserved. Deleting is logical: `deleted_at` gets a date, the row stays and its code is
    free again. It must match migration 0004.
    """

    __tablename__ = "monitored_components"
    __table_args__ = (
        CheckConstraint(
            "char_length(code) BETWEEN 2 AND 50 "
            "AND code ~ '^[a-z][a-z0-9]*(-[a-z0-9]+)*$' "
            "AND code NOT IN ('maily-system-api', 'database')",
            name="code_check",
        ),
        CheckConstraint("btrim(name) <> '' AND name = btrim(name)", name="name_check"),
        CheckConstraint("kind IN ('service', 'frontend')", name="kind_check"),
        CheckConstraint("sort_order BETWEEN 0 AND 9999", name="sort_order_check"),
        CheckConstraint(
            "kind <> 'service' OR (ready_path IS NOT NULL AND info_path IS NOT NULL)",
            name="service_paths_check",
        ),
        CheckConstraint("kind <> 'frontend' OR ready_path IS NULL", name="frontend_ready_path_check"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, server_default=text("gen_random_uuid()"))
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(100))
    # 'service' or 'frontend' (the database is only integrated).
    kind: Mapped[str] = mapped_column(String(20))
    # http(s), without credentials, query or fragment; scheme and host in lower case, no final slash.
    base_url: Mapped[str] = mapped_column(String(255))
    # Service: /health/live by default. Frontend: its health route.
    live_path: Mapped[str] = mapped_column(String(200))
    # Service: /health/ready by default. Frontend: always NULL.
    ready_path: Mapped[str | None] = mapped_column(String(200))
    # Service: /info by default. Frontend: optional.
    info_path: Mapped[str | None] = mapped_column(String(200))
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
    # Kept by the `monitored_components_set_updated_at` trigger on every UPDATE.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
    # Logical deletion with its date; NULL = current. Never published.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# The code is unique among the components that are not deleted (FR-024): the code of a deleted one is
# free. It also decides simultaneous creations: only one succeeds (FR-028).
Index(
    MONITORED_COMPONENT_CODE_INDEX,
    MonitoredComponent.code,
    unique=True,
    postgresql_where=text("deleted_at IS NULL"),
)
