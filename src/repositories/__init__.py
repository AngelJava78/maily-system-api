# Upper bound of an int4 primary key. A positive identifier above it cannot exist, so the
# Repositories treat it as "not found" without querying the database (asyncpg would raise
# DataError and the request would end in a 500).
INT4_MAX = 2_147_483_647
