# Modelo de datos: Dashboard de Plataforma

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md) | **Decisiones**: [research.md](research.md)

## Esquema persistente: sin cambios

Esta feature **no tiene datos persistentes** (FR-020): no hay tablas, modelos ORM, repositorios ni
migraciones nuevas, y `project-definition/DATA_SCHEMA.md` no cambia. El esquema vigente después de esta
feature es exactamente el de la feature 001 (migraciones `0001` y `0002`).

| Principio VI | Estado |
|---|---|
| Cambios de esquema declarados | Ninguno |
| `DATA_SCHEMA.md` (esquema objetivo) | Sin cambios; no hay reglas de datos nuevas que marcar con `-- [spec 003-platform-dashboard]` |
| Migraciones | Ninguna (la comprobación está en el [quickstart](quickstart.md)) |

Todo lo de abajo vive **en memoria**, dentro de la petición, o es de solo lectura en el código.

---

## 1. Registros del puerto de datos (`src/integrations/dashboard_source.py`)

`dataclass` congeladas, sin dependencias de Pydantic, FastAPI ni SQLAlchemy (regla de la capa de
integraciones). Son el único dato que cruza del origen al Service; **no contienen datos personales**.

| Registro | Campo | Tipo | Regla |
|---|---|---|---|
| `ClinicStatusRecord` | `id` | `int` | Identificador del estatus en el catálogo de clínicas (dato ajeno) |
| | `name` | `str` | Nombre en español («Activa», «En prueba», …) |
| `ClinicRecord` | `id` | `UUID` | Identificador de la clínica |
| | `name` | `str` | Nombre comercial |
| | `created_at` | `datetime` | **Con zona horaria** (el Service ordena por él); no se admiten fechas ingenuas |
| | `status` | `ClinicStatusRecord` | Un solo estatus por clínica |
| `ClinicCounts` | `total` | `int` ≥ 0 | Todas las clínicas, en cualquier estatus |
| | `active` | `int` ≥ 0 | Clínicas con estatus «Activa» |
| | `trial` | `int` ≥ 0 | Clínicas con estatus «En prueba» |

La relación es solo de lectura: una `ClinicRecord` tiene un `ClinicStatusRecord`; `ClinicCounts` no
referencia clínicas concretas.

## 2. Vista que construye el Service (`src/services/dashboard_service.py`)

`DashboardView` (`dataclass` congelada). Cada campo es `None` cuando **su fuente falló** (FR-027); un `0` o
una lista vacía solo significan "la fuente respondió que no hay".

| Campo | Tipo | Fuente (consulta del puerto) |
|---|---|---|
| `total_clinics` | `int \| None` | `clinic_counts().total` |
| `active_clinics` | `int \| None` | `clinic_counts().active` |
| `trial_clinics` | `int \| None` | `clinic_counts().trial` |
| `total_doctors` | `int \| None` | `doctors_total()` |
| `total_patients` | `int \| None` | `patients_total()` |
| `total_users` | `int \| None` | `users_total()` |
| `recent_clinics` | `list[ClinicRecord] \| None` | `recent_clinics(limit)`, ya ordenada y cortada por el Service |

### Degradación (FR-027 y Aclaraciones 1 y 5)

| Fuente que falla | Campos que quedan en `null` | El resto |
|---|---|---|
| `clinic_counts` | `total_clinics`, `active_clinics`, `trial_clinics` | Se devuelve |
| `recent_clinics` | `recent_clinics` (**`null`**, no `[]`) | Se devuelve |
| `doctors_total` | `total_doctors` | Se devuelve |
| `patients_total` | `total_patients` | Se devuelve |
| `users_total` | `total_users` | Se devuelve |
| Todas | Los siete campos | `200` con todo en `null`; solo el control de acceso puede impedir responder |
| Cualquier excepción que **no** sea `DashboardSourceUnavailable` | — | Error de programación: `500 internal_error`, nunca `null` silencioso |

## 3. DTOs de la respuesta (`src/dtos/dashboard.py`)

Nombres de campo en inglés (Principio VII). Los siete campos de `DashboardRead` son **obligatorios**: la
clave siempre aparece, con su valor o con `null` (FR-026).

### `DashboardRead`

| Campo | Tipo JSON | Admite `null` | Descripción |
|---|---|---|---|
| `total_clinics` | entero ≥ 0 | sí | Total de clínicas de la plataforma |
| `active_clinics` | entero ≥ 0 | sí | Clínicas activas |
| `trial_clinics` | entero ≥ 0 | sí | Clínicas con periodo de prueba |
| `total_doctors` | entero ≥ 0 | sí | Doctores de toda la plataforma |
| `total_patients` | entero ≥ 0 | sí | Pacientes de toda la plataforma |
| `total_users` | entero ≥ 0 | sí | Usuarios de toda la plataforma (incluye a los doctores) |
| `recent_clinics` | arreglo de `RecentClinicRead` (0 a 10) | sí | Las clínicas más recientes, de la más nueva a la más antigua |

### `RecentClinicRead`

| Campo | Tipo JSON | Descripción |
|---|---|---|
| `id` | cadena `uuid` | Identificador de la clínica |
| `name` | cadena | Nombre de la clínica |
| `created_at` | cadena `date-time` | ISO 8601 con zona horaria **UTC** y sufijo `Z` (`2026-10-15T16:20:00Z`) |
| `status` | `ClinicStatusRead` | Estatus de la clínica |

### `ClinicStatusRead`

| Campo | Tipo JSON | Descripción |
|---|---|---|
| `id` | entero | Identificador del estatus en el catálogo de clínicas (estable; basarse en él) |
| `name` | cadena | Nombre en español (puede cambiar) |

`ClinicStatusRead` es **distinto** de `StatusRead` (estatus de suscripción): son catálogos de dominios
diferentes. Los DTOs de salida no incluyen ningún campo que no esté en estas tablas (FR-008).

## 4. Parámetro de consulta `limit` (no es un DTO)

| Atributo | Valor |
|---|---|
| Nombre | `limit` (consulta, opcional) |
| Tipo publicado | entero, `minimum: 1` |
| Forma aceptada | solo dígitos ASCII, sin signo ni separadores ni decimales |
| Efecto | cantidad de clínicas recientes: `min(limit, 10)` |
| Sin `limit` | el valor por defecto de la configuración (3, 5 o 10) |
| Rechazo | `422 validation_error` con `errors[]` = `[{ "field": "limit", "message": … }]` |

Tabla completa de entradas y resultados en [research.md R3](research.md) y en el
[catálogo de errores](contracts/error-catalog.md).

## 5. Configuración

| Variable | Obligatoria | Valores admitidos | Por defecto | Vacía |
|---|---|---|---|---|
| `DASHBOARD_RECENT_CLINICS_LIMIT` | no | exactamente `3`, `5` o `10` (se ignoran espacios en los extremos) | `5` | Como si no estuviera (vale 5) |

- Cualquier otro valor (`4`, `0`, `11`, `-5`, `abc`, `5.5`, `5.0`, `05`, `+5`) impide arrancar y el mensaje
  nombra la variable sin mostrar su valor (FR-018).
- Se valida en el arranque, junto a las demás variables; se lee una sola vez (cambiarla exige reiniciar).
- Va comentada en `.env.example` con sus valores admitidos y su valor por defecto, y se pasa a la API desde
  `docker-compose.yml`.

## 6. Datos ficticios de la Fase 1 (`src/integrations/dummy_dashboard_source.py`)

Constantes literales: nada se calcula con el reloj ni al azar, así que son iguales en cada llamada y tras cada
reinicio (FR-021). Los conteos de clínicas se **derivan** de este mismo conjunto.

Catálogo de estatus de clínica que usa el conjunto: **1 Activa**, **2 En prueba**, **3 Suspendida**.

Clínicas, **de la más nueva a la más antigua** (el orden en que las devuelve la API). Las filas 4 y 5 tienen
exactamente la misma fecha. **En el código se almacenan en orden alfabético por nombre** (filas 3, 8, 7, 10, 5,
1, 12, 9, 2, 4, 6, 11 de esta tabla), ni por fecha ni por identificador: así la API solo devuelve el orden
correcto si ordena de verdad, y el par empatado queda almacenado al revés (San Rafael antes que Dental Sonríe),
de modo que solo sale bien si desempata por identificador ascendente (FR-015).

| # | `id` | `name` | `created_at` (UTC) | Estatus |
|---|---|---|---|---|
| 1 | `5457da22-336d-49d8-8876-4d7edb5586ae` | Clínica Santa Aurora | 2026-10-15T16:20:00Z | 2 En prueba |
| 2 | `7513bda5-dd0f-48a0-9053-383ac7ec2c92` | Consultorio Del Valle | 2026-10-12T09:05:00Z | 2 En prueba |
| 3 | `ca8b4382-8b86-4916-b3cb-002680986de3` | Centro Médico Horizonte | 2026-10-09T18:40:00Z | 1 Activa |
| 4 | `41902d77-45cb-451e-9e11-65c60e56ecf8` | Dental Sonríe | 2026-10-08T15:00:00Z | 2 En prueba |
| 5 | `e042d32c-3886-4777-953c-68db1d969e0e` | Clínica San Rafael | 2026-10-08T15:00:00Z | 1 Activa |
| 6 | `ecb1488c-d9cf-4d3c-bb5f-dd8e9365339d` | Pediatría Arcoíris | 2026-10-02T11:30:00Z | 1 Activa |
| 7 | `820e815b-8a28-448e-bb4e-152c2f89a2ad` | Clínica Los Pinos | 2026-09-26T14:10:00Z | 1 Activa |
| 8 | `dd5600ca-3d55-4f38-8c91-c843ec327e9c` | Centro de Salud Integral | 2026-09-18T10:00:00Z | 1 Activa |
| 9 | `a3e85cc2-e5c9-4106-a055-5e7dcc32bf8b` | Consultorio Alba | 2026-09-05T17:45:00Z | 1 Activa |
| 10 | `c9e9c89d-96b1-4aef-9373-98771c6557e6` | Clínica Nueva Vida | 2026-08-21T13:15:00Z | 1 Activa |
| 11 | `c0b2ebc7-9b5d-45e8-b8e1-f590ed886e9e` | Policlínica Reforma | 2026-07-30T08:30:00Z | 1 Activa |
| 12 | `8c292a31-e02e-4377-b64b-3f95d1933512` | Clínica Vista Hermosa | 2026-06-11T12:00:00Z | 3 Suspendida |

Indicadores resultantes:

| Indicador | Valor | Origen |
|---|---|---|
| `total_clinics` | **12** | clínicas del conjunto |
| `active_clinics` | **8** | las de estatus 1 (filas 3, 5 a 11) |
| `trial_clinics` | **3** | las de estatus 2 (filas 1, 2, 4) |
| `total_doctors` | **37** | constante |
| `total_patients` | **1284** | constante |
| `total_users` | **52** | constante (37 doctores + 15 más) |

### Resultados esperados por valor de `limit`

| Petición | Clínicas que llegan (por `#`) |
|---|---|
| sin `limit` (por defecto 5) | 1, 2, 3, **4, 5** (el par empatado completo, con Dental Sonríe primero) |
| `limit=1` | 1 |
| `limit=3` | 1, 2, 3 |
| `limit=4` | 1, 2, 3, **4** (el empate lo decide el identificador: entra Dental Sonríe) |
| `limit=10` | 1 a 10 (hay «Activa» y «En prueba»; la Suspendida y la fila 11 quedan fuera) |
| `limit=11`, `limit=1000`, un `limit` de 5 000 dígitos | 1 a 10, sin error |
| `DASHBOARD_RECENT_CLINICS_LIMIT=3` y sin `limit` | 1, 2, 3 |
| `DASHBOARD_RECENT_CLINICS_LIMIT=10` y sin `limit` | 1 a 10 |

### Invariantes (se comprueban con pruebas automáticas)

| Id | Invariante | Requisito |
|---|---|---|
| I1 | `active_clinics + trial_clinics ≤ total_clinics` (aquí 8 + 3 = 11 < 12) | FR-006, FR-022 |
| I2 | Clínicas recientes devueltas `≤ total_clinics` | FR-022 |
| I3 | Por estatus, las recientes «Activa» `≤ active_clinics` y las «En prueba» `≤ trial_clinics` | FR-022 |
| I4 | `total_users ≥ total_doctors` | FR-007, FR-022 |
| I5 | Todo identificador es un UUID válido y no hay dos iguales | FR-021 |
| I6 | Hay al menos 10 clínicas; entre las 10 más recientes hay «Activa» y «En prueba» y al menos dos con la misma fecha | FR-023 |
| I7 | Todas las fechas tienen zona horaria; la respuesta las muestra en UTC | FR-009 |
| I8 | Dos construcciones del conjunto, o dos consultas, dan el mismo resultado | FR-021, SC-006 |

El constructor de `DummyDashboardSource` admite otro conjunto de clínicas y otros totales (para las
pruebas): con un conjunto vacío y los totales en cero devuelve `[]` y todo en `0` (FR-014).

## 7. Ciclo de vida y transiciones

Ninguno: es un modelo de solo lectura sin estados. No hay escritura, caché ni persistencia (FR-029).
