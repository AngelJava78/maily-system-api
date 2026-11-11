# Modelo de datos: módulos de la suscripción en su propia tabla

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Esquema**:
[contracts/database-schema.sql](contracts/database-schema.sql)

## Cambios de esquema respecto al esquema vigente (Principio VI)

El esquema vigente es el que entregan las migraciones `0001` a `0006` (`001-subscriptions-api`,
`004-correct-subscriptions-api`, `005-health-monitoring`, `006-add-subscription-type` y
`007-add-clinics-limit`). Esta feature lo modifica con **una** migración nueva:

| Migración | Contenido |
|---|---|
| `0007_subscription_modules_table` | Crea `subscription_modules`; migra a esa tabla los módulos que ya tenía cada suscripción (research R5); quita de `subscriptions` la columna `module_keys` y la restricción `module_keys_check` |

## Entidades

### Módulo incluido en una suscripción (`subscription_modules`) — tabla nueva

| Columna | Tipo | Reglas | Spec |
|---|---|---|---|
| `subscription_id` | `int4` | `NOT NULL`, `REFERENCES subscriptions (id)`; parte de la clave primaria | **008** |
| `module_key` | `text` | `NOT NULL`; parte de la clave primaria; la clave de un módulo de clínica propiedad de `users-api` (sin cambios de formato, Principio IX) | **008** |

`PRIMARY KEY (subscription_id, module_key)`: sin columna `id` propia (research R1). Esa misma
clave primaria es, a la vez, lo que resuelve FR-002 (ninguna fila duplicada: la clave primaria lo
impide; ninguna fila sin su suscripción: la `FOREIGN KEY` lo impide). Sin índice adicional sobre
`module_key` por sí solo (research R9): ninguna consulta de esta especificación lo necesita.

### Suscripción (`subscriptions`) — columna que se quita

| Columna que se quita | Por qué |
|---|---|
| `module_keys` (`text[]`) y su `CHECK` `module_keys_check` | Sustituida por la relación con `subscription_modules`: una suscripción ya no guarda sus módulos en una columna propia, sino en una fila por módulo en la tabla nueva (FR-001) |

El resto de las columnas: sin cambios, ver
[specs/007-add-clinics-limit/data-model.md](../007-add-clinics-limit/data-model.md).

**La regla "`patients` siempre incluido" ya no es un `CHECK` de base de datos** (research R2): un
`CHECK` de PostgreSQL no puede ver otras filas de la misma tabla, así que no hay forma declarativa
de expresar "existe una fila de esta suscripción con `module_key = 'patients'`" sobre
`subscription_modules`. Sigue siendo, igual que la validación contra `users-api` y las reglas de
prerrequisito (ninguna de las tres es hoy una restricción de base de datos), una garantía exclusiva
de `SubscriptionService._resolve_modules` — sin cambios de código en esa función.

**Migración de los datos existentes, sin backfill fuera de Alembic** (research R5, a diferencia de
`006`): `INSERT INTO subscription_modules (subscription_id, module_key) SELECT id,
unnest(module_keys) FROM subscriptions` — una sola sentencia dentro de la propia migración `0007`,
porque el dato de origen ya vive en esta misma base de datos (resuelve FR-003/SC-002).

**Reversibilidad** (research R6): `downgrade` de `0007` hace lo inverso en orden inverso: agrega
de nuevo `module_keys` con su valor por defecto, la rellena con `array_agg(module_key ORDER BY
module_key)` por cada suscripción (con `patients` como respaldo si alguna no tuviera ninguna fila),
recrea el `CHECK` y, por último, elimina `subscription_modules`.

## Modelo ORM (Principio I, II)

| Cambio | Archivo |
|---|---|
| Columna `module_keys` → relación `modules: Mapped[list["SubscriptionModule"]]` (`lazy="raise"`, `order_by="SubscriptionModule.module_key"`) + propiedad de solo lectura `module_keys` (`[m.module_key for m in self.modules]`, research R3/R4) | `src/models/subscription.py` |
| Modelo nuevo `SubscriptionModule` (`__tablename__ = "subscription_modules"`; `subscription_id`, `module_key`, ambos parte de la clave primaria compuesta) | `src/models/subscription_module.py` (nuevo) |

`SubscriptionRead.model_validate(subscription)` (`from_attributes=True`,
`src/routers/subscriptions.py::_to_read`) sigue leyendo `subscription.module_keys` exactamente
igual que hoy, ahora resuelto por la propiedad en vez de por la columna: **cero cambios** en
`src/dtos/subscription.py` (research R3). El contrato publicado (`SubscriptionRead`,
`SubscriptionCreate`, `SubscriptionUpdate`) es exactamente el mismo que documenta
[specs/007-add-clinics-limit/contracts/openapi-subscriptions.yaml](../007-add-clinics-limit/contracts/openapi-subscriptions.yaml)
(FR-004): esta especificación no genera un `openapi-subscriptions.yaml` propio porque no cambia
nada en él.

## Repository (Principio I)

| Método | Qué cambia |
|---|---|
| `create(...)` | Sigue recibiendo `module_keys: list[str]` ya resuelto por el Service (sin cambios en esa firma). Internamente: `INSERT` de la suscripción + `INSERT` por lotes de sus filas en `subscription_modules`, en una sola transacción (research R7) |
| `update(subscription_id, changes)` | Si `changes` incluye `"module_keys"`, se saca de `changes` antes de construir el `UPDATE` de `subscriptions` (que sigue ejecutándose siempre, con el resto de `changes`, para conservar la comprobación de existencia/estatus y el disparador de `updated_at`, research R8); después, `DELETE` + `INSERT` reemplazan por completo las filas de `subscription_modules` de esa suscripción. Una sola transacción, un solo commit, igual que hoy (research R7) |
| `_select_with_relations()` | Agrega `selectinload(Subscription.modules)` (colección uno-a-muchos: `selectinload`, no `joinedload`, para no multiplicar filas de la suscripción en `list_current()`) |
| `src/repositories/transactions.py` | Gana una variante de `execute_and_commit` para más de una sentencia de escritura antes de un único commit (research R7), reutilizada por `create()` y `update()` |

`SubscriptionService` (`create()`, `update()`, `_resolve_modules()`) **no cambia**: sigue pasando
`module_keys: list[str]` ya validado y ordenado al Repository, exactamente como hoy (research
R3/R8). Tampoco cambian las reglas que resuelve esa función (validación contra `users-api`,
prerrequisitos entre módulos, `patients` siempre incluido) — ver
[specs/004-correct-subscriptions-api/spec.md](../004-correct-subscriptions-api/spec.md) FR-015 a
FR-020, sin cambios aquí.

## Datos ajenos (sin relación con esta feature)

El catálogo de módulos de clínica (sus nombres, descripciones y cuáles están activos) sigue siendo
propiedad de `users-api` (`GET /api/v1/modules`): esta especificación no lo copia ni lo cachea, solo
guarda, en la tabla nueva, qué claves eligió cada suscripción — exactamente la misma relación de
responsabilidad que ya fijó `004` para la columna `module_keys` que esta feature sustituye
(Principio IX, sin cambios).
