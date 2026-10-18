-- Se ejecuta solo la primera vez que se crea el volumen de datos de PostgreSQL.
-- La base `maily_system` la crea la propia imagen (POSTGRES_DB); esta es la de las pruebas.
CREATE DATABASE maily_system_test;
