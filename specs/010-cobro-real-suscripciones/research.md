# Research: Cobro Real de Suscripciones de Clínicas

Las preguntas de alcance y de arquitectura quedaron resueltas en `spec.md` (sección Clarifications,
incluida la sesión de rediseño 2026-11-11). Esto cubre las decisiones técnicas que la especificación
deja al plan.

## R1: Cómo ampliar la integración con `mailySoft-usuarios` sin romper lo existente

**Decision**: `UsersApiClient` gana un método nuevo, `get_current_access(token)`, que llama a
`GET /api/v1/authorization/me` y devuelve un `CallerAccess` (`tenant_id: str | None`,
`permissions: frozenset[str]`, `password_change_required: bool`). `check_permission(token,
permission)` (ya existente, llama a `/authorization/check`) no cambia y sigue siendo lo que usan
listar/consultar el historial. `AuthorizationService` gana `require_as_caller(token, permission)`.

**Rationale**: Una sola llamada a Usuarios por petición (Principio VIII), la única que informa
`tenant_id`. `/authorization/me` ya es un contrato publicado de `mailySoft-usuarios` (spec 009,
ampliado por la 019) que `mailySoft-agenda` y `mailySoft-pagos` ya consumen con esta misma forma.

**Alternatives considered**: Sin cambios respecto a la versión anterior de este research.

## R2: Monto en centavos sin perder exactitud

**Decision**: `amount = int(price * 100)` donde `price` es el `Decimal` vigente del plan
(`monthly_price` o `annual_price`, `NUMERIC(10, 2)`), validado con `to_integral_exact` para que un
precio con más de dos decimales (no debería ocurrir) levante un error en vez de truncar en silencio.

**Rationale**: Evita cualquier operación de punto flotante (Principio VI).

## R3: `Idempotency-Key` determinista por periodo

**Decision**: `f"clinic-subscription:{clinic_subscription_id}:{period.isoformat()}"`, donde
`clinic_subscription_id` es el identificador **opaco de Clínicas** (research R6 nuevo) y `period` es
la fecha que envía quien dispara el cobro (FR-001). Dos disparos con el mismo
`clinic_subscription_id` y el mismo `period` producen siempre la misma clave.

**Rationale**: Cumple el contrato de Pagos (`Idempotency-Key`, 1 a 100 caracteres) sin que
`maily-system-api` tenga que calcular ni recordar cuál es «el periodo vigente» — ese cálculo, tras el
rediseño, no es responsabilidad de este servicio (lo decide quien dispara el cobro, típicamente
guiado por lo que muestre Clínicas).

**Alternatives considered**: Calcular el periodo localmente a partir de un `next_billing_at` propio
— descartado por el rediseño: ese dato vive en Clínicas, no aquí.

## R4: Referencia opaca hacia Pagos

**Decision**: `resource_type = "system-api:clinic-subscription"` (constante, sin cambios);
`resource_id = clinic_subscription_id` (el identificador de Clínicas, como texto; cumple
`minLength: 1, maxLength: 200` del contrato de Pagos). Sigue siendo opaco para Pagos, igual que
antes del rediseño; lo único que cambió es quién es dueño de ese identificador (Clínicas, no una
tabla propia).

## R5: Cliente de Pagos (`PaymentsApiClient`)

**Decision**: Sin cambios respecto a la versión anterior de este research: mismo patrón que
`ClinicsApiClient`/`UsersApiClient`, con `create_payment` y `get_payment`, y las mismas cuatro
excepciones (`PaymentsApiRejectedToken`, `PaymentsApiPermissionDenied`,
`PaymentsApiIdempotencyConflict`, `PaymentsApiUnavailable`).

## R6: Ampliación del cliente de Clínicas (`get_clinic_subscription`) — NUEVO tras el rediseño

**Decision**: `ClinicsApiClient` (ya existente desde la spec 001, hoy solo con `get_counts`) gana
`async get_clinic_subscription(token, clinic_subscription_id) -> ClinicSubscriptionInfo` (dataclass:
`tenant_id: str`, `subscription_id: int`, `billing_cycle: str`), que llama a una operación nueva,
`GET /api/v1/clinics/clinic-subscriptions/{clinic_subscription_id}`, documentada en
`contracts/clinics-api-integration.md` como ampliación del contrato de la spec 001. Devuelve el
objeto cuando existe y pertenece a la organización de `token`; lanza `ClinicsApiNotFound` cuando no
existe, está cancelada o es de otra organización (los tres casos indistinguibles desde aquí — FR-003
no revela cuál), y `ClinicsApiUnavailable` (ya existente) para cualquier otra falla.

**Rationale**: Es la pieza central del rediseño (plan.md, Constitution Check, Principio IX): la
asignación clínica↔plan↔ciclo pertenece a Clínicas, así que `maily-system-api` la consulta con el
mismo patrón que ya usa para `clinics_count`, en vez de guardarla en una tabla propia. Reutilizar el
cliente existente (en vez de crear uno nuevo) evita duplicar la configuración
(`CLINICS_API_BASE_URL`, tiempo de espera) que ya existe desde la spec 001.

**Alternatives considered**:
- Un cliente HTTP nuevo y separado para esta operación — descartado: es el mismo servicio externo
  (Clínicas) que ya se consulta para `clinics_count`; separar el cliente duplicaría configuración sin
  ganar nada, y el Principio IX ya trata a «Clínicas» como un solo sistema externo.
- Pedir a Clínicas también «qué periodo toca cobrar» — descartado para esta entrega (ver Assumptions
  de la spec): simplifica el contrato nuevo a lo mínimo que esta especificación necesita; calcular el
  periodo pendiente es parte de la automatización diferida (FR-030), que sí tendrá que resolverlo
  (probablemente con una operación de Clínicas distinta, tipo «qué hay que cobrar hoy»).

## R7: Cuándo se puede disparar un cobro (elegibilidad) — ajustado tras el rediseño

**Decision**: Un cobro (`clinic_subscription_id` + `period`) es elegible cuando no existe ya uno
`approved` para ese mismo par en el historial local. Un cobro existente `pending`, `rejected` o
`cancelled` del mismo par SÍ permite un nuevo intento (mismo periodo, misma `Idempotency-Key`).

**Rationale**: Ya no hay un estatus local de «la suscripción de clínica» que bloquee el cobro (esa
entidad no vive aquí tras el rediseño): la única fuente de verdad sobre «ya se cobró este periodo» es
el propio historial de `maily-system-api`. Es la misma lógica que la versión anterior de este
research (R7 original), sin la noción de «suscripción Cancelada» (ahora es Clínicas quien decide si
la suscripción sigue vigente, y lo hace fallar con `ClinicsApiNotFound` antes de llegar a esta
comprobación — FR-003).

## R8: Sincronización del estatus al consultar (sin tarea en segundo plano)

**Decision**: Al leer un cobro `pending`, el `Service` llama primero a `PaymentsApiClient.
get_payment`; si Pagos responde, traduce el nuevo estatus y lo persiste antes de construir la
respuesta; si Pagos no responde (`PaymentsApiUnavailable`), se registra una advertencia y se
devuelve el estatus local tal cual (FR-014). Un cobro que ya no está `pending` nunca dispara esta
llamada.

**Rationale**: Igual que la versión anterior de este research; **ya no incluye** «avanzar
`next_billing_at`» (esa fecha no es de este servicio tras el rediseño — ver Assumptions de la spec:
no se avisa a Clínicas del resultado).

**Credenciales de la sincronización**: igual que antes del rediseño, usa una credencial de
aplicación propia (`PAGOS_API_SERVICE_TOKEN`, variable de entorno opcional), porque el token de quien
disparó el cobro no se guarda (Principio VIII: este servicio nunca guarda tokens) y `GET
/api/v1/payments/{id}` de Pagos exige igualmente un token con `payments:read`. Sin esa variable, la
sincronización se omite (se devuelve el último estatus local) y se registra una advertencia al
arrancar.

## R9: Simulación de Clínicas y de Pagos en las pruebas

**Decision**: `tests/stubs/clinics_api/app.py` (ya existente desde la spec 001) gana `GET
/api/v1/clinics/clinic-subscriptions/{id}` y una superficie de pruebas
(`POST /__test__/clinic-subscriptions` para registrar una a mano, con su `tenant_id`,
`subscription_id` y `billing_cycle`); su `GET /api/v1/clinics/subscription-counts` existente no
cambia. `tests/stubs/payments_api/app.py` (nuevo) sigue el mismo diseño que la versión anterior de
este research (pagos genéricos en memoria, `/__test__/tokens`, `/__test__/payments/{id}/status`,
`/__test__/faults`). `tests/stubs/users_api/app.py` gana `GET /api/v1/authorization/me` (sin tocar
`/check`).

**Rationale**: Mismo patrón que ya usan las specs 001 y 005 para no depender de los servicios reales
(Principio V); ampliar el stub de clínicas ya existente (en vez de crear uno nuevo) refleja que, en
el mundo real, Clínicas sería un solo servicio con las dos operaciones.
