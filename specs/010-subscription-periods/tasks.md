---

description: "Task list for feature 010-subscription-periods (Periodo de prueba y siguiente pago de cada organización)"
---

# Tasks: Periodo de prueba y siguiente pago de cada organización («Periodos de suscripción»)

**Input**: Design documents from `/specs/010-subscription-periods/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md. Requiere la
**constitución v1.1.0** vigente, las features 001 a 009 ya implementadas (suscripciones, dashboard, salud), Docker
con Compose 2.24 o superior, `uv` con Python 3.14 o superior y, solo para la colección de punta a punta,
Node.js con npm.

**Tests**: Incluidas. La spec las exige (FR-051 a FR-053) y el Principio V también. Se sigue TDD dentro de cada
fase: las tareas de pruebas van primero y **deben fallar** antes de implementar (cuando la prueba necesita
código que aún no existe, falla al importarlo; eso cuenta). **Ninguna prueba llama a un API real**: usan las
simulaciones de `tests/stubs/` y dobles en memoria. Las pruebas que necesitan PostgreSQL real se marcan `slow`
solas (`tests/conftest.py`) y el ciclo de `/speckit-implement` corre solo el nivel rápido (`uv run pytest`);
la suite completa (`uv run pytest -m ""`) y Newman son la puerta de la fase final.

**Organization**: Tareas agrupadas por historia de usuario de [spec.md](spec.md): US1 a US4 (P1) y US5 a US8
(P2). El **MVP** es Setup + Foundational + US1 + US2 + US3 + US4: un Dueño que consulta su periodo, inicia el
pago y ve moverse la fecha, con el acceso protegido. US5 a US8 cierran los cambios de plan, la degradación, la
configuración y la colección de punta a punta.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede ejecutar en paralelo (archivos distintos, sin dependencias abiertas)
- **[Story]**: historia de usuario a la que pertenece (US1 a US8); sin etiqueta en Setup, Foundational, Polish
  e Integración
- Todas las rutas son relativas a la raíz del repositorio

## Referencias rápidas

- Decisiones y evidencia: [research.md](research.md) (R1 a R21)
- Esquema, modelos, registros, DTOs y configuración: [data-model.md](data-model.md)
- Contrato HTTP: [contracts/openapi-subscription-periods.yaml](contracts/openapi-subscription-periods.yaml)
- Operación → permiso: [contracts/permission-matrix.md](contracts/permission-matrix.md)
- Códigos de error, mensajes exactos y precedencia: [contracts/error-catalog.md](contracts/error-catalog.md)
- DDL de la migración 0008: [contracts/database-schema.sql](contracts/database-schema.sql)
- Contratos consumidos: [clinics](contracts/clinics-api-integration.md), [payments](contracts/payments-api-integration.md),
  [users](contracts/users-api-integration.md)
- Colección de Postman, simulaciones y guardianas: [contracts/e2e-collection.md](contracts/e2e-collection.md)
- Ajustes a pruebas existentes (A1 a A14): sección «Ajustes a las pruebas existentes» de [plan.md](plan.md)
- Guía de validación: [quickstart.md](quickstart.md)

## Convenciones de esta feature (valen para todas las tareas)

- **Prohibido**: modificar `.specify/feature.json` (debe seguir en `specs/010-subscription-periods`); escribir
  tokens, contraseñas o secretos reales en cualquier archivo; añadir dependencias (solo biblioteca estándar y
  lo que ya hay); tocar el comportamiento o el contrato de las operaciones existentes; imprimir o registrar
  el token, las direcciones o los cuerpos de otros APIs. Los commits **no** son tareas de las fases 1 a 12: se
  hacen en la fase 13 (Integración), que pidió la persona responsable.
- **Pruebas existentes** (FR-053): las únicas que se editan son las de los ajustes A1 a A14 del plan, y solo
  de la forma que describe cada tarea. Si otra prueba existente falla, **no se arregla editándola**: se
  corrige el código nuevo y, si el choque es real, se anota en el resumen final.
- **Idioma** (Principio VII): identificadores, campos de la API y códigos de error en inglés; mensajes,
  descripciones de OpenAPI y documentos en español; comentarios y docstrings en inglés; los registros del
  servicio en inglés.
- **Mensajes exactos**: salen de [contracts/error-catalog.md](contracts/error-catalog.md); no se parafrasean.
- **Todo lo que hace I/O es `async`** (Principio III), incluidos los proveedores de `src/dependencies.py`. Los
  cálculos de fechas son funciones puras y síncronas.
- **Capas** (Principio I): el Router no importa integraciones, repositorios, base de datos ni modelos; el
  Service no importa `fastapi` ni `sqlalchemy`; las integraciones no importan DTOs ni modelos y solo usan
  `dataclass` y biblioteca estándar; el Repository no importa integraciones ni DTOs.
  `tests/unit/test_layering.py` debe seguir en verde en cada fase.
- **Importes**: `Decimal` y `NUMERIC(10,2)`, nunca `float` (Principio VI). Hacia Pagos, entero en la unidad
  mínima.
- **Fechas**: siempre `datetime` con zona, normalizadas a UTC; el reloj viene del `Clock` inyectado
  (`src/services/clock.py`); ninguna regla llama a `datetime.now()`.
- **Constantes** (se definen una sola vez, con nombre, en el módulo que se indica):

  | Constante | Valor | Módulo |
  |---|---|---|
  | `SUBSCRIPTION_PERIODS_READ` | `"subscription_periods:read"` | `src/security.py` |
  | `SUBSCRIPTION_PERIODS_WRITE` | `"subscription_periods:write"` | `src/security.py` |
  | `SUBSCRIPTION_PERIODS_PATH` | `"/api/v1/subscription-periods"` | `src/routers/subscription_periods.py` |
  | `CURRENCY` | `"MXN"` | `src/services/billing_rules.py` |
  | `RESOURCE_TYPE` | `"system-api:subscription"` | `src/services/billing_rules.py` |
  | `MONTHS` | `{"monthly": 1, "annual": 12}` | `src/services/billing_rules.py` |
  | `MAX_APPLY_ATTEMPTS` | `3` | `src/services/subscription_period_service.py` |
  | `PAYMENT_PROVIDER` | `"mercado_pago"` | `src/integrations/payments_api.py` |
  | `ORGANIZATIONS_PATH` | `"/api/v1/organizations"` | `src/integrations/clinics_api.py` |
  | `PAYMENTS_PATH` | `"/api/v1/payments"` | `src/integrations/payments_api.py` |
  | Estados del cobro | `pending`, `applied`, `closed`; motivos `rejected`, `cancelled`, `inconsistent`, `refunded` | `src/models/subscription_charge.py` (`ChargeStatus`, `ClosedReason`) |

- **Interfaces compartidas entre tareas** (usar exactamente estos nombres):
  - `src/integrations/errors.py`: `OrganizationNotFound(IntegrationError)` y `PaymentsApiUnavailable(IntegrationError)`,
    sin argumentos y con mensaje genérico.
  - `src/integrations/clinics_api.py`: `OrganizationRecord(id: UUID, subscription_id: int, billing_period: str,
    created_at: datetime)` (`@dataclass(frozen=True, slots=True)`) y
    `ClinicsApiClient.get_organization(token: str, organization_id: UUID) -> OrganizationRecord`.
  - `src/integrations/payments_api.py`: `PaymentRecord(id: UUID, status: str, amount: int, currency: str,
    resource_type: str, resource_id: str, checkout_url: str | None, updated_at: datetime)` y
    `PaymentsApiClient(http_client, base_url, timeout_seconds)` con
    `async create_payment(token, *, idempotency_key, amount, currency, resource_type, resource_id, description,
    metadata) -> PaymentRecord` y `async get_payment(token, payment_id: UUID) -> PaymentRecord`.
  - `src/repositories/subscription_repository.py`: `PlanTerms(id, name, trial_days, monthly_price, annual_price)` y
    `SubscriptionRepository.get_plan_terms(subscription_id: int) -> PlanTerms | None`.
  - `src/repositories/subscription_period_repository.py`: `ApplyOutcome(StrEnum)` con `APPLIED`,
    `ALREADY_RESOLVED`, `STALE`, y `SubscriptionPeriodRepository(session)` con `get`, `create_if_absent`,
    `list_pending` (copias desligadas de la sesión), `find_pending`, `find_by_payment_id`, `count_resolved_with_terms`, `add_charge`, `close_charge`, `apply_charge`
    (firmas en la tarea T021).
  - `src/services/billing_rules.py`: `add_months`, `payment_due_at`, `period_state`, `days_remaining`,
    `covered_period`, `to_minor_units`, `idempotency_key`, `started_at_of`, `trial_ends_at_of`
    (firmas en la tarea T014).
  - `src/services/subscription_period_service.py`: `PeriodView`, `PaymentStart` y
    `SubscriptionPeriodService(periods, subscriptions, clinics_api, payments_api, clock, cutoff)` con
    `async get_status(token, organization_id) -> PeriodView` y
    `async start_payment(token, organization_id) -> PaymentStart`.
  - `src/dtos/subscription_period.py`: `PlanRead`, `SubscriptionPeriodRead`, `SubscriptionPaymentRead`.
  - `src/dependencies.py`: `get_payments_api_client`, `get_subscription_period_repository`,
    `get_subscription_period_service`.
  - `tests/billing_support.py`: dobles `FakeOrganizationsApi`, `FakePaymentsApi`, `FakePeriodRepository`,
    constructores y la clase `BillingApi` (aplicación + simulaciones + reloj).
  - `tests/conftest.py`: fixtures `payments_stub_app`, `payments_stub`, `payments_api_client`, `billing_api`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Comprobar el punto de partida y fijar una línea base verde. Esta feature no necesita herramientas ni
dependencias nuevas.

- [X] T001 Comprobar el punto de partida: la rama actual es `010-subscription-periods`, `.specify/feature.json`
  dice `specs/010-subscription-periods`, `git status` solo muestra `specs/010-subscription-periods/` sin
  seguimiento y `uv sync` termina sin errores.
- [X] T002 Línea base rápida: `uv run pytest` en verde **antes de cambiar nada**; anotar el número de pruebas
  que pasan (para comparar al final).
- [X] T003 Línea base completa: `docker compose up -d db`, crear `maily_system_test` si no existe
  (`docker compose exec db psql -U postgres -c "CREATE DATABASE maily_system_test"`) y `uv run pytest -m ""` en
  verde antes de cambiar nada; así cualquier fallo posterior es de esta feature.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Todo lo que las historias comparten: versión, errores, configuración, reglas puras, esquema,
Repository, clientes de Clínicas y Pagos con sus simulaciones, DTOs y la infraestructura de pruebas.

**⚠️ CRITICAL**: Ninguna historia puede empezar hasta terminar esta fase.

### Versión, errores y permisos

- [X] T004 [P] Versión `4.0.0` → `4.1.0` (research R20, ajustes A2 y A5): `VERSION` en `src/__init__.py`,
  `version` en `pyproject.toml`, la versión del paquete raíz `mailysoft-system-api` en `uv.lock` y el literal
  `"4.0.0"` en `tests/unit/test_main.py` (`app.version`), `tests/unit/test_health_settings.py` (`BuildInfo`) y
  `tests/contract/test_openapi_contract.py` (`info.version`). `tests/unit/test_version.py` debe pasar.
- [X] T005 [P] Prueba (debe fallar) `tests/unit/test_billing_messages.py`: los cinco códigos nuevos existen con
  su valor exacto (`organization_not_found`, `organization_check_unavailable`, `payments_unavailable`,
  `nothing_to_charge`, `organization_subscription_not_found`); `len(ErrorCode) == 22`; cada excepción nueva
  (`OrganizationNotFoundError`, `OrganizationCheckUnavailableError`, `PaymentsUnavailableError`,
  `NothingToChargeError`, `OrganizationSubscriptionNotFoundError`) tiene su `code`, su `status_code`
  (404, 503, 503, 409, 409) y su mensaje **exacto** de [contracts/error-catalog.md](contracts/error-catalog.md)
  (el 404 repite el identificador que se le pasó); el mensaje de validación
  `VALIDATION_MESSAGES["subscription-periods"][("organization_id", "invalid")]` es «El identificador de la
  organización debe ser un UUID.»; ningún mensaje contiene `http`, `Bearer` ni `SECRETO`.
- [X] T006 Ajustes A2 a A4 a las pruebas que fijan el conjunto de códigos de error: `len(ErrorCode) == 17` →
  `22` (con un comentario «la spec 010 añadió 5 códigos») y el conjunto exacto de `test_error_messages.py` suma
  los cinco nuevos, en `tests/unit/test_error_messages.py` (renombrar `…seventeen…` → `…twenty_two…`),
  `tests/unit/test_dashboard_messages.py`, `tests/unit/test_health_messages.py`,
  `tests/contract/test_openapi_contract.py` (renombrar `…seventeen…` → `…twenty_two…`),
  `tests/contract/test_dashboard_openapi.py` y `tests/contract/test_health_openapi.py`. Ninguna otra aserción
  cambia.
- [X] T007 Implementar en `src/messages.py` los cinco `ErrorCode`, sus mensajes (texto **exacto** del catálogo) y el
  bloque `VALIDATION_MESSAGES["subscription-periods"] = {("organization_id", "invalid"): …}`; y en
  `src/exceptions.py` las cinco excepciones (`OrganizationNotFoundError(organization_id: UUID)`,
  `OrganizationCheckUnavailableError()`, `PaymentsUnavailableError()`, `NothingToChargeError()`,
  `OrganizationSubscriptionNotFoundError()`), cada una subclase de `AppError` con su `code` y `status_code`.
  `tests/unit/test_billing_messages.py` pasa.
- [X] T008 [P] Añadir en `src/security.py` `SUBSCRIPTION_PERIODS_READ` y `SUBSCRIPTION_PERIODS_WRITE` (con el
  comentario que remite a `specs/010-subscription-periods/contracts/permission-matrix.md`); en
  `src/integrations/errors.py`, `OrganizationNotFound(IntegrationError)` («The clinics API has no such
  organization for this token») y `PaymentsApiUnavailable(IntegrationError)` («The payments API did not answer
  as expected»).

### Configuración (FR-039, FR-040)

- [X] T009 Prueba (debe fallar) `tests/unit/test_billing_config.py`: `PaymentsSettings` (aislada del entorno y de
  `.env` con `_env_file=None`): `PAYMENTS_API_BASE_URL` obligatoria y normalizada igual que las otras dos
  (`http(s)://host`, sin barra final, otro esquema o sin host → inválida); `PAYMENTS_API_TIMEOUT_SECONDS`
  opcional, 5.0 por omisión, «mayor que 0 y hasta 30»; vacía = no definida (`env_ignore_empty`).
  `BillingSettings`: `BILLING_CUTOFF_AT` obligatoria, ISO 8601 **con** zona (`2026-11-18T00:00:00Z`,
  `2026-11-17T18:00:00-06:00`), normalizada a UTC; sin zona (`2026-11-18T00:00:00`), numérica (`1700000000`),
  vacía o no fecha → inválida. `configuration_error_message(...)` nombra `PAYMENTS_API_BASE_URL` o
  `BILLING_CUTOFF_AT` y **nunca el valor**; `payments_url_warnings(settings)` avisa (nombrando la variable,
  nunca la dirección) solo con `http://` fuera de una red local o de Docker (`localhost`, `127.0.0.1`, `::1` y
  nombres sin punto no avisan; `https://` no avisa).
- [X] T010 Implementar en `src/config.py`: `PaymentsSettings` y `BillingSettings` (patrón de
  `IntegrationSettings`/`BuildSettings`: `SettingsConfigDict(env_file=".env", extra="ignore",
  env_ignore_empty=True)`; la fecha con un validador `mode="before"` que usa `datetime.fromisoformat`, exige
  `utcoffset() is not None` y devuelve el instante en UTC, con un mensaje que no incluye el valor),
  `get_payments_settings()` y `get_billing_settings()` (con `lru_cache`) y `payments_url_warnings(settings:
  PaymentsSettings) -> list[str]`. **No** tocar `IntegrationSettings` (`src/scripts/backfill_subscription_types.py`
  y su prueba siguen igual; research R11). `tests/unit/test_billing_config.py` pasa.
- [X] T011 Cablear el arranque en `src/main.py` (`lifespan`): añadir `get_payments_settings` y
  `get_billing_settings` a la tupla `loaders` (un solo mensaje nombra todas las variables malas) y registrar
  `payments_url_warnings(get_payments_settings())` junto a `insecure_url_warnings`. Todavía **no** incluir el
  router (llega en US1).
- [X] T012 Ajuste A6(i) en `tests/conftest.py`: fixture `autouse` `billing_environment` (función) que con
  `monkeypatch` define `PAYMENTS_API_BASE_URL=http://payments-api:8080` y
  `BILLING_CUTOFF_AT=2020-01-01T00:00:00Z` y limpia antes y después `get_payments_settings` y
  `get_billing_settings`. Con esto las pruebas que arrancan el `lifespan` (`test_main`, `test_config`,
  `test_health_startup`, `test_dashboard_startup`) siguen sin editarse. Comprobar con `uv run pytest tests/unit`
  que todo lo existente sigue en verde.

### Reglas puras de fechas e importes (FR-008 a FR-017, FR-029, FR-030)

- [X] T013 Prueba (debe fallar) `tests/unit/test_billing_rules.py`, con `datetime` aware en UTC y **sin dobles**:
  los 16 ejemplos de «Ejemplos de referencia del cálculo de fechas» de [spec.md](spec.md) fila por fila (alta,
  corte, `trial_ends_at`, estado y días en cada consulta, periodos cubiertos de los pagos en prueba y vencido);
  `add_months` (31 ene 2027 → 28 feb 2027, 31 ene 2028 → 29 feb 2028, 28 feb 2027 → 28 mar 2027, 31 ago →
  30 sep, 29 feb 2028 + 12 → 28 feb 2029, conserva la hora UTC); `period_state` en los cuatro estados y en los
  límites (instante exacto del fin de la prueba y de la fecha de pago → `overdue`; amount `0.00` → `no_charge`
  aunque haya prueba; sin prueba nunca `trial`); `days_remaining` (48 h → 2, 49 h → 3, 0.5 h → 1, 0 → 0, vencida
  0.5 h → 0, vencida 24 h → −1, vencida 137.5 h → −5; con microsegundos y sin `float`: una diferencia de
  1 microsegundo por encima de un día entero da el día siguiente); `payment_due_at` (`paid_until`, si no
  `trial_ends_at`, si no `started_at`); `covered_period` (a tiempo, vencida, exactamente en la fecha, mensual y
  anual); `to_minor_units` (`Decimal("499.00")` → 49900, `Decimal("0.01")` → 1, `Decimal("1234567.89")` →
  123456789; un valor con más de dos decimales lanza `ValueError`); `started_at_of` (la más reciente entre el
  alta y el corte, en UTC, aunque lleguen con otra zona); `trial_ends_at_of` (`None` con 0 días; inicio +
  `trial_days` × 24 h); `idempotency_key` (determinista; empieza con `sub-<organización>-`; mide 65
  caracteres; cambia con cualquier condición o intento; usa la hora UTC aunque llegue con otra zona).
- [X] T014 Implementar `src/services/billing_rules.py` (solo biblioteca estándar: `calendar`, `datetime`,
  `decimal`, `hashlib`, `uuid`; sin E/S): `CURRENCY`, `RESOURCE_TYPE`, `MONTHS`, `PeriodState = Literal["trial",
  "current", "overdue", "no_charge"]` y las funciones `add_months(moment, months)`, `payment_due_at(started_at,
  trial_ends_at, paid_until)`, `period_state(now, amount, trial_ends_at, due)`, `days_remaining(due, now)`
  (división entera con redondeo hacia +∞, exacta y sin `float`: `-((now - due) // timedelta(days=1))`, donde
  `timedelta // timedelta` devuelve un `int`),
  `covered_period(due, approved_at, billing_period)`, `to_minor_units(amount)`, `started_at_of(created_at,
  cutoff)`, `trial_ends_at_of(started_at, trial_days)` e `idempotency_key(organization_id, settles_due_at,
  billing_period, amount_minor, attempt, description)` =
  `f"sub-{organization_id}-{sha256(f'{settles_due_at.astimezone(UTC).isoformat()}|{billing_period}|{amount_minor}|{attempt}|{description}'.encode()).hexdigest()[:24]}"`
  (la descripción entra en la clave: research R6).
  `tests/unit/test_billing_rules.py` pasa.

### Esquema, modelos y Repository (Principio VI)

- [X] T015 [P] Crear `src/models/subscription_period.py` y `src/models/subscription_charge.py` y exportarlos en
  `src/models/__init__.py`, reproduciendo **exactamente** [data-model.md](data-model.md) secciones 2 a 4.
  `SubscriptionPeriod`: `organization_id` `Uuid` clave primaria sin valor por defecto; `started_at`
  `DateTime(timezone=True)` no nula; `trial_ends_at` y `paid_until` `DateTime(timezone=True)` nulas;
  `created_at` y `updated_at` con `server_default=text("CURRENT_TIMESTAMP")`; `CheckConstraint` con los
  nombres cortos `trial_ends_check` («trial_ends_at IS NULL OR trial_ends_at >= started_at») y
  `paid_until_check` («paid_until IS NULL OR paid_until > started_at»). `SubscriptionCharge`: `id` `Uuid`
  clave primaria con `server_default=text("gen_random_uuid()")`; `organization_id`
  `ForeignKey("subscription_periods.organization_id")`; `payment_id` `Uuid`; `amount` `Numeric(10, 2)`;
  `currency` `String(3)`; `billing_period` `String(10)`; `settles_due_at` `DateTime(timezone=True)`; `attempt`
  `Integer`; `status` `String(10)` con `server_default=text("'pending'")`; `closed_reason` `String(20)` nula;
  `period_starts_at`, `period_ends_at` y `resolved_at` nulas; `created_at` y `updated_at`; `UniqueConstraint
  ("payment_id")` (nombre `subscription_charges_payment_id_key` por la convención) y
  `UniqueConstraint("organization_id", "settles_due_at", "billing_period", "amount", "attempt",
  name="subscription_charges_terms_attempt_key")`; los siete `CheckConstraint` (`amount_check`: «amount > 0»;
  `currency_check`: «currency = 'MXN'»; `billing_period_check`: «billing_period IN ('monthly', 'annual')»;
  `attempt_check`: «attempt >= 1»; `status_check`: «status IN ('pending', 'applied', 'closed')»;
  `closed_reason_check`: «closed_reason IS NULL OR closed_reason IN ('rejected', 'cancelled', 'inconsistent',
  'refunded')»; `resolution_check`: el de [database-schema.sql](contracts/database-schema.sql)); y el `Index`
  parcial `subscription_charges_pending_idx` sobre `(organization_id, created_at)` con
  `postgresql_where=text("status = 'pending'")`. Constantes `ChargeStatus` y `ClosedReason` (`StrEnum`) en el
  mismo módulo.
- [X] T016 Migración `alembic/versions/0008_subscription_periods.py` (`revision = "0008"`, `down_revision =
  "0007"`; docstring en español como las anteriores): `upgrade()` crea `subscription_periods`, su disparador
  `subscription_periods_set_updated_at`, `subscription_charges`, el índice parcial y su disparador
  `subscription_charges_set_updated_at`, reproduciendo [contracts/database-schema.sql](contracts/database-schema.sql)
  (los `CheckConstraint` con los **nombres cortos** del modelo, como en `0004`); `downgrade()` borra los
  disparadores, el índice y las tablas en orden inverso y **no** la función `set_updated_at()` de 0001.
- [X] T017 [P] Prueba `tests/integration/test_subscription_periods_migration.py` (marcada `slow` sola): `0008`
  sube desde `0007` y deja las dos tablas con sus restricciones (`subscription_periods_pkey`,
  `subscription_periods_trial_ends_check`, `subscription_periods_paid_until_check`, `subscription_charges_pkey`,
  `subscription_charges_organization_id_fkey`, `subscription_charges_payment_id_key`,
  `subscription_charges_terms_attempt_key` y los siete `CHECK`), el índice parcial y los dos disparadores;
  inserciones inválidas fallan con el SQLSTATE y el nombre de restricción correctos (`assert_pg_error`):
  importe 0 (`subscription_charges_amount_check`), moneda `USD`, periodo `weekly`, `attempt` 0, estado
  `applied` sin periodo cubierto (`subscription_charges_resolution_check`), `closed` sin motivo, `pending` con
  `resolved_at`, `trial_ends_at` anterior a `started_at`, `paid_until` igual a `started_at`, `payment_id`
  repetido, mismas condiciones e intento repetidos, un cobro sin periodo (clave foránea); el disparador mueve
  `updated_at` en un `UPDATE`; `0008` baja a `0007` sin borrar `set_updated_at()` y vuelve a subir. Además
  `tests/integration/test_models_match_migrations.py` (sin editarlo) pasa con los modelos nuevos.
- [X] T018 [P] Prueba `tests/integration/test_plan_terms.py` (`slow`): `SubscriptionRepository.get_plan_terms`
  devuelve el plan con su nombre, `trial_days`, `monthly_price` y `annual_price` (`Decimal` con dos decimales)
  **en cualquier estatus** (Activa, Inactiva, Bloqueada, Eliminada y uno añadido a mano), `None` si no existe y
  `None` para un identificador mayor que `INT4_MAX` sin consultar la base.
- [X] T019 Implementar en `src/repositories/subscription_repository.py`: `PlanTerms`
  (`@dataclass(frozen=True, slots=True)`: `id: int`, `name: str`, `trial_days: int`, `monthly_price: Decimal`,
  `annual_price: Decimal`) y `async get_plan_terms(subscription_id: int) -> PlanTerms | None` (un `SELECT` de esas
  cinco columnas **sin filtrar por estatus**, con la guarda de `INT4_MAX`). No cambia ningún otro método.
- [X] T020 [P] Prueba `tests/integration/test_subscription_period_repository.py` (`slow`, con la base real y
  `committing_session`/`AsyncSession(engine)`): `create_if_absent` crea una vez y devuelve la fila existente sin
  cambiarla ante una segunda llamada (incluidas 10 simultáneas con `asyncio.gather` y sesiones distintas:
  una fila); `get` devuelve `None` si no hay; `add_charge` guarda un cobro `pending` con `currency` `MXN` y lanza
  `UniqueViolationError` con `constraint_name` `subscription_charges_payment_id_key` o
  `subscription_charges_terms_attempt_key` según el caso; `list_pending` (solo `pending`, de esa organización,
  por `created_at` e `id`); `find_pending` por organización, `settles_due_at`, `billing_period` e importe;
  `count_resolved_with_terms` cuenta solo los intentos ya terminados (aplicados o cerrados, nunca el pendiente); `close_charge` cierra un `pending` con su motivo y
  `resolved_at` y devuelve `False` si ya no estaba pendiente; `apply_charge`: devuelve `APPLIED` y deja el cobro
  `applied` con el periodo cubierto y `paid_until` movido en la misma transacción; una segunda llamada con el
  mismo cobro devuelve `ALREADY_RESOLVED` y no cambia nada; con `expected_paid_until` distinto del actual
  devuelve `STALE` y **deshace también la reclamación del cobro** (sigue `pending`); 20 llamadas simultáneas a
  `apply_charge` del mismo cobro → exactamente un `APPLIED` y `paid_until` movido una vez; dos cobros
  distintos aplicados a la vez → ambos terminan `applied` tras reintentar con `expected_paid_until` nuevo.
- [X] T021 Implementar `src/repositories/subscription_period_repository.py`: `ApplyOutcome(StrEnum)`
  (`APPLIED`, `ALREADY_RESOLVED`, `STALE`) y `SubscriptionPeriodRepository(session)` con
  `async get(organization_id: UUID) -> SubscriptionPeriod | None`;
  `async create_if_absent(organization_id: UUID, started_at: datetime, trial_ends_at: datetime | None) ->
  SubscriptionPeriod` (`insert(...).on_conflict_do_nothing(index_elements=["organization_id"])`, `commit` y
  lectura con `populate_existing`); `async list_pending(organization_id) -> list[SubscriptionCharge]`;
  `async find_pending(organization_id, settles_due_at, billing_period, amount) -> SubscriptionCharge | None`;
  `async count_resolved_with_terms(organization_id, settles_due_at, billing_period, amount) -> int`;
  `async add_charge(*, organization_id, payment_id, amount, billing_period, settles_due_at, attempt,
  currency="MXN") -> SubscriptionCharge` (por `execute_and_commit`, que ya traduce las violaciones únicas);
  `async close_charge(charge_id: UUID, reason: str, resolved_at: datetime) -> bool` (`UPDATE … WHERE id AND
  status='pending' RETURNING id`); y `async apply_charge(*, charge_id, organization_id, expected_paid_until,
  period_starts_at, period_ends_at, resolved_at) -> ApplyOutcome` con las **dos sentencias condicionadas en una
  sola transacción** de [research R5](research.md) (reclamar con `status='pending'`; mover `paid_until` con
  `IS NOT DISTINCT FROM :expected`; `ALREADY_RESOLVED` o `STALE` hacen `rollback`). Sin reglas de negocio:
  recibe los valores ya calculados. `tests/integration/test_subscription_period_repository.py` pasa.

### Simulaciones y clientes de las integraciones (FR-047, FR-048)

- [X] T022 [P] Crear la simulación de Pagos `tests/stubs/payments_api/__init__.py` (vacío) y
  `tests/stubs/payments_api/app.py` siguiendo el patrón de `tests/stubs/clinics_api/app.py` (autocontenida: no
  importa `src/`; `MARKER = "SECRETO-INTERNO"`; middleware `_RecordCalls` que guarda `path`, `method`,
  `authorization`, `idempotency_key` y `header_names` de todo lo que no sea `/__test__/`): `POST
  /api/v1/payments` (sin `Authorization: Bearer` → 401 `unauthenticated`; valida `provider`, `amount` entero >
  0, `currency` de 3 letras, `resource_type` con `^[a-z0-9-]+:[a-z0-9_-]+$` y `resource_id`; **idempotente**: la
  misma `Idempotency-Key` con el mismo cuerpo devuelve el mismo pago, con otro cuerpo `409
  idempotency_key_conflict`; responde 201 con un `PaymentRead` completo: `id` UUID, `status` `pending`,
  `provider`, `amount`, `currency`, `resource_type`, `resource_id`, `description`, `metadata`,
  `refunded_amount` 0, `checkout_url` `https://checkout.example.test/pay/<id>`, `idempotency_key`, `created_at`
  y `updated_at`); `GET /api/v1/payments/{id}` (200 o `404 payment_not_found`; `checkout_url` solo mientras el
  estatus sea `pending`); `POST /__test__/payments/{id}/status` `{status, amount?, currency?}` (cambia el
  estatus, opcionalmente el importe y la moneda, y `updated_at`; valida que el estatus sea uno de
  `pending`, `approved`, `rejected`, `cancelled`, `partially_refunded`, `refunded`); `POST /__test__/payments`
  (crea un pago «por otra vía» con los campos que se envíen y el estatus indicado); `GET /__test__/payments`;
  `GET /__test__/calls`; `POST /__test__/faults` `{mode, count, delay_seconds, operation}` con los modos
  `unavailable` (503), `unauthorized` (401), `forbidden` (403), `organization_required` (403), `malformed`
  (200 sin los campos), `not_json` (texto), `redirect` (307), `slow`, `unknown_status` (200 con un estatus que
  no existe) y `no_checkout` (pendiente con `checkout_url` nulo), y `operation` = `create`, `get` o `any` (por
  omisión `any`); `POST /__test__/reset`. Los cuerpos de falla llevan la marca. `app = create_stub_app()` al
  final.
- [X] T023 [P] Ajuste A13: extender `tests/stubs/clinics_api/app.py` de forma aditiva: `GET
  /api/v1/organizations/{id}` (sin `Authorization: Bearer` → 401; organización desconocida o token distinto del
  `owner_token` registrado → `404` con cuerpo `{"code": "not_found", "message": "<MARKER> detalle interno"}`;
  si no, 200 con `id`, `subscription_id`, `billing_period`, `created_at` y un campo extra `name` que la API
  debe ignorar), `POST /__test__/organizations` `{id, subscription_id, billing_period, created_at,
  owner_token}`, `FaultIn.operation` (`counts` por omisión, o `organizations`; `take_fault(operation)` solo
  consume las fallas de su operación, de modo que `subscription-counts` se comporta exactamente igual que
  antes), los modos nuevos `missing_billing_period`, `invalid_billing_period` y `not_found_other_code` (404 con
  `code` distinto de `not_found`), y `POST /__test__/reset` que también vacía las organizaciones. El middleware
  de llamadas guarda además `organization_id` cuando la ruta es la de organizaciones. Las pruebas existentes
  de `subscription-counts` siguen sin editarse.
- [X] T024 [P] Ajuste A6(ii parcial) y A7 en `tests/conftest.py` y `tests/helpers.py`: fixtures
  `payments_stub_app`, `payments_stub` (cliente `httpx` con `ASGITransport`, `base_url=PAYMENTS_BASE_URL`) y
  `payments_api_client` (`PaymentsApiClient(payments_stub, PAYMENTS_BASE_URL, 5.0)`, importado dentro de la
  fixture); `PAYMENTS_BASE_URL = "http://payments-api.test"` en `tests/helpers.py`; `Api.__init__` acepta
  `payments_stub: httpx.AsyncClient | None = None` **al final** y gana `payments_calls()`, `payments_fault(mode,
  count=1, delay=30, operation="any")` y `register_organization(organization_id, subscription_id,
  billing_period="monthly", created_at=…, owner_token=TEST_TOKEN)`; `Api.clinics_fault` acepta
  `operation="counts"` (las llamadas existentes no cambian). **No** tocar `ALL_PERMISSIONS` de
  `tests/helpers.py`: las pruebas nuevas conceden sus dos permisos con `grant(...)`.
- [X] T025 [P] Prueba (debe fallar) `tests/unit/test_clinics_organization_client.py`, con
  `ClinicsApiClient` real contra la simulación (fixtures `clinics_stub`/`clinics_stub_app`): 200 devuelve un
  `OrganizationRecord` con `created_at` en UTC y `billing_period` correcto y reenvía el token tal cual (sin otras
  cabeceras que `Authorization` y `Accept`); el campo extra se ignora; 404 con `code` `not_found` →
  `OrganizationNotFound`; 404 con otro código, `unavailable` (503), `unauthorized` (401), `forbidden` (403),
  `malformed`, `not_json`, `redirect` (no se sigue), `slow` (con un tiempo de 0.2 s), un `id` distinto del
  pedido, `subscription_id` 0, negativo, booleano o texto, `created_at` sin zona o inválido,
  `missing_billing_period` y `invalid_billing_period` → `ClinicsApiUnavailable`; los registros de la
  integración (`caplog`) no contienen el token, la dirección ni la marca `SECRETO-INTERNO`; una sola llamada
  HTTP por consulta, sin reintentos.
- [X] T026 Implementar `ClinicsApiClient.get_organization(token, organization_id)` y `OrganizationRecord` en
  `src/integrations/clinics_api.py` (mismo patrón que `get_counts`: `asyncio.timeout` total, solo
  `Authorization` y `Accept`, `ORGANIZATIONS_PATH`; 200 con JSON de objeto y validación estricta de `id` (UUID
  igual al pedido), `subscription_id` (`type(...) is int` y ≥ 1), `billing_period` (`monthly` o `annual`) y
  `created_at` (`datetime.fromisoformat` con `tzinfo`, normalizado a UTC); 404 con `code == "not_found"` →
  `OrganizationNotFound`; todo lo demás → `ClinicsApiUnavailable`; registra solo el tipo de falla y el
  estado). No cambia `get_counts`. `tests/unit/test_clinics_organization_client.py` pasa.
- [X] T027 [P] Prueba (debe fallar) `tests/unit/test_payments_api_client.py`, con `PaymentsApiClient` real
  contra la simulación de Pagos: `create_payment` envía `POST /api/v1/payments` con `Idempotency-Key`,
  `Authorization` reenviado y el cuerpo `{provider: "mercado_pago", amount, currency, resource_type,
  resource_id, description, metadata}`, y devuelve un `PaymentRecord` (acepta 201); repetir la misma clave y el
  mismo cuerpo devuelve el mismo `id`; `get_payment` devuelve el estatus y `updated_at` en UTC; 404, 401, 403,
  409, 503, `organization_required`, `malformed`, `not_json`, `redirect`, `slow`, `unknown_status` (estatus
  fuera del contrato), un `id` distinto del pedido, `amount` booleano o decimal, `updated_at` sin zona y un
  cuerpo que no es objeto → `PaymentsApiUnavailable`; `no_checkout` devuelve `checkout_url` `None` (válido);
  los registros no contienen el token, la dirección ni la marca; sin reintentos (una llamada por operación).
- [X] T028 Implementar `src/integrations/payments_api.py`: `PAYMENT_PROVIDER`, `PAYMENTS_PATH`, `PaymentRecord`
  y `PaymentsApiClient(http_client, base_url, timeout_seconds)` con `create_payment` y `get_payment` (mismo
  patrón que `ClinicsApiClient`: `asyncio.timeout` total, sin redirecciones —el cliente compartido ya no las
  sigue—, sin reintentos, solo cabeceras `Authorization`, `Accept`, `Content-Type` e `Idempotency-Key`;
  validación estricta del `PaymentRead`: `id` UUID, `status` en el conjunto de seis, `amount` `int` no
  booleano, `currency` de tres letras, `resource_type` y `resource_id` texto, `checkout_url` texto o `None`,
  `updated_at` ISO con zona en UTC; cualquier otra cosa → `PaymentsApiUnavailable`). `tests/unit/
  test_payments_api_client.py` pasa.

### DTOs y composición

- [X] T029 [P] Prueba (debe fallar) `tests/unit/test_subscription_period_dtos.py`: `SubscriptionPeriodRead`
  siempre trae sus nueve claves (también cuando valen `null`); las fechas salen en ISO 8601 UTC con `Z`
  (`2026-12-04T15:30:00Z`) aunque entren con otra zona; `amount` sale como texto con dos decimales (`"499.00"`,
  `"0.00"`, `"4990.00"`); `currency` solo admite `MXN`, `state` los cuatro valores, `billing_period` los dos;
  un valor fuera del contrato se rechaza; `days_remaining` y `payment_in_progress` aceptan `null`;
  `SubscriptionPaymentRead` trae `checkout_url`, `amount`, `currency`, `billing_period`; ningún DTO trae
  campos de token, de identificadores de pago ni de direcciones de otros APIs; los esquemas JSON publican
  los nueve campos como obligatorios.
- [X] T030 Implementar `src/dtos/subscription_period.py` (docstrings y descripciones de campo en español como los
  demás DTOs): `PlanRead` (`id`, `name`), `SubscriptionPeriodRead` y `SubscriptionPaymentRead` con
  `AwareDatetime` normalizado a UTC (`field_validator` como `RecentClinicRead`) y `amount` con
  `field_serializer` a `format(value.quantize(Decimal("0.01")), "f")` (patrón de `SubscriptionRead`);
  `Literal` para `state`, `billing_period` y `currency`. `tests/unit/test_subscription_period_dtos.py` pasa.

### Infraestructura de pruebas compartida

- [X] T031 Crear `tests/billing_support.py` (sin fixtures; patrón de `tests/dashboard_support.py` y
  `tests/health_support.py`): reutiliza `FakeClock` de `tests/health_support.py`; `ORG_ID`, `OTHER_ORG_ID`,
  `PLAN_NAME` y constructores `make_organization(...) -> OrganizationRecord`,
  `make_payment(status="pending", amount=49900, ...) -> PaymentRecord`; los dobles en memoria
  `FakeOrganizationsApi` (doble de `ClinicsApiClient.get_organization`: registra las llamadas, devuelve lo
  configurado o lanza `OrganizationNotFound` / `ClinicsApiUnavailable`), `FakePaymentsApi` (doble de
  `PaymentsApiClient`: `create_payment` idempotente por clave, `get_payment` con estatus configurables por pago,
  fallas por operación, llamadas registradas y `updated_at` configurable) y `FakePeriodRepository` (doble de
  `SubscriptionPeriodRepository` con **la misma semántica**: `create_if_absent` idempotente, `apply_charge` con
  reclamación y compare-and-swap, `ALREADY_RESOLVED` y `STALE`; guarda objetos `SubscriptionPeriod` y
  `SubscriptionCharge` reales en memoria), más un `FakeSubscriptionRepository`-compatible con `get_plan_terms`
  (la clase `FakeSubscriptionRepository` de `tests/unit/fakes.py` **no se edita**: se añade en este archivo una
  subclase o un doble propio que sirve `get_plan_terms`).
- [X] T032 Ajuste A6(ii–iii) en `tests/conftest.py`: la fixture `api` suma la simulación de Pagos (parámetro
  `payments_stub`, `Api(..., payments_stub)`), sobrescribe `get_payments_api_client` y vacía también
  `subscription_charges, subscription_periods` en su `TRUNCATE` final; fixture nueva `billing_api` (parte de
  `_NEEDS_REAL_DATABASE`) que crea la aplicación con la base real, **tres** simulaciones (Usuarios, Clínicas y
  Pagos), un `FakeClock` en `TEST_NOW` y el `get_clock` sobrescrito, concede a `TEST_TOKEN` los dos permisos
  nuevos y devuelve un `BillingApi` (definido en `tests/billing_support.py`: `app`, `client`, `anonymous`,
  `users_stub`, `clinics_stub`, `payments_stub`, `engine`, `clock`, y métodos `add_plan(**valores)` que usa
  `insert_subscription`, `register_organization(...)`, `set_payment_status(payment_id, status, amount=None,
  currency=None)`, `create_foreign_payment(...)`, `payments(...)`/`payments_calls()`/`clinics_calls()`/
  `users_calls()`, `payments_fault(...)`, `clinics_fault(...)`, `periods()` y `charges()` que leen las tablas, y
  `get_period(org)` / `start_payment(org)` que llaman a las rutas). Al terminar vacía las dos tablas nuevas.
- [X] T033 Comprobar la fase: `uv run pytest` (rápido) en verde, `uv run pytest tests/integration -m ""` en verde y
  `uv run pytest tests/unit/test_layering.py` en verde. **Checkpoint**: las reglas, el esquema, el Repository,
  los clientes, las simulaciones y la infraestructura están listos.

**Checkpoint**: Foundation ready — las historias pueden empezar.

---

## Phase 3: User Story 1 - Saber en qué punto está la prueba y cuándo toca pagar (Priority: P1) 🎯 MVP

**Goal**: Que el Dueño consulte el estado de su organización (`get_subscription_period`): estado, fechas, días,
plan, periodo de cobro, importe y cobro en curso; el registro se crea una sola vez en la primera consulta.

**Independent Test**: Con Clínicas, Pagos y Usuarios simulados y un reloj fijo, consultar una organización
nueva y comprobar su estado y sus fechas; mover el reloj a cada lado de los límites y repetir; comprobar que las
fechas no cambian.

### Tests for User Story 1 ⚠️

- [X] T034 [P] [US1] Prueba (debe fallar) `tests/unit/test_subscription_period_service.py` (parte consulta, con
  `FakeOrganizationsApi`, `FakePaymentsApi`, `FakePeriodRepository`, el doble del catálogo y `FakeClock`):
  escenarios 1 a 7 de la historia 1 de [spec.md](spec.md) y los ejemplos 1 a 6 y 12 a 15 de referencia
  (`trial` con 9 días; `overdue` con −5; sin prueba → `trial_ends_at` `None`, `payment_due_at` = inicio,
  `overdue`; importe 0.00 → `no_charge` con fechas y días `None`; alta anterior al corte → inicio = corte; corte
  futuro → `current`); la primera consulta crea el registro **una vez** y la segunda no cambia `started_at` ni
  `trial_ends_at` aunque cambien el plan de la organización o los `trial_days` del catálogo; el plan usado al
  crear el registro es el vigente en ese momento; `amount` mensual o anual según el periodo de cobro de la
  organización; `payment_in_progress` es `False` sin cobros; la consulta llama a Clínicas con el token recibido
  y no a Pagos si no hay cobros; Clínicas: `OrganizationNotFound` → `OrganizationNotFoundError`,
  `ClinicsApiUnavailable` → `OrganizationCheckUnavailableError`; plan inexistente →
  `OrganizationSubscriptionNotFoundError` y no se crea registro.
- [X] T035 [P] [US1] Prueba (debe fallar) `tests/contract/test_subscription_periods_api.py` (parte consulta, con
  `billing_api`; `slow`): `GET /api/v1/subscription-periods/{id}` devuelve 200 con las nueve claves y la forma
  del contrato para los escenarios 1 a 4, 6 y 9 (fechas en UTC con `Z`, `amount` `"499.00"`, `Cache-Control:
  no-store`); la primera consulta deja **una** fila en `subscription_periods` y la segunda no la cambia; diez
  primeras consultas simultáneas (`asyncio.gather`) → una fila y diez respuestas idénticas (escenario 7);
  cambiar el plan en la simulación y los `trial_days` en el catálogo no mueve las fechas (escenario 6); la
  consulta no escribe nada más que el periodo; con el reloj movido (`clock.set`) el estado y los días cambian
  como en los ejemplos.

### Implementation for User Story 1

- [X] T036 [US1] Implementar `src/services/subscription_period_service.py` (parte consulta): `PeriodView`
  (`@dataclass(frozen=True, slots=True)`: `state`, `trial_ends_at`, `payment_due_at`, `days_remaining`,
  `plan_id`, `plan_name`, `billing_period`, `amount`, `payment_in_progress`) y
  `SubscriptionPeriodService(periods, subscriptions, clinics_api, payments_api, clock, cutoff)` con
  `get_status(token, organization_id)`: (1) lee la organización en Clínicas y traduce `OrganizationNotFound` →
  `OrganizationNotFoundError(organization_id)` y `ClinicsApiUnavailable` → `OrganizationCheckUnavailableError`;
  (2) `get_plan_terms(organization.subscription_id)` y, si es `None`,
  `OrganizationSubscriptionNotFoundError`; (3) `periods.get(...)` y, si no existe, `create_if_absent` con
  `started_at_of(...)` y `trial_ends_at_of(...)` calculados con el plan **actual**; (4) calcula el importe (`monthly_price` o
  `annual_price` según el periodo de cobro), la fecha de pago, el estado y los días con `billing_rules` y el
  reloj; (5) devuelve la vista. Aquí **no** hay conciliación todavía (`payment_in_progress` = `False`): la
  añade US3. Importar `OrganizationNotFound`/`ClinicsApiUnavailable` de `src.integrations.errors`. Registrar
  en inglés, nivel `INFO`, cuándo se crea un registro (solo el identificador de la organización).
- [X] T037 [US1] Composición en `src/dependencies.py`: `get_payments_api_client` (usa `get_payments_settings()` y
  el cliente HTTP compartido), `get_subscription_period_repository(session)` y
  `get_subscription_period_service(...)` (arma el Service con los repositorios, `get_clinics_api_client`,
  `get_payments_api_client`, `get_clock` y `get_billing_settings().billing_cutoff_at`), todos `async def`.
- [X] T038 [US1] Router `src/routers/subscription_periods.py` (patrón de `routers/dashboard.py`):
  `SUBSCRIPTION_PERIODS_PATH`, `router = APIRouter(prefix=…, tags=["subscription-periods"])`, el handler
  `get_subscription_period` en `GET /{organization_id}` con `organization_id: UUID`, `response_model=
  SubscriptionPeriodRead`, `operation_id="get_subscription_period"`, `**protected(SUBSCRIPTION_PERIODS_READ,
  responses={200: …, 404: …, 409: …, 422: …})` con ejemplos en español tomados de
  [contracts/openapi-subscription-periods.yaml](contracts/openapi-subscription-periods.yaml), `Cache-Control:
  no-store` en la respuesta y conversión explícita `PeriodView` → DTO; descripción en español (qué es cada
  estado, `days_remaining`, que la primera consulta crea el registro, que aplica los cobros aprobados y que no
  hay gracia) y la línea «Permiso requerido: `subscription_periods:read`.». Incluirlo en `src/main.py`
  (`app.include_router`), con la etiqueta `subscription-periods` en `OPENAPI_TAGS` y un párrafo en `DESCRIPTION`.
- [X] T039 [US1] Comprobar la historia: `uv run pytest tests/unit/test_subscription_period_service.py` en verde y
  `uv run pytest tests/contract/test_subscription_periods_api.py -m ""` en verde.

**Checkpoint**: la consulta funciona de punta a punta (sin cobros todavía).

---

## Phase 4: User Story 2 - Iniciar el pago y llegar al checkout (Priority: P1)

**Goal**: `create_subscription_payment`: crear el cobro en Pagos con el importe del catálogo, registrarlo y
devolver el checkout; idempotente por periodo.

**Independent Test**: Con Pagos simulado, iniciar el pago de una organización con plan y periodo conocidos,
comprobar lo que recibió Pagos y el registro propio; repetir y comprobar que no hay un segundo cobro; provocar
una falla de Pagos y comprobar el 503 sin cobro.

### Tests for User Story 2 ⚠️

- [X] T040 [P] [US2] Prueba (debe fallar) `tests/unit/test_subscription_period_service.py` (parte pago): escenarios
  1 a 7 y 10 de la historia 2: crea **un** pago en `FakePaymentsApi` con `amount` en unidad mínima (49900),
  `currency` `MXN`, `resource_type` `system-api:subscription`, `resource_id` = la organización, la
  `Idempotency-Key` determinista y el token recibido, y registra el cobro `pending` con el `payment_id`, el
  importe `Decimal("499.00")`, el periodo de cobro, `settles_due_at` = la fecha de pago vigente y `attempt` 1;
  anual → 499000 y `annual`; repetirlo → mismo `checkout_url` y `created=False` sin llamar otra vez a
  `create_payment`; cobro previo cerrado → intento 2, clave distinta, pago nuevo; importe distinto (cambio de
  plan) → cobro nuevo con el importe vigente; importe 0.00 → `NothingToChargeError` sin llamar a Pagos;
  Pagos con falla en `create_payment` (sin respuesta, 401/403, estatus inesperado) → `PaymentsUnavailableError`
  y **ningún** cobro registrado; un pago devuelto sin `checkout_url` o no pendiente → el cobro **sí** se
  registra y se lanza `PaymentsUnavailableError`; una violación única al registrar (carrera) → se lee el cobro
  existente y se devuelve su checkout con `created=False`; la clave de idempotencia es la de
  `billing_rules.idempotency_key`; el importe y el periodo nunca vienen de fuera.
- [X] T041 [P] [US2] Prueba (debe fallar) `tests/contract/test_subscription_periods_api.py` (parte pago;
  `slow`): `POST /api/v1/subscription-periods/{id}/payments` responde 201 con `checkout_url`, `amount`,
  `currency` y `billing_period`; la simulación de Pagos recibió exactamente una creación con 49900/`MXN`/
  referencia/`Idempotency-Key` y el token de la persona; la tabla `subscription_charges` tiene un cobro
  `pending` con los valores registrados; repetirlo → 200 con el mismo checkout y **un** solo cobro y **un**
  solo pago en Pagos; un cuerpo con `{"amount": 1, "currency": "USD", "billing_period": "annual"}` se ignora
  (se cobra lo del catálogo); importe 0.00 → 409 `nothing_to_charge` y Pagos no recibe nada; Pagos caído →
  503 `payments_unavailable` y sin cobros; cobro cerrado (rechazado en la simulación y consultado) → un nuevo
  inicio da 201 con otro checkout; en prueba y al corriente también se acepta; dos inicios simultáneos →
  un solo cobro; `Cache-Control: no-store` en 200 y 201.

### Implementation for User Story 2

- [X] T042 [US2] Implementar en `src/services/subscription_period_service.py` `PaymentStart`
  (`checkout_url`, `amount`, `billing_period`, `created`) y `start_payment(token, organization_id)`: reutiliza
  los pasos 1 a 3 de `get_status` (extraídos a un método privado que devuelve organización, plan, periodo e
  importe), rechaza el importe 0.00 con `NothingToChargeError`, busca `find_pending` con las mismas condiciones
  (`settles_due_at` = la fecha de pago vigente, periodo de cobro, importe) y, si existe, obtiene su pago con
  `get_payment` y devuelve su `checkout_url` (`created=False`; si Pagos falla o no trae checkout →
  `PaymentsUnavailableError`); si no, calcula `attempt = count_resolved_with_terms + 1`, la clave con
  `idempotency_key`, llama a `create_payment` (descripción «Suscripción {plan} — mensual|anual», `metadata`
  `{"billing_period", "settles_due_at"}`), registra el cobro con `add_charge` y devuelve `created=True`; la
  violación única (`UniqueViolationError`) se resuelve leyendo el cobro pendiente existente (`created=False`);
  `PaymentsApiUnavailable` en `create_payment` → `PaymentsUnavailableError` sin registrar nada; un pago sin
  checkout o no pendiente se registra y luego lanza `PaymentsUnavailableError`. Sin conciliación todavía (US3).
- [X] T043 [US2] Añadir al router `create_subscription_payment` en `POST /{organization_id}/payments`
  (`operation_id="create_subscription_payment"`, `status_code=201` por omisión y 200 cuando `created` es falso
  poniéndolo en `response.status_code`, `**protected(SUBSCRIPTION_PERIODS_WRITE, responses={200: …, 201: …,
  404: …, 409: …, 422: …, 503: …})` con los ejemplos del contrato, `Cache-Control: no-store`, **sin cuerpo**: no
  declara ningún parámetro de cuerpo, así que cualquier cuerpo se ignora) y su descripción en español (no recibe
  importe, idempotente por periodo, 409 sin cobro, 503 sin cobro registrado) con «Permiso requerido:
  `subscription_periods:write`.».
- [X] T044 [US2] Comprobar la historia: las dos pruebas de US2 en verde (`uv run pytest
  tests/unit/test_subscription_period_service.py` y `uv run pytest tests/contract/test_subscription_periods_api.py
  -m ""`).

**Checkpoint**: se puede iniciar el pago y obtener el checkout.

---

## Phase 5: User Story 3 - La fecha del siguiente pago se mueve, una sola vez, cuando el pago se aprueba (Priority: P1)

**Goal**: Conciliar los cobros pendientes con Pagos antes de responder (consulta e inicio del pago), aplicar los
aprobados exactamente una vez y cerrar los demás; solo cuentan los cobros que la API inició.

**Independent Test**: Con Pagos simulado, iniciar un pago, aprobarlo en la simulación y consultar: la fecha se
mueve; consultar otra vez y a la vez: no cambia; rechazar otro: se cierra; crear un pago directamente en Pagos:
no tiene efecto.

### Tests for User Story 3 ⚠️

- [X] T045 [P] [US3] Prueba (debe fallar) `tests/unit/test_subscription_period_service.py` (parte conciliación):
  escenarios 1 a 11 de la historia 3 y los ejemplos 7 a 11 de referencia: aprobado en prueba → `paid_until` =
  fin de la prueba + 1 mes y el estado sigue `trial`; vencida → periodo desde la aprobación y `current`; anual;
  fin de mes (31 ene → 28 feb); aprobado antes de la fecha pero detectado después → cuenta como a tiempo
  (usa `updated_at` del pago, acotado al reloj: un `updated_at` futuro se trata como «ahora»); una segunda
  consulta no mueve la fecha; `rejected`/`cancelled` → cobro `closed` (motivo `rejected`/`cancelled`) sin mover
  fechas y `payment_in_progress` `False`; `approved` con otro importe, otra moneda o otra referencia →
  `closed`/`inconsistent` con un `WARNING` (sin token ni datos personales) y sin mover fechas;
  `partially_refunded`/`refunded` sin aplicar → `closed`/`refunded`; `pending` → sigue y
  `payment_in_progress` `True`; dos cobros aprobados se aplican **en orden de creación** y el segundo continúa
  donde termina el primero; un `STALE` del Repository provoca relectura y reintento (hasta `MAX_APPLY_ATTEMPTS`)
  y un `ALREADY_RESOLVED` no hace nada; un pago creado directamente en `FakePaymentsApi` y no registrado nunca
  aparece; la conciliación consulta a Pagos **todos los pendientes a la vez** con el token recibido; el inicio
  del pago concilia **antes** de calcular el periodo (un cobro aprobado se aplica y el cobro nuevo, si se crea,
  es para la fecha siguiente: historia 2, escenario 9) y reutiliza el `checkout_url` ya verificado sin una
  segunda consulta.
- [X] T046 [P] [US3] Prueba (debe fallar) `tests/contract/test_subscription_periods_api.py` (parte aprobación;
  `slow`): iniciar el pago, `set_payment_status(..., "approved")`, consultar → `payment_due_at` movido y estado
  correcto, el cobro `applied` con el periodo cubierto y `paid_until` en la tabla; una segunda consulta no la
  mueve; rechazado → cobro `closed` y un nuevo inicio da 201 con otro checkout; aprobado con otro importe → no
  se aplica; un pago creado «por otra vía» con la misma referencia y aprobado no mueve nada; con el reloj
  movido, el pago aprobado antes de la fecha y consultado después cuenta como a tiempo; Pagos sin cambios →
  `payment_in_progress` `true`.
- [X] T047 [P] [US3] Prueba (debe fallar) `tests/contract/test_subscription_periods_concurrency.py` (`slow`): 20
  consultas simultáneas (`asyncio.gather` sobre el mismo cliente) tras aprobar un cobro → todas responden 200
  con la misma `payment_due_at`, el cobro queda `applied` **una** vez y `paid_until` se movió una sola vez
  (SC-005); 20 primeras consultas simultáneas de una organización → una sola fila; dos cobros distintos
  aprobados y 10 consultas simultáneas → ambos `applied` y `paid_until` = fin del segundo.

### Implementation for User Story 3

- [X] T048 [US3] Implementar en `src/services/subscription_period_service.py` la conciliación `_reconcile(token,
  period)`: lee `list_pending`; consulta **todos** con `asyncio.gather(..., return_exceptions=True)` y
  `payments_api.get_payment`; por resultado: `PaymentsApiUnavailable` → no verificable (`unverified`);
  cualquier otra excepción se relanza; `pending` → verificado pendiente (guarda su `PaymentRecord` para
  reutilizar el `checkout_url`); `approved` → si `id`, `amount` (== `to_minor_units(charge.amount)`), `currency`
  y la referencia (`resource_type` == `RESOURCE_TYPE`, `resource_id` == `str(organization_id)`) coinciden, se
  aplica (`_apply`), si no se cierra `inconsistent` con `logger.warning("Charge %s of organization %s closed as
  inconsistent")`; `rejected` → `close_charge(..., "rejected")`; `cancelled` → `"cancelled"`;
  `partially_refunded`/`refunded` → `"refunded"`. `_apply`: hasta `MAX_APPLY_ATTEMPTS` veces relee el periodo,
  calcula `covered_period(payment_due_at(...), min(payment.updated_at, now), charge.billing_period)` y llama a
  `apply_charge` con `expected_paid_until` = el `paid_until` leído; `STALE` reintenta, `ALREADY_RESOLVED` y
  `APPLIED` terminan. Se aplican en orden de creación, uno por uno. Devuelve el periodo vigente, los pagos
  pendientes verificados y `unverified`. `payment_in_progress` = `True` si hay pendiente verificado, si no `None`
  si `unverified`, si no `False` (FR-015). Cablearla en `get_status` y `start_payment` **antes** de calcular el
  estado/periodo (con el periodo releído después de conciliar). `tests/unit/test_subscription_period_service.py`
  pasa entero.
- [X] T049 [US3] Comprobar la historia: `uv run pytest tests/unit/test_subscription_period_service.py` y
  `uv run pytest tests/contract/test_subscription_periods_api.py tests/contract/test_subscription_periods_concurrency.py -m ""`
  en verde.

**Checkpoint**: el ciclo consultar → pagar → ver la fecha movida funciona, una sola vez.

---

## Phase 6: User Story 4 - Solo el Dueño de la organización puede consultar y pagar (Priority: P1)

**Goal**: Comprobar y fijar el control de acceso: token, permiso exacto, Dueño (Clínicas) y orden de las
comprobaciones. Esta fase **no añade código de producción** salvo lo que las pruebas descubran que falta: el
acceso ya lo implementan `protected(...)` (US1/US2) y el Service (Clínicas).

**Independent Test**: Probar ambas operaciones sin token, con token inválido, sin permiso, con solo lectura al
iniciar el pago, sobre otra organización, con Usuarios o Clínicas caídos y con un identificador inválido; solo el
Dueño con el permiso sobre su organización obtiene respuesta.

### Tests for User Story 4 ⚠️

- [X] T050 [P] [US4] Prueba `tests/contract/test_subscription_periods_access_control.py` (`slow`, parametrizada
  por las dos operaciones donde aplique): sin token y con un esquema distinto de Bearer → 401
  `unauthenticated`; token inválido → 401 `invalid_token`; token vencido → 401 `token_expired`; sin el permiso
  → 403 `permission_denied` cuyo mensaje nombra el permiso de **esa** operación; solo `:read` al iniciar el
  pago → 403 (`…:write`); `:write` solo no consulta; organización de otra persona o inexistente → 404
  `organization_not_found` **idéntico** (mismo cuerpo salvo el identificador) y sin fila en
  `subscription_periods`; Clínicas caída, lenta, 401, 403, 5xx, redirección o cuerpo inesperado → 503
  `organization_check_unavailable` sin crear nada; Usuarios caído → 503 `authorization_unavailable` sin
  consultar Clínicas ni Pagos; **orden**: sin permiso + identificador inválido → 403 (no 422), sin token +
  inválido → 401, Usuarios caído + inválido → 503, con permiso + inválido → 422 con
  `{"field": "organization_id", "message": "El identificador de la organización debe ser un UUID."}`; permiso
  revocado (`set_permissions`) surte efecto en la siguiente petición; cada petición hace **una** consulta de
  permiso, exacta, con el token recibido; el token no aparece en ninguna respuesta de error; la API publica su
  contrato sin token e indica el permiso de cada operación (`x-required-permission`).
- [X] T051 [P] [US4] Ajuste A1 en `tests/contract/test_permission_coverage.py`: `EXPECTED_PERMISSIONS` y
  `REQUESTS` suman `get_subscription_period` (`GET /api/v1/subscription-periods/{ORG}`) y
  `create_subscription_payment` (`POST …/payments`); la fixture `seeded` registra en la simulación de Clínicas
  la organización de `REQUESTS` con `owner_token=TEST_TOKEN` y un plan con precio (el «Base» ya inserta uno de
  100.00); `snapshot` incluye `subscription_periods` y `subscription_charges`. Las pruebas parametrizadas
  existentes (401, 403, 503, permiso exacto) deben pasar con las **15** operaciones. Ninguna aserción se
  debilita.
- [X] T052 [P] [US4] Prueba `tests/contract/test_subscription_periods_openapi.py` (`slow`
  no necesario si usa `create_app().openapi()` sin base): el OpenAPI generado tiene las dos operaciones con sus
  `operationId`, la etiqueta `subscription-periods`, `security` `BearerAuth`, `x-required-permission`
  (`subscription_periods:read` y `:write`), parámetro de ruta `organization_id` de tipo `string/uuid`, las
  respuestas 200/201/401/403/404/409/422/503/500 documentadas, los esquemas `SubscriptionPeriodRead` (nueve
  campos obligatorios) y `SubscriptionPaymentRead`, el encabezado `Cache-Control` en las respuestas correctas,
  descripciones en español y «Permiso requerido: …»; los códigos de error del esquema `ErrorResponse` incluyen
  los cinco nuevos; coincide con [contracts/openapi-subscription-periods.yaml](contracts/openapi-subscription-periods.yaml)
  en operaciones, permisos y códigos; todas las operaciones de la API (salvo las cuatro de salud públicas)
  declaran `security` y permiso.

### Implementation for User Story 4

- [X] T053 [US4] Corregir en el código de producción **solo lo que T050 a T052 descubran que falta o no coincide**
  (por ejemplo cabeceras, ejemplos de OpenAPI, el orden de las comprobaciones o un mensaje); lo normal es que
  no haga falta nada. Anotar en el resumen final qué se corrigió.
- [X] T054 [US4] Comprobar la historia: `uv run pytest tests/contract/test_subscription_periods_access_control.py
  tests/contract/test_permission_coverage.py tests/contract/test_subscription_periods_openapi.py -m ""` en verde.

**Checkpoint**: el MVP completo (US1 a US4) está protegido y verificado.

---

## Phase 7: User Story 5 - Los cambios de plan no reescriben el pasado (Priority: P2)

**Goal**: Fijar con pruebas que un cambio de plan o de periodo de cobro no mueve fechas ya fijadas y que el
siguiente cobro usa lo vigente; el estatus del plan no afecta al cobro.

**Independent Test**: Con una organización ya consultada, cambiar su plan y su periodo de cobro en la simulación
y los días de prueba en el catálogo; las fechas son las mismas y el plan y el importe informados son los nuevos.

### Tests for User Story 5 ⚠️

- [X] T055 [P] [US5] Prueba `tests/unit/test_subscription_period_service.py` (parte cambios de plan) y
  `tests/contract/test_subscription_periods_api.py` (parte cambios de plan; `slow`): escenarios 1 a 5 de la
  historia 5: plan nuevo con otros `trial_days` → mismo `trial_ends_at` y plan nuevo en la respuesta; mensual →
  anual → misma `payment_due_at` e importe anual; un cobro mensual pendiente aprobado después del cambio a anual
  mueve **un mes** (el periodo con que se registró); un plan Inactiva, Bloqueada o Eliminada se usa igual (precio
  y días de prueba) tanto al consultar como al iniciar el pago; un plan que no existe en el catálogo → 409
  `organization_subscription_not_found` en ambas operaciones, sin registro nuevo y sin llamar a Pagos; plan que
  cambia a uno con importe 0.00 → `no_charge` (y de vuelta a uno de pago, la fecha ya fijada que puede estar
  vencida); dos tarifas con una sola en 0.00 → `no_charge` solo con ese periodo de cobro.

### Implementation for User Story 5

- [X] T056 [US5] Corregir en `src/services/subscription_period_service.py` y `src/repositories/
  subscription_repository.py` **solo lo que T055 descubra que falta** (lo normal: nada, porque FR-033 y FR-034 ya
  se cumplen por diseño: las fechas se fijan al crear el registro y el plan se lee sin filtrar el estatus).
  Anotar en el resumen final qué se corrigió.
- [X] T057 [US5] Comprobar la historia: las pruebas de T055 en verde.

**Checkpoint**: los cambios de plan se comportan como la spec manda.

---

## Phase 8: User Story 6 - Si falla un API ajeno, se degrada sin inventar nada (Priority: P2)

**Goal**: Cada celda de la tabla de degradación (Usuarios, Clínicas, Pagos × consultar, iniciar el pago) y la
higiene de errores (nada interno llega al cliente).

**Independent Test**: Con simulaciones que fallan una por una, comprobar cada celda y que ninguna respuesta
contiene direcciones, cuerpos de error ni credenciales.

### Tests for User Story 6 ⚠️

- [X] T058 [P] [US6] Prueba `tests/contract/test_subscription_periods_degradation.py` (`slow`, parametrizada por modo
  de falla: `unavailable`, `unauthorized`, `forbidden`, `organization_required`, `malformed`, `not_json`,
  `redirect`, `slow` con un tiempo de integración de 0.2 s, `unknown_status`): Usuarios y Clínicas fallan →
  503 en consulta e inicio y **nada** se crea ni cambia (snapshots de ambas tablas); Clínicas responde 200
  sin `billing_period` o con uno inválido → 503 `organization_check_unavailable` (no se supone «mensual»);
  Pagos falla al consultar con un cobro pendiente → 200 con `payment_in_progress` `null` y las fechas, el
  estado y el importe calculados con lo guardado; Pagos falla pero **no hay** cobros sin resolver → respuesta
  normal con `payment_in_progress` `false` y la simulación de Pagos no recibe llamadas; Pagos devuelve algo
  inesperado (404, estatus desconocido, cuerpo ilegible) sobre un cobro → ese cobro sigue `pending` y la
  consulta responde `null`; Pagos falla al iniciar el pago → 503 `payments_unavailable` y la tabla de cobros
  no gana filas; con varios cobros, uno verificable pendiente y otro no → `payment_in_progress` `true`; en
  ninguna respuesta ni en `caplog` aparece la marca `SECRETO-INTERNO`, el token, una dirección de otro API ni
  su cuerpo; los mensajes están en español y los códigos en inglés.
- [X] T059 [P] [US6] Prueba `tests/unit/test_subscription_period_service.py` (parte degradación) con los dobles:
  las mismas celdas sin base de datos, incluida la regla de que `PaymentsApiUnavailable` en una consulta
  nunca se convierte en error, y que una excepción de programación (por ejemplo `RuntimeError` en
  `get_payment`) **no** se traga (se propaga como 500).

### Implementation for User Story 6

- [X] T060 [US6] Corregir solo lo que T058 y T059 descubran que falta (la degradación ya está en el diseño de
  `_reconcile`, `get_organization` y `start_payment`). Anotar en el resumen final qué se corrigió.
- [X] T061 [US6] Comprobar la historia: las pruebas de T058 y T059 en verde.

**Checkpoint**: la degradación está fijada y probada.

---

## Phase 9: User Story 7 - Quien opera el servicio configura la fecha de corte, Pagos y el origen del frontend (Priority: P2)

**Goal**: Configuración documentada y validada al arrancar, advertencia de la dirección sin cifrar, CORS para el
frontend y despliegue.

**Independent Test**: Arrancar con la configuración válida, con la fecha de corte ausente o inválida, sin la
dirección de Pagos, con una dirección de Pagos `http://` no local y con un origen permitido y otro no.

### Tests for User Story 7 ⚠️

- [X] T062 [P] [US7] Prueba `tests/unit/test_billing_startup.py` (escenarios 1 a 7 de la historia 7; sin
  PostgreSQL): `lifespan` con la configuración completa arranca; sin `BILLING_CUTOFF_AT`, con una fecha sin
  zona o con texto → `RuntimeError` cuyo mensaje nombra `BILLING_CUTOFF_AT` y no contiene el valor; sin
  `PAYMENTS_API_BASE_URL` → nombra la variable; **faltando varias a la vez** (por ejemplo `USERS_API_BASE_URL`,
  `PAYMENTS_API_BASE_URL` y `BILLING_CUTOFF_AT`) → **un** solo mensaje que las nombra todas; una dirección de
  Pagos `http://pagos.empresa.com` arranca y registra una advertencia que nombra `PAYMENTS_API_BASE_URL` y
  **no** contiene la dirección; `http://payments-api:8080` y `https://…` no avisan; un cambio de
  `BILLING_CUTOFF_AT` con el servicio en marcha no surte efecto hasta reiniciar (la configuración se lee una
  vez: `get_billing_settings` con caché); `.env.example` documenta `PAYMENTS_API_BASE_URL`,
  `PAYMENTS_API_TIMEOUT_SECONDS` y `BILLING_CUTOFF_AT` (lee el archivo y busca los tres nombres).
- [X] T063 [P] [US7] Prueba de CORS en `tests/contract/test_subscription_periods_access_control.py` (o en
  `tests/unit/test_main.py`-style nuevo `tests/unit/test_billing_cors.py` si no necesita base): con
  `CORS_ALLOWED_ORIGINS=http://front.test`, la petición previa (`OPTIONS`) a
  `/api/v1/subscription-periods/{id}` con `Access-Control-Request-Method: GET` y a `…/payments` con
  `POST`, y `Access-Control-Request-Headers: authorization` responde 200 con `access-control-allow-origin:
  http://front.test` y sin `allow-credentials`; un `GET` desde ese origen trae la cabecera de CORS; desde un
  origen no listado no se habilita ninguno; sin la variable, ninguno. Esta feature no añade variables de CORS.

### Implementation for User Story 7

- [X] T064 [P] [US7] Documentar en `.env.example` (en el bloque «APIs de los que depende este servicio», con el
  estilo de las demás): `PAYMENTS_API_BASE_URL=` (obligatoria; el token de la persona se reenvía a esa
  dirección: usa `https://` salvo en local o Docker), `# PAYMENTS_API_TIMEOUT_SECONDS=5` y
  `BILLING_CUTOFF_AT=` con un comentario que explique que es **obligatoria**, ISO 8601 con zona
  (`2026-11-18T00:00:00Z`), que ningún primer periodo empieza antes, que en el primer despliegue vale el
  instante del despliegue y que las organizaciones existentes con un plan sin prueba vencen ese día (una fecha
  posterior les da margen); y mencionar bajo `CORS_ALLOWED_ORIGINS` que el origen del frontend se agrega ahí.
- [X] T065 [P] [US7] Ajuste A14 en `docker-compose.yml`: el servicio `api` pasa `PAYMENTS_API_BASE_URL:
  ${PAYMENTS_API_BASE_URL:-}`, `PAYMENTS_API_TIMEOUT_SECONDS: ${PAYMENTS_API_TIMEOUT_SECONDS:-}` y
  `BILLING_CUTOFF_AT: ${BILLING_CUTOFF_AT:-}` con comentarios en español; `backfill-subscription-types` y los
  demás servicios no cambian. Validar con `docker compose config -q`.
- [X] T066 [US7] Comprobar la historia: `uv run pytest tests/unit/test_billing_startup.py
  tests/unit/test_billing_config.py` y la prueba de CORS en verde.

**Checkpoint**: la operación del servicio queda configurada y verificada.

---

## Phase 10: User Story 8 - Avanzar sin esperar a los demás APIs (Priority: P2)

**Goal**: Contratos consumidos, simulaciones, pedidos a los otros APIs y la colección de Postman de punta a
punta con sus guardianas.

**Independent Test**: Revisar que existe, por cada API, el contrato consumido y el documento de pedidos con las
cuatro partes; ejecutar la suite sin ningún API real; ejecutar la colección con Newman.

### Tests for User Story 8 ⚠️

- [X] T067 [P] [US8] Prueba `tests/unit/test_pedidos_documents.py` (SC-013, FR-049): existen
  `specs/010-subscription-periods/contracts/pedidos-usuarios.md`, `pedidos-clinicas.md` y `pedidos-pagos.md`;
  cada uno tiene los encabezados «Qué pide el negocio» (para qué), «Lo que te pido» (qué falta y la forma
  propuesta), «Cómo lo usa maily-system-api»/«Cómo lo usará…» y «Qué bloquea», con una tabla de bloqueos que
  no está vacía; los tres contratos consumidos (`users-api-integration.md`, `clinics-api-integration.md`,
  `payments-api-integration.md`) existen y mencionan «Falta» o «Existe»; ningún documento contiene tokens ni
  secretos (`JWT`, `Bearer eyJ`).
- [X] T068 [P] [US8] Prueba `tests/contract/test_periods_postman_collection.py` (reglas G1 a G8 de
  [contracts/e2e-collection.md](contracts/e2e-collection.md), con el patrón de
  `test_health_postman_collection.py`: funciones `check_*` y copias alteradas en memoria que prueban que cada
  regla detecta lo que debe): G1 formato v2.1; G2 operaciones cubiertas en ambos sentidos (los
  `operationId` de las rutas `/api/v1/subscription-periods`; `setup` y `docs` son ayudas); G3 descripciones y
  `pm.test`; G4 estatus 200, 201, 401, 403, 404, 409, 422 y 503; G5 autenticación solo con variables
  (`{{accessToken}}`, `{{ownerToken}}`, `{{readerToken}}`, `{{plainToken}}`, `{{adminToken}}`, `{{badToken}}`);
  G6 sin secretos (la marca de la simulación no se escribe entera: `"SECRE" + "TO-INTERNO"`); G7 alcance
  (simulaciones solo por `/__test__/`; la API solo se escribe con `POST …/payments` y, en preparación y
  limpieza, `POST`/`DELETE` de `/api/v1/subscriptions`); G8 ninguna variable oculta por el entorno; más: las
  ocho carpetas esperadas (`0. Preparación`, `1. Consulta`, `2. Iniciar el pago`, `3. Pago aprobado`, `4. Control
  de acceso`, `5. Degradación`, `6. Contrato`, `7. Limpieza`), el entorno `e2e` tiene `paymentsStubUrl`
  (`http://127.0.0.1:8015`), `package.json` tiene `e2e:periods` (con `junit-periods.xml`) y `e2e:all` lo
  incluye.
- [X] T069 [P] [US8] Ajustes A8 y A12: `tests/contract/postman_support.py` suma `PERIODS_COLLECTION`
  (`collections/MailySoft-System-Periodos.postman_collection.json`), `PERIODS_PREFIX` (`/api/v1/subscription-periods`)
  y `PERIODS_HELPER_PREFIXES` (`{"setup", "docs"}`); `tests/contract/test_dashboard_postman_collection.py` (G9)
  suma la colección de periodos al mapa de colecciones (`prefixes_of_the_collections`, **cinco**) y la prueba
  pasa a «las cinco colecciones juntas cubren exactamente las operaciones de la API». Ninguna otra aserción cambia.

### Implementation for User Story 8

- [X] T070 [US8] Crear `tests/postman/collections/MailySoft-System-Periodos.postman_collection.json` (formato v2.1;
  autenticación `Bearer {{accessToken}}` a nivel de colección; script previo que registra con sufijo aleatorio
  en la simulación de Usuarios `ownerToken` (`subscription_periods:read` y `:write`), `readerToken` (solo
  `:read`), `plainToken` (sin permisos) y `adminToken` (permisos de suscripciones y `modules:read`), y
  `badToken`; ningún token escrito en el archivo) con las **ocho carpetas** y los recorridos de
  [contracts/e2e-collection.md](contracts/e2e-collection.md): preparación (reiniciar las tres simulaciones,
  la API publica las dos operaciones, crear tres planes con `POST /api/v1/subscriptions` y `adminToken`: 14
  días de prueba mensual 499.00/anual 4990.00, sin prueba, y sin cobro; guardar sus identificadores en
  variables), consulta (en prueba con 9 días, misma consulta mismas fechas, vencida con −26, sin prueba, sin
  cobro, anual), iniciar el pago (201 y verificación en Pagos de 49900/`MXN`/referencia, 200 repetido con el
  mismo checkout, cobro en curso, 409 sin cobro), pago aprobado (la fecha se mueve un mes y una segunda
  consulta no la mueve; rechazado y nuevo 201; otro importe no se aplica; pago por otra vía no mueve nada),
  control de acceso (401, 401, 403, 403 por solo lectura, 404, 422, 403 antes de 422, 503 de Usuarios),
  degradación (503 de Clínicas, 503 sin `billing_period`, 200 con `payment_in_progress` `null`, 503 de Pagos sin
  cobro nuevo), contrato (`docs: …`) y limpieza (eliminar los tres planes y reiniciar). Cada organización se
  da de alta en la simulación de Clínicas con `created_at` calculado con `Date` (hace 5, 40 días, 1 hora) y su
  Dueño (`ownerToken`); cada petición con nombre `<operationId>: …` o `setup: …`/`docs: …`, descripción en español
  y `pm.test`. Se puede generar con un script de apoyo fuera del repositorio; solo el JSON se versiona.
- [X] T071 [P] [US8] Ajustes A9 a A11: `tests/postman/docker-compose.e2e.yml` (servicio `payments-api-stub` con la
  imagen del proyecto, volumen `./tests/stubs/payments_api:/stub:ro`, puerto `127.0.0.1:${E2E_PAYMENTS_STUB_PORT:-8015}:8080`
  y el mismo `healthcheck`; la `api` depende de él y recibe `PAYMENTS_API_BASE_URL: http://payments-api-stub:8080`
  y `BILLING_CUTOFF_AT: "2020-01-01T00:00:00Z"`; el comentario de la cabecera menciona las cuatro simulaciones);
  `tests/postman/environments/e2e.postman_environment.json` (clave `paymentsStubUrl` = `http://127.0.0.1:8015`);
  `tests/postman/package.json` (`e2e:periods` con `reports/junit-periods.xml` y `e2e:all` = `npm run e2e && npm run
  e2e:dashboard && npm run e2e:health && npm run e2e:periods`). Validar con `docker compose -f docker-compose.yml
  -f tests/postman/docker-compose.e2e.yml config -q`.
- [X] T072 [US8] Comprobar la historia: `uv run pytest tests/unit/test_pedidos_documents.py
  tests/contract/test_periods_postman_collection.py tests/contract/test_dashboard_postman_collection.py` en
  verde. La ejecución real con Newman es parte de la fase 12.

**Checkpoint**: la colección, la pila y los documentos están listos.

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Documentación, esquema objetivo y verificación global.

- [X] T073 [P] Actualizar `project-definition/DATA_SCHEMA.md` con las dos tablas, sus restricciones, el índice y los
  disparadores, cada bloque con el comentario `-- [spec 010-subscription-periods]` (siguiendo el formato de
  `-- [spec 005-health-monitoring]`), y ampliar su tabla «Nombres de restricciones de los que depende el
  código» con `subscription_charges_payment_id_key` y `subscription_charges_terms_attempt_key`. Debe coincidir
  con [contracts/database-schema.sql](contracts/database-schema.sql).
- [X] T074 [P] Actualizar `README.md`: en «Qué incluye hoy» una sección «Periodos de suscripción» (qué hace, las dos
  operaciones, los cuatro estados, que la primera consulta crea el registro y aplica los cobros aprobados, que
  contra los servicios reales hacen falta los pedidos a Usuarios, Clínicas y Pagos con enlaces a
  `specs/010-subscription-periods/contracts/pedidos-*.md`); en «Configuración» las filas `PAYMENTS_API_BASE_URL`
  (obligatoria), `PAYMENTS_API_TIMEOUT_SECONDS` y `BILLING_CUTOFF_AT` (obligatoria; qué hace y por qué), el
  párrafo «Seguridad de las direcciones» ahora con **tres** direcciones, la nota de que el origen del frontend
  va en `CORS_ALLOWED_ORIGINS`; en «Pruebas» la guía `specs/010-subscription-periods/quickstart.md`; en «Pruebas de
  punta a punta» la cuarta colección (`e2e:periods`, la pila con **cuatro** simulaciones y el puerto `:8015`) y
  que G9 comprueba las cinco; en «Estructura» los archivos nuevos. Quitar «las tres colecciones» donde ya no
  sea cierto.
- [X] T075 [P] Revisar `src/main.py`: el párrafo nuevo de `DESCRIPTION` y la etiqueta `subscription-periods` de
  `OPENAPI_TAGS` están en español y dicen qué hace el recurso (estados, que informa y cobra pero no bloquea, que
  el importe lo calcula la API, que las fechas van en UTC); `app.version` es `4.1.0`.
- [X] T076 Barrido de trazabilidad: para cada requisito FR-001 a FR-054 y SC-001 a SC-013 de [spec.md](spec.md)
  comprobar (con `grep` en `src/` y `tests/`) que hay código y al menos una prueba que lo cubra; anotar en el
  resumen final cualquier hueco y cerrarlo. Comprobar también que no quedó código muerto (por ejemplo la
  conciliación sin llamarse) ni `print`, `TODO` o `FIXME` nuevos (`grep -rn "print(\|TODO\|FIXME" src`).
- [X] T077 Revisar que el código nuevo cumple las capas y el idioma: `uv run pytest tests/unit/test_layering.py`,
  identificadores en inglés, mensajes en español, docstrings y comentarios en inglés, sin `float` en importes
  (`grep -rn "float(" src/services/billing_rules.py src/services/subscription_period_service.py` no encuentra
  nada), sin `datetime.now()` fuera de `src/services/clock.py` (`grep -rn "datetime.now\|utcnow" src` solo lo
  encuentra donde ya estaba).
- [X] T078 Ejecutar la validación del [quickstart.md](quickstart.md) nivel 1: `uv run pytest` (rápido) en verde y
  comparar el número de pruebas con el de T002.

---

## Phase 12: Verificación completa (la puerta de la constitución antes de integrar en `main`)

**Purpose**: Principio V y «Flujo de Desarrollo y Puertas de Calidad»: suite completa, migraciones desde cero,
OpenAPI sin errores, cobertura de permisos, colecciones de Postman y revisión de capas.

- [X] T079 Suite completa con PostgreSQL 17 real: `docker compose up -d db` (si no está) y `uv run pytest -m ""` en
  verde, **sin tests omitidos ni marcados como esperados que fallen**; comparar con la línea base de T003.
- [X] T080 Migraciones desde cero: `uv run alembic downgrade base && uv run alembic upgrade head && uv run alembic
  check` contra la base de pruebas (o la de `docker compose run --rm migrate`) sin diferencias entre modelos y
  migraciones; `uv run alembic downgrade 0007 && uv run alembic upgrade head` también funciona.
- [X] T081 OpenAPI: `uv run python -c "from src.main import create_app; import json; json.dumps(create_app().openapi())"`
  sin errores y `tests/contract/test_subscription_periods_openapi.py` en verde (ya incluido en T079).
- [X] T082 Punta a punta: `npm ci --prefix tests/postman`, levantar la pila aislada (`docker compose -p
  maily-system-e2e -f docker-compose.yml -f tests/postman/docker-compose.e2e.yml up -d --build --wait api`),
  `npm run e2e:all --prefix tests/postman` en verde (las **cuatro** colecciones; salida 0) y desmontar la pila
  (`down -v`). Si la colección nueva falla, corregir la colección o el código y repetir; no se integra con
  Newman en rojo.
- [X] T083 Revisión final de cumplimiento: ejecutar la skill `/code-review` sobre el diff o, si no está
  disponible, una relectura propia del diff completo (`git diff main...HEAD --stat` y los archivos nuevos)
  buscando defectos de lógica (límites de fechas, exactitud de una sola vez, fuga del token o de datos de otros
  APIs, capas, mensajes); corregir lo encontrado y repetir T079 y T082 si el código cambió.

---

## Phase 13: Integración (solicitada por la persona responsable el 2026-11-18)

**Purpose**: Dejar la feature en `main` y limpiar la rama, solo si todo lo anterior está en verde.

- [X] T084 Commit en la rama `010-subscription-periods` siguiendo el estilo del repositorio (`feat(subscription-periods):
  …(spec 010)`, un solo commit con la spec, el plan, las tareas, el código, las pruebas, las colecciones y los
  documentos), con la línea `Co-Authored-By` indicada para este entorno. Preparar con rutas explícitas (`git
  add specs/010-subscription-periods src tests alembic README.md .env.example docker-compose.yml
  project-definition pyproject.toml uv.lock`): **nunca** `.env`, `tests/postman/reports/`, `.venv/`,
  `node_modules/` ni archivos con secretos (revisar `git status` y `git diff --cached --stat`). La identidad del
  commit es la del historial del repositorio (el `git config` local no tiene ninguna) y se pasa solo con `-c
  user.name=… -c user.email=…`, sin modificar la configuración.
- [X] T085 Subir la rama: `git push -u origin 010-subscription-periods`.
- [X] T086 Integrar en `main`: `git fetch origin`, comprobar que `main` no avanzó (`git rev-parse main
  origin/main`); si avanzó, integrar `origin/main` en la rama, repetir T079 y T082 y volver a subir; después
  `git checkout main && git merge --ff-only 010-subscription-periods` (si no es posible el avance rápido,
  `git merge --no-ff` con el mensaje del commit), `git push origin main`. Si `main` rechaza el push
  (protección de rama), abrir un PR con `gh pr create` y fusionarlo con `gh pr merge --merge`.
- [X] T087 Borrar la rama **solo si quedó integrada en `main`**: comprobar con `git merge-base --is-ancestor
  010-subscription-periods origin/main` (código de salida 0) y `git branch --merged origin/main` que la lista;
  entonces `git branch -d 010-subscription-periods` y `git push origin --delete 010-subscription-periods`. Si la
  comprobación falla, **no se borra nada** y se informa.
- [X] T088 Resumen final para la persona responsable: qué se construyó, qué se verificó (suite completa y
  Newman, con sus resultados), los ajustes a pruebas existentes, las interpretaciones por defecto que conviene
  confirmar (las del checklist de la spec), los tres pedidos pendientes para los otros equipos y el estado de
  la rama (integrada y borrada, o por qué no).

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: sin dependencias.
- **Foundational (Phase 2)**: depende de Setup; **bloquea** todas las historias. Dentro de la fase:
  T004 a T008 (versión, errores, permisos) → T009 a T012 (configuración) → T013 y T014 (reglas) en paralelo con
  T015 a T021 (esquema, modelos y Repository; T018 depende de T019) y con T022 a T028 (simulaciones y clientes)
  y T029 y T030 (DTOs); T031 y T032 (infraestructura de pruebas) necesitan T015 a T030; T033 cierra la fase.
- **US1 (Phase 3)**: depende de Foundational. **US2 (Phase 4)** depende de US1 (reutiliza sus pasos y su
  router). **US3 (Phase 5)** depende de US1 y US2 (concilia cobros que US2 crea). **US4 (Phase 6)** depende de
  US1 y US2 (necesita las dos rutas). **US5 (Phase 7)** y **US6 (Phase 8)** dependen de US3. **US7 (Phase 9)**
  depende de US1 y US2 (la prueba de CORS usa las rutas). **US8 (Phase 10)** depende de US1 a US3 (la colección
  recorre los tres flujos).
- **Polish (Phase 11)** depende de las historias deseadas; **Verificación (Phase 12)** de todo lo anterior;
  **Integración (Phase 13)** de la Verificación en verde.

### User Story Dependencies

- **US1 (P1)**: tras Foundational; sin dependencias de otras historias.
- **US2 (P1)**: tras US1 (mismo Service y mismo Router).
- **US3 (P1)**: tras US2; cablea la conciliación en las dos operaciones.
- **US4 (P1)**: tras US2; casi solo pruebas.
- **US5 a US8 (P2)**: tras US3; entre sí independientes salvo lo indicado.

### Within Each Story

- Las pruebas se escriben primero y **deben fallar**; luego el código; luego la comprobación de la historia.
- Modelos → Repository → Service → Router → integración con el resto.

### Parallel Opportunities

- Foundational: T004, T005, T008, T015, T017, T018, T020, T022, T023, T024, T025, T027 y T029 son de archivos
  distintos y se pueden preparar en paralelo; T006/T007, T010 y T014 son los que cierran cada bloque.
- Una vez cerrada la fase fundamental, US1 y la preparación de US7 (T064, T065) y US8 (T067, T069, T071) pueden
  avanzar en paralelo.
- Las pruebas marcadas [P] de una misma historia son de archivos distintos y no dependen entre sí.

---

## Parallel Example: Foundational

```bash
# Pruebas y archivos de bloques distintos que se pueden escribir a la vez:
Task: "Prueba tests/unit/test_billing_rules.py (T013)"
Task: "Modelos src/models/subscription_period.py y subscription_charge.py (T015)"
Task: "Simulación tests/stubs/payments_api/app.py (T022)"
Task: "DTOs tests/unit/test_subscription_period_dtos.py (T029)"
```

---

## Implementation Strategy

### MVP First (US1 a US4)

1. Phase 1: Setup (línea base verde)
2. Phase 2: Foundational (bloquea todo)
3. Phases 3 a 6: US1 → US2 → US3 → US4
4. **STOP and VALIDATE**: el recorrido de punta a punta del `quickstart.md` nivel 4 contra las simulaciones.
5. Seguir con US5 a US8 y el pulido.

### Incremental Delivery

1. Setup + Foundational → la base está lista y la línea base sigue verde.
2. US1 → se puede consultar el estado (sin cobros).
3. US2 → se puede iniciar el pago.
4. US3 → la fecha se mueve una sola vez.
5. US4 → el acceso queda verificado; MVP completo.
6. US5 a US8 → cambios de plan, degradación, configuración y punta a punta.
7. Verificación completa → Integración.

---

## Notes

- [P] tasks = archivos distintos, sin dependencias abiertas.
- [Story] relaciona cada tarea con su historia de [spec.md](spec.md).
- Verificar que las pruebas fallan antes de implementar.
- Ninguna prueba llama a un API real; las simulaciones reproducen los contratos de `contracts/` incluidas las
  piezas pedidas que aún no existen (`billing_period` de Clínicas, `tenant_id` y permisos de Usuarios).
- Evitar: tareas vagas, conflictos en el mismo archivo y dependencias entre historias que rompan su independencia.
