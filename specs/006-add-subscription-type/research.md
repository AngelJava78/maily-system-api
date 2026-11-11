# Research: Tipo de suscripción (Individual o Empresarial)

Revisión tras Clarifications (2026-10-26): el tipo pasa de una columna con `CHECK` fijo a un
catálogo propio, igual que el estatus de la suscripción. Esta versión de `research.md` **reemplaza**
la decisión R1 original (una columna con dos valores cerrados) y ajusta las decisiones que dependían
de ella (R2, R5); R3, R4, R6 y R7 no cambian de fondo.

## R1 — Representación de `subscription_type`: catálogo propio (tabla), no una columna con `CHECK`

**Decision**: una tabla nueva, `subscription_types` (`id serial4 PRIMARY KEY`, `name varchar(50) NOT
NULL UNIQUE`, `description text`), **idéntica en forma** a `subscription_statuses`. `subscriptions`
gana `subscription_type_id int4 NOT NULL DEFAULT 1 REFERENCES subscription_types(id)` (reemplaza a
la columna `subscription_type varchar(20)` de la versión anterior). Se siembra con dos filas,
`(1, 'Individual', …)` y `(2, 'Empresarial', …)`, en la misma migración que crea la tabla y agrega la
columna (no hace falta repartirlo en dos migraciones como `subscription_statuses` hizo en `0001`/
`0002`: aquí es una sola feature, no el esquema fundacional del proyecto).

**Rationale**: Clarifications (2026-10-26) — el responsable del proyecto corrigió explícitamente la
decisión anterior: el tipo debe poder ampliarse en el futuro (hoy son dos, "pero podríamos tener
más") **insertando una fila**, no con una migración que reescriba un `CHECK`. Eso es, exactamente,
cómo ya funciona `subscription_statuses` en este mismo proyecto (Principio VI: "catálogo en base de
datos… administrado a mano"). Replicar esa forma exacta (incluida la relación `id` ↔ `name`, el
`id` estable y el `name` editable) es más consistente que inventar un mecanismo nuevo.

**Alternatives considered**:
- Columna de texto con `CHECK` (la decisión original, R1 anterior): rechazada explícitamente por el
  responsable del proyecto: ampliar el conjunto de valores exige una migración que reescriba la
  restricción, no solo insertar un dato.
- Columna de texto sin ninguna restricción (acepta cualquier valor que se envíe, sin catálogo que lo
  valide): rechazada porque no hay forma de distinguir un tipo real de un error de tecleo, y porque
  el propio spec (FR-002) exige rechazar un valor que "no corresponda a un tipo del catálogo".
- Una tabla de catálogo pero referenciada por `name` (no por `id`) desde `subscriptions`: rechazada
  por el mismo motivo que ya aplica al estatus (Principio VI: "quien consume la API MUST basarse en
  el identificador…, no en su nombre"); el `name` es dato editable, no una clave estable.

## R2 — Nombre del campo y de la tabla: `subscription_type_id` / `subscription_types`

**Decision**: la tabla se llama `subscription_types` (plural, como `subscription_statuses`); la
columna de `subscriptions` que la referencia se llama `subscription_type_id` (como `status_id`
referencia a `subscription_statuses`). El DTO de lectura expone `subscription_type` como objeto
anidado (`{id, name}`, como `status`); el DTO de creación recibe `subscription_type_id` (entero,
como `SubscriptionStatusChange.status_id`).

**Rationale**: mismo patrón que ya usa este proyecto para el estatus en los tres lugares (tabla,
columna FK, DTO de lectura anidado); cero vocabulario nuevo que aprender.

**Alternatives considered**: ver R1 de la versión anterior de este documento (seguía vigente para el
nombre del campo, no para su tipo de dato).

## R3 — Cómo se cumplen FR-008/FR-009/FR-010 (datos existentes): sin cambios de fondo

**Decision**: igual que antes — (a) la migración agrega `subscription_type_id` con `DEFAULT 1`
('Individual'), que PostgreSQL asigna a cada fila existente en la misma sentencia; (b) el script de
reconciliación (`src/scripts/backfill_subscription_types.py`) sigue siendo quien, fuera de Alembic,
pide el conteo de clínicas y marca `enterprise` (ahora: `subscription_type_id = 2`) a quien
corresponda, reintentando sin límite.

**Rationale**: el cambio de R1 (tabla en vez de columna con `CHECK`) no cambia por qué esto vive fuera
de Alembic (la API de clínicas sigue sin credenciales de servicio, Principio I sigue reservando los
clientes de integración a los Services). Ver la versión anterior de este documento para el detalle
completo; no se repite aquí.

**Alternatives considered**: sin cambios respecto a la versión anterior.

## R4 — Token del script de reconciliación

Sin cambios respecto a la versión anterior de este documento.

## R5 — Códigos de error: uno nuevo, no cero (corrige la decisión anterior)

**Decision**: la versión anterior de este documento (columna con `CHECK`) concluía "cero códigos de
error nuevos", porque un valor no reconocido se rechazaba con Pydantic puro (sin E/S). Con un
catálogo en tabla, saber si un `subscription_type_id` existe de verdad **requiere una lectura de base
de datos**, que Pydantic no puede hacer por sí solo. Por eso:

- «Falta o no es un entero positivo» sigue siendo `validation_error` (DTO, sin E/S): nueva entrada
  `("subscription_type_id", "required")` y `("subscription_type_id", "invalid")` en
  `VALIDATION_MESSAGES["subscriptions"]`, el mismo mensaje para ambas (como ya hace `status_id` con
  `_STATUS_REQUIRED_MESSAGE`).
- «Es un entero positivo, pero no existe ningún tipo con ese identificador» sí es un código nuevo:
  `subscription_type_not_found` (422), análogo a `subscription_module_not_found`. Se detecta
  **sin una lectura previa**: el `INSERT` se intenta igual que siempre, y si la clave foránea
  `subscriptions_subscription_type_id_fkey` lo rechaza, `execute_and_commit` ya traduce eso a
  `ForeignKeyViolationError` (`src/repositories/errors.py`, ya existe, hoy sin usar en este flujo) —
  el Service solo necesita atraparlo y traducirlo, igual que ya hace con `UniqueViolationError` para
  el nombre repetido. Sin lectura adicional, sin carrera de por medio.
- «Se intenta modificar en una actualización» sigue sin código nuevo: sigue siendo el mecanismo
  genérico de campo no permitido, ahora bajo el nombre `subscription_type_id`.

**Rationale**: reutiliza `ForeignKeyViolationError`, que ya existe y ya se traduce automáticamente en
`execute_and_commit`, exactamente como `UniqueViolationError` ya se usa para el nombre repetido; no
hace falta una consulta de existencia por separado ni arriesgar una carrera entre comprobar y
escribir.

**Alternatives considered**:
- Verificar la existencia del `subscription_type_id` con una lectura previa en el Service (`SELECT …
  FROM subscription_types WHERE id = …`) antes de intentar el `INSERT`: rechazada por la carrera que
  ya evita el patrón de "no comprobar antes, dejar que la base de datos decida" (research, el mismo
  motivo documentado para el nombre repetido) y por ser una consulta de más cuando la clave foránea
  ya hace la comprobación gratis.
- Devolver `404` en vez de `422`: rechazada por consistencia con `subscription_module_not_found`
  (un dato de la solicitud que no se reconoce es un problema de validación de la solicitud, no de
  "el recurso no existe").

## R6 — Versión del contrato publicado

Sin cambios respecto a la versión anterior: `VERSION` sigue subiendo a `3.0.0` (cambio incompatible
de forma: `subscription_type_id` es un campo obligatorio nuevo, y la forma de `subscription_type` en
las respuestas cambia de cadena a objeto).

## R7 — Alcance del script de reconciliación

Sin cambios respecto a la versión anterior: sigue pidiendo el conteo de todas las suscripciones, sin
filtrar por estatus (ver la versión anterior de este documento para el detalle).

## R8 — Constantes de los dos tipos de hoy: `ClassVar[int]`, como `SubscriptionStatus`

**Decision**: `src/models/subscription_type.py` define `SubscriptionType.INDIVIDUAL: ClassVar[int] =
1` y `.ENTERPRISE: ClassVar[int] = 2`, exactamente como `SubscriptionStatus.ACTIVE` / `.DELETED` etc.
El código que necesita referirse a "Individual" o "Empresarial" por su significado de negocio (el
valor por defecto de la migración, el script de reconciliación, FR-006) usa estas constantes, nunca
el número suelto ni el texto.

**Rationale**: FR-006 (cuántas clínicas admite cada tipo) es una regla de negocio **propia de estos
dos valores**, no del mecanismo de catálogo en sí; un tercer tipo que se agregue a mano en el futuro
no hereda ninguna regla de clínicas solo por existir (la propia spec lo aclara, Assumptions). Esto es
exactamente la misma relación que ya existe entre `subscription_statuses` (catálogo ampliable) y el
código que hoy solo conoce reglas para los cuatro estatus con significado propio (Activa, Inactiva,
Bloqueada, Eliminada): un quinto estatus añadido a mano no dispara ninguna regla nueva porque nadie
la escribió. Un tercer tipo añadido a mano se comportaría igual: se podría guardar y leer, pero
ninguna regla de negocio lo reconocería hasta que una especificación futura la agregue.

**Alternatives considered**: validar dinámicamente contra el catálogo cuáles son "los tipos que
limitan a una clínica" (p. ej. una columna `max_clinics` en `subscription_types`): rechazada por
sobre-ingeniería; el spec (Assumptions) dice explícitamente que esta especificación no define reglas
de clínicas para un tercer tipo hipotético, así que no hay nada que una columna de ese tipo
resolviera hoy.
