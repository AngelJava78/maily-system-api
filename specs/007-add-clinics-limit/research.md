# Research: Límite de clínicas por suscripción

## R1 — Representación: una columna simple, no una tabla nueva

**Decision**: `clinics_limit` es una columna `int4 NOT NULL` más en `subscriptions`, igual que
`consulting_rooms_limit`, `doctors_limit`, `assistants_limit` y `new_patients_per_year_limit`
(004). No es un catálogo (a diferencia de `subscription_type_id`, 006): no tiene `id`/`name`
propios, es un número que cada suscripción guarda directamente.

**Rationale**: la regla del usuario ("similar al campo `consulting_rooms_limit`") ya fija la forma:
un techo informativo por suscripción. A diferencia del tipo de suscripción, aquí no hay un conjunto
cerrado de valores con nombre que administrar a mano; es un número con un rango que depende de otro
campo de la misma fila.

**Alternatives considered**: ninguna — la propia descripción del usuario ya desambigua esto (ver
también la respuesta registrada en el chat de `/speckit-specify` sobre el nombre del campo).

## R2 — Dónde vive la regla "1 si Individual, 1–100 si no": Pydantic, no la base de datos

**Decision**: el rango base (`1` a `100`, siempre) es un `Field(ge=1, le=100)` en
`SubscriptionCreate.clinics_limit` y en `SubscriptionUpdate.clinics_limit` (como ya hace cada uno
de los otros cuatro límites con su propio rango). La restricción adicional —"si
`subscription_type_id` es Individual (1), debe ser exactamente 1"— es un `model_validator(mode=
"after")` nuevo en `SubscriptionCreate`, que compara los dos campos ya validados individualmente:

```python
@model_validator(mode="after")
def clinics_limit_matches_type(self) -> "SubscriptionCreate":
    if self.subscription_type_id == 1 and self.clinics_limit != 1:
        raise ValueError(SUBSCRIPTION_CLINICS_LIMIT_MUST_BE_ONE_MESSAGE)
    return self
```

El `1` se escribe literal (no se importa `SubscriptionType.INDIVIDUAL` del modelo): mismo criterio
que ya usa `SubscriptionStatusChange.status_id` (`value not in (1, 2, 3)`) — los DTOs de este
proyecto nunca importan constantes de `src/models/` (capas, Principio I/II).

**Rationale**: `model_validator(mode="after")` ya es el mecanismo que usa este mismo archivo para
una regla entre dos o más campos (`SubscriptionUpdate.at_least_one_field`); no hace falta ningún
mecanismo nuevo. Pydantic solo ejecuta los validadores "after" cuando los campos individuales ya
son válidos, así que si falta `clinics_limit` o `subscription_type_id`, o están fuera de su propio
rango, el error de ESE campo se reporta solo, sin un segundo error confuso de esta regla cruzada.

**Alternatives considered**:
- Resolverlo solo con una restricción `CHECK` en la base de datos (sin nada en el DTO): rechazada
  porque una violación de `CHECK` llega como un error interno (500) salvo que se traduzca a mano, y
  porque esta API nunca comprueba datos de negocio contra la base si puede resolverse sin E/S
  (mismo criterio que ya aplica a los otros cuatro límites y a los rangos de precios).
- Un tipo de dato condicional en el esquema (p. ej. dos esquemas de creación distintos según el
  tipo, con `discriminator`): rechazada por sobre-ingeniería frente a un `model_validator` de tres
  líneas; FastAPI/Pydantic expondría un contrato más confuso para un caso tan acotado.

## R3 — Inmutabilidad en Individual al actualizar: una comprobación en el Service, no en el DTO

**Decision**: `SubscriptionUpdate.clinics_limit` **sí** existe (a diferencia de
`subscription_type_id`, que está ausente a propósito de ese DTO): una suscripción no Individual
necesita poder modificarlo. La regla "no se puede cambiar en una Individual" no puede vivir en el
DTO porque el DTO de actualización nunca ve el tipo actual de la suscripción (no es un dato de la
solicitud). Por eso `SubscriptionService.update()` se extiende: si `"clinics_limit"` está entre los
campos enviados, lee primero la suscripción vigente (igual que ya hace cuando la solicitud trae
`module_keys`, reutilizando esa misma lectura si ambos vienen juntos) y, si su
`subscription_type_id` es `SubscriptionType.INDIVIDUAL` (1), rechaza toda la solicitud antes de
tocar el repositorio — igual, en efecto práctico, que ya hace la ausencia del campo para
`subscription_type_id`, pero decidido en tiempo de ejecución porque aquí la inmutabilidad depende
del *valor actual de otro campo*, no de la mera presencia del campo en el esquema.

**Rationale**: `subscription_type_id` es fijo para siempre (006, FR-004), así que el tipo de una
suscripción nunca cambia después de creada: no hay ninguna carrera posible entre leer el tipo y
aplicar el cambio (a diferencia de, por ejemplo, el nombre repetido, donde sí se evita a propósito
una lectura previa). Leer antes de escribir es, aquí, seguro y ya es el patrón que sigue esta misma
función para `module_keys`.

**Alternatives considered**:
- Seguir el patrón exacto de `subscription_type_id` (ausente de `SubscriptionUpdate`) y exponer en
  su lugar una operación separada para cambiar el límite de clínicas de las suscripciones no
  Individual: rechazada — rompería FR-006/FR-023 (los límites se actualizan todos igual, junto con
  el resto de los datos generales) sin ninguna ganancia; el campo sí es modificable para la mayoría
  de las suscripciones, así que no es un caso de inmutabilidad universal.
- Un `CHECK` de base de datos que comparara el valor nuevo contra el tipo (ver R6) como único
  mecanismo, sin chequeo en el Service: rechazada para el caso de reenviar el mismo valor (1) que
  ya tiene una Individual — un `CHECK` sobre la fila resultante no distingue "no cambió nada" de
  "se reafirmó el mismo valor", y la especificación (FR-005, igual criterio que 006 FR-004) exige
  rechazar la solicitud completa en ambos casos, no solo cuando el valor nuevo sería distinto.

## R4 — Código de error: ninguno nuevo; se reutiliza el error de validación genérico

**Decision**: ni la regla de creación (Individual ⇒ exactamente 1) ni la de actualización
(inmutable en Individual) agregan un código a `ErrorCode`. Ambas se presentan como
`validation_error` (422) con `errors: [{field: "clinics_limit", message: "…"}]`, igual forma que
cualquier error de un campo de la solicitud. La de creación ya sale así gratis (es un
`ValueError` de un `model_validator` de Pydantic). La de actualización necesita una excepción nueva
en `src/exceptions.py`, `SubscriptionDataError`, que es la versión para suscripciones de
`MonitoredComponentDataError` (ya existe, spec 005): `code = ErrorCode.VALIDATION_ERROR`,
`status_code = 422`, recibe `errors: list[dict]` armados con `field_error(field, message)`. Ese
`field_error` se sube de `MonitoredComponentDataError` a `AppError` (la clase base) para que ambas
subclases lo compartan sin duplicar el método — es el único cambio de forma a una clase ya
existente que pide esta feature.

**Rationale**: el error de creación no es "¿existe este recurso?" (como
`subscription_type_not_found`, que sí necesita su propio código porque identifica un recurso
ajeno que no se encontró): es una regla de forma de la propia solicitud, igual categoría que "el
nombre es obligatorio" o "el campo «status» no está permitido". El error de actualización es
exactamente la misma categoría, solo que la condición que lo dispara (el tipo actual de la
suscripción) no puede comprobarse sin leer la base de datos primero — `MonitoredComponentDataError`
ya resuelve ese mismo problema para el registro de componentes (spec 005): un rechazo que decide el
Service, con la forma de un error de validación porque, para quien consume la API, lo es.

**Alternatives considered**:
- Un código nuevo `clinics_limit_immutable` (paralelo a `subscription_type_not_found`): rechazada
  por inconsistencia de categoría (ver Rationale) y porque añade un código al catálogo (y a las
  pruebas que cuentan "los N códigos exactos") sin que distinga nada que `errors[].field` no
  distinga ya.
- Repetir en `src/exceptions.py` el método `field_error` dentro de una clase nueva, sin tocar
  `MonitoredComponentDataError`: rechazada por duplicar código que ya existe idéntico; subirlo a
  `AppError` es un cambio mínimo y hace el mecanismo reutilizable para la próxima feature que lo
  necesite.

## R5 — Datos existentes: `DEFAULT 1` alcanza; no hace falta un script de reconciliación

**Decision**: la migración agrega la columna con `DEFAULT 1 NOT NULL`. A diferencia de 006 (que
necesitó un script fuera de Alembic para decidir, por fila, Individual o Empresarial según el
conteo real de clínicas), aquí el valor `1` es válido para **cualquier** suscripción existente sin
consultar nada externo: es el único valor permitido si ya es Individual, y el valor más bajo —
siempre dentro de 1 a 100 — si no lo es (FR-007, Assumptions del spec). Quien administra los planes
puede subir después el límite de las suscripciones no Individual con la operación de actualización
ya existente, cuando lo necesite.

**Rationale**: esto es, en efecto, la misma técnica que ya usa `trial_days DEFAULT 0` o
`self_service DEFAULT false` en 004: un valor por defecto que PostgreSQL asigna a cada fila
existente en la misma sentencia `ALTER TABLE … ADD COLUMN`, sin una fila intermedia sin dato y sin
ningún proceso de despliegue aparte.

**Alternatives considered**:
- Replicar el script de reconciliación de 006 para fijar un límite "a la medida" de cada
  suscripción no Individual (p. ej., según su `clinics_count` actual): rechazada por alcance — la
  especificación (Assumptions) ya decide explícitamente que el valor de respaldo es 1, ajustable
  después a mano; no hay ningún requisito que pida adivinar un número mejor a partir del uso real
  (de hecho, FR-010 prohíbe validar el límite contra el uso real).

## R6 — Restricción `CHECK` en la base de datos: respaldo defensivo, nunca debería dispararse por la API

**Decision**: además de las dos capas de Pydantic (R2) y la comprobación del Service (R3), la
migración agrega una restricción `CHECK` de dos columnas en `subscriptions`:

```sql
CHECK (
  (subscription_type_id = 1 AND clinics_limit = 1) OR
  (subscription_type_id <> 1 AND clinics_limit BETWEEN 1 AND 100)
)
```

**Rationale**: mismo espíritu que los `CHECK` que ya tienen los otros cuatro límites
(`consulting_rooms_limit BETWEEN 0 AND 1000000`, etc.): una garantía de la base de datos que la API
nunca debería necesitar en la práctica, porque Pydantic (creación) y el Service (actualización) ya
impiden que una fila inválida llegue a escribirse. Se confirma por construcción, no por prueba de
extremo a extremo:
- **Crear**: el DTO exige `clinics_limit` entre 1 y 100 siempre, y el `model_validator` de R2 exige
  exactamente 1 cuando el tipo es Individual (1) → el `CHECK` se cumple por los dos casos.
- **Actualizar**: si la solicitud trae `clinics_limit`, el Service (R3) ya rechazó la operación
  cuando el tipo vigente es Individual, así que el repositorio solo recibe ese cambio para una
  suscripción no Individual, con un valor que el DTO ya acotó a 1–100 → el `CHECK` se cumple. Si la
  solicitud no trae `clinics_limit`, la fila conserva un valor que ya era válido.
- No hay ninguna carrera posible entre ambos pasos porque `subscription_type_id` no cambia nunca
  después de creada la suscripción (006, FR-004): el tipo que el Service lee antes de escribir es,
  por construcción, el mismo que tendrá la fila después.

Por eso esta feature **no** necesita traducir una violación de este `CHECK` a un error propio (no
hay ningún código nuevo de "integridad" que mapear): es exactamente la misma situación, y la misma
decisión, que ya aplica a los `CHECK` de los otros cuatro límites.

**Alternatives considered**: omitir el `CHECK` por completo, confiando solo en Pydantic y el
Service: rechazada por inconsistencia con el resto de la tabla (todas las demás reglas de rango de
`subscriptions` tienen su `CHECK` como respaldo) y porque, sin costo adicional real, es la última
defensa si algún día otra vía de escritura (una migración futura, un script administrativo)
olvidara la regla.

## R7 — Versión del contrato publicado

**Decision**: `VERSION` sube de `3.0.0` a `4.0.0`. La ruta sigue siendo `/api/v1`.

**Rationale**: `clinics_limit` se agrega como obligatorio a `SubscriptionCreate` — una solicitud de
creación que ya funcionaba sin él deja de aceptarse — y las lecturas (`SubscriptionRead`) ganan un
campo más: cambio incompatible de forma, igual criterio que ya aplicaron 004 (2.0.0) y 006 (3.0.0)
por la misma razón (un campo obligatorio nuevo).

**Alternatives considered**: ninguna — el propio Principio IV de la constitución fija el criterio
("los cambios incompatibles en un contrato publicado MUST versionarse"), sin alternativa razonable.
