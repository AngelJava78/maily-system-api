# Implementation Plan: Dashboard de Plataforma («Panel de Maily»)

**Branch**: `003-platform-dashboard` | **Date**: 2026-10-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-platform-dashboard/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

Una operación de **solo lectura**, `GET /api/v1/dashboard`, que alimenta la pantalla de resumen general del
administrador de plataforma: en una sola consulta devuelve seis indicadores (total de clínicas, activas, con
periodo de prueba, doctores, pacientes y usuarios) y las clínicas más recientes. Exige token y el permiso
`dashboard:read`, que decide el API de usuarios. En la **Fase 1** los datos son ficticios, deterministas y no
tocan la base de datos; el contrato queda fijo para cuando existan las fuentes reales y, si una falla, solo el
valor afectado llega como `null`.

Enfoque técnico (decisiones y evidencia en [research.md](research.md)):

- **Una costura para los datos (R1)**: un puerto `DashboardSource` en `src/integrations/` con cinco consultas
  independientes (conteos de clínicas, clínicas recientes, doctores, pacientes y usuarios). La Fase 1 lo cumple
  `DummyDashboardSource`, con 12 clínicas fijas y conteos derivados del mismo conjunto
  ([data-model.md](data-model.md)). Cuando existan los APIs reales solo se cambia quién cumple el puerto
  ([data-sources.md](contracts/data-sources.md)).
- **Reglas en el Service (R2)**: tope fijo de 10, valor por defecto de la configuración, orden (fecha
  descendente, desempate por identificador ascendente) y corte; cinco consultas en paralelo con
  `asyncio.gather`; una fuente que falla (`DashboardSourceUnavailable`) deja en `null` solo lo suyo, nunca un
  cero inventado.
- **`limit` leído a mano (R3)**: Pydantic aceptaría `5.0`, `+3` o `1_0` y rechazaría un entero de miles de
  dígitos, y la spec pide lo contrario en ambos casos. Una dependencia analiza la cadena de consulta cruda
  (solo dígitos, sin repetidos) y lanza el 422 por el manejador de errores existente; el contrato sigue
  publicando `limit` como entero.
- **Acceso (R4)**: `protected("dashboard:read")` como en suscripciones. Verificado: la dependencia de seguridad
  se resuelve **antes** que cualquier lectura de `limit`, así que 401/403/503 ganan a un `limit` inválido. A
  diferencia de la feature 001, **no hay desviación** del Principio VIII (es un `GET` sin cuerpo).
- **Configuración (R5, R6)**: `DASHBOARD_RECENT_CLINICS_LIMIT` (3, 5 o 10; 5 por defecto) en una clase nueva
  `DashboardSettings`, validada en el arranque junto a las demás; al arrancar con datos ficticios se registra
  un aviso.
- **Sin caché (R7)**: `Cache-Control: no-store` en la respuesta 200.
- **Contrato (R8, R9)**: `DashboardRead` con siete campos obligatorios y anulables; fecha en UTC con `Z`; ruta
  `/api/v1/dashboard`; la versión publicada sigue en `1.0.0`. Sin códigos de error nuevos
  ([error-catalog.md](contracts/error-catalog.md)).
- **Pruebas sin servicios reales (R11, R12)**: pytest sin base de datos, con la simulación del API de usuarios
  que ya existe (no cambia) y una fuente simulada; una colección de Postman nueva y de solo lectura que
  reutiliza el entorno `e2e` ([e2e-collection.md](contracts/e2e-collection.md)).
- **Esquema (R14)**: ninguno. Sin tablas, sin migraciones, sin cambios en `DATA_SCHEMA.md`.

## Technical Context

**Language/Version**: Python 3.14+ (el entorno de desarrollo ejecuta 3.15.0)

**Primary Dependencies**: las del proyecto, **sin dependencias nuevas**: FastAPI 0.143.x, Pydantic v2
(+ pydantic-settings), httpx (solo en las pruebas de esta feature), uvicorn. Desarrollo: pytest,
pytest-asyncio; herramienta aparte: Newman (npm, ya existente).

**Storage**: N/A. La feature no lee ni escribe la base de datos del servicio (FR-020); sus datos son
constantes del código.

**Testing**: pytest + pytest-asyncio + httpx. Service con una fuente doble (`FakeDashboardSource`); la
implementación ficticia con pruebas propias (determinismo e invariantes); endpoints por HTTP contra la
aplicación con la simulación del API de usuarios montada en memoria; prueba estática de que los módulos del
dashboard no tocan la base de datos; prueba de cobertura de permisos; Postman/Newman contra la pila aislada.
Ninguna prueba necesita PostgreSQL ni Docker, salvo la suite completa y Newman.

**Target Platform**: Contenedor Linux (Docker Compose, imagen `python:3.14-slim`); desarrollo en Windows con
VS Code. La pila de punta a punta de la feature 001 no cambia.

**Project Type**: web-service

**Performance Goals**: el resumen aparece en < 2 s en el 95 % de las consultas (SC-001), suponiendo que el API
de usuarios responde en < 500 ms. El costo propio es insignificante: cinco consultas ficticias instantáneas y
en paralelo, y a lo sumo 10 clínicas que ordenar.

**Constraints**: falla cerrada en el control de acceso y permiso **antes** de validar `limit`; efecto
inmediato de bloqueos y cambios de permisos (sin caché de decisiones); la respuesta 200 declara
`Cache-Control: no-store`; ninguna respuesta con datos personales; los registros no incluyen el token ni
detalles de las fuentes; ningún cero inventado cuando una fuente falla; ninguna prueba automatizada llama a un
API real; no se toca el comportamiento ni el contrato de las operaciones de suscripciones (FR-032).

**Scale/Scope**: 1 operación (`get_dashboard`); 0 tablas y 0 migraciones; 0 códigos de error nuevos (siguen
siendo 12) y 1 mensaje de validación; 1 variable de entorno opcional; 1 puerto de datos con 5 consultas y 1
implementación ficticia (12 clínicas); 1 colección de Postman nueva (24 peticiones, 4 carpetas); 5 archivos de
código nuevos en `src/` y 6 modificados de forma aditiva.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principio / regla | Evaluación inicial | Tras diseño (Fase 1) |
|---|---|---|
| I. Capas estrictas y código en `src/` | ✅ | ✅ Todo en `src/` y en las carpetas existentes (no hay carpeta nueva). Router (`routers/dashboard.py`): valida `limit`, llama al Service y serializa; no importa Repositories, integraciones, base de datos ni modelos. Service (`services/dashboard_service.py`): reglas de negocio, importa el puerto de `integrations/` y no `fastapi` ni `sqlalchemy`. Integraciones (`dashboard_source.py`, `dummy_dashboard_source.py`): solo `dataclass` y biblioteca estándar. `test_layering.py` lo vigila y una prueba nueva afirma que los módulos del dashboard no importan `sqlalchemy`, `src.database`, `src.models` ni `src.repositories` |
| II. Modelos ≠ DTOs | ✅ | ✅ No hay modelos ORM. `DashboardRead`, `RecentClinicRead` y `ClinicStatusRead` son DTOs de salida; la conversión registro → DTO es explícita (`model_validate` con `from_attributes`); los registros del puerto solo tienen los campos del contrato, sin datos personales |
| III. Asincronía | ✅ | ✅ El puerto y el Service son `async`; las cinco consultas corren con `asyncio.gather`. Sin librerías bloqueantes |
| IV. OpenAPI y REST | ✅ | ✅ [openapi-dashboard.yaml](contracts/openapi-dashboard.yaml) validado como OpenAPI 3.1.0; `response_model`, etiqueta `dashboard`, 200/401/403/422/503 con ejemplos en español, mismo cuerpo de error. **Ruta singular**: es una vista única, no una colección (R9). **Lista sin paginar**: la excepción del Principio IV está declarada en la spec (FR-016) con su máximo fijo (10, muy por debajo de 500) y su orden determinista (FR-015). Como indicó la persona responsable, no hace falta enmendar la constitución. Cambio compatible: `info.version` sigue en `1.0.0` |
| V. Pruebas pytest | ✅ | ✅ Service con doble de la fuente; endpoint con cliente async; prueba que recorre las rutas (ajuste A1 de la tabla de abajo); ninguna prueba llama a un API real; Postman complementa y no repite pytest. No hay Repository, así que no hay pruebas contra PostgreSQL |
| VI. Migraciones Alembic | ✅ | ✅ **Sin cambios de esquema**: no hay migraciones ni modelos, y `project-definition/DATA_SCHEMA.md` no cambia ([data-model.md](data-model.md)) |
| VII. Idioma | ✅ | ✅ Campos (`total_clinics`, `recent_clinics`, `created_at`…), parámetro (`limit`) y códigos en inglés; mensajes, OpenAPI y documentos en español; comentarios y docstrings en inglés |
| VIII. Control de acceso delegado | ✅ | ✅ Token reenviado sin modificar al API de usuarios, una consulta por petición, sin caché, falla cerrada (401/403/503); `BearerAuth` + `x-required-permission: dashboard:read`; dependencias en `src/security.py` que pasan por `AuthorizationService`. **El permiso se comprueba antes de validar `limit`**, comprobado con un experimento (R4): no hay desviación (es un `GET` sin cuerpo). Fila nueva en la [matriz](contracts/permission-matrix.md) sin alterar las existentes. Sin secretos ni tokens en registros |
| IX. Integraciones | ✅ | ✅ Los datos ficticios no son copia de datos ajenos (viven en el código y no almacenan nada real). Esta feature no consume ningún API nuevo; el puerto fija desde ahora la degradación: `null` explícito, nunca un cero inventado, y el resto del dashboard se devuelve ([data-sources.md](contracts/data-sources.md)). El control de acceso sigue fallando cerrado. El contrato consumido de cada API real lo documentará la especificación que lo conecte |
| Stack obligatorio | ✅ | ✅ Solo tecnologías de la tabla; sin dependencias nuevas |
| Configuración por entorno, sin secretos | ✅ | ✅ `DASHBOARD_RECENT_CLINICS_LIMIT` validada al arrancar; el mensaje nombra la variable y nunca su valor; sin secretos propios |
| Docker y Compose | ✅ | ✅ `docker-compose.yml` solo pasa la variable nueva al servicio `api`; la pila de punta a punta no cambia |
| Flujo y puertas de calidad | ✅ | ✅ Este plan incluye el Constitution Check; estructura `src/`, `tests/`; matriz de permisos y colección de Postman se actualizan **en el mismo cambio** que la API (colección nueva, fila nueva); puertas verificables en el [quickstart](quickstart.md) |

**Resultado**: PASS contra los principios I a IX, **sin necesidad de enmendar la constitución** y **sin
violaciones que justificar**. Nota de revisión (no es una violación): la lista de recientes se declara como
excepción de paginación del Principio IV por prudencia, aunque no es un catálogo paginable sino un fragmento
acotado del resumen (spec, Assumptions).

## Ajustes a las pruebas existentes (FR-032, FR-033)

Todas las operaciones de suscripciones y todas sus pruebas de comportamiento **quedan intactas**. El barrido de
lo que da por hecho "exactamente estas 6 operaciones" o "ningún aviso" encontró cuatro puntos
([research.md R13](research.md)); ninguno cambia lo que se verifica de las suscripciones:

| Id | Archivo | Ajuste | Por qué | FR-033 |
|---|---|---|---|---|
| A1 | `tests/contract/test_permission_coverage.py` | **Ampliar** `EXPECTED_PERMISSIONS` y `REQUESTS` con `get_dashboard` (dos entradas; ninguna aserción cambia) | La prueba exige igualdad exacta con el OpenAPI y `checked == len(EXPECTED_PERMISSIONS)`; añadir una operación la rompe. Sigue siendo global y ahora ejercita también el dashboard | (a) |
| A2 | `tests/contract/test_openapi_contract.py` | **Acotar** `test_it_has_exactly_the_six_operations_of_the_contract` a las rutas bajo `/api/v1/subscriptions` | Compara todas las operaciones con las 6 de suscripciones | (a) |
| A3 | `tests/contract/postman_support.py` | **Acotar**: `operation_ids_of_the_api(path_prefix=…)` con valor por defecto `/api/v1/subscriptions`; añadir las constantes de la colección del dashboard. Las pruebas de la colección de suscripciones y de la manual **no se editan** | Comparan las operaciones de la API con las peticiones de sus colecciones (que cubren suscripciones) | (a) |
| B1 | `tests/unit/test_main.py` | **Acotar** `assert caplog.text == ""` de `test_docker_and_https_addresses_do_not_warn` a `assert "BASE_URL" not in caplog.text` | El aviso de datos ficticios (FR-024, obligatorio) añade un registro al arrancar; es la única aserción de "cero registros" del repositorio | (b) |

**Nada se debilita**. Lo que A2 y A3 dejan de vigilar de forma global se recupera con pruebas nuevas: la
cobertura de permisos sigue global (A1); G9 comprueba que las tres colecciones **juntas** cubren exactamente las
operaciones de la API; `test_dashboard_openapi.py` comprueba el contrato de `get_dashboard`; y una prueba
recorre todas las operaciones del OpenAPI exigiendo `security` y `x-required-permission`.

> **Decisión que conviene confirmar (B1)**. La spec pedía no tocar pruebas existentes y a la vez un aviso
> obligatorio al arrancar; chocan en esa única aserción, y por eso la enmienda FR-033(b) de la spec. Alternativa
> si se prefiere no editar `test_main.py`: registrar el aviso desde un `lifespan` propio del router del
> dashboard, de modo que las pruebas que llaman a `src.main.lifespan` no lo vean. Se descartó porque esquiva la
> prueba en lugar de corregirla y esconde el aviso fuera del arranque normal ([R6](research.md)).

## Puntos a confirmar fuera de este repositorio (no bloquean el plan)

1. **API de usuarios**: que `dashboard:read` exista en su catálogo y esté asociado al rol de administración de
   plataforma ([permission-matrix.md](contracts/permission-matrix.md), regla 5). Hasta entonces, la simulación
   lo concede y lo niega.
2. **APIs de clínicas, doctores, pacientes y usuarios**: aún no existen. Cada especificación futura que conecte
   uno documentará su contrato consumido y cumplirá el puerto de [data-sources.md](contracts/data-sources.md).

## Project Structure

### Documentation (this feature)

```text
specs/003-platform-dashboard/
├── plan.md                              # Este archivo
├── research.md                          # Fase 0: decisiones R1–R15, evidencia y ajustes a pruebas existentes
├── data-model.md                        # Fase 1: sin esquema; registros, vista, DTOs, configuración y datos ficticios
├── quickstart.md                        # Fase 1: guía de validación en cuatro niveles
├── contracts/
│   ├── openapi-dashboard.yaml           # Fase 1: contrato HTTP de get_dashboard (OpenAPI 3.1, validado)
│   ├── permission-matrix.md             # Fase 1: la fila nueva (7 operaciones en total)
│   ├── error-catalog.md                 # Fase 1: códigos que aplican, mensaje de validación nuevo y precedencia
│   ├── data-sources.md                  # Fase 1: puerto de las fuentes, degradación y cómo conectar las reales
│   └── e2e-collection.md                # Fase 1: colección de Postman nueva y sus pruebas guardianas
├── checklists/
│   └── requirements.md
└── tasks.md                             # Fase 2 (/speckit-tasks, aún no creado)
```

### Source Code (repository root)

El repositorio ya tiene la feature 001 (`src/`, `tests/`, `alembic/`). Esta feature añade archivos y modifica
otros **de forma aditiva** (sin cambiar lo que hacen las operaciones existentes).

```text
src/
├── main.py                       # (modifica) incluye el router; etiqueta `dashboard` y párrafo en DESCRIPTION; lifespan: valida DashboardSettings junto a la configuración existente y registra el aviso de datos ficticios
├── config.py                     # (modifica) DashboardSettings + get_dashboard_settings; configuration_error_message acepta varios errores
├── dependencies.py               # (modifica) build_dashboard_source, get_dashboard_source, get_dashboard_service
├── security.py                   # (modifica) constante DASHBOARD_READ = "dashboard:read"
├── messages.py                   # (modifica) DASHBOARD_LIMIT_INVALID_MESSAGE y VALIDATION_MESSAGES["dashboard"]
├── integrations/
│   ├── errors.py                 # (modifica) DashboardSourceUnavailable
│   ├── dashboard_source.py       # (nuevo) puerto DashboardSource y registros ClinicCounts, ClinicRecord, ClinicStatusRecord
│   └── dummy_dashboard_source.py # (nuevo) DummyDashboardSource: datos ficticios fijos de la Fase 1
├── routers/
│   └── dashboard.py              # (nuevo) GET /api/v1/dashboard: lectura estricta de `limit`, Cache-Control, documentación en español
├── services/
│   └── dashboard_service.py      # (nuevo) DashboardService, DashboardView: tope, valor por defecto, orden, degradación
└── dtos/
    └── dashboard.py              # (nuevo) DashboardRead, RecentClinicRead, ClinicStatusRead

tests/
├── dashboard_support.py          # (nuevo) FakeDashboardSource, constructores de clínicas y ayuda para las pruebas HTTP
├── unit/
│   ├── test_dashboard_service.py        # (nuevo) tope, valor por defecto, orden, desempate, menos clínicas, ninguna, degradación, token
│   ├── test_dashboard_dtos.py           # (nuevo) siete claves obligatorias y anulables, UTC con Z, sin campos personales
│   ├── test_dummy_dashboard_source.py   # (nuevo) determinismo, invariantes I1–I8, conjunto vacío
│   ├── test_dashboard_config.py         # (nuevo) 3/5/10/ausente/vacía válidos; inválidos nombran la variable sin el valor
│   ├── test_dashboard_messages.py       # (nuevo) el mensaje de validación de `limit`; ningún código de error nuevo
│   ├── test_dashboard_startup.py        # (nuevo) el arranque falla o avisa (lifespan); no llega el valor ni secretos
│   ├── test_dashboard_layering.py       # (nuevo) los módulos del dashboard no tocan la base de datos
│   └── test_main.py                     # (ajuste B1)
├── contract/
│   ├── conftest.py                      # (nuevo) fixtures sin base de datos: aplicación + simulación del API de usuarios
│   ├── test_dashboard_api.py            # (nuevo) historias 1 y 3, Cache-Control, forma, conjunto vacío, `limit` (todas las variantes)
│   ├── test_dashboard_access_control.py # (nuevo) 401/403/503, permiso antes de `limit`, permiso exacto, una consulta por petición, token
│   ├── test_dashboard_degradation.py    # (nuevo) historia 6: 200 con `null`, sin fugas, todas las fuentes caídas
│   ├── test_dashboard_openapi.py        # (nuevo) contrato de get_dashboard; todas las operaciones declaran seguridad y permiso
│   ├── test_dashboard_postman_collection.py  # (nuevo) reglas G1–G9
│   ├── test_permission_coverage.py      # (ajuste A1)
│   ├── test_openapi_contract.py         # (ajuste A2)
│   └── postman_support.py               # (ajuste A3)
└── postman/
    ├── collections/MailySoft-System-Dashboard.postman_collection.json   # (nuevo) 24 peticiones
    └── package.json                     # (modifica) scripts `e2e:dashboard` y `e2e:all`; `e2e` queda igual

.env.example                      # (modifica) DASHBOARD_RECENT_CLINICS_LIMIT comentada, con valores admitidos y valor por defecto
docker-compose.yml                # (modifica) el servicio `api` recibe DASHBOARD_RECENT_CLINICS_LIMIT (vacía = valor por defecto)
README.md                         # (modifica) qué incluye, configuración, pruebas de punta a punta (ya no "las dos colecciones"), estructura
```

Sin cambios: `alembic/`, `src/models/`, `src/repositories/`, `src/database/`, `project-definition/`,
`tests/stubs/` (la simulación del API de usuarios ya acepta `dashboard:read`), `tests/postman/environments/` y
`tests/postman/docker-compose.e2e.yml`, y las dos colecciones de Postman existentes.

**Structure Decision**: proyecto único de servicio web con la estructura obligatoria de la constitución
(Principio I). El dashboard es un recurso nuevo con su propio Router, Service y DTOs, que no toca los de
suscripciones (como anticipó el plan de la feature 001). No lleva Repository porque no persiste nada; en su
lugar tiene un **puerto de datos** en `src/integrations/` —el lugar de los clientes de otros sistemas—, que hoy
cumple una implementación ficticia y mañana cumplirán los APIs reales sin tocar el resto.

## Trazabilidad de requisitos

| Requisitos de la spec | Dónde se cumplen |
|---|---|
| FR-001 a FR-004 (acceso, permiso, orden con `limit`, matriz) | R4; `protected(DASHBOARD_READ)`; [permission-matrix.md](contracts/permission-matrix.md); [error-catalog.md](contracts/error-catalog.md) |
| FR-005 a FR-009 (indicadores, definiciones, sin datos personales, forma de cada clínica) | [data-model.md](data-model.md) secciones 1 a 3; R8 |
| FR-010 a FR-016 (`limit`, tope, orden, vacío, excepción de paginación) | R2, R3; [openapi-dashboard.yaml](contracts/openapi-dashboard.yaml) |
| FR-017 a FR-019 (variable de entorno) | R5, R6; [data-model.md](data-model.md) sección 5 |
| FR-020 a FR-024 (datos ficticios, determinismo, invariantes, aviso) | R1, R6, R10; [data-model.md](data-model.md) sección 6; [data-sources.md](contracts/data-sources.md) |
| FR-025 a FR-028 (contrato estable, `null`, falla de una fuente) | R1, R2, R8; [data-sources.md](contracts/data-sources.md) |
| FR-029 a FR-031 (solo lectura, sin caché, errores, documentación) | R7, R15; [error-catalog.md](contracts/error-catalog.md); [openapi-dashboard.yaml](contracts/openapi-dashboard.yaml) |
| FR-032, FR-033 (no tocar lo existente; excepciones) | "Ajustes a las pruebas existentes" (A1–A3, B1); R13 |
| FR-034 a FR-037 (pruebas, Postman, cobertura de permisos) | R11, R12; [e2e-collection.md](contracts/e2e-collection.md); [quickstart.md](quickstart.md) |

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

Sin violaciones de la constitución: no hay nada que justificar. (A diferencia de la feature 001, no hay
desviación del Principio VIII: el permiso va antes que la validación sin excepción.)

Limitaciones aceptadas, que no son violaciones:

- Mientras los datos sean ficticios, la degradación (`null`) no puede ocurrir en producción; queda definida,
  declarada en el contrato y comprobada con fuentes simuladas.
- El mensaje de validación de `limit` es único para todas las entradas inválidas (no distingue "menor que 1" de
  "no es un entero"): simple y sin repetir el valor recibido.
