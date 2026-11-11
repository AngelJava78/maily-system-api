# Research: Cobro Real de Suscripciones de Clínicas

Todas las preguntas de alcance y de arquitectura quedaron resueltas en `spec.md` (sección
Clarifications). Esto cubre las decisiones técnicas que la especificación deja al plan.

## R1: Cómo ampliar la integración con `mailySoft-usuarios` sin romper lo existente

**Decision**: `UsersApiClient` gana un método nuevo, `get_current_access(token)`, que llama a
`GET /api/v1/authorization/me` y devuelve un `CallerAccess` (`tenant_id: str | None`,
`permissions: frozenset[str]`, `password_change_required: bool`). `check_permission(token,
permission)` (ya existente, llama a `/authorization/check`) no cambia y sigue siendo lo que usan
todas las operaciones salvo «cobrar». `AuthorizationService` gana `require_as_caller(token,
permission)`, que llama a `get_current_access`, resuelve `password_change_required` (403, mismo
código que el resto del ecosistema MailySoft) y comprueba el permiso localmente contra el conjunto
que trae la respuesta (unión de los permisos de los roles Activos), en vez de pedírselo a Usuarios
con `check`. `require(token, permission)` (ya existente) sigue intacto para las demás operaciones.

**Rationale**: Es **una sola llamada a Usuarios por petición** (Principio VIII), y la única que
informa `tenant_id` (lo que la operación de cobro necesita, FR-030). `/authorization/me` ya es un
contrato publicado de `mailySoft-usuarios` (spec 009, ampliado por la 019) que `mailySoft-agenda` y
`mailySoft-pagos` ya consumen con esta misma forma de CallerContext — no es una tecnología nueva, así
que no hace falta enmendar la constitución de este repositorio (Constitution Check del plan).

**Alternatives considered**:
- Dos llamadas (`check` para el permiso + `me` para el `tenant_id`): viola «una sola consulta por
  petición» y duplica latencia sin necesidad, porque `/me` ya trae los permisos.
- Guardar el `tenant_id` de la clínica solo localmente y no comprobar el de quien llama: dejaría que
  cualquier persona autenticada (de cualquier organización) disparara el cobro de cualquier clínica,
  contradiciendo FR-012.

## R2: Monto en centavos sin perder exactitud

**Decision**: `amount = int(price * 100)` donde `price` es el `Decimal` vigente del plan
(`monthly_price` o `annual_price`, `NUMERIC(10, 2)`). Como el precio siempre tiene como máximo dos
decimales, `price * 100` es siempre un entero exacto en `Decimal`; se usa
`int(price.scaleb(2))` o equivalente (`(price * 100).to_integral_exact()`) para que un precio mal
guardado con más de dos decimales (no debería ocurrir, está forzado por la columna) levante un error
en vez de truncar en silencio.

**Rationale**: Evita cualquier operación de punto flotante (Principio VI); falla ruidosamente ante un
dato que no cumple la invariante en vez de cobrar un monto equivocado.

**Alternatives considered**: `round(float(price) * 100)` — descartado: el punto flotante es
justamente lo que la constitución prohíbe para dinero.

## R3: `Idempotency-Key` determinista por periodo

**Decision**: `f"clinic-subscription:{clinic_subscription_id}:{period}"`, donde `period` es la fecha
(`YYYY-MM-DD`) de `next_billing_at` **en el momento de disparar el cobro** (antes de avanzarla). Dos
disparos para el mismo periodo (mismo `clinic_subscription_id` + mismo `next_billing_at`) producen
siempre la misma clave; un disparo de un periodo distinto (tras un cobro aprobado que ya avanzó
`next_billing_at`) produce una clave distinta.

**Rationale**: Cumple el contrato de Pagos (`Idempotency-Key`, string de 1 a 100 caracteres) y FR-010
sin guardar un contador ni un UUID adicional: el periodo ya identifica unívocamente el cobro dentro
de una suscripción de clínica.

**Alternatives considered**: Una clave aleatoria guardada tras el primer intento — funciona igual,
pero exige una escritura de reserva antes de llamar a Pagos (más compleja) para que un segundo
intento concurrente la reutilice; la clave determinista no necesita ese paso.

## R4: Referencia opaca hacia Pagos

**Decision**: `resource_type = "system-api:clinic-subscription"` (constante); `resource_id =
str(clinic_subscription.id)` (el entero propio, como texto; cumple `minLength: 1, maxLength: 200` del
contrato de Pagos).

**Rationale**: Namespaced como exige el Principio X de Pagos; distingue este recurso del catálogo de
planes (que esta especificación no cobra directamente) si en el futuro alguien integrara también ese
recurso.

## R5: Cliente de Pagos (`PaymentsApiClient`)

**Decision**: Mismo patrón que `ClinicsApiClient`/`UsersApiClient` (`src/integrations/payments_api.py`,
constructor con `http_client`, `base_url`, `timeout_seconds`); dos métodos:
`create_payment(token, idempotency_key, …) -> PaymentView` (`POST /api/v1/payments`) y
`get_payment(token, payment_id) -> PaymentView` (`GET /api/v1/payments/{id}`). Excepciones propias en
`src/integrations/errors.py`: `PaymentsApiRejectedToken(code)` (401 de Pagos, que a su vez reenvió el
rechazo de Usuarios), `PaymentsApiPermissionDenied` (403, distinto de un token inválido: con el
permiso `payments:write`/`payments:read` ausente en Usuarios), `PaymentsApiIdempotencyConflict` (409,
la misma `Idempotency-Key` con datos distintos — FR edge case) y `PaymentsApiUnavailable` (todo lo
demás: tiempo agotado, 503, 5xx, cuerpo inesperado, redirección).

**Rationale**: Reutiliza exactamente el estilo que ya existe (asyncio.timeout, sin reintentos, nunca
sigue redirecciones, nunca registra el token) y separa el conflicto de idempotencia (que la
especificación trata como un caso de negocio, no como «no disponible») del resto de fallas.

**Alternatives considered**: Tratar el 409 de idempotencia como «no disponible» (503) — descartado:
el edge case de la especificación lo define como su propio resultado, útil para quien integra
(sabría que cambió el precio entre dos intentos), no como una duda de disponibilidad.

## R6: Catálogo de estatus de la suscripción de clínica

**Decision**: Tabla `clinic_subscription_statuses` (mismo patrón que `subscription_statuses`,
administrada a mano): `1 Activa`, `2 Con cobro pendiente de resolver`, `3 Cancelada`. El estatus 2
cubre tanto un cobro `pending` (en curso) como uno `rejected`/`cancelled` (que necesita un nuevo
intento): ambos son «hay algo que atender en esta suscripción», que es lo único que FR-002 y la
historia 3 (escenario 4) exigen distinguir de «al día» (Activa).

**Rationale**: Reutiliza el patrón ya probado de `subscription_statuses` en vez de inventar un
esquema de estados distinto; un solo campo basta porque la especificación nunca pide distinguir
«pendiente» de «rechazado» en el estatus de la suscripción (sí en el del cobro, que es otra tabla).

**Alternatives considered**: Derivar el estatus solo del último cobro, sin columna propia — descartado
porque una suscripción puede no tener ningún cobro todavía (recién creada, antes del primer disparo)
y seguir siendo Activa; una columna explícita es más simple de filtrar (FR-007) que una subconsulta
en cada lectura.

## R7: Cuándo se puede disparar un cobro (elegibilidad)

**Decision** (revisada durante la implementación: ver «Corrección» abajo): una suscripción de
clínica es elegible para un nuevo cobro cuando su estatus **no es Cancelada**. Eso es todo lo que
se comprueba localmente antes de llamar a Pagos.

**Corrección sobre la primera lectura**: la primera versión de esta decisión también exigía «sin un
cobro vigente en `pending`», pensando que así se cumplía la historia 2 (escenario 3: «Cancelada, o
con un cobro ya aprobado y vigente, se rechaza»). Al implementarlo, esa condición extra contradecía
la propia historia 2 (escenario 2): un reintento del mismo periodo (p. ej. tras un corte de red)
**debe** volver a llegar a Pagos con la misma `Idempotency-Key` y recibir el mismo pago, nunca un
409 local. Como el periodo (`next_billing_at`) solo avanza cuando un cobro se aprueba (research R6),
«un cobro `approved` que ya cubra el periodo actual» no puede ocurrir en la práctica: en cuanto se
aprueba, el periodo ya avanzó. Por tanto la única condición real es Cancelada; un cobro `pending` o
`rejected` del periodo vigente **nunca** bloquea un nuevo intento, se deja que Pagos decida (siempre
idempotente). Antes de decidir, `charge()` sincroniza el cobro vigente si está `pending` (igual que
una lectura, research R8): así un cobro ya resuelto en otro lugar avanza el periodo antes de
reintentar, en vez de reintentar sobre un periodo que ya quedó pagado.

**Rationale**: Es la lectura literal de la historia 2 (escenarios 2 y 3 juntos, no por separado) y
de FR-008: «Cancelada» es la única condición verdaderamente bloqueante; «con un cobro pendiente de
resolver» en FR-008 describe el *estatus visible* de la suscripción (estatus 2, que un cobro
`pending` o `rejected` produce), no una regla de rechazo adicional sobre el propio disparo del cobro.

## R8: Sincronización del estatus al consultar (sin tarea en segundo plano)

**Decision**: Al leer una suscripción de clínica o un cobro cuyo cobro vigente está `pending`, el
`Service` llama primero a `PaymentsApiClient.get_payment`; si Pagos responde, traduce el nuevo
estatus y lo persiste (una escritura dentro de la misma operación de lectura) antes de construir la
respuesta; si Pagos no responde (`PaymentsApiUnavailable`), se registra una advertencia y se devuelve
el estatus local tal cual (nunca se falla la lectura completa por esto: FR-017). Un cobro que ya no
está `pending` nunca dispara esta llamada.

**Rationale**: Cumple la historia 3 sin un proceso periódico propio (que la especificación reserva
para la automatización diferida, FR-029) y sin inventar un endpoint de «sincronizar» aparte que nadie
pediría llamar.

**Alternatives considered**: Un endpoint `POST .../charges/{id}/sync` explícito — descartado por
redundante: nada en la especificación distingue «leer» de «leer ya actualizado»; añadir un paso
manual solo complicaría el flujo de la historia 3.

**Credenciales de la sincronización**: el token de quien disparó el cobro no se guarda (Principio
VIII: este servicio nunca guarda tokens) y, para cuando alguien vuelve a leer la suscripción, puede
haber vencido. `GET /api/v1/payments/{id}` de Pagos exige igualmente un token con `payments:read`
(su Principio VIII), así que la sincronización usa una credencial de **aplicación** propia de este
servicio (`PAGOS_API_SERVICE_TOKEN`, variable de entorno — contracts/payments-api-integration.md),
no el token de quien lee. Es un token de Auth0 como cualquier otro (de una cuenta con `payments:read`
en Usuarios): no exige ningún cambio en Pagos ni en Usuarios, solo que esa cuenta exista y tenga el
permiso, igual que cualquier persona. Sin esa variable configurada, la sincronización se omite
(se devuelve el último estatus local) y se registra una advertencia al arrancar, nunca un error que
impida arrancar (es una mejora, no un requisito, igual que `CLINICS_API_BASE_URL`).

## R9: Simulación de Pagos en las pruebas

**Decision**: `tests/stubs/payments_api/app.py`, autocontenido (sin importar `src/`), con el mismo
estilo que `tests/stubs/users_api/app.py` y `tests/stubs/clinics_api/app.py`: `POST /api/v1/payments`
(valida `Idempotency-Key`, guarda el pago en memoria con estatus `pending` y un `checkout_url`
determinista) y `GET /api/v1/payments/{id}`, más rutas `/__test__/` para registrar tokens con
permisos y `tenant_id`, provocar fallas (`unavailable`, `forbidden`, `slow`, `not_json`…) y mover a
mano el estatus de un pago (`pending` → `approved`/`rejected`/`cancelled`) para probar la historia 3.
`tests/stubs/users_api/app.py` gana `GET /api/v1/authorization/me` (con `tenant_id` y permisos por
rol, igual que el contrato real) sin tocar su `GET /api/v1/authorization/check` existente.

**Rationale**: Mismo patrón que ya usan las specs 001 y 005 para no depender de los servicios reales
(Principio V); separa el stub de Pagos del de Usuarios porque son contratos y fallas distintas.
