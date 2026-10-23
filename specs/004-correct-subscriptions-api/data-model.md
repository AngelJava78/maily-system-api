# Modelo de datos: Corrección del modelo de datos de la API de Suscripciones

**Feature**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md) · **Esquema**:
[contracts/database-schema.sql](contracts/database-schema.sql)

## Cambios de esquema respecto al esquema vigente (Principio VI)

El esquema vigente es el que entregan las migraciones `0001` y `0002` de `001-subscriptions-api`
(tablas `subscription_statuses` y `subscriptions`). Esta feature lo modifica con **una** migración
nueva:

| Migración | Contenido |
|---|---|
| `0003_subscription_pricing_modules_limits` | Sobre `subscriptions`: renombra `features` → `other_features` (y su `CHECK`); añade `annual_price`, `trial_days`, `self_service`, `module_keys` y los cuatro límites de la clínica |

No se crea ninguna tabla nueva: el catálogo de módulos **no vive en este esquema** (research R1–R4;
Principio IX). `subscription_statuses` no cambia.

`project-definition/DATA_SCHEMA.md` (esquema objetivo) se actualiza en esta feature: las líneas que
cambian llevan el comentario `-- [spec 004-correct-subscriptions-api]`; las que no cambian conservan su
marca `-- [spec 001-subscriptions-api]`.

## Entidades

### Estatus de suscripción (`subscription_statuses`)

Sin cambios respecto a `001-subscriptions-api`.

### Suscripción (`subscriptions`)

| Columna | Tipo | Reglas | Spec |
|---|---|---|---|
| `id` | `serial4` | Clave primaria | 001 |
| `name` | `varchar(100)` | `NOT NULL`, `CHECK (btrim(name) <> '')`; único (sin distinguir mayúsculas) entre las no eliminadas | 001 |
| `description` | `varchar(500)` | Opcional (`NULL` = sin descripción) | 001 |
| `monthly_price` | `numeric(10,2)` | `NOT NULL`, `CHECK (monthly_price >= 0)`; pesos mexicanos, sin IVA | 001 |
| `annual_price` | `numeric(10,2)` | `NOT NULL`, `CHECK (annual_price >= 0)`; pesos mexicanos, sin IVA; **independiente** de `monthly_price` (sin proporción obligatoria, Clarifications P1) | **004** |
| `trial_days` | `int4` | `NOT NULL DEFAULT 0`, `CHECK (trial_days BETWEEN 0 AND 3650)`; `0` = sin periodo de prueba | **004** |
| `self_service` | `bool` | `NOT NULL DEFAULT false`; si está en autoconsumo en el portal de MailySoft (Clarifications P5: nace en falso) | **004** |
| `module_keys` | `text[]` | `NOT NULL DEFAULT ARRAY['patients']`, `CHECK ('patients' = ANY(module_keys))`; claves de módulos de tipo Clínica de la API de usuarios (Clarifications P2–P4) que incluye el plan, **siempre con `patients`** | **004** |
| `other_features` | `text[]` | `NOT NULL DEFAULT '{}'`, `CHECK (cardinality(other_features) <= 20)`; lista **ordenada** de textos libres que no son módulos (antes se llamaba `features`) | 001, renombrada en **004** |
| `consulting_rooms_limit` | `int4` | `NOT NULL`, `CHECK (BETWEEN 0 AND 1000000)`; techo de consultorios de la clínica | **004** |
| `doctors_limit` | `int4` | `NOT NULL`, `CHECK (BETWEEN 0 AND 1000000)`; techo de doctores | **004** |
| `assistants_limit` | `int4` | `NOT NULL`, `CHECK (BETWEEN 0 AND 1000000)`; techo de asistentes | **004** |
| `new_patients_per_year_limit` | `int4` | `NOT NULL`, `CHECK (BETWEEN 0 AND 1000000)`; techo de pacientes nuevos que puede registrar la clínica cada año | **004** |
| `status_id` | `int4` | `NOT NULL DEFAULT 1`, clave foránea a `subscription_statuses(id)` | 001 |
| `created_at` | `timestamptz` | `NOT NULL DEFAULT CURRENT_TIMESTAMP` | 001 |
| `updated_at` | `timestamptz` | `NOT NULL DEFAULT CURRENT_TIMESTAMP`; lo actualiza el disparador `subscriptions_set_updated_at` (sin cambios) | 001 |

**Índice único parcial** `subscriptions_name_not_deleted_key`: sin cambios.

**Los cuatro límites son techos informativos, no contadores de uso** (FR-022, FR-023): esta base de
datos no guarda cuántos consultorios, doctores, asistentes o pacientes nuevos tiene de alta cada
clínica; eso lo guarda el sistema que administra las clínicas. Bajar un límite nunca falla.

**`module_keys` no guarda nombre ni descripción del módulo** (Clarifications P4): solo la clave que
la API de usuarios reconoce. Quien consulta esta API resuelve el nombre para mostrar directamente en
la API de usuarios.

**Nombres de restricciones** (además de las once de `001-subscriptions-api` que no cambian):
`subscriptions_annual_price_check`, `subscriptions_trial_days_check`,
`subscriptions_module_keys_check`, `subscriptions_other_features_check` (reemplaza a
`subscriptions_features_check`), `subscriptions_consulting_rooms_limit_check`,
`subscriptions_doctors_limit_check`, `subscriptions_assistants_limit_check`,
`subscriptions_new_patients_per_year_limit_check`. Todas automáticas de PostgreSQL vía
`NAMING_CONVENTION` (`src/models/base.py`), sin cambios en esa convención.

## Ciclo de vida del estatus

Sin cambios respecto a `001-subscriptions-api`: los cuatro estatus, las mismas transiciones, la misma
condición de baja (sin clínicas asignadas, comprobable).

## Reglas derivadas (nuevas de esta feature)

- **`module_keys` siempre contiene `patients`** (FR-017): el Service construye el conjunto completo
  (`sorted({*enviados, "patients"})`) antes de cualquier escritura; el `CHECK` es una segunda defensa,
  no la única.
- **Dependencias entre módulos** (FR-018): `reminders` exige `scheduling`; `clinical_record_templates`
  exige `clinical_records`; `prescriptions` exige `clinical_records`; `billing` exige `finance`. Se
  valida en `src/clinic_modules.py` (sin red) contra el conjunto completo que va a guardarse, en cada
  creación y en cada actualización que toque `module_keys`.
- **Toda clave de `module_keys` que no sea `patients` debe existir, estar Activa y ser de tipo
  Clínica en la API de usuarios** en el momento de la escritura (FR-015, FR-019); no se comprueba de
  nuevo en lecturas posteriores (research R5): si la API de usuarios borra o bloquea después un módulo
  que una suscripción ya tenía, esta API sigue devolviendo esa clave hasta la próxima escritura que
  toque `module_keys`.
- **`annual_price` no guarda relación con `monthly_price`**: ambos se validan por separado, cada uno
  ≥ 0 con hasta 2 decimales; ninguna regla compara uno contra el otro.
- **`trial_days` y los cuatro límites no tienen mínimo mayor que cero**: `0` es válido en los cinco
  (sin periodo de prueba; un límite en `0` significa que ese plan no permite dar de alta ese recurso).
- **Concurrencia**: sin cambios respecto a 001 (índice único para el nombre; una sola sentencia
  condicionada para la baja y el cambio de estatus). La validación de módulos **no** participa en
  ninguna carrera de escritura: es una comprobación previa a la sentencia SQL, no parte de ella.
- **Reversibilidad**: `downgrade` de `0003` revierte las siete columnas y el renombrado, en el orden
  inverso al de `upgrade`; no toca `subscription_statuses` ni los datos ya existentes de las demás
  columnas.

## DTOs (Principio II)

Se listan por su contenido; el contrato exacto está en
[contracts/openapi-subscriptions.yaml](contracts/openapi-subscriptions.yaml).

| DTO | Campos | Notas |
|---|---|---|
| `StatusRead` | `id`, `name` | Sin cambios |
| `SubscriptionRead` | `id`, `name`, `description`, `monthly_price`, `annual_price`, `trial_days`, `self_service`, `module_keys`, `other_features`, `consulting_rooms_limit`, `doctors_limit`, `assistants_limit`, `new_patients_per_year_limit`, `status`, `clinics_count`, `created_at`, `updated_at` | `monthly_price` y `annual_price` son cadenas con 2 decimales; `module_keys` ordenada alfabéticamente; `clinics_count` entero o `null` |
| `SubscriptionCreate` | `name`, `description?`, `monthly_price`, `annual_price`, `trial_days?` (por defecto `0`), `self_service?` (por defecto `false`), `module_keys?` (por defecto `[]`, se le suma `patients` siempre), `other_features?` (por defecto `[]`), `consulting_rooms_limit`, `doctors_limit`, `assistants_limit`, `new_patients_per_year_limit` | `extra="forbid"`; `annual_price` y los cuatro límites son obligatorios (sin ellos, `422`) |
| `SubscriptionUpdate` | Los mismos campos que `Create`, todos opcionales | `extra="forbid"`; al menos un campo; `name`, `monthly_price`, `annual_price`, `trial_days`, `self_service` y los cuatro límites **no admiten `null`**; `module_keys: []` dentro de `other_features: []` vacían la lista (`patients` se conserva igual) |
| `SubscriptionStatusChange` | `status_id` | Sin cambios |
| `ErrorResponse` / `FieldError` | `code`, `message`, `errors?` | El `enum` de `code` crece con los 3 códigos nuevos |

Los DTOs de entrada siguen sin admitir `id`, `status`, `clinics_count`, `created_at` ni `updated_at`
(FR-026, FR-030).

### Validación de cada campo nuevo (DTO)

| Campo | Regla | Mensaje si falla |
|---|---|---|
| `annual_price` | Igual que `monthly_price`: `Decimal`, `ge=0`, `max_digits=10`, `decimal_places=2` | «El precio anual es obligatorio.» / «El precio anual debe ser un importe de 0 a 99 999 999,99 con hasta dos decimales.» |
| `trial_days` | Entero, `ge=0`, `le=3650` | «Los días de prueba deben ser un número entero de 0 a 3650.» |
| `self_service` | Booleano estricto (no acepta `1`/`"true"`) | «El autoconsumo debe ser verdadero o falso.» |
| `module_keys` | Lista de hasta 50 elementos, cada uno `^[a-z][a-z0-9_]*$`, máx. 50 caracteres (mismo patrón que la API de usuarios exige a `key`) | «Cada módulo debe identificarse con una clave válida.» |
| `other_features` | Igual que la antigua `features`: hasta 20 elementos de 1 a 150 caracteres | (mismo mensaje que 001, con el nuevo nombre de campo) |
| `consulting_rooms_limit`, `doctors_limit`, `assistants_limit`, `new_patients_per_year_limit` | Entero, `ge=0`, `le=1000000` | «El límite de {consultorios\|doctores\|asistentes\|pacientes nuevos al año} debe ser un número entero de 0 a 1 000 000.» |

La validación de que cada clave de `module_keys` **exista de verdad** en la API de usuarios y de que
las **dependencias** se cumplan ocurre en el Service, no en el DTO (necesita una llamada async; ver
[contracts/users-api-integration.md](contracts/users-api-integration.md) y research R5–R6): un DTO
válido puede, aun así, producir `subscription_module_not_found` (422) o
`subscription_module_prerequisite_missing` (409).

## Datos ajenos (solo lectura, no se guardan)

| Dato | Dueño | Cómo llega |
|---|---|---|
| Identidad y permisos de la persona | API de usuarios | Consulta por petición con el token (sin cambios) |
| **Catálogo de módulos de tipo Clínica (nombre, descripción, vigencia)** | **API de usuarios** | **Consulta solo al crear/actualizar módulos (`list_clinic_module_keys`); esta API guarda la `key` que validó, no el nombre ni la descripción** |
| Número de clínicas por suscripción | API de clínicas | Consulta en cada lectura (sin cambios) |
