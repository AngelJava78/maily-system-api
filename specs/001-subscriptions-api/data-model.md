# Modelo de datos: API REST de Suscripciones

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Esquema**:
[contracts/database-schema.sql](contracts/database-schema.sql)

## Cambios de esquema respecto al esquema vigente (Principio VI)

Es la **primera** feature del servicio: no existe esquema vigente anterior. Esta feature introduce
**todo** el esquema, mediante dos migraciones de Alembic:

| Migración | Contenido |
|---|---|
| `0001_subscriptions_schema` | Tablas `subscription_statuses` y `subscriptions`, índice único parcial del nombre, restricciones `CHECK`, función y disparador de `updated_at` |
| `0002_seed_subscription_statuses` | Datos iniciales del catálogo de estatus (ids 1 a 4) y ajuste de su secuencia |

`project-definition/DATA_SCHEMA.md` (esquema objetivo) **se crea en esta feature** con el contenido de
`contracts/database-schema.sql`, cada regla marcada con `-- [spec 001-subscriptions-api]`. No se
cargan suscripciones: los seis planes de los pantallazos son ejemplos (spec, Assumptions).

## Entidades

### Estatus de suscripción (`subscription_statuses`)

Catálogo que se administra **a mano** (sin API). Los estatus del sistema se reconocen por su
identificador, no por su nombre; no deben eliminarse ni renumerarse.

| Columna | Tipo | Reglas |
|---|---|---|
| `id` | `serial4` | Clave primaria |
| `name` | `varchar(50)` | `NOT NULL`, único |
| `description` | `text` | Opcional |

| `id` | `name` | Significado (spec, Assumptions) |
|---|---|---|
| 1 | Activa | Disponible y ofrecida a clínicas nuevas. Estatus de una suscripción nueva |
| 2 | Inactiva | Retirada de la oferta, conservada; las clínicas que ya la tienen siguen con ella |
| 3 | Bloqueada | Suspendida por la administración |
| 4 | Eliminada | Baja lógica: fuera de toda consulta y operación |

Un estatus añadido a mano tendrá `id` ≥ 5 (la secuencia se deja en 4 al cargar los datos).

### Suscripción (`subscriptions`)

| Columna | Tipo | Reglas |
|---|---|---|
| `id` | `serial4` | Clave primaria |
| `name` | `varchar(100)` | `NOT NULL`, `CHECK (btrim(name) <> '')`; único (sin distinguir mayúsculas) entre las no eliminadas |
| `description` | `varchar(500)` | Opcional (`NULL` = sin descripción) |
| `monthly_price` | `numeric(10,2)` | `NOT NULL`, `CHECK (monthly_price >= 0)`; pesos mexicanos |
| `features` | `text[]` | `NOT NULL DEFAULT '{}'`, `CHECK (cardinality(features) <= 20)`; lista **ordenada** de textos libres |
| `status_id` | `int4` | `NOT NULL DEFAULT 1`, clave foránea a `subscription_statuses(id)` |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT CURRENT_TIMESTAMP` |
| `updated_at` | `timestamptz` | `NOT NULL DEFAULT CURRENT_TIMESTAMP`; lo actualiza un disparador `BEFORE UPDATE` |

**Índice único parcial** `subscriptions_name_not_deleted_key` sobre `lower(name)` donde
`status_id <> 4` (FR-014): una Inactiva o Bloqueada sigue reservando su nombre; el de una Eliminada
queda libre. Es la **única** regla de unicidad; el Service la traduce a `409`.

**Sin columna de conteo de clínicas ni tabla de asignaciones**: el número de clínicas es un dato del
API de clínicas (FR-009, Principio IX) y solo existe en las respuestas (`clinics_count`).

**Nombres de restricciones**: los automáticos de PostgreSQL (`subscriptions_pkey`,
`subscriptions_status_id_fkey`, `subscriptions_name_check`, `subscriptions_monthly_price_check`,
`subscriptions_features_check`, `subscription_statuses_name_key`); llevan nombre explícito el índice
parcial y el disparador. Los modelos reproducen esos nombres con una `NAMING_CONVENTION` (patrón de
la referencia) y `alembic check` confirma que modelos y migraciones coinciden.

## Ciclo de vida del estatus

```text
                  ┌──────────── cambiar estatus (1, 2 o 3) ────────────┐
                  ▼                                                     │
 crear ──► [1 Activa] ◄──► [2 Inactiva] ◄──► [3 Bloqueada] ─────────────┘
              │                 │                 │
              └───── eliminar (solo sin clínicas) ┴──────► [4 Eliminada]  (sin retorno con esta API)
```

| Desde | Operación | Hacia | Condición |
|---|---|---|---|
| (nueva) | crear | 1 Activa | Nombre libre |
| 1, 2, 3 o ≥ 5 | cambiar estatus | 1, 2 o 3 | Distinto del actual (si no, `409 subscription_status_unchanged`) |
| 1, 2, 3 o ≥ 5 | eliminar | 4 Eliminada | Sin clínicas asignadas y comprobable (`409 subscription_has_clinics` / `503 clinics_check_unavailable`) |
| 4 | cualquiera | — | `404` (se comporta como inexistente) |

## Reglas derivadas

- **Vigente** = `status_id <> 4`. Solo las vigentes aparecen en el listado y en las consultas.
- **Orden del listado**: `created_at` ascendente y, a igualdad, `id` ascendente (FR-006).
- **`updated_at`** cambia con cualquier `UPDATE`, también con el cambio de estatus.
- **Concurrencia**: el índice único decide los nombres repetidos; las bajas y los cambios de estatus
  son una sola sentencia condicionada (`WHERE … status_id <> 4`), de modo que con solicitudes
  simultáneas solo una prospera (research R11 y R12).
- **Reversibilidad**: `downgrade` de `0002` borra los estatus y falla si hay suscripciones que los
  usan (restricción foránea); `downgrade` de `0001` elimina las dos tablas. Solo para bases de
  desarrollo.

## DTOs (Principio II)

Se listan por su contenido; el contrato exacto está en
[contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml).

| DTO | Campos | Notas |
|---|---|---|
| `StatusRead` | `id`, `name` | Estatus como objeto |
| `SubscriptionRead` | `id`, `name`, `description`, `monthly_price`, `features`, `status`, `clinics_count`, `created_at`, `updated_at` | `monthly_price` es cadena con 2 decimales; `clinics_count` es entero o `null` (= no disponible) |
| `SubscriptionCreate` | `name`, `description?`, `monthly_price`, `features?` (por defecto `[]`) | `extra="forbid"`; textos recortados; `description` vacía = `null` |
| `SubscriptionUpdate` | `name?`, `description?`, `monthly_price?`, `features?` | `extra="forbid"`; al menos un campo; `name` y `monthly_price` no admiten `null`; `features: []` vacía la lista |
| `SubscriptionStatusChange` | `status_id` | Solo 1, 2 o 3 |
| `ErrorResponse` / `FieldError` | `code`, `message`, `errors?` | Formato uniforme (FR-021) |

Los DTOs de entrada **no** admiten `id`, `status`, `clinics_count`, `created_at` ni `updated_at`
(se rechazan como campos no permitidos, FR-015 y FR-019). Ningún DTO contiene el token.

## Datos ajenos (solo lectura, no se guardan)

| Dato | Dueño | Cómo llega |
|---|---|---|
| Identidad y permisos de la persona | API de usuarios | Consulta por petición con el token ([contrato](contracts/users-api-integration.md)) |
| Número de clínicas por suscripción | API de clínicas | Consulta en cada lectura ([contrato](contracts/clinics-api-integration.md)) |
