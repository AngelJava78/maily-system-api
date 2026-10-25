# Modelo de datos (Fase 1): Monitoreo de salud de los servicios de Maily

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Investigación**: [research.md](research.md)

La feature añade **una tabla** (el registro de componentes) y varias estructuras que viven solo en memoria
o en la configuración: el resultado de salud, el estado público, la copia del registro, el horario de la
base de datos y la lista de hosts permitidos. Los nombres de campo son parte del acuerdo con
maily-backoffice 016 (y, los del contrato v1, también con mailySoft-usuarios 016 y mailySoft-pacientes 008).

## 1. Cambio de esquema respecto al vigente (Principio VI)

| | Antes (migraciones 0001–0003) | Después (0004) |
|---|---|---|
| Tablas | `subscription_statuses`, `subscriptions` | + `monitored_components` |
| Índices con nombre | `subscriptions_name_not_deleted_key` | + `monitored_components_code_not_deleted_key` |
| Funciones | `set_updated_at()` | Sin cambios (se reutiliza) |
| Disparadores | `subscriptions_set_updated_at` | + `monitored_components_set_updated_at` |
| Datos iniciales | 4 estatus | Sin cambios: el registro **empieza vacío** (FR-031) |

Ninguna otra tabla cambia (FR-032). La migración `0004_monitored_components.py` revisa `0003`, es reversible
(su `downgrade` borra el disparador, el índice y la tabla, pero **no** la función, que es de 0001) y
reproduce [contracts/database-schema.sql](contracts/database-schema.sql). `project-definition/DATA_SCHEMA.md`
añade la tabla, el índice y el disparador con el comentario `-- [spec 005-health-monitoring]` y amplía su
tabla de nombres de restricciones. `project-definition/create_database.sql` no cambia: crea hasta 0002 y
`alembic upgrade head` aplica después 0003 y 0004.

## 2. Componente registrado (tabla `monitored_components`)

| Columna | Tipo | Nula | Por defecto | Reglas (DTO y `CHECK`) |
|---|---|---|---|---|
| `id` | `uuid` | no | `gen_random_uuid()` | Lo asigna el servicio; no se envía ni se modifica |
| `code` | `varchar(50)` | no | — | 2 a 50 caracteres; `^[a-z][a-z0-9]*(-[a-z0-9]+)*$` (empieza con letra, sin guion final ni dos seguidos); no `maily-system-api` ni `database`; único entre los no eliminados |
| `name` | `varchar(100)` | no | — | 1 a 100 caracteres, sin espacios en los extremos (se recortan al recibir) |
| `kind` | `varchar(20)` | no | — | `service` o `frontend` |
| `base_url` | `varchar(255)` | no | — | Reglas de [research R14](research.md#r14-ssrf-y-lista-permitida-fr-025-fr-026-fr-027-sc-004); host en la lista permitida al registrar o cambiarla; se guarda con esquema y host en minúsculas y sin barra final |
| `live_path` | `varchar(200)` | no | servicio: `/health/live` | Reglas de rutas de R14; en un frontend es su ruta de salud y es obligatoria |
| `ready_path` | `varchar(200)` | sí | servicio: `/health/ready` | Servicio: obligatoria (no se anula); frontend: **nula** |
| `info_path` | `varchar(200)` | sí | servicio: `/info`; frontend: nula | Servicio: obligatoria (no se anula); frontend: opcional |
| `enabled` | `boolean` | no | `true` | — |
| `sort_order` | `int4` | no | `0` | 0 a 9999 |
| `created_at` | `timestamptz` | no | `CURRENT_TIMESTAMP` | — |
| `updated_at` | `timestamptz` | no | `CURRENT_TIMESTAMP` | Lo mueve el disparador en cada `UPDATE` |
| `deleted_at` | `timestamptz` | sí | `NULL` | Marca de baja lógica con su fecha; **no se publica** |

Restricciones con nombre (las usa el código o las pruebas): `monitored_components_pkey`,
`monitored_components_code_check`, `monitored_components_name_check`, `monitored_components_kind_check`,
`monitored_components_sort_order_check`, `monitored_components_service_paths_check` (un servicio tiene
`ready_path` e `info_path`) y `monitored_components_frontend_ready_path_check` (un frontend no tiene
`ready_path`). El índice único parcial `monitored_components_code_not_deleted_key` (`code` donde
`deleted_at IS NULL`) decide los conflictos de código; el Service lo reconoce por su nombre.

### Ciclo de vida

```text
          alta (201)                       baja (204)
  ───────────────────►  VIGENTE  ─────────────────────►  ELIMINADO (deleted_at con fecha)
                        │      ▲                          · no aparece en ningún lado (404)
     modificar (200)    │      │  habilitar               · su code queda libre: un alta nueva
     enabled=false ─────┘      └───── enabled=true          crea otra fila con otro id
                   HABILITADO ⇄ DESHABILITADO
                   (se consulta)  (sigue en el registro y en el listado; no se consulta ni sale en la salud)
```

### Modelo ORM

`src/models/monitored_component.py`: `MonitoredComponent(Base)` con las columnas de arriba (`Uuid` de
SQLAlchemy con `server_default=text("gen_random_uuid()")`), las `CheckConstraint` con los nombres cortos que
completa la convención de `Base` (`code_check`, `service_paths_check`…) y el `Index` único parcial
declarado como en `Subscription`. Se exporta en `src/models/__init__.py` para que
`test_models_match_migrations.py` lo compare con la migración.

## 3. DTOs del registro (`src/dtos/monitored_component.py`)

Todos con `extra="forbid"` y `str_strip_whitespace=True`. Los mensajes de validación están en el
[catálogo de errores](contracts/error-catalog.md).

| DTO | Uso | Campos |
|---|---|---|
| `MonitoredComponentCreate` | Cuerpo de `create_monitored_component` | `code`, `name`, `kind`, `base_url` (obligatorios); `live_path`, `ready_path`, `info_path`, `enabled`, `sort_order` (opcionales) |
| `MonitoredComponentUpdate` | Cuerpo de `update_monitored_component` | Los mismos, todos opcionales; al menos uno; `null` solo donde la columna lo admite |
| `MonitoredComponentRead` | Respuesta de alta, consulta, listado y modificación | `id`, `code`, `name`, `kind`, `base_url`, `live_path`, `ready_path`, `info_path`, `enabled`, `sort_order`, `created_at`, `updated_at` (sin `deleted_at`) |

Reglas que dependen de `kind`. Las aplica el Service del registro, no un validador de modelo del DTO:
Pydantic no puede atribuir a un campo el error de un validador de modelo (saldría en `body`), y el
catálogo los pide en el campo afectado. El Service distingue «no enviado» de «enviado como `null`» con el
`model_fields_set` del DTO y usa la misma función para el alta y para el resultado de una modificación:

| `kind` | `live_path` | `ready_path` | `info_path` |
|---|---|---|---|
| `service` | Por defecto `/health/live`; `null` → 422 | Por defecto `/health/ready`; `null` → 422 | Por defecto `/info`; `null` → 422 |
| `frontend` | Obligatoria; ausente o `null` → 422 | Debe ser nula: cualquier valor → 422 | Opcional (nula por defecto) |

**Modificación** (FR-028): el DTO valida los campos enviados (tipos, formatos, campos desconocidos o no
modificables como `id`, las fechas o `deleted_at`, y «al menos uno»). El Service fusiona lo enviado con la
fila bloqueada y valida el **resultado** con las reglas del alta: si pasa a `service` y sus rutas guardadas
son nulas sin que se envíen, toma los valores por defecto; si pasa a `frontend` con `ready_path` guardada y
no se envía `ready_path: null`, responde 422 en `ready_path`. Los errores del resultado salen con el mismo
cuerpo `validation_error` (research R4 y R15).

`base_url` en `MonitoredComponentRead` es el **único** lugar de la API donde se publica la dirección
(FR-023).

## 4. Registros internos (Service e integraciones)

Clases `dataclass(frozen=True, slots=True)` sin Pydantic ni FastAPI (como `dashboard_source.py`).

| Registro | Módulo | Campos | Para qué |
|---|---|---|---|
| `ComponentTarget` | `services/health_service.py` | `id`, `code`, `name`, `kind`, `base_url`, `live_path`, `ready_path`, `info_path`, `sort_order` | Lo que se chequea de un registrado; forma de la copia en memoria |
| `ProbeResponse` | `integrations/health_probe.py` | `status_code` (o `None`), `body` (bytes ≤ 64 KiB o `None`), `failure` (código de FR-018 o `None`), `latency_ms` | Resultado crudo y acotado de una llamada; nunca sale del proceso |
| `CheckResult` | `integrations/health_contract.py` | `name`, `status` (`ok`/`error`), `latency_ms`, `error` | Un chequeo depurado (forma de `/health/ready`) |
| `BuildData` | `integrations/health_contract.py` | `version`, `commit`, `build_date`, `environment` (texto o `unknown`) | Datos de build depurados |
| `CallOutcome` | `integrations/health_contract.py` | `ok` (bool), `error` (código o `None`), `checks` (tupla de `CheckResult`), `latency_ms` | Interpretación de `live`/`ready`/ruta de salud de un frontend |
| `ComponentHealth` | `services/health_service.py` | Los trece campos de FR-012 | Un componente del resultado |
| `HealthResult` | `services/health_service.py` | `status`, `checked_at`, `registry_available`, `components` (tupla) | Lo que se guarda en la caché y sirve a las dos rutas |

## 5. Respuestas de salud (`src/dtos/health.py`)

Las fechas se publican en ISO 8601 UTC con `Z`. Ningún DTO de salud tiene un campo para direcciones, hosts,
IP, cuerpos o mensajes de excepción.

| DTO | Ruta | Campos |
|---|---|---|
| `LiveRead` | `GET /health/live` | `status` = `ok` |
| `CheckRead` | (anidado) | `name`, `status` (`ok`/`error`), `latency_ms` (entero ≥ 0 o `null`), `error` (`null`, `timeout`, `connection_error`, `not_configured`, `unexpected_error`) |
| `ReadyRead` | `GET /health/ready` (200 y 503) | `status` (`ok`/`unavailable`), `checks` (lista de `CheckRead`; aquí, solo `database`) |
| `InfoRead` | `GET /info` | `service` = `maily-system-api`, `version`, `commit`, `build_date`, `environment` (texto o `unknown`) |
| `ComponentHealthRead` | (anidado) | `code`, `name`, `kind` (`service`/`database`/`frontend`), `status` (`up`/`degraded`/`down`/`stopped`/`unknown`), `latency_ms`, `checked_at`, `version`, `commit`, `build_date`, `environment`, `checks`, `error` (código de FR-018 o `null`), `next_start_at` (fecha o `null`) |
| `HealthRead` | `GET /api/v1/health` | `status` (`ok`/`degraded`/`down`), `checked_at`, `registry_available`, `components` (nunca nula) |
| `PublicComponentRead` | (anidado) | **solo** `code`, `name`, `kind`, `status`, `next_start_at` |
| `PublicStatusRead` | `GET /health/status` | **solo** `status`, `checked_at`, `components` |

`PublicStatusRead` y `PublicComponentRead` se construyen campo por campo desde el mismo `HealthResult`
(nunca copiando el componente completo), y una prueba de contrato compara sus claves con la lista cerrada de
FR-047 (SC-014). Añadir un campo a la salud no lo añade al estado público.

## 6. Estado en memoria del proceso (`HealthState`)

Uno por aplicación (`app.state.health`, creado en `create_app()`); sin E/S ni configuración. Ver research
[R10](research.md#r10-caché-agregación-compartida-y-periodo-mínimo-del-estado-público-fr-020-fr-048-sc-006-sc-016) y
[R11](research.md#r11-copia-del-registro-en-memoria-fr-036-sc-009).

| Campo | Contenido | Cambia cuando |
|---|---|---|
| `generation` | Entero | Alta, modificación o baja exitosas (`invalidate()`) |
| `last` | `HealthResult`, instante monótono en que terminó y su generación, o nada | Termina una agregación de la generación vigente; se borra al invalidar |
| `in_flight` | Generación y tarea de la agregación en curso, o nada | Se lanza o termina una agregación (a lo más una) |
| `registry_snapshot` | Tupla de `ComponentTarget`, o `None` si nunca se leyó | Cada lectura exitosa del registro (también vacía) |
| `readiness_task` | Tarea de la comprobación de `/health/ready` en curso, o nada | Se lanza o termina una comprobación |
| `last_statuses` | Estado anterior de cada componente y de `ready` | Cada agregación o comprobación (para avisar solo de cambios, research R23) |

Edad máxima de un resultado guardado: `HEALTH_CACHE_SECONDS` para `GET /api/v1/health` y
`max(HEALTH_CACHE_SECONDS, 15)` para `GET /health/status`.

## 7. Configuración (`src/config.py`)

Todas opcionales; vacía = no configurada; un valor inválido impide arrancar y el mensaje nombra la variable,
nunca su valor (FR-038). Se leen una vez (cambiarlas exige reiniciar).

| Variable | Clase | Valores | Por defecto | Valor que usa el servicio |
|---|---|---|---|---|
| `HEALTH_CHECK_TIMEOUT_SECONDS` | `HealthSettings` | Entero 1–10 (solo dígitos) | `3` | `int` |
| `HEALTH_CACHE_SECONDS` | `HealthSettings` | Entero 0–300 | `15` | `int` |
| `HEALTH_READY_TIMEOUT_SECONDS` | `HealthSettings` | Entero 1–10 | `2` | `int` |
| `HEALTH_ALLOWED_HOSTS` | `HealthSettings` | Lista de FR-027 (research R14) | Sin lista | `AllowedHosts` |
| `DATABASE_SCHEDULE_TIMEZONE` | `HealthSettings` + `database_schedule_from` | Zona IANA | Sin horario | `DatabaseSchedule.zone` (`ZoneInfo`) |
| `DATABASE_SCHEDULE_DAYS` | ídem | Días en inglés, separados por comas, sin repetir | Sin horario | `DatabaseSchedule.days` (`frozenset[int]`) |
| `DATABASE_SCHEDULE_START` | ídem | `HH:MM` 24 h | Sin horario | `DatabaseSchedule.start` (`time`) |
| `DATABASE_SCHEDULE_END` | ídem | `HH:MM` 24 h, mayor que el inicio | Sin horario | `DatabaseSchedule.end` (`time`) |
| `APP_COMMIT_SHA` | `BuildSettings` | 7–64 hexadecimales | `unknown` | Texto en minúsculas |
| `APP_BUILD_DATE` | `BuildSettings` | ISO 8601 con `Z` o desfase | `unknown` | Fecha UTC (`Z`) |
| `APP_ENVIRONMENT` | `BuildSettings` | 1–50 de `[A-Za-z0-9._-]` | `unknown` | Texto |

Objetos de valor que entrega la configuración:

- **`HealthConfig`**: `check_timeout_seconds`, `ready_timeout_seconds`, `cache_seconds`, `allowed_hosts` y
  `schedule` (o `None`). Es lo que reciben los Services (por una dependencia de FastAPI que las pruebas
  sustituyen); así las pruebas usan tiempos de fracciones de segundo sin pasar por la validación del
  entorno (research R20).

- **`AllowedHosts`**: `exact: frozenset[str]` y `suffixes: tuple[str, ...]`; `allows(host)` compara en
  minúsculas (sufijo: `host.endswith(sufijo)` y `host != sufijo[1:]`). Vacía: no admite ninguno.
- **`DatabaseSchedule`**: `zone`, `days`, `start`, `end`. Las reglas de la ventana y del próximo encendido
  están en `src/services/health_schedule.py` (research R12).
- **`BuildInfo`**: `service`, `version` (de `src.VERSION`), `commit`, `build_date`, `environment`; la usan
  `/info` y el componente integrado `maily-system-api`.

Valores recomendados (iguales al runbook `Deploy-PgAutoShutdown.ps1`): `DATABASE_SCHEDULE_TIMEZONE=America/Mexico_City`,
`DATABASE_SCHEDULE_DAYS=Monday,Tuesday,Wednesday,Thursday,Friday`, `DATABASE_SCHEDULE_START=08:00` y
`DATABASE_SCHEDULE_END=20:00`.

## 8. Estados y reglas (resumen)

- **Componente registrado** (servicio o frontend): `up`, `degraded`, `down` o `unknown` según
  [research R8](research.md#r8-reglas-de-estado-fr-014-a-fr-018).
- **`maily-system-api`**: `up` o `degraded` (`not_ready`); nunca `down` (está atendiendo la consulta).
- **`database`**:

  ```text
  consulta responde ───────────────────────────────► up       (next_start_at null)
  consulta falla ─┬─ sin horario ──────────────────► down     (next_start_at null)
                  ├─ dentro de [inicio, fin) local ─► down     (next_start_at null)
                  └─ fuera de la ventana ──────────► stopped  (error = causa observada;
                                                               next_start_at = próximo inicio, UTC)
  ```

- **Estado global**: `down` > `degraded` (si hay `degraded`, `stopped` o `unknown`) > `ok` (FR-017).
- **`registry_available`**: `true` si la lectura de esta agregación terminó bien (aunque esté vacía);
  `false` si se usó la copia o no hay copia.
