# Investigación (Fase 0): Periodo de prueba y siguiente pago de cada organización

**Spec**: [spec.md](spec.md) | **Plan**: [plan.md](plan.md)

La spec dejó resueltas las reglas de negocio y las cinco decisiones abiertas (por defecto, ver
«Clarifications»). Lo que sigue son las decisiones **técnicas** del plan, con su evidencia: se leyó el
código de este repositorio y, en solo lectura, el de `mailySoft-clinicas`, `mailySoft-pagos` y
`mailySoft-usuarios` (ninguno se modificó). No quedó ningún «NEEDS CLARIFICATION».

---

## R1. Rutas y operaciones (FR-001, FR-006, FR-044)

**Decisión**: dos operaciones bajo un recurso propio, en plural y con la organización como identificador:

| Operación | Ruta | `operationId` | Permiso | Respuestas |
|---|---|---|---|---|
| Consultar el estado | `GET /api/v1/subscription-periods/{organization_id}` | `get_subscription_period` | `subscription_periods:read` | 200, 401, 403, 404, 409, 422, 503 |
| Iniciar el pago | `POST /api/v1/subscription-periods/{organization_id}/payments` | `create_subscription_payment` | `subscription_periods:write` | 200, 201, 401, 403, 404, 409, 422, 503 |

**Razón**: el recurso de esta API es el *periodo de suscripción* (un registro por organización), y el
permiso propuesto se llama `subscription_periods:*`; la ruta sigue el patrón de `subscriptions` (recurso
plural en `/api/v1`, permiso con el mismo nombre). El cobro es un subrecurso `payments` del periodo: `POST`
lo crea (201) o devuelve el pendiente (200). Cuerpo vacío: cualquier cuerpo se ignora (FR-016).

**Alternativas**: `/api/v1/organizations/{id}/subscription-period` (descartada: `organizations` es el recurso
de Clínicas y mezclaría los dos espacios de nombres); una ruta singular sin identificador que saque la
organización de «mis clínicas» (descartada: la spec indica que la organización va en la petición y que
Clínicas la comprueba con un 404, FR-003).

## R2. Capas y módulos (Principio I, `tests/unit/test_layering.py`)

**Decisión**: todo en las carpetas existentes de `src/`; ninguna carpeta nueva.

| Capa | Módulo (nuevo salvo que diga «modifica») | Qué hace |
|---|---|---|
| Routers | `routers/subscription_periods.py` | Las dos operaciones; `protected(...)`, `Cache-Control: no-store`, 201/200 |
| Services | `services/subscription_period_service.py` | Orquesta: Clínicas → catálogo → registro → conciliación → vista / inicio del pago |
| Services | `services/billing_rules.py` | Funciones **puras** de las reglas (R3); sin E/S, sin `fastapi` ni `sqlalchemy` |
| Repositories | `repositories/subscription_period_repository.py` | Todo el SQL del registro y los cobros (R4, R5, R6) |
| Repositories | `repositories/subscription_repository.py` (modifica) | `get_plan_terms`: el plan del catálogo **en cualquier estatus** (FR-034) |
| Integrations | `integrations/payments_api.py` | Cliente de Pagos (R10) |
| Integrations | `integrations/clinics_api.py` (modifica) | `get_organization` (R9) |
| Integrations | `integrations/errors.py` (modifica) | `OrganizationNotFound`, `PaymentsApiUnavailable` |
| Models | `models/subscription_period.py`, `models/subscription_charge.py` | ORM de las dos tablas (R14) |
| DTOs | `dtos/subscription_period.py` | `SubscriptionPeriodRead`, `SubscriptionPaymentRead`, `PlanRead` |
| Raíz | `config.py`, `dependencies.py`, `security.py`, `messages.py`, `exceptions.py`, `main.py` (modifican) | Configuración, composición, permisos, errores |

Las reglas de capas ya vigentes bastan: el Service no importa `sqlalchemy` (por eso el bloqueo y la
unicidad viven en el Repository, R5), el Router no toca Repositories ni integraciones, las integraciones no
importan DTOs ni modelos (por eso `OrganizationRecord` y `PaymentRecord` son `dataclass` propios del módulo
de la integración, como `ClinicRecord` en `dashboard_source.py`).

## R3. Las reglas de fechas son funciones puras (FR-009 a FR-014, FR-029, FR-030)

**Decisión**: `services/billing_rules.py` contiene, sin E/S y con `datetime` aware en UTC:

- `add_months(moment, months)`: conserva hora y día del mes; si el día no existe, el último del mes
  (31 ene → 28 feb; 29 feb + 12 meses → 28 feb). Calendario de la biblioteca estándar (`calendar.monthrange`).
- `payment_due_at(period)`: `paid_until` si hay; si no, `trial_ends_at`; si no hay prueba, `started_at`.
- `period_state(now, amount, trial_ends_at, due)`: `no_charge` si `amount == 0`; `trial` si hay prueba y
  `now < trial_ends_at`; `overdue` si `now >= due`; si no, `current` (FR-013).
- `days_remaining(due, now)`: **división entera con redondeo hacia +∞ sobre microsegundos**:
  `-((now - due) // 86_400 s)` calculado con `timedelta // timedelta` (entero exacto, sin `float`). Verificado
  contra los 16 ejemplos de la spec (48 h → 2, 49 h → 3, vencida 24 h → −1, vencida 137.5 h → −5).
- `covered_period(due, approved_at, billing_period)`: empieza en `due` si `approved_at < due` y en
  `approved_at` si no; termina en `add_months(start, 1 | 12)` (FR-029).
- `to_minor_units(amount)`: `Decimal` de dos decimales → `int` exacto (499.00 → 49900); falla si el valor no
  es exacto (nunca redondea).
- `idempotency_key(...)`: ver R6.

**Razón**: son las reglas que el negocio más va a mirar y las que más se prestan a errores de límite; como
funciones puras se prueban con reloj fijo y tablas (SC-004) sin base de datos ni dobles. **Alternativa**:
métodos del Service (descartada: mezclaría E/S con aritmética y no se podría probar sin dobles).

## R4. El registro se crea una sola vez (FR-007, SC-005)

**Decisión**: `INSERT … ON CONFLICT (organization_id) DO NOTHING` y luego `SELECT`. La clave primaria es la
organización, así que dos primeras consultas simultáneas calculan las mismas fechas (determinísticas: alta,
corte, `trial_days`) y una sola inserta; la otra lee la fila ya creada. El plan usado es el que el catálogo
informa **en ese momento** (FR-009).

**Alternativas**: `SELECT … FOR UPDATE` previo (no hay fila que bloquear antes de crearla); un candado
asesor (`pg_advisory_xact_lock`): añade un mecanismo donde la clave primaria ya basta.

## R5. Un cobro aprobado mueve la fecha exactamente una vez (FR-032, SC-005)

**Decisión**: una transacción con **dos escrituras condicionadas**, en el Repository, sin bloquear nada
mientras se llama a Pagos:

```sql
-- 1) reclamar el cobro: solo uno de los que compiten lo encuentra pendiente
UPDATE subscription_charges
   SET status='applied', period_starts_at=:start, period_ends_at=:end, resolved_at=:now
 WHERE id=:charge AND organization_id=:org AND status='pending'
RETURNING id;                                   -- 0 filas → «ya resuelto»: se deshace, no se hace nada
-- 2) mover la fecha, solo si nadie la movió desde que se calculó el periodo (compare-and-swap)
UPDATE subscription_periods
   SET paid_until=:end
 WHERE organization_id=:org AND paid_until IS NOT DISTINCT FROM :expected
RETURNING organization_id;                      -- 0 filas → «obsoleto»: se deshace todo
COMMIT;
```

El Service calcula `start` y `end` con `billing_rules.covered_period` a partir del periodo que leyó; si el
Repository responde «obsoleto» (otro cobro movió `paid_until` entre medias), el Service **relee y recalcula**
(hasta 3 intentos) y el segundo cobro continúa donde termina el primero (historia 3, escenario 11). La
fecha de aprobación se acota a `min(updated_at de Pagos, reloj)` (FR-031).

**Razón**: la reclamación `WHERE status='pending'` es lo que garantiza «una sola vez» aunque lleguen 20
consultas a la vez, y el compare-and-swap evita calcular un periodo sobre una fecha ya movida, sin
sostener un bloqueo durante la llamada HTTP a Pagos. **Alternativas**: `SELECT … FOR UPDATE` de dos fases
(`begin_apply` / `finish_apply`): obliga a dejar una transacción abierta entre llamadas del Service y a
liberar el bloqueo en todas las rutas de error; un candado asesor por organización: un mecanismo más que
probar. Ambas funcionan, ninguna es más simple.

## R6. Idempotencia determinista con Pagos (FR-022 a FR-025)

**Decisión**: la clave de `Idempotency-Key` es
`sub-<organization_id>-<hash>` con `hash = sha256("<settles_due_at ISO UTC>|<billing_period>|<importe en
unidad mínima>|<intento>|<descripción>")[:24]` (65 caracteres; Pagos admite hasta 100). Es **determinista**:
mismas condiciones, intento y descripción → misma clave → Pagos devuelve el mismo pago (también si se perdió
la respuesta). La **descripción** («Suscripción {plan} — mensual|anual») entra en la clave porque Pagos rechaza
(409) la misma clave con otro cuerpo: si el plan se renombra entre una respuesta perdida y su reintento, la
clave cambia y se crea otro pago (el primero nunca se registró ni se ofreció), en lugar de quedar atascado en
ese rechazo (lo encontró la revisión final).

- **Periodo** = fecha de pago que salda (`settles_due_at`) + duración. **Condiciones** = periodo + importe.
- **Intento**: 1 más el número de intentos con esas condiciones que **ya terminaron** (cobros aplicados o
  cerrados; nunca el pendiente). Con un cobro `pending` con esas condiciones no se crea otro (se devuelve el
  suyo, 200); con todos resueltos, el intento siguiente da una clave nueva y Pagos crea un pago nuevo
  (FR-023). Un importe distinto es otra condición (FR-024).
- **Carrera de dos inicios**: ambos calculan el mismo intento y la misma clave, Pagos devuelve el mismo
  pago a los dos y la restricción única `(organization_id, settles_due_at, billing_period, amount,
  attempt)` deja que solo uno registre el cobro; el otro lee el existente y responde 200.
- **Por qué el pendiente no cuenta** (lo encontró la prueba de carga de la historia 3): si el cobro
  pendiente contara, una solicitud que buscó el pendiente *antes* de que otra lo registrara y contó
  *después* calcularía el intento 2, otra clave y por tanto otro pago en Pagos para el mismo periodo. Sin
  contarlo, esa solicitud calcula el intento 1 y la misma clave que la primera.
- **Red de seguridad en la base**: el índice único parcial `subscription_charges_pending_terms_key`
  `(organization_id, settles_due_at, billing_period, amount) WHERE status = 'pending'` impide que existan
  dos cobros sin resolver para el mismo periodo e importe, sea cual sea el intento. Si Pagos respondiera con
  otro pago para la misma clave (no debería), el pago que no quedó registrado no se ofrece nunca: se
  devuelve el checkout del cobro registrado, porque nada aplicaría la aprobación del otro.

**Razón**: una clave derivada solo de la organización y el periodo no permitiría reintentar tras un
rechazo (Pagos devolvería el pago rechazado); el intento y el importe resuelven los dos casos sin estado
extra. **Alternativa**: clave aleatoria guardada antes de llamar (descartada: si la respuesta se pierde, el
reintento no encontraría la clave y crearía un segundo pago).

## R7. Conciliación antes de responder (FR-026 a FR-031)

**Decisión**: `SubscriptionPeriodService._reconcile(token, period)`:

1. Lee los cobros `pending` de la organización (índice parcial, R14).
2. Pregunta a Pagos por **todos a la vez** (`asyncio.gather(..., return_exceptions=True)`), cada uno con el
   token de la persona y el tiempo máximo total de la integración.
3. Por cada resultado: `PaymentsApiUnavailable` → no verificable; `pending` → sigue; `approved` → se
   aplica si importe, moneda y referencia (`resource_type`, `resource_id` = organización) coinciden con lo
   registrado y, si no, se cierra `inconsistent` con un `WARNING` sin datos personales; `rejected` /
   `cancelled` → se cierra; `partially_refunded` / `refunded` → se cierra `refunded` sin aplicar (D3).
4. Aplica en el orden de creación, **uno por uno** (R5), releyendo el periodo en cada vuelta.

La lista de cobros pendientes se entrega **desligada de la sesión** (`expunge`): cuando otra solicitud llegó
primero, `apply_charge` desiste con un `rollback`, que expira todo lo que la sesión tiene cargado, y leer un
objeto expirado exigiría una E/S que no puede ocurrir fuera del contexto asíncrono (`MissingGreenlet`). Lo
encontró la prueba de concurrencia de la historia 3 (dos cobros aprobados y diez consultas simultáneas). Por
la misma razón el periodo se lee **después** de conciliar, nunca antes.

Devuelve el periodo vigente, los pagos verificados como pendientes (con su `checkout_url`, que el inicio del
pago reutiliza sin una segunda consulta) y si algún cobro no se pudo verificar. `payment_in_progress` es
`true` si hay un pendiente verificado, si no `null` si alguno no se pudo verificar y si no `false` (FR-015). Un cobro aprobado que no se pudo aplicar tras los reintentos (otra petición movía la fecha) cuenta como «no se pudo verificar»: sigue pendiente y la siguiente petición lo intenta de nuevo.

**Razón**: Pagos no avisa de los cambios (pedido (d) de la descripción) y la spec prohíbe tareas
programadas (FR-012); la conciliación al consultar es la única vía. La comprobación de la referencia es
defensa en profundidad: un pago registrado por esta API siempre la lleva. **Alternativa**: consultar uno
por uno (descartada: la latencia crece con el número de pendientes; SC-001 exige hasta cinco).

## R8. Degradación (FR-035 a FR-038, historia 6)

| Falla | Consulta | Inicio del pago |
|---|---|---|
| Usuarios | `AuthorizationUnavailableError` → 503 (existente) | igual |
| Clínicas (sin respuesta, tiempo, 401/403/3xx/5xx, cuerpo inesperado, **sin `billing_period`**) | `OrganizationCheckUnavailableError` → 503 | igual |
| Clínicas 404 con código `not_found` | `OrganizationNotFoundError` → 404 | igual |
| Pagos al **consultar** un cobro | ese cobro queda sin verificar; 200 con `payment_in_progress: null` | — |
| Pagos al **crear** el pago | — | `PaymentsUnavailableError` → 503, sin registrar el cobro |

Un 404 de Clínicas con un código distinto de `not_found` (por ejemplo una ruta que su versión no tiene) se
trata como falla (503): no debe confundirse con «la organización no existe».

## R9. Contrato consumido de Clínicas (FR-003, FR-047; Principio IX)

**Decisión**: `ClinicsApiClient.get_organization(token, organization_id)` hace
`GET {CLINICS_API_BASE_URL}/api/v1/organizations/{id}` con el token reenviado. Acepta **solo** un 200 con
un objeto JSON que traiga: `id` (el mismo UUID pedido), `subscription_id` (entero ≥ 1, no booleano),
`billing_period` (`monthly` o `annual`) y `created_at` (ISO 8601 **con** zona); devuelve un `OrganizationRecord`.
Lo demás es `ClinicsApiUnavailable`, salvo el 404 con `code: "not_found"` → `OrganizationNotFound`. No sigue
redirecciones, tiene el tiempo máximo total de `CLINICS_API_TIMEOUT_SECONDS`, no reintenta y nunca registra el
token, la dirección ni el cuerpo.

**Evidencia** (solo lectura): `mailySoft-clinicas/src/routers/organizations.py` (`GET /organizations/{id}`,
permiso `organizations:read`), `services/organization_queries_service.py` (un rol de clínica solo lee la
organización cuyo Owner es el usuario del token; otra, `NotFound`), `dtos/organization.py`
(`OrganizationRead` trae `subscription_id` y `created_at`, y **no** `billing_period`, que sí guarda
`models/organization.py`). El pedido a Clínicas está en [contracts/pedidos-clinicas.md](contracts/pedidos-clinicas.md).

## R10. Contrato consumido de Pagos (FR-020, FR-026, FR-047)

**Decisión**: `PaymentsApiClient` con dos operaciones, ambas con el token reenviado, tiempo máximo total,
sin redirecciones ni reintentos:

- `create_payment(token, *, idempotency_key, amount, currency, resource_type, resource_id, description,
  metadata)` → `POST /api/v1/payments` con `Idempotency-Key` y cuerpo `{provider: "mercado_pago", amount,
  currency, resource_type, resource_id, description, metadata}`; acepta 201 (y 200) con un `PaymentRead`.
- `get_payment(token, payment_id)` → `GET /api/v1/payments/{id}`.

Un `PaymentRecord` válido trae: `id` (UUID), `status` (uno de `pending`, `approved`, `rejected`,
`cancelled`, `partially_refunded`, `refunded`), `amount` (entero, no booleano), `currency` (3 letras),
`resource_type`, `resource_id`, `updated_at` (ISO 8601 con zona) y `checkout_url` (texto o `null`). Cualquier
otra cosa —incluidos 401, 403, 404, 409, 5xx, redirecciones y estatus desconocidos— es
`PaymentsApiUnavailable`.

**Evidencia** (solo lectura): `mailySoft-pagos/specs/001-payments-foundation/contracts/openapi-pagos.yaml`
(operaciones, `PaymentCreate`, `PaymentRead`, `Idempotency-Key` de 1 a 100 caracteres, `409` ante la misma
clave con otro cuerpo), `src/security.py` y `services/payment_service.py` (aísla por el `tenant_id` del
llamador, que sale de `/authorization/me`), `ESTADO.md` (la integración con un consumidor real está
pendiente), `contracts/mercado-pago-integration.md` (`back_urls` se omite si no se envía
`redirect_urls`; `in_process`/`authorized` → `pending`). Pagos no publica fecha de aprobación: solo
`updated_at`, que `payment_repository.py` actualiza con `func.now()` en cada cambio de estatus.

## R11. Configuración (FR-039 a FR-041)

**Decisión**: dos clases nuevas, **separadas** de `IntegrationSettings`:

- `PaymentsSettings`: `PAYMENTS_API_BASE_URL` (obligatoria; misma validación y normalización que las otras
  dos) y `PAYMENTS_API_TIMEOUT_SECONDS` (opcional, 5 s, mayor que 0 y hasta 30).
- `BillingSettings`: `BILLING_CUTOFF_AT` (obligatoria, ISO 8601 **con** zona, normalizada a UTC; un valor sin
  zona, numérico o vacío no es válido).

Se cargan junto a las demás en `lifespan`, de modo que **un solo mensaje** nombra todas las variables
faltantes o inválidas sin mostrar sus valores. Una advertencia más al arrancar si
`PAYMENTS_API_BASE_URL` usa `http://` fuera de una red local o de Docker (misma regla que las otras dos).

**Razón de separarlas**: `src/scripts/backfill_subscription_types.py` (spec 006) y su servicio de Compose
usan `IntegrationSettings`; una variable obligatoria nueva ahí los rompería sin que necesiten Pagos.
**CORS**: no hay cambio de código; `CORS_ALLOWED_ORIGINS` ya admite `GET`, `POST` y las cabeceras
`Authorization` y `Content-Type` (FR-041); se añaden pruebas de la petición previa y de un origen no listado
sobre las rutas nuevas y se documenta en el README.

## R12. Errores nuevos y precedencia (FR-004, FR-045)

Cinco códigos nuevos (17 → 22), sin tocar los existentes:

| Código | HTTP | Cuándo |
|---|---|---|
| `organization_not_found` | 404 | Clínicas respondió `not_found` (no existe o no es de la persona) |
| `organization_check_unavailable` | 503 | No se pudo comprobar la organización (cualquier otra respuesta de Clínicas) |
| `payments_unavailable` | 503 | Pagos no pudo crear el pago (o devolvió un pago sin checkout) |
| `nothing_to_charge` | 409 | El importe vigente es 0.00 |
| `organization_subscription_not_found` | 409 | El plan que informa Clínicas no existe en el catálogo |

Detalle y mensajes en [contracts/error-catalog.md](contracts/error-catalog.md). El 422 por un
`organization_id` que no es UUID usa el manejador existente con el mensaje nuevo del bloque
`subscription-periods`. **Precedencia verificada**: FastAPI resuelve las dependencias de seguridad antes de
validar los parámetros de ruta, así que 401/403/503 de acceso ganan al 422 (como en suscripciones y dashboard).

## R13. DTOs y serialización (FR-011, FR-015, FR-016, FR-046)

**Decisión**: `SubscriptionPeriodRead` (siete campos propuestos en la spec más `subscription`) y
`SubscriptionPaymentRead`. Fechas `AwareDatetime` normalizadas a UTC y serializadas con `Z` (como
`RecentClinicRead`); `amount` es texto con dos decimales (`format(value.quantize(Decimal("0.01")), "f")`,
como `monthly_price`); `currency` es el literal `MXN`; todos los campos están siempre presentes y los que
pueden faltar valen `null` (`trial_ends_at`, `payment_due_at`, `days_remaining`, `payment_in_progress`). Las
respuestas 200 y 201 llevan `Cache-Control: no-store`.

## R14. Esquema (Principio VI; FR-042, FR-043)

**Decisión**: dos tablas nuevas y ninguna columna nueva en las existentes; migración `0008`
reversible. Detalle completo en [data-model.md](data-model.md) y [contracts/database-schema.sql](contracts/database-schema.sql).

- `subscription_periods` (clave: `organization_id`): `started_at`, `trial_ends_at` (nulo = sin prueba),
  `paid_until` (nulo = sin pagos), `created_at`, `updated_at` (disparador de 0001).
- `subscription_charges`: el cobro con su `payment_id` único, importe `numeric(10,2)`, moneda, duración,
  `settles_due_at`, `attempt`, periodo cubierto (al aplicarse), `status`, `closed_reason`, fechas; unicidad
  `(organization_id, settles_due_at, billing_period, amount, attempt)` y un índice parcial de los
  pendientes por organización.
- Sin clave foránea hacia otro sistema (la organización es del API de clínicas, Principio IX): la
  referencia es solo el UUID. `subscription_charges.organization_id` sí referencia `subscription_periods`.

## R15. Reloj (FR-011)

**Decisión**: se reutiliza `services/clock.py` (`Clock`, `SystemClock`) y la dependencia `get_clock` de la
spec 005. El Service recibe el reloj y las pruebas lo sustituyen con el `FakeClock` de
`tests/health_support.py`; ninguna regla llama a `datetime.now()`. La fecha de corte entra al Service como
valor (no lee la configuración), igual que el límite del dashboard.

## R16. Simulaciones de las pruebas (FR-048)

**Decisión**:

- **Clínicas** (`tests/stubs/clinics_api/app.py`, modifica): `GET /api/v1/organizations/{id}` con el
  contrato de R9; superficie `/__test__/organizations` para dar de alta una organización con su plan, su
  periodo de cobro, su alta y el token de su Dueño (otro token recibe 404 `not_found`, como el API real);
  las fallas existentes (`unavailable`, `unauthorized`, `forbidden`, `malformed`, `not_json`, `redirect`,
  `slow`) aplican también a esta operación, más `missing_billing_period`.
- **Pagos** (`tests/stubs/payments_api/app.py`, **nuevo**): `POST /api/v1/payments` (idempotente por
  `Idempotency-Key`, 409 con otro cuerpo) y `GET /api/v1/payments/{id}`; superficie `/__test__/` para
  cambiar el estatus de un pago, crear un pago «por otra vía», programar fallas y ver las llamadas.
- **Usuarios**: sin cambios (ya acepta cualquier permiso `recurso:acción`).

Las tres simulaciones son autocontenidas (no importan `src/`) y registran la marca `SECRETO-INTERNO` en cada
cuerpo de falla para comprobar que nada interno llega al cliente.

## R17. Pruebas (Principio V)

| Nivel | Qué | Dónde | Necesita PostgreSQL |
|---|---|---|---|
| Unidad | Reglas puras con tablas (los 16 ejemplos), configuración, mensajes, DTOs, clientes HTTP de Clínicas y Pagos contra sus simulaciones, Service con dobles, capas | `tests/unit/` | No |
| Contrato | Las dos operaciones por HTTP con base de datos real, Usuarios/Clínicas/Pagos simulados y `FakeClock`: historias 1 a 6, acceso, degradación, carreras (20 consultas simultáneas), CORS | `tests/contract/` | Sí (`slow`) |
| Integración | Repository (unicidad, reclamación, compare-and-swap, creación única) y migración 0008 (sube, baja, coincide con los modelos) | `tests/integration/` | Sí (`slow`) |
| Punta a punta | Colección de Postman nueva sobre la pila aislada | `tests/postman/` | Docker + Newman |

`/speckit-implement` corre solo el nivel rápido; la suite completa (`uv run pytest -m ""`) y Newman son la
puerta antes de integrar en `main` (Principio V).

## R18. Colección de Postman (FR-052)

**Decisión**: `MailySoft-System-Periodos.postman_collection.json` (estructura y guardianas en
[contracts/e2e-collection.md](contracts/e2e-collection.md)), nueva e independiente, con las guardianas G1 a
G9 de las colecciones anteriores. Reloj real: los escenarios fijan la **antigüedad** de la organización en la
simulación de Clínicas (alta hace 1 día / hace 40 días) y la pila fija `BILLING_CUTOFF_AT` en una fecha
lejana en el pasado, así que no hace falta mover el reloj. Un script de Newman nuevo (`e2e:periods`) y el
`e2e:all` actualizado.

## R19. Ajustes a pruebas existentes (FR-053)

Barrido hecho con `grep` (conteos de códigos de error, versión, `PUBLIC_ROUTES`, operaciones, arranque del
`lifespan`, colecciones). Todos se ajustan solo para **reconocer lo nuevo**; ninguna comprobación de
comportamiento cambia. La tabla de ajustes está en [plan.md](plan.md#ajustes-a-las-pruebas-existentes-fr-053).

## R20. Versión publicada

**Decisión**: `4.0.0` → `4.1.0` (MINOR: dos operaciones y cinco códigos nuevos, sin cambios incompatibles).
`src/__init__.py`, `pyproject.toml`, `uv.lock` (versión del paquete raíz) y las tres pruebas que fijan el
literal se actualizan juntos (`test_version.py` exige que coincidan).

## R21. Pedidos a los otros APIs (FR-049)

**Decisión**: tres documentos en `contracts/`, con la estructura que ya usa el ecosistema
(`mailySoft-clinicas/project-definition/pedidos-usuarios-alta-de-personal.md`): qué pide el negocio, qué se
pide y con qué forma, cómo lo usa esta API, criterios de aceptación para las pruebas del otro equipo,
preguntas y qué bloquea. Cada pedido trae las cuatro partes de SC-013. Son [pedidos-usuarios.md](contracts/pedidos-usuarios.md),
[pedidos-clinicas.md](contracts/pedidos-clinicas.md) y [pedidos-pagos.md](contracts/pedidos-pagos.md); los envía la persona
responsable. **No bloquean** el desarrollo ni las pruebas (usan las simulaciones); sí bloquean la
verificación contra los servicios reales y el despliegue.
