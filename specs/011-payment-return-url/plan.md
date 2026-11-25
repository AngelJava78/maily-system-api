# Implementation Plan: Regreso automático a MailySoft después de pagar la suscripción («Dirección de regreso del pago»)

**Branch**: `011-payment-return-url` | **Date**: 2026-11-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/011-payment-return-url/spec.md`

## Summary

Una variable de entorno opcional nueva, `PAYMENTS_RETURN_URL`, con la dirección `https` de la pantalla de
pago del frontend. Si está definida, iniciar el pago de un periodo de suscripción envía a Pagos
`redirect_urls.success` con esa dirección (feature 002 de mailySoft-pagos), para que Mercado Pago regrese
solo a la persona cuando su pago se aprueba; la dirección también entra en la clave de idempotencia del
cobro. Sin la variable, el cuerpo y las claves son idénticos a los de hoy. El arranque valida la dirección
con las reglas propias que aplica Pagos (todas menos su lista de orígenes permitidos) y, si no las cumple,
no arranca y nombra la variable sin su valor. No cambia ninguna operación, ningún DTO, la base de datos ni
el cobro de clínicas; el regreso de la persona nunca es prueba de pago ([research](research.md)).

## Technical Context

**Language/Version**: Python 3.14+ (el entorno de desarrollo ejecuta 3.15.2)

**Primary Dependencies**: las del proyecto, **sin dependencias nuevas** (FastAPI, Pydantic v2 +
pydantic-settings, httpx) y la biblioteca estándar (`ipaddress`, `json`, `urllib.parse`). Desarrollo: pytest,
pytest-asyncio; herramienta aparte: Newman.

**Storage**: PostgreSQL 17, **sin cambios** (ni tablas, ni columnas, ni migraciones).

**Testing**: pytest + pytest-asyncio + httpx. Nivel rápido: configuración (tabla de direcciones), arranque,
cliente de Pagos contra respuestas fijas y la simulación en memoria, clave de idempotencia y Service con
dobles. Nivel lento: la aplicación real con PostgreSQL 17 y las tres simulaciones. Postman/Newman sin
cambios. `/speckit-implement` corre solo el nivel rápido.

**Target Platform**: contenedor Linux (Docker Compose, imagen `python:3.14-slim`).

**Project Type**: web-service

**Performance Goals**: sin efecto medible: un campo más en el cuerpo de una llamada que ya existe y una
validación al arrancar.

**Constraints**: con la variable sin definir, cuerpo y claves idénticos a los de hoy (SC-002); la dirección
nunca en mensajes, registros ni respuestas; el cobro de clínicas no cambia; sin reintentos automáticos ni
operaciones nuevas; el estado de un cobro solo cambia en la conciliación con Pagos.

**Scale/Scope**: 1 variable de entorno; 5 módulos de `src/` modificados de forma aditiva (`config.py`,
`integrations/payments_api.py`, `services/billing_rules.py`, `services/subscription_period_service.py`,
`dependencies.py`); 1 simulación extendida (Pagos); 1 archivo de pruebas de contrato nuevo y 7 archivos de
pruebas o de soporte extendidos; 3 archivos de documentación o despliegue.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio / regla | Evaluación inicial | Tras diseño (Fase 1) |
|---|---|---|
| I. Capas estrictas y código en `src/` | ✅ | ✅ La configuración se lee y valida en `src/config.py`; `src/dependencies.py` la inyecta en el Service (R6); el Service decide la clave y pide el cuerpo; la regla de la clave es pura en `billing_rules.py`; el cliente (`src/integrations/`) solo arma el cuerpo y registra. Sin carpetas ni módulos raíz nuevos: `test_layering.py` sin cambios |
| II. Modelos ≠ DTOs | ✅ | ✅ No cambian modelos ni DTOs; la dirección no aparece en ninguna respuesta (FR-009) |
| III. Asincronía | ✅ | ✅ La llamada a Pagos sigue siendo la misma llamada httpx asíncrona; la validación es cálculo puro al arrancar |
| IV. OpenAPI y REST | ✅ | ✅ Sin operaciones, campos ni códigos nuevos: `/openapi.json` idéntico (FR-013, quickstart §4) |
| V. Pruebas pytest | ✅ | ✅ Service con dobles; cliente contra la simulación y respuestas fijas; endpoint por HTTP con la base real; la simulación de Pagos valida el campo y reproduce su rechazo (R8). Postman sin cambios porque ninguna operación cambia; niveles rápido y lento como manda el principio |
| VI. Migraciones Alembic | ✅ | ✅ No aplica: sin cambios en la base (FR-013) |
| VII. Idioma | ✅ | ✅ Variable, campo y códigos en inglés; mensajes y documentos en español; comentarios y docstrings en inglés |
| VIII. Control de acceso delegado | ✅ | ✅ Sin cambios: mismas operaciones, mismos permisos, mismo token reenviado. Sin secretos nuevos: la dirección no es un secreto, pero tampoco se registra (podría llevar datos en su consulta) |
| IX. Integraciones | ✅ | ✅ Contrato consumido documentado ([payments-api-integration.md](contracts/payments-api-integration.md)) y simulado; la dirección viene de una variable validada al arrancar; sin reintentos (el 422 no se reintenta sin la dirección, R7); fallas traducidas a `payments_unavailable` sin filtrar el cuerpo de Pagos |
| Configuración validada al arrancar, sin mostrar valores | ✅ | ✅ El mensaje único de configuración nombra `PAYMENTS_RETURN_URL` (FR-004) |
| Flujo y puertas de calidad | ✅ | ✅ Suite completa, migraciones desde cero, OpenAPI, cobertura de permisos, Postman y capas antes de integrar ([R10](research.md#r10-puertas-de-calidad-antes-de-integrar-a-main)); la matriz y las colecciones no cambian porque la API no cambia |

Sin desviaciones: «Complexity Tracking» queda vacío.

## Ajustes a las pruebas existentes

Ninguna comprobación existente cambia (SC-005). Solo se ajusta el soporte de las pruebas:

| Archivo | Ajuste | Por qué |
|---|---|---|
| `tests/conftest.py` (`billing_environment`) | Quita `PAYMENTS_RETURN_URL` y hace que `PaymentsSettings` no lea `.env` durante cada prueba | Que el `.env` local nunca active la dirección en una prueba que no la espera |
| `tests/unit/test_billing_startup.py` (`ENV_NAMES`) | Agrega `PAYMENTS_RETURN_URL` a las variables que se aíslan | Las pruebas de arranque definen exactamente lo que usan |
| `tests/billing_support.py` (`FakePaymentsApi`, `make_world`) | `create_payment` acepta `return_url`, lo registra y lo incluye en su huella; `make_world` acepta `return_url` | El Service lo pasa siempre; el doble imita la idempotencia de Pagos |
| `tests/stubs/payments_api/app.py` | Valida y guarda `redirect_urls`; modo de falla `return_not_allowed` | Contrato consumido nuevo (FR-014) |

## Documentación y despliegue

- `.env.example`: `PAYMENTS_RETURN_URL` comentada entre las opcionales, con su explicación (vacía en
  desarrollo local; en otros ambientes, la pantalla `/payment` del frontend; su origen en la lista de Pagos).
- `README.md`: fila de la variable en «Configuración» y una viñeta en la sección de periodos de suscripción
  sobre el regreso automático y la regla de que el regreso no es prueba de pago.
- `docker-compose.yml`: `PAYMENTS_RETURN_URL: ${PAYMENTS_RETURN_URL:-}` junto a las de Pagos.
- `tests/postman/docker-compose.e2e.yml`: `PAYMENTS_RETURN_URL: ""`, para que la pila aislada no herede la
  variable del `.env` de quien la corre (sigue sin dirección, como el desarrollo local).
- Sin cambios: OpenAPI, matriz de permisos, `DATA_SCHEMA.md`, migraciones y colecciones de Postman.

## Project Structure

### Documentation (this feature)

```text
specs/011-payment-return-url/
├── plan.md              # Este archivo
├── research.md          # Fase 0: decisiones R1-R10
├── data-model.md        # Fase 1: configuración, campo enviado y clave
├── quickstart.md        # Fase 1: cómo comprobarlo
├── contracts/
│   └── payments-api-integration.md   # Cambio del contrato consumido de Pagos
├── checklists/
│   └── requirements.md  # Calidad de la especificación
└── tasks.md             # Fase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
src/
├── config.py                          # PaymentsSettings.payments_return_url + validación (R1-R3)
├── dependencies.py                    # inyecta la dirección en SubscriptionPeriodService (R6)
├── integrations/
│   └── payments_api.py                # create_payment(..., return_url=None) + registro del 422 (R4, R7)
└── services/
    ├── billing_rules.py               # idempotency_key(..., return_url=None) (R5)
    └── subscription_period_service.py # usa la dirección en la clave y en el cuerpo (R6)

tests/
├── conftest.py                        # aislamiento de la variable (ajuste)
├── billing_support.py                 # doble de Pagos (ajuste)
├── stubs/payments_api/app.py          # validación, registro y falla nueva
├── unit/
│   ├── test_billing_config.py         # tabla de direcciones contra PaymentsSettings
│   ├── test_billing_startup.py        # arranque con dirección válida e inválida
│   ├── test_payments_api_client.py    # cuerpo con y sin dirección, registro del 422
│   ├── test_billing_rules.py          # clave con y sin dirección
│   └── test_subscription_period_service.py  # dirección en la creación y en la clave
└── contract/
    └── test_subscription_periods_return_url.py  # nuevo: con la aplicación real y la simulación
```

**Structure Decision**: el proyecto único de siempre (`src/` y `tests/`), sin carpetas nuevas.

## Trazabilidad de requisitos

| Requisito | Dónde se cumple | Dónde se prueba |
|---|---|---|
| FR-001, FR-002, FR-005 | `config.py` (`PaymentsSettings`, caché de `get_payments_settings`) | `test_billing_config.py`, `test_billing_startup.py` |
| FR-003, FR-004 | `config.py` (validación) + `configuration_error_message` | `test_billing_config.py` (tabla), `test_billing_startup.py` (mensaje y registro) |
| FR-006, FR-007 | `payments_api.py`, `subscription_period_service.py`, `dependencies.py` | `test_payments_api_client.py`, `test_subscription_period_service.py`, `test_subscription_periods_return_url.py` |
| FR-008 | `billing_rules.py` | `test_billing_rules.py`, `test_subscription_period_service.py` |
| FR-009 | Sin cambios en el Router ni en los DTOs | `test_subscription_periods_return_url.py` (misma forma de respuesta) |
| FR-010 | `payments_api.py` (registro) + mapeo existente a 503 | `test_payments_api_client.py`, `test_subscription_periods_return_url.py` |
| FR-011 | `clinic_subscription_service.py` sin cambios (no pasa `return_url`) | Pruebas existentes del cobro de clínicas sin cambios |
| FR-012 | Sin operación nueva; conciliación de la spec 010 | `test_subscription_periods_return_url.py` (parámetros de «aprobado» ignorados) + suite existente |
| FR-013 | — | Suite completa + comparación de `/openapi.json` (quickstart §4) |
| FR-014 | `contracts/payments-api-integration.md`, simulación de Pagos | `test_subscription_periods_return_url.py` |
| FR-015 | `.env.example`, `README.md`, `docker-compose.yml` | Revisión |

## Complexity Tracking

Sin desviaciones de la constitución que justificar.
