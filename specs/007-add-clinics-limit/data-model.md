# Modelo de datos: Límite de clínicas por suscripción

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Esquema**:
[contracts/database-schema.sql](contracts/database-schema.sql)

## Cambios de esquema respecto al esquema vigente (Principio VI)

El esquema vigente es el que entregan las migraciones `0001` a `0005` (`001-subscriptions-api`,
`004-correct-subscriptions-api`, `005-health-monitoring` y `006-add-subscription-type`). Esta
feature lo modifica con **una** migración nueva:

| Migración | Contenido |
|---|---|
| `0006_add_clinics_limit` | Agrega `subscriptions.clinics_limit int4 NOT NULL DEFAULT 1`, más un `CHECK` de dos columnas que lo acota según `subscription_type_id` (research R6) |

## Entidades

### Suscripción (`subscriptions`) — columna nueva

| Columna | Tipo | Reglas | Spec |
|---|---|---|---|
| `clinics_limit` | `int4` | `NOT NULL DEFAULT 1`; `CHECK ((subscription_type_id = 1 AND clinics_limit = 1) OR (subscription_type_id <> 1 AND clinics_limit BETWEEN 1 AND 100))` (research R6) | **007** |

El resto de las columnas: sin cambios, ver
[specs/006-add-subscription-type/data-model.md](../006-add-subscription-type/data-model.md).

**Por qué `DEFAULT 1` resuelve FR-007 sin backfill aparte** (research R5): PostgreSQL asigna `1` a
cada fila existente en la misma sentencia `ALTER TABLE … ADD COLUMN`; `1` es válido tanto para una
suscripción Individual (es el único valor permitido) como para una no Individual (es el valor más
bajo de 1 a 100). A diferencia de `006`, esta migración no necesita ningún script fuera de Alembic.

**Nombre de la restricción nueva** (automático de PostgreSQL vía `NAMING_CONVENTION`,
`src/models/base.py`): `subscriptions_clinics_limit_check` (una `CheckConstraint` con nombre
explícito, mismo estilo que `consulting_rooms_limit_check`).

**Reversibilidad**: `downgrade` de `0006` quita el `CHECK` y luego la columna (orden inverso al de
`upgrade`); se pierde el dato, igual criterio que cualquier `drop_column` de este proyecto.

## DTOs (Principio II)

| DTO | Campo | Notas |
|---|---|---|
| `SubscriptionRead` | `clinics_limit: int` (`ge=1, le=100`) | Quinto límite, junto a los otros cuatro; siempre presente |
| `SubscriptionCreate` | `clinics_limit: int` (`ge=1, le=100`) | Obligatorio, como los otros cuatro límites; además sujeto al `field_validator` de abajo |
| `SubscriptionUpdate` | `clinics_limit: int \| None` (`ge=1, le=100`, `default=None`) | A diferencia de `subscription_type_id`, **sí** se agrega a este DTO: es modificable para las suscripciones no Individual (research R3) |

### Validación de `clinics_limit`

| Campo | Capa | Regla | Mensaje si falla |
|---|---|---|---|
| `clinics_limit` (crear) | DTO (`Field`, sin E/S) | Entero obligatorio, de 1 a 100 | «El límite de clínicas debe ser un número entero de 1 a 100.» (falta, `null`, no es entero, o fuera de 1–100) |
| `clinics_limit` + `subscription_type_id` (crear) | DTO (`field_validator` sobre `clinics_limit`, lee `subscription_type_id` de `info.data`; sin E/S, research R2) | Si `subscription_type_id == 1` (Individual), `clinics_limit` MUST ser `1` | «Una suscripción Individual debe tener límite de clínicas igual a 1.» |
| `clinics_limit` (actualizar) | DTO (`Field` + validador "no nulo", sin E/S) | Si se envía, entero de 1 a 100; no puede ser `null` (la columna es `NOT NULL`) | Mismo mensaje que al crear |
| `clinics_limit` (actualizar) | Service (lee la suscripción vigente, research R3) | Si se envía y la suscripción vigente es Individual (`subscription_type_id == SubscriptionType.INDIVIDUAL`), se rechaza la solicitud completa, cambie o no el valor | «El límite de clínicas no puede modificarse en una suscripción Individual.» |

Ambos mensajes de `ValueError`/Service se muestran con la misma forma que cualquier otro error de
un campo: `{"code": "validation_error", "message": "Hay datos no válidos en la solicitud.",
"errors": [{"field": "clinics_limit", "message": "…"}]}` (research R4: ningún código de error
nuevo). Contrato exacto: [contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml).

## Reglas derivadas

- **Por qué el Service necesita leer antes de escribir aquí, a diferencia del resto de
  `update()`** (research R3): la inmutabilidad depende del tipo *actual* de la suscripción, un dato
  que la solicitud de actualización no lleva. Esa lectura se comparte con la que ya dispara
  `module_keys` cuando ambos campos llegan en la misma solicitud (una sola consulta, no dos).
- **Sin carrera posible** (research R3, R6): `subscription_type_id` es fijo para siempre desde que
  se creó la suscripción (006, FR-004), así que el tipo leído antes de escribir es el mismo que
  tendrá la fila después, sin ninguna ventana donde pueda cambiar entre medias.
- **El `CHECK` es puramente defensivo** (research R6): Pydantic (crear) y el Service (actualizar)
  ya garantizan, por construcción, que ninguna fila puede violarlo; no se traduce ninguna
  excepción de integridad nueva para él, igual que los `CHECK` de los otros cuatro límites.
- **Nada nuevo para `subscription_type_id` ni para el catálogo de tipos** (006, sin cambios): esta
  feature solo *lee* `subscription_type_id` para decidir la regla; no agrega, quita ni modifica
  ninguna fila de `subscription_types`.

## Datos ajenos (sin relación con esta feature)

`clinics_count` (el número real de clínicas que ya usan una suscripción, aportado por el API de
clínicas en cada lectura, Principio IX) no cambia y no tiene relación de validación con
`clinics_limit`: uno es un dato externo de solo lectura: el otro, un techo que esta API guarda y
nunca compara contra el uso real (FR-010; ver spec.md, Assumptions).
