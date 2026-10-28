# Investigación: guardar los módulos de la suscripción en su propia tabla

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

## R1. Forma de la relación nueva

**Decisión**: una tabla `subscription_modules` con `subscription_id int4 NOT NULL REFERENCES
subscriptions (id)` y `module_key text NOT NULL`, y `PRIMARY KEY (subscription_id, module_key)`
(clave primaria compuesta, sin columna `id` propia). Ningún catálogo de módulos nuevo en este
servicio.

**Rationale**: la clave primaria compuesta da, sin ninguna columna extra, las dos garantías que
pide la especificación: FR-001 (una fila por módulo, en vez de un valor compuesto en una columna) y
FR-002 (ni dos filas iguales para la misma suscripción —la propia clave primaria lo impide— ni una
fila sin su suscripción —la `FOREIGN KEY` lo impide—). No hace falta un `id` autoincremental:
ningún otro dato de este proyecto necesita referenciar una fila de módulo por sí sola.

**Alternatives considered**:
- `id serial4 PRIMARY KEY` + `UNIQUE (subscription_id, module_key)`: mismo resultado con una
  columna más que nadie usa; rechazada por agregar una estructura sin ningún consumidor.
- Una tabla `modules` propia de este servicio (con los nombres y descripciones de cada módulo) y
  una `FOREIGN KEY` real desde `subscription_modules`: contradice el pedido explícito ("la lista de
  módulos no es responsabilidad de este microservicio") y el Principio IX (el catálogo es de
  `users-api`); rechazada.

## R2. Qué pasa con la regla "patients siempre incluido" a nivel de base de datos

**Decisión**: no se repite como una restricción de base de datos en la tabla nueva. Sigue siendo,
igual que ya ocurre hoy con la validación contra `users-api` y con las reglas de prerrequisito
entre módulos (ninguna de las dos es hoy un `CHECK`), una garantía exclusiva de
`SubscriptionService._resolve_modules` (sin cambios de código en esta especificación).

**Rationale**: un `CHECK` de PostgreSQL no ve otras filas de la misma tabla (no admite
subconsultas): "esta suscripción tiene al menos una fila con `module_key = 'patients'`" es una
regla entre filas, no una regla que una sola fila pueda cumplir por sí misma, así que no puede
expresarse como `CHECK` sobre `subscription_modules`. La única forma declarativa de PostgreSQL
para esa regla sería un disparador que cuente filas tras cada escritura — una pieza sin precedente
en este proyecto (el único disparador que existe, `subscriptions_set_updated_at`, no depende de
otras filas) para una garantía que el Service ya cumple sin excepción desde `004`, con el mismo
nivel de confianza que ya tiene hoy la validación contra `users-api`, que tampoco es un `CHECK`.

**Alternatives considered**:
- Disparador `AFTER INSERT OR DELETE` sobre `subscription_modules` que rechace dejar a una
  suscripción sin la fila `patients`: técnicamente posible, pero agrega una pieza nueva y una
  fuente más de errores de integridad que traducir, para una regla que el único punto de escritura
  (el Service) ya garantiza siempre; rechazada por complejidad desproporcionada.

## R3. Cómo se sigue leyendo `module_keys` sin tocar los DTOs

**Decisión**: `src/models/subscription.py` reemplaza la columna `module_keys` por una relación
`modules: Mapped[list["SubscriptionModule"]]` (`lazy="raise"`, igual criterio que `status` y
`subscription_type`; `order_by="SubscriptionModule.module_key"`) y agrega una propiedad de Python
de solo lectura, `module_keys`, que devuelve `[m.module_key for m in self.modules]`.

**Rationale**: `SubscriptionRead.model_validate(subscription)` (Principio II, `from_attributes=True`,
`src/routers/subscriptions.py::_to_read`) sigue leyendo el atributo `module_keys` exactamente
igual que hoy: **cero cambios** en `src/dtos/subscription.py` y en `src/routers/subscriptions.py`.
El cambio de almacenamiento queda aislado en la capa de persistencia (Principio I), que es
justamente el motivo de ser de esa capa.

**Alternatives considered**: construir `module_keys` a mano en cada punto del Router que arma un
`SubscriptionRead` (`list`, `get`, `create`, `update`, `change_status`): reparte la misma lógica en
cinco lugares en vez de una sola propiedad del modelo; rechazada por duplicación.

## R4. Orden alfabético de la lista expuesta

**Decisión**: el orden alfabético (ya exigido por el contrato, FR-004) lo da el propio `order_by`
de la relación (R3); la propiedad `module_keys` no ordena nada en Python.

**Rationale**: un solo lugar fija el orden, en vez de repetirlo en la propiedad o en cada llamada.

## R5. Migración de los datos existentes (FR-003), sin script fuera de Alembic

**Decisión**: una sola migración de Alembic (`0007`) hace, en este orden: (1) crear
`subscription_modules`; (2) `INSERT INTO subscription_modules (subscription_id, module_key)
SELECT id, unnest(module_keys) FROM subscriptions` — una sola sentencia SQL dentro de la propia
migración; (3) quitar la restricción `module_keys_check` y la columna `module_keys` de
`subscriptions`.

**Rationale**: a diferencia de `006-add-subscription-type` (que necesitó
`src/scripts/backfill_subscription_types.py`, un script fuera de Alembic, porque dependía de una
llamada a la API de clínicas), aquí el dato de origen ya vive en esta misma base de datos:
`unnest()` lo convierte en filas con una sola sentencia SQL, sin ningún paso manual ni ninguna
llamada externa. Esto resuelve FR-003 y SC-002 (ninguna suscripción pierde ni gana módulos al
desplegar esta corrección).

**Alternatives considered**: migrar los datos con un script Python aparte, como `006`: innecesario
aquí porque no hay ninguna API externa involucrada en este backfill; rechazada por complejidad
innecesaria.

## R6. Reversibilidad (`downgrade`, Principio VI)

**Decisión**: `downgrade()` hace lo inverso en orden inverso: (1) agrega de nuevo la columna
`module_keys` (`ARRAY(Text) NOT NULL DEFAULT ARRAY['patients']::text[]`); (2) la rellena con
`UPDATE subscriptions SET module_keys = (SELECT COALESCE(array_agg(module_key ORDER BY
module_key), ARRAY['patients']::text[]) FROM subscription_modules WHERE subscription_id =
subscriptions.id)`; (3) vuelve a crear la restricción `module_keys_check`; (4) elimina
`subscription_modules`.

**Rationale**: simétrico a `upgrade()`; ninguna suscripción pierde sus módulos al revertir, igual
criterio que exige el Principio VI para toda migración de este proyecto. El `COALESCE` cubre, solo
por defensa, una suscripción sin ninguna fila de módulo (no debería ocurrir nunca, R2), dejándola
con `patients` en vez de un arreglo vacío que violaría el `CHECK` que se recrea en el mismo paso.

## R7. Atomicidad en el Repository: una operación pública, dos tablas, un solo commit

**Decisión**: `src/repositories/transactions.py` gana una variante de `execute_and_commit` que
ejecuta más de una sentencia de escritura antes de un único `commit` (traduciendo
`IntegrityError` igual que la actual). `SubscriptionRepository.create()` la usa para el `INSERT`
de la suscripción seguido del `INSERT` por lotes en `subscription_modules`; `update()` la usa para
el `UPDATE` de `subscriptions` (ver R8) seguido, solo si `module_keys` llegó en `changes`, de un
`DELETE` + `INSERT` sobre `subscription_modules` que reemplaza el conjunto completo. Ambos
métodos siguen siendo, de cara a quien los llama, una sola operación con un solo commit — la misma
regla que ya exige `transactions.py` ("cada escritura es su propia transacción").

**Rationale**: el mecanismo actual (`execute_and_commit`) asume una sola sentencia por escritura.
Con dos tablas involucradas en la misma operación de negocio, hace falta que ambas sentencias
corran en la misma transacción para cumplir FR-009 (todo o nada: si falla a mitad de camino, no
queda ni el conjunto de módulos viejo mezclado con cambios nuevos en `subscriptions`, ni al revés).

**Alternatives considered**: dos transacciones separadas, una por tabla — rompe FR-009 ante un
fallo entre ambas; rechazada.

## R8. `update()` conserva su firma pública (`changes: Mapping[str, Any]`)

**Decisión**: `SubscriptionRepository.update()` saca `module_keys` de `changes` (si está) antes de
construir el `UPDATE` de `subscriptions` con el resto; ese `UPDATE` **siempre** se ejecuta —incluso
si, tras sacar `module_keys`, no queda ningún otro cambio— para conservar, atómicamente, la
comprobación de existencia/estatus ya existente (la condición `WHERE id = … AND status_id <>
Eliminada`) y el disparador `subscriptions_set_updated_at` (cambiar los módulos de una suscripción
cuenta como modificarla).

**Rationale**: mantiene sin cambios la firma pública de `update()` y, con ella,
`SubscriptionService.update()` (que construye `changes` con `data.model_dump(exclude_unset=True)`
y ya decide por su cuenta, antes de llamar al Repository, cuándo `module_keys` necesita resolverse
contra `users-api`, R3 de `004`): ningún ajuste de Service por este cambio de almacenamiento.

**Alternatives considered**: omitir el `UPDATE` de `subscriptions` cuando `module_keys` es el único
campo en `changes`: dejaría sin comprobar atómicamente la existencia/estatus de la suscripción
antes de tocar `subscription_modules`, y sin mover `updated_at`; rechazada.

## R9. Un índice sobre `module_key` por sí solo, aparte de la clave primaria

**Decisión**: no se agrega ningún índice sobre `module_key` por sí solo en esta especificación.

**Rationale**: la clave primaria compuesta (R1) ya resuelve de sobra las únicas consultas que esta
especificación necesita (`create`, `update` y la lectura de cada suscripción con sus módulos, todas
por `subscription_id`, la columna líder de esa clave). Ninguna operación de esta especificación
consulta "qué suscripciones usan el módulo X" (esa posibilidad se menciona en la spec como la razón
de fondo del cambio, no como un requisito a implementar ahora). Agregar ese índice hoy sería
construir para un caso de uso que ninguna especificación pide todavía.

**Alternatives considered**: `CREATE INDEX ... ON subscription_modules (module_key)` por
adelantado: rechazado por ser trabajo no pedido (si una especificación futura necesita esa
consulta, se agrega entonces, cuando se conozca su patrón real de acceso).
