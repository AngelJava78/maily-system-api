-- Esquema de la feature 006-cobro-real-suscripciones (PostgreSQL 17).
-- Es el contenido que entrega la migración 0005 y el que se refleja en
-- project-definition/DATA_SCHEMA.md. `subscriptions` y `subscription_statuses` (spec 001) no cambian.
--
-- Mismo estilo que specs/001-subscriptions-api/contracts/database-schema.sql: las claves primarias,
-- únicas y foráneas y los CHECK sin nombre explícito usan el nombre automático de PostgreSQL.

-- ---------------------------------------------------------------------------------------------
-- Catálogo de estatus de la suscripción de clínica  -- [spec 006-cobro-real-suscripciones FR-002]
-- Administrado a mano, igual que subscription_statuses. Se reconoce por id, no por name.
-- ---------------------------------------------------------------------------------------------
CREATE TABLE clinic_subscription_statuses (
	id serial4 PRIMARY KEY,
	name varchar(50) NOT NULL UNIQUE,
	description text
);

-- ---------------------------------------------------------------------------------------------
-- Suscripción de una clínica  -- [spec 006-cobro-real-suscripciones FR-001 a FR-007]
-- ---------------------------------------------------------------------------------------------
CREATE TABLE clinic_subscriptions (
	id serial4 PRIMARY KEY,
	tenant_id uuid NOT NULL, -- [FR-006] la clínica; sin tabla de clínicas (fuera de alcance)
	subscription_id int4 NOT NULL REFERENCES subscriptions (id), -- [FR-001] el plan asignado
	billing_cycle varchar(10) NOT NULL CHECK (billing_cycle IN ('monthly', 'annual')), -- [FR-002]
	started_at timestamptz NOT NULL,
	next_billing_at timestamptz NOT NULL, -- [FR-005] avanza un ciclo tras un cobro approved
	status_id int4 NOT NULL DEFAULT 1 REFERENCES clinic_subscription_statuses (id), -- 1 = Activa
	-- Sin columna "cobro vigente": sería una referencia circular con clinic_subscription_charges,
	-- que ya referencia esta tabla. El cobro vigente es la fila más reciente de esa tabla.
	created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
	updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- [FR-004] a lo sumo una suscripción Activa (1) o con cobro pendiente de resolver (2) por clínica.
CREATE UNIQUE INDEX clinic_subscriptions_one_active_per_tenant_key ON clinic_subscriptions (tenant_id)
	WHERE status_id IN (1, 2);

-- [FR-007] filtros del listado.
CREATE INDEX clinic_subscriptions_tenant_id_idx ON clinic_subscriptions (tenant_id);
CREATE INDEX clinic_subscriptions_status_id_idx ON clinic_subscriptions (status_id);

CREATE TRIGGER clinic_subscriptions_set_updated_at
	BEFORE UPDATE ON clinic_subscriptions
	FOR EACH ROW EXECUTE FUNCTION set_updated_at(); -- reutiliza la función de la migración 0001

-- ---------------------------------------------------------------------------------------------
-- Historial de cobros  -- [spec 006-cobro-real-suscripciones FR-008 a FR-018, research R3/R6]
-- ---------------------------------------------------------------------------------------------
CREATE TABLE clinic_subscription_charges (
	id serial4 PRIMARY KEY,
	clinic_subscription_id int4 NOT NULL REFERENCES clinic_subscriptions (id),
	period date NOT NULL, -- la fecha de next_billing_at vigente cuando se disparó (research R3)
	amount int4 NOT NULL CHECK (amount > 0), -- [FR-009] centavos, nunca numeric
	currency varchar(3) NOT NULL DEFAULT 'MXN',
	payment_id uuid NOT NULL, -- el id que devolvió mailySoft-pagos
	payment_status varchar(20) NOT NULL
		CHECK (payment_status IN ('pending', 'approved', 'rejected', 'cancelled', 'partially_refunded', 'refunded')), -- [FR-018]
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

CREATE TRIGGER clinic_subscription_charges_set_updated_at
	BEFORE UPDATE ON clinic_subscription_charges
	FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------------------------
-- Datos iniciales (parte de la misma migración 0005)  -- [spec 006-cobro-real-suscripciones FR-002]
-- ---------------------------------------------------------------------------------------------
INSERT INTO clinic_subscription_statuses (id, name, description) VALUES
	(1, 'Activa',                             'Al día; sin ningún cobro pendiente de resolver.'),
	(2, 'Con cobro pendiente de resolver',    'Tiene un cobro en curso (pending) o rechazado que admite un nuevo intento.'),
	(3, 'Cancelada',                          'Baja lógica: ya no admite nuevos cobros.');

-- Los estatus añadidos a mano empiezan en 4.
SELECT setval(pg_get_serial_sequence('clinic_subscription_statuses', 'id'), 3);
