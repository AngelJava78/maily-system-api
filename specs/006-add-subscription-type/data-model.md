# Modelo de datos: Tipo de suscripción (Individual o Empresarial)

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Esquema**:
[contracts/database-schema.sql](contracts/database-schema.sql)

**Revisión tras Clarifications (2026-10-26)**: el tipo es un catálogo propio (tabla), no una columna
con `CHECK` fijo. Este documento reemplaza la versión anterior.

## Cambios de esquema respecto al esquema vigente (Principio VI)

El esquema vigente es el que entregan las migraciones `0001` a `0004` (`001-subscriptions-api`,
`004-correct-subscriptions-api` y `005-health-monitoring`). Esta feature lo modifica con **una**
migración (`0005`, reescrita tras la corrección: no se usó fuera de este repositorio, así que se
corrige en el mismo archivo en vez de apilar una `0006` sobre un diseño que se abandona):

| Migración | Contenido |
|---|---|
| `0005_add_subscription_type` | Crea `subscription_types` (catálogo, como `subscription_statuses`); la siembra con `Individual` (id 1) y `Empresarial` (id 2); agrega `subscriptions.subscription_type_id int4 NOT NULL DEFAULT 1 REFERENCES subscription_types(id)` |

## Entidades

### Tipo de suscripción (`subscription_types`) — tabla nueva

Igual forma que `subscription_statuses` (research R1):

| Columna | Tipo | Reglas |
|---|---|---|
| `id` | `serial4` | Clave primaria. `1` = Individual, `2` = Empresarial (constantes `SubscriptionType.INDIVIDUAL`/`.ENTERPRISE`, research R8); quien consume la API MUST basarse en el `id`, no en el `name` |
| `name` | `varchar(50)` | `NOT NULL UNIQUE`; dato del catálogo, editable a mano |
| `description` | `text` | Opcional |

Administrado a mano, igual que el estatus: esta especificación **no** agrega ninguna operación de
la API para crear, editar ni eliminar un tipo (FR-001). Agregar un tercero en el futuro es una fila
nueva en esta tabla (por una migración de datos o a mano), no una migración que reescriba una
restricción.

### Suscripción (`subscriptions`) — columna nueva

| Columna | Tipo | Reglas | Spec |
|---|---|---|---|
| `subscription_type_id` | `int4` | `NOT NULL DEFAULT 1`, `REFERENCES subscription_types(id)`; la aplicación nunca la escribe fuera de `create()` (inmutabilidad real, FR-004) | **006** |

El resto de las columnas: sin cambios, ver
[specs/004-correct-subscriptions-api/data-model.md](../004-correct-subscriptions-api/data-model.md).

**Por qué `DEFAULT 1` resuelve FR-001/FR-002/FR-008 sin backfill aparte**: igual que `status_id
DEFAULT 1`, PostgreSQL asigna el valor por defecto a cada fila existente en la misma sentencia
`ALTER TABLE … ADD COLUMN` (siempre que la fila 1 de `subscription_types` ("Individual") ya exista,
por eso la tabla se crea y se siembra **antes** de agregar la columna, en la misma migración).
Ninguna suscripción pasa, ni siquiera momentáneamente, por un estado sin tipo.

**Por qué FR-009/FR-010 (ascender a Empresarial las que ya tenían más de una clínica) sigue sin vivir
en esta migración**: sin cambios respecto a la versión anterior de este documento (la API de
clínicas no tiene credenciales de servicio; ver research R3/R4 y el script de reconciliación, más
abajo).

**Nombres de restricciones nuevos** (automáticos de PostgreSQL vía `NAMING_CONVENTION`,
`src/models/base.py`): `subscription_types_pkey`, `subscription_types_name_key`,
`subscriptions_subscription_type_id_fkey`.

## Reconciliación de tipos (FR-009, FR-010; no es una migración de Alembic)

Sin cambios de fondo respecto a la versión anterior de este documento, salvo el valor que escribe:
**`SubscriptionRepository.mark_enterprise(ids)` ahora hace `UPDATE subscriptions SET
subscription_type_id = 2 WHERE id = ANY(:ids)`** (antes: `subscription_type = 'enterprise'`), usando
la constante `SubscriptionType.ENTERPRISE` (research R8), nunca el número suelto. El resto del flujo
(`src/scripts/backfill_subscription_types.py`, el reintento sin límite, el token) no cambia.

## DTOs (Principio II)

| DTO | Campo | Notas |
|---|---|---|
| `SubscriptionTypeRead` *(nuevo, `src/dtos/subscription_type.py`)* | `id`, `name` | Igual forma que `StatusRead` (`src/dtos/status.py`) |
| `SubscriptionRead` | `subscription_type: SubscriptionTypeRead` | Objeto anidado (como `status`), no una cadena |
| `SubscriptionCreate` | `subscription_type_id: int` | Obligatorio, entero estricto, `> 0`; no se valida contra una lista fija (research R5): si no existe en el catálogo, la clave foránea lo rechaza al escribir |
| `SubscriptionUpdate` | *(no se agrega)* | Sin cambios: a propósito, para la inmutabilidad de FR-004 |

### Validación de `subscription_type_id` (DTO + Service)

| Campo | Capa | Regla | Mensaje si falla |
|---|---|---|---|
| `subscription_type_id` (crear) | DTO (Pydantic, sin E/S) | Entero estricto, `> 0`, obligatorio (como `SubscriptionStatusChange.status_id`) | «El tipo de suscripción es obligatorio y debe ser un número entero positivo.» (falta, `null`, no es entero, o `<= 0`) |
| `subscription_type_id` (crear) | Service (clave foránea al escribir, research R5) | Debe existir en `subscription_types`; se descubre al intentar el `INSERT`, no con una lectura previa | «No se encontró el tipo de suscripción con el identificador {subscription_type_id}.» (código nuevo `subscription_type_not_found`, 422) |
| `subscription_type_id` (actualizar) | DTO (Pydantic, `extra="forbid"`) | No declarado en `SubscriptionUpdate` | «El tipo de suscripción no puede modificarse una vez creada.» |

Contrato exacto: [contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml)
(esquema `SubscriptionTypeRead`, reutilizado por `SubscriptionRead`).

## Reglas derivadas (nuevas o corregidas de esta feature)

- **Inmutabilidad por ausencia, no por comprobación** (FR-004): sin cambios de fondo; solo cambia el
  nombre del campo ausente (`subscription_type_id` en vez de `subscription_type`).
- **Sin carrera de escritura, sin lectura previa** (research R5): el `INSERT` de `create()` intenta
  escribir `subscription_type_id` tal cual; si no existe, `ForeignKeyViolationError`
  (`src/repositories/errors.py`, ya existe) se traduce a `SubscriptionTypeNotFoundError` (422) en el
  Service, exactamente como `UniqueViolationError` ya se traduce para el nombre repetido.
- **El límite de clínicas por tipo (FR-006) es una regla de los dos valores de hoy, no del
  mecanismo de catálogo** (research R8): un tercer tipo agregado a mano no hereda ninguna regla de
  clínicas; el código solo reconoce reglas para `SubscriptionType.INDIVIDUAL`/`.ENTERPRISE`
  explícitamente, igual que hoy solo hay reglas de negocio para los cuatro estatus con significado
  propio, nunca para un quinto estatus agregado a mano.
- **Reversibilidad**: `downgrade` de `0005` quita `subscription_type_id` de `subscriptions` y luego
  elimina `subscription_types` (orden inverso al de `upgrade`); se pierde el dato, igual criterio
  que cualquier `drop_column`/`drop_table` de este proyecto.

## Datos ajenos (solo lectura, no se guardan)

Sin cambios respecto a la versión anterior de este documento: el número de clínicas sigue viniendo
del API de clínicas en cada lectura, nunca almacenado; el script de reconciliación lo lee una sola
vez para decidir el tipo inicial de lo que ya existía.
