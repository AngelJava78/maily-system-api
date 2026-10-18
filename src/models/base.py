from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Reproduces the automatic names that PostgreSQL gives to constraints (subscriptions_pkey,
# subscriptions_status_id_fkey, subscriptions_name_check, ...), so the models and the migrations
# agree with `contracts/database-schema.sql`.
NAMING_CONVENTION = {
    "pk": "%(table_name)s_pkey",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "ix": "idx_%(table_name)s_%(column_0_name)s",
    "ck": "%(table_name)s_%(constraint_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
