-- Esquema de la feature 010-cobro-real-suscripciones (PostgreSQL 17).
-- Es el contenido que entrega la migración 0008 y el que se refleja en
-- project-definition/DATA_SCHEMA.md. No toca ninguna tabla de las specs 001-009.
--
-- Tras el rediseño (2026-11-11) es una sola tabla: no hay clinic_subscriptions ni su catálogo de
-- estatus aquí (esa entidad vive en el futuro microservicio Clínicas, Principio IX).

-- ---------------------------------------------------------------------------------------------
-- Historial de cobros  -- [spec 010-cobro-real-suscripciones FR-001, FR-010, FR-011]
-- ---------------------------------------------------------------------------------------------
CREATE TABLE clinic_subscription_charges (
	id serial4 PRIMARY KEY,
	clinic_subscription_id uuid NOT NULL, -- identificador opaco de Clínicas (FR-002); sin FK local
	tenant_id uuid NOT NULL, -- copiado de la respuesta de Clínicas al cobrar (FR-010)
	period date NOT NULL, -- la fecha que envía quien dispara el cobro (FR-001)
	amount int4 NOT NULL CHECK (amount > 0), -- [FR-006] centavos, nunca numeric
	currency varchar(3) NOT NULL DEFAULT 'MXN',
	payment_id uuid NOT NULL, -- el id que devolvió mailySoft-pagos
	payment_status varchar(20) NOT NULL
		CHECK (payment_status IN ('pending', 'approved', 'rejected', 'cancelled', 'partially_refunded', 'refunded')), -- [FR-015]
	checkout_url text,
	idempotency_key varchar(100) NOT NULL,
	created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- A lo sumo un cobro por suscripción de clínica y periodo (research R3): lo que hace que un
-- reintento con la misma Idempotency-Key actualice la misma fila en vez de crear otra.
CREATE UNIQUE INDEX clinic_subscription_charges_one_per_period_key
	ON clinic_subscription_charges (clinic_subscription_id, period);

CREATE INDEX clinic_subscription_charges_payment_id_idx ON clinic_subscription_charges (payment_id);
CREATE INDEX clinic_subscription_charges_clinic_subscription_id_idx
	ON clinic_subscription_charges (clinic_subscription_id);
CREATE INDEX clinic_subscription_charges_tenant_id_idx ON clinic_subscription_charges (tenant_id);

-- Reutiliza la función set_updated_at() ya creada por la migración 0001.
CREATE TRIGGER clinic_subscription_charges_set_updated_at
	BEFORE UPDATE ON clinic_subscription_charges
	FOR EACH ROW EXECUTE FUNCTION set_updated_at();
