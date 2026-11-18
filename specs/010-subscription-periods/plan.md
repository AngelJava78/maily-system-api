# Implementation Plan: Periodo de prueba y siguiente pago de cada organización («Periodos de suscripción»)

**Branch**: `010-subscription-periods` | **Date**: 2026-11-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/010-subscription-periods/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

La MailySoft System API pasa a ser la **dueña del control** del periodo de prueba y del siguiente pago de cada
organización cliente. Dos operaciones para el Dueño (rol Owner): `GET /api/v1/subscription-periods/{organization_id}`
informa el estado (`trial`, `current`, `overdue` o `no_charge`), cuándo termina la prueba, la fecha del
siguiente pago, los días que faltan, el plan, el periodo de cobro, el importe y si hay un cobro en curso; y
`POST /api/v1/subscription-periods/{organization_id}/payments` inicia el pago: crea el cobro en Pagos con un
importe que calcula la API con su catálogo y devuelve el checkout. Un cobro aprobado en Pagos mueve la fecha
del siguiente pago **exactamente una vez**. Todo con el token del Dueño reenviado a Clínicas (que comprueba
que la organización es suya) y a Pagos; nada de Auth0 ni credenciales de máquina.

Enfoque técnico (decisiones y evidencia en [research.md](research.md)):

- **Rutas (R1)**: recurso `subscription-periods` con la organización como identificador y el cobro como
  subrecurso `payments`; permisos `subscription_periods:read` y `subscription_periods:write`.
- **Reglas puras (R3)**: `services/billing_rules.py` con el estado, los días (división entera con redondeo
  hacia +∞), la aritmética de meses con ajuste al fin de mes y el periodo cubierto; probadas con los 16
  ejemplos de la spec y un reloj fijo, sin base de datos.
- **Dos tablas (R14)**: `subscription_periods` (una fila por organización: inicio, fin de la prueba, pagada
  hasta) y `subscription_charges` (los cobros que la API inició, con su resultado propio); migración `0008`
  reversible. Nada de otro API se copia: la organización, el plan vigente, el periodo de cobro y los pagos se
  piden en cada uso.
- **Una sola vez (R4, R5)**: el periodo se crea con `INSERT … ON CONFLICT DO NOTHING`; un cobro se aplica
  reclamándolo con `UPDATE … WHERE status='pending'` y moviendo `paid_until` con compare-and-swap en **una**
  transacción, sin sostener bloqueos durante las llamadas a Pagos.
- **Idempotencia con Pagos (R6)**: clave determinista (organización + hash de fecha que salda, duración,
  importe e intento); un cobro pendiente con las mismas condiciones se reutiliza (200), uno cerrado permite
  un intento nuevo (201), una carrera de dos inicios la decide una restricción única.
- **Conciliación al consultar (R7)**: antes de responder, los cobros pendientes se verifican en Pagos **en
  paralelo** (Pagos no avisa) y se aplican o cierran según su estatus; la referencia, el importe y la moneda
  deben coincidir; un pago ajeno nunca cuenta.
- **Integraciones (R9, R10)**: `ClinicsApiClient.get_organization` y `PaymentsApiClient`, con validación
  estricta de la respuesta, tiempo máximo total, sin reintentos ni redirecciones; todo lo que no sea
  exactamente lo esperado es «no disponible» (503 o consulta degradada), nunca un dato inventado.
- **Configuración (R11)**: `PaymentsSettings` y `BillingSettings` aparte de `IntegrationSettings` (el script de
  `backfill` de la spec 006 no necesita Pagos); `BILLING_CUTOFF_AT` obligatoria; CORS sin cambios de código.
- **Pruebas (R15 a R19)**: reloj inyectable (el de la spec 005), simulaciones de Clínicas (extendida) y de
  Pagos (nueva), colección de Postman nueva con guardianas, y **catorce ajustes enumerados** a pruebas e
  infraestructura existentes, ninguno de comportamiento.
- **Versión (R20)**: `4.0.0` → `4.1.0` (dos operaciones y cinco códigos de error nuevos, compatibles).
- **Pedidos (R21)**: un documento por API (Usuarios, Clínicas y Pagos) en `contracts/`, listos para enviar.

## Technical Context

**Language/Version**: Python 3.14+ (el entorno de desarrollo ejecuta 3.15.2)

**Primary Dependencies**: las del proyecto, **sin dependencias nuevas** (FastAPI 0.143.x, Pydantic v2 +
pydantic-settings, SQLAlchemy 2.0 async + asyncpg, Alembic, httpx, uvicorn) y la biblioteca estándar
(`calendar`, `hashlib`, `decimal`, `asyncio`). Desarrollo: pytest, pytest-asyncio; herramienta aparte: Newman.

**Storage**: PostgreSQL 17. Dos tablas nuevas (`subscription_periods`, `subscription_charges`) con la
migración `0008`; ninguna tabla existente cambia.

**Testing**: pytest + pytest-asyncio + httpx. Reglas puras con tablas y reloj fijo; Service con dobles de los
dos clientes, del Repository y del reloj; clientes HTTP contra las simulaciones en memoria; Repository y
migración contra PostgreSQL 17 real; endpoints por HTTP con la base real, las tres simulaciones y `FakeClock`
(incluida una prueba de 20 consultas simultáneas); prueba de cobertura de permisos; Postman/Newman contra la
pila aislada. `/speckit-implement` corre solo el nivel rápido (sin PostgreSQL).

**Target Platform**: contenedor Linux (Docker Compose, imagen `python:3.14-slim`); la pila de punta a punta
gana la simulación de Pagos.

**Project Type**: web-service

**Performance Goals**: el estado aparece en < 3 s en el 95 % de las consultas (SC-001) suponiendo que cada
API ajeno responde en < 500 ms; costo propio: 1 consulta de permiso, 1 lectura de Clínicas, N consultas a
Pagos **en paralelo** (N = cobros pendientes, hasta 5 en el objetivo) y un puñado de consultas a la base.

**Constraints**: falla cerrada en el acceso (permiso y Dueño) antes de crear o cambiar nada; efecto inmediato
de bloqueos y cambios de permisos (sin caché de decisiones); un cobro mueve la fecha exactamente una vez
(también con peticiones simultáneas); sin tareas programadas ni procesos en segundo plano; ningún valor
inventado cuando un API ajeno falla; el token nunca se guarda, se registra ni sale en respuestas; las
respuestas 200 y 201 declaran `Cache-Control: no-store`; ninguna prueba automatizada llama a un API real; no
cambia el comportamiento ni el contrato de las operaciones existentes.

**Scale/Scope**: 2 operaciones (`get_subscription_period`, `create_subscription_payment`); 2 tablas y 1
migración; 5 códigos de error nuevos (17 → 22); 3 variables de entorno nuevas; 8 módulos nuevos en `src/` y 11
modificados de forma aditiva; 1 simulación nueva (Pagos) y 1 extendida (Clínicas); 1 colección de Postman
nueva; 14 ajustes a pruebas e infraestructura existentes; 3 documentos de pedidos a otros APIs.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio / regla | Evaluación inicial | Tras diseño (Fase 1) |
|---|---|---|
| I. Capas estrictas y código en `src/` | ✅ | ✅ Todo en las carpetas existentes ([R2](research.md)). Router: valida con DTOs, llama al Service y serializa (`Cache-Control`, 200/201). Service: orquesta Clínicas, catálogo, registro y Pagos; las reglas puras van a `billing_rules.py` (sin E/S); no importa `fastapi` ni `sqlalchemy`, por eso el SQL (creación única, reclamación del cobro, compare-and-swap) vive en el Repository. Integraciones: solo HTTP y validación de la forma, con `dataclass` propios (no importan DTOs ni modelos). `test_layering.py` lo vigila sin cambios: no hay carpeta ni módulo raíz nuevos |
| II. Modelos ≠ DTOs | ✅ | ✅ `SubscriptionPeriod` y `SubscriptionCharge` (ORM) separados de `SubscriptionPeriodRead`, `SubscriptionPaymentRead` y `PlanRead`; los DTOs de salida no llevan tokens, identificadores de pago ni datos ajenos; la organización, el plan vigente y el periodo de cobro son campos de solo lectura de la respuesta, no columnas ([data-model.md](data-model.md)) |
| III. Asincronía | ✅ | ✅ httpx y SQLAlchemy async en todo el camino; los cobros pendientes se consultan con `asyncio.gather`; `hashlib` y `calendar` son cálculo puro, sin E/S |
| IV. OpenAPI y REST | ✅ | ✅ [openapi-subscription-periods.yaml](contracts/openapi-subscription-periods.yaml): recurso plural bajo `/api/v1`, `POST` que crea (201) o devuelve el cobro pendiente (200), 401/403/404/409/422/503 con ejemplos en español y el cuerpo de error uniforme; sin listados, así que no aplica la paginación. **Observación**: el `GET` de consulta tiene un efecto acotado e idempotente (crea el registro y aplica cobros ya decididos en Pagos) porque la spec lo ordena (reglas 1 y «antes de responder… aplica los aprobados»); se justifica en Complexity Tracking C1 |
| V. Pruebas pytest | ✅ | ✅ Service con dobles; Repository y migración contra PostgreSQL 17 real; cada endpoint por HTTP con cliente async; las simulaciones de Usuarios, Clínicas y Pagos reproducen sus contratos **y fallas**; la prueba de cobertura recorre las 15 operaciones protegidas y las 8 públicas; los niveles rápido/lento y Postman se organizan como manda el principio ([R17](research.md#r17-pruebas-principio-v)) |
| VI. Migraciones Alembic | ✅ | ✅ Migración `0008` reversible ([database-schema.sql](contracts/database-schema.sql)); importes `NUMERIC(10,2)` y `Decimal`, nunca `float`; modelos consistentes con `test_models_match_migrations.py`; cambio declarado en la spec (FR-043) y en [data-model.md](data-model.md) con su diferencia respecto al esquema vigente; `DATA_SCHEMA.md` lo refleja con `-- [spec 010-subscription-periods]`; sin datos iniciales |
| VII. Idioma | ✅ | ✅ Rutas, campos, estados, permisos y códigos en inglés; mensajes, OpenAPI y documentos en español; comentarios y docstrings en inglés |
| VIII. Control de acceso delegado | ✅ | ✅ Token reenviado sin modificar al API de usuarios, permiso exacto por operación, por petición, sin caché y falla cerrada (401/403/503), **antes** de validar `organization_id` y de consultar Clínicas (FastAPI resuelve la seguridad antes que los parámetros de ruta; [R12](research.md#r12-errores-nuevos-y-precedencia-fr-004-fr-045)); `BearerAuth` + `x-required-permission`; dependencias en `src/security.py` que pasan por `AuthorizationService`. Filas nuevas en la [matriz](contracts/permission-matrix.md) sin alterar las existentes. **Sin Auth0 ni credenciales de máquina**: a Clínicas y a Pagos solo se reenvía el token de la persona (FR-005). Sin secretos ni tokens en la base de datos, las respuestas ni los registros. Sin desviación (es un `GET` sin cuerpo y un `POST` que ignora su cuerpo) |
| IX. Integraciones | ✅ | ✅ La organización, el plan vigente, el periodo de cobro y los pagos **no se copian**: la base guarda solo el identificador de la organización como referencia y lo que la propia API pidió (importe, moneda, periodo). Llamadas asíncronas, con tiempo máximo total, sin reintentos automáticos y sin redirecciones; direcciones y tiempos desde variables de entorno; fallas traducidas a códigos propios en inglés con mensaje en español, sin filtrar cuerpos ni direcciones. Degradación definida ([R8](research.md#r8-degradación-fr-035-a-fr-038-historia-6)): el acceso falla cerrado (Clínicas, Usuarios) y Pagos solo degrada la verificación de un cobro en curso. Contratos consumidos documentados ([clinics](contracts/clinics-api-integration.md), [payments](contracts/payments-api-integration.md), [users](contracts/users-api-integration.md)) y simulados |
| Stack obligatorio | ✅ | ✅ Solo tecnologías de la tabla; sin dependencias nuevas |
| Configuración por entorno, sin secretos | ✅ | ✅ `PAYMENTS_API_BASE_URL`, `PAYMENTS_API_TIMEOUT_SECONDS` y `BILLING_CUTOFF_AT` validadas al arrancar en el mismo mensaje que las demás; los mensajes nombran la variable y nunca su valor; ningún secreto nuevo |
| Docker y Compose | ✅ | ✅ `docker-compose.yml` pasa las variables nuevas al servicio `api`; la pila e2e suma la simulación de Pagos y sigue aislada |
| Flujo y puertas de calidad | ✅ | ✅ Este plan incluye el Constitution Check; la matriz «operación → permiso» y la colección de Postman se actualizan **en el mismo cambio** que la API; puertas comprobables en el [quickstart](quickstart.md) (suite completa con `-m ""` y Newman antes de integrar en `main`) |

**Resultado**: PASS contra los principios I a IX, **sin enmendar la constitución**. Un punto a justificar
(C1, el `GET` con efecto acotado) y ninguna violación; el servicio es hoy «suscripciones, dashboard y salud»
y esta feature añade el cobro de la suscripción dentro del mismo dominio.

## Ajustes a las pruebas existentes (FR-053)

Las pruebas de comportamiento de suscripciones, dashboard y salud **quedan intactas**. El barrido (`grep` de
conteos de códigos de error, versión, `PUBLIC_ROUTES`, operaciones, arranque del `lifespan`, colecciones de
Postman y fixtures compartidas) encontró lo siguiente; todo se ajusta solo para **reconocer lo nuevo**:

| Id | Archivo | Ajuste | Por qué |
|---|---|---|---|
| A1 | `tests/contract/test_permission_coverage.py` | `EXPECTED_PERMISSIONS` y `REQUESTS` suman las dos operaciones (**15**); la fixture `seeded` registra una organización en la simulación de Clínicas (Dueño = `TEST_TOKEN`) y `snapshot` incluye `subscription_periods` y `subscription_charges` | La prueba exige igualdad exacta con el OpenAPI y recorre cada operación con la base real; «no cambia nada» pasa a vigilar también las tablas nuevas. Ninguna aserción se debilita |
| A2 | `tests/contract/test_openapi_contract.py` | `test_the_error_codes_are_the_seventeen_of_the_catalog` → 22 (se renombra); el literal de la versión `4.0.0` → `4.1.0` | Fija el número de códigos y la versión publicada |
| A3 | `tests/unit/test_error_messages.py` | El conjunto exacto de códigos suma los cinco nuevos (se renombra `…seventeen…` → `…twenty_two…`) | Fija el conjunto exacto |
| A4 | `tests/unit/test_dashboard_messages.py`, `tests/unit/test_health_messages.py`, `tests/contract/test_dashboard_openapi.py`, `tests/contract/test_health_openapi.py` | `len(ErrorCode) == 17` → 22 (con el mismo comentario de que la spec 010 añadió 5, sin impacto en lo que cada una verifica) | Ídem |
| A5 | `tests/unit/test_main.py`, `tests/unit/test_health_settings.py`, `tests/contract/test_dashboard_openapi.py` | El literal `4.0.0` → `4.1.0` (junto con `src/__init__.py`, `pyproject.toml` y `uv.lock`) | `test_version.py` exige que la versión coincida en todos los sitios |
| A6 | `tests/conftest.py` | (i) fixture `autouse` `billing_environment` que define `PAYMENTS_API_BASE_URL` y `BILLING_CUTOFF_AT` para todas las pruebas y limpia las cachés de sus configuraciones; (ii) la fixture `api` suma la simulación de Pagos y vacía también las dos tablas nuevas al terminar; (iii) fixture nueva `billing_api` con `FakeClock` | Las pruebas que arrancan el `lifespan` (`test_main`, `test_config`, `test_health_startup`, `test_dashboard_startup`) fallarían sin las variables obligatorias nuevas, y no se editan |
| A7 | `tests/helpers.py` | `Api` acepta `payments_stub` (parámetro nuevo al final) y gana `payments_calls`, `payments_fault` y `register_organization`; `clinics_fault` acepta `operation` (por omisión, `counts`) | Las pruebas de la API necesitan la simulación nueva sin cambiar las llamadas existentes |
| A8 | `tests/contract/test_dashboard_postman_collection.py` | G9: el mapa de colecciones suma la de periodos (`prefixes_of_the_collections`, **cinco**); «las cinco colecciones juntas» | La cobertura conjunta debe incluir la colección nueva con sus dos operaciones |
| A9 | `tests/postman/docker-compose.e2e.yml` | Servicio `payments-api-stub` y las variables `PAYMENTS_API_BASE_URL` y `BILLING_CUTOFF_AT` de la API ([e2e-collection.md](contracts/e2e-collection.md)) | La colección nueva necesita Pagos simulado |
| A10 | `tests/postman/environments/e2e.postman_environment.json` | Clave nueva `paymentsStubUrl` | Ídem |
| A11 | `tests/postman/package.json` | Script `e2e:periods`; `e2e:all` lo incluye | Ídem; `e2e`, `e2e:dashboard` y `e2e:health` no cambian |
| A12 | `tests/contract/postman_support.py` | Constantes `PERIODS_COLLECTION`, `PERIODS_PREFIX` y `PERIODS_HELPER_PREFIXES` | Las guardianas de la colección nueva y G9 las comparten |
| A13 | `tests/stubs/clinics_api/app.py` | `GET /api/v1/organizations/{id}`, `/__test__/organizations`, fallas por operación y `missing_billing_period`/`invalid_billing_period`; el contrato de `subscription-counts` y sus fallas **no cambian** | La simulación de Clínicas debe reproducir también la lectura de la organización |
| A14 | `docker-compose.yml` | El servicio `api` pasa `PAYMENTS_API_BASE_URL`, `PAYMENTS_API_TIMEOUT_SECONDS` y `BILLING_CUTOFF_AT` (vacías = no definidas); `backfill-subscription-types` **no cambia** | Configuración del despliegue |
| A15 | `tests/contract/test_health_postman_collection.py` | El contenido exacto de `scripts["e2e:all"]` suma `&& npm run e2e:periods` (el resto de la prueba no cambia) | A11 añade la colección nueva a `e2e:all` y esa prueba lo fijaba con una igualdad (lo encontró la implementación, no el barrido inicial) |

**Nada se debilita**: A2 a A5 solo cambian un número o un literal que cada prueba fijaba; A1 y A8 amplían
tablas internas sin tocar una aserción; A6 a A7 y A9 a A14 son infraestructura aditiva; A15 solo actualiza un literal que A11 cambia. La prueba de
versión, la de capas y la de cobertura de permisos siguen vigilando lo mismo.

## Documentación y despliegue

- **README**: sección «Periodos de suscripción» (qué hace, las dos operaciones, los estados, la fecha de
  corte y por qué es obligatoria, que contra los servicios reales hacen falta los pedidos a los otros APIs),
  filas nuevas en la tabla de configuración y en las rutas del navegador (CORS), la colección nueva en
  «Pruebas de punta a punta» y la estructura.
- **`.env.example`**: las tres variables nuevas, comentadas, con su significado, el formato y el valor de
  ejemplo; `PAYMENTS_API_BASE_URL` y `BILLING_CUTOFF_AT` obligatorias.
- **`docker-compose.yml`**: A14. La imagen no cambia (`alembic upgrade head` aplica la `0008`).
- **`project-definition/DATA_SCHEMA.md`**: las dos tablas con `-- [spec 010-subscription-periods]`.
- **`specs/010-subscription-periods/contracts/pedidos-*.md`**: los tres pedidos, listos para enviar.

## Puntos a confirmar fuera de este repositorio (no bloquean el plan)

1. **mailySoft-usuarios**: alta de los permisos `subscription_periods:read` y `:write` (módulo de tipo
   Sistema) y su asignación al rol Owner; `payments:read` y `payments:write` para el Owner; `tenant_id` en
   `GET /api/v1/authorization/me` ([pedidos-usuarios.md](contracts/pedidos-usuarios.md)). Hasta entonces, contra
   el API real toda petición recibe 403.
2. **mailySoft-clinicas**: `billing_period` en `GET /api/v1/organizations/{id}`
   ([pedidos-clinicas.md](contracts/pedidos-clinicas.md)). Hasta entonces, contra el API real las dos
   operaciones responden 503.
3. **mailySoft-pagos**: `redirect_urls` y `approved_at` ([pedidos-pagos.md](contracts/pedidos-pagos.md)); no
   bloquean.
4. **Frontend**: tomar el `organization_id` de «mis clínicas», incluir su origen en `CORS_ALLOWED_ORIGINS` y,
   al volver del checkout, volver a consultar (aplica el pago).
5. **Operación**: fijar `BILLING_CUTOFF_AT` en el instante del despliegue inicial (D2): las organizaciones
   con un plan sin prueba (`trial_days` = 0) vencen ese mismo día; una fecha posterior les da margen.

## Project Structure

### Documentation (this feature)

```text
specs/010-subscription-periods/
├── plan.md                                  # Este archivo
├── research.md                              # Fase 0: decisiones R1–R21 y su evidencia
├── data-model.md                            # Fase 1: dos tablas, modelos, registros, DTOs y configuración
├── quickstart.md                            # Fase 1: guía de validación en cuatro niveles
├── contracts/
│   ├── openapi-subscription-periods.yaml    # Fase 1: las dos operaciones (OpenAPI 3.1)
│   ├── permission-matrix.md                 # Fase 1: 2 filas nuevas (15 protegidas)
│   ├── error-catalog.md                     # Fase 1: 5 códigos nuevos (22), mensaje de validación y precedencia
│   ├── database-schema.sql                  # Fase 1: tablas, restricciones, índice y disparadores (migración 0008)
│   ├── clinics-api-integration.md           # Fase 1: contrato consumido de Clínicas
│   ├── payments-api-integration.md          # Fase 1: contrato consumido de Pagos
│   ├── users-api-integration.md             # Fase 1: contrato consumido de Usuarios y lo que falta
│   ├── e2e-collection.md                    # Fase 1: colección de Postman, simulaciones y pruebas guardianas
│   ├── pedidos-usuarios.md                  # Fase 1: pedido a Usuarios (listo para enviar)
│   ├── pedidos-clinicas.md                  # Fase 1: pedido a Clínicas
│   └── pedidos-pagos.md                     # Fase 1: pedido a Pagos
├── checklists/
│   └── requirements.md
└── tasks.md                                 # Fase 2 (/speckit-tasks, aún no creado)
```

### Source Code (repository root)

```text
src/
├── __init__.py                            # (modifica) VERSION = "4.1.0"
├── main.py                                # (modifica) incluye el router; etiqueta `subscription-periods` y párrafo en DESCRIPTION; lifespan carga PaymentsSettings y BillingSettings con las demás y registra la advertencia de la dirección de Pagos sin cifrar
├── config.py                              # (modifica) PaymentsSettings, BillingSettings, get_payments_settings, get_billing_settings, payments_url_warnings
├── dependencies.py                        # (modifica) get_payments_api_client, get_subscription_period_repository, get_subscription_period_service (usa get_clock, get_subscription_repository y get_clinics_api_client)
├── security.py                            # (modifica) SUBSCRIPTION_PERIODS_READ, SUBSCRIPTION_PERIODS_WRITE
├── messages.py                            # (modifica) 5 ErrorCode y sus mensajes; VALIDATION_MESSAGES["subscription-periods"]
├── exceptions.py                          # (modifica) OrganizationNotFoundError, OrganizationCheckUnavailableError, PaymentsUnavailableError, NothingToChargeError, OrganizationSubscriptionNotFoundError
├── routers/
│   └── subscription_periods.py            # (nuevo) get_subscription_period y create_subscription_payment: protected(...), Cache-Control, 201/200, documentación en español
├── services/
│   ├── billing_rules.py                   # (nuevo) reglas puras: add_months, payment_due_at, period_state, days_remaining, covered_period, to_minor_units, idempotency_key
│   └── subscription_period_service.py     # (nuevo) SubscriptionPeriodService: get_status, start_payment, conciliación; PeriodView y PaymentStart
├── integrations/
│   ├── errors.py                          # (modifica) OrganizationNotFound, PaymentsApiUnavailable
│   ├── clinics_api.py                     # (modifica) get_organization y OrganizationRecord
│   └── payments_api.py                    # (nuevo) PaymentsApiClient (create_payment, get_payment) y PaymentRecord
├── repositories/
│   ├── subscription_repository.py         # (modifica) get_plan_terms y PlanTerms
│   └── subscription_period_repository.py  # (nuevo) periodo, cobros, aplicar/cerrar, ApplyOutcome
├── models/
│   ├── __init__.py                        # (modifica) exporta SubscriptionPeriod y SubscriptionCharge
│   ├── subscription_period.py             # (nuevo)
│   └── subscription_charge.py             # (nuevo)
└── dtos/
    └── subscription_period.py             # (nuevo) PlanRead, SubscriptionPeriodRead, SubscriptionPaymentRead

alembic/versions/0008_subscription_periods.py    # (nuevo) dos tablas, índice parcial y disparadores; downgrade reversible

tests/
├── billing_support.py                     # (nuevo) dobles (FakeClinicsOrganizations, FakePaymentsApi, FakePeriodRepository), constructores y ayuda HTTP
├── conftest.py                            # (ajuste A6)
├── helpers.py                             # (ajuste A7)
├── stubs/
│   ├── clinics_api/app.py                 # (ajuste A13)
│   └── payments_api/{__init__,app}.py     # (nuevo) simulación de Pagos (pytest y pila e2e)
├── unit/
│   ├── test_billing_rules.py              # (nuevo) los 16 ejemplos, límites, fin de mes, bisiesto, redondeo, unidad mínima, clave
│   ├── test_billing_config.py             # (nuevo) PaymentsSettings y BillingSettings: válidas, vacías, inválidas; sin valores en los mensajes
│   ├── test_billing_startup.py            # (nuevo) lifespan: un mensaje con todas las variables; advertencia de Pagos sin cifrar
│   ├── test_billing_messages.py           # (nuevo) los cinco mensajes y el de validación; 22 códigos
│   ├── test_subscription_period_dtos.py   # (nuevo) forma, UTC con Z, importe con dos decimales, invariantes
│   ├── test_clinics_organization_client.py # (nuevo) get_organization contra la simulación: 200, 404, fallas, validación estricta
│   ├── test_payments_api_client.py        # (nuevo) create_payment y get_payment contra la simulación: éxito, idempotencia, fallas
│   ├── test_subscription_period_service.py # (nuevo) historias 1, 2, 3, 5 y 6 con dobles y FakeClock
│   ├── test_error_messages.py             # (ajuste A3)
│   ├── test_dashboard_messages.py         # (ajuste A4)
│   ├── test_health_messages.py            # (ajuste A4)
│   ├── test_health_settings.py            # (ajuste A5)
│   └── test_main.py                       # (ajuste A5)
├── contract/
│   ├── test_subscription_periods_api.py            # (nuevo) historias 1 a 3 y 5 por HTTP con base real, reloj fijo y simulaciones
│   ├── test_subscription_periods_access_control.py # (nuevo) 401/403/404/422/503 y su orden; CORS; el permiso exacto
│   ├── test_subscription_periods_degradation.py    # (nuevo) historia 6: cada celda de la tabla, sin fugas
│   ├── test_subscription_periods_concurrency.py    # (nuevo) 20 consultas simultáneas: un registro, una aplicación
│   ├── test_subscription_periods_openapi.py        # (nuevo) etiqueta, seguridad, permisos, respuestas y esquemas
│   ├── test_periods_postman_collection.py          # (nuevo) reglas G1–G8 de la colección nueva
│   ├── test_permission_coverage.py        # (ajuste A1)
│   ├── test_openapi_contract.py           # (ajuste A2)
│   ├── test_dashboard_openapi.py          # (ajuste A4)
│   ├── test_health_openapi.py             # (ajuste A4)
│   ├── test_dashboard_postman_collection.py # (ajuste A8)
│   └── postman_support.py                 # (ajuste A12)
├── integration/
│   ├── test_subscription_period_repository.py   # (nuevo) contra PostgreSQL 17: creación única, reclamación, compare-and-swap, unicidad, restricción de estado
│   └── test_subscription_periods_migration.py   # (nuevo) 0008 sube y baja; la función de 0001 sobrevive
└── postman/
    ├── collections/MailySoft-System-Periodos.postman_collection.json   # (nuevo)
    ├── environments/e2e.postman_environment.json                        # (ajuste A10)
    ├── docker-compose.e2e.yml                                           # (ajuste A9)
    └── package.json                                                     # (ajuste A11)

pyproject.toml                    # (modifica) version 4.1.0
uv.lock                           # (modifica) versión del paquete raíz
.env.example                      # (modifica) las tres variables
docker-compose.yml                # (ajuste A14)
README.md                         # (modifica) periodos de suscripción, configuración, pruebas y estructura
project-definition/DATA_SCHEMA.md # (modifica) las dos tablas -- [spec 010-subscription-periods]
```

Sin cambios: `src/database/`, `src/scripts/`, el código de suscripciones, dashboard y salud, las otras colecciones
de Postman, `tests/stubs/users_api` (ya acepta cualquier permiso `recurso:acción`), `tests/stubs/components`,
`project-definition/create_database.sql` (crea hasta 0002; `alembic upgrade head` aplica el resto) y la
colección manual.

**Structure Decision**: proyecto único de servicio web con la estructura obligatoria del Principio I. Los
periodos de suscripción son un recurso nuevo con su propio Router, Service, Repository, modelos, DTOs y
cliente de Pagos, que no tocan los de suscripciones salvo por **una lectura** nueva del catálogo
(`get_plan_terms`) y **un método** nuevo del cliente de Clínicas (`get_organization`). Las reglas de negocio
más delicadas (fechas y estado) son funciones puras para poder probarlas con tablas y reloj fijo.

## Trazabilidad de requisitos

| Requisitos de la spec | Dónde se cumplen |
|---|---|
| FR-001 a FR-006 (acceso, Dueño, orden, sin Auth0, matriz) | R1, R8, R9, R12; [permission-matrix.md](contracts/permission-matrix.md); [error-catalog.md](contracts/error-catalog.md); [clinics-api-integration.md](contracts/clinics-api-integration.md) |
| FR-007 a FR-011 (registro, inicio, prueba, fecha de pago, UTC y reloj) | R3, R4, R15; [data-model.md](data-model.md) secciones 2 y 7 |
| FR-012 a FR-015 (estado, días, respuesta) | R3, R13; [data-model.md](data-model.md) sección 6; [openapi-subscription-periods.yaml](contracts/openapi-subscription-periods.yaml) |
| FR-016 a FR-019 (importe, unidad mínima, cero, IVA) | R3, R13; [data-model.md](data-model.md) sección 3 |
| FR-020 a FR-025 (iniciar el pago, idempotencia, códigos) | R1, R6, R10; [payments-api-integration.md](contracts/payments-api-integration.md); [openapi-subscription-periods.yaml](contracts/openapi-subscription-periods.yaml) |
| FR-026 a FR-033 (conciliación, qué cuenta, periodo cubierto, una sola vez) | R5, R7; [data-model.md](data-model.md) sección 3 (ciclo de vida); [payments-api-integration.md](contracts/payments-api-integration.md) |
| FR-034, FR-035 (cambios de plan, estatus del plan) | R2 (`get_plan_terms`), R6; [error-catalog.md](contracts/error-catalog.md) |
| FR-036 a FR-038 (degradación, sin inventar, higiene de errores) | R8, R9, R10; [error-catalog.md](contracts/error-catalog.md) |
| FR-039 a FR-041 (fecha de corte, Pagos, CORS) | R11; [data-model.md](data-model.md) sección 7 |
| FR-042, FR-043 (datos propios, esquema) | R14; [data-model.md](data-model.md); [database-schema.sql](contracts/database-schema.sql) |
| FR-044 a FR-046 (contrato, errores, caché) | R12, R13; [openapi-subscription-periods.yaml](contracts/openapi-subscription-periods.yaml); [error-catalog.md](contracts/error-catalog.md) |
| FR-047 a FR-050 (contratos consumidos, simulaciones, pedidos) | R9, R10, R16, R21; [clinics](contracts/clinics-api-integration.md), [payments](contracts/payments-api-integration.md) y [users](contracts/users-api-integration.md); [pedidos](contracts/pedidos-usuarios.md) |
| FR-051 a FR-054 (pruebas, Postman, ajustes, documentación) | R17 a R19; «Ajustes a las pruebas existentes» (A1–A14); [e2e-collection.md](contracts/e2e-collection.md); [quickstart.md](quickstart.md) |

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Id | Punto a justificar | Por qué hace falta | Alternativa más simple descartada porque |
|---|---|---|---|
| C1 | **Principio IV**: el `GET get_subscription_period` tiene un efecto acotado e idempotente (crea el registro de la organización la primera vez y aplica o cierra cobros que Pagos ya decidió). No es una violación de una regla escrita, pero una consulta con efectos merece una justificación | La spec lo ordena: «el registro se crea en la primera consulta» (regla 1) y «antes de responder… consulta su estado en Pagos y aplica los aprobados» (historia 1); Pagos no avisa de los cambios y no hay tareas programadas (FR-012), así que la consulta es el único momento en que se puede descubrir un pago. El efecto es determinista, no depende de lo que mande la persona, solo refleja pagos que la propia API inició y es idempotente (repetirla no cambia nada más); basta el permiso de lectura | Un `POST` aparte que concilie obligaría a la aplicación a llamarlo antes de cada consulta (y a saber cuándo), y una tarea programada está prohibida por FR-012 |

Limitaciones aceptadas, que no son violaciones:

- **Contra los servicios reales de hoy la feature no responde 200**: faltan los permisos de Usuarios (403) y el
  `billing_period` de Clínicas (503). Es lo pedido (la spec manda no inventar datos) y está documentado en
  los tres pedidos y en el [quickstart](quickstart.md).
- **Un cobro pagado y nunca consultado no mueve la fecha** hasta la siguiente consulta o inicio de pago (no
  hay avisos ni tareas); la fecha de aprobación que informa Pagos decide si llegó a tiempo.
- **Meses sin día ancla** (FR-030): un día 29 a 31 acortado por un mes corto no se recupera.
- **Fecha de aprobación aproximada** (`updated_at` de Pagos) hasta que Pagos publique `approved_at`.
